import streamlit as st
import pandas as pd

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
from thesistester.visualization import (
    build_levels_chart,
    clip_by_time_window,
    recent_rows_window,
    timestamp_bounds,
)


_OPENING_RANGE_KEY = "levels_opening_range_minutes"
_SMA_LENGTHS_KEY = "levels_sma_lengths_raw"
_EMA_LENGTHS_KEY = "levels_ema_lengths_raw"
_SMA_TIMEFRAMES_KEY = "levels_sma_timeframes"
_EMA_TIMEFRAMES_KEY = "levels_ema_timeframes"
_VWAP_WINDOWS_KEY = "levels_vwap_windows"
_POC_WINDOWS_KEY = "levels_poc_windows"
_VALUE_AREA_PCT_KEY = "levels_value_area_pct"
_PRIOR_DAY_AGG_TICKS_KEY = "levels_prior_day_profile_aggregation_ticks"
_PRIOR_WEEK_AGG_TICKS_KEY = "levels_prior_week_profile_aggregation_ticks"
_PRIOR_MONTH_AGG_TICKS_KEY = "levels_prior_month_profile_aggregation_ticks"
_PENDING_WIDGET_SYNC_KEY = "_pending_levels_widget_sync_settings"
_INDICATOR_TIMEFRAME_OPTIONS = ["1min", "5min", "30min"]
_VWAP_WINDOW_OPTIONS = ["15min", "30min", "1h", "4h"]
_POC_WINDOW_OPTIONS = ["30min", "1h", "4h"]
# Stage 6 — opt-in level family keys
_PIVOTS_ENABLED_KEY = "levels_pivots_enabled"
_PIVOT_TIMEFRAMES_KEY = "levels_pivot_timeframes"
_PIVOT_LEFT_KEY = "levels_pivot_left"
_PIVOT_RIGHT_KEY = "levels_pivot_right"
_SESSION_VWAP_ENABLED_KEY = "levels_session_vwap_enabled"
_SINGLE_PRINTS_ENABLED_KEY = "levels_single_prints_enabled"
_APOC_ENABLED_KEY = "levels_apoc_enabled"
_PIVOT_TIMEFRAME_OPTIONS = ["1min", "5min", "30min", "4h"]


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
    out.setdefault("prior_day_profile_aggregation_ticks", 1)
    out.setdefault("prior_week_profile_aggregation_ticks", 1)
    out.setdefault("prior_month_profile_aggregation_ticks", 1)
    # Stage 6 — opt-in level family defaults (all disabled for backward compat)
    out.setdefault("pivots_enabled", False)
    out.setdefault("pivot_timeframes", ["1min", "5min", "30min", "4h"])
    out.setdefault("pivot_left", 2)
    out.setdefault("pivot_right", 2)
    out.setdefault("session_vwap_enabled", False)
    out.setdefault("session_vwap_anchor", "RTH")
    out.setdefault("single_prints_enabled", False)
    out.setdefault("apoc_enabled", False)
    for key in ("sma_timeframes", "ema_timeframes", "vwap_windows", "poc_windows", "pivot_timeframes"):
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
    daily_agg = settings.get("prior_day_profile_aggregation_ticks", 1)
    weekly_agg = settings.get("prior_week_profile_aggregation_ticks", 1)
    monthly_agg = settings.get("prior_month_profile_aggregation_ticks", 1)
    created_at_raw = meta.get("created_at")
    created_at = str(created_at_raw)[:10] if created_at_raw else "unknown date"
    opt_in_parts = []
    if settings.get("pivots_enabled"):
        opt_in_parts.append("pivots")
    if settings.get("session_vwap_enabled"):
        opt_in_parts.append("dVWAP")
    if settings.get("single_prints_enabled"):
        opt_in_parts.append("SP")
    if settings.get("apoc_enabled"):
        opt_in_parts.append("APOC")
    opt_in_suffix = f" · Opt-in: {','.join(opt_in_parts)}" if opt_in_parts else ""
    return (
        f"{str(meta.get('settings_hash', 'unknown'))[:12]}… · OR {opening_range}m · "
        f"VA {value_area_label} · Day/Week/Month agg {daily_agg}/{weekly_agg}/{monthly_agg} · saved {created_at}"
        f"{opt_in_suffix}"
    )


