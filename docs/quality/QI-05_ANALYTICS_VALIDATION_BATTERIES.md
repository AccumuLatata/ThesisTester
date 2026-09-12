# QI-05 — Analytics and validation batteries

**Slice:** QI-5 (research-only)
**Status:** Completed
**Audited commit:** `32ad34c` (`32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc`) — `main` after [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) (QI-11)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi5-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 14 (C/H/M/L = 0/4/8/2)
**Time spent:** one agent run on 2026-09-12
**Inputs (premises, not re-audited):** `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1. Fold construction and `causal_prefix` are locked (AUDIT S5 / AH §2 item 6). `validation_summary()` shape is not altered.

This report does **not** call any backtest, metric, or Study result correct or reliable. Vocabulary is plan §3.3.

## Commands run (verbatim)

```bash
git fetch origin main
git fetch origin cursor/audit-final-merge-3a8e
git checkout -B main origin/main
git checkout -b cursor/qi-05-analytics-batteries-6b55
git rev-parse HEAD   # 32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc

export THESISTESTER_STORE_DIR=/tmp/qi5-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no
# 3966 passed, 5 skipped in 146.22s (0:02:26)

radon cc -s -a <QI-5 files> -n D
radon mi -s <QI-5 files>
vulture <QI-5 files> --min-confidence 60
rg -n 'except Exception|except:' <QI-5 files>
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' <QI-5 files>
rg -l '^import streamlit|^from streamlit' thesistester/analytics
rg -c 'st.session_state' pages/8_Grid_Search.py pages/9_Time_Analysis.py pages/10_Validation.py pages/13_Portfolio.py

PYTHONPATH=/workspace python3 /tmp/qi5/probe_qi05.py
# /tmp/qi5/probe_results.json
PYTHONPATH=/workspace python3 /tmp/qi5/verify_qi05.py
# /tmp/qi5/verify_results.json (seed CI / WFA overlap / Policy AST / radon spot)

export THESISTESTER_STORE_DIR=/tmp/qi5-store-scope
pytest -q --tb=line \
  tests/test_otf_validation.py tests/test_walk_forward.py \
  tests/test_phase8_validation.py tests/test_phase6_grid.py \
  tests/test_monte_carlo.py tests/test_overfitting.py \
  tests/test_noise.py tests/test_sensitivity.py \
  tests/test_excursions.py tests/test_portfolio.py \
  tests/test_phase7_time_analysis.py tests/test_confluence_attribution.py \
  tests/test_prev30m_vwap_hit_analytics.py \
  tests/test_api.py::test_validation_r16_noise_is_opt_in_and_seeded
# 240 passed in 14.70s

PYTHONHASHSEED=7 pytest -q --tb=no -p no:cacheprovider \
  tests/test_otf_validation.py tests/test_walk_forward.py \
  tests/test_phase8_validation.py tests/test_monte_carlo.py
