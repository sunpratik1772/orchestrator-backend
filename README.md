# orchestrator-backend

  > Python FastAPI workflow engine. Auto-discovered node registry, DAG executor, and self-healing Gemini Copilot.

  This is the standalone backend for the orchestrator stack. It pairs with [`orchestrator-frontend`](https://github.com/sunpratik1772/orchestrator-frontend) (React + Vite). Both deploy independently to Cloud Run.

  ---

  ## Features

  - **33 workflow node types** — triggers (manual, schedule, webhook, API), data (CSV, DB, HTTP, PDF), transforms (filter, map, join, group-by, dedupe), control (condition, router, merge), AI (agent, embedder), integrations (GitHub, Notion, Slack, Gmail, MCP), output (response, CSV/Excel writer).
  - **Auto-discovery** — drop a `.yaml` + `.py` pair in `backend/engine/nodes/` and the runtime picks it up. Single source of truth: the YAML spec drives the executor, the Copilot prompt, the validator, AND the frontend's block palette.
  - **Self-healing Copilot** — Gemini-powered planner with 3-attempt retry. Uses an exhaustive prompt (block registry + field keys + worked patterns), validates output against a spec-derived schema, and feeds traceback into the next attempt.
  - **DAG executor** — topological sort + per-level execution + branch-aware edges (`sourceHandle: "true"|"false"` for conditions, `sourceHandle: route.label` for routers).
  - **86 pytest tests** — covers every node, the DAG runner, the validator, and 15 end-to-end Copilot prompts.

  ---

  ## Quickstart (local dev)

  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r backend/requirements.txt
  cp .env.example .env  # then add GOOGLE_API_KEY
  uvicorn backend.app.main:app --reload --port 8080
  ```

  Visit http://localhost:8080/docs for the interactive OpenAPI UI.

  ---

  ## Build & run with Docker

  ```bash
  docker build -t orchestrator-backend .
  docker run -p 8080:8080 \
    -e GOOGLE_API_KEY=your-key \
    -e ALLOWED_ORIGINS="https://your-frontend.run.app" \
    orchestrator-backend
  ```

  ---

  ## Deploy to Cloud Run

  ```bash
  gcloud builds submit --tag gcr.io/PROJECT_ID/orchestrator-backend
  gcloud run deploy orchestrator-backend \
    --image gcr.io/PROJECT_ID/orchestrator-backend \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=...,ALLOWED_ORIGINS=https://your-frontend.run.app" \
    --memory 1Gi --cpu 1 --timeout 600s
  ```

  > `--timeout 600s` matters: the Copilot streaming endpoint can take 30-60s for complex prompts.

  ---

  ## Project structure

  ```
  backend/
    app/                       # FastAPI HTTP layer
      main.py                  # entrypoint: CORS, /healthz, mount routers
      routers/
        workflows.py           # CRUD + /execute
        copilot.py             # /chat (SSE streaming)
        blocks.py              # /blocks (node registry as JSON)
        contracts.py           # /contracts (OpenAPI-style spec for the UI)
      schemas.py               # Pydantic request/response models
    engine/
      registry.py              # auto-discovers NODE_SPEC modules
      node_spec.py             # NodeSpec dataclass + YAML loader
      dag_runner.py            # topo-sort + per-level executor
      validator.py             # pure DAG validation (cycle detection, etc.)
      expressions.py           # safe row-expression evaluator
      nodes/                   # ⬅ ONE yaml + ONE py per node type
        filter.yaml + filter.py
        condition.yaml + condition.py
        agent.yaml + agent.py
        ...                    # 33 total
    copilot/
      workflow_generator.py    # Gemini planner + self-healing loop + Zod-style validator
    data_sources/
      metadata/*.yaml          # 4 mock datasets (employees, orders, products, support)
    tests/                     # 86 pytest tests
    Dockerfile                 # original (kept for reference; root Dockerfile is canonical)
  scripts/
    gen_ts_specs.py            # regenerates the frontend's TS specs from YAMLs
  docs/                        # architecture + API reference
  ```

  ---

  ## Environment variables

  | Var | Required | Purpose |
  |---|---|---|
  | `GOOGLE_API_KEY` | for AI features | Gemini access for the `agent` node and Copilot |
  | `ALLOWED_ORIGINS` | recommended | CORS allowlist (comma-separated, default `*`) |
  | `PORT` | runtime | HTTP port (default `8080`, Cloud Run sets this) |
  | `GITHUB_TOKEN` | optional | GitHub integration nodes |
  | `NOTION_API_KEY` | optional | Notion integration nodes |
  | `SLACK_WEBHOOK_URL` | optional | Slack notification node |
  | `GMAIL_CLIENT_SECRET` | optional | Gmail integration |
  | `MCP_SERVER_URL` | optional | Model Context Protocol integration |

  See `.env.example` for a copyable template.

  ---

  ## API surface (highlights)

  | Method | Path | Purpose |
  |---|---|---|
  | GET | `/api/healthz` | Liveness probe |
  | GET | `/api/blocks` | Full node registry (used by the UI's block palette) |
  | GET | `/api/contracts` | Per-node param spec (for Copilot prompt) |
  | GET | `/api/workflows` | List workflows |
  | POST | `/api/workflows` | Create workflow |
  | GET | `/api/workflows/{id}` | Read workflow |
  | PATCH | `/api/workflows/{id}` | Update workflow |
  | POST | `/api/workflows/{id}/execute` | Run workflow synchronously |
  | POST | `/api/copilot/chat` | Streaming SSE: thinking → workflow_created |

  Full OpenAPI: `/docs` (Swagger UI) or `/openapi.json`.

  ---

  ## Adding a new node type

  1. Create `backend/engine/nodes/mynode.yaml` declaring `type_id`, `category`, `params`, `outputs`.
  2. Create `backend/engine/nodes/mynode.py` exporting `NODE_SPEC = _spec_from_yaml(__file__, run=my_run_fn)`.
  3. Restart — auto-discovery picks it up. The UI's block palette will show the new node next time it polls `/api/blocks`.
  4. (If frontend repo): re-run `scripts/gen_ts_specs.py` to refresh the generated TS specs.

  No code changes anywhere else.

  ---

  ## Testing

  ```bash
  cd backend && pytest -v
  ```

  Copilot regression suite (15 prompts, requires `GOOGLE_API_KEY` + a running server) lives at `backend/tests/test_copilot_prompts.py`.

  ---

  ## License

  MIT
  