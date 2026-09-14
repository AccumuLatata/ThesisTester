"""RS1 StudySpec schema — fail-closed validation tests."""

from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

import pytest
import yaml

import pandas as pd

from thesistester.assistant.workspace import SESSION_LEVEL_CATALOG
from thesistester.data.derive import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.levels.apoc import APOC_COLUMNS
from thesistester.levels.catalog import (
    APOC_LEVEL_NAMES,
    PRIOR_PROFILE_LEVEL_NAMES,
    SESSION_STRUCTURAL_LEVEL_NAMES,
    STATIC_STUDY_LEVEL_NAMES,
    pivot_column_names,
)
from thesistester.levels.pivots import SUPPORTED_PIVOT_TIMEFRAMES, compute_pivot_levels
from thesistester.study import schema as study_schema
from thesistester.study.schema import (
    STUDY_EXPAND_REQUIRED_AXES,
    STUDY_FACTOR_AXIS_ALLOWED,
    STUDY_FACTOR_AXIS_RULES,
    STUDY_INGEST_RULES,
    STUDY_INGESTION_MODES,
    STUDY_REPORT_FIELD_RULES,
    STUDY_SCHEMA_VERSION,
    STUDY_STATIC_LEVEL_NAMES,
    VALID_DIRECTIONS,
    VALID_TRIGGERS,
    StudySpecError,
    StudySpecWarning,
    _WARNING_QUANTOWER_PRIMARY,
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
            "core_level": ["ONH"],
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
    # Default group_by only includes axes present on this study's factors.
    assert "trigger" in validated["study"]["report"]["group_by"]
    # stable re-normalize
    again = validate_study_spec(normalize_study_spec(validated))
    assert again["study"]["output_dir"] == validated["study"]["output_dir"]
    assert again["study"]["report"]["multiple_testing"] == "warn"
    assert "random_baseline" not in validated["study"]["report"]
    assert "random_baseline" not in again["study"]["report"]


def test_default_report_group_by_intersects_factors():
    raw = _minimal_study()
    del raw["study"]["report"]
    del raw["study"]["stage"]
    del raw["study"]["factors"]["trigger"]
    del raw["study"]["factors"]["trigger_timeframe"]
    validated = validate_study_spec(normalize_study_spec(raw))
    group_by = validated["study"]["report"]["group_by"]
    assert "trigger" not in group_by
    assert "trigger_timeframe" not in group_by
    assert "partner_levels" in group_by


def test_static_catalog_excludes_suggested_rolling_vwap():
    tokens = closed_level_token_set(
        {
            "vwap_windows": [],
            "poc_windows": [],
            "pivots_enabled": False,
            "prev30m_vwap_enabled": False,
        }
    )
    assert "VWAP_rolling_1h" not in tokens
    tokens_with_window = closed_level_token_set({"vwap_windows": ["1h"]})
    assert "VWAP_rolling_1h" in tokens_with_window


@pytest.mark.parametrize("core_level", ["pdVAH", "pwPOC", "pmVAL"])
def test_named_va_core_without_tick_paths_refuses(core_level):
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = [core_level]
    with pytest.raises(StudySpecError, match="VA requires ticks"):
        validate_study_spec(normalize_study_spec(raw))


@pytest.mark.parametrize("core_level", ["pdVAH", "pwPOC", "pmVAL"])
def test_named_va_core_with_tick_paths_validates(core_level):
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = [core_level]
    raw["study"]["dataset"]["tick_paths"] = ["data/es_ticks.csv"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == [core_level]


@pytest.mark.parametrize("core_level", ["APOC", "pAPOC"])
def test_named_apoc_core_without_tick_paths_refuses(core_level):
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = [core_level]
    with pytest.raises(StudySpecError, match="APOC requires ticks"):
        validate_study_spec(normalize_study_spec(raw))


@pytest.mark.parametrize("core_level", ["APOC", "pAPOC"])
def test_named_apoc_core_with_tick_paths_validates(core_level):
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = [core_level]
    raw["study"]["dataset"]["tick_paths"] = ["data/es_ticks.csv"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == [core_level]


def test_named_rolling_poc_without_tick_paths_refuses():
    raw = _minimal_study()
    raw["study"]["levels"]["poc_windows"] = ["30min"]
    raw["study"]["factors"]["core_level"] = ["POC_rolling_30min"]
    with pytest.raises(StudySpecError, match="rolling POC requires ticks"):
        validate_study_spec(normalize_study_spec(raw))


def test_named_rolling_poc_with_tick_paths_validates():
    raw = _minimal_study()
    raw["study"]["levels"]["poc_windows"] = ["30min"]
    raw["study"]["factors"]["core_level"] = ["POC_rolling_30min"]
    raw["study"]["dataset"]["tick_paths"] = ["data/es_ticks.csv"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == ["POC_rolling_30min"]


def test_onh_study_without_tick_families_validates_on_15s_only():
    raw = _minimal_study()
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == ["ONH"]
    assert "tick_paths" not in validated["study"]["dataset"]


def test_study_levels_accepts_explicit_apoc_tick_source():
    raw = _minimal_study()
    raw["study"]["levels"]["apoc_profile_source"] = "tick_last_volume_v1"
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["levels"]["apoc_profile_source"] == "tick_last_volume_v1"


def test_study_levels_rejects_bar_range_apoc_proxy():
    raw = _minimal_study()
    raw["study"]["levels"]["apoc_profile_source"] = "bar_range_uniform_volume_v1"
    with pytest.raises(StudySpecError, match="apoc_profile_source"):
        validate_study_spec(normalize_study_spec(raw))


def test_study_levels_rejects_typical_apoc_source():
    raw = _minimal_study()
    raw["study"]["levels"]["apoc_profile_source"] = "typical_mvp_v1"
    with pytest.raises(StudySpecError, match="apoc_profile_source"):
        validate_study_spec(normalize_study_spec(raw))


def test_study_levels_accepts_explicit_rolling_poc_tick_source():
    raw = _minimal_study()
    raw["study"]["levels"]["rolling_poc_profile_source"] = "tick_last_volume_v1"
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["levels"]["rolling_poc_profile_source"] == "tick_last_volume_v1"


def test_study_levels_rejects_typical_rolling_poc_source():
    raw = _minimal_study()
    raw["study"]["levels"]["rolling_poc_profile_source"] = "typical_mvp_v1"
    with pytest.raises(StudySpecError, match="rolling_poc_profile_source"):
        validate_study_spec(normalize_study_spec(raw))


def test_lc1_closed_set_includes_prior_profile_twins_not_gated_or_rolling():
    tokens = closed_level_token_set(
        {
            "vwap_windows": [],
            "poc_windows": [],
            "pivots_enabled": False,
            "prev30m_vwap_enabled": False,
        }
    )
    assert set(PRIOR_PROFILE_LEVEL_NAMES) <= tokens
    assert not any(name.startswith("VWAP_rolling_") for name in tokens)
    assert not any(name.startswith("POC_rolling_") for name in tokens)
    assert not any(name.startswith("Pivot_") for name in tokens)
    assert "prev30mVWAP" not in tokens


def test_lc1_study_static_names_are_catalog_identity():
    assert STUDY_STATIC_LEVEL_NAMES is STATIC_STUDY_LEVEL_NAMES
    assert STUDY_STATIC_LEVEL_NAMES == STATIC_STUDY_LEVEL_NAMES
    assert not any(name.startswith("VWAP_rolling_") for name in STUDY_STATIC_LEVEL_NAMES)
    assert not any(name.startswith("POC_rolling_") for name in STUDY_STATIC_LEVEL_NAMES)


def _session_levels_ordered_from_source() -> list[str]:
    """Local ``ordered`` list in ``compute_session_levels`` (not a module attr)."""
    source = Path("thesistester/levels/sessions.py").read_text(encoding="utf-8")
    match = re.search(r"ordered = \[([^\]]+)\]", source)
    assert match is not None, "compute_session_levels ordered list not found"
    return ast.literal_eval("[" + match.group(1) + "]")


def test_lc1_session_structural_names_match_compute_session_levels_ordered():
    assert list(SESSION_STRUCTURAL_LEVEL_NAMES) == _session_levels_ordered_from_source()
    assert tuple(APOC_LEVEL_NAMES) == APOC_COLUMNS


def test_load_study_spec_from_yaml(tmp_path: Path):
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(_minimal_study()), encoding="utf-8")
    loaded = load_study_spec(path)
    assert loaded["study"]["factors"]["core_level"] == ["ONH"]


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


def test_missing_required_factor_axis_fails_closed():
    raw = _minimal_study()
    del raw["study"]["factors"]["core_level"]
    with pytest.raises(StudySpecError, match="Missing required factor axes"):
        validate_study_spec(normalize_study_spec(raw))
    required = frozenset(rule.axis for rule in STUDY_FACTOR_AXIS_RULES if rule.required)
    assert "core_level" in required


def test_unknown_study_key_fails_closed():
    raw = _minimal_study()
    raw["study"]["bot_personality"] = "aggressive"
    with pytest.raises(StudySpecError, match="Unknown study keys"):
        validate_study_spec(normalize_study_spec(raw))


def _valid_lineage() -> dict:
    return {
        "parent_output_dir": "/tmp/parent_study",
        "parent_identity_hash": "abc123",
        "parent_run_name": "cell_000",
        "admit": {
            "group": "entry_rth_segment",
            "value": "rth_open_30m",
            "rule": "briefing_best_avg_r",
            "min_trades": 30,
            "thin": False,
        },
    }


def test_omitted_lineage_still_validates():
    raw = _minimal_study()
    assert "lineage" not in raw["study"]
    spec = validate_study_spec(normalize_study_spec(raw))
    assert "lineage" not in spec["study"]


def test_null_lineage_is_omitted_after_normalize():
    raw = _minimal_study()
    raw["study"]["lineage"] = None
    spec = validate_study_spec(normalize_study_spec(raw))
    assert "lineage" not in spec["study"]


def test_empty_lineage_mapping_fails_closed():
    raw = _minimal_study()
    raw["study"]["lineage"] = {}
    with pytest.raises(StudySpecError, match="study.lineage is missing required keys"):
        validate_study_spec(normalize_study_spec(raw))


def test_valid_lineage_validates():
    raw = _minimal_study()
    raw["study"]["lineage"] = _valid_lineage()
    spec = validate_study_spec(normalize_study_spec(raw))
    assert spec["study"]["lineage"]["admit"]["group"] == "entry_rth_segment"


def test_unknown_lineage_key_fails_closed():
    raw = _minimal_study()
    raw["study"]["lineage"] = {**_valid_lineage(), "extra": True}
    with pytest.raises(StudySpecError, match="Unknown study.lineage keys"):
        validate_study_spec(normalize_study_spec(raw))


def test_unknown_lineage_admit_key_fails_closed():
    raw = _minimal_study()
    lineage = _valid_lineage()
    lineage["admit"]["bucket"] = "nope"
    raw["study"]["lineage"] = lineage
    with pytest.raises(StudySpecError, match="Unknown study.lineage.admit keys"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_lineage_admit_group_fails_closed():
    raw = _minimal_study()
    lineage = _valid_lineage()
    lineage["admit"]["group"] = "session_name"
    raw["study"]["lineage"] = lineage
    with pytest.raises(StudySpecError, match="study.lineage.admit.group"):
        validate_study_spec(normalize_study_spec(raw))


def test_invalid_trigger_rejected():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger"] = ["teleport"]
    with pytest.raises(StudySpecError, match="factors.trigger"):
        validate_study_spec(normalize_study_spec(raw))


def test_fade_and_continuation_triggers_accepted():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger"] = ["fade", "continuation"]
    raw["study"]["stage"]["include"]["trigger"] = ["fade", "continuation"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["trigger"] == ["fade", "continuation"]
    assert validated["study"]["stage"]["include"]["trigger"] == ["fade", "continuation"]
    assert set(validated["study"]["factors"]["trigger"]) <= VALID_TRIGGERS


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
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["constants"]["direction"] == "long"
    assert validated["study"]["constants"]["direction"] in VALID_DIRECTIONS


def test_direction_factor_axis_allowed():
    raw = _minimal_study()
    raw["study"]["factors"]["direction"] = ["long", "short"]
    # explicit_cells / filter group_by may reference it; keep stage filter axes valid
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["direction"] == ["long", "short"]
    assert set(validated["study"]["factors"]["direction"]) <= VALID_DIRECTIONS


def _schema_assigned_names(tree: ast.AST) -> set[str]:
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)
    return assigned


def test_study_factor_axis_rules_own_table_not_c1_c2():
    """C-3 / QI-07-03: own tables; seven axes; omit ingestion_mode → primary."""
    assert tuple(rule.axis for rule in STUDY_FACTOR_AXIS_RULES) == (
        "core_level",
        "partner_levels",
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
        "otf",
        "direction",
    )
    assert tuple(rule.axis for rule in STUDY_FACTOR_AXIS_RULES if rule.required) == (
        "core_level",
        "partner_levels",
    )
    assert study_schema._SUPPORTED_FACTOR_AXES == frozenset(
        rule.axis for rule in STUDY_FACTOR_AXIS_RULES
    )
    assert study_schema._REQUIRED_FACTOR_AXES == frozenset(
        rule.axis for rule in STUDY_FACTOR_AXIS_RULES if rule.required
    )
    assert STUDY_EXPAND_REQUIRED_AXES == ("confluence_mode", "trigger", "trigger_timeframe")
    assert set(STUDY_FACTOR_AXIS_ALLOWED) == {
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
        "direction",
    }
    assert tuple(rule.field for rule in STUDY_REPORT_FIELD_RULES) == (
        "primary_metric",
        "multiple_testing",
    )
    ingest = next(rule for rule in STUDY_INGEST_RULES if rule.key == "ingestion_mode")
    assert ingest.omit_means == "primary"
    assert ingest.allowed == STUDY_INGESTION_MODES
    tree = ast.parse(Path(study_schema.__file__).read_text(encoding="utf-8"))
    assigned = _schema_assigned_names(tree)
    for name in (
        "STUDY_FACTOR_AXIS_RULES",
        "STUDY_REPORT_FIELD_RULES",
        "STUDY_INGEST_RULES",
        "STUDY_CONSTANTS_ENABLED_RULES",
        "STUDY_EXPAND_REQUIRED_AXES",
    ):
        assert name in assigned
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.update(alias.name for alias in node.names)
    assert "SETUP_CONFIG_RULES" not in used_names
    assert "RUN_SPEC_RULES" not in used_names
    assert "SETUP_CONFIG_RULES" not in imported
    assert "RUN_SPEC_RULES" not in imported
    assert not hasattr(study_schema, "SETUP_CONFIG_RULES")
    assert not hasattr(study_schema, "RUN_SPEC_RULES")


def test_own_table_comment_needles_do_not_bind():
    """Comment text naming C-1/C-2 tables must not satisfy the AST Name lock."""
    fake = (
        "STUDY_FACTOR_AXIS_RULES = ()\n"
        "STUDY_REPORT_FIELD_RULES = ()\n"
        "STUDY_INGEST_RULES = ()\n"
        "STUDY_CONSTANTS_ENABLED_RULES = ()\n"
        "STUDY_EXPAND_REQUIRED_AXES = ()\n"
        "# do not import SETUP_CONFIG_RULES or RUN_SPEC_RULES\n"
    )
    tree = ast.parse(fake)
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "SETUP_CONFIG_RULES" not in used_names
    assert "RUN_SPEC_RULES" not in used_names
    bound = "x = SETUP_CONFIG_RULES\ny = RUN_SPEC_RULES\n"
    bound_tree = ast.parse(bound)
    bound_names = {node.id for node in ast.walk(bound_tree) if isinstance(node, ast.Name)}
    assert "SETUP_CONFIG_RULES" in bound_names
    assert "RUN_SPEC_RULES" in bound_names


def _c3_probe_core_level():
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = ["NOT_A_LEVEL"]
    return raw


def _c3_probe_partner_levels():
    raw = _minimal_study()
    raw["study"]["factors"]["partner_levels"] = [["NOT_A_LEVEL"]]
    return raw


def _c3_probe_confluence_mode():
    raw = _minimal_study()
    raw["study"]["factors"]["confluence_mode"] = ["nope"]
    return raw


def _c3_probe_trigger():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger"] = ["nope"]
    return raw


def _c3_probe_trigger_timeframe():
    raw = _minimal_study()
    raw["study"]["factors"]["trigger_timeframe"] = ["30min"]
    return raw


def _c3_probe_otf():
    raw = _minimal_study()
    raw["study"]["factors"]["otf"] = ["not-a-mapping"]
    return raw


def _c3_probe_direction():
    raw = _minimal_study()
    raw["study"]["factors"]["direction"] = ["sideways"]
    return raw


_FACTOR_AXIS_PROBES: tuple[tuple[str, object, str], ...] = (
    ("core_level", _c3_probe_core_level, "Unknown core_level"),
    ("partner_levels", _c3_probe_partner_levels, "Unknown partner"),
    ("confluence_mode", _c3_probe_confluence_mode, "factors.confluence_mode"),
    ("trigger", _c3_probe_trigger, "factors.trigger"),
    ("trigger_timeframe", _c3_probe_trigger_timeframe, "30min is not a valid trigger timeframe"),
    ("otf", _c3_probe_otf, r"factors.otf\[0\] must be a mapping"),
    ("direction", _c3_probe_direction, "factors.direction"),
)


def test_validate_study_spec_rule_table_probe_names_match_axes():
    assert tuple(row[0] for row in _FACTOR_AXIS_PROBES) == tuple(
        rule.axis for rule in STUDY_FACTOR_AXIS_RULES
    )


def _axis_check_error(rule, factors, *, closed_tokens, constants) -> str | None:
    try:
        if rule.check is not None:
            rule.check(factors, closed_tokens=closed_tokens, constants=constants)
        else:
            study_schema._validate_enum_factor_axis(factors, rule)
    except StudySpecError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize(("axis", "make_spec", "expected"), _FACTOR_AXIS_PROBES)
def test_validate_study_spec_one_row_per_supported_axis(axis, make_spec, expected):
    raw = make_spec()
    spec = normalize_study_spec(raw)
    with pytest.raises(StudySpecError, match=expected):
        validate_study_spec(spec)
    factors = spec["study"]["factors"]
    constants = spec["study"]["constants"]
    tokens = closed_level_token_set(spec["study"].get("levels") or {})
    rule = next(item for item in STUDY_FACTOR_AXIS_RULES if item.axis == axis)
    message = _axis_check_error(
        rule, factors, closed_tokens=tokens, constants=constants
    )
    assert message is not None
    assert re.search(expected, message)
    for other in STUDY_FACTOR_AXIS_RULES:
        if other.axis == axis or other.axis not in factors:
            continue
        other_message = _axis_check_error(
            other, factors, closed_tokens=tokens, constants=constants
        )
        if other_message is None:
            continue
        assert not re.search(expected, other_message), other.axis


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
                "core_level": "ONH",
                "partner_levels": ["SMA_50_1min"],
                # missing remaining axes
            }
        ],
    }
    with pytest.raises(StudySpecError, match="missing factor keys"):
        validate_study_spec(normalize_study_spec(raw))

    cell = {
        "core_level": "ONH",
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
    assert "Pivot_1m_High" not in disabled
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
    assert "Pivot_1m_High" in enabled
    assert "Pivot_1min_High" not in enabled
    assert "prev30mVWAP" in enabled


def test_lc2_closed_set_uses_engine_pivot_spelling():
    tokens = closed_level_token_set({"pivots_enabled": True, "pivot_timeframes": ["1min"]})
    assert "Pivot_1m_High" in tokens
    assert "Pivot_1m_Low" in tokens
    assert "Pivot_1min_High" not in tokens

    all_tfs = closed_level_token_set(
        {"pivots_enabled": True, "pivot_timeframes": list(SUPPORTED_PIVOT_TIMEFRAMES)}
    )
    assert {
        "Pivot_1m_High",
        "Pivot_5m_High",
        "Pivot_30m_High",
        "Pivot_4h_High",
        "Pivot_1m_Low",
        "Pivot_5m_Low",
        "Pivot_30m_Low",
        "Pivot_4h_Low",
    } <= all_tfs
    assert "Pivot_5min_High" not in all_tfs
    assert "Pivot_30min_High" not in all_tfs


def test_lc2_pivot_column_names_match_engine_columns():
    timestamps = pd.date_range("2026-06-02 09:30:00", periods=8, freq="1min", tz="America/New_York")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        }
    )
    timeframes = ["1min", "5min", "30min", "4h"]
    result = compute_pivot_levels(frame, instrument="ES", pivot_timeframes=timeframes, enabled=True)
    assert list(result.columns) == list(pivot_column_names(timeframes))
    assert list(pivot_column_names(SUPPORTED_PIVOT_TIMEFRAMES)) == [
        "Pivot_1m_High",
        "Pivot_1m_Low",
        "Pivot_5m_High",
        "Pivot_5m_Low",
        "Pivot_30m_High",
        "Pivot_30m_Low",
        "Pivot_4h_High",
        "Pivot_4h_Low",
    ]


