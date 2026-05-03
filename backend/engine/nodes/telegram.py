"""Telegram send via Bot API. Falls back to a stub when no bot token + chat_id are set.

Auth precedence:
  1. botToken config param OR TELEGRAM_BOT_TOKEN env → POST https://api.telegram.org/bot<token>/sendMessage
  2. Neither → return {simulated: true} stub so the workflow can still run end-to-end in dev

chat_id resolution:
  cfg.chatId → TELEGRAM_CHAT_ID env → required (errors if missing in real-send mode)
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


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    token = cfg.get("botToken") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = cfg.get("chatId") or os.getenv("TELEGRAM_CHAT_ID")
    parse_mode = cfg.get("parseMode") or "Markdown"
    rows = _upstream_rows(incoming)
    msg = cfg.get("message") or (
        f"New data: {_json.dumps(rows[0], default=str)[:200]}" if rows else "Workflow completed"
    )

    if not token:
        return {
            "simulated": True,
            "needsIntegration": "telegram",
            "chatId": chat_id,
            "message": msg,
            "note": "Set TELEGRAM_BOT_TOKEN (and TELEGRAM_CHAT_ID, or pass chatId in config) to send real messages.",
            "rows": rows,
            "rowCount": len(rows),
        }

    if not chat_id:
        return {
            "sent": False,
            "error": "missing_chat_id",
            "note": "Set TELEGRAM_CHAT_ID env or pass chatId in node config.",
            "rows": rows,
            "rowCount": len(rows),
        }

    payload: dict[str, Any] = {"chat_id": chat_id, "text": msg}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    result = body.get("result") or {}
    return {
        "sent": bool(body.get("ok")),
        "status": resp.status_code,
        "chatId": chat_id,
        "messageId": result.get("message_id"),
        "date": result.get("date"),
        "error": body.get("description") if not body.get("ok") else None,
        "errorCode": body.get("error_code") if not body.get("ok") else None,
        "rows": rows,
        "rowCount": len(rows),
    }


NODE_SPEC = _spec_from_yaml(_HERE / "telegram.yaml", run)
