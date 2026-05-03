"""Execute user-provided Python on the rows. Sandboxed via restricted builtins."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import logging

logger = logging.getLogger(__name__)


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


_SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs,
    "sorted": sorted, "reversed": reversed, "list": list, "dict": dict,
    "set": set, "tuple": tuple, "any": any, "all": all, "round": round,
    "int": int, "float": float, "str": str, "bool": bool, "range": range,
    "enumerate": enumerate, "zip": zip, "filter": filter, "map": map,
    "True": True, "False": False, "None": None,
}


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    code_text = cfg.get("code") or ""
    rows = _upstream_rows(incoming)
    locals_ = {"rows": rows, "result": None}
    if not code_text.strip():
        return {"rows": rows, "rowCount": len(rows)}
    try:
        exec(code_text, {"__builtins__": _SAFE_BUILTINS}, locals_)  # noqa: S102 — restricted globals
    except Exception as exc:
        logger.exception("code node failed")
        return {"rows": rows, "rowCount": len(rows), "error": str(exc)}
    out = locals_.get("result")
    if out is None:
        out = locals_.get("rows", rows)
    if not isinstance(out, list):
        out = [out]
    return {"rows": out, "rowCount": len(out)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "code.yaml", run)
  