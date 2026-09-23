"""
Model router — maps investigation task types to model profiles.

Business code calls `router.profile_for(task_type)` instead of hardcoding
a profile. This lets us adjust routing (e.g., downgrade to fast_classifier
in cost-saving mode) without touching node code.
"""

from __future__ import annotations

from runtime.llm.profiles import ModelProfile

# Task-type strings that appear in SessionState.agent_task context
_ROUTING_TABLE: dict[str, ModelProfile] = {
    "classify": ModelProfile.FAST_CLASSIFIER,
    "triage": ModelProfile.FAST_CLASSIFIER,
    "route": ModelProfile.FAST_CLASSIFIER,
    "tool_call": ModelProfile.TOOL_REASONER,
    "investigate": ModelProfile.TOOL_REASONER,
    "diagnose": ModelProfile.TOOL_REASONER,
    "extract": ModelProfile.STRUCTURED_EXTRACTOR,
    "parse": ModelProfile.STRUCTURED_EXTRACTOR,
    "report": ModelProfile.REPORT_WRITER,
    "summarize": ModelProfile.REPORT_WRITER,
    "analyze_long": ModelProfile.LONG_CONTEXT_ANALYST,
    "offline": ModelProfile.LOCAL_OFFLINE_MODEL,
}

_DEFAULT_PROFILE = ModelProfile.TOOL_REASONER


def profile_for(task_type: str) -> ModelProfile:
    """
    Return the appropriate model profile for a given task type.

    Falls back to TOOL_REASONER for unknown task types.
    """
    return _ROUTING_TABLE.get(task_type.lower(), _DEFAULT_PROFILE)
