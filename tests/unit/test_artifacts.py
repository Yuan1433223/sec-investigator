from datetime import datetime

from kks_runtime.artifacts.investigation import InvestigationArtifact, ReportArtifact


def test_investigation_artifact_defaults():
    a = InvestigationArtifact(
        session_id="s1",
        target="1.2.3.4",
        risk_level="medium",
        summary="test summary",
    )
    assert a.artifact_type == "investigation"
    assert a.findings == {}
    assert a.asset_findings == {}
    assert a.report == {}
    assert a.recommendations == []
    assert isinstance(a.created_at, datetime)


def test_investigation_artifact_dump():
    a = InvestigationArtifact(
        session_id="s1",
        target="example.com",
        findings={"logs": {"qps": 100}},
        risk_level="high",
        summary="spike detected",
        recommendations=["check WAF logs"],
    )
    d = a.model_dump(mode="json")
    assert d["artifact_type"] == "investigation"
    assert d["risk_level"] == "high"
    assert d["findings"]["logs"]["qps"] == 100
    assert d["asset_findings"] == {}
    assert d["report"] == {}


def test_report_artifact():
    r = ReportArtifact(
        session_id="s2",
        target="example.com",
        content="# Report\n\nAll clear.",
    )
    assert r.artifact_type == "report"
    d = r.model_dump(mode="json")
    assert "# Report" in d["content"]
