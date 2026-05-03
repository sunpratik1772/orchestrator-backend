"""Sleep for a configurable duration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import asyncio


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    ms = int(cfg.get("durationMs") or 500)
    # Guard so a runaway pause cannot stall a CI run forever.
    ms = max(0, min(ms, 60000))
    await asyncio.sleep(ms / 1000)
    rows = _upstream_rows(incoming)
    return {"paused": ms, "rows": rows, "rowCount": len(rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "pause.yaml", run)
  