# 88 passed in 8.49s
```

Probe script lives at `/tmp/qi5/probe_qi05.py` (pasted in §10). Transcripts are not committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership; 18 files):

| Path | Role |
|---|---|
| `thesistester/analytics/__init__.py` | Re-exports (QI-5 owned; `metrics` / `entry_window` symbols are QI-4-owned modules) |
| `thesistester/analytics/grid.py` | SL/TP sweep (`run_sl_tp_grid` E 33) |
| `thesistester/analytics/walk_forward.py` | WFA (`run_walk_forward_sl_tp` F 50) |
| `thesistester/analytics/validation.py` | Phase 8 `validation_summary` (shape frozen) |
| `thesistester/analytics/monte_carlo.py` | R11 |
| `thesistester/analytics/overfitting.py` | R15 (MI 16.09) |
| `thesistester/analytics/noise.py` | R16 |
| `thesistester/analytics/sensitivity.py` | R19 |
| `thesistester/analytics/excursions.py` | R10 |
| `thesistester/analytics/portfolio.py` | R21 |
| `thesistester/analytics/time_analysis.py` | Phase 7 buckets |
| `thesistester/analytics/otf_validation.py` | OTF matrix (AH3 / C3 probe home) |
| `thesistester/analytics/confluence_attribution.py` | Combo attribution (MI 0.00) |
| `thesistester/analytics/prev30m_vwap_hit.py` | prev30m hit R |
| `pages/8_Grid_Search.py` | Composer A grid |
| `pages/9_Time_Analysis.py` | Time + Focus overlay |
| `pages/10_Validation.py` | Validation / WFA / batteries (1,949 LOC, 4 defs) |
| `pages/13_Portfolio.py` | R21 page (0 defs, 122 LOC) |

**Read as spec only (not owned):** `docs/METRICS_GLOSSARY.md` (QI-13); `AUDIT_FINAL` §5; AH §2. `analytics/metrics.py` and Admit half of `analytics/entry_window.py` are QI-4-owned. Focus helpers in `entry_window.py` were read only for H12 status (`summarize_focused_trades`, `FOCUS_HONESTY_BANNER`). `study/schema._INDEX_PRIMARY_METRICS` and `reporting.py` `## Validation Diagnostics` were read for H16 / H13 status (QI-7 / QI-6 files).

**Skipped**

- Mutation sample on `walk_forward.py` — already measured by QI-11-04 (60% own-file); not re-run.
- CAI `realistic` RSS / flame graphs — QI-14.
- Re-opening fold construction / `causal_prefix` math (AUDIT S5 locked).
- Altering `validation_summary()` keys.
- AppTest of pages 8/9/10/13 — QI-10.

---

## 2. Code-quality readout

### 2.1 Metrics table (this scope)

| Metric | Result | Trigger action |
|---|---|---|
| `radon cc` D+ | `run_walk_forward_sl_tp` **F 50** (mandatory); `run_sl_tp_grid` E 33; `summarize_by_group` D 30; `sensitivity_summary` D 27; `summarize_by_pair_and_trigger_variant` D 23; `cscv_pbo` D 22 | F → QI-05-01. Others classified below |
| Module MI | `confluence_attribution.py` **C 0.00**; `pages/10_Validation.py` **C 0.00**; `overfitting.py` B 16.09 (trigger < 20); `walk_forward.py` A 21.10; others A | Two MI=0 findings |
| Function length > 150 | `run_walk_forward_sl_tp` **526** physical lines; `run_sl_tp_grid` 243 | Same two orchestrators |
| Broad `except` | 2, both in `otf_validation.py` | One **hides defect** (QI-05-12); one re-raises `ValueError` (**narrow-guard OK**) |
| `vulture` ≥60 | 20 candidates | All public combo helpers / dataclass fields — **false positives** (page/API/tests import them) |
| Streamlit in library | 0 in `thesistester/analytics/` | R18 holds |
| Cross-module private imports | 1: `overfitting.py` → `grid._directional_grid_metrics` | QI-05-14 |
| `# noqa` / `# type: ignore` | 1: `otf_validation._simulate` imports `backtest._empty_trades_df` | QI-4 private helper |
| `st.session_state` matching lines | page 10 **140** · page 8 **49** · page 9 **25** · page 13 **10** | Key graph → QI-10 |
| TODO/FIXME | 0 | — |

Scope CC: 177 blocks, average **B 6.28**.

### 2.2 Hot-spot reading notes

**`run_walk_forward_sl_tp` (F 50, 526 lines).** One function owns fold-boundary construction, per-fold OTF source (`fold_local` / `causal_prefix` — not re-audited), train-grid selection, test sim, stitched-OOS overlap policy, and summary assembly. This is the analytics sibling of `simulate_trades` F 133: every battery that multiplies engine load goes through it. Decomposition is a QR-C candidate **after** QI-11-04 deepens own-file asserts. Fold math stays locked.

