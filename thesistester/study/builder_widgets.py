"""Studies Build widget / stage helpers (C-24 / QI-07-07).

Pure helpers for ``pages/15_Studies.py``. No Streamlit import here.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from thesistester.study.builder_draft import (
    COMMON_MA_LENGTHS,
    OTF_PRESET_ORDER,
    OTF_PRESETS,
    PREFERRED_REPORT_GROUP_BY,
    STAGE_MODE_EXPLICIT,
    STAGE_MODE_FILTER,
    STAGE_MODE_FULL,
    StudyDraft,
    TF_MODE_EXPLICIT,
    TF_MODE_NO_MA,
    TF_MODE_PRODUCT_DEFAULT,
    _LEVELS_ADVANCED_KEYS,
)
from thesistester.study.builder_hydrate import otf_preset_ids
from thesistester.study.schema import closed_level_token_set


def _partner_set_widget_key(index: int) -> str:
    """Stable Streamlit widget key for partner-set row ``index`` (SB2)."""
    return f"_study_builder_partner_set_{index}"


def _stage_include_widget_key(axis: str) -> str:
    """Stable Streamlit widget key for a stage-filter include axis (SB3)."""
    return f"_study_builder_stage_include_{axis}"


def infer_tf_mode(levels: Mapping[str, Any], key: str) -> str:
    """Map a levels TF key to the SB2 radio label."""
    if key not in levels or levels[key] is None:
        return TF_MODE_PRODUCT_DEFAULT
    value = levels[key]
    if isinstance(value, list) and len(value) == 0:
        return TF_MODE_NO_MA
    return TF_MODE_EXPLICIT


def apply_levels_tf_mode(
    levels: Mapping[str, Any],
    key: str,
    mode: str,
    selected: list[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``levels`` with ``key`` omitted, ``[]``, or explicit TFs."""
    out = copy.deepcopy(dict(levels))
    if mode == TF_MODE_PRODUCT_DEFAULT:
        out.pop(key, None)
    elif mode == TF_MODE_NO_MA:
        out[key] = []
    else:
        out[key] = [str(item) for item in (selected or [])]
    return out


def parse_csv_ints(text: str) -> list[int]:
    """Parse comma-separated integers (grid SL/TP lists)."""
    values: list[int] = []
    for part in str(text).split(","):
        stripped = part.strip()
        if not stripped:
            continue
        values.append(int(stripped))
    return values


def parse_csv_tokens(text: str) -> list[str]:
    """Parse comma-separated tokens (vwap/poc/pivot windows)."""
    return [part.strip() for part in str(text).split(",") if part.strip()]


def format_csv_values(values: Any) -> str:
    """Join a list for a text widget."""
    if not isinstance(values, list):
        return ""
    return ", ".join(str(item) for item in values)


def levels_advanced_enabled(levels: Mapping[str, Any]) -> bool:
    """True when the draft overrides optional window / pivot keys."""
    return any(key in levels for key in _LEVELS_ADVANCED_KEYS)


def ma_length_options(current: list[int], extra: int | None = None) -> list[int]:
    """Common MA lengths plus any already-selected or typed extras."""
    values = set(COMMON_MA_LENGTHS)
    values.update(int(item) for item in current)
    if extra is not None and int(extra) > 0:
        values.add(int(extra))
    return sorted(values)


def otf_from_preset_ids(ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]] | None:
    """Build ``draft.otf`` from selected preset ids (order locked)."""
    selected = {str(item) for item in ids}
    if not selected:
        return None
    return [
        copy.deepcopy(OTF_PRESETS[preset_id])
        for preset_id in OTF_PRESET_ORDER
        if preset_id in selected
    ]


