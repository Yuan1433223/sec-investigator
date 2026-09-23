"""
Supervisor node.

Routes deterministically based on missing findings and the resolved asset
capability scope. The LLM only writes the contextual task instruction.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from runtime.events.protocol import ApprovalRequestEvent
from runtime.graph.nodes.asset_resolution import _is_ip as _is_ip
from runtime.llm.profiles import build_model
from runtime.state.session import SessionState
from security.playbooks.catalog import PlaybookKind, get_playbook
from security.policies.evidence import default_policy

_PLAYBOOK = get_playbook(PlaybookKind.ALERT_TRIAGE)

_AVAILABLE_WORKERS = Literal["log_detective", "machine_check", "security_guard", "reporter"]

_WORKER_FINDINGS: dict[str, frozenset[str]] = {
    "log_detective": frozenset(get_playbook(PlaybookKind.LOG_ANALYSIS).required_findings),
    "machine_check": frozenset(get_playbook(PlaybookKind.INFRA_DIAGNOSIS).required_findings),
    "security_guard": frozenset(get_playbook(PlaybookKind.ATTACK_ANALYSIS).required_findings),
}

_DISPATCH_ORDER: list[str] = ["log_detective", "machine_check", "security_guard"]


class AgentTaskDecision(BaseModel):
    """LLM output: contextual task instruction for the chosen worker node."""

    agent_task: str = Field(
        description=(
            "Specific, one-sentence task instruction for the worker node. "
            "Include the target name and what aspect to focus on."
        )
    )


def _eligible_workers(capability_scope: dict[str, list[str]] | None) -> frozenset[str]:
    """
    Map resolved asset capabilities to the workers allowed in this session.

    log_detective always stays enabled because every investigation needs a log
    view of the target. machine_check and security_guard depend on asset scope.
    """
    scope = capability_scope or {}
    allowed = {"log_detective"}
    if scope.get("machine"):
        allowed.add("machine_check")
    if scope.get("security"):
        allowed.add("security_guard")
    return frozenset(allowed)


def _next_worker(findings: dict, eligible_workers: frozenset[str]) -> str:
    """
    Return the next worker to dispatch, or 'reporter' if all required findings
    are present for every eligible worker.
    """
    for worker in _DISPATCH_ORDER:
        if worker not in eligible_workers:
            continue
        required = _WORKER_FINDINGS[worker]
        if not required.issubset(findings.keys()):
            return worker
    return "reporter"


async def supervisor_node(state: SessionState) -> dict:
    """
    Orchestrator node: route to the next worker, approval gate, or reporter.
    """
    target = state.get("target", "unknown")
    findings = state.get("findings", {})
    messages = state.get("messages", [])
    target_type = state.get("target_type", "domain")
    eligible_workers = _eligible_workers(state.get("capability_scope"))

    next_node = _next_worker(findings, eligible_workers)

    if next_node == "reporter":
        policy = default_policy()
        if policy.requires_approval(findings):
            write = get_stream_writer()
            session_id = state.get("session_id", "")
            write(ApprovalRequestEvent(session_id=session_id, findings=findings))
            next_node = "approval_gate"

    task_prompt = (
        f"Target: {target} ({'IP address' if target_type == 'ip' else 'domain name'})\n"
        f"Resolved source: {state.get('source_type') or 'unknown'}\n"
        f"Eligible workers: {sorted(eligible_workers)}\n"
        f"Next worker: {next_node}\n"
        f"Findings already collected: {list(findings.keys()) or '(none)'}\n"
        f"Conversation context: {len(messages)} turns so far\n\n"
        f"Write a one-sentence task instruction for the {next_node} worker."
    )
    llm = build_model(_PLAYBOOK.model_profile)
    decision: AgentTaskDecision = await llm.with_structured_output(
        AgentTaskDecision
    ).ainvoke(
        [
            SystemMessage(content=_PLAYBOOK.system_prompt),
            HumanMessage(content=task_prompt),
        ]
    )

    return {
        "next_node": next_node,
        "agent_task": decision.agent_task,
        "status": "waiting_approval" if next_node == "approval_gate" else "running",
    }
