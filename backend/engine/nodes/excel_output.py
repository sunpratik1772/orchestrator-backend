"""Build a multi-tab .xlsx and return base64 bytes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import base64
import io


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    raw_names = (cfg.get("tabNames") or "").split(",")
    tab_names = [n.strip() for n in raw_names if n.strip()]
    filename = cfg.get("filename") or "output.xlsx"

    datasets: list[dict] = []
    idx = 0
    for up in incoming.values():
        if isinstance(up, dict) and isinstance(up.get("rows"), list):
            name = tab_names[idx] if idx < len(tab_names) else f"Sheet{idx + 1}"
            datasets.append({"tab": name[:31], "rows": up["rows"]})
            idx += 1
    if not datasets:
        return {"filename": filename, "tabs": 0, "rowsWritten": 0, "note": "No rows received"}

    try:
        from openpyxl import Workbook
    except Exception as exc:
        return {"filename": filename, "error": f"openpyxl missing: {exc}", "tabs": 0, "rowsWritten": 0}

    wb = Workbook()
    wb.remove(wb.active)  # default sheet
    total = 0
    preview = []
    for ds in datasets:
        ws = wb.create_sheet(title=ds["tab"])
        rows = ds["rows"]
        if rows:
            cols = list(rows[0].keys())
            ws.append(cols)
            for r in rows:
                ws.append([r.get(c) for c in cols])
        total += len(rows)
        preview.append({"tab": ds["tab"], "rows": rows[:3], "total": len(rows)})

    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    return {
        "filename": filename,
        "tabs": len(datasets),
        "tabNames": [d["tab"] for d in datasets],
        "rowsWritten": total,
        "byteSize": len(data),
        "base64": base64.b64encode(data).decode("ascii"),
        "preview": preview,
    }
  
NODE_SPEC = _spec_from_yaml(_HERE / "excel_output.yaml", run)
  