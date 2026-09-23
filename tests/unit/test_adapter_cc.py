"""
Unit tests for CCAdapter.

All HTTP calls are intercepted with respx — no real network.
"""
from __future__ import annotations

import respx
from httpx import Response, TimeoutException

from security.adapters.cc import CCAdapter, PointStatus

_BASE = "http://fake-cc"


def _make_adapter(test_settings) -> CCAdapter:
    return CCAdapter(settings=test_settings)


# ---------------------------------------------------------------------------
# get_host_point
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_host_point_happy_path(test_settings):
    payload = {
        "data": [
            {
                "address": "1.2.3.4",
                "input_pps": 3000,
                "input_submit_pps": 500,
                "output_pps": 100,
                "output_bps": 1000.0,
            }
        ]
    }
    respx.get(f"{_BASE}/api/host/host_point_list").mock(return_value=Response(200, json=payload))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_host_point(["1.2.3.4"])
    assert len(result) == 1
    assert isinstance(result[0], PointStatus)
    assert result[0].address == "1.2.3.4"
    assert result[0].input_pps == 3000
    await adapter.aclose()


@respx.mock
async def test_get_host_point_empty_data(test_settings):
    respx.get(f"{_BASE}/api/host/host_point_list").mock(
        return_value=Response(200, json={"data": []})
    )
    adapter = _make_adapter(test_settings)
    result = await adapter.get_host_point(["1.2.3.4"])
    assert result == []
    await adapter.aclose()


@respx.mock
async def test_get_host_point_non_200(test_settings):
    respx.get(f"{_BASE}/api/host/host_point_list").mock(return_value=Response(500))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_host_point(["1.2.3.4"])
    assert result == []
    await adapter.aclose()


@respx.mock
async def test_get_host_point_timeout_returns_empty(test_settings):
    respx.get(f"{_BASE}/api/host/host_point_list").mock(side_effect=TimeoutException("timeout"))
    adapter = _make_adapter(test_settings)
    result = await adapter.get_host_point(["1.2.3.4"])
    assert result == []
    await adapter.aclose()


@respx.mock
async def test_get_host_point_null_data_key(test_settings):
    respx.get(f"{_BASE}/api/host/host_point_list").mock(
        return_value=Response(200, json={"data": None})
    )
    adapter = _make_adapter(test_settings)
    result = await adapter.get_host_point(["1.2.3.4"])
    assert result == []
    await adapter.aclose()


# ---------------------------------------------------------------------------
# get_batch_host_status
# ---------------------------------------------------------------------------


async def test_get_batch_host_status_empty_ips(test_settings):
    """Empty IP list returns early without making any HTTP request."""
    adapter = _make_adapter(test_settings)
    result = await adapter.get_batch_host_status([])
    assert result["status"] is False
    assert result["data"] == []
    assert result["success_count"] == 0
    await adapter.aclose()


async def test_get_batch_host_status_whitespace_ips_skipped(test_settings):
    adapter = _make_adapter(test_settings)
    result = await adapter.get_batch_host_status(["  ", "", "   "])
    assert result["status"] is False
    await adapter.aclose()


@respx.mock
async def test_get_batch_host_status_happy_path(test_settings):
    payload = {"status": True, "data": [{"ip": "1.2.3.4", "shield_count": 5}]}
    respx.get(f"{_BASE}/api/host/batch_host_status").mock(
        return_value=Response(200, json=payload)
    )
    adapter = _make_adapter(test_settings)
    result = await adapter.get_batch_host_status(["1.2.3.4"])
    assert result["status"] is True
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    await adapter.aclose()


@respx.mock
async def test_get_batch_host_status_truncates_to_20(test_settings):
    # 25 IPs → only first 20 sent
    ips = [f"10.0.0.{i}" for i in range(25)]
    captured = {}

    def handler(request):
        captured["ips"] = request.url.params.get("ips", "")
        return Response(200, json={"status": True, "data": []})

    respx.get(f"{_BASE}/api/host/batch_host_status").mock(side_effect=handler)
    adapter = _make_adapter(test_settings)
    await adapter.get_batch_host_status(ips)
    sent_ips = captured["ips"].split(",")
    assert len(sent_ips) == 20
    await adapter.aclose()