def test_lc2_pivot_column_names_rejects_bare_string():
    with pytest.raises(TypeError, match="iterable of timeframe keys"):
        pivot_column_names("1min")


def test_lc2_unsupported_pivot_timeframe_fails_closed():
    with pytest.raises(StudySpecError, match="pivot_timeframes"):
        closed_level_token_set({"pivots_enabled": True, "pivot_timeframes": ["15min"]})
    with pytest.raises(StudySpecError, match="pivot_timeframes"):
        closed_level_token_set({"pivots_enabled": False, "pivot_timeframes": ["1m"]})
    with pytest.raises(StudySpecError, match="pivot_timeframes"):
        closed_level_token_set({"pivots_enabled": True, "pivot_timeframes": ["1min "]})


def test_lc2_pivot_1min_token_fails_closed():
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = ["Pivot_1min_High"]
    with pytest.raises(StudySpecError, match="Unknown core_level token"):
        validate_study_spec(normalize_study_spec(raw))


def test_lc2_pivot_1m_token_is_admitted():
    raw = _minimal_study()
    raw["study"]["factors"]["core_level"] = ["Pivot_1m_High"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == ["Pivot_1m_High"]


def test_lc2_session_level_catalog_uses_engine_pivot_spelling():
    assert "Pivot_1m_High" in SESSION_LEVEL_CATALOG
    assert "Pivot_5m_High" in SESSION_LEVEL_CATALOG
    assert "Pivot_30m_High" in SESSION_LEVEL_CATALOG
    assert "Pivot_1min_High" not in SESSION_LEVEL_CATALOG
    assert "Pivot_5min_High" not in SESSION_LEVEL_CATALOG
    assert "Pivot_30min_High" not in SESSION_LEVEL_CATALOG


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


def test_dataset_ingestion_mode_omitted_stays_legal():
    raw = _minimal_study()
    assert "ingestion_mode" not in raw["study"]["dataset"]
    with warnings.catch_warnings():
        warnings.simplefilter("error", StudySpecWarning)
        spec = validate_study_spec(normalize_study_spec(raw))
    assert "ingestion_mode" not in spec["study"]["dataset"]


_VENDOR_15S_HE = Path("tests/fixtures/vendor/quantower_history_exporter_15s.csv")
_QUANTOWER_PROFILE = "quantower_history_exporter"
_BUILDER_PATH = Path("thesistester/study/builder.py")
_PROGRAM_B_ROOTS = (
    Path("examples/studies/program_b"),
    Path("examples/studies/program_b_run2"),
)


def test_quantower_omitted_ingestion_mode_warns_and_does_not_rewrite():
    """QI-07-05 / QI-7 §10: 15s HE + omit stays primary; validate warns, no rewrite."""
    assert _VENDOR_15S_HE.is_file(), f"missing QI-7 §10 fixture: {_VENDOR_15S_HE}"
    raw = _minimal_study()
    raw["study"]["dataset"]["path"] = str(_VENDOR_15S_HE)
    raw["study"]["dataset"]["format_profile"] = _QUANTOWER_PROFILE
    assert "ingestion_mode" not in raw["study"]["dataset"]
    with pytest.warns(StudySpecWarning, match=re.escape(_WARNING_QUANTOWER_PRIMARY)):
        spec = validate_study_spec(normalize_study_spec(raw))
    assert "ingestion_mode" not in spec["study"]["dataset"]
    assert spec["study"]["dataset"]["format_profile"] == _QUANTOWER_PROFILE


def test_quantower_primary_ingestion_mode_warns_and_keeps_primary():
    raw = _minimal_study()
    raw["study"]["dataset"]["format_profile"] = _QUANTOWER_PROFILE
    raw["study"]["dataset"]["ingestion_mode"] = "primary"
    with pytest.warns(StudySpecWarning, match=re.escape(_WARNING_QUANTOWER_PRIMARY)):
        spec = validate_study_spec(normalize_study_spec(raw))
    assert spec["study"]["dataset"]["ingestion_mode"] == "primary"
    assert spec["study"]["dataset"]["ingestion_mode"] != INGESTION_MODE_15S_PRIMARY_DERIVE_1M


def test_quantower_padded_format_profile_warns_and_does_not_rewrite():
    """Builder strips profile tokens; validate must still warn without mutating the key."""
    raw = _minimal_study()
    raw["study"]["dataset"]["format_profile"] = f"  {_QUANTOWER_PROFILE}  "
    assert "ingestion_mode" not in raw["study"]["dataset"]
    with pytest.warns(StudySpecWarning, match=re.escape(_WARNING_QUANTOWER_PRIMARY)):
        spec = validate_study_spec(normalize_study_spec(raw))
    assert spec["study"]["dataset"]["format_profile"] == f"  {_QUANTOWER_PROFILE}  "
    assert "ingestion_mode" not in spec["study"]["dataset"]


def test_quantower_15s_primary_ingestion_mode_accepted_without_warning():
    raw = _minimal_study()
    raw["study"]["dataset"]["format_profile"] = _QUANTOWER_PROFILE
    raw["study"]["dataset"]["ingestion_mode"] = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    with warnings.catch_warnings():
        warnings.simplefilter("error", StudySpecWarning)
        spec = validate_study_spec(normalize_study_spec(raw))
    assert spec["study"]["dataset"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M


def test_quantower_warning_sentence_matches_builder_draft_warnings():
    """Same sentence as builder.draft_warnings; no diverging copy."""
    from thesistester.study.builder import StudyDraft, draft_warnings

    draft = StudyDraft()
    draft.format_profile = _QUANTOWER_PROFILE
    assert draft.ingestion_mode == "primary"
    assert draft_warnings(draft) == (_WARNING_QUANTOWER_PRIMARY,)


def test_builder_does_not_duplicate_quantower_primary_warning_sentence():
    """AST-bind: builder imports the schema constant and does not re-literal the sentence."""
    source = _BUILDER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = False
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "thesistester.study.schema"
            and any(alias.name == "_WARNING_QUANTOWER_PRIMARY" for alias in node.names)
        ):
            imported = True
            break
    assert imported, "builder must import _WARNING_QUANTOWER_PRIMARY from schema"
    for node in tree.body:
        targets: list[ast.Name] = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        if any(target.id == "_WARNING_QUANTOWER_PRIMARY" for target in targets):
            raise AssertionError("builder must not reassign _WARNING_QUANTOWER_PRIMARY")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == _WARNING_QUANTOWER_PRIMARY:
            raise AssertionError("builder must not re-literal the Quantower-primary sentence")


def test_program_b_manifests_validate_without_quantower_primary_warning():
    """A-14 exit gate: Program B 15s-primary packets stay silent at validate."""
    seen: set[Path] = set()
    for root in _PROGRAM_B_ROOTS:
        for manifest_name in ("manifest.yaml", "manifest_tick.yaml"):
            manifest_path = root / manifest_name
            assert manifest_path.is_file(), manifest_path
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            for row in manifest["studies"]:
                path = (root / row["file"]).resolve()
                if path in seen:
                    continue
                seen.add(path)
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                dataset = raw["study"]["dataset"]
                assert dataset.get("format_profile") == _QUANTOWER_PROFILE, path.name
                assert dataset.get("ingestion_mode") == INGESTION_MODE_15S_PRIMARY_DERIVE_1M, (
                    path.name
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("error", StudySpecWarning)
                    validate_study_spec(normalize_study_spec(raw))
    assert seen, "Program B manifests listed no studies"


def test_dataset_ingestion_mode_accepts_known_tokens():
    for token in sorted(STUDY_INGESTION_MODES):
        raw = _minimal_study()
        raw["study"]["dataset"]["ingestion_mode"] = token
        spec = validate_study_spec(normalize_study_spec(raw))
        assert spec["study"]["dataset"]["ingestion_mode"] == token
    assert INGESTION_MODE_15S_PRIMARY_DERIVE_1M in STUDY_INGESTION_MODES


def test_dataset_ingestion_mode_rejects_unknown_token():
    raw = _minimal_study()
    raw["study"]["dataset"]["ingestion_mode"] = "ticks"
    with pytest.raises(StudySpecError, match="ingestion_mode must be one of"):
        validate_study_spec(normalize_study_spec(raw))


def test_dataset_ingestion_mode_rejects_non_string():
    raw = _minimal_study()
    raw["study"]["dataset"]["ingestion_mode"] = True
    with pytest.raises(StudySpecError, match="ingestion_mode must be one of"):
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


def test_empty_partner_set_valid_for_exclusive_anchor_min_valid_zero():
    raw = _minimal_study()
    raw["study"]["constants"]["min_valid_confluences"] = 0
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["anchor_rules"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["partner_levels"] == [[]]


def test_empty_partner_set_invalid_when_min_valid_is_one():
    raw = _minimal_study()
    raw["study"]["constants"]["min_valid_confluences"] = 1
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["anchor_rules"]
    with pytest.raises(StudySpecError, match="must be a non-empty list"):
        validate_study_spec(normalize_study_spec(raw))


def test_empty_partner_set_invalid_when_min_valid_omitted():
    raw = _minimal_study()
    raw["study"]["constants"].pop("min_valid_confluences")
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["anchor_rules"]
    with pytest.raises(StudySpecError, match="must be a non-empty list"):
        validate_study_spec(normalize_study_spec(raw))


def test_empty_partner_set_invalid_when_global_cluster_present():
    raw = _minimal_study()
    raw["study"]["constants"]["min_valid_confluences"] = 0
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["global_cluster", "anchor_rules"]
    with pytest.raises(StudySpecError, match="must be a non-empty list"):
        validate_study_spec(normalize_study_spec(raw))


def test_empty_partner_set_invalid_when_min_valid_is_truncated_float():
    raw = _minimal_study()
    raw["study"]["constants"]["min_valid_confluences"] = 0.9
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["anchor_rules"]
    with pytest.raises(StudySpecError, match="must be a non-empty list"):
        validate_study_spec(normalize_study_spec(raw))


def _anchor_only_minimal_study():
    raw = _minimal_study()
    raw["study"]["constants"]["min_valid_confluences"] = 0
    raw["study"]["factors"]["partner_levels"] = [[]]
    raw["study"]["factors"]["confluence_mode"] = ["anchor_rules"]
    return raw


def test_stage_explicit_cells_allow_empty_partner_set_in_domain():
    raw = _anchor_only_minimal_study()
    raw["study"]["stage"] = {
        "mode": "explicit_cells",
        "cells": [
            {
                "core_level": "ONH",
                "partner_levels": [],
                "confluence_mode": "anchor_rules",
                "trigger": "touch",
                "trigger_timeframe": "base",
                "otf": {"enabled": False},
            }
        ],
    }
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["stage"]["cells"][0]["partner_levels"] == []


def test_stage_filter_include_allows_empty_partner_set_in_domain():
    raw = _anchor_only_minimal_study()
    raw["study"]["stage"] = {"mode": "filter", "include": {"partner_levels": [[]]}}
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["stage"]["include"]["partner_levels"] == [[]]


def test_stage_explicit_cells_empty_partner_set_still_must_be_in_domain():
    raw = _minimal_study()
    raw["study"]["stage"] = {
        "mode": "explicit_cells",
        "cells": [
            {
                "core_level": "ONH",
                "partner_levels": [],
                "confluence_mode": "global_cluster",
                "trigger": "touch",
                "trigger_timeframe": "base",
                "otf": {"enabled": False},
            }
        ],
    }
    with pytest.raises(StudySpecError, match="not one of factors.partner_levels"):
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
        "core_level": "ONH",
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
        "core_level": "RTH_Open",  # not in factors.core_level (stand-in is ONH)
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


def test_same_bar_opposite_direction_tokens_accepted():
    tokens = ("legacy", "skip_both", "raise")
    assert set(tokens) == study_schema._VALID_SAME_BAR_OPPOSITE_DIRECTION
    for token in tokens:
        raw = _minimal_study()
        raw["study"]["constants"]["backtest"]["same_bar_opposite_direction"] = token
        validated = validate_study_spec(normalize_study_spec(raw))
        assert validated["study"]["constants"]["backtest"]["same_bar_opposite_direction"] == token
        assert token in study_schema._VALID_SAME_BAR_OPPOSITE_DIRECTION


def test_same_bar_opposite_direction_omitted_is_ok():
    raw = _minimal_study()
    assert "same_bar_opposite_direction" not in raw["study"]["constants"]["backtest"]
    validate_study_spec(normalize_study_spec(raw))


def test_same_bar_opposite_direction_invalid_token_rejected():
    raw = _minimal_study()
    raw["study"]["constants"]["backtest"]["same_bar_opposite_direction"] = "flip_coin"
    with pytest.raises(StudySpecError, match="same_bar_opposite_direction"):
        validate_study_spec(normalize_study_spec(raw))


def test_same_bar_opposite_direction_null_rejected():
    raw = _minimal_study()
    raw["study"]["constants"]["backtest"]["same_bar_opposite_direction"] = None
    with pytest.raises(StudySpecError, match="same_bar_opposite_direction"):
        validate_study_spec(normalize_study_spec(raw))


def test_random_baseline_omitted_stays_absent():
    raw = _minimal_study()
    del raw["study"]["report"]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert "random_baseline" not in validated["study"]["report"]


def test_random_baseline_valid_block_accepts():
    raw = _minimal_study()
    raw["study"]["report"]["random_baseline"] = {
        "enabled": True,
        "n_replicas": 50,
        "random_state": 42,
    }
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["report"]["random_baseline"]["enabled"] is True
    assert validated["study"]["report"]["random_baseline"]["n_replicas"] == 50


def test_random_baseline_unknown_nested_key_fails():
    raw = _minimal_study()
    raw["study"]["report"]["random_baseline"] = {
        "enabled": True,
        "n_replicas": 50,
        "replica_expectancies": True,
    }
    with pytest.raises(StudySpecError, match="Unknown study.report.random_baseline"):
        validate_study_spec(normalize_study_spec(raw))


@pytest.mark.parametrize(
    "block, match",
    [
        ({"enabled": True, "n_replicas": 0}, "n_replicas"),
        ({"enabled": True, "n_replicas": 1.5}, "n_replicas"),
        ({"enabled": "true"}, "enabled"),
        ({"enabled": True, "random_state": True}, "random_state"),
        ({"n_replicas": 50}, "enabled"),
    ],
)
def test_random_baseline_invalid_values_fail(block, match):
    raw = _minimal_study()
    raw["study"]["report"]["random_baseline"] = block
    with pytest.raises(StudySpecError, match=match):
        validate_study_spec(normalize_study_spec(raw))


_WFA_OOS_METRIC = "wfa_median_test_expectancy_r"
_RANKABLE_PRIMARY_METRICS = frozenset(
    {"expectancy_r", "total_r", "max_drawdown_r", "trade_count", "profit_factor"}
)
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "thesistester" / "study" / "schema.py"


def _index_primary_metrics_targets(node: ast.stmt) -> list[ast.Name]:
    if isinstance(node, ast.Assign):
        return [target for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target]
    return []


def _index_primary_metrics_call(node: ast.stmt) -> ast.Call:
    value = node.value
    if (
        not isinstance(value, ast.Call)
        or not isinstance(value.func, ast.Name)
        or value.func.id != "frozenset"
        or len(value.args) != 1
        or not isinstance(value.args[0], ast.Set)
    ):
        raise AssertionError("_INDEX_PRIMARY_METRICS must be a frozenset({...}) literal")
    return value


def _index_primary_metrics_literals_from(source: str) -> frozenset[str]:
    """AST-bind `_INDEX_PRIMARY_METRICS` string literals (comment needles fail-closed)."""
    tree = ast.parse(source)
    assignments = [
        node
        for node in tree.body
        if any(
            target.id == "_INDEX_PRIMARY_METRICS" for target in _index_primary_metrics_targets(node)
        )
    ]
    if not assignments:
        raise AssertionError("missing _INDEX_PRIMARY_METRICS assignment")
    if len(assignments) != 1:
        raise AssertionError("multiple _INDEX_PRIMARY_METRICS assignments")
    tokens: set[str] = set()
    for elt in _index_primary_metrics_call(assignments[0]).args[0].elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            raise AssertionError("_INDEX_PRIMARY_METRICS members must be string literals")
        tokens.add(elt.value)
    return frozenset(tokens)


def _index_primary_metrics_literals() -> frozenset[str]:
    return _index_primary_metrics_literals_from(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_index_primary_metrics_allowlist_excludes_wfa_oos_token():
    """QI-05-06 / A-11 document path: ranking allowlist stays in-sample."""
    literals = _index_primary_metrics_literals()
    assert literals == _RANKABLE_PRIMARY_METRICS
    assert literals == study_schema._INDEX_PRIMARY_METRICS
    assert _WFA_OOS_METRIC not in literals
    assert _WFA_OOS_METRIC not in study_schema._INDEX_PRIMARY_METRICS


def test_index_primary_metrics_comment_needles_do_not_bind():
    """File-level / comment WFA needles must not satisfy the allowlist AST bind."""
    fake = (
        "_INDEX_PRIMARY_METRICS = frozenset(\n"
        '    {"expectancy_r", "total_r", "max_drawdown_r", "trade_count", "profit_factor"}\n'
        ")\n"
        f"# {_WFA_OOS_METRIC}\n"
    )
    literals = _index_primary_metrics_literals_from(fake)
    assert literals == _RANKABLE_PRIMARY_METRICS
    assert _WFA_OOS_METRIC not in literals

    widened = (
        "_INDEX_PRIMARY_METRICS = frozenset(\n"
        '    {"expectancy_r", "total_r", "max_drawdown_r", "trade_count", '
        f'"profit_factor", "{_WFA_OOS_METRIC}"}}\n'
        ")\n"
    )
    assert _WFA_OOS_METRIC in _index_primary_metrics_literals_from(widened)

    second_assign = (
        "_INDEX_PRIMARY_METRICS = frozenset(\n"
        '    {"expectancy_r", "total_r", "max_drawdown_r", "trade_count", "profit_factor"}\n'
        ")\n"
        f"_INDEX_PRIMARY_METRICS = _INDEX_PRIMARY_METRICS | {{'{_WFA_OOS_METRIC}'}}\n"
    )
    try:
        _index_primary_metrics_literals_from(second_assign)
    except AssertionError as exc:
        assert "multiple _INDEX_PRIMARY_METRICS assignments" in str(exc)
    else:
        raise AssertionError("second assignment must not bind the first allowlist literal")


@pytest.mark.parametrize("metric", sorted(_RANKABLE_PRIMARY_METRICS))
def test_rankable_primary_metric_accepted(metric):
    raw = _minimal_study()
    raw["study"]["report"]["primary_metric"] = metric
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["report"]["primary_metric"] == metric


def test_wfa_median_test_expectancy_r_not_rankable_primary_metric():
    """QI-05-06 / A-11: stored WFA OOS token is rejected as primary_metric."""
    raw = _minimal_study()
    raw["study"]["report"]["primary_metric"] = _WFA_OOS_METRIC
    with pytest.raises(StudySpecError, match="primary_metric must be one of") as excinfo:
        validate_study_spec(normalize_study_spec(raw))
    message = str(excinfo.value)
    listed, sep, got = message.partition("; got ")
    assert sep, f"reject message must echo the rejected token: {message}"
    assert _WFA_OOS_METRIC not in listed
    assert _WFA_OOS_METRIC in got
    for token in sorted(_RANKABLE_PRIMARY_METRICS):
        assert token in listed
