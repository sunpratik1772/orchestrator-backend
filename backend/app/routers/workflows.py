"""CRUD + executions for workflows. Storage backed by JSON files in `backend/drafts/`."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from .. import deps
from ..schemas import RunRequest, WorkflowCreate, WorkflowUpdate
from ...engine.context import RunContext
from ...engine.dag_runner import run_workflow
from ...engine.registry import block_registry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/workflows")
def list_workflows() -> list[dict[str, Any]]:
    return deps.list_workflows()


@router.post("/workflows", status_code=status.HTTP_201_CREATED)
def create_workflow(body: WorkflowCreate) -> dict[str, Any]:
    return deps.save_workflow(body.model_dump())


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    wf = deps.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowUpdate) -> dict[str, Any]:
    existing = deps.get_workflow(workflow_id)
    if not existing:
        raise HTTPException(404, "Workflow not found")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    existing.update(patch)
    existing["id"] = workflow_id
    return deps.save_workflow(existing)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str):
    if not deps.delete_workflow(workflow_id):
        raise HTTPException(404, "Workflow not found")
    return None


# --- Block registry / mock datasets / stats / logs ---------------------------
@router.get("/blocks")
def blocks() -> list[dict[str, Any]]:
    """Frontend-compatible block registry."""
    return block_registry()


@router.get("/mock-datasets")
def mock_datasets() -> list[str]:
    from ...data_sources.registry import dataset_names
    return dataset_names()


@router.get("/stats")
def stats() -> dict[str, Any]:
    workflows = deps.list_workflows()
    executions = deps.list_executions(limit=10000)
    succ = [e for e in executions if e.get("status") == "completed"]
    fail = [e for e in executions if e.get("status") == "failed"]
    avg = int(sum(e.get("durationMs", 0) for e in executions) / max(1, len(executions)))
    return {
        "totalWorkflows": len(workflows),
        "activeWorkflows": sum(1 for w in workflows if w.get("status") == "active"),
        "totalExecutions": len(executions),
        "successfulExecutions": len(succ),
        "failedExecutions": len(fail),
        "avgDurationMs": avg,
    }


_LOG_COLORS = [
    "#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626",
    "#0891b2", "#ea580c", "#16a34a", "#9333ea", "#0d9488",
]


@router.get("/logs")
def logs() -> list[dict[str, Any]]:
    executions = deps.list_executions(limit=200)
    workflows = {w["id"]: w for w in deps.list_workflows()}
    color_map: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for ex in executions:
        wf_id = ex.get("workflowId", "unknown")
        if wf_id not in color_map:
            color_map[wf_id] = _LOG_COLORS[len(color_map) % len(_LOG_COLORS)]
        meta = (ex.get("output") or {}).get("_meta", {})
        cost = meta.get("cost") or {"baseRun": 1, "modelInput": 0, "modelOutput": 0, "total": 1, "tokensIn": 0, "tokensOut": 0}
        display_output = {k: v for k, v in (ex.get("output") or {}).items() if k != "_meta"}
        dur = ex.get("durationMs", 0)
        out.append({
            "id": ex.get("executionId"),
            "workflowId": wf_id,
            "workflowName": workflows.get(wf_id, {}).get("name", "Deleted Workflow"),
            "workflowColor": color_map[wf_id],
            "dateISO": ex.get("startedAt", datetime.now(timezone.utc).isoformat()),
            "date": ex.get("startedAt", "—"),
            "status": "error" if ex.get("status") == "failed" else ex.get("status"),
            "trigger": meta.get("trigger", "manual"),
            "level": meta.get("level", "error" if ex.get("status") == "failed" else "info"),
            "durationMs": dur,
            "duration": (f"{dur}ms" if dur < 1000 else f"{dur/1000:.1f}s") if dur else "—",
            "cost": cost,
            "input": meta.get("input", {}),
            "output": display_output,
            "logs": ex.get("logs", []),
        })
    return out


@router.get("/workflows/{workflow_id}/executions")
def list_workflow_executions(workflow_id: str):
    return deps.list_executions(workflow_id=workflow_id, limit=50)


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str):
    for e in deps.list_executions(limit=10000):
        if e.get("executionId") == execution_id:
            return e
    raise HTTPException(404, "Execution not found")
  