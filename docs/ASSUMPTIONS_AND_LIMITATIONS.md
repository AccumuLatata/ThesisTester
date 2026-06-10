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

### 5a) Confirmed pivots are opt-in scalar levels
- Confirmed pivots are disabled by default (`pivots_enabled=False`), so existing level output is unchanged unless the user explicitly enables them.
- Supported pivot timeframe settings remain exactly `1min`, `5min`, `30min`, and `4h`.
- Default fractal settings are `pivot_left=2` and `pivot_right=2`, matching the 5-candle pivot convention.
- Each pivot column holds the latest confirmed pivot high/low for its timeframe; before the first confirmed pivot exists, the value is `NaN`.
- Confirmed pivots are delayed by right-side confirmation and are not real-time swing predictions.
- Confirmed pivots do not encode SFP, liquidity sweep, breaker, reclaim, or retest semantics.

### 5b) Developing session VWAP (`dVWAP_RTH`) is opt-in
- `dVWAP_RTH` is disabled by default (`session_vwap_enabled=False`), so existing level output is unchanged unless explicitly enabled.
- Only `anchor="RTH"` is supported in current implementation (`dVWAP_ETH` is not implemented).
- `dVWAP_RTH` resets at each RTH session open; non-RTH bars always emit `NaN`.
- Zero cumulative RTH volume emits `NaN` (safe divide-by-zero handling).
- If the input DataFrame lacks a `session` column, RTH membership is derived from the instrument configuration and the timestamp timezone.
- `session_vwap_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.

### 5c) TPO 30m Single Prints are opt-in scalar levels
- Single Prints are disabled by default (`single_prints_enabled=False`), so existing level output is unchanged unless explicitly enabled.
- Only RTH 30-minute brackets contribute; ETH bars are completely excluded.
- Only completed 30-minute brackets are used; the current incomplete bracket is always excluded.
- Price bins are sized by instrument `tick_size` from `INSTRUMENTS`.
- A bin is a Single Print if it is touched by exactly one completed bracket within the session.
- Developing Single Prints (`dSinglePrint_30m_NearestAbove/Below`): nearest SP price strictly above/below current bar close, from completed current-session brackets only. NaN on non-RTH bars and before the first bracket completes.
- Prior-session Single Prints (`pSinglePrint_30m_NearestAbove/Below`): nearest SP price strictly above/below close, from the previous completed RTH session's frozen SP set. NaN on non-RTH bars and if the prior session had no Single Prints.
- `single_prints_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.
- No dynamic Single Print columns are generated; only the four scalar columns above.
- **Single Prints and APOC/pAPOC are independent level families.** Single Prints are TPO auction-structure levels; APOC/pAPOC are profile/POC levels. They are computed independently. Passing `apoc_enabled=True` to `compute_tpo_levels` now raises `ValueError` (see 5d).
- Known limitations: no full market-profile object, no volume-at-price, no dynamic list of all Single Print bins.

