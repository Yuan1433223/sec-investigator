"""Unit tests for Feishu delivery adapter."""

from security.schemas.report import InvestigationReport
from surfaces.feishu.delivery import report_to_feishu_payload


def _make_report(**kwargs) -> InvestigationReport:
    defaults = {
        "alert_status": "warning",
        "summary": "System is experiencing elevated error rates.",
        "recommendations": "Check the application logs and restart if necessary.",
        "root_cause": "Traffic spike caused 502 errors on the upstream.",
        "performance_conclusion": "CPU and memory are normal.",
        "security_conclusion": "No active attack detected.",
        "network_conclusion": "Connectivity is stable.",
        "request_conclusion": "Error rate is 8%, above normal.",
    }
    defaults.update(kwargs)
    return InvestigationReport(**defaults)


# ---------------------------------------------------------------------------
# report_to_feishu_payload structure
# ---------------------------------------------------------------------------


def test_payload_has_msg_type_interactive():
    payload = report_to_feishu_payload(_make_report(), "example.com")
    assert payload["msg_type"] == "interactive"


def test_payload_has_card_key():
    payload = report_to_feishu_payload(_make_report(), "example.com")
    assert "card" in payload


def test_card_has_header():
    card = report_to_feishu_payload(_make_report(), "example.com")["card"]
    assert "header" in card
    assert "title" in card["header"]


def test_card_title_contains_entity():
    card = report_to_feishu_payload(_make_report(), "1.2.3.4")["card"]
    title_text = card["header"]["title"]["content"]
    assert "1.2.3.4" in title_text


def test_card_title_contains_status():
    card = report_to_feishu_payload(_make_report(alert_status="critical"), "x.com")["card"]
    title_text = card["header"]["title"]["content"]
    assert "CRITICAL" in title_text


def test_card_has_elements():
    card = report_to_feishu_payload(_make_report(), "example.com")["card"]
    assert len(card["elements"]) >= 1


def test_card_body_contains_summary():
    card = report_to_feishu_payload(_make_report(), "example.com")["card"]
    body = card["elements"][0]["content"]
    assert "System is experiencing" in body


def test_card_body_contains_recommendations():
    card = report_to_feishu_payload(_make_report(), "example.com")["card"]
    body = card["elements"][0]["content"]
    assert "restart if necessary" in body


def test_card_body_contains_root_cause():
    card = report_to_feishu_payload(_make_report(), "example.com")["card"]
    body = card["elements"][0]["content"]
    assert "Traffic spike" in body


# ---------------------------------------------------------------------------
# Card color by alert_status
# ---------------------------------------------------------------------------


def test_normal_status_gives_green_card():
    card = report_to_feishu_payload(_make_report(alert_status="normal"), "x")["card"]
    assert card["header"]["template"] == "green"


def test_warning_status_gives_yellow_card():
    card = report_to_feishu_payload(_make_report(alert_status="warning"), "x")["card"]
    assert card["header"]["template"] == "yellow"


def test_critical_status_gives_red_card():
    card = report_to_feishu_payload(_make_report(alert_status="critical"), "x")["card"]
    assert card["header"]["template"] == "red"


def test_unknown_status_gives_blue_card():
    """An unrecognised status string falls back to blue."""
    from surfaces.feishu.delivery import _card_color

    assert _card_color("something_else") == "blue"


# ---------------------------------------------------------------------------
# Minimal report (sparse findings)
# ---------------------------------------------------------------------------


def test_minimal_report_still_produces_valid_payload():
    report = InvestigationReport()
    payload = report_to_feishu_payload(report, "unknown")
    assert payload["msg_type"] == "interactive"
    assert "card" in payload
