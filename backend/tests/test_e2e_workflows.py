"""End-to-end workflows that mirror real user scenarios.

These exercise the runner with multi-step DAGs that touch many nodes at
once, including branching, joining, parallel execution, and aggregation.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.engine.context import RunContext
from backend.engine.dag_runner import build_levels, run_workflow


def _run(nodes, edges, ctx=None):
    return asyncio.run(run_workflow(nodes, edges, ctx))


# ─────────────────────────── Topology ───────────────────────────
def test_levels_partition_correctly():
    """Diamond graph: A → (B, C) → D should produce 3 levels."""
    nodes = [{"id": x, "type": "manual_trigger", "config": {}} for x in "ABCD"]
    edges = [
        {"id": "1", "source": "A", "target": "B"},
        {"id": "2", "source": "A", "target": "C"},
        {"id": "3", "source": "B", "target": "D"},
        {"id": "4", "source": "C", "target": "D"},
    ]
    levels = build_levels(nodes, edges)
    assert [sorted(l) for l in levels] == [["A"], ["B", "C"], ["D"]]


def test_parallel_level_executes_concurrently():
    """Two pause(200ms) at the same level should not be serialized."""
    import time
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "p1", "type": "pause", "config": {"durationMs": 200}},
        {"id": "p2", "type": "pause", "config": {"durationMs": 200}},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "p1"},
        {"id": "e2", "source": "t", "target": "p2"},
    ]
    t0 = time.time()
    status, _, _ = _run(nodes, edges)
    elapsed = time.time() - t0
    assert status == "completed"
    # Sequential would be > 0.4s; parallel should land near 0.2s. Allow generous slack.
    assert elapsed < 0.45, f"Pauses appear serialized (took {elapsed:.2f}s)"


# ─────────────────────────── Real scenarios ───────────────────────────
def test_full_lead_pipeline_with_grouping():
    """Trigger → CSV → Filter → Group By → Sort. Verifies cross-node dataflow."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "load", "type": "csv_extract", "config": {"source": "leads.csv"}},
        {"id": "filt", "type": "filter", "config": {"expression": "row.score >= 60"}},
        {"id": "agg", "type": "group_by", "config": {
            "groupBy": "country", "aggregateCol": "lead_id", "aggregateFn": "count"
        }},
        {"id": "ord", "type": "sort", "config": {"sortBy": "count_lead_id", "order": "desc"}},
        {"id": "out", "type": "response", "config": {}},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "load"},
        {"id": "e2", "source": "load", "target": "filt"},
        {"id": "e3", "source": "filt", "target": "agg"},
        {"id": "e4", "source": "agg", "target": "ord"},
        {"id": "e5", "source": "ord", "target": "out"},
    ]
    status, output, logs = _run(nodes, edges)
    assert status == "completed", logs
    counts = [r["count_lead_id"] for r in output["ord"]["rows"]]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) == output["filt"]["rowCount"]


