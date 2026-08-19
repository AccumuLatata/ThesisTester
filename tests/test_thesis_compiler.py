import pytest

from thesistester.assistant import (
    StructuredThesisChoices,
    compile_canonical_run_spec,
    compile_run_spec,
    compile_thesis,
    map_persisted_confirmed_run_spec,
    map_thesis_choices_to_run_spec,
    normalize_setup_level_selection,
    normalize_walk_forward_controls,
)


@pytest.mark.parametrize("token", ["wVWAP", "mVWAP"])
def test_compiler_marks_htf_vwap_prompt_with_existing_session_vwap_assumption(token):
    unresolved = "Enable developing session VWAPs for the dVWAP thesis."
    draft = compile_thesis(f"Fade {token} in the New York session.")
    assert any(item == unresolved for item in draft.unresolved_assumptions)
    assert any("dVWAP" in item for item in draft.unresolved_assumptions)

    enabled = compile_thesis(
        f"Fade {token} in the New York session.",
        choices={"levels": {"session_vwap_enabled": True}},
    )
    assert unresolved not in enabled.unresolved_assumptions


def test_compiler_marks_ambiguous_trading_language_for_clarification():
    draft = compile_thesis("Uptrend retraces to dVWAP with a 30m SMA confluence in B session.")
    assert not draft.ready_for_confirmation
    assert any("dataset" in item.lower() for item in draft.unresolved_assumptions)
    assert any("dVWAP" in item for item in draft.unresolved_assumptions)


def test_compiler_is_deterministic_for_complete_explicit_choices():
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "levels": {"session_vwap_enabled": True, "sma_lengths": [50]},
        "setup": {
            "trigger": "touch",
            "tolerance_ticks": 2,
        },
        "backtest": {"stop_loss_ticks": 8, "take_profit_ticks": 16},
    }
    first = compile_thesis("dVWAP SMA stop target", choices=choices)
    second = compile_thesis("dVWAP SMA stop target", choices=choices)
    assert first == second
    assert first.ready_for_confirmation


def test_compiler_does_not_stage_narrative_llm_hints_as_executable_choices():
    draft = compile_thesis(
        "Test a touch entry.",
        choices={
            "trend_rule": "positive 30-minute SMA slope",
            "trigger": "touch",
            "dataset": {"path": "bars.csv", "instrument": "ES"},
        },
    )

    assert draft.normalized_run_spec == {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
    }
    assert not draft.ready_for_confirmation


def test_compiler_ignores_legacy_flat_keys_for_structured_clarifications():
    draft = compile_thesis(
        "Uptrend retraces to dVWAP with a 30m SMA confluence.",
        choices={
            "session_vwap_anchor": "RTH",
            "confluence_tolerance_ticks": 2,
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "setup": {"trigger": "touch"},
            "backtest": {"intrabar_model": "sl_first"},
        },
    )

    assert draft.normalized_run_spec == {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "setup": {"trigger": "touch"},
        "backtest": {"intrabar_model": "sl_first"},
    }
    assert any("dVWAP" in item for item in draft.unresolved_assumptions)
    assert any("SMA confluence tolerance" in item for item in draft.unresolved_assumptions)


def test_normalize_setup_level_selection_rejects_empty_levels():
    with pytest.raises(ValueError, match="at least one level"):
        normalize_setup_level_selection("", previous_min=1, previous_max=1)
    with pytest.raises(ValueError, match="at least one level"):
        normalize_setup_level_selection([], previous_min=1, previous_max=1)


def test_normalize_setup_level_selection_clamps_to_provided_levels():
    levels, min_confluences, max_confluences = normalize_setup_level_selection(
        "dVWAP_RTH, SMA_50_30min",
        previous_min=3,
        previous_max=5,
    )

    assert levels == ["dVWAP_RTH", "SMA_50_30min"]
    assert min_confluences == 2
    assert max_confluences == 2


