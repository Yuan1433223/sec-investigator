"""Helpers for selecting a primary asset from the resolved inspection scope."""

from __future__ import annotations

from collections.abc import Iterable

from kks_runtime.state.session import SessionState
from kks_security.schemas.node_machine import NodeMachine


def inspection_assets(state: SessionState) -> list[NodeMachine]:
    """Parse the raw inspection scope into typed NodeMachine objects."""
    return [
        NodeMachine.model_validate(item)
        for item in state.get("inspection_scope", [])
    ]


def active_asset(state: SessionState) -> NodeMachine | None:
    """Return the active asset slice injected by a Send fan-out, if present."""
    raw_asset = state.get("active_asset")
    if not raw_asset:
        return None
    return NodeMachine.model_validate(raw_asset)


def select_assets(
    state: SessionState,
    *,
    capability_scope_key: str,
    required_capabilities: Iterable[str],
) -> list[NodeMachine]:
    """Return all assets eligible for a worker capability group."""
    required = set(required_capabilities)
    assets = inspection_assets(state)
    assets_by_id = {asset.asset_id: asset for asset in assets}
    scope_ids = (state.get("capability_scope") or {}).get(capability_scope_key, [])

    selected: list[NodeMachine] = []
    seen: set[str] = set()
    for asset_id in scope_ids:
        asset = assets_by_id.get(asset_id)
        if asset and asset.asset_id not in seen and required.intersection(asset.capabilities):
            selected.append(asset)
            seen.add(asset.asset_id)

    for asset in assets:
        if asset.asset_id in seen:
            continue
        if required.intersection(asset.capabilities):
            selected.append(asset)
            seen.add(asset.asset_id)
    return selected


def select_primary_asset(
    state: SessionState,
    *,
    capability_scope_key: str,
    required_capabilities: Iterable[str],
) -> NodeMachine | None:
    """
    Select the first asset eligible for the current serial worker execution.

    This keeps current single-worker routing deterministic while preparing
    state for later Send-based fan-out.
    """
    scoped_asset = active_asset(state)
    if scoped_asset is not None:
        return scoped_asset

    required = set(required_capabilities)
    assets = inspection_assets(state)
    assets_by_id = {asset.asset_id: asset for asset in assets}
    scope_ids = (state.get("capability_scope") or {}).get(capability_scope_key, [])

    for asset_id in scope_ids:
        asset = assets_by_id.get(asset_id)
        if asset and required.intersection(asset.capabilities):
            return asset

    for asset in assets:
        if required.intersection(asset.capabilities):
            return asset
    return None


def build_asset_findings(
    asset: NodeMachine | None,
    *,
    finding_key: str,
    finding_value: dict,
) -> dict[str, dict[str, object]]:
    """Build the nested asset_findings payload expected by SessionState."""
    if asset is None:
        return {}
    return {
        asset.asset_id: {
            "asset": asset.model_dump(),
            finding_key: finding_value,
        }
    }
