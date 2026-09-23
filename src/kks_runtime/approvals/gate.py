"""
HITL approval gate node.

Integrated into the investigation graph between supervisor and reporter.
The supervisor routes to this node only when EvidencePolicy.requires_approval()
returns True (i.e., at least one finding has risk_level == 'critical').

Execution model (LangGraph interrupt semantics):
  1. First call: interrupt() raises GraphInterrupt after saving a checkpoint.
     The graph is paused; the caller receives the paused state.
  2. Resume call: caller sends Command(resume={"approved": True/False, "approver": "..."}).
     interrupt() returns that dict; the node emits ApprovalDecisionEvent and
     returns the appropriate state update.

The supervisor emits ApprovalRequestEvent before routing here, so the SSE
stream shows the request event before the graph pauses.
"""

from __future__ import annotations

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from kks_runtime.events.protocol import ApprovalDecisionEvent
from kks_runtime.state.session import SessionState


async def approval_gate_node(state: SessionState) -> dict:
    """
    HITL gate: pause the graph for human review; continue or abort on resume.

    On first execution: interrupt() pauses the graph (raises GraphInterrupt internally).
    On resume execution: interrupt() returns the resume payload.

    Resume payload expected:
        {"approved": bool, "approver": str}

    Returns:
        On approve → {} (no state change; graph continues to reporter)
        On reject  → {"status": "failed", "error": "<message>"}
    """
    session_id = state.get("session_id", "")
    findings = state.get("findings", {})

    # Pause for human review.
    # First invocation: GraphInterrupt is raised here; code below does NOT run.
    # Second invocation (after Command(resume=...)): returns the resume dict.
    decision: dict = interrupt(
        {
            "type": "approval_request",
            "session_id": session_id,
            "findings": findings,
        }
    )

    # --- The following runs only after a successful resume ---
    approved: bool = bool(decision.get("approved", False))
    approver: str = str(decision.get("approver", "unknown"))

    write = get_stream_writer()
    write(
        ApprovalDecisionEvent(
            session_id=session_id,
            approved=approved,
            approver=approver,
        )
    )

    if not approved:
        return {
            "status": "failed",
            "error": f"Investigation rejected by approver '{approver}'",
        }
    return {}
