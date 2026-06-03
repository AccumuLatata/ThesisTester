from pathlib import Path

import streamlit as st

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import (
    DataValidationError,
    format_interval,
    load_ohlcv,
    validate_ohlcv,
)
from thesistester.data.resample import SUPPORTED_TIMEFRAMES, resample_ohlcv
from thesistester.data.sessions import tag_session

st.title("\U0001F4E5 Data")

inst = st.selectbox("Instrument", list(INSTRUMENTS.keys()))
meta = INSTRUMENTS[inst]
st.caption(
    f"{meta.name} \u00b7 tick size {meta.tick_size} \u00b7 point value ${meta.point_value:,.0f} "
    f"\u00b7 session tz {meta.exchange_tz} ({meta.rth_start}\u2013{meta.rth_end} RTH)"
)

source = st.radio("Source", ["Sample data", "Upload CSV"], horizontal=True)

file = None
if source == "Upload CSV":
    file = st.file_uploader(
        "OHLCV CSV with columns: timestamp,open,high,low,close,volume", type=["csv"]
    )
else:
    sample = Path(__file__).resolve().parents[1] / "sample_data" / "ES_sample_1m.csv"
    file = sample if sample.exists() else None
    if file is None:
        st.error("Sample data not found.")

if file is not None:
    try:
        raw_df = load_ohlcv(file, tz=meta.exchange_tz)
        report = validate_ohlcv(raw_df)
        base_interval = format_interval(report.inferred_interval)
        df = tag_session(raw_df, inst)

        st.success(f"Loaded {len(df):,} bars.")
        st.caption(f"{df['timestamp'].min()} \u2192 {df['timestamp'].max()}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Rows", f"{len(df):,}")
        c2.metric("Inferred base interval", base_interval)
        c3.metric("Validation issues", len(report.issues))

        if report.is_clean:
            st.info("Validation passed \u2713")
        else:
            st.warning("Validation issues detected:")
            for issue in report.messages():
                st.write(f"- {issue}")

        c1, c2 = st.columns(2)
        c1.metric("RTH bars", int((df["session"] == "RTH").sum()))
        c2.metric("ETH bars", int((df["session"] == "ETH").sum()))

        selected_timeframes = st.multiselect(
            "Preview resampled timeframes",
            options=list(SUPPORTED_TIMEFRAMES),
            default=["5min", "15min"],
        )

        resampled_data = {}
        for timeframe in selected_timeframes:
            out = resample_ohlcv(raw_df, timeframe)
            out = tag_session(out, inst)
            resampled_data[timeframe] = out
            with st.expander(f"{timeframe} preview ({len(out):,} rows)"):
                st.dataframe(out.head(50), use_container_width=True)

        st.subheader("Base timeframe preview")
        st.dataframe(df.head(50), use_container_width=True)

        st.session_state["data"] = df
        st.session_state["resampled_data"] = resampled_data
        st.session_state["instrument"] = inst
        st.session_state["base_interval"] = base_interval
    except DataValidationError as exc:
        st.error(str(exc))
