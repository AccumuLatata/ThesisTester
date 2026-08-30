# Study Observatory — Implementation Plan (SO)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-30  
**Status:** **SO7 shipped (corpus studies pane). SO1–SO4 + SO7 complete. SO5 / SO6 parked.**  
**Series code:** **SO** (Study Observatory)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** RS1–RS5 + RS-D7 + RS-D2 + RS-D4 + RS-D8 + RS-D9; SB1–SB3; SIA0–SIA3; SV0–SV5; SAF1–SAF3; AO1; Program B operator packet (`examples/studies/program_b/`)  
**Related living docs:** `docs/STUDY_RUNNER.md` §SO, `docs/USER_GUIDE.md` (H2 `Studies viewer (read-only)` until SO2; new H2 `Study Observatory` in SO2), `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/PROGRAM_B_OPERATOR_RUNBOOK.md`, `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`  
**Does not reopen:** parked RS-D1 / D3 / D6; SV Inspect / catalog / briefing contracts; SAF draft / promote flags; SB emit/hydrate; SIA ingest tokens; RS execute / ledger / `report_study` write; `engine/`; golden-master regeneration  
**Related but separate:** Studies Inspect (`pages/15_Studies.py`) remains the **one-study microscope**. Portfolio (`pages/13_Portfolio.py`) remains multi-setup **trade** composition. Research Bundles remains zip import into classic session. Classic thesis runs stay out until a later series joins on `dataset_id` / `research_identity`.  
**Related follow-on (do not implement here):** SO5 opt-in watch; SO6 grounded Discuss over the observatory frame. Neither reopens SV Refresh, RQ auditor, or `STUDY.*` tools.

**Completeness posture:** After SO7, an operator can open one Streamlit page, see **every** local catalog dir’s ledger progress (ok / failed / pending / running / skipped) plus every index cell as a typed fact table, filter/sort by instrument, setup kind, n / E / PF / WR, keep incomparable locks out of one rank (cohort lock), apply a Program B lens when that packet is present, save a desk, and drill one **study** or one **cell** into existing Inspect — without a second runner, a new primary metric, classic `st.session_state` mutation, invented cell rows for ledger-only dirs, or writes into `results/studies/`.

---

## 1. Purpose

SV shipped a read-only **single-study** Inspect. Program B (and every later packet) writes many `output_dir`s under `results/studies/`. The operator then file-hunts the 15s packet (23 files) plus parked VA (4), then N overviews. `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md` §12 already named the research gap: cells have n / E / PF; there is **no first-class cross-study map**.

Ship a **Study Observatory**: a corpus-level, program-agnostic investigation surface over artifacts the runner already writes. New studies appear because they are study dirs, not because someone edits a registry. Program B is the first **lens**, not the product identity.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Study Observatory (corpus fact table + facets + cohort lock + lenses) |
| Package home | **New** `thesistester/study/observatory.py` (Streamlit/Plotly-free) |
| UI home | **New** `pages/16_Study_Observatory.py` (SO2). Do **not** grow `pages/15_Studies.py` |
| CLI | Additive `python -m thesistester study observatory` (SO1). Existing `expand\|run\|report\|promote\|rollup\|list` argv **unchanged** |
| Discover | Reuse SV1 `discover_study_dirs` / trusted roots / one-level prefixes. No second scanner |
| Load path | Read `study.spec.yaml` + `study.expansion.json` + `results_index.csv` + ledger counts. **`write_artifacts=False` forever.** Do **not** call `report_study` per study on page load. Do **not** call `rollup_study` |
| Grain | **Cell** (`study_dir` + `run_name`). Study is a grouping dimension |
| Engine / golden impact | **None** |
| Schema / expand / execute / launch / promote / report write | **No behavior edits** |
| Assistant / MCP | Unchanged through SO4. SO6 (parked) must not add `STUDY.*` without a later RS6 amend |
| Research Bundles / classic keys | **No** `apply_research_bundle_to_session`. Drill uses existing Studies session keys only |
| Series complete when | SO4 acceptance is green. SO7 (studies pane) is the first post-SO4 UX amend. SO5 / SO6 stay parked |

**Feasibility:** High. Catalog discovery, index columns (`expectancy_r`, `profit_factor`, `win_rate`, `dataset_id`, `instrument`), expansion factor tags, and Inspect drill keys already exist. Missing piece is a **cached concat + comparability gate + page**, not a new aggregator or ranker.

### 2.1 In-scope vs out

| In SO1–SO4 | Explicitly out (entire series) |
|---|---|
| Typed cell fact table over SV1 catalog hits | Recursive walk of the repo / store |
| Facets + sort on locked columns | New primary metric / composite “edge score” |
| Cohort lock (default on) | Global PF leaderboard across incomparable locks |
| Generic n×E scatter + table (SO2) | Unzip-all-cells equity / trade charts |
| Program B lens when `progB_*` cells exist (SO3) | Hard-coding Observatory as Program-B-only |
| Inspect drill via existing Studies keys | Classic hydrate; Bundles / Portfolio deep-link |
| Saved desks + store sidecar (SO4) | Writes into `results/studies/` or `study.overview.*` |
| Studies pane + ledger strip (SO7) | Inventing cell rows for ledger-only dirs; SO5 watch |
| Additive `study observatory` CLI | Changing `expand\|run\|report\|promote\|rollup\|list` |
| Extend / add USER_GUIDE per §8 | Engine / golden regen / `run_batch` / `STUDY.run` |
| | Job queue, kill/retry, in-process `run_study` |
| | DuckDB, cloud sync, classic thesis-run merge |
| | SO5 watch / SO6 Discuss (parked) |
| | Parked RS-D1 / D3 / D6; SV/SAF/SB/SIA behavior edits |

