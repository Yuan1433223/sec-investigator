from __future__ import annotations

from langgraph.types import Send

from kks_runtime.graph.nodes.fanout import route_security_checks
from kks_runtime.graph.nodes.rollups import machine_rollup_node, security_rollup_node
from kks_security.schemas.node_machine import NodeMachine


def test_route_security_checks_domain_policy_only_falls_back_to_target_scope():
    sends = route_security_checks(
        {
            "target": "example.com",
            "session_id": "test-01",
            "agent_task": "check security",
            "inspection_scope": [],
            "capability_scope": {
                "log": ["target"],
                "machine": [],
                "security": ["domain_policy"],
            },
        }
    )
    assert isinstance(sends, list)
    assert len(sends) == 1
    assert isinstance(sends[0], Send)
    assert sends[0].node == "security_guard"
    assert "active_asset" not in sends[0].arg


async def test_machine_rollup_aggregates_asset_findings():
    asset_a = NodeMachine.build(
        ip="10.0.0.1",
        node_type="node",
        source="GF",
        origin_target="1.1.1.1",
        target_type="ip",
    )
    asset_b = NodeMachine.build(
        ip="10.0.0.2",
        node_type="node",
        source="GF",
        origin_target="1.1.1.1",
        target_type="ip",
    )
    result = await machine_rollup_node(
        {
            "asset_findings": {
                asset_a.asset_id: {
                    "asset": asset_a.model_dump(),
                    "machine": {"summary": "node a ok", "risk_level": "low"},
                },
                asset_b.asset_id: {
                    "asset": asset_b.model_dump(),
                    "machine": {"summary": "node b stressed", "risk_level": "high"},
                },
            }
        }
    )
    rollup = result["findings"]["machine"]
    assert rollup["risk_level"] == "high"
    assert rollup["asset_count"] == 2
    assert rollup["affected_assets"] == [asset_b.asset_id]


async def test_security_rollup_noops_when_target_scoped_finding_already_exists():
    result = await security_rollup_node(
        {
            "findings": {
                "security": {"summary": "target scoped", "risk_level": "medium"}
            },
            "asset_findings": {},
        }
    )
    assert result == {}


async def test_security_rollup_collects_operational_issue_assets():
    asset = NodeMachine.build(
        ip="20.0.0.1",
        node_type="product",
        source="GF",
        origin_target="example.com",
        target_type="domain",
    )
    result = await security_rollup_node(
        {
            "asset_findings": {
                asset.asset_id: {
                    "asset": asset.model_dump(),
                    "security": {
                        "summary": "config error",
                        "risk_level": "low",
                        "operational_issue": "integration_or_config_error",
                    },
                }
            }
        }
    )
    rollup = result["findings"]["security"]
    assert rollup["operational_issue_assets"] == [asset.asset_id]
    assert rollup["operational_issue_count"] == 1
