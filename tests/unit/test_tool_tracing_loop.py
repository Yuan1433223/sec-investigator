"""Unit tests for consecutive same-tool-call loop protection in make_traced_tools.

The GLM relay can loop on a no-op tool (e.g. current_time) for all 10 budget
slots. The loop-stop sentinel forces the LLM to summarize after max_repeated
consecutive calls of the same tool.
"""
from __future__ import annotations

import pytest
from langchain_core.tools import tool

from runtime.graph.nodes._tool_tracing import make_traced_tools


@tool
async def _fake_time() -> str:
    """Fake current time tool."""
    return "2026-10-01T12:00:00+08:00"


@tool
async def _fake_other() -> str:
    """Fake other tool."""
    return "other-result"


@pytest.fixture
def _patch_writer(monkeypatch):
    events = []
    monkeypatch.setattr(
        "runtime.graph.nodes._tool_tracing.get_stream_writer",
        lambda: events.append,
    )
    return events


@pytest.mark.asyncio
async def test_loop_stop_after_max_repeated_calls(_patch_writer):
    """Calling the same tool 5 times with max_repeated=4 → 4th call returns sentinel."""
    traced = make_traced_tools([_fake_time], "test", max_empty=0, max_repeated=4)
    tool = traced[0]

    # First 3 calls: normal
    for _ in range(3):
        r = await tool.ainvoke({})
        assert not str(r).startswith("[LOOP_STOP")

    # 4th call: loop-stop sentinel
    r = await tool.ainvoke({})
    assert str(r).startswith("[LOOP_STOP")


@pytest.mark.asyncio
async def test_loop_stop_resets_on_other_tool(_patch_writer):
    """Switching to another tool resets the repeated counter."""
    traced = make_traced_tools(
        [_fake_time, _fake_other], "test", max_empty=0, max_repeated=3
    )
    t1, t2 = traced

    # 2 calls on t1 → count=2
    await t1.ainvoke({})
    await t1.ainvoke({})
    # switch to t2 → should NOT trigger loop-stop (count reset)
    r = await t2.ainvoke({})
    assert not str(r).startswith("[LOOP_STOP")
    # back to t1 → count starts fresh at 1
    r = await t1.ainvoke({})
    assert not str(r).startswith("[LOOP_STOP")


@pytest.mark.asyncio
async def test_loop_stop_disabled_when_zero(_patch_writer):
    """max_repeated=0 disables loop-stop entirely."""
    traced = make_traced_tools([_fake_time], "test", max_empty=0, max_repeated=0)
    tool = traced[0]
    for _ in range(8):
        r = await tool.ainvoke({})
        assert not str(r).startswith("[LOOP_STOP")


@pytest.mark.asyncio
async def test_evidence_sink_called_before_sentinel(_patch_writer):
    """evidence_sink receives raw result even when loop-stop sentinel replaces it."""
    seen: list[tuple[str, object]] = []
    traced = make_traced_tools(
        [_fake_time], "test",
        max_empty=0, max_repeated=3,
        evidence_sink=lambda n, r: seen.append((n, r)),
    )
    tool = traced[0]
    for _ in range(4):
        await tool.ainvoke({})
    # evidence sink should have received 4 raw results (the real timestamp),
    # not the sentinel string
    assert len(seen) == 4
    for name, val in seen:
        assert name == "_fake_time"
        assert not str(val).startswith("[LOOP_STOP")
