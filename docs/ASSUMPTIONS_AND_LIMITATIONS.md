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

### 2) Intrabar resolution is explicit and remains assumption-bound
- `intrabar_model="sl_first"` is the default and exactly preserves the legacy
  pessimistic rule: if stop and target are reachable in one OHLC bar, stop wins.
- `intrabar_model="path_open_proximity"` uses a deterministic three-segment
  heuristic. If the open is closer to the high, the path is O→H→L→C; otherwise
  O→L→H→C. Equal proximity remains SL-first and is counted as ambiguous.
- `intrabar_model="subtimeframe"` walks observed lower-timeframe bars in
  timestamp order. It fails closed unless data is strictly finer, complete for
  every parent bar, and reconciles to parent O/H/L/C. When stop and target occur
  inside the same terminal sub-bar, residual ordering is still unknowable and
  resolves SL-first.
- `intrabar_model="subtimeframe_conservative"` is explicitly not full observed
  replay: it uses observed replay only for complete reconciled parent groups
  and SL-first for missing or misaligned lower groups. Diagnostics identify
  every fallback parent bar and exit; invalid OHLC and OHLC mismatches still
  reject the data.
- For intrabar `3c`/legacy `confirm_3bar` entries, pre-entry movement is
  excluded. If an entry and stop occur in one lower bar, stop is taken
  pessimistically; a target seen only in that entry sub-bar is not credited
  because target-after-entry ordering is unproved. The event is counted as
  residual ambiguity.
- Path-model exits use `SL_intrabar_path` / `TP_intrabar_path`; lower-timeframe
  exits use `SL_subtimeframe` / `TP_subtimeframe`. Legacy reasons remain `SL` /
  `TP`.
- Non-legacy trades add model/resolution audit columns. Run diagnostics state
  the both-hit denominator (`bracket_exit_trade_count`), residual ambiguity
  count, affected parent bars, and lower interval where applicable.
- The open-proximity path is a deterministic sensitivity assumption, not an
  estimate of the true market path. Lower-timeframe replay reduces uncertainty
  only to the lower bar; it does not recover tick ordering.
- The Data-page lower-timeframe upload is retained only for the active session
  (and any exported research bundle), not alongside a locally saved primary
  dataset. Re-upload it after restoring a local dataset, or use the R18
  `dataset.subtimeframe_path` contract for a reproducible headless run.
- When a lower upload cannot be replayed, the Data-page compatibility report is
  diagnostic only: it identifies every incompatible parent bar but never
  patches, drops, or otherwise alters either source dataset.
- The explicit `quantower_history_exporter` profile maps semicolon-delimited
  `Time left`/OHLCV bars to canonical data. Parser success does not establish
  that separately exported 1m and 15s files reconcile; R12 remains the
  authority for that check.
- Complete 15s→1m derivation (`thesistester.data.derive`) powers the
  Data-page **recommended** Upload-CSV ingestion mode
  (`15s_primary_derive_1m`, currently `quantower_history_exporter` only).
  The mode treats the 15-second frame as source truth and emits a one-minute
  parent only for minutes with exactly four aligned opens
  (`:00/:15/:30/:45`). Incomplete or misaligned minutes are dropped rather
  than repaired; dropped-minute diagnostics are session-scoped and
  downloadable.
- In that mode the derived one-minute frame is the canonical `data` used for
  levels/signals, and the original 15-second bars are attached as
  `subtimeframe_data` for R12. The separate lower-timeframe uploader is hidden
  whenever the ingestion-mode radio selects `15s_primary_derive_1m`, even
  before a new 15-second CSV installs provenance (stale one-minute `data`
  must not reopen the dual-upload path). Switching away from the mode keeps
  the derived one-minute `data` but clears provenance/subtimeframe artifacts
  and drops the in-widget CSV so the legacy primary path cannot re-parse the
  15-second export as raw bars. Legacy one-minute primary + optional
  dual-upload remains available as an advanced path; omitting
  `dataset.ingestion_mode` in API/CLI keeps the primary contract.
- Derived one-minute volume is the sum of retained 15-second volumes. That
  volume, and therefore VWAP/profile levels computed from it, can differ from
  a separately exported vendor one-minute file even when timestamps overlap.
  Derived-1m and vendor-native-1m datasets are not interchangeable research
  identities.
- Derivation does not change R12 residual ambiguity: stop/target ties inside
  one 15-second bar remain pessimistic SL-first under the existing contract.
- The 15-second-primary path persists the retained 15-second source as a local
  `subtimeframe.parquet` sidecar (dataset schema v2) with
  `ingestion_provenance` in `meta.json`. Declared sidecars that are missing
  or corrupt fail closed on load; derive-mode provenance cannot be saved or
  session-restored without a usable lower frame. Research bundles restore the same
  members. Headless runs accept
  `dataset.ingestion_mode: 15s_primary_derive_1m` on a single Quantower 15s
  CSV and must not also set `dataset.subtimeframe_path`. Manual dual-upload
  lower files that are never saved remain session-scoped unless exported in a
  research bundle.
