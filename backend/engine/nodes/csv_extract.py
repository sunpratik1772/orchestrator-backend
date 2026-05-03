"""Read rows from a registered mock dataset."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
from ...data_sources.registry import get_rows


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    source = cfg.get("source") or ""
    rows = get_rows(source)
    limit = cfg.get("limit")
    if isinstance(limit, (int, float)) and int(limit) > 0:
        rows = rows[: int(limit)]
    if rows:
        ctx.datasets[source or "rows"] = rows
    return {"source": source, "rows": rows, "rowCount": len(rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "csv_extract.yaml", run)
  