def _queue_levels_widget_sync(settings: dict | None) -> None:
    if isinstance(settings, dict):
        st.session_state[_PENDING_WIDGET_SYNC_KEY] = settings
    else:
        st.session_state[_PENDING_WIDGET_SYNC_KEY] = None


def _sync_levels_widget_state(settings: dict) -> None:
    opening_range = settings.get("opening_range_minutes")
    if opening_range in {5, 15, 30}:
        st.session_state[_OPENING_RANGE_KEY] = opening_range

    sma_lengths = settings.get("sma_lengths")
    if isinstance(sma_lengths, list) and sma_lengths:
        st.session_state[_SMA_LENGTHS_KEY] = ",".join(str(length) for length in sma_lengths)

    ema_lengths = settings.get("ema_lengths")
    if isinstance(ema_lengths, list) and ema_lengths:
        st.session_state[_EMA_LENGTHS_KEY] = ",".join(str(length) for length in ema_lengths)

    sma_timeframes = settings.get("sma_timeframes")
    if isinstance(sma_timeframes, list):
        st.session_state[_SMA_TIMEFRAMES_KEY] = [
            timeframe for timeframe in _INDICATOR_TIMEFRAME_OPTIONS if timeframe in sma_timeframes
        ]

    ema_timeframes = settings.get("ema_timeframes")
    if isinstance(ema_timeframes, list):
        st.session_state[_EMA_TIMEFRAMES_KEY] = [
            timeframe for timeframe in _INDICATOR_TIMEFRAME_OPTIONS if timeframe in ema_timeframes
        ]

    vwap_windows = settings.get("vwap_windows")
    if isinstance(vwap_windows, list):
        st.session_state[_VWAP_WINDOWS_KEY] = [
            window for window in _VWAP_WINDOW_OPTIONS if window in vwap_windows
        ]

    poc_windows = settings.get("poc_windows")
    if isinstance(poc_windows, list):
        st.session_state[_POC_WINDOWS_KEY] = [
            window for window in _POC_WINDOW_OPTIONS if window in poc_windows
        ]

    value_area_pct = settings.get("value_area_pct")
    if isinstance(value_area_pct, (int, float)):
        value_area_pct_int = round(value_area_pct * 100)
        if 50 <= value_area_pct_int <= 95:
            st.session_state[_VALUE_AREA_PCT_KEY] = value_area_pct_int

    prior_day_aggregation_ticks = settings.get("prior_day_profile_aggregation_ticks", 1)
    if isinstance(prior_day_aggregation_ticks, int) and prior_day_aggregation_ticks > 0:
        st.session_state[_PRIOR_DAY_AGG_TICKS_KEY] = prior_day_aggregation_ticks

    prior_week_aggregation_ticks = settings.get("prior_week_profile_aggregation_ticks", 1)
    if isinstance(prior_week_aggregation_ticks, int) and prior_week_aggregation_ticks > 0:
        st.session_state[_PRIOR_WEEK_AGG_TICKS_KEY] = prior_week_aggregation_ticks

    prior_month_aggregation_ticks = settings.get("prior_month_profile_aggregation_ticks", 1)
    if isinstance(prior_month_aggregation_ticks, int) and prior_month_aggregation_ticks > 0:
        st.session_state[_PRIOR_MONTH_AGG_TICKS_KEY] = prior_month_aggregation_ticks

    # Stage 6 — opt-in level family widget sync
    st.session_state[_PIVOTS_ENABLED_KEY] = bool(settings.get("pivots_enabled", False))

    pivot_timeframes = settings.get("pivot_timeframes")
    if isinstance(pivot_timeframes, (list, tuple)):
        st.session_state[_PIVOT_TIMEFRAMES_KEY] = [
            tf for tf in _PIVOT_TIMEFRAME_OPTIONS if tf in pivot_timeframes
        ]
    else:
        st.session_state[_PIVOT_TIMEFRAMES_KEY] = list(_PIVOT_TIMEFRAME_OPTIONS)

    pivot_left = settings.get("pivot_left", 2)
    if isinstance(pivot_left, int) and pivot_left >= 1:
        st.session_state[_PIVOT_LEFT_KEY] = pivot_left

    pivot_right = settings.get("pivot_right", 2)
    if isinstance(pivot_right, int) and pivot_right >= 1:
        st.session_state[_PIVOT_RIGHT_KEY] = pivot_right

    st.session_state[_SESSION_VWAP_ENABLED_KEY] = bool(settings.get("session_vwap_enabled", False))
    st.session_state[_SINGLE_PRINTS_ENABLED_KEY] = bool(settings.get("single_prints_enabled", False))
    st.session_state[_APOC_ENABLED_KEY] = bool(settings.get("apoc_enabled", False))


