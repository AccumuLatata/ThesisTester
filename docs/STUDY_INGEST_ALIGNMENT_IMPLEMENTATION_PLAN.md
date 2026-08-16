# Study Ingest Alignment — Implementation Plan (SIA)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-15  
**Status:** **SIA0–SIA2 landed. SIA3 this PR.**  
**Series code:** **SIA** (Study Ingest Alignment)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** Research Study Runner RS1–RS5 + RS-D8 + RS-D9; Study Builder SB1–SB3; 15s-primary ingest (`thesistester/data/derive.py`, `api._load_15s_primary_experiment_data`)  
**Related living docs:** `docs/STUDY_RUNNER.md`, `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`, `docs/15s_primary_derived_1m_implementation_plan.md`, `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`  
**Does not reopen:** parked RS-D1 / D3 / D6; SB emit/expand/execute semantics; Data-page ingest; `engine/`; golden-master regeneration  
**Related follow-on (do not implement here):** Study Viewer — `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV). Inspect UX only; does not reopen SIA ingest/emit/example contracts.

**Completeness posture:** After SIA3, a **new** StudySpec authored from Build (or from the updated stage-first example) selects the same headless ingest+R12 contract the Data page already installs: Quantower 15s CSV → derive 1m → attach 15s as R12 source → `intrabar_model=subtimeframe_conservative`. Execution stays `expand` → `run_experiment`. Existing StudySpecs that omit `ingestion_mode` remain `primary` + whatever `intrabar_model` they already declare.

---

## 1. Purpose

Studies is a factorial launcher over R18 `run_experiment`. That is the correct architecture. It is **not** a second simulator.

The defect is the **authoring contract**. Builder defaults, examples, and the Build tab teach legacy 1m + `sl_first`. Pointing a study at the same 15s Quantower file used on Data, without `dataset.ingestion_mode: 15s_primary_derive_1m`, loads that file as **primary decision-TF** (15s bars, no derived 1m, no R12 source). That is a different experiment: levels, signals, volume/VWAP/profile, and trades will not match the classic recommended path.

This series amends **Studies authoring only** so new studies emit the RunSpec the 15s plan already specified for API/CLI. It does not walk Streamlit pages, import `pages/1_Data.py`, read classic `st.session_state`, or edit the engine.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Study Ingest Alignment |
| What changes | Study Builder defaults + first-class `ingestion_mode` + Build-tab widget + teaching example + honesty docs + one parity test |
| What executes | Unchanged: `emit` → Preview → CLI `study run` → `expand_study` → `run_experiment` |
| Compute path used | Existing `api._load_15s_primary_experiment_data` when the emitted RunSpec says so |
| Engine / golden impact | **None** |
| `schema_version` | Stays `1`. No new StudySpec language. No new factor axes |
| Omitted `ingestion_mode` | Still means `primary` (API/CLI identity). Do not reject legacy YAML |
| New-draft default | `15s_primary_derive_1m` + `quantower_history_exporter` + `subtimeframe_conservative` |
| Classic pages / `engine/` / `api.py` execute body | **Frozen** |
| Series complete when | SIA3 acceptance checklist is green |

**Feasibility:** High. Dataset is already a pass-through. `run_experiment` already implements 15s-primary. `validate_run_spec` already rejects `15s_primary_derive_1m` + `subtimeframe_path` and requires Quantower profile. The gap is that Build does not treat `ingestion_mode` as a first-class field and defaults/examples still emit the legacy contract.

### 2.1 In-scope vs out

| In SIA1–SIA3 | Explicitly out (entire series) |
|---|---|
| First-class `StudyDraft.ingestion_mode` | Driving classic nav / page robots |
| New-draft defaults matching Data-page recommended ingest + USER_GUIDE R12 model | Importing `pages/1_Data.py` into `thesistester.study` |
| Build-tab ingest radio (same labels as Data, copied locally) | Reading classic `st.session_state["data"]` / `subtimeframe_data` at execute time |
| Fail-closed emit/schema checks **when the key is present** | `schema_version` bump; new factor axes |
| Smell warnings (15s + `sl_first`; Quantower + `primary`) | Filename / interval auto-detection |
| Teaching example + honesty docs | Forcing existing YAML onto 15s |
| One study-cell vs `run_experiment` parity test on the existing vendor 15s fixture | Unifying Data-page `_prepare_15s_primary_dataset` with `api._load_15s_primary_experiment_data` |
| | “Copy from loaded Data session” button |
| | `engine/` / `simulate_trades` / `intrabar.py` / `derive.py` edits |
| | Golden regeneration; `run_batch` semantics |
| | In-process `run_study`; launch/execute/promote behavior change |
| | Auto-rewriting `intrabar_model` when the operator toggles ingest mode |
| | Grid `intrabar_model` mirroring (pre-existing gap; warn only) |

---

## 3. Problem (locked evidence)

### 3.1 Classic recommended path (do not change)

`pages/1_Data.py` `DEFAULT_UPLOAD_INGESTION_MODE = 15s_primary_derive_1m`.

Upload of a Quantower 15s export:

1. Parse/validate 15s source.
2. `derive_complete_parent_ohlcv` (`observed_aligned_15s_to_1m_v2`).
3. Latch derived 1m as `data` / `base_interval="1min"`.
4. Latch original 15s as `subtimeframe_data`.
5. `prepare_subtimeframe_conservative_context()` fail-closed.

Levels/signals/decision TF use derived 1m. 15s is R12-only. USER_GUIDE recommends `subtimeframe_conservative` for this ingest (sparse minutes). Backtest widget default remains `sl_first` (`index=0`); attachment is necessary, not sufficient. SIA does **not** change that widget.

Headless equivalent already exists:

```yaml
dataset:
  path: nq_15s.csv
  format_profile: quantower_history_exporter
  ingestion_mode: 15s_primary_derive_1m
