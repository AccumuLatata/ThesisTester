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
| `thesistester/levels/pivots.py` | Confirmed 1min / 5min / 30min / 4h pivot levels |
| `thesistester/levels/session_vwap.py` | Developing session VWAPs (`dVWAP_RTH`, `dVWAP`, `wVWAP`, `mVWAP`) |
| `thesistester/levels/tpo.py` | TPO 30m Single Print scalar levels |
| `thesistester/levels/apoc.py` | A-Period POC scalar levels (`APOC`, `pAPOC`) |
| `thesistester/levels/prev30m_vwap.py` | Previous 30m VWAP (`prev30mVWAP` + Phase 3 stack) + early-window hit diagnostics |
| `thesistester/engine/naked.py` | Naked/untested level flags |
| `thesistester/engine/confluence.py` | Global confluence zone detection |
| `thesistester/engine/anchor_confluence.py` | Anchor-based confluence detection |
| `thesistester/engine/signals.py` | Signal generation (public: touch/reject/break/reclaim/3c; legacy/internal helper: confirm_3bar) |
| `thesistester/engine/signals_3c.py` | 3c setup detector (base and non-base timeframes) |

---

## Level and signal family audit table

Rows with `—` in the Tests column were verified by code inspection rather than by a
dedicated future-shock regression test. Overall, audited behavior here is verified by
future-shock tests and/or code inspection.

### Session levels — `levels/sessions.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `pdHigh/pdLow/pdOpen/pdEQ` | `_period_levels` with `session_date` key | **Yes** | First bar of the new trading day (via `shift(1)` on per-day aggregate) | None | `test_r3_point_in_time.py::test_prior_session_levels_future_shock` |
| `pwHigh/pwLow/pwOpen/pwEQ` | `_period_levels` with `week_key` | **Yes** | First bar of the new week | None | Same |
| `pmHigh/pmLow/pmOpen/pmEQ` | `_period_levels` with `month_key` | **Yes** | First bar of the new month | None | Same |
| `dOpen/wOpen/mOpen` | `_current_opens` via `transform("first")` | **Yes** | Available from the very first bar of the current period | These reflect the current (incomplete) period open, not a "prior" level | — |
| `RTH_Open` | `_rth_open` | **Yes** | Gated by `df["timestamp"] >= first_rth_ts`; NaN until the first RTH bar arrives | None | `test_r3_point_in_time.py::test_rth_open_not_visible_before_rth` |
| `ONH / ONL` | `_overnight_high_low` | **Yes** | Gated by the first RTH bar timestamp; NaN during ETH | Overnight is computed across all ETH bars of the session; ONH/ONL is the completed overnight high/low, gated until RTH begins | `test_r3_point_in_time.py::test_overnight_levels_gated` |
| `AsiaHigh / AsiaLow` | `_asia_high_low` → `_session_window_high_low` | **Yes** | Gated by clock time at Asia close (`asia_end` on the Asia session key date); NaN during the Asia window | Default window `20:00–00:00` ET (instrument `asia_start`/`asia_end`); ETH bars only; not rolling; distinct from ONH/ONL. Empty `asia_start`/`asia_end` → all-NaN. Empty `eth_start` remaps evening bars onto the next calendar day (ONH-style). Wrapping Asia requires `asia_end < eth_start <= asia_start` (or empty `eth_start`) | `tests/test_session_levels.py` Asia suite + `test_r3_point_in_time.py::test_asia_levels_gated_until_close` |
| `LondonHigh / LondonLow` | `_london_high_low` → `_session_window_high_low` | **Yes** | Gated by clock time at London close (`london_end` on the session key date); NaN during the London window | Default window `02:00–05:00` ET (instrument `london_start`/`london_end`); ETH bars only; not rolling; distinct from Asia and ONH/ONL. Empty `london_start`/`london_end` → all-NaN. Non-wrapping London requires `eth_start > london_end` (or empty `eth_start`); `eth_start <= london_end` fails closed | `tests/test_session_levels.py` London suite + `test_r3_point_in_time.py::test_london_levels_gated_until_close` |
| `pONH / pONL / pRTH_Open / pRTH_High / pRTH_Low` | `_previous_session_references` | **Yes** | All bars of the next session, via `shift(1)` on per-session aggregates | `pRTH_High`/`pRTH_Low` use RTH bars only (≠ `pdHigh`/`pdLow`); NaN when prior session has no RTH | `tests/test_session_levels.py` previous-session suite + `test_r3_point_in_time.py::test_prth_high_low_future_shock` |
| `OR_High / OR_Low` | `_opening_range` | **Yes** | Gated by clock time: `start_minute + opening_range_minutes` after session midnight in exchange timezone | OR availability depends on the clock gate, not on whether OR bars exist | `test_r3_point_in_time.py::test_opening_range_not_visible_before_or_end` |
| `prevSettlement` | `_prev_settlement` | **Yes** | First bar of the new day, via `shift(1)` | Falls back to prior-day final close when no `settlement` column present | — |

