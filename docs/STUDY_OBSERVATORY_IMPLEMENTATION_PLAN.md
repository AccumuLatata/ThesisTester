# Study Observatory — Implementation Plan (SO)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-30  
**Status:** **SO8–SO9 shipped. SO5/SO6 parked.**  
**Series code:** **SO** (Study Observatory)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** RS1–RS5 + RS-D7 + RS-D2 + RS-D4 + RS-D8 + RS-D9; SB1–SB3; SIA0–SIA3; SV0–SV5; SAF1–SAF3; AO1; Program B operator packet (`examples/studies/program_b/`)  
**Related living docs:** `docs/STUDY_RUNNER.md` §SO, `docs/USER_GUIDE.md` (H2 `Studies viewer (read-only)` until SO2; new H2 `Study Observatory` in SO2), `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/PROGRAM_B_OPERATOR_RUNBOOK.md`, `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`  
**Does not reopen:** parked RS-D1 / D3 / D6; SV Inspect / catalog / briefing contracts; SAF draft / promote flags; SB emit/hydrate; SIA ingest tokens; RS execute / ledger / `report_study` write; `engine/`; golden-master regeneration  
**Related but separate:** Studies Inspect (`pages/15_Studies.py`) remains the **one-study microscope**. Portfolio (`pages/13_Portfolio.py`) remains multi-setup **trade** composition. Research Bundles remains zip import into classic session. Classic thesis runs stay out until a later series joins on `dataset_id` / `research_identity`.  
**Related follow-on (do not implement here):** SO5 opt-in watch; SO6 grounded Discuss over the observatory frame. Neither reopens SV Refresh, RQ auditor, or `STUDY.*` tools. **This amend does not unpark SO5 or SO6.**

**Completeness posture:** After SO7, an operator can open one Streamlit page, see **every** local catalog dir’s ledger progress (ok / failed / pending / running / skipped) plus every index cell as a typed fact table, filter/sort by instrument, setup kind, n / E / PF / WR, keep incomparable locks out of one rank (cohort lock), apply a Program B lens when that packet is present, save a desk, and drill one **study** or one **cell** into existing Inspect — without a second runner, a new primary metric, classic `st.session_state` mutation, invented cell rows for ledger-only dirs, or writes into `results/studies/`. After **SO8**, the active-cohort control is readable without changing `cohort_key` or sort. After **SO9**, the Program B lens can keep `desk_class` / `useful_confluence` and focus a heatmap pair through existing core/partner facets. SO5 / SO6 remain parked. SO8–SO9 are **shipped**.

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
| Series complete when | **SO0–SO9** shipped. SO5 / SO6 stay parked |

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
| Cohort literacy (SO8) | Changing `cohort_key` composition or sort; a comparability score |
| Lens as filter (SO9) | Usefulness float; heatmap color = raw E; desk `schema_version` bump |
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
        +-- format_cohort_label / cohort_choice_labels       (SO8; display only)
        |
        +-- optional lens: program_b                         (SO3)
        |         +-- desk_class / useful_confluence facets  (SO9; lens-on only)
        |         +-- heatmap focus → existing core/partner  (SO9)
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
| `_observatory_pending_facets` | SO9 | one-shot dict merged into `observatory_facet_*` before widgets |
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

SO8 labels are display, not a new lock. SO9 lens facets are query state, not Admit and not a rank score.

### 4.11 Cohort literacy (locked — SO8)

The raw `cohort_key` in §4.5 stays the identity used for lock, sort, majority pick, and saved desks. SO8 adds **display** helpers only. It must not change token order, join character, missing-token rule, or `sort_observatory_frame`.

**Parse.** `parse_cohort_key(key) -> dict[str, str]` splits on `|` into `COHORT_FIELDS` order. If the token count ≠ `len(COHORT_FIELDS)`, return `{}` and treat the raw string as the label (fail closed, no crash).

**Short label** (`format_cohort_label(key)`), empty token → `—`:

```text
{instrument} · {dataset_id} · SL{stop_loss_ticks}/TP{take_profit_ticks} · {trigger}@{trigger_timeframe} · min_valid={min_valid_confluences}
```

