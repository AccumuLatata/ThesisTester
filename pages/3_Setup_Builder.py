from __future__ import annotations

import hashlib
import re
from typing import Any

import streamlit as st

from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.entry_window_policy import RTH_SEGMENT_LABELS, normalize_entry_window
from thesistester.persistence import (
    compute_otf_config_hash,
    delete_setup,
    list_saved_setups,
    load_setup,
    save_setup,
)
from thesistester.setup import (
    DEFAULT_OTF_FILTER_CONFIG,
    OTF_TIMEFRAME_CHOICES,
    DEFAULT_TRIGGER_TIMEFRAME,
    TRIGGER_TIMEFRAME_CHOICES,
    VALID_CONFLUENCE_MODES,
    VALID_DIRECTIONS,
    VALID_TRIGGER_TIMEFRAMES,
    VALID_TRIGGERS,
    available_level_columns,
    build_setup_config,
    build_setup_kwargs_from_mapping,
    default_selected_levels,
    get_effective_entry_window_config,
    get_effective_otf_filter_config,
    normalize_trigger_timeframe,
    normalize_otf_filter_config,
    validate_entry_window_config,
    validate_setup_config,
)
from thesistester.classic_context import render_classic_thesis_chrome
from thesistester.classic_nav import render_classic_nav_prefill_caption
from thesistester.classic_proposal import render_classic_proposal_card
from thesistester.engine.otf import OTF_ALGORITHM_VERSION
from thesistester.research_keys import pop_setup_mutation_signal_keys

ENTRY_WINDOW_MODE_OPTIONS = ("rth_segments", "clock_range")


CONFLUENCE_MODE_LABELS = {
    "Global cluster": "global_cluster",
    "Anchor-based rules": "anchor_rules",
}

CONFLUENCE_MODE_DISPLAY = {value: key for key, value in CONFLUENCE_MODE_LABELS.items()}
TRIGGER_TIMEFRAME_LABELS = {
    "Base/current timeframe": "base",
    "1 minute": "1min",
    "5 minutes": "5min",
    "15 minutes": "15min",
}
TRIGGER_TIMEFRAME_DISPLAY = {value: key for key, value in TRIGGER_TIMEFRAME_LABELS.items()}
EDITOR_STATE_KEY = "_setup_builder_editor_config"
PENDING_WIDGET_SYNC_KEY = "_setup_builder_pending_widget_sync"
WIDGET_KEY_SETUP_NAME = "_setup_builder_setup_name"
WIDGET_KEY_DESCRIPTION = "_setup_builder_description"
WIDGET_KEY_SAVED_SETUP = "_setup_builder_saved_setup"
WIDGET_KEY_CONFLUENCE_MODE = "_setup_builder_confluence_mode"
WIDGET_KEY_SELECTED_LEVELS = "_setup_builder_selected_levels"
WIDGET_KEY_TOLERANCE_TICKS = "_setup_builder_tolerance_ticks"
WIDGET_KEY_MIN_CONFLUENCES = "_setup_builder_min_confluences"
WIDGET_KEY_MAX_CONFLUENCES = "_setup_builder_max_confluences"
WIDGET_KEY_ANCHOR_LEVEL = "_setup_builder_anchor_level"
WIDGET_KEY_CONFLUENCE_LEVELS = "_setup_builder_confluence_levels"
WIDGET_KEY_MIN_VALID_CONFLUENCES = "_setup_builder_min_valid_confluences"
WIDGET_KEY_NAKED_ONLY = "_setup_builder_naked_only"
WIDGET_KEY_NAKED_REQUIREMENT = "_setup_builder_naked_requirement"
WIDGET_KEY_TRIGGER = "_setup_builder_trigger"
WIDGET_KEY_TRIGGER_TIMEFRAME = "_setup_builder_trigger_timeframe"
WIDGET_KEY_DIRECTION = "_setup_builder_direction"
WIDGET_KEY_ENTRY_RETRACE_TICKS = "_setup_builder_entry_retrace_ticks"
WIDGET_KEY_REQUIRE_CLOSE_CONFIRMATION = "_setup_builder_require_close_confirmation"
WIDGET_KEY_MAX_ENTRY_WAIT_BARS = "_setup_builder_max_entry_wait_bars"
WIDGET_KEY_ALLOW_MISSING_LEVEL_REMOVAL = "_setup_builder_allow_missing_level_removal"
WIDGET_KEY_OTF_ENABLED = "_setup_builder_otf_enabled"
WIDGET_KEY_OTF_TIMEFRAMES = "_setup_builder_otf_timeframes"
WIDGET_KEY_OTF_ALIGNMENT_MODE = "_setup_builder_otf_alignment_mode"
WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS = "_setup_builder_otf_min_consecutive_bars"
WIDGET_KEY_OTF_DIRECTIONAL = "_setup_builder_otf_directional"
WIDGET_KEY_OTF_COMPLETED_BARS_ONLY = "_setup_builder_otf_completed_bars_only"
WIDGET_KEY_OTF_SESSION_RESET = "_setup_builder_otf_session_reset"
WIDGET_KEY_ENTRY_WINDOW_ENABLED = "_setup_builder_entry_window_enabled"
WIDGET_KEY_ENTRY_WINDOW_MODE = "_setup_builder_entry_window_mode"
WIDGET_KEY_ENTRY_WINDOW_RTH_SEGMENTS = "_setup_builder_entry_window_rth_segments"
WIDGET_KEY_ENTRY_WINDOW_START_TIME = "_setup_builder_entry_window_start_time"
WIDGET_KEY_ENTRY_WINDOW_END_TIME = "_setup_builder_entry_window_end_time"
WIDGET_KEY_ENTRY_WINDOW_TIMEZONE = "_setup_builder_entry_window_timezone"
_OTF_REPAIR_DICT_KEY = "_otf_repair_warning"
_ENTRY_WINDOW_REPAIR_DICT_KEY = "_entry_window_repair_warning"
_SETUP_BUILDER_OTF_REPAIR_SESSION_KEY = "_setup_builder_otf_repair_warning"
_SETUP_BUILDER_ENTRY_WINDOW_REPAIR_SESSION_KEY = "_setup_builder_entry_window_repair_warning"


def _anchor_rule_key(prefix: str, level: str) -> str:
    """Build a stable Streamlit widget key for an anchor-rule control."""
    sanitized_level = re.sub(r"[^0-9A-Za-z_]+", "_", level).strip("_")
    level_hash = hashlib.sha256(level.encode("utf-8")).hexdigest()[:8]
    key_level = f"{sanitized_level}_{level_hash}" if sanitized_level else f"level_{level_hash}"
    return f"{prefix}_{key_level}"


def _safe_string_fallback(value: object, default: str) -> tuple[str, bool]:
    if isinstance(value, str):
        return value, False
    return default, True


