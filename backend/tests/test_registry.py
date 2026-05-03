"""Smoke test: every node in engine/nodes has a discoverable NODE_SPEC."""
from backend.engine.registry import all_specs, NODE_SPECS


def test_registry_loads_all_30_nodes():
    specs = list(all_specs())
    assert len(specs) >= 30, f"Expected at least 30 nodes, got {len(specs)}"
    assert "manual_trigger" in NODE_SPECS
    assert "csv_extract" in NODE_SPECS
    assert "filter" in NODE_SPECS
    assert "condition" in NODE_SPECS
    assert "agent" in NODE_SPECS
    assert "github" in NODE_SPECS


def test_every_spec_has_handler_and_contract():
    for s in all_specs():
        assert callable(s.handler), f"{s.type_id} missing handler"
        c = s.contract
        assert c["type_id"] == s.type_id
        assert isinstance(c["params"], list)
  