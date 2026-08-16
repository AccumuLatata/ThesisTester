# Study Viewer — Implementation Plan (SV)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-16  
**Status:** **SV0 plan-locked.** SV1–SV4 not started.  
**Series code:** **SV** (Study Viewer)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** Research Study Runner RS1–RS5 + RS-D7 + RS-D2 + RS-D4 + RS-D8 + RS-D9; Study Builder SB1–SB3; Study Ingest Alignment SIA0–SIA3  
**Related living docs:** `docs/STUDY_RUNNER.md` §SV, `docs/USER_GUIDE.md` (H2 `Studies viewer (read-only)`), `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`  
**Does not reopen:** parked RS-D1 / D3 / D6; RS-D2 inspect path-paste / `write_artifacts=False` / no classic-session mutation; RS-D8 preview; RS-D9 CLI-spawn; SB emit/hydrate; SIA ingest tokens; `engine/`; golden-master regeneration  
**Related but separate:** Research Bundles (`pages/12_Research_Bundles.py`) is upload/import of one zip into classic session. SV must **not** deep-link that page or call `apply_research_bundle_to_session`.

**Completeness posture:** SV1–SV4 is one shippable product update on the **existing** Studies page: an operator can list local study dirs, reopen one later, see failed-cell errors / group summaries / optional rollup files, chart the already-loaded overview frames, and peek one cell’s index + `trade_summary.json` — without a second runner, a new ranker, or classic `st.session_state` mutation. Inspect, Preview, launch, expand, execute, promote, and report stay behavior-identical except for additive Inspect panes and an additive `study list` CLI.

---

## 1. Purpose

RS-D2 shipped a read-only Inspect pane. It still requires the operator to **paste** an `output_dir`. After `study run` / `study report` / optional `study rollup`, success, errors, quality, and factor effects live across `study.ledger.json`, `results_index.csv`, `study.overview.md`, `study.otf_delta.csv`, optional `study.rollup.*`, and per-cell `*.research.zip`. That file hunt is the product gap.

Ship a **Study Viewer** that **projects artifacts the runner already writes**. No second aggregator. No in-process execute. No classic-session hydrate.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Study Viewer (catalog + quality + overview charts + cell peek) |
| Package home | `thesistester/study/viewer.py` (extend; pages import this module directly) |
| UI home | Same `pages/15_Studies.py` **Inspect** tab — no new nav slot |
| CLI | Additive `python -m thesistester study list` (SV1). Existing `expand\|run\|report\|promote\|rollup` argv **unchanged** |
| Load path | Existing `load_study_view` / `report_study(..., write_artifacts=False)` / `load_ledger` |
| Engine / golden impact | **None** |
| Schema / expand / execute / launch / promote / report write | **No behavior edits** |
| Rollup | Display existing `study.rollup.csv` / `.md` only. **Do not** call `rollup_study()` (that helper always writes) |
| Assistant / MCP | Unchanged (`assistant.study_tools` stays default-off; no new `STUDY.*`) |
| Research Bundles / Backtest / Validation | **No** deep-link, `st.switch_page`, or `apply_research_bundle_to_session` |
| Cloud / job queue / store schema | **Non-goals** |
| Series complete when | SV4 acceptance checklist is green (catalog → load → errors/groups/rollup-if-present → charts → cell peek) |

**Feasibility:** High. `StudyViewerModel` already holds ranked / low-N / unresolved / OTF Δ / overview frames. `StudyReportResult.group_summaries` is already computed and unused on the page. Ledger cells already store `error`. Plotly is already a classic-page dependency. Bundle PF/WR already reads `trade_summary.json` behind `_bundle_path_within_study`.

### 2.1 In-scope vs out

| In SV1–SV4 | Explicitly out (entire series) |
|---|---|
| Bounded local catalog under RS-D2 trusted roots | Recursive walk of the whole repo / store |
| Click-to-load into existing Inspect | New sidebar page / numeric slot |
| Additive `study list` | Changing `expand\|run\|report\|promote\|rollup` argv or `run_study` |
| Failed-cell error table + group-summary tables | A second ranker / new primary metrics |
| Read-only rollup **files** if present | Calling `rollup_study()`; auto-`study report` write |
| Plotly from already-loaded frames | Equity / trade charts that unzip every cell |
| One-cell zip peek (`trade_summary.json` + index + ledger error) | Hydrate classic `CLASSIC_RESEARCH_SESSION_KEYS` |
| Download selected `*.research.zip` | Research Bundles deep-link / `apply_research_bundle_to_session` |
| Studies-scoped session keys only | Job queue, kill/retry, auto-refresh, cloud sync |
| Extend USER_GUIDE H2 `Studies viewer (read-only)` | New USER_GUIDE H2 (HC allowlist) |
| | Parked RS-D1 / D3 / D6; SB/SIA behavior edits |
| | `engine/` edits; golden regeneration; `run_batch` semantics |
| | In-process `run_study` / `STUDY.run` |

