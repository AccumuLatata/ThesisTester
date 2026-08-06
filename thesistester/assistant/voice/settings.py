"""Load non-secret `[assistant.voice]` settings (VA-0/VA-2).

No network. Secret resolution lives in ``xai_realtime.require_xai_api_key``.
Missing section → disabled safe defaults.

Optional local UI overrides live in ``config/assistant.voice.override.toml``
(gitignored): only ``enabled`` and ``mode``. Tracked ``assistant.toml`` stays
``enabled=false`` by default; the Research Assistant Voice controls panel
writes the override file so Streamlit and the realtime sidecar share the same
operator choice without dirtying the tracked config.
"""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_DEFAULT_CHANNELS = ("results_qa", "product_help")
_ALLOWED_MODES = frozenset({"push_to_talk", "realtime"})
_ALLOWED_CHANNELS = frozenset({"results_qa", "product_help"})
DEFAULT_VOICE_UI_OVERRIDE_PATH = Path("config/assistant.voice.override.toml")


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


def with_voice_overrides(
    settings: VoiceSettings,
    *,
    enabled: bool | None = None,
    mode: str | None = None,
) -> VoiceSettings:
    """Return a copy with optional ``enabled`` / ``mode`` overrides applied."""
    updates: dict[str, Any] = {}
    if enabled is not None:
        updates["enabled"] = bool(enabled)
    if mode is not None:
        updates["mode"] = _coerce_mode(mode)
    return replace(settings, **updates) if updates else settings


def load_voice_ui_overrides(
    path: str | Path = DEFAULT_VOICE_UI_OVERRIDE_PATH,
) -> dict[str, Any]:
    """Load local UI override file; missing/invalid → empty dict (fail closed)."""
    override_path = Path(path)
    if not override_path.is_file():
        return {}
    try:
        with override_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    if "enabled" in payload:
        out["enabled"] = _coerce_enabled_flag(payload.get("enabled"), default=False)
    if "mode" in payload:
        out["mode"] = _coerce_mode(payload.get("mode"))
    return out


def save_voice_ui_overrides(
    *,
    enabled: bool,
    mode: str,
    path: str | Path = DEFAULT_VOICE_UI_OVERRIDE_PATH,
) -> Path:
    """Persist operator Voice UI choices (enabled + mode only) for Streamlit/sidecar."""
    override_path = Path(path)
    resolved_mode = _coerce_mode(mode)
    if resolved_mode not in _ALLOWED_MODES:
        raise VoiceSettingsError(f"Unsupported voice mode: {mode!r}.")
    override_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Local Voice UI overrides (gitignored). Tracked assistant.toml stays default-off.\n"
        f"enabled = {'true' if bool(enabled) else 'false'}\n"
        f'mode = "{resolved_mode}"\n'
    )
    override_path.write_text(text, encoding="utf-8")
    return override_path


def clear_voice_ui_overrides(path: str | Path = DEFAULT_VOICE_UI_OVERRIDE_PATH) -> bool:
    """Delete the local override file. Returns True when a file was removed."""
    override_path = Path(path)
    if not override_path.is_file():
        return False
    override_path.unlink()
    return True


def load_voice_settings(path: str | Path = "config/assistant.toml") -> VoiceSettings:
    """Load `[assistant.voice]`; missing section → ``enabled=False`` safe defaults.

    Requires a top-level ``[assistant]`` table when the file exists (same shape
    as other assistant loaders). Non-boolean ``enabled`` fails closed to False.

    Does **not** apply the local Voice UI override file — use
    ``resolve_voice_settings`` for operator enable/mode from the sidebar.
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


def resolve_voice_settings(
    path: str | Path = "config/assistant.toml",
    *,
    ui_override_path: str | Path | None = DEFAULT_VOICE_UI_OVERRIDE_PATH,
) -> VoiceSettings:
    """Tracked voice settings plus optional local UI ``enabled`` / ``mode`` overrides.

    Used by the Research Assistant page and realtime sidecar register path so
    sidebar toggles take effect without editing tracked ``assistant.toml``.
    """
    base = load_voice_settings(path)
    if ui_override_path is None:
        return base
    overrides = load_voice_ui_overrides(ui_override_path)
    if not overrides:
        return base
    return with_voice_overrides(
        base,
        enabled=overrides.get("enabled"),
        mode=overrides.get("mode"),
    )
