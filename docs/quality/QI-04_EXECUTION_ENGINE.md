# QI-04 — Execution engine: simulation, intrabar, exits, admission, metrics

**Slice:** QI-4 (research-only)
**Status:** Completed
**Audited commit:** `e30cc48` (`e30cc48c3e3b97af3e95f932be9ce27e28598328`) — `main` after [#479](https://github.com/AccumuLatata/ThesisTester/pull/479) (QI-0 baseline)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi4-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 10 (C/H/M/L = 0/4/4/2)
**Time spent:** one agent run on 2026-09-12
**Inputs (premises, not re-audited):** `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1. Goldens read as identity spec only (QI-11-owned files).

This report does **not** call any backtest, metric, or Study result correct or reliable. Vocabulary is plan §3.3.

## Commands run (verbatim)

```bash
git fetch origin main
git checkout -b cursor/qi-04-execution-engine-6f45
git rev-parse HEAD   # e30cc48c3e3b97af3e95f932be9ce27e28598328

export THESISTESTER_STORE_DIR=/tmp/qi4-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no
# 3966 passed, 5 skipped in 135.02s (0:02:15)

radon cc -s -a <QI-4 files>
radon mi -s <QI-4 files>
radon raw -s <QI-4 files>
vulture <QI-4 files> --min-confidence 60
rg -n 'except Exception|except:' <QI-4 files>
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' <QI-4 files>
rg -l '^import streamlit|^from streamlit' thesistester/engine thesistester/analytics/metrics.py thesistester/analytics/entry_window.py thesistester/entry_window_policy.py thesistester/execution_defaults.py thesistester/visualization/backtest_chart.py thesistester/visualization/trade_review_chart.py thesistester/visualization/trade_review_export.py

PYTHONPATH=/workspace python3 /tmp/qi4/probe_qi04.py
# H5 overlap, H7 UI-helper vs api.run_backtest, empty metrics, AH5 unit,
# C1 store, determinism, malformed ValueError, phase-CC AST map

# H15 runtime (OTF clock expression)
# apply_configured_otf_filter(..., session_timezone="UTC") vs inst.exchange_tz

pytest -q --tb=line \
  tests/test_ah1_session_flatten.py tests/test_ah5_sl_first_3c_entry.py \
  tests/test_phase5_backtest.py tests/test_phase5_metrics.py \
  tests/test_institutional_metrics.py tests/test_backtest_direction_collision.py \
  tests/test_backtest_grid_defaults.py tests/test_backtest_chart.py \
  tests/test_entry_window_admission.py tests/test_entry_window_golden.py \
  tests/test_entry_window_sw2b.py tests/test_entry_window_sw3.py \
  tests/test_entry_window_sw4.py tests/test_entry_window_sw5.py \
  tests/test_entry_window_sw6.py tests/test_golden_master.py \
  tests/test_otf_golden.py tests/test_fade_golden.py \
  tests/test_intrabar.py tests/test_sim_core.py \
  tests/visualization/test_trade_review_chart.py
# 318 passed in 5.81s

PYTHONHASHSEED=7 pytest -q --tb=no -p no:cacheprovider \
  tests/test_ah1_session_flatten.py tests/test_ah5_sl_first_3c_entry.py \
  tests/test_phase5_backtest.py tests/test_golden_master.py \
  tests/test_otf_golden.py tests/test_entry_window_golden.py
# 88 passed in 1.43s

# after tracked edits (report + findings.csv only):
export THESISTESTER_STORE_DIR=/tmp/qi4-store-after
pytest -q --tb=no
# 3966 passed, 5 skipped in 135.02s (0:02:15) — identical to before
git status --porcelain
# clean after the report+CSV commit (only those two tracked files exist on the branch)
```

Probe transcripts live under `/tmp/qi4/` (`probe_qi04.py`, `probe_results.json`, `radon_*.txt`, `pytest-*.txt`). Not committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership; 13 files):

| Path | Role |
|---|---|
| `thesistester/engine/backtest.py` | `simulate_trades` orchestrator (CC 133) |
| `thesistester/engine/sim_core.py` | R22 array-backed bar resolve |
| `thesistester/engine/intrabar.py` | R12 models + AH5 clip |
| `thesistester/engine/exit_management.py` | R13 BE/trail |
| `thesistester/entry_window_policy.py` | Admit normalize/contains |
| `thesistester/analytics/entry_window.py` | Focus/Admit UI helpers + skip partition |
| `thesistester/execution_defaults.py` | Backtest/Grid widget sanitise |
| `thesistester/analytics/metrics.py` | `summarize_trades` / equity |
| `thesistester/visualization/backtest_chart.py` | Focus overlay chart |
| `thesistester/visualization/trade_review_chart.py` | R20 review |
| `thesistester/visualization/trade_review_export.py` | worst-loser ZIP |
| `thesistester/visualization/__init__.py` | re-exports (QI-4 owned) |
| `pages/7_Backtest.py` | Composer A entry point |

Direction-collision policy lives in `backtest.py` (`same_bar_opposite_direction`). Admit half of `analytics/entry_window.py` is in scope; Focus-over-statement (H12) is a QI-5 handoff.

**Read as spec only (not owned):** `AUDIT_FINAL` §5; AH §2; `tests/fixtures/golden/README.md`; `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §§2–4a; `docs/USER_GUIDE.md` Exposure / Intrabar / Exit management / Session close / Focus vs Admit; `docs/METRICS_GLOSSARY.md` core formulas; `docs/SIMULATE_PERF.md` (W12 numbers → QI-14).

**Skipped**

- Mutation sample on `backtest.py` / `intrabar.py` / `metrics.py` — QI-11.
- Full CAI `realistic` RSS / flame graph — QI-14 (structure notes only).
- Grid page widgets (H5/H7 also appear there) — QI-5 file.
- `api.run_backtest` / `classic_export.py` internals — QI-6 files; called only as the Composer B / export side of QI-4 parity probes.
- Re-recording goldens; questioning `sl_first` default, calendar-date flatten, or `allow_all` default.

---

## 2. Code-quality readout

### 2.1 Metrics table (this scope)

| Metric | Result | Trigger action |
|---|---|---|
| `radon cc` D+ | `simulate_trades` **F 133** (mandatory); `summarize_trades` E 33; `build_backtest_candlestick_chart` E 34; `summarize_by_group` D 29; `resolve_ohlc_bar` D 24 | Read and classified below |
| Module MI | `pages/7_Backtest.py` **C 0.00**; `backtest.py` B 12.95; `intrabar.py` B 13.25; others A (≥26) | Page is a refactor candidate |
| Function length > 150 | `simulate_trades` **938** physical lines (447–1384); `build_backtest_candlestick_chart` 172 | Same two hot spots |
| Broad `except` | 1: `pages/7_Backtest.py` `except Exception as e` | **narrow-guard OK** — ledger fail + typed `ValueError` UI, then `raise` |
| `vulture` ≥60 | 12 candidates | All false positives (Study/Data/Grid/dataclass/public API) |
| Streamlit in library | 0 in QI-4 library modules | Holds R18 boundary |
| Cross-module private imports | 0 in QI-4 files | — |
| `# noqa` / `# type: ignore` | 0 | — |
| `st.session_state` matching lines | **80** on `pages/7_Backtest.py` | Key graph → QI-10 |
| Scope tests | 318 passed; hashseed subset 88 passed | Deterministic on this cell |

Average CC across 121 QI-4 blocks: **B 6.86**.

### 2.2 `simulate_trades` phase map (exit criterion)

Radon CC for the whole function is **133 (F)**. An AST McCabe walk of the same function (decision nodes whose `lineno` falls in each phase) attributes complexity as follows. Phase CCs are **not** required to sum to 133 (nested predicates, `BoolOp` vs radon, docstring span). They answer “where does the F-grade live?”

| Phase | Lines | Phys. lines | Approx. CC | What it does |
|---|---|---:|---:|---|
| P0 signature + docstring | 447–608 | 162 | 1 | Public contract |
| P1 validate / normalize | 609–656 | 48 | 14 | Fail-closed inputs; Admit normalize |
| P2 empty-signals return | 658–694 | 37 | 5 | Safe empty `SimulationResult` |
| P3 frame / `BarData` / costs | 696–741 | 46 | 3 | R22 snapshot; subtf context |
| P4 loop 1 admission | 743–867 | 125 | 17 | Entry bar/price; window then cutoff (C9); store `entry_local_ts` |
| P5 order + DA3 | 869–899 | 31 | 8 | Restrictive sort; `skip_both` / `raise` |
| P6 loop 2 exposure | 901–988 | 88 | 18 | Occupancy / cooldown skips |
| **P7 SL/TP + flatten + exit walk** | **990–1204** | **215** | **46 (F)** | Bracket, R13, R12 per bar, session cap |
| P8 P&L / R | 1206–1234 | 29 | 3 | Gross/net; `pnl_points` alias |
| P9 row schema + diag accum | 1236–1332 | 97 | 11 | Additive intrabar/R13 columns |
| P10 result assembly | 1334–1384 | 51 | 13 | Trades / skips / three diagnostics |

**Reading.** R22 extracted `sim_core.BarData` / `resolve_trade_bar` but did not shrink the orchestrator. **P7 alone is F-grade.** P4+P6 (admission) are C-grade. P&L is small and linear. This is plan H-A confirmed as a maintainability fact, not a fill defect.

**Loop-carried state (C1 class).** Loop 1 now stores `entry_local_ts` on each candidate; loop 2 unpacks it. Flatten uses `entry_local_ts.normalize() + session_close_time`. Empty cap emits `empty_session_close_cap` when skip capture is on. AH1 probe tests exist (`tests/test_ah1_session_flatten.py`, 5 tests). C1 status: **closed-verified** (probe present; math not re-audited).

**`sim_core` boundary (R22).** `sim_core.py` is BarData + `resolve_trade_bar` only. No admission, no exposure, no P&L. Conservative fallback clips entry-not-reached / unresolved TP — that is R12 resolution, not a second admission engine. **Boundary holds.**

**Exit / skip vocabulary.** String literals, no `Enum`. Skip: `outside_entry_window`, `after_entry_cutoff`, `direction_conflict`, `cooldown_active`, `overlapping_{position,direction,setup}`, `empty_session_close_cap`. Exit: `SL`/`TP`/`BE`/`TRAIL`/`TIME`/`DATA_END`/`SESSION_CLOSE`/`EOD` plus `_intrabar_path` / `_subtimeframe` / `_subtimeframe_fallback` suffixes. Schema home: `_TRADE_COLUMNS` + additive `_INTRABAR_TRADE_COLUMNS` / `_EXIT_MANAGEMENT_TRADE_COLUMNS`. 3c void and missing entry bar still `continue` with no skip row (M7 residual).

**Other D+ (classified, not extra findings):**

| Symbol | CC | Classification |
|---|---|---|
| `resolve_ohlc_bar` | D 24 | AH5 clip + path models in one function. Readable. No independent defect. |
| `summarize_trades` | E 33 | One KPI kitchen-sink; empty path is safe (`None` not NaN). |
| `summarize_by_group` | D 29 | Combo/group table helper. |
| `build_backtest_candlestick_chart` | E 34 | Overlay budget (max 8 levels / 24 zones). Presentation only. |
| `normalize_entry_window` | C 20 | Below D trigger; shared Admit/Focus contract. |

---

## 3. Application-quality readout (§3.2)

Entry points: Backtest page (Composer A), `simulate_trades` (engine), `api.run_backtest` (Composer B, called for parity only).

| # | Check | Result |
|---|---|---|
| 1 Happy path | Scope suite 318 passed including goldens (identity, not correctness). Probe 3-trade run is deterministic (`sha256` stable). | Pass as *suite/identity* |
| 2 Empty / minimal | Empty signals: page `st.stop` before run. `summarize_trades(empty)` → `trade_count=0`, `expectancy_r is None` (not NaN); empty equity frame. | Pass |
| 3 Malformed | Engine `ValueError` for SL≤0, bad policy, `25:00` cutoff, flatten without close time. Page maps simulate-phase `ValueError` to `st.error` then `st.stop`; other exceptions re-raise. | Pass (fail-closed) |
| 4 Stale-state | Page displays leftover `trades` after a later Signals regen; no fingerprint vs `signals`. Not in ARCHITECTURE nonce table as a Backtest-owned clear. | Handoff QI-10 |
| 5 Composer parity | **H7 diverges** (cutoff without flatten). **H15 wiring diverges** (OTF/Admit TZ). Engine function is shared; composers feed different kwargs. No committed cross-composer test for those forks. | Findings QI-04-03/04/07 |
| 6 Honesty surface | Admit banners + skip split (window / cutoff / other) present. `allow_all` inflation **not** on the Policy widget (H5). `pnl_points` listed beside `gross_pnl_points` without alias caption (M8 residual). DA1 collision diagnostic computed (`return_result=True`) but not stored/shown. | Findings QI-04-02/06/10 |
| 7 Persistence | Execution defaults save/reset via `execution_defaults` + `local_store` (store owned QI-1). Collision diagnostic is in-memory only by contract (ARCHITECTURE). | Defaults path OK; DA1 gap is QI-04-06 |
| 8 Perf envelope | Tiny probe: 120 bars × 20 signals = 5.3 ms. `SIMULATE_PERF.md` serial baseline is QI-14. Structure: O(candidates × bars_held) Python loop in P7. | Handoff QI-14 (W12) |
| 9 Operability | Skip reasons and OTF reject expander say *why* a candidate vanished. 3c voids and missing entry bars still do not. Identity hashes are Composer B / bundle (QI-6). | Partial; M7 |
| 10 Copy | Focus ≠ Admit badges consistent with USER_GUIDE. Policy widget has no inflation help (USER_GUIDE §Exposure does). USER_GUIDE cutoff row describes UI gating only. | H5 / H7 / QI-13 |

Focus overlay uses `FOCUS_HONESTY_BANNER` (“post-hoc / not re-simulated”). It does **not** say Focus N can exceed Admit under `single_position` — H12, handoff QI-5.

---

## 4. Prior-audit carry-over status

| ID | Audit claim | Status on `e30cc48` | Evidence |
|---|---|---|---|
| **C1** flatten `entry_local_ts` leak | Closed by AH1 | **closed-verified** | Store + loop-2 unpack present; `empty_session_close_cap`; `tests/test_ah1_session_flatten.py` (5 tests) in the 318-pass scope run |
| **H6** `sl_first` × 3c pre-entry SL | Closed by AH5 | **closed-verified** | `resolve_ohlc_bar` clips via `_sl_first_hits_after_entry`; `tests/test_ah5_sl_first_3c_entry.py` (8 tests). Default model name still `sl_first` |
| **H5** `allow_all` undisclosed on Backtest/Grid | Open / parked (AH §8 presentation) | **still open** on Backtest Policy selectbox (no `help=`). USER_GUIDE / ASSUMPTIONS already state inflation. Grid widget → QI-5 | Probe: 2 overlapping opposite candidates → 2 trades / 0 skips under `allow_all`; 1 trade + `overlapping_position` under `single_position` |
| **H7** UI cutoff gated on flatten; API is not | Open / parked (AH §8 / AH8) | **still open** | UI helper `flatten=False` → cutoff `None` → 1 trade. `api.run_backtest(..., flat_by_session_close=False, no_new_entries_after="15:00")` → 0 trades, skip `after_entry_cutoff`. Page disables widget; `classic_export` forces `None` (QI-6 file) |
| **H15** OTF UI TZ vs API TZ | Open / parked | **still open (wiring + clock)** | UI: `session_timezone=exchange_tz` and `entry_window_exchange_tz=exchange_tz` (`session_state.exchange_timezone or inst.exchange_tz`). API: both `inst.exchange_tz`. Runtime: UTC vs `America/New_York` on MNQ → decision/ref stamps `+00:00` vs `-05:00`. This fixture did **not** change accept/reject (both `up`/accepted). Admission-changing DST case not reproduced here |
| **W12** performance profile | Structure here; measurement QI-14 | **handoff** | P7 F-grade walk is the serial hot path; `SIMULATE_PERF.md` already times `simulate_trades` |
| **M7** silent non-fills | Partial | Flatten empty-cap now has a skip (AH1). **3c void / missing entry bar still silent** | Code `continue` in P4 |
| **M8** `pnl_points` unlabeled | Residual | Glossary names the alias. Trade table still lists both columns without a caption | Page display_cols |
| **L3** `confirm_3bar` residual | Residual | Still fills hand-built rows (AH5 confirm test). Not generated | Not a new defect |

AH §2.1 locks not reopened: calendar-date flatten, `allow_all` default, `sl_first` default name.

---

## 5. Findings

Full records: `docs/quality/findings.csv` (`QI-04-01`…`QI-04-10`).

| ID | Axis | Class | Sev | Conf | Title |
|---|---|---|---|---|---|
| QI-04-01 | code | Maintainability risk | High | Strong | `simulate_trades` remains F-grade (CC 133); P7 exit walk alone is F (≈46) |
| QI-04-02 | app | UX/operability gap | High | Verified | H5: Backtest **Policy** widget still has no `allow_all` inflation disclosure |
| QI-04-03 | app | Verified defect | High | Verified | H7: cutoff-without-flatten still UI-admits / API-skips the same spec |
| QI-04-04 | app | Verified defect | High | Strong | H15: OTF (and Admit) TZ still UI-session vs API-instrument |
| QI-04-05 | code | Maintainability risk | Medium | Strong | `pages/7_Backtest.py` MI 0.00 / 1,858 LOC / 5 defs / 80 session refs |
| QI-04-06 | app | UX/operability gap | Medium | Verified | Classic page drops `direction_collision_diagnostic` computed by `return_result=True` |
| QI-04-07 | code | Test-quality gap | Medium | Verified | No committed H7/H15 cross-composer test (`rg` empty under `tests/`) |
| QI-04-08 | app | Design limitation | Medium | Strong | M7 residual: 3c void / missing entry bar still have no skip row |
| QI-04-09 | code | Maintainability risk | Low | Strong | Exit/skip reasons are stringly-typed (no enum / single vocabulary module) |
| QI-04-10 | app | Documentation drift | Low | Strong | M8 residual: trade table shows `pnl_points` without the glossary “gross alias” label |

---

## 6. Positive verification

Do not re-audit these on later slices unless the owning file changes.

1. **C1 flatten leak is closed in code + probe tests.** Per-candidate `entry_local_ts`; empty-cap skip name `empty_session_close_cap`. AH1 P1–P5 committed.
2. **H6 / AH5 is closed in code + probe tests.** `sl_first` + `entry_price` uses `_path_after_entry`. Default model name unchanged. Goldens not regenerated in this slice (identity suite green).
3. **`sim_core` contains no admission or P&L.** R22 boundary holds.
4. **Empty-trade metrics fail safe.** `trade_count=0`; rate/expectancy keys are `None`, not NaN.
5. **Malformed execution inputs fail closed** with `ValueError` (SL, policy, cutoff parse, flatten-without-close).
6. **`simulate_trades` is deterministic** on a 3-signal fixture (byte-identical JSON, two calls).
7. **Library QI-4 modules are Streamlit-free.** Page `except Exception` is a narrow ledger guard, not a swallow.
8. **Admit vs Focus copy on the Backtest page is distinct** (armed / applied badges + honesty banners). Skip caption splits window / cutoff / exposure-other.
9. **AH5 probe is a committed test file** (`tests/test_ah5_sl_first_3c_entry.py`), not only a one-off script.
10. **Scope + golden identity suites are green** on this commit (318 + hashseed 88). That is not a correctness claim (`AUDIT_FINAL` §5.1 item 10).

---

## 7. Handoffs to other slices

| To | Observation (not a QI-4 finding against their files) |
|---|---|
| QI-5 | Grid **Policy** selectbox also lacks `allow_all` help (H5). Grid cutoff widget is flatten-gated (H7 sibling). Focus overlay does not state H12 “Focus N may exceed Admit”. |
| QI-6 | `api.run_backtest` is the H7/H15 Composer B side (`session_timezone=inst.exchange_tz`; cutoff not flatten-gated; `session_timezone` nulled when flatten is off). `classic_export` forces `no_new_entries_after=None` when flatten is false. |
| QI-10 | Backtest shows leftover `trades` after Signals regen; 80 session-state lines; DA1 key absent from page persist. |
| QI-11 | Add H7/H15 composer-parity tests (QI-04-07). Mutation sample on `backtest.py` / `intrabar.py` / `metrics.py`. Goldens remain identity-only. |
| QI-13 | USER_GUIDE “Session close” documents UI cutoff gating as the product and does not name the API fork. No H15 composer sentence. |
| QI-14 | W12: measure P7 (`resolve_trade_bar` per held bar). `SIMULATE_PERF.md` already has serial medians; do not treat this slice’s 5 ms toy as a baseline. |

---

## 8. Docs that would need amending in QR

List only. **Not amended.**

| Doc | Why QR would touch it |
|---|---|
| `docs/USER_GUIDE.md` §Exposure policy / Backtest widgets | H5 widget caption; H7 composer-fork sentence if admissions are aligned or labelled |
| `docs/USER_GUIDE.md` §Session close and entry cutoff | Today describes UI-only cutoff gating |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §3–4 | H7/H15 parked-fork status; M7 skip inventory after any skip-row change |
| `docs/ARCHITECTURE.md` session-key table | DA1 persist-or-not; Backtest stale-trade invalidation |
| `docs/AGENT_GUIDE.md` | Composer table (OTF TZ, cutoff-without-flatten) if QR-A lands AH8 |
| `docs/METRICS_GLOSSARY.md` | Only if `pnl_points` labelling or skip-reason set changes |
| `docs/SIMULATE_PERF.md` | QI-14 re-measure after any P7 extract (QR-C) |

---

## Execution parity table (exit criterion)

| Item | Classic UI (`pages/7_Backtest.py`) | `api.run_backtest` / Study / CLI / Assistant | Status |
|---|---|---|---|
| Engine function | `simulate_trades` | same | Shared |
| `allow_all` default | yes (AH §2.1) | yes | Locked; **disclosure** missing on UI widget (H5) |
| Overlap N (probe) | 2 trades, 0 skips | same engine if same kwargs | Inflation is real; skip table empty |
| Cutoff without flatten | Widget disabled; `effective_no_new_entries_after=None` | YAML cutoff applied; skip `after_entry_cutoff` | **H7 open** |
| `session_timezone` when flatten off | `None` | `None` (even if YAML set a TZ) | Same nulling; cutoff still applied headless |
| OTF `session_timezone` | `exchange_timezone` or `inst.exchange_tz` | always `inst.exchange_tz` | **H15 open** |
| Admit `entry_window_exchange_tz` | same `exchange_tz` var | `inst.exchange_tz` | Same fork as H15 |
| Backtest OHLCV frame | `levels` if present else `data` | always levels frame (`run_experiment`; QI-6) | Locked §5.1 item 7; not re-opened |
| DA1 collision diagnostic | computed, **not** stored/shown | returned on `run_backtest` | QI-04-06 |
| Flatten clock | per-candidate `entry_local_ts` | same | C1 closed |

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