---

## 3. Why this is not a second Study Viewer

| Studies Inspect (SV) | Study Observatory (SO) |
|---|---|
| One `output_dir` | All catalog study dirs |
| `load_study_view` / `report_study(write=False)` | Concat of index ⟕ expansion; **no** `report_study` loop |
| Briefing / peek / charts for that study | Facets, cohort, scatter, optional lens |
| Catalog = discovery + ledger counts | Catalog is only the **input list** |
| No auto-refresh (locked) | SO2 Refresh explicit; SO5 parked watch does **not** change Inspect |

Reuse: `discover_study_dirs`, `default_study_viewer_roots`, `resolve_study_dir`, `is_study_dir`, `STUDIES_VIEWER_*` drill keys, `CLASSIC_RESEARCH_SESSION_KEYS` freeze tests, index metric names, Program B numeric locks **as a named lens**.

Do not reuse: `apply_research_bundle_to_session`, Data/Levels/Backtest widget keys, Portfolio merge, Inspect Plotly frames as the corpus chart source.

---

## 4. Architecture (locked)

```text
trusted roots (cwd + store)
        |
        +-- discover_study_dirs --> StudyCatalogEntry[]     (SV1; unchanged)
        |
        +-- load_observatory_frame (mtime cache)            (SO1)
        |         |
        |         +-- per study: spec locks + expansion factors
        |         |              + results_index.csv (if file)
        |         |              + ledger counts (corpus strip)
        |         +-- never: report_study, rollup_study, unzip-all
        |
        +-- apply_facets / cohort_lock / sort                (SO1–SO2)
        |
        +-- optional lens: program_b                         (SO3)
        |
        +-- pages/16  (Plotly + widgets)                     (SO2+)
        +-- study observatory CLI                            (SO1)
        +-- click cell --> STUDIES_VIEWER_* + switch_page 15 (SO2)
        |
        +-- never: run_study, report write, rollup_study,
                   apply_research_bundle_to_session, classic keys,
                   writes under results/studies/
```

| Module | Role | Must not |
|---|---|---|
| `thesistester/study/observatory.py` | Discover-driven concat, cache stamp, facets, cohort key, sort allow-list, Program B projection helpers (SO3) | Import `execute`, `launch`, `builder`, `promote`, `tools`, `cli_study`, `thesistester.cli`, `rollup`, Streamlit, Plotly, `pages`; call `report_study` / `rollup_study`; write study dirs |
| `pages/16_Study_Observatory.py` | Facet widgets, scatter, table, lens chrome, Inspect drill | Call `run_study`, `rollup_study`, `report_study(..., write_artifacts=True)`, `apply_research_bundle_to_session`; write classic keys; grow `pages/15_Studies.py` |
| `thesistester/study/cli_study.py` | Additive `observatory` subcommand only. **May** import `observatory.py` | Change `expand\|run\|report\|promote\|rollup\|list` flags; import Plotly or pages |
| `thesistester/study/viewer.py` | Unchanged discover / Inspect load | Import `observatory` (Inspect must not load the corpus compiler) |
| `thesistester/study/report.py` / `ledger.py` / `execute.py` / `rollup.py` | Unchanged write paths | Any SO behavior edit. SO1 may **import** existing read helpers / public names only |
| `thesistester/study/__init__.py` | Optional export of observatory types (SO1) | Import Plotly or pages |
| Store sidecar (SO4) | `{store}/study_observatory/` schema-versioned desks | Write `results/studies/` or rewrite overview/rollup |

**Allowed import direction:** `cli_study` → `observatory` → `viewer` (discover only).  
**Forbidden:** `viewer` → `observatory`; `observatory` → `cli_study` / `execute` / `thesistester.cli`.

Pages import `thesistester.study.observatory` directly (Studies/viewer pattern). Bind session-key **strings** on the page so a stale observatory module cannot `ImportError` the page.

### 4.1 Recognition and roots (locked — SV1)

A directory is a study dir iff it contains `study.spec.yaml` (SV §4.1).

Trusted roots and one-level prefixes stay SV §4.2–4.3: `results/studies/` and `out/` under cwd + store. Extra-root refused. Corrupt spec/index on **one** dir must not fail the corpus (row omitted or study-level error; rest loads).

Do **not** require `results_index.csv` (in-flight studies belong on the corpus strip). Do **not** require Program B names. Do **not** treat `tests/fixtures/study/golden/` as a default hit.

### 4.2 Grain and fact table (locked)

**Grain (two frames, do not mix):** `frame` is one row per **index** cell (`run_name` present). `studies` is one row per catalog dir (ledger counts, `index_present`, `error`). A ledger-only dir appears in `studies` only — do **not** invent a fake cell row in `frame`. Expansion names with no index row stay out of `frame` (they still count as pending on the corpus strip).

SO1 builds a `pandas.DataFrame` with **locked columns** (names normative; extra factor columns allowed when expansion has them):

