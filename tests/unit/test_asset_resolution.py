"""
Unit tests for asset_resolution_node and its helpers.

All external adapter calls are mocked: no network required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from runtime.graph.nodes.asset_resolution import (
    _is_ip,
    _machines_from_gf_nodes,
    _machines_from_resolver_data,
    _machines_from_waf_nodes,
    _split_scope,
    asset_resolution_node,
)
from security.collectors.gf_collector import GFNode
from security.collectors.waf_collector import WAFNode
from security.schemas.node_machine import NodeMachine


def test_is_ip_bare_ip():
    assert _is_ip("1.2.3.4") is True


def test_is_ip_with_spaces():
    assert _is_ip("  10.0.0.1  ") is True


def test_is_ip_domain():
    assert _is_ip("example.com") is False


def test_is_ip_partial():
    assert _is_ip("1.2.3") is False


def test_is_ip_empty():
    assert _is_ip("") is False


def test_machines_from_waf_nodes():
    nodes = [
        WAFNode(ip="1.1.1.1", node_type="node_product"),
        WAFNode(ip="2.2.2.2", node_type="product"),
    ]
    machines = _machines_from_waf_nodes(
        nodes,
        origin_target="example.com",
        target_type="domain",
    )
    assert len(machines) == 2
    assert machines[0] == NodeMachine.build(
        ip="1.1.1.1",
        node_type="node_product",
        source="WAF",
        origin_target="example.com",
        target_type="domain",
    )
    assert machines[1] == NodeMachine.build(
        ip="2.2.2.2",
        node_type="product",
        source="WAF",
        origin_target="example.com",
        target_type="domain",
    )


def test_machines_from_gf_nodes():
    nodes = [
        GFNode(ip="3.3.3.3", node_type="node_product"),
        GFNode(ip="4.4.4.4", node_type="product"),
    ]
    machines = _machines_from_gf_nodes(
        nodes,
        origin_target="example.com",
        target_type="domain",
    )
    assert machines[0] == NodeMachine.build(
        ip="3.3.3.3",
        node_type="node_product",
        source="GF",
        origin_target="example.com",
        target_type="domain",
    )
    assert machines[1] == NodeMachine.build(
        ip="4.4.4.4",
        node_type="product",
        source="GF",
        origin_target="example.com",
        target_type="domain",
    )


def test_machines_from_resolver_data_waf():
    data = {"node_ip": "5.5.5.5", "ip_list": ["6.6.6.6", "7.7.7.7"]}
    machines = _machines_from_resolver_data(
        "WAF",
        data,
        origin_target="5.5.5.5",
        target_type="ip",
    )
    assert machines[0] == NodeMachine.build(
        ip="5.5.5.5",
        node_type="node_product",
        source="WAF",
        origin_target="5.5.5.5",
        target_type="ip",
    )
    assert machines[1] == NodeMachine.build(
        ip="6.6.6.6",
        node_type="product",
        source="WAF",
        origin_target="5.5.5.5",
        target_type="ip",
    )
    assert machines[2] == NodeMachine.build(
        ip="7.7.7.7",
        node_type="product",
        source="WAF",
        origin_target="5.5.5.5",
        target_type="ip",
    )


def test_machines_from_resolver_data_gf_list():
    data = [{"node_ip": "8.8.8.8", "ip_list": ["9.9.9.9"]}]
    machines = _machines_from_resolver_data(
        "GF",
        data,
        origin_target="8.8.8.8",
        target_type="ip",
    )
    assert machines[0] == NodeMachine.build(
        ip="8.8.8.8",
        node_type="node_product",
        source="GF",
        origin_target="8.8.8.8",
        target_type="ip",
    )
    assert machines[1] == NodeMachine.build(
        ip="9.9.9.9",
        node_type="product",
        source="GF",
        origin_target="8.8.8.8",
        target_type="ip",
    )


def test_machines_from_resolver_data_none():
    assert _machines_from_resolver_data(
        "WAF",
        None,
        origin_target="1.1.1.1",
        target_type="ip",
    ) == []


def test_machines_from_resolver_data_skips_duplicate_node_ip_in_ip_list():
    data = {"node_ip": "1.1.1.1", "ip_list": ["1.1.1.1", "2.2.2.2"]}
    machines = _machines_from_resolver_data(
        "WAF",
        data,
        origin_target="1.1.1.1",
        target_type="ip",
    )
    ips = [machine.ip for machine in machines]
    assert ips.count("1.1.1.1") == 1


def test_split_scope_node_product_appears_in_both():
    machines = [
        NodeMachine.build(
            ip="1.1.1.1",
            node_type="node_product",
            source="WAF",
            origin_target="example.com",
            target_type="domain",
        ),
        NodeMachine.build(
            ip="2.2.2.2",
            node_type="node",
            source="WAF",
            origin_target="example.com",
            target_type="domain",
        ),
        NodeMachine.build(
            ip="3.3.3.3",
            node_type="product",
            source="WAF",
            origin_target="example.com",
            target_type="domain",
        ),
    ]
    node_ips, product_ips = _split_scope(machines)
    assert "1.1.1.1" in node_ips and "1.1.1.1" in product_ips
    assert "2.2.2.2" in node_ips and "2.2.2.2" not in product_ips
    assert "3.3.3.3" not in node_ips and "3.3.3.3" in product_ips


@pytest.mark.asyncio
async def test_asset_resolution_ip_waf():
    waf_data = {"node_ip": "10.0.0.1", "ip_list": ["10.0.0.2"]}
    mock_resolver = AsyncMock()
    mock_resolver.resolve_ip = AsyncMock(return_value=(True, "WAF", waf_data))
    mock_resolver.aclose = AsyncMock()

    with patch(
        "runtime.graph.nodes.asset_resolution.NodeResolver",
        return_value=mock_resolver,
    ):
        result = await asset_resolution_node({"target": "10.0.0.1"})

    assert result["target_type"] == "ip"
    assert result["resolved_target"] == "10.0.0.1"
    assert result["source_type"] == "WAF"
    assert result["resolution_reason"] == "resolved_from_ip_lookup"
    assert result["capability_scope"] == {
        "log": ["target"],
        "machine": ["WAF:node_product:10.0.0.1"],
        "security": [
            "WAF:node_product:10.0.0.1",
            "WAF:product:10.0.0.2",
        ],
    }
    assert "10.0.0.1" in result["node_ips"]
    assert "10.0.0.2" in result["product_ips"]
    scope = result["inspection_scope"]
    assert len(scope) == 2
    assert scope[0]["type"] == "node_product"
    assert scope[0]["source"] == "WAF"
    assert scope[0]["asset_id"] == "WAF:node_product:10.0.0.1"


@pytest.mark.asyncio
async def test_asset_resolution_ip_unresolved_becomes_bare_node():
    mock_resolver = AsyncMock()
    mock_resolver.resolve_ip = AsyncMock(return_value=(False, "GF", None))
    mock_resolver.aclose = AsyncMock()

    with patch(
        "runtime.graph.nodes.asset_resolution.NodeResolver",
        return_value=mock_resolver,
    ):
        result = await asset_resolution_node({"target": "192.168.1.1"})

    assert result["target_type"] == "ip"
    assert result["source_type"] is None
    assert result["resolution_reason"] == "unresolved_ip_fallback"
    assert result["node_ips"] == ["192.168.1.1"]
    assert result["product_ips"] == []
    assert result["capability_scope"] == {
        "log": ["target"],
        "machine": ["UNRESOLVED:node:192.168.1.1"],
        "security": [],
    }
    assert result["inspection_scope"][0]["type"] == "node"
    assert result["inspection_scope"][0]["is_resolved"] is False


@pytest.mark.asyncio
async def test_asset_resolution_domain_gf_first():
    gf_nodes = [GFNode(ip="20.0.0.1", node_type="node_product")]
    mock_gf = AsyncMock()
    mock_gf.query_nodes_by_domain = AsyncMock(return_value=gf_nodes)
    mock_gf.aclose = AsyncMock()

    with patch(
        "runtime.graph.nodes.asset_resolution.GFCollector",
        return_value=mock_gf,
    ):
        result = await asset_resolution_node({"target": "example.com"})

    assert result["target_type"] == "domain"
    assert result["source_type"] == "GF"
    assert result["resolution_reason"] == "resolved_from_domain_lookup"
    assert result["capability_scope"] == {
        "log": ["target"],
        "machine": ["GF:node_product:20.0.0.1"],
        "security": ["GF:node_product:20.0.0.1", "domain_policy"],
    }
    assert "20.0.0.1" in result["node_ips"]
    assert "20.0.0.1" in result["product_ips"]


@pytest.mark.asyncio
async def test_asset_resolution_domain_falls_back_to_waf():
    waf_nodes = [WAFNode(ip="30.0.0.1", node_type="node_product")]
    mock_gf = AsyncMock()
    mock_gf.query_nodes_by_domain = AsyncMock(return_value=[])
    mock_gf.aclose = AsyncMock()
    mock_waf = AsyncMock()
    mock_waf.query_nodes_by_domain = AsyncMock(return_value=waf_nodes)
    mock_waf.aclose = AsyncMock()

    with (
        patch("runtime.graph.nodes.asset_resolution.GFCollector", return_value=mock_gf),
        patch("runtime.graph.nodes.asset_resolution.WAFCollector", return_value=mock_waf),
    ):
        result = await asset_resolution_node({"target": "example.com"})

    assert result["target_type"] == "domain"
    assert result["source_type"] == "WAF"
    assert "30.0.0.1" in result["node_ips"]


@pytest.mark.asyncio
async def test_asset_resolution_domain_no_results():
    mock_gf = AsyncMock()
    mock_gf.query_nodes_by_domain = AsyncMock(return_value=[])
    mock_gf.aclose = AsyncMock()
    mock_waf = AsyncMock()
    mock_waf.query_nodes_by_domain = AsyncMock(return_value=[])
    mock_waf.aclose = AsyncMock()

    with (
        patch("runtime.graph.nodes.asset_resolution.GFCollector", return_value=mock_gf),
        patch("runtime.graph.nodes.asset_resolution.WAFCollector", return_value=mock_waf),
    ):
        result = await asset_resolution_node({"target": "unknown.example.com"})

    assert result["target_type"] == "domain"
    assert result["source_type"] is None
    assert result["resolution_reason"] == "unresolved_domain"
    assert result["node_ips"] == []
    assert result["product_ips"] == []
    assert result["capability_scope"] == {
        "log": ["target"],
        "machine": [],
        "security": ["domain_policy"],
    }
    assert result["inspection_scope"] == []
