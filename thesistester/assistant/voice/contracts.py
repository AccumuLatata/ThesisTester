"""Schema-versioned voice session contracts (VA-0).

Metadata and serialization only. No I/O, Streamlit, network, or tool execution.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

VOICE_CONTRACT_SCHEMA_VERSION = 1
VOICE_SESSION_KIND = "voice_session"
_VOICE_SESSION_ID_RE = re.compile(r"^vs_[0-9a-f]{32}$")
_THESIS_ID_RE = re.compile(r"^th_[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{32}$")
_CONVERSATION_ID_RE = re.compile(r"^conv_[0-9a-f]{32}$")
_VOICE_MODES = frozenset({"push_to_talk", "realtime"})
_VOICE_CHANNELS = frozenset({"results_qa", "product_help"})
_VOICE_SESSION_STATUSES = frozenset({"active", "ended"})
_TRANSCRIPT_ROLES = frozenset({"user", "assistant", "system"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VoiceContractError(ValueError):
    """Raised when a voice contract payload is invalid."""


def _validate_json_value(value: Any, *, field_name: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise VoiceContractError(f"{field_name} must not contain non-finite floats.")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, field_name=f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise VoiceContractError(f"{field_name} keys must be strings.")
            _validate_json_value(item, field_name=f"{field_name}.{key}")
        return
    raise VoiceContractError(f"{field_name} must contain JSON-safe values.")


def _require_schema_version(value: Any) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value != VOICE_CONTRACT_SCHEMA_VERSION
    ):
        raise VoiceContractError(f"Unsupported voice contract schema_version: {value}.")
    return value


def _require_nonempty_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VoiceContractError(f"{field_name} must be a non-empty string.")
    return value


def _optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VoiceContractError(f"{field_name} must be a string or null.")
    return value


@dataclass(frozen=True)
class GroundingVerdict:
    """Digit-token audit outcome for spoken/trusted voice text."""

    grounded: bool
    audited_text: str
    allowed_digit_tokens: tuple[str, ...]
    uncited_digit_tokens: tuple[str, ...]
    remediation: str | None = None
    schema_version: int = VOICE_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if not isinstance(self.grounded, bool):
            raise VoiceContractError("grounded must be a boolean.")
        if not isinstance(self.audited_text, str):
            raise VoiceContractError("audited_text must be a string.")
        for name, values in (
            ("allowed_digit_tokens", self.allowed_digit_tokens),
            ("uncited_digit_tokens", self.uncited_digit_tokens),
        ):
            if not isinstance(values, tuple) or any(not isinstance(item, str) for item in values):
                raise VoiceContractError(f"{name} must be a tuple of strings.")
        if self.remediation is not None and not isinstance(self.remediation, str):
            raise VoiceContractError("remediation must be a string or null.")
        if self.grounded and self.uncited_digit_tokens:
            raise VoiceContractError("grounded verdict cannot include uncited_digit_tokens.")
        if not self.grounded and not (self.remediation or "").strip():
            raise VoiceContractError("ungrounded verdict requires a non-empty remediation.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GroundingVerdict:
        if not isinstance(payload, Mapping):
            raise VoiceContractError("GroundingVerdict must be an object.")
        allowed = {
            "schema_version",
            "grounded",
            "audited_text",
            "allowed_digit_tokens",
            "uncited_digit_tokens",
            "remediation",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise VoiceContractError(f"Unknown GroundingVerdict keys: {unknown}")
        required = {"grounded", "audited_text"}
        missing = sorted(required - set(payload))
        if missing:
            raise VoiceContractError(f"Missing GroundingVerdict keys: {missing}")
        allowed_tokens = payload.get("allowed_digit_tokens", [])
        uncited_tokens = payload.get("uncited_digit_tokens", [])
        if not isinstance(allowed_tokens, list) or not isinstance(uncited_tokens, list):
            raise VoiceContractError("digit token fields must be arrays.")
        return cls(
            schema_version=payload.get("schema_version", VOICE_CONTRACT_SCHEMA_VERSION),
            grounded=payload["grounded"],
            audited_text=payload["audited_text"],
            allowed_digit_tokens=tuple(allowed_tokens),
            uncited_digit_tokens=tuple(uncited_tokens),
            remediation=payload.get("remediation"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "grounded": self.grounded,
            "audited_text": self.audited_text,
            "allowed_digit_tokens": list(self.allowed_digit_tokens),
            "uncited_digit_tokens": list(self.uncited_digit_tokens),
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class VoiceTranscriptTurn:
    """One user/assistant/system turn in a voice session transcript."""

    role: str
    text: str
    created_at: str
    channel: str
    path: str
    grounding: GroundingVerdict | None = None
    schema_version: int = VOICE_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if self.role not in _TRANSCRIPT_ROLES:
            raise VoiceContractError(f"Unsupported transcript role: {self.role}.")
        if not isinstance(self.text, str):
            raise VoiceContractError("text must be a string.")
        _require_nonempty_str(self.created_at, field_name="created_at")
        if self.channel not in _VOICE_CHANNELS:
            raise VoiceContractError(f"Unsupported voice channel: {self.channel}.")
        _require_nonempty_str(self.path, field_name="path")
        if self.grounding is not None and not isinstance(self.grounding, GroundingVerdict):
            raise VoiceContractError("grounding must be a GroundingVerdict or null.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VoiceTranscriptTurn:
        if not isinstance(payload, Mapping):
            raise VoiceContractError("VoiceTranscriptTurn must be an object.")
        allowed = {
            "schema_version",
            "role",
            "text",
            "created_at",
            "channel",
            "path",
            "grounding",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise VoiceContractError(f"Unknown VoiceTranscriptTurn keys: {unknown}")
        required = {"role", "text", "created_at", "channel", "path"}
        missing = sorted(required - set(payload))
        if missing:
            raise VoiceContractError(f"Missing VoiceTranscriptTurn keys: {missing}")
        grounding_raw = payload.get("grounding")
        grounding = None if grounding_raw is None else GroundingVerdict.from_dict(grounding_raw)
        return cls(
            schema_version=payload.get("schema_version", VOICE_CONTRACT_SCHEMA_VERSION),
            role=payload["role"],
            text=payload["text"],
            created_at=payload["created_at"],
            channel=payload["channel"],
            path=payload["path"],
            grounding=grounding,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
            "channel": self.channel,
            "path": self.path,
            "grounding": None if self.grounding is None else self.grounding.to_dict(),
        }


@dataclass(frozen=True)
class VoiceToolInvocation:
    """Audit row for one allowlisted voice tool call attempt."""

    tool_name: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any]
    created_at: str
    error: str | None = None
    schema_version: int = VOICE_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_nonempty_str(self.tool_name, field_name="tool_name")
        if not isinstance(self.arguments, dict):
            raise VoiceContractError("arguments must be an object.")
        _validate_json_value(self.arguments, field_name="arguments")
        if not isinstance(self.ok, bool):
            raise VoiceContractError("ok must be a boolean.")
        if not isinstance(self.result, dict):
            raise VoiceContractError("result must be an object.")
        _validate_json_value(self.result, field_name="result")
        _require_nonempty_str(self.created_at, field_name="created_at")
        if self.error is not None and not isinstance(self.error, str):
            raise VoiceContractError("error must be a string or null.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VoiceToolInvocation:
        if not isinstance(payload, Mapping):
            raise VoiceContractError("VoiceToolInvocation must be an object.")
        allowed = {
            "schema_version",
            "tool_name",
            "arguments",
            "ok",
            "result",
            "created_at",
            "error",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise VoiceContractError(f"Unknown VoiceToolInvocation keys: {unknown}")
        required = {"tool_name", "arguments", "ok", "result", "created_at"}
        missing = sorted(required - set(payload))
        if missing:
            raise VoiceContractError(f"Missing VoiceToolInvocation keys: {missing}")
        arguments = payload.get("arguments")
        result = payload.get("result")
        if not isinstance(arguments, dict) or not isinstance(result, dict):
            raise VoiceContractError("arguments and result must be objects.")
        return cls(
            schema_version=payload.get("schema_version", VOICE_CONTRACT_SCHEMA_VERSION),
            tool_name=payload["tool_name"],
            arguments=dict(arguments),
            ok=payload["ok"],
            result=dict(result),
            created_at=payload["created_at"],
            error=payload.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "ok": self.ok,
            "result": self.result,
            "created_at": self.created_at,
            "error": self.error,
        }


@dataclass(frozen=True)
class VoiceSessionRecord:
    """Persisted voice session bound to a thesis and optional verified run."""

    session_id: str
    thesis_id: str
    mode: str
    channel: str
    status: str
    created_at: str
    updated_at: str
    run_id: str | None = None
    expected_canonical_bundle_hash: str | None = None
    conversation_id: str | None = None
    ended_at: str | None = None
    provider: str = "xai"
    model: str = "grok-voice-think-fast-2.0"
    voice: str = "eve"
    transcript: tuple[VoiceTranscriptTurn, ...] = ()
    tool_invocations: tuple[VoiceToolInvocation, ...] = ()
    revision: int = 1
    schema_version: int = VOICE_CONTRACT_SCHEMA_VERSION
    kind: str = VOICE_SESSION_KIND

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if self.kind != VOICE_SESSION_KIND:
            raise VoiceContractError(f"kind must be {VOICE_SESSION_KIND!r}.")
        if not isinstance(self.session_id, str) or not _VOICE_SESSION_ID_RE.fullmatch(
            self.session_id
        ):
            raise VoiceContractError("session_id must match vs_[0-9a-f]{32}.")
        if not isinstance(self.thesis_id, str) or not _THESIS_ID_RE.fullmatch(self.thesis_id):
            raise VoiceContractError("thesis_id must match th_[0-9a-f]{32}.")
        if self.mode not in _VOICE_MODES:
            raise VoiceContractError(f"Unsupported voice mode: {self.mode}.")
        if self.channel not in _VOICE_CHANNELS:
            raise VoiceContractError(f"Unsupported voice channel: {self.channel}.")
        if self.status not in _VOICE_SESSION_STATUSES:
            raise VoiceContractError(f"Unsupported voice session status: {self.status}.")
        _require_nonempty_str(self.created_at, field_name="created_at")
        _require_nonempty_str(self.updated_at, field_name="updated_at")
        run_id = _optional_str(self.run_id, field_name="run_id")
        expected_hash = _optional_str(
            self.expected_canonical_bundle_hash,
            field_name="expected_canonical_bundle_hash",
        )
        conversation_id = _optional_str(self.conversation_id, field_name="conversation_id")
        ended_at = _optional_str(self.ended_at, field_name="ended_at")
        if conversation_id is not None and not _CONVERSATION_ID_RE.fullmatch(conversation_id):
            raise VoiceContractError("conversation_id must match conv_[0-9a-f]{32}.")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise VoiceContractError("revision must be a positive integer.")
        if self.channel == "results_qa":
            if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
                raise VoiceContractError(
                    "results_qa voice sessions require run_id matching run_[0-9a-f]{32}."
                )
            if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
                raise VoiceContractError(
                    "results_qa voice sessions require expected_canonical_bundle_hash "
                    "as a 64-char lowercase hex sha256."
                )
        elif run_id is not None or expected_hash is not None:
            raise VoiceContractError(
                "product_help voice sessions must omit run_id and expected_canonical_bundle_hash."
            )
        if self.status == "ended" and not (ended_at or "").strip():
            raise VoiceContractError("ended sessions require ended_at.")
        if self.status == "active" and ended_at is not None:
            raise VoiceContractError("active sessions must omit ended_at.")
        _require_nonempty_str(self.provider, field_name="provider")
        _require_nonempty_str(self.model, field_name="model")
        _require_nonempty_str(self.voice, field_name="voice")
        if not isinstance(self.transcript, tuple) or any(
            not isinstance(item, VoiceTranscriptTurn) for item in self.transcript
        ):
            raise VoiceContractError("transcript must be a tuple of VoiceTranscriptTurn.")
        for index, turn in enumerate(self.transcript):
            if turn.channel != self.channel:
                raise VoiceContractError(
                    f"transcript[{index}].channel must match session channel "
                    f"{self.channel!r} (do not mix histories)."
                )
        if not isinstance(self.tool_invocations, tuple) or any(
            not isinstance(item, VoiceToolInvocation) for item in self.tool_invocations
        ):
            raise VoiceContractError("tool_invocations must be a tuple of VoiceToolInvocation.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VoiceSessionRecord:
        if not isinstance(payload, Mapping):
            raise VoiceContractError("VoiceSessionRecord must be an object.")
        allowed = {
            "schema_version",
            "kind",
            "session_id",
            "thesis_id",
            "run_id",
            "expected_canonical_bundle_hash",
            "conversation_id",
            "mode",
            "channel",
            "status",
            "created_at",
            "updated_at",
            "ended_at",
            "provider",
            "model",
            "voice",
            "transcript",
            "tool_invocations",
            "revision",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise VoiceContractError(f"Unknown VoiceSessionRecord keys: {unknown}")
        required = {
            "session_id",
            "thesis_id",
            "mode",
            "channel",
            "status",
            "created_at",
            "updated_at",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise VoiceContractError(f"Missing VoiceSessionRecord keys: {missing}")
        transcript_raw = payload.get("transcript", [])
        tools_raw = payload.get("tool_invocations", [])
        if not isinstance(transcript_raw, list) or not isinstance(tools_raw, list):
            raise VoiceContractError("transcript and tool_invocations must be arrays.")
        return cls(
            schema_version=payload.get("schema_version", VOICE_CONTRACT_SCHEMA_VERSION),
            kind=payload.get("kind", VOICE_SESSION_KIND),
            session_id=payload["session_id"],
            thesis_id=payload["thesis_id"],
            run_id=payload.get("run_id"),
            expected_canonical_bundle_hash=payload.get("expected_canonical_bundle_hash"),
            conversation_id=payload.get("conversation_id"),
            mode=payload["mode"],
            channel=payload["channel"],
            status=payload["status"],
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            ended_at=payload.get("ended_at"),
            provider=_require_nonempty_str(payload.get("provider", "xai"), field_name="provider"),
            model=_require_nonempty_str(
                payload.get("model", "grok-voice-think-fast-2.0"), field_name="model"
            ),
            voice=_require_nonempty_str(payload.get("voice", "eve"), field_name="voice"),
            transcript=tuple(VoiceTranscriptTurn.from_dict(item) for item in transcript_raw),
            tool_invocations=tuple(VoiceToolInvocation.from_dict(item) for item in tools_raw),
            revision=payload.get("revision", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "session_id": self.session_id,
            "thesis_id": self.thesis_id,
            "run_id": self.run_id,
            "expected_canonical_bundle_hash": self.expected_canonical_bundle_hash,
            "conversation_id": self.conversation_id,
            "mode": self.mode,
            "channel": self.channel,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "provider": self.provider,
            "model": self.model,
            "voice": self.voice,
            "transcript": [item.to_dict() for item in self.transcript],
            "tool_invocations": [item.to_dict() for item in self.tool_invocations],
            "revision": self.revision,
        }


def validate_voice_session_id(session_id: str) -> str:
    """Return ``session_id`` when it matches the frozen ``vs_`` id format."""
    if not isinstance(session_id, str) or not _VOICE_SESSION_ID_RE.fullmatch(session_id):
        raise VoiceContractError("session_id must match vs_[0-9a-f]{32}.")
    return session_id


def coerce_transcript(
    turns: Sequence[VoiceTranscriptTurn | Mapping[str, Any]],
) -> tuple[VoiceTranscriptTurn, ...]:
    """Normalize mixed turn objects/dicts into validated transcript turns."""
    out: list[VoiceTranscriptTurn] = []
    for item in turns:
        if isinstance(item, VoiceTranscriptTurn):
            out.append(item)
        else:
            out.append(VoiceTranscriptTurn.from_dict(item))
    return tuple(out)
