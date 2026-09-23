"""
Integration-level graph tests (all LLM calls mocked).

Supervisor routing is now deterministic (_next_worker based on required_findings).
Tests that want supervisor → reporter inject a pre-populated findings dict so
_next_worker immediately returns "reporter" without any LLM routing call.

The supervisor still calls build_model to generate agent_task; that is mocked
to return an AgentTaskDecision-compatible object.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from runtime.events.protocol import ArtifactEvent, FinalEvent, StatusEvent
from runtime.graph.investigation import build_investigation_graph
from security.schemas.report import InvestigationReport

# Pre-populated findings that satisfy all required_findings for IP targets
_ALL_FINDINGS = {"logs": {}, "machine": {}, "security": {}}
# Pre-populated findings that satisfy all required_findings for domain targets
_DOMAIN_FINDINGS = {"logs": {}, "security": {}}


def _mock_supervisor_llm() -> MagicMock:
    """
    Mock build_model for supervisor: returns a model whose with_structured_output()
    produces an object with agent_task='stub'. Routing itself is deterministic code.
    """
    task_decision = MagicMock()
    task_decision.agent_task = "Stub task instruction"
    mock_structured = AsyncMock(return_value=task_decision)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


def _mock_reporter_llm() -> MagicMock:
    """Return a mock LLM that produces a minimal InvestigationReport without API calls."""
    report = InvestigationReport(
        alert_status="normal",
        summary="System is operating normally (test stub).",
        recommendations="No action required.",
    )
    mock_structured = AsyncMock(return_value=report)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


@pytest.fixture
def graph():
    return build_investigation_graph(checkpointer=MemorySaver())


def test_graph_nodes_exist(graph):
    assert "supervisor" in graph.get_graph().nodes
    assert "reporter" in graph.get_graph().nodes
    assert "log_detective" in graph.get_graph().nodes
    assert "machine_check" in graph.get_graph().nodes
    assert "security_guard" in graph.get_graph().nodes


@pytest.mark.asyncio
async def test_graph_ainvoke_completes(graph):
    """Graph completes with status=completed when all findings are pre-populated."""
    _supervisor = "runtime.graph.nodes.supervisor.build_model"
    _reporter = "runtime.graph.nodes.reporter.build_model"
    with (
        patch(_supervisor, return_value=_mock_supervisor_llm()),
        patch(_reporter, return_value=_mock_reporter_llm()),
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": "1.2.3.4",
                "session_id": "test-01",
                "findings": _ALL_FINDINGS,  # all required → supervisor Agent20260422 to reporter
            },
            config={"configurable": {"thread_id": "test-01"}},
        )
    assert result["status"] == "completed"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["artifact_type"] == "investigation"
    assert result["artifacts"][0]["target"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_graph_ainvoke_domain_target(graph):
    """Domain target completes after log + security findings are present."""
    _supervisor = "runtime.graph.nodes.supervisor.build_model"
    _reporter = "runtime.graph.nodes.reporter.build_model"
    with (
        patch(_supervisor, return_value=_mock_supervisor_llm()),
        patch(_reporter, return_value=_mock_reporter_llm()),
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="investigate domain")],
                "target": "example.com",
                "session_id": "test-04",
                "findings": _DOMAIN_FINDINGS,  # logs + security sufficient for domain
            },
            config={"configurable": {"thread_id": "test-04"}},
        )
    assert result["status"] == "completed"
    assert result["artifacts"][0]["target"] == "example.com"


@pytest.mark.asyncio
async def test_graph_streams_artifact_event(graph):
    _supervisor = "runtime.graph.nodes.supervisor.build_model"
    _reporter = "runtime.graph.nodes.reporter.build_model"
    events = []
    with (
        patch(_supervisor, return_value=_mock_supervisor_llm()),
        patch(_reporter, return_value=_mock_reporter_llm()),
    ):
        async for chunk in graph.astream(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": "example.com",
                "session_id": "test-02",
                "findings": _DOMAIN_FINDINGS,
            },
            config={"configurable": {"thread_id": "test-02"}},
            stream_mode="custom",
        ):
            events.append(chunk)

    artifact_events = [e for e in events if isinstance(e, ArtifactEvent)]
    assert len(artifact_events) == 1
    assert artifact_events[0].artifact_type == "investigation"

    final_events = [e for e in events if isinstance(e, FinalEvent)]
    assert len(final_events) == 1
    assert "investigation" in final_events[0].artifacts[0]["artifact_type"]


@pytest.mark.asyncio
async def test_graph_streams_status_events(graph):
    """Reporter node emits at least two StatusEvent frames: start and complete."""
    _supervisor = "runtime.graph.nodes.supervisor.build_model"
    _reporter = "runtime.graph.nodes.reporter.build_model"
    events = []
    with (
        patch(_supervisor, return_value=_mock_supervisor_llm()),
        patch(_reporter, return_value=_mock_reporter_llm()),
    ):
        async for chunk in graph.astream(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": "1.2.3.4",
                "session_id": "test-03",
                "findings": _ALL_FINDINGS,
            },
            config={"configurable": {"thread_id": "test-03"}},
            stream_mode="custom",
        ):
            events.append(chunk)

    status_events = [e for e in events if isinstance(e, StatusEvent)]
    assert len(status_events) >= 2
    messages = [e.message for e in status_events]
    assert any("Generating" in m for m in messages)
    assert any("complete" in m for m in messages)


# ---------------------------------------------------------------------------
# RAG wiring: log_detective tool list includes search_knowledge
# ---------------------------------------------------------------------------


def test_log_detective_tool_list_includes_search_knowledge():
    """search_knowledge must be in _LOG_TOOLS — no LLM invocation needed."""
    from runtime.graph.nodes.log_detective import _LOG_TOOLS

    tool_names = {t.name for t in _LOG_TOOLS}
    assert "search_knowledge" in tool_names, (
        f"search_knowledge missing from _LOG_TOOLS. Got: {sorted(tool_names)}"
    )


def test_log_detective_tool_list_still_contains_es_tools():
    """Sanity: ES tools must not have been accidentally dropped."""
    from runtime.graph.nodes.log_detective import _LOG_TOOLS
    from security.tools.es_tools import ES_TOOLS

    es_names = {t.name for t in ES_TOOLS}
    tool_names = {t.name for t in _LOG_TOOLS}
    missing = es_names - tool_names
    assert not missing, f"ES tools dropped from _LOG_TOOLS: {missing}"
