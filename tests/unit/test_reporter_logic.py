"""
Unit tests for reporter node pure functions.

Tests _derive_risk_level, _parse_recommendations, and the artifact mapping
without invoking the LLM. Imports the private helpers directly.
"""
from __future__ import annotations

from runtime.artifacts.investigation import InvestigationArtifact
from runtime.graph.nodes.reporter import (
    _derive_risk_level,
    _format_asset_findings,
    _format_findings,
    _parse_recommendations,
)
from security.schemas.report import InvestigationReport

# ---------------------------------------------------------------------------
# _derive_risk_level
# ---------------------------------------------------------------------------


def test_derive_risk_level_normal():
    report = InvestigationReport(alert_status="normal")
    assert _derive_risk_level(report) == "low"


def test_derive_risk_level_warning():
    report = InvestigationReport(alert_status="warning")
    assert _derive_risk_level(report) == "medium"


def test_derive_risk_level_critical():
    report = InvestigationReport(alert_status="critical")
    assert _derive_risk_level(report) == "high"


def test_derive_risk_level_none_falls_back_to_medium():
    # alert_status field has default="warning" in the schema, but
    # _derive_risk_level guards with .get(..., "medium") for None
    report = InvestigationReport()
    # default alert_status is "warning" → "medium"
    assert _derive_risk_level(report) == "medium"


# ---------------------------------------------------------------------------
# _parse_recommendations
# ---------------------------------------------------------------------------


def test_parse_recommendations_none():
    assert _parse_recommendations(None) == []


def test_parse_recommendations_placeholder():
    assert _parse_recommendations("[requires analysis]") == []


def test_parse_recommendations_bracket_prefix():
    # Any text starting with "[" is treated as placeholder
    assert _parse_recommendations("[no data]") == []


def test_parse_recommendations_bullet_list():
    text = "• item one\n• item two\n• item three"
    result = _parse_recommendations(text)
    assert result == ["item one", "item two", "item three"]


def test_parse_recommendations_dash_list():
    text = "- check logs\n- restart service"
    result = _parse_recommendations(text)
    assert result == ["check logs", "restart service"]


def test_parse_recommendations_numbered_list():
    text = "1. First action\n2. Second action\n3. Third action"
    result = _parse_recommendations(text)
    assert result == ["First action", "Second action", "Third action"]


def test_parse_recommendations_strips_empty_lines():
    text = "• item one\n\n• item two\n\n"
    result = _parse_recommendations(text)
    assert result == ["item one", "item two"]


def test_parse_recommendations_single_line():
    text = "Just one recommendation"
    result = _parse_recommendations(text)
    assert result == ["Just one recommendation"]


def test_parse_recommendations_mixed_leading_chars():
    text = "* action A\n  - action B\n1. action C"
    result = _parse_recommendations(text)
    assert "action A" in result
    assert "action C" in result


def test_format_findings_empty():
    assert _format_findings({}) == "No findings collected."


def test_format_findings_sections():
    text = _format_findings({"logs": {"risk_level": "low"}, "security": {"risk_level": "high"}})
    assert "### LOGS FINDINGS" in text
    assert "### SECURITY FINDINGS" in text


def test_format_asset_findings_empty():
    assert _format_asset_findings({}) == "No asset-scoped findings collected."


def test_format_asset_findings_includes_asset_identity_and_worker_results():
    text = _format_asset_findings(
        {
            "GF:node_product:1.1.1.1": {
                "asset": {"ip": "1.1.1.1", "type": "node_product", "source": "GF"},
                "machine": {"summary": "healthy", "risk_level": "low"},
                "security": {"summary": "protected", "risk_level": "medium"},
            }
        }
    )
    assert "GF:node_product:1.1.1.1 | ip=1.1.1.1" in text
    assert "- machine:" in text
    assert "- security:" in text


# ---------------------------------------------------------------------------
# Artifact mapping (no LLM)
# ---------------------------------------------------------------------------


def test_artifact_risk_level_matches_derive():
    report = InvestigationReport(
        alert_status="critical",
        summary="System is under attack.",
        recommendations="Block offending IPs.\nEnable rate limiting.",
    )
    risk = _derive_risk_level(report)
    recs = _parse_recommendations(report.recommendations)

    artifact = InvestigationArtifact(
        session_id="test-session",
        target="1.2.3.4",
        findings={"security": {"has_attack": True}},
        asset_findings={"GF:product:1.2.3.4": {"security": {"risk_level": "high"}}},
        report=report.model_dump(mode="json"),
        risk_level=risk,
        summary=report.summary or "Investigation complete.",
        recommendations=recs,
    )

    assert artifact.risk_level == "high"
    assert artifact.summary == "System is under attack."
    assert "Block offending IPs." in artifact.recommendations


def test_artifact_summary_fallback():
    report = InvestigationReport(summary=None)
    summary = report.summary or "Investigation complete."
    assert summary == "Investigation complete."


def test_artifact_serialises_to_json():
    report = InvestigationReport(alert_status="normal", summary="All clear.")
    artifact = InvestigationArtifact(
        session_id="s1",
        target="example.com",
        report=report.model_dump(mode="json"),
        risk_level=_derive_risk_level(report),
        summary=report.summary or "Investigation complete.",
        recommendations=_parse_recommendations(report.recommendations),
    )
    d = artifact.model_dump(mode="json")
    assert d["artifact_type"] == "investigation"
    assert d["risk_level"] == "low"
    assert d["report"]["summary"] == "All clear."
    assert isinstance(d["created_at"], str)  # datetime serialised to ISO string