### Prior profile levels — `levels/profile.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `pdVAH / pdVAL / pdPOC` | `map_shifted_prior_profile` on tick `PriorProfileTable` (day keys) | **Yes** | First bar of the new trading session when a tick table is present; **columns absent** without ticks | Tick Last×Volume VAP, 70% expander; `shift(1)` is on 1m unique session keys (not table-present rows). Session T+1 looks up session T in the table (`NaN` if that session has no ticks). Current incomplete session is never the prior. 1m truncation does not recompute VA | `test_r3_point_in_time.py::test_prior_day_profile_future_shock`, `tests/test_tick_vap_cutover.py` |
| `pwVAH / pwVAL / pwPOC` | `map_shifted_prior_profile` (week keys `W-SUN`) | **Yes** | First bar of the new trading week when a tick table is present; **columns absent** without ticks | Same shift guarantee; week histogram is merged day histograms, not a second tick pass | `test_r3_point_in_time.py::test_prior_week_profile_future_shock` |
| `pmVAH / pmVAL / pmPOC` | `map_shifted_prior_profile` (month keys `M`) | **Yes** | First bar of the new trading month when a tick table is present; **columns absent** without ticks | Same | `tests/test_tick_vap.py` month family |
| `POC_rolling_*` | `_rolling_poc` | **Yes** | Each bar uses `timestamps <= now` strictly | O(N²) MVP implementation; bars near the window boundary use only the bars in `(now - window, now]` | `test_r3_point_in_time.py::test_rolling_poc_future_shock` |

### Rolling indicators — `levels/indicators.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `SMA_N` (base timeframe) | `rolling(N).mean()` on close | **Yes** | Bar `N-1` onwards (min_periods=N) | SMA at bar `i` includes bar `i` close; if signals trigger intrabar, this is close-known | `test_r3_point_in_time.py::test_rolling_indicators_future_shock` |
| `EMA_N` (base timeframe) | `ewm(span=N).mean()` on close | **Yes** | Bar `N-1` onwards | Same bar-close note as SMA | Same |
| `SMA_N_TF` / `EMA_N_TF` (higher TF) | `_append_timeframe_levels` with `align_timestamp = bar_open + TF_delta` | **Yes** | After the higher-TF candle *completes* (not at its open) | Level is exposed at `merge_asof(direction="backward")` only once `align_timestamp ≤ base_timestamp` | `test_phase3_levels.py::test_higher_timeframe_indicator_alignment_has_no_lookahead` |
| `VWAP_rolling_*` | `rolling(window).sum(pv) / rolling(window).sum(vol)` | **Yes** | Each bar uses only the time-indexed rolling window up to and including the current bar | Bar-level typical-price approximation; true intrabar VWAP would require tick data | `test_r3_point_in_time.py::test_rolling_indicators_future_shock` |

