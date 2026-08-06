"""VA-3 voice tool allowlist + spoken grounding tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesistester.assistant.explainer import EvidenceClaim, build_evidence_packet
from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.voice.grounding import audit_spoken_text, extract_digit_tokens
from thesistester.assistant.voice.session import VoiceSessionService
from thesistester.assistant.voice.tools import (
    VOICE_TOOL_SCHEMAS,
    VoiceToolSession,
    execute_voice_tool,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

_RUN_SPEC = {
    "dataset": {"path": "bars.csv", "instrument": "ES"},
    "levels": {},
    "setup": {
        "name": "voice tools",
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


def _complete_run(
    repository: LocalThesisRepository,
    tmp_path: Path,
    *,
    thesis_id: str | None = None,
    bundle_name: str = "voice.research.zip",
):
    if thesis_id is None:
        thesis = repository.create_thesis(name="voice tools")
        thesis_id = thesis.thesis_id
    else:
        thesis = repository.get_thesis(thesis_id)
    draft = repository.create_spec_version(
        thesis_id,
        normalized_run_spec=_RUN_SPEC,
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    confirmed = repository.confirm_spec_version(
        thesis_id, draft.version, confirmation_note="approved"
    )
    run = repository.start_run(
        thesis_id, spec_version=confirmed.version, request={"request_id": bundle_name}
    )
    bundle_bytes = build_research_bundle({})
    digest = canonical_bundle_hash(bundle_bytes)
    bundle_path = tmp_path / bundle_name
    bundle_path.write_bytes(bundle_bytes)
    completed = repository.complete_run(
        thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={
            "bundle_path": str(bundle_path),
            "canonical_bundle_hash": digest,
        },
    )
    return thesis, completed, digest, bundle_path


def _results_service(tmp_path: Path):
    repository = _repository(tmp_path)
    thesis, run, digest, _bundle = _complete_run(repository, tmp_path)
    tools = AssistantTools(data_roots=(tmp_path,))
    service = VoiceSessionService(repository, tools=tools)
    record = service.create_session(
        thesis.thesis_id,
        run.run_id,
        expected_hash=digest,
        mode="push_to_talk",
        channel="results_qa",
    )
    handle = service.tool_session(thesis.thesis_id, record.session_id)
    return service, handle, thesis, run, digest


def test_voice_tool_schemas_freeze_exact_v1_names():
    names = {item["name"] for item in VOICE_TOOL_SCHEMAS}
    assert names == {
        "get_run_overview",
        "get_metric",
        "list_caveats",
        "compare_two_runs",
    }
    assert all(item["type"] == "function" for item in VOICE_TOOL_SCHEMAS)


def test_unknown_and_injection_tool_names_fail_with_one_audit(tmp_path):
    service, handle, thesis, _run, _digest = _results_service(tmp_path)
    before = service.repository.get_voice_session(thesis.thesis_id, handle.session_id)
    assert before.tool_invocations == ()

    for name in (
        "web_search",
        "execute_confirmed_run",
        "PIPELINE.run_experiment",
        "mcp",
        "save_comparison",
        "x_search",
    ):
        result = execute_voice_tool(name, {}, session=handle)
        assert result["ok"] is False
        assert "denied" in (result["error"] or "").lower() or "Unknown" in (result["error"] or "")

    record = service.repository.get_voice_session(thesis.thesis_id, handle.session_id)
    assert len(record.tool_invocations) == 6
    assert all(not item.ok for item in record.tool_invocations)
    assert {item.tool_name for item in record.tool_invocations} == {
        "web_search",
        "execute_confirmed_run",
        "PIPELINE.run_experiment",
        "mcp",
        "save_comparison",
        "x_search",
    }


def test_get_run_overview_and_list_caveats_from_bound_packet(tmp_path):
    _service, handle, _thesis, run, digest = _results_service(tmp_path)
    overview = execute_voice_tool("get_run_overview", {}, session=handle)
    assert overview["ok"] is True
    assert overview["result"]["run_id"] == run.run_id
    assert overview["result"]["canonical_bundle_hash"] == digest
    assert isinstance(overview["result"]["caveats"], list)
    assert overview["result"]["caveats"]
    assert overview["audit"]["ok"] is True

    caveats = execute_voice_tool("list_caveats", {}, session=handle)
    assert caveats["ok"] is True
    assert caveats["result"]["caveats"]
    assert any(
        "diagnostic" in item.get("message", "").lower() for item in caveats["result"]["caveats"]
    )


def test_get_metric_path_guards(tmp_path):
    _service, handle, _thesis, _run, _digest = _results_service(tmp_path)

    ok = execute_voice_tool("get_metric", {"path": "results.trade_count"}, session=handle)
    assert ok["ok"] is True
    assert ok["result"]["path"] == "results.trade_count"
    assert ok["result"]["value"] == 0
    assert ok["result"]["value_type"] == "integer"

    for bad_path in ("", "..", "results/../secrets", "results..trade_count", "claims.0.value"):
        denied = execute_voice_tool("get_metric", {"path": bad_path}, session=handle)
        assert denied["ok"] is False

    missing = execute_voice_tool(
        "get_metric", {"path": "results.not_a_real_metric"}, session=handle
    )
    assert missing["ok"] is False
    assert "Unknown metric path" in (missing["error"] or "")

    empty_leaf = execute_voice_tool("get_metric", {"path": "results.trade_summary"}, session=handle)
    assert empty_leaf["ok"] is False
    assert "empty" in (empty_leaf["error"] or "").lower()

    root_only = execute_voice_tool("get_metric", {"path": "results"}, session=handle)
    assert root_only["ok"] is False
    assert (
        "scalar" in (root_only["error"] or "").lower()
        or "leaf" in (root_only["error"] or "").lower()
    )


def test_compare_two_runs_is_pure_and_fails_closed_on_hash(tmp_path):
    repository = _repository(tmp_path)
    thesis, left, left_hash, _left_bundle = _complete_run(
        repository, tmp_path, bundle_name="left.research.zip"
    )
    _thesis2, right, right_hash, right_bundle = _complete_run(
        repository,
        tmp_path,
        thesis_id=thesis.thesis_id,
        bundle_name="right.research.zip",
    )
    tools = AssistantTools(data_roots=(tmp_path,))
    service = VoiceSessionService(repository, tools=tools)
    record = service.create_session(
        thesis.thesis_id,
        left.run_id,
        expected_hash=left_hash,
        mode="push_to_talk",
        channel="results_qa",
    )
    handle = VoiceToolSession(
        service=service, thesis_id=thesis.thesis_id, session_id=record.session_id
    )

    compared = execute_voice_tool(
        "compare_two_runs", {"other_run_id": right.run_id}, session=handle
    )
    assert compared["ok"] is True
    assert compared["result"]["persisted"] is False
    assert compared["result"]["left_run_id"] == left.run_id
    assert compared["result"]["right_run_id"] == right.run_id
    assert compared["result"]["right_canonical_bundle_hash"] == right_hash
    assert "comparison" in compared["result"]
    assert repository.list_comparisons(thesis.thesis_id) == ()

    # Replace other bundle with a different valid zip → hash mismatch fail closed.
    replacement = build_research_bundle(
        {
            "data": pd.DataFrame(
                {
                    "timestamp": pd.date_range(
                        "2026-06-01 09:30:00", periods=3, freq="1min", tz="America/New_York"
                    ),
                    "open": [1.0, 2.0, 3.0],
                    "high": [2.0, 3.0, 4.0],
                    "low": [0.5, 1.5, 2.5],
                    "close": [1.5, 2.5, 3.5],
                    "volume": [10, 20, 30],
                }
            )
        }
    )
    assert canonical_bundle_hash(replacement) != right_hash
    right_bundle.write_bytes(replacement)
    failed = execute_voice_tool("compare_two_runs", {"other_run_id": right.run_id}, session=handle)
    assert failed["ok"] is False
    assert "does not match" in (failed["error"] or "").lower()
    assert repository.list_comparisons(thesis.thesis_id) == ()


def test_exactly_one_audit_row_per_invocation_attempt(tmp_path):
    service, handle, thesis, _run, _digest = _results_service(tmp_path)
    execute_voice_tool("get_metric", {"path": "results.trade_count"}, session=handle)
    execute_voice_tool("get_metric", {"path": ""}, session=handle)
    execute_voice_tool("web_search", {"q": "x"}, session=handle)
    record = service.repository.get_voice_session(thesis.thesis_id, handle.session_id)
    assert len(record.tool_invocations) == 3
    assert [item.ok for item in record.tool_invocations] == [True, False, False]


def test_help_session_cannot_read_run_tools(tmp_path):
    repository = _repository(tmp_path)
    thesis = repository.create_thesis(name="help tools")
    service = VoiceSessionService(repository, tools=AssistantTools(data_roots=(tmp_path,)))
    record = service.create_session(
        thesis.thesis_id,
        None,
        mode="push_to_talk",
        channel="product_help",
    )
    handle = service.tool_session(thesis.thesis_id, record.session_id)
    result = execute_voice_tool("list_caveats", {}, session=handle)
    assert result["ok"] is False
    assert "results_qa" in (result["error"] or "")


def test_spoken_grounding_reuses_digit_token_rules():
    packet = build_evidence_packet(
        {},
        provenance={"canonical_bundle_hash": "a" * 64, "bundle_path": "x"},
    )
    claims = (
        EvidenceClaim(text="Win rate is 0.55", path="results.trade_summary.win_rate", value=0.55),
    )
    grounded = audit_spoken_text(
        "Win rate is 0.55 and about 55%.",
        packet=packet,
        claims=claims,
    )
    assert grounded.grounded is True
    assert grounded.uncited_digit_tokens == ()

    ungrounded = audit_spoken_text(
        "Win rate is 0.99 with 12 trades invented.",
        packet=packet,
        claims=claims,
    )
    assert ungrounded.grounded is False
    assert "0.99" in ungrounded.uncited_digit_tokens
    assert ungrounded.remediation

    # Caveat message digits must not launder inventable spoken metrics (C2 parity).
    caveat_launder = audit_spoken_text(
        "Win rate is 30%.",
        packet=packet,
    )
    assert caveat_launder.grounded is False

    # Tool-result hashes/strings must not allowlist spoken digits.
    hash_tool = audit_spoken_text(
        "Hash starts with 05.",
        tool_result={"canonical_bundle_hash": "05" + "a" * 62, "run_id": "run_" + "1" * 32},
    )
    assert hash_tool.grounded is False

    metric_tool = audit_spoken_text(
        "Trade count is 0.",
        tool_result={"path": "results.trade_count", "value": 0, "value_type": "integer"},
    )
    assert metric_tool.grounded is True

    tokens = extract_digit_tokens("SL 8 / TP 16 at 0.25R")
    assert "8" in tokens
    assert "16" in tokens
    assert "0.25" in tokens


def test_bound_packet_rehydrates_across_service_instances(tmp_path):
    repository = _repository(tmp_path)
    thesis, run, digest, _bundle = _complete_run(repository, tmp_path)
    tools = AssistantTools(data_roots=(tmp_path,))
    creator = VoiceSessionService(repository, tools=tools)
    record = creator.create_session(
        thesis.thesis_id,
        run.run_id,
        expected_hash=digest,
        mode="push_to_talk",
        channel="results_qa",
    )
    # New service instance (simulates Streamlit rerun / worker) has empty cache.
    other = VoiceSessionService(repository, tools=tools)
    handle = other.tool_session(thesis.thesis_id, record.session_id)
    result = execute_voice_tool("list_caveats", {}, session=handle)
    assert result["ok"] is True
    assert result["result"]["caveats"]


def test_ended_session_still_persists_deny_audit(tmp_path):
    service, handle, thesis, _run, _digest = _results_service(tmp_path)
    service.end_session(thesis.thesis_id, handle.session_id)
    before = len(
        service.repository.get_voice_session(thesis.thesis_id, handle.session_id).tool_invocations
    )
    denied = execute_voice_tool("web_search", {}, session=handle)
    assert denied["ok"] is False
    after = service.repository.get_voice_session(thesis.thesis_id, handle.session_id)
    assert len(after.tool_invocations) == before + 1
    assert after.tool_invocations[-1].tool_name == "web_search"
    assert after.tool_invocations[-1].ok is False
