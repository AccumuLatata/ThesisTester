# Audit Honesty — Implementation Plan (AH)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-18  
**Status:** **AH0–AH3 landed. AH4 this PR.** AH5–AH6 specified, not implemented.  
**Series code:** **AH** (Audit Honesty)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Inputs:** `AUDIT_FINAL.md` on `cursor/audit-final-merge-3a8e` (slices 0–7 at `83a42f8`); CTO review ranking (research-honesty first; C2/H2 before C3 for Studies-first ops; H6 first-wave with golden-stop)  
**Finding IDs** (`C1`/`C2`/`C3`/`H1`/`H2`/`H3`/`H6`) are from that merge report. This plan is the implementation SoT; do not re-audit locked layers while implementing.

**Does not reopen:** R9–R22 milestone text; SW C1–C9; RS execute/in-process runner; SB emit language; SIA ingest defaults; SV inspect; Help-corpus *path* moves; composer collapse; ETH-as-CME flatten; `allow_all` default; API battery `enabled` default flip.

**Related living docs (amend only the sentence that overclaims, in the PR that makes it true):**  
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/AGENT_GUIDE.md`, `docs/STUDY_RUNNER.md`, `docs/otf-filter.md` / `docs/research-methodology.md` (AH3 only), `docs/ARCHITECTURE.md` (AH4 session keys only), `docs/ENGINEERING_ROADMAP.md`.

**Help corpus:** paths stay frozen (`docs/README.md` maintenance rule 2). Amending ASSUMPTIONS/ARCHITECTURE in-place is required by §4. Do **not** move those files or add a new Help H2 for this series.

---

## 1. Purpose

The shipped engine core is generally causal on the happy path. Research identity is not.

Three defects silently change fills, dataset bytes, or validation ranking. Around them sit restore leftovers and one headless eligibility hole. This series fixes **those defects only**, one PR wide, without inverting locked composer/clock contracts and without regenerating goldens.

Goldens prove **legacy-unchanged identity** (`flat_by_session_close=False`, default `sl_first`, OTF/Admit families when those flags are on). They do not prove flatten, restore, or UI↔API admissions. A green suite after an AH PR is necessary and not sufficient unless that PR’s **probe test** is present and red-to-green.

---

## 2. Locked contracts (do not invert)

Copied from the audit merge §5 and frozen here. An AH PR that “simplifies” any of these is out of scope and must be rejected.

1. **Two execution composers.** Classic pages call `thesistester.engine` / `analytics` / `setup` directly. They do **not** call `api.run_experiment`. CLI / Study / Assistant call `run_experiment` only (different `execution_origin`, cache, `base_directory`).
2. **Do not collapse composers** in this series. Do not route pages through `run_experiment`.
3. **`session` ≠ `trading_session_date`.** Flatten is a third clock: calendar date of **this entry’s** `entry_local_ts` + configured close (default `16:00`). Not CME session close. Not `eth_start`.
4. **OTF is not applied at signal generation.** OTF `T` = `trigger_timestamp` else `timestamp` (filled 3c: reversal, not fill).
5. **Focus ≠ Admit.** C7 identity is `allow_all` + `cooldown_bars_after_time=0` only. Study does not run Focus. Study does not call `run_otf_validation_matrix`.
6. **WFA fold slicing is already correct.** AH3 reuses that pattern inside `otf_validation.py` only. Do not edit `walk_forward.py`.
7. **`run_batch` abort semantics stay fail-fast.** AH2 does not make `thesistester run experiment.yaml` equal `study run` for origin / continue / index `status`.
8. **Page 12 import stays schema-only** in AH0–AH6. Assistant open-exact stays hash-fail-closed. Do not collapse the three integrity bars. Page-12 hash is parked (§8).
9. **Omitted `ingestion_mode` = `primary`.** Omitted levels keys = product `DEFAULT_LEVELS_SETTINGS`. Omitted battery `enabled` = `True` on API/CLI/assistant. Study expand already emits `{enabled: false}`. **Do not flip those defaults in this series.**
10. **`validate_setup_config` does not reject `BASE_COLUMNS` today.** AH6 adds that rejection. Hits (`prev30mVWAP_hit_*`) stay rejected. UI pickers already exclude `close`.
11. **Goldens are not regenerated** except the AH5 hard stop (§6.5). New probe families are additive.
12. **Help-corpus paths stay frozen.**

### 2.1 Product decisions locked by this plan

| Topic | Decision | Not in this series |
|---|---|---|
| ETH after-close flatten | Keep **calendar date of this entry + `session_close_time`**. After-close ETH (`entry_local_ts.time() > close` on that calendar date) remains a **non-fill**. AH1 adds a skip row when skip capture is on. | Next-RTH 16:00 hold; `trading_session_date` close; overnight ETH template |
| `allow_all` | Stays default. | Switching default to `single_position` |
| `sl_first` × 3c (AH5) | Honor already-passed `entry_activation_price` on the 3c/confirm **entry parent** so pre-retrace extremes cannot SL. Default model name stays `sl_first`. | New intrabar model; changing R10 `both_hit_rule`; path/subtimeframe edits |
| Study replay | AH2 pins dataset **bytes** (absolute path at expand). Replay is still `run_batch`. | Making CLI ≡ `study run`; copying CSVs into `output_dir` |
| Composer forks (OTF TZ, cutoff-without-flatten, Data-page fatal OHLCV) | **Parked** (§8). | Aligning or merging composers |
| Battery / levels omit-means-on | **Parked.** Study Advanced OFF may later emit explicit `false` (AH7) without flipping API `.get("enabled", True)`. | API default-off migration |

---

## 3. Executive summary

| Item | Decision |
|---|---|
| Feature name | Audit Honesty (AH) |
| What changes | Per-candidate flatten clock; Study dataset path pin + promote/launch search order; OTF-matrix train/OOS **price** slice; restore leftover-key isolation; 3c `sl_first` entry-bar clip; `BASE_COLUMNS` rejected in the shared validator |
| What must not change | Legacy golden trades; WFA math; Focus/Admit; OTF-at-generation; two composers; `run_batch` fail-fast; page-12 schema-only import; Help paths; omitted-key defaults |
| Engine / golden impact | **AH1** touches `simulate_trades` flatten walk only. **AH5** may touch `resolve_ohlc_bar` `sl_first`. Both are golden-gated. AH2–AH4/AH6 must not edit `engine/backtest.py` |
| Series complete when | AH1–AH6 acceptance checklists are green; goldens unchanged (or AH5 isolated regen with CSV diff + explicit approval) |

**Feasibility:** High. Each defect has a one-function or one-module locus already identified. Risk is scope creep (collapsing composers, “while we’re here” defaults, golden regen).

### 3.1 In-scope vs out (entire series)

| In AH1–AH6 | Explicitly out |
|---|---|
| C1 flatten leak + empty-cap skip reason | Composer collapse; pages calling `run_experiment` |
| C2+H2 Study path pin + search order | `run_batch` fail-fast / `origin` / index `status` rewrite |
| C3 OTF-matrix sim frame slice | `walk_forward.py`; Study wiring into the matrix |
| H1 leftover session keys + dataset-less bootstrap skip on page 12 | Page-12 `canonical_bundle_hash` requirement |
| H6 3c `sl_first` pre-entry clip (golden-stop) | New R12 model; MAE/MFE formula change |
| H3 `BASE_COLUMNS` in `validate_setup_config` | Engine second-check; UI picker redesign |
| Probe tests that fail on the slice recipe | Named-test volume without a probe |
| One honesty sentence in the living doc that currently overclaims | Help-corpus path moves; PIT table rewrite (parked M2) |

---

## 4. Fix order (research honesty, Studies-first)

Highest honesty first. Not easy-first. Not golden-align-first.

| Order | PR | Closes | Why this order |
|---|---|---|---|
| **AH0** | This plan + docs index | — | Contract lock before any code |
| **AH1** | Per-candidate `entry_local_ts` + empty-cap skip | C1, M6/M7 flatten slice | Silently wrong fills on any flatten run with >1 calendar date. Downstream metrics inherit the lie. |
| **AH2** | Pin Study dataset path; promote/launch search original spec parent first | C2, H2 | Studies is the active product surface. Coworker replay / promote can crown a different CSV. |
| **AH3** | Slice OTF-matrix train/OOS sims | C3 | Confirmatory leakage in Validation ranking. Study does not call this. After identity so Studies work is not blocked. |
| **AH4** | Manage leftover restore keys; page-12 must not bootstrap-fill `data` after a dataset-less import | H1 (leftovers + bootstrap). **Not** page-12 hash | Restored bundles attach leftover OTF/Focus/setup to imported trades. |
| **AH5** | Honor `entry_activation_price` on `sl_first` entry parent for 3c/confirm | H6 | Default R12 model. ASSUMPTIONS pre-entry exclusion is unimplemented on `sl_first`. Golden-stop if legacy 3c trades move. |
| **AH6** | Reject `BASE_COLUMNS` in `validate_setup_config` | H3 | Shared headless gate. UI already blocked. |

Do **not** start: regenerating goldens, adding named tests without the probe, aligning UI copy without changing admissions, flipping omitted-key defaults, routing pages through `run_experiment`.

---

## 5. Global regression gates (every AH PR)

Copy into each PR body as the “regression safety” paragraph.

1. **Probe first.** Land the failing test that encodes the slice recipe in the same PR as the fix (or immediately before, same branch). The test must fail on current `main` and pass after the fix.
2. **Golden-master.** Run `tests/test_golden_master.py`, `tests/test_otf_golden.py`, and the Admit-enabled golden family. They must stay green. No `GOLDEN_REGEN` except AH5 hard stop.
3. **Default-off / default-unchanged.** Flatten stays default `False`. `sl_first` stays the default model name. `allow_all` stays default. Omitted keys keep today’s meaning.
4. **Narrow diff.** One finding family per PR. Adjacent issues → handoff note, not extra files.
5. **Same-PR docs.** One living-doc honesty sentence. No drive-by ARCHITECTURE/USER_GUIDE rewrites.
6. **No Help path moves.**
7. **§4.2 checklist:** unit tests deterministic; goldens preserved; docs; CI green; small surface.

Suggested local gate (implementer, not CI-only):

```bash
pytest -q tests/test_golden_master.py tests/test_otf_golden.py tests/test_entry_window_admission.py
# plus the probe file named in that PR
```

---

## 6. Per-PR specifications

### 6.1 AH1 — Session flatten `entry_local_ts` leak (C1)

**Status:** Implemented  
**Closes:** C1; M6/M7 only for flatten empty-cap skip (not 3c-void skip, not missing-entry-bar skip)

#### Defect (verified)

`simulate_trades` has two loops:

1. Admission loop (`signals.iterrows`) sets `entry_local_ts` and stores `entry_ts` on the candidate — **not** `entry_local_ts`.
2. Exit walk (`for candidate in ordered_candidates`) unpacks `entry_ts`, then flatten uses the leaked function-scope `entry_local_ts` from the **last first-loop assignment**.

Locus: `thesistester/engine/backtest.py` (~698–716 store; ~838–848 flatten).

Cutoff admission in loop 1 is per-candidate (correct). Flatten in loop 2 is not. Default `flat_by_session_close=False` hides this from goldens. Single-signal flatten tests pass because leak == that signal.

#### Change (surgical)

1. Add `"entry_local_ts": entry_local_ts` to the `candidate_rows` dict.
2. In the second loop, `entry_local_ts = candidate["entry_local_ts"]` next to `entry_ts`.
3. Flatten continues to compute `session_close_ts = entry_local_ts.normalize() + Timedelta(session_close_time)`.
4. When `flat_by_session_close` and `bars_until_close.empty`: `continue` still drops the trade. If `return_skipped_signals` or `return_result`, append skip_reason **`empty_session_close_cap`** (same skip-row schema as `after_entry_cutoff`).
5. Do **not** store flatten clock on `trading_session_date`. Do **not** change cutoff. Do **not** add skip rows for 3c void / missing entry bar.

#### Product lock (document in ASSUMPTIONS, same PR)

- Flatten is **per-entry calendar date + configured close**.
- Overnight ETH is still not modeled.
- After-close ETH on that calendar date is a non-fill (`empty_session_close_cap` when skip capture is on).
- `SESSION_CLOSE` is not CME session close.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/engine/backtest.py` (candidate dict + second-loop unpack + empty-cap skip) | `intrabar.py`, WFA, grid, API composer, pages, Study |
| `tests/test_phase5_backtest.py` or new `tests/test_ah1_session_flatten.py` | Golden parquet/CSV |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §3 (leak is fixed; per-entry-date; empty-cap skip name) | USER_GUIDE H2; PIT table |

