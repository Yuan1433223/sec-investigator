"""
Unit tests for reporter node pure functions.

Tests _derive_risk_level, _parse_recommendations, and the artifact mapping
without invoking the LLM. Imports the private helpers directly.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runtime.artifacts.investigation import InvestigationArtifact
from runtime.graph.nodes.reporter import (
    _degraded_report,  # backward-compat alias for _deterministic_report
    _derive_risk_level,
    _deterministic_report,
    _extract_report,
    _format_asset_findings,
    _format_findings,
    _has_real_content,
    _parse_recommendations,
    reporter_node,
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
    assert "### logs 发现" in text
    assert "### security 发现" in text


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
        summary=report.summary or "调查完成。",
        recommendations=recs,
    )

    assert artifact.risk_level == "high"
    assert artifact.summary == "System is under attack."
    assert "Block offending IPs." in artifact.recommendations


def test_artifact_summary_fallback():
    report = InvestigationReport(summary=None)
    summary = report.summary or "调查完成。"
    assert summary == "调查完成。"


def test_artifact_serialises_to_json():
    report = InvestigationReport(alert_status="normal", summary="All clear.")
    artifact = InvestigationArtifact(
        session_id="s1",
        target="example.com",
        report=report.model_dump(mode="json"),
        risk_level=_derive_risk_level(report),
        summary=report.summary or "调查完成。",
        recommendations=_parse_recommendations(report.recommendations),
    )
    d = artifact.model_dump(mode="json")
    assert d["artifact_type"] == "investigation"
    assert d["risk_level"] == "low"
    assert d["report"]["summary"] == "All clear."
    assert isinstance(d["created_at"], str)  # datetime serialised to ISO string

# ---------------------------------------------------------------------------
# reporter_node graceful degradation on failed structured extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reporter_node_degrades_when_report_is_none():
    """Structured extraction returning None → deterministic report from findings."""
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = MagicMock(
        ainvoke=AsyncMock(return_value=None)
    )

    events: list = []
    fake_writer = lambda ev: events.append(ev)  # noqa: E731

    with (
        patch("runtime.graph.nodes.reporter.get_stream_writer", return_value=fake_writer),
        patch("runtime.graph.nodes.reporter.build_model", return_value=mock_model),
    ):
        result = await reporter_node(
            {
                "target": "example.com",
                "session_id": "s1",
                "findings": {"logs": {"risk_level": "high", "summary": "5xx 突增"}},
                "asset_findings": {},
            }
        )

    artifact = result["artifacts"][0]
    assert result["status"] == "completed"
    # deterministic report: logs high → warning alert → medium risk
    assert artifact["risk_level"] == "medium"
    # summary contains real findings data, not "报告生成失败" placeholder
    assert "报告生成失败" not in artifact["summary"]
    assert "5xx 突增" in artifact["summary"]
    # status event says "deterministic report" not "degraded report"
    assert any("deterministic report" in getattr(ev, "message", "") for ev in events)


@pytest.mark.asyncio
async def test_reporter_node_degrades_when_report_wrong_type():
    """A raw dict (non-conforming extraction) must also degrade, not crash."""
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = MagicMock(
        ainvoke=AsyncMock(return_value={"summary": "not a pydantic model"})
    )

    with (
        patch("runtime.graph.nodes.reporter.get_stream_writer", return_value=lambda _: None),
        patch("runtime.graph.nodes.reporter.build_model", return_value=mock_model),
    ):
        result = await reporter_node(
            {
                "target": "example.com",
                "session_id": "s1",
                "findings": {},
                "asset_findings": {},
            }
        )

    assert result["status"] == "completed"
    # empty findings → deterministic report → normal alert
    assert result["artifacts"][0]["report"]["alert_status"] == "normal"


def test_deterministic_report_empty_findings():
    """Empty findings → normal alert, summary says no data collected."""
    report = _deterministic_report("example.com", {})
    assert report.alert_status == "normal"
    assert "未采集到数据" in report.summary
    assert report.root_cause


def test_deterministic_report_logs_critical():
    """logs critical with 5xx rate → critical alert, 5xx recommendations."""
    report = _deterministic_report("api2.xs2027.cn", {
        "logs": {
            "risk_level": "critical",
            "summary": "5xx 错误率突增",
            "error_rate": {"5xx": "70.0%", "4xx": "0.0%"},
            "rate_5xx": 0.70,
            "rate_4xx": 0.0,
        },
    })
    assert report.alert_status == "critical"
    assert "70.0%" in report.summary
    assert "5xx" in report.recommendations
    assert "源站应用" in report.recommendations
    assert "5xx" in report.root_cause


def test_deterministic_report_logs_4xx_high():
    """logs high with 4xx rate → warning alert, 4xx recommendations."""
    report = _deterministic_report("game.ali213.net", {
        "logs": {
            "risk_level": "high",
            "summary": "4xx 流量异常",
            "error_rate": {"4xx": "83.0%"},
            "rate_4xx": 0.83,
        },
    })
    assert report.alert_status == "warning"
    assert "83.0%" in report.summary
    assert "爬虫" in report.recommendations


# ---------------------------------------------------------------------------
# _has_real_content — empty-shell detection
# ---------------------------------------------------------------------------


def test_has_real_content_default_report_is_shell():
    """A bare InvestigationReport() with all schema defaults is an empty shell."""
    report = InvestigationReport()
    assert _has_real_content(report) is False


def test_has_real_content_placeholder_summary_and_recs():
    """summary and recommendations both on '[requires analysis]' → shell."""
    report = InvestigationReport(
        summary="[requires analysis]",
        recommendations="[requires analysis]",
    )
    assert _has_real_content(report) is False


def test_has_real_content_real_summary():
    """Real summary text → has content even if recommendations is placeholder."""
    report = InvestigationReport(
        summary="5xx 错误率 70%，源站故障。",
        recommendations="[requires analysis]",
    )
    assert _has_real_content(report) is True


def test_has_real_content_real_recommendations():
    """Real recommendations → has content even if summary is placeholder."""
    report = InvestigationReport(
        summary="[requires analysis]",
        recommendations="1. 重启源站\n2. 检查后端服务",
    )
    assert _has_real_content(report) is True


def test_has_real_content_both_real():
    report = InvestigationReport(
        summary="源站 5xx 故障。",
        recommendations="1. 重启服务",
    )
    assert _has_real_content(report) is True


# ---------------------------------------------------------------------------
# _extract_report — empty-shell falls through to next layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_report_shell_l1_falls_through_to_l2():
    """L1 returns a pydantic-valid but shell report → fall through to L2."""
    shell = InvestigationReport()  # all defaults = shell
    real = InvestigationReport(
        summary="真实摘要",
        recommendations="1. 行动",
    )

    mock_model = MagicMock()
    # L1 returns shell
    mock_model.with_structured_output.side_effect = [
        MagicMock(ainvoke=AsyncMock(return_value=shell)),
        MagicMock(ainvoke=AsyncMock(return_value=real)),
    ]

    events: list = []
    result = await _extract_report(mock_model, [], lambda ev: events.append(ev))
    assert result is real
    # L2 emitted the "json_mode" status
    assert any("json_mode" in getattr(ev, "message", "") for ev in events)


@pytest.mark.asyncio
async def test_extract_report_all_shell_returns_none():
    """All three layers return shells → None → degraded report."""
    shell = InvestigationReport()

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = MagicMock(
        ainvoke=AsyncMock(return_value=shell)
    )
    mock_model.ainvoke = AsyncMock(return_value=MagicMock(content="no json here"))

    result = await _extract_report(mock_model, [], lambda ev: None)
    assert result is None

