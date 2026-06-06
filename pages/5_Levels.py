import plotly.graph_objects as go
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_session_levels
from thesistester.persistence import (
    clear_active_levels_hash,
    compute_dataset_id,
    delete_levels,
    find_matching_levels,
    get_active_levels_hash,
    list_saved_levels,
    load_levels,
    save_levels,
    set_active_levels_hash,
)


def _parse_lengths(raw: str, label: str) -> list[int]:
    """Parse comma-separated length values for indicator controls."""
    lengths: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value <= 0:
            raise ValueError(f"{label} lengths must be positive integers, got: {value}")
        lengths.append(value)
    if not lengths:
        raise ValueError(f"Please provide at least one {label} length.")
    return sorted(set(lengths))


def _normalize_levels_settings(settings: dict | None) -> dict | None:
    """Return a stable settings shape for stale-result comparisons."""
    if not isinstance(settings, dict):
        return None
    out = dict(settings)
    for key in ("vwap_windows", "poc_windows"):
        value = out.get(key)
        if isinstance(value, list):
            out[key] = sorted(value)
        elif isinstance(value, tuple):
            out[key] = sorted(list(value))
    return out


def _levels_data_fingerprint(df, instrument: str) -> dict:
    """Return a lightweight fingerprint of the current loaded input data context."""
    timestamp_min = None
    timestamp_max = None
    if not df.empty and "timestamp" in df.columns:
        timestamp_min = str(df["timestamp"].min())
        timestamp_max = str(df["timestamp"].max())

    return {
        "instrument": instrument,
        "rows": len(df),
        "timestamp_min": timestamp_min,
        "timestamp_max": timestamp_max,
        "columns": sorted(df.columns),
        "base_interval": st.session_state.get("base_interval"),
        "source_timezone": st.session_state.get("source_timezone"),
        "exchange_timezone": st.session_state.get("exchange_timezone"),
    }


def _saved_levels_label(meta: dict) -> str:
    settings = meta.get("levels_settings")
    if not isinstance(settings, dict):
        settings = {}
    opening_range = settings.get("opening_range_minutes", "—")
    value_area_pct = settings.get("value_area_pct")
    if isinstance(value_area_pct, (int, float)):
        value_area_label = f"{int(value_area_pct * 100)}%"
    else:
        value_area_label = "—"
    created_at = str(meta.get("created_at", ""))[:10] or "unknown date"
    return (
        f"{str(meta.get('settings_hash', 'unknown'))[:12]}… · OR {opening_range}m · "
        f"VA {value_area_label} · saved {created_at}"
    )


def _load_saved_levels_into_session(dataset_id: str, settings_hash: str) -> bool:
    try:
        levels_df, session_levels, loaded_meta = load_levels(dataset_id, settings_hash)
    except (FileNotFoundError, ValueError, OSError) as exc:
        if get_active_levels_hash(dataset_id) == settings_hash:
            clear_active_levels_hash(dataset_id)
        st.error(f"Unable to load saved levels ({settings_hash[:12]}...): {exc}")
        return False

    st.session_state["levels"] = levels_df
    st.session_state["session_levels"] = session_levels
    st.session_state["levels_settings"] = loaded_meta.get("levels_settings")
    st.session_state["levels_data_fingerprint"] = loaded_meta.get("levels_data_fingerprint")
    set_active_levels_hash(dataset_id, settings_hash)
    return True


st.title("📏 Levels")

bootstrap_active_saved_dataset()

