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
from runtime.graph.nodes._tool_tracing import ainvoke_react_agent, make_traced_tools
from runtime.llm.profiles import ModelProfile, build_model
from runtime.state.session import SessionState
from security.playbooks.catalog import PlaybookKind, get_playbook
from security.policies.evidence import default_policy
from security.policies.extraction import EvidenceCollector
from security.schemas.findings import SecurityFindings
from security.tools.public_tools import check_connection_status
from security.tools.security_tools import get_security_tools

_PLAYBOOK = get_playbook(PlaybookKind.ATTACK_ANALYSIS)
_RECURSION_LIMIT = _PLAYBOOK.max_tool_calls * 2 + 1


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
    collector = EvidenceCollector("security")
    security_tools = get_security_tools() + [check_connection_status]
    traced_tools = make_traced_tools(
        security_tools, "security_guard", evidence_sink=collector.observe
    )
    agent = create_react_agent(
        model=llm, tools=traced_tools, prompt=_PLAYBOOK.system_prompt,
        name="security_guard",
    )
    resp = await ainvoke_react_agent(
        agent,
        [HumanMessage(content=task)],
        recursion_limit=_RECURSION_LIMIT,
        node="security_guard",
        write=write,
        degrade_message="Security tool budget exhausted; returning partial finding",
    )
    scoped_asset = active_asset(state)
    primary_asset = scoped_asset or select_primary_asset(
        state,
        capability_scope_key="security",
        required_capabilities=("cc", "ddos"),
    )

    # Deterministic attack flags from the CC/DDoS tools actually called.
    evidence = collector.extract_security()

    if resp is None:
        # Graceful degradation: don't crash the investigation. Deterministic
        # partial finding enriched with observed attack flags (no longer hard-coded low).
        has_evidence = any(v is not None for v in evidence.values())
        findings_dict = {
            "summary": (
                "安全防护检查在工具预算内未完全收敛，已采集部分防护数据。"
                if has_evidence else
                "安全防护检查在工具预算内未收敛，未采集到有效防护数据。"
            ),
            "cc_status": "no_data",
            "ddos_status": "no_data",
            "protection_status": "incomplete",
            "risk_level": "low",
            "analysis_text": (
                "安全防护检查未完全收敛，已记录关键防护指标。"
                if has_evidence else
                "安全防护检查未完全收敛，且未采集到有效工具数据。"
            ),
            "operational_issue": "coverage_gap",
            "operational_issue_detail": (
                "模型未在工具预算内完全收敛，已基于实际工具返回数据评估。"
                if has_evidence else
                "模型未在工具预算内收敛，且未采集到有效工具数据。"
            ),
        }
        for key, value in evidence.items():
            if value is not None:
                findings_dict[key] = value
        findings_dict["risk_level"] = default_policy().classify_security(findings_dict)
        write(StatusEvent(node="security_guard", message="Security check complete (partial)"))
        result = {
            "messages": [],
            "asset_findings": build_asset_findings(
                primary_asset,
                finding_key="security",
                finding_value=findings_dict,
            ),
        }
        if scoped_asset is None:
            result["findings"] = {"security": findings_dict}
        return result

    analysis_text: str = resp["messages"][-1].content

    extractor = build_model(ModelProfile.STRUCTURED_EXTRACTOR)
    try:
        findings: SecurityFindings = await extractor.with_structured_output(
            SecurityFindings,
            method="function_calling"
        ).ainvoke(
            "用简体中文填写所有字段内容。Extract structured security findings from this protection status"
            f" analysis:\n\n{analysis_text}"
        )
        if findings is None:
            findings = SecurityFindings.model_construct()
    except Exception:
        findings = SecurityFindings.model_construct()

    # Deterministic risk_level override — code-level policy, not LLM judgement.
    findings_dict = findings.model_dump()
    for key, value in evidence.items():
        if value is not None:
            findings_dict[key] = value
    findings_dict["risk_level"] = default_policy().classify_security(findings_dict)
    _annotate_operational_issue(findings_dict)

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
