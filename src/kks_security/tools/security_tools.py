"""LangChain tools for CC/DDoS security checks.

All tools use the adapter-injection pattern:
  _make_security_tools(cc_adapter, ddos_adapter) → list[BaseTool]

The module-level ``SECURITY_TOOLS`` default constructs real adapters from settings,
which are only evaluated at first import (not at module load — no import-time
singletons; the list is built lazily via _make_security_tools()).
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from kks_runtime.config.settings import get_settings
from kks_security.adapters.cc import CCAdapter, PointStatus
from kks_security.adapters.ddos import DDoSAdapter
from kks_security.collectors.gf_collector import GFCollector
from kks_security.collectors.node_resolver import NodeResolver
from kks_security.collectors.waf_collector import WAFCollector

# ---------------------------------------------------------------------------
# Attack detection helpers (code-level policy, not hidden in prompts)
# ---------------------------------------------------------------------------


def _is_cc_attack(point: PointStatus, settings=None) -> bool:
    """Return True when PPS data exceeds configured CC attack thresholds."""
    s = settings or get_settings()
    if point.input_pps is None or point.input_submit_pps is None:
        return False
    return (
        point.input_pps > s.cc_attack_pps_threshold
        and (point.input_pps - point.input_submit_pps) >= s.cc_attack_delta_threshold
    )


def _is_ddos_attack(event: dict[str, Any], settings=None) -> bool:
    """Return True when a DDoS event exceeds the configured traffic threshold.

    The API ``bps`` field is actually expressed in kbps (confirmed against donor code).
    The default threshold is 1_000_000 kbps == 1 Gbps.
    """
    s = settings or get_settings()
    bps_kbps = event.get("bps") or 0
    return bps_kbps >= s.ddos_attack_kbps_threshold


def _normalize_ddos_response(resp: Any) -> tuple[bool, list[dict[str, Any]]]:
    """Accept both raw list and wrapped dict responses from the DDoS adapter."""
    if isinstance(resp, list):
        return True, [dict(item) for item in resp]
    if isinstance(resp, dict):
        events = resp.get("data") or []
        if not isinstance(events, list):
            return bool(resp.get("status", False)), []
        return bool(resp.get("status", False)), [dict(item) for item in events]
    return False, []


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------


def _make_security_tools(
    cc_adapter: CCAdapter | None = None,
    ddos_adapter: DDoSAdapter | None = None,
    gf_collector: GFCollector | None = None,
    waf_collector: WAFCollector | None = None,
    node_resolver: NodeResolver | None = None,
):
    """Return list of security LangChain tools with injected adapters."""
    _cc = cc_adapter
    _ddos = ddos_adapter
    _gf = gf_collector
    _waf = waf_collector
    _nr = node_resolver

    def _get_cc() -> CCAdapter:
        nonlocal _cc
        if _cc is None:
            _cc = CCAdapter()
        return _cc

    def _get_ddos() -> DDoSAdapter:
        nonlocal _ddos
        if _ddos is None:
            _ddos = DDoSAdapter()
        return _ddos

    def _get_gf() -> GFCollector:
        nonlocal _gf
        if _gf is None:
            _gf = GFCollector()
        return _gf

    def _get_waf() -> WAFCollector:
        nonlocal _waf
        if _waf is None:
            _waf = WAFCollector()
        return _waf

    def _get_nr() -> NodeResolver:
        nonlocal _nr
        if _nr is None:
            _nr = NodeResolver()
        return _nr

    @tool
    async def check_cc_status(ips: list[str]) -> dict:
        """Check real-time CC attack status for a list of IPs.

        Returns per-IP PPS/bps data and whether each IP exceeds attack thresholds
        (input_pps > threshold AND filtered_delta >= delta_threshold).

        Args:
            ips: List of IP addresses to check.
        """
        adapter = _get_cc()
        points = await adapter.get_host_point(ips)
        if not points:
            return {"status": "no_data", "points": []}
        result = []
        for p in points:
            entry = p.model_dump()
            entry["is_under_attack"] = _is_cc_attack(p)
            result.append(entry)
        return {"status": "ok", "points": result}

    @tool
    async def check_ddos_status(
        ips: list[str],
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> dict:
        """Check DDoS attack events for a list of IPs within a time window.

        Returns raw events and flags which events exceed the 1 Gbps threshold
        (bps field is in kbps; threshold = 1,000,000 kbps).

        Args:
            ips:        IP addresses to query.
            time_start: Start of window, format ``YYYY-MM-DD HH:MM:SS``.
            time_end:   End of window, format ``YYYY-MM-DD HH:MM:SS``.
        """
        adapter = _get_ddos()
        resp = await adapter.get_ddos_list(ips, time_start=time_start, time_end=time_end)
        status, events = _normalize_ddos_response(resp)
        annotated = []
        for ev in events:
            ev["exceeds_threshold"] = _is_ddos_attack(ev)
            annotated.append(ev)
        return {"status": status, "events": annotated, "count": len(annotated)}

    @tool
    async def check_host_status(ips: list[str]) -> dict:
        """Check the shield/protection status for a list of IPs.

        Returns whether each host has active protection, is forbidden, and
        the count of currently blocked IPs.

        Args:
            ips: List of IP addresses (max 20).
        """
        adapter = _get_cc()
        return await adapter.get_batch_host_status(ips)

    @tool
    async def query_nodes_ip_by_ip(ip: str) -> dict:
        """Resolve an IP address to its product type (WAF or GF) and associated node IPs.

        Returns the product type that owns the IP and all related node/product IPs.

        Args:
            ip: IP address to resolve.
        """
        resolver = _get_nr()
        success, product_type, data = await resolver.resolve_ip(ip)
        return {"success": success, "product_type": product_type, "data": data}

    @tool
    async def query_nodes_ip_by_domain(
        source_type: str,
        domain: str,
        port: int | str | None = None,
    ) -> dict:
        """Resolve a domain name to its node IPs via WAF or GF product.

        Args:
            source_type: "WAF" or "GF" — which product to query.
            domain:      Domain name to resolve (e.g. "example.com").
            port:        Optional port number (80/443 are treated as no-port).
        """
        if source_type.upper() == "WAF":
            collector = _get_waf()
            nodes = await collector.query_nodes_by_domain(domain, port)
            node_list = [{"ip": n.ip, "node_type": n.node_type} for n in nodes]
            return {"source": "WAF", "nodes": node_list}
        else:
            collector = _get_gf()
            nodes = await collector.query_nodes_by_domain(domain, port)
            node_list = [{"ip": n.ip, "node_type": n.node_type} for n in nodes]
            return {"source": "GF", "nodes": node_list}

    @tool
    async def query_domain_protection_policy(
        domain: str,
        port: int | str | None = None,
    ) -> dict:
        """Fetch the WAF protection rules configured for a domain in GF product.

        Auto-detects which GF product line (YXD/GFIP/DDOS) owns the domain,
        then returns a formatted summary of all protection rules.

        Args:
            domain: Domain name to query.
            port:   Optional port number.
        """
        collector = _get_gf()
        return await collector.query_domain_protection_policy(domain, port)

    return [
        check_cc_status,
        check_ddos_status,
        check_host_status,
        query_nodes_ip_by_ip,
        query_nodes_ip_by_domain,
        query_domain_protection_policy,
    ]


# Module-level default tool list — constructed lazily on first access.
# Workers import SECURITY_TOOLS; tests use _make_security_tools() with mocks.
SECURITY_TOOLS = _make_security_tools()
