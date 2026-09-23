"""NodeMachine: typed representation of a single inspectable asset."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from security.assets.capabilities import derive_capabilities


class NodeMachine(BaseModel):
    """A single inspectable asset with explicit routing metadata."""

    asset_id: str
    ip: str
    type: Literal["node", "product", "node_product"]
    source: Literal["WAF", "GF"] | None = None
    origin_target: str | None = None
    target_type: Literal["ip", "domain"] | None = None
    is_resolved: bool = True
    capabilities: list[str]
    labels: list[str] = []

    @classmethod
    def build(
        cls,
        *,
        ip: str,
        node_type: Literal["node", "product", "node_product"],
        source: Literal["WAF", "GF"] | None,
        origin_target: str | None,
        target_type: Literal["ip", "domain"] | None,
        is_resolved: bool = True,
        labels: list[str] | None = None,
    ) -> "NodeMachine":
        """Construct a NodeMachine with consistent asset metadata."""
        source_label = source or "UNRESOLVED"
        asset_id = f"{source_label}:{node_type}:{ip}"
        return cls(
            asset_id=asset_id,
            ip=ip,
            type=node_type,
            source=source,
            origin_target=origin_target,
            target_type=target_type,
            is_resolved=is_resolved,
            capabilities=derive_capabilities(node_type),
            labels=labels or [],
        )
