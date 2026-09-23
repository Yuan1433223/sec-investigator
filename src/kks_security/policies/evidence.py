"""
Evidence thresholds — code-level policy.

All numeric thresholds that determine whether observed data constitutes
an attack or anomaly live here. Business code reads from EvidencePolicy;
prompts may reference the *values* for human-readable context but must
not be the sole source of truth.

CLAUDE.md hard rule 3: Do not hide critical evidence thresholds only in prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kks_runtime.config.settings import Settings, get_settings


def _normalize_ratio(value: Any) -> float:
    """
    Normalize either ratio-form or percent-form values to a fraction.

    Examples:
    - 0.0723 -> 0.0723
    - 7.23   -> 0.0723
    - 72.3   -> 0.723
    """
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1.0 and numeric <= 100.0:
        return numeric / 100.0
    return numeric


def _all_machine_metrics_missing(findings: dict[str, Any]) -> bool:
    """Return True when no quantitative machine telemetry is present."""
    return (
        findings.get("cpu_pct") is None
        and findings.get("memory_pct") is None
        and findings.get("tcp_established") is None
    )


@dataclass(frozen=True)
class EvidencePolicy:
    """Immutable set of evidence thresholds for a single investigation."""

    # CC attack detection (settings-backed)
    cc_attack_pps_threshold: int
    """input_pps must exceed this value for a CC event to be flagged."""
    cc_attack_delta_threshold: int
    """input_pps - input_submit_pps must exceed this value for a CC event."""

    # DDoS attack detection (settings-backed)
    ddos_attack_kbps_threshold: int
    """bps (in kbps) must reach this value to flag a DDoS event (1 Gbps = 1_000_000 kbps)."""

    # Infrastructure health thresholds
    high_cpu_pct: float = 0.80
    """CPU usage fraction above which a machine is considered under pressure."""
    high_memory_pct: float = 0.85
    """Memory usage fraction above which a machine is considered under pressure."""
    high_tcp_connections: int = 10_000
    """TCP established connections above which the machine is considered loaded."""

    # Log analysis thresholds
    high_error_rate_pct: float = 0.10
    """5xx error rate fraction above which log analysis should flag an anomaly."""
    min_request_count_for_analysis: int = 100
    """Minimum request count before drawing meaningful conclusions from log data."""

    # HITL escalation threshold
    hitl_required_for_critical: bool = field(default=True)
    """
    When True, any finding with risk_level == 'critical' causes the supervisor to route
    to the approval_gate before the reporter.  Set False in fully-automated deployments.
    """

    # -----------------------------------------------------------------------
    # Deterministic risk classification
    # -----------------------------------------------------------------------

    def classify_logs(self, findings: dict[str, Any]) -> str:
        """
        Derive risk_level for LogFindings based on raw numeric fields.

        Logic (applied in order, returns first match):
          critical  → 5xx_rate >= 0.50 OR 4xx_rate >= 0.80
          high      → 5xx_rate >= high_error_rate_pct OR 4xx_rate >= 0.50
          medium    → 5xx_rate > 0 OR 4xx_rate > 0.20
          low       → otherwise
        """
        rate_5xx = _normalize_ratio(findings.get("rate_5xx"))
        rate_4xx = _normalize_ratio(findings.get("rate_4xx"))
        if rate_5xx >= 0.50 or rate_4xx >= 0.80:
            return "critical"
        if rate_5xx >= self.high_error_rate_pct or rate_4xx >= 0.50:
            return "high"
        if rate_5xx > 0 or rate_4xx > 0.20:
            return "medium"
        return "low"

    def classify_machine(self, findings: dict[str, Any]) -> str:
        """
        Derive risk_level for MachineFindings from raw numeric fields.

        Logic (applied in order):
          critical  → cpu_pct >= 0.95 OR memory_pct >= 0.95
          high      → cpu_pct >= high_cpu_pct OR memory_pct >= high_memory_pct
                      OR tcp_established >= high_tcp_connections
          medium    → cpu_pct >= 0.60 OR memory_pct >= 0.70
          low       → otherwise (includes no-data case where all values are 0)
        """
        if _all_machine_metrics_missing(findings):
            # No telemetry is not "healthy"; treat it as an observability gap.
            return "medium"

        cpu = _normalize_ratio(findings.get("cpu_pct"))
        memory = _normalize_ratio(findings.get("memory_pct"))
        tcp = findings.get("tcp_established") or 0
        if cpu >= 0.95 or memory >= 0.95:
            return "critical"
        if cpu >= self.high_cpu_pct or memory >= self.high_memory_pct or tcp >= self.high_tcp_connections:
            return "high"
        if cpu >= 0.60 or memory >= 0.70:
            return "medium"
        return "low"

    def classify_security(self, findings: dict[str, Any]) -> str:
        """
        Derive risk_level for SecurityFindings from raw attack flags.

        Logic (applied in order):
          critical  → cc_is_under_attack AND ddos_exceeds_threshold
          high      → cc_is_under_attack OR ddos_exceeds_threshold
          medium    → cc_pps > 0 OR ddos_event_count > 0
          low       → otherwise
        """
        cc_attack = bool(findings.get("cc_is_under_attack"))
        ddos_attack = bool(findings.get("ddos_exceeds_threshold"))
        cc_pps = findings.get("cc_input_pps") or 0
        ddos_count = findings.get("ddos_event_count") or 0
        if cc_attack and ddos_attack:
            return "critical"
        if cc_attack or ddos_attack:
            return "high"
        if cc_pps > 0 or ddos_count > 0:
            return "medium"
        return "low"

    def requires_approval(self, findings: dict[str, Any]) -> bool:
        """
        Return True when the collected findings require human approval before reporting.

        Trigger condition: at least one finding dict has risk_level == 'critical'
        AND hitl_required_for_critical is True.

        The check is intentionally simple and based solely on the structured
        risk_level field that every finding schema (LogFindings, SecurityFindings,
        MachineFindings) declares — no text parsing, no threshold re-evaluation.
        """
        if not self.hitl_required_for_critical:
            return False
        for finding_dict in findings.values():
            if isinstance(finding_dict, dict) and finding_dict.get("risk_level") == "critical":
                return True
        return False


def default_policy(settings: Settings | None = None) -> EvidencePolicy:
    """
    Build an EvidencePolicy from current settings.

    Reads per-deployment thresholds (CC PPS, DDoS kbps) from Settings;
    infrastructure and log thresholds use package defaults unless overridden.
    """
    s = settings or get_settings()
    return EvidencePolicy(
        cc_attack_pps_threshold=s.cc_attack_pps_threshold,
        cc_attack_delta_threshold=s.cc_attack_delta_threshold,
        ddos_attack_kbps_threshold=s.ddos_attack_kbps_threshold,
    )
