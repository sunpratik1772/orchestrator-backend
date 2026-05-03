"""Drop duplicate rows by a key column (keeps first seen)."""
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
    key = cfg.get("key")
    rows = _upstream_rows(incoming)
    if not key:
        return {"rows": rows, "rowCount": len(rows)}
    seen: set = set()
    out = []
    for r in rows:
        k = r.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return {"rows": out, "rowCount": len(out), "removed": len(rows) - len(out), "key": key}
  
NODE_SPEC = _spec_from_yaml(_HERE / "deduplicate.yaml", run)
  