---

## 3. Why this is not a new research app

| Classic Backtest / Validation / Bundles | Study Viewer (SV) |
|---|---|
| One session run in `st.session_state` | Many cells already on disk |
| Mutates trades / equity / grid keys | Studies-scoped keys only |
| Re-simulates or imports a zip into the session | Reads ledger + overview + optional one zip member |
| Charts one equity curve | Charts the **study** overview (descriptive screen) |
| Research Bundles import restores classic pages | Listing `bundle_path` + optional download; no import |

Reuse: `resolve_study_dir`, `default_study_viewer_roots`, `load_study_view`, `report_study(..., write_artifacts=False)`, `load_ledger`, `_bundle_path_within_study`, `CLASSIC_RESEARCH_SESSION_KEYS` freeze tests.

Do not reuse: `apply_research_bundle_to_session`, Data/Levels/Backtest widget keys, Setup Builder state, Portfolio.

---

## 4. Architecture (locked)

```text
trusted roots (cwd + store)
        |
        +-- discover_study_dirs --> StudyCatalogEntry[]   (SV1; no writes)
        |
output_dir --load_study_view--> StudyViewerModel          (existing; write_artifacts=False)
        |         |
        |         +-- ledger cells.*.error, group_summaries, optional rollup files  (SV2)
        |         +-- Plotly from ranked / overview / group_summaries               (SV3)
        |         +-- selected run_name --> index row + ledger error
        |                                   + optional trade_summary.json peek      (SV4)
        |
        +-- never: run_study, report_study(write=True), rollup_study,
                   apply_research_bundle_to_session, classic session keys
```

| Module | Role | Must not |
|---|---|---|
| `thesistester/study/viewer.py` | Catalog discover, failed-cell table, group-summary display frames, optional rollup-file read, cell-peek helper | Import `execute`, `launch`, `builder`, `promote`, `tools`, `cli_study`, `thesistester.cli`, `run_batch`, Streamlit, Plotly; call `rollup_study`; write overview/rollup |
| `pages/15_Studies.py` | Inspect panes/widgets; Plotly charts (SV3) | Call `run_study`, `rollup_study`, `report_study(..., write_artifacts=True)`, `apply_research_bundle_to_session`, `st.switch_page`; write classic keys |
| `thesistester/study/cli_study.py` | Additive `list` subcommand only (SV1). **May** import `viewer.py` (discover / optional unique-error helper) | Change expand/run/report/promote/rollup flags or execute loop; import Plotly or pages |
| `thesistester/study/report.py` / `ledger.py` / `rollup.py` / `execute.py` / `launch.py` | Unchanged | Any SV edit |
| `thesistester/study/__init__.py` | Optional export of `discover_study_dirs` / catalog types (SV1) | Import Plotly or pages |

`cli_study.py` already imports `execute` / `run_study` / `rollup_study`. If `viewer.py` imported `cli_study`, Inspect would load the execute path and `discover_study_dirs` would cycle. **Allowed direction:** `cli_study` → `viewer`. **Forbidden:** `viewer` → `cli_study` or `thesistester.cli`.

Pages keep importing `thesistester.study.viewer` directly (existing pattern). Package init may export catalog helpers; it must not start importing Plotly.

### 4.1 Recognition rule (locked)

A directory is a **study dir** iff it is a directory and contains a file named `study.spec.yaml`.

- Do **not** require `results_index.csv` (in-flight / ledger-only views stay valid).
- Do **not** require `study.ledger.json`.
- Do **not** treat `tests/fixtures/study/golden/` as a default catalog hit (it is not under the locked search prefixes). Path-paste of a fixture dir under trusted roots remains allowed (existing RS-D2).

### 4.2 Trusted roots (locked)

Same as RS-D2: `default_study_viewer_roots()` → `(Path.cwd().resolve(), get_store_root().resolve())`.

