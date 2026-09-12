# QI-7 — Study system

**Slice:** QI-7 (research-only)
**Status:** Completed
**Audited commit:** `539dd2e` (`539dd2e9dabc9ba918f03b26f66537f3d9fca3ce`) — `main` after [#488](https://github.com/AccumuLatata/ThesisTester/pull/488) (QI-5)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, PyYAML 6.0.3, radon 6.0.1, vulture 2.16, bandit 1.9.4
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi07-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data. No real keys.
**Finding count:** 10 (C/H/M/L = 0/0/8/2)
**Time spent:** one agent run on 2026-09-12.

`AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e` and `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1 are premises. RS-D2 / RS-D9 / SAF locks are premises: this slice does **not** propose in-process `run_study()` from pages, auto-refresh, kill/retry, or a ToD factor axis. `tests/study/` is QI-11-owned (read as evidence). `docs/STUDY_RUNNER.md` is QI-13-owned (read as spec).

This report does **not** call any backtest, metric, or Study result correct or reliable. The 4-cell E2E used `sample_data/ES_sample_1m.csv` (12 bars) so cells could *complete*; ranked/promote counts after a surgical index edit are honesty-surface evidence only.

## Commands run (verbatim)

```bash
git fetch origin main
git fetch origin cursor/audit-final-merge-3a8e
git checkout -B cursor/qi-07-study-system-bd76 origin/main
git rev-parse HEAD   # 539dd2e9dabc9ba918f03b26f66537f3d9fca3ce

export THESISTESTER_STORE_DIR=/tmp/qi07-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no
# before: 3966 passed, 5 skipped in 142.52s

radon cc thesistester/study pages/15_Studies.py pages/16_Study_Observatory.py \
  examples/studies/program_b/*.py -s -n D --total-average
radon mi <same> -s
vulture thesistester/study pages/15_Studies.py pages/16_Study_Observatory.py --min-confidence 60
bandit -q -ll thesistester/study/naming.py thesistester/study/launch.py \
  thesistester/study/execute.py thesistester/study/observatory.py
rg -n 'except Exception|except:' thesistester/study pages/15_Studies.py pages/16_Study_Observatory.py
rg -c 'st\.session_state' pages/15_Studies.py pages/16_Study_Observatory.py
rg -n 'import streamlit|from streamlit' thesistester/study

PYTHONPATH=/workspace THESISTESTER_STORE_DIR=/tmp/qi07-store-probes \
  python3 /tmp/qi07_probes.py
# /tmp/qi07/probe_results.json

THESISTESTER_STORE_DIR=/tmp/qi07-store-ah2 pytest -q tests/study/test_ah2_study_path_pin.py --tb=no
# 9 passed

THESISTESTER_STORE_DIR=/tmp/qi07-store-study pytest -q tests/study -p no:cacheprovider --tb=no
# 543 passed
PYTHONHASHSEED=7 pytest -q tests/study -p no:cacheprovider --tb=no
# 543 passed

PYTHONPATH=/workspace python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b/manifest.yaml
# ok 20 studies / 898 cells
PYTHONPATH=/workspace python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b/manifest_tick.yaml
# ok (tick packet)

export THESISTESTER_STORE_DIR=/tmp/qi07-store-after
pytest -q --tb=no
git status --porcelain
```

Probe script lived at `/tmp/qi07_probes.py` (pasted in §10). Transcripts are not committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership)

| Path | LOC | Role |
|---|---:|---|
| `thesistester/study/schema.py` | 973 | StudySpec validate; `_validate_factors` F(46) |
| `thesistester/study/expand.py` | 543 | Cartesian expand + AH2 path pin |
| `thesistester/study/execute.py` | 1,353 | `run_study` F(60); ledger; `run_experiment` loop |
| `thesistester/study/report.py` | 974 | Overview MD/CSV |
| `thesistester/study/promote.py` | 648 | Survivor draft; `_compose_promoted_draft` E(37) |
| `thesistester/study/rollup.py` | 375 | Diagnostic rollup |
| `thesistester/study/viewer.py` | 1,174 | Inspect catalog / quality / peek |
| `thesistester/study/observatory.py` | 2,069 | Corpus fact table; desks under store |
| `thesistester/study/builder.py` | 1,386 | `hydrate_study_draft` F(62); emit/hydrate |
| `thesistester/study/launch.py` | 691 | Detached CLI spawn; pid claim |
| `thesistester/study/preview.py` | 167 | In-memory validate + expand |
| `thesistester/study/admit_followup.py` | 332 | SAF child draft |
| `thesistester/study/briefing.py` | 603 | SV5 / ToD projection (not a factor axis) |
| `thesistester/study/cli_study.py` | 390 | `study` verbs |
| `thesistester/study/tools.py` | 572 | RS6 assistant wrappers (default-off) |
| `thesistester/study/ledger.py` | 144 | Soft-resume ledger |
| `thesistester/study/naming.py` | 85 | Run-name SHA1 fingerprint |
| `thesistester/study/apoc_provenance.py` | 187 | Wave-7 provenance helpers |
| `thesistester/study/__init__.py` | 122 | Eager re-exports including `run_study` |
| `pages/15_Studies.py` | 2,261 | Build / Preview (+ launch) / Inspect |
| `pages/16_Study_Observatory.py` | 966 | Read-only observatory UI |
| `examples/studies/program_b/generate_program_b_yaml.py` | 685 | Program B generator |
| `examples/studies/program_b/validate_program_b_yaml.py` | 502 | `validate_study_file` F(110) |
| **Total (owned `.py`)** | **17,202** | |

Read-as-spec (QI-13): `docs/STUDY_RUNNER.md`, `docs/AGENT_GUIDE.md` §Study, `docs/ARCHITECTURE.md` SV/SO/SAF import sentences.

Read-as-evidence (QI-11): `tests/study/**` including `test_ah2_study_path_pin.py` and AST import-allow lists.

**Skipped**

- `tests/study/` internals as a test-quality audit — QI-11 (this slice only used them as status evidence).
- Living-doc amendments — named in §8 only.
- In-process page `run_study`, auto-refresh, kill/retry, ToD factor axis — locked; not proposed.
- Dual-venv Windows pid-alive against a real NT kernel — covered by committed mocks (`test_pid_is_alive_windows_*`); this VM is Linux.
- Full Program A/B *execution* of 898 cells — validators expand-validate only (no `run_study`).
- Mutation testing — QI-11.

---

## 2. Code-quality readout

### 2.1 Metrics (`539dd2e`)

| Metric | Value |
|---|---|
| `radon cc` D+ in scope | **F:** `pages/15_Studies._draft_from_builder_widgets` **73**, `_render_build` **59**; `builder.hydrate_study_draft` **62**; `execute.run_study` **60**; `schema._validate_factors` **46**; `program_b.validate_study_file` **110**. **E:** `_render_inspect` 40, `_compose_promoted_draft` 37, `_render_inspect_peek` 36, `schema.validate_study_spec` 32, `generate_packet` 31. **D:** `_narrow_factors_to_survivors` 30, `_sync_builder_widgets` 29, `peek_study_cell` 28, `_render_inspect_catalog` 28, `_build_setup_for_cell` 25, `rollup._compose_row` 24, `schema._validate_constants` 23, `build_otf_delta` 23, `select_admit_bucket` 22, `_render_launch_controls` 22, `_render_saved_desks` 22, `_validate_levels_map` / `closed_level_token_set` / `_validate_report` 21, `launch._pin_dataset_paths` 21. Average **B (7.06)** over 548 blocks |
| MI = 0.00 | `pages/15_Studies.py`, `pages/16_Study_Observatory.py`, `observatory.py`, `builder.py`, `execute.py`, `viewer.py`, `schema.py`. Others: `report.py` 7.57, `briefing.py` 12.16, `promote.py` 16.79 |
| Function length > 150 | `_render_build` 398 · `run_study` 264 · `validate_study_file` 222 · `hydrate_study_draft` 170 · `_draft_from_builder_widgets` 164 |
| Broad `except Exception` | 17 in `thesistester/study/` (see §2.4). **0** on `pages/15_Studies.py` / `pages/16_Study_Observatory.py` |
| `st.session_state` lines | Studies **235** · Observatory **70** (matches QI-0 Studies 235) |
| Streamlit in `thesistester/study/` | **0** AST imports (comments/docstrings only) |
| Private-import `rg` | `preview` → `expand._apply_stage_filter`; `rollup` → `report._bundle_path_within_study`; pages/builder `loader as _data_loader` (alias false friend) |
| `vulture` ≥60 | TypedDict / CLI entry / Wave-7 constants used by Program B validator — **no confirmed dead public API**. `cli_study.add_study_subparser` is the CLI mount (false unused) |
| `bandit -ll` | **B324 High** `naming.factor_cell_fingerprint` SHA1 (identity suffix, not a secret) |
| Coverage (QI-0 table, same product tree) | `execute.py` 76% (140 miss) · `observatory.py` 84% (142 miss) · `schema.py` 85% · `builder.py` 84% · `viewer.py` 87% · `launch.py` 83% · `cli_study.py` 91% · `ledger.py` 94% |
| Churn (last 400 commits) | still Study-heavy: `observatory.py` 26 · `pages/16` 20 · `schema.py` 19 · `pages/15` 11 |

### 2.2 Import-contract verification table (exit criterion)

AST/direct imports on `539dd2e` (`/tmp/qi07/probe_results.json` §imports). Chain reading matches QI-12 §2.6 independently.

| Contract | Documented? | Direct hold? | Module-level chain | Runtime / grimp-style chain | Evidence |
|---|---|---|---|---|---|
| `preview` ↛ `execute` | Yes (RS-D8 / AGENT_GUIDE) | **Yes** | Hold (`preview` → `expand` only) | **Broken:** `expand` → `thesistester.cli` (`EXPERIMENT_SCHEMA_VERSION`) → function-import `cli_study` → `execute`. Also `thesistester.study.__init__` eager-imports `run_study` | AST: no `execute` in `preview.py`. `tests/study/test_study_preview.py::test_preview_module_import_allow_list` |
| `viewer` ↛ `cli_study` / `cli` / `execute` / `rollup` / Plotly / Streamlit / `observatory` | Yes (SV/SO) | **Yes** | **Hold** | **Hold** | AST empty banned set. `test_viewer_module_import_allow_list` |
| `observatory` ↛ `cli_study` / `execute` / Streamlit / Plotly | Yes (SO) | **Yes** | **Hold** | **Hold** | AST empty. `test_observatory_and_viewer_import_guards`. Writes only `{store}/study_observatory/desks` |
| `launch` ↛ `execute` (AH2 / RS-D9) | Yes | **Yes** | Hold | **Broken** via `expand` → `cli` → `cli_study` | AST + `test_launch_module_import_allow_list` |
| `launch` ↛ `viewer` | Yes (ARCHITECTURE) | **Yes** | Hold | **Broken** via same `cli_study` function import | Same |
| `builder` ↛ `execute` | **Call ban** (SB), not an import ban | **Yes** (no import; no `run_study(`) | N/A | N/A | `test_builder_module_import_allow_list` |
| `admit_followup` ↛ execute/launch/viewer/cli/Streamlit | Yes (SAF) | **Yes** | **Hold** | **Hold** | AST |
| library study ↛ Streamlit | Yes (R18) | **Yes** | **Hold** | **Hold** | AST 0 files |
| pages 15/16 ↛ in-process `run_study()` | Yes (RS-D9) | **Yes** | Pages do not import `execute` | **Runtime:** any `import thesistester.study.*` runs `__init__.py` and *loads* `execute` | `page15_run_study_call=false`; spawn is `spawn_launch` → `python -m thesistester study run` |

**Reading.** Direct / AST bans **hold** and are already tested (QI-11). The broken *chains* are the documented package-init honesty + `expand`’s constant import of `thesistester.cli`. That is QI-12-07’s missing mechanical gate, not a new leaf-ban breach. This slice does **not** propose routing pages through `run_study()`.

### 2.3 `pages/15_Studies.py` decomposition map (exit criterion)

**Three tabs, not four.** Visual order: `Inspect output dir` · `Preview StudySpec` · `Build StudySpec`. Launch is **not** a tab — RS-D9 “Run via CLI” is embedded in Preview after a successful validate (`_render_launch_controls`). Build runs *before* Preview on each rerun so Apply can write `studies_preview_yaml` before Preview widgets mount.

| Cluster | Symbols | Role | Extract direction (QR-D; not an implementation) |
|---|---|---|---|
| Inspect catalog | `_render_inspect_catalog`, `_catalog_select_label` | SV1 scan + Load selected | Keep as one helper module |
| Inspect quality | `_render_inspect_quality` | Failed / group / rollup-if-present / launch-log | Already isolated |
| Inspect charts | `_render_inspect_charts`, `_ranked_chart_frame` | SV3 Plotly on loaded frames | Page-only (viewer forbids Plotly) |
| Inspect peek / briefing | `_render_inspect_peek`, `_render_inspect_briefing`, `_apply_inspect_admit_followup` | SV4/SV5 + SAF2 Preview write | Peek vs Admit already split |
| Inspect orchestrator | `_render_inspect` E(40) | Path / load / refresh / cache | Thin orchestrator after pane extract |
| Preview | `_render_preview`, `_render_preview_result` | YAML + `preview_study_yaml` | Stays page |
| Launch | `_render_launch_controls`, `_spawn_or_error`, `_clear_launch_session` | Confirm-bind + `spawn_launch` | Already isolated |
| Build collect | `_draft_from_builder_widgets` **F(73)** 164 lines | Widget → `StudyDraft` | Section collectors (identity / dataset / levels / factors / batteries / stage-report) |
| Build render | `_render_build` **F(59)** 398 lines | Entire Build tab | `_render_build_{identity,dataset,levels,factors,batteries,actions}` — `_render_builder_stage` / `_render_builder_report` already exist |
| Hydrate / sync | `_sync_builder_widgets` D(29), `_hydrate_builder_draft` | Draft ↔ `_study_builder_*` | Parallel to Setup Builder QI-03-04 |
| Ingest helpers | `_resolved_builder_ingestion_mode`, `_apply_builder_ingestion_mode`, `normalize_builder_format_profile` | SIA radios + format labels | Page-local stale-safe copies of builder helpers |

**Session-key namespaces (no classic leakage)**

| Namespace | Written on page 15 | Notes |
|---|---|---|
| `studies_*` | viewer dir/cache/catalog, preview YAML/cache, launch output/approval, admit notice/error, builder draft/pending_sync | Observatory **writes** `studies_viewer_*` on drill-through then `st.switch_page` |
| `_study_builder_*` | 61 `WIDGET_KEY_*` + dynamic `partner_set_{i}` / `stage_include_{axis}` | Build widgets only |
| `observatory_*` | **not used** on page 15 | Page 16 only |
| Classic research keys | **none** | Docstrings forbid `apply_research_bundle_to_session` / classic hydrate |

**Execution model:** no `run_study(`; no `autorefresh`; `st.rerun()` is widget/apply/hydrate only. CLI spawn via `spawn_launch`. Inspect Refresh is explicit (RS-D2).

### 2.4 Hot-spot notes

- **`run_study` F(60), 264 lines, MI 0.00 module.** Phases: `prepare_study_expansion` → confirm/lock → write expansion → ledger merge → `cells_to_run` (soft-resume) → mark `running` → in-process or spawn pool → `_finalize_running_cells` (leftover `running` → `failed`) → index sync. Complexity is orchestration, not fill math. Broad `except Exception` in `execute_study_cell` is *continue-on-failure* (RS3; returns `status=failed` + typed error string) — *narrow-guard OK*. Random-baseline `except Exception` nulls DA5 fields rather than failing an ok cell — *swallows battery*, not cell status.
- **`schema.py` 973 / `_validate_factors` F(46) / `validate_study_spec` E(32).** Hand-rolled authoring gate. Expand then calls `api.validate_run_spec` per cell (QI-6). Shared concepts (ingestion_mode, triggers, direction) are **reimplemented**, not delegated. Not a request to collapse composers.
- **`hydrate_study_draft` F(62).** Mapping → `StudyDraft`; comment says emit validates. Parallel to `_draft_from_builder_widgets`.
- **`observatory.py` 2,069 / MI 0.00.** Largest study module; coverage 142 misses (QI-0 top-10). Read-only contract holds (see §6).
- **`validate_study_file` F(110).** Program B lock table in one function (instrument / trigger / ingest / format / cell counts). Packet drift is a change-cost risk.
- **`naming.factor_cell_fingerprint` SHA1.** 10-hex disambiguator of canonical factor JSON. `expand.study_identity_hash` already uses SHA256. Bandit B324; not a password/secret hash (QI-12-06 handoff).
- **Launch Windows branches.** `os.name == "nt"` → `_pid_is_alive_windows` (`ctypes` OpenProcess, never `os.kill`); `_popen_detach_kwargs` omits `DETACHED_PROCESS`. Tests exist (`test_windows_*`, `test_study_dir_lock_msvcrt_*`).
- **Broad except classification (study library):** viewer/observatory BLE001 = *one corrupt dir must not fail the catalog* (accepted Signals-page pattern). `launch.spawn_launch` `except Exception: cleanup; raise` = *narrow-guard OK*. `tools.py` wraps report/promote as capability errors.

---

## 3. Application-quality readout (§3.2 per entry point)

### 3.1 CLI `python -m thesistester study` (`cli_study.dispatch_study`)

| Check | Result |
|---|---|
| Happy | `--help` exit 0; verbs `expand/run/report/promote/rollup/list/observatory`. 4-cell expand+run exit 0 (`run_count=4`, `ok=4`) |
| Empty / missing | `study report /tmp/qi07-does-not-exist` → rc 2, **no Traceback**, `Study report error: …` (unlike QI-06-07 `run` verb) |
| Malformed | `StudySpecError` / `StudyReportError` / `StudyPromoteError` caught; rc 2 |
| Stale / resume | Soft-resume after a ledger `running` + missing zip: next `study run --confirm` executed **1 / 4** and restored `ok` + zip |
| Composer parity | Study loop is `run_experiment` + `execution_origin=study` (AH §2 item 1). Replay `thesistester run experiment.yaml` remains `run_batch` |
| Honesty | Expand prints `Replay: python -m thesistester run …/experiment.yaml` **without** the AGENT_GUIDE “not study run” sentence (QI-07-06). Report MD has the multiple-testing paragraph |
| Persistence | Expansion writes `study.spec.yaml` / `study.expansion.json` (`source_spec_parent` set) / `experiment.yaml` with **absolute** dataset pins |
| Operability | `Cell status: ok=… failed=…` on run; unique ledger errors when any failed |

### 3.2 Library `expand → run_study → report_study → promote_study → load_observatory_frame`

E2E under `/tmp/qi07/e2e` on `sample_data/ES_sample_1m.csv` (12 RTH bars). Spec: 2 cores (`ONH`,`ONL`) × 2 triggers (`touch`,`reject`) × singleton partners/mode/tf/otf = **4 cells**; all batteries `{enabled: false}`; `min_trades: 0`.

| Step | Evidence |
|---|---|
| Expand | rc 0; 4 runs; every `dataset.path` = `/tmp/qi07/e2e/data/es_1m.csv` (spec-parent pin); `source_spec_parent` recorded |
| Run | rc 0; ledger 4×`ok`; **not** a claim that fills/P&L are meaningful on 12 bars |
| Resume | Victim marked `running`, zip deleted; rerun executed 1 cell; victim `ok`, zip restored |
| Report | Honesty line uses `len(overview)` only. After injecting one `failed` row + forcing one ranked primary: `Cells in overview: **4**; ranked: **1**; low-N: **0**; unresolved primary: **2**. **No `## Failed` heading.** `failed` word count in MD = 0 |
| Rollup | `cell_count=4` (= full index, including failed). Per-cell table shows `status=failed` but no Failed section |
| Promote | `top_n=10` selected the forced-ranked ok cell only; injected failed **excluded**. Fail-closed when no ranked survivors (`StudyPromoteError`) |
| Observatory | Prefix scan of cwd looks one level under `results/studies/` and `out/` — a study whose `output_dir` *is* `out/` is invisible until `extra_dirs=["out"]`. Then frame **4** rows (3 ok + 1 failed), studies **1**. **No new files** in the study dir. `{store}/results/studies` not created |

Cells completed. Ranked `expectancy_r=0.25` was **written into the index for the H16 recipe** — it is not a verified expectancy.

### 3.3 Pages 15 / 16

| Check | Result |
|---|---|
| Happy (static) | Build → Apply → Preview → spawn CLI; Inspect load/refresh; Observatory desks + Open in Inspect. Not AppTested here (QI-10/QI-11) |
| Empty | Inspect/preview typed `StudyViewerError` / `StudySpecError` → `st.error`. No raw `except Exception` |
| Stale | Inspect cache keyed by dir; Refresh explicit. No auto-refresh (RS-D2 holds in source) |
| Composer | Pages do not call `run_study()`. Preview expand is in-process dry-run only |
| Honesty | Build live strip + Preview show battery flags. Quantower+primary warning is **builder `draft_warnings` only** (QI-07-05) |
| Persistence | Builder draft in `studies_builder_draft`; Preview YAML in `studies_preview_yaml`. Observatory desks under store |
| Accessibility | Tab labels ≠ QI shorthand (“Launch” is a Preview pane) |

### 3.4 Builder / schema authoring gate

| Check | Result |
|---|---|
| Batteries OFF emit | `default_study_draft()` and empty-battery emit write `grid/validation/walk_forward: {enabled: false}` — **AH7 current state is already explicit false** (parked item done for batteries) |
| New draft ingest | `ingestion_mode=15s_primary_derive_1m`, `format_profile=quantower_history_exporter` (SIA) |
| Hand-authored Quantower omit mode | `validate_study_spec` **accepts**; omitted → RunSpec `primary` (different experiment). Builder warning only when widgets say primary+Quantower |
| ToD factor | `factors.time_of_day` → `StudySpecError: Unsupported factor axes`. ToD stays peek/Admit lineage (`_LINEAGE_ADMIT_GROUPS`) |
| WFA as `primary_metric` | Rejected; allowlist `{expectancy_r, total_r, max_drawdown_r, trade_count, profit_factor}` (QI-05-06) |

### 3.5 Program B packets

`validate_program_b_yaml.py examples/studies/program_b/manifest.yaml` → **ok 20 studies / 898 cells**. `manifest_tick.yaml` → ok. Generator is import-loaded by the validator; **neither imports `execute`**.

### 3.6 H2 pin (status)

`pin_dataset_paths_against_parent` + `dataset_path_search_roots` on a spec-parent vs cwd twin: pin = spec-parent absolute; search order **spec parent → extra_roots → cwd last**. `tests/study/test_ah2_study_path_pin.py` **9 passed** (AH2-P1–P5 + extras).

---

## 4. Prior-audit carry-over status

| Item | Status on `539dd2e` | Finding |
|---|---|---|
| **C2** Study replay path (AH2) | **Closed-verified.** Expand pins spec-parent absolute paths; `source_spec_parent` in `study.expansion.json`. Probe family `test_ah2_*` present. Math/identity of *bytes* not re-audited beyond pin target | none (positive) |
| **H2** Promote / launch cwd-first pin | **Closed** for spec-parent-first search (AH2). Residual **parked:** coworker portable relative rewrite (AH2 §6.2 out-of-scope) | QI-07-10 |
| **H16** Failed-cell MD/rollup + WFA-ignorant ranking | **MD/rollup still open** (no Failed section; rollup `cell_count=len(frame)`). **Ranking half** still locked in-sample (`AUDIT_FINAL` §5.1 item 34); QI-05-06 already filed the allowlist. Index *writes* `wfa_median_test_expectancy_r` via `execute.build_index_row_from_state` | QI-07-04 (MD/rollup only) |
| **W11** Study/headless split | **Closed-verified** by R18/RS. Pages stay Composer A; study CLI/library call `run_experiment`. Do not collapse | none |
| **AH7** Builder Advanced OFF → explicit `enabled: false` | **Current state:** batteries already emit `{enabled: false}`. Levels Advanced-OFF vs product defaults is H4 / QI-02 | none (positive for batteries) |
| **C1/C3/H1/H3/H6** | Not this slice | — |

Locked premises not re-opened: two composers; `run_batch` ≠ `study run`; ranking stays in-sample `primary_metric`; failed cells excluded from ranked/promote and **included** in overview CSV / rollup N (`AUDIT_FINAL` §5.1 item 34); ToD is not a factor axis; no in-process page runner.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Sev | Class | Title |
|---|---|---|---|
| QI-07-01 | Medium | Maintainability risk | `pages/15_Studies.py` MI 0.00 / F(73)+F(59) — three tabs fused |
| QI-07-02 | Medium | Maintainability risk | `run_study` F(60) / `execute.py` MI 0.00 |
| QI-07-03 | Medium | Maintainability risk | StudySpec validator 973 lines; `_validate_factors` F(46) parallel to `validate_run_spec` |
| QI-07-04 | Medium | UX/operability gap | H16 MD/rollup: failed cells in N, no Failed section (Inspect has one) |
| QI-07-05 | Medium | UX/operability gap | 15s Quantower + omitted `ingestion_mode` accepted at validate |
| QI-07-06 | Medium | UX/operability gap | Expand CLI / `experiment.yaml` omit “not study run” (docs have it) |
| QI-07-07 | Medium | Maintainability risk | `observatory`/`viewer`/`builder`/`schema` + page 16 MI 0.00 |
| QI-07-08 | Medium | Maintainability risk | Program B `validate_study_file` F(110) |
| QI-07-09 | Low | Security risk | `naming.factor_cell_fingerprint` SHA1 (identity suffix) |
| QI-07-10 | Low | Design limitation | H2 residual: coworker portable relative pin parked (AH2) |

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **Direct import bans hold** for `preview`, `viewer`, `observatory`, `launch`, `builder`, `admit_followup`. AST tables + 7 named import-allow tests passed. No Streamlit import inside `thesistester/study/`.
2. **Pages 15/16 do not call `run_study()`** and do not import `execute`. Launch is `spawn_launch` → detached CLI. No auto-refresh / kill / retry in source (RS-D2/RS-D9).
3. **AH2 / C2 / H2 pin-roots are implemented and tested.** Search order spec-parent first; expand writes absolute paths when the file exists; 9 `test_ah2_*` passed. Coworker portable rewrite stays parked (QI-07-10).
4. **Ledger soft-resume after a killed-looking cell works as specified:** leftover `running` + missing zip is re-queued; `--force` not required. 4-cell run printed `executed 1 / 4` on resume.
5. **Failed cells cannot be promoted.** Promote selected only `status=ok` ranked rows. Inspect/viewer already list unique failed errors (`failed_cells_frame` / “Failed cell errors”).
6. **Observatory is read-only for `results/studies/`.** `load_observatory_frame(extra_dirs=["out"])` returned 4 cells / 1 study and wrote **zero** files into the study dir. Desks are store-scoped.
7. **ToD is not a factor axis** (`StudySpecError` on `factors.time_of_day`). `_SUPPORTED_FACTOR_AXES` is the seven closed axes. SAF lineage groups stay post-hoc.
8. **Builder batteries OFF emit explicit `enabled: false`.** New drafts default to 15s-primary + Quantower (SIA). Program B manifests validate clean (20/898 and tick packet).
9. **Study CLI fail-closed without a traceback** on a missing report path (rc 2). `--help` lists all verbs.
10. **`tests/study` 543 passed twice** (`-p no:cacheprovider` and `PYTHONHASHSEED=7`). Suite result, not a Study-correctness claim.

---

## 7. Handoffs to other slices

| To | Observation (not a finding) |
|---|---|
| QI-5 | H16 ranking allowlist already QI-05-06. Index WFA columns are written here (`execute.build_index_row_from_state`) |
| QI-6 | `expand` imports `thesistester.cli.EXPERIMENT_SCHEMA_VERSION` (chain hub). `validate_run_spec` remains the cell gate. Study CLI traceback gap is **closed** vs the `run` verb (QI-06-07) |
| QI-10 | 235 + 70 session-state lines; `studies_*` / `_study_builder_*` / `observatory_*`; Observatory → Inspect drill keys; no classic hydrate |
| QI-11 | Study coverage debt 140/142 misses on execute/observatory; AppTest is page 16 only; accept-path smells QI-11-06 already named `tests/study/test_study_schema.py` |
| QI-12 | SHA1 B324 (QI-12-06); import-linter chains (QI-12-07). This table is the study-specific SoT |
| QI-13 | STUDY_RUNNER / AGENT_GUIDE already disclose replay ≠ `study run`; USER_GUIDE Studies tabs vs “Launch”; Failed-section copy |
| QI-14 | `--workers` scaling and Observatory load vs corpus size not measured |
| QI-2 | Levels Advanced-OFF vs `DEFAULT_LEVELS_SETTINGS` (H4) when Build expander is off |
| QI-1 | Format-profile fallback duplication (`builder._FORMAT_PROFILE_LABELS_FALLBACK`) — QI-01-06 already noted runtime equality |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/STUDY_RUNNER.md` | Failed-section / rollup N label (H16); expand CLI replay caveat; `out/` prefix vs `out/<name>` catalog rule |
| `docs/AGENT_GUIDE.md` §Study | Quantower omit-mode is warning-only at validate; import-linter vs AST; SHA1 identity note |
| `docs/USER_GUIDE.md` Studies / Observatory | Three-tab layout (Launch under Preview); Failed visible on Inspect not in `study.overview.md` |
| `docs/ARCHITECTURE.md` | Session keys `studies_*` / `_study_builder_*` / `observatory_*`; package-init honesty sentence |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | H16 presentation gap; omitted `ingestion_mode` = primary (already implied) |
| `docs/METRICS_GLOSSARY.md` | Only if QR adds a Failed-count / rollup-N definition |

---

## 9. E2E evidence (throwaway; not a correctness claim)

```text
commit 539dd2e
spec  /tmp/qi07/e2e/study.yaml
data  /tmp/qi07/e2e/data/es_1m.csv  (copy of sample_data/ES_sample_1m.csv, 12 bars)
cells 4 (ONH|ONL × touch|reject)

expand  rc=0  run_count=4
        pinned dataset.path = /tmp/qi07/e2e/data/es_1m.csv  (all four)
        source_spec_parent recorded
        experiment.yaml has no "not study run" sentence
        stdout includes: Replay: python -m thesistester run …/experiment.yaml

run     rc=0  ledger ok=4 failed=0
        (completion only — fills/P&L not verified)

resume  mark c0000 running + delete zip
        rerun: executed 1 / 4; victim ok; zip restored

H16    inject c0003 failed; force c0000 expectancy_r/trade_count for a ranked row
        report: overview=4 ranked=1 unresolved=2; no ## Failed; "failed" absent from MD
        rollup: cell_count=4; status=failed on the injected row; no Failed section
        promote: selected=[c0000]; injected excluded

observatory  extra_dirs=["out"] → frame=4 studies=1 (3 ok + 1 failed)
             no writes under the study dir; store results/studies absent
```

H2 twin-file pin (`/tmp/qi07/h2`): `expand_pin_is_parent=true`; roots `[spec, out, draft, cwd]`.

Program B: `ok 20 studies / 898 cells` (15s manifest); tick manifest rc 0.

---

## 10. Probe recipes (pasted; not committed)

Full script: `/tmp/qi07_probes.py`. Essential recipes:

```python
# Import-ban AST (direct only)
# see /tmp/qi07_probes.py::study_module_imports

# 4-cell StudySpec (batteries explicit false)
{
  "schema_version": 1,
  "study": {
    "name": "qi07_e2e",
    "workers": 1,
    "confirm_above_runs": 4,
    "dataset": {"path": "data/es_1m.csv", "instrument": "ES",
                "source_timezone": "America/New_York"},
    "levels": {"sma_lengths": [50], "ema_lengths": [21],
               "sma_timeframes": ["1min"], "ema_timeframes": ["5min"]},
    "constants": {
      "direction": "both", "tolerance_ticks": 0,
      "min_confluences": 2, "max_confluences": 2, "min_valid_confluences": 1,
      "naked_only": False, "naked_requirement": "any", "trigger_params": {},
      "backtest": {"stop_loss_ticks": 8, "take_profit_ticks": 16,
                   "exposure_policy": "single_position"},
      "grid": {"enabled": False}, "validation": {"enabled": False},
      "walk_forward": {"enabled": False},
    },
    "factors": {
      "core_level": ["ONH", "ONL"],
      "partner_levels": [["SMA_50_1min"]],
      "confluence_mode": ["anchor_rules"],
      "trigger": ["touch", "reject"],
      "trigger_timeframe": ["base"],
      "otf": [{"enabled": False}],
    },
    "mode_rules": {"anchor_rules": {
      "selected_levels": [], "anchor_level": "${core_level}",
      "confluence_rules": {"from_partners": "required"}}},
    "report": {"primary_metric": "expectancy_r", "min_trades": 0,
               "multiple_testing": "warn"},
  },
}
```

```bash
export THESISTESTER_STORE_DIR=/tmp/qi07-store-probes
unset OPENAI_API_KEY XAI_API_KEY
python -m thesistester study expand /tmp/qi07/e2e/study.yaml --output-dir /tmp/qi07/e2e/out
python -m thesistester study run /tmp/qi07/e2e/study.yaml --output-dir /tmp/qi07/e2e/out --confirm
python -m thesistester study report /tmp/qi07/e2e/out
python -m thesistester study rollup /tmp/qi07/e2e/out
python -m thesistester study promote /tmp/qi07/e2e/out --output /tmp/qi07/e2e/draft.yaml --top-n 10
# observatory: study dir must be extra_dirs or sit under results/studies/ or out/<name>
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
