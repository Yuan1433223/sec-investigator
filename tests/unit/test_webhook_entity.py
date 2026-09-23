"""Unit tests for webhook entity extraction helpers."""
from datetime import UTC, datetime

from surfaces.webhook.entity import (
    build_investigation_question,
    detect_entity_type,
    extract_entity,
)
from surfaces.webhook.schemas import GrafanaAlert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC).isoformat()


def _alert(labels: dict, starts_at: str = _NOW) -> GrafanaAlert:
    return GrafanaAlert(
        status="firing",
        labels=labels,
        annotations={},
        startsAt=starts_at,
        endsAt=starts_at,
        generatorURL="http://example.com",
    )


# ---------------------------------------------------------------------------
# extract_entity
# ---------------------------------------------------------------------------


def test_extract_entity_uses_entity_label():
    alert = _alert({"entity": "example.com"})
    assert extract_entity(alert) == "example.com"


def test_extract_entity_strips_whitespace():
    alert = _alert({"entity": "  1.2.3.4  "})
    assert extract_entity(alert) == "1.2.3.4"


def test_extract_entity_rejects_no_value():
    alert = _alert({"entity": "[no value]"})
    assert extract_entity(alert) is None


def test_extract_entity_rejects_empty_string():
    alert = _alert({"entity": ""})
    assert extract_entity(alert) is None


def test_extract_entity_fallback_server_name():
    alert = _alert({"server_name": "www.example.com"})
    assert extract_entity(alert) == "www.example.com"


def test_extract_entity_fallback_instance():
    alert = _alert({"instance": "10.0.0.1:9090"})
    assert extract_entity(alert) == "10.0.0.1:9090"


def test_extract_entity_prefers_entity_over_fallback():
    alert = _alert({"entity": "real.com", "server_name": "fallback.com"})
    assert extract_entity(alert) == "real.com"


def test_extract_entity_none_when_no_labels():
    alert = _alert({})
    assert extract_entity(alert) is None


# ---------------------------------------------------------------------------
# detect_entity_type
# ---------------------------------------------------------------------------


def test_detect_domain_by_alertname_keyword():
    assert detect_entity_type("domain traffic spike", {}) == "domain"


def test_detect_node_by_alertname_keyword():
    assert detect_entity_type("node cpu high", {}) == "node"


def test_detect_domain_by_server_name_label():
    assert detect_entity_type("generic alert", {"server_name": "x.com"}) == "domain"


def test_detect_node_by_server_addr_label():
    assert detect_entity_type("generic alert", {"server_addr": "10.0.0.1"}) == "node"


def test_detect_node_by_instance_label():
    assert detect_entity_type("generic alert", {"instance": "host:9100"}) == "node"


def test_detect_unknown_fallback():
    assert detect_entity_type("DatasourceNoData", {}) == "unknown"


# ---------------------------------------------------------------------------
# build_investigation_question
# ---------------------------------------------------------------------------


def test_build_question_contains_entity():
    alerts = [_alert({"alertname": "High CPU"}, starts_at="2026-01-01T12:00:00+00:00")]
    q = build_investigation_question("example.com", alerts)
    assert "example.com" in q


def test_build_question_contains_alertname():
    alerts = [_alert({"alertname": "High CPU"}, starts_at="2026-01-01T12:00:00+00:00")]
    q = build_investigation_question("example.com", alerts)
    assert "High CPU" in q


def test_build_question_contains_time_window():
    alerts = [_alert({"alertname": "X"}, starts_at="2026-01-01T12:00:00+00:00")]
    q = build_investigation_question("example.com", alerts)
    # Window starts 15 min before: 11:45
    assert "11:45" in q


def test_build_question_no_alerts_fallback():
    q = build_investigation_question("example.com", [])
    assert "example.com" in q
    assert "no alert" in q.lower()


def test_build_question_multiple_alertnames():
    alerts = [
        _alert({"alertname": "Alert1"}, starts_at="2026-01-01T12:00:00+00:00"),
        _alert({"alertname": "Alert2"}, starts_at="2026-01-01T12:00:00+00:00"),
    ]
    q = build_investigation_question("host", alerts)
    assert "Alert1" in q
    assert "Alert2" in q
