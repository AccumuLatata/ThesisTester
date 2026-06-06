from pathlib import Path
import sys
import os

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.data.loader import (
    DataValidationError,
    format_interval,
    load_ohlcv,
    validate_ohlcv,
)
from thesistester.data.resample import SUPPORTED_TIMEFRAMES, resample_ohlcv
from thesistester.data.sessions import tag_session
from thesistester.app_state import (
    ACTIVE_SAVED_DATASET_KEY,
    BOOTSTRAP_MESSAGE_KEY,
    bootstrap_active_saved_dataset,
)
from thesistester.persistence import (
    clear_active_dataset_id,
    compute_dataset_id,
    delete_dataset,
    get_store_root,
    list_datasets,
    load_dataset,
    save_dataset,
    set_active_dataset_id,
)

FLASH_MESSAGE_KEY = "_data_local_store_message"
PENDING_INSTRUMENT_SELECTOR_KEY = "_pending_data_instrument_selector"
PENDING_SOURCE_TZ_SELECTOR_KEY = "_pending_data_source_timezone_selector"


@st.cache_data(show_spinner=False)
def cached_resample_and_tag(raw_df, instrument: str, timeframe: str):
    """Cache and return session-tagged resampled OHLCV data for preview."""
    out = resample_ohlcv(raw_df, timeframe)
    return tag_session(out, instrument)


def _default_dataset_name(df, instrument: str) -> str:
    if df is None or df.empty or "timestamp" not in df.columns:
        return f"{instrument} dataset"
    start = df["timestamp"].min()
    end = df["timestamp"].max()
    return f"{instrument} {start.date()} to {end.date()}"


def _saved_dataset_label(meta: dict) -> str:
    rows = f"{int(meta.get('rows', 0)):,} rows"
    date_range = "unknown range"
    if meta.get("timestamp_min") and meta.get("timestamp_max"):
        start = meta["timestamp_min"][:10]
        end = meta["timestamp_max"][:10]
        date_range = f"{start} → {end}"
    saved_at = meta.get("created_at", "")[:10] or "unknown date"
    return f"{meta.get('name', meta['dataset_id'])} · {meta.get('instrument', '—')} · {rows} · {date_range} · saved {saved_at}"


def _clear_dataset_dependent_state() -> None:
    for key in [
        "levels",
        "session_levels",
        "levels_settings",
        "levels_data_fingerprint",
        "confluence_zones",
        "naked_flags",
        "last_signal_setup",
        "signal_context",
        "signals",
        "trades",
        "trade_summary",
        "equity_curve",
        "grid_results",
        "best_grid_result",
        "time_bucketed_trades",
        "time_grouped_summary",
        "validation_summary",
    ]:
        st.session_state.pop(key, None)