#### Probe tests (must exist)

| ID | Recipe | Assert |
|---|---|---|
| AH1-P1 | Two simple signals; last first-loop entry is **Tue 02:00**; earlier entry **Mon 18:30**; flatten on, close `16:00` | Mon 18:30 uses **Monday** 16:00 (empty cap → no trade + skip `empty_session_close_cap` when captured). Tue 02:00 uses **Tuesday** 16:00. Must **not** flatten both to Tuesday. |
| AH1-P2 | Inverse: last first-loop entry Mon 18:30; later Tue RTH entry | Tue RTH flattens at Tue 16:00, not Mon 16:00 (no silent drop). |
| AH1-P3 | Single-signal RTH flatten (existing phase5 fixtures) | Unchanged trades vs current tests. |
| AH1-P4 | `flat_by_session_close=False` multi-date | Identical to flatten-off today (no new exits). |
| AH1-P5 | Empty cap + `return_result=False` (golden default) | Trades-only return; no schema change. |

#### Acceptance

- [x] Probe P1/P2 fail on unpatched `main` and pass after the fix
- [x] Existing `test_session_close_*` in `tests/test_phase5_backtest.py` green
- [x] Golden families green; no regen
- [x] ASSUMPTIONS §3 states per-entry calendar close + `empty_session_close_cap`
- [x] Skip capture still does not change which flatten-off trades fill
- [x] Diff does not touch OTF, Admit, R12, R13

