# ThesisTester correctness audit — FINAL MERGE

**Mode:** research / investigation only. No application-code changes.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**This file is the only merge deliverable.** It synthesizes Slices 0–7. It does not re-audit engine math. Per-slice evidence stays in the slice PRs.

| Slice | PR | File | Branch |
|---|---|---|---|
| 0 Overview | [#390](https://github.com/AccumuLatata/ThesisTester/pull/390) | `AUDIT_OVERVIEW.md` | `cursor/audit-overview-slice0-fa42` |
| 1 Data / time | [#391](https://github.com/AccumuLatata/ThesisTester/pull/391) | `AUDIT_SLICE1.md` | `cursor/audit-slice1-data-time-7ccd` |
| 2 Levels / PIT | [#392](https://github.com/AccumuLatata/ThesisTester/pull/392) | `AUDIT_SLICE2.md` | `cursor/audit-slice2-levels-pit-762a` |
| 3 Signals / 3c | [#393](https://github.com/AccumuLatata/ThesisTester/pull/393) | `AUDIT_SLICE3.md` | `cursor/audit-slice3-signals-3c-0929` |
| 4 Execution | [#394](https://github.com/AccumuLatata/ThesisTester/pull/394) | `AUDIT_SLICE4.md` | `cursor/audit-slice4-execution-228d` |
| 5 Analytics / WFA | [#395](https://github.com/AccumuLatata/ThesisTester/pull/395) | `AUDIT_SLICE5.md` | `cursor/audit-slice5-analytics-wfa-4f95` |
| 6 Study Runner | [#396](https://github.com/AccumuLatata/ThesisTester/pull/396) | `AUDIT_SLICE6.md` | `cursor/audit-slice6-study-runner-89d1` |
| 7 Persistence / API | [#398](https://github.com/AccumuLatata/ThesisTester/pull/398) | `AUDIT_SLICE7.md` | `cursor/audit-slice7-persistence-api-2b32` |

**How this merge was written.** Slice 7 §5 is the locked persistence / composer / assistant contract. Fill / 3c / WFA math is not re-opened except to list inherited bugs that travel on restored bundles. Passing goldens and named-test counts are not treated as proof that restore, report labels, or UI↔API admissions agree. Page 12 import, Report zip, and Assistant open-exact are three different integrity bars. `thesistester run experiment.yaml` is not `study run`. Discuss packet-path grounding does not cover Help, live voice, or hash-less bundle analytics.

The single SoT question: **what is causal at time T**, across levels, 3c, OTF, R12, Admit, WFA — **plus which composer applied it**.

---

## 1. Executive summary

### What the product is

ThesisTester is an **intraday futures strategy-research workbench** (ES / NQ / MES / MNQ). It is not a live trading system and does not claim a durable edge.

The research object is a **confluence setup**: selected session / structural / indicator / profile levels → zone detection (global cluster or anchor rules) → trigger (`touch` / `reject` / `break` / `reclaim` / `3c`) → candidate signals → bar-by-bar simulation under explicit execution assumptions (costs, exposure, session flatten, R12 intrabar model, R13 BE/trail, optional OTF admission, optional Admit entry window).

Outputs are **diagnostics**. Validation, walk-forward, OTF matrix, Focus, Study reports, and assistant Discuss are honesty-gated screening tools. Goldens are a **legacy-unchanged identity** gate (`docs/ENGINEERING_PROPOSAL.md` §4), not a correctness proof.

### How the audit was run

Eight sequential research-only slices at `83a42f8`. Each slice locked contracts for the next and did not implement fixes. Named suites were run (Slice 1: 126; Slice 2: 352; Slice 3: 357; Slice 4: 705; Slice 5: 327; Slice 6: 292; Slice 7: 313). Those counts police the contracts they encode. They do **not** prove restore isolation, report labeling, UI↔API admission parity, or flatten correctness.

There is **one engine** and **two execution composers**:

- **Composer A — classic UI.** Pages 1–10/13 call `thesistester.engine` / `analytics` / `setup` directly. They do **not** call `api.run_experiment`. Cache policy is effectively `off`.
- **Composer B — headless.** `api.run_experiment` is the only pipeline used by CLI (`run_batch`), Study (`run_study`), and Assistant tools. Origin / cache / `base_directory` still differ inside B.

Parity is a tested composition contract, not a shared page function. A bug can exist in one composer only and no golden will catch it.

### Overall verdict

**The shipped engine core is generally causal on the happy path.** There is no silent continuous-contract price synthesizer. 3c does not backdate `bar_index` to arrival. OTF is not applied at signal generation. Rolls never rewrite OHLC. R12 does not upsample. WFA session folds key by `trading_session_date` + `eth_start`. Discuss/Explain numbers require packet paths.

**Research honesty is not equally causal.** The product can present two “the same” experiments that differ in admissions, levels, dataset bytes, or leftover diagnostics — without a test failing. Three defects silently change *fills or ranking*:

1. Session flatten uses a leaked `entry_local_ts` from the last first-loop candidate (Slice 4).
2. Advertised Study `experiment.yaml` replay resolves relative `dataset.path` against a different parent than `study run` (Slice 6).
3. OTF validation-matrix train ranking simulates train signals on the **full** frame, so train expectancy can include OOS-bar P&L (Slice 5).

Around those sit a cluster of **composer forks** (OTF timezone, cutoff-without-flatten, levels-vs-data frame, `BASE_COLUMNS`, battery `enabled` default, `base_directory`, cache policy) and **restore / report leftover mixing** (Slice 7). Goldens stay green because they do not cover flatten, restore, or those forks.

**Lead-developer takeaway:** treat this file’s §5 as the contract you must not invert. Fix order is §6 (research-honesty first, not easy-first). Do not start by “aligning goldens” or “adding more named tests” until the three critical defects and the composer table are closed.

---

## 2. Unified “causal at T” map

**T is not one clock.** Each stage has its own decision instant. The engine answer is coherent if you keep the clocks apart. The composer answer is not: UI and `run_experiment` can feed a different timezone, a different OHLCV frame, or a different cutoff into the same function.

Two clocks that must never be inverted (Slice 1, locked through Slice 7):

| Clock | Function | Rule | Used for |
|---|---|---|---|
| `session` ∈ {RTH, ETH} | `data.sessions.tag_session` | Exchange-local wall clock in `[rth_start, rth_end)` → RTH. Uses `09:30`/`16:00` only. **Does not use `eth_start`.** | RTH membership (OR, ONH gate, RTH_Open, dVWAP_RTH, TPO, APOC, Time Analysis C1 segments) |
| `trading_session_date` | `levels.session_date.trading_session_date` | If local time `>= eth_start` (`18:00`), date += 1 day. Midnight is not a CME reset. | pd*/pw*/pm*, dVWAP, prev30m, TPO/APOC keys, OTF session reset, WFA session folds |

Disagreement window: calendar `16:00–24:00` and `00:00–09:30` are ETH; `18:00–24:00` already belongs to the **next** CME date. The `16:00–18:00` ETH pocket is still *today’s* trading date. Session flatten is a **third** clock (calendar date of `entry_local_ts` + 16:00) and is currently leaky.

### 2.1 Data

| | |
|---|---|
| **T** | Bar `timestamp` after localize/convert to instrument `exchange_timezone`. |
| **What is causal** | Parent minute `m` uses only stamps inside `m` (15s-primary v2). Resample bucket `[label, label+freq)`. No empty-bar synthesis. No upsample. Rolls do not rewrite prices. |
| **What is not causal / not CME** | `1D` / `4h` resample is midnight-origin, not `eth_start`. A calendar `1D` bar mixes two `trading_session_date`s after 18:00. Capture profiles floor to 1 minute. |
| **Composers** | **UI** `pages/1_Data.py`: `load_ohlcv` → `tag_session`. Legacy primary OHLCV fatals are **warning-only**. 15s-primary parent is fail-closed. **API** `load_dataset` / `_load_experiment_data`: same loader; duplicates / missing / HL / OC-range / negative volume are **fatal**. **Study / CLI / Assistant:** `run_experiment` → API load. Omitted `ingestion_mode` → `primary`. Studies Build first-visit is `15s_primary_derive_1m`. |
| **TZ triple** | Naive → localize(`source_tz`) → convert(`target`). Aware → convert(embedded); `source_tz` ignored. `display_timezone` is export-only and never mutates engine bars. |

### 2.2 Levels

| | |
|---|---|
| **T** | Same bar `timestamp` as data. A non-NaN level at T may use bars `<= T` (running), a completed prior period (`shift(1)`), or a clock-gated window that has ended. |
| **What is causal** | Prior-period structural / profile: `shift(1)` on `trading_session_date` (or week/month of that date). Clock-gated OR / Asia / London / APOC / TPO brackets / prev30m freeze: emit only when `timestamp >= window_end`. HTF SMA/EMA / pivots: expose only after `align_timestamp` via backward `merge_asof`. dVWAP: per-session `cumsum` on bars `<= T`. prev30m: **no** dataframe-end finalize. |
| **Documented same-bar close** | SMA/EMA / rolling VWAP/POC / dVWAP typical price include bar *i* close. Signals are bar-close confirmed. Intrabar use of those columns is a known limitation, not a future-bar leak. |
| **Incomplete emit** | Clock-gated families emit after the clock if **any** in-window bars exist. Empty window → all-NaN. Sparse 15s-primary minutes are a valid (incomplete) OR/Asia/London. |
| **Not a CME session bar** | Product default enables `Pivot_4h_*` and `VWAP_rolling_4h` (midnight-origin resample). |
| **Composers** | **UI** widgets seeded from `DEFAULT_LEVELS_SETTINGS` (advanced ON, OR 15); stale snapshot helper setdefaults **advanced OFF / ticks 1**. Tags missing `session` before compute. **API / Study** `normalize_levels_config` → product fill; **does not** tag missing `session`. **Bare** `compute_all_levels(df)` is a fourth plane: OR 30, gates False. Do not treat it as the product. |

`session_levels` is a second full bar-aligned frame from the same `compute_session_levels`, not a per-session table. Currently argument-identical; untested as a pair.

### 2.3 Signals / 3c

| | |
|---|---|
| **T (simple)** | Trigger-candle **completion**. `bar_index` / `timestamp` = canonical trigger-end. `trigger_timestamp` equals `timestamp` on `base`. |
| **T (3c structure)** | Arrival / inside / SFP / reversal evaluated on trigger TF. Retrace scan starts after reversal-candle completion. |
| **T (3c row written)** | Filled → **fill** bar (`entry_bar_index`, `retrace_entry_price`). Void → **reversal** bar. **Never backdated to arrival.** |
| **T (OTF later)** | `trigger_timestamp` if present else `timestamp`. For filled 3c that is **reversal completion**, not fill time. |
| **Non-base wait** | Duration `max_wait * TF delta`, half-open `(reversal_end, reversal_end + max_wait*Δ]`. Skips the completion-timestamp base bar. Not “N completed trigger candles.” |
| **Composers** | **UI** `pages/6_Signals.py`: picker = `available_level_columns`; saved-setup blockers disable Generate on ineligible columns. **API / CLI / Assistant / Study:** `validate_setup_config` only — **accepts `close`**. Study *factors* cannot name `close` today (`closed_level_token_set`); a hand-edited `experiment.yaml` can. |
| **OTF at this stage** | **Not applied.** Full candidate population. `otf_filter` on setup / `signal_settings` is provenance for later admission. Disabled ≠ passed. |

Two tested objects: simple triggers use the zone envelope; 3c uses each `CandidateLevel.level_price`. Non-base 3c projects every intra-window zone onto the trigger candle (stale developing-level price vs completed HTF OHLC). Naked filter is zone-admission at `zone.bar_index`, not per-level for 3c.

Public triggers: `touch` / `reject` / `break` / `reclaim` / `3c`. `confirm_3bar` cannot be generated; `simulate_trades` still fills hand-built rows.

### 2.4 Fills / OTF / Admit / R12 / R13

| Stage | T | Causal rule | Composer fork |
|---|---|---|---|
| **OTF admission** | `trigger_timestamp` else `timestamp` | HTF bar usable iff `availability_timestamp <= T` (`merge_asof` backward, exact matches allowed). TFs: 5/15/30m only. Session reset: `trading_session_date` + `eth_start`. 1D/4h rejected. Default off. | **UI TZ** = session `exchange_timezone` or `inst.exchange_tz`. **API TZ** = always `inst.exchange_tz` (ignores `dataset.exchange_timezone`). |
| **Simple fill** | Next bar after trigger-end | Theoretical price = that bar’s **open**. `entry_model=next_bar_open`. | Same engine. |
| **3c fill** | `entry_bar_index` | `retrace_entry_price`. Void: no fill, **no skip row**. | Same engine. |
| **Admit** | **Entry-bar** local time (`entry_timestamp`), not signal-bar | C1 segments from `entry_window_policy`. `None` ≡ `{enabled:False}`. Window before cutoff (C9). | Same engine. Grid/WFA inherit a **fixed** window. |
| **Cutoff** | Entry-bar local `>` cutoff | Strict after. | **UI / classic-export:** field forced `None` unless flatten on. **API / YAML / Study / Assistant:** cutoff applies without flatten. |
| **Exposure** | Entry bar vs open positions | Default `allow_all`: every executable candidate is an independent position. Restrictive policies sort and skip. | Same engine. UI has no inflation caption. |
| **R12** | Parent bar (and sub-bars if selected) | No upsample. Same-sub-bar entry+SL+TP → SL, never TP. `sl_first` **ignores** `entry_price` — 3c can SL on pre-retrace parent extreme. Conservative: explicit SL-first on holes. | UI uses session `base_interval` / `subtimeframe_interval`. `run_experiment` prefers declared 15s-primary provenance. |
| **R13** | After completed parent bar | Armed stop active **next** bar. 3c/confirm do not arm on the entry parent. | Same engine. Uncovered by goldens. |
| **Session flatten** | **Intended:** calendar date of *this* entry + `session_close_time` (default 16:00). **Implemented:** calendar date of leaked last first-loop `entry_local_ts`. | Not `trading_session_date`. Not ETH overnight. Empty `bars_until_close` → silent drop, no skip. | Same leak in both composers. UI gates cutoff on flatten; API does not. |
| **Backtest frame** | OHLCV (+ timestamps) | Level columns unused by this layer. | **UI:** `levels` if present else `data`. **`run_experiment`:** always `level_payload["levels"]`. **Bare `run_backtest(data)`:** caller frame. |

Skip rows exist for Admit / cutoff / exposure / cooldown. They do **not** exist for 3c void, missing entry bar, or empty flatten cap. OTF rejects are a distinct frame. Population identity “candidates − rejects − skips = trades” is false.

**WFA OTF source (locked for Slice 5, verified there):** default `fold_local` = fold OHLCV slice only. `causal_prefix` = `df.iloc[:fold_end]` with prefix **strictly before** fold start. Only fold-local signals scored. Bars after fold end never used. Grid applies OTF **once**, not per cell.

### 2.5 Focus

| | |
|---|---|
| **T** | `entry_timestamp` (C2). Exit time is used only to sort subset equity after the filter. |
| **What it is** | Post-hoc filter of completed `trades` + subset-replay `summarize_trades` / `equity_curve`. **Not** `simulate_trades`. Equity/DD is **not** all-day path DD. |
| **What it is not** | Admit. C7 identity (`Focus ≡ Admit`) holds only under `allow_all` + `cooldown_bars_after_exit=0`. Under `single_position` / cooldown, Focus **over-states** constrained-path counts. |
| **Composers** | Classic Time Analysis / Backtest overlay / reporting. Study does **not** run Focus. Assistant bundle time-analysis tools can, without requiring bundle hash. |
| **Silent non-fills** | Never appear. Skip-frame length is not “all non-fills.” |

### 2.6 WFA / batteries / Study ranking

| | |
|---|---|
| **T (session fold bounds)** | `trading_session_date` + instrument `eth_start`. Half-open, contiguous. Not calendar flatten, not clock `session`. ETH overnight bars on the same CME date stay in one fold (probed Slice 5; suite is RTH-heavy). |
| **T (per-fold path)** | Train/test OHLCV are sliced. A train trade cannot hold into the test slice. Train SL/TP selection uses train-grid metrics only. |
| **T (OTF on fold)** | Same OTF `T` as §2.4, on `fold_local` or `causal_prefix` source. Filter remains PIT. |
| **T (OTF *matrix*)** | Filter is PIT on the full frame. **Train/OOS sims also use the full `source_df`.** Last train signal can TP on an OOS-only spike. Ranking column `train_expectancy_r` is then an OOS-path number. Study does **not** call this matrix. |
| **T (Phase 8 / R10–R16)** | In-sample on the passed trade frame. No holdout peek. After a grid search this is a selected sample with no multiplicity correction. |
| **Study crown** | In-sample `primary_metric` even when `walk_forward.enabled: true`. WFA OOS sits on the index / rollup only. A promoted cell is not a deployable parameter. |

`run_wfa_matrix` default metric is OOS (`median_test_expectancy_r`). Selecting the greenest cell is multiple-testing, not a fold leak. Overlapping test windows: stitched equity is guarded; `aggregate_test_total_r` **sums** every fold.

---

## 3. Composer disagreement table

Two execution composers remain (UI pages vs `run_experiment`). CLI / Study / Assistant are the **same API composer** with different provenance, cache, and path parents. Disagreements that change admissions, levels, batteries, or bytes are still live.

| Topic | Classic UI | `api.run_experiment` | CLI `run_batch` | Study `run_study` | Assistant |
|---|---|---|---|---|---|
| **Calls `run_experiment`?** | **No.** Pages compose engine directly. | Yes (this *is* the composer) | Yes, `origin=cli` | Yes, `origin=study` | Yes, `origin=assistant` |
| **Cache** | `off` (no artifact wiring) | Default **`off`** | `read_write` | `read_write` | `read_write` |
| **OTF resolve order** | Shared 5-step (`signal_settings` key present → snapshot → last setup → setup → disabled) | Same | Same | Same | Same |
| **OTF `T`** | `trigger_timestamp` else `timestamp` | Same | Same | Same | Same |
| **OTF timezone** | `session_state.exchange_timezone` **or** `inst.exchange_tz` | **Always** `inst.exchange_tz` — ignores `dataset.exchange_timezone` used for load | Same as API | Same as API | Same as API |
| **Cutoff without flatten** | Widgets + classic-export force `no_new_entries_after=None` | YAML accepted; engine applies cutoff | Same as API | Same as API | Same as API |
| **Backtest OHLCV frame** | `levels` if present else `data` | **Always** `level_payload["levels"]` | Always levels | Always levels | Always levels |
| **`BASE_COLUMNS` / `close`** | Pickers + saved-setup blockers use `available_level_columns` | `validate_setup_config` rejects hits only, **not** `close` | Accepts | Factors cannot name `close`; hand-edited `experiment.yaml` can | Accepts via `build_setup` |
| **Omitted `levels` keys** | First-visit widgets = product ON. Stale snapshot helper = gates **OFF** / ticks **1** | `{**DEFAULT_LEVELS_SETTINGS, **raw}` (product ON, OR 15, ticks 4/8/10) | Same as API | Same product fill. Build Advanced OFF **omits** keys → still product ON | Same as API. Classic export **refuses** to invent |
| **Bare `compute_all_levels`** | Not used on calculate path | Not used | Not used | **Not used** | Not used |
| **Battery `enabled` default** | Page widgets | `.get("enabled", True)` for grid / WFA / validation | Same trap on raw YAML | Expand emits `{enabled: false}`, never `{}` | `_bounded_spec` same default-on trap |
| **Omitted `ingestion_mode`** | Data page recommends 15s-primary | **`primary`** | `primary` | YAML omit → `primary`. Build first-visit → `15s_primary_derive_1m` | `primary` |
| **`base_directory` for relative paths** | N/A (uploaded bytes / session) | Caller | **`experiment.yaml` parent** | **StudySpec parent** | **`dataset.path` parent** |
| **Fail vs continue** | N/A (one run) | N/A (one run) | **Fail-fast.** No index if any cell dies | **Continue.** Failed row, no zip | One run / Study tools when flag on |
| **Index `status`** | N/A | N/A | Metrics + `bundle_path` only | Same + **`status`** | N/A |
| **Setup validate** | Picker + `validate_setup_config` + compatibility | `validate_setup_config` only | Same | Same (+ closed token set on factors) | Same |

**Replay that is not identity-equivalent**

`python -m thesistester run out/study1/experiment.yaml` is fail-fast, `origin=cli`, cache `read_write`, and resolves `dataset.path: data/es_15s.csv` against **output_dir**. `study run examples/studies/….yaml` resolves the same relative path against the **StudySpec parent**. AGENT_GUIDE L38–39 still advertises this as the “unchanged R18 path.” It is not `study run`.

**Three integrity bars that must not be collapsed**

| Bar | What it checks | What it does not |
|---|---|---|
| **Page 12 import** | Schema / section validation | `canonical_bundle_hash`. Tampered `trades.parquet` imports. |
| **Report zip** | Session dump (no re-sim) | Bundle hash. Can attach leftover `otf_filter_summary`. Phase 8 has no section banner. |
| **Assistant open-exact / complete_run** | Hash-fail-closed | Does not cover Help digits, live voice PCM, or TIME/OTF/resample/roll tools that skip `expected_hash`. |

**Cache vs identity (do not conflate)**

`source_binding_key` includes `ingestion_mode` + `derivation_policy`. `dataset_id` / `data_artifact_key` do **not**. Same parent OHLC from native 1m vs 15s-derived 1m can share a levels cache object. Cold vs warm `canonical_bundle_hash` is stable on tested paths. That does not prove restore or composer honesty.

---

## 4. Master prioritized findings

Deduplicated across slices. Severity is **research honesty** (can a researcher believe a false causal claim, a false identity, or a contaminated ranking?), not fix difficulty. Each finding: severity, title, slice(s), file/function, bad case, why it matters.

### Critical

These three can silently change fills, dataset identity, or validation ranking while docs/CI present the run as the intended experiment.

| ID | Title | Slice(s) | Where | Bad case | Why it matters |
|---|---|---|---|---|---|
| **C1** | **Session flatten `entry_local_ts` leak** | S4 (S5/S7 inherit on restored trades) | `thesistester/engine/backtest.py` `simulate_trades` — first loop stores `entry_ts` on the candidate; second-loop flatten reads the leaked loop variable `entry_local_ts` | Last signal enters Tue 02:00 → Mon 18:30/23:00 ETH entries are held through Tue RTH and exit `DATA_END`/`SESSION_CLOSE` at Tue 15:59/16:00. Inverse: last signal Mon 18:30 → later Tue RTH entries compute Mon 16:00 close → empty `bars_until_close` → **silent drop**, no skip row | Every multi-signal flatten run assigns **one** calendar close to all trades. One-signal RTH goldens stay green. `SESSION_CLOSE` is not per-entry-date and not CME session close. Time Analysis / Focus-adjacent exit grouping of those trades is poisoned. |
| **C2** | **Advertised Study `experiment.yaml` replay is a different experiment** | S6 (S7 confirmed) | `thesistester/study/expand.py` (copies relative path); `study/execute.prepare_study_expansion` (`base_directory=study_path.parent`); `thesistester/cli.py` `main` (`base_directory=experiment_path.parent`) | `examples/studies/pdPOC_ma_confluence_battery.yaml` + `path: data/es_15s.csv` → `study run` uses `examples/studies/data/…`; `thesistester run out/…/experiment.yaml` uses `out/…/data/…` (missing or a different file). Also fail-fast vs continue, `origin=cli` vs `study`, no index `status` | AGENT_GUIDE still calls this the “unchanged R18 path.” A coworker replaying the emitted YAML can crown a different CSV — or fail — and believe they reproduced the study. |
| **C3** | **OTF validation matrix train ranking peeks at OOS prices via the holding period** | S5 | `thesistester/analytics/otf_validation.py` `_simulate` / train-OOS split; `pages/10_Validation.py` copy “train results drive ranking/selection only” | Signals split at `train_fraction`; both sims pass **full** `source_df`. Probe: last train signal TPs on an OOS-only spike (`r=10`) vs `EOD`/`r=0` on a sliced train frame; matrix `train_expectancy_r=10` | Column-honest (OOS columns unused for selection), **path-leaky**. UI says OOS never influences selection. WFA fold slicing does **not** have this bug. Study does not call the matrix; classic Validation and any future wiring do. |

### High

Composer forks, restore mixing, and defaults that change the research object without a failing test.

| ID | Title | Slice(s) | Where | Bad case | Why it matters |
|---|---|---|---|---|---|
| **H1** | **Bundle restore leftover keys + dataset-less bootstrap** | S7 | `research_bundle._MANAGED_RESEARCH_KEYS` / `_BACKTEST_META_KEYS` omit `otf_filter_summary`, `backtest_otf_filter`, `setup_config`, `focused_trades`. `reporting.build_otf_filter_metadata` reads `otf_filter_summary`. `pages/12_Research_Bundles.py` calls `bootstrap_active_saved_dataset()` first; page 12 import is schema-only | UI OTF run (12 rejected) then import a CLI zip (OTF off) → Report still shows 12 rejected. Dataset-less zip + active saved dataset A → after rerun, `data`=A and `trades`=B | Uploader nonce is real and tested. It does not clear leftover *session keys*. Assistant open-exact hash-verifies; page 12 does not. Restored research is not an isolated snapshot. |
| **H2** | **Promote / launch cwd-first CSV pin** | S6 | `study/promote._rewrite_dataset_paths_for_draft`; `study/launch._pin_dataset_paths`. Search roots: cwd, study **output** dir, draft parent — **not** the original StudySpec parent | Ranked cells ran on `examples/studies/data/es_15s.csv`; promote finds repo `cwd/data/es_15s.csv` first and pins that | Survivor draft is a different dataset than the cells that were ranked. Combined with C2, Study path identity has two independent retargets. |
| **H3** | **API accepts `close` as a level** | S3, S7 (S6 residual on hand-edited YAML) | `thesistester/setup.py` `validate_setup_config` rejects `NON_LEVEL_OUTPUT_COLUMNS` only. `api.build_setup` / `generate_signals`. Engine `detect_confluence_zones` has no eligibility check | `selected_levels=["close","ONH"]` → validate `[]`; API emits `close\|ONH` zones and touch signals (Slice 3 probe) | UI pickers cannot do this. Headless / Assistant / CLI can. Hits remain rejected (Slice 2 contract held). Fake price near the close clusters with real levels. |
| **H4** | **Product-default levels when Advanced off / omitted keys** | S2, S6 | `levels/defaults.py` `DEFAULT_LEVELS_SETTINGS`; `research_identity.normalize_levels_config`; `pages/15_Studies.py` Advanced OFF pops `prev30m_vwap_enabled` / `pivots_enabled`; classic `_normalize_levels_settings` setdefaults OFF / ticks 1 | Build Advanced OFF YAML looks SMA-only; `compute_levels` still enables prev30m / pivots / APOC / default VWAP/POC. Old Levels snapshot missing Stage 6 keys loads gates OFF on the page and ON through the API | Two settings planes plus a third snapshot helper. Operator mental model “off = off” is false on the product plane. Same fill as a sparse hand-written YAML — wrong plane, not a Study-only fork. |
| **H5** | **`allow_all` overlap inflation undisclosed on Backtest/Grid** | S4 (S5 sample sizes inherit) | `engine/backtest.py` `simulate_trades`; `pages/7_Backtest.py` / `8_Grid_Search.py` exposure selectbox (no help text) | Simple `bar_index=1` + filled 3c `entry_bar_index=2` → 2 trades under `allow_all`, 1 under `single_position` | Default exposure treats every candidate as an independent position. Skip table is empty, so nothing looks wrong. ASSUMPTIONS §4 states the fact; pages do not. Inflates Focus / time / combo / battery N. |
| **H6** | **`sl_first` pre-entry SL on 3c** | S4 | `engine/intrabar.py` `resolve_ohlc_bar` ignores `entry_price` for `sl_first`; `backtest.py` still passes `entry_activation_price` (used only by path / subtimeframe) | Retrace at 100, parent low 97 before the retrace, SL 2 pts → `SL` | Default R12 model is a pessimistic full-bar read. ASSUMPTIONS §2 pre-entry exclusion is implemented only on subtimeframe / path-after-entry. Goldens are `sl_first` and do not prove 3c entry-bar honesty. |
| **H7** | **UI cutoff gated on flatten; API is not** | S4, S7 | `pages/7_Backtest.py` / `8_Grid_Search.py`; `classic_export.py`; `api.run_backtest` | YAML `no_new_entries_after` + `flat_by_session_close: false` → headless skips `after_entry_cutoff`; same spec in UI admits | Same RunSpec, two admissions. Study / Assistant / CLI are the API side. |
| **H8** | **Raw YAML / assistant `_bounded_spec` batteries default on** | S7 (S6 expand already emits `{enabled:false}`) | `api.py` `run_experiment` `.get("enabled", True)` for grid / WFA / validation; `assistant/tools.py` `_bounded_spec` | `grid:` with SL/TP lists and omitted `enabled` → full sweep runs | Study cannot emit this. Hand-written R18 and assistant can. Combined with H4, omitted keys are not “off.” |
| **H9** | **`dataset_id` omits ingest story** | S7 (S1 residual) | `research_identity.DataIdentity.dataset_id`; `execution_artifacts.source_binding_key` (does include mode) | Native 1m CSV vs 15s-derived 1m with identical parent OHLC → same `dataset_id` / levels cache; R12 subtimeframe still differs | Bindings do not cross modes. Levels cache can. Parent+levels look identical; fills can differ. No named test. |
| **H10** | **Data-page legacy primary does not fail-closed on fatal OHLCV; API does** | S1 | `pages/1_Data.py` primary branch always `tag_session` + install, warns only. `api.load_dataset` aborts on duplicates / missing / HL / OC-range / negative volume | Duplicate 1m bars (VWAP/POC-sensitive) enter classic `session_state` and can be saved | Composer drift at the first gate. 15s-primary parent path *does* fail-closed. Classic research can proceed on data the API would reject. |
| **H11** | **Canonical path + pandas 3 rejects honest DST-crossing aware CSVs** | S1 | `data/loader.py` `load_ohlcv` `to_datetime(format="mixed")` without `utc=True` | File with `2026-03-08 01:59:00-05:00` then `03:00:00-04:00` → raw `ValueError` (“pass utc=True”) on **canonical** only. Vendor profiles UTC-normalize first and load | Fail-closed is real; it is over-closed on the public canonical path. Exception is untyped. Operator cannot pass `utc=True`. No named test for mixed-offset canonical. |
| **H12** | **Focus over-states constrained-path counts under non-`allow_all`** | S5 | `analytics/entry_window.py` `summarize_focused_trades`; banner; `pages/9_Time_Analysis.py` | `single_position` admits out-of-window A that blocks in-window B; Focus on the in-window bucket still shows in-window fills that existed only because A occupied the slot | Copy is honest about post-hoc / subset-replay. It does **not** say Focus N can exceed Admit. C7 tests only `allow_all` + 0 cooldown. `research-methodology.md` is OTF-only. |
| **H13** | **Phase 8 confirmatory UI / export** | S5, S7 | `pages/10_Validation.py` `st.success` on permutation `p≤0.05`; metric label `P(mean R > 0)`; `reporting.py` `## Validation Diagnostics` has no section banner | After a grid search, bootstrap/permutation on the selected sample with no multiplicity correction; markdown lists CI / p / overfit with no diagnostic banner (R10+ batteries have banners) | Computation is diagnostic (no holdout peek). Presentation reads confirmatory. No API `diagnostic_only` flag. |
| **H14** | **Non-base 3c stale developing-level projection** | S3 | `engine/signals.py` `_project_zones_to_trigger_df`; `signals_3c.py` `detect_3c_setups_with_trigger_timeframe` | 5-min trigger, `dVWAP` / SMA / rolling VWAP at minute 1 of the window, tested against the **completed** 5-min OHLC | Decision T is HTF close (not a future-bar leak). Level-as-of is stale. Simple triggers keep only `base_end` zones. Static levels (`pdHigh`) are unaffected. Combined with zone-level (not per-`CandidateLevel`) naked admission. |
| **H15** | **OTF UI TZ vs API TZ** | S4, S7 | `pages/7_Backtest.py` vs `api.run_backtest` `session_timezone=inst.exchange_tz` | Data page sets `exchange_timezone: "UTC"` on MNQ. UI OTF localizes naive `T` to UTC; headless uses instrument `America/New_York` | Same bars, different HTF alignment. OTF `T` contract is shared; the clock it is expressed in is not. |
| **H16** | **Failed Study cells under-reported in MD / over-counted in rollup; ranking ignores WFA OOS** | S6 | `study/report.py` honesty counts `len(overview)`; `rollup` `cell_count=len(frame)`; promote `primary_metric` | 40-cell study, 8 failures: MD “cells in overview: 40; ranked: 12” with no Failed section. WFA-enabled study still crowns in-sample `expectancy_r` | Failed cannot be promoted (honest). Operator reading only MD / rollup N can miss why. Crown vs rollup WFA columns disagree. |

### Medium

Honesty / doc / test-coverage issues that do not silently rewrite the default happy-path fill, but will produce “wrong OR / wrong session day / confirmatory statistic” reports.

| ID | Title | Slice(s) | Where | Bad case | Why it matters |
|---|---|---|---|---|---|
| **M1** | **`1D` / `4h` resample ≠ CME session** | S1, S2 | `data/resample.py`; product default `Pivot_4h_*` / `VWAP_rolling_4h`; OTF rejects 1D/4h (closed for OTF) | Hours `16:00…01:00` ET → `1D` labels `00:00` Mon and `00:00` Tue; Monday’s daily bar includes `18:00–23:00` (already Tuesday `trading_session_date`); both tag ETH | Preview-only today for Data. Levels product default **includes** 4h midnight-origin columns as ordinary prices. Do not read them as session-anchored. |
| **M2** | **PIT table overclaims tests for `pw*`/`pm*` structural; OR / `RTH_Open` / ONH / HTF MAs weaker than “Causal? = Yes”** | S2 | `docs/POINT_IN_TIME_GUARANTEES.md`; `test_prior_session_levels_future_shock` asserts only `pd*` | A current-week leak into `pwHigh` would pass that test. Inspection-only `—` rows (`dOpen*`, `prevSettlement`, `pm` profile) still have no R3 future-shock | Living table is the inventory researchers trust. Tests column is not coverage. Post-R3 families *are* future-shocked; the table’s wording still over-reads the rest. |
| **M3** | **Missing-`session` split: `sessions.py` NaN vs gated families re-tag** | S2 | `levels/sessions.py` does not re-tag; `session_vwap` / `tpo` / `apoc` / `prev30m` call `tag_session`. `api.compute_levels` does not pre-tag | Untagged frame → OR/ONH/Asia/London NaN in both `levels` and `session_levels`, while dVWAP/TPO/APOC/prev30m still emit (as ES unless overridden) | UI / `load_dataset` hide this. Notebook / assistant resample preview (`api.preview_resampled_ohlcv` omits `session`) can hit it. |
| **M4** | **Clock-incomplete OR / Asia / London / APOC / TPO emit after clock** | S2 | Family clock gates | Missing 09:30 still emits 15-min OR at 09:45 from 09:31–09:34 | Documented, not lookahead. Strategies that assume “15-minute OR means 15 minutes of bars” are wrong on gappy 15s-primary. |
| **M5** | **`naked_only` is zone-admission, not per-`CandidateLevel`** | S3 | `engine/signals.py` `_naked_count` | `naked_only=any` + 3c fires on a tested sibling inside an admitted zone. Non-base: filter uses early-window zone `bar_index`, metadata uses HTF arrival | Combined with H14. Formation-bar naked stays True even if that bar traded the level. |
| **M6** | **ETH / after-close flatten is not CME-session flatten even if C1 is fixed** | S4 | `backtest.py` `normalize()` + 16:00 | Isolated Mon 18:30 + close Mon 16:00 → empty (silent drop). Tue 02:00 → hold through RTH | Matches written ASSUMPTIONS (“RTH-style, ETH overnight not modeled”). Contradicts a “session close” mental model. Uses neither `trading_session_date` nor clock `session`. |
| **M7** | **Silent non-fills have no skip row** | S4, S5 | `simulate_trades` `continue` for 3c void / missing entry bar / empty flatten cap | “Accepted trades / candidates” looks like voids vanished | Focus / metrics under-count attempted entries. Disabled OTF stamps `otf_filter_passed=True` (`otf_filter_enabled=False`) — filter-on-`passed` alone is a lie. |
| **M8** | **`pnl_points` gross vs crowned R net, unlabeled in export** | S4, S5, S7 | Engine trade columns; `reporting.py` / page 11 CSVs | Costs > 0: analyst sums exported `pnl_points` vs `trade_summary.total_r` | Glossary / analytics use net R. Defaults (zero cost) hide the split. Report MD quotes net R next to unlabeled gross columns. |
| **M9** | **Overlapping WFA test windows: headline OOS R is a fold-sum** | S5 | `analytics/walk_forward.summarize_walk_forward` | `step_sessions < test_sessions` → `aggregate_test_total_r` double-counts; stitched equity is deduped | UI overlap help mentions stitched equity only. |
| **M10** | **WFA matrix / grid ranking are selection surfaces without an adjacent “do not pick the greenest cell” line** | S5 | `pages/10_Validation.py` heatmap; `pages/8_Grid_Search.py` ranking help | Greenest `median_test_expectancy_r` / best in-sample SL/TP | ASSUMPTIONS warn. Pages invite the contest. Same class as Study crown (H16). |
| **M11** | **R10 `both_hit_rule` ≠ selected R12 — documented, not labeled on Validation UI/report** | S5 | `analytics/excursions.py`; `pages/10_Validation.py`; `reporting.py` | User sets R12 `path_open_proximity` while R10 stays `stop_first`; `P(target)` disagrees with engine ambiguity | Independent diagnostic by contract. UI never says “≠ R12.” |
| **M12** | **Portfolio correlation is pre-admission** | S5 | `analytics/portfolio.py` `setup_correlation_matrices(candidates)`; page 13 | `single_position` drops overlaps; heatmap still shows candidate-path correlation | KPIs use `admitted`. No “pre-admission” caption. |
| **M13** | **Time Analysis clock mix + `entry_*` names on exit-grouped tables** | S5 | `analytics/time_analysis.add_time_buckets` | Exit-basis table rows labeled `entry_rth_segment`. Calendar `entry_date` ≠ `trading_session_date` | Three clocks in one product. Thin-sample warning without hide (unlike combo). |
| **M14** | **Page 12 hash / leftover session keys (nonce does not cover H1)** | S7 | `pages/12_Research_Bundles.py`; ARCHITECTURE nonce claim | Tampered `trades.parquet` imports. Leftover `focused_trades` / `display_timezone` / path captions survive | Three integrity bars (see §3). Do not treat import as open-exact. |
| **M15** | **`PIPELINE.dispatch(confirmed=True)` skips repository Confirm; `STUDY.run` under 200 cells executes without the approval triple** | S7 | `assistant` handlers / `study/tools.py`; page 14 uses `execute_confirmed_run` | `study_tools` on + 40-cell study + `confirmed=True` without `payload.approval` executes. Chat does not call `PIPELINE.dispatch` | Default-off flags are real. Under-threshold execute is by design and under-documented. |
| **M16** | **Bundle analytics tools skip hash verification** | S7 | `assistant/tools.py` `summarize_bundle_time_analysis` / `run_bundle_otf_validation` / `preview_bundle_resample` / `validate_bundle_roll_assumptions` | Swapped file at an allowed path → invented-looking analytics from tampered bytes | Discuss/complete_run paths that pass `expected_hash` stay fail-closed. AGENT_GUIDE “every numeric claim needs a packet path” is Discuss/Explain only. |
| **M17** | **`global_cluster` missing columns → empty zones, Study cell `ok` + 0 trades** | S3, S6 | `engine/confluence.py` silent `present_cols` drop; anchor_rules raises | Token admitted but column not computed (H4 plane mismatch) | Low-N, not `failed`. Anchor path is fail-closed. |
| **M18** | **Wrong naive `source_timezone` is a silent shift** | S1 | `data/loader.py`; NT default UTC | NT file already in ET, left on UTC default → 4–5 hour shift | Documented operator contract. Easy to miss next to “aware ignores selector.” |
| **M19** | **Legacy dual-upload R12 interval inferred, not declared; volume not reconciled** | S1, S4 | Data-page `_load_subtimeframe_upload`; `engine/intrabar._resolve_bar_intervals` | Sparse 15s with modal 30s gaps treated as a 30s grid (`expected_count=2`) | 15s-primary / `run_experiment` declare `15s`. Incomplete conservative attach is intentional; the expected grid can be wrong. |
| **M20** | **Phase 8 `validation_summary` / goldens-as-correctness process debt** | S0, S5, S7 | `reporting.py`; `tests/fixtures/golden/README.md` | 705 / 313 / 292 passed cited as proof flatten / restore / composer honesty | Goldens cover default-off legacy, OTF-enabled identity, Admit-enabled identity. Uncovered: R13 on, conservative R12, costs > 0, `single_position`, flatten, cutoff-without-flatten. |

### Low

| ID | Title | Slice(s) | Notes |
|---|---|---|---|
| **L1** | Signals / trade-review charts plot fill `timestamp`, not `trigger_timestamp` / OTF `T` | S3, S4 | No engine rewrite. Decision clock is hidden. |
| **L2** | Saved-run canonicalize sorts by `timestamp` | S3 | Values kept; order / RangeIndex change. |
| **L3** | `confirm_3bar` helper + residual fill remain | S3, S4 | Product generation closed. Hand-built rows still execute. Untested in phase5. |
| **L4** | `otf.py` module docstring still denies backtest/grid/WFA integration | S0, S4 | True of file purity; product integration is `otf_filter.py` / `otf_integration.py`. |
| **L5** | TPO developing vs prior last-bracket gap | S2 | Last RTH 30m bucket rarely develops (no RTH bar at 16:00) but is in next `pSinglePrint`. Causal; easy to misread. |
| **L6** | `api.preview_resampled_ohlcv` omits `session` | S1, S2 | Data-page preview re-tags. Feeds M3. |
| **L7** | 15s plan Goals vs v2 body (sparse minutes retained) | S1 | Code = v2. ARCHITECTURE + ASSUMPTIONS match v2. |
| **L8** | Global greedy confluence cap discards leftover levels; anchor `level_count` includes the anchor | S3 | Diagnostics honesty, not lookahead. |
| **L9** | Voice live PCM can speak ungrounded digits; `require_tool_for_numbers` is dead config | S7 | Persisted transcript is fail-closed. Voice default-off. |
| **L10** | Audit `tool_entry.request` not secret-scrubbed | S7 | Default UI path does not put keys in payloads. `.env.example` is store-dir only. |
| **L11** | Study ledger `skipped` never assigned; package `__init__` imports execute when Studies page loads | S6 | Viewer source allow-list holds. Process import ≠ second runner unless called. |
| **L12** | `app.py` hub copy still linear through Report; Studies is a parallel product | S0, S7 | README workflow stops at Backtest. |
| **L13** | Help-corpus paths frozen; Help uses corpus digits, not packet paths | S7 | Do not move USER_GUIDE / ARCHITECTURE / ASSUMPTIONS / METRICS / otf-filter / research-methodology / README to “fix” honesty. |
| **L14** | `ENGINEERING_PROPOSAL.md` §§1–3 are a pre-R9 snapshot | S0 | Do not use as capability SoT. Living status → `ENGINEERING_ROADMAP.md`. Normative living content is §4 only. |

---

## 5. Locked contracts (do not invert)

This is the SoT the next engineer must not invert. Open product decisions are §5.5 — do not assume they will change.

### 5.1 Pipeline / composers

1. **Two execution composers.** UI pages call engine/analytics directly. `run_experiment` is the headless composer. CLI / Study / Assistant call `run_experiment` only (different `execution_origin` / cache / `base_directory`). Pages do **not** call `run_experiment`.
2. **Shared validator, not shared defaults.** `validate_run_spec` is one function. Omitted `ingestion_mode` = `primary`. Omitted levels keys = product `DEFAULT_LEVELS_SETTINGS`. Omitted battery `enabled` = **True** on API/CLI/assistant; Study expand emits `{enabled: false}`.
3. **Two levels planes.** Product = `DEFAULT_LEVELS_SETTINGS` via `normalize_levels_config` (UI first-visit, `api.compute_levels`, Study omit/merge). Library = `compute_all_levels` keyword defaults (OR 30, gates False). Classic snapshot `_normalize_levels_settings` is a third path (missing Stage 6 keys → OFF / ticks 1). Bare `compute_all_levels(df)` is **not** the product experiment.
4. **`validate_setup_config` does not reject `BASE_COLUMNS`.** UI pickers do. Hits (`prev30mVWAP_hit_*`) stay rejected. Study factors cannot name `close` today.
5. **OTF `T` = `trigger_timestamp` else `timestamp`** (filled 3c: **reversal**, not fill). OTF TZ: UI may use session `exchange_timezone`; API OTF uses `inst.exchange_tz`. Default off. Disabled ≠ passed. Resolve order: `signal_settings["otf_filter"]` if key present → setup snapshot → `last_signal_setup` → `setup_config` → disabled.
6. **Cutoff-without-flatten is headless-legal; UI/classic-export force `None`.**
7. **`run_experiment` always backtests the levels frame.** UI prefers levels else data.
8. **`run_batch` fail-fast, `origin=cli`, no `status` column, index written only if all cells succeed.** `run_study` continue, `origin=study`, index includes `status`. Relative paths: experiment parent vs StudySpec parent vs assistant dataset parent. **Replay of `experiment.yaml` is not `study run`.**
9. **Cache:** API default `off`; CLI/Study/Assistant `read_write`. Cold vs warm bundle hash equal on tested paths including 15s-primary. `execution_origin` excluded from identity. `dataset_id` excludes ingest story; `source_binding_key` includes it. Subtimeframe is never a data artifact. Engine-version drift is a miss.
10. **Goldens ≠ correctness.** Legacy / OTF-enabled / Admit-enabled identity only.

### 5.2 Clocks / data / levels

11. **Canonical OHLCV:** tz-aware exchange TZ, `open/high/low/close/volume`, optional clock `session`. Display TZ is export-only.
12. **`session` ≠ `trading_session_date`.** Do not group, flatten, or fold on `session` as a CME date. `eth_start=18:00` is the date contract; `rth_*` is RTH membership. All four symbols share both.
13. **15s-primary** = `quantower_history_exporter` only; policy `observed_aligned_15s_to_1m_v2` (sparse on-grid retained; misaligned dropped; no empty-bar synth). Derived 1m ≠ vendor 1m. OHLC-identical 15s resolved (lowest volume); conflicts fail-closed; native 1m never auto-deduped. Omit mode → primary. `subtimeframe_path` illegal in derive mode.
14. **R12 data:** no upsample, no interpolation, volume not reconciled. Strict fail-closed; conservative incomplete → fallback reasons; OHLC mismatch fatal. Compatibility report never patches.
15. **Rolls:** metadata/gap diagnostics only. No continuous synthesis.
16. **Resample `1D`/`4h` is midnight-origin, not a CME session.** OTF cannot select them (5/15/30m only).
17. **Clock-gated levels emit on clock, not full bar coverage.** Incomplete in-window data is a valid emit. Same-bar close in rolling series is documented intent.
18. **`prev30mVWAP_hit_*` are diagnostics.** Price stack `prev30mVWAP` / `_k` is setup-eligible.
19. **Missing `session`:** `sessions.py` does not re-tag (NaN session-dependent). Gated families re-tag with the compute `instrument`. UI tags first; `api.compute_levels` does not.
20. **`session_levels` is not a collapsed session table.** Second `compute_session_levels` is redundant and currently argument-identical.

### 5.3 Signals / fills / analytics

21. **OTF is not applied at generation.** Full candidate population. A disabled blob on `signal_settings` is not “OTF ran and passed.”
22. **Public triggers:** `touch` / `reject` / `break` / `reclaim` / `3c`. `arrival_tolerance_ticks` ignored (0). 3c never backdates to arrival. Simple = next-bar open. 3c filled = retrace on `entry_bar_index`. 3c void = no fill, no skip. Residual `confirm_3bar` still fills if handed in.
23. **Two confluence engines / two tested objects.** Global = shared tick window, greedy, cap 5. Anchor = per-rule ticks, required/optional. Simple = zone envelope. 3c = each `CandidateLevel`.
24. **Admit** is entry-bar local time (C2). Focus is **not** `simulate_trades` (C8). C7 identity is `allow_all` + 0 cooldown only.
25. **Costs default zero.** `pnl_currency` / `r_multiple` net; `pnl_points` gross; `stop_price` = initial risk.
26. **Exposure default `allow_all`.** Independent overlapping fills. Restrictive policies sort and skip.
27. **R12:** no upsample. Same-sub-bar SL+TP (+entry) → SL, never TP. `sl_first` does **not** clip to post-entry on 3c. MAE/MFE are full-parent. R10 `both_hit_rule` ≠ selected R12.
28. **R13:** opt-in. Commit after completed parent bar; active next bar. 3c/confirm do not arm on the entry parent.
29. **Session flatten is calendar-RTH, not CME session, and today is leaky.** Do not treat `SESSION_CLOSE` as `trading_session_date` close. Empty cap is a silent non-fill. Do not assume flatten trades are per-entry-date until C1 is fixed.
30. **Focus** filters completed `trades` on `entry_timestamp` and subset-replays equity. It does not consume skip / OTF-reject frames. Under non-`allow_all` it may over-state Admit counts.
31. **WFA session folds** key by `trading_session_date` + `eth_start`. `fold_local` vs `causal_prefix` as §2.4. Per-fold SL/TP selection uses train-grid only. `run_wfa_matrix` default metric is OOS. **OTF-matrix train sims use the full `source_df`.**
32. **Core KPIs match `METRICS_GLOSSARY`.** Combo / prev30m invent neither fills nor signals. prev30m in-window NaN is not 0. Portfolio is a stitch, not a capital simulator; correlation is on **candidates**.
33. **Phase 8 is in-sample diagnostic.** “Diagnostic only” is page-level; Phase 8 export is weaker than R10+. No machine-readable `diagnostic_only` flag.
34. **Study** is a composer over `validate_run_spec` + `run_experiment`. It does not call `run_batch`. It does not run Focus or `run_otf_validation_matrix`. Ranking stays in-sample `primary_metric`. Failed cells: ledger+index `failed`, null PF/WR, no zip; excluded from ranked/promote; included in overview CSV and rollup N. Promote writes drafts, never executes. Inspect/viewer do not call `run_study`. Page must not write classic research keys. A ranked / promoted cell is **not** a deployable parameter.

### 5.4 Persistence / bundles / assistant

35. **Nonce invalidation** prevents leftover *upload widgets* from replacing imported `data` after Data-page navigation. It does **not** clear `otf_filter_summary`, `setup_config`, or `focused_trades`.
36. **Page 12 import** is schema-only. Assistant complete/open-exact is hash-fail-closed. Report is session export, not re-sim.
37. **Bootstrap** rehydrates saved `data` when missing — including after a dataset-less bundle import.
38. **Dotenv loads only `THESISTESTER_STORE_DIR`.** Secrets via env / Streamlit Secrets, never `assistant.toml` / `.env.example`.
39. **`STUDY.*` default-off.** When on: over `confirm_above_runs` (default 200) requires bound approval triple; under threshold, `confirmed=True` executes. Voice default-off; voice tools cannot execute.
40. **Discuss/Explain numbers require packet paths + auditor.** Help uses corpus digits. Live voice PCM is not pre-gated. Prose cannot become RunSpec keys. Chat never `dispatch` / `execute_confirmed_run`. Page 14 Run confirmed goes through `execute_confirmed_run`. Direct `PIPELINE.dispatch(confirmed=True)` is a separate library gate.
41. **Help-corpus paths stay frozen.** Do not move the living Help set to “fix” honesty.

### 5.5 Still open (do not assume a fix)

Whether flatten will store per-candidate `entry_local_ts`. Whether after-close ETH entries will skip, hold to next RTH 16:00, or use `trading_session_date` close. Whether `allow_all` stays the default. Whether `sl_first` will honor `entry_activation_price` for 3c. Whether UI will allow cutoff without flatten (or YAML will reject it). Whether `validate_setup_config` will reject `BASE_COLUMNS`. Whether battery `enabled` will default false (Study already emits false). Whether API OTF will honor `dataset.exchange_timezone`. Whether `dataset_id` will include `ingestion_mode`. Whether page 12 will require `canonical_bundle_hash`. Whether bootstrap will refuse to refill `data` after a dataset-less import. Whether Study will pin `dataset.path` at expand time and search the original YAML parent on promote. Whether Build Advanced OFF will emit explicit `enabled: false`. Whether Phase 8 JSON/MD will gain `diagnostic_only`. Whether `confirm_3bar` will be deleted. Whether PIT will gain future-shock rows for `dOpen*` / `prevSettlement` / `pm` profile / asserted `pw*`/`pm*`. Whether AGENT_GUIDE L38–39 will stop advertising experiment.yaml replay as identity-equivalent.

---

## 6. Recommended fix order

Highest **research honesty** first. Not “easy first.” Not “align goldens first.” Each step should add a test that would have failed on the slice probe, then update the living doc that currently overclaims.

| Order | Fix | Closes | Why this order |
|---|---|---|---|
| **1** | Store per-candidate `entry_local_ts` on the flatten walk. Add multi-signal ETH + mixed RTH fixtures. Decide (and document) after-close ETH: skip vs next RTH 16:00 vs `trading_session_date` close. Emit a skip reason on empty cap. | C1, M6, M7 (flatten), S5 `SESSION_CLOSE` poison | Silently wrong fills on any flatten run with >1 candidate. Every downstream metric inherits the lie. |
| **2** | Slice OTF-matrix train/OOS `simulate_trades` to the chronological split (WFA already does). Keep ranking on train columns. Add the Slice 5 probe as a test. | C3 | Validation ranking is the product’s “is this filter robust?” answer. A train expectancy that includes OOS spikes is confirmatory leakage. |
| **3** | Pin Study `dataset.path` at expand (absolute, or rewrite emitted `experiment.yaml` for the replay parent). Promote/launch must search the **original StudySpec parent** before cwd. Stop advertising `thesistester run experiment.yaml` as identity-equivalent until that is true. | C2, H2 | Identity of “the same study.” A coworker replay or promote draft can crown a different CSV. |
| **4** | Manage `otf_filter_summary` / `backtest_otf_filter` / `setup_config` / `focused_trades` on restore. Reporting must read `backtest_otf_filter`. Page 12 hash-fail-closed (assistant parity). Bootstrap must not refill `data` after a dataset-less import. | H1, M14 | Restored bundles are how results leave the machine. Leftover OTF counts on imported trades is a fabricated admission story. |
| **5** | Reject `BASE_COLUMNS` in `validate_setup_config` (same bar as hits). Engine second-check optional but the validator is the shared gate. | H3 | Headless can invent `close\|ONH` zones today. One function fix covers API/CLI/Assistant/hand-edited Study YAML. |
| **6** | Honor `entry_activation_price` on `sl_first` for 3c (or stop claiming pre-entry exclusion in ASSUMPTIONS). Cover in goldens or a dedicated family. | H6 | Default model SL-kills 3c on pre-retrace extremes. Changes fill counts on the product default R12. |
| **7** | One battery `enabled` default (Study’s `{enabled:false}` / omit-means-off). One levels omit semantics (explicit `false` when Advanced off; stop dual normalizers or label them). | H4, H8 | Omitted keys currently mean product-on (levels) and battery-on (API) and battery-off (Study). That is the operational foot-gun. |
| **8** | Align OTF TZ (API honors `dataset.exchange_timezone` or UI stops preferring session TZ). Align cutoff-without-flatten (UI allow or YAML reject). Align fatal OHLCV (Data page = API). | H7, H10, H15 | Same RunSpec, two admissions / two datasets. Parity tests must be cross-composer, not same-composer. |
| **9** | Encode ingest story on `dataset_id` / levels cache (or stop serving levels artifacts across primary vs 15s-derived). | H9 | Cache honesty. Bindings already partition; the levels object does not. |
| **10** | Disclose `allow_all` inflation on Backtest/Grid; state Focus N may exceed Admit under restrictive exposure; Phase 8 banner + no `st.success` on p; label `pnl_points` gross; R10 ≠ R12 sentence; WFA overlap headline = fold-sum. | H5, H12, H13, M8–M11 | Presentation bugs. The math is often already honest in ASSUMPTIONS / glossary and silent on the page that researchers read. |
| **11** | Study report Failed section; rollup `cell_count` ok-only (or labeled); optional WFA OOS crown when WFA ran. Snap non-base 3c projection to `base_end` (like simple) or document stale developing-level as first-class. | H16, H14, M5 | Study honesty and 3c HTF semantics. After identity (step 3) so the MD describes the bytes that actually ran. |
| **12** | Canonical ingest UTC-normalize (vendor already does) or a typed `DataValidationError` without a fake `utc=True` hint. PIT table: drop overclaimed Tests cells; add future-shock for `dOpen*` / `prevSettlement` / `pm` / asserted `pw*`/`pm*` / OR. | H11, M2 | Ingest over-close and doc overclaim. Do not block fill/identity fixes on these. |
| **13** | Doc-only: AGENT_GUIDE L38–39; `otf.py` module docstring; proposal §§1–3 already bannered; Help corpus stays frozen. Delete or quarantine `confirm_3bar` residual. | L3, L4, L14 | After code SoT is true. Do not amend living Help paths casually. |

**Do not start here:** regenerating goldens, adding more named-test volume without the probes above, “aligning” UI copy without changing admissions, treating a green CI as flatten/restore proof.

---

## 7. What was NOT found

These were in-scope concerns across slices and are **closed as absent** on the audited checkout. Do not reopen them as if they were found.

| Concern | Verdict | Evidence home |
|---|---|---|
| Silent continuous-contract / roll price synthesizer | **Absent.** R7 never rewrites OHLC. Gaps remain in prices. Operator-declared `external_continuous` is honesty risk, not a code path. | S1 Q3 |
| 3c backdate `bar_index` / `timestamp` to arrival | **Absent.** Filled → fill bar; void → reversal bar. Charts do not rewrite cells (save may sort). | S3 Q3, Q7 |
| OTF applied at signal generation | **Absent** on UI, API, Study, CLI. Stored, not applied. Decision T for later admission is reversal/`trigger_timestamp`, not fill. | S3 Q5; S0 composition fact 1 |
| Conflicting 15s OHLC silently dropped | **Absent.** Conflicts fail-closed. Only OHLC-identical (incl. volume-only) resolve. Native 1m never auto-deduped. | S1 Q2 |
| Early emit of OR / Asia / London / APOC before clock gate | **Absent** under correct `session` tags. Incomplete emit *after* clock is documented. | S2 Q4 |
| Family grouping on clock `session` as a CME date | **Absent** in `levels/`. Date-grouped families call `trading_session_date`. | S2 Q7 |
| WFA session-fold off-by-one / `causal_prefix` including fold-start or post-fold bars | **Absent** on probed ETH overnight session folds. Prefix `<` fold start. Suite is under-tested (RTH fixtures). | S5 Q2 |
| WFA per-fold train selection peeking at test metrics | **Absent.** Test sim after `best_grid_result(train_grid)`. | S5 Q4 |
| Combo / prev30m inventing fills or treating in-window NaN as 0 | **Absent.** prev30m uses last finalized flag. | S5 Q7–Q8 |
| Prose → executable RunSpec keys | **Absent** on `thesis_compiler` / `classic_export`. Chat never dispatch/execute. | S7 Q6 |
| Secrets in TOML / `.env.example` / default dotenv | **Absent.** Store-dir only. Provider errors sanitized. Residual: caller-controlled audit payloads. | S7 Q5 |
| Second Study simulator / in-process page `run_study` | **Absent.** Page spawns CLI. Viewer does not import execute. Package `__init__` still *imports* execute (process residual, not a second engine). | S6 Q3, Q5 |
| Upsample / empty-bar synthesis on R12 or derive | **Absent.** | S1 Q7–Q8; S4 Q7 |
| Goldens as proof of correctness | **Not a finding against the golden harness — a process contract.** Three families prove identity. They do not prove flatten, restore, composer admissions, or 3c entry-bar `sl_first`. Passing 126/352/357/705/327/292/313 is not a merge close. | All slices § goldens |

**Also not a hidden third composer:** CLI, Study, and Assistant do not invent fills. They disagree with UI (and with each other) on **defaults, path parents, abort semantics, and leftover keys** — which is enough to change the experiment.

---

## 8. Pointers to per-slice PRs (full evidence)

Use this file as the action list. Use the slice PR for probes, line citations, and Q-by-Q traces. Do not re-audit a locked layer unless you are implementing a fix in that layer.

| Slice | PR | Read when | Do not use it to |
|---|---|---|---|
| **0** [#390](https://github.com/AccumuLatata/ThesisTester/pull/390) `AUDIT_OVERVIEW.md` | Need the module map, session-state bus, or why the audit is 7 slices not 5 | Treat overview flags as proven findings (they were map-depth) |
| **1** [#391](https://github.com/AccumuLatata/ThesisTester/pull/391) `AUDIT_SLICE1.md` | Ingest / TZ / derive / rolls / `session` vs `trading_session_date` / R12 **data** contract | Re-open loader math when fixing flatten or Study paths |
| **2** [#392](https://github.com/AccumuLatata/ThesisTester/pull/392) `AUDIT_SLICE2.md` | Family-by-family causal table, product vs keyword defaults, PIT table overclaims | Re-audit `trading_session_date` arithmetic |
| **3** [#393](https://github.com/AccumuLatata/ThesisTester/pull/393) `AUDIT_SLICE3.md` | Zone/signal row contracts, 3c fill/void index, `close` probe, OTF-not-at-generation | Re-audit 3c 4-rule math when fixing `sl_first` or OTF `T` |
| **4** [#394](https://github.com/AccumuLatata/ThesisTester/pull/394) `AUDIT_SLICE4.md` | Flatten leak trace, `allow_all` probe, cutoff-without-flatten, R12 residual SL, WFA OTF source contract | Treat goldens 705 as flatten correctness |
| **5** [#395](https://github.com/AccumuLatata/ThesisTester/pull/395) `AUDIT_SLICE5.md` | OTF-matrix probe, Focus vs Admit, session-fold + `causal_prefix` probe, Phase 8 UI | Re-open fold construction when implementing C3 (reuse WFA slicing) |
| **6** [#396](https://github.com/AccumuLatata/ThesisTester/pull/396) `AUDIT_SLICE6.md` | Three path-resolution planes, promote pin, product-plane levels, failed-cell honesty | Treat `thesistester run experiment.yaml` as `study run` |
| **7** [#398](https://github.com/AccumuLatata/ThesisTester/pull/398) `AUDIT_SLICE7.md` | Restore leftovers, hash bars, battery default-on, `dataset_id`, assistant gates. **§5 of that file is locked into this merge.** | Re-open fill/3c/WFA math; collapse page 12 / Report / open-exact into one bar |

**Inherited bugs on restored bundles** (do not re-open the math; they travel): C1 flatten leak, C3 if the zip contains an OTF-matrix artifact from a classic Validation session, H3 `close` zones, H5 `allow_all` N, H6 3c `sl_first`, H12 Focus overlay leftovers, H13 Phase 8 dict without `diagnostic_only`. Slice 7 restore (H1) can **attach the wrong leftover diagnostics** to those already-wrong trades.

---

## How the next engineer should start

1. Treat §5 as locked. Do not invert two composers, two levels planes, `session` ≠ `trading_session_date`, OTF-not-at-generation, Focus ≠ Admit, or `experiment.yaml` replay ≠ `study run`.
2. Implement §6 steps 1–4 before any golden regen or Help-corpus edit.
3. For each fix: add the slice probe as a regression test; update the one living doc that overclaims (ASSUMPTIONS / AGENT_GUIDE / PIT table / `otf-filter.md`); leave frozen Help paths in place unless the honesty sentence already lives there.
4. Goldens still do not prove the fix. Cross-composer fixtures (UI widget vs YAML vs Study expand vs assistant `_bounded_spec`) do.
)
