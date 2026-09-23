"""
Unit tests for PrometheusAdapter.

Two groups:
  1. Pure helpers (_calc_step, _peak_value) — no HTTP
  2. PrometheusAdapter via respx HTTP mocking
"""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from kks_runtime.config.settings import Settings
from kks_security.adapters.prometheus import (
    PrometheusAdapter,
    _calc_step,
    _peak_value,
)

# ---------------------------------------------------------------------------
# _calc_step — pure
# ---------------------------------------------------------------------------


def test_calc_step_minimum():
    assert _calc_step(0, 0) == 60  # max(60, 0) → duration=60 → ≤300 → 60


def test_calc_step_short_window():
    assert _calc_step(0, 60) == 60


def test_calc_step_300s_boundary():
    assert _calc_step(0, 300) == 60


def test_calc_step_1h():
    step = _calc_step(0, 3600)
    assert step == 60  # 3600 // 60 = 60, max(60, 60) = 60


def test_calc_step_24h():
    step = _calc_step(0, 86_400)
    assert step == 1440  # 86400 // 60 = 1440


def test_calc_step_very_long():
    # 200_000 seconds > 86_400 → duration // 100
    step = _calc_step(0, 200_000)
    assert step == 2000


def test_calc_step_never_below_60():
    # Any duration should return at least 60
    for d in range(0, 10000, 100):
        assert _calc_step(0, d) >= 60


# ---------------------------------------------------------------------------
# _peak_value — pure
# ---------------------------------------------------------------------------


def test_peak_value_empty():
    assert _peak_value([]) is None


def test_peak_value_range_result():
    result = [{"values": [[1, "10.5"], [2, "20.0"], [3, "15.3"]]}]
    assert _peak_value(result) == pytest.approx(20.0)


def test_peak_value_instant_result():
    result = [{"value": [1700000000, "42.7"]}]
    assert _peak_value(result) == pytest.approx(42.7)


def test_peak_value_multiple_series():
    result = [
        {"values": [[1, "5.0"], [2, "8.0"]]},
        {"values": [[1, "3.0"]]},
    ]
    # Only inspects first series
    assert _peak_value(result) == pytest.approx(8.0)


def test_peak_value_invalid_number_skipped():
    # "abc" cannot be parsed by float() → skipped; "12.0" is returned
    result = [{"values": [[1, "abc"], [2, "12.0"]]}]
    assert _peak_value(result) == pytest.approx(12.0)


def test_peak_value_all_invalid():
    result = [{"values": [[1, "abc"]]}]
    assert _peak_value(result) is None


# ---------------------------------------------------------------------------
# PrometheusAdapter — respx HTTP mocking
# ---------------------------------------------------------------------------

_PROM_BASE = "http://fake-prom:9090"

_INSTANT_OK = {
    "status": "success",
    "data": {
        "result": [
            {"metric": {"instance": "1.2.3.4:9100"}, "value": [1700000000, "55.1"]}
        ]
    },
}

_RANGE_OK = {
    "status": "success",
    "data": {
        "result": [
            {"metric": {}, "values": [[1700000000, "30.0"], [1700000060, "45.0"]]}
        ]
    },
}


def _make_adapter(test_settings: Settings) -> PrometheusAdapter:
    return PrometheusAdapter(settings=test_settings)


@respx.mock
async def test_instant_happy_path(test_settings):
    respx.get(f"{_PROM_BASE}/api/v1/query").mock(return_value=Response(200, json=_INSTANT_OK))
    adapter = _make_adapter(test_settings)
    result = await adapter.instant('up{job="node"}')
    assert len(result) == 1
    assert result[0]["value"][1] == "55.1"
    await adapter.close()


@respx.mock
async def test_range_query_happy_path(test_settings):
    respx.get(f"{_PROM_BASE}/api/v1/query_range").mock(
        return_value=Response(200, json=_RANGE_OK)
    )
    adapter = _make_adapter(test_settings)
    result = await adapter.range_query('node_cpu', start_ts=1700000000, end_ts=1700003600)
    assert len(result) == 1
    assert result[0]["values"][1][1] == "45.0"
    await adapter.close()


@respx.mock
async def test_prometheus_error_response_raises(test_settings):
    error_body = {"status": "error", "error": "bad query"}
    respx.get(f"{_PROM_BASE}/api/v1/query").mock(return_value=Response(200, json=error_body))
    adapter = _make_adapter(test_settings)
    with pytest.raises(RuntimeError, match="Prometheus error"):
        await adapter.instant("bad_promql{}")
    await adapter.close()


def test_instance_bare_ip(test_settings):
    adapter = _make_adapter(test_settings)
    assert adapter.instance("1.2.3.4") == "1.2.3.4:9100"


def test_instance_already_has_port(test_settings):
    adapter = _make_adapter(test_settings)
    assert adapter.instance("1.2.3.4:9100") == "1.2.3.4:9100"


def test_instance_custom_port(test_settings):
    adapter = _make_adapter(test_settings)
    assert adapter.instance("1.2.3.4:8080") == "1.2.3.4:8080"
