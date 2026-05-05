"""
Self-healing workflow generator (Copilot Layer 1–8).

Mirrors the TS pipeline (artifacts/api-server/src/routes/copilot.ts) so that
the Python backend produces a working workflow in 1–2 attempts instead of 3+:

  1. /pipeline-start            — announce + collect prior workflows for inspiration
  2. plan                       — Gemini drafts a workflow JSON (response_mime_type=json)
  3. extract                    — robust JSON extraction (markdown, fences, brace match)
  4a. validate (schema)         — engine.validator.validate_dag → tagged traceback
  4b. validate (semantic)       — engine.dag_runner.dry_run_workflow + sink/condition checks
  5. repair                     — tagged traceback fed back to Gemini, MAX 2 retries
  6. accept                     — emit final workflow + summary
  7. error                      — emit human-readable failure
  8. complete                   — terminal sentinel

Streams plain dict events (the SSE wrapper is the router's concern).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from ..engine.dag_runner import dry_run_workflow
from ..engine.registry import all_specs
from ..engine.validator import validate_dag

logger = logging.getLogger(__name__)
MAX_REPAIR_ATTEMPTS = 2  # matches TS: 1 initial + 2 repairs = 3 total


# ── Gemini bootstrap ──────────────────────────────────────────────────────────

def _model():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Force JSON output and low temperature for deterministic planning,
        # matching the TS side's generationConfig.
        return genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        )
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


# ── Prompt building ───────────────────────────────────────────────────────────

def _node_registry() -> dict[str, str]:
    """Compact registry: { type_id: '[category] description' }."""
    out: dict[str, str] = {}
    for s in all_specs():
        cat = (s.ui or {}).get("category") or "general"
        out[s.type_id] = f"[{cat}] {s.description}"
    return out


def _node_field_keys() -> str:
    """Authoritative per-type required/optional config field list."""
    lines: list[str] = []
    for s in all_specs():
        if not s.params:
            lines.append(f"- {s.type_id}: (no config)")
            continue
        parts = [f"{p.name}{'*' if p.required else ''}" for p in s.params]
        lines.append(f"- {s.type_id}: {', '.join(parts)}   (* = required)")
    return "\n".join(lines)


# Hardcoded dataset awareness. Source-of-truth is the CSVs that ship in the
# TS api-server data dir; if the seed CSVs change, update here.
_DATASET_SCHEMAS = """orders.csv (20 rows):
  columns: order_id, customer_email, product_sku, quantity, unit_price, total, status, region, date
  status values: "delivered" | "shipped" | "processing" | "cancelled"
  region values: "North" | "East" | "West" | "South"

products.csv (20 rows):
  columns: sku, name, category, price, cost, stock, active, rating, supplier

leads.csv (20 rows):
  columns: lead_id, first_name, last_name, email, company, industry, country, score, stage, created_at
  stage values: "new" | "contacted" | "qualified" | "proposal" | "negotiation"

employees.csv (15 rows):
  columns: employee_id, name, department, role, salary, hire_date, country, active, performance
  performance values: "exceeds" | "meets" | "below"

transactions.csv (20 rows):
  columns: tx_id, date, merchant, category, amount, type, account, currency, country
  type values: "debit" | "credit"
"""

_NODE_CONFIG_EXAMPLES = """Worked examples for the trickier nodes. Field names here MUST match the
<node_field_keys> block above (which is the source of truth).

csv_extract:
  { "source": "orders.csv" }                         // exact filename from <dataset_schemas>

filter:
  { "expression": "row.score >= 75" }                // JS-style; row.COLUMN available

map_transform:
  { "mappings": [
      { "to": "revenue", "expression": "row.quantity * row.unit_price" },
      { "to": "full_name", "expression": "row.first_name + ' ' + row.last_name" },
      { "from": "old_col", "to": "new_col" }          // rename without expression
  ]}

select_columns:
  { "columns": "col1,col2,col3" }                    // comma-separated string

sort:
  { "sortBy": "salary", "order": "asc" }             // order: "asc" | "desc"

group_by:
  { "groupBy": "region",                             // SINGLE column name string (NOT array)
    "aggregateCol": "total",
    "aggregateFn": "sum",                            // "sum" | "avg" | "min" | "max" | "count"
    "alias": "total_revenue" }

join:
  { "leftKey": "product_sku",                        // camelCase — column from LEFT dataset
    "rightKey": "sku",                               // camelCase — column from RIGHT dataset
    "joinType": "inner" }                            // camelCase — "inner" | "left" | "right" | "outer"
  NOTE: orders-products join → leftKey:"product_sku", rightKey:"sku"

deduplicate:
  { "key": "email" }

