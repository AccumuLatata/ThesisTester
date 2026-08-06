"""VA-0 voice contracts + settings freeze tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from thesistester.assistant.llm import (
    load_llm_settings,
    load_product_help_settings,
    load_results_qa_settings,
)
from thesistester.assistant.voice import (
    VOICE_CONTRACT_SCHEMA_VERSION,
    VOICE_SESSION_KIND,
    GroundingVerdict,
    VoiceContractError,
    VoiceSessionRecord,
    VoiceToolInvocation,
    VoiceTranscriptTurn,
    clear_voice_ui_overrides,
    load_voice_settings,
    resolve_voice_settings,
    save_voice_ui_overrides,
    validate_voice_session_id,
    with_voice_overrides,
)

TRACKED = Path("config/assistant.toml")
_HASH = "a" * 64
_SESSION_ID = "vs_" + "b" * 32


def _grounded_verdict() -> GroundingVerdict:
    return GroundingVerdict(
        grounded=True,
        audited_text="Win rate is 55.0 percent.",
        allowed_digit_tokens=("55.0",),
        uncited_digit_tokens=(),
        remediation=None,
    )


def test_tracked_config_keeps_voice_disabled():
    settings = load_voice_settings(TRACKED)
    assert settings.enabled is False
    assert settings.provider == "xai"
    assert settings.model == "grok-voice-think-fast-2.0"
    assert settings.voice == "eve"
    assert settings.mode == "push_to_talk"
    assert settings.channels == ("results_qa", "product_help")
    assert settings.max_session_minutes == 15
    assert settings.store_audio is False
    assert settings.allow_web_search is False
    assert settings.require_tool_for_numbers is True
    assert settings.ephemeral_token_ttl_seconds == 300
    assert settings.max_history_messages == 12
    assert settings.max_retries == 2


def test_voice_settings_keeps_python310_tomli_fallback():
    """CI runs pytest on 3.10; tomllib is 3.11+ so settings must mirror llm.py."""
    source = Path("thesistester/assistant/voice/settings.py").read_text(encoding="utf-8")
    assert "import tomli as tomllib" in source
    assert "ModuleNotFoundError" in source


def test_existing_settings_loaders_still_succeed_with_voice_section():
    llm = load_llm_settings(TRACKED)
    results = load_results_qa_settings(TRACKED)
    help_settings = load_product_help_settings(TRACKED)
    assert llm.provider == "openai"
    assert results.enabled is True
    assert help_settings.enabled is True


def test_missing_voice_section_returns_disabled_defaults(tmp_path):
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "max_tool_rounds = 8\n"
        "max_history_messages = 12\n"
        "max_retries = 2\n",
        encoding="utf-8",
    )
    settings = load_voice_settings(path)
    assert settings.enabled is False
    assert settings.model == "grok-voice-think-fast-2.0"
    assert settings.channels == ("results_qa", "product_help")


def test_enabled_flag_fails_closed_on_non_boolean(tmp_path):
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "\n"
        "[assistant.voice]\n"
        "enabled = 'false'\n"
        "store_audio = 'true'\n"
        "allow_web_search = 'yes'\n"
        "require_tool_for_numbers = 'no'\n",
        encoding="utf-8",
    )
    settings = load_voice_settings(path)
    assert settings.enabled is False
    assert settings.store_audio is True
    assert settings.allow_web_search is True
    assert settings.require_tool_for_numbers is False


def test_voice_ui_override_file_toggles_enabled_and_mode(tmp_path):
    config = tmp_path / "assistant.toml"
    config.write_text(TRACKED.read_text(encoding="utf-8"), encoding="utf-8")
    override = tmp_path / "assistant.voice.override.toml"
    base = load_voice_settings(config)
    assert base.enabled is False
    assert base.mode == "push_to_talk"

    save_voice_ui_overrides(enabled=True, mode="realtime", path=override)
    resolved = resolve_voice_settings(config, ui_override_path=override)
    assert resolved.enabled is True
    assert resolved.mode == "realtime"
    # Tracked loader remains default-off (release gate).
    assert load_voice_settings(config).enabled is False
    assert with_voice_overrides(base, enabled=True).enabled is True

    assert clear_voice_ui_overrides(override) is True
    assert resolve_voice_settings(config, ui_override_path=override).enabled is False


def test_voice_session_record_round_trip_results_channel():
    turn = VoiceTranscriptTurn(
        role="assistant",
        text="Win rate is 55.0 percent.",
        created_at="2026-08-06T12:00:00+00:00",
        channel="results_qa",
        path="handle_results_turn",
        grounding=_grounded_verdict(),
    )
    tool = VoiceToolInvocation(
        tool_name="get_metric",
        arguments={"path": "summary.win_rate"},
        ok=True,
        result={"value": 0.55},
        created_at="2026-08-06T12:00:01+00:00",
        error=None,
    )
    record = VoiceSessionRecord(
        session_id=_SESSION_ID,
        thesis_id="th_" + "c" * 32,
        run_id="run_" + "d" * 32,
        expected_canonical_bundle_hash=_HASH,
        mode="push_to_talk",
        channel="results_qa",
        status="active",
        created_at="2026-08-06T12:00:00+00:00",
        updated_at="2026-08-06T12:00:01+00:00",
        transcript=(turn,),
        tool_invocations=(tool,),
    )
    payload = record.to_dict()
    assert payload["schema_version"] == VOICE_CONTRACT_SCHEMA_VERSION
    assert payload["kind"] == VOICE_SESSION_KIND
    restored = VoiceSessionRecord.from_dict(payload)
    assert restored == record
    assert restored.to_dict() == payload


def test_voice_session_record_help_channel_omits_run_binding():
    record = VoiceSessionRecord(
        session_id=_SESSION_ID,
        thesis_id="th_" + "c" * 32,
        mode="push_to_talk",
        channel="product_help",
        status="ended",
        created_at="2026-08-06T12:00:00+00:00",
        updated_at="2026-08-06T12:05:00+00:00",
        ended_at="2026-08-06T12:05:00+00:00",
    )
    restored = VoiceSessionRecord.from_dict(record.to_dict())
    assert restored.run_id is None
    assert restored.expected_canonical_bundle_hash is None
    assert restored.status == "ended"


def test_voice_session_record_rejects_bad_id_and_results_without_hash():
    with pytest.raises(VoiceContractError, match="vs_"):
        VoiceSessionRecord(
            session_id="conv_" + "e" * 32,
            thesis_id="th_" + "c" * 32,
            run_id="run_" + "d" * 32,
            expected_canonical_bundle_hash=_HASH,
            mode="push_to_talk",
            channel="results_qa",
            status="active",
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
        )
    with pytest.raises(VoiceContractError, match="thesis_id"):
        VoiceSessionRecord(
            session_id=_SESSION_ID,
            thesis_id="../escape",
            mode="push_to_talk",
            channel="product_help",
            status="active",
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
        )
    with pytest.raises(VoiceContractError, match="run_"):
        VoiceSessionRecord(
            session_id=_SESSION_ID,
            thesis_id="th_" + "c" * 32,
            run_id="not-a-run-id",
            expected_canonical_bundle_hash=_HASH,
            mode="push_to_talk",
            channel="results_qa",
            status="active",
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
        )
    with pytest.raises(VoiceContractError, match="expected_canonical_bundle_hash"):
        VoiceSessionRecord(
            session_id=_SESSION_ID,
            thesis_id="th_" + "c" * 32,
            run_id="run_" + "d" * 32,
            expected_canonical_bundle_hash=None,
            mode="push_to_talk",
            channel="results_qa",
            status="active",
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
        )


def test_grounding_verdict_fails_closed_on_uncited_when_marked_grounded():
    with pytest.raises(VoiceContractError, match="uncited_digit_tokens"):
        GroundingVerdict(
            grounded=True,
            audited_text="Win rate is 99.",
            allowed_digit_tokens=("55",),
            uncited_digit_tokens=("99",),
        )
    with pytest.raises(VoiceContractError, match="remediation"):
        GroundingVerdict(
            grounded=False,
            audited_text="Win rate is 99.",
            allowed_digit_tokens=("55",),
            uncited_digit_tokens=("99",),
            remediation=None,
        )


def test_validate_voice_session_id_helper():
    assert validate_voice_session_id(_SESSION_ID) == _SESSION_ID
    with pytest.raises(VoiceContractError, match="vs_"):
        validate_voice_session_id("vs_nothex")


def test_voice_session_from_dict_rejects_null_provider_model_voice():
    base = {
        "session_id": _SESSION_ID,
        "thesis_id": "th_" + "c" * 32,
        "mode": "push_to_talk",
        "channel": "product_help",
        "status": "active",
        "created_at": "2026-08-06T12:00:00+00:00",
        "updated_at": "2026-08-06T12:00:00+00:00",
    }
    for field in ("provider", "model", "voice"):
        payload = {**base, field: None}
        with pytest.raises(VoiceContractError, match=field):
            VoiceSessionRecord.from_dict(payload)
    with pytest.raises(VoiceContractError, match="provider"):
        VoiceSessionRecord.from_dict({**base, "provider": 123})


def test_nested_contract_from_dict_missing_keys_raise_voice_contract_error():
    with pytest.raises(VoiceContractError, match="Missing GroundingVerdict keys"):
        GroundingVerdict.from_dict({"audited_text": "x"})
    with pytest.raises(VoiceContractError, match="Missing VoiceTranscriptTurn keys"):
        VoiceTranscriptTurn.from_dict(
            {"text": "hi", "created_at": "t", "channel": "results_qa", "path": "p"}
        )
    with pytest.raises(VoiceContractError, match="Missing VoiceToolInvocation keys"):
        VoiceToolInvocation.from_dict(
            {"arguments": {}, "ok": True, "result": {}, "created_at": "t"}
        )


def test_voice_session_rejects_transcript_channel_mismatch():
    turn = VoiceTranscriptTurn(
        role="user",
        text="help me",
        created_at="2026-08-06T12:00:00+00:00",
        channel="product_help",
        path="handle_help_turn",
    )
    with pytest.raises(VoiceContractError, match="do not mix histories"):
        VoiceSessionRecord(
            session_id=_SESSION_ID,
            thesis_id="th_" + "c" * 32,
            run_id="run_" + "d" * 32,
            expected_canonical_bundle_hash=_HASH,
            mode="push_to_talk",
            channel="results_qa",
            status="active",
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
            transcript=(turn,),
        )
