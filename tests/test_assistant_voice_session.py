"""VA-2 voice session service + xAI helper tests (mocked HTTP; no live network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from thesistester.assistant.repository import (
    AssistantRepositoryError,
    LocalThesisRepository,
    RepositoryConflictError,
)
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.voice.contracts import VoiceTranscriptTurn
from thesistester.assistant.voice.session import (
    VoiceSessionError,
    VoiceSessionService,
    _DX2_REALTIME_RESULTS_CONSTRAINT_LINES,
    build_honesty_instructions,
)
from thesistester.assistant.voice.settings import load_voice_settings
from thesistester.assistant.voice.xai_realtime import (
    VoiceConfigurationError,
    VoiceProviderError,
    _api_key_from_secrets_mapping,
    _encode_multipart,
    mint_ephemeral_token,
    require_xai_api_key,
    speech_to_text,
    text_to_speech,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

_RUN_SPEC = {
    "dataset": {"path": "bars.csv", "instrument": "ES"},
    "levels": {},
    "setup": {
        "name": "voice bind",
        "description": "",
        "instrument": "ES",
        "selected_levels": ["dVWAP_RTH"],
        "tolerance_ticks": 0,
        "min_confluences": 1,
        "max_confluences": 1,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "direction": "both",
    },
    "backtest": {
        "commission_per_side": 0,
        "slippage_ticks": 0,
        "exposure_policy": "single_position",
        "intrabar_model": "sl_first",
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "no_new_entries_after": "15:45",
    },
}


def _repository(tmp_path: Path) -> LocalThesisRepository:
    return LocalThesisRepository(tmp_path / "assistant")


def _completed_run_with_bundle(repository: LocalThesisRepository, tmp_path: Path):
    thesis = repository.create_thesis(name="voice results")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_RUN_SPEC,
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    confirmed = repository.confirm_spec_version(
        thesis.thesis_id, draft.version, confirmation_note="approved"
    )
    run = repository.start_run(
        thesis.thesis_id, spec_version=confirmed.version, request={"request_id": "voice"}
    )
    bundle_bytes = build_research_bundle({})
    digest = canonical_bundle_hash(bundle_bytes)
    bundle_path = tmp_path / "voice.research.zip"
    bundle_path.write_bytes(bundle_bytes)
    completed = repository.complete_run(
        thesis.thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={
            "bundle_path": str(bundle_path),
            "canonical_bundle_hash": digest,
        },
    )
    return thesis, completed, digest, bundle_path


def test_require_xai_api_key_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "thesistester.assistant.voice.xai_realtime._read_streamlit_xai_api_key",
        lambda: None,
    )
    with pytest.raises(VoiceConfigurationError, match="XAI_API_KEY"):
        require_xai_api_key()


def test_require_xai_api_key_rejects_placeholder_and_falls_through(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "REPLACE_WITH_ROTATED_XAI_API_KEY")
    monkeypatch.setattr(
        "thesistester.assistant.voice.xai_realtime._read_streamlit_xai_api_key",
        lambda: "secrets-rotated-xai",
    )
    assert require_xai_api_key() == "secrets-rotated-xai"


def test_require_xai_api_key_prefers_env_over_secrets(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "env-rotated-xai")
    monkeypatch.setattr(
        "thesistester.assistant.voice.xai_realtime._read_streamlit_xai_api_key",
        lambda: "secrets-rotated-xai",
    )
    assert require_xai_api_key() == "env-rotated-xai"


def test_xai_secrets_mapping_flat_and_nested_precedence():
    assert _api_key_from_secrets_mapping({"XAI_API_KEY": "flat"}) == "flat"
    assert _api_key_from_secrets_mapping({"xai": {"api_key": "nested"}}) == "nested"
    assert (
        _api_key_from_secrets_mapping({"XAI_API_KEY": "flat", "xai": {"api_key": "nested"}})
        == "flat"
    )
    assert (
        _api_key_from_secrets_mapping({"XAI_API_KEY": "REPLACE_WITH_ROTATED_XAI_API_KEY"}) is None
    )


def test_mint_ephemeral_token_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "thesistester.assistant.voice.xai_realtime._read_streamlit_xai_api_key",
        lambda: None,
    )
    with pytest.raises(VoiceConfigurationError, match="XAI_API_KEY"):
        mint_ephemeral_token()


def test_mint_stt_tts_use_mocked_transport(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    settings = load_voice_settings()

    class JSONTransport:
        def post_json(self, **kwargs):
            assert kwargs["url"].endswith("/realtime/client_secrets")
            assert kwargs["api_key"] == "test-xai-key"
            assert kwargs["payload"] == {"expires_after": {"seconds": 300}}
            return {"value": "ephemeral-secret"}

    token = mint_ephemeral_token(settings=settings, transport=JSONTransport())
    assert token.value == "ephemeral-secret"
    assert token.expires_after_seconds == 300
    assert token.to_public_dict()["has_value"] is True
    assert "ephemeral-secret" not in str(token.to_public_dict())

    class BinaryTransport:
        def post_multipart(self, **kwargs):
            assert kwargs["url"].endswith("/stt")
            assert kwargs["filename"] == "clip.wav"
            assert kwargs["file_bytes"] == b"RIFF-audio"
            return {"text": "what is my win rate?", "duration": 1.2}

        def post_json_bytes(self, **kwargs):
            assert kwargs["url"].endswith("/tts")
            assert kwargs["payload"]["text"] == "Win rate is 55 percent."
            assert kwargs["payload"]["voice_id"] == "eve"
            return b"ID3-fake-mp3"

    transport = BinaryTransport()
    stt = speech_to_text(
        b"RIFF-audio",
        filename="clip.wav",
        settings=settings,
        transport=transport,
    )
    assert stt["text"] == "what is my win rate?"
    audio = text_to_speech(
        "Win rate is 55 percent.",
        settings=settings,
        transport=transport,
    )
    assert audio.startswith(b"ID3")


def test_mint_retries_then_fails(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    settings = load_voice_settings()
    calls = {"n": 0}

    class Flaky:
        def post_json(self, **kwargs):
            calls["n"] += 1
            raise VoiceProviderError("boom")

    with pytest.raises(VoiceProviderError, match="mint failed"):
        mint_ephemeral_token(settings=settings, transport=Flaky())
    assert calls["n"] == settings.max_retries + 1


def test_help_session_without_run_persists_vs_id(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="help voice")
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
    )
    assert record.session_id.startswith("vs_")
    assert len(record.session_id) == 3 + 32
    assert record.run_id is None
    assert record.expected_canonical_bundle_hash is None
    assert record.status == "active"
    loaded = repository.get_voice_session(thesis.thesis_id, record.session_id)
    assert loaded == record
    assert service.get_bound_packet(record.session_id) is None


def test_results_session_binds_hash_verified_packet(tmp_path):
    repository = _repository(tmp_path)
    thesis, run, digest, _bundle = _completed_run_with_bundle(repository, tmp_path)
    tools = AssistantTools(data_roots=(tmp_path,))
    service = VoiceSessionService(repository, tools=tools)
    record = service.create_session(
        thesis.thesis_id,
        run.run_id,
        expected_hash=digest,
        mode="push_to_talk",
        channel="results_qa",
    )
    assert record.run_id == run.run_id
    assert record.expected_canonical_bundle_hash == digest
    packet = service.get_bound_packet(record.session_id)
    assert packet is not None
    assert packet.provenance["canonical_bundle_hash"] == digest
    instructions = service.build_honesty_instructions(record)
    assert "evidence/docs-only" in instructions
    assert "no trade advice" in instructions
    assert "numbers only from tools/packet/corpus rules" in instructions
    assert "sample-size/OOS caveats" in instructions


def test_results_session_fails_closed_on_bad_hash_and_missing_run(tmp_path):
    repository = _repository(tmp_path)
    thesis, run, digest, _bundle = _completed_run_with_bundle(repository, tmp_path)
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    with pytest.raises(VoiceSessionError, match="does not match"):
        service.create_session(
            thesis.thesis_id,
            run.run_id,
            expected_hash="f" * 64,
            mode="push_to_talk",
            channel="results_qa",
        )
    with pytest.raises(VoiceSessionError, match="does not exist"):
        service.create_session(
            thesis.thesis_id,
            "run_" + "0" * 32,
            expected_hash=digest,
            mode="push_to_talk",
            channel="results_qa",
        )


def test_results_session_fails_closed_when_bundle_file_missing(tmp_path):
    repository = _repository(tmp_path)
    thesis, run, digest, bundle_path = _completed_run_with_bundle(repository, tmp_path)
    bundle_path.unlink()
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    with pytest.raises(VoiceSessionError, match="missing"):
        service.create_session(
            thesis.thesis_id,
            run.run_id,
            expected_hash=digest,
            mode="push_to_talk",
            channel="results_qa",
        )


def test_honesty_instruction_policy_strings():
    results = build_honesty_instructions(
        channel="results_qa",
        mode="push_to_talk",
        run_id="run_" + "a" * 32,
        expected_hash="b" * 64,
    )
    help_text = build_honesty_instructions(channel="product_help", mode="realtime")
    for text in (results, help_text):
        assert "evidence/docs-only" in text
        assert "no trade advice" in text
        assert "numbers only from tools/packet/corpus rules" in text
    assert "sample-size/OOS caveats" in results
    assert "remediate to Discuss results" in help_text
    # DX-2 duplex needles are realtime/results-only — not PTT or Help.
    assert "kpi_claims" not in results
    assert "kpi_claims" not in help_text


def test_realtime_results_honesty_includes_dx2_needles():
    text = build_honesty_instructions(
        channel="results_qa",
        mode="realtime",
        run_id="run_" + "c" * 32,
        expected_hash="d" * 64,
    )
    for needle in _DX2_REALTIME_RESULTS_CONSTRAINT_LINES:
        assert needle in text
    assert "\n".join(_DX2_REALTIME_RESULTS_CONSTRAINT_LINES) in text
    assert "sample-size/OOS caveats" in text
    assert "Never enable web_search" in text or "web_search" in text


def test_end_session_flushes_transcript_best_effort(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="flush voice")
    conversation = repository.create_conversation(thesis.thesis_id)
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
        conversation_id=conversation.conversation_id,
    )
    service.append_transcript_turn(
        thesis.thesis_id,
        record.session_id,
        VoiceTranscriptTurn(
            role="user",
            text="How does grid ranking work?",
            created_at="2026-08-06T12:00:00+00:00",
            channel="product_help",
            path="stt",
        ),
    )
    ended = service.end_session(
        thesis.thesis_id,
        record.session_id,
        conversation_id=conversation.conversation_id,
    )
    assert ended.status == "ended"
    assert ended.ended_at is not None
    refreshed = repository.get_conversation(thesis.thesis_id, conversation.conversation_id)
    assert any(
        message.get("voice_session_id") == record.session_id for message in refreshed.messages
    )
    assert all("choices" not in message for message in refreshed.messages)


def test_page_modules_do_not_embed_xai_api_key():
    pages = Path("pages")
    offenders = []
    for path in pages.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "XAI_API_KEY" in text:
            offenders.append(path.name)
    assert offenders == []


def test_explicit_api_key_empty_or_placeholder_fails_closed(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "thesistester.assistant.voice.xai_realtime._read_streamlit_xai_api_key",
        lambda: None,
    )

    class JSONTransport:
        def post_json(self, **kwargs):
            raise AssertionError("transport must not run for unusable keys")

    for bad in ("", "   ", "REPLACE_WITH_ROTATED_XAI_API_KEY"):
        with pytest.raises(VoiceConfigurationError, match="XAI_API_KEY"):
            mint_ephemeral_token(api_key=bad, transport=JSONTransport())


def test_multipart_rejects_header_injection_tokens():
    with pytest.raises(VoiceConfigurationError, match="filename"):
        _encode_multipart(
            fields=[("language", "en")],
            file_field="file",
            filename='clip.wav"\r\nX-Injected: 1',
            content_type="audio/wav",
            file_bytes=b"x",
        )
    with pytest.raises(VoiceConfigurationError, match="multipart field"):
        _encode_multipart(
            fields=[("language", "en\r\nContent-Disposition: form-data; name=x")],
            file_field="file",
            filename="clip.wav",
            content_type="audio/wav",
            file_bytes=b"x",
        )


def test_invalid_voice_session_id_raises_repository_error(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="bad voice id")
    with pytest.raises(AssistantRepositoryError, match="Invalid assistant record identifier"):
        repository.get_voice_session(thesis.thesis_id, "vs_nothex")


def test_voice_session_revision_conflict(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="occ voice")
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
    )
    assert record.revision == 1
    stale = record
    service.append_transcript_turn(
        thesis.thesis_id,
        record.session_id,
        VoiceTranscriptTurn(
            role="user",
            text="hello",
            created_at="2026-08-06T12:00:00+00:00",
            channel="product_help",
            path="stt",
        ),
    )
    with pytest.raises(RepositoryConflictError, match="revision"):
        repository.save_voice_session(stale)


def test_help_session_persists_conversation_id_and_retry_flush(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="bound conv")
    conversation = repository.create_conversation(thesis.thesis_id)
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
        conversation_id=conversation.conversation_id,
    )
    assert record.conversation_id == conversation.conversation_id
    service.append_transcript_turn(
        thesis.thesis_id,
        record.session_id,
        VoiceTranscriptTurn(
            role="user",
            text="What is Help?",
            created_at="2026-08-06T12:00:00+00:00",
            channel="product_help",
            path="stt",
        ),
    )
    ended = service.end_session(thesis.thesis_id, record.session_id)
    assert ended.status == "ended"
    refreshed = repository.get_conversation(thesis.thesis_id, conversation.conversation_id)
    first_count = sum(
        1 for message in refreshed.messages if message.get("voice_session_id") == record.session_id
    )
    assert first_count >= 1
    # Retry flush must stay idempotent (no duplicate voice messages).
    service.end_session(
        thesis.thesis_id,
        record.session_id,
        conversation_id=conversation.conversation_id,
    )
    again = repository.get_conversation(thesis.thesis_id, conversation.conversation_id)
    second_count = sum(
        1 for message in again.messages if message.get("voice_session_id") == record.session_id
    )
    assert second_count == first_count


def test_partial_flush_resumes_remaining_transcript_turns(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="partial flush")
    conversation = repository.create_conversation(thesis.thesis_id)
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
        conversation_id=conversation.conversation_id,
    )
    service.append_transcript_turn(
        thesis.thesis_id,
        record.session_id,
        VoiceTranscriptTurn(
            role="user",
            text="first",
            created_at="2026-08-06T12:00:00+00:00",
            channel="product_help",
            path="stt",
        ),
    )
    service.append_transcript_turn(
        thesis.thesis_id,
        record.session_id,
        VoiceTranscriptTurn(
            role="assistant",
            text="second",
            created_at="2026-08-06T12:00:01+00:00",
            channel="product_help",
            path="tts",
        ),
    )
    # Simulate a partial prior flush: only the first turn is in the conversation.
    conversation = repository.append_conversation_message(
        thesis.thesis_id,
        conversation.conversation_id,
        expected_revision=conversation.revision,
        message={
            "role": "user",
            "content": "first",
            "channel": "product_help",
            "voice_session_id": record.session_id,
            "voice_path": "stt",
            "created_at": "2026-08-06T12:00:00+00:00",
        },
    )
    ended = service.end_session(
        thesis.thesis_id,
        record.session_id,
        conversation_id=conversation.conversation_id,
    )
    assert ended.status == "ended"
    refreshed = repository.get_conversation(thesis.thesis_id, conversation.conversation_id)
    voice_messages = [
        message
        for message in refreshed.messages
        if message.get("voice_session_id") == record.session_id
    ]
    assert len(voice_messages) == 2
    assert {message.get("content") for message in voice_messages} == {"first", "second"}


def test_results_session_rejects_bundle_outside_data_roots(tmp_path):
    import json

    repository = _repository(tmp_path)
    thesis, run, digest, bundle_path = _completed_run_with_bundle(repository, tmp_path)
    outside = tmp_path.parent / f"outside-voice-{bundle_path.name}"
    outside.write_bytes(bundle_path.read_bytes())
    run_path = repository.root / "theses" / thesis.thesis_id / "runs" / f"{run.run_id}.json"
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["provenance"] = {
        "bundle_path": str(outside),
        "canonical_bundle_hash": digest,
    }
    run_path.write_text(json.dumps(payload), encoding="utf-8")
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    with pytest.raises(VoiceSessionError, match="outside assistant data roots"):
        service.create_session(
            thesis.thesis_id,
            run.run_id,
            expected_hash=digest,
            mode="push_to_talk",
            channel="results_qa",
        )


def test_save_voice_session_rejects_non_contract_payload(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="corrupt voice")

    class Fake:
        thesis_id = thesis.thesis_id
        session_id = "vs_" + "a" * 32

        def to_dict(self):
            return {"not": "a voice session"}

    with pytest.raises(AssistantRepositoryError, match="Invalid voice session record"):
        repository.save_voice_session(Fake())
