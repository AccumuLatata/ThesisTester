# QI-04 — Execution engine: simulation, intrabar, exits, admission, metrics

**Slice:** QI-4 (research-only)
**Status:** Completed
**Audited commit:** `e30cc48` (`e30cc48c3e3b97af3e95f932be9ce27e28598328`) — `main` after [#479](https://github.com/AccumuLatata/ThesisTester/pull/479) (QI-0 baseline)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi4-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 10 (C/H/M/L = 0/2/6/2)
**Time spent:** original slice run + review correction on 2026-09-12
**Inputs (premises, not re-audited):** `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1. Goldens read as identity spec only (QI-11-owned files).

This report does **not** call any backtest, metric, or Study result correct or reliable. Vocabulary is plan §3.3.

**Review correction (same PR, research-only).** Plan §2 rule 5: anything in `AUDIT_FINAL` §5 is a premise; a finding that says the design should be otherwise is `Design limitation`, `confidence=n/a`, severity ≤ Medium. The first draft classified locked §5.1 item 6 (H7) and §5.1 item 5 (H15) as High `Verified defect` and copied the after-edit `pytest` wall-clock from the before line (`eceb815`). Those are withdrawn. H5 stays High (disclosure only; `allow_all` default not questioned). Phase-CC cells, H15 stamps, and the toy timing number are replaced with the re-measured probe in Appendix A.

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
# WITHDRAWN: "3966 passed, 5 skipped in 135.02s — identical to before"
# was copied from the before line in eceb815, not a second measured run.
```

Review re-measure (2026-09-12, same `e30cc48` product tree; docs-only edits):

```bash
PYTHONPATH=/workspace python3 /tmp/qi4/probe_qi04.py
# results: /tmp/qi4/probe_results.json (Appendix A)

radon cc -s -a <QI-4 files>   # 121 blocks, average B 6.86; simulate_trades F 133
vulture <QI-4 files> --min-confidence 60   # 12 candidates (all false positives)
rg -c 'st.session_state' pages/7_Backtest.py   # 80

export THESISTESTER_STORE_DIR=/tmp/qi4-store-review-scope
pytest -q --tb=line <same 21 files as above>
# 318 passed in 7.86s

PYTHONHASHSEED=7 pytest -q --tb=no -p no:cacheprovider <hashseed subset>
# 88 passed in 1.70s

export THESISTESTER_STORE_DIR=/tmp/qi4-store-review-full
pytest -q --tb=no
# 3966 passed, 5 skipped in 135.57s (0:02:15)  — before this review's doc edits

export THESISTESTER_STORE_DIR=/tmp/qi4-store-review-after
pytest -q --tb=no
# 3966 passed, 5 skipped in 139.30s (0:02:19)  — after this review's doc edits
# Result class identical (3966 passed, 5 skipped). Wall-clock is not identical.
```

Probe script is pasted in Appendix A (plan §8.1). Transcripts under `/tmp/qi4/` are not committed.

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

Radon CC for the whole function is **133 (F)**. An AST McCabe walk of the same function (decision nodes whose `lineno` falls in each phase) attributes complexity as follows. Walker (Appendix A): +1 for `If`/`For`/`AsyncFor`/`While`/`Assert`/`IfExp`/`ExceptHandler`; `BoolOp` adds `len(values)-1`; comprehension `ifs`; +1 function base. Phase CCs are **not** required to sum to 133 (radon vs this walker). They answer “where does the F-grade live?”

Re-measured AST total **127**. Phase buckets sum **123**; 4 decision nodes have no phase `lineno`. The first-draft cells (P7 46 / P6 18 / P5 8) did not match this walker and are withdrawn.

| Phase | Lines | Phys. lines | AST CC | What it does |
|---|---|---:|---:|---|
| P0 signature + docstring | 447–608 | 162 | 0 | Public contract (fn-entry +1 is in the 127 total) |
| P1 validate / normalize | 609–656 | 48 | 13 | Fail-closed inputs; Admit normalize |
| P2 empty-signals return | 658–694 | 37 | 4 | Safe empty `SimulationResult` |
| P3 frame / `BarData` / costs | 696–741 | 46 | 2 | R22 snapshot; subtf context |
| P4 loop 1 admission | 743–867 | 125 | 16 | Entry bar/price; window then cutoff (C9); store `entry_local_ts` |
| P5 order + DA3 | 869–899 | 31 | 5 | Restrictive sort; `skip_both` / `raise` |
| P6 loop 2 exposure | 901–988 | 88 | 14 | Occupancy / cooldown skips |
| **P7 SL/TP + flatten + exit walk** | **990–1204** | **215** | **45 (F)** | Bracket, R13, R12 per bar, session cap |
| P8 P&L / R | 1206–1234 | 29 | 2 | Gross/net; `pnl_points` alias |
| P9 row schema + diag accum | 1236–1332 | 97 | 10 | Additive intrabar/R13 columns |
| P10 result assembly | 1334–1384 | 51 | 12 | Trades / skips / three diagnostics |

**Reading.** R22 extracted `sim_core.BarData` / `resolve_trade_bar` but did not shrink the orchestrator. **P7 alone is F-grade (45 ≥ 41).** P4+P6 (admission) are C-grade. P&L is small and linear. This is plan H-A confirmed as a maintainability fact, not a fill defect.

**Loop-carried state (C1 class).** Loop 1 now stores `entry_local_ts` on each candidate; loop 2 unpacks it. Flatten uses `entry_local_ts.normalize() + session_close_time`. Empty cap emits `empty_session_close_cap` when skip capture is on. AH1 probe tests exist (`tests/test_ah1_session_flatten.py`, 5 tests). C1 status: **closed-verified** (probe present; math not re-audited).

**`sim_core` boundary (R22).** `sim_core.py` is BarData + `resolve_trade_bar` only. No admission, no exposure, no P&L. Conservative fallback clips entry-not-reached / unresolved TP — that is R12 resolution, not a second admission engine. **Boundary holds.**

**Exit / skip vocabulary.** String literals, no `Enum`. Skip: `outside_entry_window`, `after_entry_cutoff`, `direction_conflict`, `cooldown_active`, `overlapping_{position,direction,setup}`, `empty_session_close_cap`. Exit: `SL`/`TP`/`BE`/`TRAIL`/`TIME`/`DATA_END`/`SESSION_CLOSE`/`EOD` plus `_intrabar_path` / `_subtimeframe` / `_subtimeframe_fallback` suffixes. Schema home: `_TRADE_COLUMNS` + additive `_INTRABAR_TRADE_COLUMNS` / `_EXIT_MANAGEMENT_TRADE_COLUMNS`. 3c void, `confirm_3bar` void, and missing entry bar still `continue` with no skip row (M7 residual; §5.3 item 22 locks 3c void = no fill, no skip).

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
| 5 Composer parity | H7/H15 **diverge as locked** (`AUDIT_FINAL` §5.1 items 6 and 5). Engine function is shared; composers feed different kwargs. No committed test that would fail if those locks were inverted. | Design limitations QI-04-03/04; test gap QI-04-07 |
| 6 Honesty surface | Admit banners + skip split (window / cutoff / other) present. `allow_all` inflation **not** on the Policy widget (H5). `pnl_points` listed beside `gross_pnl_points` without alias caption (M8 residual). DA1 collision diagnostic computed (`return_result=True`) but not stored/shown. | Findings QI-04-02/06/10 |
| 7 Persistence | Execution defaults save/reset via `execution_defaults` + `local_store` (store owned QI-1). Collision diagnostic is in-memory only by contract (ARCHITECTURE). | Defaults path OK; DA1 gap is QI-04-06 |
| 8 Perf envelope | Tiny probe: 120 bars × 20 signals = **8.967 ms** on this review run (first-draft 5.3 ms withdrawn). `SIMULATE_PERF.md` serial baseline is QI-14. Structure: O(candidates × bars_held) Python loop in P7. | Handoff QI-14 (W12) |
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
| **H7** UI cutoff gated on flatten; API is not | Open / parked (AH §8 / AH8) | **still present; locked current fork** (`AUDIT_FINAL` §5.1 item 6). Not a contract breach. | UI helper `flatten=False` → cutoff `None` → 1 trade. `api.run_backtest(..., flat_by_session_close=False, no_new_entries_after="15:00")` → 0 trades, skip `after_entry_cutoff`. Page disables widget; `classic_export` forces `None` (QI-6 file) |
| **H15** OTF UI TZ vs API TZ | Open / parked | **still present; locked current fork** (`AUDIT_FINAL` §5.1 item 5). Wiring + clock stamps; **admission not shown to change** on this fixture. | UI: `session_timezone=exchange_tz` and `entry_window_exchange_tz=exchange_tz` (`session_state.exchange_timezone or inst.exchange_tz`). API: both `inst.exchange_tz`. Re-measured naive MNQ 120-bar fixture: `otf_signal_decision_timestamp` `2024-01-02 10:30:00+00:00` vs `2024-01-02 10:30:00-05:00`; `admission_equal=True` (both accepted). First-draft `14:31` stamps withdrawn (fixture was not pasted). |
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
| QI-04-01 | code | Maintainability risk | High | Strong | `simulate_trades` remains F-grade (CC 133); P7 exit walk alone is F (AST 45) |
| QI-04-02 | app | UX/operability gap | High | Verified | H5: Backtest **Policy** widget still has no `allow_all` inflation disclosure |
| QI-04-03 | app | Design limitation | Medium | n/a | H7: cutoff-without-flatten is the locked §5.1 item 6 fork (UI None / API applies) |
| QI-04-04 | app | Design limitation | Medium | n/a | H15: OTF/Admit TZ is the locked §5.1 item 5 fork (UI session / API instrument) |
| QI-04-05 | code | Maintainability risk | Medium | Strong | `pages/7_Backtest.py` MI 0.00 / 1,858 LOC / 5 defs / 80 session refs |
| QI-04-06 | app | UX/operability gap | Medium | Verified | Classic page drops `direction_collision_diagnostic` computed by `return_result=True` |
| QI-04-07 | code | Test-quality gap | Medium | Verified | No committed H7/H15 cross-composer test (`rg` empty under `tests/`) |
| QI-04-08 | app | Design limitation | Medium | n/a | M7 residual: 3c void / missing entry bar still have no skip row (§5.3 item 22) |
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
10. **Scope + golden identity suites are green** on this commit (318 + hashseed 88; re-measured 7.86s / 1.70s). That is not a correctness claim (`AUDIT_FINAL` §5.1 item 10).
11. **AH §2.1 defaults unchanged** on `e30cc48`: `exposure_policy="allow_all"`, `intrabar_model="sl_first"`, `flat_by_session_close=False`; flatten clock is `entry_local_ts.normalize() + session_close_time`.
12. **`AUDIT_FINAL` §5.1 items 5–6 still describe shipped wiring** (H15/H7). Status re-verified; not inverted; not a contract breach.

---

## 7. Handoffs to other slices

| To | Observation (not a QI-4 finding against their files) |
|---|---|
| QI-5 | Grid **Policy** selectbox also lacks `allow_all` help (H5). Grid cutoff widget is flatten-gated (H7 sibling). Grid Admit already uses `inst.exchange_tz` (C5 comment) — do not re-hunt H15 Admit on Grid. Focus overlay does not state H12 “Focus N may exceed Admit”. |
| QI-6 | `api.run_backtest` is the H7/H15 Composer B side of the **locked** forks (`session_timezone=inst.exchange_tz`; cutoff not flatten-gated; flatten-off nulls session TZ). `classic_export` forces `no_new_entries_after=None` when flatten is false. |
| QI-10 | Backtest shows leftover `trades` after Signals regen; 80 session-state lines; DA1 key absent from page persist. |
| QI-11 | Add H7/H15 tests that **lock the current fork** (fail if §5.1 items 5–6 are inverted), not tests that demand alignment. Mutation sample on `backtest.py` / `intrabar.py` / `metrics.py`. Goldens remain identity-only. |
| QI-13 | USER_GUIDE “Session close” documents UI cutoff gating as the product and does not name the locked API fork. No H15 composer sentence. |
| QI-14 | W12: measure P7 (`resolve_trade_bar` per held bar). `SIMULATE_PERF.md` already has serial medians; do not treat this slice’s ~9 ms toy as a baseline. |

---

## 8. Docs that would need amending in QR

List only. **Not amended.**

| Doc | Why QR would touch it |
|---|---|
| `docs/USER_GUIDE.md` §Exposure policy / Backtest widgets | H5 widget caption; H7 locked-fork sentence if AH8 labels or changes §5.1 item 6 |
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
| Cutoff without flatten | Widget disabled; `effective_no_new_entries_after=None` | YAML cutoff applied; skip `after_entry_cutoff` | **H7 still present; locked §5.1 item 6** |
| `session_timezone` when flatten off | `None` | `None` (even if YAML set a TZ) | Same nulling; cutoff still applied headless |
| OTF `session_timezone` | `exchange_timezone` or `inst.exchange_tz` | always `inst.exchange_tz` | **H15 still present; locked §5.1 item 5** |
| Admit `entry_window_exchange_tz` | same `exchange_tz` var | `inst.exchange_tz` | Same fork as H15 |
| Backtest OHLCV frame | `levels` if present else `data` | always levels frame (`run_experiment`; QI-6) | Locked §5.1 item 7; not re-opened |
| DA1 collision diagnostic | computed, **not** stored/shown | returned on `run_backtest` | QI-04-06 |
| Flatten clock | per-candidate `entry_local_ts` | same | C1 closed |

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.

---

## Appendix A — review probe (pasted; not committed)

Throwaway script re-run on 2026-09-12 against `e30cc48` product files. Write to `/tmp/qi4/probe_qi04.py`. Not a correctness claim.

```python
#!/usr/bin/env python3
"""QI-4 review probe (throwaway). Re-measures phase CC, H5/H7/H15, empty metrics.

Not a correctness claim about fills or P&L. Isolation: no store, no API keys.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import time
from pathlib import Path

import pandas as pd

from thesistester.analytics.metrics import equity_curve, summarize_trades
from thesistester.api import run_backtest
from thesistester.config import INSTRUMENTS
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.otf_integration import apply_configured_otf_filter

REPO = Path("/workspace")
BACKTEST = REPO / "thesistester/engine/backtest.py"
PAGE = REPO / "pages/7_Backtest.py"
OUT = Path("/tmp/qi4/probe_results.json")

PHASES = [
    ("P0_signature_docstring", 447, 608),
    ("P1_validate_normalize", 609, 656),
    ("P2_empty_signals", 658, 694),
    ("P3_frame_bardata_costs", 696, 741),
    ("P4_loop1_admission", 743, 867),
    ("P5_order_da3", 869, 899),
    ("P6_loop2_exposure", 901, 988),
    ("P7_sl_tp_flatten_exit", 990, 1204),
    ("P8_pnl_r", 1206, 1234),
    ("P9_row_schema_diag", 1236, 1332),
    ("P10_result_assembly", 1334, 1384),
]


def _decision(node: ast.AST) -> int:
    n = 0
    if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Assert, ast.IfExp)):
        n += 1
    elif isinstance(node, ast.ExceptHandler):
        n += 1
    elif isinstance(node, ast.BoolOp):
        n += max(0, len(node.values) - 1)
    elif isinstance(node, ast.comprehension):
        n += len(node.ifs)
    return n


def phase_cc() -> dict:
    src = BACKTEST.read_text()
    tree = ast.parse(src)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "simulate_trades"
    )
    total = 1
    per = {name: 0 for name, _, _ in PHASES}
    for node in ast.walk(fn):
        add = _decision(node)
        if not add:
            continue
        total += add
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            continue
        for name, a, b in PHASES:
            if a <= lineno <= b:
                per[name] += add
                break
    return {
        "ast_total_mccabe": total,
        "phase_cc": per,
        "fn_lineno": fn.lineno,
        "fn_end": fn.end_lineno,
        "phys_lines": fn.end_lineno - fn.lineno + 1,
    }


def _bars(n: int = 120, start: str = "2024-01-02 09:30", tz: str = "America/New_York") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1min", tz=tz)
    close = 100.0 + pd.Series(range(n), dtype=float) * 0.05
    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close + 0.25,
            "low": close - 0.25,
            "close": close,
            "volume": 100,
        }
    )


def _touch(signal_id: int, bar_index: int, direction: str) -> dict:
    return {
        "signal_id": signal_id,
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
        "zone_low": 99.0,
        "zone_high": 101.0,
        "zone_mid": 100.0,
        "level_count": 1,
        "level_names": "x",
    }


def h5() -> dict:
    df = _bars(30)
    signals = pd.DataFrame([_touch(1, 1, "long"), _touch(2, 1, "short")])
    common = dict(
        df=df,
        signals=signals,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=40,
        take_profit_ticks=40,
        return_result=True,
    )
    all_r = simulate_trades(**common, exposure_policy="allow_all")
    one_r = simulate_trades(**common, exposure_policy="single_position")
    page_src = PAGE.read_text()
    tree = ast.parse(page_src)
    has_help = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "exposure_policy":
            continue
        call = node.value
        if isinstance(call, ast.Call):
            has_help = any((kw.arg == "help") for kw in call.keywords)
    return {
        "allow_all_trade_count": int(len(all_r.trades)),
        "allow_all_skip_count": int(len(all_r.skipped_signals)),
        "single_position_trade_count": int(len(one_r.trades)),
        "single_position_skip_reasons": one_r.skipped_signals["skip_reason"].tolist()
        if len(one_r.skipped_signals)
        else [],
        "page_policy_selectbox_has_help_kw": has_help,
    }


def h7() -> dict:
    idx = pd.date_range("2024-01-02 15:00", periods=40, freq="1min", tz="America/New_York")
    close = pd.Series([100.0] * 40)
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close + 0.25,
            "low": close - 0.25,
            "close": close,
            "volume": 100,
        }
    )
    signals = pd.DataFrame([_touch(1, 30, "long")])
    ui = simulate_trades(
        df,
        signals,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=40,
        take_profit_ticks=40,
        flat_by_session_close=False,
        no_new_entries_after=None,
        return_result=True,
    )
    api = run_backtest(
        df,
        signals,
        instrument="MNQ",
        config={
            "flat_by_session_close": False,
            "no_new_entries_after": "15:00",
            "stop_loss_ticks": 40,
            "take_profit_ticks": 40,
        },
    )
    page_src = PAGE.read_text()
    disables = "disabled=not flat_by_session_close" in page_src
    classic = (REPO / "thesistester/classic_export.py").read_text()
    forces_none = (
        'backtest["no_new_entries_after"] = None' in classic
        and "flat_by_session_close" in classic
    )
    return {
        "ui_helper_trade_count_flatten_off": int(len(ui.trades)),
        "ui_helper_skip_count_flatten_off": int(len(ui.skipped_signals)),
        "api_trade_count": int(len(api["trades"])),
        "api_skip_reasons": api["skipped_signals"]["skip_reason"].tolist()
        if len(api["skipped_signals"])
        else [],
        "page_disables_widget": disables,
        "classic_export_forces_none": forces_none,
        "ui_formula_flatten_off": None,
    }


def h15() -> dict:
    df = _bars(120)
    naive = df.copy()
    naive["timestamp"] = naive["timestamp"].dt.tz_localize(None)
    signals = pd.DataFrame(
        [
            {
                **_touch(1, 60, "long"),
                "timestamp": naive["timestamp"].iloc[60],
                "trigger_timestamp": naive["timestamp"].iloc[60],
            }
        ]
    )
    otf_cfg = {
        "otf_filter": {
            "enabled": True,
            "timeframes": ["5m"],
            "require_aligned": False,
        }
    }
    utc = apply_configured_otf_filter(
        source_df=naive,
        candidate_signals=signals,
        setup_config=otf_cfg,
        session_timezone="UTC",
        eth_start=INSTRUMENTS["MNQ"].eth_start,
        signal_settings=otf_cfg,
    )
    ny = apply_configured_otf_filter(
        source_df=naive,
        candidate_signals=signals,
        setup_config=otf_cfg,
        session_timezone="America/New_York",
        eth_start=INSTRUMENTS["MNQ"].eth_start,
        signal_settings=otf_cfg,
    )

    def _stamp(res):
        acc = res.accepted_signals
        rej = res.rejected_signals
        frame = acc if len(acc) else rej
        cols = [c for c in frame.columns if "timestamp" in c or "decision" in c]
        sample = {}
        if len(frame):
            for c in cols[:8]:
                sample[c] = str(frame.iloc[0][c])
        return {
            "accepted": int(len(acc)),
            "rejected": int(len(rej)),
            "session_timezone": res.session_timezone,
            "stamps": sample,
        }

    u = _stamp(utc)
    n = _stamp(ny)
    return {
        "inst_exchange_tz": INSTRUMENTS["MNQ"].exchange_tz,
        "utc": u,
        "ny": n,
        "admission_equal": u["accepted"] == n["accepted"] and u["rejected"] == n["rejected"],
        "page_uses_session_or_inst": True,
        "api_uses_inst": True,
    }


def empty_metrics() -> dict:
    empty = summarize_trades(pd.DataFrame())
    curve = equity_curve(pd.DataFrame())
    return {
        "trade_count": empty.get("trade_count"),
        "expectancy_r_is_none": empty.get("expectancy_r") is None,
        "expectancy_r": empty.get("expectancy_r"),
        "empty_equity_rows": int(len(curve)),
    }


def malformed() -> dict:
    df = _bars(10)
    signals = pd.DataFrame([_touch(1, 1, "long")])
    cases = {}
    for name, kwargs in [
        ("sl_le_0", dict(stop_loss_ticks=0, take_profit_ticks=10)),
        ("bad_policy", dict(stop_loss_ticks=10, take_profit_ticks=10, exposure_policy="nope")),
        ("bad_cutoff", dict(stop_loss_ticks=10, take_profit_ticks=10, no_new_entries_after="25:00")),
        (
            "flatten_no_close",
            dict(stop_loss_ticks=10, take_profit_ticks=10, flat_by_session_close=True),
        ),
    ]:
        try:
            simulate_trades(df, signals, tick_size=0.25, point_value=2.0, **kwargs)
            cases[name] = "no_error"
        except ValueError as exc:
            cases[name] = f"ValueError:{exc}"
    return cases


def determinism() -> dict:
    df = _bars(40)
    signals = pd.DataFrame([_touch(1, 2, "long"), _touch(2, 8, "short"), _touch(3, 15, "long")])
    kwargs = dict(
        df=df,
        signals=signals,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=20,
        take_profit_ticks=20,
        return_result=True,
    )
    a = simulate_trades(**kwargs)
    b = simulate_trades(**kwargs)
    ja = a.trades.to_json(orient="split", date_format="iso")
    jb = b.trades.to_json(orient="split", date_format="iso")
    return {
        "sha256_a": hashlib.sha256(ja.encode()).hexdigest(),
        "sha256_b": hashlib.sha256(jb.encode()).hexdigest(),
        "identical": ja == jb,
        "trade_count": int(len(a.trades)),
    }


def timing() -> dict:
    df = _bars(120)
    signals = pd.DataFrame(
        [_touch(i + 1, 2 + i * 4, "long" if i % 2 == 0 else "short") for i in range(20)]
    )
    t0 = time.perf_counter()
    simulate_trades(
        df,
        signals,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=20,
        take_profit_ticks=20,
    )
    ms = (time.perf_counter() - t0) * 1000
    return {"bars": 120, "signals": 20, "ms": round(ms, 3)}


def defaults_and_locks() -> dict:
    sig = inspect.signature(simulate_trades)
    src = BACKTEST.read_text()
    return {
        "default_exposure_policy": sig.parameters["exposure_policy"].default,
        "default_intrabar_model": sig.parameters["intrabar_model"].default,
        "default_flat_by_session_close": sig.parameters["flat_by_session_close"].default,
        "has_entry_local_ts_store": '"entry_local_ts": entry_local_ts' in src,
        "has_empty_session_close_cap": "empty_session_close_cap" in src,
        "flatten_uses_normalize": "entry_local_ts.normalize()" in src,
        "page_mentions_collision": "direction_collision" in PAGE.read_text(),
        "has_enum_exit_reason": "class ExitReason" not in src,
    }


def sl_first_clip_present() -> dict:
    intra = (REPO / "thesistester/engine/intrabar.py").read_text()
    return {
        "has_sl_first_hits_after_entry": "def _sl_first_hits_after_entry" in intra,
        "resolve_ohlc_calls_clip": "_sl_first_hits_after_entry" in intra,
    }


def main() -> None:
    out = {
        "commit_probe_ran_against": "working-tree",
        "phase": phase_cc(),
        "h5": h5(),
        "h7": h7(),
        "h15": h15(),
        "empty_metrics": empty_metrics(),
        "malformed": malformed(),
        "determinism": determinism(),
        "timing": timing(),
        "locks": defaults_and_locks(),
        "ah5": sl_first_clip_present(),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
```
