# Point-in-Time Guarantees

## Definition

A computation is **point-in-time correct** (causal) when, for every output value
emitted at timestamp `T` (or bar index `i`), only data from bars at or before `T`
was used to produce that value. No information from bars after `T` may influence
any output visible at `T`.

This document covers the audit performed under R3 (June 2026). It is specific to the
codebase state at the time of the R3 milestone. See `docs/ENGINEERING_ROADMAP.md` for
the milestone definition. Claims of causality should not be extended beyond what is
tested here.

---

## Audited modules

| Module | Purpose |
|---|---|
| `thesistester/levels/sessions.py` | Session/structural levels (pdHigh, ONH, OR, …) |
| `thesistester/levels/profile.py` | Rolling POC and prior day/week/month profile levels |
| `thesistester/levels/indicators.py` | SMA, EMA, rolling VWAP |
| `thesistester/engine/naked.py` | Naked/untested level flags |
| `thesistester/engine/confluence.py` | Global confluence zone detection |
| `thesistester/engine/anchor_confluence.py` | Anchor-based confluence detection |
| `thesistester/engine/signals.py` | Signal generation (touch/reject/break/reclaim/3c/confirm_3bar) |
| `thesistester/engine/signals_3c.py` | 3c setup detector (base and non-base timeframes) |

---

## Level and signal family audit table

### Session levels — `levels/sessions.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `pdHigh/pdLow/pdOpen/pdEQ` | `_period_levels` with `session_date` key | **Yes** | First bar of the new trading day (via `shift(1)` on per-day aggregate) | None | `test_r3_point_in_time.py::test_prior_session_levels_future_shock` |
| `pwHigh/pwLow/pwOpen/pwEQ` | `_period_levels` with `week_key` | **Yes** | First bar of the new week | None | Same |
| `pmHigh/pmLow/pmOpen/pmEQ` | `_period_levels` with `month_key` | **Yes** | First bar of the new month | None | Same |
| `dOpen/wOpen/mOpen` | `_current_opens` via `transform("first")` | **Yes** | Available from the very first bar of the current period | These reflect the current (incomplete) period open, not a "prior" level | — |
| `RTH_Open` | `_rth_open` | **Yes** | Gated by `df["timestamp"] >= first_rth_ts`; NaN until the first RTH bar arrives | None | `test_r3_point_in_time.py::test_rth_open_not_visible_before_rth` |
| `ONH / ONL` | `_overnight_high_low` | **Yes** | Gated by the first RTH bar timestamp; NaN during ETH | Overnight is computed across all ETH bars of the session; ONH/ONL is the completed overnight high/low, gated until RTH begins | `test_r3_point_in_time.py::test_overnight_levels_gated` |
| `pONH / pONL / pRTH_Open` | `_previous_session_references` | **Yes** | All bars in the day, via `shift(1)` on per-session aggregates | None | — |
| `OR_High / OR_Low` | `_opening_range` | **Yes** | Gated by clock time: `start_minute + opening_range_minutes` after session midnight in exchange timezone | OR availability depends on the clock gate, not on whether OR bars exist | `test_r3_point_in_time.py::test_opening_range_not_visible_before_or_end` |
| `prevSettlement` | `_prev_settlement` | **Yes** | First bar of the new day, via `shift(1)` | Falls back to prior-day final close when no `settlement` column present | — |

### Prior profile levels — `levels/profile.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `pdVAH / pdVAL / pdPOC` | `_map_prior_profile_levels(day_key)` | **Yes** | First bar of the new trading day | Profile for the current incomplete day is never used as "prior"; `shift(1)` ensures bars on day D receive day D-1's complete profile | `test_r3_point_in_time.py::test_prior_day_profile_future_shock` |
| `pwVAH / pwVAL / pwPOC` | `_map_prior_profile_levels(week_key)` | **Yes** | First bar of the new week | Same shift guarantee; incomplete current week is never the prior | `test_r3_point_in_time.py::test_prior_week_profile_future_shock` |
| `pmVAH / pmVAL / pmPOC` | `_map_prior_profile_levels(month_key)` | **Yes** | First bar of the new month | Same | — |
| `POC_rolling_*` | `_rolling_poc` | **Yes** | Each bar uses `timestamps <= now` strictly | O(N²) MVP implementation; bars near the window boundary use only the bars in `(now - window, now]` | `test_r3_point_in_time.py::test_rolling_poc_future_shock` |

