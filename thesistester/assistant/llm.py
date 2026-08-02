"""Provider-neutral, structured LLM boundary for the research assistant."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class LLMConfigurationError(ValueError):
    """Raised when the optional assistant provider is not safely configured."""


class StructuredLLMClient(Protocol):
    """Minimal injectable client contract; provider SDKs stay outside engine code."""

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    max_tool_rounds: int
    max_history_messages: int


def load_llm_settings(path: str | Path = "config/assistant.toml") -> LLMSettings:
    """Load non-secret assistant settings from tracked TOML."""
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        raise LLMConfigurationError("Missing [assistant] configuration.")
    return LLMSettings(
        provider=str(assistant.get("provider", "")),
        model=str(assistant.get("model", "")),
        max_tool_rounds=int(assistant.get("max_tool_rounds", 0)),
        max_history_messages=int(assistant.get("max_history_messages", 0)),
    )


def require_openai_api_key() -> str:
    """Return only an environment-injected key; never read tracked configuration."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key or key == "REPLACE_WITH_ROTATED_OPENAI_API_KEY":
        raise LLMConfigurationError("Set OPENAI_API_KEY to a rotated credential.")
    return key
