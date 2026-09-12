# QI-11 — Test-suite quality

**Slice:** QI-11 (research-only)
**Status:** Measured
**Audited commit:** `e30cc48` (`e30cc48c3e3b97af3e95f932be9ce27e28598328`) — `main` after [#479](https://github.com/AccumuLatata/ThesisTester/pull/479) (QI-0 harness)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3
**Key packages:** pandas 3.0.5 · numpy 2.4.4 · streamlit 1.63.0 · pytest 9.1.1 · pytest-cov 7.1.0 · mutmut 3.7.0 (CLI requires a committed `[tool.mutmut]` / `setup.cfg` — **not added**; sample used `/tmp` token mutants instead)
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi11-store-*`. `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 6 (C/H/M/L = 0/0/4/2)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day

Coverage numbers below re-measure QI-0’s `/tmp/qi0-coverage` table on this commit. They match QI-0 (`TOTAL 82%`, same 14 modules < 70%). Mutation, smells, goldens, eval/benchmark classification, and dependency-sensitivity are new.

**Review re-verification (docs-only):** AST smell walk, `dtype == object` / `iloc`+`is None` greps, `pytest --collect-only` (3,971), and findings.csv schema were re-run on this branch. Mutation `/tmp/qi11` transcripts were not retained; kill-rate integers are unchanged. Corrections below are count/schema honesty, not new slices.

## Commands run (verbatim)

```bash
python3 --version
git rev-parse HEAD
python3 -c "import pytest,pandas,numpy,streamlit; print(pytest.__version__, pandas.__version__, numpy.__version__, streamlit.__version__)"

# before (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi11-store-before pytest -q --tb=no

# coverage + durations (XML under /tmp)
THESISTESTER_STORE_DIR=/tmp/qi11-store-cov pytest -q -p no:cacheprovider \
  --cov=thesistester --cov-report=term-missing \
  --cov-report=xml:/tmp/qi11-coverage/coverage.xml --durations=25

# determinism (hash seeds; do not pass -p no:randomly)
THESISTESTER_STORE_DIR=/tmp/qi11-store-det0 PYTHONHASHSEED=0 \
  pytest -q -p no:cacheprovider --durations=25 --tb=no
THESISTESTER_STORE_DIR=/tmp/qi11-store-det1 PYTHONHASHSEED=1 \
  pytest -q -p no:cacheprovider --tb=no

# skip census
pytest -q --tb=no -rs tests/test_tick_vap_session20.py \
  tests/test_rolling_poc_candidates.py tests/test_apoc_tick_source.py \
  tests/test_apoc_candidates.py

# mutation sample + metrics wrong-change: /tmp/qi11/mutate_sample.py,
# /tmp/qi11/probe_metrics_wrong.py (pasted in §10). Neutral cwd so
# pytest does not prepend the repo ahead of the mutant package.

# after (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi11-store-after pytest -q --tb=no
```

Probe transcripts stay under `/tmp/qi11/`. Nothing from `/tmp` is committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-11 exclusive owner)**

- `tests/**` — 196 `.py` files, 3,715 `def test_`, **3,971 collected** (3,966 passed + 5 skipped).
- `pyproject.toml` `[tool.pytest.ini_options]` and `[tool.coverage.*]` — **read only**.
- `tests/fixtures/golden/README.md` — **read as spec** (QI-13 owns the file).

**Skipped**

- Editing tests/fixtures (hard rule).
- Committing mutmut config (would be a tracked `pyproject.toml` / `setup.cfg` edit; QI-12 owns packaging).
- Re-deriving `AUDIT_FINAL` §5 / AH §2; goldens-as-correctness is **restated** from §7 last row, not re-litigated.
- Page `AppTest` feasibility for classic pages (QI-10).
- Coverage-floor policy / required-status (QI-12).
- Performance envelopes of the slow tests (QI-14).

---

## 2. Code-quality readout (suite as the product)