### Rolling indicators — `levels/indicators.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `SMA_N` (base timeframe) | `rolling(N).mean()` on close | **Yes** | Bar `N-1` onwards (min_periods=N) | SMA at bar `i` includes bar `i` close; if signals trigger intrabar, this is close-known | `test_r3_point_in_time.py::test_rolling_indicators_future_shock` |
| `EMA_N` (base timeframe) | `ewm(span=N).mean()` on close | **Yes** | Bar `N-1` onwards | Same bar-close note as SMA | Same |
| `SMA_N_TF` / `EMA_N_TF` (higher TF) | `_append_timeframe_levels` with `align_timestamp = bar_open + TF_delta` | **Yes** | After the higher-TF candle *completes* (not at its open) | Level is exposed at `merge_asof(direction="backward")` only once `align_timestamp ≤ base_timestamp` | `test_phase3_levels.py::test_higher_timeframe_indicator_alignment_has_no_lookahead` |
| `VWAP_rolling_*` | `rolling(window).sum(pv) / rolling(window).sum(vol)` | **Yes** | Each bar uses only the time-indexed rolling window up to and including the current bar | Bar-level typical-price approximation; true intrabar VWAP would require tick data | `test_r3_point_in_time.py::test_rolling_indicators_future_shock` |

### Naked levels — `engine/naked.py`

| Component | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `<level>_naked` flags | `flag_naked_levels` — pure forward scan from index 0 | **Yes** | Same bar as formation detection; cleared on the touching bar | Formation is detected when the level value first appears or changes; the formation bar itself is never tested | `test_r3_point_in_time.py::test_naked_flags_future_shock` |

**Important:** `flag_naked_levels` is a forward-only iterative algorithm. Naked
status at bar `i` depends only on bars `0..i`. Appending future bars cannot
retroactively clear the naked flag of any prior bar.

Signal generation uses naked status at the **arrival bar index** (not at any later
bar), so naked filtering in signals is point-in-time correct.

### Confluence zones — `engine/confluence.py` and `engine/anchor_confluence.py`

| Component | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| Global confluence zones | `detect_confluence_zones` — per-bar, uses level values at that bar only | **Yes** | Same bar as the input levels | Causality depends on the underlying level columns being causal; if a non-causal level column is passed, zones inherit the problem | `test_r3_point_in_time.py::test_confluence_zones_future_shock` |
| Anchor confluence zones | `detect_anchor_confluence_zones` — per-bar | **Yes** | Same bar | Same dependency note | `test_r3_point_in_time.py::test_anchor_confluence_future_shock` |

### Signals — `engine/signals.py` / `engine/signals_3c.py`

| Trigger | Source | Causal? | Timestamp semantics | Known limitations | Tests |
|---|---|---|---|---|---|
| `touch` | `_check_touch` | **Yes** | Signal at trigger-bar close | Next-bar execution is assumed by `entry_model="candidate_next_bar_open"` | `test_r3_point_in_time.py::test_signals_touch_future_shock` |
| `reject` | `_check_reject` | **Yes** | Signal at trigger-bar close | Same | Same |
| `break` | `_check_break` | **Yes** | Signal at trigger-bar close; uses `prev` bar to confirm breakout | Same | Same |
| `reclaim` | `_check_reclaim` | **Yes** | Signal at trigger-bar close | Same | Same |
| `confirm_3bar` | `_check_confirm_3bar` | **Yes** | Signal timestamped at **bar 3** (`bar3_idx`), not backdated to arrival bar | Entry is bar3 OHLC intrabar fill (pessimistic SL-first); bar3 is both signal bar and entry bar | `test_r3_point_in_time.py::test_confirm_3bar_not_backdated` |
| `3c` (base TF) | `detect_3c_setups` | **Yes** | Signal at `entry_idx` (filled) or `reversal_idx` (void); never backdated to arrival | Looks forward only to find reversal and retrace within allowed window | `test_r3_point_in_time.py::test_3c_signals_not_backdated` |
| `3c` (non-base TF) | `detect_3c_setups_with_trigger_timeframe` | **Yes** | `bar_index` / `timestamp` are canonical/base indexed at entry or reversal bar | `trigger_arrival_bar_index` / `trigger_reversal_bar_index` are trigger-TF indices; `trigger_timestamp` is reversal candle completion | Same |