**`run_sl_tp_grid` (E 33, 243 lines).** Mostly parameter-forwarding into `simulate_trades` plus directional columns. Complexity is cartesian BE/trail expansion, not hidden state. Classified: maintainability cost is real but not a separate finding (no F-grade / no MI=0).

**`pages/10_Validation.py` (MI 0.00, 1,949 LOC, 4 defs).** Least-decomposed page in the product. Four helpers (`_fmt_value`, `_parse_positive_int_values`, `_fmt`, plus the module docstring claim). Everything else is inline sidebar + WFA + R15/R16/R19 + MAE + MC + Phase 8 + OTF matrix. `st.session_state` 140 lines.

**`confluence_attribution.py` (MI 0.00, 1,240 LOC).** Many small helpers; MI 0 is the radon “too many blocks / too long” collapse, not one F-grade function. Highest CC is `summarize_by_pair_and_trigger_variant` D 23.

**`overfitting.py` (MI 16.09).** Below the MI<20 trigger. `cscv_pbo` D 22 is combinatorial CSCV, not a hidden leak. vs-random is seeded via `SeedSequence`.

**Empty-trade scaffolding.** Duplicated `_empty_*` dicts in `validation.py` (four functions), `monte_carlo._empty_method_result`, `noise_summary` unavailable branch, `overfitting` `available=False` bases, `portfolio._empty_candidates`. Same pattern, not a shared helper. Classified: maintainability duplication, not a finding by itself.

**`except Exception` in `otf_validation._simulate`.** Swallows any `simulate_trades` failure into `_empty_trades_df()` (`# pragma: no cover`). A train/OOS row then looks like “0 trades” rather than an error. The loop-level `except Exception` around `apply_otf_filter` re-raises `ValueError` — **narrow-guard OK**.

### 2.3 Seed-discipline inventory (exit criterion)

| Module / symbol | RNG? | `random_state` | Threaded? | Notes |
|---|---|---|---|---|
| `validation.bootstrap_expectancy_ci` | `default_rng` | `int \| None = 42` | Yes | `None` = unseeded (documented). Page always passes a widget seed |
| `validation.permutation_test_expectancy` | `default_rng` | same | Yes | Shares seed with bootstrap inside `validation_summary` |
| `validation_summary` | via children | same | Yes | **No `schema_version`** (shape frozen — QI-05-13) |
| `monte_carlo_{reshuffle,skip,block_resample}` | `default_rng` | `int \| None = 42` | Yes | Each method builds its own `default_rng(same seed)` — independently seeded, deterministic |
| `noise.perturb_ohlc` / `noise_summary` | `default_rng` | **required int** | Yes | Replica seeds from a parent stream |
| `overfitting.random_entry_signals` | `default_rng` | required int | Yes | |
| `overfitting.vs_random_benchmark` | `SeedSequence` | int = 42 | Yes | Child seeds spawned |
| `sensitivity_summary` | **none** | int = 42, stored in `config` | Stored only | OAT is deterministic; seed is theater (QI-05-13) |
| `grid` / `walk_forward` / `time_analysis` / `excursions` / `portfolio` / `prev30m` / `confluence` | none | n/a | n/a | Deterministic given inputs |
| `otf_validation` | none | n/a | n/a | |

No `np.random.default_rng()` call in this scope lacks a `random_state` argument. Probe (`/tmp/qi5/verify_qi05.py`, 12 synthetic R values, n_bootstrap=200 / n_permutations=200 / n_simulations=80): seed 42 vs 42 identical for `validation_summary` and `monte_carlo_summary`; seed 42 vs 7 moves bootstrap CI (`ci_lower` −0.542 vs −0.492) and MC reshuffle `max_drawdown_r` p50 (3.0 vs 2.8). Reshuffle `final_r` p50 is seed-invariant (0.1 = 0.1; multiset preserved — by design, not a defect). `sensitivity_summary` OAT metrics are identical after stripping stored `config.random_state`.

### 2.4 Result-dict `schema_version`