| Group | Columns | Source |
|---|---|---|
| Identity | `study_dir`, `study_name`, `study_identity_hash`, `run_name`, `bundle_path`, `status` | catalog + index |
| Spec locks | `instrument`, `dataset_id`, `ingestion_mode`, `trigger`, `trigger_timeframe`, `confluence_mode`, `direction`, `tolerance_ticks`, `min_valid_confluences`, `stop_loss_ticks`, `take_profit_ticks`, `commission_per_side`, `slippage_ticks`, `flat_by_session_close`, `exposure_policy`, `min_trades`, `primary_metric` | spec constants / dataset / report + index `dataset_id` / `instrument` |
| Lineage | `lineage_parent`, `lineage_admit_value` | optional `study.lineage` (SAF). `lineage_parent` = basename of `parent_output_dir` (same as SV catalog `parent`); `lineage_admit_value` = `admit.value`. Missing → `—` / null |
| Factors | `factor_core_level`, `factor_partner_levels`, plus any other `factor_*` already flattened by report (`trigger`, `otf`, …) | `study.expansion.json` ⟕ `run_name` |
| Metrics | `trade_count`, `expectancy_r`, `profit_factor`, `win_rate`, `max_drawdown_r`, `total_r` | **index only** |
| Derived (not inference) | `setup_kind`, `sample_class`, `cohort_key`, `lens_hint` | §4.4–4.6 |

**Index-only metrics (locked).** Observatory must **not** unzip `*.research.zip` during corpus load. RS-D7 already writes `profit_factor` / `win_rate` on the index. Null PF/WR stay null (`profit_factor_source` may be `index` or `missing` only — never `bundle` in SO1–SO4). Inspect peek remains the one-cell zip path.

**Forbidden report reuse (locked).** Do **not** call `report_study`, `build_overview_frame`, or `_resolve_bundle_metrics` — those unzip bundles when index PF/WR is missing. Read `results_index.csv` and `study.expansion.json` (`factor_map` keyed by `run_name`) directly. Prefix factor keys `factor_` to match RS4. `format_partner_levels` (public in `report.py`) is allowed so partner strings match Inspect; that helper does not open zips.

**Join.** Same key as RS4: `run_name`. Orphan index rows stay (`factors_joined=False`). Expansion names without an index row are omitted from `frame` (pending on the corpus strip via ledger).

**Sort allow-list (locked):**  
`expectancy_r`, `profit_factor`, `win_rate`, `trade_count`, `max_drawdown_r`, `study_name`, `run_name`, `status`.  
Default sort: `expectancy_r` descending **inside the active cohort** when cohort lock is on; otherwise the same column with a visible incomparability banner. **Never** default-sort `total_r`. `total_r` may appear as a column; it is **not** on the sort allow-list.

### 4.3 Cache (locked)

`load_observatory_frame(*, roots=None, extra_dirs=())` returns a frozen-ish model:

| Field | Meaning |
|---|---|
| `frame` | Cell fact table |
| `studies` | One row per catalog entry: ledger counts, `index_present`, `error` if that dir failed |
| `stamp` | Per-dir mtime tuple of files that exist among `study.spec.yaml`, `study.expansion.json`, `results_index.csv`, `study.ledger.json` |

Rebuild a dir’s slice only when that dir’s stamp changes. Discover stamp (SV `catalog_cache_stamp`) invalidates membership. Page Refresh forces rediscover + reload.

Do not cache in the study dir. Process memory / `st.session_state` only (SO1 CLI is stateless).

### 4.4 `setup_kind` and `sample_class` (locked)

| Column | Rule |
|---|---|
| `setup_kind` | `"{trigger}@{trigger_timeframe}/{confluence_mode}"` from **joined `factor_*` if present, else `study.factors` exclusive values** (not `constants` — trigger lives on factors). Display/facet only |
| `sample_class` | `missing_n` if `trade_count` is null; `below_min_trades` if `trade_count < min_trades` (row’s study `report.min_trades`, default 30); else `interpretable` |

`sample_class` is **not** +E / Hold / Dead. Those names belong to the Program B **desk overlay** (SO3).

### 4.5 Cohort key (locked)

`cohort_key` is a deterministic `|`-joined string of:

```text
instrument|dataset_id|ingestion_mode|commission_per_side|slippage_ticks|stop_loss_ticks|take_profit_ticks|trigger|trigger_timeframe|tolerance_ticks|flat_by_session_close|confluence_mode|min_valid_confluences|exposure_policy
```

`min_valid_confluences` is in the key so Wave 0 point-zone cells (`0`) do not share a ranked sort with pair-box cells (`1`) — same honesty as runbook §5 zone-shape. Missing field → empty token (row still gets a key). When **cohort lock is on** (SO2 default):

1. Facets still apply.
2. Sort / “top cells” / color ranks use only rows sharing the **majority cohort** in the filtered set, **or** the operator-picked cohort (selectbox of keys present after facets). Tie for majority count → lexicographically first `cohort_key` among the tied keys; caption states the pick.
3. Other cohorts remain visible in the table but are excluded from the ranked sort and from the scatter’s “highlight” series unless the operator picks them.
4. Caption states the lock fields.

**Break comparability** is an explicit checkbox (default off). When on: banner required; sort may span keys. This is the only legal global PF/E sort.

Do not invent a numeric “comparability score.”

### 4.6 `lens_hint` (locked)

Best-effort, never a quality score:

| Value | Rule (first match) |
|---|---|
| `program_b` | `study_name` matches `^progB_` |
| `admit_child` | `study.lineage` present with `admit` |
| `generic` | else |

SO3 **attaches** the Program B lens when the filtered frame contains any `program_b` row **or** the operator selects that lens. An empty corpus is generic empty-state, not an error.

Manifests (`examples/studies/program_b/manifest.yaml` **and** `manifest_va.yaml`) are **wave order + expected cell counts** for the lens chrome, not the ingest inventory. 15s wave order lives in `manifest.yaml`; Wave 0 VA + Wave 4 live in `manifest_va.yaml`. Future programs get a new lens module/function in a later amend — they still ingest as `generic`.