---

## Same-bar vs next-bar semantics

For **simple triggers** (`touch`, `reject`, `break`, `reclaim`):

- The signal is generated when the trigger bar **closes** (bar `i`).
- `bar_index = i`, `timestamp = bar i timestamp`.
- `entry_model = "candidate_next_bar_open"`: execution is intended at bar `i+1` open.
- The trigger bar's close is known at bar close time; no future data is required.
- Same-bar close is used as `entry_reference_price`, not as an actual fill price; backtest
  entry is bar `i+1`.

For **`confirm_3bar`**:

- Arrival at bar 1, reversal condition checked at bar 2, fill condition checked intrabar
  at bar 3.
- Signal emitted at bar 3 (`bar_idx = bar3_idx`).
- `entry_model = "bar3_stop_limit_fill"` or `"bar3_stop_limit_void"`.
- Bar 3 entry uses bar 3 OHLC with pessimistic SL-first intrabar handling.
- This is a **same-bar intrabar fill assumption**, consistent with the engine-wide SL-first
  pessimism documented in `ASSUMPTIONS_AND_LIMITATIONS.md`.

For **`3c`**:

- Arrival bar is bar 1 of the 3c sequence.
- Reversal bar is bar 2 (or later, after inside candles).
- Entry fill is the first bar after reversal where price retraces to `entry_trigger_price`.
- `bar_index = entry_idx` (filled) or `reversal_idx` (void).
- The signal is **never backdated** to the arrival bar.

---

## Naked-level handling

`flag_naked_levels` is a causal forward scan. Naked status at bar `i` is determined
solely by bars `0..i`. Future touches cannot retroactively change a bar's naked status.

Signal generation evaluates naked metadata at the **arrival bar index**, not at a later
bar. This ensures naked filtering in signals is causal.

**Warning:** Do not use the final `_naked` column output as if it reflected the naked
status at an arbitrary historical timestamp. The column is point-in-time safe only
because the forward scan produces the same value at each bar regardless of what comes
after. If you need "was this level naked on date D?", use the column value at the last
bar on date D; do not use the final row value.

---

## Unresolved limitations

1. **Bar-level volume-at-price approximation.** Prior profile levels use bar typical
   price `(H+L+C)/3` with full bar volume allocated to one bin. This is an MVP
   approximation. True intrabar volume-at-price data would produce different VAH/VAL/POC
   values but would not introduce look-ahead bias by itself.

2. **ONH/ONL not available during ETH.** Overnight high/low is NaN for all ETH bars
   and becomes available only at RTH open. If a strategy requires knowing the running
   overnight high/low during ETH, it must be computed separately with a streaming/
   cumulative approach. The current gating is intentional and conservative.

3. **`dOpen/wOpen/mOpen` reflect current-period opens.** These are current-session
   (incomplete) opens, not prior-period opens. They are available from the first bar
   of the session but represent a live level, not a historical reference. Do not confuse
   them with `pdOpen/pwOpen/pmOpen` (prior-period opens).

4. **`confirm_3bar` uses intrabar bar-3 fill.** The 3-bar sequence fill at bar 3 is
   assumed from bar-3 OHLC. This is an intrabar-fill assumption, not a next-bar-open
   assumption. Results are pessimistic (SL-first) but are not independently verified
   against tick data.

5. **Rolling VWAP / POC at bar `i` include bar `i` close/volume.** If signals trigger
   intrabar and use same-bar rolling levels, there is a mild look-ahead within the bar
   (close is not known until bar end). The current design treats signals as bar-close
   confirmed, so this is documented intent, not a bug. See assumption 5 in
   `ASSUMPTIONS_AND_LIMITATIONS.md`.
