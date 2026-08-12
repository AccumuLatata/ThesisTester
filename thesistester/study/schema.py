"""StudySpec schema_version 1 — load, normalize, fail-closed validate (RS1).

Expansion / execution live in later RS milestones. This module only accepts a
closed StudySpec and rejects unknown keys and out-of-domain factor tokens.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from thesistester.levels.common import normalized_window_label
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.indicators import SUPPORTED_INDICATOR_TIMEFRAMES
from thesistester.levels.prev30m_vwap import prev30m_price_column_names
from thesistester.setup import (
    SUGGESTED_DEFAULT_LEVELS,
    VALID_CONFLUENCE_MODES,
    VALID_DIRECTIONS,
    VALID_TRIGGER_TIMEFRAMES,
    VALID_TRIGGERS,
    normalize_otf_filter_config,
)

STUDY_SCHEMA_VERSION = 1
RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


# Static / session / profile names accepted without being implied by ``levels``.
# Documented in docs/STUDY_RUNNER.md; keep in sync with product catalogs.
def _static_catalog_names() -> frozenset[str]:
    """Session/profile names; rolling VWAP/POC come only from levels windows."""
    names = {
        *SUGGESTED_DEFAULT_LEVELS,
        "ONH",
        "ONL",
        "pONH",
        "pONL",
        "AsiaHigh",
        "AsiaLow",
        "LondonHigh",
        "LondonLow",
        "OR_High",
        "OR_Low",
        "RTH_Open",
        "pRTH_Open",
        "pRTH_High",
        "pRTH_Low",
        "prevSettlement",
        "dOpen",
        "wOpen",
        "mOpen",
        "pdOpen",
        "pwOpen",
        "pmOpen",
        "pdHigh",
        "pdLow",
        "pwHigh",
        "pwLow",
        "pmHigh",
        "pmLow",
        "pdEQ",
        "pwEQ",
        "pmEQ",
        "pdPOC",
        "dVWAP_RTH",
        "dVWAP",
        "APOC",
        "pAPOC",
        "dSinglePrint_30m_NearestAbove",
        "dSinglePrint_30m_NearestBelow",
        "pSinglePrint_30m_NearestAbove",
        "pSinglePrint_30m_NearestBelow",
        # prev30mVWAP* and Pivot_* are admitted only when the matching
        # study.levels enable flags are on (see closed_level_token_set).
    }
    # SUGGESTED_DEFAULT_LEVELS may include VWAP_rolling_1h which is not implied
    # by DEFAULT_LEVELS_SETTINGS windows (30min/4h) — do not admit statically.
    return frozenset(
        name
        for name in names
        if not str(name).startswith("VWAP_rolling_") and not str(name).startswith("POC_rolling_")
    )


STUDY_STATIC_LEVEL_NAMES: frozenset[str] = _static_catalog_names()

_DEFAULT_REPORT_GROUP_BY = (
    "partner_levels",
    "confluence_mode",
    "trigger",
    "trigger_timeframe",
    "otf",
)

_TOP_LEVEL_KEYS = frozenset({"schema_version", "study"})
_STUDY_KEYS = frozenset(
    {
        "name",
        "description",
        "output_dir",
        "workers",
        "confirm_above_runs",
        "dataset",
        "levels",
        "constants",
        "factors",
        "mode_rules",
        "report",
        "stage",
    }
)
_SUPPORTED_FACTOR_AXES = frozenset(
    {
        "core_level",
        "partner_levels",
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
        "otf",
        "direction",
    }
)
_REQUIRED_FACTOR_AXES = frozenset({"core_level", "partner_levels"})
_CONSTANTS_KEYS = frozenset(
    {
        "direction",
        "tolerance_ticks",
        "min_confluences",
        "max_confluences",
        "min_valid_confluences",
        "naked_only",
        "naked_requirement",
        "trigger_params",
        "entry_window",
        "backtest",
        "grid",
        "validation",
        "walk_forward",
    }
)
_REPORT_KEYS = frozenset(
    {
        "primary_metric",
        "secondary_metrics",
        "min_trades",
        "group_by",
        "otf_baseline",
        "multiple_testing",
    }
)
_STAGE_KEYS = frozenset({"mode", "include", "cells"})
_MODE_RULE_TOP_KEYS = frozenset({"global_cluster", "anchor_rules"})
_INDEX_PRIMARY_METRICS = frozenset(
    {"expectancy_r", "total_r", "max_drawdown_r", "trade_count", "profit_factor"}
)
_MULTIPLE_TESTING_MODES = frozenset({"warn", "error"})
_ENABLED_SECTIONS = ("grid", "validation", "walk_forward")


class StudySpecError(ValueError):
    """Raised when a StudySpec fails fail-closed validation."""


def _require_mapping(value: Any, *, section: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise StudySpecError(f"{section} must be a mapping")
    return dict(value)


def _unknown_keys(payload: Mapping[str, Any], allowed: frozenset[str], *, section: str) -> None:
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise StudySpecError(f"Unknown {section} keys: {unknown}")


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StudySpecError(f"{field} must be an integer")
    if value < 1:
        raise StudySpecError(f"{field} must be >= 1")
    return value


def _require_list(value: Any, *, field: str) -> list[Any]:
    """Require a real list (reject str/bytes which are iterable character-wise)."""
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise StudySpecError(f"{field} must be a list")
    return value


def _require_positive_int_list(value: Any, *, field: str) -> list[int]:
    values = _require_list(value, field=field)
    out: list[int] = []
    for index, item in enumerate(values):
        if isinstance(item, bool) or not isinstance(item, int):
            raise StudySpecError(f"{field}[{index}] must be an integer")
        if item < 1:
            raise StudySpecError(f"{field}[{index}] must be >= 1")
        out.append(item)
    return out


def _require_nonempty_str_list(value: Any, *, field: str) -> list[str]:
    values = _require_list(value, field=field)
    out: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str) or not item.strip():
            raise StudySpecError(f"{field}[{index}] must be a non-empty string")
        out.append(item.strip())
    return out


def _validate_levels_map(levels_map: Mapping[str, Any]) -> None:
    """Fail closed on levels shapes that would crash or invent junk tokens."""
    for key in ("sma_lengths", "ema_lengths"):
        if key not in levels_map or levels_map[key] is None:
            continue
        _require_positive_int_list(levels_map[key], field=f"study.levels.{key}")

    for key in ("sma_timeframes", "ema_timeframes"):
        values = levels_map.get(key)
        if values is None:
            continue
        parsed = _require_list(values, field=f"study.levels.{key}")
        invalid = sorted({str(v) for v in parsed if str(v) not in SUPPORTED_INDICATOR_TIMEFRAMES})
        if invalid:
            raise StudySpecError(
                f"Unsupported study.levels.{key} value(s): {invalid}; "
                f"choose from {list(SUPPORTED_INDICATOR_TIMEFRAMES)}"
            )

    for key in ("vwap_windows", "poc_windows", "pivot_timeframes"):
        if key not in levels_map or levels_map[key] is None:
            continue
        _require_nonempty_str_list(levels_map[key], field=f"study.levels.{key}")

    if "prev30m_vwap_validity_periods" in levels_map:
        _positive_int(
            levels_map.get("prev30m_vwap_validity_periods"),
            field="study.levels.prev30m_vwap_validity_periods",
        )


def closed_level_token_set(levels: Mapping[str, Any] | None) -> frozenset[str]:
    """Return the closed set of level tokens valid for core/partner factors."""
    levels_map = dict(levels or {})
    # Public helper: validate shapes so callers never see raw int()/iterate crashes.
    _validate_levels_map(levels_map)
    settings = {**DEFAULT_LEVELS_SETTINGS, **levels_map}
    tokens: set[str] = set(STUDY_STATIC_LEVEL_NAMES)

    sma_lengths = settings.get("sma_lengths") or []
    ema_lengths = settings.get("ema_lengths") or []
    # None → bare SMA_N / EMA_N (levels engine). Explicit [] → no MA tokens.
    # Do not treat empty lists as None (that invented bare columns the engine
    # never emits for empty timeframe tuples).
    sma_timeframes = settings.get("sma_timeframes")
    ema_timeframes = settings.get("ema_timeframes")

    if sma_timeframes is None:
        for length in sma_lengths:
            tokens.add(f"SMA_{int(length)}")
    else:
        for length in sma_lengths:
            for timeframe in sma_timeframes:
                tokens.add(f"SMA_{int(length)}_{timeframe}")

    if ema_timeframes is None:
        for length in ema_lengths:
            tokens.add(f"EMA_{int(length)}")
    else:
        for length in ema_lengths:
            for timeframe in ema_timeframes:
                tokens.add(f"EMA_{int(length)}_{timeframe}")

    for window in settings.get("vwap_windows") or []:
        tokens.add(f"VWAP_rolling_{normalized_window_label(str(window))}")
    for window in settings.get("poc_windows") or []:
        tokens.add(f"POC_rolling_{normalized_window_label(str(window))}")

    if bool(settings.get("prev30m_vwap_enabled", False)):
        validity = int(settings.get("prev30m_vwap_validity_periods") or 1)
        tokens.update(prev30m_price_column_names(max(validity, 1)))

    if bool(settings.get("pivots_enabled", False)):
        for timeframe in settings.get("pivot_timeframes") or []:
            label = str(timeframe).strip()
            if label:
                tokens.add(f"Pivot_{label}_High")
                tokens.add(f"Pivot_{label}_Low")

    return frozenset(tokens)


def _normalize_otf_factor_entry(raw: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise StudySpecError(f"{path} must be a mapping")
    try:
        return normalize_otf_filter_config(dict(raw))
    except ValueError as exc:
        raise StudySpecError(f"{path}: {exc}") from exc


def normalize_study_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied StudySpec with RS1 defaults applied (not yet validated)."""
    if not isinstance(raw, Mapping):
        raise StudySpecError("StudySpec must be a mapping")
    payload = copy.deepcopy(dict(raw))
    study = payload.get("study")
    if isinstance(study, Mapping):
        study_dict = dict(study)
        study_dict.setdefault("description", "")
        study_dict.setdefault("workers", 1)
        study_dict.setdefault("confirm_above_runs", 200)
        study_dict.setdefault("levels", {})
        if "name" in study_dict and "output_dir" not in study_dict:
            study_dict["output_dir"] = f"results/studies/{study_dict['name']}"
        report = study_dict.get("report")
        factors = study_dict.get("factors")
        factor_keys = set(factors) if isinstance(factors, Mapping) else set()
        default_group_by = [key for key in _DEFAULT_REPORT_GROUP_BY if key in factor_keys]
        if report is None:
            study_dict["report"] = {
                "primary_metric": "expectancy_r",
                "secondary_metrics": [
                    "profit_factor",
                    "max_drawdown_r",
                    "trade_count",
                    "total_r",
                ],
                "min_trades": 30,
                "group_by": default_group_by,
                "otf_baseline": {"enabled": False},
                "multiple_testing": "warn",
            }
        elif isinstance(report, Mapping):
            report_dict = dict(report)
            report_dict.setdefault("primary_metric", "expectancy_r")
            report_dict.setdefault(
                "secondary_metrics",
                ["profit_factor", "max_drawdown_r", "trade_count", "total_r"],
            )
            report_dict.setdefault("min_trades", 30)
            report_dict.setdefault("multiple_testing", "warn")
            report_dict.setdefault("otf_baseline", {"enabled": False})
            if "group_by" not in report_dict:
                report_dict["group_by"] = default_group_by
            study_dict["report"] = report_dict
        payload["study"] = study_dict
    return payload


