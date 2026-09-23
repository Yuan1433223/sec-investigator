"""
Playbook data model.

A Playbook is a pure-data record that bundles everything a graph node needs
to execute a specific investigation mode:

- the system prompt guiding the LLM agent
- the set of findings keys the node is expected to populate
- the model profile appropriate for the task
- a guard rail on how many tool calls the node may make

No runtime logic lives here. Nodes receive a Playbook and interpret its fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from runtime.llm.profiles import ModelProfile


class PlaybookKind(StrEnum):
    """Canonical investigation mode identifiers.

    These replace legacy names (Guard, ReAct, Plan) and map one-to-one with
    the specialised worker nodes in the investigation graph.
    """

    ATTACK_ANALYSIS = "attack_analysis"
    """CC/DDoS protection status collection — maps to security_guard node."""

    INFRA_DIAGNOSIS = "infra_diagnosis"
    """Prometheus infrastructure health check — maps to machine_check node."""

    ALERT_TRIAGE = "alert_triage"
    """Multi-dimensional triage across logs, machine, and security findings
    — guides the supervisor routing decisions."""

    REPORT_GENERATION = "report_generation"
    """Final report synthesis from all collected findings — maps to reporter node."""

    LOG_ANALYSIS = "log_analysis"
    """ES access-log data collection — maps to log_detective node."""


@dataclass(frozen=True)
class Playbook:
    """Immutable description of a single investigation mode."""

    kind: PlaybookKind
    system_prompt: str
    """LLM system prompt for the node running this playbook."""

    required_findings: list[str] = field(default_factory=list)
    """Finding keys this playbook is expected to produce in SessionState.findings."""

    model_profile: ModelProfile = ModelProfile.TOOL_REASONER
    """Model profile the node should use for its primary LLM call."""

    max_tool_calls: int = 10
    """Maximum number of tool calls allowed in one invocation (guard rail)."""