### Confirmed pivots — `levels/pivots.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `Pivot_1m_High / Pivot_1m_Low` | strict fractal comparison on native bars | **Yes** | A pivot at bar `k` is exposed only from `pivot_bar_open + (pivot_right + 1) * 1min` onward | Requires enough left/right candles; before the first confirmed pivot the column is `NaN` | `tests/test_stage2_pivot_levels.py::test_native_1min_pivot_high_tracks_latest_confirmed_level`, `tests/test_stage2_pivot_levels.py::test_native_1min_pivot_low_respects_confirmation_delay` |
| `Pivot_5m_*`, `Pivot_30m_*`, `Pivot_4h_*` | strict fractal comparison on resampled candles, merged back with `merge_asof(direction="backward")` | **Yes** | Exposed only after the higher-timeframe pivot candle closes and the full right-side confirmation window also closes (`pivot_bar_open + (pivot_right + 1) * timeframe`) | Requires base data at or below the requested pivot timeframe; no upsampling from larger source bars | `tests/test_stage2_pivot_levels.py::test_5min_pivot_from_1min_source_is_hidden_until_confirmation`, `tests/test_stage2_pivot_levels.py::test_30min_pivot_from_1min_source_is_hidden_until_confirmation`, `tests/test_stage2_pivot_levels.py::test_pivot_levels_are_point_in_time_safe_under_future_shock` |

### Developing session VWAP — `levels/session_vwap.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `dVWAP_RTH` | cumulative `cumsum(typical_price * volume) / cumsum(volume)` over RTH bars in the current RTH session | **Yes** | First RTH bar of each session; `NaN` on all non-RTH bars | Only RTH bars contribute; resets at each new RTH session; zero cumulative volume emits `NaN`; if session column is absent it is derived from instrument config | `tests/test_stage3_session_vwap.py` (future-shock tests: `test_dvwap_rth_future_shock`, `test_dvwap_rth_future_shock_across_sessions`) |
| `dVWAP` | cumulative `cumsum(typical_price * volume) / cumsum(volume)` over **all** bars in the current CME trading session (`trading_session_date` / `eth_start`) | **Yes** | First bar of each CME session; emits on ETH and RTH | ETH+RTH bars contribute; resets at each CME session open; zero cumulative volume emits `NaN`; calendar-date fallback when instrument has no `eth_start` | `tests/test_dvwap_cme_session.py` (future-shock tests: `test_dvwap_future_shock_within_session`, `test_dvwap_future_shock_across_sessions`) |
| `wVWAP` | cumulative `cumsum(typical_price * volume) / cumsum(volume)` over **all** bars in the current trading week (`trading_session_date` → `W-SUN`, same key as `wOpen`) | **Yes** | First bar of each trading week; emits on ETH and RTH | ETH+RTH bars contribute; resets at each new trading week; zero cumulative week volume emits `NaN`; developing (within-week), not a prior-week freeze | `tests/test_wvwap_mvwap.py` (future-shock: `test_wvwap_future_shock_within_week`, `test_wvwap_future_shock_across_week_boundary`) |
| `mVWAP` | cumulative `cumsum(typical_price * volume) / cumsum(volume)` over **all** bars in the current trading month (`trading_session_date` → `M`, same key as `mOpen`) | **Yes** | First bar of each trading month; emits on ETH and RTH | ETH+RTH bars contribute; resets at each new trading month; zero cumulative month volume emits `NaN`; developing (within-month), not a prior-month freeze | `tests/test_wvwap_mvwap.py` (future-shock: `test_mvwap_future_shock_within_month`, `test_mvwap_future_shock_across_month_boundary`) |

