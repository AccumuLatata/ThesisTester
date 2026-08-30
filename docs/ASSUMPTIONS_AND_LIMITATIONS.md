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
  pessimistic rule on bars with no entry activation (`entry_price is None`):
  if stop and target are reachable in one OHLC bar, stop wins. On the `3c` /
  `confirm_3bar` entry parent, `sl_first` honors the already-passed
  `entry_activation_price` and ignores SL/TP hits that exist only beyond that
  fill (reuses `_path_after_entry`; no new `intrabar_model`).
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
  and SL-first for missing or misaligned lower groups. The fallback calls
  `sl_first` **without** `entry_price`, so a pre-retrace parent extreme still
  SL-kills. Diagnostics identify every fallback parent bar and exit; invalid
  OHLC and OHLC mismatches still reject the data.
- For `3c`/legacy `confirm_3bar` entries, pre-entry movement is excluded on
  the entry parent for `sl_first` (AH5), `path_open_proximity`, and strict
  `subtimeframe`. Conservative fallback is not that clip — it remains
  full-bar `sl_first` and still SL-kills. If an entry and stop occur in one
  lower bar, stop is taken pessimistically; a target seen only in that entry
  sub-bar is not credited because target-after-entry ordering is unproved.
  The event is counted as residual ambiguity.
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
- Observed 15s→1m derivation (`thesistester.data.derive`, policy
  `observed_aligned_15s_to_1m_v2`) powers the Data-page **recommended**
  Upload-CSV ingestion mode (`15s_primary_derive_1m`, currently
  `quantower_history_exporter` only). The mode treats the 15-second frame as
  source truth and emits a one-minute parent for every minute with one or more
  on-grid opens (`:00/:15/:30/:45`). Sparse minutes from Quantower/Rithmic
  trade-only exports (empty 15s slots omitted) are retained and reported as
  sparse diagnostics; only misaligned (off-grid) minutes are dropped. Empty
  bars are never synthesized. Strict R12 `intrabar_model=subtimeframe` still
  requires complete four-bar coverage — use `subtimeframe_conservative` for
  observed replay plus SL-first fallback on sparse minutes, or enable
  Quantower Build empty bars for full coverage.
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
  CSV and must not also set `dataset.subtimeframe_path`. New Study Builder
  drafts and the pdPOC teaching example emit that contract; omitted mode on
  a 15s file is a different dataset (15s decision-TF, no derived 1m / R12
  attach). The dopen example remains legacy 1m primary. Studies does not
  walk the Data page — parity is the RunSpec, not shared `session_state`.
  Vendor-native 1m and derived 1m remain non-interchangeable. Manual dual-upload
  lower files that are never saved remain session-scoped unless exported in a
  research bundle.
- On the 15s-primary derive path (Data page, API, CLI, study), a handful of
  vendor-repeated 15-second opens are resolved **before** 1m derivation when
  every duplicate group shares OHLC (exact copies included). Policy
  `ohlc_identical_keep_lowest_volume` — the same rule as the legacy lower-TF
  button. Audit is recorded in `ingestion_provenance`
  (`source_duplicate_resolution`, group/row counts, per-group discarded
  volumes). OHLC conflicts stay fail-closed. `derive_complete_parent_ohlcv`
  still rejects a duplicate-bearing frame; resolution is a pre-derive step
  shared by Data and `run_experiment`.
- Legacy dual-upload lower-TF duplicates remain fail-closed until the
  operator clicks **Use OHLC-identical duplicates for lower-timeframe replay
  only**. The Data page can export a read-only duplicate report that
  distinguishes exact duplicate rows from conflicting same-timestamp bars.
- Primary-data (native 1m) duplicate reports are diagnostic only. Native
  one-minute primary bars are never auto-deduplicated because their volume
  affects VWAP and profile calculations.
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
- Optional session-aware mode (`flat_by_session_close=True`) caps exits to the configured session close for **this trade’s** entry calendar date (`entry_local_ts.normalize()` + `session_close_time`, default `16:00`). Each candidate stores its own `entry_local_ts`; flatten does not reuse another signal’s clock.
  - `SESSION_CLOSE` means forced flat at the last available bar at or before that per-entry close (when SL/TP is not hit first). It is **not** CME session close and does not use `trading_session_date` or `eth_start`.
  - `DATA_END` means data ended before session close and the trade was force-closed at the last available bar.
  - After-close ETH on that same calendar date (entry local time after the configured close) is a non-fill. With skip capture on (`return_result` / `return_skipped_signals`) the skip reason is `empty_session_close_cap`. Default `return_result=False` stays trades-only.
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
- Optional skipped-signal diagnostics may include exposure-policy rejections,
  `after_entry_cutoff` when `no_new_entries_after` rejects with skip capture on
  (SW2b), and `outside_entry_window` when opt-in Admit is enabled (SW2/SW3).
  Backtest captions split window / cutoff / exposure-other counts. Cutoff uses
  strict `>` (entry **at** cutoff still admits). When both window and cutoff
  would reject, skip labeling prefers `outside_entry_window` (C9 — window
  checked before cutoff; admitted trade set is identical either order).
  Signals skipped for pre-existing non-executable reasons (e.g., void `3c`,
  missing future entry bar) are still not included. Skip capture does not
  change which trades fill.
