# Study Admit Follow-up — Implementation Plan (SAF)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-18  
**Status:** **SAF0 this PR (plan lock). SAF1–SAF3 not started. SAF4 parked.**  
**Series code:** **SAF** (Study Admit Follow-up)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** RS1–RS5 + RS-D7 + RS-D8 + RS-D9; SB1–SB3; SIA0–SIA3; SV0–SV5 (briefing / per-cell NY ToD); SW C1–C9 (`entry_window_from_bucket`, Admit)  
**Related living docs:** `docs/STUDY_RUNNER.md` §SAF, `docs/USER_GUIDE.md` (H2 `Research Study Runner (headless)`, `Studies viewer (read-only)`, `Focus vs Admit`), `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md`  
**Does not reopen:** parked RS-D1 / D3 / D6; RS3 execute / ledger / lock; RS-D9 spawn flags; SV briefing ranker; SB emit defaults; SIA ingest tokens; SW Focus UI; `engine/`; golden-master regeneration  
**Related but separate:** Classic Time Analysis **Promote to Admit** (`pages/9_Time_Analysis.py`) remains the one-setup Focus→Admit loop. SAF drafts a **child StudySpec** from a completed study. Do not clone the Time Analysis page or write classic `st.session_state` Admit widgets.

**Completeness posture:** After SAF3, an operator can take a finished all-day study, draft a **linked child** that re-sims the winning cell with Admit locked to the briefing (or hour/30m) bucket, preview that YAML, and launch it with the **existing** CLI / RS-D9 spawn. Promote without the new flags stays byte-identical to RS5. Execute, expand cartesian, and `run_experiment` stay behavior-identical except they consume an already-valid `backtest.entry_window` the draft now emits.

---

## 1. Purpose

SV5 names the strongest NY `entry_rth_segment` on the crowned cell. That is **Focus-family** (post-hoc grouping of completed trades). It does not re-simulate.

The operator next step is already specified (SW + USER_GUIDE Focus vs Admit): lock **Admit** `entry_window` and re-run. Today that is hand YAML / classic Promote. Two defects:

1. **Wrong stamp risk.** Briefing copy says `constants.entry_window`. Expand puts that on **setup**. `run_backtest` / `run_grid` read **`backtest.entry_window` / `grid.entry_window`**. A setup-only stamp does not constrain the engine.
2. **No parent link.** A second `output_dir` has no machine-readable pointer to the screen that selected the cell and bucket.

SAF automates the **draft** (and Inspect → Preview handoff). It does **not** auto-`study run`. Time-of-day stays off the factor cartesian.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Study Admit Follow-up |
| What changes | Additive `study promote` flags; optional fail-closed `study.lineage`; Inspect button writes Preview YAML |
| What executes | Unchanged: human `study run` / existing RS-D9 spawn on the **child** |
| Engine / golden impact | **None**. Window is existing SW Admit on the emitted RunSpec |
| `schema_version` | Stays `1`. Optional `study.lineage` (omit = valid). No new factor axes |
| Default `study promote` | **Identical** to RS5 (no lineage, no window) when `--admit-tod` is omitted |
| Child `output_dir` | Always **new** (`results/studies/<name>_admit_<bucket>`). Never the parent dir |
| Auto-run | **Forbidden** (RS5 hard stop) |
| Series complete when | SAF3 acceptance is green. SAF4 (one-click child launch) stays parked |

**Feasibility:** High. `promote_study` already writes `explicit_cells` drafts and never executes. `extract_cell_time_of_day` / `_best_tod_bucket` already pick the NY segment from `trades.parquet`. `entry_window_from_bucket` already maps a bucket to a normalized Admit window. `run_experiment` already applies `backtest.entry_window` when `enabled: true`.

### 2.1 In-scope vs out

| In SAF1–SAF3 | Explicitly out (entire series) |
|---|---|
| `--admit-tod auto` on existing `study promote` | Auto-`study run` / in-process `run_study` |
| Stamp Admit on `constants.backtest.entry_window` **and** `constants.grid.entry_window` when grid is present | Adding ToD / RTH as a factor axis |
| Optional `study.lineage` (closed keys) | Reusing the parent `output_dir` / `--force` on the parent |
| Inspect **Draft Admit follow-up** → Preview textarea | Classic session hydrate / Time Analysis widget writes |
| `--tod-group` hour / 30min + `--allow-thin` (SAF3) | Sweeping many buckets as a cartesian |
| Catalog parent path column from `lineage` (SAF3) | New sidebar page / job queue / kill |
| | Enabling `validation` / `walk_forward` on the child |
| | `engine/` / golden regen / `run_batch` |
| | `STUDY.promote` argv change unless a later RS6 PR (out) |
| | SAF4 one-click child launch (parked) |