- Lower-upload duplicate timestamps remain fail-closed. The Data page can
  export a read-only duplicate report that distinguishes exact duplicate rows
  from conflicting same-timestamp bars; it never deduplicates automatically.
- For R12 lower data only, users may explicitly resolve duplicate groups with
  identical OHLC but conflicting volume by retaining the lowest-volume row.
  R12 does not use lower-bar volume for event ordering; every discarded volume
  is retained in research-bundle provenance. Any OHLC conflict still rejects.
- Primary-data duplicate reports are diagnostic only. Primary bars are never
  deduplicated automatically because their volume affects VWAP and profile
  calculations.
- When cleaned lower R12 data is available, the primary duplicate diagnostic
  can compare each candidate primary volume with the complete lower-bar volume
  sum. A match is evidence for investigation, not an automatic primary-volume
  selection rule.
- MAE/MFE remains based on complete parent-bar extremes for compatibility. It
  can therefore include an extreme that occurred after the modeled exit within
  the same parent bar.
- R10 excursion calibration remains a separate terminal-excursion diagnostic.
  Its `both_hit_rule` does not inherit or replay the selected R12 engine model.

### 2a) Break-even and trailing stops are completed-bar management rules
- R13 break-even and trailing stops are opt-in. Defaults `None` preserve the
  fixed-bracket legacy path.
- Break-even moves the active stop to the slipped entry price after a completed
  bar reaches the configured favorable R threshold. The moved stop becomes
  active on the next parent bar.
- Trailing stops arm after a completed bar reaches the configured favorable R
  threshold. The active stop then ratchets from the best favorable parent-bar
  high/low minus/plus the configured tick distance and is active from the next
  bar. It never loosens.
- Bar-close activation is conservative for OHLC data: the engine never assumes
  that an intrabar high armed a stop before an earlier low in the same bar.
- If an already-active BE/TRAIL stop and the fixed target are reachable in one
  bar, the selected R12 intrabar model resolves event order.
- `stop_price` remains the initial bracket stop. R-multiples and R10 MAE/MFE
  normalization still use initial risk, not the moved stop.
- A BE exit can be slightly negative after slippage/commission because the
  theoretical stop is at entry but actual fills still include adverse slippage
  and costs.

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
- For timezone-aware timestamps, non-base trigger-timeframe bucketing is DST-safe: trigger-bar flooring is performed in UTC and converted back to the original timezone for emitted trigger-bar timestamps.
- Canonical/base timestamps are preserved for output signal references; DST-safe bucketing only affects trigger-bar grouping internals.
- Backtest entry for simple triggers (`touch`, `reject`, `break`, `reclaim`) remains `bar_index + 1` on the canonical/base dataframe (first base bar after trigger-candle completion).
- For `3c` with non-base trigger timeframe: arrival, inside/muted candles, SFP tagging, and reversal confirmation are evaluated on trigger-timeframe candles. The retrace entry fill is evaluated on canonical/base bars after the reversal trigger candle is complete. `max_entry_wait_bars_after_reversal` counts trigger-timeframe bars, not base bars. Backtest execution remains unchanged because `3c` emits base-indexed `entry_bar_index` and `retrace_entry_price`.
- `arrival_bar_index`, `reversal_bar_index`, `entry_bar_index`, and `bar_index` are canonical/base indices. `trigger_arrival_bar_index`, `trigger_reversal_bar_index`, and `trigger_bar_index` are trigger-timeframe indices. `trigger_timestamp` is the reversal trigger candle completion timestamp.

### 5a) Confirmed pivots are opt-in scalar levels
- The Levels page and headless API enable confirmed pivots in their built-in configuration. Direct `compute_all_levels` calls retain `pivots_enabled=False` by default.
- Supported pivot timeframe settings remain exactly `1min`, `5min`, `30min`, and `4h`.
- Default fractal settings are `pivot_left=2` and `pivot_right=2`, matching the 5-candle pivot convention.
- Each pivot column holds the latest confirmed pivot high/low for its timeframe; before the first confirmed pivot exists, the value is `NaN`.
- Confirmed pivots are delayed by right-side confirmation and are not real-time swing predictions.
- Confirmed pivots do not encode SFP, liquidity sweep, breaker, reclaim, or retest semantics.

### 5b) Developing session VWAPs (`dVWAP_RTH`, `dVWAP`) are opt-in
- The Levels page and headless API enable session VWAPs in their built-in configuration. Direct `compute_all_levels` calls retain `session_vwap_enabled=False` by default.
- When enabled, both columns are emitted under the same gate:
  - `dVWAP_RTH` — developing VWAP from RTH open; non-RTH bars always emit `NaN`.
  - `dVWAP` — developing VWAP over the entire CME trading session (`eth_start` → next `eth_start` via `trading_session_date`); ETH and RTH bars both contribute and both emit values.