- Default `entry_window=None` / disabled preserves legacy all-day admission
  (golden-identical trades). `api.run_backtest` and classic Backtest Admit
  controls (SW3) default off.

### 4a) Time Analysis Focus vs Admit (SW1–SW4)
- **Focus summary** filters already completed trades by **entry** time bucket
  (C2 — always `entry_timestamp`, even when Time Analysis charts group by exit)
  and recomputes KPIs / equity. Focus/Promote dropdown options are also built
  from entry-time buckets so they cannot silently diverge from exit-grouped
  chart rows. It does **not** call `simulate_trades` and does **not** change
  exposure, cooldown, or which signals were admitted.
- Focused equity and max drawdown are a **subset replay** of the filtered trade
  list, not path drawdown under the all-day admission set.
- **Promote** (SW4) arms an Admit `entry_window` from a Focused/selected bucket
  and pre-fills Backtest widgets. It does **not** auto-run simulation. Thin
  samples require explicit confirmation. Promote sample counts / thin-sample
  gating always use **entry** timestamps (C2), even when Time Analysis charts
  use exit time. Until a constrained Admit re-sim, UI shows: “Entry window
  armed. Run Backtest to re-simulate under this constraint.” An all-day Run
  (Admit toggle off) does **not** consume the armed handoff.
- **Admit** (`simulate_trades` / `run_backtest` / Backtest UI `entry_window`) is
  the constrained re-simulation path. Membership uses **entry-bar** local time
  (not signal-bar time). Window rejects never enter exposure competition.
  Constrained runs show: “Constrained re-simulation — only in-window entries
  were admitted.” Focus and Admit badges stay distinct.
- **Grid / WFA / sensitivity (SW5)** inherit the same fixed Admit window when
  present. Inheritance prefers an *enabled* Backtest/Promote `entry_window`,
  else an enabled `grid_entry_window` (disabled dicts must not shadow). The
  window is not a swept axis and is not reselected per fold. Validation uses
  instrument exchange TZ for Admit membership so noise→`run_backtest` matches
  WFA/sensitivity (C5). Default-off preserves legacy all-day grid/WFA behavior.
- **Setup library / Report / Assistant (SW6):** setups may persist an additive
  optional `entry_window` key (OTF-style normalize/default; no
  `SETUP_SCHEMA_VERSION` bump). Missing/null → disabled. Incomplete Setup Builder
  Admit drafts (e.g. enabled with empty RTH segments) must not crash the editor;
  Save still fails closed via validate. Research artifacts and bundles export
  Admit window + Focus/Promote provenance with explicit Focus≠Admit honesty
  labels; disabled placeholder dicts alone are not treated as available evidence.
  Bundle import rehydrates Backtest Admit widgets from restored `entry_window`
  (Run reads widgets, not the dict alone). The assistant must not claim deployable
  edge from Focus alone (`focus_post_hoc` caveat when Focus evidence is present).
- Under `exposure_policy="allow_all"` and `cooldown_bars_after_exit=0`, Focus
  and Admit admit the same `signal_id` set (C7). See
  `docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md`.
- TZ law (C5): RTH-segment membership always evaluates in the instrument
  exchange/session timezone via `entry_window_exchange_tz` (API/UI pass the
  instrument exchange TZ). This is distinct from `session_timezone`, which
  only interprets session-close / `no_new_entries_after` clocks. Clock-range
  membership uses the window/bucket timezone. Promote writes that TZ
  explicitly into the normalized dict. Tz-naive timestamps are treated
  as exchange/session wall clocks (same as `add_time_buckets`), then
  converted — never localized directly as the bucket/display TZ. Invalid IANA
  timezone keys fail closed at normalize.

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
- StudySpec pivot tokens are the engine column names `Pivot_1m_*` / `Pivot_5m_*` /
  `Pivot_30m_*` / `Pivot_4h_*`. Hand-edited YAML that uses `Pivot_1min_*` fails
  closed at validate; there is no compatibility alias.
- Setup `SUGGESTED_DEFAULT_LEVELS` is a subset of
  `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`. Suggested `pdPOC` appears
  only when the column exists (15s-only / no-tick frames drop it). Do not add
  `pdVAH` / `pdVAL`. `VWAP_rolling_1h` is opt-in
  via `vwap_windows`; product defaults remain `30min` / `4h`. Assistant
  confluence options use that closed set (DEFAULT merge, plus live / selected);
  widget-only MA timeframes (`15min` / `1h` / `4h`) are not implied tokens and
  do not raise. Developing `dHigh` / `RTH_High` / `dVAH`, rolling VAH/VAL, IB,
  `OR_Mid`, and `pVWAP` are known catalog absences (not computed), not StudySpec
  holes.
- Missing selected/anchor level columns fail closed at `api.generate_signals` /
  `run_experiment` / study cells (`Setup references unavailable level columns`).
  They are not silent drops. Classic Signals saved-setup blockers are unchanged.
