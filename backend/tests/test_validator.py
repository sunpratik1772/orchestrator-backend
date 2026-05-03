"""DAG validator catches obvious user mistakes."""
from backend.engine.validator import validate_dag


def test_unknown_type_caught():
    err = validate_dag([{"id": "n1", "type": "nope_not_real", "config": {}}], [])
    assert err and "unknown type" in err.lower()


def test_missing_required_param():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "filter", "config": {}},  # expression is required
    ]
    edges = [{"id": "e1", "source": "n1", "target": "n2"}]
    err = validate_dag(nodes, edges)
    assert err and "expression" in err


def test_condition_edge_without_handle_caught():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "condition", "config": {"expression": "True"}},
        {"id": "n3", "type": "response", "config": {}},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},  # missing sourceHandle
    ]
    err = validate_dag(nodes, edges)
    assert err and "sourceHandle" in err


def test_valid_workflow_passes():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "csv_extract", "config": {"source": "leads.csv"}},
    ]
    edges = [{"id": "e1", "source": "n1", "target": "n2"}]
    assert validate_dag(nodes, edges) is None
  