def otf_for_selected_presets(
    selected: list[str] | tuple[str, ...],
    existing: list[Mapping[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Keep hydrated OTF dicts when chips are unchanged; rebuild only on edit.

    Widget collect must not replace pass-through / custom OTF rows just because
    the chips still match the resolved preset ids.
    """
    selected_set = {str(item) for item in selected if str(item) in OTF_PRESETS}
    matched = {preset_id for preset_id in otf_preset_ids(existing) if preset_id is not None}
    if selected_set == matched:
        if existing is None:
            return None
        return [copy.deepcopy(dict(entry)) for entry in existing]
    return otf_from_preset_ids(
        [preset_id for preset_id in OTF_PRESET_ORDER if preset_id in selected_set]
    )


def apply_grid_tick_widgets(
    grid: Mapping[str, Any],
    *,
    enabled: bool,
    sl_text: str,
    tp_text: str,
) -> dict[str, Any]:
    """Copy ``grid`` and apply SL/TP text widgets when the battery is on.

    Empty fields become ``[]`` (do not keep hydrated / prior tick lists).
    Disabled grid keeps pass-through extras.
    """
    out = copy.deepcopy(dict(grid))
    out["enabled"] = enabled
    if enabled:
        out["stop_loss_ticks_values"] = parse_csv_ints(sl_text)
        out["take_profit_ticks_values"] = parse_csv_ints(tp_text)
    return out


def coerce_whole_number(value: Any, default: int | float = 0) -> int | float:
    """Keep integer YAML when a float widget stores a whole number (``0`` vs ``0.0``)."""
    if value is None:
        return default
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def infer_stage_mode_label(stage_mode: str | None) -> str:
    """Map draft ``stage_mode`` to the SB3 radio label."""
    if stage_mode == "filter":
        return STAGE_MODE_FILTER
    if stage_mode == "explicit_cells":
        return STAGE_MODE_EXPLICIT
    return STAGE_MODE_FULL


def stage_mode_from_label(label: str) -> str | None:
    """Map the SB3 radio label to ``draft.stage_mode`` (``None`` = omit stage)."""
    if label == STAGE_MODE_FILTER:
        return "filter"
    if label == STAGE_MODE_EXPLICIT:
        return "explicit_cells"
    return None


def declared_factor_domains(draft: StudyDraft) -> dict[str, list[Any]]:
    """Current factor-widget domains, in emit axis order."""
    domains: dict[str, list[Any]] = {
        "core_level": list(draft.core_level),
        "partner_levels": [list(partner_set) for partner_set in draft.partner_levels],
        "confluence_mode": list(draft.confluence_mode),
        "trigger": list(draft.trigger),
        "trigger_timeframe": list(draft.trigger_timeframe),
    }
    if draft.otf is not None:
        domains["otf"] = copy.deepcopy(draft.otf)
    if draft.direction_as_factor:
        domains["direction"] = list(draft.direction_values)
    return domains


def format_stage_value(axis: str, value: Any) -> str:
    """Stable picker / table label for a factor value."""
    if axis == "partner_levels":
        if isinstance(value, list):
            return "+".join(str(token) for token in value) if value else "[]"
        return str(value)
    if axis == "otf":
        if isinstance(value, Mapping):
            matched = otf_preset_ids([value])
            if matched and matched[0] is not None:
                return str(matched[0])
            if value.get("enabled") is False:
                return "off"
            timeframes = value.get("timeframes")
            if isinstance(timeframes, list) and timeframes:
                return "+".join(str(item) for item in timeframes)
        return "custom"
    return str(value)


def resolve_stage_label(axis: str, label: str, domain: list[Any]) -> Any | None:
    """Return the domain member whose label equals ``label``, else ``None``."""
    target = str(label)
    for item in domain:
        if format_stage_value(axis, item) == target:
            return copy.deepcopy(item) if isinstance(item, (dict, list)) else item
    return None


def collect_stage_include(
    domains: Mapping[str, list[Any]],
    selected_labels: Mapping[str, list[str]],
) -> dict[str, list[Any]]:
    """Build ``stage.include`` from picker labels. Values are ⊆ ``domains``."""
    include: dict[str, list[Any]] = {}
    for axis, labels in selected_labels.items():
        if axis not in domains:
            continue
        domain = list(domains[axis])
        values: list[Any] = []
        seen: set[str] = set()
        for label in labels:
            resolved = resolve_stage_label(axis, str(label), domain)
            if resolved is None:
                continue
            key = format_stage_value(axis, resolved)
            if key in seen:
                continue
            seen.add(key)
            values.append(resolved)
        if values:
            include[axis] = values
    return include


def delete_stage_cells(
    cells: list[Mapping[str, Any]],
    indices: set[int] | frozenset[int],
) -> list[dict[str, Any]]:
    """Drop selected explicit-cell rows. Does not invent replacements."""
    return [
        copy.deepcopy(dict(cell))
        for index, cell in enumerate(cells)
        if index not in indices and isinstance(cell, Mapping)
    ]


def explicit_cell_row_label(index: int, cell: Mapping[str, Any]) -> str:
    """One-line label for the delete-row picker."""
    parts: list[str] = []
    for axis in (
        "core_level",
        "partner_levels",
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
        "otf",
        "direction",
    ):
        if axis in cell:
            parts.append(format_stage_value(axis, cell[axis]))
    return f"{index}: " + " · ".join(parts) if parts else f"{index}: cell"


def preferred_group_by(factor_keys: set[str] | frozenset[str]) -> list[str]:
    """Normalize default: preferred axes that exist on this study."""
    return [axis for axis in PREFERRED_REPORT_GROUP_BY if axis in factor_keys]


def constrain_group_by(
    selected: list[str],
    factor_keys: set[str] | frozenset[str],
) -> list[str]:
    """Drop group_by axes that are not declared factors."""
    return [axis for axis in selected if axis in factor_keys]


def clamp_widget_selection(selected: Any, options: list[Any]) -> list[Any]:
    """Keep only values still in ``options`` (Streamlit multiselect fail-closed).

    Session keys survive factor-domain shrinks. A selected value that is not
    in ``options`` raises on the next rerun and bricks the Build tab.
    """
    if not isinstance(selected, list):
        return []
    allowed = set(options)
    return [item for item in selected if item in allowed]


def builder_token_catalog(levels: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Sorted closed level tokens implied by ``levels`` + the static catalog."""
    return tuple(sorted(closed_level_token_set(levels)))