| Battery | Key present? | Value |
|---|---|---|
| R10 `excursion_summary` | yes | 1 |
| R11 `monte_carlo_summary` | yes | 1 |
| R14 WFA `WalkForwardResult` / summary | yes | **2** |
| R15 `overfitting_summary` | yes | 1 |
| R16 `noise_summary` | yes | 1 |
| R19 `sensitivity_summary` | yes | 1 |
| R21 `portfolio_summary` | yes | 1 |
| Phase 8 `validation_summary` | **no** | shape locked (`bootstrap` / `permutation` / `trade_count` / `grid_overfit`) |
| OTF matrix | DataFrame, no version key | — |
| Grid | DataFrame, no version key | — |

No load-path version check in these modules (bundle load is QI-6).

---

## 3. Application-quality readout (§3.2 per entry point)

Entry points: page 8 Grid, page 9 Time Analysis, page 10 Validation, page 13 Portfolio; library `run_sl_tp_grid` / `run_walk_forward_sl_tp` / `validation_summary` / `monte_carlo_summary` / `overfitting_summary` / `noise_summary` / `sensitivity_summary` / `excursion_summary` / `portfolio_summary` / `run_otf_validation_matrix`.

| §3.2 check | Grid (8) | Time (9) | Validation (10) | Portfolio (13) | Library batteries |
|---|---|---|---|---|---|
| 1 Happy path | Requires session signals; not AppTested. Library 2×1 grid on 3-session synthetic ran (2 rows) | Requires session trades; golden time buckets computed | Phase 8 on golden trades ran empty-safe + seeded | `portfolio_summary` on two golden slices `available=True` | See §2.3 / batteries probe |
| 2 Empty / minimal | Page `st.stop` on missing signals | Page `st.stop` on missing trades | Page `st.stop` on missing trades. `validation_summary(empty)` returns nulls + `insufficient` | `<2` sources → `st.info` + stop; library raises `ValueError` | MC `available=False`; noise/overfit unavailable branches exist |
| 3 Malformed | Engine `ValueError` on empty SL list (probe: `"stop_loss_ticks_values must not be empty."`) | Focus `ValueError` → `st.error` | WFA / OTF `ValueError` → `st.error`. Broad page `except` not used | `ValueError` → `st.error` | Bad `otf_history_policy` → typed `ValueError` |
| 4 Stale-state | Inherits session signals/levels; no own invalidation | Focus keys popped on Clear | Reads leftover `otf_validation_*` (QI-6-03 handoff) | Updates `portfolio_*` keys | n/a |
| 5 Composer parity | Classic page calls `run_sl_tp_grid` directly (AH §2 two-composer lock). H7 cutoff fork locked (QI-05-10) | Study does not run Focus (AH §2 item 5) | Study does not call OTF matrix (AH §2 item 5) | Page calls `api.run_portfolio_analysis` (Composer B) | Headless omit-`enabled` is QI-6 H8 |
| 6 Honesty surface | Ranking help invites “best SL/TP” (QI-05-08). Policy has no `help=` (QI-05-09) | Focus banner honest post-hoc; silent on Focus≠Admit (QI-05-04) | `st.success` on p≤0.05 (QI-05-05). Page caption “diagnostic only” | Caption + `summary.caveat` present | Module docstrings carry diagnostic caveats |
| 7 Persistence | Grid defaults save/reset | Focus/Admit session keys only | Session only | Session only | No store namespace |
| 8 Performance envelope | Not measured (QI-14). R15/R16/R19 have **cost-estimate warnings** on page 10 | cheap | WFA/matrix multiply engine; cost warnings on R15/R16/R19; MC/WFA/OTF lack a numeric cost line | cheap | — |
| 9 Operability | Best-cell SL/TP shown; no identity hash | Focus provenance counts | WFA config stored; OTF selected-row caption | Setup IDs + skip table | `schema_version` on R10–R16/R19/R21/WFA |
| 10 Copy consistency | “Admit” inherited caption present | Focus vs Admit labels exist; over-statement sentence missing | “Train results drive ranking” still on OTF matrix (AH3 slicing is now prefix — copy is still the locked selection rule) | “not a capital/margin/fill simulation” | — |

