"""StudyDraft → validated StudySpec emit helpers (C-24 / QI-07-07).

``emit_study_spec`` remains the only path into ``validate_study_spec``.
No Streamlit. Public signature unchanged.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

import yaml

from thesistester.data.derive import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.data.loader import FORMAT_PROFILES
from thesistester.study.builder_draft import (
    StudyDraft,
    _BATTERY_KEYS,
    _DATASET_KNOWN,
    _DERIVE_15S_SUPPORTED_PROFILES,
    _resolved_ingestion_mode,
    _with_enabled,
    normalize_builder_format_profile,
    normalize_tick_paths,
)
from thesistester.study.schema import (
    STUDY_INGESTION_MODES,
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)


def require_enabled_grid_ticks(grid: Mapping[str, Any]) -> None:
    """Fail closed when ``grid.enabled`` is missing required SL/TP lists.

    StudySpec validation only checks ``enabled``. ``validate_run_spec`` (expand)
    requires non-empty tick lists — but preview skips expand over
    ``PREVIEW_EXPAND_CAP``, so emit must refuse here or Apply can write YAML
    that cannot launch.
    """
    if grid.get("enabled") is not True:
        return
    for key in ("stop_loss_ticks_values", "take_profit_ticks_values"):
        values = grid.get(key)
        if not isinstance(values, list) or not values:
            raise StudySpecError(f"constants.grid.{key} must be a non-empty list when grid.enabled")
        for index, item in enumerate(values):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or float(item) <= 0:
                raise StudySpecError(f"constants.grid.{key}[{index}] must be a number > 0")


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
    profile = normalize_builder_format_profile(draft.format_profile)
    if profile not in FORMAT_PROFILES:
        raise StudySpecError(
            f"dataset.format_profile must be one of {list(FORMAT_PROFILES)}; got {profile!r}"
        )
    dataset["format_profile"] = profile
    mode = _resolved_ingestion_mode(draft.ingestion_mode)
    if mode not in STUDY_INGESTION_MODES:
        raise StudySpecError(
            "dataset.ingestion_mode must be one of "
            f"{sorted(STUDY_INGESTION_MODES)!r} when present; got {mode!r}"
        )
    if mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        if draft.subtimeframe_path:
            raise StudySpecError(
                "dataset.subtimeframe_path cannot be combined with "
                f"ingestion_mode={INGESTION_MODE_15S_PRIMARY_DERIVE_1M!r}"
            )
        if profile not in _DERIVE_15S_SUPPORTED_PROFILES:
            raise StudySpecError(
                "dataset.format_profile must be one of "
                f"{sorted(_DERIVE_15S_SUPPORTED_PROFILES)!r} when "
                f"ingestion_mode={INGESTION_MODE_15S_PRIMARY_DERIVE_1M!r}"
            )
        dataset["ingestion_mode"] = mode
    else:
        if draft.subtimeframe_path:
            dataset["subtimeframe_path"] = draft.subtimeframe_path
    tick_paths = normalize_tick_paths(draft.tick_paths)
    if not tick_paths:
        tick_paths = normalize_tick_paths(draft.dataset_extra.get("tick_paths"))
    if tick_paths:
        dataset["tick_paths"] = tick_paths
    for key, value in draft.dataset_extra.items():
        if key in _DATASET_KNOWN or key == "tick_paths":
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
    elif draft.emit_group_by:
        # Explicit YAML null must be re-emitted. Omitting the key lets
        # normalize_study_spec invent the factor-derived default list.
        report["group_by"] = None
    return report


def _emit_stage(draft: StudyDraft) -> dict[str, Any] | None:
    if draft.stage_mode is None:
        return None
    if draft.stage_mode == "filter":
        return {"mode": "filter", "include": copy.deepcopy(draft.stage_include)}
    return {"mode": "explicit_cells", "cells": copy.deepcopy(draft.stage_cells)}


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
    if draft.lineage is not None:
        study["lineage"] = copy.deepcopy(draft.lineage)
    payload = {"schema_version": STUDY_SCHEMA_VERSION, "study": study}
    require_enabled_grid_ticks(study["constants"]["grid"])
    return validate_study_spec(normalize_study_spec(payload))


def emit_study_yaml(draft: StudyDraft) -> str:
    """Dump a validated StudySpec. Comments from source files are not preserved."""
    return yaml.safe_dump(
        emit_study_spec(draft),
        sort_keys=False,
        allow_unicode=True,
    )
