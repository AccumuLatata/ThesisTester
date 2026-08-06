"""xAI credential resolution + unary STT/TTS / ephemeral-token helpers (VA-2).

Server-side only. No Streamlit UI, WebSocket client, or tool execution.
HTTP uses stdlib ``urllib`` with injectable transports for CI mocks.
"""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib import error, request

from thesistester.assistant.voice.settings import VoiceSettings, load_voice_settings

XAI_API_BASE = "https://api.x.ai/v1"
XAI_CLIENT_SECRETS_URL = f"{XAI_API_BASE}/realtime/client_secrets"
XAI_STT_URL = f"{XAI_API_BASE}/stt"
XAI_TTS_URL = f"{XAI_API_BASE}/tts"
XAI_REALTIME_WS_BASE = "wss://api.x.ai/v1/realtime"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_XAI_API_KEY_PLACEHOLDERS = frozenset(
    {
        "REPLACE_WITH_ROTATED_XAI_API_KEY",
        "REPLACE_WITH_XAI_API_KEY",
        "your_xai_api_key_here",
        "changeme",
    }
)


class VoiceConfigurationError(ValueError):
    """Raised when xAI voice credentials or settings are not safely configured."""


class VoiceProviderError(RuntimeError):
    """Raised when an xAI voice HTTP request fails or returns an invalid payload."""


class XAIJSONTransport(Protocol):
    """Injectable JSON HTTPS transport for ephemeral-token mint tests."""

    def post_json(
        self,
        *,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]: ...