### 4.7 Program B lens projection (SO3 only)

Apply only to rows with `lens_hint == program_b` (plus Wave 0 lookup). Numeric locks are the operator runbook — **not** a new StudySpec field:

| Class (`desk_class`) | Rule |
|---|---|
| `failed` | `status == failed` (wins over every class below) |
| `plus_e` | interpretable and `expectancy_r >= 0.03` and `profit_factor > 1.05` |
| `hold` | interpretable and (`abs(expectancy_r) < 0.03` or `profit_factor ∈ [0.95, 1.05]`) and not `plus_e` |
| `dead` | interpretable and `expectancy_r < 0` and not `hold` |
| `other` | interpretable and not `plus_e` / `hold` / `dead` (the runbook gap: e.g. E≥0.03 and PF<0.95) |
| `noisy` | `sample_class == below_min_trades` and `trade_count >= 15` (runbook 15≤n<30) |
| `unidentified` | `sample_class == missing_n` or (`below_min_trades` and `trade_count < 15`) or `status == skipped` |

`plus_e` / `hold` / `dead` / `other` are mutually exclusive on interpretable rows. `failed` is evaluated first.

**ΔE vs Wave 0.** For a pair row (`min_valid_confluences >= 1` and non-empty partners), look up exactly one Wave 0 cell with the same `factor_core_level`:

- `factor_core_level` ∈ `PRIOR_PROFILE_LEVEL_NAMES` (`thesistester.levels.catalog`) → `study_name == "progB_w0_va"`
- else → `study_name == "progB_w0_solo"`

`delta_e = E_pair - E_solo`. **Null** if the solo is missing, either E is null, or the lookup is not exactly one cell (two dirs with the same `study_name` + core → fail closed). Caption **must** say ΔE mixes confirm value with zone-shape (point vs partner box) — runbook §5.

**Thinning.** `n_pair / n_solo` when both `trade_count` present; else null.

**Useful-confluence flag** (boolean projection, not a rank score):  
`sample_class == interpretable` and `delta_e >= 0.03` and PF not in `[0.95, 1.05]` and `thinning` is not null. Keep the predicate in one helper; do not surface a float “usefulness” score. Do not use `~` / `≈` thresholds.

Heatmap: `factor_core_level` × `factor_partner_levels`, color = `desk_class` (not raw E). Missing / pending = grey. Only when the Program B lens is active.

Do **not** write Program B results onto the Program A desk page (docs + UI caption).

### 4.8 Session keys (locked)

Observatory-scoped only. Must not collide. Must not write `CLASSIC_RESEARCH_SESSION_KEYS` except the **existing** Studies drill keys listed below.

| Key | PR | Role |
|---|---|---|
| `observatory_cached_model` | SO2 | Cached frame + studies + stamp |
| `observatory_cache_stamp` | SO2 | Discover + per-dir mtime identity |
| `observatory_facet_state` | SO2 | Widget-backed facet values |
| `observatory_cohort_lock` | SO2 | bool, default `True` |
| `observatory_break_comparability` | SO2 | bool, default `False` |
| `observatory_sort_column` | SO2 | allow-listed name |
| `observatory_selected_run` | SO2 | `(study_dir, run_name)` or empty |
| `observatory_active_lens` | SO3 | `generic` / `program_b` / `auto` |
| `observatory_saved_desk_id` | SO4 | selected desk |
| `observatory_selected_study` | SO7 | selected catalog `study_dir` (study-level drill) |
| `studies_viewer_study_dir` | existing | **Drill only** — same string SV1 sets |
| `studies_viewer_pending_path` | existing | **Drill only** |
| `studies_viewer_cached_model` / `_dir` | existing | Drill **pops** these so Inspect reloads |

Page-local copies of key **names** (Studies pattern). Do not `from-import` names from `observatory.py` onto the page.

`st.switch_page("pages/15_Studies.py")` is **allowed** from Observatory → Inspect. Forbidden: `st.switch_page` to Bundles, Backtest, Portfolio, or Data.

### 4.9 CLI (locked, SO1)

```bash
python -m thesistester study observatory [--root PATH] ... [--csv]
```

| Rule | Behavior |
|---|---|
| Default / `--root` | Same sandbox as `study list` (SV §4.9). Call `discover_study_dirs` + `load_observatory_frame` |
| Default output | Stable text table: `study_name`, `run_name`, `instrument`, `setup_kind`, `trade_count`, `expectancy_r`, `profit_factor`, `status`, `sample_class`. Deterministic sort: `study_name`, `run_name` |
| `--csv` | Same columns to stdout; no extra banner rows |
| Side effects | None |
| Argv | **Additive** subcommand + help mention only |

No JSON schema in SO1. No 50-row cap (page may paginate/display-cap; CLI does not).

### 4.10 Honesty (locked)

On the page (SO2+) and CLI header (one line):

> Descriptive screen of completed study cells. Ranking many cells is multiple-testing, not a validated edge. Sort is within a comparability cohort unless you break the lock. Catalog membership is not a quality score.

Program B lens repeats runbook: n&lt;15 unidentified; 15≤n&lt;30 noisy; +E is not Admit; do not write onto the Program A scalp map.

---

## 5. Milestone sequence (locked)

**SO0 → SO1 → SO2 → SO3 → SO4**. Do not reorder without amending this plan. Do not implement SO2–SO4 inside SO1. Do not implement observatory code in SO0. **SO7** is the first post-SO4 UX amend (studies grain). It does **not** implement parked SO5 / SO6.