`discover_study_dirs` and click-to-load must call `resolve_study_dir` (or the same root check) before setting `STUDIES_VIEWER_DIR_KEY`. Extra-root paths stay refused.

### 4.3 Scan prefixes (locked)

Do **not** recursively walk cwd or the store. For each trusted root, scan **only** these prefixes, **one directory level** of children:

| Prefix relative to each root | Why |
|---|---|
| `results/studies/` | StudySpec normalize default `output_dir` |
| `out/` | RS5 / USER_GUIDE CLI recipe (`out/pdPOC_stage40`) |

Rules:

1. If the prefix does not exist, skip it (not an error).
2. Each immediate child directory that contains `study.spec.yaml` is a hit.
3. Deduplicate by resolved path (cwd and store may alias).
4. Do **not** scan `tests/`, `.git/`, `.thesistester_store/datasets|levels|signals|setups`, or arbitrary depth.
5. Do **not** add a new store schema (`studies/` under the store) in this series.
6. Last successfully loaded `STUDIES_VIEWER_DIR_KEY` may be **unioned** into the catalog when it still resolves under trusted roots, even if it sits outside the two prefixes (operator-chosen path). **Page-only** — `study list` has no session key.
7. Manual path paste remains. Catalog is a convenience, not the only load path.

`discover_study_dirs(*, roots=None, extra_dirs=())` (names may vary; contract is normative):

- `roots` default `default_study_viewer_roots()`; prefix-scan each per this section.
- `extra_dirs`: each existing directory is included if it is a study dir, else scanned one child level for `study.spec.yaml`.
- Return catalog entries; do not call `report_study`.
- CLI `--root` maps each PATH into `roots` (trusted root) or `extra_dirs` (prefix dir / study dir / other in-root dir) per §4.9. Do not reimplement a second scanner.

### 4.4 `StudyCatalogEntry` (locked fields)

Frozen dataclass (names may vary; fields are normative):

| Field | Type | Source |
|---|---|---|
| `study_dir` | `Path` | Resolved directory |
| `study_name` | `str` | Best-effort from `study.spec.yaml` `study.name`, else directory name |
| `study_identity_hash` | `str \| None` | `study.expansion.json` when readable |
| `run_count` | `int \| None` | Expansion `run_count` when readable |
| `ok` / `failed` / `skipped` / `running` / `pending` | `int` | Ledger status counts when `study.ledger.json` is readable; else `0` |
| `ledger_present` | `bool` | Readable ledger |
| `index_present` | `bool` | `results_index.csv` is a **file** (`Path.is_file()`). Catalog flag only. Inspect load keeps the existing present-path rule (`Path.exists()`): a present non-file path still errors rather than becoming ledger-only |
| `mtime` | `float` | `max` of directory mtime and, when they are files, `study.ledger.json` / `results_index.csv` / `study.expansion.json` / `study.spec.yaml` mtimes (in-flight ledger writes must sort above stale dirs). If a `stat` fails, omit that path and keep the rest |

Corrupt ledger / expansion JSON: skip those fields (name + path still listed). Do **not** fail the whole catalog. Do **not** call `report_study` during discover (that would re-aggregate every study on every rerun).

Sort: `mtime` descending, then `study_name` ascending. Display cap: **50** rows; caption when truncated. Discover itself may return more; the page slices.

### 4.5 Session keys (locked)

Studies-scoped only. Must not collide with existing keys. Must not write `CLASSIC_RESEARCH_SESSION_KEYS`.

| Key | PR | Role |
|---|---|---|
| `studies_viewer_study_dir` | existing | Active Inspect dir (click-to-load **sets this**, then existing Load path) |
| `studies_viewer_path_input` | existing | Path widget; click-to-load updates it **before** the widget instantiates or via the same pending-sync pattern as Build |
| `studies_viewer_cached_model` / `_dir` | existing | Inspect model cache; click-to-load must invalidate when the dir changes (existing `need_reload` already does) |
| `studies_catalog_entries` | SV1 | Cached catalog tuple/list |
| `studies_catalog_roots_key` | SV1 | Cache identity (resolved roots + prefix mtimes or a simple stamp) so Refresh Catalog rescans |
| `studies_viewer_selected_run` | SV4 | Selected `run_name` for cell peek |

Widget keys for catalog/select stay prefixed `_study_viewer_*` or `studies_viewer_*`. Do not invent classic research keys.