- `session_vwap_anchor` remains `"RTH"` for the RTH column gate only; full-session `dVWAP` does not use the anchor parameter.
- Instruments without `eth_start` fall back to calendar-date session grouping (same helper as other session-date levels).
- Zero cumulative volume in the active group emits `NaN` (safe divide-by-zero handling).
- If the input DataFrame lacks a `session` column, RTH membership for `dVWAP_RTH` is derived from the instrument configuration and the timestamp timezone.
- `session_vwap_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.
- `LEVEL_ENGINE_VERSION` bumped to 9 for the additive `dVWAP` vocabulary (cache invalidation when product defaults enable the family).

### 5c) TPO 30m Single Prints are opt-in scalar levels
- The Levels page and headless API enable Single Prints in their built-in configuration. Direct `compute_all_levels` calls retain `single_prints_enabled=False` by default.
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
- The Levels page and headless API enable APOC / pAPOC in their built-in configuration. Direct `compute_all_levels` calls retain `apoc_enabled=False` by default.
- `apoc_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.
- Profile approximation: `typical_price = (high + low + close) / 3`; full bar volume allocated to the tick bin containing `typical_price`. Same approximation as `profile.py`. POC tie-breaking: lowest-price bin wins (bins sorted ascending, `np.argmax` returns first max).
- APOC availability: `NaN` before `RTH_open + 30 min`; emitted from the first bar at or after that timestamp. Non-RTH bars always emit `NaN`.
- pAPOC availability: available from the first RTH bar of each session; frozen throughout. NaN on non-RTH bars and if the prior session produced no valid APOC.
- ETH bars never contribute to APOC computation; only RTH bars in `[RTH_open, RTH_open + 30 min)` are included.
- If the `session` column is absent, RTH membership is derived from the instrument configuration.
- `compute_tpo_levels(..., apoc_enabled=True)` raises `ValueError` with a redirect message. Use `compute_apoc_levels(..., enabled=True)` or `compute_all_levels(..., apoc_enabled=True)` instead.
- `compute_all_levels(..., single_prints_enabled=True, apoc_enabled=True)` produces all six independent columns: four Single Print columns plus `APOC` and `pAPOC`.
- Known limitations: not true volume-at-price (bar-level approximation), not full-session POC, not Single Print-derived, approximation matches `profile.py` MVP.

### 5e) Previous 30m VWAP (`prev30mVWAP`) is opt-in (Phase 1)

- The Levels page and headless API enable `prev30mVWAP` in their built-in configuration. Direct `compute_all_levels` calls retain `prev30m_vwap_enabled=False` by default.
- Bracket clock is **session-open** (`eth_start`), not RTH open. ETH and RTH bars both contribute and emit.
- Formula is bar typical-price VWAP (`(H+L+C)/3`), not tick VWAP.
- Freeze completes on clock (`timestamp >= bracket_end`) or on **true session transition** (CME halt). Mid-session dataframe truncation does **not** finalize open brackets.
- TTL: `prev30m_vwap_validity_periods` (integer ≥ 1, default 1); replace-on-new-freeze for age-1.
- Phase 3: when validity `N > 1`, additive stack columns `prev30mVWAP_2`…`prev30mVWAP_N` expose older still-valid freezes for confluence. Age-1 semantics match Phase 1; hit diagnostics remain age-1 only. `LEVEL_ENGINE_VERSION` bumped to 5 for the additive vocabulary.
- `AsiaHigh` / `AsiaLow` are additive completed Asia-session extremes (default `20:00–00:00` ET; clock-gated at Asia close; not rolling). `LEVEL_ENGINE_VERSION` bumped to 6 for the additive vocabulary.
- `LondonHigh` / `LondonLow` are additive completed London Killzone extremes (default `02:00–05:00` ET; clock-gated at London close; not rolling). `LEVEL_ENGINE_VERSION` bumped to 7 for the additive vocabulary.
- `pRTH_High` / `pRTH_Low` are additive prior-session RTH-only extremes (via `shift(1)`; distinct from full-session `pdHigh`/`pdLow`). `LEVEL_ENGINE_VERSION` bumped to 8 for the additive vocabulary.
- Prior-session seed carries only freezes that are still inside the TTL window at session transition (up to `N`); expired stack ages are not resurrected at the next open.
- Companion diagnostics `prev30mVWAP_hit_m1` / `prev30mVWAP_hit_m5` are **not** setup-selectable or auto-plotted price levels. They stay `NaN` until each early window completes (no rewrite of in-window rows). Each diagnostic requires its window `W` to be an integer multiple of the inferred base interval. `validate_setup_config` rejects them in `selected_levels` / anchor rules; assistant levels summaries omit them from `level_columns`.
- `prev30m_vwap_validity_periods` accepts integer-compatible values (including `numpy.int64`) and coerces to `int`, matching `validate_run_spec`. Cap is `MAX_VALIDITY_PERIODS` (48).
- Missing/empty `eth_start` fails closed with `ValueError` when enabled. Bracket open preserves `eth_start` seconds/microseconds.
- Enabled compute fails closed on NaT timestamps after exchange-timezone conversion.
- `prev30m_vwap_enabled=False` is a true no-op: no validation, no new columns.
- Phase 2 R analytics (`prev30m_hit_r_summary`) join **finalized** bracket hit flags onto trades by **entry** bracket (`entry_timestamp`); they do not change fills. When `level_names` is present, only trades referencing `prev30mVWAP` are scoped. `available` / `trade_count` require at least one finalized (non-null) hit flag; grouped R stats and contingency share the same universe (non-null flags and non-null `r_multiple`). Timezone-naive entry timestamps leave flags null instead of crashing the Backtest page.