| ID | Intent | Code? |
|---|---|---|
| **SO0** | Plan lock + living-doc pointers | Docs only (this PR) |
| **SO1** | Fact table + cache + facets/sort/cohort helpers + `study observatory` | `observatory.py`, `cli_study.py` (`observatory` only), tests |
| **SO2** | Page 16: corpus strip, facets, cohort lock, n×E scatter, table, Inspect drill | `pages/16_Study_Observatory.py` + page tests + USER_GUIDE H2 + HC allowlist |
| **SO3** | Program B lens: `desk_class`, ΔE vs `w0_solo`/`w0_va`, thinning, heatmap, class counts | `observatory.py` + page pane; both manifests are chrome only |
| **SO4** | Saved desks + schema-versioned store sidecar (default unused) | store helper + page load/save |
| **SO5** | Parked — opt-in fragment refresh of **corpus strip only** | — |
| **SO6** | Parked — grounded Discuss over the filtered frame | — |
| **SO7** | Corpus studies pane — ledger strip + catalog-dir table + study-level Inspect drill | `observatory.py` helpers + page 16 |

---

## 6. Per-milestone contracts

### 6.1 SO0 — Plan lock (this PR)

| | |
|---|---|
| **Scope** | This plan + living-doc pointers. **No** runtime code |
| **Docs** | `docs/README.md` index; `ENGINEERING_ROADMAP.md` status row + SO section; `STUDY_RUNNER.md` §SO planned; USER_GUIDE Studies H2 honesty (**not shipped**); ARCHITECTURE / AGENT_GUIDE / ASSUMPTIONS pointers; SV plan + Program B concept / runbook related-follow-on one-liners |
| **Help** | **No new H2.** Do not allowlist `Study Observatory` yet |
| **Acceptance** | ☑ Plan is implementable without a second discover, `report_study` loop, unzip-all, or classic hydrate; ☑ Help still describes Inspect only; ☑ SV/SAF/RS contracts not rewritten; ☑ help-corpus / USER_GUIDE structure tests green |

**Copy-ready agent prompt:**

```text
Implement SO0 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.1.
Docs-only plan lock. Do not edit thesistester/ or pages/. Point living docs
at the SO series. USER_GUIDE must not claim Observatory as shipped.
No new USER_GUIDE H2. Do not reopen SV/SAF/RS behavior text. §4.2.
```

### 6.2 SO1 — Fact table + CLI

| | |
|---|---|
| **Depends on** | SO0 |
| **Likely files** | `thesistester/study/observatory.py` (new); `thesistester/study/cli_study.py` (`observatory` only); optional `thesistester/study/__init__.py` export; `tests/study/test_study_observatory.py` (new); existing study CLI tests only if help/argv collection needs the new subcommand; docs: `STUDY_RUNNER.md` §SO mark SO1; ARCHITECTURE import-graph sentence; roadmap |
| **Behavior** | `load_observatory_frame` per §4.2–4.6; facet predicate + cohort key helpers; `study observatory` per §4.9 |
| **Out of scope** | Streamlit page; Plotly; Program B ΔE/heatmap; store sidecar; unzip; `report_study` / `build_overview_frame` / `_resolve_bundle_metrics` |
| **Regression** | `viewer.py` does not import observatory; extra-root still refused; no writes under fixture study dirs; `expand\|run\|report\|promote\|rollup\|list` argv tests still pass; goldens untouched |
| **Acceptance checklist** | |
| | ☑ Two tmp study dirs (one with index, one ledger-only) concat: cells from the first, corpus row for both |
| | ☑ Dir without `study.spec.yaml` is not ingested |
| | ☑ Extra-root `--root` refused (same honesty as `study list`) |
| | ☑ Corrupt index on one dir does not fail the other |
| | ☑ Load does not call `report_study` / `build_overview_frame` / `_resolve_bundle_metrics` / `run_study` / `rollup_study` / zipfile on bundles |
| | ☑ `observatory.py` AST: no Streamlit, Plotly, `execute`, `cli_study`, `thesistester.cli` |
| | ☑ `viewer.py` AST: still no `observatory` import |
| | ☑ `cohort_key` identical for two cells that share §4.5 fields and differs when instrument **or** `min_valid_confluences` differs |
| | ☑ `sample_class` uses that study’s `min_trades` |
| | ☑ Sort helper refuses `total_r` |
| | ☑ CLI default table + `--csv` deterministic; no file writes |
| | ☑ Engine goldens untouched; `pytest -q tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SO1 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.2
and §4.1–4.6 / §4.9. Add thesistester/study/observatory.py (fact table +
mtime cache + cohort/sample_class/setup_kind). Reuse discover_study_dirs.
Do not call report_study, build_overview_frame, or _resolve_bundle_metrics.
Do not unzip bundles. Additive CLI
`python -m thesistester study observatory` with the same --root sandbox as
study list. cli_study may import observatory; observatory must not import
cli_study / execute / Streamlit / Plotly. viewer.py must not import
observatory. No Streamlit page. No Program B heatmap. No engine/golden
edits. No new USER_GUIDE H2. §4.2.
```

### 6.3 SO2 — Observatory page (generic)