### 2.1 Size vs QI-0

| Metric | QI-0 `6786713` | This `e30cc48` |
|---|---|---|
| Test `.py` / `def test_` / collected | 196 / 3,715 / 3,966+5 skip | **same** |
| Full suite (uninstrumented) | 3,966 passed, 5 skipped, ~2:09–2:16 | **3,966 passed, 5 skipped** in 2:26 (before), 2:12 (`PYTHONHASHSEED=0`) |
| Branch coverage | 82% (35,598 / 5,132 miss) | **82%** (35,598 / 5,132 miss; 14,994 / 3,117 partial) |
| `pyproject` pytest config | `testpaths = ["tests"]` only | **unchanged** — no markers, no xdist, no timeout plugin |

### 2.2 Module × coverage × mutation × test-count

Mutation = 12 comparison-operator sites per file, applied to a `/tmp` copy of `thesistester/`, tests run with `--import-mode=importlib` from a neutral cwd. Canary `__file__` confirmed the mutant package. Timeouts count as killed. String/docstring sites are noted and excluded from the *adjusted* rate.

| Module | stmts | miss | cov% | mutation raw (adj) | Own `def test_` (files) |
|---|---:|---:|---:|---|---|
| `engine/backtest.py` | 455 | 21 | **95** | 8/12 = **66.7%** (8/11 = **72.7%** after dropping one docstring site) | 43 + 5 + 7 (`test_phase5_backtest.py`, `test_ah1_session_flatten.py`, `test_golden_master.py`) |
| `engine/intrabar.py` | 335 | 36 | **86** | 12/12 = **100%** | 16 (`test_intrabar.py`) |
| `analytics/metrics.py` | 154 | 8 | **93** | 10/12 = **83.3%** | 27 + 8 (`test_phase5_metrics.py`, `test_institutional_metrics.py`) |
| `analytics/walk_forward.py` | 380 | 34 | **88** | 6/12 = **50%** (6/10 = **60%** after dropping two error-message string sites) | 17 (`test_walk_forward.py`) |

**Trigger:** plan §3.1 “< 70% killed → coverage is shallow”. `walk_forward.py` is below even after equivalent-mutant exclusion. `backtest.py` is below on the raw sample; the three survivors that are real code are diagnostic `both_hit_pct`, BE-when-`allow_same_bar_exit=False` (asserted in `test_exit_management.py`, **not** in the backtest-owned files), and `path_open_proximity` exit-reason labeling (asserted in `test_intrabar.py`). Same own-file gap on WFA: `otf_history_policy == "fold_local"` is asserted in `test_otf_integration.py`, not in `test_walk_forward.py`. Overlap-`reject` *is* in `test_walk_forward.py` (shallow if that mutant survived).

`intrabar.py` and `metrics.py` are above the trigger. A deliberate `/tmp` one-line change `win_rate = (len(wins) + 1) / n` is **killed** by `test_win_rate` and `test_expectancy` (2 failed / 33 passed). That is assertion depth on the win-rate formula, not a claim that every metric is correct.

### 2.3 Coverage-debt map (14 modules < 70%, QI-0 list unchanged)