```

`run_experiment` → `_load_15s_primary_experiment_data` → same derive + attach + `run_backtest(..., subtimeframe_data=...)`.

### 3.2 Studies path today

| Surface | Current contract |
|---|---|
| `default_study_draft()` | `path: data/es_1m.csv`, `format_profile: canonical`, no `ingestion_mode`, `intrabar_model: sl_first` |
| `_DATASET_KNOWN` | `path`, `instrument`, `source_timezone`, `format_profile`, `subtimeframe_path` — **not** `ingestion_mode` |
| Build tab Dataset | path / instrument / timezone / profile. No ingest mode |
| `examples/studies/pdPOC_ma_confluence_battery.yaml` | `data/es_1m.csv`, no mode, `sl_first` |
| `examples/studies/dopen_ma_3c_mnq.yaml` | vendor **1m** Quantower path, `sl_first` |
| `tests/study/` | zero `15s_primary_derive_1m` coverage |
| Execute | `run_experiment` (correct shared engine) with whatever the spec emitted |

`ingestion_mode` can already survive as `dataset_extra` if hand-authored. Build will not emit it. Omitted key → API `primary`.

### 3.3 Failure modes this series closes for **new** studies

1. Same 15s file, omitted mode → research on 15s bars + `sl_first`. Not Data-page 15s-primary.
2. Vendor 1m file vs derived 1m → different `dataset_id` (volume/VWAP/profile). Already documented; examples must stop teaching this as the default.
3. Correct 15s-primary emit but `sl_first` → 15s attached and ignored. Warn; default new drafts to `subtimeframe_conservative`.

---

## 4. Architecture (locked)

```text
StudyDraft.ingestion_mode
        │
        ▼
emit_study_spec ──► StudySpec (schema_version: 1)
        │
        ▼
existing Preview / launch / expand / run_experiment
        │
        ├─ ingestion_mode == 15s_primary_derive_1m
        │     └─ api._load_15s_primary_experiment_data   (UNCHANGED)
        └─ omitted / primary
              └─ api._load_experiment_data               (UNCHANGED)