---

## 3. Problem (locked evidence)

### 3.1 Engine Admit path (do not change)

`thesistester/api.py` `run_backtest` / `run_grid` call `normalize_entry_window(settings.get("entry_window"))` on the **backtest / grid** mapping. Disabled / missing → legacy all-day (`simulate_entry_window is None`).

`thesistester/study/expand.py` copies `constants.entry_window` onto **setup** only. `constants.backtest` is copied onto the run’s `backtest` as-is. Therefore a follow-up draft **must** set `study.constants.backtest.entry_window.enabled: true` (and the same window on `grid` when that mapping exists). Stamping setup/`constants.entry_window` alone is **not** sufficient.

WFA, when enabled, merges `backtest_config` (including `entry_window`) into execution. SAF must **not** flip `walk_forward.enabled` to true.

### 3.2 Honesty (Focus ≠ Admit)

| Surface | Meaning |
|---|---|
| SV5 briefing / `entry_rth_segment` table | Post-hoc grouping of **already completed** all-day trades |
| Hour / 30min buckets | Same trades; full NY clock (CME session) at finer grain |
| Admit follow-up `study run` | **Re-sim**: off-window candidates get `outside_entry_window` before exposure |

Child KPIs will not match the briefing row under `single_position` / cooldown. Caption must say so.

### 3.3 Why not a factor axis

A 7-segment (or 23-hour) cartesian multiplies cells and overfits. RS5 + SV5 already locked: ToD is post-run. SAF keeps that lock.

---

## 4. Architecture (locked)

```text
parent output_dir (completed study)
        |
        +-- study.spec.yaml / expansion / ranked overview / cell zip
        |
        +-- promote_study(..., admit_tod="auto")     # SAF1; never execute
                |
                +-- select 1 ranked cell (top-1 or --admit-run-name)
                +-- extract_cell_time_of_day / grouped summarize
                +-- entry_window_from_bucket(...)
                +-- stamp backtest + grid windows
                +-- study.lineage { parent_*, admit }
                +-- new output_dir + new study.name
                +-- validate_study_spec  -->  draft YAML
        |
        +-- SAF2: page writes draft YAML onto Preview (existing textarea)
        +-- human: Validate / Preview --> existing Run via CLI (child dir)
        |
        +-- never: run_study from promote; write parent ledger; mutate parent spec
```

| Module | Role | Must not |
|---|---|---|
| `thesistester/study/admit_followup.py` | **New.** Select bucket, build window, stamp constants, build/validate `lineage` | Import `execute`, `launch`, `viewer`, `cli_study`, `thesistester.cli`, Streamlit, pages, `run_batch` |
| `thesistester/study/promote.py` | Call admit helper only when flags set; default path unchanged | Execute; write parent artifacts; import viewer / launch / execute |
| `thesistester/study/schema.py` | Allow optional `study.lineage` with a closed key set | Treat omitted lineage as an error; invent factor axes |
| `thesistester/study/builder.py` | Hydrate/emit `lineage` if present (SAF1 or SAF2). Default drafts omit it | Default `emit` a lineage or Admit window |
| `thesistester/study/briefing.py` | Reuse extract / best-bucket. SAF3 may add a `group_col` argument with default `entry_rth_segment` | Change briefing headline metric; import promote |
| `thesistester/study/cli_study.py` | Additive promote flags only | Change expand/run/report/rollup/list argv |
| `thesistester/study/viewer.py` | SAF3: optional catalog `parent` from spec `lineage` (read YAML only) | Import promote / admit_followup / execute / cli_study |
| `pages/15_Studies.py` | SAF2: Inspect button → emit YAML to Preview keys | `run_study(`; classic key writes; `st.switch_page` |
| `thesistester/entry_window_policy.py` | Unchanged consumer (`entry_window_from_bucket`) | Edits in this series unless a test proves a missing mapping (then a dedicated SW follow-up, not SAF) |
| `execute.py` / `expand.py` / `engine/` | Unchanged | Any SAF edit |

