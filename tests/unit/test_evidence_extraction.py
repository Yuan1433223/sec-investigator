"""Unit tests for deterministic evidence extraction + classifier integration.

These lock the A0 closed loop: raw tool results (not LLM recall) feed
EvidencePolicy.classify_* and produce the expected risk_level.
"""
from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from security.policies.evidence import default_policy
from security.policies.extraction import (
    EvidenceCollector,
    extract_log_evidence,
    extract_machine_evidence,
    extract_security_evidence,
)


def _tool(name: str, payload: dict) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        name=name,
        tool_call_id=f"call_{name}",
    )


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def test_extract_logs_5xx_dominant_is_critical():
    msgs = [
        _tool(
            "query_status_code_distribution",
            {
                "current": [
                    {"status": 200, "count": 3060},
                    {"status": 502, "count": 6415},
                    {"status": 503, "count": 408},
                    {"status": 504, "count": 306},
                ],
                "previous": [{"status": 200, "count": 9996}],
            },
        )
    ]
    ev = extract_log_evidence(msgs)
    assert ev["rate_5xx"] > 0.50
    assert ev["rate_4xx"] == 0.0
    assert default_policy().classify_logs(ev) == "critical"


def test_extract_logs_4xx_dominant_is_critical():
    msgs = [
        _tool(
            "query_status_code_distribution",
            {
                "current": [
                    {"status": 200, "count": 4778},
                    {"status": 404, "count": 19749},
                    {"status": 499, "count": 6052},
                ],
                "previous": [],
            },
        )
    ]
    ev = extract_log_evidence(msgs)
    assert ev["rate_4xx"] >= 0.80
    assert default_policy().classify_logs(ev) == "critical"


def test_extract_logs_via_qps_vs_status_trend_fallback():
    """The ReAct agent usually calls qps_trend + per-status trends, not the
    distribution tool. rate_5xx = sum(5xx counts) / sum(total-traffic counts)."""
    msgs = [
        _tool("query_es_qps_trend", {"total": 600, "trend": [{"time": "a", "count": 300}, {"time": "b", "count": 300}]}),
        _tool("query_es_status_code_trend", {"status_type": "4xx", "total": 600, "trend": [{"time": "a", "count": 0}, {"time": "b", "count": 0}]}),
        _tool("query_es_status_code_trend", {"status_type": "5xx", "total": 600, "trend": [{"time": "a", "count": 210}, {"time": "b", "count": 210}]}),
    ]
    ev = extract_log_evidence(msgs)
    assert ev["rate_5xx"] == 0.7
    assert ev["rate_4xx"] == 0.0
    assert default_policy().classify_logs(ev) == "critical"


def test_extract_logs_clean_is_low():
    msgs = [
        _tool(
            "query_status_code_distribution",
            {
                "current": [
                    {"status": 200, "count": 9700},
                    {"status": 301, "count": 200},
                    {"status": 404, "count": 100},
                ],
                "previous": [],
            },
        )
    ]
    ev = extract_log_evidence(msgs)
    assert default_policy().classify_logs(ev) == "low"


def test_extract_logs_ignores_unparseable_payloads():
    msgs = [
        ToolMessage(
            content="not json at all",
            name="query_status_code_distribution",
            tool_call_id="call_bad",
        ),
        _tool("query_request_count", {"count": 100}),
    ]
    ev = extract_log_evidence(msgs)
    assert "rate_5xx" not in ev


# ---------------------------------------------------------------------------
# Machine
# ---------------------------------------------------------------------------


def test_extract_machine_cpu_95_is_critical():
    msgs = [
        _tool(
            "query_instance_status",
            {"instance": "1.2.3.4", "cpu_usage": "96.0%", "memory_usage": "64.0%", "tcp_established": 1200},
        )
    ]
    ev = extract_machine_evidence(msgs)
    assert abs(ev["cpu_pct"] - 0.96) < 1e-6
    assert ev["tcp_established"] == 1200
    assert default_policy().classify_machine(ev) == "critical"


def test_extract_machine_healthy_is_low():
    msgs = [
        _tool("query_instance_cpu", {"cpu_usage": "5.6%"}),
        _tool("query_instance_memory", {"memory_usage": "22.0%"}),
        _tool("query_instance_tcp", {"tcp_established": 1500}),
    ]
    ev = extract_machine_evidence(msgs)
    assert default_policy().classify_machine(ev) == "low"


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_extract_security_both_attacks_critical():
    msgs = [
        _tool("check_cc_status", {"status": "ok", "points": [{"is_under_attack": True, "input_pps": 5000}]}),
        _tool("check_ddos_status", {"status": True, "events": [{"exceeds_threshold": True}], "count": 1}),
    ]
    ev = extract_security_evidence(msgs)
    assert ev["cc_is_under_attack"] is True
    assert ev["ddos_exceeds_threshold"] is True
    assert default_policy().classify_security(ev) == "critical"


def test_extract_security_no_attack_is_low():
    msgs = [
        _tool("check_cc_status", {"status": "ok", "points": [{"is_under_attack": False, "input_pps": 900}]}),
        _tool("check_ddos_status", {"status": False, "events": [], "count": 0}),
    ]
    ev = extract_security_evidence(msgs)
    assert ev["cc_is_under_attack"] is False
    assert ev["cc_input_pps"] == 900
    # Nonzero-but-below-threshold PPS → medium (observed traffic), not low.
    assert default_policy().classify_security(ev) == "medium"


# ---------------------------------------------------------------------------
# Collector (per-invocation, not a singleton)
# ---------------------------------------------------------------------------


def test_collector_observe_then_extract():
    c = EvidenceCollector("logs")
    c.observe(
        "query_status_code_distribution",
        {"current": [{"status": 502, "count": 629}, {"status": 200, "count": 371}]},
    )
    ev = c.extract_logs()
    assert abs(ev["rate_5xx"] - 0.629) < 0.01
    # Two collectors stay independent (no module-level global).
    c2 = EvidenceCollector("logs")
    assert c2.extract_logs() == {}
