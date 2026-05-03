# Backend Architecture

## One-liner
A FastAPI service that auto-discovers a registry of node handlers from
`backend/engine/nodes/`, stitches them into a DAG runner, and exposes
the result as `/workflows`, `/blocks`, `/copilot/chat`.

## Layers

```
HTTP (FastAPI)        →  app/routers/*           # /workflows, /run, /copilot, /node-manifest
Orchestration         →  engine/dag_runner.py    # Kahn's topo-sort + per-level async exec
Validation            →  engine/validator.py     # pure DAG validation
Registry              →  engine/registry.py      # pkgutil import of engine/nodes/*
Per-node handler      →  engine/nodes/<name>.py  # one .py + one .yaml each
Shared state          →  engine/context.py       # RunContext (single bag)
Datasets              →  data_sources/registry.py + metadata/*.yaml
LLM planning          →  copilot/workflow_generator.py
```

## Why this shape

* **Per-node files** — adding a new node is a 1-PR diff: drop two files in
  `engine/nodes/` and you're done. No central switch statement.
* **YAML for metadata** — the frontend's config inspector, the validator,
  and the Copilot prompt all read the same source of truth.
* **Auto-discovery** — `registry.py` calls `pkgutil.iter_modules` on
  `engine/nodes` at import time. Forgetting to "register" a node is
  impossible.
* **One `RunContext`** — every node mutates a shared bag. Mirrors the
  pattern in [rebuild-refactor](https://github.com/sunpratik1772/rebuild-refactor).

## Request lifecycle (POST /workflows/{id}/execute)

1. `run.execute` loads the saved workflow (JSON file in `drafts/`).
2. Builds a fresh `RunContext` with `alert_payload` = request body input.
3. Calls `dag_runner.run_workflow` which:
   * partitions nodes into topo-levels,
   * gathers each level concurrently with `asyncio.gather`,
   * passes each handler the per-node incoming-output map.
4. Persists an execution record under `backend/executions/`, returns it.

## Adding a new capability

* New node       → add 2 files in `engine/nodes/` (see HOW_TO_DEFINE_A_NODE.md).
* New dataset    → add 1 YAML in `data_sources/metadata/`.
* New endpoint   → add a router under `app/routers/` and `include_router`.
* New AI step    → wire it into `copilot/workflow_generator.py`.
  