- Default fractal settings are `pivot_left=2` and `pivot_right=2`, matching the 5-candle pivot convention.
- Each pivot column holds the latest confirmed pivot high/low for its timeframe; before the first confirmed pivot exists, the value is `NaN`.
- Confirmed pivots are delayed by right-side confirmation and are not real-time swing predictions.
- Confirmed pivots do not encode SFP, liquidity sweep, breaker, reclaim, or retest semantics.

### 5b) Developing session VWAPs (`dVWAP_RTH`, `dVWAP`, `wVWAP`, `mVWAP`) are opt-in
- The Levels page and headless API enable session VWAPs in their built-in configuration. Direct `compute_all_levels` calls retain `session_vwap_enabled=False` by default.
- When enabled, four columns are emitted under the same gate:
  - `dVWAP_RTH` — developing VWAP from RTH open; non-RTH bars always emit `NaN`.
  - `dVWAP` — developing VWAP over the entire CME trading session (`eth_start` → next `eth_start` via `trading_session_date`); ETH and RTH bars both contribute and both emit values.
  - `wVWAP` — developing VWAP of the current CME trading week (`trading_session_date` → `W-SUN`, same key as `wOpen`); ETH and RTH bars both contribute and emit. This is a within-week developing level, not a prior-week freeze.
  - `mVWAP` — developing VWAP of the current CME trading month (`trading_session_date` → `M`, same key as `mOpen`); ETH and RTH bars both contribute and emit. This is a within-month developing level, not a prior-month freeze.
- `session_vwap_anchor` remains `"RTH"` for the RTH column gate only; full-session `dVWAP` / `wVWAP` / `mVWAP` do not use the anchor parameter.
- Instruments without `eth_start` fall back to calendar-date session grouping (same helper as other session-date levels).
- Zero cumulative volume in the active group emits `NaN` (safe divide-by-zero handling).
- If the input DataFrame lacks a `session` column, RTH membership for `dVWAP_RTH` is derived from the instrument configuration and the timestamp timezone.
- `session_vwap_enabled=False` is a true no-op: no validation, no new columns, no timestamp checks.
- `LEVEL_ENGINE_VERSION` bumped to 10 for the additive `wVWAP` / `mVWAP` vocabulary (cache invalidation when product defaults enable the family).
- `LEVEL_ENGINE_VERSION` bumped to 11 for the tick-VAP identity cutover: `pd*` / `pw*` / `pm*` VA are tick Last×Volume when ticks are provided and omitted otherwise (cache invalidation vs typical-price VA under the same names).

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

### 5e2) Confluence combo attribution is post-trade diagnostic only

- Backtest expander **Confluence combo attribution** groups displayed trades by
  recorded `level_names` (exact canonical combo, level membership, and parsed
  token count). The Backtest **Exact combo** tab always splits by trade
  `direction` (`long` / `short`) — grain is `exact_combo_key × direction`.
  Undirected exact summaries remain for report / bundle / assistant only.
  Splitting by direction can push more Exact (and Combo × variant) groups under
  the existing hide-below-`min_trades` filter; the default threshold is not
  retuned. It does **not** change zones, signals, fills, or exposure.
- Time Analysis may optionally group by `exact_combo_key` or View-C
  `level_count_bucket` when confluence attribution is available (≥1 analyzable
  trade with a nonempty parsed combo). Those dims are **appended** after the
  existing time/setup options so the default primary remains a time bucket.
  Soft pairs and membership are **not** Time Analysis group dimensions (they
  break partition intuition via double-count / many-to-many explode). Focus /
  Promote stay limited to entry-time buckets.
- Report / Export may include an optional **Confluence Combo Attribution**
  diagnostic section. It is **recomputed on export** from session trades via the
  same mode/anchor resolution path as Backtest (`signal_settings` →
  `last_signal_setup` → `setup_config` → `signal_context`). When attribution is
  unavailable, the artifact key and markdown section are **omitted entirely**
  so legacy reports stay unchanged. No Backtest producer session key is required.
- Research Bundles may attach optional confluence combo siblings
  (`confluence_combo_summary.json` + optional `confluence_by_*.parquet`) via the
  same on-export recompute, and only when the backtest section is also included
  (so siblings are never orphaned without `trades.parquet`).
  `included["confluence_combo"]` is set only when available. Old bundles without
  those files still import; missing optional parquet siblings do not fail load.
  Restored values use managed research keys (`confluence_combo_summary`,
  `confluence_by_*`) cleared when the section is absent; baked summary
  mode/anchor is reused on recompute when ephemeral `signal_settings` are gone.
  View-C mixed int/`(unknown)` count labels are stringified for parquet safety.
  `BUNDLE_SCHEMA_VERSION` is not bumped for these optional siblings. Canonical
  bundle hashes exclude these derived siblings (and the
  `included.confluence_combo` / related `session_keys` markers) so legacy golden
  hash locks stay stable without a `GOLDEN_REGEN`.
