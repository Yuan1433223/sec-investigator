from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from runtime.approvals.gate import approval_gate_node
from runtime.graph.nodes.asset_resolution import asset_resolution_node
from runtime.graph.nodes.fanout import (
    dispatch_machine_checks_node,
    dispatch_security_checks_node,
    route_machine_checks,
    route_security_checks,
)
from runtime.graph.nodes.log_detective import log_detective_node
from runtime.graph.nodes.machine_check import machine_check_node
from runtime.graph.nodes.reporter import reporter_node
from runtime.graph.nodes.rollups import machine_rollup_node, security_rollup_node
from runtime.graph.nodes.security_guard import security_guard_node
from runtime.graph.nodes.supervisor import supervisor_node
from runtime.state.session import (
    InvestigationInput,
    InvestigationOutput,
    SessionState,
)

_ROUTE_TARGETS = {"log_detective", "machine_check", "security_guard", "reporter", "approval_gate"}


def _route_supervisor(state: SessionState) -> str:
    """Read next_node from state; default to reporter as safe fallback."""
    next_node = state.get("next_node", "reporter")
    return next_node if next_node in _ROUTE_TARGETS else "reporter"


def _route_approval_gate(state: SessionState) -> str:
    """After the approval gate resumes, route to reporter on approve or END on reject."""
    if state.get("status") == "failed":
        return END
    return "reporter"


def build_investigation_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """
    Build and compile the investigation graph.

    Phase 5 shape:
        START → asset_resolution → supervisor ──→ log_detective ───┐
                                             ├──→ machine_check ───┤→ supervisor (loop)
                                             ├──→ security_guard ──┤
                                             ├──→ approval_gate ───┤→ reporter → END  (on approve)
                                             │                     └→ END              (on reject)
                                             └──→ reporter ─────────→ END

    asset_resolution resolves the raw target to typed NodeMachine objects,
    populating target_type / inspection_scope so the supervisor can apply
    capability constraints (e.g. skip machine_check for domain-only targets).
    approval_gate is inserted when EvidencePolicy.requires_approval() is True.
    """
    builder = StateGraph(
        SessionState,
        input_schema=InvestigationInput,
        output_schema=InvestigationOutput,
    )

    builder.add_node("asset_resolution", asset_resolution_node)
    builder.add_node(
        "supervisor",
        supervisor_node,
        retry_policy=RetryPolicy(max_attempts=3),
    )
    builder.add_node("log_detective", log_detective_node)
    builder.add_node("dispatch_machine_checks", dispatch_machine_checks_node)
    builder.add_node("machine_check", machine_check_node)
    builder.add_node("machine_rollup", machine_rollup_node)
    builder.add_node("dispatch_security_checks", dispatch_security_checks_node)
    builder.add_node("security_guard", security_guard_node)
    builder.add_node("security_rollup", security_rollup_node)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("reporter", reporter_node)

    builder.add_edge(START, "asset_resolution")
    builder.add_edge("asset_resolution", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {
            "log_detective": "log_detective",
            "machine_check": "dispatch_machine_checks",
            "security_guard": "dispatch_security_checks",
            "approval_gate": "approval_gate",
            "reporter": "reporter",
        },
    )
    # Workers return to supervisor for the next routing decision
    builder.add_edge("log_detective", "supervisor")
    builder.add_conditional_edges(
        "dispatch_machine_checks",
        route_machine_checks,
        {"machine_rollup": "machine_rollup"},
    )
    builder.add_edge("machine_check", "machine_rollup")
    builder.add_edge("machine_rollup", "supervisor")
    builder.add_conditional_edges(
        "dispatch_security_checks",
        route_security_checks,
        {"security_rollup": "security_rollup"},
    )
    builder.add_edge("security_guard", "security_rollup")
    builder.add_edge("security_rollup", "supervisor")

    # Approval gate: resume → reporter (approve) or END (reject)
    builder.add_conditional_edges(
        "approval_gate",
        _route_approval_gate,
        {"reporter": "reporter", END: END},
    )

    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=checkpointer)
