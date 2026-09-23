"""
Investigation API router.

Two routes:
  POST /investigation        — non-streaming, returns InvestigationOutput JSON
  POST /investigation/stream — SSE stream of RuntimeEvent frames

Both routes create the graph + checkpointer per-request (no module-level
singletons — CLAUDE.md hard rule 4).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from runtime.checkpoint.factory import get_checkpointer
from runtime.graph.investigation import build_investigation_graph
from surfaces.web.sse import DONE_FRAME, runtime_event_to_sse, sse_frame_to_wire

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investigation", tags=["Investigation"])


class InvestigationRequest(BaseModel):
    target: str
    session_id: str
    question: str | None = None


def _build_input(req: InvestigationRequest) -> dict[str, Any]:
    content = req.question or f"Investigate: {req.target}"
    return {
        "messages": [HumanMessage(content=content)],
        "target": req.target,
        "session_id": req.session_id,
    }


def _graph_config(session_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": session_id}, "recursion_limit": 100}


@router.post("")
async def run_investigation(req: InvestigationRequest) -> dict:
    """Non-streaming investigation — returns full output when complete."""
    async with get_checkpointer() as checkpointer:
        graph = build_investigation_graph(checkpointer=checkpointer)
        result = await graph.ainvoke(
            _build_input(req),
            config=_graph_config(req.session_id),
        )
    return result


@router.post("/stream")
async def stream_investigation(req: InvestigationRequest) -> StreamingResponse:
    """SSE stream — emits RuntimeEvent frames as the investigation progresses."""

    async def _generate() -> AsyncIterator[str]:
        try:
            async with get_checkpointer() as checkpointer:
                graph = build_investigation_graph(checkpointer=checkpointer)
                async for event in graph.astream(
                    _build_input(req),
                    config=_graph_config(req.session_id),
                    stream_mode="custom",
                ):
                    frame = runtime_event_to_sse(event)
                    if frame is not None:
                        yield sse_frame_to_wire(frame)
        except Exception as exc:
            logger.exception("Stream error for session=%s", req.session_id)
            from surfaces.web.sse import SSEFrame

            frame = SSEFrame(type="error", data={"message": str(exc), "node": None})
            yield sse_frame_to_wire(frame)
        finally:
            yield DONE_FRAME

    return StreamingResponse(_generate(), media_type="text/event-stream")
