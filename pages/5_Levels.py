import plotly.graph_objects as go
import streamlit as st

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_session_levels
from thesistester.persistence import (
    compute_dataset_id,
    delete_levels,
    find_matching_levels,
    get_active_levels_hash,
    list_saved_levels,
    load_levels,
    save_levels,
    set_active_levels_hash,
)

OPENING_RANGE_KEY = "levels_opening_range_minutes"
SMA_LENGTHS_KEY = "levels_sma_lengths_raw"
EMA_LENGTHS_KEY = "levels_ema_lengths_raw"
VWAP_WINDOWS_KEY = "levels_vwap_windows"
POC_WINDOWS_KEY = "levels_poc_windows"
VALUE_AREA_PCT_KEY = "levels_value_area_pct"


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
    settings = meta.get("levels_settings") or {}
    created_at = str(meta.get("created_at", ""))[:19] or "unknown"
    opening_range = settings.get("opening_range_minutes", "—")
    sma = ",".join(str(value) for value in settings.get("sma_lengths", [])) or "—"
    ema = ",".join(str(value) for value in settings.get("ema_lengths", [])) or "—"
    vwap = ",".join(str(value) for value in settings.get("vwap_windows", [])) or "—"
    poc = ",".join(str(value) for value in settings.get("poc_windows", [])) or "—"
    value_area_pct = settings.get("value_area_pct")
    value_area_label = (
        f"{int(round(float(value_area_pct) * 100.0))}%"
        if isinstance(value_area_pct, (int, float))
        else "—"
    )
    return (
        f"{created_at} · {meta.get('settings_hash', '')[:12]} · OR {opening_range}m · "
        f"SMA[{sma}] · EMA[{ema}] · VWAP[{vwap}] · POC[{poc}] · VA {value_area_label}"
    )


def _apply_loaded_levels_state(loaded_meta: dict) -> None:
    st.session_state["levels"] = loaded_meta["levels"]
    st.session_state["session_levels"] = loaded_meta["session_levels"]
    st.session_state["levels_settings"] = loaded_meta["levels_settings"]
    st.session_state["levels_data_fingerprint"] = loaded_meta["levels_data_fingerprint"]
    settings = loaded_meta["levels_settings"] or {}
    opening_range = int(settings.get("opening_range_minutes", 30))
    st.session_state[OPENING_RANGE_KEY] = opening_range if opening_range in (5, 15, 30) else 30
    st.session_state[SMA_LENGTHS_KEY] = ",".join(
        str(value) for value in settings.get("sma_lengths", [20, 50, 200])
    )
    st.session_state[EMA_LENGTHS_KEY] = ",".join(
        str(value) for value in settings.get("ema_lengths", [20, 50, 200])
    )
    st.session_state[VWAP_WINDOWS_KEY] = [
        window
        for window in settings.get("vwap_windows", ["15min", "30min", "1h", "4h"])
        if window in {"15min", "30min", "1h", "4h"}
    ]
    st.session_state[POC_WINDOWS_KEY] = [
        window for window in settings.get("poc_windows", ["30min", "1h", "4h"]) if window in {"30min", "1h", "4h"}
    ]
    value_area_pct = settings.get("value_area_pct", 0.7)
    value_area_value = int(round(float(value_area_pct) * 100.0))
    st.session_state[VALUE_AREA_PCT_KEY] = max(50, min(95, value_area_value))


st.title("📏 Levels")