### 3.1 Metric × glossary × caveat coverage (exit criterion)

Mechanical scan of labels/keys shown on pages 8/9/10/13 vs `docs/METRICS_GLOSSARY.md`. “Caveat” = glossary (or on-page caption) states diagnostic / not-proof / not-annualized.

| Metric / label | Pages | Glossary entry? | On-page / glossary caveat? | Note |
|---|---|---|---|---|
| `expectancy_r` / Expectancy (R) | 8, 10 | yes | yes | Core formula |
| `win_rate` | 8, 9, 10 | yes | yes | |
| `profit_factor` | 8, 9 | yes | yes (∞ on all-win) | |
| `total_r` / Total R | 8, 9, 13 | yes | yes | Page 13 “Portfolio total R” is the same quantity |
| `avg_r` | 9, 10 | yes (fallback) | yes | |
| `max_drawdown_r` | 9, 13 | yes | clip(0) documented | |
| `trade_count` | 8, 9, 10 | implied | sample-size on 10 | |
| `min_direction_expectancy_r` | 8 | yes | yes (recommended weaker-side) | |
| `probability_positive` / **P(mean R > 0)** | 10 | **no** | page caption diagnostic; label reads confirmatory | QI-05-11 |
| `p_value_positive` / **p-value (positive)** | 10 | no dedicated Phase 8 row (vs-random / DA5 p-values exist) | success-path caveat present | QI-05-05 / QI-05-11 |
| `outlier_dependency_ratio` | 10 | yes | yes (descriptive) | |
| `tail_ratio` | 10 | yes | yes | |
| `max_consecutive_losses` | 10 | yes | yes | |
| `ulcer_index_r` | 10 | yes | yes | |
| Median test expectancy | 10 | yes (“Test expectancy (R)” / “WFA matrix value”) | page “can still overfit” | matcher miss only |
| OOS profitable fold rate | 10 | yes | yes | |
| `aggregate_test_total_r` | **not shown as a widget** | yes (“sum of `test_total_r`”) | glossary names the sum, not overlap double-count | QI-05-07; UI shows median instead |
| `stitched_oos_total_r` | WFA equity chart | yes | overlap help: stitched only | |
| PBO / PSR / DSR | 10 | yes | yes + cost warning | |
| Vs-random p-value | 10 | yes (“not a significance claim” in DA5; R15 row) | caption diagnostic | |
| MAE/MFE / edge ratio | 10 | yes | yes | |
| Fragile parameter | 10 | yes | yes | |
| Noise fraction / persistence | 10 | yes | yes + cost warning | |
| Portfolio admitted / skipped | 13 | R21 “Portfolio admission” | page caveat | |
| Focus honesty banner | 9 | n/a (copy) | post-hoc / subset-replay | missing Admit-N sentence |

### 3.2 WFA “best cell” / battery cost warnings

- WFA matrix heatmap uses `RdYlGn` on `median_test_expectancy_r`. No adjacent “do not pick the greenest cell” line (QI-05-08).
- Grid ranking help: `"Metric used to find the best SL/TP pair."` — contest language (M10).
- Overlap widget help: `"Reject avoids double-counting by withholding stitched equity."` — does not name `aggregate_test_total_r` as a fold-sum (QI-05-07).
- Cost warnings **present** for R15 / R16 / R19 opt-in toggles. WFA / OTF matrix / Monte Carlo have no numeric replica-cost line (WFA cost is implicit in SL×TP×folds).

### 3.3 Portfolio vs R21

Page is 122 LOC / 0 defs and calls `api.run_portfolio_analysis`. Surfaces total R, max DD, admitted/skipped, equity, marginal contribution, return correlation, skip table, plus the R21 caveat. Matches glossary R21 scope (diagnostic merge, not margin). Completeness: shipped as specified; not a half-feature. Handoff: page-13 session keys → QI-10.