| | |
|---|---|
| **Depends on** | SO1 |
| **Likely files** | `pages/16_Study_Observatory.py` (new); `tests/study/test_study_observatory.py` (page AST); `tests/test_ui_copy_guards.py` / session-key allow-lists if they enumerate pages; `docs/USER_GUIDE.md` **new H2** `Study Observatory`; `thesistester/assistant/help_corpus.py` `_USER_GUIDE_SECTIONS`; `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` §7.1.4; `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` §6.1; ASSUMPTIONS short; ARCHITECTURE page + keys; roadmap |
| **Behavior** | Corpus strip (studies / cells / running / last stamp); facets for instrument, `setup_kind`, `factor_core_level`, `factor_partner_levels`, `study_name`, `status`, `sample_class`, SL/TP, ingest; cohort lock default on; break-comparability default off; n×E scatter (color = `sample_class`; vertical line at the displayed min_trades); filterable table; sort allow-list; **Refresh**; click row → set Studies drill keys, pop Inspect cache, `st.switch_page("pages/15_Studies.py")` |
| **Out of scope** | Program B heatmap / `desk_class` / ΔE (SO3); saved desks (SO4); `st.fragment`; unzip; writing study dirs |
| **Regression** | Inspect / Preview / Build / launch unchanged; no classic keys; no Bundles switch; Help structure tests green **with** the new H2 allowlisted in the **same** PR; goldens untouched |
| **Acceptance checklist** | |
| | ☑ Empty catalog: caption, not crash; paste/list still lives on Studies |
| | ☑ Facet instrument=MNQ hides other instruments |
| | ☑ Cohort lock: two instruments cannot share one ranked sort without break-comparability |
| | ☑ Cohort lock: `min_valid_confluences` 0 vs 1 cannot share one ranked sort |
| | ☑ Break-comparability shows a banner |
| | ☑ Scatter uses `trade_count` × `expectancy_r`; empty metrics → caption |
| | ☑ Drill sets `STUDIES_VIEWER_DIR_KEY` + pending path and invalidates Inspect cache |
| | ☑ Page AST: no `run_study(` / `rollup_study(` / `apply_research_bundle_to_session` / classic key writes |
| | ☑ `observatory.py` still Plotly-free |
| | ☑ USER_GUIDE H2 `Study Observatory` filled (HC §6.2 shape); Studies H2 points here; HC/RQ allowlists updated **together** |
| | ☑ Honesty caption on the page |
| | ☑ Goldens untouched; help-corpus + `tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SO2 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.3
and §4.8 / §4.10. Add pages/16_Study_Observatory.py: corpus strip, facets,
cohort lock (default on), n×E scatter, cell table, Refresh, Inspect drill
via existing STUDIES_VIEWER_* keys + st.switch_page to pages/15_Studies.py.
Do not add Program B heatmap or saved desks. Do not call run_study /
report_study write / rollup_study / apply_research_bundle_to_session.
Do not write classic session keys. Add USER_GUIDE H2 "Study Observatory"
and update HC/RQ §7.1.4 + _USER_GUIDE_SECTIONS in the same PR.
No engine/golden edits. §4.2.
```

### 6.4 SO3 — Program B lens

| | |
|---|---|
| **Depends on** | SO2 |
| **Likely files** | `thesistester/study/observatory.py` (ΔE / `desk_class` / thinning helpers); `pages/16_Study_Observatory.py` (lens chrome + heatmap); `tests/study/test_study_observatory.py`; `tests/study/test_program_b_yaml.py` **untouched**; USER_GUIDE Observatory H2 + ASSUMPTIONS; `LEVEL_COMBINATION_RESEARCH_CONCEPT.md` §12 gap row (pointer only); roadmap |
| **Behavior** | §4.7. Lens control: `auto` (attach if any `progB_` row in **filtered** frame) / `program_b` / `generic`. Heatmap + class-count strip + ΔE / thinning columns when lens is active. Wave 0 lookup: `PRIOR_PROFILE` cores → `progB_w0_va`, else `progB_w0_solo`; not exactly one match → `delta_e` null |
| **Out of scope** | Changing Program B YAMLs / validator / generator; Admit auto-promote; Program A map writes; treating manifest as ingest |
| **Regression** | Generic page still works with zero `progB_*` dirs; Program B validate tests unchanged; no study-dir writes |
| **Acceptance checklist** | |
| | ☑ Fixture: solo ONH E=0.00 + pair ONH+SMA E=0.10 → `delta_e == 0.10`; missing solo → `delta_e` null |
| | ☑ `pdPOC` pair looks up `progB_w0_va`; two `progB_w0_solo` dirs → `delta_e` null |
| | ☑ `desk_class` matches §4.7 on n=30 / n=20 / n=10 / PF=1.0 / E=0.05+PF=0.90 / failed |
| | ☑ Heatmap absent in generic-only corpus |
| | ☑ Caption: ΔE is not a pure confluence effect; +E ≠ Admit |
| | ☑ Manifest is not required for ingest |
| | ☑ Goldens + `test_program_b_yaml` untouched |

**Copy-ready agent prompt:**

```text
Implement SO3 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.4
and §4.7. Add Program B lens projections (desk_class including noisy/other,
delta_e vs Wave 0 via PRIOR_PROFILE → progB_w0_va else progB_w0_solo,
thinning, useful-confluence boolean) and page heatmap/class counts.
Not exactly one Wave 0 match → delta_e null. Lens auto-attaches when
filtered rows include progB_*. Do not edit examples/studies/program_b/
or the validator. Do not auto-promote. No engine/golden edits. Extend
USER_GUIDE Observatory H2. §4.2.
```

### 6.5 SO4 — Saved desks + store sidecar

