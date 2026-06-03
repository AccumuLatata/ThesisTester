import streamlit as st

st.set_page_config(page_title="ThesisTester", page_icon="\U0001F4C8", layout="wide")

st.title("\U0001F4C8 ThesisTester")
st.caption("Intraday confluence-setup backtesting & research \u2014 Phase 0 scaffold")

st.markdown(
    """
Welcome. This is the **Phase 0** skeleton of ThesisTester.

**What works now**
- App boots as a multipage Streamlit app (see the sidebar).
- **Data** page: upload an OHLCV CSV (or use the bundled sample), validate it, tag RTH/ETH sessions, and preview.

**Coming next (see `docs/ENGINEERING.md`)**
- Level engine (SMA/EMA/VWAP/POC, session & profile levels)
- Confluence detection (1\u20135 levels) + triggers (incl. the 3-bar confirmation trigger)
- Backtest engine, SL/TP grid, time-of-day breakdown, statistical validation

**Confirmed configuration**
- Instruments: ES / NQ (futures session model)
- Data source: CSV upload
- Cluster tolerance unit: ticks
- Intrabar fill: SL-first (pessimistic)
- Entry timing: next-bar open (no look-ahead)
- Value area: 70%
"""
)

if "data" in st.session_state:
    df = st.session_state["data"]
    st.success(f"Data loaded in session: {len(df):,} bars.")
else:
    st.info("No data loaded yet \u2014 head to the **Data** page in the sidebar.")
