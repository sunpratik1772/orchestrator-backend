"""Mock DB query — falls back to dataset rows."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import re

from ...data_sources.registry import get_rows, dataset_names


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    query = (cfg.get("query") or "").strip()
    source = cfg.get("source")
    if not source:
        # Try to infer from "FROM <table>" — match against known dataset names.
        m = re.search(r"\bfrom\s+([\w.]+)", query, re.I)
        if m:
            tbl = m.group(1)
            for ds in dataset_names():
                if ds.split(".")[0] == tbl or ds == tbl:
                    source = ds
                    break
    rows = get_rows(source) if source else []
    return {"query": query, "source": source, "rows": rows, "rowCount": len(rows)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "db_query.yaml", run)
  