Click-to-load sequence (locked):

1. Resolve selected path with `resolve_study_dir(..., roots=default_study_viewer_roots())`.
2. Set `STUDIES_VIEWER_DIR_KEY` and the path-input key to the resolved (or operator-relative) string.
3. Drop `STUDIES_VIEWER_CACHED_MODEL_KEY` so the existing reload path runs `load_study_view`.
4. Do **not** call `run_study` / `report_study` write / `rollup_study`.

### 4.6 Quality / error projection (SV2, locked)

From the **already-loaded** `StudyViewerModel` / ledger / on-disk files:

| Pane | Source | Must not |
|---|---|---|
| Failed cells | Ledger `cells` with `status=failed` → `run_name`, `error` (full text in expander if long) | Invent errors; hide shared ingest faults |
| Group summaries | `model.report.group_summaries` (already computed by `report_study`) | Reimplement `build_group_summaries` |
| Rollup | If `study.rollup.csv` is a file, read it (and show `.md` in an expander). If absent, caption: run CLI `study rollup` | Call `rollup_study()` |
| Launch log | If `study.launch.log` is a file, show the **last 8 KiB** (or the whole file if smaller) in a collapsed expander. Decode UTF-8 with replacement | Treat Streamlit `Ignoring changed path` watcher lines as this log |

Ledger-only views (no index): failed-cell table still renders from the ledger; group summaries / rollup stay empty with the existing “ranked tables empty” honesty.

Reuse the CLI uniqueness idea (unique errors, cap 5) for a **summary caption**. The table still lists **every** failed cell. Implement a **viewer-local** helper, or move `failed_cell_error_lines` into `viewer.py` and have `cli_study` import it. Do not change CLI print text. **Forbidden:** `viewer.py` importing `cli_study.py` / `thesistester.cli` — `cli_study` eagerly imports `execute` / `run_study` / `rollup_study`.

### 4.7 Overview charts (SV3, locked)

Plotly **on the page only** (`pages/15_Studies.py`). `viewer.py` must not import Plotly.

Allowed charts (and no others in this series):

1. **Ranked primary-metric distribution** — histogram or strip of `report.primary_metric` on `ranked` (or `ranked_display` if the metric column is present).
2. **Sample size vs metric** — scatter `trade_count` × `primary_metric` on ranked cells.
3. **Group bars** — one bar chart per `group_summaries` axis using `median_<primary_metric>` (fallback `mean_<primary_metric>` if median column missing).

Rules:

- Empty frame → caption, no placeholder zeros.
- Honesty caption on **every** chart: descriptive screening, not a validated edge; same `min_trades` / multiple-testing caveats as the tables.
- Do not compute new columns (no Sharpe, no pooled PBO, no cross-cell z-scores).
- Do not unzip bundles for charts.
- Do not chart low-N / unresolved as if they were ranked winners. Optional dim/scatter of low-N is **out** (keeps the ranked contract honest).

### 4.8 Cell peek (SV4, locked)

Select a `run_name` present on the loaded overview **or** ledger.

Show:

- Factor tag columns (`factor_*`) when present on the overview row.
- Index KPIs already on the overview row (`status`, `trade_count`, primary metric, `profit_factor`, `win_rate`, `max_drawdown_r`, `bundle_path`, `profit_factor_source`).
- Ledger `error` when the cell failed.
- Optional: `trade_summary.json` from the cell zip **only if** `bundle_path` is a file inside the study dir (`_bundle_path_within_study` / equivalent). Missing member → caption, not an Inspect hard-fail.
- Optional: download button for that zip (bytes from disk), same posture as overview MD download.

Forbidden:

- `apply_research_bundle_to_session`
- Writing `trades` / `equity_curve` / `grid_results` / any `CLASSIC_RESEARCH_SESSION_KEYS`
- `st.switch_page` to Backtest, Validation, or Research Bundles
- Unzipping `trades.parquet` / equity / signals for in-Inspect charts (that is classic import)
- Reading `bundle_path` that escapes the study directory (existing report refuse)

Full trade/equity charts remain: download zip → Research Bundles **upload/import** (operator-driven; no deep-link).

### 4.9 CLI `study list` (SV1, locked)

```bash
python -m thesistester study list [--root PATH] ...
```

