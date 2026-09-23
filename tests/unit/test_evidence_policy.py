"""Unit tests for kks_security.policies.evidence."""

import pytest

from kks_runtime.config.settings import Settings
from kks_security.policies.evidence import EvidencePolicy, default_policy


def test_default_policy_returns_evidence_policy():
    policy = default_policy()
    assert isinstance(policy, EvidencePolicy)


def test_default_policy_reads_settings_thresholds():
    s = Settings(
        cc_attack_pps_threshold=5000,
        cc_attack_delta_threshold=2000,
        ddos_attack_kbps_threshold=500_000,
    )
    policy = default_policy(settings=s)
    assert policy.cc_attack_pps_threshold == 5000
    assert policy.cc_attack_delta_threshold == 2000
    assert policy.ddos_attack_kbps_threshold == 500_000


def test_default_policy_default_settings_values():
    s = Settings()
    policy = default_policy(settings=s)
    assert policy.cc_attack_pps_threshold == 2000
    assert policy.cc_attack_delta_threshold == 1000
    assert policy.ddos_attack_kbps_threshold == 1_000_000


def test_evidence_policy_is_frozen():
    policy = default_policy()
    with pytest.raises((AttributeError, TypeError)):
        policy.high_cpu_pct = 0.99  # type: ignore[misc]


def test_infrastructure_thresholds_are_sensible():
    policy = default_policy()
    assert 0 < policy.high_cpu_pct < 1
    assert 0 < policy.high_memory_pct < 1
    assert policy.high_tcp_connections > 0
    assert policy.high_error_rate_pct > 0
    assert policy.min_request_count_for_analysis > 0


def test_ddos_threshold_is_one_gbps_in_kbps():
    policy = default_policy()
    assert policy.ddos_attack_kbps_threshold == 1_000_000


def test_cc_attack_detection_logic():
    from kks_security.adapters.cc import PointStatus  # noqa: PLC0415
    from kks_security.tools.security_tools import _is_cc_attack  # noqa: PLC0415

    s = Settings(cc_attack_pps_threshold=2000, cc_attack_delta_threshold=1000)
    policy = default_policy(settings=s)

    point_attack = PointStatus(ip="1.1.1.1", input_pps=3000, input_submit_pps=1500)
    assert _is_cc_attack(point_attack, settings=s) is True

    point_ok = PointStatus(ip="1.1.1.1", input_pps=3000, input_submit_pps=2200)
    assert _is_cc_attack(point_ok, settings=s) is False

    point_low = PointStatus(ip="1.1.1.1", input_pps=1000, input_submit_pps=200)
    assert _is_cc_attack(point_low, settings=s) is False

    assert policy.cc_attack_pps_threshold == s.cc_attack_pps_threshold
    assert policy.cc_attack_delta_threshold == s.cc_attack_delta_threshold


def test_ddos_attack_detection_logic():
    from kks_security.tools.security_tools import _is_ddos_attack  # noqa: PLC0415

    s = Settings(ddos_attack_kbps_threshold=1_000_000)
    policy = default_policy(settings=s)

    assert _is_ddos_attack({"bps": 1_000_000}, settings=s) is True
    assert _is_ddos_attack({"bps": 999_999}, settings=s) is False
    assert _is_ddos_attack({"bps": None}, settings=s) is False

    assert policy.ddos_attack_kbps_threshold == s.ddos_attack_kbps_threshold


@pytest.mark.parametrize(
    "rate_5xx,rate_4xx,expected",
    [
        (0.55, 0.0, "critical"),
        (0.0, 0.85, "critical"),
        (0.0, 85.0, "critical"),
        (0.10, 0.0, "high"),
        (0.0, 0.55, "high"),
        (0.0, 55.0, "high"),
        (0.02, 0.0, "medium"),
        (0.0, 0.25, "medium"),
        (0.0, 25.0, "medium"),
        (0.0, 7.23, "low"),
        (0.0, 0.0, "low"),
        (None, None, "low"),
    ],
)
def test_classify_logs(rate_5xx, rate_4xx, expected):
    policy = default_policy()
    findings = {"rate_5xx": rate_5xx, "rate_4xx": rate_4xx}
    assert policy.classify_logs(findings) == expected


@pytest.mark.parametrize(
    "cpu_pct,memory_pct,tcp_established,expected",
    [
        (0.96, 0.0, 0, "critical"),
        (0.0, 0.97, 0, "critical"),
        (96.0, 0.0, 0, "critical"),
        (0.85, 0.0, 0, "high"),
        (0.0, 0.90, 0, "high"),
        (85.0, 0.0, 0, "high"),
        (0.0, 0.0, 12_000, "high"),
        (0.65, 0.0, 0, "medium"),
        (0.0, 0.72, 0, "medium"),
        (0.10, 0.20, 100, "low"),
        (None, None, None, "medium"),
    ],
)
def test_classify_machine(cpu_pct, memory_pct, tcp_established, expected):
    policy = default_policy()
    findings = {
        "cpu_pct": cpu_pct,
        "memory_pct": memory_pct,
        "tcp_established": tcp_established,
    }
    assert policy.classify_machine(findings) == expected


@pytest.mark.parametrize(
    "cc_attack,ddos_attack,cc_pps,ddos_count,expected",
    [
        (True, True, 5000, 2, "critical"),
        (True, False, 5000, 0, "high"),
        (False, True, 0, 2, "high"),
        (False, False, 1500, 0, "medium"),
        (False, False, 0, 3, "medium"),
        (False, False, 0, 0, "low"),
        (None, None, None, None, "low"),
    ],
)
def test_classify_security(cc_attack, ddos_attack, cc_pps, ddos_count, expected):
    policy = default_policy()
    findings = {
        "cc_is_under_attack": cc_attack,
        "ddos_exceeds_threshold": ddos_attack,
        "cc_input_pps": cc_pps,
        "ddos_event_count": ddos_count,
    }
    assert policy.classify_security(findings) == expected
