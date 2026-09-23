from kks_security.schemas.findings import LogFindings, MachineFindings, SecurityFindings


def test_log_findings_defaults():
    f = LogFindings(summary="test")
    assert f.risk_level == "medium"
    assert f.error_rate == {}
    assert f.top_errors == []
    assert f.trend_comparison is None


def test_log_findings_full():
    f = LogFindings(
        summary="QPS spike detected",
        qps_info="avg 500 rps, peak 2000 rps",
        error_rate={"4xx": "12%", "5xx": "3%"},
        top_errors=["502: /api/v1 x1200", "403: /admin x800"],
        risk_level="high",
    )
    d = f.model_dump()
    assert d["risk_level"] == "high"
    assert d["error_rate"]["4xx"] == "12%"


def test_security_findings_defaults():
    f = SecurityFindings(summary="Protection active")
    assert f.cc_status == "unknown"
    assert f.ddos_status == "unknown"
    assert f.risk_level == "medium"
    assert f.operational_issue == "none"


def test_machine_findings_health_status():
    f = MachineFindings(summary="All green", health_status="healthy", risk_level="low")
    assert f.health_status == "healthy"
    assert f.risk_level == "low"


def test_findings_dump_json_serialisable():
    import json

    f = LogFindings(summary="ok", risk_level="low")
    raw = f.model_dump(mode="json")
    # Should not raise
    json.dumps(raw)
