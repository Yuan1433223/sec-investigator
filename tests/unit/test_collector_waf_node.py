"""
Unit tests for WAFCollector and NodeResolver.

All HTTP intercepted with respx.
"""
from __future__ import annotations

import respx
from httpx import Response

from security.collectors.node_resolver import NodeResolver
from security.collectors.waf_collector import WAFCollector

_WAF_BASE = "http://fake-waf"
_GF_YXD = "http://fake-gf-yxd"
_GF_CDN = "http://fake-gf-cdn"
_GF_DDOS = "http://fake-gf-ddos"


# ---------------------------------------------------------------------------
# WAFCollector
# ---------------------------------------------------------------------------

_WAF_NODES_PATH = "/api/security_assistant/get_node_ips"
_WAF_NODE_PAYLOAD = {
    "data": [{"node_ip": "172.16.0.1", "ip_list": ["172.16.0.2", "172.16.0.3"]}]
}


def _make_waf(test_settings) -> WAFCollector:
    return WAFCollector(settings=test_settings)


@respx.mock
async def test_waf_query_nodes_happy_path(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_NODES_PATH}").mock(
        return_value=Response(200, json=_WAF_NODE_PAYLOAD)
    )
    waf = _make_waf(test_settings)
    nodes = await waf.query_nodes_by_domain("example.com")
    assert len(nodes) == 3
    assert nodes[0].ip == "172.16.0.1"
    assert nodes[0].node_type == "node_product"
    assert nodes[0].source == "WAF"
    await waf.aclose()


@respx.mock
async def test_waf_query_nodes_deduplicates_node_ip(test_settings):
    payload = {"data": [{"node_ip": "172.16.0.1", "ip_list": ["172.16.0.1", "172.16.0.2"]}]}
    respx.get(f"{_WAF_BASE}{_WAF_NODES_PATH}").mock(return_value=Response(200, json=payload))
    waf = _make_waf(test_settings)
    nodes = await waf.query_nodes_by_domain("example.com")
    ips = [n.ip for n in nodes]
    assert ips.count("172.16.0.1") == 1
    await waf.aclose()


@respx.mock
async def test_waf_query_nodes_http_error_returns_empty(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_NODES_PATH}").mock(side_effect=Exception("connection refused"))
    waf = _make_waf(test_settings)
    nodes = await waf.query_nodes_by_domain("example.com")
    assert nodes == []
    await waf.aclose()


@respx.mock
async def test_waf_query_nodes_empty_data(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_NODES_PATH}").mock(
        return_value=Response(200, json={"data": []})
    )
    waf = _make_waf(test_settings)
    nodes = await waf.query_nodes_by_domain("example.com")
    assert nodes == []
    await waf.aclose()


# ---------------------------------------------------------------------------
# NodeResolver
# ---------------------------------------------------------------------------

_WAF_RESOLVE_PATH = "/api/security_assistant/get_node_ip_by_ip"
_GF_RESOLVE_PATH = "/api/p_node/getNodeIpList"

_WAF_RESOLVE_OK = {"code": 1, "data": {"node_ip": "10.0.0.1", "ip_list": ["10.0.0.2"]}}
_GF_RESOLVE_OK = {"code": 1, "data": [{"node_ip": "10.0.1.1", "ip_list": []}]}


def _make_resolver(test_settings) -> NodeResolver:
    return NodeResolver(settings=test_settings)


@respx.mock
async def test_resolver_waf_hit(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_RESOLVE_PATH}").mock(
        return_value=Response(200, json=_WAF_RESOLVE_OK)
    )
    resolver = _make_resolver(test_settings)
    success, product_type, data = await resolver.resolve_ip("1.2.3.4")
    assert success is True
    assert product_type == "WAF"
    assert data is not None
    await resolver.aclose()


@respx.mock
async def test_resolver_waf_miss_gf_hit(test_settings):
    # WAF returns code != 1 (miss)
    respx.get(f"{_WAF_BASE}{_WAF_RESOLVE_PATH}").mock(
        return_value=Response(200, json={"code": 0, "data": None})
    )
    # First GF endpoint hits
    respx.get(f"{_GF_YXD}{_GF_RESOLVE_PATH}").mock(
        return_value=Response(200, json=_GF_RESOLVE_OK)
    )
    resolver = _make_resolver(test_settings)
    success, product_type, data = await resolver.resolve_ip("1.2.3.4")
    assert success is True
    assert product_type == "GF"
    await resolver.aclose()


@respx.mock
async def test_resolver_all_miss(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_RESOLVE_PATH}").mock(
        return_value=Response(200, json={"code": 0})
    )
    for gf_base in (_GF_YXD, _GF_CDN, _GF_DDOS):
        respx.get(f"{gf_base}{_GF_RESOLVE_PATH}").mock(
            return_value=Response(200, json={"code": 0})
        )
    resolver = _make_resolver(test_settings)
    success, product_type, data = await resolver.resolve_ip("9.9.9.9")
    assert success is False
    assert data is None
    await resolver.aclose()


@respx.mock
async def test_resolver_non_200_returns_false(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_RESOLVE_PATH}").mock(return_value=Response(404))
    for gf_base in (_GF_YXD, _GF_CDN, _GF_DDOS):
        respx.get(f"{gf_base}{_GF_RESOLVE_PATH}").mock(return_value=Response(404))
    resolver = _make_resolver(test_settings)
    success, _, data = await resolver.resolve_ip("1.1.1.1")
    assert success is False
    assert data is None
    await resolver.aclose()


@respx.mock
async def test_resolver_network_exception(test_settings):
    respx.get(f"{_WAF_BASE}{_WAF_RESOLVE_PATH}").mock(side_effect=Exception("refused"))
    for gf_base in (_GF_YXD, _GF_CDN, _GF_DDOS):
        respx.get(f"{gf_base}{_GF_RESOLVE_PATH}").mock(side_effect=Exception("refused"))
    resolver = _make_resolver(test_settings)
    success, _, data = await resolver.resolve_ip("1.1.1.1")
    assert success is False
    await resolver.aclose()