### 5f) Stage 6 UI and Persistence — opt-in level controls (Levels page)

- The Levels page (`pages/2_Levels.py`) exposes an **"Advanced opt-in levels"** expander below the existing profile settings.
- Inside the expander: checkboxes for confirmed pivots, developing session VWAPs (`dVWAP_RTH` + `dVWAP`), TPO 30m Single Prints, APOC / pAPOC, and previous 30m VWAP; all default `True` in the built-in Levels page configuration.
- `thesistester/levels/defaults.py` also sets the shared headless API defaults: 15-minute opening range; SMA 50/200 and EMA 9/21 on `1min`/`5min`/`30min`; rolling VWAP `30min`/`4h`; rolling POC `30min`; 70% value area; and prior day/week/month profile aggregation of 4/8/10 ticks.
- When pivots are enabled, pivot timeframes (multiselect), pivot left, and pivot right number inputs are shown.
- `session_vwap_anchor` is fixed to `"RTH"` for the RTH column gate; full-session `dVWAP` is emitted alongside when the session-VWAP gate is enabled.
- No Single Print or APOC configuration controls are exposed beyond the enable checkbox.
- APOC / pAPOC remain independent from Single Prints; APOC is not routed through `compute_tpo_levels`.
- `_normalize_levels_settings` retains disabled defaults for missing Stage 6 keys so old saved snapshots remain compatible without changing their historical calculation contract.
- `pivot_timeframes` is sorted deterministically in normalization (same treatment as `sma_timeframes`, `ema_timeframes`, `vwap_windows`, `poc_windows`).
- `_sync_levels_widget_state` restores opt-in controls (including `prev30mVWAP`) when a saved snapshot is loaded. Old snapshots missing newer keys load safely and default those controls to disabled.
- Saved level snapshot labels optionally append a compact `Opt-in: pivots,dVWAP,SP,APOC,prev30mVWAP` suffix when one or more opt-in families are enabled.

## 6) Point-in-time correctness (R3 audit)

A full audit of all level, confluence, and signal modules was completed under R3. The
findings are recorded in `docs/POINT_IN_TIME_GUARANTEES.md`.

**Parts that are point-in-time guaranteed:**
- All prior-period session levels (pdHigh/pdLow/pdOpen/pdEQ, pwHigh/pwLow/pwOpen/pwEQ,
  pmHigh/pmLow/pmOpen/pmEQ, pONH/pONL, pRTH_Open/pRTH_High/pRTH_Low) use a `shift(1)`
  on per-period / per-session aggregates. Future bars cannot change any prior bar's
  "prior" level values. `pRTH_High`/`pRTH_Low` aggregate prior RTH bars only and are
  distinct from full-session `pdHigh`/`pdLow`.
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
- `dVWAP` accumulates all bars in the current CME trading session
  (`trading_session_date` / `eth_start`) using a causal cumulative sum. ETH and RTH
  bars both contribute and emit. Appending future bars cannot retroactively change
  any prior bar's value. Resets at each CME session open.
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
- `AsiaHigh`/`AsiaLow` aggregate only ETH bars in the instrument Asia window
  (default `20:00–00:00` ET) and remain NaN until the Asia close clock gate; they are
  not rolling during Asia and are distinct from overnight ONH/ONL. Empty
  `asia_start`/`asia_end` fail closed (all-NaN). Empty `eth_start` remaps evening
  Asia bars to the next calendar day so the gate/aggregate share the post-midnight
  session. Wrapping Asia with `eth_start` outside `(asia_end, asia_start]` raises.
- `LondonHigh`/`LondonLow` aggregate only ETH bars in the instrument London window
  (default `02:00–05:00` ET) and remain NaN until the London close clock gate; they are
  not rolling during London and are distinct from Asia and overnight ONH/ONL. Empty
  `london_start`/`london_end` fail closed (all-NaN). Non-wrapping London with
  `eth_start <= london_end` fails closed with `ValueError` (would otherwise
  silently all-NaN via session_date split/shift).
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
- AsiaHigh/AsiaLow are unavailable during the Asia window (by design; not a rolling
  extreme). Pre-Asia ETH (e.g. 18:00–20:00 under the default window) is excluded from
  the Asia aggregate. Asia ⊂ overnight for typical ES/NQ definitions, so Asia H/L
  generally differs from ONH/ONL.