- Discuss / Results Q&A may attach a **bounded** ephemeral projection
  `results.projections.confluence_combo` (top exact combo / level-count / optional
  pairs + warning flags) recomputed from loaded trade rows via the same mode/anchor
  path.   Evidence packets copy `last_signal_setup` / `signal_settings` /
  `signal_context` into assumptions when present so stale Setup Builder
  `setup_config` alone cannot drift captions/anchor display. Packets also mount
  a table-free `results.confluence_combo_summary` identity leaf (baked 5c summary
  preferred, else artifact report block) so Discuss can reuse mode/anchor when
  ephemeral `signal_settings` are gone — same fallback as report/bundle export.
  5c bundle siblings are optional convenience, not required. The frozen discuss allowlist cites only
  those leaves; unavailable trades → calm missing fallback (no free-form
  full-table dumps, no Setup auto-recommendations, no future-edge claims).
  Membership/pairwise double-count caveats apply when those tops are present.
- Backtest may show an **opt-in** nested expander **Combo × 3c variant** inside
  Confluence combo attribution. It cross-tabs
  `exact_combo_key × direction × trigger_variant` (and
  `pair_key × direction × trigger_variant`) on `_display_trades` only. Membership /
  Level count / Pairs tabs stay undirected. Null/empty `trigger_variant` and
  unusable `direction` rows are omitted (no synthetic unknown; usable direction
  is only `long` / `short` from the trade column — never parsed from
  `trigger_variant`). Empty-`level_names` trades are also omitted from the
  cross-view (they are not combinations); usable variants must sit on a nonempty
  exact combo. Availability requires ≥1 analyzable displayed trade that has
  **both** usable `direction` and usable `trigger_variant` on the same nonempty
  combo (independent axis checks alone can both pass while the 3-key tables stay
  empty). When Focus is ON, counts will not match the standalone “3c outcome
  summary by variant/source” block (that block still uses full session `trades`).
  Not a new signal model; does not change 3c arrival / zone / fill semantics.
- Rows are **observed traded combinations**, not the theoretical power set of
  selected levels / confluence rules.
- Exact-combo keys are canonicalized (sorted tokens) so `A|B` and `B|A` merge.
- Membership attribution **double-counts** trades across levels and is not an
  additive PnL decomposition.
- Nested sets such as `A|B` vs `A|B|C` remain separate exact-combo rows. Soft
  pairwise attribution (Pairs tab) credits shared pairs without engine pairwise
  zone emission and **double-counts** trades across pairs.
- Pair mode is **anchor-partner** only when the signal-run identity is
  `anchor_rules` with a known `anchor_level` (`anchor|support` keys). Otherwise
  pairs are generic unordered canonical `A|B` keys. Anchor is never guessed from
  token order.
- **Location-only `anchor_rules`** (`confluence_rules: []`,
  `min_valid_confluences: 0`) is a different thesis than L1 `{dVWAP}`. The
  zone is a point at the live anchor price, typically **narrower** than an
  L1 zone (L1 width ∈ `[0, tolerance]` ticks). Δ vs L1 mixes “value of a
  second mark” with that width change. Rank `expectancy_r`, not `total_r`.
  n will be larger. Not proof of edge. Default `min_valid` remains 1.
- Level-count view uses the **parsed distinct token count** from `level_names`,
  not stored zone `level_count` (important for `3c`, where names may be the
  tested level only). Empty parsed counts surface as `(unknown)`, not raw `0`;
  nonzero counts use integer labels (`1`, `2`, …) matching Backtest View C.
- Thin samples are marked with `sample_warning` and hidden by default in the UI;
  analytics summaries themselves remain unfiltered.
- Sorting many combinations by total R invites selection effects; treat the
  tables as research diagnostics, not proof of future edge.

### 5f) Stage 6 UI and Persistence — opt-in level controls (Levels page)

