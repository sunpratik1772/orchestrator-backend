"""
Self-healing workflow generator (Copilot Layer 1–8).

Mirrors the TS pipeline: plan → schema check → semantic dry run → repair.
Streams progress events into an asyncio.Queue consumed by the SSE router.

Layers:
  1. /pipeline-start            — announce + collect prior workflows for inspiration
  2. plan                       — Gemini drafts a workflow JSON
  3. extract                    — robust JSON extraction (markdown, fences, brace match)
  4a. validate (schema)         — engine.validator.validate_dag
  4b. validate (semantic)       — engine.dag_runner.dry_run_workflow
  5. repair                     — feeds errors back to Gemini, max 3 retries
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
MAX_REPAIR_ATTEMPTS = 3


def _model():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-2.5-flash")
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


def _node_catalogue() -> str:
    """Compact prompt-friendly node catalogue."""
    lines = []
    for s in all_specs():
        params = ", ".join(f"{p.name}{'*' if p.required else ''}" for p in s.params)
        lines.append(f"- {s.type_id}: {s.description} [params: {params or 'none'}]")
    return "\n".join(lines)


def _system_prompt(existing: list[dict]) -> str:
    examples = ""
    if existing:
        sample = existing[0]
        examples = f"\n\nExample existing workflow ({sample.get('name')}):\n" + json.dumps(
            {"nodes": sample.get("nodes", [])[:5], "edges": sample.get("edges", [])[:5]},
            indent=2,
        )
    return f"""You are dbStudio Copilot — a workflow planner for a visual node-based engine.

Available node types:
{_node_catalogue()}

Rules:
* Output ONLY valid JSON: {{ "name": str, "description": str, "nodes": [...], "edges": [...] }}
* Each node has: id (string), type (must be from list above), label (string), config (object with that node's params), position {{x, y}}.
* Each edge has: id, source, target, sourceHandle (optional, only for condition nodes: 'true' or 'false').
* Always start with a trigger (manual_trigger / api_trigger / schedule / webhook_trigger).
* Use absolute positions: x increases left→right (start at 100, step 280), y centred ~300 with 150 vertical offset for branches.
* For condition nodes, ALL outgoing edges MUST have sourceHandle: 'true' or 'false'.
* Filter / map / condition expressions: JS-style, accessible as row.col or row['col'].{examples}
"""


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from possibly-fenced LLM output."""
    if not text:
        return None
    m = _FENCED_JSON.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # brace-match fallback
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


async def _generate(model, prompt: str) -> str:
    """Run Gemini in a thread (blocking SDK)."""
    if model is None:
        # Stub for environments without GOOGLE_API_KEY — produces a tiny demo workflow.
        return json.dumps({
            "name": "Stub Workflow",
            "description": "Set GOOGLE_API_KEY to enable AI planning.",
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "label": "Start", "config": {}, "position": {"x": 100, "y": 300}},
                {"id": "n2", "type": "csv_extract", "label": "Load Leads", "config": {"source": "leads.csv"}, "position": {"x": 380, "y": 300}},
                {"id": "n3", "type": "filter", "label": "Hot Leads", "config": {"expression": "row.score >= 80"}, "position": {"x": 660, "y": 300}},
                {"id": "n4", "type": "response", "label": "Output", "config": {}, "position": {"x": 940, "y": 300}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4"},
            ],
        })
    resp = await asyncio.to_thread(model.generate_content, prompt)
    return getattr(resp, "text", "") or ""


async def run_pipeline(
    message: str,
    history: list[dict],
    existing: list[dict],
    queue: asyncio.Queue,
) -> None:
    """Drive the planner + repair loop, emitting events into the queue."""
    await queue.put({"type": "status", "stage": "pipeline-start", "message": "Drafting workflow..."})

    model = _model()
    system = _system_prompt(existing)
    history_text = "\n".join(f"{h.get('role','user')}: {h.get('content','')}" for h in history[-6:])
    prompt = f"{system}\n\nConversation so far:\n{history_text}\n\nUser request: {message}\n\nReturn JSON now:"

    workflow: dict | None = None
    last_error = ""

    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        if attempt == 0:
            await queue.put({"type": "status", "stage": "plan", "message": "Asking the model..."})
            text = await _generate(model, prompt)
        else:
            await queue.put({"type": "status", "stage": "repair", "attempt": attempt, "message": f"Repair attempt {attempt}..."})
            repair_prompt = (
                f"{prompt}\n\nPrevious attempt failed validation:\n{last_error}\n\n"
                f"Previous workflow JSON:\n{json.dumps(workflow, indent=2) if workflow else '(no JSON extracted)'}\n\n"
                "Return a corrected workflow JSON now."
            )
            text = await _generate(model, repair_prompt)

        await queue.put({"type": "status", "stage": "extract", "message": "Parsing response..."})
        candidate = _extract_json(text)
        if not candidate:
            last_error = "Could not extract JSON from model output."
            await queue.put({"type": "warning", "stage": "extract", "message": last_error})
            continue
        workflow = candidate

        # Layer 4a — schema validation
        await queue.put({"type": "status", "stage": "validate-schema", "message": "Checking node schema..."})
        schema_err = validate_dag(workflow.get("nodes") or [], workflow.get("edges") or [])
        if schema_err:
            last_error = f"Schema error: {schema_err}"
            await queue.put({"type": "warning", "stage": "validate-schema", "message": last_error})
            continue

        # Layer 4b — semantic dry run
        await queue.put({"type": "status", "stage": "validate-semantic", "message": "Performing dry run..."})
        try:
            dry = await dry_run_workflow(workflow.get("nodes") or [], workflow.get("edges") or [])
            if dry["status"] == "failed":
                first_fail = next((l for l in dry["logs"] if l["status"] == "failed"), None)
                last_error = f"Semantic error: {first_fail['error'] if first_fail else 'unknown'}"
                await queue.put({"type": "warning", "stage": "validate-semantic", "message": last_error})
                continue
        except Exception as exc:
            last_error = f"Dry run crashed: {exc}"
            await queue.put({"type": "warning", "stage": "validate-semantic", "message": last_error})
            continue

        # Layer 6 — accept
        await queue.put({"type": "workflow", "workflow": workflow})
        await queue.put({
            "type": "message",
            "content": (
                f"Built workflow '{workflow.get('name', 'Untitled')}' with "
                f"{len(workflow.get('nodes') or [])} nodes and "
                f"{len(workflow.get('edges') or [])} edges."
            ),
        })
        await queue.put({"type": "complete"})
        return

    # All attempts exhausted
    await queue.put({
        "type": "error",
        "stage": "exhausted",
        "message": f"Could not produce a valid workflow after {MAX_REPAIR_ATTEMPTS + 1} attempts. Last error: {last_error}",
    })
  