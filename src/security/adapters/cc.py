from __future__ import annotations

import httpx
from pydantic import BaseModel

from runtime.config.settings import Settings, get_settings


class PointStatus(BaseModel):
    address: str | None = None
    input_bps: float | None = None
    input_pps: int | None = None
    input_submit_bps: float | None = None
    input_submit_pps: int | None = None
    output_bps: float | None = None
    output_pps: int | None = None
    output_submit_bps: float | None = None
    output_submit_pps: int | None = None
    fw_type: int | None = None
    fw_id: int | None = None


class CCAdapter:
    """Async client for the CC protection API.

    Wraps two endpoints:
    - /api/host/host_point_list   — real-time PPS/bps per host
    - /api/host/batch_host_status — shield counts / forbidden flags per host
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._base_url = s.cc_api_url.rstrip("/")
        self._key = s.cc_api_key
        self._timeout = s.cc_request_timeout
        self._client = httpx.AsyncClient(verify=False, timeout=self._timeout)

    async def get_host_point(self, ips: list[str]) -> list[PointStatus]:
        """Return real-time PPS/bps data for the given IPs."""
        url = f"{self._base_url}/api/host/host_point_list"
        params = {"key": self._key, "ips": ",".join(ips)}
        try:
            resp = await self._client.get(url, params=params)
        except (httpx.TimeoutException, httpx.ConnectError):
            return []
        if resp.status_code != 200:
            return []
        data = (resp.json() or {}).get("data") or []
        return [PointStatus(**item) for item in data if item]

    async def get_batch_host_status(self, ips: list[str]) -> dict:
        """Return shield counts and forbidden flags for the given IPs (max 20)."""
        valid = [ip.strip() for ip in ips if ip and ip.strip()][:20]
        if not valid:
            return {"status": False, "data": [], "success_count": 0, "failed_count": 0}
        url = f"{self._base_url}/api/host/batch_host_status"
        params = {"key": self._key, "ips": ",".join(valid)}
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            result = resp.json()
            data = result.get("data") or []
            result["success_count"] = len([x for x in data if x])
            result["failed_count"] = len(valid) - result["success_count"]
            return result
        except (httpx.HTTPError, httpx.TimeoutException):
            return {"status": False, "data": [], "success_count": 0, "failed_count": len(valid)}

    async def aclose(self) -> None:
        await self._client.aclose()