**Allowed import direction:** `promote` → `admit_followup` → `briefing` / `entry_window_policy` / `schema`.  
**Forbidden:** `briefing` → `promote`; `viewer` → `promote` / `admit_followup`; `admit_followup` → `execute` / `viewer`.

Pages may import `admit_followup` / `promote_study` (same pattern as `builder` / `launch`). They must not import `execute`.

### 4.1 CLI (locked)

Existing:

```bash
python -m thesistester study promote <study_dir> --output drafts/x.yaml [--top-n N] [--metric M] [--force]
```

Additive (omit = today’s promote):

| Flag | PR | Default | Behavior |
|---|---|---|---|
| `--admit-tod {auto}` | SAF1 | unset | Build one-cell Admit child. `store_const` / optional flag — **absence** keeps RS5 |
| `--admit-run-name NAME` | SAF1 | unset | Ranked `run_name` to constrain. Default = first ranked row (top-1) |
| `--tod-group {entry_rth_segment,entry_hour_bucket,entry_30min_bucket}` | SAF3 | `entry_rth_segment` | Only legal with `--admit-tod`. SAF1 hard-codes RTH segment |
| `--allow-thin` | SAF3 | off | Permit `sample_warning` / N < `report.min_trades`. SAF1 refuses thin |

Rules:

1. `--admit-tod` without a completed ranked cell + readable in-dir zip → `StudyPromoteError` (no write).
2. `--admit-tod` with `--top-n` ≠ 1 and no `--admit-run-name` → refuse (one cell per draft).
3. `--admit-run-name` must be ranked-eligible (existing promote honesty: no low-N promote).
4. Selected cell `bundle_path` must resolve inside the parent dir (`_bundle_path_within_study` / `resolve_cell_bundle`).
5. Best-bucket selection: same sort as `_best_tod_bucket` (`avg_r` desc, label asc). Prefer non-`sample_warning` rows. If the remaining top two `avg_r` values are equal → refuse (tie).
6. Thin: if the chosen bucket is `sample_warning` or `trade_count < study.report.min_trades` → refuse unless `--allow-thin` (SAF3).
7. `--tod-group` / `--allow-thin` without `--admit-tod` → refuse.
8. `--force` still only overwrites the **draft file**, not the parent study.
9. `--output` required (unchanged). Suggested child name is in the YAML `study.name` / `output_dir`, not forced as the `--output` path.

Help string: mention the new flags. Do not change expand/run/report/rollup/list.

### 4.2 Window stamp (locked)

Reuse `entry_window_from_bucket(group_col, value, exchange_tz=...)`.

Instrument exchange TZ from `study.dataset.instrument` via existing instrument table (MNQ/ES → `America/New_York`). Do not invent a second clock.

After `build_promoted_draft` (or inside a post-pass that still `validate_study_spec`s):

1. Deep-copy the normalized window dict (`enabled: true`).
2. Set `study.constants.entry_window` (setup stamp; expand already copies this to setup).
3. Set `study.constants.backtest.entry_window` to the **same** mapping. `backtest` is already required for expand.
4. If `study.constants.grid` is a mapping, set `grid.entry_window` to the same mapping. Do **not** flip `grid.enabled`.
5. Do not add `entry_window` onto `validation` / `walk_forward`. Do not set those `enabled: true`.
6. Do not change `workers`, dataset, ingest, or factor domains except the existing explicit_cells narrow.

Child identity:

| Field | Rule |
|---|---|
| `study.name` | `^[A-Za-z0-9][A-Za-z0-9_-]*$`. `{parent_name}_admit_{slug}` where slug is the bucket label with `:` → `` (e.g. `rth_open_30m`, `0930`) |
| `study.output_dir` | `results/studies/{study.name}` — never the parent path |
| `study.description` | Existing DRAFT promote sentence **plus** Admit / lineage one-liner (constrained re-sim, not a new screen) |

`schema_version` stays `1`.

### 4.3 `study.lineage` (locked)

Optional mapping. **Omitted on all current YAML and on default promote.** Unknown keys fail closed (`StudySpecError`).

