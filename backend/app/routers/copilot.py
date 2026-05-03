"""
POST /copilot/chat — SSE streaming Copilot endpoint.

Mirrors the 8-layer self-healing pipeline of the original TS implementation:
plan → schema-validate → semantic dry-run → repair (max 3 attempts).
Heavy lifting lives in `copilot/workflow_generator.py`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .. import deps
from ..schemas import CopilotMessage
from ...copilot.workflow_generator import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


@router.post("/copilot/chat")
async def copilot_chat(req: Request) -> StreamingResponse:
    body = CopilotMessage.model_validate(await req.json())
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def producer():
        try:
            existing = deps.list_workflows()[:15]
            await run_pipeline(body.message, body.history, existing, queue)
        except Exception as e:
            logger.exception("copilot pipeline failed")
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)  # sentinel

    async def stream() -> AsyncIterator[bytes]:
        task = asyncio.create_task(producer())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event)
        finally:
            task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
  