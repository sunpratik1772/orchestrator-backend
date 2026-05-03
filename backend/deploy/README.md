# Deploy

Two equivalent paths:

1. **Cloud Build trigger** — point GCB at this repo with `backend/deploy/cloudbuild.yaml`
   as the build config and `backend/` as the source.
2. **Manual** — `gcloud run deploy` from `backend/` using the included Dockerfile.

Required secret:

```bash
echo -n "<your-key>" | gcloud secrets create GOOGLE_API_KEY --data-file=-
```

Optional secrets (Slack / Notion / GitHub etc.) — add the same way and reference
in `cloudbuild.yaml` via additional `--update-secrets=KEY=KEY:latest` flags.
  