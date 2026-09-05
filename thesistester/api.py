"""Typed, Streamlit-free facade for the ThesisTester research pipeline.

The functions in this module only compose existing level, signal, engine, and
analytics functions. They intentionally contain no alternative trading logic.
"""

from __future__ import annotations

import math
from numbers import Integral, Real
from pathlib import Path
from typing import Any, Mapping, TypedDict

import pandas as pd

from thesistester.analytics import (
    best_grid_result,
    equity_curve,
    excursion_summary,
    monte_carlo_summary,
    grid_trade_sequences,
    noise_summary,
    overfitting_summary,
    portfolio_summary,
    sensitivity_summary,
    run_walk_forward_sl_tp,
    run_wfa_matrix,
    run_sl_tp_grid,
    summarize_trades,
    validation_summary,
)
from thesistester.analytics.time_analysis import add_time_buckets, summarize_by_group
from thesistester.analytics.otf_validation import run_otf_validation_matrix
from thesistester.config import INSTRUMENTS
from thesistester.data.derive import (
    DERIVATION_POLICY_DEFAULT,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    build_derivation_provenance,
    derive_complete_parent_ohlcv,
)
from thesistester.data.loader import (
    format_interval,
    load_ohlcv,
    prepare_15s_source_for_derivation,
    validate_ohlcv,
)
from thesistester.data.resample import resample_ohlcv
from thesistester.data.rolls import detect_contract_column, validate_roll_metadata
from thesistester.data.sessions import tag_session
from thesistester.engine.intrabar import prepare_subtimeframe_conservative_context
from thesistester.engine import (
    VALID_INTRABAR_MODELS,
    VALID_SAME_BAR_OPPOSITE_DIRECTION,
    apply_configured_otf_filter,
    detect_anchor_confluence_zones,
    detect_confluence_zones,
    flag_naked_levels,
    generate_signals as _generate_signals,
    simulate_trades,
    validate_exit_management_config,
)
from thesistester.levels.all import compute_all_levels
from thesistester.levels.catalog import named_prior_profile_tokens
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.sessions import compute_session_levels
from thesistester.levels.tick_vap import (
    LEVELS_TICK_IDENTITY_KEYS,
    PriorProfileTable,
    TICK_SOURCE_NONE,
    attach_tick_identity,
    build_prior_profile_table_from_paths,
    compute_table_path_source_id,
    compute_table_source_id,
    compute_tick_source_id,
    dataset_has_tick_inputs,
    resolve_tick_format_profile,
)
from thesistester.persistence.execution_artifacts import (
    ArtifactMiss,
    DataArtifact,
    LevelsArtifact,
    SourceDataBinding,
    invalidate_source_data_binding,
    normalize_cache_policy,
    read_source_data_binding,
    read_verified_data_artifact,
    read_verified_levels_artifact,
    summarize_cache_outcome,
    write_data_artifact,
    write_levels_artifact,
    write_source_data_binding,
)
from thesistester.persistence.local_store import (
    _normalize_signal_settings_for_hash,
    compute_signal_settings_hash,
)
from thesistester.research_identity import (
    DataIdentity,
    ExperimentIdentity,
    LevelsIdentity,
    normalize_execution_origin,
    normalize_levels_config,
)
from thesistester.entry_window_policy import normalize_entry_window
from thesistester.setup import (
    build_setup_config,
    get_effective_otf_filter_config,
    normalize_trigger_timeframe,
    validate_setup_config,
)


class LevelsResult(TypedDict):
    """Plain-data handoff from level computation."""

    levels: pd.DataFrame
    session_levels: pd.DataFrame
    levels_settings: dict[str, Any]


class SignalsResult(TypedDict):
    """Plain-data handoff from signal generation."""

    signals: pd.DataFrame
    confluence_zones: pd.DataFrame
    naked_flags: pd.DataFrame
    signal_settings: dict[str, Any]
    signal_settings_hash: str


class BacktestResult(TypedDict):
    """Plain-data handoff from one fixed-SL/TP backtest."""

    trades: pd.DataFrame
    trade_summary: dict[str, Any]
    equity_curve: pd.DataFrame
    skipped_signals: pd.DataFrame
    accepted_signals: pd.DataFrame
    rejected_signals: pd.DataFrame
    otf_filter_summary: dict[str, Any]
    intrabar_diagnostic: dict[str, Any]
    exit_management_diagnostic: dict[str, Any]
    direction_collision_diagnostic: dict[str, Any]
    entry_window: dict[str, Any]


class GridResult(TypedDict):
    """Plain-data handoff from an SL/TP grid."""

    grid_results: pd.DataFrame
    best_grid_result: dict[str, Any] | None
    accepted_signals: pd.DataFrame
    rejected_signals: pd.DataFrame
    otf_filter_summary: dict[str, Any]
    entry_window: dict[str, Any]


class ValidationResult(TypedDict, total=False):
    """Plain-data handoff from the configured validation battery."""

    validation_summary: dict[str, Any]
    excursion_summary: dict[str, Any]
    excursion_config: dict[str, Any]
    excursion_grouped_summary: pd.DataFrame
    excursion_calibration_grid: pd.DataFrame
    excursion_quadrant_summary: pd.DataFrame
    monte_carlo_summary: dict[str, Any]
    monte_carlo_config: dict[str, Any]
    noise_summary: dict[str, Any]
    noise_config: dict[str, Any]
    overfitting_summary: dict[str, Any]
    overfitting_config: dict[str, Any]
    sensitivity_summary: dict[str, Any]
    sensitivity_config: dict[str, Any]


class PortfolioResult(TypedDict):
    """Bundle-ready R21 portfolio analysis handoff."""

    portfolio_summary: dict[str, Any]
    portfolio_config: dict[str, Any]
    portfolio_trades: pd.DataFrame
    portfolio_skipped_trades: pd.DataFrame
    portfolio_equity_curve: pd.DataFrame
    portfolio_correlation: pd.DataFrame
    portfolio_drawdown_correlation: pd.DataFrame
    portfolio_marginal_contribution: pd.DataFrame


class WalkForwardAnalysisResult(TypedDict, total=False):
    """Bundle-ready R14 analysis handoff."""

    walk_forward_results: pd.DataFrame
    walk_forward_summary: dict[str, Any]
    walk_forward_config: dict[str, Any]
    walk_forward_oos_trades: pd.DataFrame
    walk_forward_stitched_equity: pd.DataFrame
    walk_forward_warnings: list[str]
    wfa_matrix: pd.DataFrame
    wfa_matrix_config: dict[str, Any]


_LEVEL_DEFAULTS: dict[str, Any] = DEFAULT_LEVELS_SETTINGS
_LEVEL_ARGUMENT_MAP = {
    "prior_day_profile_aggregation_ticks": "prior_day_aggregation_ticks",
    "prior_week_profile_aggregation_ticks": "prior_week_aggregation_ticks",
    "prior_month_profile_aggregation_ticks": "prior_month_aggregation_ticks",
}
_SETUP_EXECUTION_KEYS = {
    "name",
    "description",
    "instrument",
    "selected_levels",
    "tolerance_ticks",
    "min_confluences",
    "max_confluences",
    "naked_only",
    "naked_requirement",
    "trigger",
    "trigger_timeframe",
    "direction",
    "confluence_mode",
    "anchor_level",
    "confluence_rules",
    "min_valid_confluences",
    "trigger_params",
    "otf_filter",
    "entry_window",
}
_BACKTEST_DEFAULTS: dict[str, Any] = {
    "stop_loss_ticks": 8.0,
    "take_profit_ticks": 16.0,
    "max_holding_bars": None,
    "allow_same_bar_exit": True,
    "commission_per_side": 0.0,
    "slippage_ticks": 0.0,
    "flat_by_session_close": False,
    "session_close_time": None,
    "session_timezone": None,
    "no_new_entries_after": None,
    "exposure_policy": "allow_all",
    "cooldown_bars_after_exit": 0,
    "intrabar_model": "sl_first",
    "breakeven_after_r": None,
    "trailing_after_r": None,
    "trailing_distance_ticks": None,
    "entry_window": None,
    "same_bar_opposite_direction": "legacy",
}
_GRID_DEFAULTS: dict[str, Any] = {
    "stop_loss_ticks_values": [4.0, 8.0, 12.0],
    "take_profit_ticks_values": [8.0, 16.0, 24.0],
    "max_holding_bars": None,
    "allow_same_bar_exit": True,
    "commission_per_side": 0.0,
    "slippage_ticks": 0.0,
    "flat_by_session_close": False,
    "session_close_time": None,
    "session_timezone": None,
    "no_new_entries_after": None,
    "exposure_policy": "allow_all",
    "cooldown_bars_after_exit": 0,
    "ranking_metric": "expectancy_r",
    "min_trades": 1,
    "intrabar_model": "sl_first",
    "breakeven_after_r_values": [None],
    "trailing_after_r_values": [None],
    "trailing_distance_ticks_values": [None],
    "max_grid_cells": 500,
    "entry_window": None,
}
_VALIDATION_DEFAULTS: dict[str, Any] = {
    "n_bootstrap": 2000,
    "n_permutations": 5000,
    "confidence": 0.95,
    "random_state": 42,
    "min_trades_soft": 30,
    "min_trades_hard": 100,
    "selected_grid_metric": "expectancy_r",
}
_RUN_KEYS = {
    "name",
    "dataset",
    "levels",
    "setup",
    "backtest",
    "grid",
    "validation",
    "walk_forward",
}
_DATASET_KEYS = {
    "path",
    "subtimeframe_path",
    "instrument",
    "source_timezone",
    "exchange_timezone",
    "format_profile",
    "subtimeframe_format_profile",
    "ingestion_mode",
    # CAI-4 additive classic-export / artifact provenance (optional).
    "data_artifact_key",
    "data_identity",
    "tick_paths",
    "tick_format_profile",
    "prior_profile_table_path",
    "tick_source_id",
}
_SUPPORTED_INGESTION_MODES = frozenset({"primary", INGESTION_MODE_15S_PRIMARY_DERIVE_1M})
_DERIVE_15S_SUPPORTED_PROFILES = frozenset({"quantower_history_exporter"})
_EXCURSION_KEYS = {
    "enabled",
    "group_cols",
    "stop_r_grid",
    "target_r_grid",
    "both_hit_rule",
    "min_trades",
    "mae_r_threshold",
    "mfe_r_threshold",
}
_MONTE_CARLO_KEYS = {
    "enabled",
    "methods",
    "n_simulations",
    "skip_fraction",
    "block_length",
    "percentiles",
    "drawdown_thresholds_r",
    "random_state",
    "include_paths",
}
_OVERFITTING_KEYS = {
    "enabled",
    "pbo_partitions",
    "pbo_min_trades",
    "vs_random_n_replicas",
    "random_state",
}
_NOISE_KEYS = {
    "enabled",
    "n_replicas",
    "noise_fraction",
    "scale_basis",
    "atr_period",
    "random_state",
    "percentiles",
    "include_rows",
}
_SENSITIVITY_KEYS = {
    "enabled",
    "perturbation_fraction",
    "n_steps_per_side",
    "parameters",
    "random_state",
    "include_rows",
}
_WALK_FORWARD_KEYS = {
    "enabled",
    "fold_mode",
    "window_mode",
    "train_bars",
    "test_bars",
    "step_bars",
    "train_sessions",
    "test_sessions",
    "step_sessions",
    "ranking_metric",
    "min_train_trades",
    "stop_loss_ticks_values",
    "take_profit_ticks_values",
    "overlap_policy",
    "otf_history_policy",
    "matrix",
}
_WFA_MATRIX_KEYS = {
    "enabled",
    "train_session_values",
    "test_session_values",
    "matrix_metric",
    "max_matrix_cells",
}


def _instrument(instrument: str):
    try:
        return INSTRUMENTS[instrument]
    except KeyError as exc:
        raise ValueError(f"Unsupported instrument: {instrument!r}") from exc


def _merge_known(
    defaults: Mapping[str, Any],
    config: Mapping[str, Any] | None,
    *,
    section: str,
) -> dict[str, Any]:
    raw = dict(config or {})
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"Unknown {section} configuration keys: {unknown}")
    return {**defaults, **raw}


def _validate_keys(config: Mapping[str, Any], allowed: set[str], *, section: str) -> None:
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"Unknown {section} configuration keys: {unknown}")


