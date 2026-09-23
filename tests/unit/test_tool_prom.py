"""
Unit tests for Prometheus tool helpers and tool output shapes.

Group 1 — _ts (pure time-string conversion).
Group 2 — tool output shapes via injected mock PrometheusAdapter.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from security.tools.prom_tools import _make_prom_tools, _ts

_TIME_ARGS = {
    "instance": "1.2.3.4",
    "start_time": "2026-01-01 00:00:00",
    "end_time": "2026-01-01 01:00:00",
}

# ---------------------------------------------------------------------------
# Group 1 — _ts (pure)
# ---------------------------------------------------------------------------


def test_ts_known_value():
    # "2026-01-01 00:00:00" in local time — test relative equality
    result = _ts("2026-01-01 00:00:00")
    assert isinstance(result, int)
    assert result > 1_700_000_000  # sanity: after Nov 2023


def test_ts_deterministic():
    assert _ts("2026-06-15 12:30:00") == _ts("2026-06-15 12:30:00")


def test_ts_ordering():
    assert _ts("2026-01-01 00:00:00") < _ts("2026-01-01 01:00:00")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_prom(instant_result=None, range_result=None):
    m = MagicMock()
    m.instance = lambda ip: ip if ":" in ip else f"{ip}:9100"
    m.instant = AsyncMock(return_value=instant_result or [])
    m.range_query = AsyncMock(return_value=range_result or [])
    return m


def _toolmap(adapter):
    return {t.name: t for t in _make_prom_tools(adapter=adapter)}


# ---------------------------------------------------------------------------
# Group 2 — tool output shapes
# ---------------------------------------------------------------------------


async def test_query_instance_uname_empty():
    tools = _toolmap(_mock_prom())
    result = await tools["query_instance_uname"].ainvoke({"instance": "1.2.3.4"})
    assert result == {"system": {}}


async def test_query_instance_uname_with_data():
    metric = {
        "metric": {
            "instance": "1.2.3.4:9100",
            "nodename": "host1",
            "sysname": "Linux",
            "machine": "x86_64",
            "release": "5.15.0",
        },
        "value": [0, "1"],
    }
    tools = _toolmap(_mock_prom(instant_result=[metric]))
    result = await tools["query_instance_uname"].ainvoke({"instance": "1.2.3.4"})
    assert result["system"]["nodename"] == "host1"
    assert result["system"]["sysname"] == "Linux"


async def test_query_instance_cpu_has_data():
    range_result = [{"values": [[0, "45.5"]]}]
    tools = _toolmap(_mock_prom(range_result=range_result))
    result = await tools["query_instance_cpu"].ainvoke(_TIME_ARGS)
    assert result["cpu_usage"] == "45.5%"


async def test_query_instance_cpu_no_data():
    tools = _toolmap(_mock_prom(range_result=[]))
    result = await tools["query_instance_cpu"].ainvoke(_TIME_ARGS)
    assert result["cpu_usage"] == "no data"


async def test_query_instance_memory_has_data():
    range_result = [{"values": [[0, "72.3"]]}]
    tools = _toolmap(_mock_prom(range_result=range_result))
    result = await tools["query_instance_memory"].ainvoke(_TIME_ARGS)
    assert result["memory_usage"] == "72.3%"


async def test_query_instance_tcp_has_data():
    range_result = [{"values": [[0, "1523.0"]]}]
    tools = _toolmap(_mock_prom(range_result=range_result))
    result = await tools["query_instance_tcp"].ainvoke(_TIME_ARGS)
    assert result["tcp_established"] == 1523


async def test_query_instance_tcp_no_data():
    tools = _toolmap(_mock_prom(range_result=[]))
    result = await tools["query_instance_tcp"].ainvoke(_TIME_ARGS)
    assert result["tcp_established"] is None


async def test_query_instance_bandwidth_shapes_output():
    # range_query called twice (rx and tx) — return same result for both
    range_result = [{"values": [[0, "100.5"]]}]
    adapter = _mock_prom(range_result=range_result)
    tools = _toolmap(adapter)
    result = await tools["query_instance_bandwidth"].ainvoke(_TIME_ARGS)
    assert "rx_mbps" in result
    assert "tx_mbps" in result
    assert result["rx_mbps"] == pytest.approx(100.5)


async def test_query_instance_status_composite():
    range_result = [{"values": [[0, "50.0"]]}]
    adapter = _mock_prom(range_result=range_result)
    tools = _toolmap(adapter)
    result = await tools["query_instance_status"].ainvoke(_TIME_ARGS)
    assert "cpu_usage" in result
    assert "memory_usage" in result
    assert "tcp_established" in result
    assert result["instance"] == "1.2.3.4"


# ---------------------------------------------------------------------------
# Group 3 — query_instance_disk and query_instance_socket
# ---------------------------------------------------------------------------


async def test_query_instance_disk_shapes_output():
    # Two devices: sda and sdb, each with read + write series
    range_result = [
        {"metric": {"device": "sda"}, "values": [[0, "1.5"], [60, "2.0"]]},
        {"metric": {"device": "sdb"}, "values": [[0, "0.5"], [60, "0.8"]]},
    ]
    prom = _mock_prom(range_result=range_result)
    tools = _toolmap(prom)
    result = await tools["query_instance_disk"].ainvoke(_TIME_ARGS)
    assert "disk_io" in result
    # Both devices present
    assert "sda" in result["disk_io"]
    assert "sdb" in result["disk_io"]
    # Keys present per device
    assert "read_mbps" in result["disk_io"]["sda"]
    assert "write_mbps" in result["disk_io"]["sda"]


async def test_query_instance_disk_empty_no_data():
    prom = _mock_prom(range_result=[])
    tools = _toolmap(prom)
    result = await tools["query_instance_disk"].ainvoke(_TIME_ARGS)
    assert result == {"disk_io": {}}


async def test_query_instance_disk_read_write_values():
    """_peak_value extracts max float from values; verify the round-trip."""
    range_result_read = [
        {"metric": {"device": "sda"}, "values": [[0, "1.0"], [60, "3.0"]]}
    ]
    range_result_write = [
        {"metric": {"device": "sda"}, "values": [[0, "0.5"], [60, "1.5"]]}
    ]
    from unittest.mock import AsyncMock, MagicMock
    prom = MagicMock()
    prom.instance = lambda ip: ip if ":" in ip else f"{ip}:9100"
    # First call = read, second call = write
    prom.range_query = AsyncMock(side_effect=[range_result_read, range_result_write])
    tools = _toolmap(prom)
    result = await tools["query_instance_disk"].ainvoke(_TIME_ARGS)
    sda = result["disk_io"]["sda"]
    assert sda["read_mbps"] == 3.0   # peak of [1.0, 3.0]
    assert sda["write_mbps"] == 1.5  # peak of [0.5, 1.5]


async def test_query_instance_socket_has_data():
    range_result = [{"metric": {}, "values": [[0, "120"], [60, "150"], [120, "130"]]}]
    prom = _mock_prom(range_result=range_result)
    tools = _toolmap(prom)
    result = await tools["query_instance_socket"].ainvoke(_TIME_ARGS)
    assert "sockets_used" in result
    assert result["sockets_used"] == 150  # peak of [120, 150, 130]


async def test_query_instance_socket_no_data():
    prom = _mock_prom(range_result=[])
    tools = _toolmap(prom)
    result = await tools["query_instance_socket"].ainvoke(_TIME_ARGS)
    assert result == {"sockets_used": None}


def test_prom_tools_list_includes_new_tools():
    from security.tools.prom_tools import PROM_TOOLS
    names = {t.name for t in PROM_TOOLS}
    assert "query_instance_disk" in names
    assert "query_instance_socket" in names
