"""Route rows to labelled buckets by an expression result."""
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
    expr = cfg.get("expression") or ""
    rows = _upstream_rows(incoming)
    buckets: dict[str, list] = {}
    for r in rows:
        label = str(eval_row(expr, r, raw=True) or "default")
        buckets.setdefault(label, []).append(r)
    return {"buckets": buckets, "rowCount": len(rows), "labels": list(buckets.keys()), "rows": rows}
  
NODE_SPEC = _spec_from_yaml(_HERE / "router.yaml", run)
  