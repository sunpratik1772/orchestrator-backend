"""Copilot pipeline tests.

When GOOGLE_API_KEY is missing the planner returns a deterministic stub
workflow — perfect for CI without secrets. We test the full self-healing
loop against that stub plus simulated repair scenarios.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.copilot.workflow_generator import (
    MAX_REPAIR_ATTEMPTS,
    _extract_json,
    _node_catalogue,
    run_pipeline,
)


# ─────────────────────────── JSON extraction ───────────────────────────
def test_extract_plain_json():
    text = '{"name": "x", "nodes": [], "edges": []}'
    assert _extract_json(text) == {"name": "x", "nodes": [], "edges": []}


def test_extract_fenced_json():
    text = 'Here is the workflow:\n```json\n{"name": "y", "nodes": [], "edges": []}\n```\nDone.'
    assert _extract_json(text)["name"] == "y"


def test_extract_brace_match_fallback():
    text = "garbage before {\"name\": \"z\", \"nodes\": [], \"edges\": []} garbage after"
    assert _extract_json(text)["name"] == "z"


def test_extract_returns_none_on_garbage():
    assert _extract_json("no json at all") is None
    assert _extract_json("") is None


def test_node_catalogue_lists_all_specs():
    text = _node_catalogue()
    for nt in ("manual_trigger", "csv_extract", "filter", "condition", "agent",
               "response", "github", "excel_output"):
        assert nt in text


# ─────────────────────────── End-to-end pipeline (stub planner) ───────────────────────────
async def _drain(queue: asyncio.Queue) -> list[dict]:
    events: list[dict] = []
    while True:
        ev = await queue.get()
        if ev is None:
            break
        events.append(ev)
    return events


def test_pipeline_event_sequence(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    async def go():
        queue: asyncio.Queue = asyncio.Queue()
        producer = asyncio.create_task(run_pipeline("any", [], [], queue))
        await producer
        await queue.put(None)
        return await _drain(queue)

    events = asyncio.run(go())
    stages = [e.get("stage") for e in events if "stage" in e]
    types = [e.get("type") for e in events]

    # Should always start with pipeline-start
    assert "pipeline-start" in stages
    # Should reach plan + extract + validate phases
    assert "plan" in stages
    assert "extract" in stages
    assert "validate-schema" in stages
    assert "validate-semantic" in stages
    # Should end successfully (workflow + complete)
    assert "workflow" in types
    assert "complete" in types
    # Workflow event must contain a valid shape
    wf_event = next(e for e in events if e.get("type") == "workflow")
    wf = wf_event["workflow"]
    assert isinstance(wf["nodes"], list) and isinstance(wf["edges"], list)
    assert len(wf["nodes"]) >= 2
    # Every node uses a real type_id
    from backend.engine.registry import NODE_SPECS
    for n in wf["nodes"]:
        assert n["type"] in NODE_SPECS


def test_pipeline_recovers_from_invalid_first_attempt(monkeypatch):
    """Force the planner to emit garbage then valid JSON; the repair loop should accept attempt 2."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from backend.copilot import workflow_generator as wg

    valid_wf = {
        "name": "Repaired",
        "description": "ok",
        "nodes": [
            {"id": "n1", "type": "manual_trigger", "label": "Start", "config": {}, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": "csv_extract", "label": "Load", "config": {"source": "leads.csv"}, "position": {"x": 200, "y": 0}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    call_count = {"n": 0}

    async def fake_generate(model, prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "no json here, just words"
        return json.dumps(valid_wf)

    monkeypatch.setattr(wg, "_generate", fake_generate)

    async def go():
        queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline("test", [], [], queue)
        await queue.put(None)
        return await _drain(queue)

    events = asyncio.run(go())
    types = [e.get("type") for e in events]
    assert "warning" in types  # first attempt failed extraction
    assert "workflow" in types
    assert "complete" in types
    assert call_count["n"] == 2


def test_pipeline_emits_error_when_all_repairs_fail(monkeypatch):
    """If the planner never produces valid JSON, pipeline should emit a final error event."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from backend.copilot import workflow_generator as wg

    async def always_garbage(model, prompt):
        return "this is not json"

    monkeypatch.setattr(wg, "_generate", always_garbage)

    async def go():
        queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline("test", [], [], queue)
        await queue.put(None)
        return await _drain(queue)

    events = asyncio.run(go())
    last_real = [e for e in events if e.get("type") == "error"]
    assert last_real, f"Expected an error event, got types: {[e.get('type') for e in events]}"
    assert "exhausted" in last_real[0].get("stage", "")


def test_pipeline_repairs_invalid_workflow_schema(monkeypatch):
    """Planner emits JSON with an unknown node type → schema layer rejects → repair → accept."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from backend.copilot import workflow_generator as wg

    bad_wf = json.dumps({
        "name": "Bad", "description": "",
        "nodes": [{"id": "n1", "type": "totally_made_up", "config": {}, "position": {"x": 0, "y": 0}}],
        "edges": [],
    })
    good_wf = json.dumps({
        "name": "Good", "description": "",
        "nodes": [
            {"id": "n1", "type": "manual_trigger", "config": {}, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": "response", "config": {}, "position": {"x": 200, "y": 0}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })
    seq = [bad_wf, good_wf]

    async def fake_gen(model, prompt):
        return seq.pop(0) if seq else good_wf

    monkeypatch.setattr(wg, "_generate", fake_gen)

    async def go():
        queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline("repair me", [], [], queue)
        await queue.put(None)
        return await _drain(queue)

    events = asyncio.run(go())
    warnings = [e for e in events if e.get("type") == "warning"]
    assert any("Schema error" in w.get("message", "") for w in warnings)
    assert any(e.get("type") == "workflow" for e in events)
