"""
Tests for deterministic required_findings routing in supervisor_node.

Validates _next_worker capability routing without making any LLM calls.
"""

from __future__ import annotations

from runtime.graph.nodes.asset_resolution import _is_ip
from runtime.graph.nodes.supervisor import _eligible_workers, _next_worker


def test_is_ip_bare_ip():
    assert _is_ip("1.2.3.4") is True


def test_is_ip_with_spaces():
    assert _is_ip("  10.0.0.1  ") is True


def test_is_ip_domain():
    assert _is_ip("example.com") is False


def test_is_ip_partial():
    assert _is_ip("1.2.3") is False


def test_is_ip_empty():
    assert _is_ip("") is False


def test_eligible_workers_with_full_scope():
    eligible = _eligible_workers(
        {"log": ["target"], "machine": ["prom"], "security": ["security"]}
    )
    assert eligible == frozenset({"log_detective", "machine_check", "security_guard"})


def test_eligible_workers_with_log_only_scope():
    eligible = _eligible_workers({"log": ["target"], "machine": [], "security": []})
    assert eligible == frozenset({"log_detective"})


def test_eligible_workers_with_domain_policy_only_security():
    eligible = _eligible_workers(
        {"log": ["target"], "machine": [], "security": ["domain_policy"]}
    )
    assert eligible == frozenset({"log_detective", "security_guard"})


def test_ip_no_findings_routes_to_log_detective():
    eligible = frozenset({"log_detective", "machine_check", "security_guard"})
    assert _next_worker({}, eligible) == "log_detective"


def test_ip_logs_only_routes_to_machine_check():
    eligible = frozenset({"log_detective", "machine_check", "security_guard"})
    assert _next_worker({"logs": {}}, eligible) == "machine_check"


def test_ip_logs_machine_routes_to_security_guard():
    eligible = frozenset({"log_detective", "machine_check", "security_guard"})
    assert _next_worker({"logs": {}, "machine": {}}, eligible) == "security_guard"


def test_ip_all_findings_route_to_reporter():
    eligible = frozenset({"log_detective", "machine_check", "security_guard"})
    findings = {"logs": {}, "machine": {}, "security": {}}
    assert _next_worker(findings, eligible) == "reporter"


def test_domain_without_machine_capability_skips_machine_check():
    eligible = frozenset({"log_detective", "security_guard"})
    assert _next_worker({"logs": {}}, eligible) == "security_guard"


def test_log_only_scope_routes_directly_to_reporter_after_logs():
    eligible = frozenset({"log_detective"})
    assert _next_worker({"logs": {}}, eligible) == "reporter"


def test_extra_findings_key_does_not_break_routing():
    eligible = frozenset({"log_detective", "machine_check", "security_guard"})
    findings = {"logs": {}, "machine": {}, "security": {}, "custom_extra": {}}
    assert _next_worker(findings, eligible) == "reporter"
