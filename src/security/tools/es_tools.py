"""
Elasticsearch LangChain tools for the log_detective worker.

Each @tool function:
1. Builds an ES DSL using ESDSLBuilder (pure, no I/O)
2. Executes it via ESAdapter (async, injectable for testing)
3. Returns a JSON-serialisable dict

The `adapter` parameter is optional: callers can inject a mock for tests.
In production the tools share one ESAdapter per factory lifetime (lazy init,
created on first use, then cached in closure scope — no import-time singleton).

Migrated from KKShieldHelper-main/agents/tools/es.py — removed global
ESClient singleton, added explicit adapter injection.

Status-code range map (query_es_status_code_trend):
  "1xx" → (100, 200), "2xx" → (200, 300), "3xx" → (300, 400),
  "4xx" → (400, 500), "5xx" → (500, 600), "normal" → (200, 400)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

from security.adapters.es import ESAdapter, Source
from security.adapters.es_dsl import ESDSLBuilder, _normalise_time

logger = logging.getLogger(__name__)

# Optional special-customer registry (mirrors KKShieldHelper-main/tools/resource/)
_SPECIAL_CUSTOMER_JSON = (
    Path(__file__).parent.parent / "resource" / "special_customer.json"
)

_STATUS_RANGES: dict[str, tuple[int, int]] = {
    "1xx": (100, 200),
    "2xx": (200, 300),
    "3xx": (300, 400),
    "4xx": (400, 500),
    "5xx": (500, 600),
    "normal": (200, 400),
}


def _agg_result(response: dict[str, Any]) -> Any:
    """Extract the 'result' or 'top_items' aggregation from an ES response."""
    aggs = response.get("aggregations", {})
    if "result" in aggs:
        return aggs["result"]
    if "top_items" in aggs:
        return aggs["top_items"]
    return aggs


def _total_hits(response: dict[str, Any]) -> int:
    hits = response.get("hits", {}).get("total", {})
    if isinstance(hits, dict):
        return hits.get("value", 0)
    return int(hits)


def _make_es_tools(adapter: ESAdapter | None = None):
    """
    Factory that returns a list of ES tools bound to the given adapter.

    If adapter is None the first tool call lazily creates one ESAdapter and
    caches it in closure scope — all subsequent calls in the same factory
    lifetime reuse the same connection pool.
    Pass a mock adapter in tests to avoid real ES connections.
    """
    _cached: ESAdapter | None = adapter

    async def _adapter() -> ESAdapter:
        nonlocal _cached
        if _cached is None:
            _cached = ESAdapter()
        return _cached

    @tool
    async def query_es_raw_logs(
        size: int = 20,
        fields: list[str] | None = None,
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Query raw ES log documents. Returns the most recent N records."""
        _fields = fields or [
            "time", "http_host", "server_addr", "status",
            "remote_addr", "request_uri", "http_user_agent",
        ]
        dsl = ESDSLBuilder.raw_documents(
            fields=_fields, size=size,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        return {"total": _total_hits(resp), "hits": [h["_source"] for h in resp["hits"]["hits"]]}

    @tool
    async def query_es_unique_count(
        field: str,
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Count distinct values of a field (e.g., unique client IPs)."""
        dsl = ESDSLBuilder.unique_count(
            field=field,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        return {
            "field": field,
            "unique_count": _agg_result(resp).get("value", 0),
            "total_docs": _total_hits(resp),
        }

    @tool
    async def query_es_top_n(
        field: str,
        size: int = 10,
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Top N values of a field by document count (e.g., top client IPs, top URLs)."""
        dsl = ESDSLBuilder.top_n_ranking(
            field=field, size=size,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        buckets = _agg_result(resp).get("buckets", [])
        return {
            "field": field,
            "top_n": [{"value": b["key"], "count": b["doc_count"]} for b in buckets],
        }

    @tool
    async def query_es_qps_trend(
        interval: str = "1m",
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """QPS / request volume trend over time. interval: 1s, 1m, 5m, 1h, 1d."""
        time_field = "time" if source == "GF" else "create_date"
        dsl = ESDSLBuilder.time_series_count(
            interval=interval, time_field=time_field,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        buckets = _agg_result(resp).get("buckets", [])
        return {
            "interval": interval,
            "total": _total_hits(resp),
            "trend": [{"time": b["key_as_string"], "count": b["doc_count"]} for b in buckets],
        }

    @tool
    async def query_es_status_code_trend(
        status_type: Literal["1xx", "2xx", "3xx", "4xx", "5xx", "normal"],
        interval: str = "1m",
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """HTTP status code class trend over time (e.g., 4xx errors per minute)."""
        status_range = _STATUS_RANGES[status_type]
        time_field = "time" if source == "GF" else "create_date"
        dsl = ESDSLBuilder.time_series_count(
            interval=interval, time_field=time_field,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
            status_range=status_range,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        buckets = _agg_result(resp).get("buckets", [])
        return {
            "status_type": status_type,
            "interval": interval,
            "total": _total_hits(resp),
            "trend": [{"time": b["key_as_string"], "count": b["doc_count"]} for b in buckets],
        }

    @tool
    async def query_es_top_n_trend(
        field: str,
        top_n: int = 5,
        interval: str = "1m",
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Top N field values + their request counts over time (nested aggregation)."""
        time_field = "time" if source == "GF" else "create_date"
        dsl = ESDSLBuilder.top_n_time_series(
            group_field=field, top_n=top_n, interval=interval, time_field=time_field,
            domain=domain, ip=ip, start_time=start_time, end_time=end_time,
        )
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        items = _agg_result(resp).get("buckets", [])
        return {
            "field": field,
            "top_n": [
                {
                    "value": item["key"],
                    "total": item["doc_count"],
                    "trend": [
                        {"time": b["key_as_string"], "count": b["doc_count"]}
                        for b in item.get("time_series", {}).get("buckets", [])
                    ],
                }
                for item in items
            ],
        }

    @tool
    async def query_request_count(
        query_by: Literal["ip", "domain"],
        value: str | list[str],
        start_time: str,
        end_time: str,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Query total request count for a domain or IP in a time range.

        Args:
            query_by: "domain" or "ip".
            value: Domain name(s) or IP address(es). Accepts a single string or list.
            start_time: Start time, format YYYY-MM-DD HH:MM:SS.
            end_time: End time, format YYYY-MM-DD HH:MM:SS.
            source: "GF" (高防) or "WAF". Default GF.

        Returns:
            {"count": int} — total number of matching log documents.
        """
        field = "http_host" if query_by == "domain" else "server_addr"
        if isinstance(value, list):
            filter_clause: dict[str, Any] = {"terms": {field: value}}
        else:
            filter_clause = {"term": {field: value}}
        time_field = "time" if source == "GF" else "create_date"
        dsl: dict[str, Any] = {
            "query": {
                "bool": {
                    "filter": [
                        filter_clause,
                        {"range": {time_field: {"gte": _normalise_time(start_time), "lte": _normalise_time(end_time)}}},
                    ]
                }
            },
            "size": 0,
            "aggs": {
                "total_requests": {
                    "value_count": {"field": field}
                }
            },
        }
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        count = resp.get("aggregations", {}).get("total_requests", {}).get("value", 0)
        return {"count": int(count)}

    @tool
    async def query_status_code_distribution(
        query_by: Literal["ip", "domain"],
        value: str | list[str],
        start_time: str,
        end_time: str,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Query HTTP status code distribution for a domain or IP.

        Returns the distribution for the requested time window AND the 30-minute
        window immediately before it, so the LLM can compare current vs baseline.

        Args:
            query_by: "domain" or "ip".
            value: Domain name(s) or IP address(es).
            start_time: Start time, format YYYY-MM-DD HH:MM:SS.
            end_time: End time, format YYYY-MM-DD HH:MM:SS.
            source: "GF" or "WAF". Default GF.

        Returns:
            {"current": [{"status": int, "count": int}, ...],
             "previous": [{"status": int, "count": int}, ...]}
        """
        field = "http_host" if query_by == "domain" else "server_addr"
        time_field = "time" if source == "GF" else "create_date"
        status_field = "status" if source == "GF" else "status_code"
        if isinstance(value, list):
            filter_clause: dict[str, Any] = {"terms": {field: value}}
        else:
            filter_clause = {"term": {field: value}}

        start_time = _normalise_time(start_time)
        end_time = _normalise_time(end_time)
        compare_start = (
            datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S") - timedelta(minutes=30)
        ).strftime("%Y-%m-%d %H:%M:%S")

        dsl: dict[str, Any] = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        filter_clause,
                        {
                            "bool": {
                                "should": [
                                    {
                                        "range": {
                                            time_field: {"gte": compare_start, "lt": start_time}
                                        }
                                    },
                                    {
                                        "range": {
                                            time_field: {"gte": start_time, "lt": end_time}
                                        }
                                    },
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    ]
                }
            },
            "aggs": {
                "previous": {
                    "filter": {"range": {time_field: {"gte": compare_start, "lt": start_time}}},
                    "aggs": {"dist": {"terms": {"field": status_field, "size": 10}}},
                },
                "current": {
                    "filter": {"range": {time_field: {"gte": start_time, "lt": end_time}}},
                    "aggs": {"dist": {"terms": {"field": status_field, "size": 10}}},
                },
            },
        }
        es = await _adapter()
        resp = await es.execute_dsl(dsl, source=source)
        aggs = resp.get("aggregations", {})

        def _buckets(key: str) -> list[dict[str, Any]]:
            buckets = aggs.get(key, {}).get("dist", {}).get("buckets", [])
            return [{"status": b["key"], "count": b["doc_count"]} for b in buckets]

        return {"current": _buckets("current"), "previous": _buckets("previous")}

    @tool
    async def query_es_trend_comparison(
        metrics: list[dict[str, Any]],
        comparison_mode: Literal[
            "current_vs_yesterday", "current_vs_last_week", "period_vs_period"
        ],
        current_start_time: str,
        current_end_time: str,
        interval: str = "1h",
        domain: str | None = None,
        ip: str | None = None,
        compare_start_time: str | None = None,
        compare_end_time: str | None = None,
        source: Source = "GF",
    ) -> dict[str, Any]:
        """Historical trend comparison — compare multiple metrics across two time periods.

        Computes current vs yesterday / last-week / custom period for any combination
        of request volume, unique-IP count, and status-code counts.

        Args:
            metrics: List of metric specs. Each is a dict with a "type" key:
                - {"type": "request_count"}
                - {"type": "unique_count", "field": "remote_addr"}
                - {"type": "status_code", "status_type": "4xx"}
            comparison_mode: One of:
                - "current_vs_yesterday": compare to same window 24 h ago
                - "current_vs_last_week": compare to same window 7 days ago
                - "period_vs_period": compare to explicit compare_start/end_time
            current_start_time: Current window start, YYYY-MM-DD HH:MM:SS.
            current_end_time: Current window end, YYYY-MM-DD HH:MM:SS.
            interval: Time bucket size for trend data (1s, 1m, 5m, 1h, 1d). Default 1h.
            domain: Filter by domain (http_host).
            ip: Filter by node IP (server_addr).
            compare_start_time: Required for period_vs_period mode.
            compare_end_time: Required for period_vs_period mode.
            source: "GF" or "WAF". Default GF.

        Returns:
            Dict with comparison_mode, time_range, and per-metric stats including
            total/average/peak for both periods and percentage change.
        """
        import asyncio as _asyncio

        if not metrics:
            return {"error": "metrics must not be empty"}

        # Normalise times before parsing — LLM may pass ISO 8601 with timezone
        current_start_time = _normalise_time(current_start_time)
        current_end_time = _normalise_time(current_end_time)

        # Resolve comparison window
        cur_start = datetime.strptime(current_start_time, "%Y-%m-%d %H:%M:%S")
        cur_end = datetime.strptime(current_end_time, "%Y-%m-%d %H:%M:%S")
        if comparison_mode == "current_vs_yesterday":
            delta = timedelta(days=1)
            cmp_start = cur_start - delta
            cmp_end = cur_end - delta
        elif comparison_mode == "current_vs_last_week":
            delta = timedelta(days=7)
            cmp_start = cur_start - delta
            cmp_end = cur_end - delta
        elif comparison_mode == "period_vs_period":
            if not compare_start_time or not compare_end_time:
                return {
                    "error": (
                        "period_vs_period requires compare_start_time"
                        " and compare_end_time"
                    )
                }
            cmp_start = datetime.strptime(_normalise_time(compare_start_time), "%Y-%m-%d %H:%M:%S")
            cmp_end = datetime.strptime(_normalise_time(compare_end_time), "%Y-%m-%d %H:%M:%S")
        else:
            return {"error": f"unsupported comparison_mode: {comparison_mode}"}

        cmp_start_str = cmp_start.strftime("%Y-%m-%d %H:%M:%S")
        cmp_end_str = cmp_end.strftime("%Y-%m-%d %H:%M:%S")
        time_field = "time" if source == "GF" else "create_date"

        def _stats(trend: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
            values = [item.get(value_key, 0) for item in trend]
            total = sum(values)
            avg = round(total / len(values), 2) if values else 0
            peak = max(values) if values else 0
            return {
                "total": total,
                "average": avg,
                "peak": peak,
                "trend": [
                    {"time": item.get("time", ""), "value": item.get(value_key, 0)}
                    for item in trend
                ],
            }

        def _pct(cur: float, cmp: float) -> str:
            if cmp == 0:
                return "+100%" if cur > 0 else "0%"
            ch = (cur - cmp) / cmp * 100
            return f"+{ch:.1f}%" if ch >= 0 else f"{ch:.1f}%"

        async def _compare_one(metric: dict[str, Any]) -> dict[str, Any]:
            mtype = metric.get("type")
            es = await _adapter()

            if mtype == "request_count":
                name = "request_count"
                vkey = "count"

                async def _fetch(s: str, e: str) -> list[dict[str, Any]]:
                    dsl = ESDSLBuilder.time_series_count(
                        interval=interval, time_field=time_field,
                        domain=domain, ip=ip, start_time=s, end_time=e,
                    )
                    r = await es.execute_dsl(dsl, source=source)
                    return [
                        {"time": b["key_as_string"], "count": b["doc_count"]}
                        for b in r.get("aggregations", {}).get("result", {}).get("buckets", [])
                    ]

            elif mtype == "unique_count":
                field = metric.get("field")
                if not field:
                    return {
                        "metric_name": "unique_count_?",
                        "error": "field required for unique_count",
                    }
                name = f"unique_count_{field}"
                vkey = "unique_count"

                async def _fetch(s: str, e: str) -> list[dict[str, Any]]:  # type: ignore[misc]
                    # unique count per interval via cardinality sub-agg
                    tf = time_field
                    dsl: dict[str, Any] = {
                        "size": 0,
                        "query": ESDSLBuilder.time_series_count(
                            interval=interval, time_field=tf,
                            domain=domain, ip=ip, start_time=s, end_time=e,
                        ).get("query", {"match_all": {}}),
                        "aggs": {
                            "result": {
                                "date_histogram": {
                                    "field": tf,
                                    "calendar_interval": interval,
                                    "min_doc_count": 0,
                                },
                                "aggs": {
                                    "unique_count": {"cardinality": {"field": field}}
                                },
                            }
                        },
                    }
                    r = await es.execute_dsl(dsl, source=source)
                    return [
                        {"time": b["key_as_string"], "unique_count": b["unique_count"]["value"]}
                        for b in r.get("aggregations", {}).get("result", {}).get("buckets", [])
                    ]

            elif mtype == "status_code":
                st = metric.get("status_type")
                if not st:
                    return {"metric_name": "status_code_?", "error": "status_type required"}
                name = f"status_code_{st}"
                vkey = "count"
                status_range = _STATUS_RANGES.get(st)
                if not status_range:
                    return {"metric_name": name, "error": f"unknown status_type: {st}"}

                async def _fetch(s: str, e: str) -> list[dict[str, Any]]:  # type: ignore[misc]
                    dsl = ESDSLBuilder.time_series_count(
                        interval=interval, time_field=time_field,
                        domain=domain, ip=ip, start_time=s, end_time=e,
                        status_range=status_range,
                    )
                    r = await es.execute_dsl(dsl, source=source)
                    return [
                        {"time": b["key_as_string"], "count": b["doc_count"]}
                        for b in r.get("aggregations", {}).get("result", {}).get("buckets", [])
                    ]

            else:
                return {
                    "metric_name": mtype or "unknown",
                    "error": f"unsupported metric type: {mtype}",
                }

            cur_trend, cmp_trend = await _asyncio.gather(
                _fetch(current_start_time, current_end_time),
                _fetch(cmp_start_str, cmp_end_str),
            )
            cur_stats = _stats(cur_trend, vkey)
            cmp_stats = _stats(cmp_trend, vkey)
            return {
                "metric_name": name,
                "current_period": {
                    "start_time": current_start_time,
                    "end_time": current_end_time,
                    **cur_stats,
                },
                "compare_period": {
                    "start_time": cmp_start_str,
                    "end_time": cmp_end_str,
                    **cmp_stats,
                },
                "comparison": {
                    "total_change": cur_stats["total"] - cmp_stats["total"],
                    "total_change_percent": _pct(cur_stats["total"], cmp_stats["total"]),
                    "average_change": round(cur_stats["average"] - cmp_stats["average"], 2),
                    "average_change_percent": _pct(cur_stats["average"], cmp_stats["average"]),
                    "peak_change": cur_stats["peak"] - cmp_stats["peak"],
                    "peak_change_percent": _pct(cur_stats["peak"], cmp_stats["peak"]),
                    "trend_direction": "上升" if cur_stats["total"] > cmp_stats["total"] else (
                        "下降" if cur_stats["total"] < cmp_stats["total"] else "持平"
                    ),
                },
            }

        import asyncio as _asyncio2
        results = await _asyncio2.gather(*[_compare_one(m) for m in metrics])
        metrics_result: dict[str, Any] = {}
        for r in results:
            mname = r.pop("metric_name", "unknown")
            metrics_result[mname] = r

        return {
            "comparison_mode": comparison_mode,
            "interval": interval,
            "time_range": {
                "current": {"start_time": current_start_time, "end_time": current_end_time},
                "compare": {"start_time": cmp_start_str, "end_time": cmp_end_str},
            },
            "metrics": metrics_result,
        }

    @tool
    async def query_customer_business_desc(
        start_time: str,
        end_time: str,
        ip: str | None = None,
        domain: str | None = None,
    ) -> str:
        """Query customer business description to help judge whether anomalous traffic is an attack.

        Looks up the entity in the GF ES index to find its gamedun_id, then checks
        a local special-customer registry. Returns a business context hint or a
        generic "no special business" message.

        Note: Only one of ip or domain should be provided.

        Args:
            start_time: Query start time, YYYY-MM-DD HH:MM:SS.
            end_time: Query end time, YYYY-MM-DD HH:MM:SS.
            ip: Server IP address (use instead of domain).
            domain: Domain name (use instead of ip).

        Returns:
            A string describing the customer's business context, or
            "客户无特殊业务，正常流程分析即可" if no special entry is found.
        """
        if not ip and not domain:
            return "需要IP或者域名才能判断是否有特殊业务"

        field = "http_host" if domain else "server_addr"
        value = domain or ip
        dsl: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {field: value}},
                        {"range": {"time": {"gte": _normalise_time(start_time), "lte": _normalise_time(end_time)}}},
                    ]
                }
            },
            "sort": [{"time": {"order": "desc"}}],
            "size": 1,
        }
        es = await _adapter()
        try:
            resp = await es.execute_dsl(dsl, source="GF")
        except Exception as exc:
            logger.warning("query_customer_business_desc ES query failed: %s", exc)
            return "未获取到客户信息"

        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            return "客户无特殊业务，正常流程分析即可"

        gamedun_id = hits[0].get("_source", {}).get("gamedun_id")
        if not gamedun_id:
            return "客户无特殊业务，正常流程分析即可"

        # Check local special-customer registry (optional file — absent in dev)
        if _SPECIAL_CUSTOMER_JSON.exists():
            try:
                data = json.loads(_SPECIAL_CUSTOMER_JSON.read_text(encoding="utf-8"))
                for item in data.get("client_special_list", []):
                    if gamedun_id in item.get("domains", []):
                        return (
                            "客户业务允许脚本抢购，请求突增视为正常业务行为而非攻击，"
                            "忽略请求频率异常、UA异常、客户端高度集中等异常表现。"
                            "安全干预的唯一判定标准为'后端基础设施健康度'，而非'前端请求频率'，"
                            "防护策略上建议用业务防刷和频率限制，不用完全限制死"
                        )
            except Exception as exc:
                logger.warning("Failed to read special_customer.json: %s", exc)

        return "客户无特殊业务，正常流程分析即可"

    return [
        query_es_raw_logs,
        query_es_unique_count,
        query_es_top_n,
        query_es_qps_trend,
        query_es_status_code_trend,
        query_es_top_n_trend,
        query_request_count,
        query_status_code_distribution,
        query_es_trend_comparison,
        query_customer_business_desc,
    ]


# Default tool list (no injected adapter — uses ESAdapter from settings)
ES_TOOLS = _make_es_tools()
