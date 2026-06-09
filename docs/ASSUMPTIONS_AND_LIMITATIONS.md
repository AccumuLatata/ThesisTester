# ASSUMPTIONS AND LIMITATIONS

This engine is for **research screening**, not proof of a durable edge.

## Verified engine assumptions (current implementation)

### 1) P&L is net-of-cost when costs are supplied; gross by default
- `simulate_trades(...)` accepts optional `commission_per_side` (default `0.0`) and `slippage_ticks` (default `0.0`) parameters (`thesistester/engine/backtest.py:88-90`).
- With both parameters at their defaults the engine reproduces the prior gross-only behavior exactly.
- When non-zero costs are supplied, `pnl_currency` and `r_multiple` reflect **net-of-cost** results.  `gross_pnl_currency` and `gross_pnl_points` remain available for reference (`thesistester/engine/backtest.py:317-325`).
- Adverse slippage is applied to both entry and exit: long entries fill higher; long exits fill lower (and vice versa for shorts).  SL/TP levels are anchored to the slipped entry price for internal consistency.
- Commission is a flat currency cost per side; round-trip cost = `2 × commission_per_side`.
- **Warning:** using unrealistically low cost assumptions (e.g., zero slippage during volatile opens) will overstate net expectancy.

### 2) Intrabar ambiguity is resolved with SL-first pessimism
- If both stop and target are reachable in one bar, the engine exits at stop (`thesistester/engine/backtest.py:221-226`).
- This behavior is explicitly documented in module notes (`thesistester/engine/backtest.py:12-14`).

### 3) TIME and EOD exits are bar-index based
- `max_holding_bars` is implemented as a bar-count cap (`entry_bar_index + max_holding_bars - 1`) (`thesistester/engine/backtest.py:194-196`).
- TIME exit uses that capped bar’s close (`thesistester/engine/backtest.py:240-243`).
- If no SL/TP/TIME exit triggers, `EOD` is the **final bar in the loaded dataset** (`thesistester/engine/backtest.py:245-247`), not a session close event.

### 4) Signals are simulated independently (no overlap/exposure control)
- The simulator loops each signal row independently (`for _, sig in signals.iterrows()`) and appends one trade result per signal (`thesistester/engine/backtest.py:137-140`, `264-301`).
- There is no portfolio state, position netting, capital constraint, or overlap gate in this loop.

### 5) Simple-trigger and `3c` timestamp semantics are canonical/base aligned
- For all triggers, emitted `timestamp` is always the canonical/base dataframe timestamp at `bar_index`.
- When `trigger_timeframe` is non-base, trigger evaluation is performed on resampled trigger candles, and `trigger_timestamp` stores trigger-candle completion/actionability time.
- Backtest entry for simple triggers (`touch`, `reject`, `break`, `reclaim`) remains `bar_index + 1` on the canonical/base dataframe (first base bar after trigger-candle completion).
- For `3c` with non-base trigger timeframe: arrival, inside/muted candles, SFP tagging, and reversal confirmation are evaluated on trigger-timeframe candles. The retrace entry fill is evaluated on canonical/base bars after the reversal trigger candle is complete. `max_entry_wait_bars_after_reversal` counts trigger-timeframe bars, not base bars. Backtest execution remains unchanged because `3c` emits base-indexed `entry_bar_index` and `retrace_entry_price`.
- `arrival_bar_index`, `reversal_bar_index`, `entry_bar_index`, and `bar_index` are canonical/base indices. `trigger_arrival_bar_index`, `trigger_reversal_bar_index`, and `trigger_bar_index` are trigger-timeframe indices. `trigger_timestamp` is the reversal trigger candle completion timestamp.

## Validation implications
- Validation diagnostics explicitly warn that assumptions like sign symmetry and independence limits apply; serial dependence is ignored (`thesistester/analytics/validation.py:10-11`, `115-117`).
- Outputs are explicitly framed as diagnostics and not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`).

## Practical interpretation
- **Expectancy is gross when default zero-cost parameters are used.** Supply `commission_per_side` and `slippage_ticks` to get net expectancy.
- Treat results as **screening diagnostics, not proof of edge**.
