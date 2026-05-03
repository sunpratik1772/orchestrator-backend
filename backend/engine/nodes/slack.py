"""Slack incoming-webhook send. Falls back to a stub when no webhook is set."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import json as _json
import os

import httpx


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    webhook = cfg.get("webhookUrl") or os.getenv("SLACK_WEBHOOK_URL")
    rows = _upstream_rows(incoming)
    msg = cfg.get("message") or (f"New data: {_json.dumps(rows[0], default=str)[:200]}" if rows else "Workflow completed")
    if not webhook:
        return {
            "simulated": True, "needsIntegration": "slack",
            "channel": cfg.get("channel", "#general"), "message": msg,
            "note": "Set SLACK_WEBHOOK_URL or pass webhookUrl in config.",
            "rows": rows, "rowCount": len(rows),
        }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook, json={"text": msg, "channel": cfg.get("channel", "#general")})
    return {"sent": resp.status_code < 400, "status": resp.status_code, "channel": cfg.get("channel"), "rows": rows, "rowCount": len(rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "slack.yaml", run)
  