"""Provider-neutral, structured LLM boundary for the research assistant."""

from __future__ import annotations

import os
import json
from urllib import error, request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib


class LLMConfigurationError(ValueError):
    """Raised when the optional assistant provider is not safely configured."""


class LLMProviderError(RuntimeError):
    """Raised when a provider request fails or returns invalid structured output."""


class StructuredLLMClient(Protocol):
    """Minimal injectable client contract; provider SDKs stay outside engine code."""

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class OpenAITransport(Protocol):
    """Injectable HTTPS transport for deterministic provider tests."""

    def post_json(self, *, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class UrllibOpenAITransport:
    """Minimal standard-library transport; no provider SDK reaches engine code."""

    def post_json(self, *, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        outbound = request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=30) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMProviderError("OpenAI structured request failed.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI response must be an object.")
        return decoded


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    max_tool_rounds: int
    max_history_messages: int
    max_retries: int = 2


@dataclass(frozen=True)
class ResultsQASettings:
    """Non-secret settings for the results discussion channel (RQ-series)."""

    enabled: bool
    max_history_messages: int
    allow_time_enrichment: bool


@dataclass(frozen=True)
class ProductHelpSettings:
    """Non-secret settings for the product/help channel (RQ-series)."""

    enabled: bool
    max_history_messages: int
    max_corpus_chars: int


@dataclass
class OpenAIStructuredClient:
    """OpenAI Responses client restricted to JSON-schema output."""

    settings: LLMSettings
    api_key: str
    transport: OpenAITransport
    endpoint: str = "https://api.openai.com/v1/responses"
    last_attempt_count: int = 0

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": [{"type": "input_text", "text": user}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "assistant_response",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = None
        for attempt in range(1, self.settings.max_retries + 2):
            try:
                response = self.transport.post_json(
                    url=self.endpoint, api_key=self.api_key, payload=payload
                )
                self.last_attempt_count = attempt
                break
            except LLMProviderError:
                self.last_attempt_count = attempt
                if attempt == self.settings.max_retries + 1:
                    raise
        assert response is not None
        text = response.get("output_text")
        if not isinstance(text, str) or not text.strip():
            output = response.get("output")
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict) or item.get("type") != "message":
                        continue
                    content = item.get("content")
                    if not isinstance(content, list):
                        continue
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "output_text":
                            candidate = part.get("text")
                            if isinstance(candidate, str) and candidate.strip():
                                text = candidate
                                break
                    if isinstance(text, str) and text.strip():
                        break
        if not isinstance(text, str):
            raise LLMProviderError("OpenAI response did not contain output_text.")
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("OpenAI response is not valid JSON.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI structured output must be an object.")
        return decoded


def create_openai_client(
    settings: LLMSettings, *, transport: OpenAITransport | None = None
) -> OpenAIStructuredClient:
    """Create an OpenAI client only for the configured provider."""
    if settings.provider != "openai":
        raise LLMConfigurationError("Configured provider is not openai.")
    return OpenAIStructuredClient(
        settings=settings,
        api_key=require_openai_api_key(),
        transport=transport or UrllibOpenAITransport(),
    )


def _load_assistant_toml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise LLMConfigurationError("Assistant configuration must be a TOML table.")
    return payload


def load_llm_settings(path: str | Path = "config/assistant.toml") -> LLMSettings:
    """Load non-secret assistant settings from tracked TOML."""
    payload = _load_assistant_toml(path)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        raise LLMConfigurationError("Missing [assistant] configuration.")
    return LLMSettings(
        provider=str(assistant.get("provider", "")),
        model=str(assistant.get("model", "")),
        max_tool_rounds=int(assistant.get("max_tool_rounds", 0)),
        max_history_messages=int(assistant.get("max_history_messages", 0)),
        max_retries=int(assistant.get("max_retries", 2)),
    )


