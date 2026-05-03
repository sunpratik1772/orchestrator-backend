"""GET /node-manifest and GET /contracts — drives frontend palette / config inspector."""
from __future__ import annotations

from fastapi import APIRouter

from ...engine.registry import contracts_document, all_specs

router = APIRouter()


@router.get("/node-manifest")
def node_manifest() -> dict:
    """Per-spec view used by the UI palette + config inspector."""
    return {"nodes": [s.contract for s in all_specs()]}


@router.get("/contracts")
def contracts() -> dict:
    return contracts_document()
  