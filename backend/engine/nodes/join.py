"""SQL-style join of two upstream datasets."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  

def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    lk, rk = cfg.get("leftKey"), cfg.get("rightKey")
    jt = (cfg.get("joinType") or "inner").lower()
    upstream = list(incoming.values())
    if len(upstream) < 2 or not lk or not rk:
        return {"rows": [], "rowCount": 0, "error": "Two upstream datasets and leftKey/rightKey required"}
    left = upstream[0].get("rows") or [] if isinstance(upstream[0], dict) else []
    right = upstream[1].get("rows") or [] if isinstance(upstream[1], dict) else []
    by_right: dict[Any, list[dict]] = {}
    for r in right:
        by_right.setdefault(r.get(rk), []).append(r)

    out: list[dict] = []
    matched_right: set = set()
    for lrow in left:
        kv = lrow.get(lk)
        matches = by_right.get(kv, [])
        if matches:
            for rr in matches:
                out.append({**rr, **lrow})
                matched_right.add(id(rr))
        elif jt in ("left", "outer"):
            out.append(dict(lrow))

    if jt in ("right", "outer"):
        for rr in right:
            if id(rr) not in matched_right:
                out.append(dict(rr))

    return {"rows": out, "rowCount": len(out), "leftKey": lk, "rightKey": rk, "joinType": jt}
  
NODE_SPEC = _spec_from_yaml(_HERE / "join.yaml", run)
  