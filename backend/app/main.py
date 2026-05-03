"""
FastAPI entrypoint.

Wires CORS, mounts every router under `app.routers`, and exposes
`/healthz` for liveness probes. Real logic lives in `engine/`,
`copilot/`, and the per-node modules.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import copilot, node_manifest, run, workflows

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="dbStudio Refactor",
    description="Per-node Python backend for visual AI workflow builder.",
    version="1.0.0",
)

_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# Mount all routers under /api so the generated TS client (which produces
# `/api/workflows`, `/api/copilot/chat`, etc.) works against both backends
# with only an origin swap.
app.include_router(workflows.router, prefix="/api")
app.include_router(run.router, prefix="/api")
app.include_router(copilot.router, prefix="/api")
app.include_router(node_manifest.router, prefix="/api")

# Keep legacy un-prefixed mounts for any callers that hit them directly.
app.include_router(workflows.router)
app.include_router(run.router)
app.include_router(copilot.router)
app.include_router(node_manifest.router)
  