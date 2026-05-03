"""
DAG runner — executes a workflow definition against a RunContext.

Three public entry points:

  * `build_levels(nodes, edges)` — topo-level partition (each level is
    a list of node ids that can run in parallel).
  * `build_incoming_outputs(node_id, edges, output_map)` — the per-node
    upstream map handlers consume.
  * `run_workflow(nodes, edges, ctx, dry_run=False)` — full execution.
    Returns `(status, output_map, logs)`.

Nothing in this file knows about specific node types; new nodes plug in
via the registry (`registry.NODE_HANDLERS`).
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from .context import RunContext
from .registry import NODE_HANDLERS

logger = logging.getLogger(__name__)


# --- Topology ----------------------------------------------------------------
def build_levels(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Kahn's algorithm. Each returned level is a list of node ids that can run in parallel."""
    indeg: dict[str, int] = {n["id"]: 0 for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in indeg and t in indeg:
            indeg[t] += 1
            children[s].append(t)

    ready = deque([nid for nid, d in indeg.items() if d == 0])
    levels: list[list[str]] = []
    visited = 0
    while ready:
        lvl = list(ready)
        ready.clear()
        levels.append(lvl)
        for nid in lvl:
            visited += 1
            for c in children[nid]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    ready.append(c)
    if visited != len(nodes):
        # Cycle or orphans — append remaining nodes as a final level so
        # they still execute and the user sees the failure clearly.
        leftover = [nid for nid, d in indeg.items() if d > 0]
        if leftover:
            levels.append(leftover)
    return levels


def build_incoming_outputs(
    node_id: str, edges: list[dict], output_map: dict[str, Any]
) -> dict[str, Any]:
    """Return {upstream_node_id: upstream_output} for the given node, honouring sourceHandle."""
    incoming: dict[str, Any] = {}
    for e in edges:
        if e.get("target") != node_id:
            continue
        src = e.get("source")
        if src is None or src not in output_map:
            continue
        upstream = output_map[src]
        handle = e.get("sourceHandle")
        if handle and isinstance(upstream, dict) and upstream.get("_type") == "condition":
            # Branch routing: edge from a condition node carries either its
            # `rows_true` or `rows_false` shelf depending on the handle.
            rows_key = "rows_true" if handle == "true" else "rows_false"
            incoming[src] = {"rows": upstream.get(rows_key, []), "rowCount": len(upstream.get(rows_key, []))}
        else:
            incoming[src] = upstream
    return incoming


# --- Execution ---------------------------------------------------------------
async def _call_handler(handler, node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    """Handlers can be sync or async — we adapt either."""
    if inspect.iscoroutinefunction(handler):
        return await handler(node, ctx, incoming)
    return await asyncio.to_thread(handler, node, ctx, incoming)


async def run_workflow(
    nodes: list[dict],
    edges: list[dict],
    ctx: RunContext | None = None,
    *,
    dry_run: bool = False,
    on_event=None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Execute a workflow. Returns (status, output_map, logs)."""
    ctx = ctx or RunContext()
    ctx.values.setdefault("_dry_run", dry_run)
    levels = build_levels(nodes, edges)

    output_map: dict[str, Any] = ctx.output_map
    logs: list[dict[str, Any]] = []
    status: str = "completed"

    if on_event:
        on_event({"type": "workflow_start", "run_id": ctx.run_id, "levels": len(levels)})

    for level_idx, level in enumerate(levels):
        # Run all nodes at this depth concurrently.
        async def _run_one(nid: str):
            node = next((n for n in nodes if n["id"] == nid), None)
            if not node:
                return None
            handler = NODE_HANDLERS.get(node["type"])
            if not handler:
                return _failed_log(node, level_idx, len(level) > 1, f"Unknown node type '{node['type']}'")

            incoming = build_incoming_outputs(nid, edges, output_map)
            t0 = time.time()
            if on_event:
                on_event({"type": "node_start", "node_id": nid, "node_type": node["type"]})
            try:
                output = await _call_handler(handler, node, ctx, incoming)
                rec = {
                    "nodeId": nid,
                    "nodeLabel": node.get("label") or node.get("type"),
                    "nodeType": node["type"],
                    "status": "completed",
                    "output": output,
                    "error": None,
                    "durationMs": int((time.time() - t0) * 1000),
                    "startedAt": datetime.now(timezone.utc).isoformat(),
                    "parallel": len(level) > 1,
                    "level": level_idx,
                }
                if on_event:
                    on_event({"type": "node_complete", "node_id": nid, "duration_ms": rec["durationMs"]})
                return rec
            except Exception as exc:
                logger.exception("Node %s (%s) failed", nid, node["type"])
                rec = _failed_log(node, level_idx, len(level) > 1, str(exc))
                rec["durationMs"] = int((time.time() - t0) * 1000)
                if on_event:
                    on_event({"type": "node_error", "node_id": nid, "error": str(exc)})
                return rec

        results = await asyncio.gather(*[_run_one(nid) for nid in level])
        for r in results:
            if r is None:
                continue
            output_map[r["nodeId"]] = r["output"]
            logs.append(r)
            if r["status"] == "failed":
                status = "failed"

    if on_event:
        on_event({"type": "workflow_complete", "status": status})
    return status, output_map, logs


def _failed_log(node: dict, level_idx: int, parallel: bool, error: str) -> dict:
    return {
        "nodeId": node["id"],
        "nodeLabel": node.get("label") or node.get("type"),
        "nodeType": node["type"],
        "status": "failed",
        "output": {},
        "error": error,
        "durationMs": 0,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "parallel": parallel,
        "level": level_idx,
    }


async def dry_run_workflow(nodes: list[dict], edges: list[dict]) -> dict[str, Any]:
    """In-memory dry run for the Copilot self-healing loop."""
    status, output_map, logs = await run_workflow(nodes, edges, dry_run=True)
    return {"status": status, "outputMap": output_map, "logs": logs}
  