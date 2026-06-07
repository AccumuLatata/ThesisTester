from __future__ import annotations

import hashlib
import re
from typing import Any

import streamlit as st

from thesistester.persistence import (
    delete_setup,
    list_saved_setups,
    load_setup,
    save_setup,
)
from thesistester.setup import (
    DEFAULT_TRIGGER_TIMEFRAME,
    TRIGGER_TIMEFRAME_CHOICES,
    VALID_TRIGGER_TIMEFRAMES,
    available_level_columns,
    build_setup_config,
    default_selected_levels,
    normalize_trigger_timeframe,
    validate_setup_config,
)


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
WIDGET_KEY_MAX_ENTRY_WAIT_BARS = "_setup_builder_max_entry_wait_bars"
WIDGET_KEY_ALLOW_MISSING_LEVEL_REMOVAL = "_setup_builder_allow_missing_level_removal"


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


def _safe_trigger_fallback(value: object) -> tuple[str, bool]:
    options = ["touch", "reject", "break", "reclaim", "3c"]
    if isinstance(value, str) and value in options:
        return value, False
    return "touch", True


def _safe_direction_fallback(value: object) -> tuple[str, bool]:
    options = ["long", "short", "both"]
    if isinstance(value, str) and value in options:
        return value, False
    return "both", True


def _safe_trigger_timeframe_fallback(value: object) -> tuple[str, bool]:
    normalized = normalize_trigger_timeframe(value)
    if normalized in VALID_TRIGGER_TIMEFRAMES:
        return normalized, False
    return DEFAULT_TRIGGER_TIMEFRAME, True


def _safe_confluence_mode_fallback(value: object) -> tuple[str, bool]:
    if isinstance(value, str) and value in CONFLUENCE_MODE_DISPLAY:
        return value, False
    return "global_cluster", True


def _render_setup_summary(config: dict) -> None:
    confluence_mode = config.get("confluence_mode", "global_cluster")
    st.markdown(f"**Name:** {config['name']}")
    st.markdown(f"**Instrument:** {config['instrument']}")
    st.markdown(f"**Description:** {config.get('description', '') or '-'}")
    st.markdown(f"**Mode:** {CONFLUENCE_MODE_DISPLAY.get(confluence_mode, confluence_mode)}")
    st.markdown(f"**Selected levels ({len(config['selected_levels'])}):** {', '.join(config['selected_levels'])}")
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
        if isinstance(current_dataset_id, str) and current_dataset_id and dataset_id == current_dataset_id:
            return 0
        if dataset_id in (None, ""):
            return 1
        return 2

    return sorted(setups, key=_bucket)


def _dataset_relation_label(setup_dataset_id: object, current_dataset_id: str | None) -> str:
    if setup_dataset_id in (None, ""):
        return "global/no dataset"
    if isinstance(current_dataset_id, str) and current_dataset_id and setup_dataset_id == current_dataset_id:
        return "current dataset"
    return "other dataset"


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
    return {
        "name": "Untitled setup",
        "description": "",
        "instrument": instrument,
        "selected_levels": list(defaults),
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": DEFAULT_TRIGGER_TIMEFRAME,
        "direction": "both",
        "confluence_mode": "global_cluster",
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "trigger_params": {},
        "setup_id": None,
        "dataset_id": dataset_id,
    }


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
    seeded["dataset_id"] = seeded.get("dataset_id", dataset_id)
    return seeded


def _unavailable_level_references(config: dict[str, Any], level_columns: list[str]) -> dict[str, list[str]]:
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
            {str(level) for level in selected_levels if str(level) and str(level) not in level_columns}
        ),
    }


def _has_unavailable_level_references(unavailable: dict[str, list[str]]) -> bool:
    return any(unavailable.get(key) for key in ("anchor_level", "confluence_rules", "selected_levels"))


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


