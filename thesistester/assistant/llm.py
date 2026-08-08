"""Provider-neutral, structured LLM boundary for the research assistant."""

from __future__ import annotations

import os
import json
import re
import ssl
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

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = bool(retryable)


# Auth / client faults should not burn retry budget (invalid key, bad request, etc.).
_NON_RETRYABLE_HTTP_CODES = frozenset({400, 401, 403, 404})


class StructuredLLMClient(Protocol):
    """Minimal injectable client contract; provider SDKs stay outside engine code."""

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class OpenAITransport(Protocol):
    """Injectable HTTPS transport for deterministic provider tests."""

    def post_json(self, *, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _sanitize_provider_error_text(text: str, *, api_key: str | None = None) -> str:
    """Redact credential-shaped tokens from provider/error text before UI display."""
    cleaned = text
    if isinstance(api_key, str):
        key = api_key.strip()
        # Exact configured key, including non-``sk-`` shapes OpenAI may echo.
        if len(key) >= 8:
            cleaned = cleaned.replace(key, "***")
    cleaned = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", cleaned)
    cleaned = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+", "Bearer ***", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:300]


def _openai_http_error_detail(exc: error.HTTPError, *, api_key: str | None = None) -> str:
    """Extract a short, non-secret OpenAI error detail from an HTTPError body."""
    raw = ""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    message = ""
    code: str | None = None
    if raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                if isinstance(err.get("message"), str):
                    message = err["message"]
                code_val = err.get("code")
                if isinstance(code_val, str) and code_val.strip():
                    code = code_val.strip()
                elif code_val is not None and not isinstance(code_val, bool):
                    # Some gateways emit numeric/stringable codes.
                    code = str(code_val).strip() or None
            elif isinstance(err, str):
                message = err
            elif isinstance(payload.get("message"), str):
                message = payload["message"]
        if not message:
            message = raw
    parts = [f"HTTP {exc.code}"]
    if code:
        parts.append(code)
    if message:
        parts.append(_sanitize_provider_error_text(message, api_key=api_key))
    elif isinstance(exc.reason, str) and exc.reason.strip():
        parts.append(_sanitize_provider_error_text(exc.reason, api_key=api_key))
    return ": ".join(parts)


def _openai_transport_failure_message(exc: BaseException, *, api_key: str | None = None) -> str:
    """Build an actionable provider failure message without leaking secrets."""
    prefix = "OpenAI structured request failed"
    if isinstance(exc, error.HTTPError):
        detail = _openai_http_error_detail(exc, api_key=api_key).rstrip(".")
        return f"{prefix} ({detail})."
    if isinstance(exc, TimeoutError):
        return f"{prefix} (timed out)."
    if isinstance(exc, json.JSONDecodeError):
        return f"{prefix} (invalid JSON response)."
    if isinstance(exc, ssl.SSLError):
        detail = _sanitize_provider_error_text(str(exc), api_key=api_key).rstrip(".")
        if detail:
            return f"{prefix} (TLS error: {detail})."
        return f"{prefix} (TLS error)."
    if isinstance(exc, error.URLError):
        reason = exc.reason
        # Common path: urlopen wraps SSL faults as URLError(reason=SSLError).
        if isinstance(reason, ssl.SSLError):
            detail = _sanitize_provider_error_text(str(reason), api_key=api_key).rstrip(".")
            if detail:
                return f"{prefix} (TLS error: {detail})."
            return f"{prefix} (TLS error)."
        detail = (
            _sanitize_provider_error_text(str(reason), api_key=api_key).rstrip(".")
            if reason is not None
            else ""
        )
        if detail:
            return f"{prefix} ({detail})."
        return f"{prefix} (network error)."
    return f"{prefix}."


def _is_tls_allowlist_error(exc: BaseException) -> bool:
    """True for DI-1 TLS faults that must wrap as retryable provider errors.

    Allowlist only: ``ssl.SSLError``, ``ssl.CertificateError``, and
    ``URLError`` whose ``reason`` is one of those. No blanket ``OSError``.
    """
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, error.URLError):
        reason = exc.reason
        return isinstance(reason, ssl.SSLError)
    return False


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
        except (error.URLError, TimeoutError, json.JSONDecodeError, ssl.SSLError) as exc:
            retryable = True
            if isinstance(exc, error.HTTPError) and exc.code in _NON_RETRYABLE_HTTP_CODES:
                retryable = False
            elif _is_tls_allowlist_error(exc):
                retryable = True
            raise LLMProviderError(
                _openai_transport_failure_message(exc, api_key=api_key),
                retryable=retryable,
            ) from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI response must be an object.", retryable=False)
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
    """Non-secret settings for the results discussion channel (RQ/DI-series)."""

    enabled: bool
    max_history_messages: int
    allow_time_enrichment: bool
    # DI-1 recovery knobs — defaults change Discuss UX; auditor stays identical.
    repair_retry_enabled: bool = True
    deterministic_overview_fallback: bool = True


