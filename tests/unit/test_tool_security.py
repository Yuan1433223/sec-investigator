"""
Unit tests for security tool helpers and tool wiring.

Group 1 — pure attack-detection logic (_is_cc_attack, _is_ddos_attack).
Group 2 — tool output wiring via injected mock adapters.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from kks_runtime.config.settings import Settings
from kks_security.adapters.cc import PointStatus
from kks_security.tools.security_tools import _is_cc_attack, _is_ddos_attack, _make_security_tools

# ---------------------------------------------------------------------------
# Group 1 — _is_cc_attack (pure)
# ---------------------------------------------------------------------------


def _settings_with_thresholds(pps=2000, delta=1000) -> Settings:
    return Settings(
        cc_attack_pps_threshold=pps,
        cc_attack_delta_threshold=delta,
    )


def test_is_cc_attack_none_pps():
    point = PointStatus(input_pps=None, input_submit_pps=None)
    assert _is_cc_attack(point, _settings_with_thresholds()) is False


def test_is_cc_attack_above_both_thresholds():
    # input_pps=3000 > 2000, delta=3000-500=2500 >= 1000
    point = PointStatus(input_pps=3000, input_submit_pps=500)
    assert _is_cc_attack(point, _settings_with_thresholds()) is True


def test_is_cc_attack_pps_above_but_delta_below():
    # input_pps=3000 > 2000, but delta=3000-2500=500 < 1000
    point = PointStatus(input_pps=3000, input_submit_pps=2500)
    assert _is_cc_attack(point, _settings_with_thresholds()) is False


def test_is_cc_attack_pps_at_threshold_not_above():
    # input_pps=2000 is NOT > 2000
    point = PointStatus(input_pps=2000, input_submit_pps=0)
    assert _is_cc_attack(point, _settings_with_thresholds()) is False


def test_is_cc_attack_pps_just_above_threshold():
    point = PointStatus(input_pps=2001, input_submit_pps=0)
    assert _is_cc_attack(point, _settings_with_thresholds()) is True


def test_is_cc_attack_delta_exactly_at_threshold():
    # delta = 3000 - 1000 = 2000 >= 1000 → True (uses >=)
    point = PointStatus(input_pps=3000, input_submit_pps=2000)
    assert _is_cc_attack(point, _settings_with_thresholds(pps=2000, delta=1000)) is True


# ---------------------------------------------------------------------------
# Group 2 — _is_ddos_attack (pure)
# ---------------------------------------------------------------------------


def _settings_ddos(threshold=1_000_000) -> Settings:
    return Settings(ddos_attack_kbps_threshold=threshold)


def test_is_ddos_attack_none_bps():
    assert _is_ddos_attack({"bps": None}, _settings_ddos()) is False


def test_is_ddos_attack_below_threshold():
    assert _is_ddos_attack({"bps": 999_999}, _settings_ddos()) is False


def test_is_ddos_attack_at_threshold():
    # Uses >=, so exactly at threshold is True
    assert _is_ddos_attack({"bps": 1_000_000}, _settings_ddos()) is True


def test_is_ddos_attack_above_threshold():
    assert _is_ddos_attack({"bps": 5_000_000}, _settings_ddos()) is True


def test_is_ddos_attack_missing_bps_key():
    assert _is_ddos_attack({}, _settings_ddos()) is False


# ---------------------------------------------------------------------------
# Group 3 — tool output wiring
# ---------------------------------------------------------------------------


def _mock_cc():
    m = MagicMock()
    m.get_host_point = AsyncMock(
        return_value=[PointStatus(address="1.2.3.4", input_pps=3000, input_submit_pps=500)]
    )
    m.get_batch_host_status = AsyncMock(
        return_value={"status": True, "data": [{"ip": "1.2.3.4"}], "success_count": 1}
    )
    return m


def _mock_ddos():
    m = MagicMock()
    m.get_ddos_list = AsyncMock(
        return_value={"status": True, "data": [{"bps": 2_000_000}]}
    )
    return m


def _mock_resolver():
    m = MagicMock()
    m.resolve_ip = AsyncMock(return_value=(True, "WAF", {"node_ip": "10.0.0.1"}))
    return m


def _mock_waf_collector():
    m = MagicMock()
    m.query_nodes_by_domain = AsyncMock(return_value=[])
    return m


def _mock_gf_collector():
    m = MagicMock()
    m.query_nodes_by_domain = AsyncMock(return_value=[])
    m.query_domain_protection_policy = AsyncMock(
        return_value={"summary": "No rules", "project": "YXD"}
    )
    return m


def _tools():
    return _make_security_tools(
        cc_adapter=_mock_cc(),
        ddos_adapter=_mock_ddos(),
        node_resolver=_mock_resolver(),
        waf_collector=_mock_waf_collector(),
        gf_collector=_mock_gf_collector(),
    )


async def test_check_cc_status_annotates_attack_flag():
    tools = {t.name: t for t in _tools()}
    result = await tools["check_cc_status"].ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] == "ok"
    assert len(result["points"]) == 1
    # input_pps=3000 > 2000, delta=2500 >= 1000 → True
    assert result["points"][0]["is_under_attack"] is True


async def test_check_cc_status_no_data():
    cc = MagicMock()
    cc.get_host_point = AsyncMock(return_value=[])
    tools = {t.name: t for t in _make_security_tools(cc_adapter=cc)}
    result = await tools["check_cc_status"].ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] == "no_data"
    assert result["points"] == []


async def test_check_ddos_status_annotates_threshold_flag():
    tools = {t.name: t for t in _tools()}
    result = await tools["check_ddos_status"].ainvoke({"ips": ["1.2.3.4"]})
    assert result["count"] == 1
    # bps=2_000_000 >= 1_000_000 → True
    assert result["events"][0]["exceeds_threshold"] is True


async def test_check_host_status_returns_adapter_result():
    tools = {t.name: t for t in _tools()}
    result = await tools["check_host_status"].ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] is True
    assert result["success_count"] == 1


async def test_check_ddos_status_accepts_raw_list_response():
    ddos = MagicMock()
    ddos.get_ddos_list = AsyncMock(return_value=[{"bps": 2_000_000}])
    tools = {t.name: t for t in _make_security_tools(ddos_adapter=ddos)}
    result = await tools["check_ddos_status"].ainvoke({"ips": ["1.2.3.4"]})
    assert result["status"] is True
    assert result["count"] == 1
    assert result["events"][0]["exceeds_threshold"] is True


async def test_query_nodes_ip_by_ip_shapes_output():
    tools = {t.name: t for t in _tools()}
    result = await tools["query_nodes_ip_by_ip"].ainvoke({"ip": "1.2.3.4"})
    assert result["success"] is True
    assert result["product_type"] == "WAF"
    assert result["data"] == {"node_ip": "10.0.0.1"}


async def test_query_nodes_ip_by_domain_waf():
    tools = {t.name: t for t in _tools()}
    result = await tools["query_nodes_ip_by_domain"].ainvoke(
        {"source_type": "WAF", "domain": "example.com"}
    )
    assert result["source"] == "WAF"
    assert "nodes" in result


async def test_query_nodes_ip_by_domain_gf():
    tools = {t.name: t for t in _tools()}
    result = await tools["query_nodes_ip_by_domain"].ainvoke(
        {"source_type": "GF", "domain": "example.com"}
    )
    assert result["source"] == "GF"


async def test_query_domain_protection_policy():
    tools = {t.name: t for t in _tools()}
    result = await tools["query_domain_protection_policy"].ainvoke({"domain": "example.com"})
    assert result["summary"] == "No rules"
    assert result["project"] == "YXD"
