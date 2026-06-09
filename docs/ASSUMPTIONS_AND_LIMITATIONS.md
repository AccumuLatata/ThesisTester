# ASSUMPTIONS AND LIMITATIONS

This engine is for **research screening**, not proof of a durable edge.

## Verified engine assumptions (current implementation)

### 1) Execution costs are optional; zero-cost is the default
- `simulate_trades(...)` now accepts optional `commission_per_side` and `slippage_ticks` inputs (`thesistester/engine/backtest.py`).
- Defaults are `commission_per_side=0.0` and `slippage_ticks=0.0`, which reproduce legacy gross behavior.
- With non-zero costs, `pnl_currency` and `r_multiple` are **net-of-cost** (commission/slippage applied), while gross fields remain available (`gross_pnl_*`, `net_pnl_currency`, `commission_cost`, `slippage_cost`).
- Report/export artifacts track execution-cost assumptions **separately** for backtest and grid sections, and only when corresponding result data is present in the current export.
- Backtest and grid outputs are directly comparable only when they were produced under the same execution-cost assumptions.
- Unrealistic cost assumptions can still overstate edge; research results should be interpreted with conservative cost settings.

### 2) Intrabar ambiguity is resolved with SL-first pessimism
- If both stop and target are reachable in one bar, the engine exits at stop. Implemented in `simulate_trades()` in `thesistester/engine/backtest.py`.
- This behavior is explicitly documented in the module design notes in `thesistester/engine/backtest.py`.

### 3) TIME, SESSION_CLOSE, DATA_END, and EOD exits are bar-index based
- `max_holding_bars` is implemented as a bar-count cap (`entry_bar_index + max_holding_bars - 1`) in `simulate_trades()` in `thesistester/engine/backtest.py`.
- TIME exit uses that capped bar’s close in `simulate_trades()` in `thesistester/engine/backtest.py`.
- Default mode keeps legacy behavior: if no SL/TP/TIME exit triggers, `EOD` is the **final bar in the loaded dataset**, not a session close event.
- Optional session-aware mode (`flat_by_session_close=True`) caps exits to the configured session close for each trade entry date:
  - `SESSION_CLOSE` means forced flat at the last available bar at or before the configured close time (when SL/TP is not hit first).
  - `DATA_END` means data ended before session close and the trade was force-closed at the last available bar.
- Current session-aware flattening is intended for same-calendar-day RTH-style sessions; overnight ETH session templates are not yet modeled.
- If session-aware mode is not enabled, users can still unintentionally model overnight holds across sessions.

### 4) Exposure policy is explicit and configurable
- `simulate_trades(...)` supports `exposure_policy` with:
  - `allow_all` (default, legacy behavior),
  - `single_position`,
  - `single_direction`,
  - `single_setup`.
- Default remains `allow_all` for backward compatibility and broad signal screening.
- `allow_all` can inflate trade counts because overlapping signals are treated independently.
- Restrictive policies apply deterministic admission ordering and optional cooldown (`cooldown_bars_after_exit`) to model more conservative trade lifecycle assumptions.
- Optional skipped-signal diagnostics contain exposure-policy rejections only; signals skipped for pre-existing non-executable reasons (e.g., void `3c`, missing future entry bar) are not included in skipped diagnostics.

### 5) Simple-trigger and `3c` timestamp semantics are canonical/base aligned
- For all triggers, emitted `timestamp` is always the canonical/base dataframe timestamp at `bar_index`.
- When `trigger_timeframe` is non-base, trigger evaluation is performed on resampled trigger candles, and `trigger_timestamp` stores trigger-candle completion/actionability time.
- Backtest entry for simple triggers (`touch`, `reject`, `break`, `reclaim`) remains `bar_index + 1` on the canonical/base dataframe (first base bar after trigger-candle completion).
- For `3c` with non-base trigger timeframe: arrival, inside/muted candles, SFP tagging, and reversal confirmation are evaluated on trigger-timeframe candles. The retrace entry fill is evaluated on canonical/base bars after the reversal trigger candle is complete. `max_entry_wait_bars_after_reversal` counts trigger-timeframe bars, not base bars. Backtest execution remains unchanged because `3c` emits base-indexed `entry_bar_index` and `retrace_entry_price`.
- `arrival_bar_index`, `reversal_bar_index`, `entry_bar_index`, and `bar_index` are canonical/base indices. `trigger_arrival_bar_index`, `trigger_reversal_bar_index`, and `trigger_bar_index` are trigger-timeframe indices. `trigger_timestamp` is the reversal trigger candle completion timestamp.