def _load_saved_levels_into_session(dataset_id: str, settings_hash: str) -> bool:
    try:
        levels_df, session_levels, loaded_meta = load_levels(dataset_id, settings_hash)
    except (FileNotFoundError, ValueError, OSError) as exc:
        if get_active_levels_hash(dataset_id) == settings_hash:
            clear_active_levels_hash(dataset_id)
        st.error(
            f"Unable to load saved levels ({settings_hash[:12]}...): {exc}. "
            "Try recalculating levels or removing this saved snapshot."
        )
        return False

    st.session_state["levels"] = levels_df
    st.session_state["session_levels"] = session_levels
    st.session_state["levels_settings"] = loaded_meta.get("levels_settings")
    st.session_state["levels_data_fingerprint"] = loaded_meta.get("levels_data_fingerprint")
    _queue_levels_widget_sync(loaded_meta.get("levels_settings"))
    set_active_levels_hash(dataset_id, settings_hash)
    return True


st.title("📏 Levels")

bootstrap_active_saved_dataset()

pending_widget_sync = st.session_state.pop(_PENDING_WIDGET_SYNC_KEY, None)
if isinstance(pending_widget_sync, dict):
    _sync_levels_widget_state(pending_widget_sync)

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
opening_range_minutes = st.selectbox(
    "Opening range duration (minutes)",
    [5, 15, 30],
    index=2,
    key=_OPENING_RANGE_KEY,
)
sma_lengths_raw = st.text_input(
    "SMA lengths (comma-separated)",
    value="20,50,200",
    key=_SMA_LENGTHS_KEY,
)
ema_lengths_raw = st.text_input(
    "EMA lengths (comma-separated)",
    value="20,50,200",
    key=_EMA_LENGTHS_KEY,
)
sma_timeframes = st.multiselect(
    "SMA timeframes",
    options=_INDICATOR_TIMEFRAME_OPTIONS,
    default=["1min"],
    key=_SMA_TIMEFRAMES_KEY,
)
ema_timeframes = st.multiselect(
    "EMA timeframes",
    options=_INDICATOR_TIMEFRAME_OPTIONS,
    default=["1min"],
    key=_EMA_TIMEFRAMES_KEY,
)
vwap_windows = st.multiselect(
    "Rolling VWAP windows",
    options=_VWAP_WINDOW_OPTIONS,
    default=_VWAP_WINDOW_OPTIONS,
    key=_VWAP_WINDOWS_KEY,
)
poc_windows = st.multiselect(
    "Rolling POC windows",
    options=_POC_WINDOW_OPTIONS,
    default=_POC_WINDOW_OPTIONS,
    key=_POC_WINDOWS_KEY,
)
value_area_pct = (
    st.slider(
        "Value area (%)",
        min_value=50,
        max_value=95,
        value=70,
        step=1,
        key=_VALUE_AREA_PCT_KEY,
    )
    / 100.0
)
aggregation_help = (
    "Affects only prior day pdVAH/pdVAL/pdPOC, prior week pwVAH/pwVAL/pwPOC, "
    "and prior month pmVAH/pmVAL/pmPOC profile binning. "
    "Does not change instrument tick size or rolling POC windows."
)
prior_day_aggregation_ticks = st.number_input(
    "Prior day VA profile aggregation (ticks)",
    min_value=1,
    value=1,
    step=1,
    key=_PRIOR_DAY_AGG_TICKS_KEY,
    help=aggregation_help,
)
prior_week_aggregation_ticks = st.number_input(
    "Prior week VA profile aggregation (ticks)",
    min_value=1,
    value=1,
    step=1,
    key=_PRIOR_WEEK_AGG_TICKS_KEY,
    help=aggregation_help,
)
prior_month_aggregation_ticks = st.number_input(
    "Prior month VA profile aggregation (ticks)",
    min_value=1,
    value=1,
    step=1,
    key=_PRIOR_MONTH_AGG_TICKS_KEY,
    help=aggregation_help,
)