def _set_active_dataset_state(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    resampled_data: dict | None,
    saved_dataset_id: str | None,
):
    dataset_id = saved_dataset_id or compute_dataset_id(
        df,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    previous_dataset_id = st.session_state.get("dataset_id")
    if previous_dataset_id is not None and previous_dataset_id != dataset_id:
        _clear_dataset_dependent_state()
    st.session_state["data"] = df
    st.session_state["resampled_data"] = resampled_data or {}
    st.session_state["instrument"] = instrument
    st.session_state["base_interval"] = base_interval
    st.session_state["source_timezone"] = source_timezone
    st.session_state["exchange_timezone"] = exchange_timezone
    st.session_state["dataset_id"] = dataset_id
    if saved_dataset_id is None:
        clear_active_dataset_id()
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
    else:
        set_active_dataset_id(saved_dataset_id)
        st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_dataset_id


def _render_dataset_summary(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    report=None,
    resampled_data: dict | None = None,
    saved_dataset_loaded: bool = False,
):
    st.success(f"Loaded {len(df):,} bars.")
    st.caption(f"{df['timestamp'].min()} → {df['timestamp'].max()}")
    st.caption(
        f"Source timezone: {source_timezone} → canonical exchange timezone: {exchange_timezone}"
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Rows", f"{len(df):,}")
    summary_cols[1].metric("Inferred base interval", base_interval or "unknown")
    summary_cols[2].metric("RTH bars", int((df["session"] == "RTH").sum()))
    summary_cols[3].metric("ETH bars", int((df["session"] == "ETH").sum()))

    if report is not None:
        detail_cols = st.columns(2)
        detail_cols[0].metric("Validation issues", len(report.issues))
        detail_cols[1].metric("Instrument", instrument)
        if report.is_clean:
            st.info("Validation passed ✓")
        else:
            st.warning("Validation issues detected:")
            for issue in report.messages():
                st.write(f"- {issue}")
    elif saved_dataset_loaded:
        st.info("Loaded canonical dataset from local store.")
    else:
        st.info("Using dataset from current session.")

    for timeframe, out in (resampled_data or {}).items():
        with st.expander(f"{timeframe} preview ({len(out):,} rows)"):
            st.dataframe(out.head(50), use_container_width=True)

    st.subheader("Base timeframe preview")
    st.dataframe(df.head(50), use_container_width=True)


st.title("\U0001F4E5 Data")

bootstrap_active_saved_dataset()

flash_message = st.session_state.pop(FLASH_MESSAGE_KEY, None)
if flash_message:
    st.success(flash_message)
bootstrap_message = st.session_state.pop(BOOTSTRAP_MESSAGE_KEY, None)
if bootstrap_message:
    st.success(bootstrap_message)

st.subheader("Local saved datasets")
st.caption(f"Local store: `{get_store_root()}`")
if not os.environ.get("THESISTESTER_STORE_DIR"):
    st.warning(
        "THESISTESTER_STORE_DIR is not set. Saved datasets are stored in a local repo folder "
        "and may not persist across environments."
    )
saved_datasets = list_datasets()
saved_dataset_options = {item["dataset_id"]: item for item in saved_datasets}

if saved_datasets:
    selected_saved_dataset_id = st.selectbox(
        "Saved datasets",
        options=list(saved_dataset_options),
        format_func=lambda dataset_id: _saved_dataset_label(saved_dataset_options[dataset_id]),
    )
    selected_saved_dataset = saved_dataset_options[selected_saved_dataset_id]

    action_cols = st.columns(3)
    if action_cols[0].button("Load saved dataset", use_container_width=True):
        loaded_df, loaded_meta = load_dataset(selected_saved_dataset_id)
        _set_active_dataset_state(
            loaded_df,
            instrument=loaded_meta["instrument"],
            base_interval=loaded_meta.get("base_interval"),
            source_timezone=loaded_meta.get("source_timezone"),
            exchange_timezone=loaded_meta.get("exchange_timezone"),
            resampled_data={},
            saved_dataset_id=loaded_meta["dataset_id"],
        )
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Loaded saved dataset '{loaded_meta['name']}' ({loaded_meta['dataset_id'][:12]}...)."
        )
        st.session_state[PENDING_INSTRUMENT_SELECTOR_KEY] = loaded_meta["instrument"]
        if loaded_meta.get("source_timezone") is not None:
            st.session_state[PENDING_SOURCE_TZ_SELECTOR_KEY] = loaded_meta[
                "source_timezone"
            ]
        st.rerun()

    if action_cols[1].button("Delete saved dataset", use_container_width=True):
        delete_dataset(selected_saved_dataset_id)
        if st.session_state.get(ACTIVE_SAVED_DATASET_KEY) == selected_saved_dataset_id:
            st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Deleted saved dataset '{selected_saved_dataset.get('name', selected_saved_dataset_id)}'."
        )
        st.rerun()

    if action_cols[2].button("Refresh saved datasets", use_container_width=True):
        st.rerun()
else:
    st.caption(f"No saved datasets found in `{get_store_root()}`.")
    if st.button("Refresh saved datasets"):
        st.rerun()

st.divider()

available_instruments = list(INSTRUMENTS.keys())
if PENDING_INSTRUMENT_SELECTOR_KEY in st.session_state:
    st.session_state["data_instrument_selector"] = st.session_state.pop(
        PENDING_INSTRUMENT_SELECTOR_KEY
    )
if "data_instrument_selector" not in st.session_state:
    st.session_state["data_instrument_selector"] = st.session_state.get(
        "instrument",
        available_instruments[0],
    )