### 5d) APOC / pAPOC are opt-in profile-based scalar levels (Stage 5)
- `APOC` and `pAPOC` are **profile / POC levels**, not Single Print levels. They are implemented in `thesistester/levels/apoc.py` and are independent of `tpo.py`.
- `APOC` = POC of the first completed RTH 30-minute bracket (the A-period). Not derived from Single Prints; uses profile-style OHLCV approximation.
- `pAPOC` = prior completed RTH session's APOC. Frozen at the start of the new RTH session.
- APOC is disabled by default (`apoc_enabled=False`), so existing level output is unchanged unless explicitly enabled.
- `apoc_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.
- Profile approximation: `typical_price = (high + low + close) / 3`; full bar volume allocated to the tick bin containing `typical_price`. Same approximation as `profile.py`. POC tie-breaking: lowest-price bin wins (bins sorted ascending, `np.argmax` returns first max).
- APOC availability: `NaN` before `RTH_open + 30 min`; emitted from the first bar at or after that timestamp. Non-RTH bars always emit `NaN`.
- pAPOC availability: available from the first RTH bar of each session; frozen throughout. NaN on non-RTH bars and if the prior session produced no valid APOC.
- ETH bars never contribute to APOC computation; only RTH bars in `[RTH_open, RTH_open + 30 min)` are included.
- If the `session` column is absent, RTH membership is derived from the instrument configuration.
- `compute_tpo_levels(..., apoc_enabled=True)` raises `ValueError` with a redirect message. Use `compute_apoc_levels(..., enabled=True)` or `compute_all_levels(..., apoc_enabled=True)` instead.
- `compute_all_levels(..., single_prints_enabled=True, apoc_enabled=True)` produces all six independent columns: four Single Print columns plus `APOC` and `pAPOC`.
- Known limitations: not true volume-at-price (bar-level approximation), not full-session POC, not Single Print-derived, approximation matches `profile.py` MVP.

### 5e) Stage 6 UI and Persistence — opt-in level controls (Levels page)

- The Levels page (`pages/5_Levels.py`) exposes an **"Advanced opt-in levels"** expander below the existing profile settings.
- Inside the expander: checkboxes for confirmed pivots, developing RTH VWAP, TPO 30m Single Prints, and APOC / pAPOC; all default `False`.
- No computation behavior changes when all new controls remain unchecked.
- When pivots are enabled, pivot timeframes (multiselect), pivot left, and pivot right number inputs are shown.
- `session_vwap_anchor` is fixed to `"RTH"` for Stage 6; no new anchors are exposed.
- No Single Print or APOC configuration controls are exposed beyond the enable checkbox.
- APOC / pAPOC remain independent from Single Prints; APOC is not routed through `compute_tpo_levels`.
- `_normalize_levels_settings` adds all eight Stage 6 keys with disabled/default values so old saved snapshots remain compatible without crashing.
- `pivot_timeframes` is sorted deterministically in normalization (same treatment as `sma_timeframes`, `ema_timeframes`, `vwap_windows`, `poc_windows`).
- `_sync_levels_widget_state` restores all four new controls when a saved snapshot is loaded. Old snapshots missing Stage 6 keys load safely and default new controls to disabled.
- Saved level snapshot labels optionally append a compact `Opt-in: pivots,dVWAP,SP,APOC` suffix when one or more opt-in families are enabled.

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
- Confirmed pivots use strict left/right fractal confirmation and are exposed only after
  pivot-candle close plus the full right-side confirmation delay. Higher-timeframe pivot
  values are merged back only after the higher-timeframe candle and confirmation window
  have both completed.
- `dVWAP_RTH` accumulates only RTH bars in the current RTH session using a causal
  cumulative sum. Appending future bars cannot retroactively change any prior bar's
  value. Non-RTH bars always emit `NaN`. Resets at each new RTH session.
- `dSinglePrint_30m_NearestAbove/Below` use only completed 30-minute RTH brackets at
  or before the current bar's timestamp. The current incomplete bracket is excluded.
  ETH bars do not contribute. Non-RTH bars always emit `NaN`. Appending future bars
  cannot alter Single Print values at earlier timestamps.
- `pSinglePrint_30m_NearestAbove/Below` use the prior completed RTH session's frozen
  SP set. Once a session is complete its SP set is immutable. Non-RTH bars always
  emit `NaN`. If the prior session had no Single Prints, columns are `NaN`.
- `APOC` uses only RTH bars in `[RTH_open, RTH_open + 30 min)` of the current session.
  It is `NaN` before `RTH_open + 30 min`. Appending future bars cannot alter APOC at
  earlier timestamps. Non-RTH bars always emit `NaN`.
- `pAPOC` uses the prior completed RTH session's APOC. Once a session's APOC is computed
  it is immutable. Appending future session bars cannot change prior sessions' pAPOC
  values. Non-RTH bars always emit `NaN`.
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
- Confirmed pivots require enough left/right candles to become knowable and expose only
  the latest confirmed scalar levels. Historical pivot-instance columns and higher-order
  classifications (SFP, breaker, reclaim, retest) are not implemented yet.
- `dVWAP_RTH` uses bar-level typical price `(H+L+C)/3`. True intrabar VWAP would
  require tick data. Since signals are treated as bar-close confirmed, this is
  documented intent, not a bug.
- Single Print columns (`dSinglePrint_30m_*`, `pSinglePrint_30m_*`) expose only scalar
  nearest-above/below summaries. A full list of all Single Print bins is not emitted.
  No volume-at-price or full market profile object is available.

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

## Futures roll methodology (R7)
- ThesisTester R7 does **not** synthesize continuous futures prices.
- R7 performs **no OHLC back-adjustment** and does not rewrite uploaded price columns.
- For `external_continuous`, continuity assumptions come from the data provider; ThesisTester only records/exports the declared adjustment method and roll rule.
- For `segmented_contracts`, roll gaps can remain in backtest metrics unless users pre-adjust data externally before upload.
- Declared roll policy and roll-validation diagnostics are exported in research artifacts for auditability.

## Practical interpretation
- With default settings, expectancy remains equivalent to prior gross outputs.
- With non-zero cost settings, expectancy and downstream KPIs become net-of-cost.
- Treat results as **screening diagnostics, not proof of edge**.
