"""
Unit tests for GFCollector.

Group 1 — pure helpers (no HTTP): port normalisation, wildcard,
           endpoint labels, _format_rules_summary.
Group 2 — HTTP paths via respx.
"""
from __future__ import annotations

import respx
from httpx import Response

from kks_security.collectors.gf_collector import GFCollector

_YXD = "http://fake-gf-yxd"
_CDN = "http://fake-gf-cdn"
_DDOS_EP = "http://fake-gf-ddos"
_NODE_LIST_PATH = "/api/p_domainRule/getNodeIpList"
_WAF_PATH = "/api/p_domainRule/getDomainWaf"


def _make_collector(test_settings) -> GFCollector:
    return GFCollector(settings=test_settings)


# ---------------------------------------------------------------------------
# Group 1 — pure helpers
# ---------------------------------------------------------------------------


def test_normalise_port_80():
    assert GFCollector._normalise_port(80) is None


def test_normalise_port_443():
    assert GFCollector._normalise_port(443) is None


def test_normalise_port_8080():
    assert GFCollector._normalise_port(8080) == 8080


def test_normalise_port_none():
    assert GFCollector._normalise_port(None) is None


def test_to_wildcard_three_parts():
    assert GFCollector._to_wildcard("www.example.com") == "*.example.com"


def test_to_wildcard_two_parts():
    assert GFCollector._to_wildcard("example.com") == "*.example.com"


def test_to_wildcard_deep():
    assert GFCollector._to_wildcard("a.b.c.d") == "*.b.c.d"


def test_format_rules_summary_failed_response():
    resp = {"code": 0, "msg": "domain not found", "data": None}
    summary = GFCollector._format_rules_summary(resp)
    assert "Query failed" in summary
    assert "domain not found" in summary


def test_format_rules_summary_empty_rules():
    resp = {"code": 1, "data": {"domain": "example.com", "data": []}}
    summary = GFCollector._format_rules_summary(resp)
    assert "no protection rules" in summary


def test_format_rules_summary_whitelist_group():
    resp = {
        "code": 1,
        "data": {
            "domain": "x.com",
            "data": [
                {
                    "rule_type": "白名单",
                    "purpose": "allow office",
                    "match": {
                        "ip": ["1.2.3.4", "5.6.7.8"],
                        "url": ["/admin"],
                        "action_desc": "allow",
                    },
                }
            ],
        },
    }
    summary = GFCollector._format_rules_summary(resp)
    assert "白名单" in summary
    assert "1.2.3.4" in summary
    assert "allow" in summary


def test_format_rules_summary_geo_block_foreign():
    resp = {
        "code": 1,
        "data": {
            "domain": "x.com",
            "data": [
                {
                    "rule_type": "区域封禁",
                    "purpose": "block foreign",
                    "match": {"area": 2, "status": 1},
                }
            ],
        },
    }
    summary = GFCollector._format_rules_summary(resp)
    assert "block foreign" in summary
    assert "enabled" in summary


def test_format_rules_summary_rate_limit_group():
    resp = {
        "code": 1,
        "data": {
            "domain": "x.com",
            "data": [
                {
                    "rule_type": "访问频率",
                    "purpose": "rate limit",
                    "match": [
                        {
                            "name": "rule1",
                            "trigger_freq_desc": "high freq",
                            "req_count": 100,
                            "req_seconds": 1,
                            "action_desc": "block",
                            "status": 1,
                        }
                    ],
                }
            ],
        },
    }
    summary = GFCollector._format_rules_summary(resp)
    assert "rule1" in summary
    assert "block" in summary
    assert "enabled" in summary


# ---------------------------------------------------------------------------
# Group 2 — HTTP via respx
# ---------------------------------------------------------------------------

_NODE_PAYLOAD = {
    "data": [
        {"node_ip": "10.0.0.1", "ip_list": ["10.0.0.2", "10.0.0.3"]}
    ]
}


@respx.mock
async def test_query_nodes_by_domain_first_endpoint_matches(test_settings):
    respx.get(f"{_YXD}{_NODE_LIST_PATH}").mock(return_value=Response(200, json=_NODE_PAYLOAD))
    # CDN and DDOS should not be called if YXD matches
    collector = _make_collector(test_settings)
    nodes = await collector.query_nodes_by_domain("example.com")
    assert len(nodes) == 3  # node_ip + 2 ip_list items
    assert nodes[0].ip == "10.0.0.1"
    assert nodes[0].node_type == "node_product"
    await collector.aclose()


@respx.mock
async def test_query_nodes_by_domain_fallback_to_second_endpoint(test_settings):
    respx.get(f"{_YXD}{_NODE_LIST_PATH}").mock(return_value=Response(200, json={"data": []}))
    respx.get(f"{_CDN}{_NODE_LIST_PATH}").mock(return_value=Response(200, json=_NODE_PAYLOAD))
    collector = _make_collector(test_settings)
    nodes = await collector.query_nodes_by_domain("example.com")
    assert len(nodes) == 3
    await collector.aclose()


@respx.mock
async def test_query_nodes_by_domain_wildcard_fallback(test_settings):
    # Exact domain returns empty; wildcard call returns nodes.
    # respx matches by URL + params, so we use a pattern mock that accepts any params.
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        domains_param = request.url.params.get("domains", "")
        if domains_param.startswith("*"):
            return Response(200, json=_NODE_PAYLOAD)
        return Response(200, json={"data": []})

    respx.get(f"{_YXD}{_NODE_LIST_PATH}").mock(side_effect=handler)
    respx.get(f"{_CDN}{_NODE_LIST_PATH}").mock(return_value=Response(200, json={"data": []}))
    respx.get(f"{_DDOS_EP}{_NODE_LIST_PATH}").mock(return_value=Response(200, json={"data": []}))
    collector = _make_collector(test_settings)
    nodes = await collector.query_nodes_by_domain("www.example.com")
    # wildcard "*.example.com" should have been tried and matched
    assert len(nodes) == 3
    await collector.aclose()


@respx.mock
async def test_query_nodes_by_domain_deduplicates(test_settings):
    # node_ip appears in ip_list too — should be deduplicated
    payload = {"data": [{"node_ip": "10.0.0.1", "ip_list": ["10.0.0.1", "10.0.0.2"]}]}
    respx.get(f"{_YXD}{_NODE_LIST_PATH}").mock(return_value=Response(200, json=payload))
    collector = _make_collector(test_settings)
    nodes = await collector.query_nodes_by_domain("example.com")
    ips = [n.ip for n in nodes]
    assert ips.count("10.0.0.1") == 1  # not duplicated
    await collector.aclose()


@respx.mock
async def test_query_nodes_by_domain_all_fail(test_settings):
    for base in (_YXD, _CDN, _DDOS_EP):
        respx.get(f"{base}{_NODE_LIST_PATH}").mock(side_effect=Exception("err"))
    collector = _make_collector(test_settings)
    nodes = await collector.query_nodes_by_domain("example.com")
    assert nodes == []
    await collector.aclose()
