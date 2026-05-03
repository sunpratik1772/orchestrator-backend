"""Rename or compute new columns from per-row expressions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
from ..expressions import eval_row


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    mappings = cfg.get("mappings") or []
    rows = _upstream_rows(incoming)
    out_rows: list[dict] = []
    for r in rows:
        new_row = dict(r)
        for m in mappings:
            to = m.get("to")
            if not to:
                continue
            if "expression" in m and m["expression"]:
                new_row[to] = eval_row(m["expression"], new_row, raw=True)
            elif "from" in m and m["from"]:
                new_row[to] = new_row.get(m["from"])
        out_rows.append(new_row)
    return {"rows": out_rows, "rowCount": len(out_rows), "mapped": len(mappings)}
  
NODE_SPEC = _spec_from_yaml(_HERE / "map_transform.yaml", run)
  