| | |
|---|---|
| **Depends on** | SO3 |
| **Likely files** | `thesistester/study/observatory.py` or `thesistester/study/observatory_desks.py` (prefer keep desks in `observatory.py` until it splits cleanly); `pages/16_Study_Observatory.py`; tests; ARCHITECTURE store namespace; ASSUMPTIONS (desks are queries, not evidence) |
| **Behavior** | Persist **facet + cohort + lens + sort** (not the fact table) under `get_store_root() / "study_observatory" / "desks"` with `schema_version: 1`. Load/save/delete from the page. Unknown schema → ignore + caption (proposal §4 rule 4). Default: no desks file required. **Never** write `results/studies/` |
| **Out of scope** | Tags/notes on individual cells (later amend); cloud sync; SO5 watch |
| **Acceptance checklist** | |
| | ☑ Save → reload session → same facets/lens/sort |
| | ☑ Sidecar JSON has `schema_version: 1` |
| | ☑ Corrupt / v2 file is ignored, page still loads |
| | ☑ No file created under a study `output_dir` |
| | ☑ Docs: desk ≠ validated edge |
| | ☑ Series docs mark SO1–SO4 complete; SO5/SO6 still parked |

**Copy-ready agent prompt:**

```text
Implement SO4 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.5.
Add schema-versioned saved desks under the ThesisTester store
(study_observatory/desks), not under results/studies/. Persist query state
only. Unknown schema ignored. No watch/Discuss. No engine/golden edits.
Mark SO1–SO4 shipped in living docs. §4.2.
```

### 6.6 SO5 — Parked: opt-in watch

**Intent.** Checkbox default **off**. When on, a `st.fragment` (or equivalent) re-reads **ledger counts / stamp only** every 15s and refreshes the corpus strip. Full fact-table reload only when an index/spec/expansion mtime changes.

**Must not:** change Studies Inspect Refresh; poll `report_study`; unzip; run when the checkbox is off; import `st.fragment` into `observatory.py`.

Do not implement in SO1–SO4.

### 6.7 SO6 — Parked: grounded Discuss

**Intent.** Optional later: Discuss a **filtered observatory frame** with the same fail-closed number auditor as Results QA (cite existing columns/paths only).

**Must not:** add default-on `STUDY.*` tools; invent metrics in prose; treat lens class counts as a validated edge.

Do not implement in SO1–SO4. Requires a later RQ/RI amend if it lands.

### 6.8 SO7 — Corpus studies pane

| | |
|---|---|
| **Depends on** | SO4 |
| **Likely files** | `thesistester/study/observatory.py` (progress / studies-table helpers); `pages/16_Study_Observatory.py`; `tests/study/test_study_observatory.py`; USER_GUIDE Observatory H2; ARCHITECTURE keys; STUDY_RUNNER §SO; roadmap |
| **Behavior** | Surface the existing `studies` grain. Corpus strip adds ledger sums (`ok` / `failed` / `pending` / `skipped`) next to studies / cells / running / last stamp. Studies table: one row per catalog dir; ledger-only dirs included; **no** invented `frame` rows. Sort: parse `error` first, then running / pending / failed desc, then `study_name` / `study_dir`. **Open study in Inspect** sets Studies path keys, pops Inspect cache, **assigns empty** leftover `studies_viewer_selected_run` (do **not** `pop` that widget key — Streamlit can restore a shared `cell_000`), `st.switch_page` to page 15. Cell drill unchanged (still sets run). |
| **Out of scope** | SO5 `st.fragment` watch; SO6 Discuss; new metrics; unzip; writing study dirs; changing `study observatory` CLI columns; saved-desk schema bump |
| **Regression** | Cell grain / cohort lock / lens / desks unchanged; Inspect / Preview / Build / launch unchanged; no classic keys; goldens untouched |
| **Acceptance checklist** | |
| | ☑ Indexed + ledger-only fixture: strip `pending >= 1`; studies table lists both; `frame` still has cells from the indexed dir only |
| | ☑ Corrupt-index sibling sorts before the good dir |
| | ☑ Duplicate `study_name` labels disambiguate with `study_dir` |
| | ☑ Study drill clears leftover selected run (assign empty; do not pop the widget key); cell drill still sets it |
| | ☑ Page AST: `Open study in Inspect`; no `run_study` / `st.fragment` / classic keys |
| | ☑ `observatory.py` still Streamlit/Plotly-free |
| | ☑ USER_GUIDE Observatory H2 extended (same H2; no new heading) |
| | ☑ Goldens untouched; `tests/study/` + help-corpus structure green |

**Copy-ready agent prompt:**

```text
Implement SO7 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.8.
Surface the existing studies grain on pages/16_Study_Observatory.py:
ledger strip (ok/failed/pending/skipped) + catalog-dir table +
Open study in Inspect (path keys + clear leftover selected run;
assign empty, do not pop the widget key).
Do not invent cell rows for ledger-only dirs. Do not implement SO5 watch
or SO6 Discuss. Do not change CLI columns, desk schema, engine, or goldens.
Extend USER_GUIDE Observatory H2 (no new H2). §4.2.
```

---

## 7. End-to-end product acceptance (after SO7)

A researcher running many studies (Program B 15s packet of 23 files, parked VA packet of 4, or any later StudySpecs) can:

1. Open **Study Observatory** while cells are finishing.
2. See corpus progress (ok / failed / running / pending / skipped) and the catalog-dir table without opening one Inspect session per study. Ledger-only dirs stay on the studies pane.
3. Filter by instrument, setup kind, core, partners, n-gate, status.
4. Sort by E / PF / WR / n **inside a comparability cohort** (or explicitly break the lock).
5. Read the n×E scatter (n=30 line) as the primary money plot.
6. If Program B dirs exist, switch on the lens: class counts, ΔE vs Wave 0, core×confirm heatmap.
7. Save the current query as a desk.
8. Click one study or one cell → existing Studies Inspect (briefing / peek) without classic hydrate.
9. CLI `study observatory` prints the **cell** grain for headless / bot logs (not the studies pane).