@dataclass(frozen=True)
class ProductHelpSettings:
    """Non-secret settings for the product/help channel (RQ-series)."""

    enabled: bool
    max_history_messages: int
    max_corpus_chars: int


@dataclass(frozen=True)
class AssistantUxSettings:
    """Non-secret Research Assistant page UX preselection (RUX-series)."""

    default_mode: str


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
            except LLMProviderError as exc:
                self.last_attempt_count = attempt
                if (
                    not getattr(exc, "retryable", True)
                ) or attempt == self.settings.max_retries + 1:
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
            raise LLMProviderError("OpenAI response did not contain output_text.", retryable=False)
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("OpenAI response is not valid JSON.", retryable=False) from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI structured output must be an object.", retryable=False)
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
            repair_retry_enabled=True,
            deterministic_overview_fallback=True,
        )
    return ResultsQASettings(
        enabled=_coerce_enabled_flag(section.get("enabled", False), default=False),
        max_history_messages=_positive_int(
            section.get("max_history_messages"), default=top_history
        ),
        allow_time_enrichment=_coerce_enabled_flag(
            section.get("allow_time_enrichment", False), default=False
        ),
        repair_retry_enabled=_coerce_enabled_flag(
            section.get("repair_retry_enabled", True), default=True
        ),
        deterministic_overview_fallback=_coerce_enabled_flag(
            section.get("deterministic_overview_fallback", True), default=True
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


def load_assistant_ux_settings(path: str | Path = "config/assistant.toml") -> AssistantUxSettings:
    """Load `[assistant.ux]`; missing section / unknown mode → ``discuss``."""
    from thesistester.assistant.ux import ASSISTANT_MODE_DISCUSS, ASSISTANT_MODES

    assistant = _assistant_table(path)
    section = assistant.get("ux")
    if not isinstance(section, dict):
        return AssistantUxSettings(default_mode=ASSISTANT_MODE_DISCUSS)
    raw = section.get("default_mode", ASSISTANT_MODE_DISCUSS)
    if isinstance(raw, str) and raw.strip() in ASSISTANT_MODES:
        return AssistantUxSettings(default_mode=raw.strip())
    return AssistantUxSettings(default_mode=ASSISTANT_MODE_DISCUSS)


def is_draft_channel_message(message: Any) -> bool:
    """Return True when a conversation message belongs to thesis-draft history.

    Additive helper for RQ-1: treat missing/`None` ``channel`` as draft; any
    message with ``channel`` set (including empty string, ``results_qa``, or
    ``product_help``) is non-draft so draft history isolation can exclude it.
    Does not mutate messages or change orchestrator behavior yet.
    """
    if not isinstance(message, dict):
        return True
    if "channel" not in message:
        return True
    return message.get("channel") is None


_OPENAI_API_KEY_PLACEHOLDER = "REPLACE_WITH_ROTATED_OPENAI_API_KEY"


def _usable_openai_api_key(value: Any) -> str | None:
    """Return a non-empty, non-placeholder key string; otherwise None.

    Tolerates common Streamlit Secrets / env copy-paste faults: surrounding
    whitespace, a UTF-8 BOM, and one layer of wrapping quotes
    (``\"sk-...\"`` / ``'sk-...'``), which otherwise become part of the Bearer
    token and fail OpenAI auth as HTTP 401.
    """
    if not isinstance(value, str):
        return None
    key = value.strip().lstrip("\ufeff").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1].strip()
    if not key or key == _OPENAI_API_KEY_PLACEHOLDER:
        return None
    return key


def _api_key_from_secrets_mapping(secrets: Any) -> str | None:
    """Resolve OPENAI_API_KEY from a Streamlit-like secrets mapping.

    Precedence inside secrets:
    1. top-level ``OPENAI_API_KEY`` (canonical Community Cloud shape)
    2. nested ``[openai].api_key`` (compatibility)
    3. nested ``[openai].OPENAI_API_KEY`` (common mis-key; accepted only as fallback)
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
    for nested_key in ("api_key", "OPENAI_API_KEY"):
        try:
            nested = _usable_openai_api_key(section.get(nested_key))
        except Exception:
            nested = None
        if nested is not None:
            return nested
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