def _sync_editor_widget_state(config: dict[str, Any], level_columns: list[str], *, overwrite: bool) -> list[str]:
    warnings: list[str] = []

    def _assign(key: str, value: Any) -> None:
        if overwrite or key not in st.session_state:
            st.session_state[key] = value

    name_value, name_fallback = _safe_string_fallback(config.get("name"), "Untitled setup")
    if name_fallback:
        warnings.append("Loaded setup name is invalid; using default name.")
    _assign(WIDGET_KEY_SETUP_NAME, name_value)

    description_value, description_fallback = _safe_string_fallback(config.get("description"), "")
    if description_fallback:
        warnings.append("Loaded setup description is invalid; using empty description.")
    _assign(WIDGET_KEY_DESCRIPTION, description_value)

    mode_value, mode_fallback = _safe_confluence_mode_fallback(config.get("confluence_mode"))
    if mode_fallback:
        warnings.append("Loaded setup confluence mode is invalid; falling back to global_cluster.")
    _assign(WIDGET_KEY_CONFLUENCE_MODE, CONFLUENCE_MODE_DISPLAY.get(mode_value, "Global cluster"))

    selected_levels = config.get("selected_levels")
    if isinstance(selected_levels, list):
        selected_level_seed = [str(level) for level in selected_levels if str(level) in level_columns]
    else:
        selected_level_seed = default_selected_levels(level_columns)
        warnings.append("Loaded selected levels are invalid; using default level selection.")
    _assign(WIDGET_KEY_SELECTED_LEVELS, selected_level_seed)

    tolerance_ticks, tolerance_fallback = _safe_float_fallback(
        config.get("tolerance_ticks"),
        default=4.0,
        min_value=0.0,
    )
    if tolerance_fallback:
        warnings.append("Loaded tolerance ticks is invalid; using a safe value.")
    _assign(WIDGET_KEY_TOLERANCE_TICKS, tolerance_ticks)

    min_confluences, min_confluences_fallback = _safe_int_fallback(
        config.get("min_confluences"),
        default=2,
        min_value=1,
        max_value=5,
    )
    if min_confluences_fallback:
        warnings.append("Loaded minimum confluences is invalid; using a safe value.")
    _assign(WIDGET_KEY_MIN_CONFLUENCES, min_confluences)

    max_confluences, max_confluences_fallback = _safe_int_fallback(
        config.get("max_confluences"),
        default=5,
        min_value=min_confluences,
        max_value=5,
    )
    if max_confluences_fallback:
        warnings.append("Loaded maximum confluences is invalid; using a safe value.")
    _assign(WIDGET_KEY_MAX_CONFLUENCES, max_confluences)

    anchor_seed = config.get("anchor_level")
    anchor_default = (
        str(anchor_seed)
        if isinstance(anchor_seed, str) and anchor_seed in level_columns
        else (level_columns[0] if level_columns else None)
    )
    _assign(WIDGET_KEY_ANCHOR_LEVEL, anchor_default)

    rules_seed = config.get("confluence_rules", [])
    rule_defaults = {}
    if isinstance(rules_seed, list):
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
            required_value = bool(rule.get("required", False))
            if tol_fallback:
                warnings.append(f"Loaded tolerance for confluence rule '{level}' is invalid; using a safe value.")
            rule_defaults[level] = {
                "tolerance_ticks": tol_value,
                "required": required_value,
            }
    confluence_options = [level for level in level_columns if level != anchor_default]
    selected_confluence_levels = [level for level in rule_defaults if level in confluence_options]
    _assign(WIDGET_KEY_CONFLUENCE_LEVELS, selected_confluence_levels)
    for level in selected_confluence_levels:
        _assign(_anchor_rule_key("anchor_rule_tol", level), rule_defaults[level]["tolerance_ticks"])
        _assign(_anchor_rule_key("anchor_rule_required", level), rule_defaults[level]["required"])

    min_valid_raw = config.get("min_valid_confluences")
    min_valid_default = 1
    min_valid_fallback = False
    if mode_value == "anchor_rules":
        min_valid_default, min_valid_fallback = _safe_int_fallback(
            min_valid_raw,
            default=1,
            min_value=1,
            max_value=max(1, len(selected_confluence_levels) if selected_confluence_levels else 1),
        )
        if min_valid_fallback:
            warnings.append("Loaded minimum valid confluences is invalid; using a safe value.")
    _assign(WIDGET_KEY_MIN_VALID_CONFLUENCES, min_valid_default)

    _assign(WIDGET_KEY_NAKED_ONLY, bool(config.get("naked_only", False)))

    naked_requirement = str(config.get("naked_requirement", "any")).lower()
    if naked_requirement not in ("any", "all"):
        naked_requirement = "any"
        warnings.append("Loaded naked requirement is invalid; falling back to 'any'.")
    _assign(WIDGET_KEY_NAKED_REQUIREMENT, naked_requirement)

    trigger, trigger_fallback = _safe_trigger_fallback(config.get("trigger"))
    if trigger_fallback:
        warnings.append("Loaded trigger is invalid; falling back to touch.")
    _assign(WIDGET_KEY_TRIGGER, trigger)

    trigger_timeframe, timeframe_fallback = _safe_trigger_timeframe_fallback(config.get("trigger_timeframe"))
    if timeframe_fallback:
        warnings.append("Loaded trigger timeframe is invalid; falling back to base.")
    _assign(
        WIDGET_KEY_TRIGGER_TIMEFRAME,
        TRIGGER_TIMEFRAME_DISPLAY.get(trigger_timeframe, "Base/current timeframe"),
    )

    direction, direction_fallback = _safe_direction_fallback(config.get("direction"))
    if direction_fallback:
        warnings.append("Loaded direction is invalid; falling back to both.")
    _assign(WIDGET_KEY_DIRECTION, direction)

    trigger_params_seed = config.get("trigger_params", {})
    entry_retrace_default = 4.0
    max_wait_default = 5
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
        if entry_retrace_fallback:
            warnings.append("Loaded entry retrace ticks is invalid; using a safe value.")
        if max_wait_fallback:
            warnings.append("Loaded max entry wait bars is invalid; using a safe value.")
    _assign(WIDGET_KEY_ENTRY_RETRACE_TICKS, entry_retrace_default)
    _assign(WIDGET_KEY_MAX_ENTRY_WAIT_BARS, max_wait_default)

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
    )
    setup_id = editor_seed.get("setup_id")
    if isinstance(setup_id, str) and setup_id:
        config["setup_id"] = setup_id
    config["dataset_id"] = current_dataset_id if isinstance(current_dataset_id, str) and current_dataset_id else None
    return config


