"""Evaluate rows against an expression and surface pass-rate."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
from ..expressions import eval_row


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    criteria = cfg.get("criteria") or "True"
    label = cfg.get("label") or "passed"
    rows = _upstream_rows(incoming)
    passed: list[dict] = []
    failed: list[dict] = []
    for r in rows:
        try:
            ok = bool(eval_row(criteria, r))
        except Exception:
            ok = False
        (passed if ok else failed).append({**r, "_eval": label if ok else "failed"})
    rate = (len(passed) / len(rows) * 100) if rows else 0
    return {
        "rows": passed, "rowCount": len(passed),
        "passed": len(passed), "failed": len(failed),
        "passRate": f"{rate:.1f}%", "criteria": criteria,
    }
  
NODE_SPEC = _spec_from_yaml(_HERE / "evaluator.yaml", run)
  