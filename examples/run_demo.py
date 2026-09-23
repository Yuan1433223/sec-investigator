"""Offline end-to-end demo — run an investigation with ``DATA_SOURCE=fake``.

The data layer is fully synthetic and offline (no VPN, no enterprise
ES/Prometheus/WAF/GF). The agent still needs a working LLM API key in ``.env``
to reason and write the report — that is inherent to an agent.

Usage::

    uv run python examples/run_demo.py [target] [window_start window_end]

Examples::

    uv run python examples/run_demo.py game.ali213.net
    uv run python examples/run_demo.py api2.xs2027.cn
    uv run python examples/run_demo.py kk331dsdi32onew.liu6t.cn
"""

from __future__ import annotations

import asyncio
import json
import sys

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

DEFAULT_TARGET = "game.ali213.net"


def _brief(data: dict, limit: int = 90) -> str:
    s = json.dumps(data, ensure_ascii=False)
    return s if len(s) <= limit else s[: limit - 3] + "..."


async def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET

    from runtime.config.settings import get_settings
    from runtime.events.protocol import (
        ApprovalRequestEvent,
        ErrorEvent,
        FinalEvent,
        StatusEvent,
        ToolCallEvent,
        ToolResultEvent,
    )
    from runtime.graph.investigation import build_investigation_graph
    from langgraph.types import Command

    s = get_settings()
    print(f"data_source = {s.data_source} | target = {target}\n")
    if not (s.openai_api_key or s.anthropic_api_key):
        print("[warn] 未配置 LLM API key（OPENAI_API_KEY / ANTHROPIC_API_KEY）。")
        print("        数据层已离线 fake，但 agent 仍需一个模型来推理与写报告。\n")

    graph = build_investigation_graph(checkpointer=MemorySaver())
    session_id = f"demo-{target}"
    question = (
        f"实体: {target}, 请巡检分析该域名近期流量/状态码异常的原因，"
        "给出结论与处置建议。"
    )

    print("=" * 64)
    events: list = []
    config = {"configurable": {"thread_id": session_id}}

    def _consume(events_list: list) -> None:
        for ev in events_list:
            if isinstance(ev, StatusEvent):
                print(f"[{ev.node}] {ev.message}")
            elif isinstance(ev, ToolCallEvent):
                print(f"   ↳ {ev.tool_name}({_brief(ev.tool_input)})")
            elif isinstance(ev, ToolResultEvent):
                out = ev.output
                if isinstance(out, dict):
                    print(f"   ← {ev.tool_name}: {_brief(out)}")
            elif isinstance(ev, ErrorEvent):
                print(f"[error @ {ev.node}] {ev.message}")

    async for ev in graph.astream(
        {
            "messages": [HumanMessage(content=question)],
            "target": target,
            "session_id": session_id,
        },
        config=config,
        stream_mode="custom",
    ):
        events.append(ev)
    _consume(events)

    # Critical findings pause the graph at the HITL approval gate. In demo mode
    # we auto-approve and resume — the production surface would ask a human.
    saw_approval = any(isinstance(e, ApprovalRequestEvent) for e in events)
    if not any(isinstance(e, FinalEvent) for e in events) and saw_approval:
        print("\n[approval] critical finding → 自动批准（demo 模式），继续生成报告...")
        resume: list = []
        async for ev in graph.astream(
            Command(resume={"approved": True, "approver": "demo-auto-approve"}),
            config=config,
            stream_mode="custom",
        ):
            resume.append(ev)
        _consume(resume)
        events += resume

    final = next((e for e in events if isinstance(e, FinalEvent)), None)
    if final is None:
        print("\n[!] 无 FinalEvent，调查未正常结束。")
        return

    print("=" * 64)
    print("\nFINDINGS")
    for dim, f in final.findings.items():
        print(f"  · {dim}: risk={f.get('risk_level')} | {f.get('summary', '')[:100]}")

    for art in final.artifacts:
        if art.get("artifact_type") == "investigation":
            print("\nREPORT")
            print(f"  alert_status : {art.get('alert_status')}")
            print(f"  summary      : {art.get('summary')}")
            print(f"  root_cause   : {art.get('root_cause', '')}")
            recs = art.get("recommendations")
            if recs:
                print(f"  recommendations:\n{recs}")


if __name__ == "__main__":
    asyncio.run(main())