---

## 4. Prior-audit carry-over status

| Item | Status on `32ad34c` | Finding |
|---|---|---|
| **C3** OTF-matrix train path leak | **Closed-verified.** `tests/test_otf_validation.py` has **5** `test_ah3_*` probes. `run_otf_validation_matrix` slices `train_price_df = source_df.iloc[:split_bar]`. Math not re-audited | none (positive) |
| **H12** Focus over-statement | **Still open.** Probe: `single_position` all-day fills signals `{1,3}`; Focus 10:00–11:30 shows `{3}`; Admit re-sim shows `{2}`. Sets unequal. `allow_all` C7 identity holds (`{2,3,4}` = `{2,3,4}`). `FOCUS_HONESTY_BANNER` does not mention Admit or N-overstatement. Focus N>Admit N was **not** reproduced on this fixture (N=1=1); occupancy-conditioned fill substitution was | QI-05-04 |
| **H13** Phase 8 confirmatory UI / export | **Still open (partial copy mitigation).** `st.success` still fires when permutation `p≤0.05` (now with a “not a significance test” sentence). Metric label still `P(mean R > 0)`. `reporting.py` `## Validation Diagnostics` still has **no** diagnostic banner (QI-6 file; QI-06-02 already noted) | QI-05-05 |
| **H16** Study ranking ignores WFA OOS | **Still open** (QI-5 half). `study.schema._INDEX_PRIMARY_METRICS` = `{expectancy_r, total_r, max_drawdown_r, trade_count, profit_factor}`. `wfa_median_test_expectancy_r` is written on the study index (`execute.py`) but **cannot** be `primary_metric`. Failed-cell MD/rollup → QI-7 | QI-05-06 |
| **H5** Grid `allow_all` disclosure | **Still open** on page 8. Policy `selectbox` has no `help=` (verified by extracting the call). QI-04-02 covered page 7 | QI-05-09 |
| **H7** Grid cutoff-without-flatten | **Locked fork still implemented.** `effective_no_new_entries_after = (… ) if flat_by_session_close else None`. Status only; do not invert | QI-05-10 |
| **M9** Overlapping WFA fold-sum | **Still true.** `summarize_walk_forward` sums `test_total_r` (probe 3+4=7). 8-session overlap run (`test_sessions=3`, `step_sessions=1`, `overlap_policy='reject'`): 5 folds; warning `"OOS windows overlap; stitched equity is unavailable under overlap_policy='reject'"`; `aggregate_test_total_r=0.733`; `stitched_oos_total_r=None`; `stitched_oos_status=overlapping_oos_windows` | QI-05-07 |
| **M10** Greenest-cell contest | **Still true** on page 8 ranking help and page 10 RdYlGn heatmap | QI-05-08 |