#### Out of AH1

3c void skip rows; Focus/Time Analysis relabel; changing default flatten to on; ETH overnight template.

---

### 6.2 AH2 — Study dataset path identity (C2 + H2)

**Status:** Implemented  
**Closes:** C2, H2

#### Defect (verified)

| Path | `base_directory` / search |
|---|---|
| `study run` | `prepare_study_expansion` → `study_path.parent` (`thesistester/study/execute.py`) |
| `thesistester run out/…/experiment.yaml` | `experiment_path.parent` (`thesistester/cli.py`) |
| Promote | `[cwd, source_study_dir(output), draft parent]` — cwd first (`promote._rewrite_dataset_paths_for_draft`) |
| Launch | allowed roots then **cwd appended** (`launch._pin_dataset_paths`) |

`expand_study` copies `study.dataset` relative paths into every RunSpec (`expand.py` ~318). `write_expansion_artifacts` does not record the original spec parent. `docs/AGENT_GUIDE.md` L38–39 advertises YAML replay as the “unchanged R18 path.” Dataset bytes can differ; abort/origin already differ.

#### Change (surgical)

1. **Pin at expand (identity):** When expanding, resolve `dataset.path` and `dataset.subtimeframe_path` against the **StudySpec file parent**. If a relative path exists as a file there, write the **absolute resolved path** into:
   - in-memory `expansion.experiment` runs
   - emitted `experiment.yaml`
   - copied `study.spec.yaml` dataset block  
   If the relative path is **not** found under the spec parent, leave it relative (do not invent cwd files; do not copy CSVs).
