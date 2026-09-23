"""Unit tests for SSE frame conversion (runtime_event_to_sse, sse_frame_to_wire)."""
import json

from runtime.events.protocol import (
    ApprovalDecisionEvent,
    ApprovalRequestEvent,
    ArtifactEvent,
    ErrorEvent,
    FinalEvent,
    StatusEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from surfaces.web.sse import DONE_FRAME, SSEFrame, runtime_event_to_sse, sse_frame_to_wire

# ---------------------------------------------------------------------------
# runtime_event_to_sse
# ---------------------------------------------------------------------------


def test_status_event_maps_to_status_frame():
    event = StatusEvent(node="supervisor", message="Starting investigation")
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "status"
    assert frame.data["node"] == "supervisor"
    assert frame.data["message"] == "Starting investigation"


def test_tool_call_event_maps_to_tool_call_frame():
    event = ToolCallEvent(node="security_guard", tool_name="check_cc", tool_input={"ip": "1.2.3.4"})
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "tool_call"
    assert frame.data["tool_name"] == "check_cc"
    assert frame.data["tool_input"] == {"ip": "1.2.3.4"}


def test_tool_result_event_maps_to_tool_result_frame():
    event = ToolResultEvent(node="machine_check", tool_name="prom_query", output={"cpu": "45%"})
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "tool_result"
    assert frame.data["output"] == {"cpu": "45%"}


def test_artifact_event_maps_to_artifact_frame():
    event = ArtifactEvent(artifact_type="investigation", data={"target": "1.2.3.4"})
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "artifact"
    assert frame.data["artifact_type"] == "investigation"
    assert frame.data["data"]["target"] == "1.2.3.4"


def test_final_event_maps_to_final_frame():
    event = FinalEvent(findings={"security": {}}, artifacts=[{"type": "report"}])
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "final"
    assert "findings" in frame.data
    assert "artifacts" in frame.data


def test_error_event_maps_to_error_frame():
    event = ErrorEvent(message="something broke", node="reporter")
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "error"
    assert frame.data["message"] == "something broke"
    assert frame.data["node"] == "reporter"


def test_error_event_without_node():
    event = ErrorEvent(message="unknown error")
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.data["node"] is None


def test_approval_request_event_maps_to_frame():
    event = ApprovalRequestEvent(session_id="s1", findings={"security": {"risk_level": "critical"}})
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "approval_request"
    assert frame.data["session_id"] == "s1"


def test_approval_decision_event_maps_to_frame():
    event = ApprovalDecisionEvent(session_id="s1", approved=True, approver="alice")
    frame = runtime_event_to_sse(event)
    assert frame is not None
    assert frame.type == "approval_decision"
    assert frame.data["approved"] is True
    assert frame.data["approver"] == "alice"


# ---------------------------------------------------------------------------
# sse_frame_to_wire
# ---------------------------------------------------------------------------


def test_wire_format_prefix():
    frame = SSEFrame(type="status", data={"node": "x", "message": "y"})
    wire = sse_frame_to_wire(frame)
    assert wire.startswith("data: ")
    assert wire.endswith("\n\n")


def test_wire_format_valid_json():
    frame = SSEFrame(type="artifact", data={"artifact_type": "investigation", "data": {}})
    wire = sse_frame_to_wire(frame)
    payload = json.loads(wire[len("data: "):].strip())
    assert payload["type"] == "artifact"
    assert payload["artifact_type"] == "investigation"


def test_done_frame_format():
    payload = json.loads(DONE_FRAME[len("data: "):].strip())
    assert payload["type"] == "done"


def test_wire_format_non_ascii_preserved():
    frame = SSEFrame(type="status", data={"node": "x", "message": "分析中"})
    wire = sse_frame_to_wire(frame)
    assert "分析中" in wire
