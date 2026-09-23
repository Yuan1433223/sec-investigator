"""
HITL approval gate tests.

Coverage:
- EvidencePolicy.requires_approval() — pure function, no LLM
- supervisor_node routing to approval_gate when critical finding present
- approval_gate_node resume semantics (approve and reject paths)
- Full graph interrupt + resume cycle with mocked LLMs
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from kks_runtime.events.protocol import ApprovalDecisionEvent, ApprovalRequestEvent
from kks_runtime.graph.investigation import build_investigation_graph
from kks_security.policies.evidence import EvidencePolicy
from kks_security.schemas.report import InvestigationReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_FINDINGS = {
    "logs": {"risk_level": "low"},
    "machine": {"risk_level": "low"},
    "security": {"risk_level": "medium"},
}

_CRITICAL_FINDINGS = {
    "logs": {"risk_level": "low"},
    "machine": {"risk_level": "low"},
    "security": {"risk_level": "critical"},
}

_IP_TARGET = "1.2.3.4"


def _policy(**kwargs) -> EvidencePolicy:
    """Build a minimal EvidencePolicy for testing, with sane defaults."""
    base = {
        "cc_attack_pps_threshold": 2000,
        "cc_attack_delta_threshold": 1000,
        "ddos_attack_kbps_threshold": 1_000_000,
    }
    base.update(kwargs)
    return EvidencePolicy(**base)


def _mock_supervisor_llm() -> MagicMock:
    task = MagicMock()
    task.agent_task = "Stub task"
    mock_structured = AsyncMock(return_value=task)
    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return llm


def _mock_reporter_llm() -> MagicMock:
    report = InvestigationReport(
        alert_status="critical",
        summary="Active attack detected (test stub).",
        recommendations="Escalate immediately.",
    )
    mock_structured = AsyncMock(return_value=report)
    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return llm


# ---------------------------------------------------------------------------
# EvidencePolicy.requires_approval — pure function tests
# ---------------------------------------------------------------------------


def test_requires_approval_false_when_hitl_disabled():
    policy = _policy(hitl_required_for_critical=False)
    assert policy.requires_approval(_CRITICAL_FINDINGS) is False


def test_requires_approval_false_when_all_findings_safe():
    policy = _policy()
    assert policy.requires_approval(_SAFE_FINDINGS) is False


def test_requires_approval_true_when_security_critical():
    policy = _policy()
    assert policy.requires_approval(_CRITICAL_FINDINGS) is True


def test_requires_approval_true_when_logs_critical():
    policy = _policy()
    findings = {"logs": {"risk_level": "critical"}, "security": {"risk_level": "low"}}
    assert policy.requires_approval(findings) is True


def test_requires_approval_false_with_empty_findings():
    policy = _policy()
    assert policy.requires_approval({}) is False


def test_requires_approval_ignores_non_dict_values():
    policy = _policy()
    # Non-dict findings values (e.g., raw strings) must not cause errors
    findings = {"logs": "raw text", "security": {"risk_level": "critical"}}
    assert policy.requires_approval(findings) is True


def test_requires_approval_false_when_risk_level_high_not_critical():
    policy = _policy()
    findings = {"security": {"risk_level": "high"}}
    assert policy.requires_approval(findings) is False


# ---------------------------------------------------------------------------
# supervisor_node — approval_gate routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_routes_to_approval_gate_for_critical():
    """Supervisor must route to approval_gate when findings include a critical risk level."""
    task_stub = MagicMock()
    task_stub.agent_task = "Stub"
    mock_structured = AsyncMock(return_value=task_stub)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)

    events = []

    def _fake_writer():
        return events.append

    with (
        patch("kks_runtime.graph.nodes.supervisor.build_model", return_value=mock_llm),
        patch("kks_runtime.graph.nodes.supervisor.get_stream_writer", _fake_writer),
        patch(
            "kks_runtime.graph.nodes.supervisor.default_policy",
            return_value=_policy(hitl_required_for_critical=True),
        ),
    ):
        from kks_runtime.graph.nodes.supervisor import supervisor_node

        result = await supervisor_node(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-sv-1",
                "findings": _CRITICAL_FINDINGS,
                "artifacts": [],
                "next_node": "",
                "agent_task": "",
                "status": "running",
                "error": None,
            }
        )

    assert result["next_node"] == "approval_gate"
    approval_events = [e for e in events if isinstance(e, ApprovalRequestEvent)]
    assert len(approval_events) == 1
    assert approval_events[0].session_id == "hitl-sv-1"


@pytest.mark.asyncio
async def test_supervisor_routes_directly_to_reporter_when_safe():
    """Supervisor must route directly to reporter when no finding is critical."""
    task_stub = MagicMock()
    task_stub.agent_task = "Stub"
    mock_structured = AsyncMock(return_value=task_stub)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)

    events = []

    def _fake_writer():
        return events.append

    with (
        patch("kks_runtime.graph.nodes.supervisor.build_model", return_value=mock_llm),
        patch("kks_runtime.graph.nodes.supervisor.get_stream_writer", _fake_writer),
        patch(
            "kks_runtime.graph.nodes.supervisor.default_policy",
            return_value=_policy(hitl_required_for_critical=True),
        ),
    ):
        from kks_runtime.graph.nodes.supervisor import supervisor_node

        result = await supervisor_node(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-sv-2",
                "findings": _SAFE_FINDINGS,
                "artifacts": [],
                "next_node": "",
                "agent_task": "",
                "status": "running",
                "error": None,
            }
        )

    assert result["next_node"] == "reporter"
    approval_events = [e for e in events if isinstance(e, ApprovalRequestEvent)]
    assert len(approval_events) == 0


# ---------------------------------------------------------------------------
# Graph interrupt + resume (full cycle)
# ---------------------------------------------------------------------------


@pytest.fixture
def graph():
    return build_investigation_graph(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_graph_pauses_at_approval_gate(graph):
    """
    With critical findings, the graph must pause at approval_gate.
    The first ainvoke must NOT complete (status != 'completed').
    An ApprovalRequestEvent must appear in the custom stream.
    """
    config = {"configurable": {"thread_id": "hitl-pause-1"}}
    events = []

    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        async for chunk in graph.astream(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-pause-1",
                "findings": _CRITICAL_FINDINGS,
            },
            config=config,
            stream_mode="custom",
        ):
            events.append(chunk)

    approval_request_events = [e for e in events if isinstance(e, ApprovalRequestEvent)]
    assert len(approval_request_events) == 1, "Expected exactly one ApprovalRequestEvent"
    assert approval_request_events[0].session_id == "hitl-pause-1"

    # Graph must be paused — not yet completed
    state = await graph.aget_state(config)
    assert state.values.get("status") != "completed"


@pytest.mark.asyncio
async def test_graph_resumes_and_completes_on_approve(graph):
    """
    After pausing, resume with approved=True.
    The graph must complete with status='completed' and emit ApprovalDecisionEvent.
    """
    config = {"configurable": {"thread_id": "hitl-approve-1"}}

    # First invocation — pause at approval_gate
    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        async for _ in graph.astream(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-approve-1",
                "findings": _CRITICAL_FINDINGS,
            },
            config=config,
            stream_mode="custom",
        ):
            pass  # consume stream until pause

    # Second invocation — resume with approval
    resume_events = []
    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        async for chunk in graph.astream(
            Command(resume={"approved": True, "approver": "test_reviewer"}),
            config=config,
            stream_mode="custom",
        ):
            resume_events.append(chunk)

    decision_events = [e for e in resume_events if isinstance(e, ApprovalDecisionEvent)]
    assert len(decision_events) == 1
    assert decision_events[0].approved is True
    assert decision_events[0].approver == "test_reviewer"

    final_state = await graph.aget_state(config)
    assert final_state.values.get("status") == "completed"


@pytest.mark.asyncio
async def test_graph_resumes_and_fails_on_reject(graph):
    """
    After pausing, resume with approved=False.
    The graph must exit with status='failed' and emit ApprovalDecisionEvent(approved=False).
    """
    config = {"configurable": {"thread_id": "hitl-reject-1"}}

    # First invocation — pause
    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        async for _ in graph.astream(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-reject-1",
                "findings": _CRITICAL_FINDINGS,
            },
            config=config,
            stream_mode="custom",
        ):
            pass

    # Second invocation — reject
    resume_events = []
    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        async for chunk in graph.astream(
            Command(resume={"approved": False, "approver": "security_lead"}),
            config=config,
            stream_mode="custom",
        ):
            resume_events.append(chunk)

    decision_events = [e for e in resume_events if isinstance(e, ApprovalDecisionEvent)]
    assert len(decision_events) == 1
    assert decision_events[0].approved is False

    final_state = await graph.aget_state(config)
    assert final_state.values.get("status") == "failed"
    assert "security_lead" in (final_state.values.get("error") or "")


@pytest.mark.asyncio
async def test_graph_skips_approval_gate_for_safe_findings(graph):
    """
    With safe (non-critical) findings, the graph must complete without pausing.
    No ApprovalRequestEvent should appear.
    """
    config = {"configurable": {"thread_id": "hitl-safe-1"}}

    with (
        patch(
            "kks_runtime.graph.nodes.supervisor.build_model",
            return_value=_mock_supervisor_llm(),
        ),
        patch(
            "kks_runtime.graph.nodes.reporter.build_model",
            return_value=_mock_reporter_llm(),
        ),
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": _IP_TARGET,
                "session_id": "hitl-safe-1",
                "findings": _SAFE_FINDINGS,
            },
            config=config,
        )

    assert result["status"] == "completed"
    # Custom stream events not captured in ainvoke, but status proves no gate was hit
