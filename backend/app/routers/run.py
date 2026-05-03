"""POST /workflows/{id}/execute — runs a saved workflow against the DAG runner."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import deps
from ..schemas import RunRequest
from ...engine.context import RunContext
from ...engine.dag_runner import run_workflow

logger = logging.getLogger(__name__)
router = APIRouter()


def _calc_cost(nodes: list[dict]) -> dict[str, Any]:
    agent_count = sum(1 for n in nodes if n.get("type") == "agent")
    tool_count = sum(1 for n in nodes if n.get("type") in {"http", "gmail", "github", "slack", "notion", "mcp"})
    base = 1
    model_in = agent_count * 4 + tool_count
    model_out = agent_count * 2
    return {
        "baseRun": base, "modelInput": model_in, "modelOutput": model_out,
        "total": base + model_in + model_out,
        "tokensIn": 0, "tokensOut": 0,
    }


@router.post("/workflows/{workflow_id}/execute")
async def execute(workflow_id: str, body: RunRequest | None = None) -> dict[str, Any]:
    wf = deps.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    body = body or RunRequest()

    nodes = wf.get("nodes") or []
    edges = wf.get("edges") or []
    started_at = datetime.now(timezone.utc)
    ctx = RunContext(alert_payload=body.input or {})
    status, output_map, logs = await run_workflow(nodes, edges, ctx)
    completed_at = datetime.now(timezone.utc)

    execution_id = uuid.uuid4().hex
    record = {
        "executionId": execution_id,
        "workflowId": workflow_id,
        "status": status,
        "output": {**output_map, "_meta": {"trigger": body.trigger, "cost": _calc_cost(nodes), "level": "error" if status == "failed" else "info", "input": body.input or {}}},
        "logs": logs,
        "durationMs": int((completed_at - started_at).total_seconds() * 1000),
        "startedAt": started_at.isoformat(),
        "completedAt": completed_at.isoformat(),
    }
    deps.append_execution(record)
    deps.bump_workflow_run(workflow_id)
    return record
  