import streamlit as st

st.title("\u25B6\uFE0F Run")
st.caption("Stub \u2014 wired up in Phase 5.")
if "data" in st.session_state:
    st.success(f"Data ready: {len(st.session_state['data']):,} bars.")
else:
    st.warning("Load data first on the Data page.")
st.info("Backtest execution lands in Phase 5.")