st.title("🧩 Setup Builder")
st.caption("Configure and save reusable setup parameters for the Signals → Backtest workflow.")

if "levels" not in st.session_state:
    st.warning("No levels computed. Please load data on the Data page and compute levels on the Levels page first.")
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
    st.session_state[EDITOR_STATE_KEY] = _seed_editor_config(
        active_setup=active_setup,
        instrument=instrument,
        defaults=defaults,
        dataset_id=current_dataset_id,
    )

editor_seed = st.session_state.get(EDITOR_STATE_KEY)
if not isinstance(editor_seed, dict):
    editor_seed = _seed_editor_config(
        active_setup=active_setup,
        instrument=instrument,
        defaults=defaults,
        dataset_id=current_dataset_id,
    )
    st.session_state[EDITOR_STATE_KEY] = editor_seed

pending_widget_sync = st.session_state.pop(PENDING_WIDGET_SYNC_KEY, None)
if isinstance(pending_widget_sync, dict):
    editor_seed = dict(pending_widget_sync)
    st.session_state[EDITOR_STATE_KEY] = editor_seed
    sync_warnings = _sync_editor_widget_state(editor_seed, all_level_columns, overwrite=True)
else:
    sync_warnings = _sync_editor_widget_state(editor_seed, all_level_columns, overwrite=False)
for warning_message in sync_warnings:
    st.warning(warning_message)

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
saved_setup_options = {item["setup_id"]: item for item in saved_setups if isinstance(item.get("setup_id"), str)}

