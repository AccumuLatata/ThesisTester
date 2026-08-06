"""Voice session lifecycle, evidence bind, honesty instructions, and PTT (VA-2…4).

Persists sibling ``voice_sessions/vs_*.json`` documents. Does not widen
``Conversation`` identity rules. Allowlisted tool execution lives in
``voice/tools.py`` (VA-3). Push-to-talk spoken Discuss/Help lives in
``run_push_to_talk_turn`` (VA-4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import uuid4

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import LLMConfigurationError, LLMProviderError
from thesistester.assistant.llm_explainer import LLMEvidenceError
from thesistester.assistant.repository import (
    AssistantRepositoryError,
    LocalThesisRepository,
    ResearchRun,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools
from thesistester.assistant.voice.contracts import (
    GroundingVerdict,
    VoiceContractError,
    VoiceSessionRecord,
    VoiceToolInvocation,
    VoiceTranscriptTurn,
    validate_voice_session_id,
)
from thesistester.assistant.voice.grounding import (
    HELP_NO_OPENAI_REMEDIATION,
    UNGROUNDED_SPOKEN_REMEDIATION,
    allowed_tokens_from_help_corpus,
    audit_spoken_text,
    format_speakable_help_reply,
    format_speakable_results_reply,
    format_speakable_tool_result,
    strip_claim_path_markup,
)
from thesistester.assistant.voice.intent import VoiceIntentRouter
from thesistester.assistant.voice.settings import VoiceSettings, load_voice_settings
from thesistester.assistant.voice.xai_realtime import (
    VoiceConfigurationError,
    VoiceProviderError,
    speech_to_text,
    text_to_speech,
)
from thesistester.assistant.workspace import require_run_bundle_hash

_VOICE_CHANNELS = frozenset({"results_qa", "product_help"})
_VOICE_MODES = frozenset({"push_to_talk", "realtime"})
_TTS_MIME = "audio/mpeg"


class _ResultsHelpOrchestrator(Protocol):
    """Minimal orchestrator surface used by push-to-talk channel turns."""

    def handle_results_turn(self, client: Any, **kwargs: Any) -> Any: ...

    def handle_help_turn(self, client: Any, **kwargs: Any) -> Any: ...


class VoiceSessionError(ValueError):
    """Raised when a voice session cannot be created or updated safely."""


@dataclass(frozen=True)
class PushToTalkTurnResult:
    """One VA-4 half-duplex spoken turn (STT → channel/fallback → grounding → TTS)."""

    session_id: str
    channel: str
    answer_path: str
    stt_text: str
    speakable_text: str
    grounding: GroundingVerdict
    trusted: bool
    audio_bytes: bytes | None
    audio_mime: str = _TTS_MIME
    tool_name: str | None = None
    spoken_note: str | None = None
    remediation: str | None = None
    openai_used: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        """UI-safe view (no raw audio bytes)."""
        return {
            "session_id": self.session_id,
            "channel": self.channel,
            "answer_path": self.answer_path,
            "stt_text": self.stt_text,
            "speakable_text": self.speakable_text,
            "trusted": self.trusted,
            "grounded": self.grounding.grounded,
            "uncited_digit_tokens": list(self.grounding.uncited_digit_tokens),
            "tool_name": self.tool_name,
            "spoken_note": self.spoken_note,
            "remediation": self.remediation,
            "openai_used": self.openai_used,
            "has_audio": bool(self.audio_bytes),
            "audio_mime": self.audio_mime,
        }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_voice_session_id() -> str:
    return f"vs_{uuid4().hex}"


def parse_iso_utc(value: str) -> datetime:
    """Parse a persisted ISO-8601 timestamp into an aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        raise VoiceSessionError("Timestamp must be a non-empty ISO-8601 string.")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise VoiceSessionError("Timestamp is not valid ISO-8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def session_exceeded_ttl(
    record: VoiceSessionRecord,
    *,
    max_session_minutes: int,
    now: datetime | None = None,
) -> bool:
    """True when an active voice session has exceeded ``max_session_minutes``."""
    if not isinstance(max_session_minutes, int) or isinstance(max_session_minutes, bool):
        raise VoiceSessionError("max_session_minutes must be an integer.")
    if max_session_minutes < 1:
        raise VoiceSessionError("max_session_minutes must be >= 1.")
    created_at = record.created_at
    if not isinstance(created_at, str):
        raise VoiceSessionError("Voice session is missing created_at.")
    created = parse_iso_utc(created_at)
    current = (
        now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc)
    )
    elapsed = current - created
    return elapsed.total_seconds() >= (max_session_minutes * 60)


