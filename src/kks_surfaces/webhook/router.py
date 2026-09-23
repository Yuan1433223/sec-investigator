"""
Grafana webhook router.

Thin adapter — no AI analysis logic. Receives Grafana alerts, extracts the
investigation entity, deduplicates via EntityDedupService, fires a background
investigation task, and returns 200 immediately (Grafana requires a fast response).

Dedup behaviour (mirrors KKShieldHelper-main/utils/redis_client.py):
  - entity currently analyzing → skip
  - entity analyzed within 6 h → skip
  - entity failed within 1 h → skip
  - concurrent analyses ≥ 3 → skip
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks
from langchain_core.messages import HumanMessage

from kks_runtime.checkpoint.factory import get_checkpointer
from kks_runtime.config.settings import get_settings
from kks_runtime.graph.investigation import build_investigation_graph
from kks_security.schemas.report import InvestigationReport
from kks_surfaces.feishu.delivery import send_report_to_feishu
from kks_surfaces.webhook.dedup import get_dedup_service
from kks_surfaces.webhook.entity import build_investigation_question, extract_entity
from kks_surfaces.webhook.schemas import GrafanaAlert, GrafanaWebhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


async def _run_investigation(question: str, entity: str) -> None:
    """Background task: run one investigation for the extracted entity."""
    session_id = f"webhook-{entity}"
    dedup = get_dedup_service()
    try:
        async with get_checkpointer() as checkpointer:
            graph = build_investigation_graph(checkpointer=checkpointer)
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content=question)],
                    "target": entity,
                    "session_id": session_id,
                },
                config={
                    "configurable": {"thread_id": session_id},
                    "recursion_limit": 100,
                },
            )
        dedup.mark_analyzed(entity)

        # Surface-layer Feishu delivery — best-effort, never blocks the task.
        # reporter_node emits FinalEvent; here we read the final state artifacts
        # to reconstruct and deliver the Feishu card.
        s = get_settings()
        if s.feishu_alert_webhook_url and result.get("artifacts"):
            artifact = result["artifacts"][-1]
            try:
                report = InvestigationReport(
                    summary=artifact.get("summary"),
                    recommendations="\n".join(artifact.get("recommendations", [])) or None,
                    alert_status=_risk_to_alert_status(artifact.get("risk_level")),
                )
                ok = await send_report_to_feishu(s.feishu_alert_webhook_url, report, entity)
                if ok:
                    logger.info("Feishu card delivered for entity=%s", entity)
                else:
                    logger.warning("Feishu delivery returned non-200 for entity=%s", entity)
            except Exception:
                logger.exception("Feishu delivery failed for entity=%s", entity)
    except Exception:
        logger.exception("Background investigation failed for entity=%s", entity)
        dedup.mark_failed(entity)


def _risk_to_alert_status(risk_level: str | None) -> str:
    return {"low": "normal", "medium": "warning", "high": "critical", "critical": "critical"}.get(
        risk_level or "medium", "warning"
    )


@router.post("/grafana")
async def grafana_webhook(
    webhook: GrafanaWebhook,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Receive a Grafana alert webhook.

    Filters to firing alerts, extracts the investigation entity, applies dedup
    and concurrency gate, then starts a background investigation.
    Returns 200 immediately.
    """
    firing: list[GrafanaAlert] = [a for a in webhook.alerts if a.status == "firing"]

    if not firing:
        return {"accepted": False, "reason": "no firing alerts"}

    # Extract entity from the first firing alert (with fallback label chain).
    entity = extract_entity(firing[0])
    if not entity:
        logger.warning(
            "Could not extract entity from alert labels: %s", firing[0].labels
        )
        return {"accepted": False, "reason": "entity could not be determined"}

    # Dedup + concurrency gate — atomic check-and-mark.
    dedup = get_dedup_service()
    if not dedup.try_start(entity):
        current_status = dedup.status(entity)
        logger.info(
            "Dedup rejected: entity=%s status=%s firing_count=%d",
            entity, current_status, len(firing),
        )
        return {"accepted": False, "reason": f"entity dedup: {current_status}"}

    # Build question aggregating ALL firing alerts for this entity.
    question = build_investigation_question(entity, firing)
    background_tasks.add_task(_run_investigation, question, entity)

    logger.info(
        "Accepted webhook: entity=%s firing_count=%d alert_names=%s",
        entity,
        len(firing),
        [a.labels.get("alertname", "?") for a in firing],
    )
    return {"accepted": True, "entity": entity, "firing_count": len(firing)}
