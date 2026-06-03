# ThesisTester

Simple Streamlit app for intraday strategy research on futures data.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run tests

```bash
pytest -q
```

## Phase status

- **Phase 1 (data layer):** CSV OHLCV ingestion, timezone normalization, validation,
  base-interval inference, RTH/ETH session tagging, and OHLCV resampling (1min, 5min,
  15min, 30min, 1h, 4h, 1D).
- **Phase 2 (session/structural levels):** session level engine for opens, prior O/H/L/EQ,
  overnight and opening-range levels, RTH open, and previous settlement preview via the
  new Streamlit **Levels** page.
- **Phase 3 (indicator/profile levels):** SMA/EMA and rolling VWAP levels, rolling POC
  windows, and prior day/week/month profile levels (`VAH/VAL/POC`) with 70% value area
  and tick-bucketed ES/NQ volume bins.
- **Phase 4 (confluence detection, naked levels, signal generation):** tick-based
  confluence zone detection (`detect_confluence_zones`), naked/untested level flags
  (`flag_naked_levels`), and five trigger types — `touch`, `reject`, `break`, `reclaim`,
  `confirm_3bar` — exposed via a new **Signals** page (`pages/6_Signals.py`).
  Candidate signals are stored in `st.session_state["signals"]` for Phase 5 backtesting.
- **Phase 5 (backtest engine, KPIs, results):** bar-by-bar trade simulation with a
  single fixed SL/TP tick configuration (`thesistester/engine/backtest.py`).  Simple
  triggers enter at next-bar open; filled `confirm_3bar` signals enter at their bar-3
  limit price.  Intrabar ambiguity uses SL-first pessimistic rule.  Trade metrics
  (win rate, expectancy, profit factor, max drawdown R, equity curve) are computed in
  `thesistester/analytics/metrics.py` and displayed on a new **Backtest** page
  (`pages/7_Backtest.py`).  Trades are stored in `st.session_state["trades"]`.
- **Phase 6 (SL/TP grid search, expectancy heatmaps):** sweeps all stop-loss × take-profit
  combinations over the Phase 5 backtest engine (`thesistester/analytics/grid.py`).
  `run_sl_tp_grid()` returns one summary row per cell; `best_grid_result()` picks the
  top-ranked cell by any metric.  A new **Grid Search** page (`pages/8_Grid_Search.py`)
  lets users configure SL/TP ranges and displays four Plotly heatmaps (expectancy R,
  total R, win rate, max drawdown R).  Best result and full grid are stored in
  `st.session_state["best_grid_result"]` and `st.session_state["grid_results"]`.