- LondonHigh/LondonLow are unavailable during the London window (by design; not a
  rolling extreme). Pre-London ETH (e.g. 00:00–02:00 under the default window) and
  Asia extremes are excluded from the London aggregate. Empty London window strings
  disable the level (all-NaN); equal `london_start`/`london_end` fails closed with
  `ValueError`.
- `pRTH_High`/`pRTH_Low` follow the immediately prior *observed* session (same
  `shift(1)` chain as `pRTH_Open`). If that prior session has no RTH bars, values
  are NaN even when an older session had RTH. They are RTH-only and therefore
  generally differ from full-session `pdHigh`/`pdLow`.
- Rolling VWAP/POC/SMA/EMA at bar `i` include bar `i` close/volume. Signals treated
  as bar-close confirmed; this is documented intent, not a bug.
- `dOpen/wOpen/mOpen` are current-period (live) opens, not prior-period references.
  Do not confuse them with `pdOpen/pwOpen/pmOpen`.
- Confirmed pivots require enough left/right candles to become knowable and expose only
  the latest confirmed scalar levels. Historical pivot-instance columns and higher-order
  classifications (SFP, breaker, reclaim, retest) are not implemented yet.
- `dVWAP_RTH` and `dVWAP` use bar-level typical price `(H+L+C)/3`. True intrabar
  VWAP would require tick data. Since signals are treated as bar-close confirmed,
  this is documented intent, not a bug.
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
- The R18 headless facade composes the existing pipeline; it does not strengthen
  causal, execution, or statistical guarantees. Externally supplied level/data
  columns are only point-in-time safe if their construction is causal.
- Batch execution can make broad parameter searches cheap enough to create
  severe multiple-testing bias. A large run count is not independent evidence;
  retain attempted runs and use genuinely held-out or walk-forward evaluation.
- CLI parallelism is across isolated runs only. A single run remains
  single-threaded; large level grids and validation batteries can still have
  substantial CPU and memory cost.
- Determinism requires fixed input files, configuration, dependency major
  versions, and explicit seeds. Canonical bundle hashes intentionally ignore
  archive/manifest timestamps, but the DataFrame projection remains
  pandas-major-sensitive as documented by the golden-master policy.
