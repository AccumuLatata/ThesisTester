# ThesisTester audit Slice 6 — Study Runner

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390), Slice 1 (`AUDIT_SLICE1.md`, PR #391), Slice 2 (`AUDIT_SLICE2.md`, PR #392), Slice 3 (`AUDIT_SLICE3.md`, PR #393), Slice 4 (`AUDIT_SLICE4.md`, PR #394), Slice 5 (`AUDIT_SLICE5.md`, PR #395). Prior **locked contracts** are treated as given. Fill math, 3c, `trading_session_date`, Focus/WFA internals, and classic `session_state` pages 1–14 were not re-audited except where Study **composes** those surfaces.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/study/` — **292 passed**.
**Goldens:** `tests/fixtures/study/golden/*` are byte-stable expand artifacts. They prove **legacy-unchanged StudySpec → experiment.yaml identity**, not cell correctness, failed-cell honesty, or path pinning.

This file is the Slice 6 deliverable. Slice 7 must treat the **locked contracts** in §5 as given, and the **open items** in §6 as still unverified outside this layer.

---

## 0. Contracts used here (not re-proven)

### From Slice 5 (locked)

1. Focus is post-hoc on `entry_timestamp`. Not `simulate_trades`. C7 identity is `allow_all` + 0 cooldown only.
2. WFA session folds key by `trading_session_date` + `eth_start`. `causal_prefix` prefix strictly `<` fold start. OTF once per phase.
3. `run_wfa_matrix` default metric is OOS. Selecting the greenest cell is multiple-testing.
4. OTF validation matrix ranking column is `train_expectancy_r`, but sims use the full `source_df` — do **not** treat that ranking as fold-isolated.
5. Core KPIs match glossary. `r_multiple` / `pnl_currency` net; `pnl_points` gross.
6. R10 `both_hit_rule` does not inherit R12.
7. Combo / prev30m invent neither fills nor signals. In-window NaN is not 0.
8. Portfolio is a stitch, not a capital simulator. Correlation is on candidates.
9. Phase 8 is in-sample diagnostic. No `diagnostic_only` flag.
10. Goldens ≠ correctness. Skip-frame count ≠ all non-fills. Disabled-OTF `otf_filter_passed=True` is not a pass.
11. `SESSION_CLOSE` / exit-grouped time buckets are **not** `trading_session_date` closes.
12. Do not treat WFA matrix / grid ranking / Focus bucket / OTF-matrix “winner” as a deployable parameter.

### Also locked (handoff)

Two settings planes (`bare compute_all_levels` ≠ product). `validate_setup_config` does not reject `BASE_COLUMNS` (API/Study can leak `close` as a level). Studies Build first-visit default is 15s-primary; classic API/CLI default is not. Study viewer must not import execute/cli/rollup/Streamlit.

---

## 1. Architecture of the Study layer

### 1.1 What this layer owns

Study is a **factorial composer** over the same `validate_run_spec` + `run_experiment` path as a hand-written R18 YAML run. It does **not** invent fills, signals, or a second simulator.

```text
StudySpec YAML  (schema_version: 1)
        │
        ▼
normalize_study_spec → validate_study_spec     ← closed tokens, enabled:true|false
        │
        ▼
expand_study  → R18 experiment.runs[] + factor_map
        │         each run: validate_run_spec
        │         setup via api.build_setup (validate_setup_config only)
        ▼
run_study  (NOT run_batch)
        │   per cell: run_experiment(origin="study") → build_research_bundle
        │   continue-on-failure; ledger + results_index.csv
        ▼
report_study  (index ⟕ expansion; PF/WR index→bundle; no live recompute)
        │
        ├─► promote_study   ranked survivors → draft StudySpec (no execute)
        └─► rollup_study    compose WFA/validation/overfitting (no cross-cell PBO)
```

Surfaces:

| Surface | Calls `run_study`? | Writes overview/rollup? |
|---|---|---|
| `python -m thesistester study run` | Yes (in-process) | No |
| RS6 `STUDY.run` (default-off) | Yes (in-process) | No |
| Studies Preview **Run via CLI** | No — `Popen` CLI child | No |
| Inspect / catalog / peek | No | `report_study(..., write_artifacts=False)` only; never `rollup_study()` |
| `python -m thesistester run experiment.yaml` | No — `run_batch` | Overwrites `results_index.csv` (fail-fast) |

### 1.2 Three path-resolution planes (do not conflate)

| Plane | Relative `dataset.path` resolves against | Who uses it |
|---|---|---|
| **Study execute** | StudySpec file parent (`prepare_study_expansion` → `base_directory=study_path.parent`) | `study run`, `STUDY.run` |
| **R18 CLI replay** | `experiment.yaml` parent (`cli.main` → `run_batch(..., base_directory=experiment_path.parent)`) | advertised `thesistester run out/study1/experiment.yaml` |
| **Launch / promote pin** | First existing file under cwd / store / (promote: study output dir, draft parent) | Studies **Run via CLI**, `study promote` |

Expand copies `dataset.path` **as authored**. It does not pin. AGENT_GUIDE L38–39 advertises replaying the emitted `experiment.yaml` as “unchanged R18 path.” That replay is **not** identity-equivalent to `study run` of the source YAML when the path is relative.

### 1.3 Two default planes Study must not invert

| Plane | Who fills omitted keys | Study uses it? |
|---|---|---|
| **Product** `DEFAULT_LEVELS_SETTINGS` | `closed_level_token_set`, `normalize_levels_config` / `compute_levels` | Yes — token admission **and** execute |
| **Bare** `compute_all_levels` keyword defaults (advanced families False; OR 30) | library call without API wrapper | **No** |

Omitted `study.levels` keys are **not** “family off.” They are product-on (prev30m/pivots/APOC/session VWAP True; SMA 50/200; OR 15). Same as a hand-written YAML with a sparse `levels:` block. Not the bare engine plane.

---

## 2. Must-answer questions

### Q1. Does study expand produce a RunSpec equivalent to a hand-written YAML run? Any silent default fill from the wrong settings plane?

**Structurally yes: each expanded cell is a `validate_run_spec` R18 run with the same `run_experiment` body. Equivalence of *relative* dataset identity and of omitted-key fills is not complete. Silent fills are the product / API plane, not bare `compute_all_levels`.**

Expand (`expand.py` `_expand_validated`) emits, per cell:

- `dataset` = deep copy of `study.dataset` (no path rewrite, no ingest default injection)
- `levels` = deep copy of authored `study.levels` (may be `{}` or SMA-only)
- `setup` = `api.build_setup(...)` (required trigger / mode / TF; OTF omit → `{enabled: False}`; direction omit → `both`)
- `backtest` = authored mapping (must include `stop_loss_ticks` / `take_profit_ticks`)
- `grid` / `validation` / `walk_forward` = authored or `{enabled: False}` — **never** bare `{}` (avoids `run_experiment`’s `.get("enabled", True)` default-on trap)

Every cell passes `validate_run_spec`. Golden `tests/fixtures/study/golden/*` is byte-stable for an 8-cell mini spec.

**Where expand ≡ a hand-written YAML with the same mappings:** same keys, same `build_setup` normalization, same `run_experiment` merge of `_BACKTEST_DEFAULTS` / `_LEVEL_DEFAULTS`. `test_enabled_false_emitted_not_bare_empty` locks the battery emission.

**Where it is not equivalent:**

| Gap | Bad case |
|---|---|
| Relative `dataset.path` | Source YAML at `examples/studies/pdPOC_ma_confluence_battery.yaml` with `path: data/es_15s.csv`. `study run` resolves `examples/studies/data/es_15s.csv`. Written `out/study1/experiment.yaml` still has `path: data/es_15s.csv`. `python -m thesistester run out/study1/experiment.yaml` resolves `out/study1/data/es_15s.csv`. AGENT_GUIDE L38–39 presents this as a valid replay. |
| Product levels fill | Authored `levels:` only SMA/EMA (pdPOC example L46–50; builder Advanced OFF pops `prev30m_vwap_enabled` / `pivots_enabled` — `pages/15_Studies.py` L1399–1407). Token set **and** `compute_levels` still enable prev30m/pivots/APOC/VWAP windows via `{**DEFAULT_LEVELS_SETTINGS, **raw}`. Operator who thinks “Advanced off = families off” gets product-on columns. Same fill as a sparse hand-written YAML — wrong *mental* plane, not a Study-only fork of the API. |
| Backtest omit | Expand requires SL/TP only. Omitted `exposure_policy` → API `_BACKTEST_DEFAULTS` = **`allow_all`**. Builder emit always writes `single_position` (`builder._default_backtest`). Hand-written StudySpec without the key ≠ Build draft. |
| Dataset omit | `ingestion_mode` omitted → `primary` at `run_experiment` (Slice 1 / SIA). `format_profile` omitted → `canonical`. `source_timezone` omitted → instrument `exchange_tz`. Build first-visit is 15s-primary + Quantower + UTC + MNQ. |
| Study schema dataset keys | `validate_study_spec` does **not** `_unknown_keys` on `dataset`. Extra keys fail only later at `validate_run_spec` (expand). `data_artifact_key` / `data_identity` are legal RunSpec keys and can pass through a StudySpec unexamined. |

`closed_level_token_set` (`schema.py` L256) merges product defaults before admitting MA / prev30m / Pivot tokens. That is the **same** merge `normalize_levels_config` uses at execute. Token admission and compute stay on one plane (product). They do **not** use bare `compute_all_levels` keyword defaults.

### Q2. Failed-cell honesty: are failed cells visible, counted, and excluded from rollup/promote correctly?

**Visible and excluded from ranking / promote. Counted into rollup `cell_count` and report “cells in overview.” Report markdown has no failed section. Ledger `skipped` is never written.**

| Surface | Failed cells |
|---|---|
| Ledger | `status=failed`, `error` string, `bundle_path=None`; stale zip unlinked (`execute._apply_cell_result`) |
| CLI `study run` | `Cell status: ok=… failed=…`; unique errors via `failed_cell_error_lines`; process exit 1 if any failed (`cli_study.py` L221–226) |
| `results_index.csv` | `status=failed`; all R18 metrics + PF/WR null |
| Report ranked / low-N / unresolved / group / OTF Δ | `status==ok` required (`report.split_ranked_and_low_n`, `build_group_summaries`, `build_otf_delta`) |
| Report overview CSV | Failed rows **included** (joined) so they are inspectable |
| Report markdown | Honesty counts `len(overview)` (includes failed) + ranked / low-N / unresolved. **No Failed section** |
| Promote | Ranked-eligible only (`select_survivor_run_names`); failed cannot be selected |
| Rollup | **Every** index row, including failed (`build_rollup_frame`). No bundle → batteries `not_run` / null. `cell_count=len(frame)` includes failed. Markdown table shows `status` |
| Inspect | `failed_cells_frame` lists every failed `run_name` + full error; caption caps unique errors (SV2) |
| Soft resume | Failed cells are **re-queued** (`cells_to_run` skips only `ok` + existing zip) |

**Honest:** failed cannot become ranked winners or promote survivors; PF/WR cannot stick on failed/pending (`execute.py` L821–823, L851–853).

**Not honest enough:**

- Report MD can say “Cells in overview: 40; ranked: 12” with 8 failures invisible except in the CSV.
- Rollup “cells=40” after 10 failures looks like battery coverage of 40.
- `LEDGER_STATUSES` includes `skipped`; execute never marks `skipped`. Inspect progress treats `skipped` as terminal. Dead status.

**Bad case:** shared ingest fault fails all 40 cells. CLI prints unique errors (good). `study report` still writes overview; ranked empty; operator reading only the MD honesty block may not see *why*.

### Q3. Any in-process `run_study` that bypasses the versioned batch path?

**No second simulator. The page does not call `run_study`. CLI / opt-in `STUDY.run` call the same `run_experiment` loop. Study deliberately does not call `run_batch` (continue-on-failure). Package import of Studies still loads `execute`.**

Documented contract (`STUDY_RUNNER.md` RS3): study loops `run_experiment` + `build_research_bundle`; does **not** call `run_batch`. Each cell still `validate_run_spec` (inside `run_experiment`). That is the versioned **cell** path, not the versioned **batch** path.

| Caller | In-process `run_study`? | Path |
|---|---|---|
| `thesistester study run` | Yes | `cli_study` → `run_study` → `execute_study_cell` → `run_experiment` |
| `STUDY.run` (`tools.run_study_capability`) | Yes, when `[assistant.study_tools] enabled=true` | same `run_study` |
| Studies page | **No** (source + tests forbid `run_study` in page/preview/launch) | `launch.spawn_launch` → `Popen` CLI |
| Inspect / peek / catalog | No | artifacts only |

`run_batch` (`cli.py` L117–127) **raises** on cell failure (`_execute_run` does not catch). Study `execute_study_cell` **always** returns ok/failed. Replaying `experiment.yaml` via `thesistester run` is fail-fast, `execution_origin="cli"`, and a different `base_directory` (Q1). It is not a silent alternate engine, but it is not the study ledger path.

**Import leak:** `thesistester/study/__init__.py` imports `execute` / `rollup` at package load. `pages/15_Studies.py` does `from thesistester.study import viewer` (and `preview`). Opening Studies therefore **imports** `run_study` / `rollup_study` into the Streamlit process even though the page never calls them. `viewer.py` itself stays clean (`test_viewer_module_import_allow_list`).

### Q4. PF / metric source: index vs bundle vs live recompute? Can rollup mix net/gross or peek at test?

**Index then bundle for PF/WR only. No live recompute. Study KPIs are net-R from `trade_summary`. Rollup does not mix `pnl_points`. Promote/report crown in-sample `primary_metric`, not WFA OOS — even when WFA ran.**

Report resolve (`report._resolve_bundle_metrics`):

1. Index `profit_factor` / `win_rate` when present → `profit_factor_source=index`
2. Else bundle `trade_summary.json` (path sandboxed to study dir)
3. Else `missing`

`expectancy_r` / `total_r` / `max_drawdown_r` / `trade_count` come from the index as written. Soft resume rehydrates those plus PF/WR from the bundle when the index row is hollow (`execute._index_row_from_existing_bundle`). There is **no** `summarize_trades` recompute in report/promote/rollup.

Those index fields are `trade_summary` values → `r_multiple` (net). Study never reads `pnl_points`. Rollup WFA columns are `median_test_expectancy_r` / `stitched_oos_total_r` (also R, net). No net/gross mix in this layer.

**Peek / ranking honesty:**

- Promote ranks `report.primary_metric` (allow-list: `expectancy_r`, `total_r`, `max_drawdown_r`, `trade_count`, `profit_factor`) — **full-sample backtest**, not `wfa_median_test_expectancy_r`.
- Enabling `walk_forward` does not change the crowned column. WFA OOS sits on the index / rollup only.
- `multiple_testing: error` suppresses MD crowning; the ranked table still emits.
- Rollup copies per-cell WFA aggregates (Slice 5: overlapping folds **sum** `test_total_r`). Compose-only; no new peek. Inherits Slice 5 overlap / “do not pick the greenest OOS cell.”

**Bad case:** 40-cell study with `walk_forward.enabled: true`. Promote `--top-n 10` still picks the greenest **in-sample** `expectancy_r`. Rollup can show weak OOS on those same cells. No study UI says “ranking ignored WFA.”

### Q5. Isolation: can Study Viewer import execute/cli/rollup/Streamlit? Does Studies mutate classic `session_state`?

**`viewer.py` does not import execute/cli/rollup/Streamlit/Plotly (tested). The Studies **page** is Streamlit + Plotly and, via package `__init__`, loads execute/rollup. Classic research keys are not written (tested walk of assignments).**

| Module | execute | cli / cli_study | rollup_study | Streamlit | Plotly |
|---|---|---|---|---|---|
| `viewer.py` | No | No | No (reads `study.rollup.*` if present) | No | No |
| `preview.py` | No | No (expand only) | No | No | No |
| `launch.py` | No | argv string only | No | No | No |
| `builder.py` | No | No | No | No | No |
| `pages/15_Studies.py` | Not called; **imported via package** | No | Not called | Yes | Yes (SV3 charts) |

Page session writes are Studies-scoped (`studies_viewer_*`, `studies_catalog_*`, `studies_preview_*`, `studies_launch_*`, `studies_builder_*`, `_study_builder_*` widgets). `CLASSIC_RESEARCH_SESSION_KEYS` (`data`, `levels`, `trades`, …) are documented as forbidden. Peek (`viewer.peek_study_cell`) reads index + ledger error + optional `trade_summary.json`; does not `apply_research_bundle_to_session`.

**Residual:** process-level import of `run_study` (Q3). Not a second runner unless something calls it.

### Q6. Ingest tokens vs Slice 1 allow-list; 15s-primary default vs classic default.

**Allow-list matches Slice 1 at `validate_run_spec` time. StudySpec validate is weaker (no unknown-dataset-key gate). Omitted mode is `primary`. Build first-visit is 15s-primary. This is locked SIA and tested.**

Slice 1 closed dataset keys (`api._DATASET_KEYS`): `path`, `instrument`, `source_timezone`, `exchange_timezone`, `format_profile`, `subtimeframe_path`, `subtimeframe_format_profile`, `ingestion_mode`, plus `data_artifact_key` / `data_identity`.

Study schema (`schema.py` L394–412): requires `path` + `instrument`; if `ingestion_mode` present, must be `primary` | `15s_primary_derive_1m`. Does **not** reject unknown dataset keys. Expand copies the mapping; `validate_run_spec` then fail-closes unknowns and enforces 15s-primary ⇒ Quantower + no `subtimeframe_path`.

| Authoring | Default ingest |
|---|---|
| `default_study_draft()` / Build first visit | `15s_primary_derive_1m`, Quantower HE, MNQ, UTC, `subtimeframe_conservative` |
| `StudyDraft()` field defaults / omitted YAML key | `primary` (classic API/CLI) |
| `examples/studies/pRTH_open_ma.yaml`, pdPOC example | 15s-primary (pdPOC stays ES / NY) |
| `examples/studies/dopen_ma_3c_mnq.yaml` | legacy `primary` 1m (documented) |

`test_same_15s_bytes_without_ingestion_mode_are_a_different_experiment`: same 15s bytes without the mode load as 15s **decision** TF (`base_interval=="15s"`), different `dataset_id`. That is the SIA honesty bug if an operator points a 15s Quantower file at a study and omits the mode.

Builder `_DATASET_KNOWN` omits `exchange_timezone` / `subtimeframe_format_profile`; those can still ride in `dataset_extra` and emit.

### Q7. Does Study call `validate_setup_config` only (close leak) or also `available_level_columns`?

**`validate_setup_config` only, via `build_setup`. Never `available_level_columns`. Factor tokens cannot be `close` (not in `closed_level_token_set`). Residual leak is missing-column silence in `global_cluster`, not a Study path that selects BASE_COLUMNS.**

Evidence:

- `expand._build_setup_for_cell` → `api.build_setup` → `validate_setup_config` (`api.py` L1464–1476).
- `thesistester/study/` has **zero** calls to `available_level_columns`.
- `STUDY_STATIC_LEVEL_NAMES` is session/profile names; MA/prev30m/Pivot tokens are implied by product-merged levels. `close` / `open` / `session` are not in that set → `Unknown core_level token` at validate.
- Locked: `validate_setup_config` rejects `NON_LEVEL_OUTPUT_COLUMNS` (hits) but **not** `BASE_COLUMNS`. A hand-edited `experiment.yaml` `setup.selected_levels: [close]` still passes setup validate; confluence then treats `close` as a level price (`engine/confluence.py` `present_cols` keeps columns that exist).

**Study-specific residual:** `generate_signals` for `global_cluster` does **not** check missing columns (anchor_rules does — `api.py` L1509–1511). `detect_confluence_zones` silently drops absent names (`confluence.py` L83–85: if none present → empty zones). A token that is admitted but not computed (settings-plane mismatch, or typo that still matches a closed token after a future catalog change) yields a **successful 0-trade ok cell**, not a failed cell.

`prev30mVWAP_hit_*` cannot be Study factors (Slice 2 locked; `closed_level_token_set` uses price-stack names only).

### Q8. If Study runs WFA / OTF matrix / Focus, does it inherit Slice 5 honesty bugs or add new ones?

**Study does not run Focus or the OTF validation matrix. It can enable per-cell WFA / Phase 8 / grid via constants and then inherits Slice 5 on those cells. It adds a new honesty bug: ranking / promote stay on in-sample `primary_metric` even when WFA ran.**

| Surface | In Study? | Honesty |
|---|---|---|
| Focus / Admit | No factor, no report path | N/A (dopen example tells operators to use Time Analysis **after** `study run`) |
| `run_otf_validation_matrix` | **Not** called from `run_experiment` | Cannot inherit the train-path OOS leak **through Study** unless a future constant wires it |
| OTF as **factor** | Admission filter on the cell (`setup.otf_filter`) | Slice 4: disabled ≠ passed. Study report OTF Δ is metric(variant) − metric(baseline), multiple-testing caution |
| `walk_forward.enabled: true` | `run_experiment` → `run_walk_forward` | Inherits Slice 5 session folds / `causal_prefix` / overlapping aggregate **sum**. Study index stores `wfa_median_test_expectancy_r` / `wfa_stitched_oos_total_r`. **Crowning ignores them** (Q4) |
| `validation.enabled: true` | Phase 8 `run_validation` on **full-sample** trades | Inherits Slice 5: diagnostic, no `diagnostic_only` flag. Nested R10–R16 only if those mappings are present (`enabled` default-on if the mapping exists) |
| `grid.enabled: true` | In-sample SL/TP sweep | Index stores `best_grid_*`. Ranked metric is still the **base** backtest `trade_summary`, not best-grid expectancy |

Builder battery widgets set `enabled` only (except grid SL/TP lists). `validation: {enabled: true}` with no nested batteries → Phase 8 only. `walk_forward: {enabled: true}` with no fold fields → API WFA defaults (not audited here beyond Slice 5 consume).

Cost hints print when any cell has grid/validation/WFA enabled. That is a runtime warning, not a ranking gate.

### Q9. Promote/rollup: can a promoted cell silently change identity (levels defaults, OTF blob, entry window)?

**Factor tuples and OTF blobs are preserved. Dataset path pinning can retarget bars. Levels stay authored-sparse (product fill at next execute). Name / output_dir / description always change (new `study_identity_hash`). Entry window is copied if present.**

Promote (`promote.build_promoted_draft`):

- Copies source `study` including `levels`, `constants` (backtest, grid, validation, WFA, `entry_window`), `report`
- Replaces `factors` with survivor domains; `stage.mode: explicit_cells` with one cell per ranked survivor (every axis, OTF `normalize_otf_filter_config`)
- Rewrites `name` → `{name}_survivors`, `output_dir` → `results/studies/{name}_survivors`, prepends DRAFT description
- Absolutizes `dataset.path` / `subtimeframe_path` via `_rewrite_dataset_paths_for_draft`

**Search roots for pin:** `cwd`, **source study output dir**, draft parent. **Not** the original StudySpec YAML parent.

**Bad case (path):** CLI `study run examples/studies/pdPOC_….yaml` resolved `examples/studies/data/es_15s.csv`. Written `study.spec.yaml` still has `path: data/es_15s.csv`. Promote finds `cwd/data/es_15s.csv` first (repo Data file) and pins **that**. Re-run of the draft is a different dataset than the cells that were ranked.

**Bad case (levels):** source `levels` omitted `prev30m_vwap_enabled`. Draft copies the omit. Re-expand + `compute_levels` still product-enables prev30m. If `DEFAULT_LEVELS_SETTINGS` later changes, identity hash of the authored spec is unchanged but computed columns change. Hash is of normalized StudySpec bytes, not merged product settings.

**OTF:** factor_map stores canonical OTF; promote writes that blob into `stage.cells` and narrowed `factors.otf`. Re-expand canonicalizes again. No extra alias invent. If the source study had **no** `otf` factor, cells get `{enabled: False}` at expand — draft also has no otf axis.

**Entry window:** copied in `constants` when present (including YAML `null`). Expand passes it into `build_setup` → `normalize_entry_window`. Omitted key → `None` → disabled window (`None` ≡ `{enabled: False}`, Slice 4). Promote does not invent a window.

**Rollup** does not rewrite identity. It composes index + bundle members. Failed rows stay `not_run`.

### Q10. Test gaps vs `STUDY_RUNNER.md`. Goldens ≠ correctness.

**292 passed.** Coverage is strong on schema fail-closed, expand cartesian/stage, ledger resume/lock, PF/WR backfill, ranked/low-N/orphan gates, promote draft shape, rollup compose-only, viewer import allow-list, SIA 15s vs omitted mode, builder first-visit vs `StudyDraft()` legacy.

**Missing vs this slice’s claims:**

| Gap | Severity |
|---|---|
| `study run` vs `thesistester run experiment.yaml` `base_directory` (relative path) | **High** |
| Promote pin prefers cwd file over the file `study run` actually used | **High** |
| Product-default fill when Build Advanced is off / `levels` omits family flags (token set + compute) | **High** |
| `close` as `core_level` rejected only via closed set (no explicit BASE_COLUMNS test) | **Medium** |
| Report MD has no failed-cell section (viewer does) | **Medium** |
| Package `__init__` import of execute when Studies page loads | **Medium** |
| WFA-enabled study still crowns in-sample `expectancy_r` | **Medium** |
| `global_cluster` missing column → empty zones, cell `ok` | **Medium** |
| Ledger `skipped` never produced | **Low** |
| Builder vs API `exposure_policy` default (`single_position` vs `allow_all`) when key omitted | **Low** |
| Goldens / 292 passed ≠ study honesty | **Low** (process) |

Goldens remain identity gates. Passing 292 tests does **not** prove path pinning, product-plane fill, or promote dataset retarget.

---

## 3. Prioritized findings

### Critical

1. **Advertised `experiment.yaml` replay is not the same experiment as `study run` when `dataset.path` is relative.**  
   Expand copies the relative path. `study run` resolves it against the **StudySpec parent**. `thesistester run out/study1/experiment.yaml` resolves it against **output_dir**. AGENT_GUIDE L38–39 and `STUDY_RUNNER.md` RS5 recipe treat replay as the “unchanged R18 path.”  
   `expand.py` L318; `execute.prepare_study_expansion` L523; `cli.main` L251–254.  
   **Bad case:** `examples/studies/pdPOC_ma_confluence_battery.yaml` + `path: data/es_15s.csv` → study uses `examples/studies/data/…`; replay uses `out/pdPOC_stage40/data/…` (missing or a different file).

### High

2. **Promote / launch pin search-roots-then-cwd can silently retarget bars.**  
   Promote roots: cwd, study **output** dir, draft parent — not the original YAML parent. First existing `data/es_15s.csv` wins. Launch uses cwd + store, then cwd fallback.  
   `promote._rewrite_dataset_paths_for_draft`; `launch._pin_dataset_paths`.  
   **Bad case:** ranked cells ran on `examples/studies/data/es_15s.csv`; draft pins repo `data/es_15s.csv`.

3. **Omitted / Advanced-off `study.levels` fills the product plane (families on), not “off.”**  
   Token catalog and `compute_levels` both merge `DEFAULT_LEVELS_SETTINGS`. Build Advanced OFF **pops** prev30m/pivots keys (`15_Studies.py` L1399–1407) so the YAML looks SMA-only; execute still computes prev30m/pivots/APOC/default VWAP/POC windows.  
   Same as a sparse hand-written YAML — the wrong *settings plane* if the operator inferred bare `compute_all_levels`.  
   pdPOC / pRTH examples author the same sparse `levels:` block.

4. **Failed cells are excluded from promote/ranking but under-reported in `study report` MD and over-counted in rollup `cell_count`.**  
   No Failed section in overview MD. Rollup honesty `cells=N` includes failures.

5. **Ranking / promote ignore WFA OOS even when `walk_forward.enabled: true`.**  
   Crown is in-sample `primary_metric`. Inherits Slice 5 “do not treat winner as deployable” and **adds** a study-layer mismatch vs rollup WFA columns.

### Medium

6. **Studies page process-imports `execute` / `rollup` via `thesistester.study.__init__`.**  
   `viewer.py` contract holds. Isolation is module-source, not process. Not a second runner unless called.

7. **`validate_setup_config` only — no `available_level_columns`.**  
   Study factors cannot name `close` today. `global_cluster` missing columns are silent empty zones → `ok` + 0 trades (low-N), not `failed`. Hand-edited `experiment.yaml` can still put `close` in `selected_levels` (locked API leak; Slice 7).

8. **StudySpec dataset validate is not the Slice 1 allow-list.**  
   Unknown keys / `data_artifact_key` pass RS1; expand/`validate_run_spec` is the real gate. Fail is at expand, not load.

9. **Builder vs API backtest defaults.**  
   Build/examples: `exposure_policy: single_position`. Omitted key in a hand YAML: `allow_all`. C7 / Focus later consumers of those trades (if anyone Focuses a bundle) inherit Slice 5 over-state under `single_position`.

10. **OTF Δ and group summaries are descriptive screens** (`min_trades`, multiple-testing). `multiple_testing: error` only suppresses crowning text.

11. **`run_batch` replay is fail-fast and `execution_origin=cli`.** Different ledger/honesty than `study run`.

### Low

12. Ledger `skipped` is specified but never assigned.
13. Report PF/WR bundle fallback is per-field; other KPIs are index-only except soft-resume hollow-row repair.
14. Builder grid `intrabar_model` can stay `sl_first` while backtest is `subtimeframe_conservative` (warn only; SIA parked).
15. Goldens / 292 passed ≠ Study correctness.

---

## 4. Residual risks (not closed here)

- Slice 4 flatten leak and Slice 5 Focus/WFA/OTF-matrix bugs still apply to **per-cell bundles** if an operator opens a zip on classic pages or enables WFA/validation on constants.
- Zero default costs in teaching examples (pdPOC) hide net vs gross; study PF is still net-R.
- `study_identity_hash` is of the **authored** normalized StudySpec, not of merged product levels or resolved CSV bytes. Two specs with different omitted-key fills can hash differently while computing the same columns — or hash the same across a `DEFAULT_LEVELS_SETTINGS` bump if the authored map is unchanged.
- Soft resume trusts an existing zip + ledger `ok` without re-hashing RunSpec vs bundle experiment identity (beyond study identity hash of the spec).
- Assistant `STUDY.run` is a real in-process runner when the flag is on; sandbox is `data_roots`, not “no execute.”
- Slice 7 must not treat `thesistester run experiment.yaml` as study-equivalent without locking `base_directory` and continue-on-failure.

---

## 5. Contracts Slice 7 must treat as **locked**

1. **Study is a composer over `validate_run_spec` + `run_experiment`.** It does not call `run_batch`. Cells continue after failure. `execution_origin="study"`, `cache_policy="read_write"`.
2. **Expand does not invent trigger / confluence_mode / trigger_timeframe.** Omitted OTF → disabled. Batteries emit `{enabled: false}`, never `{}`.
3. **Omitted `study.levels` keys fill the product plane** (`DEFAULT_LEVELS_SETTINGS`) for both token admission and `compute_levels`. Not bare `compute_all_levels`.
4. **Omitted `dataset.ingestion_mode` is `primary`.** Build first-visit / `default_study_draft()` is `15s_primary_derive_1m`. Same 15s bytes without the mode are a different experiment (SIA3 test).
5. **Study setup validate is `validate_setup_config` only.** Factors are gated by `closed_level_token_set` (no `close`). No `available_level_columns` at expand time.
6. **Failed cells:** ledger + index `status=failed`, null PF/WR, no zip; excluded from ranked / promote; included in overview CSV and rollup row count. Soft resume re-runs them.
7. **PF/WR:** index then bundle `trade_summary`; no live recompute. Other crowned KPIs are index (net R). Rollup does not use `pnl_points`.
8. **Promote** writes `explicit_cells` drafts; never executes. Paths may be rewritten (cwd-first). New name/hash. OTF from factor_map is canonical.
9. **Inspect / viewer.py** do not call `run_study` / `rollup_study` / write overview. Peek is not classic session hydrate. Page must not write classic research keys.
10. **Study does not run Focus or `run_otf_validation_matrix`.** WFA/Phase 8/grid only if constants enable them. Ranking stays in-sample `primary_metric`.
11. **Goldens ≠ study correctness.** Do not treat a ranked / promoted cell as a deployable parameter (Slice 5 #12).

---

## 6. Contracts still **open** (do not assume)

1. Whether product will pin `dataset.path` at expand time (absolute, or rewrite `experiment.yaml` for replay).
2. Whether promote/launch will search the **original StudySpec parent** before cwd.
3. Whether Build Advanced OFF will emit explicit `prev30m_vwap_enabled: false` (etc.) instead of omitting keys.
4. Whether `study report` MD will gain a Failed section; whether rollup `cell_count` will be ok-only.
5. Whether ranking will offer / default to a WFA OOS column when WFA ran.
6. Whether package `__init__` will stop importing execute (so Studies process-import isolation matches `viewer.py`).
7. Whether `global_cluster` will fail closed on missing level columns (anchor_rules already does).
8. Full `api.py` / `cli.py` orchestration, `run_batch` abort semantics, and assistant non-STUDY tools — **Slice 7**.

---

## 7. How Slice 7 should start

1. Treat §5 as the StudySpec ↔ RunSpec / failed-cell / PF / isolation / ingest-default contract. Do not re-audit Study expand/report/promote internals except where API/CLI **replay** them.
2. Lock `run_batch` vs `run_study`: fail-fast vs continue; `execution_origin`; `base_directory` for relative paths; index column parity (`R18_INDEX_METRIC_KEYS`).
3. Do not assume `thesistester run <study>/experiment.yaml` equals `study run` of the source YAML.
4. Do not assume `validate_setup_config` rejects `close`; API/CLI can still leak BASE_COLUMNS. Study factors cannot, today.
5. Consume `validation_summary` without a `diagnostic_only` flag. Do not treat study-ranked or CLI-index “best row” as deployable.
6. Goldens still do not prove API/CLI honesty.

---

## 8. How Slice 6 started (traceability)

Read Slice 0 map (Studies = parallel non-mutating surface; `run_experiment` only; viewer must not import execute), Slice 1 ingest tokens + 15s-primary vs omitted `primary`, Slice 2 product vs bare levels + `validate_setup_config` / `available_level_columns`, Slice 5 locked Focus/WFA/KPI/ranking honesty.

Scoped to `thesistester/study/*`; `pages/15_Studies.py`; `examples/studies/`; `tests/study/`; `docs/STUDY_RUNNER.md` + RS/SB/SIA/SV plans + AGENT_GUIDE study sections; `api.build_setup` / `validate_run_spec` / `run_experiment` / `cli.run_batch` **only as called from study execute**.

Did not enter engine fill internals, classic pages 1–14, Data page, assistant (except default-off `STUDY.*`), or persistence hash internals beyond `study_identity_hash` / bundle hash on index rows.