That short form is **not** the cohort identity. Fields omitted from the short form (ingest, costs, tolerance, flatten, confluence_mode, exposure_policy) still distinguish keys.

**Unique labels** (`cohort_choice_labels(keys) -> list[str]`, parallel to `keys`):

1. Start with `format_cohort_label` for each key.
2. If two or more keys share a short label, append ` · ` plus `{field}={value}` for every §4.5 field that differs **inside that colliding group**, in `COHORT_FIELDS` order.
3. If labels still collide, append ` — {raw_key}`.

Page **Active cohort** selectbox: **value = raw `cohort_key`**; `format_func` uses the unique label. Saved desks still persist the raw key. The cells table keeps the raw `cohort_key` column (do not replace it).

**Differ caption** (`cohort_differ_fields(keys) -> tuple[str, ...]`): §4.5 field names whose parsed values are not identical across `keys`. Empty if fewer than two keys or all keys equal. Caption: `Differing lock fields in this filtered set: {fields}` or `All filtered cells share one cohort key.` Show after facets, including when break-comparability is on.

CLI §4.9 columns stay raw. Do not print labels.

### 4.12 Lens as filter (locked — SO9)

SO3 projections (`desk_class`, `useful_confluence`, heatmap) stay the same predicates. SO9 makes them **queryable**. No usefulness float. Heatmap color stays `desk_class`.

**When.** Extra facets render and apply only while the Program B lens is active (`resolve_program_b_lens` is true). When the lens is off, ignore `desk_class` / `useful_confluence` even if they sit in session state or a loaded desk. Caption if a desk carried them: `Saved lens facets are inert until the Program B lens is on.`

**Facets.** Add to the page (lens-on only) and to `DESK_FACET_COLUMNS`:

| Column | Widget | Empty selection |
|---|---|---|
| `desk_class` | multiselect of values present after generic facets | no filter |
| `useful_confluence` | multiselect of canonical bools present (`True` / `False`) | no filter |

`apply_facets` already matches canonical tokens. Do not add a second predicate engine. Class-count **metrics** stay display (SO3). Do not require clickable `st.metric`.

**Heatmap focus.** A Plotly click is optional chrome only. The **tested** control is a selectbox **Heatmap cell** whose options are `core × partner` tokens from `program_b_heatmap_cells` on the current Program B rows (grey / missing cells may appear; selecting one still writes the two facet keys). Selection writes the existing widgets:

- `observatory_facet_factor_core_level`
- `observatory_facet_factor_partner_levels`

Use the SO4 pending-key pattern (`_observatory_pending_facets`) so writes happen before those multiselects instantiate. Clearing Core / Partner facets clears the focus. Caption: `Heatmap focus writes the Core / Partner facets. Clear those facets to see the full heatmap again.`

Helpers (Streamlit/Plotly-free): `heatmap_focus_label(core, partner) -> str` (partner empty → `(solo)`, same token as SO3 `HEATMAP_SOLO_PARTNER`); `parse_heatmap_focus_label(label) -> tuple[str, str] | None`.

**Desks.** `schema_version` stays **1**. Extend `DESK_FACET_COLUMNS` only. Old v1 files without the new keys load as empty lens facets. Unknown schema / v2 still ignored. Do not persist a separate focus id.

**Must not:** change `desk_class_for` / `useful_confluence_for` / Wave 0 lookup; color the heatmap by raw E; add `STUDY.*` tools; import `st.fragment`.

---

## 5. Milestone sequence (locked)

**SO0 → SO1 → SO2 → SO3 → SO4**. Do not reorder without amending this plan. Do not implement SO2–SO4 inside SO1. Do not implement observatory code in SO0. **SO7** (studies grain) is **shipped**. It does **not** implement parked SO5 / SO6.

**SO8** (cohort literacy) is **shipped**. **SO9** (lens as filter) is **shipped**. Do not implement SO5 or SO6. SO8 does not depend on SO7.