with st.expander("Advanced opt-in levels", expanded=False):
    st.caption("All opt-in levels are disabled by default. Existing behavior is unchanged unless a box is checked.")
    pivots_enabled = st.checkbox(
        "Enable confirmed pivots",
        value=False,
        key=_PIVOTS_ENABLED_KEY,
    )
    if pivots_enabled:
        pivot_timeframes = st.multiselect(
            "Pivot timeframes",
            options=_PIVOT_TIMEFRAME_OPTIONS,
            default=_PIVOT_TIMEFRAME_OPTIONS,
            key=_PIVOT_TIMEFRAMES_KEY,
        )
        pivot_left = st.number_input(
            "Pivot left",
            min_value=1,
            value=2,
            step=1,
            key=_PIVOT_LEFT_KEY,
        )
        pivot_right = st.number_input(
            "Pivot right",
            min_value=1,
            value=2,
            step=1,
            key=_PIVOT_RIGHT_KEY,
        )
    else:
        # Preserve prior pivot widget state when present, but provide deterministic
        # local defaults for the disabled settings payload/hash.
        if _PIVOT_TIMEFRAMES_KEY not in st.session_state:
            st.session_state[_PIVOT_TIMEFRAMES_KEY] = list(_PIVOT_TIMEFRAME_OPTIONS)
        if _PIVOT_LEFT_KEY not in st.session_state:
            st.session_state[_PIVOT_LEFT_KEY] = 2
        if _PIVOT_RIGHT_KEY not in st.session_state:
            st.session_state[_PIVOT_RIGHT_KEY] = 2
        pivot_timeframes = list(_PIVOT_TIMEFRAME_OPTIONS)
        pivot_left = 2
        pivot_right = 2
    session_vwap_enabled = st.checkbox(
        "Enable developing RTH VWAP (dVWAP_RTH)",
        value=False,
        key=_SESSION_VWAP_ENABLED_KEY,
    )
    single_prints_enabled = st.checkbox(
        "Enable TPO 30m Single Prints",
        value=False,
        key=_SINGLE_PRINTS_ENABLED_KEY,
    )
    apoc_enabled = st.checkbox(
        "Enable APOC / pAPOC",
        value=False,
        key=_APOC_ENABLED_KEY,
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
        "sma_timeframes": sma_timeframes,
        "ema_timeframes": ema_timeframes,
        "vwap_windows": vwap_windows,
        "poc_windows": poc_windows,
        "value_area_pct": value_area_pct,
        "prior_day_profile_aggregation_ticks": int(prior_day_aggregation_ticks),
        "prior_week_profile_aggregation_ticks": int(prior_week_aggregation_ticks),
        "prior_month_profile_aggregation_ticks": int(prior_month_aggregation_ticks),
        "pivots_enabled": pivots_enabled,
        "pivot_timeframes": pivot_timeframes,
        "pivot_left": int(pivot_left),
        "pivot_right": int(pivot_right),
        "session_vwap_enabled": session_vwap_enabled,
        "session_vwap_anchor": "RTH",
        "single_prints_enabled": single_prints_enabled,
        "apoc_enabled": apoc_enabled,
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
        width="stretch",
    ):
        if _load_saved_levels_into_session(dataset_id, matching_saved_levels["settings_hash"]):
            levels_df = st.session_state.get("levels")
            previous_settings = _normalize_levels_settings(st.session_state.get("levels_settings"))
            previous_data_fingerprint = st.session_state.get("levels_data_fingerprint")
            has_calculated_levels = True
            levels_are_stale = False
            settings_are_stale = False
            st.rerun()
    if saved_level_actions[1].button(
        "Delete saved levels",
        key="delete_matching_saved_levels_prompt",
        width="stretch",
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
        width="stretch",
    ):
        if _load_saved_levels_into_session(dataset_id, selected_settings_hash):
            levels_df = st.session_state.get("levels")
            previous_settings = _normalize_levels_settings(st.session_state.get("levels_settings"))
            previous_data_fingerprint = st.session_state.get("levels_data_fingerprint")
            has_calculated_levels = True
            levels_are_stale = False
            settings_are_stale = False
            st.rerun()
    if snapshot_actions[1].button(
        "Delete selected saved levels",
        key="delete_selected_saved_levels",
        width="stretch",
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

        try:
            levels_df = compute_all_levels(
                base_df,
                instrument=instrument,
                opening_range_minutes=opening_range_minutes,
                sma_lengths=sma_lengths,
                ema_lengths=ema_lengths,
                sma_timeframes=sma_timeframes,
                ema_timeframes=ema_timeframes,
                vwap_windows=vwap_windows,
                poc_windows=poc_windows,
                value_area_pct=value_area_pct,
                prior_day_aggregation_ticks=int(prior_day_aggregation_ticks),
                prior_week_aggregation_ticks=int(prior_week_aggregation_ticks),
                prior_month_aggregation_ticks=int(prior_month_aggregation_ticks),
                pivots_enabled=pivots_enabled,
                pivot_timeframes=pivot_timeframes,
                pivot_left=int(pivot_left),
                pivot_right=int(pivot_right),
                session_vwap_enabled=session_vwap_enabled,
                session_vwap_anchor="RTH",
                single_prints_enabled=single_prints_enabled,
                apoc_enabled=apoc_enabled,
            )
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

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
        width="stretch",
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
        width="stretch",
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
st.dataframe(levels_df[preview_cols].tail(200), width="stretch")

selected_levels = st.multiselect(
    "Levels to plot",
    options=level_columns,
    default=[col for col in ["RTH_Open", "OR_High", "OR_Low", "ONH", "ONL"] if col in level_columns],
)

chart_range = st.selectbox(
    "Chart range",
    options=["Last 2,000 rows", "Last 10,000 rows", "Custom date range", "Full dataset"],
    index=0,
)
st.caption(
    "Chart range affects visualization only. The levels table and saved level artifacts remain unchanged."
)

chart_start = None
chart_end = None
if chart_range == "Last 2,000 rows":
    chart_start, chart_end = recent_rows_window(levels_df, rows=2_000)
elif chart_range == "Last 10,000 rows":
    chart_start, chart_end = recent_rows_window(levels_df, rows=10_000)
elif chart_range == "Custom date range":
    min_ts, max_ts = timestamp_bounds(levels_df)
    if min_ts is not None and max_ts is not None:
        custom_cols = st.columns(2)
        custom_start_date = custom_cols[0].date_input(
            "Custom chart start",
            value=min_ts.date(),
            min_value=min_ts.date(),
            max_value=max_ts.date(),
        )
        custom_end_date = custom_cols[1].date_input(
            "Custom chart end",
            value=max_ts.date(),
            min_value=min_ts.date(),
            max_value=max_ts.date(),
        )
        chart_start = pd.Timestamp(custom_start_date)
        chart_end = pd.Timestamp(custom_end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

chart_levels_df = (
    levels_df.copy(deep=True)
    if chart_range == "Full dataset"
    else clip_by_time_window(levels_df, start=chart_start, end=chart_end)
)

fig = build_levels_chart(levels_df=chart_levels_df, selected_levels=selected_levels)
st.plotly_chart(fig, width="stretch")
