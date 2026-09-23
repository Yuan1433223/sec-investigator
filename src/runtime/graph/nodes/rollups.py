"""Aggregate asset-scoped findings back into top-level graph findings."""

from __future__ import annotations

from typing import Any

from runtime.state.session import SessionState

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _max_risk(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "low"
    return max(
        (entry.get("risk_level", "low") for entry in entries),
        key=lambda risk: _RISK_ORDER.get(risk, -1),
    )


def _collect_asset_entries(state: SessionState, *, finding_key: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for asset_id, payload in (state.get("asset_findings") or {}).items():
        if not isinstance(payload, dict):
            continue
        finding = payload.get(finding_key)
        if not isinstance(finding, dict):
            continue
        asset = payload.get("asset") if isinstance(payload.get("asset"), dict) else {}
        entries.append(
            {
                "asset_id": asset_id,
                "ip": asset.get("ip"),
                "type": asset.get("type"),
                "source": asset.get("source"),
                "risk_level": finding.get("risk_level", "low"),
                "summary": finding.get("summary", ""),
                "details": finding,
            }
        )
    return entries


def _build_rollup(entries: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    highest_risk = _max_risk(entries)
    non_low_assets = [
        entry["asset_id"]
        for entry in entries
        if _RISK_ORDER.get(entry["risk_level"], 0) > _RISK_ORDER["low"]
    ]
    return {
        "summary": f"{label} checks completed for {len(entries)} asset(s); highest risk={highest_risk}.",
        "risk_level": highest_risk,
        "asset_count": len(entries),
        "affected_assets": non_low_assets,
        "per_asset": entries,
    }


async def machine_rollup_node(state: SessionState) -> dict:
    """Aggregate machine asset findings after fan-out."""
    if state.get("findings", {}).get("machine"):
        return {}
    entries = _collect_asset_entries(state, finding_key="machine")
    if not entries:
        return {}
    return {"findings": {"machine": _build_rollup(entries, label="Infrastructure")}}


async def security_rollup_node(state: SessionState) -> dict:
    """Aggregate security asset findings after fan-out."""
    if state.get("findings", {}).get("security"):
        return {}
    entries = _collect_asset_entries(state, finding_key="security")
    if not entries:
        return {}
    rollup = _build_rollup(entries, label="Security")
    operational_issue_assets = [
        entry["asset_id"]
        for entry in entries
        if entry["details"].get("operational_issue", "none") != "none"
    ]
    rollup["operational_issue_assets"] = operational_issue_assets
    rollup["operational_issue_count"] = len(operational_issue_assets)
    return {"findings": {"security": rollup}}
