"""
Pure DAG validation. Zero runtime dependencies (no I/O, no LLM calls).

Used by:
  * the Copilot self-healing loop's Layer 4a (schema check), and
  * any external caller that wants to validate a saved workflow.
"""
from __future__ import annotations

from .registry import NODE_SPECS


def validate_dag(nodes: list[dict], edges: list[dict]) -> str | None:
    """Return None if valid, or a human-readable traceback string."""
    valid_types = set(NODE_SPECS.keys())
    ids = set()
    for n in nodes:
        if n.get("type") not in valid_types:
            return f"Node {n.get('id')!r} has unknown type {n.get('type')!r}"
        if n["id"] in ids:
            return f"Duplicate node id {n['id']!r}"
        ids.add(n["id"])
        spec = NODE_SPECS[n["type"]]
        cfg = n.get("config") or {}
        for p in spec.params:
            if p.required and (cfg.get(p.name) in (None, "", [])):
                return (
                    f"Node {n['id']!r} ({n['type']}) is missing required config "
                    f"field {p.name!r}"
                )
    for e in edges:
        if e.get("source") not in ids:
            return f"Edge {e.get('id')!r} references unknown source {e.get('source')!r}"
        if e.get("target") not in ids:
            return f"Edge {e.get('id')!r} references unknown target {e.get('target')!r}"

    # condition outgoing edges must carry sourceHandle
    by_src = {}
    for e in edges:
        by_src.setdefault(e["source"], []).append(e)
    for n in nodes:
        if n["type"] != "condition":
            continue
        outs = by_src.get(n["id"], [])
        if outs and any(not e.get("sourceHandle") for e in outs):
            return (
                f"Condition node {n['id']!r} has outgoing edges without sourceHandle. "
                f"Each edge from a condition must set sourceHandle: 'true' or 'false'."
            )
    return None
  