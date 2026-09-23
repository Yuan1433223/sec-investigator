from kks_security.adapters.es_dsl import ESDSLBuilder


def test_raw_documents_basic():
    dsl = ESDSLBuilder.raw_documents(
        fields=["time", "status"],
        size=5,
        domain="example.com",
        start_time="2026-04-22 00:00:00",
        end_time="2026-04-22 01:00:00",
    )
    assert dsl["size"] == 5
    assert dsl["_source"] == ["time", "status"]
    filters = dsl["query"]["bool"]["filter"]
    assert any("http_host" in str(f) for f in filters)
    assert any("range" in f for f in filters)


def test_unique_count_no_filters():
    dsl = ESDSLBuilder.unique_count(field="remote_addr")
    assert dsl["size"] == 0
    assert dsl["aggs"]["result"]["cardinality"]["field"] == "remote_addr"
    assert dsl["query"]["bool"]["filter"] == []


def test_top_n_ranking_order():
    dsl = ESDSLBuilder.top_n_ranking(field="request_uri", size=20, domain="x.com")
    terms = dsl["aggs"]["result"]["terms"]
    assert terms["field"] == "request_uri"
    assert terms["size"] == 20
    assert terms["order"] == {"_count": "desc"}


def test_time_series_count_interval():
    dsl = ESDSLBuilder.time_series_count(interval="5m", domain="x.com")
    hist = dsl["aggs"]["result"]["date_histogram"]
    assert hist["fixed_interval"] == "5m"
    assert hist["field"] == "time"  # default GF time field


def test_time_series_count_waf_time_field():
    dsl = ESDSLBuilder.time_series_count(
        interval="1m", time_field="create_date", domain="x.com"
    )
    hist = dsl["aggs"]["result"]["date_histogram"]
    assert hist["field"] == "create_date"


def test_time_series_unique_count_nested():
    dsl = ESDSLBuilder.time_series_unique_count(
        unique_field="remote_addr", interval="1h"
    )
    aggs = dsl["aggs"]["result"]
    assert "aggs" in aggs
    assert aggs["aggs"]["count"]["cardinality"]["field"] == "remote_addr"


def test_top_n_time_series_structure():
    dsl = ESDSLBuilder.top_n_time_series(
        group_field="remote_addr", top_n=5, interval="1m", domain="x.com"
    )
    top_items = dsl["aggs"]["top_items"]
    assert top_items["terms"]["field"] == "remote_addr"
    assert top_items["terms"]["size"] == 5
    assert "time_series" in top_items["aggs"]


def test_status_range_filter():
    dsl = ESDSLBuilder.raw_documents(
        fields=["status"], status_range=(400, 500), domain="x.com"
    )
    filters = dsl["query"]["bool"]["filter"]
    status_filter = next(f for f in filters if "range" in f and "status" in f["range"])
    assert status_filter["range"]["status"]["gte"] == 400
    assert status_filter["range"]["status"]["lt"] == 500


def test_ip_filter():
    dsl = ESDSLBuilder.unique_count(field="remote_addr", ip="1.2.3.4")
    filters = dsl["query"]["bool"]["filter"]
    assert any(f.get("term", {}).get("server_addr") == "1.2.3.4" for f in filters)