def test_normalize_walk_forward_controls_requires_modes_when_enabled():
    assert normalize_walk_forward_controls(enabled=False) == {"enabled": False}

    enabled = normalize_walk_forward_controls(
        enabled=True,
        train_sessions=20,
        test_sessions=5,
        step_sessions=5,
        window_mode="anchored",
        overlap_policy="first",
    )

    assert enabled == {
        "enabled": True,
        "fold_mode": "sessions",
        "window_mode": "anchored",
        "overlap_policy": "first",
        "otf_history_policy": "fold_local",
        "train_sessions": 20,
        "test_sessions": 5,
        "step_sessions": 5,
    }
    bars = normalize_walk_forward_controls(
        enabled=True,
        fold_mode="bars",
        train_bars=100,
        test_bars=20,
        step_bars=20,
        ranking_metric="expectancy_r",
        min_train_trades=5,
        stop_loss_ticks_values=[8],
        take_profit_ticks_values=[16],
    )
    assert bars["train_bars"] == 100
    assert bars["ranking_metric"] == "expectancy_r"
    assert bars["stop_loss_ticks_values"] == [8]
    assert bars["otf_history_policy"] == "fold_local"
    causal = normalize_walk_forward_controls(
        enabled=True,
        fold_mode="bars",
        train_bars=100,
        test_bars=20,
        step_bars=20,
        otf_history_policy="causal_prefix",
    )
    assert causal["otf_history_policy"] == "causal_prefix"
    # Whitespace handling must match walk_forward.normalize_otf_history_policy.
    padded = normalize_walk_forward_controls(
        enabled=True,
        fold_mode="bars",
        train_bars=100,
        test_bars=20,
        step_bars=20,
        otf_history_policy=" causal_prefix ",
    )
    assert padded["otf_history_policy"] == "causal_prefix"
    with pytest.raises(ValueError, match="window_mode"):
        normalize_walk_forward_controls(enabled=True, window_mode="diagonal")
    with pytest.raises(ValueError, match="otf_history_policy"):
        normalize_walk_forward_controls(enabled=True, otf_history_policy="any")


def test_enabled_walk_forward_controls_compile_canonically():
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "setup": {
            "name": "Enabled walk-forward",
            "description": "",
            "instrument": "ES",
            "selected_levels": ["dVWAP_RTH"],
            "trigger": "touch",
            "tolerance_ticks": 0,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "direction": "both",
        },
        "backtest": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "walk_forward": normalize_walk_forward_controls(
            enabled=True,
            train_sessions=20,
            test_sessions=5,
            step_sessions=5,
            window_mode="rolling",
            overlap_policy="reject",
        ),
    }

    compiled = map_thesis_choices_to_run_spec(name="Enabled walk-forward", choices=choices)

    assert compiled["walk_forward"]["window_mode"] == "rolling"
    assert compiled["walk_forward"]["overlap_policy"] == "reject"


@pytest.mark.parametrize("empty_section", ("dataset", "setup", "backtest"))
def test_compiler_requires_non_empty_required_choice_sections(monkeypatch, empty_section):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "dataset": {"instrument": "ES"},
        "setup": {"trigger": "touch"},
        "backtest": {"intrabar_model": "sl_first"},
    }
    choices[empty_section] = {}

    draft = compile_thesis("Explicit thesis", choices=choices)

    assert not draft.ready_for_confirmation
    assert draft.unresolved_assumptions
    with pytest.raises(ValueError):
        map_thesis_choices_to_run_spec(name="Explicit thesis", choices=choices)


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
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "validation": {"random_state": 42},
    }
    assert compile_canonical_run_spec(name="Explicit", choices=choices)["name"] == "Explicit"

    choices["backtest"].pop("slippage_ticks")
    with pytest.raises(ValueError, match="slippage_ticks"):
        compile_canonical_run_spec(name="Implicit", choices=choices)