| ID | Intent | Code? |
|---|---|---|
| **SO0** | Plan lock + living-doc pointers | Docs only (historical) |
| **SO1** | Fact table + cache + facets/sort/cohort helpers + `study observatory` | `observatory.py`, `cli_study.py` (`observatory` only), tests |
| **SO2** | Page 16: corpus strip, facets, cohort lock, n×E scatter, table, Inspect drill | `pages/16_Study_Observatory.py` + page tests + USER_GUIDE H2 + HC allowlist |
| **SO3** | Program B lens: `desk_class`, ΔE vs `w0_solo`/`w0_va`, thinning, heatmap, class counts | `observatory.py` + page pane; both manifests are chrome only |
| **SO4** | Saved desks + schema-versioned store sidecar (default unused) | store helper + page load/save |
| **SO5** | Parked — opt-in fragment refresh of **corpus strip only** | — |
| **SO6** | Parked — grounded Discuss over the filtered frame | — |
| **SO7** | Corpus studies pane — ledger strip + catalog-dir table + study-level Inspect drill | `observatory.py` helpers + page 16 |
| **SO8.0** | Plan lock for SO8 / SO9 (this amend) | Docs only |
| **SO8** | Cohort literacy: readable labels + differ caption — **shipped** | `observatory.py` helpers + page 16 `format_func` |
| **SO9** | Lens as filter: `desk_class` / `useful_confluence` + heatmap focus — **shipped** | `observatory.py` helpers + page 16 widgets |

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

Do not implement in SO1–SO4 or SO8–SO9. Do not unpark in this amend.

### 6.7 SO6 — Parked: grounded Discuss

**Intent.** Optional later: Discuss a **filtered observatory frame** with the same fail-closed number auditor as Results QA (cite existing columns/paths only).

**Must not:** add default-on `STUDY.*` tools; invent metrics in prose; treat lens class counts as a validated edge.

Do not implement in SO1–SO4 or SO8–SO9. Requires a later RQ/RI amend if it lands. Do not unpark in this amend.

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

### 6.9 SO8.0 — Plan lock for SO8 / SO9 (this PR)

| | |
|---|---|
| **Scope** | This amend + living-doc **planned** pointers. **No** runtime code |
| **Docs** | This plan §§4.11–4.12 / §6.9–6.11; `ENGINEERING_ROADMAP.md` SO8/SO9 planned rows; `STUDY_RUNNER.md` §SO planned rows; `AGENT_GUIDE.md` do-not-implement-inside-RS; `ARCHITECTURE.md` planned pointer; `ASSUMPTIONS_AND_LIMITATIONS.md` planned honesty; `docs/README.md` index |
| **Help** | **No new H2.** USER_GUIDE must **not** claim cohort labels or lens facets as shipped |
| **Must not** | Edit `thesistester/` or `pages/`; unpark SO5/SO6; implement SO8/SO9 behavior; reopen SV/SAF/RS |
| **Acceptance** | ☑ SO8/SO9 are implementable without `report_study`, unzip, execute, or a desk `schema_version` bump; ☑ SO5/SO6 still parked in every living pointer; ☑ Help still describes the shipped Observatory only; ☑ help-corpus / USER_GUIDE structure tests green |

**Copy-ready agent prompt:**

```text
Implement SO8.0 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.9.
Docs-only plan lock for SO8 (cohort literacy) and SO9 (lens as filter).
Do not edit thesistester/ or pages/. Do not unpark SO5/SO6. USER_GUIDE
must not claim SO8/SO9 as shipped. No new USER_GUIDE H2. §4.2.
```

### 6.10 SO8 — Cohort literacy

