# NodeSpec Contract

Every node module exports `NODE_SPEC: NodeSpec`. The dataclass:

| Field                | Type                  | Notes                                              |
|----------------------|-----------------------|----------------------------------------------------|
| `type_id`            | str                   | Globally unique. Frontend uses this as `node.type`. |
| `description`        | str                   | Short, one line.                                   |
| `handler`            | callable              | `(node, ctx, incoming) -> dict`. Sync or async.    |
| `ui`                 | dict                  | display_name, icon, color, palette section.        |
| `input_ports`        | tuple[PortSpec, ...]  | Drives the validator.                              |
| `output_ports`       | tuple[PortSpec, ...]  | Drives the validator.                              |
| `params`             | tuple[ParamSpec, ...] | Drives the frontend's config inspector.            |
| `semantics_requires` | tuple[str, ...]       | Optional capability tags.                          |

Handler signature:

```python
def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    ...
```

* `node` — the saved node dict (`{ id, type, config, label, position }`).
* `ctx` — the shared `RunContext` for the run.
* `incoming` — `{upstream_node_id: upstream_output_dict}`. Branch routing
  from condition nodes is already resolved before you get this map.

Return value:

* Must be JSON-serialisable.
* Use `rows` for tabular data, `response` for text, `buckets` for
  routed groups (router node), and `_type: "condition"` + `rows_true` /
  `rows_false` for branching.
  