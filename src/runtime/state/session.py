import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def _merge_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge: b values overwrite a. Used as findings reducer."""
    return {**a, **b}


def _merge_nested_dict(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge nested asset findings while preserving prior worker outputs."""
    merged = dict(a)
    for outer_key, inner_value in b.items():
        existing = merged.get(outer_key, {})
        if isinstance(existing, dict) and isinstance(inner_value, dict):
            merged[outer_key] = {**existing, **inner_value}
        else:
            merged[outer_key] = inner_value
    return merged


class SessionState(TypedDict):
    """Full internal state for an investigation session."""

    messages: Annotated[list[AnyMessage], add_messages]
    findings: Annotated[dict[str, Any], _merge_dict]
    asset_findings: NotRequired[Annotated[dict[str, dict[str, Any]], _merge_nested_dict]]
    artifacts: Annotated[list[dict[str, Any]], operator.add]
    target: str
    session_id: str
    next_node: str
    agent_task: str
    status: Literal["running", "completed", "failed", "waiting_approval"]
    error: str | None

    # Asset resolution fields populated by asset_resolution_node.
    target_type: NotRequired[Literal["ip", "domain"]]
    resolved_target: NotRequired[str]
    source_type: NotRequired[Literal["WAF", "GF"] | None]
    resolution_reason: NotRequired[str | None]
    node_ips: NotRequired[list[str]]
    product_ips: NotRequired[list[str]]
    capability_scope: NotRequired[dict[str, list[str]]]
    inspection_scope: NotRequired[list[dict]]
    active_asset: NotRequired[dict[str, Any]]


class InvestigationInput(TypedDict):
    """External input: what callers provide when invoking the graph."""

    messages: list[AnyMessage]
    target: str
    session_id: str
    findings: NotRequired[dict[str, Any]]


class InvestigationOutput(TypedDict):
    """External output: what callers receive after the graph completes."""

    messages: list[AnyMessage]
    findings: dict[str, Any]
    asset_findings: NotRequired[dict[str, dict[str, Any]]]
    artifacts: list[dict[str, Any]]
    status: str
