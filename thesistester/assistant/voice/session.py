"""Voice session lifecycle, evidence bind, and honesty instructions (VA-2/VA-3).

Persists sibling ``voice_sessions/vs_*.json`` documents. Does not widen
``Conversation`` identity rules. Allowlisted tool execution lives in
``voice/tools.py`` (VA-3).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.repository import (
    AssistantRepositoryError,
    LocalThesisRepository,
    ResearchRun,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools
from thesistester.assistant.voice.contracts import (
    VoiceContractError,
    VoiceSessionRecord,
    VoiceToolInvocation,
    VoiceTranscriptTurn,
    validate_voice_session_id,
)
from thesistester.assistant.voice.settings import VoiceSettings, load_voice_settings
from thesistester.assistant.workspace import require_run_bundle_hash

_VOICE_CHANNELS = frozenset({"results_qa", "product_help"})
_VOICE_MODES = frozenset({"push_to_talk", "realtime"})


class VoiceSessionError(ValueError):
    """Raised when a voice session cannot be created or updated safely."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_voice_session_id() -> str:
    return f"vs_{uuid4().hex}"


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
    ) -> VoiceSessionRecord:
        record = self.repository.get_voice_session(thesis_id, session_id)
        if record.status != "active":
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
        # Idempotent: a prior flush (or retry after end) must not duplicate turns.
        if any(
            isinstance(message, Mapping) and message.get("voice_session_id") == record.session_id
            for message in conversation.messages
        ):
            return
        revision = conversation.revision
        for turn in record.transcript:
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
            try:
                conversation = self.repository.append_conversation_message(
                    thesis_id,
                    conversation_id,
                    expected_revision=revision,
                    message=message,
                )
                revision = conversation.revision
            except (AssistantRepositoryError, VoiceContractError):
                return
        for invocation in record.tool_invocations:
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
            }
            if record.run_id is not None:
                placeholder["run_id"] = record.run_id
            try:
                conversation = self.repository.append_conversation_message(
                    thesis_id,
                    conversation_id,
                    expected_revision=revision,
                    message=placeholder,
                    tool_entry=tool_entry,
                )
                revision = conversation.revision
            except AssistantRepositoryError:
                return
