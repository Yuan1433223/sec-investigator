"""
Reporter node — synthesises collected findings into an InvestigationReport.

Replaces the Phase 1 stub (which always wrote risk_level="low" with a placeholder
summary). Now uses the REPORT_GENERATION playbook and the REPORT_WRITER model
profile to produce a structured InvestigationReport.

Feishu delivery is the responsibility of the surface layer (surfaces/feishu/).
This node emits FinalEvent with the artifact; surfaces subscribe and deliver.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

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
        f"目标: {target}\n\n"
        f"已收集的分项发现:\n\n{findings_text}\n\n"
        f"资产维度发现:\n\n{asset_findings_text}\n\n"
        "请用简体中文撰写整份调查报告（含摘要、告警状态、各维度结论与根因分析）。"
    )

    llm = build_model(_PLAYBOOK.model_profile)
    messages = [
        SystemMessage(content=_PLAYBOOK.system_prompt),
        HumanMessage(content=user_message),
    ]

    report: InvestigationReport | None = await _extract_report(llm, messages, write)

    if report is None:
        # All structured-extraction channels returned shells or failed.
        # Deterministic fallback: synthesize a real report from collected findings
        # rather than emitting a "generation failed" placeholder.
        write(StatusEvent(node="reporter", message="Model structured output unavailable; emitting deterministic report"))
        report = _deterministic_report(target, findings)

    # The model writes explanations; aggregate severity stays code-controlled.
    risk_level = _findings_risk_level(findings)
    report.alert_status = _risk_to_alert_status(risk_level)
    window = state.get("analysis_window")
    if window:
        report.analysis_start = window["start"]
        report.analysis_end = window["end"]
    artifact = InvestigationArtifact(
        session_id=session_id,
        target=target,
        findings=findings,
        asset_findings=asset_findings,
        report=report.model_dump(mode="json"),
        risk_level=risk_level,
        summary=report.summary or "调查完成。",
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


async def _extract_report(llm: Any, messages: list, write: Any) -> InvestigationReport | None:
    """Three-layer structured-extraction ladder. Each layer falls through on any
    failure (None, wrong type, empty-shell placeholder, exception) instead of
    crashing the investigation.

      L1: function_calling (native tool/function structured output)
      L2: json_mode (response_format json_object — works on OpenAI-compatible relays)
      L3: raw text → regex-isolate the JSON object → pydantic validate
    """
    # L1 — function calling
    try:
        out = await llm.with_structured_output(
            InvestigationReport, method="function_calling"
        ).ainvoke(messages)
        if isinstance(out, InvestigationReport) and _has_real_content(out):
            return out
    except Exception as exc:  # noqa: BLE001 - any relay quirk → next layer
        logger.warning("reporter L1 function_calling failed: %s", exc)

    # L2 — json mode
    try:
        out = await llm.with_structured_output(
            InvestigationReport, method="json_mode"
        ).ainvoke(messages)
        if isinstance(out, InvestigationReport) and _has_real_content(out):
            write(StatusEvent(node="reporter", message="Structured report via json_mode"))
            return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("reporter L2 json_mode failed: %s", exc)

    # L3 — raw text → JSON object → pydantic
    try:
        resp = await llm.ainvoke(messages)
        text = getattr(resp, "content", None) or str(resp)
        obj_text = _extract_json_object(text)
        if obj_text:
            data = json.loads(obj_text)
            report = InvestigationReport.model_validate(data)
            if _has_real_content(report):
                write(StatusEvent(node="reporter", message="Structured report parsed from raw JSON"))
                return report
    except Exception as exc:  # noqa: BLE001
        logger.warning("reporter L3 raw-json parse failed: %s", exc)

    return None


def _has_real_content(report: InvestigationReport) -> bool:
    """Return True when summary and recommendations carry real (non-placeholder) text.

    The schema defaults every string field to "[requires analysis]" and alert_status
    to "warning". A relay that returns a syntactically valid but semantically empty
    JSON (all fields on defaults) passes pydantic validation but produces a misleading
    report. Treat such shells as extraction failure so the ladder falls through.
    """
    placeholders = {"", None, "[requires analysis]", "unknown", "insufficient data", "not collected"}

    def _is_placeholder(v: Any) -> bool:
        if v is None:
            return True
        s = str(v).strip()
        return s in placeholders

    # summary and recommendations are the two user-facing headline fields.
    # If both are placeholders, the report is an empty shell.
    return not (_is_placeholder(report.summary) and _is_placeholder(report.recommendations))


def _extract_json_object(text: str) -> str | None:
    """Isolate the first balanced-ish JSON object from model text output."""
    if not text:
        return None
    # fenced ```json ... ``` block first
    fenced = re.search(r"```(?:json|JSON)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return None


def _derive_risk_level(report: InvestigationReport) -> str:
    """Map alert_status to InvestigationArtifact risk_level vocabulary."""
    mapping = {"normal": "low", "warning": "medium", "critical": "critical"}
    return mapping.get(report.alert_status or "warning", "medium")


def _findings_risk_level(findings: dict) -> str:
    """Preserve the highest finding; incomplete evidence cannot mean healthy."""
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    entries = [value for value in findings.values() if isinstance(value, dict)]
    levels = [value.get("risk_level", "medium") for value in entries]
    risk = max(levels, key=lambda value: order.get(value, 1)) if levels else "medium"
    if risk == "low" and any(
        value.get("evidence_status") in {"partial", "insufficient"} for value in entries
    ):
        return "medium"
    return risk if risk in order else "medium"


def _risk_to_alert_status(risk: str) -> str:
    return {"low": "normal", "medium": "warning", "high": "warning",
            "critical": "critical"}[risk]


def _deterministic_report(target: str, findings: dict) -> InvestigationReport:
    """Build a real InvestigationReport from collected findings when the LLM
    structured-output ladder fails. Only summarizes facts already gathered;
    never fabricates. This is code-level policy, not a prompt.
    """
    logs = findings.get("logs", {}) if isinstance(findings, dict) else {}
    machine = findings.get("machine", {}) if isinstance(findings, dict) else {}
    security = findings.get("security", {}) if isinstance(findings, dict) else {}

    log_rl = logs.get("risk_level", "low") if isinstance(logs, dict) else "low"
    mac_rl = machine.get("risk_level", "low") if isinstance(machine, dict) else "low"
    sec_rl = security.get("risk_level", "low") if isinstance(security, dict) else "low"

    # alert_status: any critical → critical; any high → warning; else normal
    alert = _risk_to_alert_status(_findings_risk_level(findings))

    # --- summary: per-dimension facts -------------------------------------
    parts: list[str] = []
    if isinstance(logs, dict) and logs:
        er = logs.get("error_rate", {})
        er_str = ""
        if isinstance(er, dict):
            er_str = f"，错误率 {er.get('5xx', '—')} 5xx / {er.get('4xx', '—')} 4xx"
        parts.append(f"日志维度：{logs.get('summary', '已采集')}（风险 {log_rl}{er_str}）")
    else:
        parts.append("日志维度：未采集到数据")

    if isinstance(machine, dict) and machine:
        parts.append(f"基础设施维度：{machine.get('summary', '已采集')}（风险 {mac_rl}）")
    else:
        parts.append("基础设施维度：未采集到数据")

    if isinstance(security, dict) and security:
        parts.append(f"安全防护维度：{security.get('summary', '已采集')}（风险 {sec_rl}）")
    else:
        parts.append("安全防护维度：未采集到数据")

    summary = f"目标 {target} 调查完成。" + "；".join(parts) + "。"

    # --- root_cause: deterministic rule ----------------------------------
    rate_5 = logs.get("rate_5xx") if isinstance(logs, dict) else None
    rate_4 = logs.get("rate_4xx") if isinstance(logs, dict) else None
    if isinstance(rate_5, (int, float)) and rate_5 >= 0.50:
        root = f"源站 5xx 错误率异常偏高（{rate_5:.0%}），指向应用层故障或上游依赖异常。"
    elif isinstance(rate_4, (int, float)) and rate_4 >= 0.80:
        root = f"4xx 错误率异常偏高（{rate_4:.0%}），指向异常客户端或爬虫流量。"
    elif mac_rl in ("critical", "high"):
        root = "基础设施资源水位异常，需排查主机负载与进程状态。"
    elif sec_rl in ("critical", "high"):
        root = "检测到 CC/DDoS 攻击标记，需确认攻击目标与清洗策略。"
    else:
        root = "当前证据未能确定根因；请结合数据覆盖情况与原始观测人工复核。"

    # --- recommendations: deterministic rule -------------------------------
    recs: list[str] = []
    if isinstance(rate_5, (int, float)) and rate_5 >= 0.50:
        recs.append("1. 立即排查源站应用与上游依赖（5xx 突增）")
        recs.append("2. 检查负载均衡与回源链路")
    if isinstance(rate_4, (int, float)) and rate_4 >= 0.80:
        recs.append("1. 排查异常客户端/爬虫流量来源")
        recs.append("2. 核对 WAF 拦截策略")
    if mac_rl in ("critical", "high"):
        recs.append("1. 检查主机负载与资源水位")
        recs.append("2. 核查进程/容器异常")
    if sec_rl in ("critical", "high"):
        recs.append("1. 确认攻击目标与清洗策略")
        recs.append("2. 核对封禁名单")
    if not recs:
        recs.append("1. 结合分项发现人工复核处置")
    recs.append("以上为确定性汇总，建议人工复核后执行")
    recommendations = "\n".join(recs)

    # --- per-dimension conclusions -----------------------------------------
    performance_conclusion = (
        str(machine.get("summary", "未采集到该维度数据")) if isinstance(machine, dict) and machine
        else "未采集到该维度数据"
    )
    network_conclusion = "未采集到该维度数据"
    security_conclusion = (
        str(security.get("summary", "未采集到该维度数据")) if isinstance(security, dict) and security
        else "未采集到该维度数据"
    )
    request_conclusion = (
        str(logs.get("summary", "未采集到该维度数据")) if isinstance(logs, dict) and logs
        else "未采集到该维度数据"
    )

    return InvestigationReport(
        alert_status=alert,
        summary=summary,
        recommendations=recommendations,
        performance_conclusion=performance_conclusion,
        network_conclusion=network_conclusion,
        security_conclusion=security_conclusion,
        request_conclusion=request_conclusion,
        root_cause=root,
    )


# Backward-compatible alias: the old "degraded" placeholder has been upgraded to
# a real deterministic report synthesized from collected findings.
_degraded_report = _deterministic_report


def _format_findings(findings: dict) -> str:
    """Serialize target-scoped findings into a stable prompt block."""
    if not findings:
        return "No findings collected."
    sections = [
        f"### {key} 发现\n{value}"
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
