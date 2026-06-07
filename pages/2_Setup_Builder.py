from __future__ import annotations

import hashlib
import re

import streamlit as st

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
    st.markdown(
        f"**Trigger timeframe:** "
        f"{TRIGGER_TIMEFRAME_DISPLAY.get(normalize_trigger_timeframe(config.get('trigger_timeframe')), 'Base/current timeframe')}"
    )
    st.markdown(f"**Direction:** {config['direction']}")
    if config["trigger"] == "3c":
        params = config.get("trigger_params", {})
        st.markdown("**Trigger params:**")
        st.markdown(
            f"- Entry retrace ticks: {params.get('entry_retrace_ticks', 4.0)}\n"
            f"- Max entry wait bars after reversal: {params.get('max_entry_wait_bars_after_reversal', 5)}"
        )


st.title("🧩 Setup Builder")
st.caption("Configure and save reusable setup parameters for the Signals → Backtest workflow.")

if "levels" not in st.session_state:
    st.warning("No levels computed. Please load data on the Data page and compute levels on the Levels page first.")
    st.stop()

levels_df = st.session_state["levels"]
instrument = st.session_state.get("instrument", "ES")
all_level_columns = available_level_columns(levels_df)

if not all_level_columns:
    st.warning("No level columns found. Please compute levels on the Levels page first.")
    st.stop()

defaults = default_selected_levels(all_level_columns)

st.subheader("Setup identity")
setup_name = st.text_input("Setup name", value="Untitled setup")
description = st.text_area("Description / notes", value="", height=90)

st.subheader("Level and confluence settings")
selected_mode_label = st.selectbox(
    "Confluence mode",
    options=list(CONFLUENCE_MODE_LABELS.keys()),
    index=0,
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
        default=defaults,
    )
    tolerance_ticks = st.number_input("Tolerance ticks", min_value=0.0, value=4.0, step=0.5)
    min_conf = st.slider("Minimum confluences", min_value=1, max_value=5, value=2)
    max_conf = st.slider("Maximum confluences", min_value=1, max_value=5, value=5)
else:
    if not all_level_columns:
        st.warning("No level columns found. Please compute levels on the Levels page first.")
        st.stop()
    anchor_level = st.selectbox("Anchor level", options=all_level_columns, index=0)
    confluence_level_options = [level for level in all_level_columns if level != anchor_level]
    selected_confluence_levels = st.multiselect(
        "Confluence levels",
        options=confluence_level_options,
        default=[],
    )
    for level in selected_confluence_levels:
        st.markdown(f"**{level}**")
        rule_tolerance = st.number_input(
            f"Tolerance ticks — {level}",
            min_value=0.0,
            value=4.0,
            step=0.5,
            key=_anchor_rule_key("anchor_rule_tol", level),
        )
        rule_required = st.checkbox(
            f"Required — {level}",
            value=False,
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
        min_valid_confluences = int(
            st.number_input(
                "Minimum valid confluences",
                min_value=1,
                max_value=len(selected_confluence_levels),
                value=1,
                step=1,
            )
        )
    else:
        st.info("Select at least one confluence level.")

    selected_levels = [anchor_level, *selected_confluence_levels] if anchor_level else list(selected_confluence_levels)

naked_only = st.toggle("Naked only", value=False)
naked_requirement = st.radio("Naked requirement", options=["any", "all"], index=0, horizontal=True)

st.subheader("Trigger settings")
trigger_options = ["touch", "reject", "break", "reclaim", "3c"]
trigger = st.selectbox("Trigger", options=trigger_options, index=0)
trigger_timeframe_options = [
    option for option in TRIGGER_TIMEFRAME_CHOICES if option in VALID_TRIGGER_TIMEFRAMES
]
trigger_timeframe_default = trigger_timeframe_options.index(DEFAULT_TRIGGER_TIMEFRAME)
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
direction = st.selectbox("Direction", options=["long", "short", "both"], index=2)

trigger_params = {}
if trigger == "3c":
    entry_retrace_ticks = st.number_input("Entry retrace ticks", min_value=0.0, value=4.0, step=0.5)
    max_entry_wait_bars = st.number_input(
        "Max entry wait bars after reversal",
        min_value=0,
        value=5,
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

    errors = validate_setup_config(config)
    if errors:
        for error in errors:
            st.error(error)
    else:
        st.session_state["setup_config"] = config
        existing = st.session_state.get("setup_configs", [])
        replaced = any(item.get("name") == config["name"] for item in existing)
        updated = [item for item in existing if item.get("name") != config["name"]]
        updated.append(config)
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