def _assistant_table(path: str | Path) -> dict[str, Any]:
    payload = _load_assistant_toml(path)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        raise LLMConfigurationError("Missing [assistant] configuration.")
    return assistant


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_enabled_flag(value: Any, *, default: bool = False) -> bool:
    """Parse channel enable flags fail-closed.

    Accepts real booleans and common true/false spellings. Strings like
    ``\"false\"`` must not enable a channel (``bool(\"false\")`` is True).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        return default
    if value is None:
        return default
    return default


def load_results_qa_settings(path: str | Path = "config/assistant.toml") -> ResultsQASettings:
    """Load `[assistant.results_qa]`; missing section → disabled safe defaults."""
    assistant = _assistant_table(path)
    top_history = _positive_int(assistant.get("max_history_messages"), default=12)
    section = assistant.get("results_qa")
    if not isinstance(section, dict):
        return ResultsQASettings(
            enabled=False,
            max_history_messages=top_history,
            allow_time_enrichment=False,
        )
    return ResultsQASettings(
        enabled=_coerce_enabled_flag(section.get("enabled", False), default=False),
        max_history_messages=_positive_int(
            section.get("max_history_messages"), default=top_history
        ),
        allow_time_enrichment=_coerce_enabled_flag(
            section.get("allow_time_enrichment", False), default=False
        ),
    )


def load_product_help_settings(path: str | Path = "config/assistant.toml") -> ProductHelpSettings:
    """Load `[assistant.product_help]`; missing section → disabled safe defaults."""
    assistant = _assistant_table(path)
    top_history = _positive_int(assistant.get("max_history_messages"), default=12)
    section = assistant.get("product_help")
    if not isinstance(section, dict):
        return ProductHelpSettings(
            enabled=False,
            max_history_messages=top_history,
            max_corpus_chars=24000,
        )
    return ProductHelpSettings(
        enabled=_coerce_enabled_flag(section.get("enabled", False), default=False),
        max_history_messages=_positive_int(
            section.get("max_history_messages"), default=top_history
        ),
        max_corpus_chars=_positive_int(section.get("max_corpus_chars"), default=24000),
    )


def is_draft_channel_message(message: Any) -> bool:
    """Return True when a conversation message belongs to thesis-draft history.

    Additive helper for RQ-1: treat missing/`None` ``channel`` as draft; any
    message with ``channel`` set (including ``results_qa`` / ``product_help``)
    is non-draft. Does not mutate messages or change orchestrator behavior yet.
    """
    if not isinstance(message, dict):
        return True
    channel = message.get("channel")
    if channel is None:
        return True
    if not isinstance(channel, str):
        return False
    return channel.strip() == ""


_OPENAI_API_KEY_PLACEHOLDER = "REPLACE_WITH_ROTATED_OPENAI_API_KEY"


def _usable_openai_api_key(value: Any) -> str | None:
    """Return a non-empty, non-placeholder key string; otherwise None."""
    if not isinstance(value, str):
        return None
    key = value.strip()
    if not key or key == _OPENAI_API_KEY_PLACEHOLDER:
        return None
    return key


def _api_key_from_secrets_mapping(secrets: Any) -> str | None:
    """Resolve OPENAI_API_KEY from a Streamlit-like secrets mapping.

    Precedence inside secrets:
    1. top-level ``OPENAI_API_KEY`` (canonical Community Cloud shape)
    2. nested ``[openai].api_key`` (compatibility only)
    """
    if secrets is None or not hasattr(secrets, "get"):
        return None
    try:
        flat = _usable_openai_api_key(secrets.get("OPENAI_API_KEY"))
    except Exception:
        flat = None
    if flat is not None:
        return flat
    try:
        section = secrets.get("openai")
    except Exception:
        return None
    if section is None or not hasattr(section, "get"):
        return None
    try:
        return _usable_openai_api_key(section.get("api_key"))
    except Exception:
        return None


def _read_streamlit_openai_api_key() -> str | None:
    """Best-effort Streamlit Secrets fallback; never reads tracked config files."""
    try:
        import streamlit as st

        return _api_key_from_secrets_mapping(st.secrets)
    except Exception:
        return None


def require_openai_api_key() -> str:
    """Return a rotated OpenAI key from env, else Streamlit Secrets.

    Resolution order:
    1. ``OPENAI_API_KEY`` environment variable
    2. Streamlit Secrets ``OPENAI_API_KEY``
    3. Streamlit Secrets ``[openai].api_key``

    Never reads tracked configuration (for example ``config/assistant.toml``).
    """
    key = _usable_openai_api_key(os.environ.get("OPENAI_API_KEY"))
    if key is not None:
        return key
    key = _usable_openai_api_key(_read_streamlit_openai_api_key())
    if key is not None:
        return key
    raise LLMConfigurationError("Set OPENAI_API_KEY to a rotated credential.")
