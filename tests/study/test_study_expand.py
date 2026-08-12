"""RS2 StudySpec → R18 experiment expansion tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from thesistester.api import validate_run_spec
from thesistester.cli import _RUN_NAME_RE
from thesistester.study.expand import (
    expand_study,
    expand_study_to_directory,
    write_expansion_artifacts,
)
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "study"
GOLDEN_DIR = FIXTURES / "golden"


def _plan_example_study(**overrides):
    """Literal §6.1 factor lists → 800 full / 40 stage-filtered cells."""
    study = {
        "name": "pdPOC_expand",
        "dataset": {
            "path": "data/es_1m.csv",
            "instrument": "ES",
            "source_timezone": "America/New_York",
        },
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
            "partner_levels": [
                ["SMA_50_1min"],
                ["SMA_50_5min"],
                ["SMA_200_30min"],
                ["EMA_21_5min"],
            ],
            "confluence_mode": ["global_cluster", "anchor_rules"],
            "trigger": ["touch", "reject", "break", "reclaim", "3c"],
            "trigger_timeframe": ["base", "1min", "5min", "15min"],
            "otf": [
                {"enabled": False},
                {
                    "enabled": True,
                    "timeframes": ["5m"],
                    "alignment_mode": "all",
                    "minimum_consecutive_bars": 3,
                },
                {
                    "enabled": True,
                    "timeframes": ["15m"],
                    "alignment_mode": "all",
                    "minimum_consecutive_bars": 3,
                },
                {
                    "enabled": True,
                    "timeframes": ["30m"],
                    "alignment_mode": "all",
                    "minimum_consecutive_bars": 3,
                },
                {
                    "enabled": True,
                    "timeframes": ["5m", "15m", "30m"],
                    "alignment_mode": "all",
                    "minimum_consecutive_bars": 3,
                },
            ],
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
            "group_by": ["partner_levels", "confluence_mode", "otf"],
            "otf_baseline": {"enabled": False},
            "multiple_testing": "warn",
        },
    }
    study.update(overrides)
    return {"schema_version": STUDY_SCHEMA_VERSION, "study": study}


def _base_study(**overrides):
    return _plan_example_study(**overrides)


def test_golden_expansion_byte_stable(tmp_path: Path):
    raw = yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    normalized = validate_study_spec(normalize_study_spec(raw))
    expansion = expand_study(normalized)
    write_expansion_artifacts(
        tmp_path,
        normalized_spec=normalized,
        expansion=expansion,
    )
    for name in ("study.spec.yaml", "study.expansion.json", "experiment.yaml"):
        actual = (tmp_path / name).read_text(encoding="utf-8")
        expected = (GOLDEN_DIR / name).read_text(encoding="utf-8")
        assert actual == expected, f"Golden mismatch for {name}"


def test_every_expanded_run_passes_validate_run_spec():
    raw = yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    expansion = expand_study(raw)
    assert expansion.run_count == 8
    for run in expansion.experiment["runs"]:
        validate_run_spec(run)


def test_global_and_anchor_emission_rules():
    raw = yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    expansion = expand_study(raw)
    globals_ = [
        r for r in expansion.experiment["runs"] if r["setup"]["confluence_mode"] == "global_cluster"
    ]
    anchors = [
        r for r in expansion.experiment["runs"] if r["setup"]["confluence_mode"] == "anchor_rules"
    ]
    assert globals_ and anchors
    for run in globals_:
        setup = run["setup"]
        assert setup["selected_levels"][0] == "pdPOC"
        assert len(setup["selected_levels"]) >= 2
        assert setup["min_confluences"] == setup["max_confluences"] == len(setup["selected_levels"])
        assert len(setup["selected_levels"]) <= 5
    for run in anchors:
        setup = run["setup"]
        assert setup["selected_levels"] == []
        assert setup["anchor_level"] == "pdPOC"
        assert setup["confluence_rules"]
        assert all(rule.get("required") is True for rule in setup["confluence_rules"])


def test_run_names_unique_and_match_cli_regex():
    raw = yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    expansion = expand_study(raw)
    names = [run["name"] for run in expansion.experiment["runs"]]
    assert len(names) == len(set(names))
    for name in names:
        assert _RUN_NAME_RE.fullmatch(name)
        assert name in expansion.factor_map


def test_stage_filter_reduces_800_to_40():
    raw = _base_study(
        stage={
            "mode": "filter",
            "include": {"trigger": ["touch"], "trigger_timeframe": ["base"]},
        }
    )
    full = expand_study(_base_study())
    staged = expand_study(raw)
    assert full.run_count == 800
    assert staged.run_count == 40
    for factors in staged.factor_map.values():
        assert factors["trigger"] == "touch"
        assert factors["trigger_timeframe"] == "base"


def test_explicit_cells_no_cartesian_leakage():
    raw = _base_study(
        factors={
            "core_level": ["pdPOC"],
            "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
            "confluence_mode": ["global_cluster", "anchor_rules"],
            "trigger": ["touch", "3c"],
            "trigger_timeframe": ["base", "5min"],
            "otf": [{"enabled": False}],
        },
        stage={
            "mode": "explicit_cells",
            "cells": [
                {
                    "core_level": "pdPOC",
                    "partner_levels": ["SMA_50_1min"],
                    "confluence_mode": "global_cluster",
                    "trigger": "touch",
                    "trigger_timeframe": "base",
                    "otf": {"enabled": False},
                },
                {
                    "core_level": "pdPOC",
                    "partner_levels": ["EMA_21_5min"],
                    "confluence_mode": "anchor_rules",
                    "trigger": "3c",
                    "trigger_timeframe": "5min",
                    "otf": {"enabled": False},
                },
            ],
        },
    )
    expansion = expand_study(raw)
    assert expansion.run_count == 2
    modes = {f["confluence_mode"] for f in expansion.factor_map.values()}
    triggers = {f["trigger"] for f in expansion.factor_map.values()}
    assert modes == {"global_cluster", "anchor_rules"}
    assert triggers == {"touch", "3c"}
    # Cartesian of factors would be 2*2*2*2*1 = 16 without explicit_cells.
    assert expansion.run_count != 16


def test_enabled_false_emitted_not_bare_empty():
    expansion = expand_study(
        yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    )
    for run in expansion.experiment["runs"]:
        assert run["grid"] == {"enabled": False}
        assert run["validation"] == {"enabled": False}
        assert run["walk_forward"] == {"enabled": False}


def test_otf_canonicalized_in_factor_map():
    raw = _base_study(
        factors={
            "core_level": ["pdPOC"],
            "partner_levels": [["SMA_50_1min"]],
            "confluence_mode": ["global_cluster"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [
                {
                    "enabled": True,
                    "timeframes": ["5min"],  # alias
                    "alignment_mode": "all",
                    "minimum_consecutive_bars": 3,
                }
            ],
        }
    )
    expansion = expand_study(raw)
    assert expansion.run_count == 1
    otf = next(iter(expansion.factor_map.values()))["otf"]
    assert otf["timeframes"] == ["5m"]
    setup_otf = expansion.experiment["runs"][0]["setup"]["otf_filter"]
    assert setup_otf["timeframes"] == ["5m"]


def test_expand_study_to_directory_writes_artifacts(tmp_path: Path):
    raw = yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    expansion = expand_study_to_directory(raw, tmp_path)
    assert expansion.run_count == 8
    assert (tmp_path / "study.spec.yaml").is_file()
    assert (tmp_path / "study.expansion.json").is_file()
    assert (tmp_path / "experiment.yaml").is_file()
    payload = json.loads((tmp_path / "study.expansion.json").read_text(encoding="utf-8"))
    assert payload["run_count"] == 8
    assert payload["study_identity_hash"] == expansion.study_identity_hash


def test_setup_injects_name_instrument_description():
    expansion = expand_study(
        yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    )
    for run in expansion.experiment["runs"]:
        setup = run["setup"]
        assert setup["name"] == run["name"]
        assert setup["instrument"] == "ES"
        assert setup["description"] == "RS2 golden expansion fixture"


def test_otf_alias_duplicates_fail_closed():
    raw = _base_study(
        factors={
            "core_level": ["pdPOC"],
            "partner_levels": [["SMA_50_1min"]],
            "confluence_mode": ["global_cluster"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [
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
            ],
        },
        mode_rules={
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            }
        },
    )
    raw["study"]["report"]["group_by"] = ["otf"]
    with pytest.raises(StudySpecError, match="duplicates a prior OTF config"):
        expand_study(raw)


def test_duplicate_or_core_overlapping_partners_fail_closed():
    raw = _base_study(
        factors={
            "core_level": ["pdPOC"],
            "partner_levels": [["ONH", "ONH"]],
            "confluence_mode": ["global_cluster"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [{"enabled": False}],
        },
        mode_rules={
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            }
        },
    )
    raw["study"]["report"]["group_by"] = ["partner_levels"]
    with pytest.raises(StudySpecError, match="Duplicate partner level token"):
        expand_study(raw)

    raw = _base_study(
        factors={
            "core_level": ["pdPOC"],
            "partner_levels": [["pdPOC"]],
            "confluence_mode": ["global_cluster"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [{"enabled": False}],
        },
        mode_rules={
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            }
        },
    )
    raw["study"]["report"]["group_by"] = ["partner_levels"]
    with pytest.raises(StudySpecError, match="must not include core_level"):
        expand_study(raw)


def test_missing_required_cell_axes_fail_closed():
    raw = _base_study()
    del raw["study"]["factors"]["confluence_mode"]
    del raw["study"]["mode_rules"]
    raw["study"]["report"]["group_by"] = ["partner_levels", "otf"]
    with pytest.raises(StudySpecError, match="missing 'confluence_mode'"):
        expand_study(raw)


def test_missing_backtest_fails_closed():
    raw = _base_study()
    del raw["study"]["constants"]["backtest"]
    with pytest.raises(StudySpecError, match="backtest is required for expansion"):
        expand_study(raw)


def test_anchor_emits_placeholder_min_max_confluences():
    expansion = expand_study(
        yaml.safe_load((FIXTURES / "golden_study.yaml").read_text(encoding="utf-8"))
    )
    for run in expansion.experiment["runs"]:
        if run["setup"]["confluence_mode"] == "anchor_rules":
            assert run["setup"]["min_confluences"] == 1
            assert run["setup"]["max_confluences"] == 1


def test_run_name_respects_max_length():
    from thesistester.study.naming import _MAX_RUN_NAME_LEN, build_run_name

    long_name = "A" * 100
    name = build_run_name(
        long_name,
        index=0,
        factors={
            "confluence_mode": "global_cluster",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "partner_levels": ["SMA_50_1min"],
            "otf": {"enabled": False},
        },
    )
    assert len(name) <= _MAX_RUN_NAME_LEN
    assert _RUN_NAME_RE.fullmatch(name)
