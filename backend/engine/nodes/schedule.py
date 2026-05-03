"""Cron-style trigger — actual scheduling lives outside the runner."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  

def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    return {"scheduled": True, "cron": cfg.get("cron", "0 * * * *")}
  
NODE_SPEC = _spec_from_yaml(_HERE / "schedule.yaml", run)
  