| Module | % | miss | Class | Direct tests |
|---|---:|---:|---|---|
| `__main__.py` | 0 | 4 | **untestable-by-design** (`if __name__` guard; `test_cli.py` calls `main()`) | none needed |
| `assistant/handlers.py` | 46 | 112 | **missing tests** (dispatch table) | no file mentions `get_handler` / `tool_limits_from_envelope` |
| `assistant/voice/sidecar.py` | 48 | 262 | **untestable-by-design** (subprocess/network) + missing offline helpers | voice tests cover bind/redact; not launch/health loop |
| `classic_nav.py` | 59 | 81 | **missing tests** (classic bridge; no classic-page `AppTest`) | `test_classic_nav.py` exists; branches remain |
| `cli.py` | 59 | 59 | **missing tests** (argparse / subprocess branches) | `test_cli.py` hits the happy path + a few fail-fasts |
| `levels/common.py` | 59 | 5 | **missing tests** | **zero** test mentions of `require_tz_aware_timestamp` / `normalized_window_label`. Missed: missing-`timestamp` raise; entire `Timedelta` label branch |
| `classic_record.py` | 61 | 72 | **missing tests** | `test_classic_record.py` |
| `assistant/voice/xai_realtime.py` | 63 | 79 | **untestable-by-design** (provider I/O) + missing offline helpers | evals/realtime tests stub transports |
| `assistant/voice/grounding.py` | 66 | 57 | **missing tests** (edge branches) | voice evals cover digit audit |
| `classic_ledger.py` | 66 | 44 | **missing tests** | `test_classic_ledger.py` |
| `classic_context.py` | 67 | 77 | **missing tests** | `test_classic_context.py` |
| `classic_proposal.py` | 67 | 53 | **missing tests** | no `test_classic_proposal.py`; exercised from `test_cai9_page_capabilities.py` and `test_classic_nav.py` |
| `journal/rules.py` | 68 | 89 | **missing tests** | `test_journal_counterfactual.py` only (package import of `apply_journal_rules` / `parse_journal_rule`; no `journal.rules` path) |
| `journal/ledger.py` | 69 | 29 | **missing tests** | `test_journal_match.py` only (package import of `build_forward_ledger`; no `journal.ledger` path) |

Absolute-miss top 10 (unchanged vs QI-0): `sidecar.py` 262 · `results_overview.py` 226 · `api.py` 144 · `study/observatory.py` 142 · `orchestrator.py` 141 · `study/execute.py` 140 · `execution_artifacts.py` 128 · `journal/report.py` 114 · `handlers.py` 112 · `voice/session.py` 111. Engine/analytics remain ≥ 77%. **Coverage debt is not the simulation core.**

### 2.4 Dependency-sensitivity scan

Seed list from plan §4.3 / #478, plus the requested greps.

