"""
Machine Check worker node.

Dispatches a ReAct agent with Prometheus tools to assess infrastructure
health for a target IP. Returns structured MachineFindings in `findings`.

Changes vs prior version:
- tools are wrapped with make_traced_tools() → emits ToolCallEvent/ToolResultEvent
- agent.ainvoke receives recursion_limit = max_tool_calls * 2 + 1 (enforces budget)
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
from security.schemas.findings import MachineFindings
from security.tools.prom_tools import PROM_TOOLS

_PLAYBOOK = get_playbook(PlaybookKind.INFRA_DIAGNOSIS)
_RECURSION_LIMIT = _PLAYBOOK.max_tool_calls * 2 + 1


async def machine_check_node(state: SessionState) -> dict:
    """
    Worker node: assess infrastructure health via Prometheus metrics.

    Uses TOOL_REASONER profile for multi-step tool calling.
    Tool budget: max_tool_calls from INFRA_DIAGNOSIS playbook, enforced via recursion_limit.
    """
    write = get_stream_writer()
    write(StatusEvent(node="machine_check", message="Querying infrastructure metrics..."))

    task = state.get("agent_task") or f"Check infrastructure for {state.get('target', 'unknown')}"

    llm = build_model(_PLAYBOOK.model_profile)
    traced_tools = make_traced_tools(PROM_TOOLS, "machine_check")
    agent = create_react_agent(model=llm, tools=traced_tools, prompt=_PLAYBOOK.system_prompt)

    resp = await agent.ainvoke(
        {"messages": [HumanMessage(content=task)]},
        config={"recursion_limit": _RECURSION_LIMIT},
    )
    analysis_text: str = resp["messages"][-1].content

    extractor = build_model(ModelProfile.STRUCTURED_EXTRACTOR)
    findings: MachineFindings = await extractor.with_structured_output(
        MachineFindings,
        method="function_calling"
    ).ainvoke(
        f"Extract structured machine findings from this infrastructure analysis:\n\n{analysis_text}"
    )

    # Deterministic risk_level override — code-level policy, not LLM judgement.
    findings_dict = findings.model_dump()
    findings_dict["risk_level"] = default_policy().classify_machine(findings_dict)
    scoped_asset = active_asset(state)
    primary_asset = scoped_asset or select_primary_asset(
        state,
        capability_scope_key="machine",
        required_capabilities=("prom",),
    )

    write(StatusEvent(node="machine_check", message="Infrastructure check complete"))

    result = {
        "messages": resp["messages"],
        "asset_findings": build_asset_findings(
            primary_asset,
            finding_key="machine",
            finding_value=findings_dict,
        ),
    }
    if scoped_asset is None:
        result["findings"] = {"machine": findings_dict}
    return result
