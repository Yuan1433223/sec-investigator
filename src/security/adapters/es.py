"""
Async Elasticsearch adapter.

Uses httpx directly against the ES REST API — avoids elasticsearch-py
version-header negotiation issues (client 9.x sends compatible-with=9
but our server is ES 7.x which only accepts 7 or 8).

All callers go through `ESAdapter.execute_dsl()` — they never import
httpx or elasticsearch directly.

Index routing:
  source="GF"  → es_gf_index (高防 logs, time field = "time")
  source="WAF" → es_waf_index (WAF logs, time field = "create_date")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx

from runtime.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

Source = Literal["GF", "WAF"]

# Which ES time field to use for each source
TIME_FIELD: dict[Source, str] = {
    "GF": "time",
    "WAF": "create_date",
}


class ESAdapter:
    """
    Async adapter around the ES REST API (via httpx).

    Do NOT instantiate at module level — create per-request or inject via
    the tool factory so there's no import-time singleton (hard rule 4).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._base_url = s.es_url.rstrip("/")
        self._auth = (s.es_username, s.es_password) if s.es_username else None
        self._timeout = s.es_request_timeout
        self._gf_index = s.es_gf_index
        self._waf_index = s.es_waf_index
        self._client = httpx.AsyncClient(
            verify=False,           # internal ES uses self-signed cert
            timeout=self._timeout,
        )

    def _index_for(self, source: Source) -> str:
        return self._gf_index if source == "GF" else self._waf_index

    async def execute_dsl(
        self,
        dsl: dict[str, Any],
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Execute an ES DSL query and return the raw response dict."""
        index = self._index_for(source)
        url = f"{self._base_url}/{index}/_search"
        response = await self._client.post(
            url,
            json=dsl,
            auth=self._auth,
        )
        if response.status_code >= 400:
            logger.error(
                "ES %s %s → %d\nDSL: %s\nBody: %s",
                "POST", url, response.status_code,
                json.dumps(dsl, ensure_ascii=False)[:500],
                response.text[:300],
            )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ESAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
