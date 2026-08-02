import pytest

from thesistester.assistant import (
    StructuredThesisChoices,
    compile_canonical_run_spec,
    compile_run_spec,
    compile_thesis,
)


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


def test_run_spec_compiler_requires_explicit_execution_sections(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "dataset": {"path": "bars.csv"},
        "setup": {"instrument": "ES"},
        "backtest": {"stop_loss_ticks": 8},
    }
    compiled = compile_run_spec(name="Explicit", choices=choices)

    assert compiled["name"] == "Explicit"
    assert compiled["dataset"] is not choices["dataset"]
    with pytest.raises(ValueError, match="backtest"):
        compile_run_spec(name="Missing", choices={"dataset": {}, "setup": {}})


def test_canonical_compiler_rejects_implicit_execution_assumptions(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "levels": {},
        "setup": {"trigger": "touch", "tolerance_ticks": 0, "selected_levels": ["dVWAP_RTH"]},
        "backtest": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
        },
        "validation": {"random_state": 42},
    }
    assert compile_canonical_run_spec(name="Explicit", choices=choices)["name"] == "Explicit"

    choices["backtest"].pop("slippage_ticks")
    with pytest.raises(ValueError, match="slippage_ticks"):
        compile_canonical_run_spec(name="Implicit", choices=choices)


def test_canonical_compiler_normalizes_omitted_levels_to_empty_mapping(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "setup": {"trigger": "touch", "tolerance_ticks": 0, "selected_levels": ["dVWAP_RTH"]},
        "backtest": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
        },
    }

    structured = StructuredThesisChoices.from_mapping(choices)
    compiled = compile_canonical_run_spec(name="No levels", choices=choices)

    assert structured.levels == {}
    assert compiled["levels"] == {}


def test_structured_choices_rejects_non_mapping_levels():
    with pytest.raises(ValueError, match="levels"):
        StructuredThesisChoices.from_mapping(
            {
                "dataset": {},
                "levels": [],
                "setup": {},
                "backtest": {},
            }
        )


def test_structured_choices_have_stable_canonical_serialization():
    choices = StructuredThesisChoices(
        dataset={"instrument": "ES", "path": "bars.csv"},
        levels={},
        setup={},
        backtest={},
    )
    assert choices.canonical_json() == choices.canonical_json()
