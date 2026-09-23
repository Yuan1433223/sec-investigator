from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from runtime.graph.nodes.log_detective import log_detective_node
from runtime.graph.nodes.machine_check import machine_check_node
from runtime.graph.nodes.security_guard import _annotate_operational_issue, security_guard_node
from security.schemas.findings import MachineFindings, SecurityFindings
from security.schemas.node_machine import NodeMachine


def _mock_structured_model(result: object) -> MagicMock:
    mock = MagicMock()
    mock.with_structured_output.return_value = MagicMock(ainvoke=AsyncMock(return_value=result))
    return mock


def _mock_policy(*, machine: str = "low", security: str = "low") -> MagicMock:
    policy = MagicMock()
    policy.classify_machine.return_value = machine
    policy.classify_security.return_value = security
    return policy


@pytest.mark.asyncio
async def test_machine_check_dual_writes_asset_findings():
    asset = NodeMachine.build(
        ip="10.0.0.1",
        node_type="node_product",
        source="GF",
        origin_target="example.com",
        target_type="domain",
    )
    findings = MachineFindings(
        summary="infra normal",
        connectivity="ok",
        system_metrics="cpu normal",
        tcp_status="stable",
        health_status="healthy",
        analysis_text="agent analysis",
    )
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="analysis")]})

    with (
        patch("runtime.graph.nodes.machine_check.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.machine_check.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.machine_check.create_react_agent", return_value=mock_agent),
        patch(
            "runtime.graph.nodes.machine_check.build_model",
            side_effect=[MagicMock(), _mock_structured_model(findings)],
        ),
        patch(
            "runtime.graph.nodes.machine_check.default_policy",
            return_value=_mock_policy(machine="medium"),
        ),
    ):
        result = await machine_check_node(
            {
                "target": "example.com",
                "agent_task": "check infra",
                "inspection_scope": [asset.model_dump()],
                "capability_scope": {
                    "log": ["target"],
                    "machine": [asset.asset_id],
                    "security": [asset.asset_id],
                },
            }
        )

    assert result["findings"]["machine"]["risk_level"] == "medium"
    assert result["asset_findings"][asset.asset_id]["asset"]["asset_id"] == asset.asset_id
    assert result["asset_findings"][asset.asset_id]["machine"]["summary"] == "infra normal"


@pytest.mark.asyncio
async def test_security_guard_dual_writes_asset_findings():
    asset = NodeMachine.build(
        ip="20.0.0.1",
        node_type="product",
        source="WAF",
        origin_target="example.com",
        target_type="domain",
    )
    findings = SecurityFindings(
        summary="protection normal",
        cc_status="enabled",
        ddos_status="enabled",
        protection_status="normal",
        analysis_text="agent analysis",
    )
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="analysis")]})

    with (
        patch("runtime.graph.nodes.security_guard.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.security_guard.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.security_guard.create_react_agent", return_value=mock_agent),
        patch(
            "runtime.graph.nodes.security_guard.build_model",
            side_effect=[MagicMock(), _mock_structured_model(findings)],
        ),
        patch(
            "runtime.graph.nodes.security_guard.default_policy",
            return_value=_mock_policy(security="low"),
        ),
    ):
        result = await security_guard_node(
            {
                "target": "example.com",
                "agent_task": "check security",
                "inspection_scope": [asset.model_dump()],
                "capability_scope": {
                    "log": ["target"],
                    "machine": [],
                    "security": [asset.asset_id, "domain_policy"],
                },
            }
        )

    assert result["findings"]["security"]["risk_level"] == "low"
    assert result["asset_findings"][asset.asset_id]["asset"]["asset_id"] == asset.asset_id
    assert result["asset_findings"][asset.asset_id]["security"]["cc_status"] == "enabled"


@pytest.mark.asyncio
async def test_security_guard_domain_policy_only_stays_target_scoped():
    findings = SecurityFindings(
        summary="domain policy only",
        cc_status="unknown",
        ddos_status="unknown",
        protection_status="unknown",
        analysis_text="agent analysis",
    )
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="analysis")]})

    with (
        patch("runtime.graph.nodes.security_guard.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.security_guard.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.security_guard.create_react_agent", return_value=mock_agent),
        patch(
            "runtime.graph.nodes.security_guard.build_model",
            side_effect=[MagicMock(), _mock_structured_model(findings)],
        ),
        patch(
            "runtime.graph.nodes.security_guard.default_policy",
            return_value=_mock_policy(security="medium"),
        ),
    ):
        result = await security_guard_node(
            {
                "target": "example.com",
                "agent_task": "check security",
                "inspection_scope": [],
                "capability_scope": {
                    "log": ["target"],
                    "machine": [],
                    "security": ["domain_policy"],
                },
            }
        )

    assert result["findings"]["security"]["risk_level"] == "medium"
    assert result["asset_findings"] == {}


