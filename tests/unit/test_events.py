
from pydantic import TypeAdapter

from runtime.events.protocol import (
    ArtifactEvent,
    ErrorEvent,
    FinalEvent,
    RuntimeEvent,
    StatusEvent,
    ToolCallEvent,
    ToolResultEvent,
)

_adapter = TypeAdapter(RuntimeEvent)


def _roundtrip(event):
    raw = event.model_dump(mode="json")
    return _adapter.validate_python(raw)


def test_status_event_roundtrip():
    e = StatusEvent(node="supervisor", message="starting")
    result = _roundtrip(e)
    assert isinstance(result, StatusEvent)
    assert result.node == "supervisor"


def test_tool_call_event_roundtrip():
    e = ToolCallEvent(
        node="log_detective", tool_name="query_es_qps", tool_input={"domain": "example.com"}
    )
    result = _roundtrip(e)
    assert isinstance(result, ToolCallEvent)
    assert result.tool_input["domain"] == "example.com"


def test_tool_result_event_roundtrip():
    e = ToolResultEvent(node="log_detective", tool_name="query_es_qps", output={"qps": 500})
    result = _roundtrip(e)
    assert isinstance(result, ToolResultEvent)


def test_artifact_event_roundtrip():
    e = ArtifactEvent(artifact_type="investigation", data={"risk_level": "high"})
    result = _roundtrip(e)
    assert isinstance(result, ArtifactEvent)
    assert result.artifact_type == "investigation"


def test_final_event_roundtrip():
    e = FinalEvent(findings={"logs": {}}, artifacts=[{"artifact_type": "investigation"}])
    result = _roundtrip(e)
    assert isinstance(result, FinalEvent)


def test_error_event_roundtrip():
    e = ErrorEvent(message="timeout", node="machine_check")
    result = _roundtrip(e)
    assert isinstance(result, ErrorEvent)
    assert result.node == "machine_check"


def test_error_event_node_optional():
    e = ErrorEvent(message="unknown error")
    assert e.node is None
    result = _roundtrip(e)
    assert result.node is None


def test_discriminator_routes_correctly():
    raw = {"type": "status", "node": "reporter", "message": "done"}
    result = _adapter.validate_python(raw)
    assert isinstance(result, StatusEvent)
