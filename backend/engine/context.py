"""
RunContext — the single shared bag every node reads from and writes to.

Mental model: a workflow is a DAG of stateless handler functions. The
only state that flows between them is this RunContext. Each node mutates
it in place; the dag_runner re-passes the same instance to every successor.

Three "shelves" by convention:

  * datasets — keyed lists of row-dicts produced by data nodes (the
    primary "data plane"). Mirrors pandas DataFrames in spirit; we use
    list[dict] so json-serialising for SSE / logs is trivial.
  * values   — scalars / config / disposition / counts. Use ctx.set/get.
  * sections — narrative text blocks (kept for parity with the source
    architecture; unused by the default node set, ready for report nodes).

Plus a few terminal flags every workflow can set so HTTP callers and
tests can inspect the outcome without re-walking the graph.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    """Mutable context shared across all node handlers in one run."""

    alert_payload: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    datasets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    executive_summary: str = ""
    disposition: str = ""
    output_branch: str = ""
    report_path: str = ""

    # Per-node outputs as the runner sees them (drives downstream wiring).
    # The dag_runner stamps this; handlers should not write here directly.
    output_map: dict[str, Any] = field(default_factory=dict)

    # Stamped onto every event / log line for traceability.
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
  