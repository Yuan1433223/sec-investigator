"""Integration test — LangGraph subgraph event bubbling.

Verifies that ToolCallEvent/ToolResultEvent written inside create_react_agent
subgraphs (via get_stream_writer) actually arrive at the top-level stream
when astream(stream_mode="custom", subgraphs=True) is used and _unwrap()
extracts them.

This is distinct from test_approval_flow.py: that test PATCHES create_react_agent
with a fake loop, so no real subgraph exists. Here we use the REAL
create_react_agent with a stub LLM that emits a tool_call, and assert the
bubbled event reaches the top-level stream.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langgraph.checkpoint.memory import MemorySaver

from runtime.events.protocol import ApprovalRequestEvent, ToolCallEvent
from runtime.graph.investigation import build_investigation_graph
from security.schemas.findings import LogFindings, MachineFindings, SecurityFindings
from security.schemas.report import InvestigationReport

TARGET = "api2.xs2027.cn"


class _ToolCallingLLM(BaseChatModel):
    """Stub chat model that emits a tool_call on first call, then a final message.

    Mimics a ReAct LLM: first turn → tool_calls, second turn → plain content.
    Supports bind_tools() (returns self so create_react_agent can wrap tools).
    """

    called: int = 0
    _tools: list = []

    @property
    def _llm_type(self) -> str:
        return "tool-calling-stub"

    def bind_tools(self, tools, **kwargs):
        bound = _ToolCallingLLM()
        bound.called = 0
        bound._tools = list(tools) if tools else []
        return bound

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.called += 1
        if self.called == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_status_code_distribution",
                        "args": {
                            "query_by": "domain",
                            "value": TARGET,
                            "start_time": "2026-04-18 12:18:00",
                            "end_time": "2026-04-18 12:36:00",
                        },
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Status distribution analysed: 5xx dominant.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _structured(obj) -> MagicMock:
    m = MagicMock()
    m.with_structured_output.return_value = MagicMock(ainvoke=AsyncMock(return_value=obj))
    return m


def _supervisor_fake() -> MagicMock:
    from runtime.graph.nodes.supervisor import AgentTaskDecision
    return _structured(AgentTaskDecision(agent_task="Investigate the target."))


def _reporter_fake() -> MagicMock:
    report = InvestigationReport(
        alert_status="critical",
        summary="源站 5xx 突增，已确认为应用层故障（结构化报告）。",
        recommendations="1. 检查源站应用进程；2. 切换备用源站。",
    )
    return _structured(report)


class _NeutralReActAgent:
    async def ainvoke(self, messages, config=None):
        return {"messages": [AIMessage(content="No anomalies of note.")]}


@pytest.mark.asyncio
async def test_subgraph_tool_events_bubble_to_top_level():
    """ToolCallEvent from inside create_react_agent subgraph must reach top-level
    astream(stream_mode='custom', subgraphs=True) output."""

    fake_llm = _ToolCallingLLM()

    def _log_build_model(profile, *a, **kw):
        if profile == "structured_extractor":
            return _structured(LogFindings.model_construct())
        # Return our tool-calling stub for the reasoner profile
        return fake_llm

    with (
        patch("runtime.graph.nodes.supervisor.build_model",
              side_effect=lambda *a, **kw: _supervisor_fake()),
        patch("runtime.graph.nodes.log_detective.build_model",
              side_effect=_log_build_model),
        # NOTE: create_react_agent is NOT patched here — we want the real subgraph
        patch("runtime.graph.nodes.machine_check.create_react_agent",
              side_effect=lambda **kw: _NeutralReActAgent()),
        patch("runtime.graph.nodes.machine_check.build_model",
              side_effect=lambda profile, *a, **kw: (
                  _structured(MachineFindings.model_construct())
                  if profile == "structured_extractor" else MagicMock()
              )),
        patch("runtime.graph.nodes.security_guard.create_react_agent",
              side_effect=lambda **kw: _NeutralReActAgent()),
        patch("runtime.graph.nodes.security_guard.build_model",
              side_effect=lambda profile, *a, **kw: (
                  _structured(SecurityFindings.model_construct())
                  if profile == "structured_extractor" else MagicMock()
              )),
        patch("runtime.graph.nodes.reporter.build_model",
              side_effect=lambda *a, **kw: _reporter_fake()),
    ):
        graph = build_investigation_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "subgraph-bubble-1"}}

        raw_chunks = []
        async for chunk in graph.astream(
            {
                "messages": [AIMessage(content="investigate")],
                "target": TARGET,
                "session_id": "subgraph-bubble-1",
            },
            config=config,
            stream_mode="custom",
            subgraphs=True,
        ):
            raw_chunks.append(chunk)

    # Unwrap each chunk (tuple = subgraph, bare = top-level)
    tool_events = []
    for chunk in raw_chunks:
        if isinstance(chunk, tuple) and len(chunk) == 2:
            ns, event = chunk
        else:
            ns, event = [], chunk
        if isinstance(event, ToolCallEvent):
            tool_events.append(event)

    # Core assertion: at least one ToolCallEvent bubbled up from the subgraph
    assert len(tool_events) >= 1, (
        f"Expected ToolCallEvent from subgraph, got {len(tool_events)} "
        f"tool events out of {len(raw_chunks)} total chunks"
    )
    assert any(
        e.tool_name == "query_status_code_distribution" for e in tool_events
    ), f"Expected query_status_code_distribution tool call, got: {[e.tool_name for e in tool_events]}"

    # Also verify approval still triggers (A0 loop intact)
    approval_reqs = [
        e for chunk in raw_chunks
        for e in ([chunk[1]] if isinstance(chunk, tuple) else [chunk])
        if isinstance(e, ApprovalRequestEvent)
    ]
    assert len(approval_reqs) >= 1, "approval_gate should still trigger on critical"
