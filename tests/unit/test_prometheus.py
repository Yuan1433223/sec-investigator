from unittest.mock import AsyncMock, MagicMock

import pytest

from kks_security.adapters.prometheus import PrometheusAdapter, _calc_step, _peak_value
from kks_security.tools.prom_tools import _make_prom_tools

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_calc_step_short_range():
    assert _calc_step(0, 300) == 60


def test_calc_step_day():
    step = _calc_step(0, 86_400)
    assert step >= 60
    assert step <= 86_400 // 60  # at most 1-per-minute


def test_calc_step_long_range():
    step = _calc_step(0, 7 * 86_400)
    assert step >= 60


def test_peak_value_range():
    results = [{"values": [[1, "10.5"], [2, "20.0"], [3, "15.3"]]}]
    assert _peak_value(results) == pytest.approx(20.0)


def test_peak_value_instant():
    results = [{"value": [1700000000, "42.7"]}]
    assert _peak_value(results) == pytest.approx(42.7)


def test_peak_value_empty():
    assert _peak_value([]) is None


# ---------------------------------------------------------------------------
# PrometheusAdapter.instance()
# ---------------------------------------------------------------------------


def test_instance_bare_ip():
    # We can't init the real adapter without a settings object, so use a mock
    adapter = object.__new__(PrometheusAdapter)
    adapter._node_port = 64998
    assert adapter.instance("1.2.3.4") == "1.2.3.4:64998"


def test_instance_already_has_port():
    adapter = object.__new__(PrometheusAdapter)
    adapter._node_port = 64998
    assert adapter.instance("1.2.3.4:9100") == "1.2.3.4:9100"


# ---------------------------------------------------------------------------
# Prometheus tools with mock adapter
# ---------------------------------------------------------------------------


def _mock_adapter(instant_return=None, range_return=None):
    m = MagicMock(spec=PrometheusAdapter)
    m.instance = lambda ip: ip if ":" in ip else f"{ip}:64998"
    m.instant = AsyncMock(return_value=instant_return or [])
    m.range_query = AsyncMock(return_value=range_return or [])
    return m


@pytest.mark.asyncio
async def test_query_instance_uname_with_data():
    mock_result = [
        {
            "metric": {
                "instance": "1.2.3.4:64998",
                "nodename": "web01",
                "sysname": "Linux",
                "machine": "x86_64",
                "release": "5.15.0",
            }
        }
    ]
    adapter = _mock_adapter(instant_return=mock_result)
    tools = _make_prom_tools(adapter)
    uname_tool = next(t for t in tools if t.name == "query_instance_uname")

    result = await uname_tool.ainvoke({"instance": "1.2.3.4"})
    assert result["system"]["nodename"] == "web01"
    assert result["system"]["machine"] == "x86_64"


@pytest.mark.asyncio
async def test_query_instance_uname_empty():
    adapter = _mock_adapter(instant_return=[])
    tools = _make_prom_tools(adapter)
    uname_tool = next(t for t in tools if t.name == "query_instance_uname")
    result = await uname_tool.ainvoke({"instance": "1.2.3.4"})
    assert result == {"system": {}}


@pytest.mark.asyncio
async def test_query_instance_cpu():
    mock_range = [{"values": [[1, "35.5"], [2, "72.1"], [3, "68.0"]]}]
    adapter = _mock_adapter(range_return=mock_range)
    tools = _make_prom_tools(adapter)
    cpu_tool = next(t for t in tools if t.name == "query_instance_cpu")

    result = await cpu_tool.ainvoke({
        "instance": "1.2.3.4",
        "start_time": "2026-04-22 00:00:00",
        "end_time": "2026-04-22 01:00:00",
    })
    cpu_r = [{"values": [[1, "55.0"]]}]
    mem_r = [{"values": [[1, "62.0"]]}]
    tcp_r = [{"values": [[1, "1200"]]}]

    adapter = MagicMock(spec=PrometheusAdapter)
    adapter.instance = lambda ip: ip if ":" in ip else f"{ip}:64998"

    call_count = 0

    async def fake_range(promql, start, end):
        nonlocal call_count
        call_count += 1
        if "cpu" in promql:
            return cpu_r
        if "MemAvailable" in promql:
            return mem_r
        return tcp_r

    adapter.range_query = fake_range

    tools = _make_prom_tools(adapter)
    status_tool = next(t for t in tools if t.name == "query_instance_status")

    result = await status_tool.ainvoke({
        "instance": "1.2.3.4",
        "start_time": "2026-04-22 00:00:00",
        "end_time": "2026-04-22 01:00:00",
    })
    assert result["cpu_usage"] == "55.0%"
    assert result["memory_usage"] == "62.0%"
    assert result["tcp_established"] == 1200
