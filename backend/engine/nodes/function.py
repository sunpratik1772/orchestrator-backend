"""Run Python with access to input + prevOutput. Result placed in `result`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import logging

logger = logging.getLogger(__name__)

_SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs, "sorted": sorted,
    "reversed": reversed, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "any": any, "all": all, "round": round, "int": int, "float": float,
    "str": str, "bool": bool, "range": range, "enumerate": enumerate, "zip": zip,
}


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    code_text = cfg.get("code") or ""
    prev_output = next(iter(incoming.values()), {}) if incoming else {}
    locals_ = {"input": ctx.alert_payload, "prevOutput": prev_output, "result": None}
    if not code_text.strip():
        return {"result": prev_output}
    try:
        exec(code_text, {"__builtins__": _SAFE_BUILTINS}, locals_)  # noqa: S102
    except Exception as exc:
        logger.exception("function node failed")
        return {"error": str(exc), "result": None}
    return {"result": locals_.get("result")}
  
NODE_SPEC = _spec_from_yaml(_HERE / "function.yaml", run)
  