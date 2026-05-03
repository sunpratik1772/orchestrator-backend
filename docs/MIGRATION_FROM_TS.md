# Migration from the TypeScript backend

This Python backend is a behavioural drop-in for the previous Express
service in `artifacts/api-server`. The API contract is preserved.

## Endpoint mapping

| TS (Express)                       | Python (FastAPI)              | Notes                       |
|------------------------------------|-------------------------------|-----------------------------|
| `GET /workflows`                   | `GET /workflows`              | Same shape.                 |
| `POST /workflows`                  | `POST /workflows`             | Same shape.                 |
| `GET /workflows/:id`               | `GET /workflows/{id}`         |                             |
| `PUT /workflows/:id`               | `PUT /workflows/{id}`         |                             |
| `DELETE /workflows/:id`            | `DELETE /workflows/{id}`      |                             |
| `POST /workflows/:id/execute`      | `POST /workflows/{id}/execute`| Same response shape.        |
| `POST /copilot/chat` (SSE)         | `POST /copilot/chat` (SSE)    | Same event types.           |
| `GET /blocks`                      | `GET /blocks`                 | Same compact shape.         |
| `GET /mock-datasets`               | `GET /mock-datasets`          | Returns dataset filenames.  |
| `GET /stats`                       | `GET /stats`                  |                             |
| `GET /logs`                        | `GET /logs`                   |                             |
| (new)                              | `GET /node-manifest`          | Per-node UI metadata.       |
| (new)                              | `GET /contracts`              | Versioned contract export.  |

## Behavioural differences

* Storage moved from in-memory + JSON to per-workflow JSON files
  under `backend/drafts/`. Same observable behaviour, easier to debug.
* Expression evaluator uses Python eval against a restricted builtin set,
  with JS → Python coercion (`===`, `&&`, `!=`, `true`/`false` → Python).
  All existing user expressions (`row.score >= 75`, etc.) work unchanged.
* Integration nodes return `{ simulated: true, needsIntegration: ... }`
  when secrets are missing — matches the TS `simulated` flag.

## Frontend changes required

Just point the frontend at the new base URL. No other code changes needed.

```ts
// before
const API_BASE = "/api";

// after — point at the new Cloud Run service.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
```

## What's NOT migrated

* The `api-server` artifact stays in the monorepo for reference. It can be
  deleted or kept side-by-side during cutover. The two backends can run
  against the same frontend behind a feature flag if you want a phased rollout.
  