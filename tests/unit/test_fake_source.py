"""
Fake data-source contract tests (DATA_SOURCE=fake).

These lock in the fixture → tool contract: with ``data_source="fake"`` every
adapter serves realistic synthetic data derived from the recorded incidents
(docs/incidents.md), fully offline. If a real adapter changes its response
contract, these tests will fail — guarding the demo path.
"""
from __future__ import annotations

import pytest

from runtime.config.settings import Settings
from security.adapters.cc import CCAdapter
from security.adapters.ddos import DDoSAdapter
from security.adapters.es import ESAdapter
from security.adapters.prometheus import PrometheusAdapter
from security.collectors.gf_collector import GFCollector
from security.collectors.node_resolver import NodeResolver
from security.rag.engine import RAGEngine
from security.tools.es_tools import _make_es_tools
from security.tools.prom_tools import _make_prom_tools


@pytest.fixture
def fake_settings() -> Settings:
    """Settings in fake mode with well-formed placeholder base URLs (hosts ignored)."""
    return Settings(
        data_source="fake",
        es_url="http://es.example.internal:9200",
        prometheus_url="http://prom.example.internal:9090",
        cc_api_url="http://cc.example.internal",
        ddos_api_url="http://ddos.example.internal",
        waf_api_url="http://waf.example.internal",
        gf_yxd_api_url="http://gf-yxd.example.internal",
        gf_cdn_api_url="http://gf-cdn.example.internal",
        gf_ddos_api_url="http://gf-ddos.example.internal",
    )


# ---------------------------------------------------------------------------
# ES — incident 1 (game.ali213.net, distributed crawler 4xx spike)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_es_qps_trend_matches_incident1_peak(fake_settings):
    tools = {t.name: t for t in _make_es_tools(ESAdapter(fake_settings))}
    r = await tools["query_es_qps_trend"].ainvoke(
        {
            "domain": "game.ali213.net",
            "interval": "1m",
            "start_time": "2026-04-23 11:56:40",
            "end_time": "2026-04-23 12:14:40",
        }
    )
    peak = max(b["count"] for b in r["trend"])
    assert peak >= 7000, f"expected 4xx spike peak ≈7418, got {peak}"
    assert any(b["time"].startswith("2026-04-23 12:03") for b in r["trend"])


@pytest.mark.asyncio
async def test_fake_es_top_ip_is_known_crawler(fake_settings):
    tools = {t.name: t for t in _make_es_tools(ESAdapter(fake_settings))}
    r = await tools["query_es_top_n"].ainvoke(
        {"field": "remote_addr", "domain": "game.ali213.net"}
    )
    assert r["top_n"][0]["value"] == "74.7.227.59", "top IP should match incident 1"


@pytest.mark.asyncio
async def test_fake_es_status_distribution_4xx_dominant(fake_settings):
    tools = {t.name: t for t in _make_es_tools(ESAdapter(fake_settings))}
    r = await tools["query_status_code_distribution"].ainvoke(
        {
            "query_by": "domain",
            "value": "game.ali213.net",
            "start_time": "2026-04-23 12:00:00",
            "end_time": "2026-04-23 12:10:00",
        }
    )
    cur = {x["status"]: x["count"] for x in r["current"]}
    prev = {x["status"]: x["count"] for x in r["previous"]}
    cur_4xx = sum(v for k, v in cur.items() if 400 <= k < 500)
    prev_4xx = sum(v for k, v in prev.items() if 400 <= k < 500)
    assert cur_4xx > prev_4xx * 8, "4xx should spike vs the 30-min-prior baseline"


# ---------------------------------------------------------------------------
# Prometheus — node health consistent with the incident
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_prom_incident1_node_healthy(fake_settings):
    tools = {t.name: t for t in _make_prom_tools(PrometheusAdapter(fake_settings))}
    r = await tools["query_instance_status"].ainvoke(
        {
            "instance": "117.24.6.116",
            "start_time": "2026-04-23 12:00:00",
            "end_time": "2026-04-23 12:10:00",
        }
    )
    assert float(r["cpu_usage"].rstrip("%")) < 30, "incident 1 node should be healthy"
    assert r["tcp_established"] is not None


@pytest.mark.asyncio
async def test_fake_prom_incident3_node_overloaded(fake_settings):
    tools = {t.name: t for t in _make_prom_tools(PrometheusAdapter(fake_settings))}
    r = await tools["query_instance_status"].ainvoke(
        {
            "instance": "112.90.155.1",
            "start_time": "2026-04-18 02:23:40",
            "end_time": "2026-04-18 02:41:40",
        }
    )
    assert float(r["cpu_usage"].rstrip("%")) > 70, "incident 3 node should be overloaded"


# ---------------------------------------------------------------------------
# Security — no CC/DDoS for these incidents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_cc_no_attack(fake_settings):
    cc = CCAdapter(fake_settings)
    points = await cc.get_host_point(["117.24.6.116"])
    await cc.aclose()
    assert points, "should return host points"
    assert points[0].input_pps < 2000, "pps below CC threshold → no attack"


@pytest.mark.asyncio
async def test_fake_ddos_empty(fake_settings):
    ddos = DDoSAdapter(fake_settings)
    resp = await ddos.get_ddos_list(["117.24.6.116"])
    await ddos.aclose()
    assert resp.get("data") == []


# ---------------------------------------------------------------------------
# Resolution — GF nodes for the incident domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_domain_resolution_returns_gf_nodes(fake_settings):
    gf = GFCollector(fake_settings)
    nodes = await gf.query_nodes_by_domain("game.ali213.net")
    await gf.aclose()
    assert nodes, "domain should resolve to GF nodes"
    assert any(n.ip == "117.24.6.116" for n in nodes)


@pytest.mark.asyncio
async def test_fake_ip_resolution_product_gf(fake_settings):
    resolver = NodeResolver(fake_settings)
    ok, product_type, data = await resolver.resolve_ip("117.24.6.116")
    await resolver.aclose()
    assert ok is True
    assert product_type == "GF", "incident nodes belong to GF product"
    assert isinstance(data, list) and data and data[0].get("node_ip") == "117.24.6.116"


# ---------------------------------------------------------------------------
# RAG — offline knowledge base
# ---------------------------------------------------------------------------


def test_fake_rag_returns_runbook(fake_settings):
    engine = RAGEngine(fake_settings)
    docs = engine.search("4xx crawler 404 scan", top_k=3)
    assert docs, "fake RAG should return a runbook excerpt"
    assert "4xx" in docs[0]["text"] or "爬虫" in docs[0]["text"]