if "data" not in st.session_state:
    st.warning("No data loaded. Please load data from the Data page first.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
dataset_id = st.session_state.get("dataset_id")
if not isinstance(dataset_id, str) or not dataset_id:
    dataset_id = compute_dataset_id(
        st.session_state["data"],
        instrument=instrument,
        base_interval=st.session_state.get("base_interval"),
        source_timezone=st.session_state.get("source_timezone"),
        exchange_timezone=st.session_state.get("exchange_timezone"),
    )
st.session_state["dataset_id"] = dataset_id
opening_range_minutes = st.selectbox("Opening range duration (minutes)", [5, 15, 30], index=2)
sma_lengths_raw = st.text_input("SMA lengths (comma-separated)", value="20,50,200")
ema_lengths_raw = st.text_input("EMA lengths (comma-separated)", value="20,50,200")
vwap_windows = st.multiselect(
    "Rolling VWAP windows",
    options=["15min", "30min", "1h", "4h"],
    default=["15min", "30min", "1h", "4h"],
)
poc_windows = st.multiselect(
    "Rolling POC windows",
    options=["30min", "1h", "4h"],
    default=["30min", "1h", "4h"],
)
value_area_pct = st.slider("Value area (%)", min_value=50, max_value=95, value=70, step=1) / 100.0

try:
    sma_lengths = _parse_lengths(sma_lengths_raw, "SMA")
    ema_lengths = _parse_lengths(ema_lengths_raw, "EMA")
except ValueError as exc:
    st.error(str(exc))
    st.stop()

current_settings = _normalize_levels_settings(
    {
        "instrument": instrument,
        "opening_range_minutes": opening_range_minutes,
        "sma_lengths": sma_lengths,
        "ema_lengths": ema_lengths,
        "vwap_windows": vwap_windows,
        "poc_windows": poc_windows,
        "value_area_pct": value_area_pct,
    }
)
current_data_fingerprint = _levels_data_fingerprint(st.session_state["data"], instrument)
previous_settings = _normalize_levels_settings(st.session_state.get("levels_settings"))
previous_data_fingerprint = st.session_state.get("levels_data_fingerprint")
has_calculated_levels = "levels" in st.session_state and "session_levels" in st.session_state
levels_df = st.session_state.get("levels")

matching_saved_levels = find_matching_levels(
    dataset_id=dataset_id,
    levels_settings=current_settings,
)
levels_are_stale = (
    has_calculated_levels
    and previous_data_fingerprint is not None
    and previous_data_fingerprint != current_data_fingerprint
)
settings_are_stale = previous_settings is not None and previous_settings != current_settings

if matching_saved_levels is not None and (not has_calculated_levels or levels_are_stale or settings_are_stale):
    st.info("Matching saved levels found for this dataset/settings.")
    saved_level_actions = st.columns(2)
    if saved_level_actions[0].button(
        "Load saved levels",
        key="load_matching_saved_levels",
        use_container_width=True,
    ):
        if _load_saved_levels_into_session(dataset_id, matching_saved_levels["settings_hash"]):
            levels_df = st.session_state.get("levels")
            previous_settings = _normalize_levels_settings(st.session_state.get("levels_settings"))
            previous_data_fingerprint = st.session_state.get("levels_data_fingerprint")
            has_calculated_levels = True
            levels_are_stale = False
            settings_are_stale = False
            st.success("Loaded saved levels without recalculating.")
    if saved_level_actions[1].button(
        "Delete saved levels",
        key="delete_matching_saved_levels_prompt",
        use_container_width=True,
    ):
        delete_levels(dataset_id, matching_saved_levels["settings_hash"])
        if get_active_levels_hash(dataset_id) == matching_saved_levels["settings_hash"]:
            clear_active_levels_hash(dataset_id)
        matching_saved_levels = None
        st.success("Deleted matching saved levels.")

saved_level_snapshots = [
    item
    for item in list_saved_levels(dataset_id)
    if isinstance(item.get("settings_hash"), str) and item["settings_hash"]
]
if saved_level_snapshots:
    st.divider()
    st.subheader("Saved level snapshots")
    snapshot_options = {item["settings_hash"]: item for item in saved_level_snapshots}
    snapshot_ids = list(snapshot_options)
    active_snapshot_hash = get_active_levels_hash(dataset_id)
    default_index = snapshot_ids.index(active_snapshot_hash) if active_snapshot_hash in snapshot_ids else 0
    selected_settings_hash = st.selectbox(
        "Saved snapshots",
        options=snapshot_ids,
        index=default_index,
        format_func=lambda settings_hash: _saved_levels_label(snapshot_options[settings_hash]),
        key="saved_levels_snapshot_selector",
    )
    selected_snapshot_meta = snapshot_options[selected_settings_hash]
    selected_snapshot_settings = _normalize_levels_settings(
        selected_snapshot_meta.get("levels_settings")
    )
    if selected_snapshot_settings is not None and selected_snapshot_settings != current_settings:
        st.caption("Selected snapshot settings differ from current controls.")
    snapshot_actions = st.columns(2)
    if snapshot_actions[0].button(
        "Load selected saved levels",
        key="load_selected_saved_levels",
        use_container_width=True,
    ):
        if _load_saved_levels_into_session(dataset_id, selected_settings_hash):
            levels_df = st.session_state.get("levels")
            previous_settings = _normalize_levels_settings(st.session_state.get("levels_settings"))
            previous_data_fingerprint = st.session_state.get("levels_data_fingerprint")
            has_calculated_levels = True
            levels_are_stale = False
            settings_are_stale = False
            st.success("Loaded selected saved levels.")
    if snapshot_actions[1].button(
        "Delete selected saved levels",
        key="delete_selected_saved_levels",
        use_container_width=True,
    ):
        delete_levels(dataset_id, selected_settings_hash)
        if get_active_levels_hash(dataset_id) == selected_settings_hash:
            clear_active_levels_hash(dataset_id)
        if (
            matching_saved_levels is not None
            and matching_saved_levels.get("settings_hash") == selected_settings_hash
        ):
            matching_saved_levels = None
        st.success("Deleted selected saved levels.")

button_label = "Recalculate levels" if has_calculated_levels else "Calculate levels"
calculate_levels = st.button(button_label, type="primary")

if calculate_levels:
    with st.spinner("Calculating levels..."):
        base_df = st.session_state["data"]
        if "session" not in base_df.columns:
            base_df = tag_session(base_df, instrument)

        levels_df = compute_all_levels(
            base_df,
            instrument=instrument,
            opening_range_minutes=opening_range_minutes,
            sma_lengths=sma_lengths,
            ema_lengths=ema_lengths,
            vwap_windows=vwap_windows,
            poc_windows=poc_windows,
            value_area_pct=value_area_pct,
        )

        session_levels = compute_session_levels(
            base_df,
            instrument=instrument,
            opening_range_minutes=opening_range_minutes,
        )
        st.session_state["session_levels"] = session_levels
        st.session_state["levels"] = levels_df
        st.session_state["levels_settings"] = current_settings
        st.session_state["levels_data_fingerprint"] = current_data_fingerprint
        previous_settings = current_settings
        previous_data_fingerprint = current_data_fingerprint
        has_calculated_levels = True

levels_df = st.session_state.get("levels")
if levels_df is None:
    st.info("Configure the settings above, then click **Calculate levels** to generate levels.")
    st.stop()

if (
    has_calculated_levels
    and previous_data_fingerprint is not None
    and previous_data_fingerprint != current_data_fingerprint
):
    st.warning("Loaded data has changed. Click **Recalculate levels** to update results.")
    st.stop()

if previous_settings is not None and previous_settings != current_settings:
    st.info("Settings have changed. Click **Recalculate levels** to update results.")

levels_current = (
    has_calculated_levels
    and previous_data_fingerprint is not None
    and previous_data_fingerprint == current_data_fingerprint
    and previous_settings is not None
    and previous_settings == current_settings
)

if levels_current:
    st.divider()
    persistence_actions = st.columns(2)
    if persistence_actions[0].button(
        "Save levels locally",
        key="save_current_levels_locally",
        use_container_width=True,
    ):
        saved_levels_meta = save_levels(
            dataset_id=dataset_id,
            levels=st.session_state["levels"],
            session_levels=st.session_state["session_levels"],
            levels_settings=st.session_state["levels_settings"],
            levels_data_fingerprint=st.session_state["levels_data_fingerprint"],
        )
        set_active_levels_hash(dataset_id, saved_levels_meta["settings_hash"])
        matching_saved_levels = saved_levels_meta
        st.success(
            f"Saved levels locally ({saved_levels_meta['settings_hash'][:12]}...)."
        )
    if matching_saved_levels is not None and persistence_actions[1].button(
        "Delete saved levels",
        key="delete_current_saved_levels",
        use_container_width=True,
    ):
        delete_levels(dataset_id, matching_saved_levels["settings_hash"])
        if get_active_levels_hash(dataset_id) == matching_saved_levels["settings_hash"]:
            clear_active_levels_hash(dataset_id)
        matching_saved_levels = None
        st.success("Deleted matching saved levels.")

base_columns = {"timestamp", "open", "high", "low", "close", "volume", "session", "settlement"}
level_columns = [col for col in levels_df.columns if col not in base_columns]

st.subheader("Levels preview")
preview_cols = ["timestamp", "close", "session", *level_columns]
st.dataframe(levels_df[preview_cols].tail(200), use_container_width=True)

selected_levels = st.multiselect(
    "Levels to plot",
    options=level_columns,
    default=[col for col in ["RTH_Open", "OR_High", "OR_Low", "ONH", "ONL"] if col in level_columns],
)

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=levels_df["timestamp"],
        y=levels_df["close"],
        mode="lines",
        name="close",
    )
)

for col in selected_levels:
    fig.add_trace(
        go.Scatter(
            x=levels_df["timestamp"],
            y=levels_df[col],
            mode="lines",
            name=col,
        )
    )

fig.update_layout(height=520, margin=dict(l=10, r=10, t=35, b=10), legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)
