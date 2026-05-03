"""Merge rows from every upstream dataset."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  

def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    strategy = (cfg.get("strategy") or "concat").lower()
    out: list[dict] = []
    for up in incoming.values():
        if isinstance(up, dict) and isinstance(up.get("rows"), list):
            out.extend(up["rows"])
    if strategy == "union":
        # Naive union: dedupe on the JSON repr of each row.
        seen: set = set()
        deduped = []
        for r in out:
            key = repr(sorted(r.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        out = deduped
    return {"rows": out, "rowCount": len(out), "strategy": strategy}
  
NODE_SPEC = _spec_from_yaml(_HERE / "data_merge.yaml", run)
  