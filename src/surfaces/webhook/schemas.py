"""
Grafana webhook schemas.

Clean migration from KKShieldHelper-main/models/grafana.py:
- Removed Chinese comments
- Retained extra="allow" for forward-compatibility with Grafana schema changes
- orgId, title, message, truncatedAlerts are optional (not always present)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GrafanaAlert(BaseModel):
    model_config = {"extra": "allow"}

    status: str
    labels: dict[str, Any]
    annotations: dict[str, str]
    startsAt: str
    endsAt: str
    generatorURL: str
    fingerprint: str | None = None
    silenceURL: str | None = None
    dashboardURL: str | None = None
    panelURL: str | None = None
    values: dict[str, Any] | None = None


class GrafanaWebhook(BaseModel):
    model_config = {"extra": "allow"}

    receiver: str
    status: str
    alerts: list[GrafanaAlert]
    groupLabels: dict[str, Any]
    commonLabels: dict[str, Any]
    commonAnnotations: dict[str, str]
    externalURL: str
    version: str
    groupKey: str
    orgId: int | None = None
    title: str | None = None
    message: str | None = None
    truncatedAlerts: int | None = None
