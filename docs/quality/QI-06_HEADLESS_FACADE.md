# QI-6 — Headless facade, CLI, identity, bundles, reporting, classic bridge

**Slice:** QI-6 (research-only)
**Status:** Completed
**Audited commit:** `e30cc48` (`e30cc48c3e3b97af3e95f932be9ce27e28598328`) — `main` after merge of [#479](https://github.com/AccumuLatata/ThesisTester/pull/479) (QI-0 baseline)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, PyYAML 6.0.3, pyarrow 25.0.1
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi6-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data. Adversarial zips only under `/tmp`.
**Finding count:** 12 (C/H/M/L = 0/2/8/2)
**Time spent:** one agent run on 2026-09-12.

`AUDIT_FINAL.md` §5 and `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 are premises. This slice does **not** propose collapsing composers or the three integrity bars (AH §2 items 1, 2, 8). No backtest, metric, or Study result is described as correct or reliable.

## Commands run (verbatim)

```bash
git rev-parse HEAD
python3 --version
export THESISTESTER_STORE_DIR=/tmp/qi6-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no                                          # before: 3966 passed, 5 skipped in 149.74s

radon cc <QI-6 files> -s -n D --total-average
radon mi <QI-6 files> -s
rg -n 'except Exception|except:' <QI-6 files>
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' <QI-6 files>
rg -n '^import streamlit|^from streamlit' thesistester
rg -n 'import streamlit' thesistester/classic_*.py thesistester/app_state.py
vulture <QI-6 files> --min-confidence 60
bandit -q -ll thesistester/research_bundle.py thesistester/cli.py \
  thesistester/persistence/execution_artifacts.py

# probes (scripts under /tmp; transcripts /tmp/qi6-evidence/)
python3 /tmp/qi6_probes.py
PYTHONPATH=/workspace python3 /tmp/qi6_parity_and_index.py
pytest -q tests/test_research_bundle.py tests/test_cli.py \
  tests/test_app_state.py tests/test_golden_master.py \
  tests/test_assistant_execution_parity.py tests/test_research_identity.py \
  -k 'ah4 or canonical_bundle_hash or module_cli_bundle or api_cli_and_assistant or hash_matches_recorded'
pytest -q tests/test_golden_master.py::test_canonical_bundle_hash_matches_recorded_pandas_major \
  tests/test_golden_master.py::test_bundle_projection_ignores_manifest_and_zip_timestamps

export THESISTESTER_STORE_DIR=/tmp/qi6-store-after
pytest -q --tb=no                                          # after: 3966 passed, 5 skipped in 140.61s
```

Probe scripts are pasted in §10. They were never committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership; `classic_nav.py` is QI-10 and was not claimed)

| Path | LOC | Role |
|---|---:|---|
| `thesistester/api.py` | 3,204 | Headless facade + hand-rolled RunSpec validator + composer |
| `thesistester/cli.py` | 265 | `python -m thesistester run` + study/journal subparser mount |
| `thesistester/__main__.py` | 9 | Module entry |
| `thesistester/__init__.py` | 3 | Package version attr |
| `thesistester/research_identity.py` | 672 | Data/levels/experiment identity |
| `thesistester/research_bundle.py` | 1,108 | Zip build/load/apply + `canonical_bundle_hash` |
| `thesistester/reporting.py` | 1,648 | Artifact + markdown report |
| `thesistester/classic_context.py` | 587 | Classic research-mode helpers + chrome |
| `thesistester/classic_export.py` | 719 | Session → RunSpec exporter |
| `thesistester/classic_ledger.py` | 359 | Thesis ledger for classic pages |
| `thesistester/classic_proposal.py` | 366 | CAI-9 staged draft apply |
| `thesistester/classic_record.py` | 446 | Record-and-discuss |
| `thesistester/app_state.py` | 126 | Saved-dataset bootstrap (Streamlit) |
| `thesistester/persistence/execution_artifacts.py` | 1,519 | CAI cache (data/levels artifacts) |
| `pages/11_Report_Export.py` | 386 | Report / Export page |
| `pages/12_Research_Bundles.py` | 266 | Bundle export/import page |
| **Total** | **11,683** | |

**Skipped (out of scope or not feasible here)**

- `classic_nav.py` — QI-10 exclusive. Lazy `import streamlit` there is a QI-10 handoff.
- Dual-venv pandas 2.2 vs 3.0 hash recompute — this VM has pandas 3.0.5 only. Golden `legacy_bundle_hash.txt` records `pandas_major=3`; `test_canonical_bundle_hash_matches_recorded_pandas_major` passed here and is designed to **skip** on a pandas-2 cell. Dual-major measurement is QI-12.
- Full 32-cell `examples/studies/pRTH_open_ma.yaml` — Study-owned, needs a 15s History Exporter file that is not in-repo. Probe used a **single** pRTH-shaped RunSpec on the golden NQ 1m fixture (identity-parity only; not a Study correctness claim).
- Mutation testing — QI-11.
- Living-doc amendments — named only (§8).

---

## 2. Code-quality readout

### 2.1 Metrics (QI-6 files, `e30cc48`)

| Metric | Value |
|---|---|
| `radon cc` D+ in scope | F: `build_markdown_report` **152**, `validate_run_spec` **104**, `load_research_bundle` **75**, `build_research_bundle` **63**, `run_validation` **51**. E: `validate_classic_proposal` 39, `evict_execution_artifacts` 32, `_backtest_section` 31. `run_experiment` E **40** (just under F). Average B (7.64) over 280 blocks |
| MI | `api.py` **0.00** · `reporting.py` **0.00** · `execution_artifacts.py` **0.00** · `research_bundle.py` 3.79 · `classic_export.py` 17.11. Others A/B |
| Function length > 150 | `validate_run_spec` 880 · `run_experiment` 348 · `build_markdown_report` 287 · `build_research_bundle` 225 · `load_research_bundle` 218 · `run_validation` 215 · `build_research_artifact` 181 · `render_classic_thesis_chrome` 178 · `_load_15s_primary_experiment_data` 156 |
| Broad `except` in scope | 10. Classified: `execution_artifacts` publish `except Exception: cleanup; raise` = *narrow-guard OK*; `research_bundle._read_parquet_from_zip` wraps pandas/pyarrow as `ValueError` = *narrow-guard OK*; classic ledger/record/context BLE001 = *swallows chrome crash* (UI must not die) |
| `vulture` ≥60 | TypedDict field false positives; public API (`run_portfolio_analysis`, `peek_research_identity`, classic ledger helpers) used by pages/tests. No confirmed dead public symbol |
| Private cross-module import | `research_bundle` → `local_store._hash_dataframe` (QI-1-owned). Page 11 → `reporting._dash_if_none` |
| Streamlit in library | Module-scope: `app_state.py` only (matches QI-0 / `ARCHITECTURE.md` R9 note). Lazy inside `render_*`: `classic_context`, `classic_ledger`, `classic_record`, `classic_proposal` (chrome documented for `classic_context`; the other three are undocumented siblings) |
| Coverage (QI-0 table, same tree) | `api.py` 81% (144 miss) · `cli.py` 59% · `__main__.py` 0% · `research_identity.py` 76% · `research_bundle.py` 87% · `reporting.py` 86% · `execution_artifacts.py` 79% (128 miss) · classic_* 61–67% · `app_state.py` 96% |
| `bandit -ll` on bundle/cli/artifacts | clean |

### 2.2 `api.py` responsibility map (exit criterion)

AST spans on `e30cc48` (3,204 physical lines). Imports / blanks / comments are the ~9% unassigned remainder.

| Responsibility | Defs | Lines | Share | What it actually is |
|---|---:|---:|---:|---|
| TypedDict contracts (`*Result`) | 7 | 76 | 2.4% | Facade types |
| Constant allow-lists / defaults | 13 | 126 | 3.9% | Parallel schema tables (`_RUN_KEYS`, `_GRID_DEFAULTS`, battery key sets) |
| Validation helpers | 15 | 168 | 5.2% | Hand-rolled field checkers |
| `validate_run_spec` | 1 | **880** | **27.5%** | One function; CC 104; not a declarative schema |
| Dataset load / 15s-primary / ticks | 5 | 354 | 11.0% | Composition + cache (`execution_artifacts`) |
| Levels / setup / signals wrappers | 6 | 262 | 8.2% | The “thin facade” R18 advertised |
| Analytics composition (`run_*`) | 11 | 706 | 22.0% | Grid / WFA / validation / batteries / portfolio / time / OTF matrix |
| `run_experiment` | 1 | 348 | 10.9% | Full composer (validate → load → levels → signals → backtest → optional batteries) |
| **Module total** | | **3,204** | **100%** | |

**Reading.** R18 (`ENGINEERING_PROPOSAL.md`) scoped `api.py` as a thin typed facade. Measured: **~8% wrapper facade**, **~36% validation** (`validate_run_spec` + helpers + tables), **~44% composition/orchestration**, rest types. `validate_run_spec` is a hand-rolled schema (allow-lists + per-key `isinstance` / range / enum branches). A `TypedDict` + validator table could shrink CC without changing fail-closed behavior; that is a QR-C direction, not a behavior claim. `run_experiment` still applies `.get("enabled", True)` for `grid` / `walk_forward` / `validation` (H8; parked).

### 2.3 Hot-spot notes

- **`build_markdown_report` (CC 152, 287 lines).** Highest CC in the repo (QI-0). It is a linear template: extract artifact dicts, append fixed section strings, then conditional excursion/MC/noise/overfit/sensitivity/portfolio/OTF-validation blocks. Complexity is branch-per-section, not trading logic. QR-C: data → template, not more `if` chains.
- **`load_research_bundle` / `build_research_bundle` (CC 75 / 63).** Section-by-section zip I/O with parallel `_MANAGED_RESEARCH_KEYS`, `_*_META_KEYS`, `_KNOWN_FILES`, `_SECTION_REQUIRED_FILES`, hashed `session_keys`. Adding a session key requires touching several lists (H1 class).
- **`execution_artifacts.py` (1,519 LOC, MI 0.00).** Cache verify/publish/evict. Broad excepts on publish re-raise after temp cleanup (OK). Coverage debt 128 misses (QI-11).
- **Classic bridge.** `classic_export._backtest_section` E 31 is the H7 cutoff-without-flatten fork locus (QI-4). Not re-audited.

---

## 3. Application-quality readout (§3.2 per entry point)

### 3.1 `api.run_experiment` / `validate_run_spec`

| Check | Result |
|---|---|
| Happy path | pRTH-shaped RunSpec on golden NQ 1m CSV completed; `trade_summary.trade_count` observed = 2. **Not** a correctness claim (data/execution/P&L/session/bias not fully verified on this path) |
| Empty / minimal | Existing suite covers empty-ish fixtures; `validate_run_spec` fails closed on missing `dataset.path` / unknown keys |
| Malformed | Typed `ValueError` from `validate_run_spec` (no Streamlit traceback on this entry) |
| Composer parity | API hash = CLI hash on the pRTH-shaped spec (`062106ac…bda3`). Existing `test_module_cli_bundle_matches_headless_ui_equivalent_pipeline` and `test_api_cli_and_assistant_canonical_hashes_match` passed in the scoped run (11 tests) |
| Honesty | Omitted battery `enabled` still means **on** (H8 probe: `grid:` without `enabled` produced 4 grid rows; `enabled: false` produced none) |
| Persistence | Cache policy default `off`; CLI uses `read_write`. Cold/warm hash equality is already suite-gated (not re-claimed here) |
| Operability | Returned state carries `dataset_id`, `data_identity`, `levels_identity`, `experiment_identity`, `cache_provenance` |
| Performance | `run_experiment` wall 0.169 s on the golden-small CSV; CLI process 0.913 s (spawn + index write). Informational; not compared to `SIMULATE_PERF.md` |

### 3.2 CLI `python -m thesistester run`

| Check | Result |
|---|---|
| `--help` | exit 0; verbs `run` / `study` / `journal`. `run --help` documents experiment path, `--workers`, `--output-dir` only. **No** battery-`enabled` / omit-means-on text |
| Exit codes | Success 0. Invalid YAML / missing file → exit 1 |
| Errors | **Raw traceback** to stderr (`cli.main` does not catch `ValueError`). Message itself is actionable (`Experiment file must define a non-empty runs list`) but the operator sees a stack |
| `results_index.csv` | Columns = `R18_INDEX_METRIC_KEYS` + `bundle_path`. No `status` (AH §2 item 7 / `AUDIT_FINAL` §5.1 item 8 — locked). Study adds DA + `status` (QI-7) |

### 3.3 Bundles (`build` / `load` / `apply`) + page 12

Threat-model outcomes (exit criterion). All zips built under `/tmp`.

| Probe | Expected (fail closed unless locked otherwise) | Observed |
|---|---|---|
| Missing `manifest.json` | `ValueError` | **FAIL_CLOSED** — `Bundle is missing manifest.json.` |
| Not a zip | `ValueError` | **FAIL_CLOSED** — `Invalid research bundle zip file.` |
| Path-traversal members (`../evil.txt`, `../../tmp/qi6-evil`) | No disk write | **LOADED_IN_MEMORY**; `session_values={}`; no new `/tmp/qi6-evil*`. Members are never extracted to disk; only known filenames are read |
| Oversized unknown member (2 MiB zeros, DEFLATE) | Size cap or reject | **ACCEPTED_IGNORED**. Compressed size 2,426 bytes. `load_research_bundle` has **no** max uncompressed / total-member cap. Unknown names are ignored after `ZipFile` open |
| Foreign parquet schema as `trades.parquet` | Schema-only import (AH §2.8) | **ACCEPTED_SCHEMA_ONLY** — columns `unexpected_col`, `not_a_trade` restored |
| Tampered `trades.parquet` (r_multiple += 50) | Page 12 does not hash-gate (parked) | **ACCEPTED_SCHEMA_ONLY**. `canonical_bundle_hash` changed `2d9ec45b6f83` → `548db969179e`; imported `r_multiple=51.0`. `pages/12_Research_Bundles.py` contains **zero** `canonical_bundle_hash` / “schema-only” / “tamper” strings (`test_ah4_p5_page_12_stays_schema_only` still asserts the hash symbol is absent) |

**Three integrity bars (AH §2 item 8 — verify labels, do not collapse)**

| Bar | Code | Labelled where? |
|---|---|---|
| Page 12 import | `load_research_bundle` + `apply_research_bundle_to_session`; no hash | Page caption: “portable research state snapshots”. **No** schema-only / hash-not-checked sentence on the page. `USER_GUIDE.md` Research Bundles “What it is not” *does* distinguish manifest/schema vs `canonical_bundle_hash` on record/discuss |
| Report zip | Page 11 session dump / markdown / CSV; no re-sim; no bundle hash | Page is “export reproducible research artifacts from current session state” — session dump, not open-exact |
| Assistant open-exact / `complete_run` | Hash-fail-closed (`ARCHITECTURE.md` provenance-gated loads) | Assistant / USER_GUIDE Discuss path |

Bars remain **mechanically distinct**. They are **not** labelled distinctly on page 12 itself.

**H1 residual (after AH4).** AH4 probe tests P1–P5 exist and passed (`test_ah4_*`). `_MANAGED_RESEARCH_KEYS` now includes the AH4 leftovers (`otf_filter_summary`, `setup_config`, `focused_trades`, …). Residual keys **not** in that set still survive apply:

| Key | After dataset-less/backtest-only import | Honesty surface |
|---|---|---|
| `otf_validation_matrix` | **present** (`train_expectancy_r=9.9` leftover) | Page 11 checklist + CSV export + `build_research_artifact` tables |
| `direction_collision_diagnostic` | **present** | Classic / report collision copy |
| `display_timezone` | **present** | Export TZ (not fills) |
| `resampled_data` | **present** | Resample cache |
| `otf_filter_summary` (AH4) | **cleared** | Report metadata no longer shows leftover 12-rejected |

Dataset-less bootstrap skip (`BUNDLE_IMPORT_OMITTED_DATA_KEY` / `should_skip_dataset_bootstrap`) still holds (AH4-P3).

### 3.4 Reporting + page 11

Session `trade_summary` `{trade_count: 1, avg_r: 1.25, total_r: 1.25, win_rate: 1.0}` → artifact `results` matches; markdown contains `Trade count: 1`, `Avg R: 1.2500`, `Total R: 1.2500`. `_fmt_pct` uses `.1%` (same as page 11 `_fmt(..., ".1%")`) → `100.0%`, not `100.00%`. Identity parity for those scalars holds on this fixture.

`## Validation Diagnostics` still has **no** “diagnostic only” banner (H13; QI-5-owned carry-over; locus is `reporting.build_markdown_report`).

### 3.5 Identity + pandas major

- `canonical_bundle_hash` ignores zip timestamps: two empty-state builds differ as bytes, hashes equal (`test_bundle_projection_ignores_manifest_and_zip_timestamps`).
- Golden hash on this pandas 3.0.5 VM: `test_canonical_bundle_hash_matches_recorded_pandas_major` **passed**. Record: `pandas_major=3` / `sha256=77597105…8547f1`.
- Golden README §3.1: hash is pandas-major-sensitive; CI py3.10 cell is pandas 2.x and **skips** the hash assert. Not re-measured on pandas 2.2 here (QI-12).

### 3.6 `app_state.bootstrap_active_saved_dataset`

Seven page importers: `1_Data`, `2_Levels`, `6_Signals`, `7_Backtest`, `8_Grid_Search`, `12_Research_Bundles`, `13_Portfolio`. Page 12 gates bootstrap with `should_skip_dataset_bootstrap`. Empty session without an active saved id returns False (existing `test_app_state`). Isolation: throwaway store only.

---

## 4. Prior-audit carry-over status

| Item | Assigned | Status on `e30cc48` | Notes |
|---|---|---|---|
| **H1** leftovers + dataset-less bootstrap (AH4, residual) | QI-6 / QI-10 | **Partial closed.** AH4-P1–P5 tests present and green. AH4 keys clear. **Residual leftovers** `otf_validation_matrix`, `direction_collision_diagnostic`, `display_timezone`, `resampled_data` still survive apply (QI-06-03). Bootstrap skip flag holds | Do not reopen AH4 math; residual is additive |
| **H8** battery omit-means-on | QI-6 | **Parked, still true.** `run_experiment` `.get("enabled", True)` for grid/WFA/validation (and nested batteries in `run_validation`). Probe: omitted `grid.enabled` ran a 4-cell grid; `enabled: false` did not. Disclosure: `STUDY_RUNNER.md` names the “R18 default-on trap”; Study emit is explicit `false`. CLI `--help` and `USER_GUIDE.md` have **no** `thesistester run` omit=on sentence. `AGENT_GUIDE.md` example sets `enabled: false` but does not state omit=True | Locked AH §2.9 / §2.1. Disclosure-only; do not flip default |
| **§5.5 page-12 hash** | QI-6 | **Still parked.** Page 12 does not call `canonical_bundle_hash`. Tampered parquet imports. `test_ah4_p5_page_12_stays_schema_only` encodes the lock | AH §2 item 8 — do not collapse bars |
| AH4 probe tests exist | (verify only) | **Yes** — `tests/test_research_bundle.py` `test_ah4_p1`…`p5` | Not a re-audit of leftover-key math |

Closed AH items not assigned to this slice (C1/C2/C3/H3/H6) were not re-opened.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Sev | Class | Title |
|---|---|---|---|
| QI-06-01 | High | Maintainability risk | `api.py` is not a thin facade; `validate_run_spec` is 880 lines / CC 104 |
| QI-06-02 | High | Maintainability risk | `build_markdown_report` CC 152 (repo max); template-in-code |
| QI-06-03 | Medium | Verified defect | H1 residual: unmanaged leftovers (`otf_validation_matrix`, …) survive bundle apply |
| QI-06-04 | Medium | Maintainability risk | Bundle key lists are parallel SoTs; load/build are F-grade |
| QI-06-05 | Medium | Maintainability risk | Streamlit-in-library: `app_state` + undocumented lazy `classic_*` renders |
| QI-06-06 | Medium | Design limitation | Page 12 schema-only / hash parked; three bars not labelled on the page |
| QI-06-07 | Medium | UX/operability gap | CLI `run` prints tracebacks on `ValueError` |
| QI-06-08 | Medium | Documentation drift | H8 omit-means-on still true; CLI / USER_GUIDE run path silent |
| QI-06-09 | Medium | Security risk | `load_research_bundle` has no zip size / expansion cap |
| QI-06-10 | Medium | Maintainability risk | `execution_artifacts.py` MI 0.00 / 1,519 LOC |
| QI-06-11 | Low | Maintainability risk | Private imports (`_hash_dataframe`, `_dash_if_none`) |
| QI-06-12 | Low | Test-quality gap | CLI / `__main__` / classic_* coverage 0–67% |

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **AH4 leftover *managed* keys still clear** — P1–P5 committed; leftover `otf_filter_summary` / `setup_config` / `focused_trades` do not survive a zip without those sections. Dataset-less import sets `bundle_import_omitted_data` and skips bootstrap.
2. **Page 12 stays schema-only** (AH §2.8 lock) — hash symbol absent from the page; tampered parquet imports. Assistant / `complete_run` hash-fail-closed path is a separate bar (`ARCHITECTURE.md`; not collapsed).
3. **API ↔ CLI `canonical_bundle_hash` identity** on a pRTH-shaped RunSpec over the golden NQ 1m fixture: both `062106ac38001f92706f71c0a4b77beb41ad662f0bf27a412934fa0af0c0bda3`. Existing UI-equivalent and assistant-parity hash tests passed (scoped 11 tests). This is **hash identity**, not fill correctness.
4. **`results_index.csv` CLI schema** equals `R18_INDEX_METRIC_KEYS + [bundle_path]`; no `status` column (locked fail-fast / origin=cli).
5. **Malformed / missing-manifest / non-zip bundles fail closed** with typed `ValueError`. Path-traversal members are not written to disk.
6. **Report markdown scalars match `trade_summary`** for trade_count / avg_r / total_r on the synthetic session (same `_fmt_pct` convention as page 11).
7. **Golden bundle hash** matches the pandas-3 record on this VM; timestamp-neutrality of `canonical_bundle_hash` holds.
8. **`validate_run_spec` fail-closed on unknown keys** (suite + H8 specs). `ruff` not re-run repo-wide (QI-0 clean; this slice added no product code).
9. **AH4-managed OTF read order** — `build_otf_filter_metadata` prefers `backtest_otf_filter` over leftover `otf_filter_summary`.
10. **Isolation** — throwaway `/tmp` stores; no API keys; no desk PII; adversarial zips not committed.

---

## 7. Handoffs to other slices

| To | Observation (not a finding of theirs until they verify) |
|---|---|
| QI-5 | `reporting.build_markdown_report` `## Validation Diagnostics` still has no diagnostic banner (H13 locus). Report page 11 `st.success` is not in this scope |
| QI-10 | Residual `display_timezone` leftover; `classic_nav.py` lazy Streamlit; session-key graph vs `ARCHITECTURE.md` table (unmanaged keys) |
| QI-11 | Coverage: `__main__.py` 0, `cli.py` 59, classic_* 61–67, `api.py` 144 misses, `execution_artifacts.py` 128 misses. vulture TypedDict false friends |
| QI-12 | Streamlit-in-library is prose-only; no import-linter. pandas-major hash skip on py3.10 cell. `bandit` clean on this slice’s zip/cli/artifacts |
| QI-13 | `USER_GUIDE.md` names the hash/schema split; page 12 UI does not. CLI run battery-omit undocumented. `AGENT_GUIDE.md` example omits the omit=True sentence |
| QI-1 | `research_bundle` imports `local_store._hash_dataframe`. H9 `dataset_id` omits ingest story (identity module read only) |
| QI-4 | `classic_export._backtest_section` E 31 — H7 cutoff-without-flatten fork. Do not re-audit |
| QI-7 | Study `results_index` extras (`status`, DA keys) vs CLI prefix. H8 Study emit already explicit `enabled: false` |
| QI-9 | Assistant open-exact / `complete_run` hash bar — verify labels there; do not collapse into page 12 |
| QI-14 | `run_experiment` 0.169 s / CLI 0.913 s on golden-small; no CAI realistic envelope run here |

---

## 8. Docs that would need amending in QR (list only)

| Doc | Why QR might amend |
|---|---|
| `docs/ARCHITECTURE.md` | Session-key table: residual unmanaged leftovers; Streamlit boundary (`app_state` + lazy `classic_ledger` / `classic_record` / `classic_proposal`); three integrity bars named next to page 12 |
| `docs/USER_GUIDE.md` | Research Bundles page-level schema-only caption; CLI `thesistester run` omit-`enabled`=on |
| `docs/AGENT_GUIDE.md` | Explicit “omitted battery `enabled` = True on API/CLI/assistant”; Streamlit-in-library exception list |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Operator-facing H8 sentence if QR keeps the default |
| `docs/STUDY_RUNNER.md` | Already names the default-on trap — keep aligned if CLI copy is added |
| `docs/METRICS_GLOSSARY.md` | Only if Report Validation banner work (H13) needs a glossary pointer — QI-5 |

Do **not** amend these in QI.

---

## 9. Bundle threat-model table (exit criterion)

| Attack / defect class | Gate today | Outcome | Finding |
|---|---|---|---|
| Missing manifest | kind/schema check | Fail closed | none (positive) |
| Corrupt zip | `BadZipFile` → `ValueError` | Fail closed | none (positive) |
| Path traversal member | Never extract to disk; read known names only | No write; member ignored | none (positive) |
| Zip bomb / huge member | **None** (no max size) | Unknown member ignored; a *named* huge parquet/json is decompressed into RAM then parsed | QI-06-09 |
| Foreign parquet schema | Schema-only (locked) | Imports | QI-06-06 (disclosure) |
| Tampered hashed content | Page 12: none. Assistant: hash-fail-closed | Page 12 imports | QI-06-06 (parked) |
| Leftover session keys | `_MANAGED_RESEARCH_KEYS` clear-then-restore | AH4 set cleared; residual set survives | QI-06-03 |
| Dataset-less + saved dataset A | `bundle_import_omitted_data` | Bootstrap skipped | none (AH4 holds) |

---

## 10. Probe scripts (pasted; not committed)

Responsibility + leftover + zip + H8 + CLI (`/tmp/qi6_probes.py`):

```python
# excerpts — full script lived at /tmp/qi6_probes.py
# 1) AST bucket api.py into facade / validate_run_spec / composition
# 2) leftover keys vs _MANAGED_RESEARCH_KEYS; apply a backtest-only zip
# 3) adversarial zips under /tmp (missing manifest, traversal, 2MiB zeros,
#    foreign parquet, tampered r_multiple)
# 4) run_experiment with grid omitted enabled vs enabled: false
# 5) build_markdown_report vs trade_summary
# 6) python -m thesistester run on empty runs: / missing file
```

Parity + index (`/tmp/qi6_parity_and_index.py`):

```python
# Single pRTH-shaped RunSpec (SMA 50 / EMA 21 / touch / batteries explicit false)
# on tests/fixtures/golden/dataset_nq_1m_small.parquet written to CSV under /tmp.
# Compare canonical_bundle_hash(api.run_experiment) vs CLI zip.
# Assert results_index.csv columns == R18_INDEX_METRIC_KEYS + ["bundle_path"].
```

Transcripts: `/tmp/qi6-evidence/probes.txt`, `/tmp/qi6-evidence/parity.txt`, `/tmp/qi6-evidence/radon-cc.txt`, `/tmp/qi6-evidence/pytest-before.txt`, `/tmp/qi6-evidence/pytest-after.txt`.

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