2. **Record provenance:** `study.expansion.json` gains additive `source_spec_parent` (absolute string of the YAML parent). Old expansion JSON without the key remains readable.
3. **Promote search order:** `source_spec_parent` (from expansion.json) → study output dir → draft parent → **cwd last**. Prefer an existing file; do not silently pick cwd when the spec-parent file exists.
4. **Launch search order:** same preference: spec parent (from preview YAML location / recorded parent) before cwd. Keep sandbox `_ensure_within_roots`. Do not import `execute.py` into `launch.py`.
5. **Docs:** AGENT_GUIDE L38–39 and `STUDY_RUNNER.md` “`thesistester run experiment.yaml` is unchanged” — state that **after pin**, replay loads the **same dataset bytes** when the expand-time file still exists; it is still `run_batch` (fail-fast, `origin=cli`, no index `status`). It is **not** `study run`.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/study/expand.py` | `cli.py` `base_directory=experiment_path.parent` |
| `thesistester/study/execute.py` only if expand helper needs the spec path (prefer pass-in) | `run_batch` / `run_experiment` load semantics |
| `thesistester/study/promote.py` search order | In-process `run_study`; viewer |
| `thesistester/study/launch.py` search order | Copying dataset files into `output_dir` |
| Study expand/promote/launch tests | Engine, goldens, Data page |
| `docs/AGENT_GUIDE.md`, `docs/STUDY_RUNNER.md` | Help H2; SIA ingest defaults |

#### Probe tests

| ID | Recipe | Assert |
|---|---|---|
| AH2-P1 | StudySpec in `examples/studies/` with `path: data/es_15s.csv` (or a temp twin: spec-parent `data/a.csv` vs cwd `data/a.csv` with **different** bytes) | Emitted `experiment.yaml` `dataset.path` is the **spec-parent** absolute file. `api` load via CLI `base_directory=output` still opens **a.csv from spec parent**. |
| AH2-P2 | Promote from that study dir with cwd file present | Draft pins spec-parent file, not cwd. |
| AH2-P3 | Launch pin with both files present | Pinned path is spec-parent. |
| AH2-P4 | Relative path missing under spec parent | Left relative; no exception at expand; no cwd auto-create. |
| AH2-P5 | Existing study tests (expand validate, launch pid, SIA examples) | Green; `schema_version` stays `1`. |

#### Acceptance

- [x] P1–P3 fail on unpatched `main` when both files exist
- [x] `run_batch` fail-fast / origin / workers unchanged
- [x] `study run` still uses `run_experiment` + ledger continue
- [x] AGENT_GUIDE no longer claims identity-equivalent replay beyond **dataset bytes**
- [x] No CSV copy; no `cli.py` base_directory rewrite
- [x] Goldens untouched

#### Out of AH2

Portable relative rewrite for coworker machines; changing `confirm_above_runs`; pinning `ingestion_mode` into `dataset_id` (H9, parked).

---

### 6.3 AH3 — OTF validation matrix train path leak (C3)

**Status:** Implemented  
**Closes:** C3

#### Defect (verified)

`run_otf_validation_matrix` splits **signals** chronologically, then calls `_simulate(source_df, accepted_train, …)` with the **full** OHLCV frame (`thesistester/analytics/otf_validation.py` ~389–407). A last-train signal can TP on an OOS-only spike; `train_expectancy_r` ranks that number. OTF **filter** on the full frame stays PIT (keep). WFA already simulates on `train_df` / `test_df` slices — do not edit it. Study does not call this matrix.

#### Change (surgical)

1. After building `accepted_train` / `accepted_oos`, derive a **price-split timestamp**:
   - `split_ts` = minimum timestamp among OOS candidate signals if any OOS exist; else `+inf`.
   - Use the same chronological order as `_chronological_train_oos_sets` (`timestamp`, `bar_index`).
2. `train_df = source_df[source_df["timestamp"] < split_ts]` (half-open; OOS bars never enter the train walk). If no OOS, `train_df = source_df`.
3. `oos_df = source_df[source_df["timestamp"] >= split_ts]` when OOS exists; else empty frame.
4. `_simulate(train_df, accepted_train, …)` and `_simulate(oos_df, accepted_oos, …)`.
5. Reset index on slices if `simulate_trades` requires 0-based `bar_index` alignment — **must rematch signal `bar_index` / `entry_bar_index` to the sliced frame or slice by the original index without resetting in a way that desyncs indices.**  
   **Preferred (less drift):** pass a view that **keeps original `bar_index` labels** if the engine indexes by position. `simulate_trades` uses `df.reset_index(drop=True)` and `sig["bar_index"]` as positional. Therefore the slice **must remain a prefix/suffix of the original positional frame**:
   - `split_bar` = minimum `bar_index` among OOS signals (or `len(source_df)` if none).
   - `train_df = source_df.iloc[:split_bar]` (positional prefix — WFA-shaped).
   - `oos_df = source_df.iloc[split_bar:]` **cannot** be used as-is because signal `bar_index` still refers to the full frame.
   - **Lock:** simulate train on `source_df.iloc[:split_bar]` (prefix; indices 0..split_bar-1 still match). Simulate OOS on the **full** `source_df` but only with OOS signals whose `bar_index >= split_bar` (OOS holding may use later bars; that is evaluation, not selection).  
   This is the minimum change that stops train ranking from seeing OOS prices. Do **not** rewrite OOS signal indices.
6. Ranking remains `train_expectancy_r` only. OOS columns unused for selection.
7. Docstring: remove “only signals drive simulation / full dataset for prices.” State train **prices** are the positional prefix before the first OOS signal bar.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/analytics/otf_validation.py` | `walk_forward.py`, `grid.py`, `engine/backtest.py` |
| `tests/test_otf_validation.py` (+ probe) | `pages/10_Validation.py` copy except one honesty sentence if it claims “OOS never influences selection” without “path” |
| `docs/research-methodology.md` or `docs/otf-filter.md` (one sentence: train sim is prefix-sliced) | Study execute; Help H2 |

