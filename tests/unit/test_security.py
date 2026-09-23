"""Unit tests for security adapters, tools, and RAG (Phase 3).

All tests use injected mock adapters — no real HTTP calls.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from security.adapters.cc import CCAdapter, PointStatus
from security.adapters.ddos import DDoSAdapter
from security.collectors.gf_collector import GFCollector, GFNode
from security.collectors.node_resolver import NodeResolver
from security.collectors.waf_collector import WAFCollector, WAFNode
from security.rag.engine import RAGEngine
from security.rag.rag_tools import _make_rag_tools
from security.tools.security_tools import (
    _is_cc_attack,
    _is_ddos_attack,
    _make_security_tools,
)

# ---------------------------------------------------------------------------
# Attack-detection helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def test_is_cc_attack_above_threshold():
    point = PointStatus(input_pps=3000, input_submit_pps=1500)
    assert _is_cc_attack(point) is True


def test_is_cc_attack_below_pps_threshold():
    # input_pps <= 2000 → not an attack
    point = PointStatus(input_pps=1999, input_submit_pps=500)
    assert _is_cc_attack(point) is False


def test_is_cc_attack_delta_too_small():
    # input_pps > 2000 but delta < 1000 → not an attack
    point = PointStatus(input_pps=2500, input_submit_pps=1600)
    assert _is_cc_attack(point) is False


def test_is_cc_attack_missing_fields():
    point = PointStatus()
    assert _is_cc_attack(point) is False


def test_is_ddos_attack_above_threshold():
    event = {"bps": 1_000_001}
    assert _is_ddos_attack(event) is True


def test_is_ddos_attack_below_threshold():
    event = {"bps": 999_999}
    assert _is_ddos_attack(event) is False


def test_is_ddos_attack_missing_field():
    assert _is_ddos_attack({}) is False


# ---------------------------------------------------------------------------
# CCAdapter mock tests
# ---------------------------------------------------------------------------


def _mock_cc_adapter(point_return=None, host_return=None):
    m = MagicMock(spec=CCAdapter)
    m.get_host_point = AsyncMock(return_value=point_return or [])
    m.get_batch_host_status = AsyncMock(
        return_value=host_return or {
            "status": True, "data": [], "success_count": 0, "failed_count": 0,
        }
    )
    return m


def _mock_ddos_adapter(list_return=None):
    m = MagicMock(spec=DDoSAdapter)
    m.get_ddos_list = AsyncMock(return_value=list_return or {"status": True, "data": []})
    return m


@pytest.mark.asyncio
async def test_check_cc_status_with_attack():
    points = [PointStatus(address="1.2.3.4", input_pps=3200, input_submit_pps=1800)]
    cc = _mock_cc_adapter(point_return=points)
    tools = _make_security_tools(cc_adapter=cc, ddos_adapter=_mock_ddos_adapter())
    cc_tool = next(t for t in tools if t.name == "check_cc_status")

    result = await cc_tool.ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] == "ok"
    assert len(result["points"]) == 1
    assert result["points"][0]["is_under_attack"] is True


@pytest.mark.asyncio
async def test_check_cc_status_no_data():
    cc = _mock_cc_adapter(point_return=[])
    tools = _make_security_tools(cc_adapter=cc, ddos_adapter=_mock_ddos_adapter())
    cc_tool = next(t for t in tools if t.name == "check_cc_status")

    result = await cc_tool.ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] == "no_data"


@pytest.mark.asyncio
async def test_check_ddos_status_with_events():
    events = [{"bps": 2_000_000, "ip": "1.2.3.4"}]
    ddos = _mock_ddos_adapter(list_return={"status": True, "data": events})
    tools = _make_security_tools(cc_adapter=_mock_cc_adapter(), ddos_adapter=ddos)
    ddos_tool = next(t for t in tools if t.name == "check_ddos_status")

    result = await ddos_tool.ainvoke({"ips": ["1.2.3.4"]})
    assert result["count"] == 1
    assert result["events"][0]["exceeds_threshold"] is True


@pytest.mark.asyncio
async def test_check_ddos_status_with_raw_list_response():
    events = [{"bps": 2_000_000, "ip": "1.2.3.4"}]
    ddos = _mock_ddos_adapter(list_return=events)
    tools = _make_security_tools(cc_adapter=_mock_cc_adapter(), ddos_adapter=ddos)
    ddos_tool = next(t for t in tools if t.name == "check_ddos_status")

    result = await ddos_tool.ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] is True
    assert result["count"] == 1
    assert result["events"][0]["exceeds_threshold"] is True


@pytest.mark.asyncio
async def test_check_host_status():
    host_resp = {
        "status": True,
        "data": [{"ip": "1.2.3.4", "is_forbidden": False, "shield_count": 5}],
        "success_count": 1,
        "failed_count": 0,
    }
    cc = _mock_cc_adapter(host_return=host_resp)
    tools = _make_security_tools(cc_adapter=cc, ddos_adapter=_mock_ddos_adapter())
    host_tool = next(t for t in tools if t.name == "check_host_status")

    result = await host_tool.ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] is True
    assert result["success_count"] == 1


# ---------------------------------------------------------------------------
# Routing tools: query_nodes_ip_by_ip, query_nodes_ip_by_domain,
#                query_domain_protection_policy
# ---------------------------------------------------------------------------


def _mock_node_resolver(success=True, product_type="WAF", data=None):
    m = MagicMock(spec=NodeResolver)
    m.resolve_ip = AsyncMock(return_value=(success, product_type, data or {"node_ip": "10.0.0.1"}))
    return m


def _mock_waf_collector(nodes=None):
    m = MagicMock(spec=WAFCollector)
    m.query_nodes_by_domain = AsyncMock(return_value=nodes or [WAFNode(ip="10.0.0.1")])
    return m


def _mock_gf_collector(nodes=None, policy=None):
    m = MagicMock(spec=GFCollector)
    m.query_nodes_by_domain = AsyncMock(return_value=nodes or [GFNode(ip="10.0.0.2")])
    m.query_domain_protection_policy = AsyncMock(
        return_value=policy or {"summary": "no rules", "project": "YXD"}
    )
    return m


@pytest.mark.asyncio
async def test_query_nodes_ip_by_ip_success():
    nr = _mock_node_resolver(success=True, product_type="WAF", data={"node_ip": "10.0.0.1"})
    tools = _make_security_tools(node_resolver=nr)
    t = next(t for t in tools if t.name == "query_nodes_ip_by_ip")
    result = await t.ainvoke({"ip": "1.2.3.4"})
    assert result["success"] is True
    assert result["product_type"] == "WAF"


@pytest.mark.asyncio
async def test_query_nodes_ip_by_domain_waf():
    waf = _mock_waf_collector(nodes=[WAFNode(ip="10.0.0.1", node_type="node_product")])
    tools = _make_security_tools(waf_collector=waf)
    t = next(t for t in tools if t.name == "query_nodes_ip_by_domain")
    result = await t.ainvoke({"source_type": "WAF", "domain": "example.com"})
    assert result["source"] == "WAF"
    assert result["nodes"][0]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_query_nodes_ip_by_domain_gf():
    gf = _mock_gf_collector(nodes=[GFNode(ip="10.0.0.2", node_type="product")])
    tools = _make_security_tools(gf_collector=gf)
    t = next(t for t in tools if t.name == "query_nodes_ip_by_domain")
    result = await t.ainvoke({"source_type": "GF", "domain": "example.com"})
    assert result["source"] == "GF"
    assert result["nodes"][0]["ip"] == "10.0.0.2"


@pytest.mark.asyncio
async def test_query_domain_protection_policy():
    gf = _mock_gf_collector(policy={"summary": "Domain example.com: no rules", "project": "GFIP"})
    tools = _make_security_tools(gf_collector=gf)
    t = next(t for t in tools if t.name == "query_domain_protection_policy")
    result = await t.ainvoke({"domain": "example.com"})
    assert result["project"] == "GFIP"
    assert "example.com" in result["summary"]


# ---------------------------------------------------------------------------
# RAG tool
# ---------------------------------------------------------------------------


def _mock_rag_engine(results=None):
    m = MagicMock(spec=RAGEngine)
    m.search = MagicMock(return_value=results or [])
    return m


def test_search_knowledge_returns_docs():
    docs = [{"text": "CC attack mitigation guide", "source": "ops-runbook", "score": 0.85}]
    eng = _mock_rag_engine(results=docs)
    tools = _make_rag_tools(engine=eng)
    t = next(t for t in tools if t.name == "search_knowledge")
    result = t.invoke({"query": "CC attack"})
    assert "CC attack mitigation guide" in result
    assert "ops-runbook" in result


def test_search_knowledge_no_results():
    eng = _mock_rag_engine(results=[])
    tools = _make_rag_tools(engine=eng)
    t = next(t for t in tools if t.name == "search_knowledge")
    result = t.invoke({"query": "unknown topic"})
    assert "No relevant documents" in result


def test_search_knowledge_engine_error():
    eng = MagicMock(spec=RAGEngine)
    eng.search = MagicMock(side_effect=ConnectionError("Milvus unreachable"))
    tools = _make_rag_tools(engine=eng)
    t = next(t for t in tools if t.name == "search_knowledge")
    result = t.invoke({"query": "anything"})
    assert "failed" in result.lower()
