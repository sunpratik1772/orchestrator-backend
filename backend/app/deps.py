"""
Tiny storage helpers — flat JSON files in `backend/drafts/` and
`backend/executions/`. Mirrors rebuild-refactor's stateless pattern.
Swap to Postgres by replacing these function bodies.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = ROOT / "drafts"
EXECUTIONS_DIR = ROOT / "executions"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
EXECUTIONS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_workflows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(DRAFTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    p = DRAFTS_DIR / f"{workflow_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_workflow(data: dict[str, Any]) -> dict[str, Any]:
    wf_id = data.get("id") or uuid.uuid4().hex
    now = _now()
    record = {
        "id": wf_id,
        "name": data.get("name", "Untitled"),
        "description": data.get("description", ""),
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
        "status": data.get("status", "draft"),
        "createdAt": data.get("createdAt", now),
        "updatedAt": now,
        "runCount": data.get("runCount", 0),
        "lastRunAt": data.get("lastRunAt"),
    }
    (DRAFTS_DIR / f"{wf_id}.json").write_text(json.dumps(record, indent=2))
    return record


def delete_workflow(workflow_id: str) -> bool:
    p = DRAFTS_DIR / f"{workflow_id}.json"
    if not p.exists():
        return False
    p.unlink()
    return True


def append_execution(record: dict[str, Any]) -> None:
    exec_id = record.get("executionId") or uuid.uuid4().hex
    (EXECUTIONS_DIR / f"{exec_id}.json").write_text(
        json.dumps(record, indent=2, default=str)
    )


def list_executions(workflow_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for p in sorted(EXECUTIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text())
            if workflow_id and data.get("workflowId") != workflow_id:
                continue
            items.append(data)
            if len(items) >= limit:
                break
        except Exception:
            continue
    return items


def bump_workflow_run(workflow_id: str) -> None:
    wf = get_workflow(workflow_id)
    if not wf:
        return
    wf["runCount"] = int(wf.get("runCount", 0)) + 1
    wf["lastRunAt"] = _now()
    wf["updatedAt"] = _now()
    (DRAFTS_DIR / f"{workflow_id}.json").write_text(json.dumps(wf, indent=2))
  