"""SB1 StudyDraft compiler — emit / hydrate canonical StudySpec YAML.

Pure helper: no Streamlit, no execute / launch / preview. Pages import this
module directly. ``emit_study_spec`` is the only path into
``validate_study_spec``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    closed_level_token_set,
    normalize_study_spec,
    validate_study_spec,
)

STUDIES_BUILDER_DRAFT_KEY = "studies_builder_draft"
STUDIES_BUILDER_PENDING_SYNC_KEY = "studies_builder_pending_sync"

WIDGET_KEY_NAME = "_study_builder_name"
WIDGET_KEY_DESCRIPTION = "_study_builder_description"
WIDGET_KEY_OUTPUT_DIR = "_study_builder_output_dir"
WIDGET_KEY_WORKERS = "_study_builder_workers"
WIDGET_KEY_CONFIRM_ABOVE_RUNS = "_study_builder_confirm_above_runs"
WIDGET_KEY_DATASET_PATH = "_study_builder_dataset_path"
WIDGET_KEY_INSTRUMENT = "_study_builder_instrument"
WIDGET_KEY_SOURCE_TIMEZONE = "_study_builder_source_timezone"
WIDGET_KEY_FORMAT_PROFILE = "_study_builder_format_profile"
WIDGET_KEY_CORE_LEVEL = "_study_builder_core_level"
WIDGET_KEY_CONFLUENCE_MODE = "_study_builder_confluence_mode"
WIDGET_KEY_TRIGGER = "_study_builder_trigger"
WIDGET_KEY_TRIGGER_TIMEFRAME = "_study_builder_trigger_timeframe"
WIDGET_KEY_OTF = "_study_builder_otf"
WIDGET_KEY_DIRECTION_MODE = "_study_builder_direction_mode"
WIDGET_KEY_DIRECTION_CONSTANT = "_study_builder_direction_constant"
WIDGET_KEY_DIRECTION_VALUES = "_study_builder_direction_values"

_REQUIRED_FACTOR_AXES = (
    "core_level",
    "partner_levels",
    "confluence_mode",
    "trigger",
    "trigger_timeframe",
)
_DATASET_KNOWN = (
    "path",
    "instrument",
    "source_timezone",
    "format_profile",
    "subtimeframe_path",
)
_LEVELS_NULL_FORBIDDEN = ("sma_timeframes", "ema_timeframes")
_BATTERY_KEYS = ("grid", "validation", "walk_forward")
_DEFAULT_OUTPUT_DIR_PREFIX = "results/studies/"

OTF_PRESET_ORDER = ("off", "5m", "15m", "30m", "combo")
OTF_PRESET_LABELS = {
    "off": "Off",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "combo": "5m+15m+30m",
}
OTF_PRESETS: dict[str, dict[str, Any]] = {
    "off": {"enabled": False},
    "5m": {
        "enabled": True,
        "timeframes": ["5m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "15m": {
        "enabled": True,
        "timeframes": ["15m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "30m": {
        "enabled": True,
        "timeframes": ["30m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "combo": {
        "enabled": True,
        "timeframes": ["5m", "15m", "30m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
}


def _default_levels() -> dict[str, Any]:
    return {
        "sma_lengths": [50],
        "ema_lengths": [21],
        "sma_timeframes": ["1min"],
        "ema_timeframes": ["1min"],
    }


def _default_backtest() -> dict[str, Any]:
    return {
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
        "exposure_policy": "single_position",
        "commission_per_side": 0.0,
        "slippage_ticks": 0.0,
        "flat_by_session_close": False,
        "intrabar_model": "sl_first",
    }


def _default_battery() -> dict[str, Any]:
    return {"enabled": False}


def _default_secondary_metrics() -> list[str]:
    return ["profit_factor", "max_drawdown_r", "trade_count", "total_r"]


def _default_otf_baseline() -> dict[str, Any]:
    return {"enabled": False}


@dataclass
class StudyDraft:
    """Authoring state for a canonical ``schema_version: 1`` StudySpec."""

    name: str = "untitled_study"
    description: str = ""
    output_dir: str | None = None
    workers: int = 1
    confirm_above_runs: int = 200
    dataset_path: str = "data/es_1m.csv"
    instrument: str = "ES"
    source_timezone: str | None = "America/New_York"
    format_profile: str | None = None
    subtimeframe_path: str | None = None
    dataset_extra: dict[str, Any] = field(default_factory=dict)
    levels: dict[str, Any] = field(default_factory=_default_levels)
    core_level: list[str] = field(default_factory=lambda: ["pdPOC"])
    partner_levels: list[list[str]] = field(default_factory=lambda: [["SMA_50_1min"]])
    confluence_mode: list[str] = field(
        default_factory=lambda: ["global_cluster", "anchor_rules"]
    )
    trigger: list[str] = field(default_factory=lambda: ["touch"])
    trigger_timeframe: list[str] = field(default_factory=lambda: ["base"])
    otf: list[dict[str, Any]] | None = None
    direction_as_factor: bool = False
    direction_values: list[str] = field(default_factory=lambda: ["long", "short"])
    direction_constant: str = "both"
    tolerance_ticks: int | float = 0
    naked_only: bool = False
    naked_requirement: str = "any"
    min_confluences: int = 2
    max_confluences: int = 2
    min_valid_confluences: int = 1
    trigger_params: dict[str, Any] = field(default_factory=dict)
    entry_window: dict[str, Any] | None = None
    emit_entry_window: bool = False
    backtest: dict[str, Any] = field(default_factory=_default_backtest)
    grid: dict[str, Any] = field(default_factory=_default_battery)
    validation: dict[str, Any] = field(default_factory=_default_battery)
    walk_forward: dict[str, Any] = field(default_factory=_default_battery)
    from_partners: str = "required"
    primary_metric: str = "expectancy_r"
    secondary_metrics: list[str] = field(default_factory=_default_secondary_metrics)
    min_trades: int = 30
    group_by: list[str] | None = None
    otf_baseline: dict[str, Any] = field(default_factory=_default_otf_baseline)
    multiple_testing: str = "warn"
    stage_mode: str | None = None
    stage_include: dict[str, list[Any]] = field(default_factory=dict)
    stage_cells: list[dict[str, Any]] = field(default_factory=list)


def default_study_draft() -> StudyDraft:
    """Return a valid 2-cell default draft (1×1×2×1×1)."""
    return StudyDraft()


def _partner_set_widget_key(index: int) -> str:
    """Stable Streamlit widget key for partner-set row ``index`` (SB2)."""
    return f"_study_builder_partner_set_{index}"


def builder_token_catalog(levels: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Sorted closed level tokens implied by ``levels`` + the static catalog."""
    return tuple(sorted(closed_level_token_set(levels)))


