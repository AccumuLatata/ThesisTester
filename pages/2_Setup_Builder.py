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
    VALID_DIRECTIONS,
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


def _anchor_rule_key(prefix: str, level: str) -> str:
    """Build a stable Streamlit widget key for an anchor-rule control."""
    sanitized_level = re.sub(r"[^0-9A-Za-z_]+", "_", level).strip("_")
    level_hash = hashlib.sha256(level.encode("utf-8")).hexdigest()[:8]
    key_level = f"{sanitized_level}_{level_hash}" if sanitized_level else f"level_{level_hash}"
    return f"{prefix}_{key_level}"


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


def _render_setup_level_warnings(config: dict[str, Any], level_columns: list[str]) -> None:
    confluence_mode = str(config.get("confluence_mode") or "global_cluster")
    if confluence_mode == "anchor_rules":
        missing_anchor = []
        anchor_level = config.get("anchor_level")
        if isinstance(anchor_level, str) and anchor_level and anchor_level not in level_columns:
            missing_anchor.append(anchor_level)
        missing_rules = []
        for rule in config.get("confluence_rules", []):
            if not isinstance(rule, dict):
                continue
            level = str(rule.get("level", "")).strip()
            if level and level not in level_columns:
                missing_rules.append(level)
        if missing_anchor:
            st.warning(
                f"Loaded setup anchor level is unavailable in current levels: {', '.join(sorted(set(missing_anchor)))}."
            )
        if missing_rules:
            st.warning(
                f"Loaded setup has unavailable confluence-rule levels: {', '.join(sorted(set(missing_rules)))}."
            )
        return

    selected_levels = config.get("selected_levels", [])
    if not isinstance(selected_levels, list):
        return
    missing = sorted({str(level) for level in selected_levels if str(level) not in level_columns})
    if missing:
        st.warning(
            f"Loaded setup contains unavailable selected levels: {', '.join(missing)}. "
            "Only available levels are preselected in the editor."
        )


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
    )
    selected_saved_setup = saved_setup_options[selected_saved_setup_id]

    action_cols = st.columns(4)
    if action_cols[0].button("Load to editor", use_container_width=True):
        loaded_meta = load_setup(selected_saved_setup_id)
        loaded_config = dict(loaded_meta.get("setup_config", {}))
        st.session_state[EDITOR_STATE_KEY] = loaded_config
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
setup_name = st.text_input("Setup name", value=str(editor_seed.get("name", "Untitled setup")))
description = st.text_area("Description / notes", value=str(editor_seed.get("description", "")), height=90)