| Rule | Behavior |
|---|---|
| Default (`--root` omitted) | `discover_study_dirs` with `default_study_viewer_roots()` and the §4.3 prefix scan |
| `--root` | Repeatable. **Replaces** the default roots (does not union with cwd+store). Each PATH is resolved and must be one of the default trusted roots **or** a path under them. Extra-root refused (same honesty as Inspect). A user-specified PATH that does not exist or is not a directory is an **error** (unlike a missing default prefix, which is skipped) |
| Scan per `--root` PATH | After extra-root validation, include hits as follows (dedupe by resolved path, same §4.4 fields/sort): **(1)** PATH is a default trusted root → §4.3 prefix scan under that root. **(2)** PATH is itself a locked prefix directory (`…/results/studies` or `…/out` under a trusted root) → one level of children that contain `study.spec.yaml`. **(3)** PATH is a study dir (`study.spec.yaml` present) → include PATH itself. **(4)** otherwise (some other existing directory under a trusted root) → one level of children that contain `study.spec.yaml`. Do **not** append `results/studies/` + `out/` under a non-root PATH (that would miss `out/pdPOC_stage40` and empty-scan `out/`) |
| Output | Stable text table: `study_name`, `ok/failed/skipped/running/pending`, `run_count`, `path`. No JSON schema in SV1. Same sort as §4.4. **No 50-row cap** (that cap is page-only) |
| Side effects | None (no ledger write, no report, no lock) |
| Argv | **Additive** `list` subcommand + dispatch branch only. Do not change `expand\|run\|report\|promote\|rollup` flags. The parent `study` help string may mention `list` |
| Implementation | CLI must call the same `discover_study_dirs` (or a thin wrapper that applies the `--root` scan rules above). `cli_study.py` may import `viewer.py`. `viewer.py` must not import `cli_study.py` |

---

## 5. Milestone sequence (locked)

**SV0 → SV1 → SV2 → SV3 → SV4**. Do not reorder without amending this plan. Do not implement SV2–SV4 inside the SV1 PR. Do not implement SV code in SV0.

| ID | Intent | Code? |
|---|---|---|
| **SV0** | Plan lock + docs index / pointers | Docs only (this PR) |
| **SV1** | Catalog + click-to-load + `study list` | `viewer.py`, `cli_study.py` (`list` only), Inspect UI, tests |
| **SV2** | Failed cells + group summaries + optional rollup files + launch-log tail | `viewer.py` + Inspect panes; **no** `rollup.py` write-path change |
| **SV3** | Locked Plotly set on already-loaded frames | `pages/15_Studies.py` only for figures |
| **SV4** | Cell peek + optional zip download | `viewer.py` peek helper + Inspect; no classic hydrate |

---

## 6. Per-milestone contracts

### 6.1 SV0 — Plan lock (this PR)

| | |
|---|---|
| **Scope** | This plan + living-doc pointers. **No** runtime code |
| **Docs** | `docs/README.md` index; `ENGINEERING_ROADMAP.md` status row + SV section; `STUDY_RUNNER.md` §SV (planned operator contract); RS plan follow-on pointer (do not reopen §12.4 behavior); USER_GUIDE H2 short honesty that catalog/charts/peek are **not shipped**; ARCHITECTURE / AGENT_GUIDE / ASSUMPTIONS pointers; SB/SIA related-follow-on one-liners |
| **Help** | **No new H2.** Existing Studies H2 stays current-behavior-honest |
| **Acceptance** | ☑ Plan is implementable without inventing scan roots, write paths, or classic-session hydrate; ☑ Help still describes path-paste Inspect; ☑ RS-D2/D8/D9/SB/SIA contracts not rewritten; ☑ help-corpus / USER_GUIDE structure tests green |

**Copy-ready agent prompt:**

```text
Implement SV0 only from docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md §6.1.
Docs-only plan lock. Do not edit thesistester/ or pages/. Point living docs
at the SV series. USER_GUIDE must not claim catalog/charts/peek as shipped.
No new USER_GUIDE H2. Do not reopen RS-D2/D8/D9 behavior text. §4.2.
```

### 6.2 SV1 — Local study catalog

