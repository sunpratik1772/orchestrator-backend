"""Sort rows by a column ascending or descending."""
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
    key = cfg.get("sortBy")
    order = (cfg.get("order") or "asc").lower()
    rows = _upstream_rows(incoming)
    if not key:
        return {"rows": rows, "rowCount": len(rows)}

    def _k(r):
        v = r.get(key)
        # Make None sort last consistently.
        return (v is None, v)

    sorted_rows = sorted(rows, key=_k, reverse=(order == "desc"))
    return {"rows": sorted_rows, "rowCount": len(sorted_rows), "sortBy": key, "order": order}
  
NODE_SPEC = _spec_from_yaml(_HERE / "sort.yaml", run)
  