"""Annotation. Returns the configured content unchanged."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  

def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    return {"note": cfg.get("content") or ""}
  
NODE_SPEC = _spec_from_yaml(_HERE / "note.yaml", run)
  