| | |
|---|---|
| **Depends on** | SO2 (page + cohort lock). SO4 desks must keep storing the raw `cohort_key`. Does **not** depend on SO7 |
| **Likely files** | `thesistester/study/observatory.py` (`parse_cohort_key`, `format_cohort_label`, `cohort_choice_labels`, `cohort_differ_fields`); `pages/16_Study_Observatory.py` (Active cohort `format_func` + differ caption); `tests/study/test_study_observatory.py`; USER_GUIDE Observatory H2 (same heading); ASSUMPTIONS one sentence; ARCHITECTURE no new live keys; roadmap / STUDY_RUNNER mark SO8 shipped |
| **Behavior** | §4.11. Selectbox **value stays the raw key**. Labels unique under collision rules. Differ caption after facets. Cells table still shows raw `cohort_key`. CLI unchanged. `sort_observatory_frame` / `cohort_key_from_values` / majority-tie lex-first unchanged |
| **Out of scope** | SO9 lens facets / heatmap focus; SO5 `st.fragment`; SO6 Discuss; changing §4.5 field list; replacing the table key column; desk schema bump |
| **Regression** | Two keys that differ only by `min_valid_confluences` still cannot share a ranked sort; labels for those two keys must differ; loading a saved desk still restores the raw key; goldens untouched |
| **Acceptance checklist** | |
| | ☑ `parse_cohort_key` round-trips a well-formed §4.5 key; malformed (`a\|b`) → `{}` and `format_cohort_label` returns the raw string |
| | ☑ Short labels differ when `min_valid_confluences` is 0 vs 1 and all other tokens match |
| | ☑ Two keys that share the short form but differ on `commission_per_side` get unique labels that include `commission_per_side=` |
| | ☑ `cohort_choice_labels` length equals input; order preserved |
| | ☑ `cohort_differ_fields` on one key → `()`; on MNQ vs ES → `("instrument",)` |
| | ☑ Page AST: `format_cohort_label` / `cohort_choice_labels`; Active cohort still binds `observatory_cohort_pick`; no `st.fragment` |
| | ☑ `sort_observatory_frame` tests from SO1 still pass unchanged |
| | ☑ Desk load still applies raw `active_cohort` |
| | ☑ CLI table bytes / columns unchanged |
| | ☑ `observatory.py` still Streamlit/Plotly-free; `viewer.py` still has no observatory import |
| | ☑ USER_GUIDE H2 extended (no new heading); goldens untouched; `tests/study/` + help-corpus structure green |

**Copy-ready agent prompt:**

```text
Implement SO8 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.10
and §4.11. Add parse_cohort_key, format_cohort_label, cohort_choice_labels,
and cohort_differ_fields in observatory.py (Streamlit/Plotly-free).
Page 16: Active cohort format_func uses unique labels; value stays the
raw cohort_key; differ-field caption after facets. Do not change
cohort_key composition, sort_observatory_frame, CLI columns, or desks
schema. Do not implement SO9, SO5, or SO6. Extend USER_GUIDE Observatory
H2 (no new heading). No engine/golden edits. §4.2.
```

### 6.11 SO9 — Lens as filter — **shipped**

