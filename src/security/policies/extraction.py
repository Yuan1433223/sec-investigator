"""Deterministic evidence extraction from raw tool results.

Why this exists
---------------
``EvidencePolicy.classify_logs / classify_machine / classify_security`` decide
risk_level from *raw numeric* fields (``rate_5xx``, ``cpu_pct``,
``cc_is_under_attack`` ...). Historically those fields came from the
STRUCTURED_EXTRACTOR LLM reading a free-text ``analysis_text`` — and the LLM
repeatedly dropped, prose-wrote, or emptied them, so the classifier received
``None`` and defaulted everything to ``low``.

This module reads the numbers straight out of the tool results the worker
actually observed. The numbers are captured by ``EvidenceCollector.observe``
every time a traced tool returns — *before* any ReAct recursion budget is
exhausted — so the degrade path (``resp is None``) still has real telemetry.

Hard rules honoured:
- thresholds stay in code (EvidencePolicy); this module only *extracts* raw
  numbers, it never decides risk.
- no module-level singleton: workers build one collector per node invocation.
- values are normalised to fractions (0.0–1.0) matching the findings schema.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Iterator

# Tool names that carry the telemetry we care about (kept as plain strings so
# this module never imports the tool factories).
_LOG_DIST = "query_status_code_distribution"
_LOG_TREND = "query_es_status_code_trend"
_LOG_COUNT = "query_request_count"
_LOG_QPS = "query_es_qps_trend"

_MACHINE_STATUS = "query_instance_status"
_MACHINE_CPU = "query_instance_cpu"
_MACHINE_MEM = "query_instance_memory"
_MACHINE_TCP = "query_instance_tcp"

_CC = "check_cc_status"
_DDOS = "check_ddos_status"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _loads(content: Any) -> Any:
    """Best-effort JSON decode of a tool payload (dict/list pass through)."""
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str):
        return None
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json|JSON)?", "", s).strip()
        s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


def _pct_to_frac(value: Any) -> float | None:
    """Normalise ``'87.3%'`` / ``87.3`` / ``0.873`` to a fraction in [0, 1]."""
    if value is None:
        return None
    num: float | None
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if not m:
            return None
        num = float(m.group(0))
    elif isinstance(value, bool):
        return None
    elif isinstance(value, (int, float)):
        num = float(value)
    else:
        return None
    if num > 1.0 and num <= 100.0:
        return num / 100.0
    if num < 0.0:
        return None
    return num


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _iter_observations(messages: Iterable[Any]) -> Iterator[tuple[str, Any]]:
    """Yield ``(tool_name, parsed_result)`` from ToolMessages or raw tuples.

    Accepts both:
      * ``ToolMessage``-like objects (``.name`` / ``.content``), and
      * raw ``(tool_name, result)`` pairs recorded by ``EvidenceCollector``.
    """
    for item in messages:
        if isinstance(item, tuple) and len(item) == 2:
            name, result = item
            yield str(name or ""), _loads(result) if not isinstance(result, (dict, list)) else result
            continue
        name = getattr(item, "name", None) or getattr(item, "tool_name", "") or ""
        yield str(name), _loads(getattr(item, "content", item))


# ---------------------------------------------------------------------------
# Per-domain extraction
# ---------------------------------------------------------------------------


def _status_bucket_share(buckets: list[dict[str, Any]]) -> tuple[float, float, int]:
    """Return (rate_5xx, rate_4xx, total) from a list of {status, count}."""
    rows = [b for b in buckets if isinstance(b, dict)]
    total = sum(_as_int(b.get("count")) or 0 for b in rows)
    if total <= 0:
        return 0.0, 0.0, 0
    s5 = sum(_as_int(b.get("count")) or 0 for b in rows if 500 <= int(b.get("status", 0)) < 600)
    s4 = sum(_as_int(b.get("count")) or 0 for b in rows if 400 <= int(b.get("status", 0)) < 500)
    return round(s5 / total, 6), round(s4 / total, 6), total


def extract_log_evidence(messages: Iterable[Any]) -> dict[str, Any]:
    """Extract ``rate_5xx`` / ``rate_4xx`` / ``total_requests`` from ES tool output.

    Preferred source: ``query_status_code_distribution.current`` buckets — the
    ratio is conserved inside a single response regardless of the window the LLM
    picked.

    Fallback (what the ReAct agent usually actually calls): the QPS volume trend
    vs the per-status-class trends. ``rate_5xx = sum(5xx trend counts) /
    sum(total-traffic trend counts)`` over the same queried window. This is
    deterministic and does not depend on the agent ever reaching the
    distribution tool.
    """
    out: dict[str, Any] = {}
    qps_sum: int = 0
    trend5 = trend4 = 0
    req_total = None

    for name, result in _iter_observations(messages):
        if not isinstance(result, dict):
            continue
        if name == _LOG_DIST:
            cur = result.get("current") or []
            r5, r4, total = _status_bucket_share(cur)
            if total > 0:
                out["rate_5xx"] = r5
                out["rate_4xx"] = r4
                out["total_requests"] = total
                return out  # authoritative; stop here
        if name == _LOG_QPS:
            buckets = result.get("trend") or result.get("buckets") or []
            qps_sum += sum(_as_int(b.get("count")) or 0 for b in buckets if isinstance(b, dict))
        if name == _LOG_TREND:
            buckets = result.get("trend") or result.get("buckets") or []
            s = sum(_as_int(b.get("count")) or 0 for b in buckets if isinstance(b, dict))
            if result.get("status_type") == "5xx":
                trend5 += s
            elif result.get("status_type") == "4xx":
                trend4 += s
        if name == _LOG_COUNT:
            req_total = _as_int(result.get("count"))

    # Preferred fallback: QPS volume trend as the denominator.
    if qps_sum > 0:
        out["rate_5xx"] = round(trend5 / qps_sum, 6)
        out["rate_4xx"] = round(trend4 / qps_sum, 6)
        out.setdefault("total_requests", qps_sum)
        return out

    # Last-resort fallback: request-count total as the denominator.
    if req_total and req_total > 0:
        if trend5 > 0:
            out["rate_5xx"] = round(trend5 / req_total, 6)
        if trend4 > 0:
            out["rate_4xx"] = round(trend4 / req_total, 6)
        out.setdefault("total_requests", req_total)
    return out


def extract_machine_evidence(messages: Iterable[Any]) -> dict[str, Any]:
    """Extract ``cpu_pct`` / ``memory_pct`` / ``tcp_established`` from Prom tools."""
    cpu = mem = tcp = None
    for name, result in _iter_observations(messages):
        if not isinstance(result, dict):
            continue
        if name in (_MACHINE_STATUS, _MACHINE_CPU):
            v = _pct_to_frac(result.get("cpu_usage"))
            if v is not None:
                cpu = v
        if name in (_MACHINE_STATUS, _MACHINE_MEM):
            v = _pct_to_frac(result.get("memory_usage"))
            if v is not None:
                mem = v
        if name in (_MACHINE_STATUS, _MACHINE_TCP):
            v = _as_int(result.get("tcp_established"))
            if v is not None:
                tcp = v
    out: dict[str, Any] = {}
    if cpu is not None:
        out["cpu_pct"] = cpu
    if mem is not None:
        out["memory_pct"] = mem
    if tcp is not None:
        out["tcp_established"] = tcp
    return out


def extract_security_evidence(messages: Iterable[Any]) -> dict[str, Any]:
    """Extract CC/DDoS attack flags and counters from security tools."""
    cc_attack = False
    cc_pps = 0
    ddos_attack = False
    ddos_count = 0

    for name, result in _iter_observations(messages):
        if not isinstance(result, dict):
            continue
        if name == _CC:
            for pt in result.get("points") or []:
                if not isinstance(pt, dict):
                    continue
                if pt.get("is_under_attack") is True:
                    cc_attack = True
                pps = _as_int(pt.get("input_pps"))
                if pps is not None and pps > cc_pps:
                    cc_pps = pps
        elif name == _DDOS:
            events = result.get("events") or []
            ddos_count = max(ddos_count, _as_int(result.get("count")) or len(events))
            for ev in events:
                if isinstance(ev, dict) and ev.get("exceeds_threshold") is True:
                    ddos_attack = True

    out: dict[str, Any] = {}
    out["cc_is_under_attack"] = cc_attack
    out["ddos_exceeds_threshold"] = ddos_attack
    out["cc_input_pps"] = cc_pps or None
    out["ddos_event_count"] = ddos_count or None
    return out


# ---------------------------------------------------------------------------
# Per-invocation collector (NOT a module-level singleton)
# ---------------------------------------------------------------------------


class EvidenceCollector:
    """Accumulates raw tool results for one worker node invocation.

    The traced-tool wrapper calls :meth:`observe` on every tool return, so the
    numbers are on record *before* ReAct possibly dies on its recursion budget.
    Build one per node call; never reuse across sessions and never instantiate at
    module import time.
    """

    def __init__(self, kind: str) -> None:
        if kind not in {"logs", "machine", "security"}:
            raise ValueError(f"unknown collector kind: {kind!r}")
        self.kind = kind
        self._observations: list[tuple[str, Any]] = []

    def observe(self, tool_name: str, result: Any) -> None:
        """Record a raw tool return. Safe to call with any result shape."""
        self._observations.append((str(tool_name or ""), result))

    def extract_logs(self) -> dict[str, Any]:
        return extract_log_evidence(self._observations)

    def extract_machine(self) -> dict[str, Any]:
        return extract_machine_evidence(self._observations)

    def extract_security(self) -> dict[str, Any]:
        return extract_security_evidence(self._observations)

    def extracted(self) -> dict[str, Any]:
        if self.kind == "logs":
            return self.extract_logs()
        if self.kind == "machine":
            return self.extract_machine()
        return self.extract_security()