Locked premises not re-opened: WFA session-fold keys; `fold_local` vs `causal_prefix`; `validation_summary` keys; Focus ≠ Admit identity except under `allow_all` + 0 cooldown (AH §2 item 5).

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Sev | Class | Title |
|---|---|---|---|
| QI-05-01 | High | Maintainability risk | `run_walk_forward_sl_tp` F(50) / 526 lines — mandatory F-grade |
| QI-05-02 | Medium | Maintainability risk | `pages/10_Validation.py` MI 0.00 / 1,949 LOC / 4 defs |
| QI-05-03 | Medium | Maintainability risk | `confluence_attribution.py` MI 0.00 / 1,240 LOC |
| QI-05-04 | High | UX/operability gap | H12 still open: Focus fill set ≠ Admit under `single_position`; banner silent |
| QI-05-05 | High | UX/operability gap | H13 still open: `st.success` on p≤0.05 + `P(mean R > 0)`; export banner still missing |
| QI-05-06 | Medium | UX/operability gap | H16 QI-5 half: Study `primary_metric` cannot be WFA OOS |
| QI-05-07 | Medium | UX/operability gap | M9: `aggregate_test_total_r` is a fold-sum; UI overlap help names stitched equity only |
| QI-05-08 | Medium | UX/operability gap | M10: Grid/WFA ranking surfaces invite the greenest cell |
| QI-05-09 | High | UX/operability gap | H5 Grid sibling: Policy widget has no `allow_all` inflation help |
| QI-05-10 | Medium | Design limitation | H7 Grid: cutoff still gated on flatten (locked composer fork) |
| QI-05-11 | Medium | Documentation drift | `P(mean R > 0)` / Phase 8 p-value have no glossary entries |
| QI-05-12 | Medium | Maintainability risk | `otf_validation._simulate` swallows `Exception` into empty trades |
| QI-05-13 | Low | Design limitation | `validation_summary` has no `schema_version` (shape locked); `sensitivity` stores unused seed |
| QI-05-14 | Low | Maintainability risk | `overfitting` imports `grid._directional_grid_metrics` |

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **C3 / AH3 probe family exists and is named** (`test_ah3_p1_*` plus four siblings in `tests/test_otf_validation.py`). Train sim uses `source_df.iloc[:split_bar]`. Fold construction / `causal_prefix` were **not** re-opened.
2. **`validation_summary()` shape is still `{bootstrap, permutation, trade_count, grid_overfit}`.** Empty trades return null metrics + `insufficient` without raising. Probe keys listed in `/tmp/qi5/probe_results.json`.
3. **Seed discipline holds for RNG batteries.** Every `default_rng` / `SeedSequence` site takes `random_state`. Same seed → identical `validation_summary` / MC artifacts; different seed moves bootstrap CI and MC drawdown (reshuffle `final_r` invariant by design).
4. **R15 / R16 / R19 opt-in cost warnings are present** on page 10. Empty-grid R15 path is `st.info("Run Grid Search first")`.
5. **C7 Focus ≡ Admit under `allow_all` + 0 cooldown** reproduced on the H12 fixture (ids `{2,3,4}`). AH §2 item 5 still describes the product.
6. **Malformed battery inputs fail closed** (`ValueError` on empty SL list; illegal `otf_history_policy`).
7. **Portfolio page matches R21 diagnostic scope** (caveat caption + admission/equity/correlation/contribution). Not a half-ship vs glossary.
8. **Library analytics import no Streamlit.** R18 boundary holds for this slice.
9. **Scope suite 240 passed** (named analytics files) and `PYTHONHASHSEED=7` 88 passed on the WFA/OTF/Phase 8/MC subset. This is a *suite* result, not a correctness claim.
10. **WFA overlap reject withholds stitched equity** (warning + `stitched_oos_total_r=None`) — the stitched-equity guard described in AUDIT §2.6 still operates. The residual honesty issue is the fold-sum headline (QI-05-07), not a silent stitch.

---

## 7. Handoffs to other slices

| To | Observation (not a finding) |
|---|---|
| QI-4 | `metrics.py` / Admit half of `entry_window.py` not owned here. H12 uses `summarize_focused_trades` (QI-4 file). `_empty_trades_df` private import from `backtest.py` |
| QI-6 | `reporting.py` `## Validation Diagnostics` still has no diagnostic banner (H13 export half; QI-06-02). H8 battery omit-means-on. Leftover `otf_validation_*` after bundle apply (QI-06-03) |
| QI-7 | H16 failed-cell MD/rollup; Study `primary_metric` allowlist lives in `study/schema.py`. WFA columns already written on the index |
| QI-10 | Page 10 `st.session_state` 140 lines; Focus/Admit/WFA/OTF key graph; page 13 `portfolio_*` keys |
| QI-11 | QI-11-04 walk_forward own-file mutation 60%. No AppTest of pages 8/9/10/13. `_simulate` swallow is `# pragma: no cover` |
| QI-13 | Glossary gaps (QI-05-11); USER_GUIDE Focus/Admit/WFA contest copy; ASSUMPTIONS M9/M10 sentences vs page widgets |
| QI-14 | Battery wall-time / WFA×grid multiply; R15 vs-random replica cost. Not measured here |

