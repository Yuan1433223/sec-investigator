"""Integration test — the A0 closed loop on the fake data source.

Drives the REAL compiled graph (MemorySaver checkpointer) with only the LLM
and the ReAct *agent loop* stubbed out. Crucially, the log_detective worker's
REAL traced ES tools still run against the fake adapter — the fake agent loop
invokes query_status_code_distribution for api2.xs2027.cn, the deterministic
evidence extractor derives a CRITICAL risk level from that tool output, the
graph pauses at approval_gate, resumes on approve, and the reporter emits a
real (non-degraded) structured report.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from runtime.events.protocol import ApprovalDecisionEvent, ApprovalRequestEvent
from runtime.graph.investigation import build_investigation_graph
from runtime.graph.nodes.log_detective import log_detective_node
from security.schemas.findings import LogFindings, MachineFindings, SecurityFindings
from security.schemas.report import InvestigationReport

TARGET = "api2.xs2027.cn"
_WINDOW = {
    "query_by": "domain",
    "value": TARGET,
    "start_time": "2026-04-18 12:18:00",
    "end_time": "2026-04-18 12:36:00",
}


class _LogReActAgent:
    """Fake ReAct loop: invokes the REAL traced status-distribution tool, then
    returns a final analysis message. The traced wrapper feeds the collector."""

    def __init__(self, tools):
        self._by_name = {t.name: t for t in tools}

    async def ainvoke(self, messages, config=None):
        tool = self._by_name["query_status_code_distribution"]
        await tool.ainvoke(_WINDOW)
        return {"messages": [AIMessage(content="Status distribution shows dominant 5xx errors.")]}


class _NeutralReActAgent:
    """Fake ReAct loop that does no tool calls and returns a neutral summary."""

    async def ainvoke(self, messages, config=None):
        return {"messages": [AIMessage(content="No anomalies of note.")]}


def _structured(obj) -> MagicMock:
    m = MagicMock()
    m.with_structured_output.return_value = MagicMock(ainvoke=AsyncMock(return_value=obj))
    return m


# ---------------------------------------------------------------------------
# Core: log_detective really calls fake tools and reaches CRITICAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_detective_reaches_critical_from_fake_tools():
    """The worker must derive critical from REAL fake tool output (not LLM recall)."""
    def _fake_build_model(profile, *a, **kw):
        if profile == "structured_extractor":
            return _structured(LogFindings.model_construct())
        return MagicMock(name="reasoner-model")  # unused by the fake agent loop

    with (
        patch("runtime.graph.nodes.log_detective.get_stream_writer",
              return_value=lambda _ev: None),
        patch("runtime.graph.nodes._tool_tracing.get_stream_writer",
              return_value=lambda _ev: None),
        patch("runtime.graph.nodes.log_detective.build_model",
              side_effect=_fake_build_model),
        patch("runtime.graph.nodes.log_detective.create_react_agent",
              side_effect=lambda **kw: _LogReActAgent(kw.get("tools", []))),
    ):
        result = await log_detective_node(
            {
                "target": TARGET,
                "agent_task": "Analyse access logs for api2.xs2027.cn",
                "session_id": "unit-logs-1",
            }
        )

    logs = result["findings"]["logs"]
    assert logs["risk_level"] == "critical", logs
    assert logs["rate_5xx"] >= 0.50, logs
    assert logs["error_rate"], logs  # populated from deterministic numbers, not {}
    assert "5xx" in logs["error_rate"]


# ---------------------------------------------------------------------------
# Full graph: critical → interrupt → approve → structured report
# ---------------------------------------------------------------------------


def _supervisor_fake() -> MagicMock:
    from runtime.graph.nodes.supervisor import AgentTaskDecision
    return _structured(AgentTaskDecision(agent_task="Investigate the target."))


def _reporter_fake() -> MagicMock:
    report = InvestigationReport(
        alert_status="critical",
        summary="源站 5xx 突增，已确认为应用层故障（结构化报告）。",
        recommendations="1. 检查源站应用进程；2. 切换备用源站。",
    )
    return _structured(report)


@pytest.mark.asyncio
async def test_full_graph_critical_approval_loop():
    graph = build_investigation_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "a0-approval-1"}}

    def _log_build_model(profile, *a, **kw):
        if profile == "structured_extractor":
            return _structured(LogFindings.model_construct())
        return MagicMock(name="reasoner-model")

    with (
        patch("runtime.graph.nodes.supervisor.build_model",
              side_effect=lambda *a, **kw: _supervisor_fake()),
        patch("runtime.graph.nodes.log_detective.build_model",
              side_effect=_log_build_model),
        patch("runtime.graph.nodes.log_detective.create_react_agent",
              side_effect=lambda **kw: _LogReActAgent(kw.get("tools", []))),
        patch("runtime.graph.nodes.machine_check.create_react_agent",
              side_effect=lambda **kw: _NeutralReActAgent()),
        patch("runtime.graph.nodes.machine_check.build_model",
              side_effect=lambda profile, *a, **kw: (
                  _structured(MachineFindings.model_construct())
                  if profile == "structured_extractor" else MagicMock()
              )),
        patch("runtime.graph.nodes.security_guard.create_react_agent",
              side_effect=lambda **kw: _NeutralReActAgent()),
        patch("runtime.graph.nodes.security_guard.build_model",
              side_effect=lambda profile, *a, **kw: (
                  _structured(SecurityFindings.model_construct())
                  if profile == "structured_extractor" else MagicMock()
              )),
        patch("runtime.graph.nodes.reporter.build_model",
              side_effect=lambda *a, **kw: _reporter_fake()),
    ):
        events: list = []
        async for chunk in graph.astream(
            {
                "messages": [AIMessage(content="investigate")],
                "target": TARGET,
                "session_id": "a0-approval-1",
            },
            config=config,
            stream_mode="custom",
        ):
            events.append(chunk)

        approval_reqs = [e for e in events if isinstance(e, ApprovalRequestEvent)]
        assert len(approval_reqs) == 1, "approval_gate must interrupt on critical"
        state = await graph.aget_state(config)
        assert state.values.get("status") != "completed"

        resume_events: list = []
        async for chunk in graph.astream(
            Command(resume={"approved": True, "approver": "reviewer"}),
            config=config,
            stream_mode="custom",
        ):
            resume_events.append(chunk)

    decisions = [e for e in resume_events if isinstance(e, ApprovalDecisionEvent)]
    assert len(decisions) == 1 and decisions[0].approved is True

    final = await graph.aget_state(config)
    assert final.values.get("status") == "completed"

    artifacts = final.values.get("artifacts", [])
    assert artifacts, "reporter must emit an artifact"
    summary = artifacts[-1].get("summary", "")
    assert "报告生成失败" not in summary, f"degraded report leaked: {summary}"
    assert artifacts[-1].get("report", {}).get("alert_status") == "critical"
