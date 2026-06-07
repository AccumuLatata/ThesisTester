# ASSUMPTIONS AND LIMITATIONS

This engine is for **research screening**, not proof of a durable edge.

## Verified engine assumptions (current implementation)

### 1) P&L is gross (no commissions, fees, or slippage)
- `simulate_trades(...)` accepts `tick_size`, `point_value`, SL/TP, and timing flags, but no cost/slippage parameters (`thesistester/engine/backtest.py:73-82`).
- Currency P&L is computed directly as `pnl_points * point_value` (`thesistester/engine/backtest.py:254-260`).
- Therefore all reported performance/expectancy is **gross**.

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

### 5) Simple-trigger timestamp semantics are canonical/base aligned
- For simple triggers (`touch`, `reject`, `break`, `reclaim`), emitted `timestamp` is always the canonical/base dataframe timestamp at `bar_index`.
- When `trigger_timeframe` is non-base, trigger evaluation is performed on resampled trigger candles, and `trigger_timestamp` stores trigger-candle completion/actionability time.
- Backtest entry for simple triggers remains `bar_index + 1` on the canonical/base dataframe (first base bar after trigger-candle completion).
- `3c` remains base/current-timeframe only until dedicated multi-timeframe `3c` support is implemented.

## Validation implications
- Validation diagnostics explicitly warn that assumptions like sign symmetry and independence limits apply; serial dependence is ignored (`thesistester/analytics/validation.py:10-11`, `115-117`).
- Outputs are explicitly framed as diagnostics and not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`).

## Practical interpretation
- **Expectancy is gross expectancy** (costs/slippage excluded).
- Treat results as **screening diagnostics, not proof of edge**.