- The Levels page (`pages/2_Levels.py`) exposes an **"Advanced opt-in levels"** expander below the existing profile settings.
- Inside the expander: checkboxes for confirmed pivots, developing session VWAPs (`dVWAP_RTH` + `dVWAP` + `wVWAP` + `mVWAP`), TPO 30m Single Prints, APOC / pAPOC, and previous 30m VWAP; all default `True` in the built-in Levels page configuration.
- `thesistester/levels/defaults.py` also sets the shared headless API defaults: 15-minute opening range; SMA 50/200 and EMA 9/21 on `1min`/`5min`/`30min`; rolling VWAP `30min`/`4h`; rolling POC `30min`; 70% value area; and prior day/week/month profile aggregation of 4/8/10 ticks.
- When pivots are enabled, pivot timeframes (multiselect), pivot left, and pivot right number inputs are shown.
- `session_vwap_anchor` is fixed to `"RTH"` for the RTH column gate; full-session `dVWAP` / `wVWAP` / `mVWAP` are emitted alongside when the session-VWAP gate is enabled.
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
  are tick Last×Volume VAP joined via `map_shifted_prior_profile` (`shift(1)`
  on the 1m frame's unique period keys; scalars come from the tick table).
  A prior period with no ticks is `NaN` — the join does not fill from an
  earlier present table row. They are **absent** when no tick table is
  supplied. The same shift guarantee holds: future ticks cannot change an
  earlier bar's prior VA.
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
- `wVWAP` accumulates all bars in the current trading week (`W-SUN` on
  `trading_session_date`, same key as `wOpen`) using a causal cumulative sum.
  ETH and RTH bars both contribute and emit. Appending future bars cannot
  retroactively change any prior bar's value. Resets at each new trading week.
- `mVWAP` accumulates all bars in the current trading month (`M` on
  `trading_session_date`, same key as `mOpen`) using a causal cumulative sum.
  ETH and RTH bars both contribute and emit. Appending future bars cannot
  retroactively change any prior bar's value. Resets at each new trading month.
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
- Prior day/week/month VAH/VAL/POC (`pdVAH`/`pdVAL`/`pdPOC`, `pw*`, `pm*`) are
  tick Last×Volume VAP when `dataset.tick_paths` (or a persisted prior-profile
  table) is provided, and **absent** otherwise. They are not 1m typical under
  these names.   Named-VA studies refuse without ticks (`VA requires ticks`).
  Attach Quantower Tick–Tick–Last files on Data (path helper) or Studies
  Build (`dataset.tick_paths`); classic Calculate does not read Data-page
  attach. 15s remains the bar clock. New drafts omit the key.
  APOC and rolling POC remain 1m typical `(H+L+C)/3`. Product day aggregation
  is 1 tick (`prior_day_profile_aggregation_ticks`); week/month stay 8/10.
  `LEVEL_ENGINE_VERSION` is 11. Residual vs Quantower on the session-20 MNQ
  desk fixture is ~2–3 points at 1-tick (not a transferability claim).
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
- `dVWAP_RTH`, `dVWAP`, `wVWAP`, and `mVWAP` use bar-level typical price `(H+L+C)/3`. True intrabar
  VWAP would require tick data. Since signals are treated as bar-close confirmed,
  this is documented intent, not a bug. Do not confuse `wVWAP`/`mVWAP` with prior-period
  references (`pwOpen`/`pmOpen` / hypothetical `pwVWAP`/`pmVWAP`).
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
  The Studies Build tab always emits `dataset.format_profile` from that same
  allow-list (omitted / blank → `canonical`; unknown non-blank tokens fail
  emit). Omitting the key is no longer a builder path; CLI YAML that still
  omits it keeps the runner default `canonical` until re-emitted.
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
  `results_qa`) on hash-verified evidence.   **RQ-2** adds ephemeral
  `results.projections.*` grid/time rankings (empty bundle grid tables fall
  back to packet `best_grid_result`; unknown ranking-metric names are
  sanitized via the aggregate/directional allowlist preference chain and
  synced into the ephemeral metric-source path; JSON-null all-wins profit
  factors rank as +inf; projection `best` pins packet `best_grid_result`
  when re-rank disagrees; bundle table load failures warn via
  `bundle_tables_warning` instead of mimicking an empty grid; time bucket
  column falls back from `entry_rth_segment` to `entry_30min_bucket` /
  `entry_hour_bucket` when the preferred key is absent or has no usable
  label; cited `HH:MM` clock labels ground matching clock spans as wholes)
  and optional RO `TIME.analyze` enrichment when
  `assistant.results_qa.allow_time_enrichment=true` (default `false`).
  **RQ-3** ships documentation-grounded Help (`handle_help_turn` /
  `product_help`) over the §7.1 corpus + registry digest; run-performance
  questions remediate to Discuss results (no fabricated metrics). Help digit
  tokens must match number tokens in attached corpus/registry text.
  **HC-series (complete; HC-5/HC-6 maintenance):** feature/how-to Help coverage is
  USER_GUIDE-backed via RQ §7.1.4 (`docs/USER_GUIDE.md` + `HELP_CORPUS_MANIFEST`),
  including dedicated H2s for **Exposure policy**, **Intrabar resolution**,
  **Exit management**, **Session close and entry cutoff**, and **Focus vs Admit**
  (so Help does not depend on this file’s oversized Verified-engine mega-H2);
  frozen acceptance bank and parity gates live in
  `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` / `tests/test_assistant_help_coverage.py`.
  **RQ-4** binds classic Discuss via companion session key
  `classic_focus_channel="results_qa"` beside string `classic_focus_run_id`
  (never a dict).   **RQ-5** freezes honesty/injection evals in
  `tests/test_assistant_llm_evaluations.py` (missing evidence, uncited
  numbers, WFA caveat merge + OOS anti-soften, pipeline injection, draft
  isolation, corpus allowlist, provider-key remediation, offline deterministic
  Explain, registry audit).
  **DI-series (complete — DI-0…DI-3):** `docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md`
  keeps RQ digit/path honesty fail-closed while recovering Discuss UX.
  **DI-1 landed:** TLS allowlist wrap in `llm.py`; one repair retry;
  deterministic KPI/overview fallback with negative-cue veto against topic
  swap; §5.3 structured remediation when fallback does not apply; settings
  `repair_retry_enabled` / `deterministic_overview_fallback` (defaults
  `true`).   **DI-2 landed:** first-pass `path_catalog` (existing paths; plus
  overview `kpi_allowlist`) constrains claim paths without loosening the
  auditor. **DI-3 landed:** overview/KPI replies append a strictly digit-free
  expert overlay after mandatory caveats (no new run digits; no trade advice).
  Defaults change recovery UX; the auditor stays identical. DI must
  not invent metrics, alias arbitrary wrong paths onto lookalike leaves,
  serve KPI slices for vetoed specialist asks, amend the RQ auditor, or
  persist ungrounded drafts.
  **RI-series (continuation):**
  `docs/RESEARCH_INTELLIGENCE_IMPLEMENTATION.md` adds fail-open specialist /
  single-metric / meaning / mixed-ask slices while keeping the RQ auditor
  identical. **RI-1 landed:** unified `match_discuss_intent` + residual DI
  veto; deterministic `grid_ranking` builder / missing-grid short-circuit;
  `deterministic_specialist_fallback` (default `true`). **RI-3 landed:**
  `validation_wfa` builder / missing-validation short-circuit; validation/WFA/OOS
  cues sunset from residual; never substitutes `trade_summary` as OOS proof;
  mixed asks compose via RI-8 when ≤3 landed intents match.
  **RI-2 landed:** deterministic `time_ranking` builder / missing-time
  short-circuit; time/hour/bucket/clock/session-segment cues sunset from
  residual; no invented clocks; projects from `time_grouped_summary` when
  ephemeral `time_rankings` are absent or incomplete, syncing into the turn
  evidence packet before catalog/LLM audit (no new TIME.analyze).
  **RI-4 landed:** deterministic `single_metric` one-claim router over frozen
  §4.5 noun→path map; value-collocate required (bare nouns unmatched); hard-refuse
  when specialist/residual collocates present (no OOS→IS laundering); missing-leaf
  short-circuit before LLM.
  **RI-7 landed:** digit-free meaning overlay v2 (`build_expert_overlay` /
  `build_meaning_overlay`) for overview + grid/time/validation/single-metric
  replies; glossary lines for cited paths only (honesty/scope glosses preferred
  under the gloss cap); OOS-absent coaching suppressed in overlay caveats and
  specialist/mixed followups when packet caveats/limitations **or** cited
  `oos_status`/`stitched_oos_status` is missing/failed; overlay audited with
  `allowed=set()`; no LLM paraphrase.
  **RI-8 landed:** `mixed_ask` → `compose_deterministic_replies` (§4.7);
  priority-ordered summaries; merge/dedupe caveats; followups for unanswered
  topics; auditor once; compose ≤3 intents (>3 → narrow remediation).
  **RI-5 landed:** `robustness_tier2` presence-first builder over frozen §4.6
  paths (Monte Carlo / overfitting / sensitivity / noise / portfolio / OTF);
  MC + `otf validation` / `otf-validation` sunsets from residual; missing-all
  short-circuit before LLM; hard-reject undeclared nested dumps via catalog +
  decode allowlist; never substitutes `trade_summary` KPIs.
  **RI-6 landed:** `assumptions_costs` builder over frozen §4.6 cost/exposure/
  intrabar/focus/instrument/dataset paths; missing-all short-circuit before LLM;
  hard-reject performance KPI substitutions; no Help how-to ownership;
  configured SL/TP + singular cost/assumption cues; OOS-absent missing followups.
  **RI-9 landed:** `deep_trade` builder over capped ephemeral §6 projections
  (`exit_reason_counts` top N≤12 + other, `extreme_trades` N≤5 best/worst,
  `streak_summary`); trade tables load into turn context only (never raw frames
  to the model); exit/extreme asks missing tables short-circuit before LLM even
  when streak scalars exist; digit-bearing exit labels skipped; hard-reject
  undeclared / KPI paths via catalog + decode allowlist.
  **RI-10 landed (series complete):** duplex `get_run_overview` projects shared
  RI builders into specialist/mixed envelopes (no cue fork); pure overview keeps
  DI KPI envelopes; permanent residuals (bare stop/ranking/monte) stay veto ≠
  unmatched; deep-trade duplex hydrates streak scalars from packet
  `trade_summary` and topic-scopes exit/extreme/streak like text Discuss —
  exit/extreme tables still require trade rows in turn context (packet-only
  duplex returns a limitation, not KPI topic-swap); voice default remains off.
  RI must not invent metrics, remap topics onto KPI overview, answer OOS asks
  with in-sample single-metric leaves, soften OOS/selection-bias caveats, or
  touch engine/golden paths.
  **DX-series:** `docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md` targets VA-5
  full-duplex **content** parity with DI overview/KPI intelligence by reusing
  DI builders inside VA-3 tool envelopes + realtime instructions. DX does not
  switch providers, does not pre-gate live PCM, and does not call
  `propose_results_reply` on every duplex turn; text Discuss and VA-4 PTT
  remain the strongest typed-recovery paths. **DX-1 landed:**
  `has_overview_negative_cue` export; `get_run_overview` projects DI
  deterministic KPI/overview replies (claims policy A; veto strips legacy
  explainer `overview`/`claims`; unmatched / no-text → neutral
  `run_overview`); sample-size intent alias →
  `results.trade_summary.trade_count`; speakable prefers DI `summary` (+
  digit-free `expert_overlay`). **DX-2 landed:** realtime/results
  `build_honesty_instructions` appends the frozen §4.3 duplex overview
  constraint needles (prefer `summary`/`kpi_claims`/`expert_overlay`; forbid
  inventing `results.trade_count` / `results.instrument` /
  `results.validation.trade_count`; no KPI-overview topic swap for
  walk-forward/validation/ranking/time). PTT and Help instructions unchanged.
  **DX-3 landed (series complete):** §9 characterization frozen in
  `tests/test_assistant_duplex_intelligence.py`. Shipped limitation: live PCM
  is still not pre-gated; content parity is via tool envelopes + instructions;
  the tool-before-transcript race may still return a neutral overview envelope
  (DX-2 needles + durable transcript audit are the backstop). Voice default
  remains off.
  Thesis switches clear mode-scoped chat_input widget keys and other
  thesis-scoped staging. Draft-chat history
  excludes `results_qa` / `product_help` turns and tool/audit lines so
  multi-turn Discuss/Help cannot starve thesis context.