- Validation diagnostics explicitly warn that assumptions like sign symmetry and independence limits apply; serial dependence is ignored (`thesistester/analytics/validation.py:10-11`, `115-117`).
- Outputs are explicitly framed as diagnostics and not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`).
- Walk-forward / out-of-sample diagnostics are also descriptive only, not proof of edge.
- MAE/MFE excursion analytics are post-trade diagnostics only. They use terminal
  bar-level `mae_points` / `mfe_points` captured by the engine and cannot prove
  whether favorable or adverse excursion happened first within an OHLC bar.
- The SL/TP calibration grid in `thesistester/analytics/excursions.py` estimates
  hit probabilities from terminal excursions under an explicit ambiguity rule.
  It is not a re-simulation and should not be interpreted as a fill-ordered
  counterfactual backtest.
- R10 edge-ratio decay uses completed-trade `bars_held` buckets as a proxy.
  True Build Alpha-style decay across bars would require storing the intratrade
  MAE/MFE path, which is intentionally out of R10 scope.
- Monte Carlo diagnostics in `thesistester/analytics/monte_carlo.py` resample
  the realized trade `r_multiple` sequence only; they do not re-run entries,
  exits, costs, session policies, or exposure admission.
- `reshuffle` changes trade order only and therefore tests path-risk sensitivity
  to ordering. It preserves the realized R multiset and cannot reveal whether
  the trade sample itself is overfit.
- `skip` models independent missed trades by replacing random trade slots with
  0R. It does not model liquidity, calendar clustering, trader discretion, or
  execution-state dependence.
- `block_resample` preserves local streak structure better than iid reshuffle,
  but it remains a bootstrap approximation. Block length is a modeling choice,
  not a market truth.
- Monte Carlo equity fans and drawdown probabilities are diagnostics on the
  observed trade sample, not forecasts or proof of future edge.
- Walk-forward defaults remain deterministic bar-index rolling windows for
  backward compatibility. R14 session mode instead groups observed bars by the
  exchange trading-session date using the instrument ETH boundary; every
  observed session is atomic, including shortened sessions.
- Session mode is calendar-aware by observed trading date, not a complete
  exchange holiday schedule. An absent session is treated as absent data, not
  synthesized or certified as a holiday.
- Rolling windows keep a fixed train-session count; anchored windows grow the
  train history from the first observed session.
- Expectancy retention ratio is reported only when IS expectancy is positive;
  zero/negative/undefined IS expectancy has no economically meaningful ratio.
- Stitched OOS equity concatenates test-window trades only. Overlapping test
  windows default to `overlap_policy="reject"`; `first`/`last` explicitly
  assign duplicate executable entries to one fold.
- Stitched OOS equity is a sequence of fold-local OOS segments, not a single
  continuous portfolio simulation across parameter-change boundaries.
- The WFA matrix is a robustness surface across train/test session lengths,
  not another parameter optimizer. Selecting the best matrix cell using its
  OOS result reintroduces multiple-testing bias.
- R15 CSCV/PBO partitions realized trade R sequences contiguously. It is not
  purged/embargoed bar-level cross-validation and assumes limited dependence
  across blocks.
- R15 PSR/DSR uses unannualized per-trade R Sharpe-like statistics. DSR only
  corrects the grid trials declared in the current run; discarded grids,
  signal variants, manual iteration, and correlated trials are not recoverable
  automatically. Its observed sequence must be a replayed cell passing the
  declared grid selection rule; R15 does not fall back to the Phase 5 backtest.
- R15 vs-random tests a seeded random-entry timing/direction null under the
  same simulator settings. It does not test random levels, regime matching, or
  all possible alternative strategies.
- R15 re-simulates every grid cell and many random schedules. It is opt-in and
  can be expensive; results remain diagnostics rather than proof of edge.
- R16 perturbs copied parent OHLC bars with symmetric ATR- or range-scaled
  noise, then enforces bar validity. This is one declared local perturbation
  model, not a model of exchange microstructure, spread, gaps, or tick paths.
- R16 persistence prefers stable `signal_id`; when unavailable it matches
  direction plus entry timestamp. A changed/recomputed signal can therefore be
  classified as non-persistent even if it is economically similar.
- R16 keeps supplied lower-timeframe R12 data unchanged rather than inventing
  noisy sub-bars. Parent/subtimeframe reconciliation is consequently not
  guaranteed for a subtimeframe replay.
- R16 cost is replicas × the complete levels/signal/backtest pipeline. It is
  opt-in and should use a smaller replica count for exploratory runs; results
  remain diagnostics rather than proof of edge.
- R19 changes one selected execution parameter at a time around the chosen
  grid cell while holding fixed signals and all other parameters. It cannot
  detect parameter interactions, unseen regimes, or sampling uncertainty.
- R19 flags a positive/negative expectancy sign flip only within its declared
  local perturbation range. A non-fragile result is not proof that the
  parameter is globally robust; a fragile result can also reflect small-sample
  noise. Tick-valued candidates use nearest-integer rounding and may collapse
  to fewer unique values than requested.
- R19 cost scales with profiled parameters × perturbation steps × serial trade
  replays. It is opt-in; R22 acceleration is not yet available.
- R20 trade-review charts show completed-trade parent-bar OHLC context. MAE/MFE
  bands are terminal extrema relative to entry, not a temporal replay of
  adverse/favorable movement or evidence of intrabar fill ordering.
- R20 displays `stop_price` as the initial bracket stop. The optional final
  managed-stop line is a completed-bar R13 diagnostic and must not be read as
  active within the bar in which it was adjusted.
- PNG export is capped to twenty selected losers and uses only bounded windows;
  it is a review aid, not a batch simulation or an exported research result.
- R21 combines independent completed setup trades after their individual
  simulations. It is not a continuous capital, margin, liquidity, correlation,
  or fill simulation; its exposure policy is a deterministic admission
  approximation on shared parent-bar indices.
- R21 requires all source runs to share an instrument and parent bar-index
  timeline. Per-setup runs should use `allow_all` when portfolio-level
  admission is intended; otherwise exposure restrictions can be applied twice.
- R21 return/drawdown correlations align exit-timestamp R increments and fill
  no-trade steps with zero. They are descriptive historical co-movement, not
  forecasts or allocation recommendations.
- R17 vendor parsing is selected explicitly; ThesisTester does not infer a
  format from headers or file extension. Select the documented profile for the
  vendor export and verify the displayed canonical bars before research use.
- R17 tick/second and Databento trade captures are resampled to one-minute
  OHLCV for the current bar engine. Preserved raw rows, including bid/ask, are
  capture-only and are not used for spread modeling or R12 subtimeframe fills.
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

## AI Research Assistant / optional LLM (PR6 release gate)
- The assistant is a research orchestration UI over the existing engine. It does
  not introduce a second backtest path, broker connectivity, or live trading.
- Deterministic explain/compare/export works without any LLM provider. When a
  provider is configured, it may only propose non-executing draft choices or
  paraphrase an immutable evidence packet.
- Additive channels (contract complete:
  `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` RQ-0…RQ-5): multi-turn
  **results Q&A** bound to one hash-verified `EvidencePacket`, and **product
  help** grounded in a curated local docs/registry corpus. Those channels must
  not merge into thesis-draft chat, must omit draft `choices`, and must not
  dispatch compute pipelines from the model. **RQ-0** reserves
  `[assistant.results_qa]` / `[assistant.product_help]` and ships the inert
  §7.1 Help corpus allowlist (`thesistester/assistant/help_corpus.py`).
  **RQ-1** ships multi-turn Discuss results (`handle_results_turn` /
  `results_qa`) on hash-verified evidence. **RQ-2** adds ephemeral
  `results.projections.*` grid/time rankings (empty bundle grid tables fall
  back to packet `best_grid_result`; unknown ranking-metric names are
  sanitized via the aggregate/directional allowlist preference chain and
  synced into the ephemeral metric-source path; JSON-null all-wins profit
  factors rank as +inf; projection `best` pins packet `best_grid_result`
  when re-rank disagrees; bundle table load failures warn via
  `bundle_tables_warning` instead of mimicking an empty grid) and optional RO
  `TIME.analyze` enrichment when
  `assistant.results_qa.allow_time_enrichment=true` (default `false`).
  **RQ-3** ships documentation-grounded Help (`handle_help_turn` /
  `product_help`) over the §7.1 corpus + registry digest; run-performance
  questions remediate to Discuss results (no fabricated metrics). Help digit
  tokens must match number tokens in attached corpus/registry text.
  **HC-series (complete):** feature/how-to Help coverage is USER_GUIDE-backed
  via RQ §7.1.4 (`docs/USER_GUIDE.md` + `HELP_CORPUS_MANIFEST`); frozen
  acceptance bank and parity gates live in
  `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` / `tests/test_assistant_help_coverage.py`.
  **RQ-4** binds classic Discuss via companion session key
  `classic_focus_channel="results_qa"` beside string `classic_focus_run_id`
  (never a dict).   **RQ-5** freezes honesty/injection evals in
  `tests/test_assistant_llm_evaluations.py` (missing evidence, uncited
  numbers, WFA caveat merge + OOS anti-soften, pipeline injection, draft
  isolation, corpus allowlist, provider-key remediation, offline deterministic
  Explain, registry audit).
  Thesis switches clear `assistant_results_qa_drafts`,
  `assistant_product_help_draft`, and related widget keys. Draft-chat history
  excludes `results_qa` / `product_help` turns and tool/audit lines so
  multi-turn Discuss/Help cannot starve thesis context.
- LLM explanations must cite packet paths; uncited numerical tokens are rejected
  before render. When provenance includes a fingerprint, dataset identity is
  available at `assumptions.dataset.dataset_fingerprint` (and mirrored at
  `assumptions.dataset_fingerprint`); the nested key is omitted when fingerprint
  is absent. The model cannot execute tools, mutate confirmed RunSpecs, bypass
  confirmation, or invent metrics.
- Credentials: set a rotated `OPENAI_API_KEY` in the environment first, or via
  Streamlit Secrets on Community Cloud (top-level `OPENAI_API_KEY`; nested
  `[openai].api_key` or `[openai].OPENAI_API_KEY` accepted as compatibility).
  One layer of wrapping quotes / UTF-8 BOM is stripped so copy-paste into
  Secrets does not produce a Bearer token that OpenAI rejects as
  `invalid_api_key`. The placeholder `REPLACE_WITH_ROTATED_OPENAI_API_KEY` is
  rejected. Never store the key in tracked configuration. Non-secret knobs
  (`provider`, `model`, retries, history trim, `evidence_only`) live in
  `config/assistant.toml`.
- Provider timeouts retry per `max_retries`; exhaustion surfaces as a provider
  error and leaves the deterministic packet intact. Transport failures from
  `UrllibOpenAITransport` keep the stable prefix
  `OpenAI structured request failed` and append a sanitized detail
  (`HTTP <status>`, OpenAI `code`, redacted message, timeout, or invalid JSON)
  so chat UI errors are actionable without leaking credentials (`sk-…` shapes,
  `Bearer` tokens, and the exact configured key when echoed). HTTP `400` /
  `401` / `403` / `404` are non-retryable and fail on the first attempt. Cancel /
  recovery of compute uses orchestrator `cancel_run` and terminal run states,
  not chat turns.
- Provenance: completed-run explanations and comparisons require a readable
  research bundle whose `canonical_bundle_hash` matches reported provenance.
- Statistical honesty: sample-size, zero-cost, intrabar ambiguity, OOS, and
  multiple-testing caveats from the evidence packet remain mandatory framing;
  LLM narrative must not soften or omit them into trade advice.
- Registry rows that remain `unsupported` expose a user-visible limitation and
  funnel through routed capabilities (typically `PIPELINE.run_experiment` plus
  evidence/export). They are audited by `audit_capability_registry()`.

## Voice agent (VA-series — complete; default off)
- Spoken review of completed runs / product help is specified in
  `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (single VA-series contract;
  post-RQ / post-HC). Text Discuss / Help remain owned by
  `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`. VA-1 text substrate is RQ-1;
  Help corpus substrate is HC-complete. **VA-0…VA-6 complete:** contracts/flag,
  xAI STT/TTS + voice sessions, read-only voice tools + digit grounding,
  opt-in push-to-talk UI, localhost realtime sidecar
  (`python -m thesistester.assistant.voice.sidecar`), and release-gate evals in
  `tests/test_assistant_voice_evaluations.py`.
