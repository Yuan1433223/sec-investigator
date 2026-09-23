"""
SSE (Server-Sent Events) wire format for the investigation stream.

Converts RuntimeEvent objects (written by graph nodes via get_stream_writer())
into SSE frames. Never references LangGraph node names — CLAUDE.md hard rule 2.

Wire format:  data: <JSON>\n\n
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from kks_runtime.events.protocol import (
    ApprovalDecisionEvent,
    ApprovalRequestEvent,
    ArtifactEvent,
    ErrorEvent,
    FinalEvent,
    RuntimeEvent,
    StatusEvent,
    ToolCallEvent,
    ToolResultEvent,
)


@dataclass
class SSEFrame:
    type: str  # "status" | "tool_call" | "tool_result" | "artifact" | "final" | "error" | "done"
    data: dict[str, Any]


def runtime_event_to_sse(event: RuntimeEvent) -> SSEFrame | None:
    """
    Map a RuntimeEvent to an SSEFrame.

    Returns None for event types that should not be forwarded to the client.
    """
    if isinstance(event, StatusEvent):
        return SSEFrame(type="status", data={"node": event.node, "message": event.message})

    if isinstance(event, ToolCallEvent):
        return SSEFrame(
            type="tool_call",
            data={
                "node": event.node,
                "tool_name": event.tool_name,
                "tool_input": event.tool_input,
            },
        )

    if isinstance(event, ToolResultEvent):
        return SSEFrame(
            type="tool_result",
            data={"node": event.node, "tool_name": event.tool_name, "output": event.output},
        )

    if isinstance(event, ArtifactEvent):
        return SSEFrame(
            type="artifact",
            data={"artifact_type": event.artifact_type, "data": event.data},
        )

    if isinstance(event, FinalEvent):
        return SSEFrame(
            type="final",
            data={"findings": event.findings, "artifacts": event.artifacts},
        )

    if isinstance(event, ErrorEvent):
        return SSEFrame(
            type="error",
            data={"message": event.message, "node": event.node},
        )

    if isinstance(event, ApprovalRequestEvent):
        return SSEFrame(
            type="approval_request",
            data={"session_id": event.session_id, "findings": event.findings},
        )

    if isinstance(event, ApprovalDecisionEvent):
        return SSEFrame(
            type="approval_decision",
            data={
                "session_id": event.session_id,
                "approved": event.approved,
                "approver": event.approver,
            },
        )

    return None


def sse_frame_to_wire(frame: SSEFrame) -> str:
    """Serialize an SSEFrame to the SSE wire format: 'data: JSON\\n\\n'."""
    payload = json.dumps({"type": frame.type, **frame.data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


DONE_FRAME = "data: {\"type\": \"done\"}\n\n"