#### Probe tests

| ID | Recipe | Assert |
|---|---|---|
| AH3-P1 | Last train signal; OOS-only spike that would TP (`r` large) if the full frame is passed | `train_expectancy_r` matches prefix-only sim (spike absent), **not** the full-frame leak value. |
| AH3-P2 | No OOS signals (`train_fraction` such that all train, or 1-signal) | Same metrics as today. |
| AH3-P3 | Existing OTF matrix unit tests | Green; rank still by train columns only. |
| AH3-P4 | WFA tests | Untouched / green. |

#### Acceptance

- [x] P1 fails on unpatched `main`
- [x] Filter still runs on full `source_df` (PIT unchanged)
- [x] `is_train_selected` still from train metrics only
- [x] No `walk_forward.py` diff
- [x] Goldens untouched (matrix is not in the golden pipeline)

#### Out of AH3

Study calling the matrix; `diagnostic_only` flag (H13, parked); UI heatmap copy beyond one sentence.

---

### 6.4 AH4 — Restore leftover keys + dataset-less bootstrap (H1)

**Status:** Implemented  
**Closes:** H1 leftovers + bootstrap mix. **Does not** close page-12 hash (M14 hash bar stays schema-only).

#### Defect (verified)

`apply_research_bundle_to_session` clears `_MANAGED_RESEARCH_KEYS` then restores bundle values. Keys **not** in that set survive:

- `otf_filter_summary` / `otf_filter_result` (Report `build_otf_filter_metadata` reads these)
- `setup_config`
- `focused_trades` (Focus overlay)

`pages/12_Research_Bundles.py` calls `bootstrap_active_saved_dataset()` on load. Dataset-less zip + active saved dataset A → `data=A` while restored `trades` are from B.

Nonce invalidation (upload widgets) is real and stays. It does not clear these keys.

#### Change (surgical)

1. Add to `_MANAGED_RESEARCH_KEYS` (and clear on apply):  
   `otf_filter_summary`, `otf_filter_result`, `backtest_otf_filter`, `setup_config`, `focused_trades`.  
   If API/pages persist `grid_otf_filter` already via existing keys, do not rename. Prefer **clearing** leftovers over inventing new export schemas.