| | |
|---|---|
| **Depends on** | SV0 |
| **Likely files** | `thesistester/study/viewer.py`; `thesistester/study/cli_study.py` (`list` only); `thesistester/study/__init__.py` (optional export); `pages/15_Studies.py` Inspect; `tests/study/test_study_viewer.py`; extend `test_study_preview.py` session-key allow-list; `tests/study/test_study_execute.py` / CLI tests only if `study list` needs a focused CLI test; docs: `STUDY_RUNNER.md` §SV mark SV1 shipped; USER_GUIDE how-to (catalog + paste still works); ARCHITECTURE session-key sentence; roadmap |
| **Behavior** | `discover_study_dirs` per §4.3–4.4; Inspect shows a catalog table + **Refresh catalog**; row action loads via §4.5; path paste unchanged; `study list` per §4.9 |
| **Out of scope** | Charts, error pane, cell peek, rollup read, `rollup_study`, execute, new store schema |
| **Regression** | Existing `load_study_view` tests unchanged; extra-root still refused; no `report_study` during discover; no classic keys; goldens untouched |
| **Acceptance checklist** | |
| | ☑ Two fixture dirs under `results/studies/` and `out/` are listed; a dir without `study.spec.yaml` is not |
| | ☑ Extra-root path refused for click-to-load and `study list --root` |
| | ☑ `--root` that is a study dir lists that dir; `--root` that is `out/` or `results/studies/` lists one-level children; `--root` that is a trusted root uses §4.3 prefixes; missing `--root` path errors |
| | ☑ Click sets `STUDIES_VIEWER_DIR_KEY` and reuses `load_study_view` (no writes) |
| | ☑ Path paste still loads (catalog empty is not a hard error) |
| | ☑ Corrupt ledger on one dir does not fail the catalog |
| | ☑ Discover does not call `report_study` / `run_study` / `rollup_study` |
| | ☑ `viewer.py` does not import `cli_study` / `thesistester.cli` / `execute` / Plotly / Streamlit |
| | ☑ Page AST: no `run_study(`; no classic key writes; new keys allow-listed |
| | ☑ `expand\|run\|report\|promote\|rollup` argv tests still pass |
| | ☑ USER_GUIDE how-to updated (no new H2); honesty: listing ≠ quality |
| | ☑ Engine goldens untouched; `pytest -q tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SV1 only from docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md §6.2 and §4.1–4.5 / §4.9.
Add discover_study_dirs (one-level results/studies + out under trusted roots) and
Inspect catalog + click-to-load into existing STUDIES_VIEWER_DIR_KEY / load_study_view.
Add additive CLI `study list` with the locked --root scan (study dir / prefix dir /
trusted root). cli_study may import viewer; viewer must not import cli_study,
thesistester.cli, or execute. Do not call report_study during discover. Do not
change expand/run/report/promote/rollup argv. No charts, errors pane, or cell peek.
No classic session keys. No engine/golden edits. Extend USER_GUIDE H2 only. §4.2.
```

### 6.3 SV2 — Quality / errors pane

| | |
|---|---|
| **Depends on** | SV1 |
| **Likely files** | `thesistester/study/viewer.py`; `pages/15_Studies.py`; `tests/study/test_study_viewer.py`; USER_GUIDE / `STUDY_RUNNER.md` / ASSUMPTIONS (rollup-if-present; errors are not a quality score) |
| **Behavior** | §4.6 panes on Inspect after a successful load |
| **Out of scope** | Plotly; cell zip peek; `rollup_study()`; changing `rollup.py` write default |
| **Regression** | `report_study(..., write_artifacts=False)` still does not write; missing rollup is a caption, not an error; CLI `study rollup` still writes |
| **Acceptance checklist** | |
| | ☑ Failed cells from ledger show `error` text; unique-error caption capped |
| | ☑ `group_summaries` tables match `report.group_summaries` (no second aggregator) |
| | ☑ Present `study.rollup.csv` renders; absent → caption pointing at CLI `study rollup` |
| | ☑ Inspect of a completed fixture dir does not create/update `study.overview.*` or `study.rollup.*` |
| | ☑ Launch-log expander tails 8 KiB when the file exists |
| | ☑ Ledger-only view: failed table works; groups/rollup empty |
| | ☑ Docs honesty: counts / rollup ≠ validated edge |
| | ☑ Goldens untouched; study viewer tests green |

**Copy-ready agent prompt:**

```text
Implement SV2 only from docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md §6.3 and §4.6.
Project failed-cell errors, report.group_summaries, and optional study.rollup.*
files on Studies Inspect. Unique-error caption is viewer-local (or move the
helper into viewer.py for cli_study to import). Do not import cli_study from
viewer.py. Do not call rollup_study() or report_study write. Do not add Plotly
or cell zip peek. No engine/golden edits. Extend USER_GUIDE H2. §4.2.
```

