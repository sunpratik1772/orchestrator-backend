"""End-to-end: a minimal trigger → csv_extract → filter → response workflow."""
import asyncio

from backend.engine.dag_runner import run_workflow


def test_simple_workflow_runs():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "csv_extract", "config": {"source": "leads.csv"}},
        {"id": "n3", "type": "filter", "config": {"expression": "row.score >= 80"}},
        {"id": "n4", "type": "response", "config": {}},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4"},
    ]
    status, output, logs = asyncio.run(run_workflow(nodes, edges))
    assert status == "completed", logs
    assert output["n2"]["rowCount"] == 20
    assert output["n3"]["rowCount"] >= 1
    # Ensure filter actually filtered something out
    assert output["n3"]["rowCount"] < output["n2"]["rowCount"]
  