"""Issue an HTTP request and normalize the response into rows."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import asyncio
import json as _json

import httpx


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    url = cfg.get("url")
    if not url:
        return {"error": "No URL configured", "rows": [], "rowCount": 0}
    method = (cfg.get("method") or "GET").upper()
    headers: dict[str, str] = {}
    raw_h = cfg.get("headers")
    if isinstance(raw_h, str) and raw_h.strip():
        try:
            headers = _json.loads(raw_h)
        except Exception:
            headers = {}
    elif isinstance(raw_h, dict):
        headers = raw_h
    body = cfg.get("body")
    if method != "GET" and body:
        headers.setdefault("Content-Type", "application/json")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=headers, content=body if isinstance(body, str) else None)
        ct = resp.headers.get("content-type", "")
        data = resp.json() if "json" in ct else resp.text
    except Exception as exc:
        raise RuntimeError(f"HTTP error: {exc}")

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data["data"]
    elif isinstance(data, dict):
        rows = [data]
    else:
        rows = [{"response": data}]

    return {"url": url, "method": method, "status": resp.status_code, "rows": rows, "rowCount": len(rows), "data": data}
  
NODE_SPEC = _spec_from_yaml(_HERE / "http.yaml", run)
  