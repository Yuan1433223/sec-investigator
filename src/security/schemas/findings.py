"""
Structured output schemas for worker findings.

Each worker node returns one of these Pydantic models in the `findings` dict:
  {"logs": LogFindings, "security": SecurityFindings, "machine": MachineFindings}

Migrated from KKShieldHelper-main/agents/ReAct/schema.py — cleaned of legacy
graph coupling, no references to node names or graph internals.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class LogFindings(BaseModel):
    """Structured output from the log_detective worker."""

    summary: str = Field(description="Overall log analysis summary")
    qps_info: str = Field(default="No QPS data", description="QPS statistics: avg, peak, trend")
    error_rate: dict[str, Any] = Field(
        default_factory=dict,
        description="Error rate breakdown, e.g. {'4xx': '5%', '5xx': '2%'}",
    )
    top_errors: list[str] = Field(
        default_factory=list,
        description="Top 3-5 errors with status code, URL, and count",
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description="low=normal, medium=slight anomaly, high=clear anomaly, critical=severe fault",
    )
    analysis_text: str = Field(
        default="",
        description="Tool call chain log: tools called, status, and query rationale",
    )
    trend_comparison: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Historical trend comparison data "
            "(populated when query_es_trend_comparison is called)"
        ),
    )
    # Raw numeric fields — used by ThresholdPolicy.classify_logs() for deterministic risk_level.
    # Extractor should populate these when the agent's analysis text contains rate data.
    rate_5xx: float | None = Field(
        default=None,
        description="5xx error rate as a fraction (0.0–1.0), e.g. 0.02 for 2%",
    )
    rate_4xx: float | None = Field(
        default=None,
        description="4xx error rate as a fraction (0.0–1.0), e.g. 0.05 for 5%",
    )


class SecurityFindings(BaseModel):
    """Structured output from the security_guard worker."""

    summary: str = Field(description="Protection status summary (factual, no attack judgement)")
    cc_status: str = Field(default="unknown", description="CC protection status")
    ddos_status: str = Field(default="unknown", description="DDoS scrubbing status")
    protection_status: str = Field(default="unknown", description="Overall protection evaluation")
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description=(
            "low=protection normal, medium=some rules triggered, "
            "high=heavy triggering, critical=failed"
        ),
    )
    analysis_text: str = Field(default="", description="Tool call chain log")
    # Raw numeric/boolean fields — used by ThresholdPolicy.classify_security().
    cc_is_under_attack: bool | None = Field(
        default=None,
        description="True when CC tool reported is_under_attack=True for any IP",
    )
    ddos_exceeds_threshold: bool | None = Field(
        default=None,
        description="True when any DDoS event had exceeds_threshold=True",
    )
    cc_input_pps: int | None = Field(
        default=None,
        description="Highest input_pps value seen across all checked IPs",
    )
    ddos_event_count: int | None = Field(
        default=None,
        description="Total number of DDoS events returned by the API",
    )
    operational_issue: Literal["none", "coverage_gap", "integration_or_config_error"] = Field(
        default="none",
        description=(
            "Non-attack operational issue classification for the protection stack: "
            "none | coverage_gap | integration_or_config_error"
        ),
    )
    operational_issue_detail: str = Field(
        default="",
        description="Human-readable detail for coverage or integration/config issues.",
    )


class MachineFindings(BaseModel):
    """Structured output from the machine_check worker."""

    summary: str = Field(description="Infrastructure check summary")
    connectivity: str = Field(default="unknown", description="Ping/connectivity result")
    system_metrics: str = Field(default="no data", description="CPU/memory/disk summary")
    tcp_status: str = Field(default="no data", description="TCP connection state summary")
    health_status: Literal["healthy", "degraded", "unhealthy"] = Field(
        default="degraded",
        description="healthy=normal, degraded=mild load, unhealthy=severe overload or fault",
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description=(
            "low=system normal, medium=mild pressure, "
            "high=overloaded, critical=imminent crash"
        ),
    )
    analysis_text: str = Field(default="", description="Tool call chain log")
    # Raw numeric fields — used by ThresholdPolicy.classify_machine().
    # Values are fractions (0.0–1.0) for cpu_pct/memory_pct; integer for tcp_established.
    cpu_pct: float | None = Field(
        default=None,
        description="Peak CPU usage fraction (0.0–1.0), e.g. 0.87 for 87%",
    )
    memory_pct: float | None = Field(
        default=None,
        description="Peak memory usage fraction (0.0–1.0), e.g. 0.64 for 64%",
    )
    tcp_established: int | None = Field(
        default=None,
        description="Current number of established TCP connections",
    )
