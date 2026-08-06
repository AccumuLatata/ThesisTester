"""Load non-secret `[assistant.voice]` settings (VA-0).

No UI, network, or secret resolution. Missing section → disabled safe defaults.
"""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CHANNELS = ("results_qa", "product_help")
_ALLOWED_MODES = frozenset({"push_to_talk", "realtime"})
_ALLOWED_CHANNELS = frozenset({"results_qa", "product_help"})


class VoiceSettingsError(ValueError):
    """Raised when voice settings cannot be loaded safely."""


@dataclass(frozen=True)
class VoiceSettings:
    """Non-secret voice configuration. Default remains disabled through VA-6."""

    enabled: bool
    provider: str
    model: str
    voice: str
    mode: str
    channels: tuple[str, ...]
    max_session_minutes: int
    store_audio: bool
    allow_web_search: bool
    require_tool_for_numbers: bool
    ephemeral_token_ttl_seconds: int
    max_history_messages: int
    max_retries: int


def _disabled_defaults() -> VoiceSettings:
    return VoiceSettings(
        enabled=False,
        provider="xai",
        model="grok-voice-think-fast-2.0",
        voice="eve",
        mode="push_to_talk",
        channels=_DEFAULT_CHANNELS,
        max_session_minutes=15,
        store_audio=False,
        allow_web_search=False,
        require_tool_for_numbers=True,
        ephemeral_token_ttl_seconds=300,
        max_history_messages=12,
        max_retries=2,
    )


def _load_assistant_toml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise VoiceSettingsError("Assistant configuration must be a TOML table.")
    return payload


def _coerce_enabled_flag(value: Any, *, default: bool = False) -> bool:
    """Parse enable flags fail-closed.

    Accepts real booleans and common true/false spellings. Strings like
    ``\"false\"`` must not enable voice (``bool(\"false\")`` is True).
    Non-boolean / unrecognized values fail closed to ``default``.
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


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_bool_flag(value: Any, *, default: bool) -> bool:
    return _coerce_enabled_flag(value, default=default)


def _coerce_channels(value: Any) -> tuple[str, ...]:
    if value is None:
        return _DEFAULT_CHANNELS
    if not isinstance(value, list) or not value:
        return _DEFAULT_CHANNELS
    channels: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name in _ALLOWED_CHANNELS and name not in channels:
            channels.append(name)
    return tuple(channels) if channels else _DEFAULT_CHANNELS


def _coerce_mode(value: Any) -> str:
    if isinstance(value, str) and value.strip() in _ALLOWED_MODES:
        return value.strip()
    return "push_to_talk"


def load_voice_settings(path: str | Path = "config/assistant.toml") -> VoiceSettings:
    """Load `[assistant.voice]`; missing section → ``enabled=False`` safe defaults.

    Requires a top-level ``[assistant]`` table when the file exists (same shape
    as other assistant loaders). Non-boolean ``enabled`` fails closed to False.
    """
    payload = _load_assistant_toml(path)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        raise VoiceSettingsError("Missing [assistant] configuration.")
    section = assistant.get("voice")
    if not isinstance(section, dict):
        return _disabled_defaults()

    defaults = _disabled_defaults()
    return VoiceSettings(
        enabled=_coerce_enabled_flag(section.get("enabled", False), default=False),
        provider=str(section.get("provider", defaults.provider) or defaults.provider),
        model=str(section.get("model", defaults.model) or defaults.model),
        voice=str(section.get("voice", defaults.voice) or defaults.voice),
        mode=_coerce_mode(section.get("mode", defaults.mode)),
        channels=_coerce_channels(section.get("channels")),
        max_session_minutes=_positive_int(
            section.get("max_session_minutes"), default=defaults.max_session_minutes
        ),
        store_audio=_coerce_bool_flag(section.get("store_audio", False), default=False),
        allow_web_search=_coerce_bool_flag(section.get("allow_web_search", False), default=False),
        require_tool_for_numbers=_coerce_bool_flag(
            section.get("require_tool_for_numbers", True), default=True
        ),
        ephemeral_token_ttl_seconds=_positive_int(
            section.get("ephemeral_token_ttl_seconds"),
            default=defaults.ephemeral_token_ttl_seconds,
        ),
        max_history_messages=_positive_int(
            section.get("max_history_messages"), default=defaults.max_history_messages
        ),
        max_retries=_positive_int(section.get("max_retries"), default=defaults.max_retries),
    )
