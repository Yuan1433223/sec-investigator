"""Dispatch nodes for asset-scoped worker fan-out."""

from __future__ import annotations

from langgraph.config import get_stream_writer
from langgraph.types import Send

from runtime.events.protocol import StatusEvent
from runtime.graph.nodes._asset_scope import select_assets
from runtime.state.session import SessionState
from security.schemas.node_machine import NodeMachine


def _worker_task(task: str, asset: NodeMachine) -> str:
    return f"{task}\nFocus on asset {asset.ip} ({asset.type}, {asset.source or 'UNRESOLVED'})."


def _worker_send_state(state: SessionState, *, asset: NodeMachine | None = None) -> dict:
    send_state = {
        "target": state.get("target", ""),
        "session_id": state.get("session_id", ""),
        "agent_task": state.get("agent_task", ""),
    }
    if asset is not None:
        send_state["active_asset"] = asset.model_dump()
        send_state["agent_task"] = _worker_task(send_state["agent_task"], asset)
    return send_state


async def dispatch_machine_checks_node(state: SessionState) -> dict:
    """Status-only dispatch node for machine asset fan-out."""
    write = get_stream_writer()
    assets = select_assets(
        state,
        capability_scope_key="machine",
        required_capabilities=("prom",),
    )
    write(
        StatusEvent(
            node="dispatch_machine_checks",
            message=f"Dispatching infrastructure checks to {len(assets) or 1} target slice(s)...",
        )
    )
    return {}


def route_machine_checks(state: SessionState) -> list[Send] | str:
    """Fan out machine checks per resolved asset, or fall back to one direct run."""
    assets = select_assets(
        state,
        capability_scope_key="machine",
        required_capabilities=("prom",),
    )
    if not assets:
        return [Send("machine_check", _worker_send_state(state))]
    return [
        Send("machine_check", _worker_send_state(state, asset=asset))
        for asset in assets
    ]


async def dispatch_security_checks_node(state: SessionState) -> dict:
    """Status-only dispatch node for security asset fan-out."""
    write = get_stream_writer()
    assets = select_assets(
        state,
        capability_scope_key="security",
        required_capabilities=("cc", "ddos"),
    )
    scope = (state.get("capability_scope") or {}).get("security", [])
    target_slices = len(assets) or (1 if scope else 0)
    write(
        StatusEvent(
            node="dispatch_security_checks",
            message=f"Dispatching security checks to {target_slices} target slice(s)...",
        )
    )
    return {}


def route_security_checks(state: SessionState) -> list[Send] | str:
    """
    Fan out security checks per asset.

    Domain-policy-only investigations still get one target-scoped security_guard
    run so the graph does not stall waiting for a non-existent asset rollup.
    """
    assets = select_assets(
        state,
        capability_scope_key="security",
        required_capabilities=("cc", "ddos"),
    )
    if not assets:
        return [Send("security_guard", _worker_send_state(state))]
    return [
        Send("security_guard", _worker_send_state(state, asset=asset))
        for asset in assets
    ]
