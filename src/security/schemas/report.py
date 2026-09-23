"""
Report schemas — structured output for the reporter node.

Migrated and cleaned from KKShieldHelper-main/agents/report_schemas.py:
- Field names translated to English
- Feishu-specific framing removed from core schema
- Docstrings in English
- All fields Optional with sensible defaults (improves LLM structured-output reliability)

The Feishu surface adapter (surfaces/feishu/) is responsible for
translating InvestigationReport → Feishu card format.
CLAUDE.md hard rule 5: surface logic must not live in domain schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PerformanceMetrics(BaseModel):
    """Infrastructure performance snapshot."""

    cpu_usage: str | None = Field(default="unknown", description="CPU usage, e.g. '45%'")
    cpu_status: str | None = Field(
        default="normal",
        description="CPU assessment: 'normal' | 'elevated' | 'critical'",
    )
    memory_usage: str | None = Field(default="unknown", description="Memory usage, e.g. '67%'")
    memory_status: str | None = Field(
        default="normal",
        description="Memory assessment: 'normal' | 'elevated' | 'critical'",
    )
    disk_io: str | None = Field(default="unknown", description="Disk I/O, e.g. '23 MB/s'")
    disk_status: str | None = Field(
        default="normal",
        description="Disk assessment: 'normal' | 'elevated' | 'critical'",
    )
    tcp_connections: str | None = Field(
        default="unknown", description="TCP connection count, e.g. '1523'"
    )
    tcp_status: str | None = Field(
        default="normal",
        description="TCP assessment: 'normal' | 'elevated' | 'critical'",
    )


class NetworkMetrics(BaseModel):
    """Network connectivity snapshot."""

    avg_latency: str | None = Field(default="unknown", description="Average latency, e.g. '33ms'")
    packet_loss: str | None = Field(default="unknown", description="Packet loss, e.g. '0%'")
    ttl: str | None = Field(default="unknown", description="TTL value, e.g. '41'")


class SecurityMetrics(BaseModel):
    """CC/DDoS protection status snapshot."""

    has_cc_attack: bool | None = Field(
        default=None, description="True if a CC attack is currently detected"
    )
    cc_detail: str | None = Field(
        default="no attack detected",
        description="CC attack detail: PPS values, thresholds, attack flags",
    )
    has_ddos_attack: bool | None = Field(
        default=None, description="True if a DDoS event is detected within the query window"
    )
    ddos_detail: str | None = Field(
        default="no events recorded",
        description="DDoS event detail: bps values, event count, threshold comparison",
    )
    shielded_ip_count: int | None = Field(
        default=0, description="Number of IPs currently blocked by the protection system"
    )
    is_forbidden: bool | None = Field(
        default=False, description="True if all traffic to the target is blocked"
    )
    is_foreign_blocked: bool | None = Field(
        default=False, description="True if international traffic is blocked"
    )


class RequestMetrics(BaseModel):
    """Access-log request analysis snapshot."""

    request_count: str | None = Field(
        default="unknown", description="Total request count in the analysis window"
    )
    request_count_status: str | None = Field(
        default="[requires analysis]",
        description="Whether the request volume is normal, elevated, or anomalous",
    )
    top_ip: str | None = Field(
        default="not collected",
        description="Top client IP: address, request count, and share, e.g. '1.2.3.4 (1000, 8%)'",
    )
    top_ip_status: str | None = Field(
        default="insufficient data",
        description="Assessment of whether the top IP represents normal or suspicious behaviour",
    )
    top_ua: str | None = Field(
        default="not collected",
        description="Top User-Agent string, request count, and share",
    )
    top_ua_status: str | None = Field(
        default="insufficient data",
        description="Assessment of whether the User-Agent is normal browser traffic",
    )
    status_code_distribution: str | None = Field(
        default="not collected",
        description="HTTP status code breakdown, e.g. '200: 80%, 404: 10%, 502: 5%'",
    )
    status_code_status: str | None = Field(
        default="insufficient data",
        description="Assessment of whether the error-code distribution indicates an attack",
    )


class InvestigationReport(BaseModel):
    """
    Structured report produced by the reporter node.

    All fields are optional with safe defaults so that partial findings
    (e.g. only security data collected) still produce a valid report.
    """

    # Time window
    analysis_start: str | None = Field(
        default="unknown", description="Start of the analysis window, ISO-8601 or human-readable"
    )
    analysis_end: str | None = Field(
        default="unknown", description="End of the analysis window"
    )

    # Overall verdict
    alert_status: Literal["normal", "warning", "critical"] | None = Field(
        default="warning",
        description="Overall investigation status: 'normal' | 'warning' | 'critical'",
    )
    summary: str | None = Field(
        default="[requires analysis]",
        description="One-sentence overall conclusion based on collected findings",
    )
    recommendations: str | None = Field(
        default="[requires analysis]",
        description="2–4 prioritised, executable recommendations",
    )

    # Per-dimension findings
    performance_has_issue: bool = Field(
        default=False, description="True if infrastructure shows anomaly"
    )
    performance_conclusion: str | None = Field(
        default="[requires analysis]",
        description="One-sentence infrastructure health conclusion (≤ 30 words)",
    )
    performance_metrics: PerformanceMetrics | None = None

    network_has_issue: bool = Field(default=False, description="True if connectivity shows anomaly")
    network_conclusion: str | None = Field(
        default="[requires analysis]",
        description="One-sentence network connectivity conclusion (≤ 30 words)",
    )
    network_metrics: NetworkMetrics | None = None

    security_has_issue: bool = Field(
        default=False, description="True if an active attack is detected"
    )
    security_conclusion: str | None = Field(
        default="[requires analysis]",
        description="One-sentence security protection conclusion (≤ 30 words)",
    )
    security_metrics: SecurityMetrics | None = None

    request_conclusion: str | None = Field(
        default="[requires analysis]",
        description="One-sentence access-log analysis conclusion (≤ 30 words)",
    )
    request_metrics: RequestMetrics | None = None

    # Root cause
    root_cause: str | None = Field(
        default="[requires analysis]",
        description=(
            "Root-cause analysis (≤ 200 words). "
            "Distinguish: normal load / attack traffic / infrastructure failure / config issue."
        ),
    )
