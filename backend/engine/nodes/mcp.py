"""Generic MCP tool invocation. Stubbed when MCP_SERVER_URL is missing."""
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
    server = cfg.get("serverUrl") or os.getenv("MCP_SERVER_URL")
    tool = cfg.get("tool")
    rows = _upstream_rows(incoming)
    if not server:
        return {
            "simulated": True, "needsIntegration": "mcp",
            "tool": tool, "message": "Set MCP_SERVER_URL to enable.",
            "rows": rows, "rowCount": len(rows),
        }
    raw = cfg.get("params")
    params = raw if isinstance(raw, dict) else (_json.loads(raw) if raw else {})
    if rows:
        params["data"] = rows
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{server.rstrip('/')}/tools/{tool}/run", json={"params": params})
    if resp.status_code >= 400:
        raise RuntimeError(f"MCP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if isinstance(data, list):
        out_rows = data
    elif isinstance(data, dict) and isinstance(data.get("rows"), list):
        out_rows = data["rows"]
    else:
        out_rows = [data]
    return {"tool": tool, "rows": out_rows, "rowCount": len(out_rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "mcp.yaml", run)
  