def test_annotate_operational_issue_marks_integration_errors():
    findings = {
        "summary": "DDoS reported one misconfiguration event.",
        "analysis_text": "host check failed; key值不对!",
        "cc_status": "no_data",
        "ddos_status": "active",
        "protection_status": "degraded",
    }
    _annotate_operational_issue(findings)
    assert findings["operational_issue"] == "integration_or_config_error"


def test_annotate_operational_issue_marks_coverage_gap():
    findings = {
        "summary": "No IP coverage available.",
        "analysis_text": "telemetry missing",
        "cc_status": "not_applicable",
        "ddos_status": "unknown",
        "protection_status": "incomplete",
    }
    _annotate_operational_issue(findings)
    assert findings["operational_issue"] == "coverage_gap"


@pytest.mark.asyncio
async def test_machine_check_active_asset_writes_asset_scope_only():
    asset = NodeMachine.build(
        ip="30.0.0.1",
        node_type="node",
        source="GF",
        origin_target="1.1.1.1",
        target_type="ip",
    )
    findings = MachineFindings(
        summary="scoped infra",
        connectivity="ok",
        system_metrics="normal",
        tcp_status="stable",
        health_status="healthy",
        analysis_text="agent analysis",
    )
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="analysis")]})

    with (
        patch("runtime.graph.nodes.machine_check.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.machine_check.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.machine_check.create_react_agent", return_value=mock_agent),
        patch(
            "runtime.graph.nodes.machine_check.build_model",
            side_effect=[MagicMock(), _mock_structured_model(findings)],
        ),
        patch(
            "runtime.graph.nodes.machine_check.default_policy",
            return_value=_mock_policy(machine="low"),
        ),
    ):
        result = await machine_check_node(
            {
                "target": "1.1.1.1",
                "agent_task": "check infra",
                "active_asset": asset.model_dump(),
            }
        )

    assert "findings" not in result
    assert result["asset_findings"][asset.asset_id]["machine"]["summary"] == "scoped infra"

# ---------------------------------------------------------------------------
# Graceful degradation on GraphRecursionError (tool budget exhausted)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_guard_degrades_on_recursion_error():
    from langgraph.errors import GraphRecursionError

    asset = NodeMachine.build(
        ip="20.0.0.2",
        node_type="product",
        source="WAF",
        origin_target="example.com",
        target_type="domain",
    )

    async def _raise(*args, **kwargs):
        raise GraphRecursionError("Recursion limit of 13 reached")

    mock_agent = MagicMock()
    mock_agent.ainvoke = _raise

    with (
        patch("runtime.graph.nodes.security_guard.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.security_guard.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.security_guard.create_react_agent", return_value=mock_agent),
        patch("runtime.graph.nodes.security_guard.build_model", return_value=MagicMock()),
    ):
        result = await security_guard_node(
            {
                "target": "example.com",
                "agent_task": "check security",
                "inspection_scope": [asset.model_dump()],
                "capability_scope": {
                    "log": ["target"],
                    "machine": [],
                    "security": [asset.asset_id],
                },
            }
        )

    # Must not crash — return a deterministic coverage_gap partial finding.
    assert result["findings"]["security"]["operational_issue"] == "coverage_gap"
    assert result["findings"]["security"]["protection_status"] == "incomplete"
    assert result["findings"]["security"]["cc_status"] == "no_data"
    assert result["findings"]["security"]["risk_level"] == "low"
    assert result["asset_findings"][asset.asset_id]["security"]["cc_status"] == "no_data"


@pytest.mark.asyncio
async def test_log_detective_degrades_on_recursion_error():
    from langgraph.errors import GraphRecursionError

    async def _raise(*args, **kwargs):
        raise GraphRecursionError("Recursion limit reached")

    mock_agent = MagicMock()
    mock_agent.ainvoke = _raise

    with (
        patch("runtime.graph.nodes.log_detective.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.log_detective.make_traced_tools", return_value=[]),
        patch("runtime.graph.nodes.log_detective.create_react_agent", return_value=mock_agent),
        patch("runtime.graph.nodes.log_detective.build_model", return_value=MagicMock()),
    ):
        result = await log_detective_node(
            {"target": "example.com", "agent_task": "analyse logs"}
        )

    assert result["findings"]["logs"]["risk_level"] == "low"
    assert "未能在工具预算内收敛" in result["findings"]["logs"]["summary"]

