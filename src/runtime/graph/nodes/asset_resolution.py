"""
Asset Resolution node.

Resolves a raw target (IP or domain) into typed NodeMachine assets consumed by
the runtime for capability-safe routing.
"""

from __future__ import annotations

import re

from runtime.state.session import SessionState
from security.assets.capabilities import build_capability_scope
from security.collectors.gf_collector import GFCollector, GFNode
from security.collectors.node_resolver import NodeResolver
from security.collectors.waf_collector import WAFCollector, WAFNode
from security.schemas.node_machine import NodeMachine

_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _is_ip(target: str) -> bool:
    return bool(_IPV4_RE.match(target.strip()))


def _machines_from_waf_nodes(
    nodes: list[WAFNode],
    *,
    origin_target: str,
    target_type: str,
) -> list[NodeMachine]:
    return [
        NodeMachine.build(
            ip=node.ip,
            node_type=node.node_type or "node_product",
            source="WAF",
            origin_target=origin_target,
            target_type=target_type,
        )
        for node in nodes
    ]


def _machines_from_gf_nodes(
    nodes: list[GFNode],
    *,
    origin_target: str,
    target_type: str,
) -> list[NodeMachine]:
    return [
        NodeMachine.build(
            ip=node.ip,
            node_type=node.node_type or "node_product",
            source="GF",
            origin_target=origin_target,
            target_type=target_type,
        )
        for node in nodes
    ]


def _machines_from_resolver_data(
    product_type: str,
    data: dict | list | None,
    *,
    origin_target: str,
    target_type: str,
) -> list[NodeMachine]:
    """Convert raw NodeResolver.resolve_ip() data to NodeMachine list."""
    if not data:
        return []
    source = "WAF" if product_type == "WAF" else "GF"
    items = data if isinstance(data, list) else [data]
    machines: list[NodeMachine] = []
    for item in items:
        node_ip = item.get("node_ip")
        ip_list = item.get("ip_list", [])
        if node_ip:
            machines.append(
                NodeMachine.build(
                    ip=node_ip,
                    node_type="node_product",
                    source=source,
                    origin_target=origin_target,
                    target_type=target_type,
                )
            )
        for ip in ip_list:
            if ip and ip != node_ip:
                machines.append(
                    NodeMachine.build(
                        ip=ip,
                        node_type="product",
                        source=source,
                        origin_target=origin_target,
                        target_type=target_type,
                    )
                )
    return machines


def _split_scope(machines: list[NodeMachine]) -> tuple[list[str], list[str]]:
    """Return (node_ips, product_ips) from the full inspection scope."""
    node_ips: list[str] = []
    product_ips: list[str] = []
    for machine in machines:
        if "prom" in machine.capabilities:
            node_ips.append(machine.ip)
        if "cc" in machine.capabilities or "ddos" in machine.capabilities:
            product_ips.append(machine.ip)
    return node_ips, product_ips


async def asset_resolution_node(state: SessionState) -> dict:
    """
    Resolve the raw target into typed NodeMachine assets.

    Always returns the full resolution bundle so later nodes can rely on a
    stable state shape from their first invocation onward.
    """
    target = state.get("target", "").strip()

    if _is_ip(target):
        target_type = "ip"
        machines = await _resolve_ip(target)
        resolution_reason = (
            "resolved_from_ip_lookup"
            if machines and machines[0].is_resolved
            else "unresolved_ip_fallback"
        )
    else:
        target_type = "domain"
        machines = await _resolve_domain(target)
        resolution_reason = "resolved_from_domain_lookup" if machines else "unresolved_domain"

    source_type = machines[0].source if machines else None
    node_ips, product_ips = _split_scope(machines)
    capability_scope = build_capability_scope(
        ((machine.asset_id, machine.capabilities) for machine in machines),
        domain_policy=(target_type == "domain"),
    )

    return {
        "target_type": target_type,
        "resolved_target": target,
        "source_type": source_type,
        "resolution_reason": resolution_reason,
        "node_ips": node_ips,
        "product_ips": product_ips,
        "capability_scope": capability_scope,
        "inspection_scope": [machine.model_dump() for machine in machines],
    }


async def _resolve_ip(ip: str) -> list[NodeMachine]:
    resolver = NodeResolver()
    try:
        ok, product_type, data = await resolver.resolve_ip(ip)
        if ok and data:
            return _machines_from_resolver_data(
                product_type,
                data,
                origin_target=ip,
                target_type="ip",
            )
        # Unresolved IP: treat as a bare infrastructure node.
        return [
            NodeMachine.build(
                ip=ip,
                node_type="node",
                source=None,
                origin_target=ip,
                target_type="ip",
                is_resolved=False,
                labels=["standalone"],
            )
        ]
    finally:
        await resolver.aclose()


async def _resolve_domain(domain: str) -> list[NodeMachine]:
    gf = GFCollector()
    try:
        gf_nodes = await gf.query_nodes_by_domain(domain)
        if gf_nodes:
            return _machines_from_gf_nodes(
                gf_nodes,
                origin_target=domain,
                target_type="domain",
            )
    finally:
        await gf.aclose()

    waf = WAFCollector()
    try:
        waf_nodes = await waf.query_nodes_by_domain(domain)
        return _machines_from_waf_nodes(
            waf_nodes,
            origin_target=domain,
            target_type="domain",
        )
    finally:
        await waf.aclose()