def test_join_orders_with_products_then_aggregate():
    """Real BI-style flow: orders ⨝ products → high-value rows → aggregate revenue per category."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "orders", "type": "csv_extract", "config": {"source": "orders.csv"}},
        {"id": "products", "type": "csv_extract", "config": {"source": "products.csv"}},
        {"id": "joined", "type": "join", "config": {
            "leftKey": "product_sku", "rightKey": "sku", "joinType": "inner"
        }},
        {"id": "high", "type": "filter", "config": {"expression": "row.total >= 100"}},
        {"id": "by_cat", "type": "group_by", "config": {
            "groupBy": "category", "aggregateCol": "total", "aggregateFn": "sum", "alias": "revenue"
        }},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "orders"},
        {"id": "e2", "source": "t", "target": "products"},
        {"id": "e3", "source": "orders", "target": "joined"},
        {"id": "e4", "source": "products", "target": "joined"},
        {"id": "e5", "source": "joined", "target": "high"},
        {"id": "e6", "source": "high", "target": "by_cat"},
    ]
    status, output, logs = _run(nodes, edges)
    assert status == "completed", logs
    assert output["joined"]["rowCount"] == 20
    assert "category" in output["by_cat"]["rows"][0]
    assert "revenue" in output["by_cat"]["rows"][0]
    # Every revenue should be > 0
    assert all(r["revenue"] > 0 for r in output["by_cat"]["rows"])


def test_condition_routes_to_two_independent_paths():
    """Condition splits to two distinct output nodes via sourceHandle."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "load", "type": "csv_extract", "config": {"source": "products.csv"}},
        {"id": "cond", "type": "condition", "config": {"expression": "row.active === true"}},
        {"id": "active_out", "type": "response", "config": {"content": "active branch"}},
        {"id": "inactive_out", "type": "csv_output", "config": {"filename": "inactive.csv"}},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "load"},
        {"id": "e2", "source": "load", "target": "cond"},
        {"id": "e3", "source": "cond", "target": "active_out", "sourceHandle": "true"},
        {"id": "e4", "source": "cond", "target": "inactive_out", "sourceHandle": "false"},
    ]
    status, output, _ = _run(nodes, edges)
    assert status == "completed"
    assert output["active_out"]["rowCount"] == output["cond"]["trueCount"]
    assert output["inactive_out"]["rowCount"] == output["cond"]["falseCount"]
    assert output["active_out"]["rowCount"] > 0
    assert output["inactive_out"]["rowCount"] > 0


def test_csv_output_then_excel_with_multiple_inputs():
    """CSV from leads + CSV from products both feed Excel multi-tab export."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "leads", "type": "csv_extract", "config": {"source": "leads.csv"}},
        {"id": "products", "type": "csv_extract", "config": {"source": "products.csv"}},
        {"id": "report", "type": "excel_output", "config": {
            "filename": "monthly.xlsx", "tabNames": "Leads,Products"
        }},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "leads"},
        {"id": "e2", "source": "t", "target": "products"},
        {"id": "e3", "source": "leads", "target": "report"},
        {"id": "e4", "source": "products", "target": "report"},
    ]
    status, output, _ = _run(nodes, edges)
    assert status == "completed"
    assert output["report"]["tabs"] == 2
    assert output["report"]["rowsWritten"] == 40


def test_evaluator_pipeline_with_pass_rate():
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "load", "type": "csv_extract", "config": {"source": "employees.csv"}},
        {"id": "eval", "type": "evaluator", "config": {
            "criteria": "row.performance === 'exceeds'", "label": "high_performer"
        }},
    ]
    edges = [
        {"id": "e1", "source": "t", "target": "load"},
        {"id": "e2", "source": "load", "target": "eval"},
    ]
    status, output, _ = _run(nodes, edges)
    assert status == "completed"
    assert output["eval"]["passed"] + output["eval"]["failed"] == 15
    assert output["eval"]["passed"] >= 1


def test_dataset_count_in_context():
    """Verify ctx.datasets is populated by csv_extract for downstream nodes that need it."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "load", "type": "csv_extract", "config": {"source": "transactions.csv"}},
    ]
    edges = [{"id": "e1", "source": "t", "target": "load"}]
    ctx = RunContext()
    asyncio.run(run_workflow(nodes, edges, ctx))
    assert "transactions.csv" in ctx.datasets
    assert len(ctx.datasets["transactions.csv"]) == 20


def test_unknown_node_type_caught_at_runtime():
    """Even if validator is bypassed, the runner should produce a failed log entry."""
    nodes = [
        {"id": "t", "type": "manual_trigger", "config": {}},
        {"id": "x", "type": "definitely_not_a_real_node", "config": {}},
    ]
    edges = [{"id": "e1", "source": "t", "target": "x"}]
    status, _, logs = _run(nodes, edges)
    assert status == "failed"
    bad = next(l for l in logs if l["nodeType"] == "definitely_not_a_real_node")
    assert "Unknown node type" in bad["error"]