def _stt_text_from_response(response: Mapping[str, Any]) -> str:
    text = response.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise VoiceProviderError("xAI STT response missing text.")


def _claims_from_results_reply(reply: Any) -> tuple[EvidenceClaim, ...]:
    claims = getattr(reply, "claims", ()) or ()
    out: list[EvidenceClaim] = []
    for claim in claims:
        if isinstance(claim, EvidenceClaim):
            out.append(claim)
        elif isinstance(claim, Mapping):
            out.append(
                EvidenceClaim(
                    text=str(claim.get("text") or ""),
                    path=str(claim.get("path") or ""),
                    value=claim.get("value"),
                )
            )
    return tuple(out)


def run_push_to_talk_turn(
    *,
    service: VoiceSessionService,
    orchestrator: _ResultsHelpOrchestrator,
    audio_bytes: bytes,
    channel: str,
    thesis_id: str,
    conversation_id: str | None = None,
    run_id: str | None = None,
    expected_hash: str | None = None,
    openai_client: Any | None = None,
    stt_transport: Any | None = None,
    tts_transport: Any | None = None,
    intent_router: VoiceIntentRouter | None = None,
    repo_root: str | Path | None = None,
    max_history_messages: int = 12,
    filename: str = "audio.wav",
    content_type: str | None = None,
) -> PushToTalkTurnResult:
    """STT → RQ channel (or VA-3 fallback) → digit grounding → TTS.

    Creates a short-lived ``mode="push_to_talk"`` voice session, appends
    transcript turns, and ends/flushes the session before returning.
    Never mints ephemeral realtime tokens (VA-5). Never dispatches compute.
    """
    if channel not in _VOICE_CHANNELS:
        raise VoiceSessionError(f"Unsupported voice channel: {channel}.")
    if not service.settings.enabled:
        raise VoiceSessionError(
            "Voice is disabled (assistant.voice.enabled=false). "
            "Enable it in config/assistant.toml to use push-to-talk."
        )
    if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
        raise VoiceConfigurationError("Push-to-talk requires non-empty audio bytes.")

    # STT first — fail closed without XAI; never mint ephemeral tokens here.
    stt_response = speech_to_text(
        bytes(audio_bytes),
        filename=filename,
        content_type=content_type,
        settings=service.settings,
        transport=stt_transport,
    )
    stt_text = _stt_text_from_response(stt_response)
    if not stt_text:
        raise VoiceProviderError("STT produced empty transcript text.")

    record = service.create_session(
        thesis_id,
        run_id=run_id if channel == "results_qa" else None,
        expected_hash=expected_hash if channel == "results_qa" else None,
        mode="push_to_talk",
        channel=channel,
        conversation_id=conversation_id,
    )
    session_id = record.session_id
    created_at = _utcnow()
    try:
        service.append_transcript_turn(
            thesis_id,
            session_id,
            VoiceTranscriptTurn(
                role="user",
                text=stt_text,
                channel=channel,
                path="stt",
                created_at=created_at,
            ),
        )

        answer_path: str
        speakable: str
        tool_name: str | None = None
        spoken_note: str | None = None
        openai_used = False
        grounding: GroundingVerdict
        remediation: str | None = None

        if channel == "results_qa":
            (
                answer_path,
                speakable,
                grounding,
                tool_name,
                spoken_note,
                openai_used,
                remediation,
            ) = _answer_results_ptt(
                service=service,
                orchestrator=orchestrator,
                thesis_id=thesis_id,
                session_id=session_id,
                run_id=run_id,
                conversation_id=conversation_id,
                stt_text=stt_text,
                openai_client=openai_client,
                intent_router=intent_router or VoiceIntentRouter(),
                max_history_messages=max_history_messages,
            )
        else:
            (
                answer_path,
                speakable,
                grounding,
                openai_used,
                remediation,
            ) = _answer_help_ptt(
                orchestrator=orchestrator,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
                stt_text=stt_text,
                openai_client=openai_client,
                repo_root=repo_root,
                max_history_messages=max_history_messages,
            )

        trusted = bool(grounding.grounded) and not remediation
        tts_text = speakable if trusted else (remediation or UNGROUNDED_SPOKEN_REMEDIATION)
        # Re-audit the actual TTS payload when degraded so UI reflects playback text.
        if not trusted:
            grounding = audit_spoken_text(tts_text, allowed_tokens=())
            # Remediation copy is intentionally number-free; treat as playable degraded.
            if not grounding.grounded:
                tts_text = UNGROUNDED_SPOKEN_REMEDIATION
                grounding = audit_spoken_text(tts_text, allowed_tokens=())
            speakable = tts_text
            trusted = False

        audio_out: bytes | None = None
        try:
            audio_out = text_to_speech(
                tts_text,
                settings=service.settings,
                transport=tts_transport,
            )
        except (VoiceConfigurationError, VoiceProviderError):
            # Still persist transcript; UI can show text without audio.
            audio_out = None

        service.append_transcript_turn(
            thesis_id,
            session_id,
            VoiceTranscriptTurn(
                role="assistant",
                text=speakable,
                channel=channel,
                path=answer_path,
                created_at=_utcnow(),
                grounding=grounding,
            ),
        )
        return PushToTalkTurnResult(
            session_id=session_id,
            channel=channel,
            answer_path=answer_path,
            stt_text=stt_text,
            speakable_text=speakable,
            grounding=grounding,
            trusted=bool(trusted and grounding.grounded),
            audio_bytes=audio_out,
            audio_mime=_TTS_MIME,
            tool_name=tool_name,
            spoken_note=spoken_note,
            remediation=remediation,
            openai_used=openai_used,
        )
    finally:
        service.end_session(thesis_id, session_id, conversation_id=conversation_id)


