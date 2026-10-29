"""Regression checks for the runnable portfolio path; all endpoints mocked."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest
from langchain_core.tools import tool

from runtime.events.protocol import ApprovalRequestEvent, ToolCallEvent, ToolResultEvent
from runtime.graph.nodes._tool_tracing import make_traced_tools
from runtime.graph.nodes.reporter import reporter_node
from runtime.graph.nodes.asset_resolution import asset_resolution_node
from runtime.graph.nodes.supervisor import AgentTaskDecision, supervisor_node
from runtime.graph.nodes.log_detective import log_detective_node
from runtime.graph.nodes.machine_check import machine_check_node
from runtime.graph.nodes.security_guard import security_guard_node
from security.policies.extraction import EvidenceCollector
from security.schemas.findings import LogFindings, MachineFindings, SecurityFindings
from security.schemas.report import InvestigationReport
from surfaces.api.investigation import InvestigationRequest, stream_investigation


@pytest.mark.asyncio
@pytest.mark.parametrize("finding_risk,model_status,expected", [
    ("critical", "normal", "critical"), ("high", "normal", "warning"),
    ("low", "critical", "normal"), ("medium", "normal", "warning"),
])
async def test_report_severity_follows_evidence_not_model(finding_risk, model_status, expected):
    model = MagicMock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=InvestigationReport(
        alert_status=model_status, summary="Model explanation", recommendations="Review the evidence.",
    ))
    with (
        patch("runtime.graph.nodes.reporter.build_model", return_value=model),
        patch("runtime.graph.nodes.reporter.get_stream_writer", return_value=lambda _: None),
    ):
        result = await reporter_node({"target": "example.com", "session_id": "s",
            "findings": {"logs": {"risk_level": finding_risk, "evidence_status": "available"}}})
    artifact = result["artifacts"][0]
    assert artifact["risk_level"] == finding_risk
    assert artifact["report"]["alert_status"] == expected


def test_qps_without_error_query_does_not_fabricate_zero_error_rates():
    collector = EvidenceCollector("logs")
    collector.observe("query_es_qps_trend", {"trend": [{"count": 1000}]})
    assert "rate_5xx" not in collector.extract_logs()
    assert collector.evidence_status() == "partial"


def test_no_security_tools_is_insufficient_not_a_clean_bill_of_health():
    collector = EvidenceCollector("security")
    assert collector.evidence_status() == "insufficient"
    collector.observe("check_ddos_status", {"status": "ok", "events": [], "count": 0})
    assert collector.evidence_status() == "partial"


@pytest.mark.asyncio
async def test_concurrent_tool_results_have_stable_unique_ids(monkeypatch):
    events = []
    monkeypatch.setattr("runtime.graph.nodes._tool_tracing.get_stream_writer", lambda: events.append)

    @tool
    async def query(asset: str) -> str:
        """A slow first asset and fast second asset."""
        await asyncio.sleep(0.02 if asset == "first" else 0)
        return asset

    [traced] = make_traced_tools([query], "worker")
    await asyncio.gather(traced.ainvoke({"asset": "first"}), traced.ainvoke({"asset": "second"}))
    calls = [event for event in events if isinstance(event, ToolCallEvent)]
    results = [event for event in events if isinstance(event, ToolResultEvent)]
    assert len({event.call_id for event in calls}) == 2
    for event in results:
        assert next(call for call in calls if call.call_id == event.call_id).tool_input["asset"] == event.output
    assert results[0].output == "second"


@pytest.mark.asyncio
async def test_approval_is_exposed_only_after_interrupt_is_saved(monkeypatch):
    saved = False

    class Graph:
        async def astream(self, *args, **kwargs):
            nonlocal saved
            yield ApprovalRequestEvent(session_id="s", findings={})
            await asyncio.sleep(0)
            saved = True

    @asynccontextmanager
    async def checkpoint():
        yield object()

    monkeypatch.setattr("surfaces.api.investigation.get_checkpointer", checkpoint)
    monkeypatch.setattr("surfaces.api.investigation.build_investigation_graph", lambda **_: Graph())
    response = await stream_investigation(InvestigationRequest(target="example.com", session_id="s"))
    frames = []
    async for frame in response.body_iterator:
        assert saved
        frames.append(frame)
    assert '"approval_request"' in frames[0]
    assert '"done"' in frames[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("module,node,finding,missing_key", [
    ("log_detective", log_detective_node,
     LogFindings(summary="Claimed error", rate_5xx=.99, error_rate={"5xx": "99%"}), "rate_5xx"),
    ("machine_check", machine_check_node,
     MachineFindings(summary="Claimed overload", cpu_pct=.99), "cpu_pct"),
    ("security_guard", security_guard_node,
     SecurityFindings(summary="Claimed attack", cc_input_pps=999999), "cc_input_pps"),
])
async def test_unobserved_model_numbers_cannot_drive_policy(module, node, finding, missing_key):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="analysis")]})
    extractor = MagicMock()
    extractor.with_structured_output.return_value.ainvoke = AsyncMock(return_value=finding)
    path = f"runtime.graph.nodes.{module}"
    with (
        patch(f"{path}.get_stream_writer", return_value=lambda _: None),
        patch(f"{path}.create_react_agent", return_value=agent),
        patch(f"{path}.build_model", side_effect=[MagicMock(), extractor]),
    ):
        result = await node({"target": "example.com", "agent_task": "collect facts"})
    dimension = {"log_detective": "logs", "machine_check": "machine", "security_guard": "security"}[module]
    collected = result["findings"][dimension]
    assert collected[missing_key] is None
    assert collected["evidence_status"] == "insufficient"
    assert collected["risk_level"] in {"low", "medium"}
    if dimension == "logs":
        assert collected["error_rate"] == {}


@pytest.mark.asyncio
async def test_fake_fixture_window_reaches_worker_task(monkeypatch):
    monkeypatch.setattr("runtime.graph.nodes.asset_resolution.get_settings",
                        lambda: SimpleNamespace(data_source="fake"))
    monkeypatch.setattr("runtime.graph.nodes.asset_resolution._resolve_domain", AsyncMock(return_value=[]))
    resolved = await asset_resolution_node({"target": "api2.xs2027.cn"})
    assert resolved["analysis_window"] == {"start": "2026-04-18 12:18:00", "end": "2026-04-18 12:36:00"}
    model = MagicMock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=AgentTaskDecision(agent_task="Inspect logs."),
    )
    with patch("runtime.graph.nodes.supervisor.build_model", return_value=model):
        result = await supervisor_node({"target": "api2.xs2027.cn", **resolved})
    assert "2026-04-18 12:18:00" in result["agent_task"]
    assert "2026-04-18 12:36:00" in result["agent_task"]
