from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InvestigationArtifact(BaseModel):
    artifact_type: Literal["investigation"] = "investigation"
    session_id: str
    target: str
    findings: dict[str, Any] = Field(default_factory=dict)
    asset_findings: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"]
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportArtifact(BaseModel):
    artifact_type: Literal["report"] = "report"
    session_id: str
    target: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
