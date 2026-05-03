"""Filter rows by a JS-style expression evaluated per row."""
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
    kept = [r for r in rows if eval_row(expr, r)]
    return {"rows": kept, "rowCount": len(kept), "filtered": len(rows) - len(kept), "expression": expr}
  
NODE_SPEC = _spec_from_yaml(_HERE / "filter.yaml", run)
  