| | |
|---|---|
| **Depends on** | SO8 (readable cohort) + SO3 (lens projections) + SO4 (desks) |
| **Likely files** | `thesistester/study/observatory.py` (`DESK_FACET_COLUMNS` + heatmap focus helpers); `pages/16_Study_Observatory.py` (lens-on facets, Heatmap cell selectbox, pending facet merge); `tests/study/test_study_observatory.py`; USER_GUIDE Observatory H2; ASSUMPTIONS; ARCHITECTURE pending-key sentence; roadmap / STUDY_RUNNER mark SO9 shipped |
| **Behavior** | §4.12. When lens is active: `desk_class` + `useful_confluence` multiselects; `apply_facets` on those columns after generic facets. Heatmap cell selectbox writes Core / Partner via `_observatory_pending_facets` (SO4 pending pattern). Generic / auto-off: hide those widgets and do not apply the two lens columns. Desks: `schema_version` remains 1; new facet keys optional |
| **Out of scope** | SO5 watch; SO6 Discuss; usefulness float; heatmap color = raw E; changing `desk_class_for` / `useful_confluence_for` / Wave 0 lookup; clickable `st.metric`; Plotly-only focus without the selectbox; `schema_version: 2` |
| **Regression** | Generic-only corpus still hides heatmap; SO3 ΔE / desk_class fixtures unchanged; old v1 desks without the new keys still load; v2 / corrupt still ignored; goldens + `test_program_b_yaml` untouched |
| **Acceptance checklist** | |
| | ☑ Lens off: `desk_class=plus_e` in session/desk does **not** hide generic rows |
| | ☑ Lens on: `desk_class=["plus_e"]` keeps only plus_e Program B rows; other classes remain in the unfiltered projection used to populate the widget options (options from the pre-lens-facet Program B frame, apply after) |
| | ☑ `useful_confluence=[True]` keeps only useful-confluence rows; `[False]` keeps the complement; empty keeps both |
| | ☑ `heatmap_focus_label("ONH", "")` / empty partners → contains `(solo)`; `parse_heatmap_focus_label` round-trips |
| | ☑ Selecting a heatmap cell sets core + partner facets; clearing those facets restores the wider heatmap |
| | ☑ `DESK_FACET_COLUMNS` includes `desk_class` and `useful_confluence`; saved JSON still `"schema_version": 1` |
| | ☑ Pre-SO9 v1 desk without those keys loads; v2 file still ignored |
| | ☑ Page AST: `Open study in Inspect` not required; `st.fragment` absent; no `run_study` / classic keys; Plotly stays on the page |
| | ☑ `observatory.py` still Streamlit/Plotly-free |
| | ☑ USER_GUIDE H2 extended (no new heading); +E ≠ Admit caption remains |
| | ☑ Goldens + `test_program_b_yaml` untouched; `tests/study/` + help-corpus structure green |

**Widget-option honesty (locked).** `desk_class` / `useful_confluence` **options** come from the Program B rows after **generic** facets (instrument / setup / …), before the lens facets apply — otherwise picking `plus_e` would empty the widget and bounce. Heatmap cell options use that same pre-lens-facet Program B frame (or the post-`desk_class` frame; pick one and test it: **pre-lens-facet** for both, so a class filter does not hide other heatmap pairs from the picker). Cell table / scatter / sort use the fully faceted frame.

**Copy-ready agent prompt:**

```text
Implement SO9 only from docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md §6.11
and §4.12. When the Program B lens is active, facet desk_class and
useful_confluence and add a Heatmap cell selectbox that writes existing
factor_core_level / factor_partner_levels via _observatory_pending_facets.
Extend DESK_FACET_COLUMNS; do not bump schema_version. Do not add a
usefulness float or change desk_class_for / useful_confluence_for.
Generic-only corpus stays heatmap-free. Do not implement SO5/SO6.
Extend USER_GUIDE Observatory H2 (no new heading). No engine/golden
edits. §4.2.
```

---

## 7. End-to-end product acceptance (after SO9)

A researcher running many studies (Program B 15s packet of 23 files, parked VA packet of 4, or any later StudySpecs) can:

1. Open **Study Observatory** while cells are finishing.
2. See corpus progress (ok / failed / running / pending / skipped) and the catalog-dir table without opening one Inspect session per study. Ledger-only dirs stay on the studies pane.
3. Filter by instrument, setup kind, core, partners, n-gate, status.
4. Sort by E / PF / WR / n **inside a comparability cohort** (or explicitly break the lock).
4a. **(SO8)** Read which lock is active without decoding a 15-token `\|` string; see which lock fields differ in the filtered set.
5. Read the n×E scatter (n=30 line) as the primary money plot.
6. If Program B dirs exist, switch on the lens: class counts, ΔE vs Wave 0, core×confirm heatmap.
6a. **(SO9)** Keep `plus_e` / `useful_confluence` and focus one core×partner pair through existing Core / Partner facets.
7. Save the current query as a desk.
8. Click one study or one cell → existing Studies Inspect (briefing / peek) without classic hydrate.
9. CLI `study observatory` prints the **cell** grain for headless / bot logs (not the studies pane).

`study expand|run|report|promote|rollup|list` remain the academic path. Observatory does not execute.

---