```text
study.lineage:
  parent_output_dir: str          # resolved posix path of the parent study dir
  parent_identity_hash: str       # parent expansion identity (study.expansion.json / expand hash)
  parent_run_name: str            # constrained cell
  admit:
    group: entry_rth_segment | entry_hour_bucket | entry_30min_bucket
    value: str                    # e.g. rth_open_30m or 09:30
    rule: briefing_best_avg_r | explicit
    min_trades: int               # report.min_trades used at draft time
    thin: bool                    # true only when --allow-thin accepted a thin bucket
```

| Rule | Behavior |
|---|---|
| Normalize | If `lineage` absent → leave absent (do not emit empty `{}`) |
| Validate | All listed keys required when `lineage` is present. `admit.group` ∈ the three labels. `admit.rule` ∈ `{briefing_best_avg_r, explicit}`. `min_trades` ≥ 1. `thin` is bool |
| Identity hash | Lineage **is** part of `study_identity_hash` (whole normalized spec). Default promote omits it → hashes unchanged |
| Builder | Hydrate if key present. `default_study_draft()` / Start-from-example **omit** lineage |
| Runtime | Execute ignores lineage (comments / Inspect only). Do not enforce parent still exists at `study run` |

`rule: explicit` is reserved for a later `--admit-bucket VALUE` if needed. SAF1–SAF3 only emit `briefing_best_avg_r`.

### 4.4 Inspect button (SAF2, locked)

On a **loaded** Inspect model with a briefing that has a crowned cell + ToD segment:

- Button: **Draft Admit follow-up**.
- Calls the same helper as CLI `--admit-tod auto` (default group = `entry_rth_segment`, no `--allow-thin`).
- Writes YAML into the existing Preview textarea key (`studies_preview_yaml` / equivalent) and clears launch-confirm / preview cache the same way **Apply to Preview** does.
- Does **not** spawn CLI. Does **not** write `drafts/` unless we also offer an optional download (not required).
- Refuse (caption, no write): parent in-flight (`running`/`pending` on the selected cell), missing zip, thin bucket, tie, extra-root, no ranked row.
- Studies-scoped keys only. Suggested additive: `studies_admit_followup_error` (string) for the refuse caption. Allow-list in page AST tests.
- Honesty caption on the button: draft only; child is constrained re-sim; not a validated edge.

Do not put this button on Build. Do not call `run_study`.

### 4.5 Catalog parent column (SAF3, locked)

Best-effort: if `study.spec.yaml` has `study.lineage.parent_output_dir`, show a `parent` column (basename or relative-to-cwd). Corrupt / missing lineage → `—`. Do **not** call `report_study` or `promote` during discover. Read spec YAML with the same best-effort posture as `study_name` (corrupt spec already must not fail the catalog).

`study list` text table may add a `parent` column (additive). Existing columns stay. Tests that parse the table must be updated in the same PR.

### 4.6 Session keys (locked)

| Key | PR | Role |
|---|---|---|
| `studies_admit_followup_error` | SAF2 | Last refuse caption (optional) |

No classic keys. No new launch keys. Preview / launch keys stay owned by RS-D8/D9.

---

## 5. Milestone sequence (locked)

**SAF0 → SAF1 → SAF2 → SAF3**. Do not reorder. Do not implement SAF2–SAF3 inside SAF1. SAF4 is parked.

| ID | Intent | Code? |
|---|---|---|
| **SAF0** | Plan lock + living-doc pointers | Docs only (this PR) |
| **SAF1** | CLI `--admit-tod auto` + lineage + engine-correct window stamp | `admit_followup.py`, `promote.py`, `schema.py`, CLI flags, tests |
| **SAF2** | Inspect **Draft Admit follow-up** → Preview | `pages/15_Studies.py` + helper; no spawn |
| **SAF3** | `--tod-group` / `--allow-thin` + catalog `parent` | CLI + briefing group_col + viewer catalog field |
| **SAF4** | Parked: one-click **Confirm and run** on the child (RS-D9 bind on child hash) | Do not implement |

---

## 6. Per-milestone contracts

### 6.1 SAF0 — Plan lock (this PR)

