"""Split rows into true/false branches; output is consumed by sourceHandle on edges."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
from ..expressions import eval_row


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    expr = cfg.get("expression") or "True"
    rows = _upstream_rows(incoming)
    rows_true: list[dict] = []
    rows_false: list[dict] = []
    for r in rows:
        (rows_true if eval_row(expr, r) else rows_false).append(r)
    return {
        "_type": "condition",  # picked up by dag_runner.build_incoming_outputs
        "expression": expr,
        "rows_true": rows_true,
        "rows_false": rows_false,
        "trueCount": len(rows_true),
        "falseCount": len(rows_false),
        "rows": rows_true,  # default fall-through if a successor ignores sourceHandle
        "rowCount": len(rows_true),
    }
  
NODE_SPEC = _spec_from_yaml(_HERE / "condition.yaml", run)
  