### TPO 30m Single Prints — `levels/tpo.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `dSinglePrint_30m_NearestAbove` | Nearest SP price strictly above close, from completed 30-min RTH brackets in the current session | **Yes** | Only after the first completed 30-min RTH bracket; `NaN` on non-RTH bars and before any bracket completes | Only completed brackets used; current incomplete bracket excluded; ETH bars never contribute | `tests/test_stage4_single_prints.py` (future-shock tests: `test_future_shock_appending_current_session_bars_does_not_change_prior_values`, `test_future_shock_appending_next_session_bars_does_not_change_prior_session_sp`) |
| `dSinglePrint_30m_NearestBelow` | Nearest SP price strictly below close | **Yes** | Same as above | Same as above | Same |
| `pSinglePrint_30m_NearestAbove` | Nearest SP price strictly above close, from the prior completed RTH session's frozen SP set | **Yes** | First RTH bar of the next session; `NaN` on non-RTH bars and if prior session had no SP | Prior-session SP set is frozen once the session is complete; current-session bars cannot alter it | Same |
| `pSinglePrint_30m_NearestBelow` | Nearest SP price strictly below close, from prior session | **Yes** | Same as above | Same as above | Same |

**Note:** Single Prints and APOC/pAPOC are independent level families. Single Prints are TPO auction-structure levels (implemented in `tpo.py`). APOC/pAPOC are profile/POC levels (implemented in `apoc.py`). They share session and tick-size utilities but APOC is not derived from Single Prints. `compute_all_levels(..., apoc_enabled=True)` routes to APOC computation, while `compute_tpo_levels(..., apoc_enabled=True)` raises a redirecting `ValueError`.

### A-Period POC — `levels/apoc.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `APOC` | POC of RTH bars in `[RTH_open, RTH_open + 30 min)`, using typical-price profile approximation | **Yes** | `NaN` before `RTH_open + 30 min`; emitted from the first bar at or after A-period completion; `NaN` on all non-RTH bars | Bar-level typical-price approximation (not true volume-at-price); ETH bars never contribute; only the first 30-minute bracket is used, never full-session | `tests/test_stage5_apoc_levels.py` (future-shock tests: `test_future_shock_appending_current_session_bars_does_not_change_apoc`, `test_future_shock_appending_next_session_bars_does_not_change_papoc`) |
| `pAPOC` | Prior completed RTH session's APOC; frozen at the start of each new session | **Yes** | First RTH bar of the next session; frozen throughout; `NaN` on non-RTH bars and if prior session had no valid APOC | Same approximation note as APOC; uses only prior completed sessions | Same |

### Previous 30m VWAP — `levels/prev30m_vwap.py`

| Level family | Source | Causal? | Availability timing | Known limitations | Tests |
|---|---|---|---|---|---|
| `prev30mVWAP` | Frozen typical-price VWAP of the prior completed session-open 30m bracket; TTL + prior-session seed | **Yes** | First bar of the next bracket after §3.4 completion (clock or true session transition); ETH+RTH emit | Bar typical-price VWAP (not tick); mid-session truncation must not finalize open brackets; requires `eth_start` | `tests/test_prev30m_vwap.py` (future-shock: `test_future_shock_append_in_session`, `test_future_shock_append_next_session`, `test_mid_session_dataset_end_does_not_finalize_future_shock`) |
| `prev30mVWAP_2`…`_N` | Older still-valid freezes (Phase 3 stack; same freeze history / TTL) | **Yes** | Same availability clock as age-1; emitted only when validity `N>1` | Cross-session seed TTL-filters so expired ages are not resurrected | Same (+ Phase 3 stack / seed tests) |
| `prev30mVWAP_hit_m1` | Range-touch of `prev30mVWAP` in `[bracket_start, bracket_start+1min)` | **Yes** | `NaN` until first bar with `timestamp >= bracket_start+1min`; then bracket-constant; in-window rows stay `NaN` | Diagnostic only (not setup-eligible); all-NaN unless 1min is an integer multiple of base | Same |
| `prev30mVWAP_hit_m5` | Range-touch in `[bracket_start, bracket_start+5min)` | **Yes** | Same pattern with 5min window | Diagnostic only; all-NaN unless 5min is an integer multiple of base | Same |

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

