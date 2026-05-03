# Deployment

## Cloud Run (recommended)

1. Build & push:
   ```bash
   gcloud builds submit --config=backend/deploy/cloudbuild.yaml backend/
   ```
2. Cloud Build will: build the Docker image, push to GCR, and deploy.

The Dockerfile is intentionally minimal — `python:3.11-slim` + the
contents of `requirements.txt`. Cold start typically < 3 s.

## Required env vars

| Name             | Purpose                       |
|------------------|-------------------------------|
| `GOOGLE_API_KEY` | Copilot + AI Agent node       |
| `PORT`           | Auto-set by Cloud Run         |
| `ALLOWED_ORIGINS`| Comma-separated CORS origins (set to your frontend URL in prod) |

## Optional integrations

| Name                  | Used by         |
|-----------------------|-----------------|
| `SLACK_API_TOKEN_NOW` | slack node (preferred — Bot Token, uses chat.postMessage) |
| `SLACK_BOT_TOKEN`     | slack node (alias for SLACK_API_TOKEN_NOW) |
| `SLACK_WEBHOOK_URL`   | slack node (fallback if no bot token)     |
| `NOTION_API_KEY`      | notion node     |
| `GITHUB_TOKEN`        | github node     |
| `GMAIL_CLIENT_SECRET` | gmail node      |
| `MCP_SERVER_URL`      | mcp node        |

When missing, the relevant node returns `{ simulated: true, needsIntegration: ... }`
instead of throwing — your DAG keeps running.

## Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --reload --port 8080
```

## Frontend

The frontend stays in the existing repo. Point its `VITE_API_BASE_URL`
(or equivalent) to your deployed Cloud Run URL. No other changes needed
— the API contract is identical to the previous TS server.
  