st.subheader("Level and confluence settings")
mode_value = str(editor_seed.get("confluence_mode", "global_cluster"))
mode_label = CONFLUENCE_MODE_DISPLAY.get(mode_value, "Global cluster")
mode_options = list(CONFLUENCE_MODE_LABELS.keys())
selected_mode_label = st.selectbox(
    "Confluence mode",
    options=mode_options,
    index=mode_options.index(mode_label),
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
    selected_level_seed = [
        str(level) for level in editor_seed.get("selected_levels", []) if str(level) in all_level_columns
    ]
    selected_levels = st.multiselect(
        "Selected level columns",
        options=all_level_columns,
        default=selected_level_seed,
    )
    tolerance_ticks = st.number_input(
        "Tolerance ticks",
        min_value=0.0,
        value=float(editor_seed.get("tolerance_ticks", 4.0)),
        step=0.5,
    )
    min_conf_default = max(1, min(5, int(editor_seed.get("min_confluences", 2))))
    max_conf_default = max(min_conf_default, min(5, int(editor_seed.get("max_confluences", 5))))
    min_conf = st.slider("Minimum confluences", min_value=1, max_value=5, value=min_conf_default)
    max_conf = st.slider("Maximum confluences", min_value=1, max_value=5, value=max_conf_default)
else:
    anchor_seed = editor_seed.get("anchor_level")
    anchor_default = str(anchor_seed) if isinstance(anchor_seed, str) and anchor_seed in all_level_columns else all_level_columns[0]
    anchor_level = st.selectbox("Anchor level", options=all_level_columns, index=all_level_columns.index(anchor_default))
    confluence_level_options = [level for level in all_level_columns if level != anchor_level]
    rules_seed = editor_seed.get("confluence_rules", [])
    rule_defaults = {}
    for rule in rules_seed if isinstance(rules_seed, list) else []:
        if not isinstance(rule, dict):
            continue
        level = str(rule.get("level", "")).strip()
        if not level:
            continue
        rule_defaults[level] = {
            "tolerance_ticks": float(rule.get("tolerance_ticks", 4.0)),
            "required": bool(rule.get("required", False)),
        }
    confluence_seed = [level for level in rule_defaults if level in confluence_level_options]
    selected_confluence_levels = st.multiselect(
        "Confluence levels",
        options=confluence_level_options,
        default=confluence_seed,
    )
    for level in selected_confluence_levels:
        st.markdown(f"**{level}**")
        level_defaults = rule_defaults.get(level, {"tolerance_ticks": 4.0, "required": False})
        rule_tolerance = st.number_input(
            f"Tolerance ticks — {level}",
            min_value=0.0,
            value=float(level_defaults["tolerance_ticks"]),
            step=0.5,
            key=_anchor_rule_key("anchor_rule_tol", level),
        )
        rule_required = st.checkbox(
            f"Required — {level}",
            value=bool(level_defaults["required"]),
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
        min_valid_default = int(editor_seed.get("min_valid_confluences", 1))
        min_valid_default = max(1, min(len(selected_confluence_levels), min_valid_default))
        min_valid_confluences = int(
            st.number_input(
                "Minimum valid confluences",
                min_value=1,
                max_value=len(selected_confluence_levels),
                value=min_valid_default,
                step=1,
            )
        )
    else:
        st.info("Select at least one confluence level.")

    selected_levels = [anchor_level, *selected_confluence_levels] if anchor_level else list(selected_confluence_levels)

naked_only = st.toggle("Naked only", value=bool(editor_seed.get("naked_only", False)))
naked_requirement_options = ["any", "all"]
naked_requirement_default = str(editor_seed.get("naked_requirement", "any")).lower()
if naked_requirement_default not in naked_requirement_options:
    naked_requirement_default = "any"
naked_requirement = st.radio(
    "Naked requirement",
    options=naked_requirement_options,
    index=naked_requirement_options.index(naked_requirement_default),
    horizontal=True,
)

st.subheader("Trigger settings")
trigger_options = ["touch", "reject", "break", "reclaim", "3c"]
trigger_default = str(editor_seed.get("trigger", "touch"))
if trigger_default not in trigger_options:
    trigger_default = "touch"
trigger = st.selectbox("Trigger", options=trigger_options, index=trigger_options.index(trigger_default))
trigger_timeframe_options = [
    option for option in TRIGGER_TIMEFRAME_CHOICES if option in VALID_TRIGGER_TIMEFRAMES
]
trigger_timeframe_default_value = normalize_trigger_timeframe(editor_seed.get("trigger_timeframe"))
if trigger_timeframe_default_value not in trigger_timeframe_options:
    trigger_timeframe_default_value = DEFAULT_TRIGGER_TIMEFRAME
trigger_timeframe_default = trigger_timeframe_options.index(trigger_timeframe_default_value)

if trigger == "3c":
    trigger_timeframe_label = st.selectbox(
        "Trigger timeframe",
        options=list(TRIGGER_TIMEFRAME_LABELS.keys()),
        index=trigger_timeframe_default,
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
        help=(
            "Candle-close trigger logic is evaluated on the selected trigger timeframe. "
            "The default preserves current behavior."
        ),
    )
    trigger_timeframe = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_label]

direction_options = ["long", "short", "both"]
direction_default = str(editor_seed.get("direction", "both"))
if direction_default not in VALID_DIRECTIONS:
    direction_default = "both"
direction = st.selectbox("Direction", options=direction_options, index=direction_options.index(direction_default))

trigger_params = {}
trigger_params_seed = editor_seed.get("trigger_params", {})
if trigger == "3c":
    entry_retrace_default = 4.0
    max_wait_default = 5
    if isinstance(trigger_params_seed, dict):
        entry_retrace_default = float(trigger_params_seed.get("entry_retrace_ticks", 4.0))
        max_wait_default = int(trigger_params_seed.get("max_entry_wait_bars_after_reversal", 5))
    entry_retrace_ticks = st.number_input("Entry retrace ticks", min_value=0.0, value=entry_retrace_default, step=0.5)
    max_entry_wait_bars = st.number_input(
        "Max entry wait bars after reversal",
        min_value=0,
        value=max_wait_default,
        step=1,
    )
    trigger_params = {
        "entry_retrace_ticks": entry_retrace_ticks,
        "max_entry_wait_bars_after_reversal": int(max_entry_wait_bars),
    }

if st.button("Save setup", type="primary"):
    config = build_setup_config(
        name=setup_name,
        description=description,
        instrument=instrument,
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
    )
    setup_id = editor_seed.get("setup_id")
    if isinstance(setup_id, str) and setup_id:
        config["setup_id"] = setup_id
    config["dataset_id"] = current_dataset_id if isinstance(current_dataset_id, str) and current_dataset_id else None

    errors = validate_setup_config(config)
    if errors:
        for error in errors:
            st.error(error)
    else:
        saved_meta = save_setup(
            config,
            setup_id=config.get("setup_id"),
            dataset_id=config.get("dataset_id"),
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