### 6.4 SV3 — Overview charts

| | |
|---|---|
| **Depends on** | SV2 |
| **Likely files** | `pages/15_Studies.py` only (figures); tests: page AST import of plotly is allowed **on the page**; viewer.py import-guard must still forbid Plotly; USER_GUIDE + ASSUMPTIONS |
| **Behavior** | §4.7 three chart types from cached `StudyViewerModel` |
| **Out of scope** | New metrics; unzipping bundles; low-N-as-winners charts; Plotly inside `viewer.py` |
| **Acceptance checklist** | |
| | ☑ Ranked-empty → no fake series |
| | ☑ Honesty caption on each chart |
| | ☑ `viewer.py` does not import plotly |
| | ☑ No new aggregations vs `report_study` frames |
| | ☑ Goldens untouched |

**Copy-ready agent prompt:**

```text
Implement SV3 only from docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md §6.4 and §4.7.
Add the three locked Plotly charts on Studies Inspect from the cached viewer
model. Honesty caption required. Do not import plotly in viewer.py. Do not
invent metrics or unzip bundles. No engine/golden edits. Extend USER_GUIDE H2. §4.2.
```

### 6.5 SV4 — Cell peek

| | |
|---|---|
| **Depends on** | SV3 |
| **Likely files** | `thesistester/study/viewer.py` peek helper; `pages/15_Studies.py`; `tests/study/test_study_viewer.py` (sandbox refuse + missing member); USER_GUIDE / ARCHITECTURE / `STUDY_RUNNER.md` |
| **Behavior** | §4.8 |
| **Out of scope** | Classic hydrate; Bundles deep-link; trade/equity Plotly from the zip |
| **Acceptance checklist** | |
| | ☑ Peek shows index + factors + ledger error without opening a zip when there is no bundle |
| | ☑ `trade_summary.json` peek works for an in-dir zip; escaping `bundle_path` refused |
| | ☑ Missing zip member is a caption, not a page crash |
| | ☑ No `apply_research_bundle_to_session` / classic key writes / `st.switch_page` |
| | ☑ Zip download does not write the study dir |
| | ☑ USER_GUIDE: full charts stay Bundles import; no new H2 |
| | ☑ Goldens untouched; series docs mark SV1–SV4 complete |

**Copy-ready agent prompt:**

```text
Implement SV4 only from docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md §6.5 and §4.8.
Add read-only cell peek (index + ledger error + optional trade_summary.json)
with bundle_path sandbox. No apply_research_bundle_to_session, no classic
session keys, no st.switch_page. No engine/golden edits. Extend USER_GUIDE H2. §4.2.
```

---

## 7. End-to-end product acceptance (after SV4)

A researcher who finished `study run` (CLI or Preview **Run via CLI**) can:

1. Open **Studies → Inspect**.
2. See local studies under `results/studies/` and `out/` without remembering the path.
3. Click one → existing Load/Refresh path shows ledger progress + ranked / low-N / unresolved / OTF Δ.
4. Read failed-cell errors and group summaries without opening JSON/MD by hand.
5. If they already ran `study rollup`, see that table; if not, a caption tells them to use the CLI.
6. See the three locked overview charts (screening, not a validated edge).
7. Select a cell → factors + KPIs + error + optional `trade_summary.json`; download the zip if they want classic import.

CLI `study expand|run|report|promote|rollup` remains the academic path. `study list` is discovery only.

---