class XAIBinaryTransport(Protocol):
    """Injectable transport for unary STT (multipart) and TTS (JSON→bytes)."""

    def post_multipart(
        self,
        *,
        url: str,
        api_key: str,
        fields: list[tuple[str, str]],
        file_field: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]: ...

    def post_json_bytes(
        self,
        *,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> bytes: ...


def _usable_xai_api_key(value: Any) -> str | None:
    """Return a non-empty, non-placeholder key string; otherwise None."""
    if not isinstance(value, str):
        return None
    key = value.strip()
    if not key:
        return None
    if key in _XAI_API_KEY_PLACEHOLDERS:
        return None
    if key.lower().startswith("replace_with"):
        return None
    return key


def _api_key_from_secrets_mapping(secrets: Any) -> str | None:
    """Resolve ``XAI_API_KEY`` from a Streamlit-like secrets mapping.

    Precedence inside secrets:
    1. top-level ``XAI_API_KEY``
    2. nested ``[xai].api_key``
    """
    if secrets is None or not hasattr(secrets, "get"):
        return None
    try:
        flat = _usable_xai_api_key(secrets.get("XAI_API_KEY"))
    except Exception:
        flat = None
    if flat is not None:
        return flat
    try:
        section = secrets.get("xai")
    except Exception:
        return None
    if section is None or not hasattr(section, "get"):
        return None
    try:
        return _usable_xai_api_key(section.get("api_key"))
    except Exception:
        return None


def _read_streamlit_xai_api_key() -> str | None:
    """Best-effort Streamlit Secrets fallback; never reads tracked config files."""
    try:
        import streamlit as st

        return _api_key_from_secrets_mapping(st.secrets)
    except Exception:
        return None


def realtime_websocket_url(
    *, model: str | None = None, settings: VoiceSettings | None = None
) -> str:
    """Return the pinned xAI realtime WebSocket URL (server-side only)."""
    resolved = settings or load_voice_settings()
    model_id = (model or resolved.model or "").strip()
    if not model_id:
        raise VoiceConfigurationError("Realtime WebSocket requires a non-empty model id.")
    if any(ch in model_id for ch in ("\r", "\n", " ", "?", "#")):
        raise VoiceConfigurationError("Realtime model id contains illegal URL characters.")
    return f"{XAI_REALTIME_WS_BASE}?model={model_id}"


def require_xai_api_key() -> str:
    """Return a rotated xAI key from env, else Streamlit Secrets.

    Resolution order:
    1. ``XAI_API_KEY`` environment variable
    2. Streamlit Secrets ``XAI_API_KEY``
    3. Streamlit Secrets ``[xai].api_key``

    Never reads tracked configuration (for example ``config/assistant.toml``).
    Placeholders fail closed.
    """
    key = _usable_xai_api_key(os.environ.get("XAI_API_KEY"))
    if key is not None:
        return key
    key = _read_streamlit_xai_api_key()
    if key is not None:
        return key
    raise VoiceConfigurationError(
        "Set XAI_API_KEY to a rotated credential (env or Streamlit Secrets)."
    )


def _resolve_api_key(api_key: str | None) -> str:
    """Resolve caller-supplied or ambient xAI key; empty/placeholder fail closed."""
    if api_key is None:
        return require_xai_api_key()
    key = _usable_xai_api_key(api_key)
    if key is None:
        raise VoiceConfigurationError(
            "Set XAI_API_KEY to a rotated credential (env or Streamlit Secrets)."
        )
    return key


def _safe_multipart_token(value: str, *, field_name: str) -> str:
    """Reject CR/LF/quote tokens that would break multipart framing."""
    if not isinstance(value, str) or not value.strip():
        raise VoiceConfigurationError(f"{field_name} must be a non-empty string.")
    if any(ch in value for ch in ("\r", "\n", '"', "\x00")):
        raise VoiceConfigurationError(f"{field_name} contains illegal multipart characters.")
    return value


def _encode_multipart(
    *,
    fields: list[tuple[str, str]],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    safe_file_field = _safe_multipart_token(file_field, field_name="file_field")
    safe_filename = _safe_multipart_token(filename, field_name="filename")
    safe_content_type = _safe_multipart_token(content_type, field_name="content_type")
    boundary = f"----ThesisTesterVoiceBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields:
        safe_name = _safe_multipart_token(name, field_name="multipart field name")
        safe_value = _safe_multipart_token(value, field_name=f"multipart field {safe_name}")
        lines.append(f"--{boundary}\r\n".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{safe_name}"\r\n\r\n'.encode("utf-8"))
        lines.append(safe_value.encode("utf-8"))
        lines.append(b"\r\n")
    # File field last — xAI ignores option fields after the file part.
    lines.append(f"--{boundary}\r\n".encode("utf-8"))
    lines.append(
        (
            f'Content-Disposition: form-data; name="{safe_file_field}"; '
            f'filename="{safe_filename}"\r\n'
            f"Content-Type: {safe_content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    lines.append(file_bytes)
    lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(lines), f"multipart/form-data; boundary={boundary}"


class UrllibXAITransport:
    """Minimal standard-library transport; no provider SDK reaches engine code."""

    def post_json(
        self,
        *,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        outbound = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VoiceProviderError("xAI JSON request failed.") from exc
        if not isinstance(decoded, dict):
            raise VoiceProviderError("xAI JSON response must be an object.")
        return decoded

    def post_multipart(
        self,
        *,
        url: str,
        api_key: str,
        fields: list[tuple[str, str]],
        file_field: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        body, content_type_header = _encode_multipart(
            fields=fields,
            file_field=file_field,
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
        )
        outbound = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": content_type_header,
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VoiceProviderError("xAI STT request failed.") from exc
        if not isinstance(decoded, dict):
            raise VoiceProviderError("xAI STT response must be an object.")
        return decoded

    def post_json_bytes(
        self,
        *,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> bytes:
        body = json.dumps(payload).encode("utf-8")
        outbound = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg, application/octet-stream, */*",
            },
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=timeout) as response:
                audio = response.read()
        except (error.URLError, TimeoutError) as exc:
            raise VoiceProviderError("xAI TTS request failed.") from exc
        if not audio:
            raise VoiceProviderError("xAI TTS response was empty.")
        return audio


@dataclass(frozen=True)
class EphemeralToken:
    """Short-lived client secret for realtime connections (never logged)."""

    value: str
    expires_after_seconds: int
    raw: dict[str, Any]

    def to_public_dict(self) -> dict[str, Any]:
        """Return a redacted view safe for diagnostics (no secret value)."""
        return {
            "expires_after_seconds": self.expires_after_seconds,
            "has_value": bool(self.value),
        }


def _extract_ephemeral_token_value(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise VoiceProviderError("Ephemeral token response must be an object.")
    for key in ("value", "client_secret", "secret", "token"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    nested = payload.get("client_secret")
    if isinstance(nested, Mapping):
        for key in ("value", "secret", "token"):
            candidate = nested.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    raise VoiceProviderError("Ephemeral token response did not include a secret value.")


def mint_ephemeral_token(
    *,
    expires_after_seconds: int | None = None,
    settings: VoiceSettings | None = None,
    api_key: str | None = None,
    transport: XAIJSONTransport | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> EphemeralToken:
    """Mint a short-lived xAI client secret. Fails closed without a usable key."""
    resolved_settings = settings or load_voice_settings()
    ttl = (
        expires_after_seconds
        if expires_after_seconds is not None
        else resolved_settings.ephemeral_token_ttl_seconds
    )
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 1:
        raise VoiceConfigurationError("expires_after_seconds must be a positive integer.")
    key = _resolve_api_key(api_key)
    client = transport or UrllibXAITransport()
    payload = {"expires_after": {"seconds": ttl}}
    last_error: Exception | None = None
    response: dict[str, Any] | None = None
    attempts = resolved_settings.max_retries + 1
    for _ in range(attempts):
        try:
            response = client.post_json(
                url=XAI_CLIENT_SECRETS_URL,
                api_key=key,
                payload=payload,
                timeout=timeout,
            )
            last_error = None
            break
        except VoiceProviderError as exc:
            last_error = exc
    if response is None:
        assert last_error is not None
        raise VoiceProviderError("xAI ephemeral token mint failed.") from last_error
    value = _extract_ephemeral_token_value(response)
    return EphemeralToken(value=value, expires_after_seconds=ttl, raw=dict(response))


def speech_to_text(
    audio_bytes: bytes,
    *,
    filename: str = "audio.wav",
    content_type: str | None = None,
    language: str = "en",
    format_text: bool = True,
    settings: VoiceSettings | None = None,
    api_key: str | None = None,
    transport: XAIBinaryTransport | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Unary STT via ``POST /v1/stt``. Returns the provider JSON object."""
    if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
        raise VoiceConfigurationError("STT requires non-empty audio bytes.")
    resolved_settings = settings or load_voice_settings()
    key = _resolve_api_key(api_key)
    client = transport or UrllibXAITransport()
    safe_filename = _safe_multipart_token(filename, field_name="filename")
    resolved_type = (
        content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    )
    fields: list[tuple[str, str]] = []
    if format_text:
        fields.append(("format", "true"))
        if language:
            fields.append(("language", language))
    elif language:
        fields.append(("language", language))
    last_error: Exception | None = None
    response: dict[str, Any] | None = None
    for _ in range(resolved_settings.max_retries + 1):
        try:
            response = client.post_multipart(
                url=XAI_STT_URL,
                api_key=key,
                fields=fields,
                file_field="file",
                filename=safe_filename,
                content_type=resolved_type,
                file_bytes=bytes(audio_bytes),
                timeout=timeout,
            )
            last_error = None
            break
        except VoiceProviderError as exc:
            last_error = exc
    if response is None:
        assert last_error is not None
        raise VoiceProviderError("xAI STT failed.") from last_error
    text = response.get("text")
    if not isinstance(text, str):
        raise VoiceProviderError("xAI STT response missing text.")
    return response


def text_to_speech(
    text: str,
    *,
    voice_id: str | None = None,
    language: str = "en",
    settings: VoiceSettings | None = None,
    api_key: str | None = None,
    transport: XAIBinaryTransport | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    """Unary TTS via ``POST /v1/tts``. Returns raw audio bytes (default MP3)."""
    if not isinstance(text, str) or not text.strip():
        raise VoiceConfigurationError("TTS requires non-empty text.")
    resolved_settings = settings or load_voice_settings()
    key = _resolve_api_key(api_key)
    client = transport or UrllibXAITransport()
    payload = {
        "text": text,
        "voice_id": voice_id or resolved_settings.voice,
        "language": language,
    }
    last_error: Exception | None = None
    audio: bytes | None = None
    for _ in range(resolved_settings.max_retries + 1):
        try:
            audio = client.post_json_bytes(
                url=XAI_TTS_URL,
                api_key=key,
                payload=payload,
                timeout=timeout,
            )
            last_error = None
            break
        except VoiceProviderError as exc:
            last_error = exc
    if audio is None:
        assert last_error is not None
        raise VoiceProviderError("xAI TTS failed.") from last_error
    return audio