2. `build_otf_filter_metadata`: if `backtest_otf_filter` is the scoped export key used by headless, read it **after** managed restore (bundle-owned). Do not keep reading a leftover `otf_filter_summary` that was not in the zip. If both absent → unavailable (current disabled/unavailable path).
3. **Page 12 bootstrap:** do **not** change `bootstrap_active_saved_dataset()` globally. On page 12, call bootstrap **only when the import path did not just apply a bundle without `data`**. Concrete: move the module-level `bootstrap_active_saved_dataset()` so it does not run unconditionally after a dataset-less import in the same run, **or** have `apply_research_bundle_to_session` set a session flag `bundle_import_omitted_data=True` when `data` was not in `session_values`, and skip bootstrap when that flag is set. Clear the flag on Data-page successful load. Smallest diff that prevents A+B mix.
4. Do **not** require `canonical_bundle_hash` on page 12.
5. ARCHITECTURE: one sentence — nonce ≠ leftover research keys; listed keys are now managed.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/research_bundle.py` (`_MANAGED_RESEARCH_KEYS` + apply) | Assistant open-exact / hash verifier |
| `thesistester/reporting.py` (`build_otf_filter_metadata` read order) | Engine, Study execute |
| `pages/12_Research_Bundles.py` (bootstrap gating only) | Page-12 schema validation rewrite |
| `thesistester/app_state.py` **only** if a tiny skip-flag helper is cleaner than page-local logic | Changing bootstrap for pages 1–11 |
| `tests/test_research_bundle.py` | Goldens |
| `docs/ARCHITECTURE.md` session-key table (additive) | USER_GUIDE |

#### Probe tests

| ID | Recipe | Assert |
|---|---|---|
| AH4-P1 | Session has `otf_filter_summary` (12 rejected) + import CLI zip with OTF off / no OTF section | After apply, Report metadata does **not** show 12 rejected. |
| AH4-P2 | Session has `focused_trades` / `setup_config`; import bundle without those | Keys cleared; not leftover. |
| AH4-P3 | Dataset-less bundle import while active saved dataset A exists | `data` is **not** A after import (missing or bundle data only). |
| AH4-P4 | Existing bundle round-trip tests | Green; nonce tests still pass. |
| AH4-P5 | Assistant open-exact tests | Untouched / green. |

#### Acceptance

- [x] P1–P3 fail on unpatched `main`
- [x] Page 12 still schema-only (tampered parquet still imports — parked)
- [x] Complete-bundle import still restores `data` from the zip when present
- [x] No engine/golden diff
- [x] ARCHITECTURE lists the new managed keys

#### Out of AH4

Hash-fail-closed page 12; refusing bootstrap on every page; export schema version bump unless a test forces it (prefer additive clear-only).

---

### 6.5 AH5 — `sl_first` pre-entry SL on 3c (H6)

**Status:** Specified  
**Closes:** H6  
**Hard stop:** if any golden trade frame changes, **stop**. Do not silent-regen.

#### Defect (verified)

`simulate_trades` already passes `entry_activation_price=theoretical_entry_price` on the 3c/confirm **entry parent** (`backtest.py` ~887–891). `resolve_ohlc_bar` `sl_first` ignores `entry_price` and can SL on the pre-retrace parent extreme (`intrabar.py` ~350–357). Path / subtimeframe implement pre-entry exclusion. ASSUMPTIONS §2 claims it more broadly than `sl_first` implements.

Goldens are default `sl_first` and flatten-off. They may or may not include a 3c entry-bar that would change.

#### Change (surgical)

1. **First command in the PR:** run golden families on current `main` (baseline green).
2. In `resolve_ohlc_bar`, for `model == "sl_first"` only: if `entry_price is not None`, ignore SL/TP hits that occur **beyond** the entry (same semantics as `_path_after_entry` / conservative fallback already used for other models). Minimum: for `sl_first`, do not count `stop_hit` from a long bar whose **low** is through the stop if that excursion is **before** entry on a pessimistic full-bar read — implement by treating the entry bar as “SL/TP only if the stop/target is on the **post-entry** side of `entry_price`” using the existing helper if one is already shared. **Do not reimplement a new path model.** Reuse `_path_after_entry` or the conservative clip already in `sim_core.py` (~106–118) if that is the identical rule.
3. Non-entry bars (`entry_price is None`) stay exact current `sl_first`.
4. `path_open_proximity` / `subtimeframe*` **no diff**.
5. Re-run goldens.  
   - **Green:** commit. ASSUMPTIONS §2: `sl_first` now honors entry-bar activation for 3c/confirm.  
   - **Red:** **do not regen in this PR.** Open a follow-up `AH5-GOLDEN` with readable CSV diff + justification, or abort and park behind an explicit keyword (not preferred). Default model name must remain `sl_first`.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/engine/intrabar.py` (`sl_first` + `entry_price` only) and/or `sim_core.py` if that is the single chokepoint | `backtest.py` signature; WFA; Study |