| | |
|---|---|
| **Scope** | This plan + living-doc pointers. **No** runtime code |
| **Docs** | `docs/README.md` index; `ENGINEERING_ROADMAP.md` status row + SAF section; `STUDY_RUNNER.md` §SAF planned; RS/SV/SB/SIA follow-on one-liners (do not reopen their execute/inspect contracts); USER_GUIDE short honesty that the draft button / `--admit-tod` are **not shipped**; ARCHITECTURE / AGENT_GUIDE / ASSUMPTIONS pointers |
| **Help** | **No new H2.** Extend existing Studies / Study Runner / Focus vs Admit H2s only if a sentence is required for honesty. Keep chunks lean |
| **Acceptance** | ☑ Plan is implementable without engine edits or auto-run; ☑ default promote remains the RS5 contract; ☑ Help does not claim the follow-up button; ☑ help-corpus / USER_GUIDE structure tests green |

**Copy-ready agent prompt:**

```text
Implement SAF0 only from docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md §6.1.
Docs-only plan lock. Do not edit thesistester/ or pages/. Point living docs
at the SAF series. USER_GUIDE must not claim --admit-tod or the Inspect
draft button as shipped. No new USER_GUIDE H2. Do not reopen RS5/SV5/SW
behavior text. ENGINEERING_PROPOSAL.md §4.2.
```

### 6.2 SAF1 — CLI Admit draft

| | |
|---|---|
| **Depends on** | SAF0 |
| **Likely files** | `thesistester/study/admit_followup.py` (new); `promote.py`; `schema.py`; `cli_study.py` (promote flags only); optional `builder.py` hydrate of `lineage`; `tests/study/test_study_promote.py` + new `test_study_admit_followup.py`; `tests/study/test_study_schema.py`; docs: `STUDY_RUNNER.md` §SAF mark SAF1 CLI shipped; USER_GUIDE Study Runner how-to; ASSUMPTIONS (engine stamp + Focus≠Admit); ARCHITECTURE; roadmap |
| **Behavior** | §4.1–4.3. Default promote **byte-identical** (no `lineage`, no new `entry_window`). `--admit-tod auto` → one ranked cell, NY `entry_rth_segment` best bucket, stamp setup+backtest+grid windows, write lineage, new `output_dir` |
| **Out of scope** | Inspect button; `--tod-group`; `--allow-thin`; catalog parent column; spawn |
| **Regression** | Existing promote tests assert no `lineage` and no Admit window when flags omitted; expand/run/report/list argv unchanged; goldens untouched; `engine/` untouched |
| **Acceptance checklist** | |
| | ☑ `study promote` without `--admit-tod` matches pre-SAF1 draft shape (no `lineage`; windows unchanged) |
| | ☑ `--admit-tod auto` writes `constants.backtest.entry_window.enabled: true` with the briefing segment |
| | ☑ Same window on `constants.grid.entry_window` when `grid` mapping exists |
| | ☑ `constants.entry_window` matches (setup stamp) |
| | ☑ Expanded `experiment.yaml` `runs[].backtest.entry_window.enabled` is true (validate via `expand_study` in-memory) |
| | ☑ `study.lineage` validates; unknown lineage key → `StudySpecError` |
| | ☑ Omitted lineage still validates |
| | ☑ Missing zip / unranked name / thin bucket / avg_r tie → `StudyPromoteError`, no `--output` write |
| | ☑ `--top-n 2` without `--admit-run-name` refused |
| | ☑ Child `output_dir` ≠ parent path |
| | ☑ `admit_followup.py` import AST: no execute / launch / viewer / cli_study / Streamlit |
| | ☑ `briefing.py` does not import promote |
| | ☑ Engine goldens untouched; `pytest -q tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SAF1 only from docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md §6.2
and §4.1–4.3. Add thesistester/study/admit_followup.py. Extend study promote
with --admit-tod auto and --admit-run-name. Stamp Admit on
constants.backtest.entry_window and constants.grid.entry_window (and
constants.entry_window). Add optional fail-closed study.lineage. Default
promote without the flag must stay identical to RS5. Reuse
extract_cell_time_of_day / entry_window_from_bucket. Do not execute, do not
edit engine/, do not add Inspect UI, do not add --tod-group. No golden regen.
ENGINEERING_PROPOSAL.md §4.2.
```

### 6.3 SAF2 — Inspect draft → Preview

