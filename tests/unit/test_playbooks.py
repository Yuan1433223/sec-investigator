"""
Unit tests for kks_security.playbooks.
"""

import pytest

from kks_runtime.llm.profiles import ModelProfile
from kks_security.playbooks.base import PlaybookKind
from kks_security.playbooks.catalog import CATALOG, get_playbook


def test_all_playbook_kinds_in_catalog():
    for kind in PlaybookKind:
        assert kind in CATALOG, f"{kind} missing from CATALOG"


def test_get_playbook_returns_correct_kind():
    for kind in PlaybookKind:
        pb = get_playbook(kind)
        assert pb.kind == kind


def test_all_playbooks_have_non_empty_system_prompt():
    for kind, pb in CATALOG.items():
        assert pb.system_prompt.strip(), f"{kind} has empty system_prompt"


def test_all_playbooks_have_required_findings():
    for kind, pb in CATALOG.items():
        assert isinstance(pb.required_findings, list), f"{kind} required_findings is not a list"
        assert len(pb.required_findings) > 0, f"{kind} has no required_findings"


def test_all_playbooks_have_valid_model_profile():
    valid_profiles = set(ModelProfile)
    for kind, pb in CATALOG.items():
        assert pb.model_profile in valid_profiles, (
            f"{kind} model_profile {pb.model_profile!r} is not a valid ModelProfile"
        )


def test_playbook_max_tool_calls_non_negative():
    for kind, pb in CATALOG.items():
        assert pb.max_tool_calls >= 0, f"{kind} max_tool_calls is negative"


def test_playbook_is_frozen():
    pb = get_playbook(PlaybookKind.LOG_ANALYSIS)
    with pytest.raises((AttributeError, TypeError)):
        pb.system_prompt = "override"  # type: ignore[misc]


def test_log_analysis_uses_tool_reasoner():
    pb = get_playbook(PlaybookKind.LOG_ANALYSIS)
    assert pb.model_profile == ModelProfile.TOOL_REASONER


def test_infra_diagnosis_uses_tool_reasoner():
    pb = get_playbook(PlaybookKind.INFRA_DIAGNOSIS)
    assert pb.model_profile == ModelProfile.TOOL_REASONER


def test_attack_analysis_uses_tool_reasoner():
    pb = get_playbook(PlaybookKind.ATTACK_ANALYSIS)
    assert pb.model_profile == ModelProfile.TOOL_REASONER


def test_alert_triage_uses_fast_classifier():
    pb = get_playbook(PlaybookKind.ALERT_TRIAGE)
    assert pb.model_profile == ModelProfile.FAST_CLASSIFIER


def test_report_generation_uses_report_writer():
    pb = get_playbook(PlaybookKind.REPORT_GENERATION)
    assert pb.model_profile == ModelProfile.REPORT_WRITER


def test_report_generation_has_zero_tool_calls():
    """Reporter does not call tools — it synthesises existing findings."""
    pb = get_playbook(PlaybookKind.REPORT_GENERATION)
    assert pb.max_tool_calls == 0


def test_alert_triage_required_findings():
    pb = get_playbook(PlaybookKind.ALERT_TRIAGE)
    assert set(pb.required_findings) == {"logs", "machine", "security"}


def test_log_analysis_required_findings():
    pb = get_playbook(PlaybookKind.LOG_ANALYSIS)
    assert pb.required_findings == ["logs"]


def test_infra_diagnosis_required_findings():
    pb = get_playbook(PlaybookKind.INFRA_DIAGNOSIS)
    assert pb.required_findings == ["machine"]


def test_attack_analysis_required_findings():
    pb = get_playbook(PlaybookKind.ATTACK_ANALYSIS)
    assert pb.required_findings == ["security"]


def test_playbook_kind_values_are_strings():
    """PlaybookKind must be usable as string keys (StrEnum contract)."""
    for kind in PlaybookKind:
        assert isinstance(kind, str)
        assert kind == kind.value