`confirm_3bar` is audited because the helper remains in `engine/signals.py`, but it is
not part of the current public trigger set accepted by `generate_signals()`.

| Trigger | Source | Causal? | Timestamp semantics | Known limitations | Tests |
|---|---|---|---|---|---|
| `touch` | `_check_touch` | **Yes** | Signal at trigger-bar close | Next-bar execution is assumed by `entry_model="candidate_next_bar_open"` | `test_r3_point_in_time.py::test_signals_touch_future_shock` |
| `reject` | `_check_reject` | **Yes** | Signal at trigger-bar close | Same | Same |
| `break` | `_check_break` | **Yes** | Signal at trigger-bar close; uses `prev` bar to confirm breakout | Same | Same |
| `reclaim` | `_check_reclaim` | **Yes** | Signal at trigger-bar close | Same | Same |
| legacy/internal `confirm_3bar` helper | `_check_confirm_3bar` | **Yes** | Signal timestamped at **bar 3** (`bar3_idx`), not backdated to arrival bar | Entry is bar3 OHLC intrabar fill (pessimistic SL-first); bar3 is both signal bar and entry bar | `test_r3_point_in_time.py::test_confirm_3bar_not_backdated` |
| `3c` (base TF) | `detect_3c_setups` | **Yes** | Signal at `entry_idx` (filled) or `reversal_idx` (void); never backdated to arrival | Looks forward only to find reversal and retrace within allowed window | `test_r3_point_in_time.py::test_3c_signals_not_backdated` |
| `3c` (non-base TF) | `detect_3c_setups_with_trigger_timeframe` | **Yes** | `bar_index` / `timestamp` are canonical/base indexed at entry or reversal bar | `trigger_arrival_bar_index` / `trigger_reversal_bar_index` are trigger-TF indices; `trigger_timestamp` is reversal candle completion | Same |

---

## Same-bar vs next-bar semantics

### R12 intrabar resolution

All R12 models operate only on the current parent bar being evaluated:

- `sl_first` reads current parent high/low exactly as legacy behavior.
- `path_open_proximity` reads current parent O/H/L/C only.
- `subtimeframe` reads lower rows in
  `[parent_timestamp, parent_timestamp + parent_interval)` only after strict
  parent reconciliation. Rows from later parent intervals are never included.

Appending parent or lower-timeframe rows after a completed trade cannot change
that trade. `tests/test_intrabar.py::test_intrabar_models_are_future_shock_safe`
asserts this for all three models. This guarantee does not make an OHLC path
heuristic true; it establishes causality and deterministic replay only.

For **simple triggers** (`touch`, `reject`, `break`, `reclaim`):

- The signal is generated when the trigger bar **closes** (bar `i`).
- `bar_index = i`, `timestamp = bar i timestamp`.
- `entry_model = "candidate_next_bar_open"`: execution is intended at bar `i+1` open.
- The trigger bar's close is known at bar close time; no future data is required.
- Same-bar close is used as `entry_reference_price`, not as an actual fill price; backtest
  entry is bar `i+1`.

For **legacy/internal `confirm_3bar` helper**:

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

## OTF filter point-in-time rules

- OTF state for a signal at decision timestamp `T` may use only completed HTF
  bars with `availability_timestamp <= T` (equal to `bar_close_timestamp`).
- Decision timestamp selection: `trigger_timestamp` when present and non-null,
  otherwise `timestamp`.
- Alignment is backward/`merge_asof` only; future HTF bars never fill past
  decisions. Append-data / future-shock tests cover the pure engine and filter.
- Futures session reset uses `trading_session_date(..., eth_start)`. For ES/NQ,
  `eth_start="18:00"` means midnight is **not** a boundary. UI Backtest, Grid,
  validation matrix, API, and WFO forward the instrument `eth_start`.
