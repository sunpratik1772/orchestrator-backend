"""Surface a final response (string or rows)."""
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
    template = cfg.get("content") or cfg.get("template") or ""
    rows = _upstream_rows(incoming)
    content = template if template else (rows if rows else (next(iter(incoming.values()), {}) if incoming else {}))
    return {"response": content, "rows": rows, "rowCount": len(rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "response.yaml", run)
  