```

Studies remains an extra **consumer** of the compute contract. It must not become a second ingest implementation.

| Module | SIA may edit? | Rule |
|---|---|---|
| `thesistester/study/builder.py` | Yes (SIA1) | First-class field, defaults, emit/hydrate, warnings |
| `thesistester/study/schema.py` | Narrow (SIA1) | If `dataset.ingestion_mode` **present**, token ∈ {`primary`, `15s_primary_derive_1m`}. Omitted stays legal. No dataset allow-list |
| `pages/15_Studies.py` | Yes (SIA2) | Ingest radio + captions. Studies-scoped widget keys only |
| `examples/studies/pdPOC_ma_confluence_battery.yaml` | Yes (SIA3) | Teaching contract → 15s-primary |
| `examples/studies/dopen_ma_3c_mnq.yaml` | Caption only (SIA3) | Stays **legacy 1m**. Do not rewrite the 1m path to 15s-primary |
| `tests/study/test_study_builder.py` | Yes | New defaults + emit/hydrate + warnings |
| `tests/study/test_study_schema.py` | Additive | Present-key token check; omitted still passes |
| `tests/study/test_study_sia_parity.py` | New (SIA3) | Vendor 15s fixture only |
| `thesistester/study/expand.py` | **No** | `validate_run_spec` already enforces 15s pairing rules |
| `thesistester/study/execute.py` | **No** | |
| `thesistester/study/launch.py` | **No** | Keep pinning `path` + `subtimeframe_path` only |
| `thesistester/study/preview.py` | **No** | |
| `thesistester/api.py` | **No** | |
| `thesistester/data/derive.py` | **No** | |
| `thesistester/engine/**` | **No** | |
| `pages/1_Data.py` … `pages/14_*.py` | **No** | |
| `tests/fixtures/study/golden/**` | **No** | Byte-stable |
| `tests/fixtures/golden/**` | **No** | |

`thesistester.study.builder` may import `INGESTION_MODE_15S_PRIMARY_DERIVE_1M` from `thesistester.data.derive`. It must **not** import `pages.*`.

---

## 5. Locked contracts

### 5.1 Tokens

| Token | Meaning |
|---|---|
| `15s_primary_derive_1m` | Recommended. Single Quantower 15s CSV. Derive 1m. Attach 15s as R12. Forbid `subtimeframe_path` |
| `primary` | Legacy. File is the decision-TF. Optional `subtimeframe_path` for dual-upload R12 |
| omitted | Identical to `primary` at `run_experiment` (do not change API) |

Constant: use `thesistester.data.derive.INGESTION_MODE_15S_PRIMARY_DERIVE_1M` (`"15s_primary_derive_1m"`). Do not invent aliases.

### 5.2 New `default_study_draft()` (SIA1)

| Field | Today | After SIA1 |
|---|---|---|
| `dataset_path` | `data/es_1m.csv` | `data/es_15s.csv` (placeholder; file need not exist until launch — same rule as today) |
| `format_profile` | `canonical` | `quantower_history_exporter` |
| `ingestion_mode` | (absent / extra) | `15s_primary_derive_1m` |
| `subtimeframe_path` | `None` | `None` (illegal in 15s-primary) |
| `backtest.intrabar_model` | `sl_first` | `subtimeframe_conservative` |
| All other draft fields | unchanged | unchanged (still 2 cells: `1×1×2×1×1`) |

`normalize_builder_format_profile(None/blank) → canonical` is **unchanged**. That is the runner default for omitted profile on **hydrate of old YAML**, not the new-draft default.

**Factory vs field defaults (locked — do not invert):**

- `StudyDraft` dataclass field defaults stay **legacy-safe**: `dataset_path=data/es_1m.csv`, `format_profile=canonical`, new `ingestion_mode="primary"`, `_default_backtest()["intrabar_model"]="sl_first"`.
- `default_study_draft()` is the **only** place that applies the new 15s-primary contract (path / Quantower / `15s_primary_derive_1m` / `subtimeframe_conservative`).
- Do **not** change `StudyDraft.ingestion_mode` or `_default_backtest()` to the new-draft values. `hydrate_study_draft` constructs `StudyDraft(...)` with explicit kwargs; a forgotten kwarg would then silently rewrite every legacy YAML. `draft_from_mapping` starts from `asdict(default_study_draft())` and overlays known keys — a new field missing from pre-SIA session mappings would inherit the factory if the field default were 15s-primary.

`hydrate_study_draft` already copies `constants.backtest` as-is (`dict(constants.get("backtest") or {})`). YAML that omits `intrabar_model` must **not** gain `subtimeframe_conservative` on hydrate→emit (expand/API still default omitted model to `sl_first`). Do not merge `_default_backtest()` into a present backtest mapping.

### 5.3 Emit rules (SIA1)

`_emit_dataset`:

1. Always emit `path`, `instrument`, `format_profile` (SB contract unchanged).
2. If `ingestion_mode == 15s_primary_derive_1m`: **always emit** the key.
3. If `ingestion_mode == primary`: **omit** the key (legacy-identical YAML; API default is `primary`).
4. If `subtimeframe_path` is set: emit it only when mode is `primary` / omitted. 15s-primary + `subtimeframe_path` → `StudySpecError` at emit (same rule as `validate_run_spec`).
5. 15s-primary + `format_profile` not in `{quantower_history_exporter}` → `StudySpecError` at emit (same rule as `validate_run_spec`).
6. `dataset_extra` still copies unknown keys **except** `ingestion_mode` once it is first-class.

`_DATASET_KNOWN` becomes:

```text
path, instrument, source_timezone, format_profile, subtimeframe_path, ingestion_mode
```

### 5.4 Hydrate rules (SIA1)

- Present `dataset.ingestion_mode` → that token (invalid token fails at `validate_study_spec` if the caller validates; hydrate itself is not a second validator, but emit after hydrate will fail).
- Absent YAML key → draft field `primary` (so the widget can show Legacy). Re-emit omits the key (§5.3.3). Identity hash of current golden/example YAML that omit the key must stay stable across hydrate→emit **except** where SB already writes `format_profile: canonical`.
- `hydrate_study_draft` **must pass** `ingestion_mode` explicitly. Relying on the dataclass default is only safe because that default is locked to `primary` (§5.2).
- `draft_from_mapping`: if the session payload **omits** `ingestion_mode`, set `primary` after overlay (do not keep `asdict(default_study_draft())`'s new-draft value). `draft_from_mapping(None)` still returns `default_study_draft()` (new draft).
- If a pre-SIA session mapping stored the mode only in `dataset_extra["ingestion_mode"]`, `draft_from_mapping` / `hydrate_study_draft` promote it to the first-class field and drop it from extra (no double emit).
- SIA2 reads `WIDGET_KEY_INGESTION_MODE` onto `draft.ingestion_mode`. Apply then emit writes the 15s key or omits `primary`. The radio does not rewrite `format_profile` or `intrabar_model`.

### 5.5 Schema (SIA1, narrow)

In `validate_study_spec`, after the existing `study.dataset.path` / `instrument` checks:

- If `ingestion_mode` is **absent**: no new check.
- If present and not a string token in `{primary, 15s_primary_derive_1m}`: `StudySpecError`.
- Do **not** add a dataset unknown-key allow-list (`data_artifact_key`, `data_identity`, extras must keep passing).
- Do **not** require Quantower profile or forbid `subtimeframe_path` here — `validate_run_spec` at expand already does that. Schema only shift-lefts the token set so typos fail at authoring, not mid-expand.

Existing fixtures (`tests/fixtures/study/golden_study.yaml`, schema unit payloads) omit the key and must keep passing unchanged.

### 5.6 Warnings (non-fatal)

`draft_warnings` gains, in this order, after the existing partner/core overlap warning:

| Condition | Warning (stable wording for tests) |
|---|---|
| mode is 15s-primary and `backtest.intrabar_model` is `sl_first` or omitted | `15s-primary attaches 15s for R12, but backtest.intrabar_model is sl_first (or omitted → sl_first). Data-page recommended model is subtimeframe_conservative.` |
| mode is `primary` / omitted and `format_profile` is `quantower_history_exporter` | `Quantower profile with primary ingestion treats the CSV as the decision timeframe. A 15-second History Exporter file needs ingestion_mode=15s_primary_derive_1m to match the Data-page recommended path.` |
| `grid.enabled` and grid `intrabar_model` is `sl_first` or omitted while backtest model is `subtimeframe` or `subtimeframe_conservative` | `grid.intrabar_model is sl_first (or omitted → sl_first) while backtest uses observed replay. Grid cells will not use the 15s R12 path.` |

No filename sniffing. No interval inference.

### 5.7 Build tab UX (SIA2)

Add one radio under Dataset, **above** format profile, key `WIDGET_KEY_INGESTION_MODE = "_study_builder_ingestion_mode"`.

Labels (copy locally; do not import the Data page):

| Value | Label |
|---|---|
| `15s_primary_derive_1m` | `Recommended: 15-second primary — derive one-minute canonical` |
| `primary` | `Legacy: one-minute primary (advanced)` |

Captions (Build only; no new USER_GUIDE H2):

- 15s-primary: requires **Quantower History Exporter (semicolon)**; do not set `subtimeframe_path`; recommended `intrabar_model` is `subtimeframe_conservative` (sparse minutes). Launch still requires the CSV on disk.
- Legacy: file is the decision-TF. Optional `subtimeframe_path` remains YAML/hydrate-only (SIA does **not** add a subtimeframe path widget).

**Toggle policy (locked):** changing the radio does **not** rewrite `format_profile` or `intrabar_model`. Emit fails closed / warnings fire. Magical rewrites hide operator intent and break hydrate round-trips.

Seed the widget from the draft on pending-sync, same as other Build widgets.

### 5.8 Examples (SIA3)

**`pdPOC_ma_confluence_battery.yaml`** (stage-first teaching example) — update the dataset/backtest block:

```yaml
dataset:
  path: data/es_15s.csv
  instrument: ES
  source_timezone: America/New_York
  format_profile: quantower_history_exporter
  ingestion_mode: 15s_primary_derive_1m
constants:
  backtest:
    # ... existing SL/TP/costs ...
    intrabar_model: subtimeframe_conservative
```

Header comments must say: replace `dataset.path` with the **same** 15s Quantower export used on Data; vendor-native 1m is a different dataset; omitted mode on a 15s file is not this path.

Factor cartesian / stage / report blocks stay byte-equivalent except the dataset/backtest keys above. Do not change cell count (40 staged / 800 documented).

**`dopen_ma_3c_mnq.yaml`** — do **not** change path, profile, or `sl_first`. Add a banner comment: this example is a **legacy 1m primary** study; it will not match Data-page 15s-primary results on the same dates. Conversion recipe: point `path` at the 15s export, set `ingestion_mode` + Quantower profile, set `intrabar_model: subtimeframe_conservative`, remove any `subtimeframe_path`.

### 5.9 Parked (not SIA)

| Item | Why parked |
|---|---|
| Copy-from-loaded-Data-session | Convenience. Still must emit a RunSpec and execute via CLI. Separate series if wanted |
| Dedup Data-page prepare vs `api._load_15s_primary_*` | Touches the main ingest wrappers. Out of SIA on purpose |
| Force `subtimeframe_conservative` on classic Backtest when 15s session is latched | Classic path; user forbade touching it |
| Make omitted API `ingestion_mode` default to 15s-primary | Would change every headless 1m YAML. Forbidden |
| `schema_version: 2` | Unnecessary; dataset is already a pass-through |

---

## 6. Regression-safety (series-wide)

This series is **authoring/docs/tests**. It is not an engine milestone. Apply `ENGINEERING_PROPOSAL.md` §4 with these concrete gates:

1. **No `engine/` edits.** No `simulate_trades`, `intrabar`, `derive`, levels, or signals changes.
2. **No `api.py` execute/load edits.** `run_experiment` omitted-`ingestion_mode` → `primary` stays.
3. **No classic page edits** except `pages/15_Studies.py` in SIA2.
4. **No golden regeneration.** `tests/fixtures/golden/**` and `tests/fixtures/study/golden/**` byte-stable. CI golden guard unchanged.
5. **Legacy StudySpec identity.** YAML that omits `ingestion_mode` validates, expands, and executes as today. Schema unit fixtures and RS2 goldens are the proof.
6. **Hydrate→emit hash.** `pdPOC` / golden study hydrate→emit identity hash stays equal except the intentional pdPOC example edit in SIA3 (update the builder identity-hash test that reads that example in the same PR).
7. **`st.session_state`.** Only additive `_study_builder_ingestion_mode`. No classic research keys. Record the widget key in `ARCHITECTURE.md` in SIA2.
8. **Opt-in for old files.** Behavior changes only for **new drafts** and the **updated teaching example**. That is the one intentional default change; it is scoped to `default_study_draft()` + pdPOC example, not to `run_experiment`.
9. **Same-PR docs** per §9.
10. **Honesty.** Docs must state: Studies still does not walk the Data page; parity is the RunSpec contract, not session_state sharing.

PR body of every SIA PR must include a short **Regression safety** paragraph naming the frozen trees and the legacy YAML proof.

---

## 7. PR plan

### SIA0 — Plan lock (this PR)

| | |
|---|---|
| **Scope** | This document; `docs/README.md` index; `docs/ENGINEERING_ROADMAP.md` SIA stub; one-line pointers in `docs/STUDY_RUNNER.md` and `docs/AGENT_GUIDE.md` |
| **Code** | None |
| **Acceptance** | Plan is the only implementation spec; living USER_GUIDE/ASSUMPTIONS behavior text is **not** rewritten until SIA3 |

---

### SIA1 — Builder compiler contract

| | |
|---|---|
| **Depends on** | SIA0 |
| **Scope** | `thesistester/study/builder.py`; narrow `thesistester/study/schema.py` token check; `tests/study/test_study_builder.py`; additive `tests/study/test_study_schema.py` cases |
| **Behavior** | §5.2–5.6 |
| **Out of scope** | `pages/15_Studies.py`; examples; execute/expand/launch; USER_GUIDE how-to |
| **Regression** | `pytest -q tests/study/test_study_schema.py tests/study/test_study_expand.py tests/study/test_study_builder.py tests/fixtures/study/golden` (or the suite’s golden expand test). Existing YAML without the key still expands. Golden study files untouched |
| **Acceptance checklist** | |
| | ☑ `default_study_draft()` emit includes `ingestion_mode: 15s_primary_derive_1m`, `format_profile: quantower_history_exporter`, `intrabar_model: subtimeframe_conservative`, `path: data/es_15s.csv` |
| | ☑ Default emit still expands to **2** cells; `validate_run_spec` accepts the emitted runs (file need not exist at emit/expand) |
| | ☑ `StudyDraft()` / `_default_backtest()` stay legacy-safe (`primary`, `sl_first`, `es_1m.csv`, `canonical`); only `default_study_draft()` applies the new contract |
| | ☑ Hydrate YAML that omits `ingestion_mode` → draft `primary` → re-emit **omits** the key |
| | ☑ `draft_from_mapping` of a pre-SIA session dict (no `ingestion_mode` key) → `primary`, not 15s-primary |
| | ☑ Hydrate YAML with `15s_primary_derive_1m` + Quantower → first-class field; extra does not duplicate it |
| | ☑ Emit 15s-primary + `subtimeframe_path` raises `StudySpecError` |
| | ☑ Emit 15s-primary + `canonical` profile raises `StudySpecError` |
| | ☑ `validate_study_spec` rejects `ingestion_mode: ticks`; accepts omitted |
| | ☑ `draft_warnings` covers the three rows in §5.6 |
| | ☑ `normalize_builder_format_profile("")` still `canonical` |
| | ☑ Builder still does not import `execute`, `launch`, `preview`, `pages` |
| | ☑ `tests/fixtures/study/golden/**` byte-identical |

**Copy-ready agent prompt:**

```text
Implement SIA1 only from docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md
§5.2–5.6 and §7 SIA1. Studies authoring only.

In thesistester/study/builder.py: first-class StudyDraft.ingestion_mode
with field default "primary"; change default_study_draft() only (not
StudyDraft field defaults / _default_backtest) per §5.2; emit/hydrate
rules per §5.3–5.4 including draft_from_mapping absent-key → primary;
draft_warnings per §5.6. Import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.data.derive. Do not import pages.

In thesistester/study/schema.py: if dataset.ingestion_mode is present it
must be primary or 15s_primary_derive_1m. Omitted stays legal. No dataset
allow-list.

Do not edit expand, execute, launch, preview, api, engine, derive, Data
page, examples, or any golden fixtures.

Update tests/study/test_study_builder.py for the new defaults and add
schema cases. ENGINEERING_PROPOSAL.md §4.2. Frozen trees stay frozen.
```

---

### SIA2 — Build tab ingest radio

| | |
|---|---|
| **Depends on** | SIA1 |
| **Scope** | `pages/15_Studies.py` Dataset section; seed/read `WIDGET_KEY_INGESTION_MODE`; AST allow-lists in `tests/study/test_study_preview.py` / `test_study_viewer.py` if they enumerate builder keys; `docs/ARCHITECTURE.md` widget-key sentence |
| **Behavior** | §5.7. Toggle does not rewrite profile/intrabar |
| **Out of scope** | Inspect/Preview/launch semantics; classic keys; subtimeframe path widget; USER_GUIDE H2 (SIA3) |
| **Regression** | Page still must not call `run_study` / `spawn` from Build. Classic session key freeze tests stay green |
| **Acceptance checklist** | |
| | ☑ Radio has both labels; default draft seeds 15s-primary |
| | ☑ Hydrate of a `primary` spec seeds Legacy |
| | ☑ Switching radio then Apply emits the matching mode (15s key present / primary key omitted) |
| | ☑ Switching radio does not change format_profile or intrabar widgets |
| | ☑ No new USER_GUIDE H2; no HC allowlist change |
| | ☑ Existing Inspect / Preview / launch tests green |

**Copy-ready agent prompt:**

```text
Implement SIA2 only from docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md
§5.7 and §7 SIA2. Add WIDGET_KEY_INGESTION_MODE on Studies Build Dataset
(above format profile). Labels copied locally — do not import pages.1_Data.
Seed/read like other builder widgets. Do not rewrite format_profile or
intrabar_model on toggle. Do not add a subtimeframe_path widget. Do not
change Inspect, Preview, launch, expand, execute, engine, or goldens.
Extend AST allow-lists if needed. ARCHITECTURE.md: additive widget key
only. No new USER_GUIDE H2. ENGINEERING_PROPOSAL.md §4.2.
```

---

### SIA3 — Example, docs, parity test (series complete)

| | |
|---|---|
| **Depends on** | SIA2 |
| **Scope** | §5.8 examples; living docs in §9; `tests/study/test_study_sia_parity.py` |
| **Behavior** | Teaching contract + honesty. No execute-loop edits |
| **Out of scope** | Rewriting `dopen_ma_3c_mnq.yaml` onto 15s; new 15s vendor fixture (reuse existing); engine |
| **Regression** | Update only the builder identity-hash test that hydrates `pdPOC_ma_confluence_battery.yaml` if its hash changes because of the intentional example edit. RS2 goldens untouched |
| **Acceptance checklist** | |
| | ☑ pdPOC example emits/expands with 15s-primary + conservative; staged count still 40 |
| | ☑ dopen example still 8 cells; banner documents legacy 1m |
| | ☑ Parity test §8 green |
| | ☑ USER_GUIDE Studies H2 + Research Study Runner how-to mention the 15s contract; **no new H2**; each H2 body stays ≤ ~4500 chars (`test_user_guide_h2_bodies_respect_soft_chunk_budget`). Condense first if needed. Studies viewer is already ~3885 |
| | ☑ `STUDY_RUNNER.md`, `ARCHITECTURE.md`, `AGENT_GUIDE.md`, `ASSUMPTIONS_AND_LIMITATIONS.md`, roadmap SIA1–SIA3 ✅ |
| | ☑ Optional one-liner in Grok pack: coworkers must set `ingestion_mode` on 15s files. Do not rewrite the pack |
| | ☑ Full `pytest -q tests/study/` green; no golden regen |

**Copy-ready agent prompt:**

```text
Implement SIA3 only from docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md
§5.8, §8, §9, and §7 SIA3. Update pdPOC example to the 15s-primary teaching
contract; leave dopen as legacy 1m with a banner. Add
tests/study/test_study_sia_parity.py on
tests/fixtures/vendor/quantower_history_exporter_15s.csv as specified
(§8: ExpansionResult.experiment["runs"][0], not .runs).
Do not edit engine, api loaders, derive, Data page, expand, execute, or
tests/fixtures/study/golden. Extend USER_GUIDE existing Studies / Study
Runner H2s only (no new H2, no HC allowlist, each H2 ≤ ~4500 chars).
Close out STUDY_RUNNER.md, ARCHITECTURE, AGENT_GUIDE, ASSUMPTIONS,
ENGINEERING_ROADMAP SIA ✅. ENGINEERING_PROPOSAL.md §4.2.
```

---

## 8. Parity test (SIA3, locked)

File: `tests/study/test_study_sia_parity.py`  
Fixture: `tests/fixtures/vendor/quantower_history_exporter_15s.csv` (already in repo). Do not add a new vendor file.

The fixture is a few 15s bars. Trades may be empty. That is acceptable. The test proves **ingest identity**, not edge.

### 8.1 Positive: Studies emit → expand → `run_experiment` is 15s-primary

1. Build a 1-cell draft (single `confluence_mode`, single trigger/TF, OTF omitted) with:
   - `dataset_path` = the vendor 15s fixture
   - `ingestion_mode=15s_primary_derive_1m`
   - `format_profile=quantower_history_exporter`
   - `intrabar_model=subtimeframe_conservative`
   - `instrument` consistent with the fixture’s use in existing derive tests (follow `tests/test_derive.py` / vendor loader tests)
2. `emit_study_spec` → `expand_study` (returns `ExpansionResult`: `experiment`, `factor_map`, `run_count`, `study_identity_hash` — **no** `.runs` attribute).
3. `run_experiment(expansion.experiment["runs"][0], base_directory=..., execution_origin="study", cache_policy="off")`.
   `run_experiment` takes a **single run mapping** (the expand cell), not the experiment wrapper. `execution_origin="study"` is already in `EXECUTION_ORIGINS`.
4. Assert:
   - `state["ingestion_provenance"]["ingestion_mode"] == "15s_primary_derive_1m"`
   - `state["ingestion_provenance"]["derivation_policy"] == "observed_aligned_15s_to_1m_v2"`
   - `state["base_interval"] == "1min"`
   - `state["subtimeframe_data"]` is a DataFrame with more rows than `state["data"]`. The vendor fixture is **8** 15s bars / **2** complete minutes (8 source → 2 parent). Equal-count is only if a later fixture is one complete minute (4 → 1).
   - `state["backtest_intrabar_policy"]["intrabar_model"] == "subtimeframe_conservative"`
   - `state["backtest_intrabar_policy"]["subtimeframe_data_supplied"] is True`

5. Build the **same** run dict by hand (copy `expansion.experiment["runs"][0]`) and `run_experiment` again. Assert `dataset_id` equal and `ingestion_provenance` equal. This locks “study expand does not rewrite ingest keys.”

### 8.2 Negative: same bytes, omitted mode, is a different experiment

1. Same fixture path, `format_profile=quantower_history_exporter`, **no** `ingestion_mode`, `intrabar_model=sl_first`.
2. `run_experiment` (via a one-cell expand or a direct RunSpec — direct is fine; do not invent a second loader).
3. Assert `ingestion_provenance` is absent or not 15s-primary; `base_interval` is **not** `"1min"`. On this fixture `format_interval` of the inferred gap is `"15s"`.
4. Assert `dataset_id` ≠ the §8.1 `dataset_id`.

Do not “fix” this inequality by auto-detecting 15s in `primary` mode.

### 8.3 Non-goals for the test

- No Streamlit AppTest.
- No classic page helper calls.
- No trade-count vs Backtest-page comparison (would require session_state and a larger fixture).
- No golden-master trade parquet.

If a later series wants classic-session vs study-cell trade hashes, that is a new fixture + an explicit classic helper extract. Not SIA.

---

## 9. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SIA0 | Lock |
| `docs/README.md` | SIA0 | Index row under normative contracts |
| `docs/ENGINEERING_ROADMAP.md` | SIA0 stub; SIA3 ✅ | Status table + SIA section |
| `docs/STUDY_RUNNER.md` | SIA0 one-liner; SIA3 operator paragraph | New studies should emit 15s-primary; omitted mode remains primary; execute still CLI/`run_experiment` |
| `docs/AGENT_GUIDE.md` | SIA0 pointer; SIA3 shipped | Do not point 15s files at studies without `ingestion_mode` |
| `docs/USER_GUIDE.md` H2 `Research Study Runner` + H2 `Studies viewer (read-only)` | SIA3 | Dataset/intrabar rows. **No new H2** (HC allowlist untouched). Soft chunk budget: each H2 body ≤ ~4500 chars (`tests/test_assistant_help_coverage.py`). Runner ~3482 / Studies viewer ~3885 today — condense, do not add a third H2 |
| `docs/ARCHITECTURE.md` | SIA2 key; SIA3 boundary sentence | Builder emits `ingestion_mode`; execute unchanged |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SIA3 | Studies default/example alignment; omitted mode on a 15s file is a different dataset; vendor 1m ≠ derived 1m still holds |
| `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md` | SIA0 one-line related-series | Do not reopen SB1–SB3 scope |
| Grok pack | SIA3 optional one-liner | Coworkers must set the 15s RunSpec keys |

Help corpus: extending the existing Studies / Study Runner H2s does **not** require an HC allowlist PR.

---

## 10. Test plan (series)

| Layer | Tests | PR |
|---|---|---|
| Compiler | `test_study_builder.py` — defaults, emit/hydrate, warnings, import guard | SIA1 |
| Schema | Additive cases in `test_study_schema.py`; existing omitted-key cases unchanged | SIA1 |
| Expand goldens | `tests/fixtures/study/golden/**` byte-stable | all |
| Page AST | Builder widget key allow-list; no `run_study(` on Build | SIA2 |
| Launch | `test_study_launch.py` still uses its 1m temp CSV; unchanged expectations | all |
| Parity | `test_study_sia_parity.py` | SIA3 |
| Suite | `pytest -q tests/study/` per PR; full suite before SIA3 merge | all |

No Streamlit AppTest required.

---

## 11. Risk register

| Risk | Mitigation |
|---|---|
| Changing `_default_backtest()` or `StudyDraft` field defaults bleeds into hydrate / `draft_from_mapping` | Field defaults stay legacy-safe; only `default_study_draft()` applies the new contract. Hydrate copies present `backtest` as-is. Test hydrate of `golden_study.yaml` and `draft_from_mapping` of a pre-SIA session dict |
| New-draft default breaks builder tests that assert `canonical` / `es_1m.csv` / `sl_first` | Update tests that call `default_study_draft()` in SIA1; they encode the drifted contract. Do not change tests that hydrate omitted-key YAML |
| pdPOC identity-hash test fails in SIA3 | Update `test_identity_hash_roundtrip_pdpoc_example_emits_canonical_format_profile` (today asserts omitted profile → emit `canonical`). `test_example_stage_filter_expands_to_40_and_full_800` must stay 40/800. Do not touch RS2 goldens |
| SIA3 USER_GUIDE H2 exceeds Help soft budget (~4500) | Extend existing H2s only; condense first. `#372` already failed CI at 4780 |
| Operator toggles to 15s but leaves `canonical` profile | Emit fail-closed; caption; do not auto-rewrite |
| Operator leaves `sl_first` on 15s-primary | Warning; default only applies to new drafts |
| Grid enabled with omitted grid model | Warning only; do not invent grid keys (would change expand output) |
| Someone “helps” by auto-detecting 15s cadence in `primary` | Forbidden. §8.2 must keep failing if that happens |
| Page becomes a second runner | Build still must not spawn CLI; SIA2 AST |
| Scope creep into Data-page / api loader dedup | Parked. Separate series if ever |

---

## 12. End-to-end product acceptance (after SIA3)

A researcher who uses Studies the way they use Data:

1. Open **Studies → Build StudySpec** (new draft).
2. See ingest mode **Recommended: 15-second primary**.
3. Set `dataset.path` to the same Quantower 15s CSV they upload on Data.
4. Leave profile Quantower and `intrabar_model=subtimeframe_conservative` (defaults).
5. **Apply to Preview** → YAML contains `ingestion_mode: 15s_primary_derive_1m` and no `subtimeframe_path`.
6. Existing **Validate / Preview → Run via CLI**.
7. Cell bundles show 15s-primary provenance, 1m `base_interval`, supplied subtimeframe, conservative R12.

A researcher with an old 1m StudySpec:

1. Hydrate / run as today.
2. No `ingestion_mode` key appears on re-emit if they do not change the radio.
3. Results stay `primary` / existing `intrabar_model`.

CLI `study expand|run|report|promote|rollup` remains the academic path and does not depend on Streamlit.

---

## 13. Status

| Milestone | Intent | Status |
|---|---|---|
| SIA0 | Plan lock + index | ✅ |
| SIA1 | Builder compiler: field, defaults, emit/hydrate, warnings, schema token | ✅ |
| SIA2 | Build tab ingest radio | ✅ |
| SIA3 | Example + docs + parity test | This PR |

Parked (not in SIA): copy-from-session; Data/API loader dedup; classic Backtest default change; API omitted-mode default change; RS-D1 / D3 / D6.
