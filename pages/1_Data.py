from pathlib import Path

import streamlit as st

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import DataValidationError, load_ohlcv, validate_ohlcv
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
        df = load_ohlcv(file, tz=meta.exchange_tz)
        issues = validate_ohlcv(df)
        df = tag_session(df, inst)
        st.success(
            f"Loaded {len(df):,} bars \u00b7 {df['timestamp'].min()} \u2192 {df['timestamp'].max()}"
        )
        if issues:
            st.warning("Validation issues: " + "; ".join(issues))
        else:
            st.info("Validation passed \u2713")
        c1, c2 = st.columns(2)
        c1.metric("RTH bars", int((df["session"] == "RTH").sum()))
        c2.metric("ETH bars", int((df["session"] == "ETH").sum()))
        st.dataframe(df.head(50), use_container_width=True)
        st.session_state["data"] = df
        st.session_state["instrument"] = inst
    except DataValidationError as exc:
        st.error(str(exc))