def _answer_results_ptt(
    *,
    service: VoiceSessionService,
    orchestrator: _ResultsHelpOrchestrator,
    thesis_id: str,
    session_id: str,
    run_id: str | None,
    conversation_id: str | None,
    stt_text: str,
    openai_client: Any | None,
    intent_router: VoiceIntentRouter,
    max_history_messages: int,
) -> tuple[str, str, GroundingVerdict, str | None, str | None, bool, str | None]:
    if openai_client is not None:
        try:
            result = orchestrator.handle_results_turn(
                openai_client,
                thesis_id=thesis_id,
                run_id=run_id or "",
                message=stt_text,
                conversation_id=conversation_id,
                max_history_messages=max_history_messages,
                persist_conversation=False,
            )
            if getattr(result, "status", None) == "completed":
                reply = (getattr(result, "payload", None) or {}).get("results_reply")
                if reply is not None:
                    claims = _claims_from_results_reply(reply)
                    speakable = format_speakable_results_reply(reply)
                    grounding = audit_spoken_text(speakable, claims=claims)
                    if not grounding.grounded:
                        # Caveat free-text digits are not typed claim values —
                        # retry summary-only (still strip claim-path markup).
                        summary_only = strip_claim_path_markup(
                            str(getattr(reply, "summary", "") or "").strip()
                        )
                        if summary_only:
                            speakable = summary_only
                            grounding = audit_spoken_text(speakable, claims=claims)
                    remediation = None if grounding.grounded else UNGROUNDED_SPOKEN_REMEDIATION
                    return (
                        "handle_results_turn",
                        speakable,
                        grounding,
                        None,
                        None,
                        True,
                        remediation,
                    )
            # OpenAI path attempted but did not complete — surface RQ error.
            # Do not silent-fall through to VA-3 (would hide the RQ failure).
            payload = getattr(result, "payload", None) or {}
            error = payload.get("error") if isinstance(payload, Mapping) else None
            if isinstance(error, Mapping):
                message = str(error.get("message") or "Unable to answer this results question.")
            else:
                message = "Unable to answer this results question."
            speakable = message
            grounding = audit_spoken_text(speakable, allowed_tokens=())
            return (
                "handle_results_turn",
                speakable,
                grounding,
                None,
                None,
                True,
                speakable,
            )
        except LLMEvidenceError:
            # Grounding/schema failure from RQ — never silent-fall to VA-3.
            speakable = (
                "I could not ground a spoken results answer. Please use text Discuss results."
            )
            grounding = audit_spoken_text(speakable, allowed_tokens=())
            return (
                "handle_results_turn",
                speakable,
                grounding,
                None,
                None,
                True,
                speakable,
            )
        except (LLMConfigurationError, LLMProviderError, ValueError, AssistantToolError):
            # Fall through to deterministic VA-3 tool path.
            pass

    intent = intent_router.route(stt_text)
    tool_session = service.tool_session(thesis_id, session_id)
    from thesistester.assistant.voice.tools import VoiceToolError, execute_voice_tool

    try:
        envelope = execute_voice_tool(
            intent.tool_name,
            intent.arguments,
            session=tool_session,
        )
    except (VoiceToolError, VoiceSessionError, VoiceContractError) as exc:
        speakable = (
            f"I could not answer from the bound evidence ({exc}). Please use text Discuss results."
        )
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return (
            "fallback_tool",
            speakable,
            grounding,
            intent.tool_name,
            intent.spoken_note,
            False,
            speakable,
        )

    if not isinstance(envelope, Mapping) or not envelope.get("ok"):
        error_text = ""
        if isinstance(envelope, Mapping):
            error_text = str(envelope.get("error") or "").strip()
        speakable = (
            error_text
            or "I could not answer from the bound evidence. Please use text Discuss results."
        )
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return (
            "fallback_tool",
            speakable,
            grounding,
            intent.tool_name,
            intent.spoken_note,
            False,
            speakable,
        )

    tool_result = envelope.get("result")
    if not isinstance(tool_result, Mapping):
        tool_result = {}
    speakable = format_speakable_tool_result(
        intent.tool_name,
        tool_result,
        spoken_note=intent.spoken_note,
    )
    extra_values: list[Any] = []
    if intent.tool_name == "list_caveats":
        caveats = tool_result.get("caveats") or []
        warnings = tool_result.get("warnings") or []
        extra_values.append(len(caveats) if isinstance(caveats, list) else 0)
        extra_values.append(len(warnings) if isinstance(warnings, list) else 0)
    grounding = audit_spoken_text(
        speakable,
        tool_result=tool_result,
        allowed_values=extra_values or None,
    )
    remediation = None if grounding.grounded else UNGROUNDED_SPOKEN_REMEDIATION
    return (
        "fallback_tool",
        speakable,
        grounding,
        intent.tool_name,
        intent.spoken_note,
        False,
        remediation,
    )


