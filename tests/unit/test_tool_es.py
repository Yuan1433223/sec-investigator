"""
Unit tests for ES tool helpers and tool output shapes.

Group 1 — _total_hits and _agg_result (pure).
Group 2 — tool output shapes via injected mock ESAdapter.
Group 3 — status range map correctness.
Group 4 — new tools: query_request_count, query_status_code_distribution,
           query_es_trend_comparison, query_customer_business_desc.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from kks_security.tools.es_tools import (
    _STATUS_RANGES,
    _agg_result,
    _make_es_tools,
    _total_hits,
)

# ---------------------------------------------------------------------------
# Group 1 — pure helpers
# ---------------------------------------------------------------------------


def test_total_hits_dict_form():
    resp = {"hits": {"total": {"value": 42}}}
    assert _total_hits(resp) == 42


def test_total_hits_int_form():
    resp = {"hits": {"total": 7}}
    assert _total_hits(resp) == 7


def test_total_hits_missing():
    assert _total_hits({}) == 0


def test_agg_result_result_key():
    resp = {"aggregations": {"result": {"value": 5}}}
    assert _agg_result(resp) == {"value": 5}


def test_agg_result_top_items_key():
    resp = {"aggregations": {"top_items": {"buckets": []}}}
    assert _agg_result(resp) == {"buckets": []}


def test_agg_result_fallback():
    resp = {"aggregations": {}}
    assert _agg_result(resp) == {}


# ---------------------------------------------------------------------------
# Group 2 — tool output shapes
# ---------------------------------------------------------------------------


def _mock_adapter(response: dict):
    m = MagicMock()
    m.execute_dsl = AsyncMock(return_value=response)
    return m


def _toolmap(adapter):
    return {t.name: t for t in _make_es_tools(adapter=adapter)}


async def test_query_es_raw_logs_shapes_output():
    es_resp = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {"_source": {"time": "2026-01-01", "status": 200}},
                {"_source": {"time": "2026-01-01", "status": 404}},
            ],
        },
        "aggregations": {},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_raw_logs"].ainvoke({"size": 2, "domain": "example.com"})
    assert result["total"] == 2
    assert len(result["hits"]) == 2
    assert result["hits"][0]["status"] == 200


async def test_query_es_unique_count_shapes_output():
    es_resp = {
        "hits": {"total": {"value": 1000}},
        "aggregations": {"result": {"value": 42}},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_unique_count"].ainvoke({"field": "remote_addr"})
    assert result["field"] == "remote_addr"
    assert result["unique_count"] == 42
    assert result["total_docs"] == 1000


async def test_query_es_top_n_shapes_output():
    es_resp = {
        "hits": {"total": {"value": 500}},
        "aggregations": {
            "result": {
                "buckets": [
                    {"key": "1.2.3.4", "doc_count": 300},
                    {"key": "5.6.7.8", "doc_count": 200},
                ]
            }
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_top_n"].ainvoke({"field": "remote_addr", "size": 10})
    assert result["field"] == "remote_addr"
    assert len(result["top_n"]) == 2
    assert result["top_n"][0] == {"value": "1.2.3.4", "count": 300}


async def test_query_es_qps_trend_shapes_output():
    es_resp = {
        "hits": {"total": {"value": 100}},
        "aggregations": {
            "result": {
                "buckets": [
                    {"key_as_string": "2026-01-01T00:00:00", "doc_count": 50},
                    {"key_as_string": "2026-01-01T00:01:00", "doc_count": 50},
                ]
            }
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_qps_trend"].ainvoke(
        {"interval": "1m", "domain": "example.com"}
    )
    assert result["interval"] == "1m"
    assert result["total"] == 100
    assert len(result["trend"]) == 2
    assert result["trend"][0] == {"time": "2026-01-01T00:00:00", "count": 50}


async def test_query_es_status_code_trend_shapes_output():
    es_resp = {
        "hits": {"total": {"value": 30}},
        "aggregations": {
            "result": {
                "buckets": [
                    {"key_as_string": "2026-01-01T00:00:00", "doc_count": 30},
                ]
            }
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_status_code_trend"].ainvoke(
        {"status_type": "4xx", "interval": "5m"}
    )
    assert result["status_type"] == "4xx"
    assert result["total"] == 30


async def test_query_es_top_n_trend_shapes_output():
    es_resp = {
        "hits": {"total": {"value": 100}},
        "aggregations": {
            "result": {
                "buckets": [
                    {
                        "key": "1.2.3.4",
                        "doc_count": 80,
                        "time_series": {
                            "buckets": [
                                {"key_as_string": "2026-01-01T00:00:00", "doc_count": 40},
                                {"key_as_string": "2026-01-01T00:01:00", "doc_count": 40},
                            ]
                        },
                    }
                ]
            }
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_top_n_trend"].ainvoke(
        {"field": "remote_addr", "top_n": 5, "interval": "1m"}
    )
    assert result["field"] == "remote_addr"
    assert len(result["top_n"]) == 1
    assert result["top_n"][0]["value"] == "1.2.3.4"
    assert len(result["top_n"][0]["trend"]) == 2


# ---------------------------------------------------------------------------
# Group 3 — status range map
# ---------------------------------------------------------------------------


def test_status_ranges_all_keys_present():
    for key in ("1xx", "2xx", "3xx", "4xx", "5xx", "normal"):
        assert key in _STATUS_RANGES


def test_status_ranges_correct_values():
    assert _STATUS_RANGES["1xx"] == (100, 200)
    assert _STATUS_RANGES["2xx"] == (200, 300)
    assert _STATUS_RANGES["3xx"] == (300, 400)
    assert _STATUS_RANGES["4xx"] == (400, 500)
    assert _STATUS_RANGES["5xx"] == (500, 600)
    assert _STATUS_RANGES["normal"] == (200, 400)


def test_status_ranges_contiguous_and_non_overlapping():
    ranges = [v for k, v in _STATUS_RANGES.items() if k != "normal"]
    for low, high in ranges:
        assert low < high


# ---------------------------------------------------------------------------
# Group 4 — new tools
# ---------------------------------------------------------------------------


async def test_query_request_count_domain():
    es_resp = {
        "hits": {"total": {"value": 5000}},
        "aggregations": {"total_requests": {"value": 5000}},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_request_count"].ainvoke({
        "query_by": "domain",
        "value": "example.com",
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
    })
    assert result == {"count": 5000}


async def test_query_request_count_ip_list():
    es_resp = {
        "hits": {"total": {"value": 100}},
        "aggregations": {"total_requests": {"value": 100}},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_request_count"].ainvoke({
        "query_by": "ip",
        "value": ["1.2.3.4", "5.6.7.8"],
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
    })
    assert result["count"] == 100


async def test_query_status_code_distribution_shape():
    es_resp = {
        "hits": {"total": {"value": 1000}},
        "aggregations": {
            "current": {
                "dist": {"buckets": [
                    {"key": 200, "doc_count": 800},
                    {"key": 404, "doc_count": 200},
                ]}
            },
            "previous": {
                "dist": {"buckets": [
                    {"key": 200, "doc_count": 950},
                    {"key": 404, "doc_count": 50},
                ]}
            },
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_status_code_distribution"].ainvoke({
        "query_by": "domain",
        "value": "example.com",
        "start_time": "2026-01-01 00:30:00",
        "end_time": "2026-01-01 01:00:00",
    })
    assert "current" in result
    assert "previous" in result
    assert result["current"][0] == {"status": 200, "count": 800}
    assert result["previous"][1] == {"status": 404, "count": 50}


async def test_query_status_code_distribution_waf_source():
    es_resp = {
        "hits": {"total": {"value": 10}},
        "aggregations": {
            "current": {"dist": {"buckets": [{"key": 200, "doc_count": 10}]}},
            "previous": {"dist": {"buckets": []}},
        },
    }
    adapter = _mock_adapter(es_resp)
    tools = _toolmap(adapter)
    result = await tools["query_status_code_distribution"].ainvoke({
        "query_by": "domain",
        "value": "waf.example.com",
        "start_time": "2026-01-01 00:30:00",
        "end_time": "2026-01-01 01:00:00",
        "source": "WAF",
    })
    assert result["current"][0]["status"] == 200
    call_args = adapter.execute_dsl.call_args
    passed_source = (
        call_args.kwargs.get("source") or
        (call_args.args[1] if len(call_args.args) > 1 else None)
    )
    assert passed_source == "WAF"


async def test_query_es_trend_comparison_yesterday_shape():
    es_resp = {
        "hits": {"total": {"value": 60}},
        "aggregations": {
            "result": {
                "buckets": [
                    {"key_as_string": "2026-01-01T00:00:00", "doc_count": 30},
                    {"key_as_string": "2026-01-01T01:00:00", "doc_count": 30},
                ]
            }
        },
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [{"type": "request_count"}],
        "comparison_mode": "current_vs_yesterday",
        "current_start_time": "2026-01-02 00:00:00",
        "current_end_time": "2026-01-02 02:00:00",
        "domain": "example.com",
    })
    assert result["comparison_mode"] == "current_vs_yesterday"
    assert "time_range" in result
    assert "metrics" in result
    assert "request_count" in result["metrics"]
    m = result["metrics"]["request_count"]
    assert "current_period" in m
    assert "compare_period" in m
    assert "comparison" in m
    assert "total_change_percent" in m["comparison"]


async def test_query_es_trend_comparison_last_week_dates():
    from datetime import datetime, timedelta
    es_resp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {"result": {"buckets": []}},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [{"type": "request_count"}],
        "comparison_mode": "current_vs_last_week",
        "current_start_time": "2026-04-24 10:00:00",
        "current_end_time": "2026-04-24 11:00:00",
    })
    tr = result["time_range"]
    cur_start = datetime.strptime(tr["current"]["start_time"], "%Y-%m-%d %H:%M:%S")
    cmp_start = datetime.strptime(tr["compare"]["start_time"], "%Y-%m-%d %H:%M:%S")
    assert (cur_start - cmp_start) == timedelta(days=7)


async def test_query_es_trend_comparison_period_vs_period():
    es_resp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {"result": {"buckets": []}},
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [{"type": "status_code", "status_type": "5xx"}],
        "comparison_mode": "period_vs_period",
        "current_start_time": "2026-04-24 10:00:00",
        "current_end_time": "2026-04-24 11:00:00",
        "compare_start_time": "2026-04-23 10:00:00",
        "compare_end_time": "2026-04-23 11:00:00",
    })
    assert "status_code_5xx" in result["metrics"]
    assert result["time_range"]["compare"]["start_time"] == "2026-04-23 10:00:00"


async def test_query_es_trend_comparison_empty_metrics_error():
    tools = _toolmap(_mock_adapter({}))
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [],
        "comparison_mode": "current_vs_yesterday",
        "current_start_time": "2026-04-24 10:00:00",
        "current_end_time": "2026-04-24 11:00:00",
    })
    assert "error" in result


async def test_query_es_trend_comparison_period_missing_compare_times():
    tools = _toolmap(_mock_adapter({}))
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [{"type": "request_count"}],
        "comparison_mode": "period_vs_period",
        "current_start_time": "2026-04-24 10:00:00",
        "current_end_time": "2026-04-24 11:00:00",
    })
    assert "error" in result


async def test_query_es_trend_comparison_pct_change_zero_base():
    """When compare period is zero, +100% should be returned for positive current."""
    es_resp_cur = {
        "hits": {"total": {"value": 100}},
        "aggregations": {
            "result": {"buckets": [{"key_as_string": "2026-01-02T00:00:00", "doc_count": 100}]}
        },
    }
    es_resp_cmp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {"result": {"buckets": []}},
    }
    adapter = MagicMock()
    adapter.execute_dsl = AsyncMock(side_effect=[es_resp_cur, es_resp_cmp])
    tools = _toolmap(adapter)
    result = await tools["query_es_trend_comparison"].ainvoke({
        "metrics": [{"type": "request_count"}],
        "comparison_mode": "current_vs_yesterday",
        "current_start_time": "2026-01-02 00:00:00",
        "current_end_time": "2026-01-02 01:00:00",
    })
    pct = result["metrics"]["request_count"]["comparison"]["total_change_percent"]
    assert pct == "+100%"


async def test_query_customer_business_desc_no_ip_or_domain():
    tools = _toolmap(_mock_adapter({}))
    result = await tools["query_customer_business_desc"].ainvoke({
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
    })
    assert "需要" in result


async def test_query_customer_business_desc_no_hits():
    es_resp = {"hits": {"total": {"value": 0}, "hits": []}}
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_customer_business_desc"].ainvoke({
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
        "domain": "example.com",
    })
    assert "无特殊业务" in result


async def test_query_customer_business_desc_hit_no_gamedun_id():
    es_resp = {
        "hits": {"total": {"value": 1}, "hits": [{"_source": {"http_host": "example.com"}}]}
    }
    tools = _toolmap(_mock_adapter(es_resp))
    result = await tools["query_customer_business_desc"].ainvoke({
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
        "domain": "example.com",
    })
    assert "无特殊业务" in result


async def test_query_customer_business_desc_es_error_returns_fallback():
    adapter = MagicMock()
    adapter.execute_dsl = AsyncMock(side_effect=Exception("ES down"))
    tools = _toolmap(adapter)
    result = await tools["query_customer_business_desc"].ainvoke({
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-01-01 01:00:00",
        "domain": "example.com",
    })
    assert "未获取到" in result


def test_es_tools_list_includes_new_tools():
    from kks_security.tools.es_tools import ES_TOOLS
    names = {t.name for t in ES_TOOLS}
    assert "query_request_count" in names
    assert "query_status_code_distribution" in names
    assert "query_es_trend_comparison" in names
    assert "query_customer_business_desc" in names