inst = st.selectbox("Instrument", available_instruments, key="data_instrument_selector")
meta = INSTRUMENTS[inst]
st.caption(
    f"{meta.name} \u00b7 tick size {meta.tick_size} \u00b7 point value ${meta.point_value:,.0f} "
    f"\u00b7 session tz {meta.exchange_tz} ({meta.rth_start}\u2013{meta.rth_end} RTH)"
)

source = st.radio("Source", ["Sample data", "Upload CSV"], horizontal=True)
default_source_tz = "America/New_York" if source == "Sample data" else meta.exchange_tz
if PENDING_SOURCE_TZ_SELECTOR_KEY in st.session_state:
    st.session_state["data_source_timezone_selector"] = st.session_state.pop(
        PENDING_SOURCE_TZ_SELECTOR_KEY
    )
if "data_source_timezone_selector" not in st.session_state:
    st.session_state["data_source_timezone_selector"] = default_source_tz
source_tz = st.selectbox(
    "Source timestamp timezone",
    TIMEZONE_OPTIONS,
    index=TIMEZONE_OPTIONS.index(st.session_state["data_source_timezone_selector"]),
    key="data_source_timezone_selector",
    help=(
        "Use this for timezone-naive CSV timestamps. Timezone-aware timestamps are "
        "converted from their embedded timezone automatically."
    ),
)

file = None
if source == "Upload CSV":
    file = st.file_uploader(
        "OHLCV CSV with columns: timestamp,open,high,low,close,volume", type=["csv"]
    )
else:
    sample = REPO_ROOT / "sample_data" / "ES_sample_1m.csv"
    file = sample if sample.exists() else None
    if file is None:
        st.error("Sample data not found.")

use_source_dataset = file is not None and (
    source == "Upload CSV" or ACTIVE_SAVED_DATASET_KEY not in st.session_state
)

if use_source_dataset:
    try:
        raw_df = load_ohlcv(file, source_tz=source_tz, target_tz=meta.exchange_tz)
        report = validate_ohlcv(raw_df)
        base_interval = format_interval(report.inferred_interval)
        df = tag_session(raw_df, inst)

        selected_timeframes = st.multiselect(
            "Preview resampled timeframes",
            options=list(SUPPORTED_TIMEFRAMES),
            default=["5min", "15min"],
        )

        resampled_data = {}
        for timeframe in selected_timeframes:
            out = cached_resample_and_tag(raw_df, inst, timeframe)
            resampled_data[timeframe] = out
        _set_active_dataset_state(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=meta.exchange_tz,
            resampled_data=resampled_data,
            saved_dataset_id=None,
        )
        _render_dataset_summary(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=meta.exchange_tz,
            report=report,
            resampled_data=resampled_data,
        )
    except DataValidationError as exc:
        st.error(str(exc))
elif "data" in st.session_state:
    _render_dataset_summary(
        st.session_state["data"],
        instrument=st.session_state.get("instrument", inst),
        base_interval=st.session_state.get("base_interval"),
        source_timezone=st.session_state.get("source_timezone"),
        exchange_timezone=st.session_state.get("exchange_timezone"),
        resampled_data=st.session_state.get("resampled_data"),
        saved_dataset_loaded=ACTIVE_SAVED_DATASET_KEY in st.session_state,
    )

st.divider()

current_df = st.session_state.get("data")
if current_df is not None:
    current_instrument = st.session_state.get("instrument", inst)
    default_name = _default_dataset_name(current_df, current_instrument)
    dataset_name = st.text_input("Local dataset name", value=default_name)
    if st.button("Save dataset locally"):
        saved_meta = save_dataset(
            current_df,
            name=dataset_name.strip() or default_name,
            instrument=current_instrument,
            base_interval=st.session_state.get("base_interval"),
            source_timezone=st.session_state.get("source_timezone"),
            exchange_timezone=st.session_state.get("exchange_timezone"),
        )
        st.session_state["dataset_id"] = saved_meta["dataset_id"]
        set_active_dataset_id(saved_meta["dataset_id"])
        st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_meta["dataset_id"]
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Saved dataset '{saved_meta['name']}' locally ({saved_meta['dataset_id'][:12]}...)."
        )
        st.rerun()
