"""
Reporter node — synthesises collected findings into an InvestigationReport.

Replaces the Phase 1 stub (which always wrote risk_level="low" with a placeholder
summary). Now uses the REPORT_GENERATION playbook and the REPORT_WRITER model
profile to produce a structured InvestigationReport.

Feishu delivery is the responsibility of the surface layer (surfaces/feishu/).
This node emits FinalEvent with the artifact; surfaces subscribe and deliver.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from runtime.artifacts.investigation import InvestigationArtifact
from runtime.events.protocol import ArtifactEvent, FinalEvent, StatusEvent
from runtime.llm.profiles import build_model
from runtime.state.session import SessionState
from security.playbooks.catalog import PlaybookKind, get_playbook
from security.schemas.report import InvestigationReport

logger = logging.getLogger(__name__)

_PLAYBOOK = get_playbook(PlaybookKind.REPORT_GENERATION)


async def reporter_node(state: SessionState) -> dict:
    """
    Terminal node — synthesises all findings into an InvestigationReport artifact.

    Emits ArtifactEvent + FinalEvent via stream writer. Feishu delivery is
    handled by the surface layer after the graph completes.
    """
    write = get_stream_writer()
    write(StatusEvent(node="reporter", message="Generating investigation report..."))

    findings = state.get("findings", {})
    asset_findings = state.get("asset_findings", {})
    target = state.get("target", "unknown")
    session_id = state.get("session_id", "")

    findings_text = _format_findings(findings)
    asset_findings_text = _format_asset_findings(asset_findings)

    user_message = (
        f"Target: {target}\n\n"
        f"Collected findings:\n\n{findings_text}\n\n"
        f"Asset-scoped findings:\n\n{asset_findings_text}\n\n"
        "Generate the investigation report."
    )

    llm = build_model(_PLAYBOOK.model_profile)
    report: InvestigationReport = await llm.with_structured_output(InvestigationReport, method="function_calling").ainvoke(
        [
            SystemMessage(content=_PLAYBOOK.system_prompt),
            HumanMessage(content=user_message),
        ]
    )

    # Map structured report → InvestigationArtifact (runtime-layer type)
    risk_level = _derive_risk_level(report)
    artifact = InvestigationArtifact(
        session_id=session_id,
        target=target,
        findings=findings,
        asset_findings=asset_findings,
        report=report.model_dump(mode="json"),
        risk_level=risk_level,
        summary=report.summary or "Investigation complete.",
        recommendations=_parse_recommendations(report.recommendations),
    )

    artifact_dict = artifact.model_dump(mode="json")
    write(ArtifactEvent(artifact_type="investigation", data=artifact_dict))
    write(FinalEvent(findings=findings, artifacts=[artifact_dict]))
    write(StatusEvent(node="reporter", message="Report generation complete"))

    return {
        "artifacts": [artifact_dict],
        "status": "completed",
    }


def _derive_risk_level(report: InvestigationReport) -> str:
    """Map alert_status to InvestigationArtifact risk_level vocabulary."""
    mapping = {"normal": "low", "warning": "medium", "critical": "high"}
    return mapping.get(report.alert_status or "warning", "medium")


def _format_findings(findings: dict) -> str:
    """Serialize target-scoped findings into a stable prompt block."""
    if not findings:
        return "No findings collected."
    sections = [
        f"### {key.upper()} FINDINGS\n{value}"
        for key, value in findings.items()
    ]
    return "\n\n".join(sections)


def _format_asset_findings(asset_findings: dict) -> str:
    """Serialize asset-scoped findings into a concise, report-friendly block."""
    if not asset_findings:
        return "No asset-scoped findings collected."

    sections: list[str] = []
    for asset_id, payload in asset_findings.items():
        asset = payload.get("asset", {}) if isinstance(payload, dict) else {}
        header = (
            f"{asset_id} | ip={asset.get('ip', 'unknown')} "
            f"type={asset.get('type', 'unknown')} source={asset.get('source', 'unknown')}"
        )
        details = []
        for key, value in payload.items():
            if key == "asset":
                continue
            details.append(f"- {key}: {value}")
        body = "\n".join(details) or "- no worker findings"
        sections.append(f"### {header}\n{body}")
    return "\n\n".join(sections)


def _parse_recommendations(text: str | None) -> list[str]:
    """Split recommendations text into a list of individual items."""
    if not text or text.startswith("["):
        return []
    lines = [line.lstrip("•-*0123456789. ").strip() for line in text.splitlines()]
    return [line for line in lines if line]
