"""DX duplex intelligence: DX-1 envelopes + DX-2 realtime instruction needles."""

from __future__ import annotations

from pathlib import Path

from thesistester.assistant.explainer import EvidenceCaveat, EvidencePacket
from thesistester.assistant.llm_explainer import _ungrounded_number_tokens
from thesistester.assistant.results_overview import (
    KPI_CLAIM_PATHS,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    has_overview_negative_cue,
    match_overview_intent,
)
from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.voice.contracts import VoiceTranscriptTurn
from thesistester.assistant.voice.grounding import format_speakable_tool_result
from thesistester.assistant.voice.session import (
    VoiceSessionService,
    _DX2_REALTIME_RESULTS_CONSTRAINT_LINES,
    build_honesty_instructions,
)
from thesistester.assistant.voice.sidecar import build_realtime_session_update
from thesistester.assistant.voice.tools import (
    VOICE_TOOL_SCHEMAS,
    execute_voice_tool,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

# Canonical §4.3 needles — same tuple the builder/create validator use.
_DX2_NEEDLES = _DX2_REALTIME_RESULTS_CONSTRAINT_LINES

_RUN_SPEC = {
    "dataset": {"path": "bars.csv", "instrument": "ES"},
    "levels": {},
    "setup": {
        "name": "dx1",
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


def _kpi_packet(**extra_results) -> EvidencePacket:
    results = {
        "trade_count": 99,  # non-baseline leaf; must not be preferred as sample size
        "trade_summary": {
            "trade_count": 42,
            "expectancy_r": 0.25,
            "win_rate": 0.52,
            "profit_factor": 1.4,
            "max_drawdown_r": -2.0,
            "total_r": 10.5,
        },
        "best_grid_result": {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 40,
        },
    }
    results.update(extra_results)
    return EvidencePacket(
        provenance={"run_id": "run_dx1"},
        assumptions={"instrument": "NQ"},
        results=results,
        warnings=(),
        caveats=(
            EvidenceCaveat(
                code="diagnostic_only",
                message="Historical sample is diagnostic only; not proof of edge.",
            ),
        ),
        limitations=("Time analysis is not present in this evidence packet.",),
    )


def _results_session(tmp_path: Path, *, packet: EvidencePacket | None = None):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="dx1")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_RUN_SPEC,
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    confirmed = repository.confirm_spec_version(
        thesis.thesis_id, draft.version, confirmation_note="ok"
    )
    run = repository.start_run(
        thesis.thesis_id, spec_version=confirmed.version, request={"request_id": "dx1"}
    )
    bundle_bytes = build_research_bundle({})
    digest = canonical_bundle_hash(bundle_bytes)
    bundle_path = tmp_path / "dx1.research.zip"
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
    tools = AssistantTools(data_roots=(tmp_path,))
    service = VoiceSessionService(repository, tools=tools)
    record = service.create_session(
        thesis.thesis_id,
        completed.run_id,
        expected_hash=digest,
        mode="realtime",
        channel="results_qa",
    )
    if packet is not None:
        service._bound_packets[record.session_id] = packet
    handle = service.tool_session(thesis.thesis_id, record.session_id)
    return service, handle, thesis, completed, digest


def _append_user(service: VoiceSessionService, thesis_id: str, session_id: str, text: str) -> None:
    service.append_transcript_turn(
        thesis_id,
        session_id,
        VoiceTranscriptTurn(
            role="user",
            text=text,
            channel="results_qa",
            path="stt",
            created_at="2026-08-08T00:00:00+00:00",
        ),
    )


def _append_assistant(
    service: VoiceSessionService, thesis_id: str, session_id: str, text: str
) -> None:
    service.append_transcript_turn(
        thesis_id,
        session_id,
        VoiceTranscriptTurn(
            role="assistant",
            text=text,
            channel="results_qa",
            path="tts",
            created_at="2026-08-08T00:00:01+00:00",
        ),
    )


def test_has_overview_negative_cue_export_word_boundary():
    assert has_overview_negative_cue("summarize the walk-forward results") is True
    assert has_overview_negative_cue("validation diagnostics please") is True
    assert has_overview_negative_cue("KPIs and best SL/TP") is True
    assert has_overview_negative_cue("runtime of this batch") is False
    assert has_overview_negative_cue("stopwatch only") is False
    assert has_overview_negative_cue("non-stop session") is False
    assert has_overview_negative_cue("off-grid idea") is False
    # unmatched alone is not a negative cue
    assert has_overview_negative_cue("tell me about this") is False
    assert match_overview_intent("tell me about this") is None


def test_get_run_overview_neutral_no_transcript_policy_a(tmp_path: Path):
    _service, handle, _thesis, _run, digest = _results_session(tmp_path, packet=_kpi_packet())
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    assert out["ok"] is True
    result = out["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_RUN
    assert result["canonical_bundle_hash"] == digest
    assert "summary" in result and result["summary"]
    assert result["overview"] == result["summary"]
    assert result["claims"] == result["kpi_claims"]
    assert result["claims"]
    paths = {item["path"] for item in result["kpi_claims"]}
    assert paths <= set(KPI_CLAIM_PATHS)
    assert "results.trade_summary.trade_count" in paths
    assert "results.trade_count" not in paths
    assert "remediation" not in result or not result.get("remediation")
    overlay = result.get("expert_overlay") or []
    assert overlay
    for line in overlay:
        assert _ungrounded_number_tokens(line, allowed=set()) == []
    # Overlay must not be dumped into typed packet caveat dicts.
    caveat_messages = {item.get("message") for item in result["caveats"] if isinstance(item, dict)}
    assert not any(line in caveat_messages for line in overlay)


def test_get_run_overview_kpi_match_and_speakable_summary_first(tmp_path: Path):
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    _append_user(service, thesis.thesis_id, handle.session_id, "Give me the KPIs of this run")
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    assert out["ok"] is True
    result = out["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_KPI
    assert result["claims"] == result["kpi_claims"]
    speakable = format_speakable_tool_result("get_run_overview", result)
    assert result["summary"]
    assert speakable.startswith(result["summary"].rstrip(".")) or result["summary"] in speakable
    # Must prefer summary body, not invent a different legacy explainer essay.
    assert "Key metrics" in speakable or "Win rate" in speakable or "%" in speakable


def test_get_run_overview_negative_veto_strips_legacy(tmp_path: Path):
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    _append_user(
        service,
        thesis.thesis_id,
        handle.session_id,
        "summarize the walk-forward / validation results",
    )
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    assert out["ok"] is True
    result = out["result"]
    assert result["overview_intent"] is None
    assert result["claims"] == []
    assert "kpi_claims" not in result or result.get("kpi_claims") in (None, [])
    assert "summary" not in result or not result.get("summary")
    assert "expert_overlay" not in result or result.get("expert_overlay") in (None, [])
    assert result.get("remediation")
    assert _ungrounded_number_tokens(result["remediation"], allowed=set()) == []
    assert result["overview"] == result["remediation"]
    # Must not reintroduce explainer multi-template narrative via legacy overview.
    assert "Key metrics" not in (result["overview"] or "")
    assert "expectancy_r" not in (result["overview"] or "")


def test_get_run_overview_mixed_ask_full_veto(tmp_path: Path):
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    _append_user(service, thesis.thesis_id, handle.session_id, "KPIs and best SL/TP")
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    result = out["result"]
    assert result["overview_intent"] is None
    assert result["claims"] == []
    assert result.get("remediation")


def test_get_run_overview_unmatched_is_neutral_not_remediation(tmp_path: Path):
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    _append_user(service, thesis.thesis_id, handle.session_id, "tell me about this")
    # match_overview_intent is None, but no negative cue → neutral overview.
    assert match_overview_intent("tell me about this") is None
    assert has_overview_negative_cue("tell me about this") is False
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    result = out["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_RUN
    assert result["kpi_claims"]
    assert not result.get("remediation")


def test_get_run_overview_missing_trade_summary_honest(tmp_path: Path):
    packet = EvidencePacket(
        provenance={"run_id": "run_dx1_missing"},
        assumptions={},
        results={"trade_count": 0, "trade_summary": None},
        warnings=(),
        limitations=("Baseline trade summary is unavailable on this packet.",),
    )
    _service, handle, _thesis, _run, _digest = _results_session(tmp_path, packet=packet)
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    result = out["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_RUN
    assert result["kpi_claims"] == []
    assert result["claims"] == []
    assert result.get("remediation")
    assert _ungrounded_number_tokens(result["remediation"], allowed=set()) == []
    # No fabricated allowlist scalars.
    for path in KPI_CLAIM_PATHS:
        assert path not in (result.get("summary") or "")


def test_get_metric_still_returns_existing_trade_count_leaf(tmp_path: Path):
    _service, handle, _thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    out = execute_voice_tool("get_metric", {"path": "results.trade_count"}, session=handle)
    assert out["ok"] is True
    assert out["result"]["path"] == "results.trade_count"
    assert out["result"]["value"] == 99


def test_get_metric_schema_prefers_trade_summary_paths():
    metric = next(item for item in VOICE_TOOL_SCHEMAS if item["name"] == "get_metric")
    path_desc = metric["parameters"]["properties"]["path"]["description"]
    assert "results.trade_summary.trade_count" in path_desc
    assert "results.trade_summary.win_rate" in path_desc
    overview = next(item for item in VOICE_TOOL_SCHEMAS if item["name"] == "get_run_overview")
    desc = overview["description"]
    assert "do not invent results.trade_count" in desc
    assert "kpi_claims" in desc
    assert "expert_overlay" in desc


def test_match_none_alone_does_not_mean_veto(tmp_path: Path):
    """X19: bare match_overview_intent is None must not imply remediation."""
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    text = "hello there"
    assert match_overview_intent(text) is None
    assert has_overview_negative_cue(text) is False
    _append_user(service, thesis.thesis_id, handle.session_id, text)
    result = execute_voice_tool("get_run_overview", {}, session=handle)["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_RUN
    assert result["kpi_claims"]
    assert not result.get("remediation")


def test_speakable_skips_overlay_lines_with_digits():
    """DX §4.2: speakable may append only digit-free expert_overlay lines."""
    payload = {
        "summary": "Win rate is grounded from claims.",
        "expert_overlay": [
            "Historical sample is diagnostic only; not proof of edge.",
            "This line sneaks in 42 trades and must be dropped.",
        ],
        "overview": "legacy overview must not win when summary is present",
    }
    speakable = format_speakable_tool_result("get_run_overview", payload)
    assert "Win rate is grounded from claims." in speakable
    assert "Historical sample is diagnostic only" in speakable
    assert "42" not in speakable
    assert "sneaks" not in speakable
    assert _ungrounded_number_tokens(speakable, allowed=set()) == []


def test_stale_negative_cue_after_assistant_turn_is_neutral(tmp_path: Path):
    """Prior specialist ask must not false-veto after the assistant already replied."""
    service, handle, thesis, _run, _digest = _results_session(tmp_path, packet=_kpi_packet())
    _append_user(
        service,
        thesis.thesis_id,
        handle.session_id,
        "summarize the walk-forward / validation results",
    )
    # First call during the user turn still vetoes.
    veto = execute_voice_tool("get_run_overview", {}, session=handle)["result"]
    assert veto["overview_intent"] is None
    assert veto.get("remediation")
    # After assistant reply, same stale user text must not keep vetoing.
    _append_assistant(
        service,
        thesis.thesis_id,
        handle.session_id,
        "I cannot answer that specialist ask from overview alone.",
    )
    out = execute_voice_tool("get_run_overview", {}, session=handle)
    result = out["result"]
    assert result["overview_intent"] == OVERVIEW_INTENT_RUN
    assert result["kpi_claims"]
    assert not result.get("remediation")
    assert result["claims"] == result["kpi_claims"]


def test_dx2_realtime_results_instructions_contain_frozen_needles(tmp_path: Path):
    """X8: realtime/results honesty instructions include §4.3 needles."""
    text = build_honesty_instructions(
        channel="results_qa",
        mode="realtime",
        run_id="run_" + "e" * 32,
        expected_hash="f" * 64,
    )
    for needle in _DX2_NEEDLES:
        assert needle in text
    # Session create path also validates these needles for realtime results.
    service, handle, thesis, _run, digest = _results_session(tmp_path, packet=_kpi_packet())
    record = service.repository.get_voice_session(thesis.thesis_id, handle.session_id)
    assert record.mode == "realtime"
    created_instructions = service.build_honesty_instructions(record)
    for needle in _DX2_NEEDLES:
        assert needle in created_instructions


def test_dx2_needles_absent_from_ptt_and_help():
    ptt = build_honesty_instructions(
        channel="results_qa",
        mode="push_to_talk",
        run_id="run_" + "1" * 32,
        expected_hash="2" * 64,
    )
    help_rt = build_honesty_instructions(channel="product_help", mode="realtime")
    help_ptt = build_honesty_instructions(channel="product_help", mode="push_to_talk")
    for text in (ptt, help_rt, help_ptt):
        assert _DX2_NEEDLES[0] not in text
        assert "kpi_claims" not in text
        assert "never invent results.trade_count" not in text


def test_dx2_needles_reach_realtime_session_update_payload():
    """Sidecar session.update must carry the same honesty needles (no parallel builder)."""
    instructions = build_honesty_instructions(
        channel="results_qa",
        mode="realtime",
        run_id="run_" + "a" * 32,
        expected_hash="b" * 64,
    )
    payload = build_realtime_session_update(instructions=instructions, voice="eve")
    assert payload["type"] == "session.update"
    embedded = payload["session"]["instructions"]
    for needle in _DX2_NEEDLES:
        assert needle in embedded
    # Contiguous block (joined with newlines, no reordering/gaps).
    assert "\n".join(_DX2_NEEDLES) in embedded
