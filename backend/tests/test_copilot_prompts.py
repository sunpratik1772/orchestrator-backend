"""
Copilot regression suite — 9 realistic + 6 stress prompts.

These exercise the live Copilot pipeline end-to-end (Gemini → validate → heal
→ persist) and assert each generated workflow has zero hallucinated node
types and zero dangling edges.

Run:
    pytest python-backend/backend/tests/test_copilot_prompts.py -v

The suite is skipped automatically if:
  * GOOGLE_API_KEY is not set, OR
  * the API server at $COPILOT_BASE_URL (default http://localhost:80) is unreachable.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest


BASE = os.environ.get("COPILOT_BASE_URL", "http://localhost:80")


def _get(path: str):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def _server_reachable() -> bool:
    return _get("/api/blocks") is not None


pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY not set",
    ),
    pytest.mark.skipif(
        not _server_reachable(),
        reason=f"API server not reachable at {BASE}",
    ),
]


PROMPTS = [
    # Realistic — should always succeed
    ("R1", "realistic", True,  "Build a lead scoring pipeline: extract leads, filter to those with score above 70, run an AI agent to qualify them, and respond."),
    ("R2", "realistic", True,  "Create a workflow that splits orders by status: completed orders go to a notes node, pending orders go to a separate notes node."),
    ("R3", "realistic", True,  "Use a router to send products into 3 buckets: Electronics, Accessories, and everything else; each bucket ends in a response node."),
    ("R4", "realistic", True,  "Join leads with orders on a common key and output the merged rows."),
    ("R5", "realistic", True,  "Loop over employees 3 times and produce a final response."),
    ("R6", "realistic", True,  "Aggregate transactions by category, sort by total descending, and respond with the result."),
    ("R7", "realistic", True,  "For each lead, run an AI agent in per-row mode to write a personalized outreach email and add it as a column."),
    ("R8", "realistic", True,  "Pull GitHub repo details, then send a Slack message summarizing them."),
    ("R9", "realistic", True,  "Extract leads, pause until score is greater than 80, then respond."),
    # Stress — must not crash; some may legitimately refuse
    ("S1", "stress",    True,  "Build the most complex pipeline you can with at least 8 nodes including branching, AI, and an integration."),
    ("S2", "stress",    True,  "do something cool"),
    ("S3", "stress",    True,  "Make a workflow that filters leads where score > 70 AND stage == 'qualified' AND country in ('US','UK')."),
    ("S4", "stress",    True,  "Build a dual-branch flow: condition on score>=80 → AI summarize true rows, send to Notion; false rows → write to a CSV output."),
    ("S5", "stress",    False, "Use a node type called 'magic_unicorn' to process leads."),  # MUST refuse, not invent
    ("S6", "stress",    True,  "Build a workflow but don't configure any of the nodes."),
]


def _post_sse(message: str, timeout: int = 120):
    """POST to /api/copilot/chat and return parsed SSE events."""
    body = json.dumps({"message": message, "history": []}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/copilot/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    events: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = b""
        for chunk in r:
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.split(b"\n"):
                    if line.startswith(b"data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass
    return events


@pytest.mark.parametrize("pid,cat,must_create,prompt", PROMPTS, ids=[p[0] for p in PROMPTS])
def test_copilot_prompt(pid, cat, must_create, prompt):
    blocks = _get("/api/blocks") or []
    valid_types = {b["type"] for b in blocks}
    assert valid_types, "no blocks returned from /api/blocks"

    events = _post_sse(prompt)
    err = next((e for e in events if e.get("type") == "error"), None)
    assert err is None, f"[{pid}] copilot errored: {err}"

    created = next((e for e in events if e.get("type") == "workflow_created"), None)

    if not must_create:
        # S5 — model should refuse cleanly with an answer, not invent a node type
        assert created is None, f"[{pid}] expected refusal, got workflow {created}"
        return

    assert created is not None, f"[{pid}] no workflow created. events={[e.get('type') for e in events]}"

    wf = _get(f"/api/workflows/{created['workflowId']}")
    assert wf, f"[{pid}] could not fetch created workflow"

    bad_types = [n for n in wf["nodes"] if n["type"] not in valid_types]
    assert not bad_types, f"[{pid}] hallucinated node types: {[n['type'] for n in bad_types]}"

    node_ids = {n["id"] for n in wf["nodes"]}
    dangling = [e for e in (wf.get("edges") or [])
                if e["source"] not in node_ids or e["target"] not in node_ids]
    assert not dangling, f"[{pid}] dangling edges: {dangling}"

    assert wf.get("name"), f"[{pid}] workflow missing name"
    assert len(wf["nodes"]) >= 1, f"[{pid}] workflow has no nodes"