| | |
|---|---|
| **Depends on** | SAF1 |
| **Likely files** | `pages/15_Studies.py` Inspect; `tests/study/test_study_briefing.py` or page AST tests; session-key allow-list; `STUDY_RUNNER.md` §SAF; USER_GUIDE Studies viewer how-to; ARCHITECTURE key sentence |
| **Behavior** | §4.4. Button uses SAF1 helper (`entry_rth_segment`, thin refuse). Writes Preview YAML; clears confirm / preview cache like Apply |
| **Out of scope** | `--tod-group` UI; catalog parent; `Popen` / `run_study` |
| **Regression** | RS-D9 spawn flags unchanged; Apply / Validate still required before launch; no classic keys |
| **Acceptance checklist** | |
| | ☑ Button absent or disabled when Inspect has no crowned cell / no ToD segment |
| | ☑ Success writes Preview textarea; does not create `study.launch.*` |
| | ☑ Page AST: no `run_study(`; no `CLASSIC_RESEARCH_SESSION_KEYS` writes |
| | ☑ Thin / missing zip → caption via `studies_admit_followup_error` (or equivalent), no YAML clobber |
| | ☑ Extra-root parent refused |
| | ☑ `viewer.py` still does not import promote / admit_followup |
| | ☑ USER_GUIDE: draft ≠ run; extend H2 only |
| | ☑ `pytest -q tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SAF2 only from docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md §6.3
and §4.4. Add Inspect "Draft Admit follow-up" that calls the SAF1 helper and
writes YAML onto the existing Preview textarea (same cache-clear as Apply to
Preview). Do not spawn study run. Do not import execute. Do not add
--tod-group. viewer.py must not import promote or admit_followup. Studies-
scoped keys only. ENGINEERING_PROPOSAL.md §4.2.
```

### 6.4 SAF3 — Hour buckets, thin override, parent column

| | |
|---|---|
| **Depends on** | SAF2 |
| **Likely files** | `admit_followup.py`; `cli_study.py`; `briefing.py` (`group_col` default `entry_rth_segment`); `viewer.py` catalog field (YAML read only); `pages/15_Studies.py` optional group select **or** CLI-only group (prefer CLI-only to keep the button dumb); tests; docs |
| **Behavior** | §4.1 `--tod-group` / `--allow-thin`; §4.5 catalog `parent`. Inspect button stays RTH + thin-refuse (SAF1 semantics) unless a single optional select is added — **default keep button dumb**; hour follow-ups stay CLI |
| **Out of scope** | SAF4 spawn; enabling WFA; multi-cell Admit drafts |
| **Regression** | `--admit-tod auto` without new flags still RTH + thin-refuse; `study list` gains a column only if tests updated |
| **Acceptance checklist** | |
| | ☑ `--tod-group entry_hour_bucket` emits `mode: clock_range` via `entry_window_from_bucket` |
| | ☑ `--tod-group` / `--allow-thin` without `--admit-tod` refused |
| | ☑ Thin bucket succeeds only with `--allow-thin` and `lineage.admit.thin: true` |
| | ☑ Catalog / `study list` shows parent basename when lineage present |
| | ☑ Corrupt spec still does not fail discover |
| | ☑ Briefing Inspect table default remains NY `entry_rth_segment` (SV5 unchanged unless `group_col` default is preserved) |
| | ☑ Goldens untouched; `pytest -q tests/study/` green |

**Copy-ready agent prompt:**

```text
Implement SAF3 only from docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md §6.4
and §4.1 / §4.5. Add --tod-group and --allow-thin to study promote.
Generalize ToD grouping with default entry_rth_segment so SV5 briefing stays
identical. Add catalog / study list parent column from study.lineage
(best-effort YAML). Do not implement SAF4. Do not auto-run. viewer.py still
must not import promote. ENGINEERING_PROPOSAL.md §4.2.
```

### 6.5 SAF4 — Parked (do not implement)

One-click **Confirm and run follow-up** that binds RS-D9 confirm to the **child** identity hash and spawns `study run` into the child `output_dir`.

Parked because: RS5 “promote never executes”; RS-D9 already launches whatever is in Preview after Validate. Operators can Apply/Validate/Run the SAF2 YAML without a second spawn path.

Reopen only via an amendment to this plan.

---

