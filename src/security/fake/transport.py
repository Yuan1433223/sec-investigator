"""Fake HTTP transport.

A single ``httpx.MockTransport`` handler that serves the *real* adapter code
(ES DSL execution, PromQL, node resolution, CC/DDoS checks) with synthetic
fixture data when ``DATA_SOURCE=fake``.

Because the adapters only ever talk HTTP, swapping in this transport keeps every
line of existing query logic intact — the fake layer is purely I/O substitution.
The handler dispatches on the URL path and inspects the request body (DSL) or
params (PromQL) to decide which fixture to serve.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from typing import Any

import httpx

from security.fake.fixtures import (
    IncidentProfile,
    _default_profile,
    get_profile,
    search_kb,
)

_ES_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_INTERVAL_SECONDS = {"1s": 1, "1m": 60, "5m": 300, "1h": 3600, "1d": 86400}


# ---------------------------------------------------------------------------
# ES response builder
# ---------------------------------------------------------------------------


def _extract_filter_value(dsl: dict, field: str) -> str | None:
    """Find the ``term``/``terms`` value for ``field`` anywhere in a bool filter."""
    found: Any = None

    def walk(node: Any) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(node, dict):
            term = node.get("term")
            if isinstance(term, dict) and field in term:
                found = term[field]
                return
            terms = node.get("terms")
            if isinstance(terms, dict) and field in terms:
                found = terms[field]
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(dsl.get("query", {}))
    return found


def _extract_time_range(dsl: dict) -> tuple[str, str] | None:
    """Return (start, end) from the first range filter over a time field.

    Status filters also use ``range`` (with integer gte/lt), so we only accept
    a range whose bounds are date strings (time / create_date).
    """
    start = end = None
    filters = dsl.get("query", {}).get("bool", {}).get("filter", [])

    def walk(node: Any) -> None:
        nonlocal start, end
        if isinstance(node, dict):
            rng = node.get("range")
            if isinstance(rng, dict):
                for field, r in rng.items():
                    if not isinstance(r, dict):
                        continue
                    gte = r.get("gte")
                    lte = r.get("lte")
                    # time fields carry string dates; status ranges carry ints
                    if isinstance(gte, str) and isinstance(lte, str):
                        start = gte
                        end = lte
                        return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(filters)
    if start and end:
        return start, end
    return None


def _status_filter(dsl: dict) -> tuple[int, int] | None:
    """Return (gte, lt) status range if the DSL filters on HTTP status."""
    found: tuple[int, int] | None = None

    def walk(node: Any) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(node, dict):
            rng = node.get("range")
            if isinstance(rng, dict) and "status" in rng:
                gte = rng["status"].get("gte")
                lt = rng["status"].get("lt")
                found = (gte, lt)
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(dsl.get("query", {}))
    return found


def _bucket_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS.get(interval, 60)


def _parse_dt(s: str) -> datetime | None:
    """Parse a fake-ES timestamp; return None on garbage so callers degrade
    gracefully instead of crashing the investigation on a bad range time."""
    try:
        return datetime.strptime(s, _ES_TIME_FORMAT)
    except (ValueError, TypeError):
        return None


def _minute_of_day(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _trend_counts(
    profile: IncidentProfile,
    interval: str,
    start: str,
    end: str,
    status_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Synthesise a per-bucket count trend with a spike at the incident peak."""
    step = _bucket_seconds(interval)
    cur = _parse_dt(start)
    stop = _parse_dt(end)
    if cur is None or stop is None:
        return []
    spike_mod = _minute_of_day(profile.spike_time) if profile.spike_time else None

    # share of the queried status class within total traffic
    share = 1.0
    if status_range:
        gte, lt = status_range
        share = sum(
            share_val
            for code, share_val in profile.status_share.items()
            if gte <= code < lt
        ) or 0.0

    buckets: list[dict[str, Any]] = []
    while cur <= stop:
        mod = cur.hour * 60 + cur.minute
        total = profile.qps_base
        if spike_mod is not None and abs(mod - spike_mod) <= 1:
            total = profile.qps_peak
        buckets.append(
            {
                "key_as_string": cur.strftime(_ES_TIME_FORMAT),
                "doc_count": int(total * share),
            }
        )
        cur += timedelta(seconds=step)
    return buckets


def _total_docs(profile: IncidentProfile, start: str, end: str) -> int:
    """Approximate total docs in a window = sum over 1-min buckets."""
    total = 0
    cur = _parse_dt(start)
    stop = _parse_dt(end)
    if cur is None or stop is None:
        return []
    spike_mod = _minute_of_day(profile.spike_time) if profile.spike_time else None
    while cur <= stop:
        mod = cur.hour * 60 + cur.minute
        total += profile.qps_peak if spike_mod is not None and abs(mod - spike_mod) <= 1 else profile.qps_base
        cur += timedelta(minutes=1)
    return total


