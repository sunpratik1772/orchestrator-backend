"""Verify the condition node's true/false rows route to the correct successor."""
import asyncio

from backend.engine.dag_runner import run_workflow


def test_condition_routes_via_handle():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "csv_extract", "config": {"source": "orders.csv"}},
        {"id": "n3", "type": "condition", "config": {"expression": "row.total > 500"}},
        {"id": "n4", "type": "response", "config": {}},  # high-value branch
        {"id": "n5", "type": "response", "config": {}},  # low-value branch
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4", "sourceHandle": "true"},
        {"id": "e4", "source": "n3", "target": "n5", "sourceHandle": "false"},
    ]
    status, output, _ = asyncio.run(run_workflow(nodes, edges))
    assert status == "completed"
    assert output["n3"]["trueCount"] + output["n3"]["falseCount"] == 20
    assert output["n4"]["rowCount"] == output["n3"]["trueCount"]
    assert output["n5"]["rowCount"] == output["n3"]["falseCount"]
  