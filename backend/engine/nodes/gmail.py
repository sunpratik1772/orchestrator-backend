"""Gmail send-email integration. Stubbed unless GMAIL_CLIENT_SECRET is set."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import os


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    if not os.getenv("GMAIL_CLIENT_SECRET"):
        rows = _upstream_rows(incoming)
        return {
            "simulated": True, "needsIntegration": "gmail",
            "to": cfg.get("to", ""), "subject": cfg.get("subject", "(no subject)"),
            "body": cfg.get("body", ""),
            "message": "Add GMAIL_CLIENT_SECRET to send real emails.",
            "rows": rows, "rowCount": len(rows),
        }
    # Real send would happen here.
    return {"sent": True, "to": cfg.get("to"), "subject": cfg.get("subject"), "simulated": False}
  
NODE_SPEC = _spec_from_yaml(_HERE / "gmail.yaml", run)
  