def _status_buckets(share_map: dict[int, float], total: int) -> list[dict[str, Any]]:
    out = []
    for code in sorted(share_map):
        count = int(total * share_map[code])
        if count > 0:
            out.append({"key": code, "doc_count": count})
    return out


def _field_is_ip(field: str) -> bool:
    return any(t in field for t in ("remote_addr", "server_addr", "client_ip", "ip"))


def _es_response(profile: IncidentProfile, dsl: dict, source: str) -> dict[str, Any]:
    """Build a fake ES response matching the aggregation shape in ``dsl``."""
    time_field = "time" if source == "GF" else "create_date"
    tr = _extract_time_range(dsl)
    start, end = tr if tr else (profile.window_start, profile.window_end)
    total = _total_docs(profile, start, end)
    aggs = dsl.get("aggs") or {}
    hits_meta = {"total": {"value": total, "relation": "eq"}}

    # ---- request_count: value_count over a field ---------------------------
    if "total_requests" in aggs:
        return {
            "hits": hits_meta,
            "aggregations": {"total_requests": {"value": float(total)}},
        }

    # ---- status distribution: previous / current filter aggs ----------------
    if "current" in aggs and "previous" in aggs:
        return {
            "hits": hits_meta,
            "aggregations": {
                "previous": {"dist": {"buckets": _status_buckets(profile.status_share_prev, total)}},
                "current": {"dist": {"buckets": _status_buckets(profile.status_share, total)}},
            },
        }

    # ---- top-n with nested time series (top_n_trend) ------------------------
    if "top_items" in aggs:
        items = aggs["top_items"]
        field = items.get("terms", {}).get("field", "remote_addr")
        if items.get("aggs", {}).get("time_series"):
            buckets = []
            for ip, count in profile.top_ips:
                buckets.append(
                    {
                        "key": ip,
                        "doc_count": count,
                        "time_series": {
                            "buckets": _trend_counts(profile, "1m", start, end)
                        },
                    }
                )
            return {"hits": hits_meta, "aggregations": {"top_items": {"buckets": buckets}}}
        # plain terms under top_items
        buckets = _terms_buckets(profile, field, total)
        return {"hits": hits_meta, "aggregations": {"top_items": {"buckets": buckets}}}

    # ---- cardinality unique_count -------------------------------------------
    result_agg = aggs.get("result")
    if isinstance(result_agg, dict) and "cardinality" in result_agg:
        return {"hits": hits_meta, "aggregations": {"result": {"value": max(1, total // 12)}}}

    # ---- date_histogram trends ----------------------------------------------
    if isinstance(result_agg, dict) and "date_histogram" in result_agg:
        interval = result_agg["date_histogram"].get("fixed_interval", "1m")
        # nested cardinality sub-agg → unique trend
        if result_agg.get("aggs", {}).get("unique_count") or result_agg.get("aggs", {}).get("count"):
            buckets = []
            for b in _trend_counts(profile, interval, start, end):
                b = dict(b)
                b["unique_count"] = max(1, b["doc_count"] // 8)
                b["count"] = b["unique_count"]
                buckets.append(b)
            return {"hits": hits_meta, "aggregations": {"result": {"buckets": buckets}}}
        # status trend vs qps trend (distinguish by status filter in query)
        status_range = _status_filter(dsl)
        buckets = _trend_counts(profile, interval, start, end, status_range)
        return {"hits": hits_meta, "aggregations": {"result": {"buckets": buckets}}}

    # ---- top_n_ranking: terms under "result" ---------------------------------
    if isinstance(result_agg, dict) and "terms" in result_agg:
        field = result_agg["terms"].get("field", "remote_addr")
        buckets = _terms_buckets(profile, field, total)
        return {"hits": hits_meta, "aggregations": {"result": {"buckets": buckets}}}

    # ---- raw documents / customer desc (no aggs, size > 0) --------------------
    size = int(dsl.get("size", 0))
    return _raw_hits(profile, dsl, source, hits_meta, size, time_field)


def _terms_buckets(profile: IncidentProfile, field: str, total: int) -> list[dict[str, Any]]:
    if _field_is_ip(field):
        return [
            {"key": ip, "doc_count": count}
            for ip, count in profile.top_ips
        ]
    if "status" in field:
        return [
            {"key": code, "doc_count": int(total * share)}
            for code, share in sorted(profile.status_share.items())
        ]
    # generic: request paths
    return [
        {"key": path, "doc_count": int(total * share)}
        for path, share in (("/", 0.6), ("/forum.php", 0.18), ("/home.php?mod=rss", 0.12), ("/api/list", 0.10))
    ]


def _raw_hits(
    profile: IncidentProfile,
    dsl: dict,
    source: str,
    hits_meta: dict,
    size: int,
    time_field: str,
) -> dict[str, Any]:
    domain = profile.domain or "demo.example.com"
    node_ip = profile.node_ip
    client_ips = [ip for ip, _ in profile.top_ips] or ["203.0.113.9"]
    hits: list[dict[str, Any]] = []
    base = datetime(2026, 4, 23, 12, 3, 0)
    for i in range(size):
        src = {
            "time": (base - timedelta(seconds=i * 3)).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "create_date": (base - timedelta(seconds=i * 3)).strftime(_ES_TIME_FORMAT),
            "http_host": domain,
            "server_addr": node_ip,
            "status": 404 if i % 3 else 200,
            "remote_addr": client_ips[i % len(client_ips)],
            "request_uri": "/forum.php" if i % 3 else "/",
            "request_method": "GET",
            "http_user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "upstream_status": 502 if profile.is_5xx and i % 3 == 0 else 200,
            "gamedun_id": f"game-{profile.key}",
            "server_name": domain,
        }
        hits.append({"_source": src})
    return {"hits": {**hits_meta, "hits": hits}}


def _es(request: httpx.Request) -> httpx.Response:
    dsl = json.loads(request.content.decode("utf-8") or "{}")
    source = "WAF" if "waf" in request.url.path.lower() else "GF"
    domain = _extract_filter_value(dsl, "http_host") or _extract_filter_value(dsl, "servername")
    ip = _extract_filter_value(dsl, "server_addr")
    profile = get_profile(domain=domain, ip=ip) or _default_profile()
    body = _es_response(profile, dsl, source)
    return httpx.Response(200, json=body)


# ---------------------------------------------------------------------------
# Prometheus response builder
# ---------------------------------------------------------------------------

_INSTANCE_RE = re.compile(r'instance="([^"]+)"')
_DEVICE_RE = re.compile(r'device="([^"]+)"')


def _metric_name(promql: str) -> str:
    m = re.search(r"(node_[a-zA-Z_0-9]+|rate\(|irate\()", promql)
    if not m:
        return "unknown"
    name = m.group(1)
    if name in ("rate(", "irate("):
        inner = re.search(r"(node_[a-zA-Z_0-9]+)", promql)
        return inner.group(1) if inner else "unknown"
    return name


def _series_values(profile: IncidentProfile, start: int, end: int, kind: str) -> list[list]:
    n = 24
    step = max(1, (end - start) // n)
    base = {
        "node_cpu_seconds_total": profile.cpu_pct,
        "node_memory_MemAvailable_bytes": profile.mem_pct,
        "node_netstat_Tcp_CurrEstab": profile.tcp_estab,
        "node_network_receive_bytes_total": 120.0,
        "node_network_transmit_bytes_total": 40.0,
        "node_sockstat_sockets_used": 800.0,
        "node_disk_read_bytes_total": 5.0,
        "node_disk_written_bytes_total": 2.0,
    }
    val = base.get(kind, 10.0)
    out = []
    for i in range(n):
        wobble = 1 + 0.05 * math.sin(i / 2.0)
        t = start + i * step
        out.append([t, round(val * wobble, 3)])
    return out


def _prom(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    promql = params.get("query", "")
    is_range = request.url.path.endswith("query_range")
    name = _metric_name(promql)
    inst = (_INSTANCE_RE.search(promql) or [None, "127.0.0.1:64998"])[1]
    node_ip = inst.split(":")[0]
    profile = get_profile(ip=node_ip) or _default_profile()

    metric: dict[str, Any] = {"instance": inst}
    if name == "node_uname_info":
        metric.update(
            {
                "nodename": f"node-{node_ip.split('.')[-1]}",
                "sysname": "Linux",
                "machine": "x86_64",
                "release": "5.15.0-91-generic",
            }
        )
    if name.startswith("node_network") or name.startswith("node_disk"):
        metric["device"] = (_DEVICE_RE.search(promql) or [None, "eth0"])[1]

    if is_range:
        start = int(params.get("start", 0))
        end = int(params.get("end", start + 300))
        result = [{"metric": metric, "values": _series_values(profile, start, end, name)}]
    else:
        result = [{"metric": metric, "value": [int(params.get("time", 0) or 0), "1"]}]

    return httpx.Response(200, json={"status": "success", "data": {"resultType": "matrix" if is_range else "vector", "result": result}})


# ---------------------------------------------------------------------------
# Security / resolution endpoints
# ---------------------------------------------------------------------------


def _node_payload(profile: IncidentProfile) -> dict:
    return {"node_ip": profile.node_ip, "ip_list": profile.product_ips}


def _get_ip(request: httpx.Request) -> str:
    return request.url.params.get("ip") or request.url.params.get("domains") or request.url.params.get("domain") or ""


def _handle_domain_resolution(request: httpx.Request, profile: IncidentProfile | None) -> httpx.Response:
    if profile is None:
        return httpx.Response(200, json={"code": 0, "msg": "not found", "data": None})
    return httpx.Response(200, json={"code": 1, "data": [_node_payload(profile)]})


def _handle_protection_policy(request: httpx.Request, profile: IncidentProfile | None) -> httpx.Response:
    if profile is None:
        return httpx.Response(200, json={"code": 0, "msg": "not found", "data": None})
    body = {
        "code": 1,
        "data": {
            "domain": profile.domain,
            "data": [
                {
                    "rule_type": "访问频率",
                    "purpose": "封禁高频请求IP",
                    "match": [
                        {
                            "name": "高频访问限速",
                            "trigger_freq_desc": "10次/秒",
                            "req_count": 10,
                            "req_seconds": 1,
                            "action_desc": "拦截",
                            "status": 1,
                        }
                    ],
                },
                {
                    "rule_type": "黑名单",
                    "purpose": "已知恶意IP",
                    "match": {"ip": ["74.7.227.59", "45.117.11.97"], "url": [], "action_desc": "拦截"},
                },
            ],
        },
    }
    return httpx.Response(200, json=body)


def _handle_cc(request: httpx.Request, profile: IncidentProfile) -> httpx.Response:
    path = request.url.path
    ips = (request.url.params.get("ips") or "").split(",")
    if path.endswith("host_point_list"):
        points = []
        for ip in ips:
            base_pps = 900 if not profile.has_cc else profile.tcp_estab
            points.append(
                {
                    "address": ip,
                    "input_bps": base_pps * 40,
                    "input_pps": base_pps,
                    "input_submit_bps": base_pps * 38,
                    "input_submit_pps": max(0, base_pps - 100),
                    "output_bps": base_pps * 10,
                    "output_pps": base_pps // 4,
                    "fw_type": 2,
                    "fw_id": 1,
                }
            )
        return httpx.Response(200, json={"code": 1, "data": points})
    # batch_host_status
    data = [
        {"ip": ip, "shield_count": 0, "is_forbidden": 0, "status": 1}
        for ip in ips if ip
    ]
    return httpx.Response(200, json={"status": True, "data": data})


def _handle_ddos(request: httpx.Request, profile: IncidentProfile) -> httpx.Response:
    if profile.has_ddos:
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "ip": profile.node_ip,
                        "bps": 1_500_000,  # kbps → 1.5 Gbps
                        "pps": 800_000,
                        "time": profile.window_start,
                        "type": "UDP",
                    }
                ],
            },
        )
    return httpx.Response(200, json={"status": False, "data": []})


def _handle_security(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    ip_or_domain = _get_ip(request)
    profile = get_profile(domain=ip_or_domain) or get_profile(ip=ip_or_domain.split(":")[0])

    if path.endswith("/api/security_assistant/get_node_ip_by_ip"):
        # These incident nodes are GF (高防) product — WAF does not own them,
        # so fall through to the GF probe endpoints for a consistent product=GF.
        return httpx.Response(200, json={"code": 0, "data": None})
    if path.endswith("/api/p_node/getNodeIpList"):
        if profile is None:
            return httpx.Response(200, json={"code": 0, "data": None})
        return httpx.Response(200, json={"code": 1, "data": [_node_payload(profile)]})
    if path.endswith("/api/p_domainRule/getNodeIpList"):
        return _handle_domain_resolution(request, profile)
    if path.endswith("/api/p_domainRule/getDomainWaf"):
        return _handle_protection_policy(request, profile)
    if path.endswith("/api/security_assistant/get_node_ips"):
        if profile is None:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": [_node_payload(profile)]})
    if "host_point_list" in path or "batch_host_status" in path:
        return _handle_cc(request, profile or _default_profile())
    if "ddos/list" in path:
        return _handle_ddos(request, profile or _default_profile())
    return httpx.Response(404, json={"error": f"no fake route for {path}"})


# ---------------------------------------------------------------------------
# Top-level handler
# ---------------------------------------------------------------------------


class FakeTransportHandler:
    """Dispatch an httpx request to the fake fixtures. Pass to MockTransport."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/_search"):
            return _es(request)
        if path.endswith("/api/v1/query_range") or path.endswith("/api/v1/query"):
            return _prom(request)
        return _handle_security(request)


__all__ = ["FakeTransportHandler"]