| New `tests/test_ah5_sl_first_3c_entry.py` | R10 excursions |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §2 | USER_GUIDE; new R12 model |

#### Probe tests

| ID | Recipe | Assert |
|---|---|---|
| AH5-P1 | 3c long fill at 100; entry parent low 97 before retrace; SL 2 pts | **Not** SL on 97. Either hold / later exit, or SL only if post-entry extreme hits. |
| AH5-P2 | Simple next-bar-open `sl_first` both-hit | Identical to today (`entry_price is None` on that bar). |
| AH5-P3 | Golden families | Green, or hard-stop. |

#### Acceptance

- [ ] P1 fails on unpatched `main`
- [ ] P2 unchanged
- [ ] Goldens green **or** PR stopped for isolated regen
- [ ] No new `intrabar_model` value
- [ ] ASSUMPTIONS matches code

#### Out of AH5

Changing default to `path_open_proximity`; 3c void skip rows; MAE full-parent change.

---

### 6.6 AH6 — Reject `BASE_COLUMNS` in `validate_setup_config` (H3)

**Status:** Specified  
**Closes:** H3

#### Defect (verified)

`validate_setup_config` rejects `NON_LEVEL_OUTPUT_COLUMNS` only (`setup.py` ~406–412). `close` ∈ `BASE_COLUMNS` is headless-legal. `api.build_setup` / `generate_signals` can emit `close|ONH` zones. UI pickers use `available_level_columns`. Study *factors* already use `closed_level_token_set`. Hand-edited YAML / Assistant / CLI can still pass `close`.

#### Change (surgical)

1. In `validate_setup_config`, treat `BASE_COLUMNS` like hits: reject if present in `selected_levels` or anchor rule levels (same places `NON_LEVEL_OUTPUT_COLUMNS` is checked).
2. Error text lists the banned names (same style as diagnostic-column errors).
3. Do **not** add an engine `detect_confluence_zones` second-check in this PR (optional later).
4. Grep fixtures / examples for `selected_levels: [close]` — none should exist; if one does, that fixture is invalid and must be fixed to a real level, not grandfathered.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/setup.py` | Engine confluence; pages pickers (already correct) |
| `tests/test_setup_config.py` or existing setup validate tests | Study factor token set (already closed) |
| `docs/AGENT_GUIDE.md` one line if it implies any column is a level | Goldens; API defaults |

#### Probe tests

| ID | Recipe | Assert |
|---|---|---|
| AH6-P1 | `selected_levels=["close","ONH"]` | `validate_setup_config` non-empty errors; `api.build_setup` / `generate_signals` fail closed (no `close\|ONH` zones). |
| AH6-P2 | Hits still rejected | Unchanged. |
| AH6-P3 | Valid ONH-only setup | Unchanged empty error list. |

#### Acceptance

- [ ] P1 fails on unpatched `main`
- [ ] UI path unchanged
- [ ] Goldens untouched
- [ ] No engine second-check required

---

## 7. Documentation rules

| PR | Living doc | Sentence to make true |
|---|---|---|
| AH0 | This file + `docs/README.md` + `docs/ENGINEERING_ROADMAP.md` | Series exists; AH1–AH6 not implemented |
| AH1 | ASSUMPTIONS §3 | Flatten is per-entry calendar date; leak fixed; `empty_session_close_cap` |
| AH2 | AGENT_GUIDE L38–39; STUDY_RUNNER replay paragraph | Dataset bytes pinned; replay ≠ `study run` |
| AH3 | `otf-filter.md` or `research-methodology.md` | Train **prices** are prefix-sliced; filter remains full-frame PIT |
| AH4 | ARCHITECTURE session keys | Listed leftovers are managed; nonce ≠ those keys |
| AH5 | ASSUMPTIONS §2 | `sl_first` honors 3c/confirm entry activation on the entry parent |
| AH6 | AGENT_GUIDE (optional one line) | `close` / OHLCV base cols are not levels |

Do not amend `ENGINEERING_PROPOSAL.md` §§1–3. Do not move Help paths.

---

## 8. Parked (explicit non-goals)

Do not implement in AH0–AH6. Do not “quickly fix” inside an AH PR.

| ID | Topic | Why parked |
|---|---|---|
| H4 / H8 | Omit-means-on (levels product fill; API battery `enabled` default True) | Defaults migration. Study already emits `{enabled:false}`. Flipping API default changes hand-written R18 YAML. Possible later **AH7**: Build Advanced OFF emits explicit `false` only. |
| H7 / H10 / H15 | Cutoff-without-flatten; Data-page fatal OHLCV; OTF TZ | Cross-composer admission. Needs paired UI+API tests. Possible later **AH8** as **one fork per PR**. |
| H9 | `dataset_id` omits ingest story | Cache honesty; needs a written probe first. |
| H11 | Canonical mixed-offset DST CSV | Fail-closed availability, not fabricated fills. |
| H5 / H12 / H13 / M8–M11 | Presentation (allow_all caption, Focus vs Admit N, Phase 8 `st.success`, `pnl_points` gross) | Copy-only. After fill/identity SoT is true. |
| H14 / M5 | Non-base 3c stale projection / zone-level naked | Separate 3c HTF series. |
| H16 | Study MD failed section / in-sample crown | After AH2 so the MD describes the bytes that ran. |
| M2 | PIT table overclaim | Doc-only; do not block fills. |
| M14 hash | Page 12 `canonical_bundle_hash` | Open product decision; inverts §5.4 bar split. |
| — | Composer collapse | Rewrite. Close forks first (AH8), then reconsider. |
| — | ETH CME flatten / next RTH hold | §2.1 lock. |
| — | `allow_all` default change | §2.1 lock. |
| — | Delete `confirm_3bar` | Residual; not a silent fill bug for generated signals. |
| — | Golden regen “to match flatten-on” | Flatten-on is not a golden family. Additive probes only. |

---

## 9. Suggested PR titles

- `AH0: audit-honesty plan lock (docs only)`
- `AH1: per-candidate session flatten clock`
- `AH2: pin Study dataset paths at expand`
- `AH3: prefix-slice OTF-matrix train prices`
- `AH4: manage leftover bundle session keys`
- `AH5: sl_first honors 3c entry activation`
- `AH6: reject BASE_COLUMNS in setup validator`

---

## 10. Implementer prompts (copy-ready)

Use one prompt per PR. Do not combine AH1 with AH2.

### AH1

```markdown
Implement **AH1 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.1.

