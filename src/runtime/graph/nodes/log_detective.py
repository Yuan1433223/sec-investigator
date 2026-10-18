"""
Log Detective worker node.

Dispatches a ReAct agent with ES tools to analyse access logs for a target
domain or IP. Returns structured LogFindings in the `findings` dict.

Changes vs prior version:
- tools are wrapped with make_traced_tools() → emits ToolCallEvent/ToolResultEvent
- agent.ainvoke receives recursion_limit = max_tool_calls * 2 + 1 (enforces budget)
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langgraph.prebuilt import create_react_agent

from runtime.events.protocol import StatusEvent
from runtime.graph.nodes._tool_tracing import ainvoke_react_agent, make_traced_tools
from runtime.llm.profiles import ModelProfile, build_model
from runtime.state.session import SessionState
from security.playbooks.catalog import PlaybookKind, get_playbook
from security.policies.evidence import default_policy
from security.policies.extraction import EvidenceCollector
from security.rag.rag_tools import get_rag_tools
from security.schemas.findings import LogFindings
from security.tools.es_tools import get_es_tools
from security.tools.public_tools import (
    get_gf_log_table_structure,
    get_waf_log_table_structure,
)

_PLAYBOOK = get_playbook(PlaybookKind.LOG_ANALYSIS)
# recursion_limit: each tool call = 2 steps (llm → tool); +1 for final response
_RECURSION_LIMIT = _PLAYBOOK.max_tool_calls * 2 + 1


async def log_detective_node(state: SessionState) -> dict:
    """
    Worker node: analyse ES access logs for the investigation target.

    Uses TOOL_REASONER profile for multi-step tool calling.
    Tool budget: max_tool_calls from LOG_ANALYSIS playbook, enforced via recursion_limit.
    Includes search_knowledge so the agent can retrieve historical runbooks
    and incident patterns from the ops knowledge base during analysis.
    """
    write = get_stream_writer()
    write(StatusEvent(node="log_detective", message="Analysing access logs..."))

    task = state.get("agent_task") or f"Analyse logs for {state.get('target', 'unknown')}"

    llm = build_model(_PLAYBOOK.model_profile)
    collector = EvidenceCollector("logs")
    # Build tool list at runtime (lazy factory, no module-level singleton)
    log_tools = get_es_tools() + get_rag_tools() + [
        get_gf_log_table_structure,
        get_waf_log_table_structure,
    ]
    traced_tools = make_traced_tools(
        log_tools, "log_detective", evidence_sink=collector.observe
    )
    agent = create_react_agent(
        model=llm,
        tools=traced_tools,
        prompt=_PLAYBOOK.system_prompt,
        name="log_detective",
    )

    resp = await ainvoke_react_agent(
        agent,
        [HumanMessage(content=task)],
        recursion_limit=_RECURSION_LIMIT,
        node="log_detective",
        write=write,
        degrade_message="Log analysis tool budget exhausted; returning partial finding",
    )

    # Deterministic telemetry straight from the tools the agent actually called.
    # These numbers override whatever the LLM extractor recalled (or dropped).
    evidence = collector.extract_logs()

    if resp is None:
        # Graceful degradation: deterministic partial finding, but enriched with
        # the real numbers we DID observe before the budget ran out.
        has_evidence = any(v is not None for v in evidence.values())
        findings_dict = {
            "summary": (
                "日志分析在工具预算内未完全收敛，已采集部分遥测数据。"
                if has_evidence else
                "日志分析在工具预算内未收敛，未采集到有效遥测数据。"
            ),
            "qps_info": "无 QPS 数据",
            "error_rate": _error_rate_text(evidence),
            "top_errors": [],
            "risk_level": "low",
            "analysis_text": (
                "日志分析未完全收敛，已记录工具返回的关键指标。"
                if has_evidence else
                "日志分析未完全收敛，且未采集到有效工具数据。"
            ),
            "trend_comparison": None,
        }
        for key, value in evidence.items():
            if value is not None:
                findings_dict[key] = value
        findings_dict["risk_level"] = default_policy().classify_logs(findings_dict)
        write(StatusEvent(node="log_detective", message="Log analysis complete (partial)"))
        return {"messages": [], "findings": {"logs": findings_dict}}

    analysis_text: str = resp["messages"][-1].content

    # Structured extraction of the raw analysis.
    # The LLM may emit non-schema enum values (e.g. Chinese "低" for risk_level);
    # pydantic rejects those. Deterministic classify below overwrites risk_level
    # anyway, so a bad extraction degrades to an empty model instead of crashing.
    extractor = build_model(ModelProfile.STRUCTURED_EXTRACTOR)
    try:
        findings: LogFindings = await extractor.with_structured_output(
            LogFindings, method="function_calling"
        ).ainvoke(
            f"用简体中文填写所有字段内容。Extract structured findings from this log analysis:\n\n{analysis_text}"
        )
        if findings is None:
            findings = LogFindings.model_construct()
    except Exception:
        findings = LogFindings.model_construct()

    # Deterministic risk_level override — code-level policy, not LLM judgement.
    # Tool-derived raw numbers win over LLM-recalled fields.
    findings_dict = findings.model_dump()
    for key, value in evidence.items():
        if value is not None:
            findings_dict[key] = value
    findings_dict["error_rate"] = _merged_error_rate(findings_dict.get("error_rate"), evidence)
    findings_dict["risk_level"] = default_policy().classify_logs(findings_dict)

    write(StatusEvent(node="log_detective", message="Log analysis complete"))

    return {
        "messages": resp["messages"],
        "findings": {"logs": findings_dict},
    }


def _error_rate_text(evidence: dict) -> dict:
    """Render extracted rates into the human-readable error_rate breakdown."""
    out: dict[str, str] = {}
    r5 = evidence.get("rate_5xx")
    r4 = evidence.get("rate_4xx")
    if r5 is not None:
        out["5xx"] = f"{r5 * 100:.1f}%"
    if r4 is not None:
        out["4xx"] = f"{r4 * 100:.1f}%"
    return out


def _merged_error_rate(existing: Any, evidence: dict) -> dict:
    """Merge LLM error_rate with deterministic rates (deterministic wins)."""
    base = dict(existing) if isinstance(existing, dict) else {}
    base.update(_error_rate_text(evidence))
    return base