data_merge:
  { "strategy": "concat" }                           // "concat" | "union"

excel_output:
  { "tabNames": "Regional Revenue,Summary",          // comma-separated sheet names (string, NOT array)
    "filename": "report.xlsx" }

condition:
  { "expression": "row.status === 'delivered'" }
  // condition node has TWO outputs — sourceHandle "true" and "false".
  // Edges from a condition MUST set sourceHandle: "true" or "false" so the
  // engine routes rows to the right downstream branch. Forgetting this means
  // BOTH branches receive the SAME rows, which is a logic bug.

agent:
  // AI Agent — hardcoded to Gemini (gemini-2.5-flash) using server's GOOGLE_API_KEY.
  // Aggregate mode (DEFAULT, cheaper):
  //   { "prompt": "You are a sales analyst. Be concise.",
  //     "task": "Summarize the top 3 trends" }
  // Per-row mode:
  //   { "prompt": "Classify the lead intent in one word: hot|warm|cold.",
  //     "perRow": true,
  //     "rowTemplate": "Lead: {{first_name}} from {{company}}, score {{score}}",
  //     "outputColumn": "intent",
  //     "maxRows": 5 }

code:
  { "code": "return rows.filter(r => r.active === true)" }
  // Receives `rows` array. MUST return an array. Vanilla JS only.

=== WORKFLOW PATTERNS ===

ROUTER (3+ buckets) — use a "router" node, NOT chained conditions:
  config: { "routes": [
    { "label": "electronics", "condition": "row.category === 'Electronics'" },
    { "label": "accessories", "condition": "row.category === 'Accessories'" },
    { "label": "default",     "condition": "true" }
  ]}
  edges from a router MUST set sourceHandle to the matching label.

DUAL BRANCH (true/false) — use a "condition" node with two edges:
  { "source": "cond1", "target": "branch_a", "sourceHandle": "true" },
  { "source": "cond1", "target": "branch_b", "sourceHandle": "false" }

Forgetting sourceHandle on router/condition outputs is the #1 cause of
validator rejection — both branches will silently receive the SAME rows.
"""


def _system_prompt(
    existing: list[dict],
    history: list[dict],
    message: str,
    corrector_trace: str | None,
) -> str:
    history_str = "\n".join(
        f"{'User' if h.get('role') == 'user' else 'Assistant'}: {h.get('content', '')}"
        for h in history[-8:]
    ) or "No prior conversation"

    corrector_block = (
        f"\n<corrector_traceback>\nCRITICAL: Your previous attempt failed validation. "
        f"Fix the EXACT issue below and regenerate the WHOLE plan.\n{corrector_trace}\n</corrector_traceback>\n"
        if corrector_trace
        else ""
    )

    registry = _node_registry()
    field_keys = _node_field_keys()

    existing_str = (
        "\n".join(f"- \"{w.get('name')}\": {w.get('description') or 'no description'}" for w in existing[:15])
        or "None yet"
    )

    return f"""You are the dbSherpa Studio Copilot — an AI workflow architect.
{corrector_block}
<node_registry>
{json.dumps(registry, indent=2)}
</node_registry>

<node_field_keys>
AUTHORITATIVE: these are the EXACT config keys for every node type, generated
from the node-spec registry. If a key isn't listed here, the node ignores it.
{field_keys}
</node_field_keys>

<dataset_schemas>
IMPORTANT: Use ONLY these exact column names when writing configs.

{_DATASET_SCHEMAS}
</dataset_schemas>

<node_config_examples>
{_NODE_CONFIG_EXAMPLES}
</node_config_examples>

<existing_workflows>
{existing_str}
</existing_workflows>

<conversation_history>
{history_str}
</conversation_history>

<layout_rules>
- Triggers:           x = 60
- Data source nodes:  x = 320  (one per CSV, stacked vertically: y=180, y=380, y=580 …)
- Transform nodes:    x = 600  (stacked vertically: y=180, y=380 …)
- Output nodes:       x = 900
- Vertical spacing:   200 px between sibling nodes at the same x
</layout_rules>

<constraints>
1. ONLY use node types EXACTLY as written in <node_registry>. DO NOT invent types.
2. csv_extract config.source must be an exact filename from <dataset_schemas>.
3. code config.code must be valid JS that receives a `rows` array and returns an array.
4. Every node must be connected. Graph must be acyclic (no cycles).
5. Use config field names EXACTLY as shown in <node_field_keys> — these are camelCase, not snake_case.
6. condition / router edges MUST set sourceHandle. Otherwise both branches receive the same rows.
7. The terminal node should produce the user's requested output (usually excel_output if they asked for an Excel file).
8. thinking_steps: 3-6 short action phrases.
9. workflow is null only when intent is answer_question.
10. answer should be warm and explain what the workflow does step by step.
</constraints>