---

## 8. Docs that would need amending in QR (list only)

| Doc | Why QR might amend |
|---|---|
| `docs/METRICS_GLOSSARY.md` | Add `probability_positive` / Phase 8 permutation p-value; add overlap double-count caveat on Aggregate test total R (the sum itself is already named) |
| `docs/USER_GUIDE.md` | Grid Policy `allow_all` inflation; Focus N may diverge from Admit; WFA “do not pick the greenest cell”; cutoff-without-flatten Grid fork |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | H12/H13/M9/M10 operator sentences if QR keeps the math |
| `docs/ARCHITECTURE.md` | Page 10 session keys (validation / WFA / OTF / portfolio); Focus vs Admit identity footnote |
| `docs/AGENT_GUIDE.md` | Battery `schema_version` table; `validation_summary` shape freeze |
| `docs/STUDY_RUNNER.md` | `primary_metric` cannot be `wfa_median_test_expectancy_r` (H16) |

Do **not** amend these in QI.

---

## 9. `run_walk_forward_sl_tp` phase map (for QR-C, not a reopen of fold math)

| Phase | Responsibility | Notes |
|---|---|---|
| P0 validate | fold/window/overlap/OTF-policy tokens | Fail closed |
| P1 boundaries | bar or session folds (`trading_session_date` + `eth_start`) | Locked |
| P2 OTF source | `_otf_source_for_fold` `fold_local` / `causal_prefix` | Locked; do not re-audit |
| P3 train grid | `run_sl_tp_grid` on train slice + `best_grid_result` | In-sample selection |
| P4 test sim | selected SL/TP on test slice | Sliced frame (AUDIT: WFA does **not** have C3) |
| P5 stitch | overlap policy reject/first/last | Stitched equity guarded; fold-sum is separate |
| P6 summary | `summarize_walk_forward` + schema 2 extras | QI-05-07 |

---

## 10. Probe scripts (pasted; not committed)

`/tmp/qi5/probe_qi05.py` (full file under `/tmp`; not committed):

```python
# seed_inventory: AST walk of analytics/*.py for default_rng / SeedSequence /
# schema_version / random_state-without-RNG
# glossary_coverage: page label × METRICS_GLOSSARY.md
# confirmatory_scan: st.success / P(mean R > 0) / reporting banner
# h12_probe: 180-bar 1m fixture; signals at 09:05 / 10:05 / 10:30 / 10:55;
#   single_position max_holding_bars=80; Focus clock 10:00–11:30 vs Admit
# battery_seeds: golden trades_legacy.csv → validation_summary / monte_carlo /
#   excursions / time; 3-day synthetic → grid / WFA / sensitivity / overfitting /
#   portfolio; malformed ValueError; study _INDEX_PRIMARY_METRICS
```

Key probe outputs (`/tmp/qi5/probe_results.json`):

```text
H12 single_position: all_day={1,3} focus={3} admit={2} sets_equal=false
H12 allow_all C7: focus={2,3,4} admit={2,3,4}
FOCUS_HONESTY_BANNER: "Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."
Policy selectbox kwargs: options, index, key (has_help=false)
validation_summary keys: bootstrap, permutation, trade_count, grid_overfit
seed 42 vs 7 (12 synthetic R, n=200): ci_lower -0.542 vs -0.492; MC DD p50 3.0 vs 2.8; final_r p50 invariant
WFA overlap (8 sessions, test=3, step=1, reject): 5 folds
  warning=OOS windows overlap; stitched equity is unavailable
  aggregate_test_total_r=0.733  stitched_oos_total_r=None
  stitched_oos_status=overlapping_oos_windows
study primary_metrics: expectancy_r, max_drawdown_r, profit_factor, total_r, trade_count
ah3_test_exists: 5
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
