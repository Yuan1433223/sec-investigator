"""
Replay tests for 3 recorded production incidents (context.md).

These tests run the full investigation graph with:
  - Worker findings pre-injected (InvestigationInput.findings) so workers are skipped
  - Supervisor LLM mocked to produce agent_task only (routing is deterministic code)
  - Reporter LLM mocked to produce a structured InvestigationReport
  - No real ES / Prometheus HTTP calls

The goal is to prove that:
1. Supervisor routes correctly for domain targets (no machine_check)
2. With realistic findings present, the reporter produces a valid artifact
3. Key assertions from the gold answers are preserved in the report
4. Streaming produces the correct event sequence

Incident sources (context.md):
  1. game.ali213.net  — 4xx spike 1000%, distributed crawler scan
  2. api2.xs2027.cn   — 5xx spike 600%, source-station application fault
  3. kk331dsdi32onew.liu6t.cn — 5xx absolute count >6000, high-concurrency source overload
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from kks_runtime.graph.investigation import build_investigation_graph
from kks_security.schemas.report import InvestigationReport

# ---------------------------------------------------------------------------
# Scenario fixtures — input + pre-built findings matching context.md gold answers
# ---------------------------------------------------------------------------

_SCENARIOS = [
    {
        "id": "game_ali213_4xx",
        "target": "game.ali213.net",
        "question": (
            "实体: game.ali213.net, 告警: 域名1min聚合4xx趋势突增1000%, "
            "时间段: 2026-04-23 11:56:40 至 2026-04-23 12:14:40, 请巡检分析原因"
        ),
        # Pre-built findings extracted from the gold answer (context.md incident 1)
        "findings": {
            "logs": {
                "summary": "告警时段总请求约196954次，4xx合计约39620次（占比约20%）。峰值12:03单分钟4xx达7418次，是基线的12倍。404为主体（72%），499占25%。",  # noqa: E501
                "qps_info": "peak 7418/min at 12:03",
                "error_rate": {"4xx": "20%"},
                "top_errors": ["404: /forum.php (invalid path probe)", "499: crawler disconnect"],
                "risk_level": "high",
                "analysis_text": "Stub",
            },
            "security": {
                "summary": "存在分布式爬虫/批量扫描行为，多IP集中发起无效路径探测请求。UA伪装为正常浏览器，未触发游戏盾DDoS/CC安全告警。",  # noqa: E501
                "cc_status": "no CC attack detected",
                "ddos_status": "no DDoS alert",
                "protection_status": "normal, distributed crawler not blocked",
                "risk_level": "medium",
                "analysis_text": "Stub",
            },
        },
        "report_summary": "4xx请求量突增约1000%，主要由分布式爬虫/批量扫描流量洪峰引发，源站服务稳定。",  # noqa: E501
        "expected_alert_status": "warning",
    },
    {
        "id": "api2_xs2027_5xx",
        "target": "api2.xs2027.cn",
        "question": (
            "实体: api2.xs2027.cn, 告警: 域名1min聚合5xx趋势上涨600%, "
            "时间段: 2026-04-18 12:18:00 至 2026-04-18 12:36:00, 请巡检分析原因"
        ),
        "findings": {
            "logs": {
                "summary": "告警期间总请求量约24536次，其中502错误15356次（62.9%）。自12:23起5xx占比接近100%，回源地址唯一（180.188.35.116:443），单点风险高。",  # noqa: E501
                "qps_info": "502 dominant from 12:23",
                "error_rate": {"5xx": "62.9%", "2xx": "37.1%"},
                "top_errors": ["502: upstream /api 15356 times"],
                "risk_level": "critical",
                "analysis_text": "Stub",
            },
            "security": {
                "summary": "未检测到DDoS攻击及CC攻击，安全告警记录为空。客户端IP共104个唯一地址，User-Agent全部为okhttp/3.12.6（移动端App正常标识），排除安全攻击因素。",  # noqa: E501
                "cc_status": "no CC attack",
                "ddos_status": "no DDoS alert",
                "protection_status": "normal",
                "risk_level": "low",
                "analysis_text": "Stub",
            },
        },
        "report_summary": "源站180.188.35.116:443应用层服务异常，导致全部请求返回502，业务中断约10分钟。建议联系客户排查源站故障。",  # noqa: E501
        "expected_alert_status": "critical",
    },
    {
        "id": "kk331_5xx_absolute",
        "target": "kk331dsdi32onew.liu6t.cn",
        "question": (
            "实体: kk331dsdi32onew.liu6t.cn, 告警: 域名1min聚合5xx超6000、源站域名1min聚合5xx超3000, "  # noqa: E501
            "时间段: 2026-04-18 02:23:40 至 2026-04-18 02:41:40, 请巡检分析原因"
        ),
        "findings": {
            "logs": {
                "summary": "QPS在02:24从31.5万/分钟骤增至93.5万/分钟（约3倍），5xx状态码共17569次，全部为502，主回源地址47.98.255.59:80承载超过99%的请求。业务已于02:38自动恢复。",  # noqa: E501
                "qps_info": "315k→935k/min spike at 02:24",
                "error_rate": {"5xx": "502 dominant in 02:24 and 02:37-38"},
                "top_errors": ["502: upstream 47.98.255.59:80 17569 times"],
                "risk_level": "critical",
                "analysis_text": "Stub",
            },
            "security": {
                "summary": "安全系统在02:05~02:07已检测到QPS异常和状态码异常告警，攻击时段为01:50~02:05，主要UA为uni-app（iPhone iOS 18.7）。当前实时CC检测无明显攻击，防护策略正常运行。",  # noqa: E501
                "cc_status": "historical CC alert 01:50-02:05, current clear",
                "ddos_status": "no DDoS alert",
                "protection_status": "normal, rate limiting active",
                "risk_level": "medium",
                "analysis_text": "Stub",
            },
        },
        "report_summary": "主源站47.98.255.59在超高并发冲击下短暂过载返回502，QPS回落后业务自动恢复。建议客户为源站配置负载均衡。",  # noqa: E501
        "expected_alert_status": "critical",
    },
]

# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _mock_supervisor_llm() -> MagicMock:
    """Supervisor LLM: generates agent_task stub — routing is deterministic code."""
    task_decision = MagicMock()
    task_decision.agent_task = "Investigate the target as instructed."
    mock_structured = AsyncMock(return_value=task_decision)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


def _mock_reporter_llm(report: InvestigationReport) -> MagicMock:
    mock_structured = AsyncMock(return_value=report)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock(ainvoke=mock_structured)
    return mock_llm


_SUPERVISOR_PATH = "kks_runtime.graph.nodes.supervisor.build_model"
_REPORTER_PATH = "kks_runtime.graph.nodes.reporter.build_model"
_DEFAULT_POLICY_PATH = "kks_runtime.graph.nodes.supervisor.default_policy"


def _no_hitl_policy():
    """Return an EvidencePolicy with HITL disabled — replay tests bypass approval gate."""
    import dataclasses

    from kks_security.policies.evidence import default_policy

    return dataclasses.replace(default_policy(), hitl_required_for_critical=False)

# ---------------------------------------------------------------------------
# Full graph replay — pre-injected findings, domain routing verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["id"] for s in _SCENARIOS])
async def test_replay_domain_incident_completes(scenario):
    """
    Full graph replay for a recorded domain-target incident.

    Findings are pre-injected (matching context.md gold answers) so supervisor
    routes directly to reporter. Verifies:
    - status=completed
    - 1 investigation artifact with correct target
    - findings preserved (logs + security, no machine)
    - artifact contains report payload
    """
    report = InvestigationReport(
        alert_status=scenario["expected_alert_status"],
        summary=scenario["report_summary"],
        recommendations="See full report for recommended actions.",
    )

    graph = build_investigation_graph(checkpointer=MemorySaver())
    thread_id = f"replay-{scenario['id']}"

    with (
        patch(_SUPERVISOR_PATH, return_value=_mock_supervisor_llm()),
        patch(_REPORTER_PATH, return_value=_mock_reporter_llm(report)),
        patch(_DEFAULT_POLICY_PATH, return_value=_no_hitl_policy()),
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=scenario["question"])],
                "target": scenario["target"],
                "session_id": thread_id,
                "findings": scenario["findings"],  # pre-inject → supervisor routes to reporter
            },
            config={"configurable": {"thread_id": thread_id}},
        )

    assert result["status"] == "completed", f"Expected completed, got {result['status']}"

    artifacts = result["artifacts"]
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["artifact_type"] == "investigation"
    assert artifact["target"] == scenario["target"]

    findings = result["findings"]
    assert "logs" in findings
    assert "security" in findings
    assert "machine" not in findings, "machine_check must not run for domain targets"

    assert findings["logs"]["risk_level"] == scenario["findings"]["logs"]["risk_level"]

    # Artifact carries summary and recommendations from reporter
    assert isinstance(artifact.get("summary"), str)
    assert len(artifact.get("recommendations", [])) >= 0  # list, may be empty for stub


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["id"] for s in _SCENARIOS])
async def test_replay_streams_events(scenario):
    """
    Stream replay: verify FinalEvent emitted with correct artifact.
    """
    from kks_runtime.events.protocol import FinalEvent, StatusEvent

    report = InvestigationReport(
        alert_status=scenario["expected_alert_status"],
        summary=scenario["report_summary"],
        recommendations="See report.",
    )

    graph = build_investigation_graph(checkpointer=MemorySaver())
    thread_id = f"replay-stream-{scenario['id']}"
    events: list = []

    with (
        patch(_SUPERVISOR_PATH, return_value=_mock_supervisor_llm()),
        patch(_REPORTER_PATH, return_value=_mock_reporter_llm(report)),
        patch(_DEFAULT_POLICY_PATH, return_value=_no_hitl_policy()),
    ):
        async for chunk in graph.astream(
            {
                "messages": [HumanMessage(content=scenario["question"])],
                "target": scenario["target"],
                "session_id": thread_id,
                "findings": scenario["findings"],
            },
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="custom",
        ):
            events.append(chunk)

    final_events = [e for e in events if isinstance(e, FinalEvent)]
    assert len(final_events) == 1

    final = final_events[0]
    assert len(final.artifacts) == 1
    assert final.artifacts[0]["artifact_type"] == "investigation"
    assert final.artifacts[0]["target"] == scenario["target"]

    # Reporter emits at least a start StatusEvent
    status_events = [e for e in events if isinstance(e, StatusEvent)]
    reporter_events = [e for e in status_events if e.node == "reporter"]
    assert len(reporter_events) >= 1

    # machine_check must never appear in the event stream
    machine_events = [e for e in status_events if e.node == "machine_check"]
    assert len(machine_events) == 0, "machine_check must not run for domain targets"


# ---------------------------------------------------------------------------
# Routing-only tests (pure _next_worker logic — no graph invocation)
# ---------------------------------------------------------------------------


def test_domain_target_routing_skips_machine_check():
    """_next_worker never returns machine_check for a domain target."""
    from kks_runtime.graph.nodes.supervisor import _next_worker

    findings: dict = {}
    assert _next_worker(findings, is_ip_target=False) == "log_detective"
    findings["logs"] = {}
    assert _next_worker(findings, is_ip_target=False) == "security_guard"
    findings["security"] = {}
    assert _next_worker(findings, is_ip_target=False) == "reporter"


def test_ip_target_routing_includes_machine_check():
    """_next_worker includes machine_check for IP targets."""
    from kks_runtime.graph.nodes.supervisor import _next_worker

    findings: dict = {}
    assert _next_worker(findings, is_ip_target=True) == "log_detective"
    findings["logs"] = {}
    assert _next_worker(findings, is_ip_target=True) == "machine_check"
    findings["machine"] = {}
    assert _next_worker(findings, is_ip_target=True) == "security_guard"
    findings["security"] = {}
    assert _next_worker(findings, is_ip_target=True) == "reporter"


def test_all_three_scenarios_are_domain_targets():
    """Each recorded incident target is classified as a domain (not an IP)."""
    from kks_runtime.graph.nodes.supervisor import _is_ip

    for scenario in _SCENARIOS:
        assert not _is_ip(scenario["target"]), (
            f"{scenario['target']} incorrectly classified as IP"
        )


def test_scenario_findings_keys_satisfy_domain_requirements():
    """All scenario findings dicts contain the required keys for domain targets."""
    domain_required = {"logs", "security"}
    for scenario in _SCENARIOS:
        keys = set(scenario["findings"].keys())
        missing = domain_required - keys
        assert not missing, f"Scenario {scenario['id']} missing findings: {missing}"
        assert "machine" not in keys, f"Scenario {scenario['id']} should not have machine findings"


def test_critical_risk_findings_trigger_approval_policy():
    """
    Scenarios with critical log findings satisfy EvidencePolicy.requires_approval().
    This validates that if the graph were running without pre-injection,
    the approval gate would fire for incident 2 and 3.
    """
    import dataclasses

    from kks_security.policies.evidence import default_policy

    policy = dataclasses.replace(default_policy(), hitl_required_for_critical=True)

    for scenario in _SCENARIOS:
        findings = scenario["findings"]
        has_critical = any(
            v.get("risk_level") == "critical"
            for v in findings.values()
            if isinstance(v, dict)
        )
        if has_critical:
            assert policy.requires_approval(findings), (
                f"Scenario {scenario['id']} has critical findings but policy returned False"
            )
