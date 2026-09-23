"""
Feishu robot delivery adapter.

Translates InvestigationReport (from security.schemas.report) into a
Feishu robot webhook message payload using plain markdown — no Feishu card
template IDs (those are deployment details, not product code).

CLAUDE.md hard rule 5: surface delivery logic must not live in domain schemas.
"""
from __future__ import annotations

import httpx

from security.schemas.report import InvestigationReport

_STATUS_EMOJI = {
    "normal": "✅",
    "warning": "⚠️",
    "critical": "🔴",
}


def report_to_feishu_payload(report: InvestigationReport, entity: str) -> dict:
    """
    Build a Feishu interactive card payload from an InvestigationReport.

    Returns a dict suitable for POST to a Feishu robot webhook URL.
    Uses msg_type="interactive" with a simple markdown card body.
    """
    status = report.alert_status or "warning"
    emoji = _STATUS_EMOJI.get(status, "ℹ️")
    title = f"{emoji} Investigation: {entity} [{status.upper()}]"

    lines: list[str] = []

    # Summary
    if report.summary:
        lines += [f"**Summary**\n{report.summary}", ""]

    # Per-dimension conclusions
    dimensions = [
        ("Performance", report.performance_conclusion, report.performance_has_issue),
        ("Network", report.network_conclusion, report.network_has_issue),
        ("Security", report.security_conclusion, report.security_has_issue),
        ("Requests", report.request_conclusion, False),
    ]
    for label, conclusion, has_issue in dimensions:
        if conclusion and conclusion != "[requires analysis]":
            indicator = "⚠️" if has_issue else "✅"
            lines.append(f"**{label}** {indicator}: {conclusion}")

    lines.append("")

    # Root cause
    if report.root_cause and report.root_cause != "[requires analysis]":
        lines += [f"**Root Cause**\n{report.root_cause}", ""]

    # Recommendations
    if report.recommendations and report.recommendations != "[requires analysis]":
        lines += [f"**Recommendations**\n{report.recommendations}", ""]

    body_text = "\n".join(lines).strip()

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": _card_color(status),
            },
            "elements": [
                {"tag": "markdown", "content": body_text},
            ],
        },
    }


def _card_color(status: str) -> str:
    return {"normal": "green", "warning": "yellow", "critical": "red"}.get(status, "blue")


async def send_report_to_feishu(
    webhook_url: str,
    report: InvestigationReport,
    entity: str,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """
    POST an InvestigationReport as a Feishu card to the given webhook URL.

    Returns True on HTTP 200, False otherwise.
    Caller owns the http_client lifecycle if provided.
    """
    payload = report_to_feishu_payload(report, entity)
    _owner = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10)
    try:
        resp = await client.post(webhook_url, json=payload)
        return resp.status_code == 200
    finally:
        if _owner:
            await client.aclose()
