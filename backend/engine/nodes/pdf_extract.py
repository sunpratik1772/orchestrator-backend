"""Extract text from a (mock) PDF document."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
from ...data_sources.registry import PDF_MOCK


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    source = cfg.get("source") or "default"
    doc = PDF_MOCK.get(source) or PDF_MOCK["default"]
    rows = [{"page": i + 1, "text": chunk.strip()} for i, chunk in enumerate(doc["text"].split("\n\n")) if chunk.strip()]
    return {"source": source, "pages": doc["pages"], "rows": rows, "rowCount": len(rows), "fullText": doc["text"]}
  
NODE_SPEC = _spec_from_yaml(_HERE / "pdf_extract.yaml", run)
  