def _answer_help_ptt(
    *,
    orchestrator: _ResultsHelpOrchestrator,
    thesis_id: str,
    conversation_id: str | None,
    stt_text: str,
    openai_client: Any | None,
    repo_root: str | Path | None,
    max_history_messages: int,
) -> tuple[str, str, GroundingVerdict, bool, str | None]:
    if openai_client is None:
        speakable = HELP_NO_OPENAI_REMEDIATION
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return ("remediation", speakable, grounding, False, speakable)

    try:
        result = orchestrator.handle_help_turn(
            openai_client,
            thesis_id=thesis_id,
            message=stt_text,
            conversation_id=conversation_id,
            max_history_messages=max_history_messages,
            repo_root=repo_root,
            persist_conversation=False,
        )
    except (LLMConfigurationError, LLMProviderError, ValueError) as exc:
        speakable = (
            f"Spoken Help could not complete ({exc}). "
            "Use the text Help panel, or set OPENAI_API_KEY."
        )
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return ("remediation", speakable, grounding, False, speakable)

    if getattr(result, "status", None) != "completed":
        payload = getattr(result, "payload", None) or {}
        error = payload.get("error") if isinstance(payload, Mapping) else None
        if isinstance(error, Mapping):
            message = str(error.get("message") or "Unable to answer this help question.")
        else:
            message = "Unable to answer this help question."
        speakable = message
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return ("remediation", speakable, grounding, True, speakable)

    payload = getattr(result, "payload", None) or {}
    reply = payload.get("help_reply")
    if reply is None:
        speakable = HELP_NO_OPENAI_REMEDIATION
        grounding = audit_spoken_text(speakable, allowed_tokens=())
        return ("remediation", speakable, grounding, True, speakable)

    speakable = format_speakable_help_reply(reply)
    allowed = allowed_tokens_from_help_corpus(
        payload.get("corpus_chunks"),
        payload.get("registry_digest"),
    )
    grounding = audit_spoken_text(speakable, allowed_tokens=allowed)
    if not grounding.grounded:
        summary_only = strip_claim_path_markup(str(getattr(reply, "summary", "") or "").strip())
        if summary_only:
            speakable = summary_only
            grounding = audit_spoken_text(speakable, allowed_tokens=allowed)
    remediation = None if grounding.grounded else UNGROUNDED_SPOKEN_REMEDIATION
    return ("handle_help_turn", speakable, grounding, True, remediation)


