import streamlit as st

st.set_page_config(page_title="ThesisTester", page_icon="\U0001f4c8", layout="wide")

st.title("\U0001f4c8 ThesisTester")
st.caption(
    "Intraday confluence-setup research and backtesting workbench for ES/NQ/MES/MNQ futures."
)

st.markdown(
    """
ThesisTester is a multipage research workflow for intraday confluence setups.

**Recommended workflow**
1. Load and validate OHLCV data (optional lower-timeframe bars for observed replay).
2. Compute levels.
3. Configure a setup in Setup Builder (optional OTF filter).
4. Generate confluence-based candidate signals.
5. Backtest a fixed SL/TP assumption and/or run an SL/TP grid search.
6. Analyze time/session performance.
7. Run validation diagnostics (bootstrap, walk-forward, optional batteries, OTF matrix).
8. Export artifacts, research bundles, or portfolio composites.
9. Optionally orchestrate theses in Research Assistant.

**Implemented now**
- **Data**: CSV OHLCV ingestion/validation, vendor profiles, local saved datasets, optional lower-timeframe replay.
- **Levels**: session, structural, indicator, profile, and advanced opt-in level families.
- **Setup Builder**: reusable setup library with global-cluster or anchor-based confluence and optional OTF filter.
- **Signals**: confluence zone detection, naked flags, and trigger generation (OTF is not applied here).
- **Backtest**: fixed SL/TP simulation with costs, session exits, exposure policy, intrabar models, and exit management.
- **Grid Search**: SL/TP sweep and ranking over the same execution assumptions.
- **Time Analysis**: time-of-day/session-window diagnostics on completed trades.
- **Validation**: bootstrap/permutation, walk-forward, overfitting/noise/sensitivity batteries, OTF validation matrix.
- **Report / Export**: research artifact and report export for reproducibility.
- **Research Bundles**: portable session snapshot export/import.
- **Portfolio**: diagnostic multi-setup trade composition (not a capital simulator).
- **Research Assistant**: confirmation-gated thesis orchestration over the same research pipeline.

**Research assumptions / caveats**
- Outputs are research diagnostics only, not trading advice.
- Validation diagnostics do not prove a durable trading edge.
- Backtests use configurable assumptions (entry timing, intrabar resolution, costs, session exits, exposure). The default intrabar model is pessimistic SL-first when SL and TP are both reachable in the same bar; other models are opt-in.
- OTF is disabled by default. When enabled, admission is applied at Backtest, Grid, and Walk-forward — not during signal generation.
"""
)

if "data" in st.session_state:
    df = st.session_state["data"]
    st.success(f"Data loaded in session: {len(df):,} bars.")
else:
    st.info("No data loaded yet \u2014 head to the **Data** page in the sidebar.")
