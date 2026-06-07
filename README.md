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

## Anchor confluence workflow

ThesisTester supports two confluence modes:

- **Global cluster:** detects clusters among selected levels using one shared tolerance.
- **Anchor-based rules:** evaluates configured confluence levels around one anchor level using per-rule tolerances.

### Workflow

```text
Data -> Levels -> Setup Builder -> Signals -> Backtest
```

Anchor-based rules are configured in **Setup Builder** and then used on the **Signals** page through **Use saved setup** mode.

### Diagnostics

Anchor-generated zones include diagnostics such as:

- anchor level
- anchor price
- valid confluence count
- per-rule distance in ticks
- per-rule tolerance
- required/optional status
- valid/invalid reason

### Current limitation

Manual controls on the Signals page remain global-cluster only. To use anchor-based rules, create and save a setup in Setup Builder first.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Assumptions & limitations](docs/ASSUMPTIONS_AND_LIMITATIONS.md)
- [Metrics glossary](docs/METRICS_GLOSSARY.md)
- [Agent guide](docs/AGENT_GUIDE.md)

## Phase status

- **Phase 1 (data layer):** CSV OHLCV ingestion, timezone normalization, validation,
  base-interval inference, RTH/ETH session tagging, and OHLCV resampling (1min, 5min,
  15min, 30min, 1h, 4h, 1D).
- **Timezone handling:** the Data page includes a source timestamp timezone selector.
  Timezone-naive CSV timestamps are localized to the selected source timezone and
  converted to the instrument exchange timezone (`America/New_York` for ES/NQ).
  Timezone-aware timestamps are converted from their embedded timezone automatically.
- **Phase 2 (session/structural levels):** session level engine for opens, prior O/H/L/EQ,
  overnight and opening-range levels, RTH open, and previous settlement preview via the
  new Streamlit **Levels** page.
- **Phase 3 (indicator/profile levels):** SMA/EMA and rolling VWAP levels, rolling POC
  windows, and prior day/week/month profile levels (`VAH/VAL/POC`) with 70% value area
  and tick-bucketed ES/NQ volume bins.
- **Phase 4 (confluence detection, naked levels, signal generation):** tick-based
  confluence zone detection (`detect_confluence_zones`), naked/untested level flags
  (`flag_naked_levels`), and five trigger types — `touch`, `reject`, `break`, `reclaim`,
  `3c` — exposed via a new **Signals** page (`pages/6_Signals.py`). Trigger timeframe
  (`base`, `1min`, `5min`, `15min`) applies to all triggers including `3c`, defaulting
  to `base` for backward compatibility. For non-base triggers, `bar_index`/`timestamp`
  remain aligned to the canonical/base bar at trigger-candle end, while `trigger_timestamp`
  stores the trigger-candle completion/actionable time.
  For `3c` with non-base trigger timeframe, arrival, inside/muted candles, SFP tagging, and
  reversal confirmation are evaluated on trigger-timeframe candles; retrace entry fill is
  evaluated on canonical/base bars after reversal trigger candle completion;
  `max_entry_wait_bars_after_reversal` counts trigger-timeframe bars, not base bars.
  Candidate signals are stored in `st.session_state["signals"]` for Phase 5 backtesting.
- **Phase 5 (backtest engine, KPIs, results):** bar-by-bar trade simulation with a
  single fixed SL/TP tick configuration (`thesistester/engine/backtest.py`).  Simple
  triggers enter at next-bar open; filled `3c` signals enter at their retracement
  trigger price.  Intrabar ambiguity uses SL-first pessimistic rule.  Trade metrics
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
- **Phase 6.5 (workflow cleanup):** **Setup Builder** (`pages/2_Setup_Builder.py`) is now
  functional and saves reusable setup configs in-session via
  `st.session_state["setup_config"]` (and `st.session_state["setup_configs"]` for session
  history).  **Signals** (`pages/6_Signals.py`) can consume the saved setup via
  a `Use saved setup` toggle while still supporting manual configuration.