def build_honesty_instructions(
    *,
    channel: str,
    mode: str,
    run_id: str | None = None,
    expected_hash: str | None = None,
) -> str:
    """Return frozen honesty policy text for STT→channel / realtime sessions."""
    if channel not in _VOICE_CHANNELS:
        raise VoiceSessionError(f"Unsupported voice channel: {channel}.")
    if mode not in _VOICE_MODES:
        raise VoiceSessionError(f"Unsupported voice mode: {mode}.")

    shared = [
        "You are ThesisTester voice review. Speak only from bound evidence or "
        "allowlisted product documentation for this session.",
        "evidence/docs-only: do not invent metrics, runs, or product behavior.",
        "no trade advice: do not recommend live orders, position sizing, or broker actions.",
        "numbers only from tools/packet/corpus rules for this turn.",
        "If a number cannot be grounded, say so and remediate instead of guessing.",
        "Never execute research pipelines, grids, walk-forward, or confirmed runs.",
        "Never enable web_search, x_search, file_search, or mcp tools.",
    ]
    if channel == "results_qa":
        shared.extend(
            [
                "Channel: results discussion over one hash-verified completed run.",
                f"Bound run_id: {run_id}.",
                f"Expected canonical_bundle_hash: {expected_hash}.",
                "sample-size/OOS caveats always apply; treat small samples and "
                "in-sample rankings as diagnostic, not proof of edge.",
                "Prefer calling grounded results Q&A; fallback tools may only read "
                "the bound packet or compare_evidence.",
            ]
        )
    else:
        shared.extend(
            [
                "Channel: product Help over the allowlisted USER_GUIDE / registry corpus.",
                "Do not answer run-performance questions from Help; remediate to Discuss results.",
                "Do not fabricate documentation that is not in the Help corpus allowlist.",
            ]
        )
    shared.append(f"Session mode: {mode}.")
    return "\n".join(shared)


