"""Group rows by one column and aggregate another."""
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


def _agg(values: list, fn: str):
    nums = [float(v) for v in values if isinstance(v, (int, float)) or (isinstance(v, str) and _is_num(v))]
    if fn == "count":
        return len(values)
    if not nums:
        return 0
    if fn == "sum": return sum(nums)
    if fn == "avg": return sum(nums) / len(nums)
    if fn == "min": return min(nums)
    if fn == "max": return max(nums)
    return sum(nums)


def _is_num(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    group_col = cfg.get("groupBy")
    agg_col = cfg.get("aggregateCol")
    fn = (cfg.get("aggregateFn") or "sum").lower()
    alias = cfg.get("alias") or f"{fn}_{agg_col}"
    rows = _upstream_rows(incoming)
    if not group_col or not agg_col:
        return {"rows": [], "rowCount": 0, "error": "groupBy and aggregateCol required"}
    buckets: dict[Any, list] = {}
    for r in rows:
        buckets.setdefault(r.get(group_col), []).append(r.get(agg_col))
    out = [{group_col: k, alias: _agg(v, fn)} for k, v in buckets.items()]
    return {"rows": out, "rowCount": len(out), "groupBy": group_col, "aggregateFn": fn}
  
NODE_SPEC = _spec_from_yaml(_HERE / "group_by.yaml", run)
  