- Product shape: voice is a spoken transport over the same RQ channels
  (Discuss results + Help), not a second evidence dialect. It must omit draft
  `choices`, must not dispatch compute, and must fail closed on ungrounded
  numbers. Mic controls are hidden while `assistant.voice.enabled=false` and
  blocked while any thesis research run is `status=="running"`.
- **Default remains off** after VA-6 (`assistant.voice.enabled = false` in
  tracked `config/assistant.toml`). Opt-in from the Research Assistant
  **sidebar Voice controls** (Enable + Push-to-talk / Realtime) — choices
  persist to gitignored `config/assistant.voice.override.toml` so Streamlit
  and the realtime sidecar share them without dirtying tracked config — or
  set `enabled` / `mode` in TOML. Provide `XAI_API_KEY` (sidecar/STT/TTS) and
  `OPENAI_API_KEY` (PTT RQ channel turns), then use Discuss/Help voice panels /
  start the localhost sidecar. Results sessions bind hash-verified evidence;
  Help sessions reuse the §7.1 / HC corpus path. Missing OpenAI on Discuss
  falls back to one VA-3 tool template; Help without OpenAI remediates (no
  fabricated docs).
- Dual keys: xAI for STT/TTS and realtime (`XAI_API_KEY` env → Secrets
  top-level → `[xai].api_key`; placeholders rejected; never embedded in page
  modules); OpenAI for primary PTT channel turns via `handle_results_turn` /
  `handle_help_turn`. Realtime duplex uses a localhost sidecar that owns the
  xAI WebSocket (browser never receives the key). Realtime v1 is results-run
  bound only (Help duplex deferred). Raw audio is not stored by default
  (`store_audio = false`); last PTT TTS bytes may sit ephemerally in
  `assistant_voice_playback` for `st.audio` only. Sessions end at
  `max_session_minutes` (default 15). Budget guidance: ~$0.08/min speech-to-
  speech for Think Fast 2.0, plus unary STT/TTS and OpenAI for VA-4 channel
  turns. PTT spoken answers are digit-gated before TTS. Realtime live PCM
  cannot be pre-gated once uttered; assistant transcript text is still
  digit-audited against the bound packet and tool returns before durable
  persistence/flush (uncited numbers are replaced with remediation).

