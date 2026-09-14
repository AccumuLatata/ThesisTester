"""StudySpec → StudyDraft hydrate helpers (C-24 / QI-07-07).

Hydrate is not a second validator. Emit validates. Public signature unchanged.
No Streamlit.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.builder_draft import (
    OTF_PRESET_ORDER,
    OTF_PRESETS,
    StudyDraft,
    _DATASET_KNOWN,
    _default_output_dir,
    _default_secondary_metrics,
    _pop_extra_ingestion_mode,
    _pop_extra_tick_paths,
    _blank_ingestion_mode,
    _resolved_ingestion_mode,
    _with_enabled,
    normalize_builder_format_profile,
    normalize_tick_paths,
)
from thesistester.study.schema import StudySpecError


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
    round-trip requires preserving report lists, explicit ``group_by`` /
    ``description`` nulls, battery extras, dataset extras, and original
    OTF dicts (do not expand them to the full
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
    if "description" in study:
        raw_description = study["description"]
        description = None if raw_description is None else str(raw_description)
    else:
        description = ""
    output_dir = study.get("output_dir")
    output_dir_str = str(output_dir).strip() if isinstance(output_dir, str) else None
    if output_dir_str == _default_output_dir(name):
        stored_output_dir: str | None = None
    else:
        stored_output_dir = output_dir_str

    dataset_extra = {
        key: copy.deepcopy(value) for key, value in dataset.items() if key not in _DATASET_KNOWN
    }
    source_timezone = dataset.get("source_timezone")
    format_profile = dataset.get("format_profile")
    subtimeframe_path = dataset.get("subtimeframe_path")
    raw_ingestion_mode = dataset.get("ingestion_mode")
    if _blank_ingestion_mode(raw_ingestion_mode):
        raw_ingestion_mode = _pop_extra_ingestion_mode(dataset_extra)
    ingestion_mode = _resolved_ingestion_mode(raw_ingestion_mode)
    tick_paths = normalize_tick_paths(dataset.get("tick_paths"))
    if not tick_paths:
        tick_paths = normalize_tick_paths(_pop_extra_tick_paths(dataset_extra))

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
    emit_group_by = "group_by" in report_map
    group_by = [str(item) for item in group_by_raw] if isinstance(group_by_raw, list) else None

    secondary = report_map.get("secondary_metrics")
    secondary_metrics = (
        [str(item) for item in secondary]
        if isinstance(secondary, list)
        else _default_secondary_metrics()
    )

    return StudyDraft(
        name=name,
        description=description,
        output_dir=stored_output_dir,
        workers=int(study.get("workers") or 1),
        confirm_above_runs=int(study.get("confirm_above_runs") or 200),
        dataset_path=str(dataset.get("path") or ""),
        instrument=str(dataset.get("instrument") or ""),
        source_timezone=str(source_timezone) if isinstance(source_timezone, str) else None,
        format_profile=normalize_builder_format_profile(format_profile),
        ingestion_mode=ingestion_mode,
        subtimeframe_path=(str(subtimeframe_path) if isinstance(subtimeframe_path, str) else None),
        tick_paths=tick_paths,
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
        grid=_with_enabled(
            constants.get("grid") if isinstance(constants.get("grid"), Mapping) else {}
        ),
        validation=_with_enabled(
            constants.get("validation") if isinstance(constants.get("validation"), Mapping) else {}
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
        emit_group_by=emit_group_by,
        otf_baseline=_with_enabled(
            report_map.get("otf_baseline")
            if isinstance(report_map.get("otf_baseline"), Mapping)
            else {}
        ),
        multiple_testing=str(report_map.get("multiple_testing") or "warn"),
        stage_mode=stage_mode,
        stage_include=stage_include,
        stage_cells=stage_cells,
        lineage=(
            copy.deepcopy(dict(study["lineage"]))
            if isinstance(study.get("lineage"), Mapping)
            else None
        ),
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
