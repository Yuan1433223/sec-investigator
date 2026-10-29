"""The existing demo's real tools should return mutually consistent evidence."""
from datetime import datetime

import pytest

from runtime.config.settings import Settings
from security.adapters.es import ESAdapter
from security.fake.fixtures import get_profile
from security.tools.es_tools import _make_es_tools
from security.adapters.prometheus import PrometheusAdapter
from security.tools.prom_tools import _make_prom_tools


@pytest.mark.asyncio
async def test_origin_demo_status_trends_and_raw_samples_agree():
    target = "api2.xs2027.cn"
    profile = get_profile(domain=target)
    assert profile is not None
    adapter = ESAdapter(Settings(_env_file=None, data_source="fake"))
    tools = {tool.name: tool for tool in _make_es_tools(adapter)}
    window = {"domain": target, "start_time": profile.window_start, "end_time": profile.window_end}
    try:
        qps = await tools["query_es_qps_trend"].ainvoke(window)
        errors = await tools["query_es_status_code_trend"].ainvoke({**window, "status_type": "5xx"})
        dist = await tools["query_status_code_distribution"].ainvoke({
            "query_by": "domain", "value": target,
            "start_time": profile.window_start, "end_time": profile.window_end,
        })
        raw = await tools["query_es_raw_logs"].ainvoke({**window, "size": 12})
        top = await tools["query_es_top_n_trend"].ainvoke({**window, "field": "remote_addr", "top_n": 3})
    finally:
        await adapter.aclose()
    total_errors = sum(bucket["count"] for bucket in errors["trend"])
    distribution_errors = sum(row["count"] for row in dist["current"] if 500 <= row["status"] < 600)
    assert errors["total"] == total_errors
    assert total_errors < qps["total"]
    assert abs(total_errors - distribution_errors) <= len(errors["trend"]) * 4
    for hit in raw["hits"]:
        assert datetime.fromisoformat(profile.window_start) <= datetime.fromisoformat(hit["time"]).replace(tzinfo=None) <= datetime.fromisoformat(profile.window_end)
        assert hit["status"] in profile.status_share
        assert hit["upstream_status"] == hit["status"]
        assert hit["http_user_agent"] == "okhttp/3.12.6"
        assert hit["upstream_addr"] == profile.origin_ip
    for item in top["top_n"]:
        assert sum(bucket["count"] for bucket in item["trend"]) == item["total"]
        assert item["total"] < qps["total"]


@pytest.mark.asyncio
async def test_fake_disk_and_network_use_distinct_device_types():
    adapter = PrometheusAdapter(Settings(_env_file=None, data_source="fake"))
    tools = {tool.name: tool for tool in _make_prom_tools(adapter)}
    args = {"instance": "118.178.13.52", "start_time": "2026-04-18 12:18:00",
            "end_time": "2026-04-18 12:36:00"}
    try:
        disk = await tools["query_instance_disk"].ainvoke(args)
        network = await adapter.range_query('node_network_receive_bytes_total{instance="118.178.13.52:64998"}')
    finally:
        await adapter.aclose()
    assert "sda" in disk["disk_io"]
    assert "eth0" not in disk["disk_io"]
    assert network[0]["metric"]["device"] == "eth0"