class VoiceSessionService:
    """Create/end voice sessions and keep an in-memory bound packet cache."""

    def __init__(
        self,
        repository: LocalThesisRepository,
        *,
        tools: AssistantTools | None = None,
        settings: VoiceSettings | None = None,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.settings = settings or load_voice_settings()
        self._bound_packets: dict[str, EvidencePacket] = {}

    def build_honesty_instructions(self, record: VoiceSessionRecord) -> str:
        return build_honesty_instructions(
            channel=record.channel,
            mode=record.mode,
            run_id=record.run_id,
            expected_hash=record.expected_canonical_bundle_hash,
        )

    def get_bound_packet(self, session_id: str) -> EvidencePacket | None:
        validate_voice_session_id(session_id)
        return self._bound_packets.get(session_id)

    def require_bound_packet(self, thesis_id: str, session_id: str) -> EvidencePacket:
        """Return the bound packet, rehydrating from persisted run/hash on miss."""
        validate_voice_session_id(session_id)
        cached = self._bound_packets.get(session_id)
        if cached is not None:
            return cached
        record = self.repository.get_voice_session(thesis_id, session_id)
        if record.channel != "results_qa":
            raise VoiceSessionError("Bound evidence packets exist only for results_qa sessions.")
        if not record.run_id or not record.expected_canonical_bundle_hash:
            raise VoiceSessionError("Results voice session is missing run/hash binding.")
        packet, _run_id, _digest = self._bind_results_session(
            thesis_id,
            run_id=record.run_id,
            expected_hash=record.expected_canonical_bundle_hash,
        )
        self._bound_packets[session_id] = packet
        return packet

    def tool_session(self, thesis_id: str, session_id: str):
        """Return a ``VoiceToolSession`` handle for allowlisted tool execution."""
        # Local import avoids package cycles with voice.tools → session.
        from thesistester.assistant.voice.tools import VoiceToolSession

        validate_voice_session_id(session_id)
        self.repository.get_voice_session(thesis_id, session_id)
        return VoiceToolSession(service=self, thesis_id=thesis_id, session_id=session_id)

    def create_session(
        self,
        thesis_id: str,
        run_id: str | None = None,
        *,
        expected_hash: str | None = None,
        mode: str,
        channel: str,
        conversation_id: str | None = None,
    ) -> VoiceSessionRecord:
        """Bind and persist a new voice session.

        Results sessions require a completed run + hash-verified evidence packet.
        Help sessions bind thesis/conversation only (no packet).
        """
        if channel not in _VOICE_CHANNELS:
            raise VoiceSessionError(f"Unsupported voice channel: {channel}.")
        if mode not in _VOICE_MODES:
            raise VoiceSessionError(f"Unsupported voice mode: {mode}.")
        try:
            self.repository.get_thesis(thesis_id)
        except AssistantRepositoryError as exc:
            raise VoiceSessionError("Thesis does not exist.") from exc

        packet: EvidencePacket | None = None
        bound_run_id: str | None = None
        bound_hash: str | None = None
        if channel == "results_qa":
            packet, bound_run_id, bound_hash = self._bind_results_session(
                thesis_id,
                run_id=run_id,
                expected_hash=expected_hash,
            )
        else:
            if run_id is not None or expected_hash is not None:
                raise VoiceSessionError(
                    "product_help voice sessions must omit run_id and expected_hash."
                )

        # conversation_id is optional metadata for later flush; validate if present.
        if conversation_id is not None:
            try:
                self.repository.get_conversation(thesis_id, conversation_id)
            except AssistantRepositoryError as exc:
                raise VoiceSessionError("Conversation does not exist.") from exc

        timestamp = _utcnow()
        record = VoiceSessionRecord(
            session_id=_new_voice_session_id(),
            thesis_id=thesis_id,
            run_id=bound_run_id,
            expected_canonical_bundle_hash=bound_hash,
            conversation_id=conversation_id,
            mode=mode,
            channel=channel,
            status="active",
            created_at=timestamp,
            updated_at=timestamp,
            provider=self.settings.provider,
            model=self.settings.model,
            voice=self.settings.voice,
            revision=1,
        )
        instructions = self.build_honesty_instructions(record)
        required = (
            "evidence/docs-only",
            "no trade advice",
            "numbers only from tools/packet/corpus rules",
        )
        lowered = instructions.lower()
        for needle in required:
            if needle not in lowered:
                raise VoiceSessionError(f"Honesty instructions missing {needle!r}.")
        if channel == "results_qa" and "sample-size/oos caveats" not in lowered:
            raise VoiceSessionError("Results honesty instructions missing sample-size/OOS caveats.")

        saved = self.repository.save_voice_session(record)
        if packet is not None:
            self._bound_packets[saved.session_id] = packet
        return saved

    def append_transcript_turn(
        self,
        thesis_id: str,
        session_id: str,
        turn: VoiceTranscriptTurn,
    ) -> VoiceSessionRecord:
        record = self.repository.get_voice_session(thesis_id, session_id)
        if record.status != "active":
            raise VoiceSessionError("Cannot append turns to an ended voice session.")
        if turn.channel != record.channel:
            raise VoiceSessionError("Transcript turn channel must match the session channel.")
        updated = replace(
            record,
            transcript=record.transcript + (turn,),
            updated_at=_utcnow(),
        )
        return self.repository.save_voice_session(updated)

    def append_tool_invocation(
        self,
        thesis_id: str,
        session_id: str,
        invocation: VoiceToolInvocation,
        *,
        allow_ended: bool = False,
    ) -> VoiceSessionRecord:
        """Append one tool audit row.

        ``allow_ended=True`` keeps fail-closed deny/audit rows durable after
        ``end_session`` (VA-3: one audit row per invocation attempt).
        """
        record = self.repository.get_voice_session(thesis_id, session_id)
        if record.status != "active" and not allow_ended:
            raise VoiceSessionError("Cannot append tools to an ended voice session.")
        updated = replace(
            record,
            tool_invocations=record.tool_invocations + (invocation,),
            updated_at=_utcnow(),
        )
        return self.repository.save_voice_session(updated)

    def end_session(
        self,
        thesis_id: str,
        session_id: str,
        *,
        conversation_id: str | None = None,
    ) -> VoiceSessionRecord:
        """Mark the session ended and best-effort flush transcript/tool audits."""
        record = self.repository.get_voice_session(thesis_id, session_id)
        flush_conversation_id = (
            conversation_id if conversation_id is not None else record.conversation_id
        )
        if record.status == "ended":
            if flush_conversation_id is not None:
                self._flush_to_conversation_best_effort(
                    thesis_id,
                    flush_conversation_id,
                    record,
                )
            self._bound_packets.pop(session_id, None)
            return record
        ended_at = _utcnow()
        ended = replace(
            record,
            status="ended",
            ended_at=ended_at,
            updated_at=ended_at,
        )
        saved = self.repository.save_voice_session(ended)
        if flush_conversation_id is not None:
            self._flush_to_conversation_best_effort(
                thesis_id,
                flush_conversation_id,
                saved,
            )
        self._bound_packets.pop(session_id, None)
        return saved

    def _bind_results_session(
        self,
        thesis_id: str,
        *,
        run_id: str | None,
        expected_hash: str | None,
    ) -> tuple[EvidencePacket, str, str]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise VoiceSessionError("results_qa voice sessions require a non-empty run_id.")
        if not isinstance(expected_hash, str) or not expected_hash.strip():
            raise VoiceSessionError(
                "results_qa voice sessions require expected_hash (canonical bundle hash)."
            )
        normalized_run_id = run_id.strip()
        normalized_hash = expected_hash.strip().lower()
        try:
            run = self.repository.get_run(thesis_id, normalized_run_id)
        except AssistantRepositoryError as exc:
            raise VoiceSessionError("Research run does not exist.") from exc
        if run.status != "completed":
            raise VoiceSessionError("Only completed runs can bind a results voice session.")
        if not isinstance(run.provenance, Mapping):
            raise VoiceSessionError("Completed run is missing provenance.")
        try:
            provenance_hash = require_run_bundle_hash(run.provenance).lower()
        except ValueError as exc:
            raise VoiceSessionError(str(exc)) from exc
        if provenance_hash != normalized_hash:
            raise VoiceSessionError(
                "expected_hash does not match run canonical_bundle_hash provenance."
            )
        bundle_path = run.provenance.get("bundle_path")
        if not isinstance(bundle_path, str) or not bundle_path.strip():
            raise VoiceSessionError("Completed run is missing bundle_path provenance.")
        if self.tools is None:
            raise VoiceSessionError(
                "AssistantTools is required to bind a hash-verified evidence packet."
            )
        # Containment/existence checks before any byte read (tools also re-verify hash).
        try:
            resolved = Path(bundle_path.strip()).expanduser().resolve()
        except OSError as exc:
            raise VoiceSessionError("Bound research bundle path is invalid.") from exc
        if not any(resolved.is_relative_to(root.resolve()) for root in self.tools.data_roots):
            raise VoiceSessionError("Bound research bundle path is outside assistant data roots.")
        if not resolved.is_file():
            raise VoiceSessionError("Bound research bundle file is missing.")
        packet = self._load_evidence_packet(
            run,
            bundle_path=str(resolved),
            expected_hash=normalized_hash,
        )
        return packet, normalized_run_id, normalized_hash

    def _load_evidence_packet(
        self,
        run: ResearchRun,
        *,
        bundle_path: str,
        expected_hash: str,
    ) -> EvidencePacket:
        if self.tools is None:
            raise VoiceSessionError(
                "AssistantTools is required to bind a hash-verified evidence packet."
            )
        try:
            payload = self.tools.build_bundle_evidence_packet(
                bundle_path,
                expected_hash=expected_hash,
                provenance=dict(run.provenance or {}),
            )
        except (AssistantToolError, OSError) as exc:
            raise VoiceSessionError(str(exc)) from exc
        return EvidencePacket.from_dict(payload)

    def _flush_to_conversation_best_effort(
        self,
        thesis_id: str,
        conversation_id: str,
        record: VoiceSessionRecord,
    ) -> None:
        try:
            conversation = self.repository.get_conversation(thesis_id, conversation_id)
        except AssistantRepositoryError:
            return

        def _flushed_sets(
            conv: Any,
        ) -> tuple[set[tuple[Any, ...]], set[tuple[Any, ...]], int]:
            turns = {
                (
                    message.get("created_at"),
                    message.get("content"),
                    message.get("voice_path"),
                    message.get("role"),
                )
                for message in conv.messages
                if isinstance(message, Mapping)
                and message.get("voice_session_id") == record.session_id
                and message.get("voice_path") is not None
            }
            tools = {
                (
                    entry.get("created_at"),
                    entry.get("tool_name"),
                    entry.get("ok"),
                    entry.get("error"),
                )
                for entry in conv.tool_transcript
                if isinstance(entry, Mapping) and entry.get("voice_session_id") == record.session_id
            }
            return turns, tools, conv.revision

        # Resume-safe idempotency: skip only entries already present; never treat
        # "any voice_session_id message exists" as a completed flush.
        flushed_turns, flushed_tools, revision = _flushed_sets(conversation)
        for turn in record.transcript:
            turn_key = (turn.created_at, turn.text, turn.path, turn.role)
            if turn_key in flushed_turns:
                continue
            message: dict[str, Any] = {
                "role": turn.role,
                "content": turn.text,
                "channel": turn.channel,
                "voice_session_id": record.session_id,
                "voice_path": turn.path,
                "created_at": turn.created_at,
            }
            if record.run_id is not None:
                message["run_id"] = record.run_id
            # Draft hydration must omit choices — never attach choices here.
            for _attempt in range(2):
                try:
                    conversation = self.repository.append_conversation_message(
                        thesis_id,
                        conversation_id,
                        expected_revision=revision,
                        message=message,
                    )
                    revision = conversation.revision
                    flushed_turns.add(turn_key)
                    break
                except VoiceContractError:
                    return
                except AssistantRepositoryError:
                    # OCC / concurrent write — refresh and retry once; do not
                    # abort remaining transcript/tool rows for this session.
                    try:
                        conversation = self.repository.get_conversation(thesis_id, conversation_id)
                    except AssistantRepositoryError:
                        return
                    flushed_turns, flushed_tools, revision = _flushed_sets(conversation)
                    if turn_key in flushed_turns:
                        break
            else:
                continue
        for invocation in record.tool_invocations:
            tool_key = (
                invocation.created_at,
                invocation.tool_name,
                invocation.ok,
                invocation.error,
            )
            if tool_key in flushed_tools:
                continue
            tool_entry = {
                "kind": "voice_tool",
                "voice_session_id": record.session_id,
                "tool_name": invocation.tool_name,
                "arguments": invocation.arguments,
                "ok": invocation.ok,
                "result": invocation.result,
                "error": invocation.error,
                "created_at": invocation.created_at,
                "channel": record.channel,
            }
            placeholder = {
                "role": "system",
                "content": f"voice_tool:{invocation.tool_name}",
                "channel": record.channel,
                "voice_session_id": record.session_id,
                "created_at": invocation.created_at,
            }
            if record.run_id is not None:
                placeholder["run_id"] = record.run_id
            for _attempt in range(2):
                try:
                    conversation = self.repository.append_conversation_message(
                        thesis_id,
                        conversation_id,
                        expected_revision=revision,
                        message=placeholder,
                        tool_entry=tool_entry,
                    )
                    revision = conversation.revision
                    flushed_tools.add(tool_key)
                    break
                except AssistantRepositoryError:
                    try:
                        conversation = self.repository.get_conversation(thesis_id, conversation_id)
                    except AssistantRepositoryError:
                        return
                    flushed_turns, flushed_tools, revision = _flushed_sets(conversation)
                    if tool_key in flushed_tools:
                        break
            else:
                continue