def draft_warnings(draft: StudyDraft) -> tuple[str, ...]:
    """Non-fatal authoring warnings. Emit still validates; tokens are not dropped."""
    warnings: list[str] = []
    cores = {str(token) for token in draft.core_level}
    for index, partner_set in enumerate(draft.partner_levels):
        overlap = cores.intersection(str(token) for token in partner_set)
        if overlap:
            warnings.append(
                f"partner_levels[{index}] intersects core_level: {sorted(overlap)}"
            )
    return tuple(warnings)


def _canonical_mode_rules(modes: list[str], *, from_partners: str) -> dict[str, Any]:
    """Canonical templates for **listed** confluence modes only."""
    rules: dict[str, Any] = {}
    if "global_cluster" in modes:
        rules["global_cluster"] = {
            "selected_levels": ["${core_level}", "${partner_levels...}"],
        }
    if "anchor_rules" in modes:
        rules["anchor_rules"] = {
            "selected_levels": [],
            "anchor_level": "${core_level}",
            "confluence_rules": {"from_partners": from_partners},
        }
    return rules


def _with_enabled(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(dict(mapping or {}))
    if "enabled" not in out:
        out["enabled"] = False
    return out


def _emit_levels(levels: Mapping[str, Any]) -> dict[str, Any]:
    """Copy levels, dropping ``None`` values (never emit JSON null TFs)."""
    out: dict[str, Any] = {}
    for key, value in levels.items():
        if value is None:
            continue
        out[key] = copy.deepcopy(value)
    return out


def _emit_dataset(draft: StudyDraft) -> dict[str, Any]:
    dataset: dict[str, Any] = {"path": draft.dataset_path, "instrument": draft.instrument}
    if draft.source_timezone:
        dataset["source_timezone"] = draft.source_timezone
    if draft.format_profile:
        dataset["format_profile"] = draft.format_profile
    if draft.subtimeframe_path:
        dataset["subtimeframe_path"] = draft.subtimeframe_path
    for key, value in draft.dataset_extra.items():
        if key in _DATASET_KNOWN:
            continue
        dataset[key] = copy.deepcopy(value)
    return dataset


def _emit_constants(draft: StudyDraft) -> dict[str, Any]:
    constants: dict[str, Any] = {}
    if not draft.direction_as_factor:
        constants["direction"] = draft.direction_constant
    constants["tolerance_ticks"] = draft.tolerance_ticks
    constants["min_confluences"] = draft.min_confluences
    constants["max_confluences"] = draft.max_confluences
    constants["min_valid_confluences"] = draft.min_valid_confluences
    constants["naked_only"] = draft.naked_only
    constants["naked_requirement"] = draft.naked_requirement
    constants["trigger_params"] = copy.deepcopy(draft.trigger_params)
    if draft.emit_entry_window or draft.entry_window is not None:
        constants["entry_window"] = copy.deepcopy(draft.entry_window)
    constants["backtest"] = copy.deepcopy(draft.backtest)
    for key in _BATTERY_KEYS:
        constants[key] = _with_enabled(getattr(draft, key))
    return constants


def _emit_factors(draft: StudyDraft) -> dict[str, Any]:
    factors: dict[str, Any] = {
        "core_level": list(draft.core_level),
        "partner_levels": [list(partner_set) for partner_set in draft.partner_levels],
        "confluence_mode": list(draft.confluence_mode),
        "trigger": list(draft.trigger),
        "trigger_timeframe": list(draft.trigger_timeframe),
    }
    if draft.otf is not None:
        factors["otf"] = copy.deepcopy(draft.otf)
    if draft.direction_as_factor:
        factors["direction"] = list(draft.direction_values)
    return factors


def _emit_report(draft: StudyDraft) -> dict[str, Any]:
    report: dict[str, Any] = {
        "primary_metric": draft.primary_metric,
        "secondary_metrics": list(draft.secondary_metrics),
        "min_trades": draft.min_trades,
        "otf_baseline": _with_enabled(draft.otf_baseline),
        "multiple_testing": draft.multiple_testing,
    }
    if draft.group_by is not None:
        report["group_by"] = list(draft.group_by)
    return report


def _emit_stage(draft: StudyDraft) -> dict[str, Any] | None:
    if draft.stage_mode is None:
        return None
    if draft.stage_mode == "filter":
        return {"mode": "filter", "include": copy.deepcopy(draft.stage_include)}
    return {"mode": "explicit_cells", "cells": copy.deepcopy(draft.stage_cells)}


def _default_output_dir(name: str) -> str:
    return f"{_DEFAULT_OUTPUT_DIR_PREFIX}{name}"


def emit_study_spec(draft: StudyDraft) -> dict[str, Any]:
    """Build, normalize, and validate a StudySpec mapping from ``draft``."""
    study: dict[str, Any] = {
        "name": draft.name,
        "description": draft.description,
        "workers": draft.workers,
        "confirm_above_runs": draft.confirm_above_runs,
        "dataset": _emit_dataset(draft),
        "levels": _emit_levels(draft.levels),
        "constants": _emit_constants(draft),
        "factors": _emit_factors(draft),
        "mode_rules": _canonical_mode_rules(
            list(draft.confluence_mode),
            from_partners=draft.from_partners,
        ),
        "report": _emit_report(draft),
    }
    if draft.output_dir is not None:
        study["output_dir"] = draft.output_dir
    stage = _emit_stage(draft)
    if stage is not None:
        study["stage"] = stage
    payload = {"schema_version": STUDY_SCHEMA_VERSION, "study": study}
    return validate_study_spec(normalize_study_spec(payload))


def emit_study_yaml(draft: StudyDraft) -> str:
    """Dump a validated StudySpec. Comments from source files are not preserved."""
    return yaml.safe_dump(
        emit_study_spec(draft),
        sort_keys=False,
        allow_unicode=True,
    )


def _require_mapping(value: Any, *, section: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise StudySpecError(f"{section} must be a mapping")
    return dict(value)


def _hydrate_from_partners(mode_rules: Mapping[str, Any] | None) -> str:
    if not isinstance(mode_rules, Mapping):
        return "required"
    anchor = mode_rules.get("anchor_rules")
    if not isinstance(anchor, Mapping):
        return "required"
    rules = anchor.get("confluence_rules")
    if not isinstance(rules, Mapping):
        return "required"
    value = rules.get("from_partners", "required")
    return str(value) if value in {"required", "optional"} else "required"


def otf_preset_ids(otf: list[Mapping[str, Any]] | None) -> tuple[str | None, ...]:
    """Map OTF factor entries to preset ids (``None`` if custom)."""
    if otf is None:
        return ()
    ids: list[str | None] = []
    for entry in otf:
        try:
            normalized = normalize_otf_filter_config(dict(entry))
        except ValueError:
            ids.append(None)
            continue
        matched: str | None = None
        for preset_id in OTF_PRESET_ORDER:
            try:
                preset_norm = normalize_otf_filter_config(dict(OTF_PRESETS[preset_id]))
            except ValueError:
                continue
            if preset_norm == normalized:
                matched = preset_id
                break
        ids.append(matched)
    return tuple(ids)


def hydrate_study_draft(spec: Mapping[str, Any]) -> StudyDraft:
    """Populate a draft from a raw or normalized StudySpec mapping.

    Hydrate is not a second validator. Emit validates. Identity-hash
    round-trip requires preserving report lists, battery extras, dataset
    extras, and original OTF dicts (do not expand them to the full
    ``normalize_otf_filter_config`` key set).
    """
    payload = _require_mapping(spec, section="StudySpec")
    study = _require_mapping(payload.get("study"), section="study")
    dataset = _require_mapping(study.get("dataset"), section="study.dataset")
    constants = _require_mapping(study.get("constants"), section="study.constants")
    factors = _require_mapping(study.get("factors"), section="study.factors")
    report = study.get("report")
    report_map = dict(report) if isinstance(report, Mapping) else {}
    levels = study.get("levels")
    levels_map = dict(levels) if isinstance(levels, Mapping) else {}

    name = str(study.get("name") or "untitled_study")
    output_dir = study.get("output_dir")
    output_dir_str = str(output_dir).strip() if isinstance(output_dir, str) else None
    if output_dir_str == _default_output_dir(name):
        stored_output_dir: str | None = None
    else:
        stored_output_dir = output_dir_str

    dataset_extra = {
        key: copy.deepcopy(value)
        for key, value in dataset.items()
        if key not in _DATASET_KNOWN
    }
    source_timezone = dataset.get("source_timezone")
    format_profile = dataset.get("format_profile")
    subtimeframe_path = dataset.get("subtimeframe_path")

    otf_raw = factors.get("otf")
    otf: list[dict[str, Any]] | None
    if otf_raw is None:
        otf = None
    elif isinstance(otf_raw, list):
        otf = [copy.deepcopy(dict(entry)) for entry in otf_raw if isinstance(entry, Mapping)]
    else:
        raise StudySpecError("factors.otf must be a list")

    direction_in_factors = "direction" in factors
    direction_values = (
        [str(item) for item in factors.get("direction") or []]
        if direction_in_factors
        else ["long", "short"]
    )
    direction_constant = str(constants.get("direction") or "both")

    partners_raw = factors.get("partner_levels") or []
    partner_levels: list[list[str]] = []
    if isinstance(partners_raw, list):
        for item in partners_raw:
            if isinstance(item, list):
                partner_levels.append([str(token) for token in item])

    stage = study.get("stage")
    stage_mode: str | None = None
    stage_include: dict[str, list[Any]] = {}
    stage_cells: list[dict[str, Any]] = []
    if isinstance(stage, Mapping):
        mode = stage.get("mode")
        if mode in {"filter", "explicit_cells"}:
            stage_mode = str(mode)
        if stage_mode == "filter":
            include = stage.get("include")
            if isinstance(include, Mapping):
                stage_include = copy.deepcopy(dict(include))
        elif stage_mode == "explicit_cells":
            cells = stage.get("cells")
            if isinstance(cells, list):
                stage_cells = [
                    copy.deepcopy(dict(cell)) for cell in cells if isinstance(cell, Mapping)
                ]

    group_by_raw = report_map.get("group_by")
    group_by = [str(item) for item in group_by_raw] if isinstance(group_by_raw, list) else None

    secondary = report_map.get("secondary_metrics")
    secondary_metrics = (
        [str(item) for item in secondary]
        if isinstance(secondary, list)
        else _default_secondary_metrics()
    )

    return StudyDraft(
        name=name,
        description=str(study.get("description") or ""),
        output_dir=stored_output_dir,
        workers=int(study.get("workers") or 1),
        confirm_above_runs=int(study.get("confirm_above_runs") or 200),
        dataset_path=str(dataset.get("path") or ""),
        instrument=str(dataset.get("instrument") or ""),
        source_timezone=str(source_timezone) if isinstance(source_timezone, str) else None,
        format_profile=str(format_profile) if isinstance(format_profile, str) else None,
        subtimeframe_path=(
            str(subtimeframe_path) if isinstance(subtimeframe_path, str) else None
        ),
        dataset_extra=dataset_extra,
        levels=copy.deepcopy(levels_map),
        core_level=[str(token) for token in (factors.get("core_level") or [])],
        partner_levels=partner_levels,
        confluence_mode=[str(item) for item in (factors.get("confluence_mode") or [])],
        trigger=[str(item) for item in (factors.get("trigger") or [])],
        trigger_timeframe=[str(item) for item in (factors.get("trigger_timeframe") or [])],
        otf=otf,
        direction_as_factor=direction_in_factors,
        direction_values=direction_values,
        direction_constant=direction_constant,
        tolerance_ticks=constants.get("tolerance_ticks", 0),
        naked_only=bool(constants.get("naked_only", False)),
        naked_requirement=str(constants.get("naked_requirement") or "any"),
        min_confluences=int(constants.get("min_confluences", 2)),
        max_confluences=int(constants.get("max_confluences", 2)),
        min_valid_confluences=int(constants.get("min_valid_confluences", 1)),
        trigger_params=copy.deepcopy(dict(constants.get("trigger_params") or {})),
        entry_window=(
            copy.deepcopy(constants["entry_window"])
            if isinstance(constants.get("entry_window"), Mapping)
            else None
        ),
        emit_entry_window="entry_window" in constants,
        backtest=copy.deepcopy(dict(constants.get("backtest") or {})),
        grid=_with_enabled(constants.get("grid") if isinstance(constants.get("grid"), Mapping) else {}),
        validation=_with_enabled(
            constants.get("validation")
            if isinstance(constants.get("validation"), Mapping)
            else {}
        ),
        walk_forward=_with_enabled(
            constants.get("walk_forward")
            if isinstance(constants.get("walk_forward"), Mapping)
            else {}
        ),
        from_partners=_hydrate_from_partners(study.get("mode_rules")),
        primary_metric=str(report_map.get("primary_metric") or "expectancy_r"),
        secondary_metrics=secondary_metrics,
        min_trades=int(report_map.get("min_trades", 30)),
        group_by=group_by,
        otf_baseline=_with_enabled(
            report_map.get("otf_baseline")
            if isinstance(report_map.get("otf_baseline"), Mapping)
            else {}
        ),
        multiple_testing=str(report_map.get("multiple_testing") or "warn"),
        stage_mode=stage_mode,
        stage_include=stage_include,
        stage_cells=stage_cells,
    )


def hydrate_study_yaml(text: str) -> StudyDraft:
    """Parse YAML text then hydrate. Invalid YAML / non-mapping → StudySpecError."""
    if not str(text).strip():
        raise StudySpecError("StudySpec YAML is empty")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StudySpecError(f"Invalid StudySpec YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise StudySpecError("StudySpec YAML must contain a mapping")
    return hydrate_study_draft(payload)


# Re-export for SB2 widget rows without importing Streamlit here.
__all__ = [
    "OTF_PRESETS",
    "OTF_PRESET_LABELS",
    "OTF_PRESET_ORDER",
    "STUDIES_BUILDER_DRAFT_KEY",
    "STUDIES_BUILDER_PENDING_SYNC_KEY",
    "StudyDraft",
    "WIDGET_KEY_CONFIRM_ABOVE_RUNS",
    "WIDGET_KEY_CONFLUENCE_MODE",
    "WIDGET_KEY_CORE_LEVEL",
    "WIDGET_KEY_DATASET_PATH",
    "WIDGET_KEY_DESCRIPTION",
    "WIDGET_KEY_DIRECTION_CONSTANT",
    "WIDGET_KEY_DIRECTION_MODE",
    "WIDGET_KEY_DIRECTION_VALUES",
    "WIDGET_KEY_FORMAT_PROFILE",
    "WIDGET_KEY_INSTRUMENT",
    "WIDGET_KEY_NAME",
    "WIDGET_KEY_OTF",
    "WIDGET_KEY_OUTPUT_DIR",
    "WIDGET_KEY_SOURCE_TIMEZONE",
    "WIDGET_KEY_TRIGGER",
    "WIDGET_KEY_TRIGGER_TIMEFRAME",
    "WIDGET_KEY_WORKERS",
    "_partner_set_widget_key",
    "builder_token_catalog",
    "default_study_draft",
    "draft_warnings",
    "emit_study_spec",
    "emit_study_yaml",
    "hydrate_study_draft",
    "hydrate_study_yaml",
    "otf_preset_ids",
]