- **3c trigger — authoritative 4-rule / 8-variant model:**

  The `3c` trigger implements a 3-candle entry sequence with 8 named variants:
  `3c_long`, `3c_short`, `3c_long_muted`, `3c_short_muted`, `3c_sfp_long`,
  `3c_sfp_short`, `3c_sfp_long_muted`, `3c_sfp_short_muted`.

  **4 rules (long):**
  1. Arrival candle must touch or pass through the key level.
  2. Arrival candle must close above the key level.
  3. Reversal candle must close above the arrival candle high.
  4. Entry candle must retrace at least `entry_retrace_ticks`; once retraced, trigger
     market long.

  **Short rules** are the mirror image (touch from above, close below, reversal close
  below arrival low, retrace up).

  **Muted variant:** if the candle immediately after the arrival candle is an inside
  candle (relative to the arrival candle range), it is skipped; the following candle
  that breaks out and closes beyond the relevant arrival extreme becomes the reversal
  candle.  Multiple consecutive inside candles are all skipped.

  **SFP variant:** long SFP — reversal candle low takes out the arrival candle low;
  short SFP — reversal candle high takes out the arrival candle high.

  **User-configurable parameters:** `entry_retrace_ticks` (default 4),
  `max_entry_wait_bars_after_reversal` (default 5).

  **Trigger timeframe:** `3c` supports all trigger timeframes (`base`, `1min`, `5min`,
  `15min`).  For non-base timeframes, arrival/muted/SFP/reversal are evaluated on the
  selected trigger candles; retrace fill is monitored on canonical/base bars after reversal
  candle completion; wait-window bars count trigger-timeframe bars.  Backtest entry uses
  base-indexed `entry_bar_index` and `retrace_entry_price`, so backtest execution is
  unchanged.

  **`arrival_tolerance_ticks` is deprecated** and is no longer user-configurable.
  Arrival must actually touch the key level (strict, zero tolerance).  Old saved
  configs that contain `arrival_tolerance_ticks` are still loaded without error, but
  the value is ignored — effective tolerance is always zero.
- **Phase 7 (time-of-day/session-window analysis):** completed trades can now be grouped by
  RTH segment, hourly and 30-minute buckets, trigger, direction, setup name, and exit reason.
  The new **Time Analysis** page (`pages/9_Time_Analysis.py`) displays grouped KPIs,
  low-sample warnings, bar charts, heatmaps, and raw bucketed trades. Outputs are stored in
  `st.session_state["time_bucketed_trades"]` and `st.session_state["time_grouped_summary"]`.
- **Phase 8 (statistical validation):** robustness diagnostics for completed backtest results.
  Implements a bootstrap expectancy confidence interval (`bootstrap_expectancy_ci`), a
  sign-flip permutation test for positive expectancy (`permutation_test_expectancy`),
  trade-count adequacy assessment (`trade_count_diagnostics`), and a heuristic grid-search
  overfit warning (`grid_overfit_diagnostics`).  All diagnostics are combined by
  `validation_summary` in `thesistester/analytics/validation.py`.  The new **Validation**
  page (`pages/10_Validation.py`) requires completed trades, optionally uses grid results,
  displays bootstrap and permutation histograms, and stores results in
  `st.session_state["validation_summary"]`.  ⚠️ All outputs are diagnostic only — not proof
  of edge.
- **Phase 9 (report/export + reproducibility):** adds a new **Report / Export** page
  (`pages/11_Report_Export.py`) backed by `thesistester/reporting.py`. Users can export a
  consolidated `research_artifact.json`, a readable `research_report.md`, and CSV downloads
  for key result tables (`signals`, `trades`, `equity_curve`, `grid_results`,
  `time_grouped_summary`). Artifacts are built directly from current `st.session_state`
  without recomputing backtests, exclude full raw `data`/`levels` by default to avoid huge
  files, and include reproducibility caveats emphasizing research-only usage.