## 8. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SV0 | Lock |
| `docs/README.md` | SV0 | Index row |
| `docs/ENGINEERING_ROADMAP.md` | SV0 planned; SV4 ✅ | Status table + SV section |
| `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | SV0 | Follow-on pointer; **do not** reopen §12.4 behavior |
| `docs/STUDY_RUNNER.md` | SV0 planned §SV; SV1–SV4 mark shipped | Operator contract |
| `docs/USER_GUIDE.md` H2 `Studies viewer (read-only)` | SV0 honesty (not shipped); SV1–SV4 how-to | **No new H2**. Keep Help chunk lean |
| RQ §7.1.4 / `_USER_GUIDE_SECTIONS` | Only if a new H2 is added | Same PR — **do not** add a new H2 in this series |
| `docs/ARCHITECTURE.md` | SV0 pointer; SV1/SV4 keys | Boundary; Studies-scoped keys |
| `docs/AGENT_GUIDE.md` | SV0 planned; SV4 shipped | Pointer; do not implement SV inside an RS/SB/SIA PR |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SV0 short; SV3 charts | Catalog ≠ quality; charts inherit RS4 ranking honesty |
| SB / SIA plans | SV0 | Related-follow-on one-liner |
| Grok pack | SV4 optional one-liner | Humans may use catalog; coworkers still CLI. Do not rewrite the pack in SV0 |

Help corpus: extending the existing Studies H2 does **not** require an HC allowlist PR.

---

## 9. Test plan (series)

| Layer | Tests | PR |
|---|---|---|
| Discover | `tests/study/test_study_viewer.py` — prefixes, recognition, extra-root, corrupt ledger, no `report_study` call | SV1 |
| Viewer import-guard | AST: `viewer.py` must not import `cli_study`, `thesistester.cli`, `execute`, Plotly, Streamlit | SV1 (keep through SV4) |
| CLI list | Focused argv/output test including `--root` study-dir / prefix-dir / trusted-root / extra-root / missing-path; existing study CLI tests still collect `expand\|run\|…` | SV1 |
| Quality panes | Failed-cell table; group_summaries identity; rollup file present/absent; no writes | SV2 |
| Charts | AST: page may import plotly; `viewer.py` must not; empty ranked → no crash | SV3 |
| Peek | Sandbox refuse; missing member; no classic keys | SV4 |
| Page AST | Extend preview/viewer allow-lists; assert no `run_study(` / `rollup_study(` / `apply_research_bundle_to_session` | SV1–SV4 |
| Goldens | `tests/fixtures/study/golden/*` and `tests/fixtures/golden/*` byte/value-stable | all |
| Help | `tests/test_assistant_user_guide_structure.py` + help corpus — no new H2 | all |
| Suite | `pytest -q tests/study/` per code PR; full suite before SV4 merge | code PRs |

No Streamlit AppTest required if AST + pure helpers cover the contract (same posture as RS-D8/D9). If an AppTest is added, it must not call execute.

---

## 10. Risk register

| Risk | Mitigation |
|---|---|
| Walking the whole repo freezes Streamlit | Locked one-level prefixes only; no `report_study` in discover |
| Catalog implies a quality score | Honesty: listing is discovery; ledger counts are status, not edge |
| Charts become a second ranker | Locked three figures; reuse `report_study` frames only |
| Inspect starts writing artifacts | Forbid `report_study` write, `rollup_study`; tests assert no new files |
| Classic session contamination | Frozen `CLASSIC_RESEARCH_SESSION_KEYS`; no bundle apply |
| Help claims unshipped UI | SV0 USER_GUIDE stays path-paste honest; how-to lands with each code PR |
| `study list` forks discover | CLI calls the same `discover_study_dirs` |
| `viewer.py` imports `cli_study` | Forbidden. `cli_study` eagerly imports execute/rollup. CLI may import viewer |
| `--root` study dir lists nothing | Locked scan: study dir → itself; prefix dir → children; trusted root → prefixes |
| Zip peek becomes a second Bundles page | `trade_summary.json` only; download + manual import for the rest |
| Reopening RS-D2 | SV is a new series; RS §12.4 text stays historical |

---

## 11. Non-goals (series-wide)

- Cloud / multi-user study portfolio (already out of RS-D2).
- Job queue, cancel daemon, auto-refresh, kill/retry.
- In-process `run_study` / `STUDY.run`.
- Promote-from-page.
- New StudySpec keys / factor axes / `schema_version` bump.
- Cross-cell PBO / DSR / CSCV.
- Merging with confluence-combo attribution.
- Store-schema study registry.
- New USER_GUIDE H2 / HC allowlist widen (unless a later amend is explicit).

---

## 12. Regression-safety paragraph (normative)

SV is **additive UI + discover + `study list`**. It must not change simulation, fill, confluence math, `run_batch` abort semantics, StudySpec identity hashes, or golden-master trades/bundles. Inspect remains `report_study(..., write_artifacts=False)`. Discover must not re-aggregate. Rollup display must not write. Classic research `st.session_state` keys stay untouched. Each code PR follows `ENGINEERING_PROPOSAL.md` §4.2: focused tests, goldens preserved, same-PR docs, honesty captions, small surface.
