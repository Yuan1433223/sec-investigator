"""Unit tests for Grafana webhook schema parsing."""
import json

import pytest
from pydantic import ValidationError

from kks_surfaces.webhook.schemas import GrafanaAlert, GrafanaWebhook

# ---------------------------------------------------------------------------
# Minimal valid fixture
# ---------------------------------------------------------------------------

_WEBHOOK_JSON = {
    "receiver": "kks-next",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "HighCPU", "entity": "10.0.0.1"},
            "annotations": {"summary": "CPU too high"},
            "startsAt": "2026-01-01T12:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://grafana/alert/1",
            "fingerprint": "abc123",
        }
    ],
    "groupLabels": {"alertname": "HighCPU"},
    "commonLabels": {"env": "prod"},
    "commonAnnotations": {},
    "externalURL": "http://grafana",
    "version": "1",
    "groupKey": "{}:{alertname='HighCPU'}",
}


# ---------------------------------------------------------------------------
# GrafanaAlert
# ---------------------------------------------------------------------------


def test_grafana_alert_parse_required_fields():
    alert = GrafanaAlert(**_WEBHOOK_JSON["alerts"][0])
    assert alert.status == "firing"
    assert alert.labels["entity"] == "10.0.0.1"
    assert alert.fingerprint == "abc123"


def test_grafana_alert_optional_fields_default_none():
    alert = GrafanaAlert(
        status="firing",
        labels={},
        annotations={},
        startsAt="2026-01-01T00:00:00Z",
        endsAt="2026-01-01T00:00:00Z",
        generatorURL="http://g",
    )
    assert alert.fingerprint is None
    assert alert.dashboardURL is None
    assert alert.panelURL is None
    assert alert.values is None


def test_grafana_alert_extra_fields_allowed():
    data = dict(_WEBHOOK_JSON["alerts"][0], unknownField="x")
    alert = GrafanaAlert(**data)
    assert alert.status == "firing"


def test_grafana_alert_missing_required_raises():
    with pytest.raises(ValidationError):
        GrafanaAlert(status="firing")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# GrafanaWebhook
# ---------------------------------------------------------------------------


def test_grafana_webhook_parse_full():
    wh = GrafanaWebhook(**_WEBHOOK_JSON)
    assert wh.status == "firing"
    assert len(wh.alerts) == 1
    assert wh.alerts[0].labels["alertname"] == "HighCPU"


def test_grafana_webhook_optional_fields_none():
    wh = GrafanaWebhook(**_WEBHOOK_JSON)
    assert wh.orgId is None
    assert wh.title is None
    assert wh.message is None
    assert wh.truncatedAlerts is None


def test_grafana_webhook_multiple_alerts():
    data = dict(_WEBHOOK_JSON)
    data["alerts"] = [data["alerts"][0], dict(data["alerts"][0], status="resolved")]
    wh = GrafanaWebhook(**data)
    assert len(wh.alerts) == 2
    assert wh.alerts[1].status == "resolved"


def test_grafana_webhook_from_json_string():
    raw = json.dumps(_WEBHOOK_JSON)
    wh = GrafanaWebhook.model_validate_json(raw)
    assert wh.receiver == "kks-next"


def test_grafana_webhook_extra_fields_allowed():
    data = dict(_WEBHOOK_JSON, someNewGrafanaField="v2")
    wh = GrafanaWebhook(**data)
    assert wh.status == "firing"
