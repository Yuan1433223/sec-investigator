"""
Security Guard worker node.

Dispatches a ReAct agent with CC/DDoS security tools to assess protection
status for a target IP or domain. Returns structured SecurityFindings in `findings`.

Changes vs prior version:
- tools are wrapped with make_traced_tools() → emits ToolCallEvent/ToolResultEvent
- agent.ainvoke receives recursion_limit = max_tool_calls * 2 + 1 (enforces budget)
- Attack thresholds enforced in code (Settings), not in the prompt
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langgraph.prebuilt import create_react_agent

from runtime.events.protocol import StatusEvent
from runtime.graph.nodes._asset_scope import (
    active_asset,
    build_asset_findings,
    select_primary_asset,
)
from runtime.graph.nodes._tool_tracing import make_traced_tools
from runtime.llm.profiles import ModelProfile, build_model
from runtime.state.session import SessionState
from security.playbooks.catalog import PlaybookKind, get_playbook
from security.policies.evidence import default_policy
from security.schemas.findings import SecurityFindings
from security.tools.public_tools import check_connection_status, current_time
from security.tools.security_tools import SECURITY_TOOLS

_PLAYBOOK = get_playbook(PlaybookKind.ATTACK_ANALYSIS)
_RECURSION_LIMIT = _PLAYBOOK.max_tool_calls * 2 + 1

# Security tools + network reachability + time anchor.
# check_connection_status: ping CDN nodes / origin IPs to confirm connectivity.
# current_time: used to anchor relative time windows for CC/DDoS queries.
_SECURITY_TOOLS = SECURITY_TOOLS + [check_connection_status, current_time]


def _annotate_operational_issue(findings: dict) -> None:
    """Mark coverage or integration problems separately from attack severity."""
    text = " ".join(
        str(findings.get(key, ""))
        for key in ("summary", "analysis_text", "cc_status", "ddos_status", "protection_status")
    ).lower()

    if any(
        keyword in text
        for keyword in (
            "key值不对",
            "misconfiguration",
            "misconfigured",
            "request failed",
            "host check failed",
            "config",
        )
    ):
        findings["operational_issue"] = "integration_or_config_error"
        findings["operational_issue_detail"] = (
            "Security integrations returned configuration or connectivity errors."
        )
        return

    if (
        findings.get("protection_status") in {"incomplete", "degraded"}
        or findings.get("cc_status") in {"no_data", "not_applicable"}
        or findings.get("ddos_status") in {"no_data", "not_applicable"}
    ):
        findings["operational_issue"] = "coverage_gap"
        findings["operational_issue_detail"] = (
            "Security coverage is incomplete or telemetry is missing for this target."
        )
        return

    findings["operational_issue"] = "none"
    findings["operational_issue_detail"] = ""


async def security_guard_node(state: SessionState) -> dict:
    """
    Worker node: check CC/DDoS protection status via security APIs.

    Uses TOOL_REASONER profile for multi-step tool calling.
    Tool budget: max_tool_calls from ATTACK_ANALYSIS playbook, enforced via recursion_limit.
    Includes check_connection_status for pinging CDN nodes and origin servers.
    """
    write = get_stream_writer()
    write(StatusEvent(node="security_guard", message="Checking CC/DDoS protection status..."))

    task = (
        state.get("agent_task")
        or f"Check security protection for {state.get('target', 'unknown')}"
    )

    llm = build_model(_PLAYBOOK.model_profile)
    traced_tools = make_traced_tools(_SECURITY_TOOLS, "security_guard")
    agent = create_react_agent(model=llm, tools=traced_tools, prompt=_PLAYBOOK.system_prompt)
    resp = await agent.ainvoke(
        {"messages": [HumanMessage(content=task)]},
        config={"recursion_limit": _RECURSION_LIMIT},
    )
    analysis_text: str = resp["messages"][-1].content

    extractor = build_model(ModelProfile.STRUCTURED_EXTRACTOR)
    findings: SecurityFindings = await extractor.with_structured_output(
        SecurityFindings
    ).ainvoke(
        "Extract structured security findings from this protection status"
        f" analysis:\n\n{analysis_text}"
    )

    # Deterministic risk_level override — code-level policy, not LLM judgement.
    findings_dict = findings.model_dump()
    findings_dict["risk_level"] = default_policy().classify_security(findings_dict)
    _annotate_operational_issue(findings_dict)
    scoped_asset = active_asset(state)
    primary_asset = scoped_asset or select_primary_asset(
        state,
        capability_scope_key="security",
        required_capabilities=("cc", "ddos"),
    )

    write(StatusEvent(node="security_guard", message="Security check complete"))

    result = {
        "messages": resp["messages"],
        "asset_findings": build_asset_findings(
            primary_asset,
            finding_key="security",
            finding_value=findings_dict,
        ),
    }
    if scoped_asset is None:
        result["findings"] = {"security": findings_dict}
    return result
