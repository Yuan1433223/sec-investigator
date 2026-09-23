from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from runtime.graph.investigation import build_investigation_graph
from runtime.llm.profiles import _REGISTRY, ModelConfig, ModelProfile, build_model
from runtime.llm.router import profile_for
from security.schemas.report import InvestigationReport

# ---------------------------------------------------------------------------
# ModelConfig / registry
# ---------------------------------------------------------------------------


def test_all_profiles_in_registry():
    for p in ModelProfile:
        assert p in _REGISTRY, f"{p} missing from registry"


def test_model_config_frozen():
    cfg = ModelConfig(temperature=0.5)
    with pytest.raises((AttributeError, TypeError)):
        cfg.temperature = 0.9  # type: ignore[misc]


def test_build_model_returns_base_chat_model():
    from langchain_core.language_models import BaseChatModel

    m = build_model(ModelProfile.FAST_CLASSIFIER)
    assert isinstance(m, BaseChatModel)


def test_build_model_override_temperature():
    m = build_model(ModelProfile.REPORT_WRITER, temperature=0.9)
    assert m.temperature == 0.9


def test_local_model_uses_local_settings():
    from runtime.config.settings import Settings

    s = Settings(
        local_model_base="http://custom:8000/v1",
        local_model_name="mistral",
        local_model_api_key="none",
    )
    m = build_model(ModelProfile.LOCAL_OFFLINE_MODEL, settings=s)
    assert m.openai_api_base == "http://custom:8000/v1"
    assert m.model_name == "mistral"


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


def test_router_known_task_types():
    assert profile_for("classify") == ModelProfile.FAST_CLASSIFIER
    assert profile_for("report") == ModelProfile.REPORT_WRITER
    assert profile_for("investigate") == ModelProfile.TOOL_REASONER
    assert profile_for("offline") == ModelProfile.LOCAL_OFFLINE_MODEL


def test_router_case_insensitive():
    assert profile_for("CLASSIFY") == profile_for("classify")


def test_router_unknown_falls_back():
    assert profile_for("nonexistent_task") == ModelProfile.TOOL_REASONER


# ---------------------------------------------------------------------------
# Supervisor node (mocked LLM)
#
# Routing is now deterministic (_next_worker based on required_findings).
# The LLM is called only to generate agent_task for the chosen worker.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_node_Agent20260422_to_reporter():
    """
    Supervisor Agent20260422 to reporter deterministically when all required findings
    are present. The LLM stub generates the agent_task string only.
    """
    task_stub = MagicMock()
    task_stub.agent_task = "Generate final report for 1.2.3.4"
    mock_structured = AsyncMock(return_value=task_stub)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)

    with patch("runtime.graph.nodes.supervisor.build_model", return_value=mock_llm):
        from runtime.graph.nodes.supervisor import supervisor_node

        result = await supervisor_node(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": "1.2.3.4",
                "session_id": "s1",
                # All required findings present → code Agent20260422 to reporter
                "findings": {"logs": {}, "machine": {}, "security": {}},
                "artifacts": [],
                "next_node": "",
                "agent_task": "",
                "status": "running",
                "error": None,
            }
        )

    assert result["next_node"] == "reporter"
    assert result["agent_task"] == "Generate final report for 1.2.3.4"
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_graph_with_mocked_supervisor():
    """Full graph ainvoke with mocked LLM — no real API calls."""
    task_stub = MagicMock()
    task_stub.agent_task = "Summarize"
    mock_structured = AsyncMock(return_value=task_stub)
    mock_supervisor_llm = MagicMock()
    mock_supervisor_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)

    report = InvestigationReport(
        alert_status="normal",
        summary="System normal (test stub).",
        recommendations="No action required.",
    )
    mock_report_structured = AsyncMock(return_value=report)
    mock_reporter_llm = MagicMock()
    mock_reporter_llm.with_structured_output.return_value = MagicMock(
        ainvoke=mock_report_structured
    )

    with (
        patch("runtime.graph.nodes.supervisor.build_model", return_value=mock_supervisor_llm),
        patch("runtime.graph.nodes.reporter.build_model", return_value=mock_reporter_llm),
    ):
        graph = build_investigation_graph(checkpointer=MemorySaver())
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="test")],
                "target": "example.com",
                "session_id": "test-p2",
                # Pre-populate domain findings so routing goes straight to reporter
                "findings": {"logs": {}, "security": {}},
            },
            config={"configurable": {"thread_id": "test-p2"}},
        )

    assert result["status"] == "completed"
    assert len(result["artifacts"]) == 1
