"""GF (高防) collector — domain-to-node resolution and WAF rule query.

Migrated from KKShieldHelper-main/logic/collectors/gf_collector.py with:
- sync requests → async httpx
- os.getenv() → injected Settings
- Three GF endpoints: YXD (game shield), CDN (GF IP), DDOS
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from runtime.config.settings import Settings, get_settings
from security.fake.client import build_async_client

_MAX_RULES_DISPLAY = 10


@dataclass
class GFNode:
    ip: str
    node_type: Literal["node", "product", "node_product"] | None = None
    source: str = "GF"


@dataclass
class _Endpoint:
    base_url: str
    token: str


class GFCollector:
    """Async GF-product collector.

    Resolves domain names to GF node IPs across three GF product lines
    (YXD / CDN / DDOS) and fetches WAF protection-rule summaries.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._timeout = s.gf_request_timeout
        self._endpoints: list[_Endpoint] = [
            _Endpoint(s.gf_yxd_api_url.rstrip("/"), s.gf_yxd_api_xtoken),
            _Endpoint(s.gf_cdn_api_url.rstrip("/"), s.gf_cdn_api_xtoken),
            _Endpoint(s.gf_ddos_api_url.rstrip("/"), s.gf_ddos_api_xtoken),
        ]
        self._client = build_async_client(s, verify=False, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query_nodes_by_domain(
        self, domain: str, port: int | str | None = None
    ) -> list[GFNode]:
        """Resolve a domain to GF node IPs across all three GF product lines.

        Returns on the first product line that owns the domain.
        Tries wildcard (``*.sub.domain``) as a fallback for plain domains.
        """
        port = self._normalise_port(port)

        for ep in self._endpoints:
            nodes: list[GFNode] = []
            found = await self._fetch_nodes(ep, domain, port, nodes)
            if found:
                return nodes
            # Try wildcard fallback for non-wildcard domains without explicit port
            if "*" not in domain and "." in domain and port is None:
                wildcard = self._to_wildcard(domain)
                found = await self._fetch_nodes(ep, wildcard, port, nodes)
                if found:
                    return nodes

        return []

    async def query_domain_protection_policy(
        self, domain: str, port: int | str | None = None
    ) -> dict:
        """Return a formatted summary of the WAF rules configured for *domain*.

        Auto-detects which GF product line owns the domain, then fetches rules.
        """
        port = self._normalise_port(port)
        ep = await self._detect_project(domain, port)
        if ep is None:
            return {"summary": f"Domain {domain} not found in any GF product", "project": "UNKNOWN"}

        project_label = self._endpoint_label(ep)
        raw = await self._query_waf_rules(ep, domain)
        summary = self._format_rules_summary(raw)
        return {"summary": summary, "project": project_label}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_port(port: int | str | None) -> int | str | None:
        if port and int(port) in (80, 443):
            return None
        return port

    @staticmethod
    def _to_wildcard(domain: str) -> str:
        parts = domain.split(".")
        if len(parts) < 3:
            return f"*.{domain}"
        return "." .join(["*"] + parts[1:])

    def _endpoint_label(self, ep: _Endpoint) -> str:
        for label, stored in zip(
            ("YXD", "GFIP", "DDOS"), self._endpoints
        ):
            if stored is ep:
                return label
        return "UNKNOWN"

    async def _fetch_nodes(
        self,
        ep: _Endpoint,
        domain: str,
        port: int | str | None,
        nodes: list[GFNode],
    ) -> bool:
        url = f"{ep.base_url}/api/p_domainRule/getNodeIpList"
        headers = {"x-token": ep.token} if ep.token else {}
        try:
            resp = await self._client.get(
                url,
                params={"domains": domain, "port": port},
                headers=headers,
            )
            resp.raise_for_status()
            items = (resp.json() or {}).get("data") or []
        except Exception:
            return False

        for item in items:
            node_ip = item.get("node_ip")
            if node_ip and node_ip not in {n.ip for n in nodes}:
                nodes.append(GFNode(ip=node_ip, node_type="node_product"))
            for ip in item.get("ip_list", []):
                if ip != node_ip and ip not in {n.ip for n in nodes}:
                    nodes.append(GFNode(ip=ip, node_type="product"))

        return len(items) > 0

    async def _detect_project(
        self, domain: str, port: int | str | None
    ) -> _Endpoint | None:
        """Return the first endpoint that owns the domain (with wildcard fallback)."""
        for ep in self._endpoints:
            nodes: list[GFNode] = []
            if await self._fetch_nodes(ep, domain, port, nodes):
                return ep
            if "*" not in domain and "." in domain and port is None:
                wildcard = self._to_wildcard(domain)
                if await self._fetch_nodes(ep, wildcard, port, nodes):
                    return ep
        return None

    async def _query_waf_rules(self, ep: _Endpoint, domain: str) -> dict:
        url = f"{ep.base_url}/api/p_domainRule/getDomainWaf"
        headers = {"X-Token": ep.token}
        try:
            resp = await self._client.get(url, params={"domains": domain}, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"code": 0, "msg": str(exc), "data": None}

    @staticmethod
    def _format_rules_summary(response: dict) -> str:
        """Convert raw WAF rule API response to a compact text summary for the LLM."""
        ok = response.get("code") == 1 or response.get("status") is True
        if not ok:
            return f"Query failed: {response.get('msg')}"

        data = response.get("data") or {}
        domain = data.get("domain", "unknown")
        rules = data.get("data") or []

        if not rules:
            return f"Domain {domain}: no protection rules configured"

        lines = [f"Domain {domain} protection rules:"]
        for idx, group in enumerate(rules, 1):
            rule_type = group.get("rule_type", "unknown")
            purpose = group.get("purpose", "")
            match = group.get("match", {})
            lines.append(f"\n[Rule group {idx}] {rule_type} — {purpose}")

            if rule_type in ("白名单", "黑名单", "代理访问"):
                ips = match.get("ip", [])
                urls = match.get("url", [])
                ip_sfx = "..." if len(ips) > _MAX_RULES_DISPLAY else ""
                url_sfx = "..." if len(urls) > _MAX_RULES_DISPLAY else ""
                lines.append(
                    f"  IPs: {len(ips)} ({', '.join(ips[:_MAX_RULES_DISPLAY])}{ip_sfx})"
                )
                lines.append(
                    f"  URLs: {len(urls)} ({', '.join(urls[:_MAX_RULES_DISPLAY])}{url_sfx})"
                )
                if match.get("action_desc"):
                    lines.append(f"  Action: {match['action_desc']}")

            elif rule_type == "访问频率":
                if isinstance(match, list):
                    lines.append(f"  Rules: {len(match)}")
                    for i, r in enumerate(match[:_MAX_RULES_DISPLAY], 1):
                        lines.append(
                            f"    {i}. [{r.get('name')}] "
                            f"{r.get('trigger_freq_desc')} "
                            f"({r.get('req_count')}req/{r.get('req_seconds')}s) "
                            f"→ {r.get('action_desc')} "
                            f"({'enabled' if r.get('status') == 1 else 'disabled'})"
                        )

            elif rule_type == "区域封禁":
                area = match.get("area", 0)
                _area_map = {1: "block domestic", 2: "block foreign", 0: "block all"}
                desc = _area_map.get(area, "unknown")
                status = "enabled" if match.get("status") == 1 else "disabled"
                lines.append(f"  Scope: {desc}, status: {status}")

            else:
                if isinstance(match, list):
                    lines.append(f"  Rules: {len(match)}")
                elif isinstance(match, dict):
                    lines.append(f"  Config keys: {len(match)}")

        return "\n".join(lines)

    async def aclose(self) -> None:
        await self._client.aclose()
