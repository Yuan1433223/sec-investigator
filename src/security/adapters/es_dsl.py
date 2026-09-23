"""
Elasticsearch DSL query builder.

Parameterized templates that cover the query patterns used by log_detective.
All methods are pure (no I/O) — they return dicts ready to pass to the ES client.

Migrated from KKShieldHelper-main/utils/es_dsl_builder.py with the following changes:
- Ported to modern Python (no Optional imports, use X | None)
- Removed legacy GF/WAF ESTools LLM-generation class (kept as ESTools.gen_*_dsl
  in the donor — not needed here; tools use explicit DSL templates)
- Time field is parameterized (GF uses "time", WAF uses "create_date")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _normalise_time(t: str) -> str:
    """
    Normalise any reasonable datetime string to 'YYYY-MM-DD HH:MM:SS'.

    Accepts:
      '2026-04-24 19:25:21'            → unchanged
      '2026-04-24T19:25:21+08:00'      → '2026-04-24 19:25:21'
      '2026-04-24T19:25:21Z'           → '2026-04-24 19:25:21'
      '2026-04-24T19:25:21'            → '2026-04-24 19:25:21'
    """
    t = t.strip()
    # Already in the required format
    if len(t) == 19 and t[10] == " ":
        return t
    # ISO-8601 variants — strip timezone, replace T separator
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(t, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # Last resort: return as-is and let ES report the error
    return t


class ESDSLBuilder:
    """Elasticsearch DSL template factory — pure, stateless, no I/O."""

    # -------------------------------------------------------------------------
    # Filter building block
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_filters(
        domain: str | None = None,
        ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        time_field: str = "time",
        status_range: tuple[int, int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build reusable ES bool-filter clauses.

        Args:
            domain: Filter by http_host (GF) or servername (WAF).
            ip: Filter by server_addr (GF node IP).
            start_time: Inclusive lower bound (YYYY-MM-DD HH:MM:SS).
            end_time: Inclusive upper bound (YYYY-MM-DD HH:MM:SS).
            time_field: Field to use for time range ("time" for GF, "create_date" for WAF).
            status_range: (gte, lt) tuple for HTTP status code range, e.g. (400, 500).
        """
        filters: list[dict[str, Any]] = []

        if domain:
            filters.append({"term": {"http_host": domain}})
        if ip:
            filters.append({"term": {"server_addr": ip}})
        if start_time and end_time:
            filters.append({"range": {time_field: {"gte": _normalise_time(start_time), "lte": _normalise_time(end_time)}}})
        if status_range:
            gte, lt = status_range
            filters.append({"range": {"status": {"gte": gte, "lt": lt}}})

        return filters

    # -------------------------------------------------------------------------
    # Query templates
    # -------------------------------------------------------------------------

    @staticmethod
    def raw_documents(
        fields: list[str],
        size: int = 20,
        **filter_params: Any,
    ) -> dict[str, Any]:
        """Return most-recent N documents with selected _source fields."""
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "_source": fields,
            "size": size,
            "sort": [{"time": {"order": "desc"}}],
        }

    @staticmethod
    def unique_count(field: str, **filter_params: Any) -> dict[str, Any]:
        """Cardinality aggregation — count distinct values of a field."""
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "size": 0,
            "track_total_hits": True,
            "aggs": {"result": {"cardinality": {"field": field}}},
        }

    @staticmethod
    def top_n_ranking(field: str, size: int = 10, **filter_params: Any) -> dict[str, Any]:
        """Terms aggregation — top N values by doc count."""
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "size": 0,
            "aggs": {
                "result": {
                    "terms": {"field": field, "size": size, "order": {"_count": "desc"}}
                }
            },
        }

    @staticmethod
    def time_series_count(
        interval: str,
        time_field: str = "time",
        time_format: str = "yyyy-MM-dd HH:mm:ss",
        **filter_params: Any,
    ) -> dict[str, Any]:
        """Date-histogram aggregation — doc count per time bucket (QPS/traffic trend)."""
        filter_params["time_field"] = time_field
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "size": 0,
            "track_total_hits": True,
            "aggs": {
                "result": {
                    "date_histogram": {
                        "field": time_field,
                        "fixed_interval": interval,
                        "format": time_format,
                    }
                }
            },
        }

    @staticmethod
    def time_series_unique_count(
        unique_field: str,
        interval: str,
        time_field: str = "time",
        time_format: str = "yyyy-MM-dd HH:mm",
        **filter_params: Any,
    ) -> dict[str, Any]:
        """Date-histogram with nested cardinality (UV trend)."""
        filter_params["time_field"] = time_field
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "size": 0,
            "track_total_hits": True,
            "aggs": {
                "result": {
                    "date_histogram": {
                        "field": time_field,
                        "fixed_interval": interval,
                        "format": time_format,
                    },
                    "aggs": {"count": {"cardinality": {"field": unique_field}}},
                }
            },
        }

    @staticmethod
    def top_n_time_series(
        group_field: str,
        top_n: int,
        interval: str,
        time_field: str = "time",
        time_format: str = "yyyy-MM-dd HH:mm",
        **filter_params: Any,
    ) -> dict[str, Any]:
        """Terms + nested date-histogram — top N values over time (double aggregation)."""
        filter_params["time_field"] = time_field
        return {
            "query": {"bool": {"filter": ESDSLBuilder._build_filters(**filter_params)}},
            "size": 0,
            "aggs": {
                "top_items": {
                    "terms": {
                        "field": group_field,
                        "size": top_n,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "time_series": {
                            "date_histogram": {
                                "field": time_field,
                                "fixed_interval": interval,
                                "format": time_format,
                            }
                        }
                    },
                }
            },
        }
