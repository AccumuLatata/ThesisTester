"""RS1 StudySpec schema — fail-closed validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    closed_level_token_set,
    load_study_spec,
    normalize_study_spec,
    validate_study_spec,
)


def _minimal_study(**overrides):
    study = {
        "name": "pdPOC_mini",
        "dataset": {"path": "data/es_1m.csv", "instrument": "ES"},
        "levels": {
            "sma_lengths": [50, 200],
            "ema_lengths": [21],
            "sma_timeframes": ["1min", "5min", "30min"],
            "ema_timeframes": ["1min", "5min", "30min"],
        },
        "constants": {
            "direction": "both",
            "tolerance_ticks": 0,
            "min_confluences": 2,
            "max_confluences": 2,
            "min_valid_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger_params": {},
            "backtest": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "exposure_policy": "single_position",
            },
            "grid": {"enabled": False},
            "validation": {"enabled": False},
            "walk_forward": {"enabled": False},
        },
        "factors": {
            "core_level": ["pdPOC"],
            "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
            "confluence_mode": ["global_cluster", "anchor_rules"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [{"enabled": False}],
        },
        "mode_rules": {
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            },
            "anchor_rules": {
                "selected_levels": [],
                "anchor_level": "${core_level}",
                "confluence_rules": {"from_partners": "required"},
            },
        },
        "report": {
            "primary_metric": "expectancy_r",
            "secondary_metrics": ["profit_factor", "trade_count"],
            "min_trades": 30,
            "group_by": ["partner_levels", "confluence_mode"],
            "otf_baseline": {"enabled": False},
            "multiple_testing": "warn",
        },
        "stage": {
            "mode": "filter",
            "include": {"trigger": ["touch"], "trigger_timeframe": ["base"]},
        },
    }
    study.update(overrides)
    return {"schema_version": STUDY_SCHEMA_VERSION, "study": study}


def test_minimal_study_normalizes_stably():
    raw = _minimal_study()
    # omit optional defaults that normalize fills
    del raw["study"]["report"]
    del raw["study"]["stage"]
    first = normalize_study_spec(raw)
    second = normalize_study_spec(first)
    validated = validate_study_spec(second)
    assert validated["schema_version"] == 1
    assert validated["study"]["name"] == "pdPOC_mini"
    assert validated["study"]["workers"] == 1
    assert validated["study"]["confirm_above_runs"] == 200
    assert validated["study"]["output_dir"] == "results/studies/pdPOC_mini"
    assert validated["study"]["report"]["primary_metric"] == "expectancy_r"
    # stable re-normalize
    again = validate_study_spec(normalize_study_spec(validated))
    assert again["study"]["output_dir"] == validated["study"]["output_dir"]
    assert again["study"]["report"]["multiple_testing"] == "warn"


def test_load_study_spec_from_yaml(tmp_path: Path):
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(_minimal_study()), encoding="utf-8")
    loaded = load_study_spec(path)
    assert loaded["study"]["factors"]["core_level"] == ["pdPOC"]


def test_unknown_top_level_key_fails_closed():
    raw = _minimal_study()
    raw["extra"] = True
    with pytest.raises(StudySpecError, match="Unknown StudySpec keys"):
        validate_study_spec(normalize_study_spec(raw))


def test_unknown_factor_axis_fails_closed():
    raw = _minimal_study()
    raw["study"]["factors"]["sl_ticks"] = [8, 12]
    with pytest.raises(StudySpecError, match="Unsupported factor axes"):
        validate_study_spec(normalize_study_spec(raw))


def test_unknown_study_key_fails_closed():
    raw = _minimal_study()
    raw["study"]["bot_personality"] = "aggressive"
    with pytest.raises(StudySpecError, match="Unknown study keys"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_trigger_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger"] = ["teleport"]
    with pytest.raises(StudySpecError, match="factors.trigger"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_trigger_timeframe_30min_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger_timeframe"] = ["30min"]
    with pytest.raises(StudySpecError, match="30min is not a valid trigger timeframe"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_otf_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["otf"] = [{"enabled": True, "timeframes": ["1h"]}]
    with pytest.raises(StudySpecError, match="factors.otf"):
        validate_study_spec(normalize_study_spec(raw))


def test_unknown_partner_token_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["partner_levels"] = [["NOT_A_REAL_LEVEL"]]
    with pytest.raises(StudySpecError, match="Unknown partner level token"):
        validate_study_spec(normalize_study_spec(raw))


def test_direction_in_constants_allowed():
    raw = _minimal_study()
    raw["study"]["constants"]["direction"] = "long"
    validate_study_spec(normalize_study_spec(raw))


def test_direction_factor_axis_allowed():
    raw = _minimal_study()
    raw["study"]["factors"]["direction"] = ["long", "short"]
    # explicit_cells / filter group_by may reference it; keep stage filter axes valid
    validate_study_spec(normalize_study_spec(raw))


def test_grid_without_enabled_fails():
    raw = _minimal_study()
    raw["study"]["constants"]["grid"] = {}
    with pytest.raises(StudySpecError, match="explicit enabled"):
        validate_study_spec(normalize_study_spec(raw))


def test_validation_without_enabled_fails():
    raw = _minimal_study()
    raw["study"]["constants"]["validation"] = {"n_bootstrap": 100}
    with pytest.raises(StudySpecError, match="study.constants.validation"):
        validate_study_spec(normalize_study_spec(raw))


def test_stage_filter_requires_include():
    raw = _minimal_study()
    raw["study"]["stage"] = {"mode": "filter"}
    with pytest.raises(StudySpecError, match="requires stage.include"):
        validate_study_spec(normalize_study_spec(raw))


def test_stage_filter_include_must_subset_factors():
    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "filter",
        "include": {"not_a_factor": ["x"]},
    }
    with pytest.raises(StudySpecError, match="subset of factors"):
        validate_study_spec(normalize_study_spec(raw))


def test_stage_explicit_cells_requires_all_factor_keys():
    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "explicit_cells",
        "cells": [
            {
                "core_level": "pdPOC",
                "partner_levels": ["SMA_50_1min"],
                # missing remaining axes
            }
        ],
    }
    with pytest.raises(StudySpecError, match="missing factor keys"):
        validate_study_spec(normalize_study_spec(raw))

    cell = {
        "core_level": "pdPOC",
        "partner_levels": ["SMA_50_1min"],
        "confluence_mode": "global_cluster",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "otf": {"enabled": False},
    }
    raw["study"]["stage"] = {"mode": "explicit_cells", "cells": [cell]}
    validate_study_spec(normalize_study_spec(raw))


def test_stage_explicit_cells_rejects_include():
    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "explicit_cells",
        "include": {"trigger": ["touch"]},
        "cells": [],
    }
    with pytest.raises(StudySpecError, match="must not include stage.include"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_study_name_rejected():
    raw = _minimal_study()
    raw["study"]["name"] = "bad name.with.dots"
    with pytest.raises(StudySpecError, match="study.name must match"):
        validate_study_spec(normalize_study_spec(raw))


def test_confirm_above_runs_must_be_positive():
    raw = _minimal_study()
    raw["study"]["confirm_above_runs"] = 0
    with pytest.raises(StudySpecError, match="confirm_above_runs"):
        validate_study_spec(normalize_study_spec(raw))


def test_anchor_mode_rules_require_empty_selected_levels():
    raw = _minimal_study()
    raw["study"]["mode_rules"]["anchor_rules"]["selected_levels"] = ["pdPOC"]
    with pytest.raises(StudySpecError, match="selected_levels must be"):
        validate_study_spec(normalize_study_spec(raw))


def test_closed_level_token_set_includes_ma_columns():
    tokens = closed_level_token_set(
        {
            "sma_lengths": [50],
            "ema_lengths": [21],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["5min"],
        }
    )
    assert "pdPOC" in tokens
    assert "SMA_50_1min" in tokens
    assert "EMA_21_5min" in tokens
    assert "SMA_50_5min" not in tokens


def test_closed_level_token_set_empty_timeframes_do_not_invent_bare_ma():
    tokens = closed_level_token_set(
        {
            "sma_lengths": [50],
            "ema_lengths": [21],
            "sma_timeframes": [],
            "ema_timeframes": [],
        }
    )
    assert "SMA_50" not in tokens
    assert "EMA_21" not in tokens
    assert not any(t.startswith("SMA_") for t in tokens)
    assert not any(t.startswith("EMA_") for t in tokens)


def test_closed_level_token_set_gates_pivots_and_prev30m_on_flags():
    disabled = closed_level_token_set({"pivots_enabled": False, "prev30m_vwap_enabled": False})
    assert "Pivot_1min_High" not in disabled
    assert "prev30mVWAP" not in disabled

    enabled = closed_level_token_set(
        {
            "pivots_enabled": True,
            "pivot_timeframes": ["1min"],
            "prev30m_vwap_enabled": True,
            "prev30m_vwap_validity_periods": 1,
        }
    )
    assert "Pivot_1min_High" in enabled
    assert "prev30mVWAP" in enabled


def test_schema_version_rejected():
    raw = _minimal_study()
    raw["schema_version"] = 99
    with pytest.raises(StudySpecError, match="Unsupported StudySpec schema_version"):
        validate_study_spec(normalize_study_spec(raw))


def test_dataset_instrument_required():
    raw = _minimal_study()
    del raw["study"]["dataset"]["instrument"]
    with pytest.raises(StudySpecError, match="dataset.instrument is required"):
        validate_study_spec(normalize_study_spec(raw))


def test_otf_canonical_duplicates_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["otf"] = [
        {
            "enabled": True,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
        },
        {
            "enabled": True,
            "timeframes": ["5min"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
        },
    ]
    with pytest.raises(StudySpecError, match="duplicates a prior OTF config"):
        validate_study_spec(normalize_study_spec(raw))


def test_duplicate_partner_tokens_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["partner_levels"] = [["ONH", "ONH"]]
    with pytest.raises(StudySpecError, match="Duplicate partner level token"):
        validate_study_spec(normalize_study_spec(raw))


def test_schema_version_rejects_bool_and_float():
    raw = _minimal_study()
    raw["schema_version"] = True
    with pytest.raises(StudySpecError, match="Unsupported StudySpec schema_version"):
        validate_study_spec(normalize_study_spec(raw))
    raw["schema_version"] = 1.0
    with pytest.raises(StudySpecError, match="Unsupported StudySpec schema_version"):
        validate_study_spec(normalize_study_spec(raw))


def test_levels_list_fields_reject_strings_and_bad_lengths():
    raw = _minimal_study()
    raw["study"]["levels"]["sma_lengths"] = "50"
    with pytest.raises(StudySpecError, match="sma_lengths must be a list"):
        validate_study_spec(normalize_study_spec(raw))

    raw = _minimal_study()
    raw["study"]["levels"]["sma_lengths"] = ["nope"]
    with pytest.raises(StudySpecError, match="sma_lengths\\[0\\] must be an integer"):
        validate_study_spec(normalize_study_spec(raw))

    raw = _minimal_study()
    raw["study"]["levels"]["sma_lengths"] = [True]
    with pytest.raises(StudySpecError, match="sma_lengths\\[0\\] must be an integer"):
        validate_study_spec(normalize_study_spec(raw))

    raw = _minimal_study()
    raw["study"]["levels"]["vwap_windows"] = "30min"
    with pytest.raises(StudySpecError, match="vwap_windows must be a list"):
        validate_study_spec(normalize_study_spec(raw))

    with pytest.raises(StudySpecError, match="sma_lengths must be a list"):
        closed_level_token_set({"sma_lengths": "50"})


def test_group_by_must_be_study_factor_axis():
    raw = _minimal_study()
    raw["study"]["report"]["group_by"] = ["direction"]
    with pytest.raises(StudySpecError, match="group_by\\[0\\] must be a factor axis"):
        validate_study_spec(normalize_study_spec(raw))


def test_stage_include_values_must_be_in_factor_domain():
    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "filter",
        "include": {"trigger": ["3c"]},  # factors.trigger is [touch] only
    }
    with pytest.raises(StudySpecError, match="not one of factors.trigger"):
        validate_study_spec(normalize_study_spec(raw))

    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "filter",
        "include": {"trigger_timeframe": ["30min"]},
    }
    with pytest.raises(StudySpecError, match="not one of factors.trigger_timeframe"):
        validate_study_spec(normalize_study_spec(raw))


def test_stage_explicit_cells_reject_out_of_domain_values():
    raw = _minimal_study()
    cell = {
        "core_level": "pdPOC",
        "partner_levels": ["SMA_50_1min"],
        "confluence_mode": "global_cluster",
        "trigger": "teleport",
        "trigger_timeframe": "base",
        "otf": {"enabled": False},
    }
    raw["study"]["stage"] = {"mode": "explicit_cells", "cells": [cell]}
    with pytest.raises(StudySpecError, match="not one of factors.trigger"):
        validate_study_spec(normalize_study_spec(raw))

    cell = {
        "core_level": "ONH",  # not in factors.core_level
        "partner_levels": ["SMA_50_1min"],
        "confluence_mode": "global_cluster",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "otf": {"enabled": False},
    }
    raw["study"]["stage"] = {"mode": "explicit_cells", "cells": [cell]}
    with pytest.raises(StudySpecError, match="not one of factors.core_level"):
        validate_study_spec(normalize_study_spec(raw))


def test_global_cluster_selected_levels_must_be_nonempty_list():
    raw = _minimal_study()
    raw["study"]["mode_rules"]["global_cluster"]["selected_levels"] = []
    with pytest.raises(StudySpecError, match="selected_levels must be a non-empty list"):
        validate_study_spec(normalize_study_spec(raw))


def test_mode_rules_without_confluence_mode_factor_rejected():
    raw = _minimal_study()
    del raw["study"]["factors"]["confluence_mode"]
    with pytest.raises(StudySpecError, match="mode_rules requires factors.confluence_mode"):
        validate_study_spec(normalize_study_spec(raw))


def test_anchor_level_must_be_nonempty_string():
    raw = _minimal_study()
    raw["study"]["mode_rules"]["anchor_rules"]["anchor_level"] = ""
    with pytest.raises(StudySpecError, match="anchor_level must be a non-empty string"):
        validate_study_spec(normalize_study_spec(raw))