if saved_setup_options:
    selected_saved_setup_id = st.selectbox(
        "Local setup library",
        options=list(saved_setup_options),
        format_func=lambda setup_id: _saved_setup_label(saved_setup_options[setup_id], current_dataset_id),
        key=WIDGET_KEY_SAVED_SETUP,
    )
    selected_saved_setup = saved_setup_options[selected_saved_setup_id]

    action_cols = st.columns(4)
    if action_cols[0].button("Load to editor", use_container_width=True):
        loaded_meta = load_setup(selected_saved_setup_id)
        loaded_config = dict(loaded_meta.get("setup_config", {}))
        st.session_state[EDITOR_STATE_KEY] = loaded_config
        st.session_state[PENDING_WIDGET_SYNC_KEY] = loaded_config
        st.success(f"Loaded '{loaded_meta.get('name', 'setup')}' into editor.")
        st.rerun()

    if action_cols[1].button("Duplicate", use_container_width=True):
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

    if action_cols[2].button("Set active", use_container_width=True):
        loaded_meta = load_setup(selected_saved_setup_id)
        st.session_state["setup_config"] = dict(loaded_meta.get("setup_config", {}))
        st.success(f"Active setup set to '{loaded_meta.get('name', 'setup')}'.")

    if action_cols[3].button("Delete", use_container_width=True):
        delete_setup(selected_saved_setup_id)
        active = st.session_state.get("setup_config")
        if isinstance(active, dict) and active.get("setup_id") == selected_saved_setup_id:
            st.session_state.pop("setup_config", None)
        if isinstance(st.session_state.get(EDITOR_STATE_KEY), dict) and st.session_state[EDITOR_STATE_KEY].get(
            "setup_id"
        ) == selected_saved_setup_id:
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
        level for level in st.session_state.get(WIDGET_KEY_CONFLUENCE_LEVELS, []) if level in confluence_level_options
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
            min_value=1,
            max_value=len(selected_confluence_levels),
        )
        if min_valid_fallback:
            st.session_state[WIDGET_KEY_MIN_VALID_CONFLUENCES] = min_valid_default
        min_valid_confluences = int(
            st.number_input(
                "Minimum valid confluences",
                min_value=1,
                max_value=len(selected_confluence_levels),
                value=min_valid_default,
                step=1,
                key=WIDGET_KEY_MIN_VALID_CONFLUENCES,
            )
        )
    else:
        st.info("Select at least one confluence level.")

    selected_levels = [anchor_level, *selected_confluence_levels] if anchor_level else list(selected_confluence_levels)

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
trigger_options = ["touch", "reject", "break", "reclaim", "3c"]
trigger_index, _, trigger_fallback = _safe_selectbox_index_fallback(
    st.session_state.get(WIDGET_KEY_TRIGGER),
    options=trigger_options,
    default="touch",
)
if trigger_fallback:
    st.session_state[WIDGET_KEY_TRIGGER] = "touch"
trigger = st.selectbox("Trigger", options=trigger_options, index=trigger_index, key=WIDGET_KEY_TRIGGER)
trigger_timeframe_options = [
    option for option in TRIGGER_TIMEFRAME_CHOICES if option in VALID_TRIGGER_TIMEFRAMES
]
trigger_timeframe_state = st.session_state.get(WIDGET_KEY_TRIGGER_TIMEFRAME)
if isinstance(trigger_timeframe_state, str) and trigger_timeframe_state in TRIGGER_TIMEFRAME_LABELS:
    trigger_timeframe_state = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_state]
trigger_timeframe_default_value, trigger_timeframe_fallback = _safe_trigger_timeframe_fallback(trigger_timeframe_state)
if trigger_timeframe_default_value not in trigger_timeframe_options:
    trigger_timeframe_default_value = DEFAULT_TRIGGER_TIMEFRAME
    trigger_timeframe_fallback = True
if trigger_timeframe_fallback:
    st.session_state[WIDGET_KEY_TRIGGER_TIMEFRAME] = TRIGGER_TIMEFRAME_DISPLAY[DEFAULT_TRIGGER_TIMEFRAME]
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
direction = st.selectbox("Direction", options=direction_options, index=direction_index, key=WIDGET_KEY_DIRECTION)

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
    setup_name=setup_name,
    description=description,
)
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
        st.success("Active setup cleared.")