## 8. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SO0; SO8.0 amend | Lock + SO8/SO9 contracts |
| `docs/README.md` | SO0; SO8.0 pointer; SO9 shipped | Index row |
| `docs/ENGINEERING_ROADMAP.md` | SO0 planned; SO4 ✅; SO7 ✅; SO8 ✅; SO9 ✅ | Status table + SO section |
| `docs/STUDY_RUNNER.md` | SO0 §SO planned; SO1–SO4 / SO7–SO9 mark shipped | Operator contract |
| `docs/USER_GUIDE.md` H2 `Studies viewer (read-only)` | SO0 honesty (Observatory **not** shipped); SO2 Related pages | Keep Inspect-honest |
| `docs/USER_GUIDE.md` H2 `Study Observatory` | **SO2**; extended in **SO8** and **SO9** (same H2) | New H2 + HC §6.2 shape |
| RQ §7.1.4 / HC §6.1 / `_USER_GUIDE_SECTIONS` | **SO2 same PR** | Allowlist the new H2; fail-closed if drifted |
| `docs/ARCHITECTURE.md` | SO0 pointer; SO1 import graph; SO2 keys; SO4 store; SO7 study-select key; SO8 no new keys; SO9 pending-key | Boundary |
| `docs/AGENT_GUIDE.md` | SO0 planned; SO4 shipped; SO7–SO9 shipped | Do not implement SO inside an RS/SV/SAF PR; do not unpark SO5/SO6 |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SO0 short; SO2 scatter; SO3 desk_class; SO7 studies pane; SO8 labels; SO9 lens facets | Corpus ≠ edge; cohort; ΔE zone-shape; labels ≠ new lock; lens facets ≠ Admit |
| `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` | SO0 | Related-follow-on one-liner |
| `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md` §12 | SO0 pointer; SO3 optional “lens shipped” | Spreadsheet remains valid; UI is product |
| `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` | SO0 one-liner | Runbook still CLI; Observatory is readout |
| Grok pack | optional SO2 one-liner | Humans may use the page; coworkers still CLI |

Help: SO0 must **not** add a stub H2. SO2 must not ship the page without the H2 + allowlist. SO8.0 must **not** claim cohort labels or lens facets as shipped. SO8/SO9 extend the same H2 in their code PRs.

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
| Cohort labels | parse fail-closed; unique labels; differ fields; sort/CLI unchanged | SO8 |
| Lens facets | lens-off ignores desk_class; useful_confluence True/False; heatmap focus writes core/partner; schema stays v1 | SO9 |
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
| Reopening SV Refresh | SO2 explicit Refresh only; SO5 parked (not SO8/SO9) |
| Classic session contamination | Frozen classic keys; drill uses Studies keys only |
| Second discover implementation | Must call `discover_study_dirs` |
| Unreadable cohort → break lock | SO8 labels + differ caption; raw key remains identity |
| Short-label collision | `cohort_choice_labels` appends differing fields, then raw key |
| Lens filter treated as Admit | Existing +E ≠ Admit caption; no usefulness float |
| Desk schema bump breaks old files | SO9 extends `DESK_FACET_COLUMNS` only; `schema_version` stays 1 |
| Plotly click-only focus | Selectbox is the tested path; click is optional chrome |
| Unparking SO5/SO6 by accident | Explicit out in SO8.0 / SO8 / SO9; no `st.fragment`; no Discuss |

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
- Unparking SO5 watch or SO6 Discuss.
- Changing `cohort_key` composition or adding a comparability score.
- A float “usefulness” score; heatmap color = raw E.
- Saved-desk `schema_version` bump.

---

## 12. Regression-safety paragraph (every code PR)

This series is **read-only over existing study artifacts**. It does not change `simulate_trades`, levels, signals, expand, execute, report writes, or golden fixtures. New behavior is a new module + new page + additive CLI subcommand. Defaults: cohort lock on, break-comparability off, Program B lens auto-only when `progB_*` rows exist. Persisted desks (SO4) are schema-versioned and ignored on drift. SO7 is display-only over the existing `studies` grain. SO8 is display-only over the existing `cohort_key`. SO9 is query-only over existing lens columns and does not bump desk `schema_version`. SO5 / SO6 stay parked. CI: `tests/study/` + help structure when docs/allowlists change; full suite before merge.
