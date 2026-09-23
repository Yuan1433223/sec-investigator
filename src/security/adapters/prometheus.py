"""
Async Prometheus adapter.

Wraps httpx.AsyncClient against the Prometheus HTTP API v1.
Supports instant queries (/api/v1/query) and range queries (/api/v1/query_range).

All metric-level logic lives in prom_tools.py — this adapter is purely I/O.

Migrated from KKShieldHelper-main/tools/prome_check.py with:
- Removed os.getenv singleton — settings injected at construction
- Removed hardcoded BASE_URL constant
- Separated pure stat computation (_peak_value) from I/O
- Step/interval calculation kept as a static helper (_calc_step)
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from runtime.config.settings import Settings, get_settings
from security.fake.client import build_async_client


def _calc_step(start_ts: int, end_ts: int) -> int:
    """
    Return a step (seconds) that keeps result points ≤ 60 for any duration.
    Minimum step is 60 s.
    """
    duration = max(60, end_ts - start_ts)
    if duration <= 300:
        return 60
    if duration <= 86_400:
        return max(60, duration // 60)
    return max(60, duration // 100)


def _peak_value(result_list: list[dict[str, Any]]) -> float | None:
    """Extract the highest numeric value across all time-series results."""
    if not result_list:
        return None
    first = result_list[0]
    pairs = first.get("values") or ([first["value"]] if "value" in first else [])
    nums = []
    for pair in pairs:
        try:
            nums.append(float(pair[1]))
        except (IndexError, TypeError, ValueError):
            pass
    return max(nums) if nums else None


class PrometheusAdapter:
    """
    Async Prometheus HTTP API client.

    Do NOT instantiate at module level — inject via tool factory.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._base = s.prometheus_url.rstrip("/")
        self._timeout = s.prometheus_request_timeout
        self._node_port = s.prometheus_node_port
        self._client = build_async_client(s, verify=False, timeout=self._timeout)

    def instance(self, ip: str) -> str:
        """Normalise bare IP to IP:port expected by node_exporter."""
        return ip if ":" in ip else f"{ip}:{self._node_port}"

    async def _query(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        resp = await self._client.get(f"{self._base}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "success":
            raise RuntimeError(f"Prometheus error: {body.get('error')}")
        return body["data"]["result"]

    async def instant(self, promql: str) -> list[dict[str, Any]]:
        """Instant query — returns current value(s)."""
        return await self._query("/api/v1/query", {"query": promql})

    async def range_query(
        self,
        promql: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Range query — returns time-series values."""
        now = int(time.time())
        end = end_ts if end_ts is not None else now
        start = start_ts if start_ts is not None else end - 300
        step = _calc_step(start, end)
        return await self._query(
            "/api/v1/query_range",
            {"query": promql, "start": start, "end": end, "step": step},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> PrometheusAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