## 6) Point-in-time correctness (R3 audit)

A full audit of all level, confluence, and signal modules was completed under R3. The
findings are recorded in `docs/POINT_IN_TIME_GUARANTEES.md`.

**Parts that are point-in-time guaranteed:**
- All prior-period session levels (pdHigh/pdLow/pdOpen/pdEQ, pwHigh/pwLow/pwOpen/pwEQ,
  pmHigh/pmLow/pmOpen/pmEQ) use a `shift(1)` on per-period aggregates. Future bars
  cannot change any prior bar's "prior" level values.
- Prior profile levels (pdVAH/pdVAL/pdPOC, pwVAH/pwVAL/pwPOC, pmVAH/pmVAL/pmPOC)
  use the same shift guarantee.
- Rolling POC uses a strict `timestamps <= now` window. No future data enters.
- Rolling indicators (SMA/EMA/VWAP) on the base timeframe use only bars up to and
  including the current bar. Higher-timeframe indicators use `align_timestamp` gating
  so values are visible only after candle completion.
- RTH_Open and ONH/ONL are NaN until the first RTH bar of the session; no future RTH
  or overnight data can change ETH-bar values.
- Opening range (OR_High/OR_Low) is NaN until the clock-based OR window closes.
- Naked (`<level>_naked`) flags are produced by a pure forward scan; future bars cannot
  retroactively clear a prior bar's naked status.
- Confluence zones (global and anchor) operate on level values already in the
  DataFrame at each bar; causality inherits from the underlying level columns.
- All signal triggers (`touch`, `reject`, `break`, `reclaim`, `3c`) emit signals
  at the bar where the setup becomes knowable, never backdated to the arrival bar.

**Remaining limitations (see full detail in `docs/POINT_IN_TIME_GUARANTEES.md`):**
- Profile levels use a bar-level typical-price approximation. True intrabar
  volume-at-price data would change level values but would not introduce look-ahead.
- ONH/ONL is not available during ETH (by design; the overnight has not yet closed).
- Rolling VWAP/POC/SMA/EMA at bar `i` include bar `i` close/volume. Signals treated
  as bar-close confirmed; this is documented intent, not a bug.
- `dOpen/wOpen/mOpen` are current-period (live) opens, not prior-period references.
  Do not confuse them with `pdOpen/pwOpen/pmOpen`.

**Warning against non-causal diagnostic use:**
The `<level>_naked` columns are causal (each bar's value is determined by bars up to
that bar only). However, if you inspect the final naked column in an exported table and
read it as "this level is currently naked", you are reading a point-in-time snapshot at
the last data bar, not a historical snapshot at an arbitrary earlier date. Do not
interpret a diagnostic table's final naked status as a tradable signal for any bar
other than the last bar in the dataset.

## Validation implications
- Validation diagnostics explicitly warn that assumptions like sign symmetry and independence limits apply; serial dependence is ignored (`thesistester/analytics/validation.py:10-11`, `115-117`).
- Outputs are explicitly framed as diagnostics and not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`).
- Walk-forward / out-of-sample diagnostics are also descriptive only, not proof of edge.
- Current walk-forward splits use deterministic bar-index windows and are not calendar/session-aware.
- Train-window SL/TP selection can still overfit when grids are large or fold count is small.
- Each fold's test window is out-of-sample relative to that fold's train window only.
- Advanced trade metrics are trade-sequence diagnostics on realized `r_multiple`, not annualized portfolio statistics.
- Tail, percentile, skew, kurtosis, and outlier-dependency metrics are sensitive to sample size and can be unstable on small trade sets.
- Ulcer index, drawdown, and streak metrics describe the realized trade ordering that occurred in the backtest; they are not guarantees of future path smoothness.

## Practical interpretation
- With default settings, expectancy remains equivalent to prior gross outputs.
- With non-zero cost settings, expectancy and downstream KPIs become net-of-cost.
- Treat results as **screening diagnostics, not proof of edge**.
