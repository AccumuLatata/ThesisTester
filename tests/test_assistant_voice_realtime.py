"""VA-5 realtime sidecar protocol + tool-bridge tests (mocked upstream WS)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.voice.contracts import VoiceSessionRecord
from thesistester.assistant.voice.session import (
    VoiceSessionService,
    session_exceeded_ttl,
)
from thesistester.assistant.voice.settings import VoiceSettings, load_voice_settings
from thesistester.assistant.voice.sidecar import (
    SidecarError,
    SidecarRuntime,
    assert_localhost_bind,
    build_function_call_output_events,
    build_realtime_session_update,
    build_sidecar_launch_command,
    create_sidecar_app,
    ensure_local_sidecar,
    execute_realtime_tool_bridge,
    extract_transcript_from_event,
    probe_sidecar_health,
    redact_for_logs,
    sidecar_public_base_url,
)
from thesistester.assistant.voice.tools import (
    VoiceToolError,
    assert_realtime_tools_allowlisted,
    realtime_function_tool_schemas,
)
from thesistester.assistant.voice.xai_realtime import realtime_websocket_url
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

_RUN_SPEC = {
    "dataset": {"path": "bars.csv", "instrument": "ES"},
    "levels": {},
    "setup": {
        "name": "voice realtime",
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


def _enabled_realtime_settings() -> VoiceSettings:
    base = load_voice_settings()
    return VoiceSettings(
        enabled=True,
        provider=base.provider,
        model=base.model,
        voice=base.voice,
        mode="realtime",
        channels=base.channels,
        max_session_minutes=15,
        store_audio=base.store_audio,
        allow_web_search=False,
        require_tool_for_numbers=base.require_tool_for_numbers,
        ephemeral_token_ttl_seconds=base.ephemeral_token_ttl_seconds,
        max_history_messages=base.max_history_messages,
        max_retries=base.max_retries,
    )


def _repository(tmp_path: Path) -> LocalThesisRepository:
    return LocalThesisRepository(tmp_path / "assistant")


def _completed_run(repository: LocalThesisRepository, tmp_path: Path):
    thesis = repository.create_thesis(name="voice realtime")
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
        thesis.thesis_id, spec_version=confirmed.version, request={"request_id": "rt"}
    )
    bundle_bytes = build_research_bundle({})
    digest = canonical_bundle_hash(bundle_bytes)
    bundle_path = tmp_path / "rt.research.zip"
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
    conversation = repository.create_conversation(thesis.thesis_id)
    return thesis, completed, digest, conversation


def test_localhost_bind_rejects_non_loopback():
    assert assert_localhost_bind("127.0.0.1") == "127.0.0.1"
    assert assert_localhost_bind("::1") == "::1"
    with pytest.raises(SidecarError, match="non-localhost"):
        assert_localhost_bind("0.0.0.0")
    with pytest.raises(SidecarError, match="non-localhost"):
        assert_localhost_bind("192.168.1.10")
    with pytest.raises(SidecarError, match="non-localhost"):
        assert_localhost_bind("localhost")


def test_session_update_omits_search_and_mcp():
    settings = _enabled_realtime_settings()
    payload = build_realtime_session_update(
        instructions="evidence/docs-only\nno trade advice\nnumbers only from tools",
        voice="eve",
        settings=settings,
    )
    assert payload["type"] == "session.update"
    tools = payload["session"]["tools"]
    assert tools
    types = {tool.get("type") for tool in tools}
    assert types == {"function"}
    names = {tool.get("name") for tool in tools}
    assert names == {"get_run_overview", "get_metric", "list_caveats", "compare_two_runs"}
    blob = json.dumps(payload)
    for forbidden in ("web_search", "x_search", "file_search", "mcp"):
        assert forbidden not in blob
    assert payload["session"]["turn_detection"] == {"type": "server_vad"}
    assert payload["session"]["audio"]["input"]["format"]["rate"] == 24000
    assert payload["session"]["audio"]["input"]["transport"] == "binary"
    assert payload["session"]["audio"]["output"]["transport"] == "binary"
    assert payload["session"]["audio"]["input"]["transcription"]["model"] == "grok-transcribe"


def test_assert_realtime_tools_allowlisted_denies_search():
    with pytest.raises(VoiceToolError, match="Forbidden realtime tool type"):
        assert_realtime_tools_allowlisted([{"type": "web_search"}])
    with pytest.raises(VoiceToolError, match="Forbidden realtime tool type"):
        assert_realtime_tools_allowlisted([{"type": "mcp", "server_url": "https://x"}])
    with pytest.raises(VoiceToolError, match="not in VA-3 allowlist"):
        assert_realtime_tools_allowlisted(
            [{"type": "function", "name": "execute_confirmed_run", "parameters": {}}]
        )
    assert_realtime_tools_allowlisted(list(realtime_function_tool_schemas()))


def test_tool_bridge_allowlist_and_injection(tmp_path: Path):
    repository = _repository(tmp_path)
    thesis, run, digest, conversation = _completed_run(repository, tmp_path)
    service = VoiceSessionService(
        repository,
        tools=AssistantTools(data_roots=(tmp_path.resolve(),)),
        settings=_enabled_realtime_settings(),
    )
    record = service.create_session(
        thesis.thesis_id,
        run_id=run.run_id,
        expected_hash=digest,
        mode="realtime",
        channel="results_qa",
        conversation_id=conversation.conversation_id,
    )
    tool_session = service.tool_session(thesis.thesis_id, record.session_id)
    denied = execute_realtime_tool_bridge(
        name="PIPELINE.run_experiment",
        arguments={},
        tool_session=tool_session,
    )
    assert denied["ok"] is False
    assert (
        "PIPELINE" in (denied.get("error") or "")
        or "denied" in (denied.get("error") or "").lower()
        or "Unknown" in (denied.get("error") or "")
    )
    denied2 = execute_realtime_tool_bridge(
        name="execute_confirmed_run",
        arguments={},
        tool_session=tool_session,
    )
    assert denied2["ok"] is False
    overview = execute_realtime_tool_bridge(
        name="get_run_overview",
        arguments="{}",
        tool_session=tool_session,
    )
    assert overview["ok"] is True
    create_item, response_create = build_function_call_output_events(
        call_id="call_1",
        output=overview,
    )
    assert create_item["item"]["type"] == "function_call_output"
    assert response_create["type"] == "response.create"


def test_ttl_enforcement():
    created = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    record = VoiceSessionRecord(
        session_id="vs_" + ("ab" * 16),
        thesis_id="th_" + ("cd" * 16),
        run_id="run_" + ("ef" * 16),
        expected_canonical_bundle_hash="a" * 64,
        conversation_id=None,
        mode="realtime",
        channel="results_qa",
        status="active",
        created_at=created.isoformat(),
        updated_at=created.isoformat(),
        provider="xai",
        model="grok-voice-think-fast-2.0",
        voice="eve",
        revision=1,
    )
    assert (
        session_exceeded_ttl(
            record,
            max_session_minutes=15,
            now=created + timedelta(minutes=14, seconds=59),
        )
        is False
    )
    assert (
        session_exceeded_ttl(
            record,
            max_session_minutes=15,
            now=created + timedelta(minutes=15),
        )
        is True
    )


def test_redact_for_logs_strips_secrets():
    redacted = redact_for_logs(
        {"Authorization": "Bearer secret", "api_key": "x", "ok": True, "nested": {"token": "t"}}
    )
    assert redacted["Authorization"] == "[redacted]"
    assert redacted["api_key"] == "[redacted]"
    assert redacted["nested"]["token"] == "[redacted]"
    assert redacted["ok"] is True


def test_extract_transcript_events():
    assert extract_transcript_from_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "What is win rate?",
        }
    ) == ("user", "What is win rate?")
    assert extract_transcript_from_event(
        {"type": "response.output_audio_transcript.done", "transcript": "Win rate is grounded."}
    ) == ("assistant", "Win rate is grounded.")
    assert extract_transcript_from_event({"type": "session.updated"}) is None


def test_client_html_uses_js_null_not_python_none():
    from thesistester.assistant.voice.sidecar import _html_client_page

    html = _html_client_page(session_id="vs_" + ("cd" * 16))
    assert "let mediaStream = null;" in html
    assert "let mediaStream = None;" not in html


def test_realtime_websocket_url_pins_model():
    url = realtime_websocket_url(model="grok-voice-think-fast-2.0")
    assert url.startswith("wss://api.x.ai/v1/realtime?model=")
    assert "grok-voice-think-fast-2.0" in url
    assert "latest" not in url or "think-fast" in url


def test_sidecar_register_end_and_app_routes(tmp_path: Path):
    pytest.importorskip("starlette")
    repository = _repository(tmp_path)
    thesis, run, digest, conversation = _completed_run(repository, tmp_path)
    service = VoiceSessionService(
        repository,
        tools=AssistantTools(data_roots=(tmp_path.resolve(),)),
        settings=_enabled_realtime_settings(),
    )
    runtime = SidecarRuntime(
        service=service,
        settings=_enabled_realtime_settings(),
        host="127.0.0.1",
        port=8765,
    )
    body = runtime.register_session(
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        expected_hash=digest,
        conversation_id=conversation.conversation_id,
    )
    assert body["session_id"].startswith("vs_")
    assert "api_key" not in body
    assert "token" not in body
    assert "client_secret" not in body
    assert body["client_url"].startswith("http://127.0.0.1:8765/client?")
    ended = runtime.end_session(body["session_id"])
    assert ended["status"] == "ended"
    app = create_sidecar_app(runtime)
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/health" in paths
    assert "/v1/sessions" in paths
    assert "/v1/realtime/{session_id}" in paths
    assert "/client" in paths


def test_sidecar_rejects_disabled_voice(tmp_path: Path):
    repository = _repository(tmp_path)
    thesis, run, digest, conversation = _completed_run(repository, tmp_path)
    settings = load_voice_settings()  # enabled=false
    service = VoiceSessionService(
        repository,
        tools=AssistantTools(data_roots=(tmp_path.resolve(),)),
        settings=settings,
    )
    runtime = SidecarRuntime(service=service, settings=settings, host="127.0.0.1", port=8765)
    with pytest.raises(SidecarError, match="disabled"):
        runtime.register_session(
            thesis_id=thesis.thesis_id,
            run_id=run.run_id,
            expected_hash=digest,
            conversation_id=conversation.conversation_id,
        )


def test_page_source_realtime_controls_and_no_xai_socket():
    page = Path("pages/14_Research_Assistant.py").read_text(encoding="utf-8")
    assert "Voice discuss (realtime)" in page
    assert "thesistester.assistant.voice.sidecar" in page
    assert "_register_realtime_session(" in page
    assert "_render_sidecar_status_controls" in page
    assert "Launch local sidecar" in page
    assert "ensure_local_sidecar" in page
    assert "probe_sidecar_health" in page
    assert "assert_localhost_bind" in page
    assert "_client_url_is_localhost" in page
    assert "wss://api.x.ai" not in page
    assert "XAI_API_KEY" not in page
    assert 'mode == "realtime"' in page or "mode == 'realtime'" in page


def test_sidecar_public_base_url_and_launch_command_loopback_only():
    assert sidecar_public_base_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"
    with pytest.raises(SidecarError, match="127.0.0.1"):
        sidecar_public_base_url("0.0.0.0", 8765)
    with pytest.raises(SidecarError, match="127.0.0.1"):
        build_sidecar_launch_command(host="localhost", port=8765)
    with pytest.raises(SidecarError, match="port"):
        build_sidecar_launch_command(host="127.0.0.1", port=0)
    cmd = build_sidecar_launch_command(
        host="127.0.0.1",
        port=8765,
        python_executable="/usr/bin/python3",
    )
    assert cmd == [
        "/usr/bin/python3",
        "-m",
        "thesistester.assistant.voice.sidecar",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]


def test_probe_sidecar_health_fail_closed(monkeypatch):
    assert probe_sidecar_health("http://example.com") is None
    assert probe_sidecar_health("not-a-url") is None

    class _Boom:
        def __enter__(self):
            raise ConnectionRefusedError("refused")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.urllib_request.urlopen",
        lambda *args, **kwargs: _Boom(),
    )
    assert probe_sidecar_health("http://127.0.0.1:8765") is None


def test_probe_sidecar_health_ok(monkeypatch):
    class _Resp:
        status = 200

        def read(self):
            return json.dumps(
                {"ok": True, "host": "127.0.0.1", "port": 8765, "mode": "realtime"}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.urllib_request.urlopen",
        lambda *args, **kwargs: _Resp(),
    )
    health = probe_sidecar_health("http://127.0.0.1:8765")
    assert health is not None
    assert health["ok"] is True
    assert health["mode"] == "realtime"


def test_ensure_local_sidecar_noop_when_healthy(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.probe_sidecar_health",
        lambda base_url, **kwargs: {"ok": True, "port": 8765},
    )

    def _must_not_launch(**kwargs):
        raise AssertionError("launch should not run when health is ok")

    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.launch_local_sidecar",
        _must_not_launch,
    )
    status = ensure_local_sidecar(host="127.0.0.1", port=8765)
    assert status["ok"] is True
    assert status["launched"] is False
    assert status["pid"] is None


def test_ensure_local_sidecar_launches_and_waits(monkeypatch):
    probes = {"n": 0}

    def _probe(base_url, **kwargs):
        probes["n"] += 1
        if probes["n"] < 3:
            return None
        return {"ok": True, "port": 8765}

    class _Proc:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.probe_sidecar_health",
        _probe,
    )
    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.launch_local_sidecar",
        lambda **kwargs: _Proc(),
    )
    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.time.sleep",
        lambda *_args, **_kwargs: None,
    )
    status = ensure_local_sidecar(
        host="127.0.0.1",
        port=8765,
        ready_timeout_seconds=2.0,
        poll_interval_seconds=0.0,
    )
    assert status["launched"] is True
    assert status["pid"] == 4242
    assert status["health"]["ok"] is True


def test_ensure_local_sidecar_raises_when_child_exits(monkeypatch):
    class _Dead:
        pid = 7

        def poll(self):
            return 1

    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.probe_sidecar_health",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "thesistester.assistant.voice.sidecar.launch_local_sidecar",
        lambda **kwargs: _Dead(),
    )
    with pytest.raises(SidecarError, match="exited before becoming healthy"):
        ensure_local_sidecar(host="127.0.0.1", port=8765, ready_timeout_seconds=1.0)


def test_browser_cannot_inject_conversation_item_create():
    from thesistester.assistant.voice import sidecar as sidecar_mod

    allowed = sidecar_mod._BROWSER_UPSTREAM_EVENT_TYPES
    assert "input_audio_buffer.append" in allowed
    assert "input_audio_buffer.commit" in allowed
    assert "response.cancel" in allowed
    assert "conversation.item.create" not in allowed
    assert "response.create" not in allowed


def test_function_call_output_requires_call_id():
    with pytest.raises(SidecarError, match="call_id"):
        build_function_call_output_events(call_id="", output={"ok": True})
    with pytest.raises(SidecarError, match="call_id"):
        build_function_call_output_events(call_id="   ", output={"ok": True})


def test_end_session_missing_ok_is_idempotent(tmp_path: Path):
    repository = _repository(tmp_path)
    thesis, run, digest, conversation = _completed_run(repository, tmp_path)
    service = VoiceSessionService(
        repository,
        tools=AssistantTools(data_roots=(tmp_path.resolve(),)),
        settings=_enabled_realtime_settings(),
    )
    runtime = SidecarRuntime(
        service=service,
        settings=_enabled_realtime_settings(),
        host="127.0.0.1",
        port=8765,
    )
    body = runtime.register_session(
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        expected_hash=digest,
        conversation_id=conversation.conversation_id,
    )
    first = runtime.end_session(body["session_id"])
    assert first["status"] == "ended"
    assert first.get("noop") is not True
    second = runtime.end_session(body["session_id"], missing_ok=True)
    assert second["status"] == "ended"
    assert second.get("noop") is True
    with pytest.raises(SidecarError, match="not registered"):
        runtime.end_session(body["session_id"], missing_ok=False)