- LLM explanations must cite packet paths; uncited numerical tokens are rejected
  before render. Cited claim values may be int/float or pure numeric strings.
  Cited `HH:MM` / `H:MM` clock bucket labels ground matching clock spans in
  narration as wholes without allowlisting component digits (so citing
  `"08:30"` does not launder bare `8` / `30`); hash/path/column-name strings
  do not launder digits. Fractional rates accept `%` (including spaced `60 %`)
  or word-form (`60 percent` / `60 pct` / `60 Prozent` ↔ `0.6`); bare `60` is
  not inferred from `0.6`. European decimal commas in narration (`0,25`)
  normalize to the cited float `0.25` as one token (component digits are not
  allowlisted); classic thousands groups (`25,000`) are not treated as decimals
  and cannot launder a smaller cited integer. Clock-like `H:MM percent` text
  does not rewrite minutes into a synthetic percent token. Results Q&A claim
  paths are relative to the evidence packet
  root; accidental leading `evidence_packet.` / `packet.` prefixes are stripped
  repeatedly, and JSON array indices are supported
  (e.g. `results.time_grouped_summary.0.avg_r`). When provenance
  includes a fingerprint, dataset identity is available at
  `assumptions.dataset.dataset_fingerprint` (and mirrored at
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
  Duplex overview/KPI **content** parity with Discuss intelligence is under
  DX (`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md`) and must not reopen VA
  transport freezes or DI auditor rules. **DX-1 landed:** sample-size voice
  intent aliases target the DI baseline leaf
  `results.trade_summary.trade_count` (not the distinct `results.trade_count`
  leaf). **DX-2 landed:** realtime/results honesty instructions include the
  frozen duplex overview constraint needles. **DX-3 complete:** §9 eval freeze
  in `tests/test_assistant_duplex_intelligence.py`; live PCM remains
  post-utterance (not pre-gated).

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

## Research Study Runner execution lock (RS3)

- Concurrent `study run` processes on the same `output_dir` fail closed on
  `.study.lock` (POSIX `fcntl.flock` or Windows `msvcrt.locking`). The lock is
  advisory and released when the process exits; a crashed run does not leave a
  stale lock file that blocks later runs. Opening the Studies viewer does not
  acquire the lock. RS-D9 CLI-spawn from the Studies page also does **not**
  acquire `.study.lock` in the Streamlit process — the child `study run` holds
  it.
- Inspect **ledger progress** is cell-status counts
  (`ok` + `failed` + `skipped` over `run_count`), not a quality metric, ETA,
  or validated edge. A ledger-only view (readable `study.ledger.json`, missing
  `results_index.csv` file) shows that progress without ranked / OTF overview.
  A present but unreadable or invalid index is still an Inspect error.
- Study cells use `cache_policy=read_write` and fsync published artifacts.
  On Windows, file `fsync` uses a writable handle (`FlushFileBuffers` rejects
  `O_RDONLY` with `EBADF`). A remaining fsync or close OS error is skipped; the
  atomic publish still proceeds. This is durability best-effort, not a failed cell.

## Research Study Runner ranking (RS4)

- Study overview ranking (`study.overview.md` / ranked CSV rows) is a
  **descriptive multi-cell screen**, not a validated edge. Large closed
  factorials create severe multiple-testing bias: the top cell is a sample
  extreme under the study design, not independent confirmation.
- Cells with `trade_count < study.report.min_trades` are listed under low-N
  and excluded from the ranked section. Meeting `min_trades` is a sample-size
  filter only — not statistical significance. Ok cells that meet `min_trades`
  but lack a resolvable primary metric are listed under unresolved primary.
  Index-only orphans (`factors_joined=False`) are never ranked or crowned.
- OTF Δ rows (`study.otf_delta.csv`) compare metric(OTF variant) −
  metric(`report.otf_baseline`) for matched non-OTF factor tuples. They inherit
  the same multiple-testing caveats; a positive Δ is not proof that OTF adds
  edge.
- `multiple_testing: warn` (default) still crowns a “top descriptive cell” in
  Markdown with explicit caveats. `multiple_testing: error` suppresses that
  crowning; the ranked table remains descriptive only.
- Prefer stage-first expansion, human-confirmed promote (RS5), held-out /
  walk-forward evaluation, and non-zero `commission_per_side` /
  `slippage_ticks` before trusting expectancy ranks.
- Study execute does not change R18 `run_batch` semantics; overview join does
  not invent new inference.

## Research Study Runner diagnostic rollup (RS-D4)

- `study rollup` writes `study.rollup.csv` / `study.rollup.md` by **composing**
  existing per-cell index WFA columns and bundle members
  (`walk_forward_meta.json`, `validation_summary.json`,
  `overfitting_summary.json`). It does **not** compute cross-cell / pooled PBO,
  DSR, or CSCV, and it does not auto-enable batteries.
- Default study emission keeps `grid` / `validation` / `walk_forward`
  `enabled: false`, so most MVP cells show battery status `not_run` with null
  diagnostic columns — that is expected, not a bug.
- R15 `overfitting_summary` / `cscv_pbo` require **grid cell trade sequences**.
  After promote, humans may opt into survivor-stage constants with explicit
  `enabled: true` flags (never bare `{}`), for example:
  - `walk_forward.enabled: true` (with fold sizes), and/or
  - `grid.enabled: true` **and** `validation.enabled: true` **and**
    `validation.overfitting.enabled: true`
    (`run_experiment` skips the whole validation block — including overfitting —
    when the parent `validation.enabled` flag is false)
  before expecting dense overfitting columns in the rollup.
- Rollup markdown is descriptive only: present diagnostics ≠ validated edge.

## Studies Inspect listing, quality panes, charts, and cell peek (SV1–SV5 shipped)

- The Study Viewer catalog (`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`, SV1)
  **lists** local study directories under `results/studies/` and `out/`.
  Listing is discovery, not a quality score. Ledger `ok` / `failed` counts
  remain cell-status, not edge.
- Failed-cell `error` text, `report.group_summaries`, and a present
  `study.rollup.csv` are projections of artifacts the runner already wrote.
  They are not a quality score or a validated edge. Missing rollup is a
  caption pointing at CLI `study rollup`, not an Inspect error.
- Overview charts (SV3) plot frames already produced by `report_study`
  (ranked / group summaries). They inherit the RS4 ranking caveats above:
  descriptive screen, `min_trades` filter, multiple-testing bias. Charts
  must not invent new inference (no pooled PBO/DSR, no unzip-all-cells
  equity). Empty ranked / group frames show a caption, not placeholder zeros.
- Inspect must not rewrite `study.overview.*` or call `study rollup` (that
  CLI writes files). Showing `study.rollup.csv` only when the file already
  exists does not create diagnostics.
- Cell peek of `trade_summary.json` is the same per-cell summary already
  used for PF/WR fallback — not a validated edge and not a classic-session
  import. Full trade/equity charts stay Research Bundles upload/import.
- Study briefing (SV5) names the highest primary-metric cell plus factor
  settings, per-cell best SL/TP, and the strongest NY RTH segment on that
  cell's completed trades. It is a descriptive screen, not a live schedule
  and not a validated edge. Time-of-day is **not** a StudySpec factor (a
  7-bucket cartesian would multiply cells and overfit). Constrain the next
  run with Admit (`constants.backtest.entry_window`, and `grid.entry_window`
  when grid is present) after inspecting the bucket. Setup-only
  `constants.entry_window` does not constrain `run_backtest`.
  `study promote --admit-tod auto` (SAF1) stamps those engine paths and
  writes `study.lineage`; it does not execute. Inspect **Draft Admit
  follow-up** (SAF2) writes Preview YAML only; it does not execute or
  rewrite parent overview artifacts. `--tod-group` / `--allow-thin` (SAF3)
  are CLI-only; thin drafts set `lineage.admit.thin`. A follow-up Admit run
  is a constrained re-sim of one parent cell, not confirmation of the
  parent screen. Focus ≠ Admit.
- Ranked cells are the factor cartesian. The SL/TP grid is per-cell inside
  each research zip (`grid_results.parquet` / `best_grid_*` index columns).
  Missing Best SL/TP usually means `grid.enabled: false` or no grid row met
  the cell's grid `min_trades`.

## Study Observatory (SO — SO1 shipped)

- The Study Observatory (`docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md`) is
  a corpus projection of artifacts the runner already wrote. SO1 ships the
  compiler + `study observatory` CLI; the Streamlit page is **not** shipped
  (SO2). Listing every local study cell is discovery, not a quality score.
- Sorting many cells by expectancy / profit factor / win rate is the same
  multiple-testing screen as RS4, now across studies. A comparability cohort
  (instrument, dataset, costs, SL/TP, trigger, width, flatten,
  confluence_mode, min_valid_confluences, exposure_policy) is required
  before treating a sort as even a descriptive rank. Breaking the lock is
  explicit and must be labeled.
- Program B `desk_class` / ΔE vs Wave 0 (SO3) are named overlays of the
  operator runbook, not a new primary metric and not Admit. `desk_class`
  must cover the runbook split (`plus_e` / `hold` / `dead` / `noisy` /
  `unidentified`) plus `failed` / `other`. ΔE looks up `progB_w0_solo`
  or `progB_w0_va` by core; it mixes confirm value with zone-shape
  (point vs partner box).
- Observatory must not unzip every cell or rewrite `study.overview.*`.

## Practical interpretation
- With default settings, expectancy remains equivalent to prior gross outputs.
- With non-zero cost settings, expectancy and downstream KPIs become net-of-cost.
- Treat results as **screening diagnostics, not proof of edge**.
