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

from kks_runtime.events.protocol import StatusEvent
from kks_runtime.graph.nodes._tool_tracing import make_traced_tools
from kks_runtime.llm.profiles import ModelProfile, build_model
from kks_runtime.state.session import SessionState
from kks_security.playbooks.catalog import PlaybookKind, get_playbook
from kks_security.policies.evidence import default_policy
from kks_security.rag.rag_tools import RAG_TOOLS
from kks_security.schemas.findings import LogFindings
from kks_security.tools.es_tools import ES_TOOLS
from kks_security.tools.public_tools import (
    current_time,
    get_gf_log_table_structure,
    get_waf_log_table_structure,
)

_PLAYBOOK = get_playbook(PlaybookKind.LOG_ANALYSIS)
# recursion_limit: each tool call = 2 steps (llm → tool); +1 for final response
_RECURSION_LIMIT = _PLAYBOOK.max_tool_calls * 2 + 1

# ES tools + RAG knowledge search + utility helpers.
# current_time: used to anchor relative time windows.
# table structure tools: ES field reference the LLM can consult during analysis.
_LOG_TOOLS = ES_TOOLS + RAG_TOOLS + [
    current_time,
    get_gf_log_table_structure,
    get_waf_log_table_structure,
]


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
    traced_tools = make_traced_tools(_LOG_TOOLS, "log_detective")
    agent = create_react_agent(
        model=llm,
        tools=traced_tools,
        prompt=_PLAYBOOK.system_prompt,
    )

    resp = await agent.ainvoke(
        {"messages": [HumanMessage(content=task)]},
        config={"recursion_limit": _RECURSION_LIMIT},
    )
    analysis_text: str = resp["messages"][-1].content

    # Structured extraction of the raw analysis
    extractor = build_model(ModelProfile.STRUCTURED_EXTRACTOR)
    findings: LogFindings = await extractor.with_structured_output(LogFindings).ainvoke(
        f"Extract structured findings from this log analysis:\n\n{analysis_text}"
    )

    # Deterministic risk_level override — code-level policy, not LLM judgement.
    findings_dict = findings.model_dump()
    findings_dict["risk_level"] = default_policy().classify_logs(findings_dict)

    write(StatusEvent(node="log_detective", message="Log analysis complete"))

    return {
        "messages": resp["messages"],
        "findings": {"logs": findings_dict},
    }
