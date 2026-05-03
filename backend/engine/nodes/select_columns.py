"""Project a subset of columns."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  

def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    raw = cfg.get("columns") or ""
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    rows = _upstream_rows(incoming)
    if not cols:
        return {"rows": rows, "rowCount": len(rows)}
    out = [{c: r.get(c) for c in cols} for r in rows]
    return {"rows": out, "rowCount": len(out), "columns": cols}
  
NODE_SPEC = _spec_from_yaml(_HERE / "select_columns.yaml", run)
  