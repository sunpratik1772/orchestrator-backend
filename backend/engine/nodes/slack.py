"""Slack send. Prefers Bot Token (chat.postMessage); falls back to incoming webhook; stubs if neither is set.

Auth precedence:
  1. SLACK_API_TOKEN_NOW (or SLACK_BOT_TOKEN) → POST https://slack.com/api/chat.postMessage with Bearer auth
  2. webhookUrl param OR SLACK_WEBHOOK_URL env → POST the webhook URL
  3. Neither → return {simulated: true} stub so workflow can still run end-to-end in dev
"""
from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any

import httpx

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def _bot_token() -> str | None:
    return os.getenv("SLACK_API_TOKEN_NOW") or os.getenv("SLACK_BOT_TOKEN")


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    channel = cfg.get("channel", "#general")
    rows = _upstream_rows(incoming)
    msg = cfg.get("message") or (
        f"New data: {_json.dumps(rows[0], default=str)[:200]}" if rows else "Workflow completed"
    )

    token = _bot_token()
    if token:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json={"channel": channel, "text": msg},
            )
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "sent": bool(body.get("ok")),
            "via": "bot_token",
            "status": resp.status_code,
            "channel": channel,
            "ts": body.get("ts"),
            "error": body.get("error"),
            "rows": rows,
            "rowCount": len(rows),
        }

    webhook = cfg.get("webhookUrl") or os.getenv("SLACK_WEBHOOK_URL")
    if webhook:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={"text": msg, "channel": channel})
        return {
            "sent": resp.status_code < 400,
            "via": "webhook",
            "status": resp.status_code,
            "channel": channel,
            "rows": rows,
            "rowCount": len(rows),
        }

    return {
        "simulated": True,
        "needsIntegration": "slack",
        "channel": channel,
        "message": msg,
        "note": "Set SLACK_API_TOKEN_NOW (preferred) or SLACK_WEBHOOK_URL, or pass webhookUrl in config.",
        "rows": rows,
        "rowCount": len(rows),
    }


NODE_SPEC = _spec_from_yaml(_HERE / "slack.yaml", run)
