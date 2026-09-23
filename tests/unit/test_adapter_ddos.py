"""
Unit tests for DDoSAdapter.

All HTTP calls intercepted with respx.
"""
from __future__ import annotations

import respx
from httpx import Response, TimeoutException

from kks_security.adapters.ddos import DDoSAdapter

_BASE = "http://fake-ddos"


def _make_adapter(test_settings) -> DDoSAdapter:
    return DDoSAdapter(settings=test_settings)


# ---------------------------------------------------------------------------
# get_ddos_list
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_ddos_list_happy_path(test_settings):
    payload = {
        "status": True,
        "data": [
            {"ip": "1.2.3.4", "bps": 2_000_000, "time": "2026-01-01 12:00:00"}
        ],
    }
    respx.get(f"{_BASE}/api/ddos/list").mock(return_value=Response(200, json=payload))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_ddos_list(["1.2.3.4"])
    assert result["status"] is True
    assert len(result["data"]) == 1
    await adapter.aclose()


@respx.mock
async def test_get_ddos_list_with_time_window(test_settings):
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return Response(200, json={"status": True, "data": []})

    respx.get(f"{_BASE}/api/ddos/list").mock(side_effect=handler)
    adapter = _make_adapter(test_settings)
    await adapter.get_ddos_list(
        ["1.2.3.4"],
        time_start="2026-01-01 00:00:00",
        time_end="2026-01-01 01:00:00",
    )
    assert captured["params"]["time_start"] == "2026-01-01 00:00:00"
    assert captured["params"]["time_end"] == "2026-01-01 01:00:00"
    await adapter.aclose()


@respx.mock
async def test_get_ddos_list_sort_plus_time(test_settings):
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return Response(200, json={"status": True, "data": []})

    respx.get(f"{_BASE}/api/ddos/list").mock(side_effect=handler)
    adapter = _make_adapter(test_settings)
    await adapter.get_ddos_list(["1.2.3.4"], sort="+time")
    assert captured["params"]["sort"] == "+time"
    await adapter.aclose()


@respx.mock
async def test_get_ddos_list_sort_minus_time(test_settings):
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return Response(200, json={"status": True, "data": []})

    respx.get(f"{_BASE}/api/ddos/list").mock(side_effect=handler)
    adapter = _make_adapter(test_settings)
    await adapter.get_ddos_list(["1.2.3.4"], sort="-time")
    assert captured["params"]["sort"] == "-time"
    await adapter.aclose()


async def test_get_ddos_list_invalid_sort_returns_early(test_settings):
    """Invalid sort value must return error dict without making an HTTP call."""
    adapter = _make_adapter(test_settings)
    result = await adapter.get_ddos_list(["1.2.3.4"], sort="bad")
    assert result["status"] is False
    assert result["data"] == []
    await adapter.aclose()


@respx.mock
async def test_get_ddos_list_timeout(test_settings):
    respx.get(f"{_BASE}/api/ddos/list").mock(side_effect=TimeoutException("timeout"))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_ddos_list(["1.2.3.4"])
    assert result["status"] is False
    assert result.get("info") == "timeout"
    await adapter.aclose()


@respx.mock
async def test_get_ddos_list_non_200(test_settings):
    respx.get(f"{_BASE}/api/ddos/list").mock(return_value=Response(503))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_ddos_list(["1.2.3.4"])
    assert result["status"] is False
    assert result.get("info") == "request failed"
    await adapter.aclose()
