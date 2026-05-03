"""Write rows to a CSV string (returned in the output payload)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import csv
import io


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    filename = cfg.get("filename") or "output.csv"
    rows = _upstream_rows(incoming)
    if not rows:
        return {"filename": filename, "rowCount": 0, "csv": ""}
    cols = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in cols})
    text = buf.getvalue()
    return {"filename": filename, "rowCount": len(rows), "csv": text, "byteSize": len(text.encode("utf-8")), "rows": rows}
  
NODE_SPEC = _spec_from_yaml(_HERE / "csv_output.yaml", run)
  