| Pattern | Hits | Verdict |
|---|---:|---|
| `AppTest` / `.proto.` / `.set_value(` | 21 / 10 / 13 | **Framework-mechanic asserts remain.** Page 14 still reads `chat_input[0].proto.disabled` and calls `set_value()` on *enabled* inputs. Page 16 Observatory drives widgets via `set_value`. The disabled-`set_value` path was rewritten in #478 (no longer calls it) — residual risk is the next Streamlit minor that changes proto layout or enabled-widget APIs. |
| `AppTestError` | 1 | Comment only (the #478 lesson). |
| `dtype == object` | **6** in 4 files | `test_journal_join.py` (2) plus `test_journal_match.py` (2), `test_journal_levels.py` (1), `test_journal_counterfactual.py` (1). Join pair is the #478 TJ5 object/`None` contract, not an accidental pandas-3 assert. The other four are the same object-dtype habit on journal frames — still pandas-major sensitive if 4.x changes object dtypes. |
| `iloc[…]` + `is None` (same line) | **23** | Not join-heavy: counterfactual 5 · pair 4 · levels 3 · tradesviz 3 · join **2** · triggers 2 · zones 2 · reconcile 1 · Observatory 1. #478 made the *join* contract explicit (`None` not `nan`); the other 21 are journal/helper nulls of the same shape. |
| `pd.__version__` / `pandas_major` | 20 | Golden recorders + `test_golden_master.py` skip hash when major ≠ recorded. **Designed** sensitivity. |
| `streamlit.__version__` | 0 | Suite does not pin or branch on Streamlit version. |

### 2.5 Test-smell inventory

AST walk of 3,715 `def test_` (`/tmp/qi11/smells.json`).

| Smell | Count | Notes |
|---|---:|---|
| `assert True` | **0** | clean |
| Assertion-free (no `Assert` / `pytest.raises` / `assert_frame_equal` in the function body) | 24 raw | **12 false positives** — asserts live in helpers: `_assert_historical_rows_equal` (5, `test_otf.py`), `_check_valid_ohlcv_bar` (2) + `_check_valid_state_vector` (1, `test_otf_contract.py`), `_assert_tick_oracle` (2) + `_assert_session_poc` (1, `test_apoc_tick_source.py`), `_assert_wave7_tick_provenance` (1, `test_program_b_yaml.py`). **12 real no-raise accepts** listed under QI-11-06 (Study/API `validate_*`, `clear_*_when_absent_is_safe`, dir-lock re-acquire, two `_fsync_file` swallow tests). |
| `str(exc)` in source | 8 | CLI/API/session-level fail-fasts (CLI parametrize uses `"schema_version" in str(exc)`). Message-coupled; typed `pytest.raises(..., match=)` is used elsewhere in the same files. Not “all asserts are `str()`” (that looser walk is 17). |
| Snapshot / golden-projection tests | 43 fns in 8 files | The four golden families + journal trigger/reconcile projections. Overspecified **by design** for identity gates. |
| Duplicated builders (`_bar` / `_ohlcv` / `_signal` / `_df` / `_trades`) | 5 names × 8–16 files | Named suites still “police the contracts they encode”. `_make_streamlit_stub` copied across **6** files (5 page-helpers + `test_assistant_workspace.py`). |

### 2.6 Determinism and wall time

| Run | Result |
|---|---|
| before `pytest -q` | 3,966 passed, 5 skipped, 146.89 s |
| `PYTHONHASHSEED=0` `-p no:cacheprovider` `--durations=25` | **3,966 passed, 5 skipped**, 132.70 s |
| `PYTHONHASHSEED=1` `-p no:cacheprovider` | **same pass/fail/skip** (see §6) |
| coverage-instrumented | 3,966 passed, 5 skipped, 311.07 s; **TOTAL 82%** |

Uninstrumented slowest 25: **none > 5 s**. Head: `test_worst_loser_export_contains_bounded_pngs` 2.87 s (kaleido) · `test_api_cli_and_assistant_canonical_hashes_match` 2.05 s · orchestrator restore 1.95 s · R16 noise 1.85 s · CLI parallel=serial 1.77 s. Under `--cov`, R22 `test_r22_benchmark_scenarios_are_deterministic_and_complete` is 26.83 s — ignore for feedback-loop cost (QI-0 same note).

Five skips are **env-gated desk oracles** (`THESISTESTER_QT_TICK_FIXTURE`, `THESISTESTER_RP_QT_*`, `THESISTESTER_APOC_QT_*`). Not flakiness.

### 2.7 Four golden families vs default-on execution paths

`simulate_trades` defaults (keyword-only included): `allow_same_bar_exit=True`, `commission_per_side=0.0`, `slippage_ticks=0.0`, `flat_by_session_close=False`, `exposure_policy="allow_all"`, `cooldown_bars_after_exit=0`, `entry_window=None`, `intrabar_model="sl_first"`, BE/trail `None`, `same_bar_opposite_direction="legacy"`.

| Path | Default | Legacy `test_golden_master` | Additive family |
|---|---|---|---|
| `sl_first` + same-bar both-hit | on | **yes** (6 SL both-hit trades asserted) | — |
| `allow_all` | on | **yes** (explicit `BACKTEST_CONFIG`) | OTF + entry_window also `allow_all`; **fade uses `single_position`** |
| `allow_same_bar_exit=True` | on | yes | yes |
| flatten off | on (False) | yes (identity of the *off* path) | all families False — **no flatten-on golden** |
| `entry_window=None` | on | omitted → default | **`test_entry_window_golden`** when enabled |
| OTF off | product default | yes | **`test_otf_golden`** when enabled |
| trigger `touch` | setup default | yes (`generate_signals`) | **`test_fade_golden`** is fade, not default |
| BE / trailing off | on (None) | omitted → default | **no enabled-BE golden** (unit file `test_exit_management.py` only) |
| 3c filled/void | not default trigger | **not in any family** | AH5 probe `test_ah5_sl_first_3c_entry.py` (unit, not golden) |
| `same_bar_opposite_direction="legacy"` | on | omitted; not asserted | fade family uses `single_position` (different policy) |

**Carry-over (AUDIT_FINAL §7 last row, restated):** goldens prove **legacy-unchanged identity**. They do not prove flatten, restore, composer admissions, or 3c entry-bar `sl_first`. Passing the four families is not a merge close for those paths. This slice does not re-open that contract.

### 2.8 Eval suites and benchmarks

| Suite | `def test_` | Offline? | Asserts what |
|---|---:|---|---|
| `tests/test_assistant_llm_evaluations.py` | 35 | **yes** — stub clients, `monkeypatch.delenv("OPENAI_API_KEY")`, no live HTTP | injection / uncited numbers / allowlist / draft isolation |
| `tests/test_assistant_voice_evaluations.py` | 18 | **yes** — `openai_client=object()`, fake `XAI_API_KEY`, no sidecar spawn | VA-6 grounding / flag-off / bind / hash-fail-closed |
| `tests/benchmarks/test_simulate_baseline.py` | 1 | n/a | scenario **names + non-negative `median_ms`** — informational |
| `tests/benchmarks/test_cai_cold_path.py` | 2 | n/a | stage list + `median_ms >= 0` + one parity-hash smoke |
| `tests/benchmarks/test_cai_warm_path.py` | 1 | n/a | hash-equal + `median_ms >= 0` + “Informational only” note |

Evals are deterministic offline release gates. Benchmarks are **not** performance regressions.

---

## 3. Application-quality readout (checklist §3.2)

QI-11 is suite-quality, not a user-facing composer. §3.2 applied to the **test system** as the entry point:

1. **Happy path:** full suite green on `sample_data/`-free unit/golden fixtures.
2. **Empty / minimal:** metrics empty-trade tests exist and pass; not re-declared “correct”.
3. **Malformed:** many fail-closed tests; 8 are `str(exc)`-only (inventory).
4. **Stale-state:** N/A for the suite itself; AppTest files isolate `THESISTESTER_STORE_DIR`.
5. **Composer parity:** `test_assistant_execution_parity.py` / CLI serial=parallel exist (slowest-25). Not re-verified as fill-correct.
6. **Honesty:** goldens README already says identity, not correctness. Suite comments in AH probes match.
7. **Persistence:** throwaway `/tmp` stores only.
8. **Performance envelope:** uninstrumented ≈ 33 ms/test; no unit test > 5 s.
9. **Operability:** skip reasons name the missing env vars; coverage floor is CI `::warning` only (QI-12).
10. **Copy:** N/A.

---

## 4. Prior-audit carry-over status

| Item | Status this slice |
|---|---|
| `AUDIT_FINAL` §7 last row — “Goldens as proof of correctness” | **Restated, not re-litigated.** Still a process contract: three (now four) families prove identity. They do not prove flatten, restore, composer admissions, or 3c `sl_first`. |
| AH §2.1 / §5 golden-not-regenerated | Observed: recorders still require `--confirm-regenerate`; CI golden-guard job not re-opened (QI-12). |
| H-0b (coverage 82% vs 85% floor) | Re-measured **82%**. Classification of *where* misses matter is §2.3. Floor policy → QI-12. |
| #478 Streamlit/pandas test hotfixes | Still present; AppTest disabled path no longer calls `set_value()`. Residual proto/`set_value` on enabled widgets: QI-11-03. |

Locked premises: `AUDIT_FINAL` §5.1–5.4 and §7; AH §2 / §2.1. Not re-audited.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Class | Sev | One line |
|---|---|---|---|
| QI-11-01 | Test-quality gap | Medium | 14 modules < 70%; debt is assistant/voice, classic, CLI, journal — not engine. `levels/common.py` has no direct tests. |
| QI-11-02 | Test-quality gap | Medium | Four golden families do not cover every default-on *branch* (3c, BE/trail, opposite-direction `legacy`, flatten-on). Identity contract restated, not re-litigated (`AUDIT_FINAL` §7). |
| QI-11-03 | Test-quality gap | Medium | AppTest still asserts Streamlit proto / `set_value` mechanics (pages 14 and 16). Next minor can fail the suite without a product change. |
| QI-11-04 | Test-quality gap | Medium | Mutation sample: `walk_forward.py` 50% (60% adj.) killed; `backtest.py` own-file tests miss BE / path-label / diagnostic branches. |
| QI-11-05 | Test-quality gap | Low | No pytest markers; evals vs goldens vs benchmarks vs unit are indistinguishable to CI. Benchmarks assert `median_ms >= 0` only. |
| QI-11-06 | Test-quality gap | Low | 12 no-raise tests (10 validate/clear accepts + dir-lock re-acquire + 2 `_fsync_file` swallows); duplicated `_bar`/`_ohlcv`/`_signal` builders across 8–16 files. |

---

## 6. Positive verification

1. **Suite green and deterministic** on this commit: 3,966 passed / 5 skipped for before, `PYTHONHASHSEED=0`, and `PYTHONHASHSEED=1`. Same skip set (desk oracles).
2. **Engine/analytics statement coverage ≥ 77%**; `backtest.py` 95%, `metrics.py` 93%, `walk_forward.py` 88%, `intrabar.py` 86%.
3. **`intrabar.py` mutation 100%** on the 12-site sample; **`metrics.py` 83.3%**; a `/tmp` `win_rate` +1 corruption is killed by `test_win_rate` / `test_expectancy`.
4. **Eval suites are offline and deterministic** (stub LLM/voice clients; keys unset/faked). No live provider calls in CI.
5. **Golden README and legacy pipeline match the recorded default-off contract** (`flat_by_session_close=False`, `sl_first` implicit, `allow_all`, `touch` signals, both-hit SL-first × 6).
6. **AH probe files exist** (`test_ah1_session_flatten.py`, `test_ah5_sl_first_3c_entry.py`) — status only; math not re-audited.
7. **#478 journal join contract** asserts object/`None` on both pandas majors (dependency-*aware*, not a leftover `is None` accident).
8. **No `assert True`**. Zero real assertion-free tests that are empty/`pass` bodies except documented no-raise smoke.
9. **Uninstrumented feedback loop is fast** (≈ 2:10–2:26; no test > 5 s).
10. **Isolation:** throwaway `/tmp` stores; no API keys; no desk PII.

This is **suite** evidence. It is not a claim that any backtest, metric, or Study result is correct.

---

## 7. Handoffs to other slices

| To | Observation (not a finding of theirs) |
|---|---|
| QI-4 | Golden default-on gaps for flatten / 3c / BE / `same_bar_opposite_direction`; backtest mutants that only die in `test_exit_management.py` / `test_intrabar.py`. |
| QI-5 | `walk_forward.py` mutation 50%; `otf_history_policy == "fold_local"` is asserted in `test_otf_integration.py`, not `test_walk_forward.py`. Overlap-`reject` / retention-ratio sites are the own-file / shallow-assert residue. |
| QI-6 | `cli.py` 59%; `__main__.py` 0% is the `__main__` guard. |
| QI-7 | Study no-raise schema accepts; Observatory `AppTest` `set_value` (shared with QI-10). |
| QI-8 | `journal/rules.py` 68%, `journal/ledger.py` 69%; join `None`/object contract is QI-8 product, tests owned here. |
| QI-9 | `handlers.py` 46%, sidecar/xai miss counts; evals classified offline (do not re-run as “are they live?”). |
| QI-10 | AppTest proto/`set_value` residual; page 14/16 only; classic pages still helper-only. |
| QI-12 | Coverage floor still informational at 82% vs 85%; no markers/xdist; mutmut needs a config QI-12 may add; Streamlit-minor test coupling. |
| QI-13 | `tests/fixtures/golden/README.md` already states identity; QR may want one sentence pointing at QI-11-02. Do not amend now. |
| QI-14 | Slowest-25 list; R22/CAI benches are informational (`median_ms >= 0`). |

---

## 8. Docs that would need amending in QR

List only. **Not amended.**

| Doc | Why QR might touch it |
|---|---|
| `docs/AGENT_GUIDE.md` §Development environment | Markers (`unit`/`integration`/`golden`/`eval`/`benchmark`), AppTest “assert state not disabled-widget mechanics”, mutmut/xdist policy |
| `docs/ENGINEERING_PROPOSAL.md` §4.1 | Optional cross-link: goldens = identity (already implied); default-on *branch* list is a QR-B gate, not a regen |
| `tests/fixtures/golden/README.md` (QI-13) | Name the default-on branches the four families do **not** cover |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Only if QR adds a golden for flatten/3c/BE and the honesty sentence must move |
| `docs/ARCHITECTURE.md` | AppTest / session-store isolation if QI-10 mechanizes it |

---

## 9. QR suite-structure recommendation (input only)

Not an implementation. For `docs/QUALITY_REMEDIATION_PLAN.md` QR-B:

1. **Markers** (warn-first): `unit` / `integration` / `golden` / `eval` / `benchmark` / `oracle` (env-gated desk). CI stays “full suite”; developers run `-m unit` for < 5 min (already true for most files).
2. **`pytest-xdist`:** feasible for the majority (tmp_path, no shared ports). **Not** safe for `test_assistant_page_render.py` / Observatory AppTest without a `serial` marker — they mutate `sys.modules["__main__"]` and `sys.path`. Worker-local `THESISTESTER_STORE_DIR` required.
3. **Golden QR-B before engine QR-C:** additive families for flatten-on, 3c `sl_first`, and BE/trail if those defaults are ever flipped or those orchestrators are extracted. Do **not** regenerate legacy.
4. **Mutation baseline:** commit a mutmut (or this sampler) config in a tooling PR; ratchet `walk_forward.py` first.
5. **Coverage floor:** QI-12 — block at the measured 82%, then ratchet; do not treat 95% `backtest.py` as “asserted”.

---

## 10. Probe scripts (pasted; not committed)

Mutation + metrics-wrong live at `/tmp/qi11/mutate_sample.py` and `/tmp/qi11/probe_metrics_wrong.py`. Essential isolation:

```python
# pytest prepends rootdir in default import mode, so a /workspace cwd
# always loads the repo package and silently ignores PYTHONPATH mutants.
# Run from a neutral cwd with --import-mode=importlib.
env["PYTHONPATH"] = "/tmp/qi11/mut_pkg:/workspace"
subprocess.run(
    [sys.executable, "-m", "pytest", "--import-mode=importlib",
     "--rootdir", "/workspace", "/workspace/tests/test_phase5_metrics.py"],
    cwd="/tmp/qi11/pytest_cwd",
    env=env,
)
```

Smell / inventory / debt scanners: `/tmp/qi11/scan_smells.py`, `scan_inventory.py`, `scan_coverage_debt.py`, `scan_depsens.py`.

Review re-verification (not committed; `/tmp` only):

```bash
# collected == 3,971
THESISTESTER_STORE_DIR=/tmp/qi11-collect pytest --collect-only -q

# dtype == object → 6 hits / 4 files (not 2)
rg -n 'dtype\s*==\s*object' tests

# same-line iloc + is None → 23 (not 25; join has 2)
rg -n 'iloc.*is None' tests
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
