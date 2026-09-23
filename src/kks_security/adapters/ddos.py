from __future__ import annotations

import httpx

from kks_runtime.config.settings import Settings, get_settings


class DDoSAdapter:
    """Async client for the DDoS protection API.

    Wraps /api/ddos/list — time-range query for DDoS attack events.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._base_url = s.ddos_api_url.rstrip("/")
        self._key = s.ddos_api_key
        self._timeout = s.ddos_request_timeout
        self._client = httpx.AsyncClient(
            verify=False,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {s.ddos_token}",
                "Content-Type": "application/json",
            },
        )

    async def get_ddos_list(
        self,
        ips: list[str],
        time_start: str | None = None,
        time_end: str | None = None,
        sort: str | None = None,
    ) -> dict:
        """Return DDoS attack events for the given IPs within the time window.

        Args:
            ips:        IP addresses to query (comma-joined internally).
            time_start: Start of window, format ``YYYY-MM-DD HH:MM:SS``.
            time_end:   End of window, format ``YYYY-MM-DD HH:MM:SS``.
            sort:       ``+time`` (ascending) or ``-time`` (descending).
        """
        url = f"{self._base_url}/api/ddos/list"
        params: dict = {"ip": ",".join(ips), "key": self._key}
        if time_start:
            params["time_start"] = time_start
        if time_end:
            params["time_end"] = time_end
        if sort:
            if sort not in ("+time", "-time"):
                return {"status": False, "data": []}
            params["sort"] = sort
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {"status": False, "data": [], "info": "timeout"}
        except Exception:
            return {"status": False, "data": [], "info": "request failed"}

    async def aclose(self) -> None:
        await self._client.aclose()