## OTF filter (One Timeframing)

- **Default-off.** When OTF is disabled or absent from a setup, candidate
  signals, trades, grid cells, and walk-forward folds match legacy behavior.
- **Admission layer, not signal generation.** `generate_signals()` remains
  candidate-only. Backtest, Grid, and Walk-forward apply
  `apply_configured_otf_filter()` before execution. Rejected candidates are
  retained for audit and are distinct from exposure-policy skips and 3c voids.
- **Completed HTF bars only.** OTF state uses bars whose
  `availability_timestamp` is at or before the signal decision timestamp.
  This introduces intentional decision lag versus an in-progress HTF bar.
- **Directional rejection.** `unknown`, `neutral`, and opposing OTF states
  reject directional candidates under v1 `all` alignment.
- **Futures session boundaries.** Session reset uses instrument `eth_start`
  (e.g. `"18:00"` for ES/NQ) in the exchange timezone. Midnight is **not** a
  session boundary. UI Backtest/Grid/validation matrix forward `eth_start` in
  parity with the API and walk-forward surfaces.
- **Source interval.** Source bars must be strictly finer than each selected
  OTF timeframe and must divide it exactly.
- **Sample-size impact.** Multi-timeframe `all` alignment can materially reduce
  accepted trade counts; lower frequency is not evidence of edge by itself.
- **Walk-forward OTF history policy.** Default `otf_history_policy=fold_local`
  uses only each fold’s OHLCV slice, so early fold candidates may be rejected
  as `unknown` even when prior bars were causally available (leakage-safe cold
  start). Opt-in `causal_prefix` uses prefix∪fold-local bars
  (`df.iloc[:fold_end]`) so prior completed HTF history may establish OTF
  state; only fold-local signals are scored, and bars after the fold end are
  never used. The effective policy is recorded on WFO config/summary/rows.
- **Validation matrix is diagnostic.** Train-only ranking / OOS evaluation
  tooling does not prove durable edge and must not auto-select a production
  OTF configuration.
- **Config provenance.** Resolution precedence is signal-run
  `signal_settings["otf_filter"]` → setup snapshot → last signal setup →
  active setup → disabled defaults. Later Setup Builder edits do not rewrite
  an existing signal run; regenerate signals to adopt new OTF settings.
- **Incomparable results.** Changing `OTF_ALGORITHM_VERSION`, OTF config hash,
  `eth_start` / session timezone, selected timeframes, minimum consecutive
  bars, or WFO history policy makes OTF-enabled runs incomparable without
  explicit re-baselining.

## Practical interpretation
- With default settings, expectancy remains equivalent to prior gross outputs.
- With non-zero cost settings, expectancy and downstream KPIs become net-of-cost.
- Treat results as **screening diagnostics, not proof of edge**.
