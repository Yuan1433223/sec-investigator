"""Node-resolution adapter — maps an IP or domain to its product type (WAF / GF)
and returns all associated node/product IPs.

Migrated from KKShieldHelper-main/utils/waf_tools.py with:
- module-level httpx singleton → per-instance async client
- os.getenv() → injected Settings
- merged WAF + GF (YXD/CDN/DDOS) probe logic into one class
"""
from __future__ import annotations

from typing import Literal

import httpx

from runtime.config.settings import Settings, get_settings
from security.fake.client import build_async_client

ProductType = Literal["WAF", "GF"]


class NodeResolver:
    """Async adapter that resolves an IP to its product type and related IPs.

    Probes WAF first, then GF (YXD → CDN → DDOS).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._waf_base = s.waf_api_url.rstrip("/")
        self._waf_token = s.waf_api_token
        self._gf_endpoints = [
            (s.gf_yxd_api_url.rstrip("/"), s.gf_yxd_api_xtoken),
            (s.gf_cdn_api_url.rstrip("/"), s.gf_cdn_api_xtoken),
            (s.gf_ddos_api_url.rstrip("/"), s.gf_ddos_api_xtoken),
        ]
        timeout = min(s.waf_request_timeout, s.gf_request_timeout)
        self._client = build_async_client(s, verify=False, timeout=timeout)

    async def resolve_ip(
        self, ip: str
    ) -> tuple[bool, ProductType, dict | None]:
        """Return (success, product_type, node_data) for a given IP.

        node_data shape (from WAF)::

            {"node_ip": "...", "ip_list": [...]}

        node_data shape (from GF)::

            [{"node_ip": "...", "ip_list": [...]}]

        Returns ``(False, "GF", None)`` when no product owns the IP.
        """
        # 1. Try WAF
        ok, data = await self._query(
            f"{self._waf_base}/api/security_assistant/get_node_ip_by_ip",
            {"X-Access-Token": self._waf_token},
            {"ip": ip},
            success_code=1,
        )
        if ok and data:
            return True, "WAF", data

        # 2. Try GF endpoints
        for base, token in self._gf_endpoints:
            ok, data = await self._query(
                f"{base}/api/p_node/getNodeIpList",
                {"x-token": token},
                {"ip": ip},
                success_code=1,
            )
            if ok and data:
                return True, "GF", data

        return False, "GF", None

    async def _query(
        self,
        url: str,
        headers: dict,
        params: dict,
        success_code: int = 200,
    ) -> tuple[bool, dict | list | None]:
        try:
            resp = await self._client.get(url, params=params, headers=headers)
        except Exception:
            return False, None
        if resp.status_code != 200:
            return False, None
        body = resp.json() or {}
        if body.get("code") != success_code:
            return True, None
        return True, body.get("data")

    async def aclose(self) -> None:
        await self._client.aclose()
