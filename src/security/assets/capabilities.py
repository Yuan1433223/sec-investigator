"""
Asset capability helpers.

Maps resolved asset types to the worker/tool capabilities they support.
This keeps routing semantics out of graph nodes and close to the domain model.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

NodeType = Literal["node", "product", "node_product"]

_CAPABILITY_MAP: dict[NodeType, tuple[str, ...]] = {
    "node": ("ping", "prom"),
    "product": ("cc", "ddos"),
    "node_product": ("ping", "prom", "cc", "ddos"),
}


def derive_capabilities(node_type: NodeType) -> list[str]:
    """Return the capability labels supported by a resolved asset type."""
    return list(_CAPABILITY_MAP[node_type])


def build_capability_scope(
    capability_items: Iterable[tuple[str, Iterable[str]]],
    *,
    domain_policy: bool = False,
) -> dict[str, list[str]]:
    """
    Build a graph-friendly capability index from the resolved asset scope.

    The returned keys describe worker-level routing intent rather than raw tool
    names so supervisor logic stays simple and deterministic.
    """
    machine_targets: list[str] = []
    security_targets: list[str] = []

    for asset_id, caps in capability_items:
        cap_set = set(caps)
        if "prom" in cap_set:
            machine_targets.append(asset_id)
        if "cc" in cap_set or "ddos" in cap_set:
            security_targets.append(asset_id)

    scope: dict[str, list[str]] = {
        "log": ["target"],
        "machine": machine_targets,
        "security": security_targets,
    }
    if domain_policy:
        scope["security"].append("domain_policy")
    return scope