- Walk-forward OTF history:
  - **`fold_local` (default):** each fold’s OTF source is that fold’s OHLCV
    slice only (no future-fold leakage; early-fold cold starts may yield
    `unknown`).
  - **`causal_prefix` (opt-in):** source is prefix∪fold-local bars ending at
    the fold end; prefix bars are strictly before fold start and are
    market-state only. Append-future / future-shock tests cover historical
    fold invariance.

Contract reference: `docs/otf-filter.md` §6 / §13b.

## Unresolved limitations

1. **Bar-level volume-at-price approximation.** Prior profile levels use bar typical
   price `(H+L+C)/3` with full bar volume allocated to one bin. This is an MVP
   approximation. True intrabar volume-at-price data would produce different VAH/VAL/POC
   values but would not introduce look-ahead bias by itself.

2. **ONH/ONL not available during ETH.** Overnight high/low is NaN for all ETH bars
   and becomes available only at RTH open. If a strategy requires knowing the running
   overnight high/low during ETH, it must be computed separately with a streaming/
   cumulative approach. The current gating is intentional and conservative.

3. **AsiaHigh/AsiaLow not rolling during Asia.** Asia extremes stay NaN until the
   Asia close clock gate (`asia_end`, default `00:00` ET). Strategies that need a
   developing Asia high/low during the window must compute it separately; the engine
   emits only the completed Asia range.

4. **LondonHigh/LondonLow not rolling during London.** London extremes stay NaN until
   the London close clock gate (`london_end`, default `05:00` ET). Same non-rolling
   contract as Asia; developing London extremes during the window are out of scope.

5. **`dOpen/wOpen/mOpen` reflect current-period opens.** These are current-session
   (incomplete) opens, not prior-period opens. They are available from the first bar
   of the session but represent a live level, not a historical reference. Do not confuse
   them with `pdOpen/pwOpen/pmOpen` (prior-period opens).

6. **Legacy/internal `confirm_3bar` helper uses intrabar bar-3 fill.** The 3-bar
   sequence fill at bar 3 is assumed from bar-3 OHLC. This is an intrabar-fill
   assumption, not a next-bar-open assumption. Results are pessimistic (SL-first) but
   are not independently verified against tick data.

7. **Rolling VWAP / POC at bar `i` include bar `i` close/volume.** If signals trigger
   intrabar and use same-bar rolling levels, there is a mild look-ahead within the bar
   (close is not known until bar end). The current design treats signals as bar-close
   confirmed, so this is documented intent, not a bug. See assumption 5 in
   `ASSUMPTIONS_AND_LIMITATIONS.md`.

8. **Confirmed pivots are latest-confirmed scalar levels only.** The pivot engine does
   not emit historical pivot-instance columns. It keeps only the most recent confirmed
   high and low per supported timeframe, and it does not yet classify sweeps, SFPs,
   breakers, reclaims, or retests.

9. **`dVWAP_RTH`, `dVWAP`, `wVWAP`, and `mVWAP` use bar-level typical price.** `typical_price = (high + low + close) / 3`
   is a bar-level approximation. True intrabar VWAP would require tick data but would not
   introduce look-ahead bias. Bar `i` typical price is unknown until bar `i` closes;
   since signals are treated as bar-close confirmed, this is documented intent, not a bug.

10. **Single Print columns expose only scalar nearest-above/below summaries.** No dynamic
   list of all Single Print bins is emitted. The four scalar columns are sufficient for
   signal proximity queries but do not provide the full Single Print set for manual
   analysis. APOC / pAPOC are now implemented (Stage 5; see `levels/apoc.py`).

11. **APOC / pAPOC use bar-level typical-price approximation.** `typical_price = (high + low + close) / 3`
   with full bar volume allocated to one tick bin. This is an MVP approximation consistent
   with `profile.py`. True intrabar volume-at-price data would produce different POC values
   but would not introduce look-ahead bias. APOC uses only the first RTH 30-minute bracket;
   it is not the full-session POC and is not derived from Single Prints.