def _safe_int_fallback(
    value: object,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> tuple[int, bool]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default, True
    clamped = max(min_value, min(max_value, parsed))
    return clamped, clamped != parsed


def _safe_float_fallback(
    value: object,
    *,
    default: float,
    min_value: float,
) -> tuple[float, bool]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default, True
    clamped = max(min_value, parsed)
    return clamped, clamped != parsed


def _safe_selectbox_index_fallback(
    value: object,
    *,
    options: list[str],
    default: str,
) -> tuple[int, str, bool]:
    if not options:
        return 0, default, True
    fallback = default if default in options else options[0]
    if isinstance(value, str) and value in options:
        return options.index(value), value, False
    return options.index(fallback), fallback, True


def _safe_enum_fallback(value: object, *, valid: frozenset[str], default: str) -> tuple[str, bool]:
    if isinstance(value, str) and value in valid:
        return value, False
    return default, True


def _safe_require_close_confirmation(value: object) -> bool:
    """Match C-1 ``_normalize_approach_side_params`` string/flag parsing."""
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _safe_trigger_fallback(value: object) -> tuple[str, bool]:
    return _safe_enum_fallback(value, valid=VALID_TRIGGERS, default="touch")


def _safe_direction_fallback(value: object) -> tuple[str, bool]:
    return _safe_enum_fallback(value, valid=VALID_DIRECTIONS, default="both")


def _safe_trigger_timeframe_fallback(value: object) -> tuple[str, bool]:
    normalized = normalize_trigger_timeframe(value)
    if normalized in VALID_TRIGGER_TIMEFRAMES:
        return normalized, False
    return DEFAULT_TRIGGER_TIMEFRAME, True


def _safe_confluence_mode_fallback(value: object) -> tuple[str, bool]:
    return _safe_enum_fallback(value, valid=VALID_CONFLUENCE_MODES, default="global_cluster")


def _append_fallback_warning(warnings: list[str], fallback: bool, message: str) -> None:
    if fallback:
        warnings.append(message)


def _resolve_otf_for_ui(config: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Return (canonical_otf_config, warning_or_None) for UI hydration.

    Always returns a valid canonical OTF config. If the config's ``otf_filter``
    is malformed, falls back to canonical disabled defaults and returns a
    non-None warning message. Never raises.
    """
    try:
        return get_effective_otf_filter_config(config), None
    except ValueError:
        return normalize_otf_filter_config(None), (
            "OTF filter settings are invalid and were reset to disabled defaults for editing. "
            "Review and save in Setup Builder to persist the repaired configuration."
        )


def _resolve_entry_window_for_ui(config: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Return (canonical entry_window, warning_or_None) for UI hydration."""
    try:
        return get_effective_entry_window_config(config), None
    except ValueError:
        return get_effective_entry_window_config({}), (
            "Entry window settings are invalid and were reset to disabled defaults for editing. "
            "Review and save in Setup Builder to persist the repaired configuration."
        )


def _render_setup_summary(config: dict) -> None:
    confluence_mode = config.get("confluence_mode", "global_cluster")
    st.markdown(f"**Name:** {config['name']}")
    st.markdown(f"**Instrument:** {config['instrument']}")
    st.markdown(f"**Description:** {config.get('description', '') or '-'}")
    st.markdown(f"**Mode:** {CONFLUENCE_MODE_DISPLAY.get(confluence_mode, confluence_mode)}")
    st.markdown(
        f"**Selected levels ({len(config['selected_levels'])}):** {', '.join(config['selected_levels'])}"
    )
    if confluence_mode == "anchor_rules":
        st.markdown(f"**Anchor:** {config.get('anchor_level') or '-'}")
        st.markdown(f"**Rules:** {len(config.get('confluence_rules', []))}")
        st.markdown(f"**Minimum valid confluences:** {config.get('min_valid_confluences', 1)}")
    else:
        st.markdown(f"**Tolerance ticks:** {config['tolerance_ticks']}")
        st.markdown(f"**Confluences:** {config['min_confluences']} to {config['max_confluences']}")
    st.markdown(f"**Naked only:** {config['naked_only']}")
    st.markdown(f"**Naked requirement:** {config['naked_requirement']}")
    st.markdown(f"**Trigger:** {config['trigger']}")
    trigger = str(config.get("trigger", ""))
    trigger_timeframe = normalize_trigger_timeframe(config.get("trigger_timeframe"))
    st.markdown(
        f"**Trigger timeframe:** "
        f"{TRIGGER_TIMEFRAME_DISPLAY.get(trigger_timeframe, 'Base/current timeframe')}"
    )
    st.markdown(f"**Direction:** {config['direction']}")
    if trigger == "3c":
        params = config.get("trigger_params", {})
        st.markdown("**Trigger params:**")
        st.markdown(
            f"- Entry retrace ticks: {params.get('entry_retrace_ticks', 4.0)}\n"
            f"- Max entry wait bars after reversal: {params.get('max_entry_wait_bars_after_reversal', 5)}"
        )
    elif trigger in {"fade", "continuation"}:
        params = (
            config.get("trigger_params", {})
            if isinstance(config.get("trigger_params"), dict)
            else {}
        )
        st.markdown("**Trigger params:**")
        st.markdown(
            f"- Require close confirmation: {bool(params.get('require_close_confirmation', False))}"
        )
    otf_config, otf_resolve_warning = _resolve_otf_for_ui(config)
    if otf_resolve_warning:
        st.warning(otf_resolve_warning)
    st.markdown("**OTF filter configuration:**")
    st.markdown(f"- Enabled: {otf_config['enabled']}")
    st.markdown(
        f"- Timeframes: {', '.join(otf_config['timeframes']) if otf_config['timeframes'] else '(none)'}"
    )
    st.markdown(f"- Alignment mode: {otf_config['alignment_mode']}")
    st.markdown(f"- Minimum consecutive bars: {otf_config['minimum_consecutive_bars']}")
    st.markdown(f"- Directional: {otf_config['directional']}")
    st.markdown(f"- Completed bars only: {otf_config['use_completed_bars_only']}")
    st.markdown(f"- Session reset: {otf_config['session_reset']}")
    st.markdown(f"- OTF algorithm version: {OTF_ALGORITHM_VERSION}")
    st.markdown(f"- OTF configuration hash: {compute_otf_config_hash(otf_config)}")


def _duplicate_setup_name(name: str) -> str:
    base_name = (name or "").strip() or "Untitled setup"
    return f"{base_name} copy"


def _newest_first_bucketed_setups(
    setups: list[dict[str, Any]],
    *,
    current_dataset_id: str | None,
) -> list[dict[str, Any]]:
    def _bucket(item: dict[str, Any]) -> int:
        dataset_id = item.get("dataset_id")
        if (
            isinstance(current_dataset_id, str)
            and current_dataset_id
            and dataset_id == current_dataset_id
        ):
            return 0
        if dataset_id in (None, ""):
            return 1
        return 2

    return sorted(setups, key=_bucket)


def _dataset_relation_label(setup_dataset_id: object, current_dataset_id: str | None) -> str:
    if setup_dataset_id in (None, ""):
        return "global/no dataset"
    if (
        isinstance(current_dataset_id, str)
        and current_dataset_id
        and setup_dataset_id == current_dataset_id
    ):
        return "current dataset"
    return "other dataset"


# QI-03-12 / D-2: setup save / set-active / clear / delete-active pops the
# in-session candidate cluster so leftover ``signals`` cannot reach Backtest
# unflagged. Shared pop list lives on ``research_keys`` (same siblings
# dataset-clear pops) so a leftover hash cannot look like a match.
def _invalidate_session_signals_after_setup_mutation(session_state: Any) -> None:
    """Pop leftover candidates after a setup_config mutation (QI-03-12)."""
    pop_setup_mutation_signal_keys(session_state)


def _saved_setup_label(meta: dict[str, Any], current_dataset_id: str | None) -> str:
    updated_raw = meta.get("updated_at") or meta.get("created_at") or ""
    updated = str(updated_raw)[:10] if updated_raw else "unknown date"
    return (
        f"{meta.get('name', 'Untitled setup')} · {meta.get('instrument', '—')} · "
        f"{updated} · mode={meta.get('setup_config', {}).get('confluence_mode', 'global_cluster')} · "
        f"trigger={meta.get('setup_config', {}).get('trigger', 'touch')} · "
        f"direction={meta.get('setup_config', {}).get('direction', 'both')} · "
        f"{_dataset_relation_label(meta.get('dataset_id'), current_dataset_id)}"
    )


def _default_editor_config(
    *,
    instrument: str,
    defaults: list[str],
    dataset_id: str | None,
) -> dict[str, Any]:
    """Product fallbacks from ``build_setup_config`` (C-1 / C-4)."""
    built = build_setup_config(
        name="Untitled setup",
        description="",
        instrument=instrument,
        selected_levels=list(defaults),
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        trigger_timeframe=DEFAULT_TRIGGER_TIMEFRAME,
        direction="both",
        confluence_mode="global_cluster",
        anchor_level=None,
        confluence_rules=[],
        min_valid_confluences=1,
        trigger_params={},
        otf_filter=DEFAULT_OTF_FILTER_CONFIG,
        entry_window=None,
    )
    built["otf_algorithm_version"] = OTF_ALGORITHM_VERSION
    built["otf_config_hash"] = compute_otf_config_hash(built["otf_filter"])
    built["setup_id"] = None
    built["dataset_id"] = dataset_id
    return built


def _seed_editor_config(
    *,
    active_setup: dict[str, Any] | None,
    instrument: str,
    defaults: list[str],
    dataset_id: str | None,
) -> dict[str, Any]:
    seeded = _default_editor_config(instrument=instrument, defaults=defaults, dataset_id=dataset_id)
    if isinstance(active_setup, dict) and active_setup:
        seeded.update(active_setup)
    seeded["selected_levels"] = list(seeded.get("selected_levels") or defaults)
    seeded["trigger_timeframe"] = normalize_trigger_timeframe(seeded.get("trigger_timeframe"))
    otf_config, otf_warning = _resolve_otf_for_ui(seeded)
    seeded["otf_filter"] = otf_config
    if otf_warning:
        seeded[_OTF_REPAIR_DICT_KEY] = otf_warning
    seeded["otf_algorithm_version"] = OTF_ALGORITHM_VERSION
    seeded["otf_config_hash"] = compute_otf_config_hash(seeded["otf_filter"])
    entry_window_config, entry_window_warning = _resolve_entry_window_for_ui(seeded)
    seeded["entry_window"] = entry_window_config
    if entry_window_warning:
        seeded[_ENTRY_WINDOW_REPAIR_DICT_KEY] = entry_window_warning
    seeded["dataset_id"] = seeded.get("dataset_id", dataset_id)
    return seeded


def _unavailable_level_references(
    config: dict[str, Any], level_columns: list[str]
) -> dict[str, list[str]]:
    mode = _safe_confluence_mode_fallback(config.get("confluence_mode"))[0]
    if mode == "anchor_rules":
        missing_anchor: list[str] = []
        anchor_level = config.get("anchor_level")
        if isinstance(anchor_level, str) and anchor_level and anchor_level not in level_columns:
            missing_anchor.append(anchor_level)
        missing_rules: list[str] = []
        for rule in config.get("confluence_rules", []):
            if not isinstance(rule, dict):
                continue
            level = str(rule.get("level", "")).strip()
            if level and level not in level_columns:
                missing_rules.append(level)
        return {
            "anchor_level": sorted(set(missing_anchor)),
            "confluence_rules": sorted(set(missing_rules)),
            "selected_levels": [],
        }

    selected_levels = config.get("selected_levels", [])
    if not isinstance(selected_levels, list):
        return {"anchor_level": [], "confluence_rules": [], "selected_levels": []}
    return {
        "anchor_level": [],
        "confluence_rules": [],
        "selected_levels": sorted(
            {
                str(level)
                for level in selected_levels
                if str(level) and str(level) not in level_columns
            }
        ),
    }


def _has_unavailable_level_references(unavailable: dict[str, list[str]]) -> bool:
    return any(
        unavailable.get(key) for key in ("anchor_level", "confluence_rules", "selected_levels")
    )


def _render_editor_sync_warnings(warnings: list[str]) -> None:
    """Render sync fallbacks. Sync itself never calls Streamlit widgets."""
    for warning_message in warnings:
        st.warning(warning_message)


def _render_setup_level_warnings(config: dict[str, Any], level_columns: list[str]) -> None:
    unavailable = _unavailable_level_references(config, level_columns)
    if unavailable["anchor_level"]:
        st.warning(
            f"Loaded setup anchor level is unavailable in current levels: {', '.join(unavailable['anchor_level'])}."
        )
    if unavailable["confluence_rules"]:
        st.warning(
            f"Loaded setup has unavailable confluence-rule levels: {', '.join(unavailable['confluence_rules'])}."
        )
    if unavailable["selected_levels"]:
        st.warning(
            f"Loaded setup contains unavailable selected levels: {', '.join(unavailable['selected_levels'])}. "
            "Only available levels are preselected in the editor."
        )


def _hydrate_identity_fields(config: dict[str, Any], warnings: list[str]) -> tuple[str, str]:
    name_value, name_fallback = _safe_string_fallback(config.get("name"), "Untitled setup")
    _append_fallback_warning(
        warnings, name_fallback, "Loaded setup name is invalid; using default name."
    )
    description_value, description_fallback = _safe_string_fallback(config.get("description"), "")
    _append_fallback_warning(
        warnings,
        description_fallback,
        "Loaded setup description is invalid; using empty description.",
    )
    return name_value, description_value


def _hydrate_selected_levels(
    config: dict[str, Any], level_columns: list[str], warnings: list[str]
) -> list[str]:
    selected_levels = config.get("selected_levels")
    if isinstance(selected_levels, list):
        return [str(level) for level in selected_levels if str(level) in level_columns]
    warnings.append("Loaded selected levels are invalid; using default level selection.")
    return default_selected_levels(level_columns)


def _hydrate_global_cluster_fields(
    config: dict[str, Any], warnings: list[str]
) -> tuple[float, int, int]:
    tolerance_ticks, tolerance_fallback = _safe_float_fallback(
        config.get("tolerance_ticks"),
        default=4.0,
        min_value=0.0,
    )
    _append_fallback_warning(
        warnings, tolerance_fallback, "Loaded tolerance ticks is invalid; using a safe value."
    )
    min_confluences, min_confluences_fallback = _safe_int_fallback(
        config.get("min_confluences"),
        default=2,
        min_value=1,
        max_value=5,
    )
    _append_fallback_warning(
        warnings,
        min_confluences_fallback,
        "Loaded minimum confluences is invalid; using a safe value.",
    )
    max_confluences, max_confluences_fallback = _safe_int_fallback(
        config.get("max_confluences"),
        default=5,
        min_value=min_confluences,
        max_value=5,
    )
    _append_fallback_warning(
        warnings,
        max_confluences_fallback,
        "Loaded maximum confluences is invalid; using a safe value.",
    )
    return tolerance_ticks, min_confluences, max_confluences


def _hydrate_rule_defaults(rules_seed: object, warnings: list[str]) -> dict[str, dict[str, Any]]:
    rule_defaults: dict[str, dict[str, Any]] = {}
    if not isinstance(rules_seed, list):
        return rule_defaults
    for rule in rules_seed:
        if not isinstance(rule, dict):
            continue
        level = str(rule.get("level", "")).strip()
        if not level:
            continue
        tol_value, tol_fallback = _safe_float_fallback(
            rule.get("tolerance_ticks"),
            default=4.0,
            min_value=0.0,
        )
        _append_fallback_warning(
            warnings,
            tol_fallback,
            f"Loaded tolerance for confluence rule '{level}' is invalid; using a safe value.",
        )
        rule_defaults[level] = {
            "tolerance_ticks": tol_value,
            "required": bool(rule.get("required", False)),
        }
    return rule_defaults


def _hydrate_anchor_rule_fields(
    config: dict[str, Any],
    level_columns: list[str],
    mode_value: str,
    warnings: list[str],
) -> tuple[str | None, dict[str, dict[str, Any]], list[str], int]:
    anchor_seed = config.get("anchor_level")
    anchor_default = (
        str(anchor_seed)
        if isinstance(anchor_seed, str) and anchor_seed in level_columns
        else (level_columns[0] if level_columns else None)
    )
    rule_defaults = _hydrate_rule_defaults(config.get("confluence_rules", []), warnings)
    confluence_options = [level for level in level_columns if level != anchor_default]
    selected_confluence_levels = [level for level in rule_defaults if level in confluence_options]
    min_valid_default = 1
    if mode_value == "anchor_rules":
        min_valid_default, min_valid_fallback = _safe_int_fallback(
            config.get("min_valid_confluences"),
            default=1,
            min_value=0,
            max_value=max(len(selected_confluence_levels), 0),
        )
        _append_fallback_warning(
            warnings,
            min_valid_fallback,
            "Loaded minimum valid confluences is invalid; using a safe value.",
        )
    return anchor_default, rule_defaults, selected_confluence_levels, min_valid_default


def _hydrate_naked_requirement(config: dict[str, Any], warnings: list[str]) -> str:
    naked_requirement = str(config.get("naked_requirement", "any")).lower()
    if naked_requirement in {"any", "all"}:
        return naked_requirement
    warnings.append("Loaded naked requirement is invalid; falling back to 'any'.")
    return "any"


def _hydrate_trigger_fields(
    config: dict[str, Any], warnings: list[str]
) -> tuple[str, str, str, dict[str, Any], float, int, bool]:
    trigger, trigger_fallback = _safe_trigger_fallback(config.get("trigger"))
    _append_fallback_warning(
        warnings, trigger_fallback, "Loaded trigger is invalid; falling back to touch."
    )
    trigger_timeframe, timeframe_fallback = _safe_trigger_timeframe_fallback(
        config.get("trigger_timeframe")
    )
    _append_fallback_warning(
        warnings, timeframe_fallback, "Loaded trigger timeframe is invalid; falling back to base."
    )
    direction, direction_fallback = _safe_direction_fallback(config.get("direction"))
    _append_fallback_warning(
        warnings, direction_fallback, "Loaded direction is invalid; falling back to both."
    )
    trigger_params_seed = config.get("trigger_params", {})
    entry_retrace_default = 4.0
    max_wait_default = 5
    require_close_default = False
    trigger_params: dict[str, Any] = {}
    if trigger == "3c" and isinstance(trigger_params_seed, dict):
        entry_retrace_default, entry_retrace_fallback = _safe_float_fallback(
            trigger_params_seed.get("entry_retrace_ticks"),
            default=4.0,
            min_value=0.0,
        )
        max_wait_default, max_wait_fallback = _safe_int_fallback(
            trigger_params_seed.get("max_entry_wait_bars_after_reversal"),
            default=5,
            min_value=0,
            max_value=10_000,
        )
        _append_fallback_warning(
            warnings,
            entry_retrace_fallback,
            "Loaded entry retrace ticks is invalid; using a safe value.",
        )
        _append_fallback_warning(
            warnings,
            max_wait_fallback,
            "Loaded max entry wait bars is invalid; using a safe value.",
        )
        trigger_params = {
            "entry_retrace_ticks": entry_retrace_default,
            "max_entry_wait_bars_after_reversal": max_wait_default,
        }
    elif trigger in {"fade", "continuation"} and isinstance(trigger_params_seed, dict):
        require_close_default = _safe_require_close_confirmation(
            trigger_params_seed.get("require_close_confirmation", False)
        )
        trigger_params = {"require_close_confirmation": require_close_default}
    return (
        trigger,
        trigger_timeframe,
        direction,
        trigger_params,
        entry_retrace_default,
        max_wait_default,
        require_close_default,
    )


def _hydrate_otf_filter(config: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    try:
        return get_effective_otf_filter_config(config)
    except ValueError:
        warnings.append(
            "Loaded OTF filter settings are invalid; falling back to disabled defaults."
        )
        return normalize_otf_filter_config(None)


def _hydrate_entry_window(config: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    try:
        return get_effective_entry_window_config(config)
    except ValueError:
        warnings.append(
            "Loaded entry window settings are invalid; falling back to disabled defaults."
        )
        return get_effective_entry_window_config({})


def _hydrate_editor_widget_payload(
    config: dict[str, Any], level_columns: list[str], warnings: list[str]
) -> dict[str, Any]:
    """Repair a loaded setup for widgets; enums/ranges match ``validate_setup_config``."""
    name_value, description_value = _hydrate_identity_fields(config, warnings)
    mode_value, mode_fallback = _safe_confluence_mode_fallback(config.get("confluence_mode"))
    _append_fallback_warning(
        warnings,
        mode_fallback,
        "Loaded setup confluence mode is invalid; falling back to global_cluster.",
    )
    selected_level_seed = _hydrate_selected_levels(config, level_columns, warnings)
    tolerance_ticks, min_confluences, max_confluences = _hydrate_global_cluster_fields(
        config, warnings
    )
    (
        anchor_default,
        rule_defaults,
        selected_confluence_levels,
        min_valid_default,
    ) = _hydrate_anchor_rule_fields(config, level_columns, mode_value, warnings)
    (
        trigger,
        trigger_timeframe,
        direction,
        trigger_params,
        entry_retrace_default,
        max_wait_default,
        require_close_default,
    ) = _hydrate_trigger_fields(config, warnings)
    return {
        "name": name_value,
        "description": description_value,
        "instrument": str(config.get("instrument") or "ES"),
        "confluence_mode": mode_value,
        "selected_levels": selected_level_seed,
        "tolerance_ticks": tolerance_ticks,
        "min_confluences": min_confluences,
        "max_confluences": max_confluences,
        "anchor_level": anchor_default,
        "rule_defaults": rule_defaults,
        "selected_confluence_levels": selected_confluence_levels,
        "min_valid_confluences": min_valid_default,
        "naked_only": bool(config.get("naked_only", False)),
        "naked_requirement": _hydrate_naked_requirement(config, warnings),
        "trigger": trigger,
        "trigger_timeframe": trigger_timeframe,
        "direction": direction,
        "trigger_params": trigger_params,
        "entry_retrace": entry_retrace_default,
        "max_wait": max_wait_default,
        "require_close": require_close_default,
        "otf_filter": _hydrate_otf_filter(config, warnings),
        "entry_window": _hydrate_entry_window(config, warnings),
    }


def _build_synced_setup_config(
    payload: dict[str, Any], warnings: list[str]
) -> dict[str, Any] | None:
    """Canonicalize repaired fields through ``build_setup_config`` (C-4).

    On failure, keep the repaired payload (do not mix in product defaults)
    and record a warning. ``validate_setup_config`` is not a second default
    table — its enum/range sets already drove hydration.
    """
    confluence_rules = [
        {
            "level": level,
            "tolerance_ticks": payload["rule_defaults"][level]["tolerance_ticks"],
            "required": payload["rule_defaults"][level]["required"],
        }
        for level in payload["selected_confluence_levels"]
    ]
    kwargs = build_setup_kwargs_from_mapping(
        payload,
        confluence_rules=confluence_rules,
    )
    try:
        return build_setup_config(**kwargs)
    except (TypeError, ValueError):
        warnings.append(
            "Loaded setup could not be canonicalized through build_setup_config; "
            "using repaired editor values."
        )
        return None


def _assign_widget(key: str, value: Any, *, overwrite: bool) -> None:
    if overwrite or key not in st.session_state:
        st.session_state[key] = value


def _entry_window_widget_values(entry_window_config: dict[str, Any]) -> dict[str, Any]:
    mode = str(entry_window_config.get("mode") or "rth_segments")
    if mode not in ENTRY_WINDOW_MODE_OPTIONS:
        mode = "rth_segments"
    segments = [
        segment
        for segment in list(entry_window_config.get("rth_segments") or [])
        if segment in RTH_SEGMENT_LABELS
    ]
    window_tz = str(entry_window_config.get("timezone") or "America/New_York")
    if window_tz not in TIMEZONE_OPTIONS:
        window_tz = "America/New_York"
    return {
        WIDGET_KEY_ENTRY_WINDOW_ENABLED: bool(entry_window_config.get("enabled", False)),
        WIDGET_KEY_ENTRY_WINDOW_MODE: mode,
        WIDGET_KEY_ENTRY_WINDOW_RTH_SEGMENTS: segments or ["rth_open_30m"],
        WIDGET_KEY_ENTRY_WINDOW_START_TIME: str(entry_window_config.get("start_time") or "09:30"),
        WIDGET_KEY_ENTRY_WINDOW_END_TIME: str(entry_window_config.get("end_time") or "10:00"),
        WIDGET_KEY_ENTRY_WINDOW_TIMEZONE: window_tz,
    }


def _canonical_trigger_param_widgets(
    payload: dict[str, Any], built: dict[str, Any] | None
) -> tuple[float, int, bool]:
    """Prefer ``build_setup_config`` trigger_params; payload stays widget-safe."""
    entry_retrace = payload["entry_retrace"]
    max_wait = payload["max_wait"]
    require_close = payload["require_close"]
    if built is None:
        return entry_retrace, max_wait, require_close
    params = built.get("trigger_params")
    if not isinstance(params, dict):
        return entry_retrace, max_wait, require_close
    if "entry_retrace_ticks" in params:
        entry_retrace = params["entry_retrace_ticks"]
    if "max_entry_wait_bars_after_reversal" in params:
        max_wait = params["max_entry_wait_bars_after_reversal"]
    if "require_close_confirmation" in params:
        require_close = bool(params["require_close_confirmation"])
    return entry_retrace, max_wait, require_close


def _assign_editor_widget_state(
    payload: dict[str, Any], built: dict[str, Any] | None, *, overwrite: bool
) -> None:
    """Write session keys only. Render reads these keys; it does not sync.

    Canonical fields come from ``build_setup_config`` when canonicalize
    succeeded. Level-availability filters stay on the repaired payload.
    """
    src = built if built is not None else payload
    otf_config = src.get("otf_filter") or payload["otf_filter"]
    entry_retrace, max_wait, require_close = _canonical_trigger_param_widgets(payload, built)
    assignments: list[tuple[str, Any]] = [
        (WIDGET_KEY_SETUP_NAME, src.get("name", payload["name"])),
        (WIDGET_KEY_DESCRIPTION, src.get("description", payload["description"])),
        (
            WIDGET_KEY_CONFLUENCE_MODE,
            CONFLUENCE_MODE_DISPLAY.get(
                src.get("confluence_mode", payload["confluence_mode"]),
                "Global cluster",
            ),
        ),
        (WIDGET_KEY_SELECTED_LEVELS, payload["selected_levels"]),
        (WIDGET_KEY_TOLERANCE_TICKS, src.get("tolerance_ticks", payload["tolerance_ticks"])),
        (WIDGET_KEY_MIN_CONFLUENCES, src.get("min_confluences", payload["min_confluences"])),
        (WIDGET_KEY_MAX_CONFLUENCES, src.get("max_confluences", payload["max_confluences"])),
        (WIDGET_KEY_ANCHOR_LEVEL, payload["anchor_level"]),
        (WIDGET_KEY_CONFLUENCE_LEVELS, payload["selected_confluence_levels"]),
        (
            WIDGET_KEY_MIN_VALID_CONFLUENCES,
            src.get("min_valid_confluences", payload["min_valid_confluences"]),
        ),
        (WIDGET_KEY_NAKED_ONLY, bool(src.get("naked_only", payload["naked_only"]))),
        (WIDGET_KEY_NAKED_REQUIREMENT, src.get("naked_requirement", payload["naked_requirement"])),
        (WIDGET_KEY_TRIGGER, src.get("trigger", payload["trigger"])),
        (
            WIDGET_KEY_TRIGGER_TIMEFRAME,
            TRIGGER_TIMEFRAME_DISPLAY.get(
                src.get("trigger_timeframe", payload["trigger_timeframe"]),
                "Base/current timeframe",
            ),
        ),
        (WIDGET_KEY_DIRECTION, src.get("direction", payload["direction"])),
        (WIDGET_KEY_ENTRY_RETRACE_TICKS, entry_retrace),
        (WIDGET_KEY_MAX_ENTRY_WAIT_BARS, max_wait),
        (WIDGET_KEY_REQUIRE_CLOSE_CONFIRMATION, require_close),
        (WIDGET_KEY_OTF_ENABLED, bool(otf_config.get("enabled", False))),
        (WIDGET_KEY_OTF_TIMEFRAMES, list(otf_config.get("timeframes", []))),
        (WIDGET_KEY_OTF_ALIGNMENT_MODE, str(otf_config.get("alignment_mode", "all"))),
        (
            WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS,
            int(
                otf_config.get(
                    "minimum_consecutive_bars",
                    DEFAULT_OTF_FILTER_CONFIG["minimum_consecutive_bars"],
                )
            ),
        ),
        (WIDGET_KEY_OTF_DIRECTIONAL, True),
        (WIDGET_KEY_OTF_COMPLETED_BARS_ONLY, True),
        (WIDGET_KEY_OTF_SESSION_RESET, "session"),
    ]
    assignments.extend(
        _entry_window_widget_values(src.get("entry_window") or payload["entry_window"]).items()
    )
    for key, value in assignments:
        _assign_widget(key, value, overwrite=overwrite)
    for level in payload["selected_confluence_levels"]:
        rule = payload["rule_defaults"][level]
        _assign_widget(
            _anchor_rule_key("anchor_rule_tol", level),
            rule["tolerance_ticks"],
            overwrite=overwrite,
        )
        _assign_widget(
            _anchor_rule_key("anchor_rule_required", level),
            rule["required"],
            overwrite=overwrite,
        )


def _sync_editor_widget_state(
    config: dict[str, Any], level_columns: list[str], *, overwrite: bool
) -> list[str]:
    """Hydrate widgets from ``build_setup_config`` / validator-aligned fallbacks."""
    warnings: list[str] = []
    payload = _hydrate_editor_widget_payload(config, level_columns, warnings)
    built = _build_synced_setup_config(payload, warnings)
    _assign_editor_widget_state(payload, built, overwrite=overwrite)
    return warnings


def _build_current_editor_config(
    *,
    editor_seed: dict[str, Any],
    instrument: str,
    current_dataset_id: str | None,
    selected_levels: list[str],
    tolerance_ticks: float,
    min_confluences: int,
    max_confluences: int,
    naked_only: bool,
    naked_requirement: str,
    trigger: str,
    trigger_timeframe: str,
    direction: str,
    confluence_mode: str,
    anchor_level: str | None,
    confluence_rules: list[dict[str, Any]],
    min_valid_confluences: int,
    trigger_params: dict[str, Any],
    otf_filter: dict[str, Any],
    entry_window: dict[str, Any],
    setup_name: str,
    description: str,
) -> dict[str, Any]:
    config = build_setup_config(
        name=setup_name,
        description=description,
        instrument=instrument,
        selected_levels=selected_levels,
        tolerance_ticks=tolerance_ticks,
        min_confluences=min_confluences,
        max_confluences=max_confluences,
        naked_only=naked_only,
        naked_requirement=naked_requirement,
        trigger=trigger,
        trigger_timeframe=trigger_timeframe,
        direction=direction,
        confluence_mode=confluence_mode,
        anchor_level=anchor_level,
        confluence_rules=confluence_rules,
        min_valid_confluences=min_valid_confluences,
        trigger_params=trigger_params,
        otf_filter=otf_filter,
        entry_window=entry_window,
    )
    setup_id = editor_seed.get("setup_id")
    if isinstance(setup_id, str) and setup_id:
        config["setup_id"] = setup_id
    config["dataset_id"] = (
        current_dataset_id if isinstance(current_dataset_id, str) and current_dataset_id else None
    )
    return config


st.title("🧩 Setup Builder")
st.caption(
    "Configure and save reusable setup parameters for the "
    "Signals → Backtest / Grid / Validation workflow."
)
render_classic_thesis_chrome(
    page_key="setup_builder",
    allow_create_link=True,
    dataset_id=st.session_state.get("dataset_id"),
)
render_classic_nav_prefill_caption(target_page="pages/3_Setup_Builder.py")
render_classic_proposal_card(target_page="pages/3_Setup_Builder.py")

if "levels" not in st.session_state:
    st.warning(
        "No levels computed. Please load data on the Data page and compute levels on the Levels page first."
    )
    st.stop()

levels_df = st.session_state["levels"]
instrument = st.session_state.get("instrument", "ES")
current_dataset_id = st.session_state.get("dataset_id")
all_level_columns = available_level_columns(levels_df)

if not all_level_columns:
    st.warning("No level columns found. Please compute levels on the Levels page first.")
    st.stop()

defaults = default_selected_levels(all_level_columns)
active_setup = st.session_state.get("setup_config")
active_setup = active_setup if isinstance(active_setup, dict) and active_setup else None

if EDITOR_STATE_KEY not in st.session_state:
    _seeded = _seed_editor_config(
        active_setup=active_setup,
        instrument=instrument,
        defaults=defaults,
        dataset_id=current_dataset_id,
    )
    _otf_seed_warning = _seeded.pop(_OTF_REPAIR_DICT_KEY, None)
    _entry_window_seed_warning = _seeded.pop(_ENTRY_WINDOW_REPAIR_DICT_KEY, None)
    st.session_state[EDITOR_STATE_KEY] = _seeded
    if _otf_seed_warning:
        st.session_state[_SETUP_BUILDER_OTF_REPAIR_SESSION_KEY] = _otf_seed_warning
    if _entry_window_seed_warning:
        st.session_state[_SETUP_BUILDER_ENTRY_WINDOW_REPAIR_SESSION_KEY] = (
            _entry_window_seed_warning
        )

editor_seed = st.session_state.get(EDITOR_STATE_KEY)
if not isinstance(editor_seed, dict):
    _seeded = _seed_editor_config(
        active_setup=active_setup,
        instrument=instrument,
        defaults=defaults,
        dataset_id=current_dataset_id,
    )
    _otf_seed_warning = _seeded.pop(_OTF_REPAIR_DICT_KEY, None)
    _entry_window_seed_warning = _seeded.pop(_ENTRY_WINDOW_REPAIR_DICT_KEY, None)
    editor_seed = _seeded
    st.session_state[EDITOR_STATE_KEY] = editor_seed
    if _otf_seed_warning:
        st.session_state[_SETUP_BUILDER_OTF_REPAIR_SESSION_KEY] = _otf_seed_warning
    if _entry_window_seed_warning:
        st.session_state[_SETUP_BUILDER_ENTRY_WINDOW_REPAIR_SESSION_KEY] = (
            _entry_window_seed_warning
        )

pending_widget_sync = st.session_state.pop(PENDING_WIDGET_SYNC_KEY, None)
if isinstance(pending_widget_sync, dict):
    editor_seed = dict(pending_widget_sync)
    st.session_state[EDITOR_STATE_KEY] = editor_seed
    sync_warnings = _sync_editor_widget_state(editor_seed, all_level_columns, overwrite=True)
else:
    sync_warnings = _sync_editor_widget_state(editor_seed, all_level_columns, overwrite=False)
_pending_otf_repair_warning = st.session_state.pop(_SETUP_BUILDER_OTF_REPAIR_SESSION_KEY, None)
if _pending_otf_repair_warning:
    st.warning(_pending_otf_repair_warning)
_pending_entry_window_repair_warning = st.session_state.pop(
    _SETUP_BUILDER_ENTRY_WINDOW_REPAIR_SESSION_KEY, None
)
if _pending_entry_window_repair_warning:
    st.warning(_pending_entry_window_repair_warning)
_render_editor_sync_warnings(sync_warnings)

seed_dataset_id = editor_seed.get("dataset_id")
if (
    isinstance(seed_dataset_id, str)
    and seed_dataset_id
    and isinstance(current_dataset_id, str)
    and current_dataset_id
    and seed_dataset_id != current_dataset_id
):
    st.warning(
        "Loaded setup belongs to a different dataset. "
        "Review level selections carefully before saving or setting active."
    )

_render_setup_level_warnings(editor_seed, all_level_columns)

st.subheader("Saved setups")
saved_setups = _newest_first_bucketed_setups(
    list_saved_setups(),
    current_dataset_id=current_dataset_id,
)
saved_setup_options = {
    item["setup_id"]: item for item in saved_setups if isinstance(item.get("setup_id"), str)
}

if saved_setup_options:
    selected_saved_setup_id = st.selectbox(
        "Local setup library",
        options=list(saved_setup_options),
        format_func=lambda setup_id: _saved_setup_label(
            saved_setup_options[setup_id], current_dataset_id
        ),
        key=WIDGET_KEY_SAVED_SETUP,
    )
    selected_saved_setup = saved_setup_options[selected_saved_setup_id]

    action_cols = st.columns(4)
    if action_cols[0].button("Load to editor", width="stretch"):
        loaded_meta = load_setup(selected_saved_setup_id)
        loaded_config = dict(loaded_meta.get("setup_config", {}))
        st.session_state[EDITOR_STATE_KEY] = loaded_config
        st.session_state[PENDING_WIDGET_SYNC_KEY] = loaded_config
        st.success(f"Loaded '{loaded_meta.get('name', 'setup')}' into editor.")
        st.rerun()

    if action_cols[1].button("Duplicate", width="stretch"):
        duplicate_config = dict(selected_saved_setup.get("setup_config", {}))
        duplicate_config.pop("setup_id", None)
        duplicate_config["name"] = _duplicate_setup_name(str(duplicate_config.get("name", "")))
        duplicate_meta = save_setup(
            duplicate_config,
            dataset_id=duplicate_config.get("dataset_id"),
            instrument=duplicate_config.get("instrument"),
        )
        st.session_state[EDITOR_STATE_KEY] = dict(duplicate_meta["setup_config"])
        st.session_state[PENDING_WIDGET_SYNC_KEY] = dict(duplicate_meta["setup_config"])
        st.success(f"Duplicated as '{duplicate_meta.get('name', 'setup')}'.")
        st.rerun()

    if action_cols[2].button("Set active", width="stretch"):
        loaded_meta = load_setup(selected_saved_setup_id)
        st.session_state["setup_config"] = dict(loaded_meta.get("setup_config", {}))
        _invalidate_session_signals_after_setup_mutation(st.session_state)
        st.success(f"Active setup set to '{loaded_meta.get('name', 'setup')}'.")

    if action_cols[3].button("Delete", width="stretch"):
        delete_setup(selected_saved_setup_id)
        active = st.session_state.get("setup_config")
        if isinstance(active, dict) and active.get("setup_id") == selected_saved_setup_id:
            st.session_state.pop("setup_config", None)
            _invalidate_session_signals_after_setup_mutation(st.session_state)
        if (
            isinstance(st.session_state.get(EDITOR_STATE_KEY), dict)
            and st.session_state[EDITOR_STATE_KEY].get("setup_id") == selected_saved_setup_id
        ):
            st.session_state.pop(EDITOR_STATE_KEY, None)
        st.success(f"Deleted '{selected_saved_setup.get('name', selected_saved_setup_id)}'.")
        st.rerun()
else:
    st.caption("No saved setups in local store yet.")

st.subheader("Setup identity")
setup_name = st.text_input(
    "Setup name",
    value=str(st.session_state.get(WIDGET_KEY_SETUP_NAME, "Untitled setup")),
    key=WIDGET_KEY_SETUP_NAME,
)
description = st.text_area(
    "Description / notes",
    value=str(st.session_state.get(WIDGET_KEY_DESCRIPTION, "")),
    height=90,
    key=WIDGET_KEY_DESCRIPTION,
)

st.subheader("Level and confluence settings")
mode_options = list(CONFLUENCE_MODE_LABELS.keys())
mode_index, _, _ = _safe_selectbox_index_fallback(
    st.session_state.get(WIDGET_KEY_CONFLUENCE_MODE),
    options=mode_options,
    default="Global cluster",
)
selected_mode_label = st.selectbox(
    "Confluence mode",
    options=mode_options,
    index=mode_index,
    key=WIDGET_KEY_CONFLUENCE_MODE,
)
confluence_mode = CONFLUENCE_MODE_LABELS[selected_mode_label]

selected_levels: list[str] = []
tolerance_ticks = 4.0
min_conf = 2
max_conf = 5
anchor_level: str | None = None
confluence_rules: list[dict] = []
min_valid_confluences = 1

if confluence_mode == "global_cluster":
    selected_levels = st.multiselect(
        "Selected level columns",
        options=all_level_columns,
        default=list(st.session_state.get(WIDGET_KEY_SELECTED_LEVELS, [])),
        key=WIDGET_KEY_SELECTED_LEVELS,
    )
    tolerance_default, tolerance_fallback = _safe_float_fallback(
        st.session_state.get(WIDGET_KEY_TOLERANCE_TICKS),
        default=4.0,
        min_value=0.0,
    )
    tolerance_ticks = st.number_input(
        "Tolerance ticks",
        min_value=0.0,
        value=tolerance_default,
        step=0.5,
        key=WIDGET_KEY_TOLERANCE_TICKS,
    )
    min_conf_default, min_conf_fallback = _safe_int_fallback(
        st.session_state.get(WIDGET_KEY_MIN_CONFLUENCES),
        default=2,
        min_value=1,
        max_value=5,
    )
    max_conf_default, max_conf_fallback = _safe_int_fallback(
        st.session_state.get(WIDGET_KEY_MAX_CONFLUENCES),
        default=5,
        min_value=min_conf_default,
        max_value=5,
    )
    if min_conf_fallback:
        st.session_state[WIDGET_KEY_MIN_CONFLUENCES] = min_conf_default
    if max_conf_fallback:
        st.session_state[WIDGET_KEY_MAX_CONFLUENCES] = max_conf_default
    min_conf = st.slider(
        "Minimum confluences",
        min_value=1,
        max_value=5,
        value=min_conf_default,
        key=WIDGET_KEY_MIN_CONFLUENCES,
    )
    max_conf = st.slider(
        "Maximum confluences",
        min_value=1,
        max_value=5,
        value=max_conf_default,
        key=WIDGET_KEY_MAX_CONFLUENCES,
    )
else:
    anchor_index, anchor_default, anchor_fallback = _safe_selectbox_index_fallback(
        st.session_state.get(WIDGET_KEY_ANCHOR_LEVEL),
        options=all_level_columns,
        default=all_level_columns[0],
    )
    anchor_level = st.selectbox(
        "Anchor level",
        options=all_level_columns,
        index=anchor_index,
        key=WIDGET_KEY_ANCHOR_LEVEL,
    )
    confluence_level_options = [level for level in all_level_columns if level != anchor_level]
    confluence_seed = [
        level
        for level in st.session_state.get(WIDGET_KEY_CONFLUENCE_LEVELS, [])
        if level in confluence_level_options
    ]
    selected_confluence_levels = st.multiselect(
        "Confluence levels",
        options=confluence_level_options,
        default=confluence_seed,
        key=WIDGET_KEY_CONFLUENCE_LEVELS,
    )
    for level in selected_confluence_levels:
        st.markdown(f"**{level}**")
        tol_seed = st.session_state.get(_anchor_rule_key("anchor_rule_tol", level))
        required_seed = st.session_state.get(_anchor_rule_key("anchor_rule_required", level), False)
        tolerance_seed, tolerance_fallback = _safe_float_fallback(
            tol_seed,
            default=4.0,
            min_value=0.0,
        )
        rule_tolerance = st.number_input(
            f"Tolerance ticks — {level}",
            min_value=0.0,
            value=tolerance_seed,
            step=0.5,
            key=_anchor_rule_key("anchor_rule_tol", level),
        )
        rule_required = st.checkbox(
            f"Required — {level}",
            value=bool(required_seed),
            key=_anchor_rule_key("anchor_rule_required", level),
        )
        confluence_rules.append(
            {
                "level": level,
                "tolerance_ticks": float(rule_tolerance),
                "required": bool(rule_required),
            }
        )

    if selected_confluence_levels:
        min_valid_default, min_valid_fallback = _safe_int_fallback(
            st.session_state.get(WIDGET_KEY_MIN_VALID_CONFLUENCES),
            default=1,
            min_value=0,
            max_value=len(selected_confluence_levels),
        )
        if min_valid_fallback:
            st.session_state[WIDGET_KEY_MIN_VALID_CONFLUENCES] = min_valid_default
        min_valid_confluences = int(
            st.number_input(
                "Minimum valid confluences",
                min_value=0,
                max_value=len(selected_confluence_levels),
                value=min_valid_default,
                step=1,
                key=WIDGET_KEY_MIN_VALID_CONFLUENCES,
            )
        )
    else:
        min_valid_confluences = 0
        st.caption("Anchor only — no confluence required. Zone is the live anchor price.")

    selected_levels = (
        [anchor_level, *selected_confluence_levels]
        if anchor_level
        else list(selected_confluence_levels)
    )

naked_only = st.toggle(
    "Naked only",
    value=bool(st.session_state.get(WIDGET_KEY_NAKED_ONLY, False)),
    key=WIDGET_KEY_NAKED_ONLY,
)
naked_requirement_options = ["any", "all"]
naked_requirement_default = str(st.session_state.get(WIDGET_KEY_NAKED_REQUIREMENT, "any")).lower()
naked_requirement_index, _, naked_requirement_fallback = _safe_selectbox_index_fallback(
    naked_requirement_default,
    options=naked_requirement_options,
    default="any",
)
if naked_requirement_fallback:
    st.session_state[WIDGET_KEY_NAKED_REQUIREMENT] = "any"
naked_requirement = st.radio(
    "Naked requirement",
    options=naked_requirement_options,
    index=naked_requirement_index,
    horizontal=True,
    key=WIDGET_KEY_NAKED_REQUIREMENT,
)

st.subheader("Trigger settings")
trigger_options = ["touch", "reject", "break", "reclaim", "3c", "fade", "continuation"]
trigger_index, _, trigger_fallback = _safe_selectbox_index_fallback(
    st.session_state.get(WIDGET_KEY_TRIGGER),
    options=trigger_options,
    default="touch",
)
if trigger_fallback:
    st.session_state[WIDGET_KEY_TRIGGER] = "touch"
trigger = st.selectbox(
    "Trigger", options=trigger_options, index=trigger_index, key=WIDGET_KEY_TRIGGER
)
trigger_timeframe_options = [
    option for option in TRIGGER_TIMEFRAME_CHOICES if option in VALID_TRIGGER_TIMEFRAMES
]
trigger_timeframe_state = st.session_state.get(WIDGET_KEY_TRIGGER_TIMEFRAME)
if isinstance(trigger_timeframe_state, str) and trigger_timeframe_state in TRIGGER_TIMEFRAME_LABELS:
    trigger_timeframe_state = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_state]
trigger_timeframe_default_value, trigger_timeframe_fallback = _safe_trigger_timeframe_fallback(
    trigger_timeframe_state
)
if trigger_timeframe_default_value not in trigger_timeframe_options:
    trigger_timeframe_default_value = DEFAULT_TRIGGER_TIMEFRAME
    trigger_timeframe_fallback = True
if trigger_timeframe_fallback:
    st.session_state[WIDGET_KEY_TRIGGER_TIMEFRAME] = TRIGGER_TIMEFRAME_DISPLAY[
        DEFAULT_TRIGGER_TIMEFRAME
    ]
trigger_timeframe_default = trigger_timeframe_options.index(trigger_timeframe_default_value)

if trigger == "3c":
    trigger_timeframe_label = st.selectbox(
        "Trigger timeframe",
        options=list(TRIGGER_TIMEFRAME_LABELS.keys()),
        index=trigger_timeframe_default,
        key=WIDGET_KEY_TRIGGER_TIMEFRAME,
        help=(
            "Arrival, inside/muted, SFP, and reversal are evaluated on the selected "
            "trigger timeframe. Retrace entry fill is evaluated on canonical/base bars."
        ),
    )
    trigger_timeframe = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_label]
    if trigger_timeframe != "base":
        st.info(
            "3c with non-base trigger timeframe: arrival, muted, SFP, and reversal "
            "are evaluated on trigger-timeframe candles. "
            "Retrace entry fill is evaluated on canonical/base bars after reversal candle completes. "
            "max_entry_wait_bars_after_reversal counts trigger-timeframe bars."
        )
else:
    trigger_timeframe_label = st.selectbox(
        "Trigger timeframe",
        options=list(TRIGGER_TIMEFRAME_LABELS.keys()),
        index=trigger_timeframe_default,
        key=WIDGET_KEY_TRIGGER_TIMEFRAME,
        help=(
            "Candle-close trigger logic is evaluated on the selected trigger timeframe. "
            "The default preserves current behavior."
        ),
    )
    trigger_timeframe = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_label]

direction_options = ["long", "short", "both"]
direction_index, _, direction_fallback = _safe_selectbox_index_fallback(
    st.session_state.get(WIDGET_KEY_DIRECTION),
    options=direction_options,
    default="both",
)
if direction_fallback:
    st.session_state[WIDGET_KEY_DIRECTION] = "both"
direction = st.selectbox(
    "Direction",
    options=direction_options,
    index=direction_index,
    key=WIDGET_KEY_DIRECTION,
    help=(
        "touch + both + single_position accepted trades are long-only "
        "(same-bar short skipped). See ASSUMPTIONS §4b."
    ),
)

trigger_params = {}
if trigger == "3c":
    entry_retrace_default, entry_retrace_fallback = _safe_float_fallback(
        st.session_state.get(WIDGET_KEY_ENTRY_RETRACE_TICKS),
        default=4.0,
        min_value=0.0,
    )
    max_wait_default, max_wait_fallback = _safe_int_fallback(
        st.session_state.get(WIDGET_KEY_MAX_ENTRY_WAIT_BARS),
        default=5,
        min_value=0,
        max_value=10_000,
    )
    if entry_retrace_fallback:
        st.session_state[WIDGET_KEY_ENTRY_RETRACE_TICKS] = entry_retrace_default
    if max_wait_fallback:
        st.session_state[WIDGET_KEY_MAX_ENTRY_WAIT_BARS] = max_wait_default
    entry_retrace_ticks = st.number_input(
        "Entry retrace ticks",
        min_value=0.0,
        value=entry_retrace_default,
        step=0.5,
        key=WIDGET_KEY_ENTRY_RETRACE_TICKS,
    )
    max_entry_wait_bars = st.number_input(
        "Max entry wait bars after reversal",
        min_value=0,
        value=max_wait_default,
        step=1,
        key=WIDGET_KEY_MAX_ENTRY_WAIT_BARS,
    )
    trigger_params = {
        "entry_retrace_ticks": entry_retrace_ticks,
        "max_entry_wait_bars_after_reversal": int(max_entry_wait_bars),
    }
elif trigger in {"fade", "continuation"}:
    require_close_confirmation = st.checkbox(
        "Require close confirmation",
        value=bool(st.session_state.get(WIDGET_KEY_REQUIRE_CLOSE_CONFIRMATION, False)),
        key=WIDGET_KEY_REQUIRE_CLOSE_CONFIRMATION,
        help=(
            "Default off: fade/continuation are the directional analogue of touch. "
            "On: fade also requires close back on the approach side of the zone "
            "(reject geometry); continuation requires close through the far edge."
        ),
    )
    trigger_params = {"require_close_confirmation": bool(require_close_confirmation)}

st.subheader("OTF filter configuration")
st.caption(
    "OTF defaults to **disabled** so existing research behavior is unchanged until you enable it. "
    "This page saves the setup’s OTF filter settings. "
    "Signal generation keeps the full candidate population; "
    "Backtest, Grid, and Walk-forward apply OTF admission before execution when enabled. "
    "Rejected candidates remain available for audit/export."
)
st.caption(
    "OTF v1 always uses completed higher-timeframe bars only (intentional decision lag). "
    "Futures session boundaries follow the instrument overnight session start "
    "(e.g. 18:00 ET for ES/NQ); midnight is not a reset. "
    "Source bars must be strictly finer than selected OTF timeframes. "
    "Alignment mode is `all` — every selected timeframe must agree, which can shrink sample size."
)
otf_enabled = st.toggle(
    "Enable OTF filter",
    value=bool(st.session_state.get(WIDGET_KEY_OTF_ENABLED, False)),
    key=WIDGET_KEY_OTF_ENABLED,
)
otf_timeframes = st.multiselect(
    "OTF timeframes",
    options=list(OTF_TIMEFRAME_CHOICES),
    default=[
        timeframe
        for timeframe in st.session_state.get(WIDGET_KEY_OTF_TIMEFRAMES, [])
        if timeframe in OTF_TIMEFRAME_CHOICES
    ],
    key=WIDGET_KEY_OTF_TIMEFRAMES,
    disabled=not otf_enabled,
)
otf_alignment_mode = st.selectbox(
    "OTF alignment mode",
    options=["all"],
    index=0,
    key=WIDGET_KEY_OTF_ALIGNMENT_MODE,
    disabled=True,
)
otf_minimum_default, otf_minimum_fallback = _safe_int_fallback(
    st.session_state.get(WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS),
    default=3,
    min_value=1,
    max_value=10_000,
)
if otf_minimum_fallback:
    st.session_state[WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS] = otf_minimum_default
otf_minimum_consecutive_bars = int(
    st.number_input(
        "OTF minimum consecutive completed HTF bars",
        min_value=1,
        value=otf_minimum_default,
        step=1,
        key=WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS,
    )
)
st.toggle(
    "OTF directional mode (required in v1)",
    value=True,
    key=WIDGET_KEY_OTF_DIRECTIONAL,
    disabled=True,
)
st.toggle(
    "OTF use completed bars only (required in v1)",
    value=True,
    key=WIDGET_KEY_OTF_COMPLETED_BARS_ONLY,
    disabled=True,
)
st.selectbox(
    "OTF session reset policy",
    options=["session"],
    index=0,
    key=WIDGET_KEY_OTF_SESSION_RESET,
    disabled=True,
)
otf_filter = {
    "enabled": otf_enabled,
    "timeframes": otf_timeframes,
    "alignment_mode": otf_alignment_mode,
    "minimum_consecutive_bars": otf_minimum_consecutive_bars,
    "directional": True,
    "use_completed_bars_only": True,
    "session_reset": "session",
}

st.subheader("Entry window (Admit) configuration")
st.caption(
    "Optional Admit window saved on the setup library (SW6). Default **disabled** = "
    "legacy all-day admission. This stores the constrained window for reuse; "
    "Backtest still runs Admit only when its Admit toggle / Promote handoff applies "
    "`entry_window`. Distinct from Time Analysis Focus (post-hoc subset)."
)
_exchange_tz = "America/New_York"
_inst = INSTRUMENTS.get(str(instrument)) if isinstance(instrument, str) else None
if _inst is not None:
    _exchange_tz = str(_inst.exchange_tz)
entry_window_enabled = st.toggle(
    "Save Admit entry window on setup",
    value=bool(st.session_state.get(WIDGET_KEY_ENTRY_WINDOW_ENABLED, False)),
    key=WIDGET_KEY_ENTRY_WINDOW_ENABLED,
    help="Persists a normalized entry_window on the setup. Default off.",
)
entry_window: dict[str, Any]
if entry_window_enabled:
    if WIDGET_KEY_ENTRY_WINDOW_MODE not in st.session_state:
        st.session_state[WIDGET_KEY_ENTRY_WINDOW_MODE] = "rth_segments"
    entry_window_mode = st.selectbox(
        "Window mode",
        options=list(ENTRY_WINDOW_MODE_OPTIONS),
        key=WIDGET_KEY_ENTRY_WINDOW_MODE,
        format_func=lambda value: {
            "rth_segments": "RTH segments (exchange/session TZ)",
            "clock_range": "Clock range [start, end)",
        }[value],
    )
    if entry_window_mode == "rth_segments":
        if WIDGET_KEY_ENTRY_WINDOW_RTH_SEGMENTS not in st.session_state:
            st.session_state[WIDGET_KEY_ENTRY_WINDOW_RTH_SEGMENTS] = ["rth_open_30m"]
        selected_segments = st.multiselect(
            "RTH segments",
            options=list(RTH_SEGMENT_LABELS),
            key=WIDGET_KEY_ENTRY_WINDOW_RTH_SEGMENTS,
            help="Multi-segment selection is OR (C3). Membership uses exchange/session TZ (C5).",
        )
        entry_window = {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": list(selected_segments),
            "timezone": _exchange_tz,
        }
        if not selected_segments:
            st.warning("Select at least one RTH segment, or disable the entry window.")
    else:
        if WIDGET_KEY_ENTRY_WINDOW_START_TIME not in st.session_state:
            st.session_state[WIDGET_KEY_ENTRY_WINDOW_START_TIME] = "09:30"
        if WIDGET_KEY_ENTRY_WINDOW_END_TIME not in st.session_state:
            st.session_state[WIDGET_KEY_ENTRY_WINDOW_END_TIME] = "10:00"
        if WIDGET_KEY_ENTRY_WINDOW_TIMEZONE not in st.session_state:
            st.session_state[WIDGET_KEY_ENTRY_WINDOW_TIMEZONE] = (
                _exchange_tz if _exchange_tz in TIMEZONE_OPTIONS else TIMEZONE_OPTIONS[0]
            )
        ew_start = st.text_input(
            "Start time",
            key=WIDGET_KEY_ENTRY_WINDOW_START_TIME,
            help="Half-open range start HH:MM or HH:MM:SS (C4).",
        )
        ew_end = st.text_input(
            "End time",
            key=WIDGET_KEY_ENTRY_WINDOW_END_TIME,
            help="Half-open range end (exclusive). Use 24:00 for end-of-day.",
        )
        ew_tz = st.selectbox(
            "Window timezone",
            options=TIMEZONE_OPTIONS,
            key=WIDGET_KEY_ENTRY_WINDOW_TIMEZONE,
            help="Clock-range membership uses this TZ (C5). RTH segments always use exchange TZ.",
        )
        entry_window = {
            "enabled": True,
            "mode": "clock_range",
            "start_time": ew_start.strip(),
            "end_time": ew_end.strip(),
            "timezone": ew_tz,
        }
else:
    entry_window = normalize_entry_window(None, exchange_tz=_exchange_tz)

# Incomplete Admit drafts (empty RTH segments, bad clock range, …) must not
# crash the editor: normalize_entry_window raises inside build_setup_config.
# Build with a disabled placeholder, then attach the raw draft so Save still
# fails closed via validate_setup_config / validate_entry_window_config.
entry_window_errors = validate_entry_window_config(entry_window, exchange_tz=_exchange_tz)
empty_rth_draft = bool(
    entry_window.get("enabled")
    and entry_window.get("mode") == "rth_segments"
    and not list(entry_window.get("rth_segments") or [])
)
if entry_window_errors and not empty_rth_draft:
    # Empty-RTH already has a friendly warning above; surface other normalize errors.
    for error in entry_window_errors:
        st.warning(error)

candidate_entry_window: dict[str, Any] = {"enabled": False} if entry_window_errors else entry_window
candidate_config = _build_current_editor_config(
    editor_seed=editor_seed,
    instrument=instrument,
    current_dataset_id=current_dataset_id,
    selected_levels=selected_levels,
    tolerance_ticks=tolerance_ticks,
    min_confluences=min_conf,
    max_confluences=max_conf,
    naked_only=naked_only,
    naked_requirement=naked_requirement,
    trigger=trigger,
    trigger_timeframe=trigger_timeframe,
    direction=direction,
    confluence_mode=confluence_mode,
    anchor_level=anchor_level,
    confluence_rules=confluence_rules,
    min_valid_confluences=min_valid_confluences,
    trigger_params=trigger_params,
    otf_filter=otf_filter,
    entry_window=candidate_entry_window,
    setup_name=setup_name,
    description=description,
)
if entry_window_errors:
    candidate_config["entry_window"] = dict(entry_window)
editor_missing_refs = _unavailable_level_references(candidate_config, all_level_columns)
requires_missing_level_ack = _has_unavailable_level_references(editor_missing_refs)
if requires_missing_level_ack:
    st.warning(
        "This loaded setup references unavailable levels. Enable the checkbox below to save with those references removed."
    )
    save_with_missing_levels_removed = st.checkbox(
        "Save with unavailable levels removed",
        value=bool(st.session_state.get(WIDGET_KEY_ALLOW_MISSING_LEVEL_REMOVAL, False)),
        key=WIDGET_KEY_ALLOW_MISSING_LEVEL_REMOVAL,
        help="Enable this only after reviewing the unavailable level warnings above.",
    )
else:
    st.session_state.pop(WIDGET_KEY_ALLOW_MISSING_LEVEL_REMOVAL, None)
    save_with_missing_levels_removed = False

if st.button("Save setup", type="primary"):
    if requires_missing_level_ack and not save_with_missing_levels_removed:
        st.error(
            "Save blocked: loaded setup includes unavailable level references. "
            "Resolve them in the editor or explicitly choose 'Save with unavailable levels removed'."
        )
    else:
        errors = validate_setup_config(candidate_config)
        if errors:
            for error in errors:
                st.error(error)
        else:
            saved_meta = save_setup(
                candidate_config,
                setup_id=candidate_config.get("setup_id"),
                dataset_id=candidate_config.get("dataset_id"),
                instrument=instrument,
            )
            persisted_config = dict(saved_meta["setup_config"])
            st.session_state["setup_config"] = persisted_config
            st.session_state[EDITOR_STATE_KEY] = persisted_config
            _invalidate_session_signals_after_setup_mutation(st.session_state)
            existing = st.session_state.get("setup_configs", [])
            replaced = any(item.get("name") == persisted_config["name"] for item in existing)
            updated = [item for item in existing if item.get("name") != persisted_config["name"]]
            updated.append(persisted_config)
            st.session_state["setup_configs"] = updated
            if replaced:
                st.success("Setup updated and active.")
            else:
                st.success("Setup saved and active.")

active_setup = st.session_state.get("setup_config")
if active_setup:
    st.subheader("Active setup")
    _render_setup_summary(active_setup)

    if st.button("Clear active setup"):
        st.session_state.pop("setup_config", None)
        _invalidate_session_signals_after_setup_mutation(st.session_state)
        st.success("Active setup cleared.")