def _require_mapping(value: Any, *, section: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{section} must be a mapping")
    return value


def _validate_random_state(value: Any, *, section: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{section}.random_state must be an integer >= 0")


def _require_same_bar_opposite_direction(value: Any) -> str:
    """Return a DA3 policy token or raise. Rejects ``None`` / non-tokens."""
    if value not in VALID_SAME_BAR_OPPOSITE_DIRECTION:
        raise ValueError(
            "backtest.same_bar_opposite_direction must be one of "
            f"{sorted(VALID_SAME_BAR_OPPOSITE_DIRECTION)}"
        )
    return str(value)


def _validate_bool_fields(
    config: Mapping[str, Any],
    fields: set[str],
    *,
    section: str,
) -> None:
    for key in sorted(fields & set(config)):
        if not isinstance(config[key], bool):
            raise ValueError(f"{section}.{key} must be a boolean")


def _validate_number_fields(
    config: Mapping[str, Any],
    fields: set[str],
    *,
    section: str,
    integer: bool = False,
) -> None:
    expected = Integral if integer else Real
    label = "an integer" if integer else "a number"
    for key in sorted(fields & set(config)):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ValueError(f"{section}.{key} must be {label}")
        if not math.isfinite(float(value)):
            raise ValueError(f"{section}.{key} must be finite")


def _validate_list_fields(
    config: Mapping[str, Any],
    fields: set[str],
    *,
    section: str,
    item_type: type | tuple[type, ...],
) -> None:
    for key in sorted(fields & set(config)):
        value = config[key]
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{section}.{key} must be a list")
        if any(isinstance(item, bool) or not isinstance(item, item_type) for item in value):
            raise ValueError(f"{section}.{key} contains an invalid item type")


def _validate_string_fields(
    config: Mapping[str, Any],
    fields: set[str],
    *,
    section: str,
    nullable: set[str] | None = None,
) -> None:
    nullable = nullable or set()
    for key in sorted(fields & set(config)):
        value = config[key]
        if value is None and key in nullable:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{section}.{key} must be a string")


def _validate_range(
    config: Mapping[str, Any],
    key: str,
    *,
    section: str,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_exclusive: bool = False,
    maximum_exclusive: bool = False,
) -> None:
    if key not in config or config[key] is None:
        return
    value = float(config[key])
    if minimum is not None:
        invalid = value <= minimum if minimum_exclusive else value < minimum
        if invalid:
            operator = ">" if minimum_exclusive else ">="
            raise ValueError(f"{section}.{key} must be {operator} {minimum}")
    if maximum is not None:
        invalid = value >= maximum if maximum_exclusive else value > maximum
        if invalid:
            operator = "<" if maximum_exclusive else "<="
            raise ValueError(f"{section}.{key} must be {operator} {maximum}")


def _validate_positive_list(
    config: Mapping[str, Any],
    key: str,
    *,
    section: str,
    allow_empty: bool = False,
) -> None:
    if key not in config:
        return
    values = config[key]
    if not allow_empty and not values:
        raise ValueError(f"{section}.{key} must be non-empty")
    if any(not math.isfinite(float(value)) or float(value) <= 0 for value in values):
        raise ValueError(f"{section}.{key} values must be finite and > 0")


def validate_run_spec(spec: Mapping[str, Any]) -> None:
    """Fail closed on unknown or nondeterministic experiment configuration."""
    run = _require_mapping(spec, section="run")
    _validate_keys(run, _RUN_KEYS, section="run")
    dataset = _require_mapping(run.get("dataset"), section="dataset")
    _validate_keys(dataset, _DATASET_KEYS, section="dataset")
    if "path" not in dataset:
        raise ValueError("Experiment dataset.path is required")
    if not isinstance(dataset["path"], (str, Path)):
        raise ValueError("dataset.path must be a path string")
    if "subtimeframe_path" in dataset and not isinstance(dataset["subtimeframe_path"], (str, Path)):
        raise ValueError("dataset.subtimeframe_path must be a path string")
    if "data_artifact_key" in dataset and dataset["data_artifact_key"] is not None:
        if not isinstance(dataset["data_artifact_key"], str) or not dataset["data_artifact_key"]:
            raise ValueError("dataset.data_artifact_key must be a non-empty string or null")
    if "data_identity" in dataset and dataset["data_identity"] is not None:
        if not isinstance(dataset["data_identity"], Mapping):
            raise ValueError("dataset.data_identity must be a mapping or null")
    if "tick_paths" in dataset and dataset["tick_paths"] is not None:
        raw_ticks = dataset["tick_paths"]
        if not isinstance(raw_ticks, list):
            raise ValueError("dataset.tick_paths must be a list of path strings")
        if any(not isinstance(item, (str, Path)) or not str(item).strip() for item in raw_ticks):
            raise ValueError("dataset.tick_paths must be a list of path strings")
    if "tick_format_profile" in dataset and dataset["tick_format_profile"] is not None:
        try:
            resolve_tick_format_profile(dataset["tick_format_profile"])
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if "prior_profile_table_path" in dataset and dataset["prior_profile_table_path"] is not None:
        if not isinstance(dataset["prior_profile_table_path"], (str, Path)):
            raise ValueError("dataset.prior_profile_table_path must be a path string")
    if "tick_source_id" in dataset and dataset["tick_source_id"] is not None:
        if not isinstance(dataset["tick_source_id"], str) or not dataset["tick_source_id"]:
            raise ValueError("dataset.tick_source_id must be a non-empty string or null")
    for key in (
        "instrument",
        "source_timezone",
        "exchange_timezone",
        "format_profile",
        "subtimeframe_format_profile",
        "ingestion_mode",
    ):
        if key in dataset and dataset[key] is not None and not isinstance(dataset[key], str):
            raise ValueError(f"dataset.{key} must be a string or null")
    if dataset.get("format_profile", "canonical") not in {
        "canonical",
        "ninjatrader",
        "sierra_intraday",
        "quantower_history_exporter",
        "databento_trades",
        "tick_capture",
        "second_capture",
    }:
        raise ValueError("dataset.format_profile is unsupported")
    if dataset.get("subtimeframe_format_profile", "canonical") not in {
        "canonical",
        "quantower_history_exporter",
    }:
        raise ValueError("dataset.subtimeframe_format_profile is unsupported")
    ingestion_mode = str(dataset.get("ingestion_mode") or "primary")
    if ingestion_mode not in _SUPPORTED_INGESTION_MODES:
        raise ValueError(
            "dataset.ingestion_mode must be one of "
            f"{sorted(_SUPPORTED_INGESTION_MODES)!r}, got {ingestion_mode!r}"
        )
    if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        if "subtimeframe_path" in dataset:
            raise ValueError(
                "dataset.subtimeframe_path cannot be combined with "
                f"ingestion_mode={INGESTION_MODE_15S_PRIMARY_DERIVE_1M!r}"
            )
        format_profile = str(dataset.get("format_profile", "canonical"))
        if format_profile not in _DERIVE_15S_SUPPORTED_PROFILES:
            raise ValueError(
                "dataset.format_profile must be one of "
                f"{sorted(_DERIVE_15S_SUPPORTED_PROFILES)!r} when "
                f"ingestion_mode={INGESTION_MODE_15S_PRIMARY_DERIVE_1M!r}"
            )
    instrument = str(dataset.get("instrument", "ES"))
    _instrument(instrument)

    levels = run.get("levels", {})
    _require_mapping(levels, section="levels")
    _validate_keys(
        levels,
        set(_LEVEL_DEFAULTS) | set(LEVELS_TICK_IDENTITY_KEYS),
        section="levels",
    )
    _validate_bool_fields(
        levels,
        {
            "pivots_enabled",
            "session_vwap_enabled",
            "single_prints_enabled",
            "apoc_enabled",
            "prev30m_vwap_enabled",
        },
        section="levels",
    )
    _validate_number_fields(
        levels,
        {"value_area_pct"},
        section="levels",
    )
    _validate_number_fields(
        levels,
        {
            "opening_range_minutes",
            "prior_day_profile_aggregation_ticks",
            "prior_week_profile_aggregation_ticks",
            "prior_month_profile_aggregation_ticks",
            "pivot_left",
            "pivot_right",
            "prev30m_vwap_validity_periods",
        },
        section="levels",
        integer=True,
    )
    _validate_list_fields(
        levels,
        {"sma_lengths", "ema_lengths"},
        section="levels",
        item_type=Integral,
    )
    _validate_list_fields(
        levels,
        {
            "sma_timeframes",
            "ema_timeframes",
            "vwap_windows",
            "poc_windows",
            "pivot_timeframes",
        },
        section="levels",
        item_type=str,
    )
    _validate_positive_list(levels, "sma_lengths", section="levels")
    _validate_positive_list(levels, "ema_lengths", section="levels")
    _validate_range(
        levels,
        "value_area_pct",
        section="levels",
        minimum=0,
        maximum=1,
        minimum_exclusive=True,
    )
    for key in (
        "opening_range_minutes",
        "prior_day_profile_aggregation_ticks",
        "prior_week_profile_aggregation_ticks",
        "prior_month_profile_aggregation_ticks",
        "pivot_left",
        "pivot_right",
        "prev30m_vwap_validity_periods",
    ):
        if key == "prev30m_vwap_validity_periods":
            from thesistester.levels.prev30m_vwap import MAX_VALIDITY_PERIODS

            _validate_range(
                levels,
                key,
                section="levels",
                minimum=1,
                maximum=MAX_VALIDITY_PERIODS,
            )
        else:
            _validate_range(levels, key, section="levels", minimum=1)
    setup = _require_mapping(run.get("setup"), section="setup")
    _validate_string_fields(
        setup,
        {
            "name",
            "description",
            "instrument",
            "naked_requirement",
            "trigger",
            "trigger_timeframe",
            "direction",
            "confluence_mode",
            "anchor_level",
        },
        section="setup",
        nullable={"anchor_level"},
    )
    _validate_bool_fields(setup, {"naked_only"}, section="setup")
    _validate_number_fields(setup, {"tolerance_ticks"}, section="setup")
    _validate_number_fields(
        setup,
        {"min_confluences", "max_confluences", "min_valid_confluences"},
        section="setup",
        integer=True,
    )
    _validate_range(setup, "tolerance_ticks", section="setup", minimum=0)
    _validate_range(setup, "min_confluences", section="setup", minimum=1)
    _validate_range(setup, "max_confluences", section="setup", minimum=1, maximum=5)
    _validate_range(setup, "min_valid_confluences", section="setup", minimum=0)
    _validate_list_fields(
        setup,
        {"selected_levels"},
        section="setup",
        item_type=str,
    )
    rules = setup.get("confluence_rules")
    if rules is not None:
        if not isinstance(rules, list):
            raise ValueError("setup.confluence_rules must be a list")
        for index, rule in enumerate(rules):
            rule = _require_mapping(rule, section=f"setup.confluence_rules[{index}]")
            _validate_keys(
                rule,
                {"level", "tolerance_ticks", "required"},
                section=f"setup.confluence_rules[{index}]",
            )
            _validate_string_fields(
                rule,
                {"level"},
                section=f"setup.confluence_rules[{index}]",
            )
            _validate_number_fields(
                rule,
                {"tolerance_ticks"},
                section=f"setup.confluence_rules[{index}]",
            )
            _validate_range(
                rule,
                "tolerance_ticks",
                section=f"setup.confluence_rules[{index}]",
                minimum=0,
            )
            _validate_bool_fields(
                rule,
                {"required"},
                section=f"setup.confluence_rules[{index}]",
            )
    trigger_params = setup.get("trigger_params")
    if trigger_params is not None:
        trigger_params = _require_mapping(trigger_params, section="setup.trigger_params")
        _validate_keys(
            trigger_params,
            {
                "arrival_tolerance_ticks",
                "entry_retrace_ticks",
                "max_entry_wait_bars_after_reversal",
                "require_close_confirmation",
            },
            section="setup.trigger_params",
        )
        _validate_number_fields(
            trigger_params,
            {"arrival_tolerance_ticks", "entry_retrace_ticks"},
            section="setup.trigger_params",
        )
        _validate_number_fields(
            trigger_params,
            {"max_entry_wait_bars_after_reversal"},
            section="setup.trigger_params",
            integer=True,
        )
        _validate_bool_fields(
            trigger_params,
            {"require_close_confirmation"},
            section="setup.trigger_params",
        )
        for key in (
            "arrival_tolerance_ticks",
            "entry_retrace_ticks",
            "max_entry_wait_bars_after_reversal",
        ):
            _validate_range(trigger_params, key, section="setup.trigger_params", minimum=0)
    otf = setup.get("otf_filter")
    if otf is not None:
        otf = _require_mapping(otf, section="setup.otf_filter")
        _validate_keys(
            otf,
            {
                "enabled",
                "timeframes",
                "alignment_mode",
                "minimum_consecutive_bars",
                "directional",
                "use_completed_bars_only",
                "session_reset",
            },
            section="setup.otf_filter",
        )
    setup_entry_window = setup.get("entry_window")
    if setup_entry_window is not None:
        setup_entry_window = _require_mapping(setup_entry_window, section="setup.entry_window")
        try:
            normalize_entry_window(
                dict(setup_entry_window),
                exchange_tz=_instrument(instrument).exchange_tz,
            )
        except ValueError as exc:
            raise ValueError(f"Invalid setup.entry_window: {exc}") from exc
    normalized_setup = build_setup(setup)
    if normalized_setup["instrument"] != instrument:
        raise ValueError(
            "setup.instrument must match dataset.instrument "
            f"({normalized_setup['instrument']!r} != {instrument!r})"
        )
    backtest = _require_mapping(run.get("backtest", {}), section="backtest")
    _validate_keys(backtest, set(_BACKTEST_DEFAULTS), section="backtest")
    _validate_bool_fields(
        backtest,
        {"allow_same_bar_exit", "flat_by_session_close"},
        section="backtest",
    )
    _validate_number_fields(
        backtest,
        {
            "stop_loss_ticks",
            "take_profit_ticks",
            "commission_per_side",
            "slippage_ticks",
            "breakeven_after_r",
            "trailing_after_r",
            "trailing_distance_ticks",
        },
        section="backtest",
    )
    _validate_number_fields(
        backtest,
        {"cooldown_bars_after_exit"},
        section="backtest",
        integer=True,
    )
    _validate_range(
        backtest,
        "stop_loss_ticks",
        section="backtest",
        minimum=0,
        minimum_exclusive=True,
    )
    _validate_range(
        backtest,
        "take_profit_ticks",
        section="backtest",
        minimum=0,
        minimum_exclusive=True,
    )
    _validate_range(backtest, "commission_per_side", section="backtest", minimum=0)
    _validate_range(backtest, "slippage_ticks", section="backtest", minimum=0)
    _validate_range(backtest, "cooldown_bars_after_exit", section="backtest", minimum=0)
    _validate_string_fields(
        backtest,
        {
            "session_close_time",
            "session_timezone",
            "no_new_entries_after",
            "exposure_policy",
            "intrabar_model",
            "same_bar_opposite_direction",
        },
        section="backtest",
        nullable={"session_close_time", "session_timezone", "no_new_entries_after"},
    )
    if backtest.get("intrabar_model", "sl_first") not in VALID_INTRABAR_MODELS:
        raise ValueError(f"backtest.intrabar_model must be one of {sorted(VALID_INTRABAR_MODELS)}")
    _require_same_bar_opposite_direction(
        backtest.get("same_bar_opposite_direction", "legacy")
    )
    validate_exit_management_config(
        breakeven_after_r=backtest.get("breakeven_after_r"),
        trailing_after_r=backtest.get("trailing_after_r"),
        trailing_distance_ticks=backtest.get("trailing_distance_ticks"),
    )
    if backtest.get("max_holding_bars") is not None:
        _validate_number_fields(
            backtest,
            {"max_holding_bars"},
            section="backtest",
            integer=True,
        )
        _validate_range(backtest, "max_holding_bars", section="backtest", minimum=1)
    if "entry_window" in backtest and backtest["entry_window"] is not None:
        entry_window = _require_mapping(backtest["entry_window"], section="backtest.entry_window")
        exchange_tz = _instrument(instrument).exchange_tz
        try:
            normalize_entry_window(dict(entry_window), exchange_tz=exchange_tz)
        except ValueError as exc:
            raise ValueError(f"Invalid backtest.entry_window: {exc}") from exc
    grid = run.get("grid")
    if grid is not None:
        grid = _require_mapping(grid, section="grid")
        _validate_keys(grid, {*_GRID_DEFAULTS, "enabled"}, section="grid")
        _validate_bool_fields(
            grid,
            {"enabled", "allow_same_bar_exit", "flat_by_session_close"},
            section="grid",
        )
        _validate_list_fields(
            grid,
            {
                "stop_loss_ticks_values",
                "take_profit_ticks_values",
                "breakeven_after_r_values",
                "trailing_after_r_values",
                "trailing_distance_ticks_values",
            },
            section="grid",
            item_type=(Real, type(None)),
        )
        _validate_positive_list(grid, "stop_loss_ticks_values", section="grid")
        _validate_positive_list(grid, "take_profit_ticks_values", section="grid")
        _validate_number_fields(
            grid,
            {"commission_per_side", "slippage_ticks"},
            section="grid",
        )
        _validate_number_fields(
            grid,
            {"cooldown_bars_after_exit", "min_trades", "max_grid_cells"},
            section="grid",
            integer=True,
        )
        _validate_range(grid, "commission_per_side", section="grid", minimum=0)
        _validate_range(grid, "slippage_ticks", section="grid", minimum=0)
        _validate_range(grid, "cooldown_bars_after_exit", section="grid", minimum=0)
        _validate_range(grid, "min_trades", section="grid", minimum=1)
        if "entry_window" in grid and grid["entry_window"] is not None:
            grid_entry_window = _require_mapping(grid["entry_window"], section="grid.entry_window")
            try:
                normalize_entry_window(
                    dict(grid_entry_window), exchange_tz=_instrument(instrument).exchange_tz
                )
            except ValueError as exc:
                raise ValueError(f"Invalid grid.entry_window: {exc}") from exc
        _validate_string_fields(
            grid,
            {
                "session_close_time",
                "session_timezone",
                "no_new_entries_after",
                "exposure_policy",
                "ranking_metric",
                "intrabar_model",
            },
            section="grid",
            nullable={"session_close_time", "session_timezone", "no_new_entries_after"},
        )
        if grid.get("intrabar_model", "sl_first") not in VALID_INTRABAR_MODELS:
            raise ValueError(f"grid.intrabar_model must be one of {sorted(VALID_INTRABAR_MODELS)}")
        for be in grid.get("breakeven_after_r_values", [None]):
            validate_exit_management_config(
                breakeven_after_r=be,
                trailing_after_r=None,
                trailing_distance_ticks=None,
            )
        for distance in grid.get("trailing_distance_ticks_values", [None]):
            if distance is not None:
                validate_exit_management_config(
                    breakeven_after_r=None,
                    trailing_after_r=1.0,
                    trailing_distance_ticks=distance,
                )
        for trail_after in grid.get("trailing_after_r_values", [None]):
            if trail_after is not None and not any(
                distance is not None
                for distance in grid.get("trailing_distance_ticks_values", [None])
            ):
                validate_exit_management_config(
                    breakeven_after_r=None,
                    trailing_after_r=trail_after,
                    trailing_distance_ticks=None,
                )
            for distance in grid.get("trailing_distance_ticks_values", [None]):
                if distance is None:
                    continue
                if trail_after is None:
                    continue
                validate_exit_management_config(
                    breakeven_after_r=None,
                    trailing_after_r=trail_after,
                    trailing_distance_ticks=distance,
                )
        if grid.get("max_holding_bars") is not None:
            _validate_number_fields(
                grid,
                {"max_holding_bars"},
                section="grid",
                integer=True,
            )
            _validate_range(grid, "max_holding_bars", section="grid", minimum=1)
    requested_intrabar_models = {backtest.get("intrabar_model", "sl_first")}
    if isinstance(grid, Mapping) and grid.get("enabled", True):
        requested_intrabar_models.add(grid.get("intrabar_model", "sl_first"))
    if "subtimeframe" in requested_intrabar_models:
        has_lower_source = (
            "subtimeframe_path" in dataset or ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
        )
        if not has_lower_source:
            raise ValueError(
                "dataset.subtimeframe_path is required when an enabled run section "
                "uses intrabar_model='subtimeframe', unless dataset.ingestion_mode="
                f"{INGESTION_MODE_15S_PRIMARY_DERIVE_1M!r}"
            )
    walk_forward = run.get("walk_forward")
    if walk_forward is not None:
        walk_forward = _require_mapping(walk_forward, section="walk_forward")
        _validate_keys(
            walk_forward,
            _WALK_FORWARD_KEYS,
            section="walk_forward",
        )
        _validate_bool_fields(walk_forward, {"enabled"}, section="walk_forward")
        _validate_string_fields(
            walk_forward,
            {
                "fold_mode",
                "window_mode",
                "ranking_metric",
                "overlap_policy",
                "otf_history_policy",
            },
            section="walk_forward",
        )
        if walk_forward.get("fold_mode", "bars") not in {"bars", "sessions"}:
            raise ValueError("walk_forward.fold_mode must be 'bars' or 'sessions'")
        if walk_forward.get("window_mode", "rolling") not in {"rolling", "anchored"}:
            raise ValueError("walk_forward.window_mode must be 'rolling' or 'anchored'")
        if walk_forward.get("overlap_policy", "reject") not in {
            "reject",
            "first",
            "last",
        }:
            raise ValueError("walk_forward.overlap_policy must be 'reject', 'first', or 'last'")
        if "otf_history_policy" in walk_forward:
            from thesistester.analytics.walk_forward import normalize_otf_history_policy

            try:
                normalize_otf_history_policy(walk_forward.get("otf_history_policy"))
            except ValueError as exc:
                raise ValueError(f"walk_forward.otf_history_policy: {exc}") from exc
        _validate_number_fields(
            walk_forward,
            {
                "train_bars",
                "test_bars",
                "step_bars",
                "train_sessions",
                "test_sessions",
                "step_sessions",
                "min_train_trades",
            },
            section="walk_forward",
            integer=True,
        )
        _validate_list_fields(
            walk_forward,
            {"stop_loss_ticks_values", "take_profit_ticks_values"},
            section="walk_forward",
            item_type=Real,
        )
        matrix = walk_forward.get("matrix")
        if matrix is not None:
            matrix = _require_mapping(matrix, section="walk_forward.matrix")
            _validate_keys(matrix, _WFA_MATRIX_KEYS, section="walk_forward.matrix")
            _validate_bool_fields(matrix, {"enabled"}, section="walk_forward.matrix")
            _validate_list_fields(
                matrix,
                {"train_session_values", "test_session_values"},
                section="walk_forward.matrix",
                item_type=Integral,
            )
            _validate_number_fields(
                matrix,
                {"max_matrix_cells"},
                section="walk_forward.matrix",
                integer=True,
            )
            if matrix.get("enabled", False):
                for key in ("train_session_values", "test_session_values"):
                    if key not in matrix:
                        raise ValueError(f"walk_forward.matrix.{key} is required when enabled")
                    _validate_positive_list(
                        matrix,
                        key,
                        section="walk_forward.matrix",
                    )
                valid_matrix_metrics = {
                    "median_test_expectancy_r",
                    "median_retention_ratio_expectancy",
                    "stitched_oos_total_r",
                    "oos_profitable_fold_rate",
                }
                if (
                    matrix.get("matrix_metric", "median_test_expectancy_r")
                    not in valid_matrix_metrics
                ):
                    raise ValueError(
                        "walk_forward.matrix.matrix_metric must be one of "
                        f"{sorted(valid_matrix_metrics)}"
                    )
    validation = run.get("validation")
    if validation is not None:
        validation = _require_mapping(validation, section="validation")
        _validate_keys(
            validation,
            {
                *_VALIDATION_DEFAULTS,
                "enabled",
                "excursion",
                "monte_carlo",
                "overfitting",
                "noise",
                "sensitivity",
            },
            section="validation",
        )
        _validate_bool_fields(validation, {"enabled"}, section="validation")
        _validate_number_fields(validation, {"confidence"}, section="validation")
        _validate_number_fields(
            validation,
            {"n_bootstrap", "n_permutations", "min_trades_soft", "min_trades_hard"},
            section="validation",
            integer=True,
        )
        _validate_range(validation, "n_bootstrap", section="validation", minimum=1)
        _validate_range(validation, "n_permutations", section="validation", minimum=1)
        _validate_range(validation, "min_trades_soft", section="validation", minimum=1)
        _validate_range(validation, "min_trades_hard", section="validation", minimum=1)
        _validate_range(
            validation,
            "confidence",
            section="validation",
            minimum=0,
            maximum=1,
            minimum_exclusive=True,
            maximum_exclusive=True,
        )
        random_state = validation.get("random_state", _VALIDATION_DEFAULTS["random_state"])
        _validate_random_state(random_state, section="validation")
        excursion = validation.get("excursion")
        if excursion is not None:
            excursion = _require_mapping(excursion, section="validation.excursion")
            _validate_keys(excursion, _EXCURSION_KEYS, section="validation.excursion")
            _validate_bool_fields(excursion, {"enabled"}, section="validation.excursion")
            _validate_number_fields(
                excursion,
                {"min_trades"},
                section="validation.excursion",
                integer=True,
            )
            _validate_number_fields(
                excursion,
                {"mae_r_threshold", "mfe_r_threshold"},
                section="validation.excursion",
            )
            _validate_range(
                excursion,
                "min_trades",
                section="validation.excursion",
                minimum=1,
            )
            _validate_range(
                excursion,
                "mae_r_threshold",
                section="validation.excursion",
                minimum=0,
            )
            _validate_range(
                excursion,
                "mfe_r_threshold",
                section="validation.excursion",
                minimum=0,
            )
            _validate_list_fields(
                excursion,
                {"stop_r_grid", "target_r_grid"},
                section="validation.excursion",
                item_type=Real,
            )
            _validate_positive_list(
                excursion,
                "stop_r_grid",
                section="validation.excursion",
            )
            _validate_positive_list(
                excursion,
                "target_r_grid",
                section="validation.excursion",
            )
        monte_carlo = validation.get("monte_carlo")
        if monte_carlo is not None:
            monte_carlo = _require_mapping(monte_carlo, section="validation.monte_carlo")
            _validate_keys(
                monte_carlo,
                _MONTE_CARLO_KEYS,
                section="validation.monte_carlo",
            )
            _validate_bool_fields(
                monte_carlo,
                {"enabled", "include_paths"},
                section="validation.monte_carlo",
            )
            _validate_number_fields(
                monte_carlo,
                {"n_simulations"},
                section="validation.monte_carlo",
                integer=True,
            )
            if monte_carlo.get("block_length") is not None:
                _validate_number_fields(
                    monte_carlo,
                    {"block_length"},
                    section="validation.monte_carlo",
                    integer=True,
                )
                _validate_range(
                    monte_carlo,
                    "block_length",
                    section="validation.monte_carlo",
                    minimum=1,
                )
            _validate_number_fields(
                monte_carlo,
                {"skip_fraction"},
                section="validation.monte_carlo",
            )
            _validate_range(
                monte_carlo,
                "n_simulations",
                section="validation.monte_carlo",
                minimum=1,
            )
            _validate_range(
                monte_carlo,
                "skip_fraction",
                section="validation.monte_carlo",
                minimum=0,
                maximum=1,
                maximum_exclusive=True,
            )
            _validate_list_fields(
                monte_carlo,
                {"methods"},
                section="validation.monte_carlo",
                item_type=str,
            )
            _validate_list_fields(
                monte_carlo,
                {"percentiles", "drawdown_thresholds_r"},
                section="validation.monte_carlo",
                item_type=Real,
            )
            _validate_positive_list(
                monte_carlo,
                "drawdown_thresholds_r",
                section="validation.monte_carlo",
            )
            if monte_carlo.get("enabled", True):
                mc_seed = monte_carlo.get("random_state", 42)
                _validate_random_state(mc_seed, section="validation.monte_carlo")
        overfitting = validation.get("overfitting")
        if overfitting is not None:
            overfitting = _require_mapping(overfitting, section="validation.overfitting")
            _validate_keys(
                overfitting,
                _OVERFITTING_KEYS,
                section="validation.overfitting",
            )
            _validate_bool_fields(overfitting, {"enabled"}, section="validation.overfitting")
            _validate_number_fields(
                overfitting,
                {
                    "pbo_partitions",
                    "pbo_min_trades",
                    "vs_random_n_replicas",
                    "random_state",
                },
                section="validation.overfitting",
                integer=True,
            )
        noise = validation.get("noise")
        if noise is not None:
            noise = _require_mapping(noise, section="validation.noise")
            _validate_keys(noise, _NOISE_KEYS, section="validation.noise")
            _validate_bool_fields(
                noise,
                {"enabled", "include_rows"},
                section="validation.noise",
            )
            _validate_number_fields(
                noise,
                {"n_replicas", "atr_period"},
                section="validation.noise",
                integer=True,
            )
            _validate_number_fields(
                noise,
                {"noise_fraction"},
                section="validation.noise",
            )
            _validate_range(noise, "n_replicas", section="validation.noise", minimum=1)
            _validate_range(noise, "atr_period", section="validation.noise", minimum=1)
            _validate_range(
                noise,
                "noise_fraction",
                section="validation.noise",
                minimum=0,
                maximum=1,
                minimum_exclusive=True,
            )
            _validate_string_fields(noise, {"scale_basis"}, section="validation.noise")
            if noise.get("scale_basis", "atr") not in {"atr", "range"}:
                raise ValueError("validation.noise.scale_basis must be 'atr' or 'range'")
            _validate_list_fields(
                noise,
                {"percentiles"},
                section="validation.noise",
                item_type=Real,
            )
            if noise.get("enabled", True):
                _validate_random_state(
                    noise.get("random_state", 42),
                    section="validation.noise",
                )
        sensitivity = validation.get("sensitivity")
        if sensitivity is not None:
            sensitivity = _require_mapping(sensitivity, section="validation.sensitivity")
            _validate_keys(sensitivity, _SENSITIVITY_KEYS, section="validation.sensitivity")
            _validate_bool_fields(
                sensitivity,
                {"enabled", "include_rows"},
                section="validation.sensitivity",
            )
            _validate_number_fields(
                sensitivity,
                {"n_steps_per_side", "random_state"},
                section="validation.sensitivity",
                integer=True,
            )
            _validate_number_fields(
                sensitivity,
                {"perturbation_fraction"},
                section="validation.sensitivity",
            )
            _validate_range(
                sensitivity,
                "n_steps_per_side",
                section="validation.sensitivity",
                minimum=1,
            )
            _validate_range(
                sensitivity,
                "perturbation_fraction",
                section="validation.sensitivity",
                minimum=0,
                maximum=1,
                minimum_exclusive=True,
            )
            _validate_list_fields(
                sensitivity,
                {"parameters"},
                section="validation.sensitivity",
                item_type=str,
            )
            if sensitivity.get("enabled", True):
                _validate_random_state(
                    sensitivity.get("random_state", 42),
                    section="validation.sensitivity",
                )


def _setup_caption(config: Mapping[str, Any]) -> str:
    """Build the setup audit caption stored by the Signals page."""
    mode = str(config.get("confluence_mode", "global_cluster"))
    trigger_timeframe = normalize_trigger_timeframe(config.get("trigger_timeframe"))
    otf = get_effective_otf_filter_config(dict(config))
    otf_caption = (
        f"OTF=enabled({','.join(otf['timeframes'])}; min={otf['minimum_consecutive_bars']})"
        if otf["enabled"]
        else "OTF=disabled"
    )
    if mode == "anchor_rules":
        return (
            f"Mode=anchor_rules • Anchor={config.get('anchor_level') or '-'} • "
            f"Rules={len(config.get('confluence_rules') or [])} • "
            f"Min valid={int(config.get('min_valid_confluences', 1))} • "
            f"Trigger TF={trigger_timeframe} • {otf_caption}"
        )
    return (
        f"Trigger={config.get('trigger')} • Direction={config.get('direction')} • "
        f"Confluences={config.get('min_confluences')}–{config.get('max_confluences')} • "
        f"Trigger TF={trigger_timeframe} • {otf_caption}"
    )


def load_dataset(
    path: str | Path,
    *,
    instrument: str = "ES",
    source_timezone: str | None = None,
    exchange_timezone: str | None = None,
    format_profile: str = "canonical",
) -> pd.DataFrame:
    """Load an explicit vendor profile into canonical, session-tagged OHLCV."""
    inst = _instrument(instrument)
    target_timezone = exchange_timezone or inst.exchange_tz
    data = load_ohlcv(
        Path(path),
        source_tz=source_timezone,
        target_tz=target_timezone,
        format_profile=format_profile,
    )
    report = validate_ohlcv(data)
    fatal_codes = {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
    fatal_messages = [issue.message for issue in report.issues if issue.code in fatal_codes]
    if fatal_messages:
        raise ValueError("Dataset validation failed: " + "; ".join(fatal_messages))
    return tag_session(data, instrument)


def _named_prior_profile_from_setup(setup: Mapping[str, Any] | None) -> list[str]:
    """Collect prior-profile VA tokens named by a setup (selected / anchor / rules)."""
    if not setup:
        return []
    names: list[object] = []
    names.extend(setup.get("selected_levels") or [])
    anchor = setup.get("anchor_level")
    if anchor:
        names.append(anchor)
    for rule in setup.get("confluence_rules") or []:
        if isinstance(rule, Mapping) and rule.get("level"):
            names.append(rule.get("level"))
    return named_prior_profile_tokens(names)


def _require_ticks_for_named_va(
    dataset: Mapping[str, Any],
    setup: Mapping[str, Any] | None,
) -> None:
    """Layer-1: named VA without tick files or a prior-profile table refuses."""
    tokens = _named_prior_profile_from_setup(setup)
    if not tokens:
        return
    if dataset_has_tick_inputs(dict(dataset)):
        return
    raise ValueError(f"VA requires ticks: dataset.tick_paths is missing or empty (named {tokens})")


def _resolve_dataset_tick_paths(
    dataset: Mapping[str, Any],
    *,
    base_directory: str | Path,
) -> list[Path] | None:
    raw = dataset.get("tick_paths")
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("dataset.tick_paths must be a list of path strings")
    resolved: list[Path] = []
    for item in raw:
        path = Path(item)
        if not path.is_absolute():
            path = Path(base_directory) / path
        resolved.append(path)
    return resolved or None


def _resolve_prior_profile_table(
    *,
    instrument: str,
    settings: Mapping[str, Any],
    tick_paths: list[Path] | None,
    tick_format_profile: str | None,
    prior_profile_table: PriorProfileTable | None,
    prior_profile_table_path: str | Path | None,
    tick_source_id: str | None,
) -> tuple[PriorProfileTable | None, str]:
    """Load a prebuilt table, else build from tick paths. Never both."""
    if prior_profile_table is not None:
        return prior_profile_table, tick_source_id or compute_table_source_id(prior_profile_table)
    if prior_profile_table_path:
        table = PriorProfileTable.from_parquet(prior_profile_table_path)
        if tick_source_id:
            source_id = tick_source_id
        else:
            parquet = Path(prior_profile_table_path)
            source_id = (
                compute_table_path_source_id(parquet)
                if parquet.is_file()
                else compute_table_source_id(table)
            )
        return table, source_id
    if tick_paths:
        profile = resolve_tick_format_profile(tick_format_profile)
        table = build_prior_profile_table_from_paths(
            tick_paths,
            instrument=instrument,
            value_area_pct=float(settings["value_area_pct"]),
            prior_day_aggregation_ticks=int(settings["prior_day_profile_aggregation_ticks"]),
            prior_week_aggregation_ticks=int(settings["prior_week_profile_aggregation_ticks"]),
            prior_month_aggregation_ticks=int(settings["prior_month_profile_aggregation_ticks"]),
            format_profile=profile,
        )
        source_id = tick_source_id or compute_tick_source_id(tick_paths, format_profile=profile)
        return table, source_id
    return None, tick_source_id or TICK_SOURCE_NONE


def compute_levels(
    data: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
    cache_policy: str = "off",
    data_identity: DataIdentity | Mapping[str, Any] | None = None,
    store_root: str | Path | None = None,
    tick_paths: list[str | Path] | None = None,
    tick_format_profile: str | None = None,
    prior_profile_table: PriorProfileTable | None = None,
    prior_profile_table_path: str | Path | None = None,
    tick_source_id: str | None = None,
) -> LevelsResult:
    """Compute UI-equivalent levels without reading or writing session state.

    ``cache_policy`` defaults to ``off`` (legacy cold). ``read`` / ``read_write``
    reuse verified levels artifacts when a ``data_identity`` is supplied or can
    be derived. Cache misses never raise; they fall through to cold compute.
    """
    _instrument(instrument)
    settings = normalize_levels_config(config, instrument=instrument)
    table, resolved_tick_source_id = _resolve_prior_profile_table(
        instrument=instrument,
        settings=settings,
        tick_paths=[Path(path) for path in tick_paths] if tick_paths else None,
        tick_format_profile=tick_format_profile,
        prior_profile_table=prior_profile_table,
        prior_profile_table_path=prior_profile_table_path,
        tick_source_id=tick_source_id,
    )
    settings = attach_tick_identity(settings, tick_source_id=resolved_tick_source_id)
    policy = normalize_cache_policy(cache_policy)
    cache_status = "bypassed"
    cache_detail: str | None = None

    resolved_identity: DataIdentity | None = None
    if isinstance(data_identity, DataIdentity):
        resolved_identity = data_identity
    elif isinstance(data_identity, Mapping):
        resolved_identity = DataIdentity.from_dict(data_identity)

    if policy != "off" and resolved_identity is not None:
        levels_identity = LevelsIdentity.from_normalized(resolved_identity, settings)
        cached = read_verified_levels_artifact(levels_identity, store_root=store_root)
        if isinstance(cached, LevelsArtifact):
            return {
                "levels": cached.levels,
                "session_levels": cached.session_levels,
                "levels_settings": dict(cached.levels_settings),
                "cache_status": "hit",
            }
        cache_status = "miss"
        cache_detail = cached.reason if isinstance(cached, ArtifactMiss) else None

    kwargs = {
        _LEVEL_ARGUMENT_MAP.get(key, key): value
        for key, value in settings.items()
        if key != "instrument" and key not in LEVELS_TICK_IDENTITY_KEYS
    }
    levels = compute_all_levels(
        data,
        instrument=instrument,
        prior_profile_table=table,
        **kwargs,
    )
    session_levels = compute_session_levels(
        data,
        instrument=instrument,
        opening_range_minutes=int(settings["opening_range_minutes"]),
    )
    if policy == "read_write" and resolved_identity is not None:
        levels_identity = LevelsIdentity.from_normalized(resolved_identity, settings)
        write_levels_artifact(
            levels_identity,
            levels,
            session_levels,
            levels_settings=settings,
            store_root=store_root,
        )
        cache_status = "written" if cache_status == "miss" else "written"

    result: dict[str, Any] = {
        "levels": levels,
        "session_levels": session_levels,
        "levels_settings": settings,
    }
    if policy != "off":
        result["cache_status"] = cache_status
        if cache_detail is not None:
            result["cache_detail"] = cache_detail
    return result  # type: ignore[return-value]


def build_setup(config: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate a setup using the same library contract as the UI."""
    executable_config = {
        key: value for key, value in dict(config).items() if key in _SETUP_EXECUTION_KEYS
    }
    try:
        setup = build_setup_config(**executable_config)
    except TypeError as exc:
        raise ValueError(f"Invalid setup configuration: {exc}") from exc
    errors = validate_setup_config(setup)
    if errors:
        raise ValueError("Invalid setup configuration: " + "; ".join(errors))
    return setup


def _require_level_columns(levels: pd.DataFrame, names: list[str]) -> None:
    """Fail closed when a setup names columns absent from the levels frame.

    Names are stringified before membership and sorting so mixed/unhashable
    ``selected_levels`` items raise this ``ValueError`` (same wording as
    anchor-rules) instead of ``TypeError``. Exact names are required; do not
    strip — a padded token must not silently match a live column and then be
    dropped by ``detect_confluence_zones``.
    """
    missing = sorted({str(column) for column in names if str(column) not in levels.columns})
    if missing:
        raise ValueError(f"Setup references unavailable level columns: {missing}")


def generate_signals(
    levels: pd.DataFrame,
    setup: Mapping[str, Any],
    *,
    instrument: str | None = None,
) -> SignalsResult:
    """Generate zones, naked flags, and candidate signals from one setup."""
    setup_config = dict(setup)
    errors = validate_setup_config(setup_config)
    if errors:
        raise ValueError("Invalid setup configuration: " + "; ".join(errors))
    instrument_name = instrument or str(setup_config.get("instrument", "ES"))
    inst = _instrument(instrument_name)
    mode = str(setup_config.get("confluence_mode", "global_cluster"))
    selected_levels = list(setup_config.get("selected_levels", []))

    if mode == "global_cluster":
        _require_level_columns(levels, selected_levels)
        zones = detect_confluence_zones(
            levels,
            level_columns=selected_levels,
            tick_size=inst.tick_size,
            tolerance_ticks=float(setup_config["tolerance_ticks"]),
            min_confluences=int(setup_config["min_confluences"]),
            max_confluences=int(setup_config["max_confluences"]),
        )
        naked_level_columns = selected_levels
    elif mode == "anchor_rules":
        anchor_level = str(setup_config.get("anchor_level") or "")
        rules = list(setup_config.get("confluence_rules", []))
        referenced = [anchor_level, *(str(rule.get("level", "")) for rule in rules)]
        _require_level_columns(levels, referenced)
        zones = detect_anchor_confluence_zones(
            levels,
            anchor_level=anchor_level,
            confluence_rules=rules,
            tick_size=inst.tick_size,
            min_valid_confluences=int(setup_config.get("min_valid_confluences", 1)),
        )
        naked_level_columns = list(dict.fromkeys(referenced))
    else:
        raise ValueError(f"Unsupported confluence mode: {mode!r}")

    naked_flags = flag_naked_levels(
        levels,
        level_columns=naked_level_columns,
        tick_size=inst.tick_size,
        touch_tolerance_ticks=0,
    )
    trigger_params = dict(setup_config.get("trigger_params") or {})
    if setup_config["trigger"] == "3c":
        trigger_params["_source_mode"] = mode
    signals = _generate_signals(
        levels,
        zones=zones,
        trigger=str(setup_config["trigger"]),
        direction=str(setup_config["direction"]),
        tick_size=inst.tick_size,
        trigger_timeframe=str(setup_config.get("trigger_timeframe", "base")),
        trigger_params=trigger_params,
        naked_only=bool(setup_config.get("naked_only", False)),
        naked_flags=naked_flags if setup_config.get("naked_only", False) else None,
        naked_requirement=str(setup_config.get("naked_requirement", "any")),
    )
    signals = signals.copy()
    signals["setup_name"] = setup_config.get("name", "Untitled setup")
    signal_settings = _normalize_signal_settings_for_hash(
        {
            "confluence_mode": mode,
            "selected_levels": selected_levels,
            "anchor_level": setup_config.get("anchor_level"),
            "confluence_rules": list(setup_config.get("confluence_rules", [])),
            "min_valid_confluences": int(setup_config.get("min_valid_confluences", 1)),
            "tolerance_ticks": float(setup_config.get("tolerance_ticks", 0.0)),
            "min_confluences": int(setup_config.get("min_confluences", 1)),
            "max_confluences": int(setup_config.get("max_confluences", 5)),
            "naked_only": bool(setup_config.get("naked_only", False)),
            "naked_requirement": str(setup_config.get("naked_requirement", "any")),
            "trigger": str(setup_config["trigger"]),
            "trigger_timeframe": str(setup_config.get("trigger_timeframe", "base")),
            "direction": str(setup_config["direction"]),
            "trigger_params": dict(setup_config.get("trigger_params") or {}),
            "use_saved_setup": True,
            "setup_snapshot": setup_config,
        }
    )
    return {
        "signals": signals,
        "confluence_zones": zones,
        "naked_flags": naked_flags,
        "signal_settings": signal_settings,
        "signal_settings_hash": compute_signal_settings_hash(signal_settings),
    }


def run_backtest(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any] | None = None,
    signal_settings: Mapping[str, Any] | None = None,
    last_signal_setup: Mapping[str, Any] | None = None,
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> BacktestResult:
    """Run the UI backtest composition, including the shared OTF pre-filter."""
    inst = _instrument(instrument)
    settings = _merge_known(_BACKTEST_DEFAULTS, config, section="backtest")
    session_timezone = settings["session_timezone"] or inst.exchange_tz
    try:
        entry_window = normalize_entry_window(
            settings.get("entry_window"),
            exchange_tz=inst.exchange_tz,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid backtest.entry_window: {exc}") from exc
    # Engine default remains None when disabled (legacy-identical path).
    simulate_entry_window = entry_window if entry_window.get("enabled") else None
    otf = apply_configured_otf_filter(
        source_df=data,
        candidate_signals=signals,
        setup_config=dict(setup_config or {}),
        session_timezone=inst.exchange_tz,
        eth_start=inst.eth_start,
        signal_settings=dict(signal_settings or {}),
        last_signal_setup=dict(last_signal_setup or {}),
    )
    simulation = simulate_trades(
        df=data,
        signals=otf.accepted_signals,
        tick_size=inst.tick_size,
        point_value=inst.point_value,
        stop_loss_ticks=settings["stop_loss_ticks"],
        take_profit_ticks=settings["take_profit_ticks"],
        max_holding_bars=settings["max_holding_bars"],
        allow_same_bar_exit=bool(settings["allow_same_bar_exit"]),
        commission_per_side=float(settings["commission_per_side"]),
        slippage_ticks=float(settings["slippage_ticks"]),
        flat_by_session_close=bool(settings["flat_by_session_close"]),
        session_close_time=settings["session_close_time"],
        session_timezone=session_timezone if settings["flat_by_session_close"] else None,
        no_new_entries_after=settings["no_new_entries_after"],
        exposure_policy=str(settings["exposure_policy"]),
        cooldown_bars_after_exit=int(settings["cooldown_bars_after_exit"]),
        intrabar_model=str(settings["intrabar_model"]),
        subtimeframe_data=subtimeframe_data,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
        breakeven_after_r=settings["breakeven_after_r"],
        trailing_after_r=settings["trailing_after_r"],
        trailing_distance_ticks=settings["trailing_distance_ticks"],
        entry_window=simulate_entry_window,
        entry_window_exchange_tz=inst.exchange_tz,
        same_bar_opposite_direction=_require_same_bar_opposite_direction(
            settings["same_bar_opposite_direction"]
        ),
        return_result=True,
    )
    trades = simulation.trades
    skipped = simulation.skipped_signals
    return {
        "trades": trades,
        "trade_summary": summarize_trades(trades),
        "equity_curve": equity_curve(trades),
        "skipped_signals": skipped,
        "accepted_signals": otf.accepted_signals,
        "rejected_signals": otf.rejected_signals,
        "otf_filter_summary": otf.to_summary_dict(),
        "intrabar_diagnostic": simulation.intrabar_diagnostic,
        "exit_management_diagnostic": simulation.exit_management_diagnostic,
        "direction_collision_diagnostic": simulation.direction_collision_diagnostic,
        "entry_window": entry_window,
    }


def run_noise_test(
    data: pd.DataFrame,
    baseline_trades: pd.DataFrame,
    *,
    instrument: str = "ES",
    levels_config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any],
    backtest_config: Mapping[str, Any] | None = None,
    noise_config: Mapping[str, Any] | None = None,
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
    prior_profile_table: PriorProfileTable | None = None,
    prior_profile_table_path: str | Path | None = None,
    tick_source_id: str | None = None,
) -> dict[str, Any]:
    """Run R16 replicas through the canonical levels-to-backtest composition.

    Parent OHLC bars are perturbed. Lower-timeframe R12 data remains pinned so
    the test does not fabricate an unsupported sub-bar reconstruction.
    Tick VA (when named) is joined from the same prior-profile table — replicas
    must not omit the nine columns and trip LC4.
    """
    setup = build_setup(setup_config)
    settings = dict(noise_config or {})
    settings.pop("enabled", None)
    replica_levels_config = {
        key: value for key, value in dict(levels_config or {}).items() if key != "instrument"
    }

    def _run_replica(perturbed: pd.DataFrame) -> pd.DataFrame:
        levels = compute_levels(
            perturbed,
            instrument=instrument,
            config=replica_levels_config,
            prior_profile_table=prior_profile_table,
            prior_profile_table_path=prior_profile_table_path,
            tick_source_id=tick_source_id,
        )
        signals = generate_signals(levels["levels"], setup, instrument=instrument)
        backtest = run_backtest(
            levels["levels"],
            signals["signals"],
            instrument=instrument,
            config=backtest_config,
            setup_config=setup,
            signal_settings=signals["signal_settings"],
            last_signal_setup=setup,
            subtimeframe_data=subtimeframe_data,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
        )
        return backtest["trades"]

    return noise_summary(
        data,
        baseline_trades,
        replica_runner=_run_replica,
        **settings,
    )


def run_sensitivity_profile(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    tick_size: float,
    point_value: float,
    grid: pd.DataFrame,
    execution_kwargs: Mapping[str, Any] | None = None,
    selected_grid_metric: str = "expectancy_r",
    selected_min_trades: int = 1,
    sensitivity_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run R19 OAT profiling around the selected Grid Search cell."""
    if grid is None or grid.empty:
        raise ValueError("grid results are required for R19 sensitivity profiling")
    selected = best_grid_result(
        grid,
        metric=selected_grid_metric,
        min_trades=selected_min_trades,
    )
    if selected is None:
        raise ValueError("No grid cell passes the R19 selection rule.")
    settings = dict(sensitivity_config or {})
    settings.pop("enabled", None)
    _validate_keys(
        {"enabled": True, **settings},
        _SENSITIVITY_KEYS,
        section="validation.sensitivity",
    )
    return sensitivity_summary(
        df,
        signals,
        tick_size=tick_size,
        point_value=point_value,
        selected_cell=selected,
        execution_kwargs=execution_kwargs,
        **settings,
    )


def run_portfolio_analysis(
    setup_trades: Mapping[str, pd.DataFrame],
    *,
    instrument: str,
    config: Mapping[str, Any] | None = None,
    bar_count: int | None = None,
) -> PortfolioResult:
    """Run additive R21 analysis over independent completed setup trade frames."""
    settings = dict(config or {})
    allowed = {"exposure_policy", "cooldown_bars_after_exit"}
    _validate_keys(settings, allowed, section="portfolio")
    summary = portfolio_summary(
        setup_trades,
        instrument=instrument,
        exposure_policy=str(settings.get("exposure_policy", "allow_all")),
        cooldown_bars_after_exit=int(settings.get("cooldown_bars_after_exit", 0)),
        bar_count=bar_count,
    )
    return {
        "portfolio_summary": {
            key: value
            for key, value in summary.items()
            if key
            not in {
                "portfolio_trades",
                "portfolio_skipped_trades",
                "portfolio_equity_curve",
                "portfolio_correlation",
                "portfolio_drawdown_correlation",
                "portfolio_marginal_contribution",
            }
        },
        "portfolio_config": summary["config"],
        **{
            key: summary[key]
            for key in (
                "portfolio_trades",
                "portfolio_skipped_trades",
                "portfolio_equity_curve",
                "portfolio_correlation",
                "portfolio_drawdown_correlation",
                "portfolio_marginal_contribution",
            )
        },
    }


def run_grid(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any] | None = None,
    signal_settings: Mapping[str, Any] | None = None,
    last_signal_setup: Mapping[str, Any] | None = None,
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> GridResult:
    """Run the UI grid composition, including one shared OTF pre-filter."""
    inst = _instrument(instrument)
    settings = _merge_known(_GRID_DEFAULTS, config, section="grid")
    session_timezone = settings["session_timezone"] or inst.exchange_tz
    try:
        entry_window = normalize_entry_window(
            settings.get("entry_window"),
            exchange_tz=inst.exchange_tz,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid grid.entry_window: {exc}") from exc
    simulate_entry_window = entry_window if entry_window.get("enabled") else None
    otf = apply_configured_otf_filter(
        source_df=data,
        candidate_signals=signals,
        setup_config=dict(setup_config or {}),
        session_timezone=inst.exchange_tz,
        eth_start=inst.eth_start,
        signal_settings=dict(signal_settings or {}),
        last_signal_setup=dict(last_signal_setup or {}),
    )
    grid = run_sl_tp_grid(
        df=data,
        signals=otf.accepted_signals,
        tick_size=inst.tick_size,
        point_value=inst.point_value,
        stop_loss_ticks_values=list(settings["stop_loss_ticks_values"]),
        take_profit_ticks_values=list(settings["take_profit_ticks_values"]),
        max_holding_bars=settings["max_holding_bars"],
        allow_same_bar_exit=bool(settings["allow_same_bar_exit"]),
        commission_per_side=float(settings["commission_per_side"]),
        slippage_ticks=float(settings["slippage_ticks"]),
        flat_by_session_close=bool(settings["flat_by_session_close"]),
        session_close_time=settings["session_close_time"],
        session_timezone=session_timezone if settings["flat_by_session_close"] else None,
        no_new_entries_after=settings["no_new_entries_after"],
        exposure_policy=str(settings["exposure_policy"]),
        cooldown_bars_after_exit=int(settings["cooldown_bars_after_exit"]),
        intrabar_model=str(settings["intrabar_model"]),
        subtimeframe_data=subtimeframe_data,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
        breakeven_after_r_values=list(settings["breakeven_after_r_values"]),
        trailing_after_r_values=list(settings["trailing_after_r_values"]),
        trailing_distance_ticks_values=list(settings["trailing_distance_ticks_values"]),
        max_grid_cells=int(settings["max_grid_cells"]),
        entry_window=simulate_entry_window,
        entry_window_exchange_tz=inst.exchange_tz,
    )
    best = best_grid_result(
        grid,
        metric=str(settings["ranking_metric"]),
        min_trades=int(settings["min_trades"]),
    )
    return {
        "grid_results": grid,
        "best_grid_result": None if best is None else best.to_dict(),
        "accepted_signals": otf.accepted_signals,
        "rejected_signals": otf.rejected_signals,
        "otf_filter_summary": otf.to_summary_dict(),
        "entry_window": entry_window,
    }


def run_walk_forward(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any],
    execution_config: Mapping[str, Any] | None = None,
    otf_config: Mapping[str, Any] | None = None,
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> WalkForwardAnalysisResult:
    """Run R14 session/bar WFA with optional robustness matrix."""
    inst = _instrument(instrument)
    settings = dict(config)
    execution = dict(execution_config or {})
    matrix_config = settings.pop("matrix", None)
    sl_values = list(
        settings.pop("stop_loss_ticks_values", [execution.get("stop_loss_ticks", 8.0)])
    )
    tp_values = list(
        settings.pop("take_profit_ticks_values", [execution.get("take_profit_ticks", 16.0)])
    )
    fold_mode = str(settings.get("fold_mode", "bars"))
    try:
        walk_entry_window = normalize_entry_window(
            execution.get("entry_window"),
            exchange_tz=inst.exchange_tz,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid walk_forward execution entry_window: {exc}") from exc
    simulate_entry_window = walk_entry_window if walk_entry_window.get("enabled") else None
    detailed = run_walk_forward_sl_tp(
        df=data,
        signals=signals,
        tick_size=inst.tick_size,
        point_value=inst.point_value,
        stop_loss_ticks_values=sl_values,
        take_profit_ticks_values=tp_values,
        train_bars=int(settings.get("train_bars", 500 if fold_mode == "bars" else 1)),
        test_bars=int(settings.get("test_bars", 100 if fold_mode == "bars" else 1)),
        step_bars=settings.get("step_bars"),
        ranking_metric=str(settings.get("ranking_metric", "expectancy_r")),
        min_train_trades=int(settings.get("min_train_trades", 1)),
        max_holding_bars=execution.get("max_holding_bars"),
        allow_same_bar_exit=bool(execution.get("allow_same_bar_exit", True)),
        commission_per_side=float(execution.get("commission_per_side", 0.0)),
        slippage_ticks=float(execution.get("slippage_ticks", 0.0)),
        flat_by_session_close=bool(execution.get("flat_by_session_close", False)),
        session_close_time=execution.get("session_close_time"),
        session_timezone=execution.get("session_timezone"),
        no_new_entries_after=execution.get("no_new_entries_after"),
        exposure_policy=str(execution.get("exposure_policy", "allow_all")),
        cooldown_bars_after_exit=int(execution.get("cooldown_bars_after_exit", 0)),
        otf_config=dict(otf_config or {}),
        intrabar_model=str(execution.get("intrabar_model", "sl_first")),
        subtimeframe_data=subtimeframe_data,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
        breakeven_after_r_values=list(execution.get("breakeven_after_r_values", [None])),
        trailing_after_r_values=list(execution.get("trailing_after_r_values", [None])),
        trailing_distance_ticks_values=list(
            execution.get("trailing_distance_ticks_values", [None])
        ),
        max_grid_cells=int(execution.get("max_grid_cells", 500)),
        fold_mode=fold_mode,
        window_mode=str(settings.get("window_mode", "rolling")),
        train_sessions=settings.get("train_sessions"),
        test_sessions=settings.get("test_sessions"),
        step_sessions=settings.get("step_sessions"),
        exchange_timezone=inst.exchange_tz,
        eth_start=inst.eth_start,
        overlap_policy=str(settings.get("overlap_policy", "reject")),
        otf_history_policy=settings.get("otf_history_policy"),
        return_result=True,
        entry_window=simulate_entry_window,
        entry_window_exchange_tz=inst.exchange_tz,
    )
    output: WalkForwardAnalysisResult = {
        "walk_forward_results": detailed.folds,
        "walk_forward_summary": detailed.summary,
        "walk_forward_config": detailed.config,
        "walk_forward_oos_trades": detailed.oos_trades,
        "walk_forward_stitched_equity": detailed.stitched_equity,
        "walk_forward_warnings": list(detailed.warnings),
    }
    if isinstance(matrix_config, Mapping) and matrix_config.get("enabled", False):
        for key in ("train_session_values", "test_session_values"):
            if key not in matrix_config:
                raise ValueError(f"walk_forward.matrix.{key} is required when enabled")
        matrix = run_wfa_matrix(
            df=data,
            signals=signals,
            tick_size=inst.tick_size,
            point_value=inst.point_value,
            stop_loss_ticks_values=sl_values,
            take_profit_ticks_values=tp_values,
            train_session_values=list(matrix_config["train_session_values"]),
            test_session_values=list(matrix_config["test_session_values"]),
            matrix_metric=str(matrix_config.get("matrix_metric", "median_test_expectancy_r")),
            max_matrix_cells=int(matrix_config.get("max_matrix_cells", 25)),
            window_mode=str(settings.get("window_mode", "rolling")),
            exchange_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
            max_holding_bars=execution.get("max_holding_bars"),
            allow_same_bar_exit=bool(execution.get("allow_same_bar_exit", True)),
            commission_per_side=float(execution.get("commission_per_side", 0.0)),
            slippage_ticks=float(execution.get("slippage_ticks", 0.0)),
            flat_by_session_close=bool(execution.get("flat_by_session_close", False)),
            session_close_time=execution.get("session_close_time"),
            session_timezone=execution.get("session_timezone"),
            no_new_entries_after=execution.get("no_new_entries_after"),
            exposure_policy=str(execution.get("exposure_policy", "allow_all")),
            cooldown_bars_after_exit=int(execution.get("cooldown_bars_after_exit", 0)),
            otf_config=dict(otf_config or {}),
            intrabar_model=str(execution.get("intrabar_model", "sl_first")),
            subtimeframe_data=subtimeframe_data,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            breakeven_after_r_values=list(execution.get("breakeven_after_r_values", [None])),
            trailing_after_r_values=list(execution.get("trailing_after_r_values", [None])),
            trailing_distance_ticks_values=list(
                execution.get("trailing_distance_ticks_values", [None])
            ),
            max_grid_cells=int(execution.get("max_grid_cells", 500)),
            overlap_policy=str(settings.get("overlap_policy", "reject")),
            # Matrix cells must use the same OTF history policy as the primary WFO.
            otf_history_policy=settings.get("otf_history_policy"),
            entry_window=simulate_entry_window,
            entry_window_exchange_tz=inst.exchange_tz,
        )
        output["wfa_matrix"] = matrix
        output["wfa_matrix_config"] = {
            **dict(matrix_config),
            "otf_history_policy": detailed.config.get("otf_history_policy"),
        }
    return output


def run_validation(
    trades: pd.DataFrame,
    *,
    grid: pd.DataFrame | None = None,
    tick_size: float | None = None,
    config: Mapping[str, Any] | None = None,
    df: pd.DataFrame | None = None,
    signals: pd.DataFrame | None = None,
    point_value: float | None = None,
    execution_kwargs: Mapping[str, Any] | None = None,
    selected_grid_metric: str = "expectancy_r",
    selected_min_trades: int = 1,
    raw_data: pd.DataFrame | None = None,
    levels_config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any] | None = None,
    backtest_config: Mapping[str, Any] | None = None,
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
    prior_profile_table: PriorProfileTable | None = None,
    prior_profile_table_path: str | Path | None = None,
    tick_source_id: str | None = None,
) -> ValidationResult:
    """Run deterministic validation plus optional R10/R11 diagnostics."""
    raw = dict(config or {})
    excursion_config = raw.pop("excursion", None)
    monte_carlo_config = raw.pop("monte_carlo", None)
    overfitting_config = raw.pop("overfitting", None)
    noise_config = raw.pop("noise", None)
    sensitivity_config = raw.pop("sensitivity", None)
    settings = _merge_known(_VALIDATION_DEFAULTS, raw, section="validation")
    _validate_random_state(settings["random_state"], section="validation")
    result: ValidationResult = {
        "validation_summary": validation_summary(trades, grid=grid, **settings)
    }

    if excursion_config is not None and not isinstance(excursion_config, Mapping):
        raise ValueError("validation.excursion must be a mapping")
    if isinstance(excursion_config, Mapping) and excursion_config.get("enabled", True):
        if tick_size is None:
            raise ValueError("tick_size is required when excursion validation is enabled")
        _validate_keys(
            excursion_config,
            _EXCURSION_KEYS,
            section="validation.excursion",
        )
        excursion_settings = {
            key: value for key, value in excursion_config.items() if key != "enabled"
        }
        excursion = excursion_summary(trades, tick_size, **excursion_settings)
        result.update(
            {
                "excursion_summary": excursion,
                "excursion_config": excursion["config"],
                "excursion_grouped_summary": pd.DataFrame(excursion["grouped"]),
                "excursion_calibration_grid": pd.DataFrame(excursion["calibration_grid"]),
                "excursion_quadrant_summary": pd.DataFrame(excursion["quadrants"]),
            }
        )

    if monte_carlo_config is not None and not isinstance(monte_carlo_config, Mapping):
        raise ValueError("validation.monte_carlo must be a mapping")
    if isinstance(monte_carlo_config, Mapping) and monte_carlo_config.get("enabled", True):
        monte_carlo_settings = {
            key: value for key, value in monte_carlo_config.items() if key != "enabled"
        }
        _validate_keys(
            monte_carlo_config,
            _MONTE_CARLO_KEYS,
            section="validation.monte_carlo",
        )
        _validate_random_state(
            monte_carlo_settings.get("random_state", 42),
            section="validation.monte_carlo",
        )
        monte_carlo = monte_carlo_summary(trades, **monte_carlo_settings)
        result.update(
            {
                "monte_carlo_summary": monte_carlo,
                "monte_carlo_config": monte_carlo["config"],
            }
        )
    if noise_config is not None and not isinstance(noise_config, Mapping):
        raise ValueError("validation.noise must be a mapping")
    if isinstance(noise_config, Mapping) and noise_config.get("enabled", True):
        if raw_data is None or setup_config is None:
            raise ValueError("raw_data and setup_config are required for R16 noise diagnostics")
        _validate_keys(noise_config, _NOISE_KEYS, section="validation.noise")
        noise_settings = {key: value for key, value in noise_config.items() if key != "enabled"}
        _validate_random_state(
            noise_settings.get("random_state", 42),
            section="validation.noise",
        )
        summary = run_noise_test(
            raw_data,
            trades,
            instrument=str(setup_config.get("instrument", "ES")),
            levels_config=levels_config,
            setup_config=setup_config,
            backtest_config=backtest_config,
            noise_config=noise_settings,
            subtimeframe_data=subtimeframe_data,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            prior_profile_table=prior_profile_table,
            prior_profile_table_path=prior_profile_table_path,
            tick_source_id=tick_source_id,
        )
        result.update({"noise_summary": summary, "noise_config": summary["config"]})
    if sensitivity_config is not None and not isinstance(sensitivity_config, Mapping):
        raise ValueError("validation.sensitivity must be a mapping")
    if isinstance(sensitivity_config, Mapping) and sensitivity_config.get("enabled", True):
        if df is None or signals is None or tick_size is None or point_value is None:
            raise ValueError(
                "df, signals, tick_size, and point_value are required for R19 sensitivity"
            )
        sensitivity_settings = {
            key: value for key, value in sensitivity_config.items() if key != "enabled"
        }
        _validate_keys(
            sensitivity_config,
            _SENSITIVITY_KEYS,
            section="validation.sensitivity",
        )
        summary = run_sensitivity_profile(
            df,
            signals,
            tick_size=tick_size,
            point_value=point_value,
            grid=grid if grid is not None else pd.DataFrame(),
            execution_kwargs=execution_kwargs,
            selected_grid_metric=selected_grid_metric,
            selected_min_trades=selected_min_trades,
            sensitivity_config=sensitivity_settings,
        )
        result.update(
            {
                "sensitivity_summary": summary,
                "sensitivity_config": summary["config"],
            }
        )
    if overfitting_config is not None and not isinstance(overfitting_config, Mapping):
        raise ValueError("validation.overfitting must be a mapping")
    if isinstance(overfitting_config, Mapping) and overfitting_config.get("enabled", True):
        if df is None or signals is None or tick_size is None or point_value is None:
            raise ValueError(
                "df, signals, tick_size, and point_value are required for R15 overfitting"
            )
        if grid is None or grid.empty:
            raise ValueError("grid results are required for R15 overfitting")
        overfit_settings = {
            key: value for key, value in overfitting_config.items() if key != "enabled"
        }
        _validate_keys(
            overfitting_config,
            _OVERFITTING_KEYS,
            section="validation.overfitting",
        )
        sequence_result = grid_trade_sequences(
            df,
            signals,
            tick_size=tick_size,
            point_value=point_value,
            grid=grid,
            execution_kwargs=execution_kwargs,
        )
        candidate_grid = sequence_result.grid_results
        selected = best_grid_result(
            candidate_grid,
            metric=selected_grid_metric,
            min_trades=selected_min_trades,
        )
        if selected is None:
            raise ValueError(
                "No replayed grid cell passes the R15 selection rule; "
                "cannot run overfitting diagnostics."
            )
        selected_key = (
            float(selected["stop_loss_ticks"]),
            float(selected["take_profit_ticks"]),
            None
            if pd.isna(selected.get("breakeven_after_r"))
            else float(selected.get("breakeven_after_r")),
            None
            if pd.isna(selected.get("trailing_after_r"))
            else float(selected.get("trailing_after_r")),
            None
            if pd.isna(selected.get("trailing_distance_ticks"))
            else float(selected.get("trailing_distance_ticks")),
        )
        selected_trades = sequence_result.cell_trades.get(selected_key)
        if selected_trades is None:
            raise ValueError(
                "The selected R15 grid cell has no replayed trade sequence; "
                "cannot run overfitting diagnostics."
            )
        summary = overfitting_summary(
            selected_trades=selected_trades,
            cell_trades=sequence_result.cell_trades,
            grid_results=candidate_grid,
            df=df,
            tick_size=tick_size,
            point_value=point_value,
            execution_kwargs=execution_kwargs,
            selected_grid_metric=selected_grid_metric,
            selected_min_trades=selected_min_trades,
            **overfit_settings,
        )
        result.update(
            {
                "overfitting_summary": summary,
                "overfitting_config": summary["config"],
            }
        )
    return result


def run_time_analysis(
    trades: pd.DataFrame,
    *,
    group_col: str = "entry_rth_segment",
    bucket_timezone: str = "America/New_York",
    min_trades: int = 10,
) -> pd.DataFrame:
    """Return descriptive grouped time analysis without re-simulating trades."""
    bucketed = add_time_buckets(trades, bucket_tz=bucket_timezone)
    return summarize_by_group(bucketed, group_col, min_trades=min_trades)


def preview_resampled_ohlcv(
    df: pd.DataFrame, *, timeframe: str, max_rows: int = 200
) -> pd.DataFrame:
    """Return a bounded read-only OHLCV resample preview."""
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be an integer from 1 to 1000.")
    return resample_ohlcv(df, timeframe).head(max_rows).reset_index(drop=True)


def validate_roll_assumptions(
    df: pd.DataFrame, *, contract_column: str = "contract", roll_method: str = "single_contract"
) -> dict[str, Any]:
    """Return read-only futures-roll metadata diagnostics."""
    resolved_column = contract_column
    if contract_column == "contract" and contract_column not in df.columns:
        resolved_column = detect_contract_column(df) or contract_column
    return validate_roll_metadata(df, contract_column=resolved_column, roll_method=roll_method)


def run_otf_validation(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    train_fraction: float = 0.7,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    setup_config: dict | None = None,
    signal_settings: dict | None = None,
    execution_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Run the fixed OTF validation matrix through the public facade."""
    config = _instrument(instrument)
    return run_otf_validation_matrix(
        source_df=df,
        candidate_signals=signals,
        tick_size=config.tick_size,
        point_value=config.point_value,
        stop_loss_ticks=stop_loss_ticks,
        take_profit_ticks=take_profit_ticks,
        train_fraction=train_fraction,
        session_timezone=session_timezone or config.exchange_tz,
        eth_start=eth_start or config.eth_start,
        setup_config=setup_config,
        signal_settings=signal_settings,
        execution_kwargs=execution_kwargs,
    )


def _load_experiment_data(
    *,
    dataset_path: Path,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str,
    dataset_config: Mapping[str, Any],
    cache_policy: str,
    store_root: str | Path | None,
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
) -> tuple[pd.DataFrame, DataIdentity, dict[str, Any]]:
    """Load canonical data with optional verified artifact reuse."""
    policy = normalize_cache_policy(cache_policy)
    data_stage: dict[str, Any] = {"status": "bypassed", "policy": policy}
    mode = str(ingestion_mode or "primary")

    if policy != "off":
        binding = read_source_data_binding(
            source_path=dataset_path,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
            ingestion_mode=mode,
            derivation_policy=derivation_policy,
            store_root=store_root,
        )
        if isinstance(binding, SourceDataBinding):
            artifact = read_verified_data_artifact(binding.identity, store_root=store_root)
            if isinstance(artifact, DataArtifact):
                data_stage = {
                    "status": "hit",
                    "policy": policy,
                    "binding_key": binding.binding_key,
                    "artifact_key": artifact.artifact_key,
                }
                return artifact.data, binding.identity, data_stage
            data_stage = {
                "status": "miss",
                "policy": policy,
                "reason": artifact.reason
                if isinstance(artifact, ArtifactMiss)
                else "artifact_miss",
                "binding_key": binding.binding_key,
            }
            invalidate_source_data_binding(
                source_path=dataset_path,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=format_profile,
                ingestion_mode=mode,
                derivation_policy=derivation_policy,
                store_root=store_root,
            )
        elif isinstance(binding, ArtifactMiss):
            data_stage = {
                "status": "miss",
                "policy": policy,
                "reason": binding.reason,
                "detail": binding.detail,
            }

    data = load_dataset(
        dataset_path,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )
    validation_report = validate_ohlcv(data)
    base_interval = format_interval(validation_report.inferred_interval)
    data_identity = DataIdentity.from_run_spec(
        data,
        dataset_config=dataset_config,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    if policy == "read_write":
        write_data_artifact(
            data_identity,
            data,
            ingestion_meta={
                "source_path": str(dataset_path),
                "format_profile": format_profile,
                "ingestion_mode": mode,
                "derivation_policy": derivation_policy,
            },
            store_root=store_root,
        )
        write_source_data_binding(
            source_path=dataset_path,
            identity=data_identity,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
            ingestion_mode=mode,
            derivation_policy=derivation_policy,
            store_root=store_root,
        )
        data_stage = {
            "status": "written",
            "policy": policy,
            "reason": data_stage.get("reason"),
            "detail": data_stage.get("detail"),
        }
    elif policy == "read" and data_stage.get("status") == "bypassed":
        data_stage = {"status": "miss", "policy": policy, "reason": "missing"}
    return data, data_identity, data_stage


def _load_15s_primary_experiment_data(
    *,
    dataset_path: Path,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str,
    dataset_config: Mapping[str, Any],
    cache_policy: str,
    store_root: str | Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame, DataIdentity, dict[str, Any], dict[str, Any]]:
    """Load a 15s source, derive observed 1m parents, and retain R12 source bars.

    Always re-derives from the source file so provenance stays source-truthful.
    OHLC-identical duplicate 15s opens are resolved (lowest volume kept) before
    derive; OHLC conflicts stay fail-closed. Sparse on-grid minutes are
    retained; only misaligned minutes are dropped.
    Source-index bindings include ``ingestion_mode`` / ``derivation_policy`` so
    a legacy primary binding for the same bytes cannot warm-cross into this
    path (or the reverse).
    """
    policy = normalize_cache_policy(cache_policy)
    ingestion_mode = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    derivation_policy = DERIVATION_POLICY_DEFAULT
    data_stage: dict[str, Any] = {"status": "bypassed", "policy": policy}
    inst = _instrument(instrument)

    source_raw = load_ohlcv(
        Path(dataset_path),
        source_tz=source_timezone,
        target_tz=exchange_timezone or inst.exchange_tz,
        format_profile=format_profile,
    )
    source_raw, source_duplicate_audit = prepare_15s_source_for_derivation(source_raw)

    derived = derive_complete_parent_ohlcv(source_raw)
    parent_report = validate_ohlcv(derived.parent_data)
    fatal_codes = {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
    parent_fatal = [issue.message for issue in parent_report.issues if issue.code in fatal_codes]
    if parent_fatal:
        raise ValueError("Derived one-minute validation failed: " + "; ".join(parent_fatal))

    parent = tag_session(derived.parent_data, instrument)
    source = tag_session(derived.source_data, instrument)
    prepare_subtimeframe_conservative_context(
        parent,
        source,
        tick_size=inst.tick_size,
        parent_interval=derived.parent_interval,
        sub_interval=derived.source_interval,
    )
    provenance = build_derivation_provenance(
        derived,
        format_profile=format_profile,
        source_duplicate_audit=source_duplicate_audit,
    )
    base_interval = format_interval(derived.parent_interval)
    data_identity = DataIdentity.from_run_spec(
        parent,
        dataset_config=dataset_config,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )

    if policy != "off":
        binding = read_source_data_binding(
            source_path=dataset_path,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
            ingestion_mode=ingestion_mode,
            derivation_policy=derivation_policy,
            store_root=store_root,
        )
        if isinstance(binding, SourceDataBinding):
            artifact = read_verified_data_artifact(binding.identity, store_root=store_root)
            if isinstance(artifact, DataArtifact):
                data_stage = {
                    "status": "hit",
                    "policy": policy,
                    "binding_key": binding.binding_key,
                    "artifact_key": artifact.artifact_key,
                }
                # Prefer the verified artifact frame when identity matches; the
                # freshly derived parent remains the R12 reconcile authority.
                if binding.identity.dataset_id() == data_identity.dataset_id():
                    parent = artifact.data
                    data_identity = binding.identity
                return parent, source, data_identity, data_stage, provenance
            data_stage = {
                "status": "miss",
                "policy": policy,
                "reason": artifact.reason
                if isinstance(artifact, ArtifactMiss)
                else "artifact_miss",
                "binding_key": binding.binding_key,
            }
            invalidate_source_data_binding(
                source_path=dataset_path,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=format_profile,
                ingestion_mode=ingestion_mode,
                derivation_policy=derivation_policy,
                store_root=store_root,
            )
        elif isinstance(binding, ArtifactMiss):
            data_stage = {
                "status": "miss",
                "policy": policy,
                "reason": binding.reason,
                "detail": binding.detail,
            }

    if policy == "read_write":
        write_data_artifact(
            data_identity,
            parent,
            ingestion_meta={
                "source_path": str(dataset_path),
                "format_profile": format_profile,
                "ingestion_mode": ingestion_mode,
                "derivation_policy": derivation_policy,
                "ingestion_provenance": provenance,
            },
            store_root=store_root,
        )
        write_source_data_binding(
            source_path=dataset_path,
            identity=data_identity,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
            ingestion_mode=ingestion_mode,
            derivation_policy=derivation_policy,
            store_root=store_root,
        )
        data_stage = {
            "status": "written",
            "policy": policy,
            "reason": data_stage.get("reason"),
            "detail": data_stage.get("detail"),
        }
    elif policy == "read" and data_stage.get("status") == "bypassed":
        data_stage = {"status": "miss", "policy": policy, "reason": "missing"}
    return parent, source, data_identity, data_stage, provenance


def run_experiment(
    spec: Mapping[str, Any],
    *,
    base_directory: str | Path = ".",
    execution_origin: str = "api",
    cache_policy: str = "off",
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Execute one version-1 experiment and return a bundle-ready plain dict.

    ``cache_policy`` defaults to ``off`` (legacy cold path). Pass ``read_write``
    to reuse/publish verified data and levels artifacts. Cache provenance is
    attached to the returned state but must not affect canonical bundle hashes.
    """
    validate_run_spec(spec)
    run = dict(spec)
    dataset_config = dict(run.get("dataset") or {})
    if "path" not in dataset_config:
        raise ValueError("Experiment dataset.path is required")
    _require_ticks_for_named_va(dataset_config, dict(run.get("setup") or {}))
    instrument = str(dataset_config.get("instrument", "ES"))
    inst = _instrument(instrument)
    dataset_path = Path(dataset_config["path"])
    if not dataset_path.is_absolute():
        dataset_path = Path(base_directory) / dataset_path
    source_timezone = dataset_config.get("source_timezone") or inst.exchange_tz
    exchange_timezone = dataset_config.get("exchange_timezone") or inst.exchange_tz
    format_profile = str(dataset_config.get("format_profile", "canonical"))
    origin = normalize_execution_origin(execution_origin)
    policy = normalize_cache_policy(cache_policy)
    ingestion_mode = str(dataset_config.get("ingestion_mode") or "primary")
    ingestion_provenance: dict[str, Any] | None = None

    subtimeframe_data: pd.DataFrame | None = None
    if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        data, subtimeframe_data, data_identity, data_stage, ingestion_provenance = (
            _load_15s_primary_experiment_data(
                dataset_path=dataset_path,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=format_profile,
                dataset_config=dataset_config,
                cache_policy=policy,
                store_root=store_root,
            )
        )
    else:
        data, data_identity, data_stage = _load_experiment_data(
            dataset_path=dataset_path,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
            dataset_config=dataset_config,
            cache_policy=policy,
            store_root=store_root,
            ingestion_mode="primary",
            derivation_policy=None,
        )
        subtimeframe_path_value = dataset_config.get("subtimeframe_path")
        if subtimeframe_path_value is not None:
            subtimeframe_path = Path(subtimeframe_path_value)
            if not subtimeframe_path.is_absolute():
                subtimeframe_path = Path(base_directory) / subtimeframe_path
            subtimeframe_data = load_dataset(
                subtimeframe_path,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=str(dataset_config.get("subtimeframe_format_profile", "canonical")),
            )
    base_interval = data_identity.base_interval or format_interval(
        validate_ohlcv(data).inferred_interval
    )
    dataset_id = data_identity.dataset_id()

    table_path = dataset_config.get("prior_profile_table_path")
    resolved_tick_paths = None
    if not table_path:
        resolved_tick_paths = _resolve_dataset_tick_paths(
            dataset_config, base_directory=base_directory
        )
    tick_format_profile = (
        str(dataset_config["tick_format_profile"])
        if dataset_config.get("tick_format_profile") is not None
        else None
    )
    explicit_tick_source_id = (
        str(dataset_config["tick_source_id"]) if dataset_config.get("tick_source_id") else None
    )
    table, resolved_tick_source_id = _resolve_prior_profile_table(
        instrument=instrument,
        settings=normalize_levels_config(run.get("levels"), instrument=instrument),
        tick_paths=resolved_tick_paths,
        tick_format_profile=tick_format_profile,
        prior_profile_table=None,
        prior_profile_table_path=table_path,
        tick_source_id=explicit_tick_source_id,
    )
    level_result = compute_levels(
        data,
        instrument=instrument,
        config=run.get("levels"),
        cache_policy=policy,
        data_identity=data_identity,
        store_root=store_root,
        prior_profile_table=table,
        tick_source_id=resolved_tick_source_id,
    )
    levels_status = str(level_result.get("cache_status", "bypassed"))
    levels_stage: dict[str, Any] = {
        "status": levels_status,
        "policy": policy,
    }
    if "cache_detail" in level_result:
        levels_stage["reason"] = level_result["cache_detail"]
    level_payload = {
        "levels": level_result["levels"],
        "session_levels": level_result["session_levels"],
        "levels_settings": level_result["levels_settings"],
    }
    levels_identity = LevelsIdentity.from_normalized(
        data_identity, level_payload["levels_settings"]
    )
    experiment_identity = ExperimentIdentity.from_run_spec(levels_identity, run)
    cache_provenance = {
        "policy": policy,
        "outcome": summarize_cache_outcome(
            policy=policy,
            data_status=str(data_stage.get("status", "bypassed")),
            levels_status=levels_status,
        ),
        "data": data_stage,
        "levels": levels_stage,
        "store_root": str(store_root) if store_root is not None else None,
    }
    setup = build_setup(dict(run.get("setup") or {}))
    signal_result = generate_signals(level_payload["levels"], setup, instrument=instrument)
    backtest_config = dict(run.get("backtest") or {})
    declared_parent_interval = None
    declared_sub_interval = None
    if ingestion_provenance:
        declared_parent_interval = ingestion_provenance.get("derived_parent_interval")
        declared_sub_interval = ingestion_provenance.get("source_interval")
    backtest_result = run_backtest(
        level_payload["levels"],
        signal_result["signals"],
        instrument=instrument,
        config=backtest_config,
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
        last_signal_setup=setup,
        subtimeframe_data=subtimeframe_data,
        parent_interval=declared_parent_interval,
        sub_interval=declared_sub_interval,
    )

    state: dict[str, Any] = {
        "data": data,
        "dataset_id": dataset_id,
        "instrument": instrument,
        "base_interval": base_interval,
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        "format_profile": format_profile,
        **level_payload,
        "levels_data_fingerprint": {
            "instrument": instrument,
            "rows": len(data),
            "timestamp_min": str(data["timestamp"].min()) if not data.empty else None,
            "timestamp_max": str(data["timestamp"].max()) if not data.empty else None,
            "columns": sorted(data.columns),
            "base_interval": base_interval,
            "source_timezone": source_timezone,
            "exchange_timezone": exchange_timezone,
        },
        "data_identity": data_identity.to_dict(),
        "levels_identity": levels_identity.to_dict(),
        "experiment_identity": experiment_identity.to_dict(),
        "execution_origin": origin,
        "cache_provenance": cache_provenance,
        "setup_config": setup,
        **signal_result,
        "last_signal_setup": setup,
        "signal_context": {
            "setup_name": setup["name"],
            "confluence_mode": setup["confluence_mode"],
            "setup_caption": _setup_caption(setup),
        },
        "trades": backtest_result["trades"],
        "trade_summary": backtest_result["trade_summary"],
        "equity_curve": backtest_result["equity_curve"],
        "backtest_otf_filter": backtest_result["otf_filter_summary"],
        "backtest_intrabar_policy": {
            "schema_version": 1,
            "intrabar_model": backtest_config.get("intrabar_model", "sl_first"),
            "subtimeframe_data_supplied": subtimeframe_data is not None,
        },
        "backtest_intrabar_diagnostic": backtest_result["intrabar_diagnostic"],
        "backtest_exit_management_policy": {
            "schema_version": 1,
            "breakeven_after_r": backtest_config.get("breakeven_after_r"),
            "trailing_after_r": backtest_config.get("trailing_after_r"),
            "trailing_distance_ticks": backtest_config.get("trailing_distance_ticks"),
        },
        "backtest_exit_management_diagnostic": backtest_result["exit_management_diagnostic"],
        "direction_collision_diagnostic": backtest_result["direction_collision_diagnostic"],
        "backtest_execution_costs": {
            "commission_per_side": float(backtest_config.get("commission_per_side", 0.0)),
            "slippage_ticks": float(backtest_config.get("slippage_ticks", 0.0)),
        },
    }
    if subtimeframe_data is not None:
        subtimeframe_report = validate_ohlcv(subtimeframe_data)
        state["subtimeframe_data"] = subtimeframe_data
        # Prefer declared provenance interval: sparse trade-only 15s frames often
        # gap-infer as 30s/1min and would poison later UI Backtest/Grid/WFO.
        declared = (
            None if ingestion_provenance is None else ingestion_provenance.get("source_interval")
        )
        state["subtimeframe_interval"] = (
            str(declared) if declared else format_interval(subtimeframe_report.inferred_interval)
        )
        if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
            state["subtimeframe_format_profile"] = format_profile
        else:
            state["subtimeframe_format_profile"] = str(
                dataset_config.get("subtimeframe_format_profile", "canonical")
            )
    if ingestion_provenance is not None:
        state["ingestion_provenance"] = dict(ingestion_provenance)

    grid_config = run.get("grid")
    grid_settings: dict[str, Any] = {}
    if isinstance(grid_config, Mapping) and grid_config.get("enabled", True):
        grid_settings = {key: value for key, value in grid_config.items() if key != "enabled"}
        grid_result = run_grid(
            level_payload["levels"],
            signal_result["signals"],
            instrument=instrument,
            config=grid_settings,
            setup_config=setup,
            signal_settings=signal_result["signal_settings"],
            last_signal_setup=setup,
            subtimeframe_data=subtimeframe_data,
            parent_interval=declared_parent_interval,
            sub_interval=declared_sub_interval,
        )
        state.update(
            {
                "grid_results": grid_result["grid_results"],
                "best_grid_result": grid_result["best_grid_result"],
                "grid_otf_filter": grid_result["otf_filter_summary"],
                "grid_accepted_signals": grid_result["accepted_signals"],
                "grid_intrabar_policy": {
                    "schema_version": 1,
                    "intrabar_model": grid_settings.get("intrabar_model", "sl_first"),
                    "subtimeframe_data_supplied": subtimeframe_data is not None,
                },
                "grid_exit_management_policy": {
                    "schema_version": 1,
                    "breakeven_after_r_values": grid_settings.get(
                        "breakeven_after_r_values", [None]
                    ),
                    "trailing_after_r_values": grid_settings.get("trailing_after_r_values", [None]),
                    "trailing_distance_ticks_values": grid_settings.get(
                        "trailing_distance_ticks_values", [None]
                    ),
                    "max_grid_cells": grid_settings.get("max_grid_cells", 500),
                },
            }
        )

    walk_forward_config = run.get("walk_forward")
    if isinstance(walk_forward_config, Mapping) and walk_forward_config.get("enabled", True):
        wfa_settings = {
            key: value for key, value in walk_forward_config.items() if key != "enabled"
        }
        execution_for_wfa = {
            **backtest_config,
            "breakeven_after_r_values": grid_settings.get(
                "breakeven_after_r_values",
                [backtest_config.get("breakeven_after_r")],
            ),
            "trailing_after_r_values": grid_settings.get(
                "trailing_after_r_values",
                [backtest_config.get("trailing_after_r")],
            ),
            "trailing_distance_ticks_values": grid_settings.get(
                "trailing_distance_ticks_values",
                [backtest_config.get("trailing_distance_ticks")],
            ),
            "max_grid_cells": grid_settings.get("max_grid_cells", 500),
        }
        state.update(
            run_walk_forward(
                level_payload["levels"],
                signal_result["signals"],
                instrument=instrument,
                config=wfa_settings,
                execution_config=execution_for_wfa,
                otf_config=setup.get("otf_filter"),
                subtimeframe_data=subtimeframe_data,
                parent_interval=declared_parent_interval,
                sub_interval=declared_sub_interval,
            )
        )

    validation_config = run.get("validation")
    if isinstance(validation_config, Mapping) and validation_config.get("enabled", True):
        validation_settings = {
            key: value for key, value in validation_config.items() if key != "enabled"
        }
        state.update(
            run_validation(
                backtest_result["trades"],
                grid=state.get("grid_results"),
                tick_size=inst.tick_size,
                config=validation_settings,
                df=level_payload["levels"],
                signals=state.get("grid_accepted_signals", signal_result["signals"]),
                point_value=inst.point_value,
                execution_kwargs={
                    **grid_settings,
                    "subtimeframe_data": subtimeframe_data,
                    "parent_interval": declared_parent_interval,
                    "sub_interval": declared_sub_interval,
                },
                selected_grid_metric=grid_settings.get("ranking_metric", "expectancy_r"),
                selected_min_trades=int(grid_settings.get("min_trades", 1)),
                raw_data=data,
                levels_config=run.get("levels"),
                setup_config=setup,
                backtest_config=backtest_config,
                subtimeframe_data=subtimeframe_data,
                parent_interval=declared_parent_interval,
                sub_interval=declared_sub_interval,
                prior_profile_table=table,
                tick_source_id=resolved_tick_source_id,
            )
        )
    return state
