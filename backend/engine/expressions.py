"""
Safe row-expression evaluator.

The TS code allowed arbitrary JS via `new Function`. We do the same
spirit in Python, but constrain the global namespace so users can write
`row.score >= 75` or `row['quantity'] * row['unit_price']` without
shipping a full sandbox.

Two modes mirroring the TS evaluator:

  * boolean (default) — used by `filter`, `condition`, `evaluator`.
    Returns False on any exception so a single bad row never crashes
    a 10k-row pipeline.
  * raw                — used by `map_transform`. Returns the raw value
    or None on exception.

We translate JS-isms ('===', '!==', 'true', 'false', 'null', '&&', '||',
'!') to Python equivalents so Copilot-generated and human-written
JS-style expressions both work.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class _RowProxy:
    """Lets expressions write `row.foo` and `row['foo']`."""
    __slots__ = ("_d",)

    def __init__(self, d: dict[str, Any]) -> None:
        self._d = d

    def __getattr__(self, name: str) -> Any:
        return self._d.get(name)

    def __getitem__(self, name: str) -> Any:
        return self._d.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._d


_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
    "round": round, "int": int, "float": float, "str": str,
    "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "any": any, "all": all, "sorted": sorted, "reversed": reversed,
    "range": range, "enumerate": enumerate, "zip": zip,
    "True": True, "False": False, "None": None,
}


def _js_to_py(expr: str) -> str:
    """Best-effort JS → Python coercion. Tokens only."""
    # Preserve string literals, swap operators between them.
    parts = re.split(r"(\".*?\"|'.*?')", expr)
    for i, part in enumerate(parts):
        if part.startswith(('"', "'")):
            continue
        # boolean / null literals
        part = re.sub(r"\btrue\b", "True", part)
        part = re.sub(r"\bfalse\b", "False", part)
        part = re.sub(r"\bnull\b", "None", part)
        part = re.sub(r"\bundefined\b", "None", part)
        # equality
        part = part.replace("===", "==").replace("!==", "!=")
        # logical operators (avoid double-replacement)
        part = re.sub(r"&&", " and ", part)
        part = re.sub(r"\|\|", " or ", part)
        # unary not — only when followed by space, identifier, or paren, not "!="
        part = re.sub(r"(?<![=!<>])!(?=[\s\w(])", " not ", part)
        parts[i] = part
    return "".join(parts)


def eval_row(expr: str, row: dict[str, Any], extra: dict[str, Any] | None = None, *, raw: bool = False) -> Any:
    """Evaluate `expr` against a row dict. Returns False/None on error."""
    if not expr:
        return None if raw else True
    py_expr = _js_to_py(expr)
    locals_ = dict(row)
    if extra:
        locals_.update(extra)
    locals_["row"] = _RowProxy(row)
    try:
        return eval(py_expr, {"__builtins__": _SAFE_BUILTINS}, locals_)  # noqa: S307 — guarded namespace
    except Exception as e:
        logger.debug("eval_row failed for %r: %s", expr, e)
        return None if raw else False


def eval_scalar(expr: str, scope: dict[str, Any] | None = None) -> Any:
    """Evaluate a scalar expression (no row). Used by `condition` when there's no upstream rows."""
    if not expr:
        return False
    try:
        return eval(_js_to_py(expr), {"__builtins__": _SAFE_BUILTINS}, scope or {})  # noqa: S307
    except Exception as e:
        logger.debug("eval_scalar failed for %r: %s", expr, e)
        return False
  