from __future__ import annotations

import streamlit as st

from thesistester.setup import (
    available_level_columns,
    build_setup_config,
    default_selected_levels,
    validate_setup_config,
)


def _render_setup_summary(config: dict) -> None:
    st.markdown(f"**Name:** {config['name']}")
    st.markdown(f"**Instrument:** {config['instrument']}")
    st.markdown(f"**Description:** {config.get('description', '') or '-'}")
    st.markdown(f"**Selected levels ({len(config['selected_levels'])}):** {', '.join(config['selected_levels'])}")
    st.markdown(f"**Tolerance ticks:** {config['tolerance_ticks']}")
    st.markdown(f"**Confluences:** {config['min_confluences']} to {config['max_confluences']}")
    st.markdown(f"**Naked only:** {config['naked_only']}")
    st.markdown(f"**Naked requirement:** {config['naked_requirement']}")
    st.markdown(f"**Trigger:** {config['trigger']}")
    st.markdown(f"**Direction:** {config['direction']}")
    if config["trigger"] == "confirm_3bar":
        params = config.get("trigger_params", {})
        st.markdown("**Trigger params:**")
        st.markdown(
            f"- Arrival tolerance ticks: {params.get('arrival_tolerance_ticks', 0.0)}\n"
            f"- Retrace entry ticks: {params.get('retrace_entry_ticks', 4.0)}\n"
            f"- Allow equal close: {params.get('allow_equal_close', False)}"
        )


st.title("🧩 Setup Builder")
st.caption("Configure and save reusable setup parameters for the Signals page.")

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
selected_levels = st.multiselect(
    "Selected level columns",
    options=all_level_columns,
    default=defaults,
)
tolerance_ticks = st.number_input("Tolerance ticks", min_value=0.0, value=4.0, step=0.5)
min_conf = st.slider("Minimum confluences", min_value=1, max_value=5, value=2)
max_conf = st.slider("Maximum confluences", min_value=1, max_value=5, value=5)
naked_only = st.toggle("Naked only", value=False)
naked_requirement = st.radio("Naked requirement", options=["any", "all"], index=0, horizontal=True)

st.subheader("Trigger settings")
trigger_options = ["touch", "reject", "break", "reclaim", "confirm_3bar"]
trigger = st.selectbox("Trigger", options=trigger_options, index=0)
direction = st.selectbox("Direction", options=["long", "short", "both"], index=2)

trigger_params = {}
if trigger == "confirm_3bar":
    arrival_tolerance_ticks = st.number_input("Arrival tolerance ticks", min_value=0.0, value=0.0, step=0.5)
    retrace_entry_ticks = st.number_input("Retrace entry ticks", min_value=0.0, value=4.0, step=0.5)
    allow_equal_close = st.toggle("Allow equal close", value=False)
    trigger_params = {
        "arrival_tolerance_ticks": arrival_tolerance_ticks,
        "retrace_entry_ticks": retrace_entry_ticks,
        "allow_equal_close": allow_equal_close,
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
        direction=direction,
        trigger_params=trigger_params,
    )

    errors = validate_setup_config(config)
    if errors:
        for error in errors:
            st.error(error)
    else:
        st.session_state["setup_config"] = config
        existing = st.session_state.get("setup_configs", [])
        updated = [item for item in existing if item.get("name") != config["name"]]
        updated.append(config)
        st.session_state["setup_configs"] = updated
        st.success("Setup saved and active.")

active_setup = st.session_state.get("setup_config")
if active_setup:
    st.subheader("Active setup")
    _render_setup_summary(active_setup)

    if st.button("Clear active setup"):
        st.session_state.pop("setup_config", None)
        st.success("Active setup cleared.")
