import pytest

from thesistester.assistant import compile_thesis


def test_compiler_marks_ambiguous_trading_language_for_clarification():
    draft = compile_thesis("Uptrend retraces to dVWAP with a 30m SMA confluence in B session.")
    assert not draft.ready_for_confirmation
    assert any("trend" in item.lower() for item in draft.unresolved_assumptions)
    assert any("dVWAP" in item for item in draft.unresolved_assumptions)


def test_compiler_is_deterministic_for_complete_explicit_choices():
    choices = {
        "trend_rule": "30m SMA50 slope > 0",
        "trigger": "touch within 2 ticks",
        "session_window": "10:30-11:30 America/New_York",
        "success_criteria": "30 trades and walk-forward review",
        "session_vwap_anchor": "RTH",
        "confluence_tolerance_ticks": 2,
        "selection_protocol": "grid then OOS",
    }
    first = compile_thesis("dVWAP SMA stop target", choices=choices)
    second = compile_thesis("dVWAP SMA stop target", choices=choices)
    assert first == second
    assert first.ready_for_confirmation


def test_compiler_rejects_empty_prompt():
    with pytest.raises(ValueError, match="non-empty"):
        compile_thesis(" ")