User message: {message}

Respond ONLY with valid JSON (no markdown, no code fences):
{{
  "intent": "create_workflow" | "answer_question",
  "answer": "string",
  "thinking_steps": ["string"],
  "workflow": {{
    "name": "string",
    "description": "string",
    "nodes": [{{ "id": "n1", "type": "type_from_registry", "label": "string", "config": {{}}, "position": {{ "x": 60, "y": 280 }} }}],
    "edges": [{{ "id": "e1", "source": "n1", "target": "n2", "sourceHandle": "true" }}]
  }} | null
}}"""


# ── JSON extraction (robust for fenced + brace-matched output) ────────────────

_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    # Direct parse — the model is now in JSON-mode so this is the common path
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _FENCED_JSON.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


# ── Gemini call (sync SDK in a thread) ────────────────────────────────────────

async def _generate(model, prompt: str) -> str:
    if model is None:
        # Stub for environments without GOOGLE_API_KEY.
        return json.dumps({
            "intent": "create_workflow",
            "answer": "Set GOOGLE_API_KEY in Replit Secrets to enable AI planning. Returning a tiny demo workflow.",
            "thinking_steps": ["Loading stub workflow"],
            "workflow": {
                "name": "Stub Workflow",
                "description": "Demo workflow (no Gemini key configured).",
                "nodes": [
                    {"id": "n1", "type": "manual_trigger", "label": "Start", "config": {}, "position": {"x": 60, "y": 280}},
                    {"id": "n2", "type": "csv_extract", "label": "Load Leads", "config": {"source": "leads.csv"}, "position": {"x": 320, "y": 280}},
                    {"id": "n3", "type": "filter", "label": "Hot Leads", "config": {"expression": "row.score >= 80"}, "position": {"x": 600, "y": 280}},
                    {"id": "n4", "type": "csv_output", "label": "Output", "config": {"filename": "hot_leads.csv"}, "position": {"x": 900, "y": 280}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                    {"id": "e3", "source": "n3", "target": "n4"},
                ],
            },
        })
    resp = await asyncio.to_thread(model.generate_content, prompt)
    return getattr(resp, "text", "") or ""


# ── Layer 4b: Semantic dry-run with detailed feedback ─────────────────────────

async def _semantic_dry_run(workflow: dict) -> str | None:
    """Return None if the workflow is semantically sound, else a traceback string."""
    nodes = workflow.get("nodes") or []
    edges = workflow.get("edges") or []
    if not nodes:
        return "Workflow has zero nodes."

    try:
        result = await dry_run_workflow(nodes, edges)
    except Exception as exc:
        return f"Dry-run crashed: {exc}"

    # Any failed node → traceback
    failed = next((l for l in result.get("logs", []) if l.get("status") == "failed"), None)
    if failed:
        return (
            f"Node {failed.get('nodeId')!r} ({failed.get('nodeType')}) threw during execution: "
            f"{failed.get('error')}"
        )

    output_map = result.get("outputMap") or {}
    has_outgoing = {e.get("source") for e in edges}
    sinks = [n for n in nodes if n["id"] not in has_outgoing]

    for sink in sinks:
        out = output_map.get(sink["id"])
        if not out:
            continue
        if sink["type"] == "note" or sink["type"].endswith("_trigger"):
            continue
        rows = out.get("rows") if isinstance(out, dict) else None
        rows_written = out.get("rowsWritten") if isinstance(out, dict) else None
        row_count = len(rows) if isinstance(rows, list) else (rows_written if rows_written is not None else None)
        if row_count == 0:
            return (
                f"Terminal node {sink['id']!r} ({sink['type']}) produced 0 rows. The pipeline "
                f"is logically broken — likely a filter expression that excludes all rows, a code "
                f"block returning empty, or an upstream join with no matching keys. Re-examine the "
                f"dataset columns in <dataset_schemas> and fix the offending node."
            )

    # Condition routing sanity: both branches getting all-or-nothing.
    for n in nodes:
        if n.get("type") != "condition":
            continue
        out = output_map.get(n["id"]) or {}
        true_rows = out.get("rows_true") if isinstance(out, dict) else None
        false_rows = out.get("rows_false") if isinstance(out, dict) else None
        t_n = len(true_rows) if isinstance(true_rows, list) else 0
        f_n = len(false_rows) if isinstance(false_rows, list) else 0
        total = t_n + f_n
        if total > 0 and (t_n == 0 or f_n == 0):
            expr = (n.get("config") or {}).get("expression")
            return (
                f"Condition {n['id']!r} with expression {expr!r} routed ALL {total} rows to one "
                f"side (true={t_n}, false={f_n}). Either the expression is too broad/narrow, or "
                f"the user wanted both branches populated. Fix the expression to actually split "
                f"the data."
            )

    return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_pipeline(
    message: str,
    history: list[dict],
    existing: list[dict],
    queue: asyncio.Queue,
) -> None:
    """Drive the planner + repair loop, emitting events into the queue."""
    await queue.put({"type": "status", "stage": "pipeline-start", "message": "Drafting workflow..."})

    model = _model()
    if model is None and not os.getenv("GOOGLE_API_KEY"):
        await queue.put({
            "type": "warning",
            "stage": "init",
            "message": "GOOGLE_API_KEY not set — returning stub workflow.",
        })

    workflow: dict | None = None
    plan: dict | None = None
    last_error = ""
    healing_steps: list[str] = []
    total_attempts = MAX_REPAIR_ATTEMPTS + 1  # 1 initial + N repairs

    for attempt in range(total_attempts):
        if attempt == 0:
            await queue.put({"type": "status", "stage": "plan", "message": "Asking Gemini..."})
            corrector_trace: str | None = None
        else:
            await queue.put({
                "type": "status",
                "stage": "repair",
                "attempt": attempt,
                "message": f"Self-healing attempt {attempt}: {last_error[:80]}…",
            })
            corrector_trace = last_error

        prompt = _system_prompt(existing, history, message, corrector_trace)
        text = await _generate(model, prompt)

        await queue.put({"type": "status", "stage": "extract", "message": "Parsing response..."})
        plan = _extract_json(text)
        if not plan:
            last_error = "Gemini returned malformed JSON. Return ONLY a valid JSON object matching the schema."
            await queue.put({"type": "warning", "stage": "extract", "message": last_error})
            healing_steps.append("Gemini output not parseable as JSON")
            continue

        # Q&A intent — no workflow validation needed
        if plan.get("intent") == "answer_question" or not plan.get("workflow"):
            await queue.put({"type": "message", "content": plan.get("answer") or "(no answer)"})
            await queue.put({"type": "complete"})
            return

        workflow = plan["workflow"]

        # Layer 4a — schema validation
        await queue.put({"type": "status", "stage": "validate-schema", "message": "Checking node schema..."})
        schema_err = validate_dag(workflow.get("nodes") or [], workflow.get("edges") or [])
        if schema_err:
            last_error = f"[SCHEMA VIOLATION] {schema_err}"
            await queue.put({"type": "warning", "stage": "validate-schema", "message": last_error})
            healing_steps.append(f"Caught schema issue: {schema_err[:100]}")
            continue

        # Layer 4b — semantic dry run
        await queue.put({"type": "status", "stage": "validate-semantic", "message": "Performing dry run..."})
        sem_err = await _semantic_dry_run(workflow)
        if sem_err:
            last_error = f"[SEMANTIC FAILURE during dry-run] {sem_err}"
            await queue.put({"type": "warning", "stage": "validate-semantic", "message": last_error})
            healing_steps.append(f"Dry-run found: {sem_err[:100]}")
            continue

        # Layer 6 — accept
        attempts_used = attempt + 1
        if attempts_used == 1:
            await queue.put({"type": "status", "stage": "validated", "message": "Validated on first attempt ✓"})
        else:
            await queue.put({
                "type": "status",
                "stage": "validated",
                "message": f"Validated after {attempts_used} attempt(s) ✓",
            })

        await queue.put({"type": "workflow", "workflow": workflow})
        await queue.put({
            "type": "message",
            "content": plan.get("answer") or (
                f"Built workflow '{workflow.get('name', 'Untitled')}' with "
                f"{len(workflow.get('nodes') or [])} nodes and "
                f"{len(workflow.get('edges') or [])} edges."
            ),
        })
        await queue.put({"type": "complete", "attempts": attempts_used, "healingSteps": healing_steps})
        return

    # All attempts exhausted — return best-effort if we have one
    if workflow:
        healing_steps.append(f"Exhausted {total_attempts} attempts; returning best-effort plan.")
        await queue.put({"type": "warning", "stage": "exhausted", "message": last_error})
        await queue.put({"type": "workflow", "workflow": workflow})
        await queue.put({
            "type": "message",
            "content": (plan.get("answer") if plan else None) or
                       f"Best-effort workflow after {total_attempts} attempts. Last issue: {last_error}",
        })
        await queue.put({"type": "complete", "attempts": total_attempts, "healingSteps": healing_steps})
        return

    await queue.put({
        "type": "error",
        "stage": "exhausted",
        "message": f"Could not produce a valid workflow after {total_attempts} attempts. Last error: {last_error}",
    })
