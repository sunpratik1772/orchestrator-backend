"""Black-box HTTP tests via FastAPI TestClient.

Exercises every route the React frontend hits, ensuring the contract matches
the original TypeScript Express server. Storage uses a tmp directory so tests
don't pollute backend/drafts/.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Spin up the app with isolated storage dirs."""
    tmp = tmp_path_factory.mktemp("dbstudio_test")
    drafts = tmp / "drafts"
    execs = tmp / "executions"
    drafts.mkdir()
    execs.mkdir()

    # Patch deps to use tmp dirs BEFORE importing app
    from backend.app import deps
    deps.DRAFTS_DIR = drafts
    deps.EXECUTIONS_DIR = execs

    from backend.app.main import app
    return TestClient(app)


# ─────────────────────────── Health & meta ───────────────────────────
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_blocks_returns_all_33_with_required_fields(client):
    r = client.get("/blocks")
    assert r.status_code == 200
    blocks = r.json()
    assert len(blocks) == 33
    for b in blocks:
        assert {"type", "label", "description", "category", "icon", "color"} <= set(b.keys())
    types = {b["type"] for b in blocks}
    # Spot-check every category is represented
    assert {"manual_trigger", "csv_extract", "filter", "condition", "agent",
            "response", "github", "excel_output"} <= types


def test_node_manifest_contains_full_contracts(client):
    r = client.get("/node-manifest")
    assert r.status_code == 200
    nodes = r.json()["nodes"]
    assert len(nodes) == 33
    csv = next(n for n in nodes if n["type_id"] == "csv_extract")
    assert csv["params"][0]["name"] == "source"
    assert csv["params"][0]["required"] is True


def test_contracts_endpoint(client):
    r = client.get("/contracts")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.0"
    assert len(body["nodes"]) == 33


def test_mock_datasets_lists_5(client):
    r = client.get("/mock-datasets")
    assert r.status_code == 200
    names = r.json()
    assert set(names) == {"leads.csv", "products.csv", "orders.csv",
                          "employees.csv", "transactions.csv"}


def test_stats_initial_state(client):
    r = client.get("/stats")
    assert r.status_code == 200
    s = r.json()
    for key in ("totalWorkflows", "activeWorkflows", "totalExecutions",
                "successfulExecutions", "failedExecutions", "avgDurationMs"):
        assert key in s


def test_logs_initial_empty(client):
    r = client.get("/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ─────────────────────────── Workflows CRUD ───────────────────────────
def test_workflow_full_lifecycle(client):
    payload = {
        "name": "Lead Triage",
        "description": "Find hot leads",
        "nodes": [
            {"id": "n1", "type": "manual_trigger", "label": "Start", "config": {}},
            {"id": "n2", "type": "csv_extract", "label": "Leads", "config": {"source": "leads.csv"}},
            {"id": "n3", "type": "filter", "label": "Hot", "config": {"expression": "row.score >= 80"}},
            {"id": "n4", "type": "response", "label": "Out", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n4"},
        ],
        "status": "draft",
    }

    # CREATE
    r = client.post("/workflows", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    wf_id = created["id"]
    assert created["name"] == "Lead Triage"
    assert created["runCount"] == 0

    # LIST
    r = client.get("/workflows")
    assert r.status_code == 200
    assert any(w["id"] == wf_id for w in r.json())

    # GET ONE
    r = client.get(f"/workflows/{wf_id}")
    assert r.status_code == 200
    assert r.json()["nodes"][0]["type"] == "manual_trigger"

    # UPDATE
    r = client.put(f"/workflows/{wf_id}", json={"name": "Renamed", "status": "active"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["status"] == "active"

    # EXECUTE
    r = client.post(f"/workflows/{wf_id}/execute", json={"input": {}, "trigger": "manual"})
    assert r.status_code == 200, r.text
    exec_result = r.json()
    assert exec_result["status"] == "completed", exec_result.get("logs")
    assert "executionId" in exec_result
    assert len(exec_result["logs"]) == 4
    # Filter must have produced a non-zero subset of the 20 leads
    filter_log = next(l for l in exec_result["logs"] if l["nodeType"] == "filter")
    assert 0 < filter_log["output"]["rowCount"] < 20

    # EXECUTIONS LIST for this workflow
    r = client.get(f"/workflows/{wf_id}/executions")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # GET specific execution
    r = client.get(f"/executions/{exec_result['executionId']}")
    assert r.status_code == 200

    # /logs reflects this run
    r = client.get("/logs")
    assert r.status_code == 200
    logs = r.json()
    assert any(l["id"] == exec_result["executionId"] for l in logs)
    log_entry = next(l for l in logs if l["id"] == exec_result["executionId"])
    assert log_entry["workflowName"] == "Renamed"
    assert log_entry["status"] == "completed"
    assert "cost" in log_entry
    assert log_entry["cost"]["total"] >= 1

    # /stats updated
    r = client.get("/stats")
    s = r.json()
    assert s["totalExecutions"] >= 1
    assert s["successfulExecutions"] >= 1

    # workflow runCount bumped
    r = client.get(f"/workflows/{wf_id}")
    assert r.json()["runCount"] == 1
    assert r.json()["lastRunAt"] is not None

    # DELETE
    r = client.delete(f"/workflows/{wf_id}")
    assert r.status_code == 204
    r = client.get(f"/workflows/{wf_id}")
    assert r.status_code == 404


def test_get_unknown_workflow_404(client):
    r = client.get("/workflows/does-not-exist")
    assert r.status_code == 404


def test_execute_unknown_workflow_404(client):
    r = client.post("/workflows/missing/execute", json={"input": {}})
    assert r.status_code == 404


def test_delete_unknown_workflow_404(client):
    r = client.delete("/workflows/missing")
    assert r.status_code == 404


# ─────────────────────────── Failure path ───────────────────────────
def test_execute_workflow_with_failing_node_records_failure(client):
    """A node that raises should produce status='failed' and a log entry with the error."""
    payload = {
        "name": "Failing",
        "nodes": [
            {"id": "n1", "type": "manual_trigger", "config": {}},
            {"id": "n2", "type": "http", "config": {"url": "http://this-host-does-not-exist.invalid"}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    r = client.post("/workflows", json=payload)
    wf_id = r.json()["id"]
    r = client.post(f"/workflows/{wf_id}/execute", json={"input": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert any(l["status"] == "failed" and l["error"] for l in body["logs"])