`study expand|run|report|promote|rollup|list` remain the academic path. Observatory does not execute.

---

## 8. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SO0 | Lock |
| `docs/README.md` | SO0 | Index row |
| `docs/ENGINEERING_ROADMAP.md` | SO0 planned; SO4 ✅; SO7 ✅ | Status table + SO section |
| `docs/STUDY_RUNNER.md` | SO0 §SO planned; SO1–SO4 / SO7 mark shipped | Operator contract |
| `docs/USER_GUIDE.md` H2 `Studies viewer (read-only)` | SO0 honesty (Observatory **not** shipped); SO2 Related pages | Keep Inspect-honest |
| `docs/USER_GUIDE.md` H2 `Study Observatory` | **SO2** | New H2 + HC §6.2 shape |
| RQ §7.1.4 / HC §6.1 / `_USER_GUIDE_SECTIONS` | **SO2 same PR** | Allowlist the new H2; fail-closed if drifted |
| `docs/ARCHITECTURE.md` | SO0 pointer; SO1 import graph; SO2 keys; SO4 store; SO7 study-select key | Boundary |
| `docs/AGENT_GUIDE.md` | SO0 planned; SO4 shipped; SO7 shipped | Do not implement SO inside an RS/SV/SAF PR |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SO0 short; SO2 scatter; SO3 desk_class | Corpus ≠ edge; cohort; ΔE zone-shape |
| `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` | SO0 | Related-follow-on one-liner |
| `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md` §12 | SO0 pointer; SO3 optional “lens shipped” | Spreadsheet remains valid; UI is product |
| `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` | SO0 one-liner | Runbook still CLI; Observatory is readout |
| Grok pack | optional SO2 one-liner | Humans may use the page; coworkers still CLI |

Help: SO0 must **not** add a stub H2. SO2 must not ship the page without the H2 + allowlist.

---

## 9. Test plan (series)

| Layer | Tests | PR |
|---|---|---|
| Fact table | `tests/study/test_study_observatory.py` — prefixes, corrupt dir, no `report_study`, no zip, cohort key, sample_class, sort refuse `total_r` | SO1 |
| Import-guard | AST: `observatory.py` forbids Streamlit/Plotly/execute/cli_study; `viewer.py` forbids observatory | SO1 (keep) |
| CLI | `--root` sandbox + `--csv` + existing study argv still collect | SO1 |
| Page AST | no execute / rollup write / bundle apply / classic keys; Plotly on **page** only | SO2 |
| Help | structure + corpus allowlist includes `Study Observatory` | SO2 |
| Lens | ΔE / desk_class fixtures; generic corpus hides heatmap | SO3 |
| Desks | schema v1 round-trip; corrupt ignored; no study-dir write | SO4 |
| Studies pane | ledger sums; ledger-only listed; error-first sort; no invented cells | SO7 |
| Goldens | `tests/fixtures/study/golden/*` and `tests/fixtures/golden/*` stable | all |
| Program B packet | `tests/study/test_program_b_yaml.py` unchanged | all |
| Suite | `pytest -q tests/study/` per code PR; help tests when USER_GUIDE/HC change | code PRs |

No Streamlit AppTest required if AST + pure helpers cover the contract (RS-D8/D9/SV posture). If an AppTest is added, it must not call execute.

---

## 10. Risk register

| Risk | Mitigation |
|---|---|
| `report_study` × N freezes Streamlit | Forbidden; index+expansion only; mtime cache |
| Unzip-all for PF | Index-only metrics; Inspect peek stays one-cell |
| Global PF leaderboard | Cohort lock default on; banner to break |
| Observatory becomes Program-B-only | Ingest is generic; lens is optional (SO3) |
| Inspect page grows further | New page 16; drill into 15 |
| `viewer.py` imports observatory | Forbidden; Inspect stays lean |
| Help claims unshipped UI | SO0 honesty; H2 only in SO2 with allowlist |
| New H2 breaks HC CI | SO2 updates RQ/HC/`_USER_GUIDE_SECTIONS` together |
| Writes into live results | Tests: no new files under fixture `output_dir` |
| ΔE treated as pure confluence | Locked caption (zone-shape) |
| Reopening SV Refresh | SO2 explicit Refresh only; SO5 parked |
| Classic session contamination | Frozen classic keys; drill uses Studies keys only |
| Second discover implementation | Must call `discover_study_dirs` |

---

## 11. Non-goals (series-wide)

- Cloud / multi-user sync.
- Job queue, cancel, kill/retry, in-process `run_study`.
- New StudySpec keys / factor axes / `schema_version` bump.
- Cross-cell PBO / DSR / CSCV; new ranker.
- DuckDB / parquet warehouse (pandas is enough through ~10⁴ cells).
- Merging classic thesis runs (later series on `dataset_id`).
- Portfolio capital simulation.
- Auto-promote / Admit from a green Observatory cell.
- Writing Program B numbers onto the Program A Notion desk lock.
- Default-on Assistant tools.

---

## 12. Regression-safety paragraph (every code PR)

This series is **read-only over existing study artifacts**. It does not change `simulate_trades`, levels, signals, expand, execute, report writes, or golden fixtures. New behavior is a new module + new page + additive CLI subcommand. Defaults: cohort lock on, break-comparability off, Program B lens auto-only when `progB_*` rows exist. Persisted desks (SO4) are schema-versioned and ignored on drift. SO7 is display-only over the existing `studies` grain. CI: `tests/study/` + help structure when docs/allowlists change; full suite before merge.
