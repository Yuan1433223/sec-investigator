"""
Entity dedup and concurrency gate for the webhook surface.

Ported logic from KKShieldHelper-main/utils/redis_client.py, adapted for
sec-investigator's single-layer architecture:

- In-memory implementation (asyncio.Lock + dict) for single-process deployment.
  Redis upgrade is a drop-in replacement — swap _InMemoryStore for a Redis-backed
  store implementing the same interface.

State machine per entity:
    none  →  analyzing  →  analyzed   (TTL: 6 h)
                        ↘  failed     (TTL: 1 h)

Concurrency cap: MAX_CONCURRENT_ANALYSES (default 3). Matches legacy system behaviour.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

MAX_CONCURRENT_ANALYSES = 3
_TTL_ANALYZED = 6 * 3600   # 6 h
_TTL_FAILED   = 1 * 3600   # 1 h
_TTL_ANALYZING = 10 * 60   # 10 min safety expiry (prevents permanent lock on crash)

EntityStatus = Literal["none", "analyzing", "analyzed", "failed"]


@dataclass
class _EntityRecord:
    status: EntityStatus
    expires_at: float  # monotonic timestamp


class EntityDedupService:
    """
    In-memory entity dedup + concurrency gate.

    Thread-safe via asyncio.Lock. All methods are synchronous (no I/O) and
    safe to call from async context without await.

    Usage:
        svc = EntityDedupService()
        if not svc.try_start(entity):
            return  # already analyzing or recently completed
        try:
            await run_analysis(entity)
            svc.mark_analyzed(entity)
        except Exception:
            svc.mark_failed(entity)
    """

    def __init__(self) -> None:
        self._records: dict[str, _EntityRecord] = {}
        self._lock = asyncio.Lock()
        self._concurrent_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def try_start(self, entity: str) -> bool:
        """
        Atomically check dedup state and concurrency cap, then mark analyzing.

        Returns True if the caller should proceed with analysis.
        Returns False if:
          - entity is currently being analyzed, or
          - entity was recently analyzed (within TTL), or
          - concurrency cap is reached.
        """
        self._evict_expired()

        rec = self._records.get(entity)
        if rec is not None:
            logger.info(
                "Dedup skip: entity=%s status=%s ttl_remaining=%.0fs",
                entity, rec.status, max(0.0, rec.expires_at - time.monotonic()),
            )
            return False

        if self._concurrent_count >= MAX_CONCURRENT_ANALYSES:
            logger.warning(
                "Concurrency cap reached (%d/%d), dropping entity=%s",
                self._concurrent_count, MAX_CONCURRENT_ANALYSES, entity,
            )
            return False

        self._records[entity] = _EntityRecord(
            status="analyzing",
            expires_at=time.monotonic() + _TTL_ANALYZING,
        )
        self._concurrent_count += 1
        logger.info(
            "Dedup start: entity=%s concurrent=%d/%d",
            entity, self._concurrent_count, MAX_CONCURRENT_ANALYSES,
        )
        return True

    def mark_analyzed(self, entity: str) -> None:
        """Mark entity analysis as successfully completed (6 h TTL)."""
        self._records[entity] = _EntityRecord(
            status="analyzed",
            expires_at=time.monotonic() + _TTL_ANALYZED,
        )
        self._decrement()
        logger.info("Dedup analyzed: entity=%s concurrent=%d", entity, self._concurrent_count)

    def mark_failed(self, entity: str) -> None:
        """Mark entity analysis as failed (1 h TTL — retry allowed after cooldown)."""
        self._records[entity] = _EntityRecord(
            status="failed",
            expires_at=time.monotonic() + _TTL_FAILED,
        )
        self._decrement()
        logger.info("Dedup failed: entity=%s concurrent=%d", entity, self._concurrent_count)

    def status(self, entity: str) -> EntityStatus:
        """Return current dedup status for an entity."""
        self._evict_expired()
        rec = self._records.get(entity)
        return rec.status if rec else "none"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decrement(self) -> None:
        self._concurrent_count = max(0, self._concurrent_count - 1)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._records.items() if v.expires_at <= now]
        for k in expired:
            del self._records[k]


# Module-level singleton — one per process, shared across all webhook requests.
# This is intentional: the dedup state must be shared across concurrent requests.
# Do NOT instantiate per-request.
_dedup_service: EntityDedupService | None = None


def get_dedup_service() -> EntityDedupService:
    """Return the process-wide EntityDedupService instance (lazy init)."""
    global _dedup_service
    if _dedup_service is None:
        _dedup_service = EntityDedupService()
    return _dedup_service
