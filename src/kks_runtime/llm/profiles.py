"""
Model runtime abstraction.

Business code requests a ModelProfile — never a vendor SDK directly.
`build_model(profile)` resolves the profile to a LangChain BaseChatModel
using settings at call time. No module-level singletons.

Supported providers (selected by llm_provider setting):
  - "openai"     → ChatOpenAI (OpenAI / OpenAI-compatible relay)
  - "anthropic"  → ChatAnthropic (Anthropic direct or relay)
  - local profile → ChatOpenAI pointed at local_model_base
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from langchain_core.language_models import BaseChatModel

from kks_runtime.config.settings import Settings, get_settings


class ModelProfile(StrEnum):
    FAST_CLASSIFIER = "fast_classifier"
    TOOL_REASONER = "tool_reasoner"
    STRUCTURED_EXTRACTOR = "structured_extractor"
    REPORT_WRITER = "report_writer"
    LONG_CONTEXT_ANALYST = "long_context_analyst"
    LOCAL_OFFLINE_MODEL = "local_offline_model"


@dataclass(frozen=True)
class ModelConfig:
    """Per-profile defaults. All fields can be overridden at call time."""

    temperature: float = 0.0
    max_tokens: int | None = None
    use_local: bool = False
    extra: dict[str, Any] | None = None


_REGISTRY: dict[ModelProfile, ModelConfig] = {
    ModelProfile.FAST_CLASSIFIER: ModelConfig(temperature=0.0, max_tokens=1024),
    ModelProfile.TOOL_REASONER: ModelConfig(temperature=0.0),
    ModelProfile.STRUCTURED_EXTRACTOR: ModelConfig(temperature=0.0, max_tokens=2048),
    ModelProfile.REPORT_WRITER: ModelConfig(temperature=0.3),
    ModelProfile.LONG_CONTEXT_ANALYST: ModelConfig(temperature=0.0),
    ModelProfile.LOCAL_OFFLINE_MODEL: ModelConfig(temperature=0.0, use_local=True),
}


def build_model(
    profile: ModelProfile,
    settings: Settings | None = None,
    **overrides: Any,
) -> BaseChatModel:
    """
    Instantiate a LangChain chat model for the given capability profile.

    Reads settings on every call; no cached instances (hard rule 4).
    Provider is selected by settings.llm_provider:
      "anthropic" → ChatAnthropic with claude_model_name
      "openai"    → ChatOpenAI with plus_model_name / flash_model_name
    """
    s = settings or get_settings()
    cfg = _REGISTRY[profile]

    # Local endpoint always wins regardless of provider setting
    if cfg.use_local:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=s.local_model_name,
            api_key=s.local_model_api_key,
            base_url=s.local_model_base,
            temperature=cfg.temperature,
            **(cfg.extra or {}),
            **overrides,
        )

    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # FAST_CLASSIFIER uses the flash model; everything else uses main model
        model_name = (
            s.claude_flash_model_name
            if profile == ModelProfile.FAST_CLASSIFIER
            else s.claude_model_name
        )
        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": s.anthropic_api_key,
            "base_url": s.anthropic_base_url,
            "temperature": cfg.temperature,
            **(cfg.extra or {}),
            **overrides,
        }
        if cfg.max_tokens is not None:
            kwargs["max_tokens"] = cfg.max_tokens
        return ChatAnthropic(**kwargs)

    # Default: OpenAI-compatible
    from langchain_openai import ChatOpenAI

    model_name = (
        s.flash_model_name
        if profile == ModelProfile.FAST_CLASSIFIER
        else s.plus_model_name
    )
    kwargs = {
        "model": model_name,
        "api_key": s.openai_api_key or "placeholder",
        "base_url": s.openai_base_url,
        "temperature": cfg.temperature,
        **(cfg.extra or {}),
        **overrides,
    }
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    return ChatOpenAI(**kwargs)


# Backwards-compatible alias
def get_model(profile: ModelProfile, settings: Settings | None = None) -> BaseChatModel:
    return build_model(profile, settings)
