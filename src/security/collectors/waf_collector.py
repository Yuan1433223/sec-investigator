"""WAF collector — domain-to-node resolution.

Migrated from KKShieldHelper-main/logic/collectors/waf_collector.py with:
- sync requests → async httpx
- os.getenv() → injected Settings
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import httpx

from runtime.config.settings import Settings, get_settings
from security.fake.client import build_async_client


@dataclass
class WAFNode:
    ip: str
    node_type: Literal["node", "product", "node_product"] | None = None
    source: str = "WAF"


class WAFCollector:
    """Async WAF-product collector.

    Resolves domain names to WAF node IPs via the security-assistant API.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._base_url = s.waf_api_url.rstrip("/")
        self._token = s.waf_api_token
        self._timeout = s.waf_request_timeout
        self._client = build_async_client(s, verify=False, timeout=self._timeout)

    async def query_nodes_by_domain(
        self, domain: str, port: str | int | None = None
    ) -> list[WAFNode]:
        """Resolve a domain to WAF node IPs."""
        url = f"{self._base_url}/api/security_assistant/get_node_ips"
        headers = {"X-Access-Token": self._token}
        params = {"domain": domain, "port": port, "time_stamp": int(time.time())}
        try:
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            items = (resp.json() or {}).get("data") or []
        except Exception:
            return []

        nodes: list[WAFNode] = []
        for item in items:
            node_ip = item.get("node_ip")
            if node_ip:
                nodes.append(WAFNode(ip=node_ip, node_type="node_product"))
            for ip in item.get("ip_list", []):
                if ip != node_ip:
                    nodes.append(WAFNode(ip=ip, node_type="product"))
        return nodes

    async def aclose(self) -> None:
        await self._client.aclose()
