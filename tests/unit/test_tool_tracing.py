"""
Tests for the tool-tracing wrapper (make_traced_tools).

Validates that:
- ToolCallEvent is emitted before tool execution
- ToolResultEvent is emitted after successful execution
- ToolResultEvent with error dict is emitted on exception
- The wrapped tool returns the same value as the original
- Tools that have no async coroutine are returned unchanged
"""
from __future__ import annotations

import pytest
from langchain_core.tools import tool

from runtime.events.protocol import ToolCallEvent, ToolResultEvent
from runtime.graph.nodes._tool_tracing import _is_empty_result, make_traced_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_events(func):
    """
    Decorator: capture events written via get_stream_writer() during func execution.

    Requires langgraph's get_stream_writer to be patchable to a list-appending stub.
    We monkeypatch the writer directly in the module under test.
    """
    pass  # inline below via monkeypatch


@tool
async def _sample_tool(x: int, y: int) -> dict:
    """Sample async tool: returns sum and product."""
    return {"sum": x + y, "product": x * y}


@tool
async def _failing_tool(msg: str) -> str:
    """Sample tool that always raises."""
    raise ValueError(f"deliberate error: {msg}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_traced_tool_returns_correct_result(monkeypatch):
    """Wrapped tool must return the same value as the original."""
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_sample_tool], "test_node")
    result = await traced.coroutine(3, 4)

    assert result == {"sum": 7, "product": 12}


@pytest.mark.asyncio
async def test_traced_tool_emits_call_event(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_sample_tool], "test_node")
    await traced.coroutine(1, 2)

    call_events = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(call_events) == 1
    assert call_events[0].node == "test_node"
    assert call_events[0].tool_name == "_sample_tool"


@pytest.mark.asyncio
async def test_traced_tool_emits_result_event(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_sample_tool], "test_node")
    await traced.coroutine(2, 3)

    result_events = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(result_events) == 1
    assert result_events[0].node == "test_node"
    assert result_events[0].tool_name == "_sample_tool"
    assert result_events[0].output == {"sum": 5, "product": 6}


@pytest.mark.asyncio
async def test_traced_tool_emits_error_result_on_exception(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_failing_tool], "test_node")
    with pytest.raises(ValueError):
        await traced.coroutine("boom")

    result_events = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(result_events) == 1
    assert "error" in result_events[0].output
    assert result_events[0].output["error"] == "ValueError"


@pytest.mark.asyncio
async def test_traced_tool_call_event_before_result_event(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_sample_tool], "test_node")
    await traced.coroutine(0, 0)

    types = [type(e).__name__ for e in events]
    assert types.index("ToolCallEvent") < types.index("ToolResultEvent")


@pytest.mark.asyncio
async def test_make_traced_tools_preserves_tool_metadata(monkeypatch):
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: (lambda _: None),
    )

    [traced] = make_traced_tools([_sample_tool], "test_node")
    assert traced.name == _sample_tool.name
    assert traced.description == _sample_tool.description
    assert traced.args_schema == _sample_tool.args_schema


@pytest.mark.asyncio
async def test_make_traced_tools_handles_multiple_tools(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    traced_list = make_traced_tools([_sample_tool, _sample_tool], "multi_node")
    assert len(traced_list) == 2

    await traced_list[0].coroutine(1, 1)
    await traced_list[1].coroutine(2, 2)

    call_events = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(call_events) == 2


# ---------------------------------------------------------------------------
# _is_empty_result unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ([], True),
        ((), True),
        ({}, True),
        ("", True),
        ("[]", True),
        ("{}", True),
        ("null", True),
        ("none", True),
        ("  null  ", True),
        ({"hits": 0}, True),
        ({"hits": []}, True),
        ({"hits": [1, 2]}, False),
        ({"hits": "0"}, True),
        ({"hits": "2"}, False),
        ({"total": 0}, True),
        ({"count": 0}, True),
        ({"items": []}, True),
        ({"results": []}, True),
        ({"data": []}, True),
        ({"hits": 1}, False),
        ({"items": [1]}, False),
        ([1], False),
        ("some data", False),
        ({"key": "value"}, False),
        (0, False),  # integers are not empty (not a special type)
    ],
)
def test_is_empty_result(value, expected):
    assert _is_empty_result(value) is expected


# ---------------------------------------------------------------------------
# Early-stop counter tests
# ---------------------------------------------------------------------------


@tool
async def _empty_tool(q: str) -> list:
    """Always returns empty list."""
    return []


@tool
async def _nonempty_tool(q: str) -> list:
    """Always returns non-empty list."""
    return [{"result": "data"}]


@pytest.mark.asyncio
async def test_early_stop_sentinel_after_max_empty_consecutive(monkeypatch):
    """After max_empty=2 consecutive empty results, sentinel string is returned."""
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_empty_tool], "test_node", max_empty=2)

    result1 = await traced.coroutine("q1")
    result2 = await traced.coroutine("q2")

    assert result1 == []  # first empty — counter=1, not yet at threshold
    assert "EARLY_STOP" in result2  # second empty — counter=2, sentinel injected
    assert "2" in result2


@pytest.mark.asyncio
async def test_early_stop_counter_resets_on_nonempty(monkeypatch):
    """Counter resets to 0 when a non-empty result follows empty ones."""
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    traced_empty, traced_nonempty = make_traced_tools(
        [_empty_tool, _nonempty_tool], "test_node", max_empty=3
    )

    await traced_empty.coroutine("q")   # counter → 1
    await traced_empty.coroutine("q")   # counter → 2
    result = await traced_nonempty.coroutine("q")  # counter → 0 (reset)
    assert result == [{"result": "data"}]  # normal result, not sentinel

    # Two more empties — counter starts fresh from 0, does not hit threshold yet
    await traced_empty.coroutine("q")   # counter → 1
    result2 = await traced_empty.coroutine("q")  # counter → 2
    assert "EARLY_STOP" not in str(result2)  # still below max_empty=3


@pytest.mark.asyncio
async def test_early_stop_disabled_when_max_empty_zero(monkeypatch):
    """max_empty=0 disables the counter entirely; sentinel is never returned."""
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    [traced] = make_traced_tools([_empty_tool], "test_node", max_empty=0)

    for _ in range(10):
        result = await traced.coroutine("q")
        assert result == []  # always raw result, never sentinel


@pytest.mark.asyncio
async def test_early_stop_counter_shared_across_tools(monkeypatch):
    """All tools in one make_traced_tools call share the same empty counter."""
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )

    traced_a, traced_b = make_traced_tools(
        [_empty_tool, _empty_tool], "test_node", max_empty=3
    )

    await traced_a.coroutine("q")  # counter → 1
    await traced_b.coroutine("q")  # counter → 2
    result = await traced_a.coroutine("q")  # counter → 3, sentinel
    assert "EARLY_STOP" in result