def test_persisted_confirmed_compiler_hydrates_only_legacy_session_defaults(monkeypatch):
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

    with pytest.raises(ValueError, match="flat_by_session_close"):
        map_thesis_choices_to_run_spec(name="Legacy", choices=choices)

    compiled = map_persisted_confirmed_run_spec(name="Legacy", choices=choices)

    assert compiled["backtest"] == {
        **choices["backtest"],
        "flat_by_session_close": False,
        "session_close_time": None,
        "session_timezone": None,
        "no_new_entries_after": None,
    }


def test_canonical_compiler_normalizes_omitted_levels_to_empty_mapping(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "setup": {
            "trigger": "touch",
            "tolerance_ticks": 0,
            "selected_levels": ["dVWAP_RTH"],
        },
        "backtest": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
    }

    structured = StructuredThesisChoices.from_mapping(choices)
    compiled = compile_canonical_run_spec(name="No levels", choices=choices)

    assert structured.levels == {}
    assert compiled["levels"] == {}


def test_canonical_compiler_accepts_minimal_disabled_walk_forward():
    choices = {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "setup": {
            "name": "Disabled walk-forward",
            "description": "",
            "instrument": "ES",
            "selected_levels": ["dVWAP_RTH"],
            "trigger": "touch",
            "tolerance_ticks": 0,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "direction": "both",
        },
        "backtest": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "walk_forward": {"enabled": False},
    }

    compiled = compile_canonical_run_spec(name="Disabled walk-forward", choices=choices)

    assert compiled["walk_forward"] == {"enabled": False}


def test_canonical_compiler_requires_modes_for_enabled_walk_forward(monkeypatch):
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
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "walk_forward": {"enabled": True},
    }

    with pytest.raises(ValueError, match="walk_forward.fold_mode"):
        compile_canonical_run_spec(name="Enabled walk-forward", choices=choices)


@pytest.mark.parametrize(
    ("walk_forward", "message"),
    [
        (
            {
                "enabled": True,
                "fold_mode": "sessions",
                "window_mode": "rolling",
                "overlap_policy": "reject",
            },
            "walk_forward.train_sessions",
        ),
        (
            {
                "enabled": True,
                "fold_mode": "bars",
                "window_mode": "rolling",
                "overlap_policy": "reject",
            },
            "walk_forward.train_bars",
        ),
    ],
)
def test_canonical_compiler_requires_fold_sizes_for_enabled_walk_forward(
    monkeypatch, walk_forward, message
):
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
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "walk_forward": walk_forward,
    }

    with pytest.raises(ValueError, match=message):
        compile_canonical_run_spec(name="Sized walk-forward", choices=choices)


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


def test_dvwap_sma_structured_choices_compile_canonically(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    choices = {
        "name": "Prior thesis title",
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "levels": {
            "session_vwap_enabled": True,
            "sma_lengths": [50],
            "sma_timeframes": ["30min"],
        },
        "setup": {
            "selected_levels": "dVWAP_RTH",
            "trigger": "touch",
            "tolerance_ticks": 2,
        },
        "backtest": {
            "commission_per_side": 2.5,
            "slippage_ticks": 1,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "validation": {"random_state": 7},
    }

    first = map_thesis_choices_to_run_spec(name="dVWAP SMA", choices=choices)
    second = map_thesis_choices_to_run_spec(name="dVWAP SMA", choices=choices)

    assert first == second
    assert first["name"] == "dVWAP SMA"
    assert first["setup"]["instrument"] == "ES"
    assert first["setup"]["selected_levels"] == ["dVWAP_RTH"]


@pytest.mark.parametrize(
    ("choices", "message"),
    [
        ({"trend_rule": "up"}, "non-executable"),
        (
            {
                "dataset": {"path": "bars.csv", "instrument": "ES"},
                "setup": {},
                "backtest": {},
            },
            "setup.trigger",
        ),
    ],
)
def test_structured_mapping_rejects_ghost_and_incomplete_choices(monkeypatch, choices, message):
    monkeypatch.setattr(
        "thesistester.assistant.thesis_compiler.validate_run_spec", lambda spec: None
    )
    with pytest.raises(ValueError, match=message):
        map_thesis_choices_to_run_spec(name="Thesis", choices=choices)