Regression-safe and drift-safe. Do not invert §2 locked contracts.
Touch `thesistester/engine/backtest.py` flatten path only (store `entry_local_ts`
on each candidate; unpack it in the second loop; skip_reason `empty_session_close_cap`
when flatten cap is empty and skip capture is on).
Do not change default `flat_by_session_close=False`.
Do not change ETH policy to `trading_session_date` or next-RTH hold.
Do not add 3c-void skip rows. Do not regen goldens.
Add probe tests AH1-P1–P5 (P1/P2 must fail on current main before the fix).
Amend ASSUMPTIONS §3 only. Run golden + phase5 session-close tests.
```

### AH2

```markdown
Implement **AH2 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.2.

Pin Study `dataset.path` / `subtimeframe_path` to absolute files resolved against
the StudySpec parent at expand. Record `source_spec_parent` in `study.expansion.json`.
Promote/launch search that parent **before** cwd.
Do not change `cli.py` `base_directory`, `run_batch` fail-fast, or copy CSVs.
Do not edit `engine/`. Do not regen goldens.
Add AH2-P1–P5. Update AGENT_GUIDE L38–39 and STUDY_RUNNER: replay shares dataset
bytes when pinned; it is still `run_batch`, not `study run`.
```

### AH3

```markdown
Implement **AH3 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.3.

In `otf_validation.py` only: train `simulate_trades` must use the positional
OHLCV prefix before the first OOS signal `bar_index`. Keep OTF filter on the
full frame. Do not edit `walk_forward.py` or `engine/`.
Add AH3-P1 (OOS-only spike must not inflate `train_expectancy_r`).
One honesty sentence in `otf-filter.md` or `research-methodology.md`.
Goldens untouched.
```

### AH4

```markdown
Implement **AH4 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.4.

Add leftover keys to `_MANAGED_RESEARCH_KEYS` and clear them on bundle apply.
Gate page-12 `bootstrap_active_saved_dataset` so a dataset-less import cannot
re-fill `data` from the active saved dataset.
Do **not** require `canonical_bundle_hash` on page 12.
Do not edit engine/goldens. Add AH4-P1–P5. ARCHITECTURE: list new managed keys.
```

### AH5

```markdown
Implement **AH5 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.5.

`sl_first` must honor `entry_activation_price` on the 3c/confirm entry parent
by reusing existing post-entry helpers. Do not add a new `intrabar_model`.
Do not edit path/subtimeframe branches except reuse.
Run goldens first. If they go red, **stop** — no silent regen.
Add AH5-P1–P3. Amend ASSUMPTIONS §2 only.
```

### AH6

```markdown
Implement **AH6 only** from `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.6.

Reject `BASE_COLUMNS` in `validate_setup_config` wherever
`NON_LEVEL_OUTPUT_COLUMNS` is already rejected.
Do not add an engine second-check. Do not edit pages or goldens.
Add AH6-P1–P3. Fail closed on `selected_levels=["close","ONH"]`.
```