def validate_study_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a normalized StudySpec. Returns the same mapping on success."""
    payload = _require_mapping(spec, section="StudySpec")
    _unknown_keys(payload, _TOP_LEVEL_KEYS, section="StudySpec")

    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != STUDY_SCHEMA_VERSION
    ):
        raise StudySpecError(
            f"Unsupported StudySpec schema_version: {schema_version!r}; "
            f"expected {STUDY_SCHEMA_VERSION}"
        )

    study = _require_mapping(payload.get("study"), section="study")
    _unknown_keys(study, _STUDY_KEYS, section="study")

    name = study.get("name")
    if not isinstance(name, str) or not RUN_NAME_RE.fullmatch(name):
        raise StudySpecError(f"study.name must match {RUN_NAME_RE.pattern!r}; got {name!r}")

    description = study.get("description", "")
    if description is not None and not isinstance(description, str):
        raise StudySpecError("study.description must be a string")

    output_dir = study.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise StudySpecError("study.output_dir must be a non-empty string")

    _positive_int(study.get("workers"), field="study.workers")
    _positive_int(study.get("confirm_above_runs"), field="study.confirm_above_runs")

    dataset = _require_mapping(study.get("dataset"), section="study.dataset")
    if "path" not in dataset:
        raise StudySpecError("study.dataset.path is required")
    if not isinstance(dataset["path"], (str, Path)):
        raise StudySpecError("study.dataset.path must be a path string")
    instrument = dataset.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        raise StudySpecError(
            "study.dataset.instrument is required (non-empty string; "
            "injected into every expanded setup)"
        )

    levels = study.get("levels")
    if levels is None:
        levels = {}
    levels_map = _require_mapping(levels, section="study.levels")
    # Levels keys are pass-through to R18; reject non-product keys lightly via
    # DEFAULT_LEVELS_SETTINGS allowlist so typos fail closed at study authoring.
    unknown_levels = sorted(set(levels_map) - set(DEFAULT_LEVELS_SETTINGS))
    if unknown_levels:
        raise StudySpecError(f"Unknown study.levels keys: {unknown_levels}")
    _validate_levels_map(levels_map)

    closed_tokens = closed_level_token_set(levels_map)

    constants = _require_mapping(study.get("constants"), section="study.constants")
    _unknown_keys(constants, _CONSTANTS_KEYS, section="study.constants")
    _validate_constants(constants)

    factors = _require_mapping(study.get("factors"), section="study.factors")
    _validate_factors(factors, closed_tokens=closed_tokens)

    mode_rules = study.get("mode_rules")
    if "confluence_mode" in factors and mode_rules is None:
        raise StudySpecError("study.mode_rules is required when factors.confluence_mode is present")
    if mode_rules is not None and "confluence_mode" not in factors:
        raise StudySpecError("study.mode_rules requires factors.confluence_mode")
    if mode_rules is not None:
        mode_map = _require_mapping(mode_rules, section="study.mode_rules")
        _unknown_keys(mode_map, _MODE_RULE_TOP_KEYS, section="study.mode_rules")
        _validate_mode_rules(mode_map, factors=factors)

    report = _require_mapping(study.get("report"), section="study.report")
    _unknown_keys(report, _REPORT_KEYS, section="study.report")
    _validate_report(report, factor_keys=set(factors))

    stage = study.get("stage")
    if stage is not None:
        stage_map = _require_mapping(stage, section="study.stage")
        _unknown_keys(stage_map, _STAGE_KEYS, section="study.stage")
        _validate_stage(stage_map, factors=factors)

    return dict(payload)


def _validate_constants(constants: Mapping[str, Any]) -> None:
    direction = constants.get("direction")
    if direction is not None and direction not in VALID_DIRECTIONS:
        raise StudySpecError(
            f"study.constants.direction must be one of {sorted(VALID_DIRECTIONS)}; "
            f"got {direction!r}"
        )

    for key in ("tolerance_ticks", "min_confluences", "max_confluences", "min_valid_confluences"):
        if key not in constants:
            continue
        value = constants[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StudySpecError(f"study.constants.{key} must be numeric")

    if "max_confluences" in constants:
        max_conf = constants["max_confluences"]
        if isinstance(max_conf, (int, float)) and float(max_conf) > 5:
            raise StudySpecError("study.constants.max_confluences must be <= 5")

    if "trigger_params" in constants and constants["trigger_params"] is not None:
        if not isinstance(constants["trigger_params"], Mapping):
            raise StudySpecError("study.constants.trigger_params must be a mapping or null")

    if "entry_window" in constants and constants["entry_window"] is not None:
        if not isinstance(constants["entry_window"], Mapping):
            raise StudySpecError("study.constants.entry_window must be a mapping or null")

    if "backtest" in constants:
        _require_mapping(constants.get("backtest"), section="study.constants.backtest")

    for section in _ENABLED_SECTIONS:
        if section not in constants:
            continue
        mapping = _require_mapping(constants.get(section), section=f"study.constants.{section}")
        if "enabled" not in mapping:
            raise StudySpecError(
                f"study.constants.{section} must include explicit enabled "
                f"(true/false); bare mappings default-on in run_experiment"
            )
        if not isinstance(mapping["enabled"], bool):
            raise StudySpecError(f"study.constants.{section}.enabled must be a boolean")


def _validate_factors(
    factors: Mapping[str, Any],
    *,
    closed_tokens: frozenset[str],
) -> None:
    unknown = sorted(set(factors) - _SUPPORTED_FACTOR_AXES)
    if unknown:
        raise StudySpecError(
            f"Unsupported factor axes: {unknown}; supported axes: {sorted(_SUPPORTED_FACTOR_AXES)}"
        )
    missing = sorted(_REQUIRED_FACTOR_AXES - set(factors))
    if missing:
        raise StudySpecError(f"Missing required factor axes: {missing}")

    core = factors.get("core_level")
    if not isinstance(core, list) or not core:
        raise StudySpecError("factors.core_level must be a non-empty list")
    for index, token in enumerate(core):
        if not isinstance(token, str) or not token:
            raise StudySpecError(f"factors.core_level[{index}] must be a non-empty string")
        if token not in closed_tokens:
            raise StudySpecError(
                f"Unknown core_level token {token!r}; not in closed level set "
                f"implied by study.levels + static catalog"
            )

    partners = factors.get("partner_levels")
    if not isinstance(partners, list) or not partners:
        raise StudySpecError("factors.partner_levels must be a non-empty list of partner-sets")
    for index, partner_set in enumerate(partners):
        if not isinstance(partner_set, list) or not partner_set:
            raise StudySpecError(f"factors.partner_levels[{index}] must be a non-empty list")
        if len(partner_set) + 1 > 5:
            # core + partners length cap for global_cluster study emission rule
            raise StudySpecError(
                f"factors.partner_levels[{index}] too large: core+partners would exceed 5 levels"
            )
        seen_partners: set[str] = set()
        for token_index, token in enumerate(partner_set):
            if not isinstance(token, str) or not token:
                raise StudySpecError(
                    f"factors.partner_levels[{index}][{token_index}] must be a non-empty string"
                )
            if token not in closed_tokens:
                raise StudySpecError(
                    f"Unknown partner level token {token!r}; not in closed level "
                    f"set implied by study.levels + static catalog"
                )
            if token in seen_partners:
                raise StudySpecError(
                    f"Duplicate partner level token {token!r} in factors.partner_levels[{index}]"
                )
            seen_partners.add(token)

    if "confluence_mode" in factors:
        modes = factors["confluence_mode"]
        if not isinstance(modes, list) or not modes:
            raise StudySpecError("factors.confluence_mode must be a non-empty list")
        for index, mode in enumerate(modes):
            if mode not in VALID_CONFLUENCE_MODES:
                raise StudySpecError(
                    f"factors.confluence_mode[{index}] must be one of "
                    f"{sorted(VALID_CONFLUENCE_MODES)}; got {mode!r}"
                )

    if "trigger" in factors:
        triggers = factors["trigger"]
        if not isinstance(triggers, list) or not triggers:
            raise StudySpecError("factors.trigger must be a non-empty list")
        for index, trigger in enumerate(triggers):
            if trigger not in VALID_TRIGGERS:
                raise StudySpecError(
                    f"factors.trigger[{index}] must be one of "
                    f"{sorted(VALID_TRIGGERS)}; got {trigger!r}"
                )

    if "trigger_timeframe" in factors:
        timeframes = factors["trigger_timeframe"]
        if not isinstance(timeframes, list) or not timeframes:
            raise StudySpecError("factors.trigger_timeframe must be a non-empty list")
        for index, timeframe in enumerate(timeframes):
            if timeframe not in VALID_TRIGGER_TIMEFRAMES:
                raise StudySpecError(
                    f"factors.trigger_timeframe[{index}] must be one of "
                    f"{sorted(VALID_TRIGGER_TIMEFRAMES)}; got {timeframe!r} "
                    f"(30min is not a valid trigger timeframe)"
                )

    if "direction" in factors:
        directions = factors["direction"]
        if not isinstance(directions, list) or not directions:
            raise StudySpecError("factors.direction must be a non-empty list")
        for index, direction in enumerate(directions):
            if direction not in VALID_DIRECTIONS:
                raise StudySpecError(
                    f"factors.direction[{index}] must be one of "
                    f"{sorted(VALID_DIRECTIONS)}; got {direction!r}"
                )

    if "otf" in factors:
        otf_values = factors["otf"]
        if not isinstance(otf_values, list) or not otf_values:
            raise StudySpecError("factors.otf must be a non-empty list")
        seen_otf: list[dict[str, Any]] = []
        for index, entry in enumerate(otf_values):
            normalized = _normalize_otf_factor_entry(entry, path=f"factors.otf[{index}]")
            if normalized in seen_otf:
                raise StudySpecError(
                    f"factors.otf[{index}] duplicates a prior OTF config after "
                    f"normalization (alias forks are not distinct factor levels)"
                )
            seen_otf.append(normalized)


def _validate_mode_rules(mode_rules: Mapping[str, Any], *, factors: Mapping[str, Any]) -> None:
    modes = factors.get("confluence_mode")
    if not isinstance(modes, list) or not modes:
        raise StudySpecError("study.mode_rules requires a non-empty factors.confluence_mode list")
    for mode in modes:
        if mode not in mode_rules:
            raise StudySpecError(f"study.mode_rules missing entry for confluence mode {mode!r}")
        entry = _require_mapping(mode_rules.get(mode), section=f"study.mode_rules.{mode}")
        if mode == "global_cluster":
            selected = entry.get("selected_levels")
            if not isinstance(selected, list) or not selected:
                raise StudySpecError(
                    "study.mode_rules.global_cluster.selected_levels must be a non-empty list"
                )
        if mode == "anchor_rules":
            if "selected_levels" not in entry or entry.get("selected_levels") != []:
                raise StudySpecError("study.mode_rules.anchor_rules.selected_levels must be []")
            anchor = entry.get("anchor_level")
            if not isinstance(anchor, str) or not anchor.strip():
                raise StudySpecError(
                    "study.mode_rules.anchor_rules.anchor_level must be a non-empty string"
                )
            rules = entry.get("confluence_rules")
            if not isinstance(rules, Mapping):
                raise StudySpecError(
                    "study.mode_rules.anchor_rules.confluence_rules must be a mapping"
                )
            if rules.get("from_partners") not in {"required", "optional"}:
                raise StudySpecError(
                    "study.mode_rules.anchor_rules.confluence_rules.from_partners "
                    "must be 'required' or 'optional'"
                )


def _validate_report(report: Mapping[str, Any], *, factor_keys: set[str]) -> None:
    primary = report.get("primary_metric")
    if primary not in _INDEX_PRIMARY_METRICS:
        raise StudySpecError(
            f"study.report.primary_metric must be one of "
            f"{sorted(_INDEX_PRIMARY_METRICS)}; got {primary!r}"
        )
    secondary = report.get("secondary_metrics")
    if not isinstance(secondary, list):
        raise StudySpecError("study.report.secondary_metrics must be a list")
    min_trades = report.get("min_trades")
    if isinstance(min_trades, bool) or not isinstance(min_trades, int) or min_trades < 0:
        raise StudySpecError("study.report.min_trades must be an integer >= 0")

    group_by = report.get("group_by")
    if group_by is not None:
        if not isinstance(group_by, list):
            raise StudySpecError("study.report.group_by must be a list")
        for index, key in enumerate(group_by):
            if key not in factor_keys:
                raise StudySpecError(
                    f"study.report.group_by[{index}] must be a factor axis on "
                    f"this study; got {key!r}"
                )

    multiple_testing = report.get("multiple_testing")
    if multiple_testing not in _MULTIPLE_TESTING_MODES:
        raise StudySpecError(
            f"study.report.multiple_testing must be one of "
            f"{sorted(_MULTIPLE_TESTING_MODES)}; got {multiple_testing!r}"
        )

    baseline = report.get("otf_baseline")
    if baseline is not None:
        baseline_map = _require_mapping(baseline, section="study.report.otf_baseline")
        if "enabled" not in baseline_map:
            raise StudySpecError("study.report.otf_baseline must include explicit enabled")
        if not isinstance(baseline_map["enabled"], bool):
            raise StudySpecError("study.report.otf_baseline.enabled must be a boolean")


def _factor_axis_allows_value(
    axis: str,
    value: Any,
    factors: Mapping[str, Any],
    *,
    path: str,
) -> None:
    """Require ``value`` to be a member of ``factors[axis]`` (OTF via normalize)."""
    domain = factors[axis]
    if axis == "partner_levels":
        if not isinstance(value, list) or not value:
            raise StudySpecError(f"{path} must be a non-empty list")
        if not any(list(value) == list(partner_set) for partner_set in domain):
            raise StudySpecError(f"{path} value {value!r} is not one of factors.partner_levels")
        return
    if axis == "otf":
        normalized = _normalize_otf_factor_entry(value, path=path)
        for index, entry in enumerate(domain):
            candidate = _normalize_otf_factor_entry(entry, path=f"factors.otf[{index}]")
            if candidate == normalized:
                return
        raise StudySpecError(f"{path} OTF config is not one of factors.otf")
    if value not in domain:
        raise StudySpecError(f"{path} value {value!r} is not one of factors.{axis}")


def _validate_stage(stage: Mapping[str, Any], *, factors: Mapping[str, Any]) -> None:
    factor_keys = set(factors)
    mode = stage.get("mode")
    if mode not in {"filter", "explicit_cells"}:
        raise StudySpecError(f"study.stage.mode must be 'filter' or 'explicit_cells'; got {mode!r}")

    if mode == "filter":
        if "include" not in stage:
            raise StudySpecError("study.stage.mode=filter requires stage.include")
        include = _require_mapping(stage.get("include"), section="study.stage.include")
        unknown = sorted(set(include) - factor_keys)
        if unknown:
            raise StudySpecError(
                f"study.stage.include keys must be subset of factors; unknown: {unknown}"
            )
        if not include:
            raise StudySpecError("study.stage.include must be a non-empty mapping")
        for key, values in include.items():
            parsed = _require_list(values, field=f"study.stage.include.{key}")
            if not parsed:
                raise StudySpecError(f"study.stage.include.{key} must be a non-empty list")
            for index, value in enumerate(parsed):
                _factor_axis_allows_value(
                    key,
                    value,
                    factors,
                    path=f"study.stage.include.{key}[{index}]",
                )
        if "cells" in stage:
            raise StudySpecError("study.stage.mode=filter must not include stage.cells")
        return

    # explicit_cells
    if "include" in stage:
        raise StudySpecError("study.stage.mode=explicit_cells must not include stage.include")
    cells = stage.get("cells")
    if not isinstance(cells, list) or not cells:
        raise StudySpecError("study.stage.mode=explicit_cells requires non-empty stage.cells")
    for index, cell in enumerate(cells):
        cell_map = _require_mapping(cell, section=f"study.stage.cells[{index}]")
        missing = sorted(factor_keys - set(cell_map))
        if missing:
            raise StudySpecError(f"study.stage.cells[{index}] missing factor keys: {missing}")
        extra = sorted(set(cell_map) - factor_keys)
        if extra:
            raise StudySpecError(f"study.stage.cells[{index}] unknown factor keys: {extra}")
        for axis in sorted(factor_keys):
            _factor_axis_allows_value(
                axis,
                cell_map[axis],
                factors,
                path=f"study.stage.cells[{index}].{axis}",
            )


def load_study_spec(path: str | Path) -> dict[str, Any]:
    """Load YAML, normalize, and validate a StudySpec file."""
    study_path = Path(path)
    try:
        payload = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StudySpecError(f"Unable to load StudySpec {study_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise StudySpecError("StudySpec file must contain a YAML mapping")
    normalized = normalize_study_spec(payload)
    return validate_study_spec(normalized)
