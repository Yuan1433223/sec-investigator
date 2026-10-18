"""Unit test — structured_extractor returning None must not crash the worker.

GLM occasionally returns None from with_structured_output().ainvoke().
The worker must fall back to model_construct() and still produce a valid
findings dict with a deterministic risk_level.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


class _NeutralReActAgent:
    """Fake ReAct loop that returns a neutral summary (no tool calls)."""

    async def ainvoke(self, messages, config=None):
        return {"messages": [AIMessage(content="No anomalies of note.")]}


def _none_structured() -> MagicMock:
    """Return a mock whose with_structured_output().ainvoke() resolves to None."""
    m = MagicMock()
    m.with_structured_output.return_value = MagicMock(ainvoke=AsyncMock(return_value=None))
    return m


@pytest.mark.asyncio
async def test_log_detective_extractor_none_no_crash():
    """structured_extractor returns None → worker does not crash on .model_dump()."""
    from runtime.graph.nodes.log_detective import log_detective_node

    state = {
        "target": "api2.xs2027.cn",
        "agent_task": "Analyse logs for api2.xs2027.cn",
        "active_asset": None,
        "inspection_scope": [],
    }
    with patch("runtime.graph.nodes.log_detective.get_stream_writer", return_value=lambda _: None), patch(
        "runtime.graph.nodes.log_detective.create_react_agent",
        return_value=_NeutralReActAgent(),
    ), patch(
        "runtime.graph.nodes.log_detective.build_model",
        side_effect=lambda profile: _none_structured()
        if profile.value == "structured_extractor"
        else MagicMock(),
    ):
        result = await log_detective_node(state)
    assert "findings" in result
    assert "logs" in result["findings"]
    assert result["findings"]["logs"]["risk_level"] in {"low", "medium", "high", "critical"}


@pytest.mark.asyncio
async def test_machine_check_extractor_none_no_crash():
    """machine_check structured_extractor returns None → no crash."""
    from runtime.graph.nodes.machine_check import machine_check_node

    state = {
        "target": "118.178.13.52",
        "agent_task": "Check infrastructure for 118.178.13.52",
        "active_asset": None,
        "inspection_scope": [],
    }
    with patch("runtime.graph.nodes.machine_check.get_stream_writer", return_value=lambda _: None), patch(
        "runtime.graph.nodes.machine_check.create_react_agent",
        return_value=_NeutralReActAgent(),
    ), patch(
        "runtime.graph.nodes.machine_check.build_model",
        side_effect=lambda profile: _none_structured()
        if profile.value == "structured_extractor"
        else MagicMock(),
    ):
        result = await machine_check_node(state)
    assert "findings" in result
    assert "machine" in result["findings"]
    assert result["findings"]["machine"]["risk_level"] in {"low", "medium", "high", "critical"}


@pytest.mark.asyncio
async def test_security_guard_extractor_none_no_crash():
    """security_guard structured_extractor returns None → no crash."""
    from runtime.graph.nodes.security_guard import security_guard_node

    state = {
        "target": "api2.xs2027.cn",
        "agent_task": "Check security protection for api2.xs2027.cn",
        "active_asset": None,
        "inspection_scope": [],
    }
    with patch("runtime.graph.nodes.security_guard.get_stream_writer", return_value=lambda _: None), patch(
        "runtime.graph.nodes.security_guard.create_react_agent",
        return_value=_NeutralReActAgent(),
    ), patch(
        "runtime.graph.nodes.security_guard.build_model",
        side_effect=lambda profile: _none_structured()
        if profile.value == "structured_extractor"
        else MagicMock(),
    ):
        result = await security_guard_node(state)
    assert "findings" in result
    assert "security" in result["findings"]
    assert result["findings"]["security"]["risk_level"] in {"low", "medium", "high", "critical"}
