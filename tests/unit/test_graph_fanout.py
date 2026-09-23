from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from runtime.graph.investigation import build_investigation_graph
from security.policies.evidence import default_policy
from security.schemas.node_machine import NodeMachine
from security.schemas.report import InvestigationReport


def _mock_supervisor_llm() -> MagicMock:
    task_decision = MagicMock()
    task_decision.agent_task = "Investigate the target."
    mock_structured = AsyncMock(return_value=task_decision)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


def _mock_reporter_llm() -> MagicMock:
    report = InvestigationReport(
        alert_status="warning",
        summary="Fan-out completed.",
        recommendations="Review affected assets.",
    )
    mock_structured = AsyncMock(return_value=report)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


def _no_hitl_policy():
    import dataclasses

    return dataclasses.replace(default_policy(), hitl_required_for_critical=False)


@pytest.mark.asyncio
async def test_graph_fans_out_asset_workers_and_rolls_up_findings():
    asset_a = NodeMachine.build(
        ip="10.0.0.1",
        node_type="node_product",
        source="GF",
        origin_target="1.1.1.1",
        target_type="ip",
    )
    asset_b = NodeMachine.build(
        ip="10.0.0.2",
        node_type="node_product",
        source="GF",
        origin_target="1.1.1.1",
        target_type="ip",
    )

    async def _asset_resolution(_: dict) -> dict:
        return {
            "target_type": "ip",
            "resolved_target": "1.1.1.1",
            "source_type": "GF",
            "resolution_reason": "resolved_from_ip_lookup",
            "node_ips": [asset_a.ip, asset_b.ip],
            "product_ips": [asset_a.ip, asset_b.ip],
            "capability_scope": {
                "log": ["target"],
                "machine": [asset_a.asset_id, asset_b.asset_id],
                "security": [asset_a.asset_id, asset_b.asset_id],
            },
            "inspection_scope": [asset_a.model_dump(), asset_b.model_dump()],
        }

    async def _log_detective(_: dict) -> dict:
        return {
            "findings": {
                "logs": {
                    "summary": "logs collected",
                    "risk_level": "low",
                }
            }
        }

    async def _machine_check(state: dict) -> dict:
        asset = state["active_asset"]
        risk = "high" if asset["ip"] == "10.0.0.2" else "low"
        return {
            "asset_findings": {
                asset["asset_id"]: {
                    "asset": asset,
                    "machine": {
                        "summary": f"machine {asset['ip']}",
                        "risk_level": risk,
                    },
                }
            }
        }

    async def _security_guard(state: dict) -> dict:
        asset = state["active_asset"]
        risk = "critical" if asset["ip"] == "10.0.0.2" else "medium"
        return {
            "asset_findings": {
                asset["asset_id"]: {
                    "asset": asset,
                    "security": {
                        "summary": f"security {asset['ip']}",
                        "risk_level": risk,
                    },
                }
            }
        }

    graph = None
    _investigation = "runtime.graph.investigation"
    _supervisor = "runtime.graph.nodes.supervisor.build_model"
    _policy = "runtime.graph.nodes.supervisor.default_policy"
    _reporter = "runtime.graph.nodes.reporter.build_model"
    with (
        patch(f"{_investigation}.asset_resolution_node", _asset_resolution),
        patch(f"{_investigation}.log_detective_node", _log_detective),
        patch(f"{_investigation}.machine_check_node", _machine_check),
        patch(f"{_investigation}.security_guard_node", _security_guard),
        patch(_supervisor, return_value=_mock_supervisor_llm()),
        patch(_policy, return_value=_no_hitl_policy()),
        patch(_reporter, return_value=_mock_reporter_llm()),
    ):
        graph = build_investigation_graph(checkpointer=MemorySaver())
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="investigate")],
                "target": "1.1.1.1",
                "session_id": "fanout-01",
            },
            config={"configurable": {"thread_id": "fanout-01"}},
        )

    assert result["status"] == "completed"
    assert result["findings"]["machine"]["asset_count"] == 2
    assert result["findings"]["machine"]["risk_level"] == "high"
    assert result["findings"]["security"]["asset_count"] == 2
    assert result["findings"]["security"]["risk_level"] == "critical"
    assert set(result["asset_findings"]) == {asset_a.asset_id, asset_b.asset_id}
