from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class StatusEvent(BaseModel):
    type: Literal["status"] = "status"
    node: str
    message: str


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    node: str
    tool_name: str
    tool_input: dict[str, Any]


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    node: str
    tool_name: str
    output: Any


class ArtifactEvent(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact_type: str
    data: dict[str, Any]


class FinalEvent(BaseModel):
    type: Literal["final"] = "final"
    findings: dict[str, Any]
    artifacts: list[dict[str, Any]]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    node: str | None = None


class ApprovalRequestEvent(BaseModel):
    """Emitted by supervisor when a critical finding requires human approval before reporting."""

    type: Literal["approval_request"] = "approval_request"
    session_id: str
    findings: dict[str, Any]
    """Snapshot of all findings collected so far — used by the reviewer to assess risk."""


class ApprovalDecisionEvent(BaseModel):
    """Emitted by the approval gate after the human has responded (approve or reject)."""

    type: Literal["approval_decision"] = "approval_decision"
    session_id: str
    approved: bool
    approver: str
    """Identifier of the human approver (or system that provided the decision)."""


RuntimeEvent = Annotated[
    StatusEvent
    | ToolCallEvent
    | ToolResultEvent
    | ArtifactEvent
    | FinalEvent
    | ErrorEvent
    | ApprovalRequestEvent
    | ApprovalDecisionEvent,
    Field(discriminator="type"),
]
