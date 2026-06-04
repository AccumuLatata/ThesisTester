import streamlit as st

st.set_page_config(page_title="ThesisTester", page_icon="\U0001F4C8", layout="wide")

st.title("\U0001F4C8 ThesisTester")
st.caption("Intraday confluence-setup research and backtesting workbench for ES/NQ futures.")

st.markdown(
    """
ThesisTester is a multipage research workflow for intraday confluence setups.

**Recommended workflow**
1. Load and validate OHLCV data.
2. Configure a setup.
3. Compute levels.
4. Generate confluence-based signals.
5. Backtest fixed SL/TP assumptions.
6. Run SL/TP grid search.
7. Analyze time/session performance.
8. Run statistical validation diagnostics.
9. Export research artifacts.

**Implemented now**
- **Data**: CSV OHLCV ingestion and validation with ES/NQ session handling.
- **Setup Builder**: save and reuse setup configuration.
- **Levels**: session, structural, indicator, and profile level computation.
- **Signals**: confluence zone detection and trigger generation.
- **Backtest**: fixed SL/TP simulation (core execution page).
- **Grid Search**: SL/TP sweep and ranking (core execution page).
- **Time Analysis**: time-of-day/session-window diagnostics.
- **Validation**: bootstrap/permutation and overfit-oriented diagnostics.
- **Report / Export**: research artifact and report export for reproducibility.

**Research assumptions / caveats**
- Outputs are research diagnostics only, not trading advice.
- Validation diagnostics do not prove a durable trading edge.
- Backtests use assumptions including next-bar entries and pessimistic SL-first handling when SL and TP are both reachable intrabar.
"""
)

if "data" in st.session_state:
    df = st.session_state["data"]
    st.success(f"Data loaded in session: {len(df):,} bars.")
else:
    st.info("No data loaded yet \u2014 head to the **Data** page in the sidebar.")
