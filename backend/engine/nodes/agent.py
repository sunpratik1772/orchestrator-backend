"""Call Gemini with optional row context. Falls back to a stub when GOOGLE_API_KEY is missing."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import json as _json
import logging
import os
import re

logger = logging.getLogger(__name__)


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def _interpolate(template: str, row: dict[str, Any]) -> str:
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(row.get(m.group(1), "")), template)


def _model(name: str):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(name)
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    rows = _upstream_rows(incoming)
    model_name = cfg.get("model") or "gemini-2.5-flash"
    prompt = cfg.get("prompt") or ""
    task = cfg.get("task") or "Provide a concise summary."

    model = _model(model_name)
    if model is None:
        # Graceful fallback so dry-runs still work without an API key.
        return {
            "model": model_name,
            "response": f"[stub] Would call {model_name} on {len(rows)} rows. Set GOOGLE_API_KEY to enable.",
            "rows": rows,
            "rowCount": len(rows),
            "tokensIn": 0,
            "tokensOut": 0,
            "stub": True,
        }

    if cfg.get("perRow") and rows:
        out_col = cfg.get("outputColumn") or "_ai_response"
        cap = int(cfg.get("maxRows") or 5)
        template = cfg.get("rowTemplate") or _json.dumps(rows[0])
        enriched = []
        in_total = out_total = 0
        for i, r in enumerate(rows):
            if i >= cap:
                enriched.append(r)
                continue
            user_msg = f"{prompt}\n\n{_interpolate(template, r)}".strip()
            try:
                resp = model.generate_content(user_msg)
                text = (getattr(resp, "text", None) or "").strip()
                usage = getattr(resp, "usage_metadata", None)
                in_total += getattr(usage, "prompt_token_count", 0) or 0
                out_total += getattr(usage, "candidates_token_count", 0) or 0
            except Exception as exc:
                text = f"[error] {exc}"
            enriched.append({**r, out_col: text})
        return {
            "model": model_name,
            "response": f"Enriched {min(cap, len(rows))}/{len(rows)} rows",
            "rows": enriched,
            "rowCount": len(enriched),
            "tokensIn": in_total,
            "tokensOut": out_total,
        }

    user_msg = (
        f"{prompt}\n\n{task}\n\nData:\n{_json.dumps(rows[:50], indent=2, default=str)}"
        if rows
        else f"{prompt}\n\n{task}"
    )
    try:
        resp = model.generate_content(user_msg)
        text = (getattr(resp, "text", None) or "").strip()
        usage = getattr(resp, "usage_metadata", None)
        return {
            "model": model_name,
            "response": text,
            "tokensIn": getattr(usage, "prompt_token_count", 0) or 0,
            "tokensOut": getattr(usage, "candidates_token_count", 0) or 0,
            "rows": rows,
            "rowCount": len(rows),
        }
    except Exception as exc:
        return {
            "model": model_name,
            "response": f"[agent error] {exc}",
            "aiError": str(exc),
            "rows": rows,
            "rowCount": len(rows),
            "tokensIn": 0,
            "tokensOut": 0,
        }
  
NODE_SPEC = _spec_from_yaml(_HERE / "agent.yaml", run)
  