if "data" not in st.session_state:
    st.warning("No data loaded. Please load data from the Data page first.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
dataset_id = compute_dataset_id(
    st.session_state["data"],
    instrument=instrument,
    base_interval=st.session_state.get("base_interval"),
    source_timezone=st.session_state.get("source_timezone"),
    exchange_timezone=st.session_state.get("exchange_timezone"),
)
st.session_state["dataset_id"] = dataset_id
if OPENING_RANGE_KEY not in st.session_state:
    st.session_state[OPENING_RANGE_KEY] = 30
if SMA_LENGTHS_KEY not in st.session_state:
    st.session_state[SMA_LENGTHS_KEY] = "20,50,200"
if EMA_LENGTHS_KEY not in st.session_state:
    st.session_state[EMA_LENGTHS_KEY] = "20,50,200"
if VWAP_WINDOWS_KEY not in st.session_state:
    st.session_state[VWAP_WINDOWS_KEY] = ["15min", "30min", "1h", "4h"]
if POC_WINDOWS_KEY not in st.session_state:
    st.session_state[POC_WINDOWS_KEY] = ["30min", "1h", "4h"]
if VALUE_AREA_PCT_KEY not in st.session_state:
    st.session_state[VALUE_AREA_PCT_KEY] = 70

opening_range_minutes = st.selectbox(
    "Opening range duration (minutes)",
    [5, 15, 30],
    key=OPENING_RANGE_KEY,
)
sma_lengths_raw = st.text_input("SMA lengths (comma-separated)", key=SMA_LENGTHS_KEY)
ema_lengths_raw = st.text_input("EMA lengths (comma-separated)", key=EMA_LENGTHS_KEY)
vwap_windows = st.multiselect(
    "Rolling VWAP windows",
    options=["15min", "30min", "1h", "4h"],
    key=VWAP_WINDOWS_KEY,
)
poc_windows = st.multiselect(
    "Rolling POC windows",
    options=["30min", "1h", "4h"],
    key=POC_WINDOWS_KEY,
)
value_area_pct = (
    st.slider("Value area (%)", min_value=50, max_value=95, step=1, key=VALUE_AREA_PCT_KEY) / 100.0
)

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
saved_levels_snapshots = list_saved_levels(dataset_id)
if saved_levels_snapshots:
    st.divider()
    st.subheader("Saved levels snapshots")
    active_levels_hash = get_active_levels_hash(dataset_id)
    snapshot_options = [item["settings_hash"] for item in saved_levels_snapshots]
    selected_index = 0
    if active_levels_hash in snapshot_options:
        selected_index = snapshot_options.index(active_levels_hash)
    elif active_levels_hash is not None:
        st.warning("Previously active saved levels were not found for this dataset.")
    selected_settings_hash = st.selectbox(
        "Saved snapshots",
        options=snapshot_options,
        index=selected_index,
        format_func=lambda settings_hash: _saved_levels_label(
            next(
                item for item in saved_levels_snapshots if item["settings_hash"] == settings_hash
            )
        ),
    )
    selected_snapshot = next(
        item for item in saved_levels_snapshots if item["settings_hash"] == selected_settings_hash
    )
    snapshot_actions = st.columns(2)
    if snapshot_actions[0].button("Load selected saved levels", use_container_width=True):
        levels_df, session_levels, loaded_meta = load_levels(dataset_id, selected_settings_hash)
        _apply_loaded_levels_state(
            {
                "levels": levels_df,
                "session_levels": session_levels,
                "levels_settings": loaded_meta["levels_settings"],
                "levels_data_fingerprint": loaded_meta["levels_data_fingerprint"],
            }
        )
        set_active_levels_hash(dataset_id, selected_settings_hash)
        st.success("Loaded selected saved levels.")
        st.rerun()
    if snapshot_actions[1].button("Delete selected saved levels", use_container_width=True):
        delete_levels(dataset_id, selected_settings_hash)
        if get_active_levels_hash(dataset_id) == selected_settings_hash:
            set_active_levels_hash(dataset_id, None)
        st.success("Deleted selected saved levels.")
        st.rerun()

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
        levels_df, session_levels, loaded_meta = load_levels(
            dataset_id,
            matching_saved_levels["settings_hash"],
        )
        _apply_loaded_levels_state(
            {
                "levels": levels_df,
                "session_levels": session_levels,
                "levels_settings": loaded_meta["levels_settings"],
                "levels_data_fingerprint": loaded_meta["levels_data_fingerprint"],
            }
        )
        set_active_levels_hash(dataset_id, matching_saved_levels["settings_hash"])
        previous_settings = _normalize_levels_settings(loaded_meta["levels_settings"])
        previous_data_fingerprint = loaded_meta["levels_data_fingerprint"]
        has_calculated_levels = True
        levels_are_stale = False
        settings_are_stale = False
        st.success("Loaded saved levels without recalculating.")
        st.rerun()
    if saved_level_actions[1].button(
        "Delete saved levels",
        key="delete_matching_saved_levels_prompt",
        use_container_width=True,
    ):
        delete_levels(dataset_id, matching_saved_levels["settings_hash"])
        if get_active_levels_hash(dataset_id) == matching_saved_levels["settings_hash"]:
            set_active_levels_hash(dataset_id, None)
        matching_saved_levels = None
        st.success("Deleted matching saved levels.")

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
            set_active_levels_hash(dataset_id, None)
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
