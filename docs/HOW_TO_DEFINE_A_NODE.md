# How to define a new node

Two files. No registration step. The runtime auto-discovers it.

## 1. `engine/nodes/my_node.yaml`

```yaml
type_id: my_node                   # globally unique, snake_case
description: One-liner shown in the palette tooltip.
ui:
  display_name: My Node            # palette label
  icon: Sparkles                   # any lucide-react icon name
  color: "#7c3aed"
  palette: { section: { id: transform } }
input_ports:
  - { name: rows, type: dataframe }
output_ports:
  - { name: rows, type: dataframe }
params:
  - name: threshold
    type: number
    description: Filter rows where score >= this value.
    required: true
    default: 80
```

Param `type` values: `string | number | boolean | enum | code | json |
input_ref | column_ref | column_list | expression`.

Port `type` values: `dataframe | scalar | text | object | any`.

## 2. `engine/nodes/my_node.py`

```python
from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent


def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    threshold = cfg.get("threshold", 80)
    rows = []
    for upstream in incoming.values():
        if isinstance(upstream, dict) and isinstance(upstream.get("rows"), list):
            rows = upstream["rows"]; break
    kept = [r for r in rows if (r.get("score") or 0) >= threshold]
    return {"rows": kept, "rowCount": len(kept)}


NODE_SPEC = _spec_from_yaml(_HERE / "my_node.yaml", run)
```

That's it. `registry.py` will pick it up the next time the process starts.

## 3. (recommended) `tests/test_my_node.py`

```python
import asyncio
from engine.dag_runner import run_workflow

def test_my_node():
    nodes = [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {"id": "n2", "type": "csv_extract", "config": {"source": "leads.csv"}},
        {"id": "n3", "type": "my_node", "config": {"threshold": 90}},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
    ]
    status, output, _ = asyncio.run(run_workflow(nodes, edges))
    assert status == "completed"
    assert output["n3"]["rowCount"] >= 1
```

## Async handlers

Make `run` an `async def` and the runner will `await` it directly.
Use this for I/O-bound nodes (HTTP, Slack, Notion, Gmail).

## Conventions

* Always return JSON-serialisable dicts (no datetime objects, no sets).
* When a node produces row data, use the key name **`rows`** so downstream
  helpers that auto-walk `incoming` find it.
* Handlers should be deterministic and pure — push side effects through the
  integration nodes (Slack / Gmail / GitHub).
* On failure, raise a normal `Exception` — the runner records it as a
  failed log entry with the message preserved.
  