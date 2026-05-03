# orchestrator-backend

  > Python FastAPI workflow engine. Auto-discovered node registry, DAG executor, and self-healing Gemini Copilot.

  Standalone backend for the orchestrator stack. Pairs with [`orchestrator-frontend`](https://github.com/sunpratik1772/orchestrator-frontend). Both deploy independently to Cloud Run.

  ## Features

  - **33 workflow node types** — triggers, data (CSV/DB/HTTP/PDF), transforms, control flow, AI (agent, embedder), integrations (GitHub, Notion, **Slack**, Gmail, MCP), output.
  - **Auto-discovery** — drop a `.yaml` + `.py` pair in `backend/engine/nodes/` and the runtime picks it up.
  - **Self-healing Copilot** — Gemini-powered planner with 3-attempt retry + Zod-style validator.
  - **DAG executor** — topological sort + per-level execution + branch-aware edges.
  - **86 pytest tests** — every node + DAG runner + validator + 15-prompt Copilot regression.

  ## Slack integration (NEW)

  The slack node now supports **Bot Token** auth (preferred) via `chat.postMessage`, with webhook URL fallback.

  Auth precedence:
  1. `SLACK_API_TOKEN_NOW` (or `SLACK_BOT_TOKEN`) → Bearer auth + `https://slack.com/api/chat.postMessage`
  2. `webhookUrl` config param OR `SLACK_WEBHOOK_URL` env → POST to webhook
  3. Neither → returns `{simulated: true}` stub so the DAG keeps running

  The bot needs the `chat:write` scope (and `chat:write.public` if posting to public channels it isn't a member of).

  ## Quickstart

  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r backend/requirements.txt
  cp .env.example .env  # add GOOGLE_API_KEY, SLACK_API_TOKEN_NOW, etc.
  uvicorn backend.app.main:app --reload --port 8080
  ```

  Visit http://localhost:8080/docs for Swagger UI.

  ## Docker

  ```bash
  docker build -t orchestrator-backend .
  docker run -p 8080:8080 \
    -e GOOGLE_API_KEY=... \
    -e SLACK_API_TOKEN_NOW=xoxb-... \
    -e ALLOWED_ORIGINS="https://your-frontend.run.app" \
    orchestrator-backend
  ```

  ## Deploy to Cloud Run

  ```bash
  gcloud builds submit --tag gcr.io/PROJECT_ID/orchestrator-backend
  gcloud run deploy orchestrator-backend \
    --image gcr.io/PROJECT_ID/orchestrator-backend \
    --region us-central1 --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=...,SLACK_API_TOKEN_NOW=xoxb-...,ALLOWED_ORIGINS=https://your-frontend.run.app" \
    --memory 1Gi --cpu 1 --timeout 600s
  ```

  > `--timeout 600s` matters: the Copilot streaming endpoint can take 30-60s for complex prompts.

  ## Project structure

  ```
  backend/
    app/                       # FastAPI HTTP layer (routers, schemas)
    engine/
      registry.py              # auto-discovers NODE_SPEC modules
      dag_runner.py            # topo-sort + per-level executor
      validator.py             # DAG validation
      nodes/                   # ⬅ ONE yaml + ONE py per node type (33 total)
        slack.yaml + slack.py  # Bot Token (preferred) → webhook → stub
        ...
    copilot/
      workflow_generator.py    # Gemini planner + self-healing loop
    data_sources/metadata/     # 4 mock datasets
    tests/                     # 86 pytest tests
  scripts/
    gen_ts_specs.py            # regenerates frontend's TS specs from YAMLs
  docs/
  ```

  ## Environment variables

  | Var | Required | Purpose |
  |---|---|---|
  | `GOOGLE_API_KEY` | for AI features | Gemini for the `agent` node + Copilot |
  | `ALLOWED_ORIGINS` | recommended | CORS allowlist (comma-separated) |
  | `PORT` | runtime | HTTP port (default 8080) |
  | `SLACK_API_TOKEN_NOW` | optional | Slack Bot Token (preferred for slack node) |
  | `SLACK_BOT_TOKEN` | optional | Alias for `SLACK_API_TOKEN_NOW` |
  | `SLACK_WEBHOOK_URL` | optional | Slack webhook fallback |
  | `GITHUB_TOKEN` | optional | GitHub integration nodes |
  | `NOTION_API_KEY` | optional | Notion integration |
  | `GMAIL_CLIENT_SECRET` | optional | Gmail integration |
  | `MCP_SERVER_URL` | optional | Model Context Protocol integration |

  ## API surface

  | Method | Path | Purpose |
  |---|---|---|
  | GET | `/healthz` | Liveness probe |
  | GET | `/api/blocks` | Full node registry (used by UI's block palette) |
  | GET | `/api/contracts` | Per-node param spec (Copilot prompt source) |
  | GET | `/api/workflows` | List workflows |
  | POST | `/api/workflows` | Create workflow |
  | POST | `/api/workflows/{id}/execute` | Run workflow synchronously |
  | POST | `/api/copilot/chat` | Streaming SSE: thinking → workflow_created |

  Full OpenAPI: `/docs` or `/openapi.json`.

  ## Adding a new node type

  1. Create `backend/engine/nodes/mynode.yaml` (declare `type_id`, `category`, `params`, `outputs`).
  2. Create `backend/engine/nodes/mynode.py` exporting `NODE_SPEC = _spec_from_yaml(__file__, run=my_run_fn)`.
  3. Restart — auto-discovery picks it up.
  4. (Frontend repo): re-run `scripts/gen_ts_specs.py` to refresh generated TS specs.

  ## Testing

  ```bash
  cd backend && pytest -v
  ```

  ## License

  MIT
  