## 7. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SAF0 | Lock |
| `docs/README.md` | SAF0 | Index row |
| `docs/ENGINEERING_ROADMAP.md` | SAF0 planned; SAF3 ✅ | Status table + SAF section |
| `docs/STUDY_RUNNER.md` | SAF0 planned §SAF; SAF1–SAF3 mark shipped | Operator contract |
| `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | SAF0 | Follow-on pointer; **do not** reopen RS5 promote “never execute” |
| `docs/USER_GUIDE.md` H2s `Research Study Runner (headless)`, `Studies viewer (read-only)`, `Focus vs Admit` | SAF0 honesty (not shipped); SAF1–SAF3 how-to | **No new H2**. Keep Help chunks ≤ ~4500 chars |
| RQ §7.1.4 / `_USER_GUIDE_SECTIONS` | Only if a new H2 is added | Do **not** add a new H2 in this series |
| `docs/ARCHITECTURE.md` | SAF0 pointer; SAF1 lineage; SAF2 key | Boundary; Studies-scoped keys |
| `docs/AGENT_GUIDE.md` | SAF0 planned; SAF3 shipped | Pointer; do not implement SAF inside an RS/SV/SB PR |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SAF0 short; SAF1 engine stamp | Child ≠ confirmation; Focus ≠ Admit; `backtest.entry_window` is the engine path |
| `docs/METRICS_GLOSSARY.md` | Only if a new metric name is introduced | Not expected |
| SV / SB / SIA plans | SAF0 | Related-follow-on one-liner |
| Grok pack | SAF3 optional one-liner | Coworkers may `study promote --admit-tod auto`; still no auto-run. Do not rewrite the pack in SAF0 |

Help corpus: extending existing H2s does **not** require an HC allowlist PR.

---

## 8. Test plan (series)

| Layer | Tests | PR |
|---|---|---|
| Default promote | Existing `test_study_promote.py` — no lineage, windows unchanged | SAF1 |
| Admit draft | New `tests/study/test_study_admit_followup.py` — window stamp, lineage, refuse paths, expand backtest window | SAF1 |
| Schema | Unknown `lineage` key; omitted lineage; closed admit.group | SAF1 |
| Import AST | `admit_followup.py` / `viewer.py` / `briefing.py` bans | SAF1–SAF3 |
| CLI argv | Promote help/flags additive; expand/run/report/list unchanged | SAF1 |
| Page AST | No `run_study(`; new key allow-listed | SAF2 |
| Thin / hour | `--allow-thin`; `--tod-group entry_hour_bucket` → `clock_range` | SAF3 |
| Catalog | Parent column; corrupt spec | SAF3 |
| Engine goldens | Must not change | all |

Fixture: reuse an existing study fixture zip **or** a tiny synthetic `trades.parquet` + ranked overview in `tmp_path`. Do not add a large MNQ CSV. Do not call `run_experiment` in SAF tests unless an existing tiny fixture already does (prefer in-memory `expand_study` + `validate_study_spec`).

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Operators think the child confirms edge | Honesty on draft description, Inspect caption, ASSUMPTIONS |
| Setup-only `entry_window` (SV5 copy) still misleads | SAF1 docs + tests assert **backtest** (and grid) stamps; amend SV5/ASSUMPTIONS wording in SAF1 |
| Identity hash surprise | Lineage omitted on default promote; child is a new spec by design |
| Promote argv creep / RS6 drift | Additive flags only; `STUDY.promote` out of series |
| Viewer → promote import cycle | Catalog reads spec YAML only |
| Hour vs NY segment confusion | SAF1/SAF2 stay on `entry_rth_segment`; hour is SAF3 CLI |
| Accidental parent overwrite | New `output_dir`; refuse `--admit-tod` writing into the parent path |

---

## 10. Definition of done (series)

1. SAF0–SAF3 shipped; SAF4 still parked.  
2. `study promote` without flags = RS5.  
3. `--admit-tod auto` produces a validating child with engine-effective Admit and `study.lineage`.  
4. Inspect can place that YAML on Preview without executing.  
5. Hour/30min + thin override + catalog parent link work.  
6. No `engine/` edit; no golden regen; no ToD factor axis; no auto-run.  
7. Living docs + USER_GUIDE H2s updated; Help structure tests green.
