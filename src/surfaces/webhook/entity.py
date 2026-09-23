"""
Entity extraction helpers for Grafana alerts.

Ported from KKShieldHelper-main/logic/alert_handler.py — clean subset only:
- extract_entity(alert) → str | None
- detect_entity_type(alertname, labels) → "domain" | "node" | "unknown"
- build_investigation_question(entity, alerts) → str

No Redis, no chart rendering, no comparison logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from surfaces.webhook.schemas import GrafanaAlert

# Ordered fallback label keys when "entity" label is absent.
_FALLBACK_LABELS = [
    "server_name",
    "server_addr",
    "instance",
    "hostname",
    "ip",
    "target",
]

_INVALID_ENTITY_VALUES = {"[no value]", "", "null", "none"}

# Keywords that indicate domain vs node entity type, matched case-insensitively.
_DOMAIN_KEYWORDS = {"域名", "website", "server_name", "domain"}
_NODE_KEYWORDS = {"节点", "node", "server_addr", "instance", "主机", "服务器"}


def extract_entity(alert: GrafanaAlert) -> str | None:
    """
    Extract the investigation entity from a single Grafana alert.

    Priority:
    1. The "entity" label (recommended Grafana configuration)
    2. Fallback labels in _FALLBACK_LABELS order
    3. None if no valid entity is found
    """
    entity = alert.labels.get("entity")

    if entity is not None:
        if entity.strip().lower() in _INVALID_ENTITY_VALUES:
            return None
        return entity.strip()

    for key in _FALLBACK_LABELS:
        value = alert.labels.get(key)
        if value and value.strip().lower() not in _INVALID_ENTITY_VALUES:
            return value.strip()

    return None


def detect_entity_type(
    alertname: str, labels: dict
) -> Literal["domain", "node", "unknown"]:
    """
    Classify the entity as a domain, node, or unknown.

    Checks alertname keywords first, then label presence.
    """
    name_lower = alertname.lower()

    for kw in _DOMAIN_KEYWORDS:
        if kw in name_lower:
            return "domain"

    for kw in _NODE_KEYWORDS:
        if kw in name_lower:
            return "node"

    if labels.get("server_name"):
        return "domain"
    if labels.get("server_addr") or labels.get("instance"):
        return "node"

    return "unknown"


def build_investigation_question(entity: str, alerts: list[GrafanaAlert]) -> str:
    """
    Build the investigation question string passed as `target` to the graph.

    Aggregates all alertnames for the entity and includes the time window.
    """
    if not alerts:
        return f"Entity: {entity} — no alert details available, please inspect."

    alertnames = ", ".join(
        a.labels.get("alertname", "unknown alert") for a in alerts
    )

    start_time = datetime.fromisoformat(alerts[0].startsAt)
    window_start = start_time - timedelta(minutes=15)
    window_end = start_time + timedelta(minutes=3)

    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        f"Entity: {entity}, "
        f"Alerts: {alertnames}, "
        f"Window: {window_start.strftime(fmt)} to {window_end.strftime(fmt)}, "
        f"please investigate and analyse the root cause."
    )
