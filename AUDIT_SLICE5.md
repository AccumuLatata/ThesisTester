# ThesisTester audit Slice 5 — Analytics / Focus / Validation / WFA

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390), Slice 1 (`AUDIT_SLICE1.md`, PR #391), Slice 2 (`AUDIT_SLICE2.md`, PR #392), Slice 3 (`AUDIT_SLICE3.md`, PR #393), Slice 4 (`AUDIT_SLICE4.md`, PR #394). Prior **locked contracts** are treated as given; fill internals, 3c 4-rule math, and `trading_session_date` arithmetic were not re-audited except where analytics **consumes** those rows / clocks.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/test_phase5_metrics.py`, `test_institutional_metrics.py`, `test_phase8_validation.py`, `test_overfitting.py`, `test_excursions.py`, `test_monte_carlo.py`, `test_portfolio.py`, `test_entry_window_sw4.py`, `test_entry_window_sw5.py`, `test_entry_window_sw6.py`, `test_prev30m_vwap_hit_analytics.py`, `test_walk_forward.py`, `test_phase7_time_analysis.py`, `test_confluence_attribution.py`, `test_otf_validation.py`, `test_session_focus.py`, `test_entry_window_admission.py`, `test_phase6_grid.py` — **327 passed**.
**Runtime probes (not committed tests):**
- Session-fold keys vs calendar date on ETH overnight bars (`Mon 17:00` / `Mon 18:30` / `Tue 02:00`): folds group by `trading_session_date(..., eth_start="18:00")`, not `dt.date`.
- `causal_prefix` on those session folds: source is `df.iloc[:fold_end_exclusive]`; last prefix timestamp is strictly `<` first fold bar; post-fold bars excluded. `None` → `fold_local`; invalid policy raises.
- OTF validation matrix: last **train** signal simulated on the **full** frame takes TP on an OOS-period spike (`exit_bar_index=14`, `r_multiple=10`); the same signal on a train-sliced frame exits `EOD` at the slice end (`r=0`). Matrix `train_expectancy_r` reports the full-frame (OOS-path) number.
**Goldens:** not used as correctness proof. Identity / drift gates do not prove metric formulas, Focus≠Admit divergence, WFA session+ETH+prefix, or battery honesty.

This file is the Slice 5 deliverable. Later slices must treat the **locked contracts** in §5 as given, and the **open items** in §6 as still unverified outside this layer.

---

## 0. Contracts used here (not re-proven)

### From Slice 4 (locked)

1. Two composers: UI Backtest/Grid call the engine directly; `api.run_backtest` / `run_grid` are headless; `run_experiment` passes the **levels** frame. Pages do not call `api.run_backtest`.
2. OTF is admission, default off. `T = trigger_timestamp` else `timestamp` (filled 3c: reversal, not fill). HTF usable iff `availability_timestamp <= T`. TFs: 5/15/30m only. Session reset: `trading_session_date` + `eth_start`. Disabled ≠ passed.
3. WFA OTF (verify, do not reinvent): default `fold_local` = fold OHLCV slice only; `causal_prefix` = `df.iloc[:fold_end]` with prefix **strictly before** fold start; only fold-local signals scored; bars after fold end never used; `None` → `fold_local`; invalid policy raises; short fold → unknown reject. Grid OTF once, not per cell.
4. Fills: simple next-bar open; 3c filled retrace; 3c void no fill no skip row. Residual `confirm_3bar` still fills if handed in.
5. Admit: entry-bar local time (C2). `None` and `{enabled:False}` identical. Focus is **not** `simulate_trades` (C8).
6. Costs default zero. `pnl_currency` / `r_multiple` are NET; `pnl_points` is GROSS; `stop_price` = initial risk.
7. Exposure default `allow_all`. Independent overlapping fills. Skip-frame is **not** all non-fills.
8. R12: no upsample. Same-sub-bar SL+TP → SL. `sl_first` does not clip to post-entry on 3c. MAE/MFE are full-parent extremes. R10 `both_hit_rule` ≠ selected R12 model.
9. R13 opt-in; commit after completed bar; active next bar.
10. Session flatten is calendar-RTH and leaky (`entry_local_ts`). Do **not** treat `SESSION_CLOSE` as `trading_session_date` close. Do not assume flatten trades are per-entry-date until the leak is fixed.
11. Goldens ≠ correctness.

### From Slice 1 (clocks)

`session` ≠ `trading_session_date`. Time Analysis RTH segments are wall-clock 09:30–16:00 ET (`entry_window_policy.RTH_SEGMENTS`). Flatten is same-calendar-day RTH-style.

---

## 1. Architecture of the analytics layer

### 1.1 What this layer owns

This layer turns **completed trades** (plus, for WFA / grid / OTF-matrix / noise / sensitivity, a **re-sim** of the already-locked engine) into:

- KPI summaries and subset-replay equity (Focus, Time Analysis, portfolio)
- in-sample grid ranking
- walk-forward folds + stitched OOS + session-count matrix
- Phase 8 / R10–R16 / R19 / R21 batteries
- post-trade combo / prev30m hit diagnostics

It does **not** generate signals, compute levels, or change fill/OTF/Admit math.

```text
trades (+ skipped_signals / otf_rejected / entry_window)   ← consume only
        │
        ├─► metrics.summarize_trades / equity_curve          (r_multiple NET)
        ├─► Focus: filter_trades_by_entry_window(entry_timestamp)
        │         + subset-replay summarize/equity           (NO simulate_trades)
        ├─► Time Analysis: add_time_buckets (calendar / RTH clock)
        ├─► Grid: run_sl_tp_grid → simulate_trades per cell; rank in-sample
        ├─► WFA: slice OHLCV + signals per fold; OTF per phase (not per cell);
        │        train grid → best_grid_result; test simulate on test_df only
        ├─► validation / MC / overfitting / noise / sensitivity / excursions
        ├─► OTF matrix: apply_otf_filter on full df; sim train/OOS on full df
        ├─► combo attribution / prev30m hit: join completed trades
        └─► portfolio: stitch + overlay exposure; metrics on admitted
```

### 1.2 Two compute styles (do not conflate)

| Style | Modules | Re-sim? |
|---|---|---|
| **Post-hoc on completed trades** | `metrics`, `entry_window` (Focus), `time_analysis`, `validation` (bootstrap/permutation/count), `excursions`, `monte_carlo`, `confluence_attribution`, `prev30m_vwap_hit`, `portfolio` (stitch) | No |
| **Re-sim under locked engine** | `grid`, `walk_forward`, `otf_validation`, `overfitting` (grid replay / vs-random), `noise`, `sensitivity` | Yes — same `simulate_trades` |

Focus is the first style. Admit / WFA test / OTF-matrix sims are the second.

### 1.3 What Focus consumes (and does not)

`summarize_focused_trades` (`entry_window.py`) filters **`trades`** by `entry_timestamp` (default) or an explicit `timestamp_col`. It does **not** read `skipped_signals`, `otf_rejected_signals`, or `otf_filter_summary`. Silent non-fills (3c void, missing entry bar, empty flatten cap — Slice 4) never appear in Focus counts. Skip-frame length is **not** “all non-fills.”

---

## 2. Must-answer questions

### Q1. Focus copy implying path DD / re-sim? Does Focus use `entry_timestamp`? Under non-`allow_all`, does it over-state?

**Copy is honest about post-hoc / subset-replay. Membership is `entry_timestamp`. Under restrictive exposure it over-states constrained-path counts; UI says “all-day run” but does not say “trade count may exceed Admit.”**

Canonical strings:

| Location | Quote |
|---|---|
| `entry_window.py` `FOCUS_HONESTY_BANNER` | `"Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."` |
| `entry_window.py` `FOCUS_EQUITY_CAVEAT` | `"Equity/drawdown rebuilt from the filtered trade subset only (subset replay)."` |
| `pages/9_Time_Analysis.py` L4–5, L305–308 | Page: no re-sim; subheader `"Focus summary (post-hoc)"` |
| `reporting.py` L205–206, L1038–1039 | `"Focus is a post-hoc subset — not proof of deployable edge."` |
| `ASSUMPTIONS` §4a | Focus does not call `simulate_trades`; equity is subset replay, not path DD |

**Membership:** `filter_trades_by_entry_window` defaults `timestamp_col="entry_timestamp"` and uses `entry_window_contains` / `entry_rth_segment` from that timestamp. Time Analysis pins `_FOCUS_TIMESTAMP_COL = "entry_timestamp"` and rebuilds Focus options via `entry_focus_bucket_values(..., timestamp_col="entry_timestamp")` even when the chart basis is `exit_timestamp` (caption at L334–338). Exit time is used only **after** filter, to sort subset equity (`metrics.summarize_trades` / `equity_curve`).

**Equity/DD:** `summarize_focused_trades` → `summarize_trades(focused)` + `equity_curve(focused)` + `subset_replay_equity=True`. No `simulate_trades`. C8 tested in `test_session_focus.py`.

**Over-state under non-`allow_all`:** locked and still true. C7 identity is tested **only** under `allow_all` + `cooldown_bars_after_exit=0` (`test_c7_focus_equals_admit_under_allow_all`). Plan / ASSUMPTIONS: divergence under other policies is expected. Mechanism: Focus filters completed **all-day** fills; Admit re-sims with the window **before** exposure. Bad case: `single_position` admits an out-of-window trade A that blocks in-window B; Focus on the in-window bucket still shows other in-window fills that existed only because A occupied the slot. Banner mentions exposure/cooldown reflecting the all-day run; it does **not** say Focus trade count can exceed Admit. `docs/research-methodology.md` has **no** Focus/Admit section (OTF protocol only).

Minor ambiguity (low): `"Recompute the full Performance Summary"` on Time Analysis can be read as a full re-run; adjacent post-hoc copy mitigates.

### Q2. WFA session off-by-one / stitch leak? `causal_prefix` strictly before fold start on session folds? `fold_local` vs `causal_prefix` honored?

**Per-fold construction is leak-safe. Session folds key by `trading_session_date` + `eth_start`. Prefix `<` fold start holds on session folds (probed). Policies honored. Residual: overlapping-fold **summary** double-count; stale doc/comment; session+ETH+prefix under-tested.**

**Session folds** (`walk_forward._session_fold_boundaries`):

```320:346:thesistester/analytics/walk_forward.py
    session_ids = trading_session_date(timestamps, eth_start).astype(str)
    ...
    train_end_exclusive=session_ranges[train_ids[-1]][1],
    test_start=session_ranges[test_ids[0]][0],
```

Not clock `session`, not calendar flatten. Contiguous-index check fails closed (L327–328). Half-open: train `[train_start, train_end_exclusive)`, test `[test_start, test_end_exclusive)`.

**Probe (ETH overnight):** bars `Mon 17:00` (tsd `2026-01-05`), `Mon 18:30` + `Tue 02:00` + `Tue 10:00` (tsd `2026-01-06`). Fold 0 test is bars `[1,4)` — all three `2026-01-06` session bars, spanning **two calendar dates**. Calendar `dt.date` grouping would have split `Mon 18:30` from `Tue 02:00`. Contract met.

**`causal_prefix` on session folds:** `_otf_source_for_fold` is fold-mode-agnostic. `fold_local` → `df.iloc[fold_start:fold_end_exclusive]`; `causal_prefix` → `df.iloc[:fold_end_exclusive]`. Prefix bars are indices `[0, fold_start)` — strictly before fold start. Probe: fold 0 test start bar 1 (`Mon 18:30`); last prefix `Mon 17:00` `<` first fold bar; source length `== fold_end_exclusive`; last source bar is last fold bar. Post-fold bars never included.

**Policy normalize:** `None` → `fold_local`; non-str / unknown → `ValueError`. Short / unusable fold source → all candidates `unknown` reject (`_filter_fold_signals_with_otf`). Grid/WFA OTF applied **once per train/test phase**, not per SL/TP cell.

**Stitch / ownership:** session mode sets `executable_entry_ownership=True` so simple signals are owned by **fill** bar (`bar_index+1` / `entry_bar_index`). Remapped `bar_index` can be `-1` when the trigger sits in the previous session; `simulate_trades` then uses `entry = bar_idx+1 = 0` and **does not** `iloc[-1]` the trigger bar (Slice 4 fill contract: simple next-bar open). 3c validity requires remapped `entry_bar_index` inside the slice. Not a stitch leak for public triggers.

**Train vs test OHLCV:** `train_df = df.iloc[train_start:train_end_exclusive]`, `test_df = df.iloc[test_start:test_end_exclusive]`; `simulate_trades` on `test_df` only after `best_grid_result(train_grid)`. Subtimeframe clipped to fold timestamps. Bars after fold end cannot affect that fold’s path (DATA_END at slice end).

**Not leak-safe (interpretation):** `summarize_walk_forward` **sums** every valid fold’s `test_total_r` / `test_trade_count` even when test windows overlap (`step_sessions < test_sessions`). Stitched equity is deduped / rejected (`overlap_policy`); headline aggregates are not. UI overlap help mentions stitched equity only.

**Stale comment / doc:** `run_walk_forward_sl_tp` L622–623 says “using only their respective OHLCV slices” while L631–643 apply the configurable policy. `docs/otf-filter.md` L673–676 is correct; L696–697 still says train/test OTF use “only the training/test OHLCV slice,” which is false under `causal_prefix`. `POINT_IN_TIME_GUARANTEES.md` L228–235 matches code.

**UI WFA:** `pages/10_Validation.py` forwards instrument `eth_start` and exchange TZ (L517–520, L680–687). Policy selectbox help is accurate (L349–352). Caption: `"Diagnostic only — walk-forward can still overfit."`

### Q3. `both_hit_rule` vs R12 labeled independent?

**Independent in ASSUMPTIONS + glossary structure. UI/export name the rule but do not say it is not the selected R12 model.**

- Computation: `excursions.py` default `both_hit_rule="stop_first"`; caveat names the rule and “cannot prove intrabar event order.” MAE/MFE are terminal / full-parent (Slice 4).
- `ASSUMPTIONS` L124–125: *“R10 excursion calibration remains a separate terminal-excursion diagnostic. Its `both_hit_rule` does not inherit or replay the selected R12 engine model.”*
- `METRICS_GLOSSARY.md` R10 calibration vs later “R12 intrabar diagnostics” are separate sections; calibration text says “not executable counterfactual backtests.”
- UI (`pages/10_Validation.py` L1166–1167, L1216–1220): “terminal bar-level… not intrabar path order”; selectbox describes classification only. **No “≠ R12” sentence.**
- Report (`reporting.py` L1505–1513): diagnostic banner + `Calibration both-hit rule: …`. **No R12 independence line.**

**Bad case:** user sets R12 `path_open_proximity` / `target`-favoring model while R10 stays `stop_first`. Calibration `P(target)` disagrees with engine ambiguity resolution; UI never warns.

### Q4. Grid / WFA test-sample peek (train selection using test metrics)?

**Per-fold WFA SL/TP: no peek (verified + tested). Plain grid: in-sample by design. WFA matrix: ranks cells by OOS summary (documented methodology hazard). OTF validation matrix: ranks by `train_expectancy_r`, but that expectancy is simulated on the full frame and can include OOS-bar P&L — this is the computational leak.**

| Surface | Selection input | Peek? |
|---|---|---|
| `best_grid_result` on page 8 | Full-sample cell metrics | In-sample optimization (no hidden holdout) |
| WFA `run_walk_forward_sl_tp` | `run_sl_tp_grid(train_df)` then `best_grid_result(train_grid)` | **No.** Test sim only after selection. `test_walk_forward_train_selection_has_no_test_leakage` |
| `run_wfa_matrix` | Default `matrix_metric="median_test_expectancy_r"` | **Meta-selection on OOS.** ASSUMPTIONS L565–567 warn; heatmap colorbar `"Median OOS expectancy R"` (`pages/10_Validation.py` L722) invites picking the greenest cell |
| `run_otf_validation_matrix` | `_add_train_ranking` on `train_expectancy_r` only | **Column-honest, path-leaky.** Train/OOS **signals** are split; both sims pass **full** `source_df` (`otf_validation.py` L270–275, L389–407) |

**OTF-matrix probe:** 10 touch signals, `train_fraction=0.7` → train ids 0–6. Price spikes only after the split. Last train signal on full df: `exit_reason=TP`, `exit_bar_index=14`, `r_multiple=10`. Same signal on `df.iloc[:8]`: `EOD`, `r=0`. Matrix `no_otf.train_expectancy_r = 10.0`. Train ranking therefore **sees OOS prices** via holding period. UI still says “train results drive ranking/selection only” (L1780–1781) and “selected by train_expectancy_r only” (L1930–1931). Tests assert ranking columns, not “train trades cannot exit after the split bar.”

WFA does **not** have this bug: test/train frames are sliced.

Grid page (`pages/8_Grid_Search.py` L280–286): ranking metric help is `"Metric used to find the best SL/TP pair."` No in-sample / multiple-testing sentence. Glossary recommends `min_direction_expectancy_r` for directional ranking; that is opt-in (toggle default off; when on, index 8).

### Q5. Metric formulas vs `METRICS_GLOSSARY`: expectancy, PF, DD, win rate; `pnl_points` gross vs net

**Core four match the glossary. Analytics does not treat `pnl_points` as net. `r_multiple` / `pnl_currency` are net (Slice 4).**

| Metric | Glossary | `summarize_trades` |
|---|---|---|
| Win rate | `#(R_i > 0) / n` | `len(wins)/n` with `wins = r[r > 0]` |
| Profit factor | 3-branch ratio / inf / 0 | L129–136 identical |
| Expectancy | `win_rate·avg_win + loss_rate·avg_loss`; fallback `avg_r` | L141–145 |
| Max DD | `cummax(cum_r).clip(≥0) − cum_r` | `_drawdown_series` |

Breakeven `R==0` rows sit in `n` but add 0 to both sides; the expectancy formula still equals `mean(R)` when both sides exist. Fallback `avg_r` is all-win / all-loss only.

`thesistester/analytics/` has **zero** `pnl_points` references. Grid/Focus/WFA/portfolio KPIs use `r_multiple`. Portfolio equity optionally cumulates `pnl_currency` (net). Zero default costs hide gross-vs-net (Slice 4).

`time_analysis.summarize_by_group` duplicates PF / win rate / DD (same branches, `exit_timestamp` sort for DD). Exposes `avg_r`, not `expectancy_r` — equal when both sides exist. No cross-module parity test.

Sharpe-like / Sortino-like are **not annualized** (glossary + ASSUMPTIONS). UI does not always repeat that next to the number.

### Q6. Bootstrap / permutation / trade-count: “diagnostic only” enforced in UI and exports?

**Computation is diagnostic (no holdout peek). Honesty enforcement is uneven: R10–R16 / OTF / portfolio have per-section banners + `caveat` fields; Phase 8 bootstrap/permutation/grid-overfit rely on the page caption and can read confirmatory in UI and markdown export. No API `diagnostic_only` flag.**

**Compute (no test peek):**

- Bootstrap: resample mean R; `probability_positive` = fraction of bootstrap means `> 0` (`validation.bootstrap_expectancy_ci`).
- Permutation: sign-flip; one-sided p = fraction of permuted means `≥` observed (`permutation_test_expectancy`). Docstring: sign symmetry; ignores serial dependence.
- Trade-count: `insufficient` `<30` / `limited` `<100` / `reasonable`; caution messages.

Caller usually passes **full backtest** trades. After a grid search this is a selected sample — no multiplicity correction.

**UI:**

| Battery | Per-section “diagnostic only”? | Confirmatory affordance |
|---|---|---|
| Page caption L37–40 | Yes (covers all) | — |
| Bootstrap | **No** | Metric label **`P(mean R > 0)`** (L1573–1577) |
| Permutation | Partial caption | **`st.success`** when `p≤0.05` (L1626–1629) despite “not a significance test” footnote |
| Trade-count | Status messages | Honest |
| Grid overfit | Heuristic warning | Not labeled diagnostic at section |
| WFA / R15 / R16 / R19 / R10 / R11 / OTF | Yes | R15 headlines “Deflated Sharpe **probability**”, “Vs-random p-value” above caveat; MC subheader “path **robustness**” |

**Export (`reporting.py` L1491–1496):** `## Validation Diagnostics` lists CI, `P(mean R > 0)`, permutation p, trade-count status, grid overfit risk — **no section banner**. Excursions / MC / noise / sensitivity / OTF **do** get banners. Global `_CAVEATS` exists later in the artifact.

**API `run_validation`:** Phase 8 `validation_summary` has **no** `caveat`. R10+ batteries include `caveat` strings. No machine-readable `diagnostic_only: true`.

Overfitting (R15): CSCV/PBO / DSR / vs-random on **in-sample** grid-selected sequences — **no WFA test peek**. Documented. Noise/sensitivity: no look-ahead in perturbation mechanics (subtimeframe pinned unperturbed).

### Q7. Combo attribution vs engine: invent fills or reuse `simulate_trades`?

**Reuses completed trades. Does not invent fills. Does not call `simulate_trades`.**

`confluence_attribution.py`: groupby on stamped `level_names` / `r_multiple` (engine copies `level_names` onto the trade at fill time). Module docstring: “No zone / signal / fill engine changes.” Honesty captions: observed combos only, not causal edge; membership/pair double-count warnings; hide-below-min default ON in Backtest UI.

**Not a fill leak.** Interpretation traps (nested sets, pair `total_r` not a PnL decomposition, directed Exact over usable-direction subset) are documented. Focus-aware `_display_trades` feeds the combo expander; the standalone 3c-variant block and prev30m block use full session `trades` (documented inconsistency, not look-ahead).

### Q8. prev30mVWAP_hit analytics: in-window NaN treated as 0?

**No. In-window NaN is ignored. The bracket’s last finalized `0.0`/`1.0` is attached via lookup. `0.0` means engine-finalized “no touch,” not missing.**

`build_finalized_hit_lookup`: `dropna()` then last value; else `np.nan`. No `fillna(0)`. `test_uses_finalized_hit_flags_not_in_window_nan`: entry at 18:30 while the levels row is NaN still gets finalized `1.0`.

Session key is ETH `trading_session_date` via `session_bracket_keys` — not Time Analysis calendar RTH, not flatten clock.

Does not invent signals. Scopes to `level_names` containing `prev30mVWAP` when the column exists; **if `level_names` is absent, all trades are analyzed** (fixture convenience). `trade_count` = rows with any finalized flag (`dropna how="all"`); grouped R / contingency also require non-null `r_multiple` — docstring claims one universe; counts can diverge if R is null. Backtest wiring uses full `trades`, not Focus `_display_trades`.

### Q9. Portfolio / time buckets: session vs `trading_session_date` mix? Low-sample warnings honest?

**Three clocks. Low-sample warnings exist but are not uniformly enforced.**

| Surface | Clock |
|---|---|
| Time Analysis `entry_date` / hour / 30m | Calendar date in `bucket_tz` |
| Time Analysis `entry_rth_segment` | Wall-clock RTH in `session_tz` (C1) |
| prev30m / WFA session folds / OTF reset | `trading_session_date` + `eth_start` |
| Engine `SESSION_CLOSE` (feeds all consumers) | Calendar date of leaked `entry_local_ts` (Slice 4) — **not** session-date close |

`add_time_buckets` **always** names columns `entry_*` even when `timestamp_col="exit_timestamp"` (docstring L186–188). Focus options stay entry-time. Exit-grouped table rows labeled `entry_rth_segment` are easy to misread. `api.run_time_analysis` defaults `timestamp_col="entry_timestamp"` (good) and is descriptive only.

**Low-sample:**

| Surface | Threshold | Enforcement |
|---|---|---|
| Time Analysis | default 10 | `sample_warning` flag; **all rows shown** |
| Focus provenance | default 10 | `sample_warning`; Promote confirm checkbox |
| Combo | default 10 | Hide-below-min **default ON** |
| Trade-count battery | 30 / 100 | Warning copy |
| Portfolio | none | No sample warning |

**Portfolio:** `tag_setup_trades` copies completed trades; `apply_portfolio_exposure` overlays a second gate; metrics/equity on **admitted**. Caveat: *“not a continuous capital, margin, liquidity, or fill simulation.”* UI caption matches. **Correlation matrices are computed on `candidates`, not `admitted`** (`portfolio_summary` L226). Under `single_*`, heatmap includes skipped overlaps; metrics do not. Page 13 shows the heatmap with **no** “pre-admission” caption. ASSUMPTIONS already warn: per-setup runs should be `allow_all` if portfolio applies a second policy (double exposure).

Slice 4 flatten leak: do **not** interpret exit-grouped `SESSION_CLOSE` clusters as per-entry-date or CME session close until the leak is fixed.

### Q10. Test gaps vs claimed contracts. Goldens ≠ correctness.

**Well covered:** metric formulas; C2 Focus entry vs exit; C7 under `allow_all`; C8 subset-replay flag; bar-mode WFA folds; train/test isolation (no OTF); OTF policy normalize / short-fold unknown / bar-mode `causal_prefix` future-shock; OTF matrix **column** ranking; combo partition identity; prev30m finalized-vs-NaN (positive path).

**Missing vs this slice’s claims:**

| Gap | Severity |
|---|---|
| Session folds + `causal_prefix` + ETH overnight (code probed here; no test) | **High** |
| Session-fold tests use `_session_signals` grouped by `dt.date`, not `trading_session_date` | **Medium** |
| Overlap → `aggregate_test_total_r` double-count | **Medium** |
| Focus trade count **>** Admit under `single_position` | **High** (test) |
| OTF matrix train trades must not exit after the chronological split bar | **High** (test) |
| R10 ≠ R12 labeling in UI/report strings | **Medium** |
| Phase 8 export/UI honesty (`st.success`, `P(mean R > 0)`, section banner) | **Medium** |
| Grid in-sample disclaimer | **Medium** |
| Portfolio correlation on `admitted` vs `candidates` | **High** (test) |
| `time_analysis.summarize_by_group` vs `summarize_trades` parity | **Low** |
| Negative “NaN must not become 0.0” (positive lookup exists) | **Low** |
| WFA train-selection + OTF enabled combined | **Low** |

Goldens remain identity gates. Passing 327 tests does **not** prove Focus honesty under restrictive exposure, session+ETH+prefix, or OTF-matrix path isolation.

---

## 3. Prioritized findings

### Critical

None in this layer’s own math. The execution-layer flatten leak (Slice 4 §3.1) still **poisons exit-grouped Time Analysis / Focus-adjacent display** of `SESSION_CLOSE` trades; it is not re-opened here.

### High

1. **OTF validation matrix train ranking peeks at OOS prices via the holding period.**  
   `run_otf_validation_matrix` splits **signals** chronologically, then `_simulate(source_df, accepted_train, …)` on the **full** frame. Probe: last train signal TPs on an OOS-only spike (`r=10`) vs `EOD`/`r=0` on a sliced train frame; matrix `train_expectancy_r=10`. Module/UI claim “OOS metrics never influence selection” — they don’t **as columns**, but train expectancy **is** an OOS-path number. WFA fold slicing does not have this bug. `otf_validation.py` `_simulate` / L389–407; `pages/10_Validation.py` L1780–1781, L1929–1934.

2. **Focus over-states constrained-path counts under non-`allow_all`; no test and no explicit UI sentence.**  
   C7 covers identity only for `allow_all` + 0 cooldown. Banner: exposure/cooldown reflect the all-day run. Missing: “Focused trade count may exceed Admit under `single_position` / cooldown.” `research-methodology.md` is OTF-only.

3. **Session-fold + `causal_prefix` + ETH overnight is implemented correctly and untested.**  
   Probe proved prefix `<` fold start and tsd grouping. Automated suite uses RTH-only fixtures and calendar-date signal helpers (`test_walk_forward._session_signals`). `docs/otf-filter.md` L696–697 still describes fold-local-only sources.

4. **Phase 8 permutation / bootstrap read as confirmatory in UI and export.**  
   `st.success` on `p≤0.05`; metric `P(mean R > 0)` (bootstrap fraction, not a calibrated probability); markdown `## Validation Diagnostics` has no diagnostic banner. R10+ batteries are stricter. After grid search this is selected-sample inference with no multiplicity correction.

5. **Portfolio return correlation is pre-admission; UI does not say so.**  
   `setup_correlation_matrices(candidates, …)` while KPIs use `admitted`. Bad case: `single_position` drops overlaps; heatmap still shows candidate-path correlation. `portfolio.py` L226; `pages/13_Portfolio.py` L103–117.

### Medium

6. **Overlapping WFA test windows: stitched equity guarded; `aggregate_test_total_r` / `aggregate_test_trade_count` sum every fold.**  
   `summarize_walk_forward` L1022–1028. User reads headline OOS R as unique exposure when `step_sessions < test_sessions`.

7. **WFA matrix heatmap is an OOS ranking surface without an adjacent “do not select the best cell” line.**  
   ASSUMPTIONS L565–567 are correct; UI L708–731 is a greenness contest. Same class as grid in-sample ranking with no page-8 disclaimer (`pages/8_Grid_Search.py`).

8. **R10 `both_hit_rule` ≠ R12 is documented, not labeled on Validation UI or report excursion section.**

9. **Time Analysis clock mix + `entry_*` names on exit-grouped tables.**  
   Calendar `entry_date` ≠ `trading_session_date`. Thin-sample warning without hide (unlike combo). Exit-basis Focus caption exists; column names still lie.

10. **prev30m `trade_count` vs R-analyzable universe; Focus ignored on Backtest prev30m block.**  
    NaN→0 is **not** the bug (Q8).

11. **Stale maintainer comment** at `walk_forward.py` L622–623 contradicts configurable OTF history.

12. **WFA consumes globally precomputed signals.** Fold engine is sound; end-to-end PIT still depends on levels/signals (Slices 2–3). Not a fold-boundary leak.

13. **Combo / pair views invite selection effects** even with strong diagnostic copy (inherent to the question).

### Low

14. Time Analysis “Recompute the full Performance Summary” wording.
15. Monte Carlo “path robustness” + drawdown `probability` column (descriptive frequency).
16. Residual `confirm_3bar` session-fold remapping (cannot be generated via UI/API/Study; Slice 4 residual fill).
17. No machine-readable `diagnostic_only` on Phase 8 API dicts.
18. No negative unit test “in-window NaN must not coerce to 0.0.”
19. Goldens / 327 passed tests ≠ analytics correctness.

---

## 4. Residual risks (not closed here)

- Slice 4 `entry_local_ts` flatten leak: exit-timestamp Time Analysis / MAE-adjacent display of `SESSION_CLOSE` is not per-entry-date and not CME session close.
- Silent non-fills never enter Focus / metrics / skip frame — attempted-entry rates are under-counted if someone uses `len(trades)` vs `len(signals)`.
- `pnl_points` (gross) vs net R looks like a metrics bug only if a later slice / report assumes both are net. Analytics itself does not mix them.
- Upstream signal/level PIT: WFA and OTF-matrix cannot unbias a look-ahead that is already in the candidate set.
- `allow_all` overlapping fills (Slice 4) inflate Focus / time / combo / battery sample sizes; honesty copy does not restated that on every analytics page.
- Study Runner / assistant consumers of `run_validation` must scrape free-text `caveat` keys — no uniform flag.
- Matrix / grid / Focus “best cell / best bucket” selection remains a researcher process risk even when code is leak-safe.

---

## 5. Contracts Slice 6+ must treat as **locked**

1. **Focus is post-hoc on `entry_timestamp` (C2).** It filters completed `trades` and subset-replays `summarize_trades` / `equity_curve`. It is **not** `simulate_trades`. Equity/DD is **not** all-day path DD. `None` / disabled window returns the unfiltered frame. Focus does not consume skip / OTF-reject frames.
2. **C7 identity is `allow_all` + 0 cooldown only.** Under any other exposure/cooldown, Focus **may over-state** Admit trade counts. Do not treat Focus ≡ constrained path.
3. **WFA session folds key by `trading_session_date` + instrument `eth_start`.** Half-open, contiguous, not calendar flatten, not clock `session`. UI/API forward instrument `eth_start`.
4. **WFA OTF history (verified on session folds):** `fold_local` = fold slice; `causal_prefix` = `iloc[:fold_end]` with prefix **strictly `<` fold start**; fold-local signals only; no post-fold bars; `None` → `fold_local`; invalid raises; short → unknown reject; OTF once per train/test phase, not per cell.
5. **WFA per-fold SL/TP selection uses train-grid metrics only.** Test `simulate_trades` runs after `best_grid_result`. Train/test OHLCV are sliced — a train trade cannot hold into the test slice.
6. **`run_wfa_matrix` default metric is OOS (`median_test_expectancy_r`).** Selecting the greenest cell is multiple-testing, not a fold leak.
7. **OTF validation matrix ranking column is `train_expectancy_r`, but train/OOS sims use the full `source_df`.** Train P&L may include bars after the chronological signal split. Do not treat that ranking as fold-isolated. OTF **filter** itself remains PIT (`availability_timestamp <= T`).
8. **Core KPI formulas match `METRICS_GLOSSARY`:** win rate, PF 3-branch, expectancy, zero-anchored max DD. `r_multiple` / `pnl_currency` net; `pnl_points` gross; analytics does not use `pnl_points`.
9. **R10 `both_hit_rule` does not inherit R12.** Independent diagnostic; default `stop_first`. MAE/MFE full-parent (Slice 4).
10. **Combo attribution and prev30m hit analytics invent neither fills nor signals.** prev30m in-window NaN is **not** coerced to 0; finalized last non-NaN is used. prev30m keys ETH session date.
11. **Portfolio is a post-hoc merge + overlay, not a capital simulator.** Correlation is currently on **candidates**. Time Analysis buckets are calendar / C1 RTH, not `trading_session_date`.
12. **Phase 8 batteries are in-sample diagnostics on the passed trade frame.** “Diagnostic only” is page-level; Phase 8 export is weaker than R10+.
13. **Goldens ≠ analytics correctness.** Skip-frame count ≠ all non-fills.

---

## 6. Contracts still **open** (do not assume)

1. Whether product will **fix** OTF-matrix train sims to slice OHLCV at the split (this slice did not change code).
2. Whether Focus UI will state trade-count divergence vs Admit under restrictive exposure.
3. Whether overlapping WFA aggregates will be overlap-aware (or clearly labeled as fold-sum, not unique OOS).
4. Whether R10 UI will name R12 independence.
5. Whether portfolio correlation will move to `admitted` or be labeled pre-admission.
6. Whether Time Analysis will hide thin samples or rename exit-basis columns.
7. Study / assistant / report-zip **consumption** of these artifacts (Slice 6+ if in scope) — not audited here.
8. Backtest page combo / prev30m **wiring** beyond the consume contract (page 7 is mostly out of this slice except attribution consume).

---

## 7. How Slice 6+ should start

1. Treat §5 as the Focus / WFA / metric / battery / combo / prev30m / portfolio contract. Do not re-audit fills, 3c 4-rule, or `trading_session_date` arithmetic.
2. If Slice 6 is Studies / CLI / report zip / assistant: consume `trades`, Focus provenance (`subset_replay_equity`, honesty banners), WFA `otf_history_policy` + session dates, `validation_summary` **without** assuming a `diagnostic_only` flag, OTF matrix `is_train_selected` **without** assuming train P&L is split-isolated.
3. Do not treat skip-frame counts, Focus counts, or OTF `otf_filter_passed=True` while disabled as equivalent populations.
4. Do not treat `SESSION_CLOSE` / exit-grouped time buckets as `trading_session_date` closes (Slice 4 leak).
5. Do not treat WFA matrix / grid ranking / Focus bucket / OTF-matrix “winner” as a deployable parameter.
6. Goldens still do not prove study/report/assistant honesty.

---

## 8. How Slice 5 started (traceability)

Read Slice 0 map (two composers, Focus ≠ Admit, goldens ≠ correctness), Slice 1 clocks (`session` ≠ session-date; flatten calendar-RTH), Slice 2 levels PIT, Slice 3 signal-row / OTF-not-at-generation, Slice 4 §5 locked execution + §7 handoff.

Scoped to `thesistester/analytics/*`; `api.run_validation` / `run_walk_forward` / `run_time_analysis` / battery wrappers; `pages/8_Grid_Search.py` (ranking only); `pages/9_Time_Analysis.py`; `pages/10_Validation.py`; `pages/13_Portfolio.py`; named tests; `docs/METRICS_GLOSSARY.md`; ASSUMPTIONS analytics/WFA; `research-methodology.md`; `POINT_IN_TIME_GUARANTEES.md` WFA/OTF addenda; `docs/otf-filter.md` WFA bullets.

Did not enter fill internals (except consuming locked contracts), Study execute, report zip format, assistant, or Data page.
