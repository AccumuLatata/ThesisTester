# QI-01 — Data ingestion, sessions, derivation, dataset persistence

**Slice:** QI-1 (research-only)
**Status:** Completed
**Audited commit:** `32ad34c` (`32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc`) — `main` after [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) (QI-11) on top of QI-0 / Wave A
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1, vulture 2.16
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi1-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 7 (C/H/M/L = 0/0/6/1)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day.

Locked inputs treated as premises (not re-audited): `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1. `observed_aligned_15s_to_1m_v2` and OHLC-identical duplicate resolution were not re-derived (AUDIT S1 locked). `local_store.py` is exclusive to this slice (levels-namespace observations → QI-2 handoff).

**Review corrections (schema / honesty only; no product files):** Plan §2 rule 5 — a finding that says the design should be otherwise is `Design limitation`, `confidence=n/a`, severity ≤ Medium. First draft classified parked H11 (AH §8 fail-closed) as High `Verified defect` and proposed UTC-normalize as `expected`; that is withdrawn. H9/H10 stay Design limitation. `pages/1_Data.py` has **46** top-level defs (QI-00 / plan), not 48 extracted helpers (AST also counts 2 exception `__init__` methods). `save_dataset` is **144** physical lines, not 145. H9 hash prefixes `a0c7cd93db940342` / `4509affeb4543fc2` / `ef4cf8f153909cff` do not reproduce from the published four-bar recipe and are withdrawn (equality / differ still holds). `iso25010` tokens stay inside plan §A.5. `prior_id` keeps `AUDIT_FINAL` H-ids only.

Review-pass `pytest -q` on this branch: **3966 passed, 5 skipped** (134.96 s) — identical pass/fail/skip to the slice before/after. Scoped ingest suite 243 passed. Porcelain: only the two `docs/quality/` files.

## Commands run (verbatim)

```bash
python3 --version
git rev-parse HEAD
git log -1 --format='%h %ad %s' --date=short

export THESISTESTER_STORE_DIR=/tmp/qi1-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no

radon cc thesistester/data thesistester/persistence/local_store.py \
  thesistester/persistence/__init__.py thesistester/config.py pages/1_Data.py \
  -s -n D --total-average
radon mi <same files> -s
radon cc pages/1_Data.py -s
vulture <same files> --min-confidence 60
rg -n 'except Exception|except:' thesistester/data \
  thesistester/persistence/local_store.py thesistester/config.py pages/1_Data.py
rg -c 'st\.session_state' pages/1_Data.py

# probes
export THESISTESTER_STORE_DIR=/tmp/qi1-store-probes
PYTHONPATH=/workspace python3 /tmp/qi01_probes.py

# scoped suite twice
pytest -q -p no:cacheprovider tests/test_loader.py tests/test_vendor_loaders.py \
  tests/test_data_page_helpers.py tests/test_derive.py tests/test_rolls.py \
  tests/test_15s_primary_persistence.py tests/test_quantower_ticks.py \
  tests/test_local_store.py
PYTHONHASHSEED=0 pytest -q -p no:cacheprovider <same files>

export THESISTESTER_STORE_DIR=/tmp/qi1-store-after
pytest -q --tb=no
git status --porcelain
```

Probe script lives under `/tmp/qi01_probes.py` (not committed). Transcript: `/tmp/qi1-probe-results.json`.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-0 exclusive ownership; 11 files + `sample_data/`)**

| Path | Role in this slice |
|---|---|
| `thesistester/data/loader.py` | Canonical + R17 vendor profiles; `validate_ohlcv`; 15s source-dup prepare |
| `thesistester/data/derive.py` | `observed_aligned_15s_to_1m_v2` parent derivation + provenance |
| `thesistester/data/resample.py` | Preview resample (`SUPPORTED_TIMEFRAMES`) |
| `thesistester/data/rolls.py` | Roll method / gap diagnostics (R7 never rewrites OHLC) |
| `thesistester/data/sessions.py` | `tag_session` RTH/ETH wall-clock |
| `thesistester/data/quantower_ticks.py` | Tick–Tick–Last attach parser |
| `thesistester/data/__init__.py` | Re-exports |
| `thesistester/persistence/local_store.py` | `compute_dataset_id`, dataset/levels/signals/setups namespaces, schema v1→v2 |
| `thesistester/persistence/__init__.py` | Re-exports (incl. QI-6 `execution_artifacts` — not dual-owned) |
| `thesistester/config.py` | `INSTRUMENTS`, `REQUIRED_COLUMNS`, `TIMEZONE_OPTIONS` |
| `pages/1_Data.py` | Composer A ingest UI (46 top-level defs + module-level render; 2 exception `__init__` methods) |
| `sample_data/ES_sample_1m.csv` | Canonical happy-path fixture (12 bars) |

Read-as-spec (QI-13 owns): `docs/ARCHITECTURE.md` session/store keys; `docs/USER_GUIDE.md` Data H2; `docs/ASSUMPTIONS_AND_LIMITATIONS.md` ingest / holiday; `docs/AGENT_GUIDE.md` R17.

Read-as-call-site only (not owned): `thesistester/api.py` `load_dataset` / `_load_15s_primary_experiment_data` / `validate_run_spec` format-profile literal; `thesistester/research_identity.py` `DataIdentity.dataset_id`; `thesistester/persistence/execution_artifacts.py` `source_binding_key`; `thesistester/study/builder.py` `getattr` label fallback; `thesistester/levels/session_date.py` `trading_session_date` (QI-2).

**Skipped**

- Mutation of `loader.py` / `derive.py` — QI-11.
- Full-suite coverage XML re-measure — QI-0 numbers reused.
- Browser `AppTest` of page 1 — no product change; §3.2 via helpers + `/tmp` probes. Handoff QI-10.
- Re-deriving `observed_aligned_15s_to_1m_v2` or OHLC-identical keep-lowest-volume (AUDIT S1).
- Tick-gated level refusals (`APOC requires ticks`) — QI-2.
- Flame graphs / 3-month scaling — QI-14. CAI `realistic` timed for ingest only.

---

## 2. Code-quality readout

192 blocks in scope. Average CC **A (4.63)**. No F-grade (CC ≥ 41) in this slice.

### 2.1 Metric table (QI-1 files only)

| Metric | Value | Trigger hit? |
|---|---|---|
| F-grade (CC ≥ 41) | none | no mandatory F-finding |
| E-grade (31–40) | `save_dataset` **34** · `validate_roll_metadata` **31** | Read; `save_dataset` → QI-01-02 |
| D-grade (21–30) | `load_ohlcv` 25 · `_render_subtimeframe_upload` 25 · `_read_explicit_profile` 24 · `_render_tick_attach` 22 | Read and classified below |
| Physical lines > 150 | `_render_subtimeframe_upload` 186 · module-level page render ~411 (after last helper to EOF) · `save_dataset` **144** | Yes |
| MI | `pages/1_Data.py` **0.00** · `local_store.py` **0.00** · `loader.py` **14.62** (< 20) · others A (24.9–100) | Yes — structural on two modules |
| Broad `except Exception` | 3: `loader._profile_timestamp` · `loader.load_ohlcv` localize · `quantower_ticks._localize_utc` | Classified below |
| `vulture` ≥60 | 10. False positives: `Instrument` dataclass fields; `parse_interval` (QI-4 `intrabar`); `_resolve_existing_tick_path` (tested). Real unused: `rolls.ROLL_RULES` (allow-list never consulted) | noted; not promoted |
| Streamlit in library (QI-1) | 0 | none |
| Cross-module private imports | 0 in scope | none |
| `st.session_state` matching lines | page 1: **170** | QI-10 graph |
| `# noqa` / `# type: ignore` | 0 | none |
| Coverage (QI-0) | `sessions`/`config` 100% · `quantower_ticks` 90% · `local_store` 88% · `loader` 87% · `resample` 84% · `derive` 82% · `rolls` 72%. None < 70% | none |

### 2.2 `pages/1_Data.py` functions CC ≥ 21 (exit criterion)

Helpers are already extracted (**46** top-level defs; QI-00 / plan count). AST walk also sees 2 exception `__init__` methods. MI 0.00 is the **module-level Streamlit script** plus two D-grade renderers, not a single F-grade orchestrator.

| Symbol | CC | Phys. lines | Classification |
|---|---|---|---|
| `_render_subtimeframe_upload` | **D 25** | 186 | Legacy dual-upload + OHLC-identical resolve + R12 compat report + install. Extraction candidate (compat vs duplicate-resolve vs install). Covered by `tests/test_data_page_helpers.py`. **Not an independent defect** — folded into QI-01-01. |
| `_render_tick_attach` | **D 22** | 100 | Path/upload/validate/install for Tick–Tick–Last. Single feature surface. Same. |

Other long helpers below the CC-21 trigger (classified so they are not re-read): `_render_roll_assumptions` C 18 / 105 lines; `_clear_dataset_dependent_state` A 2 / 91 lines (key list); `_render_dataset_summary` C 12 / 85 lines (always `st.success` then optional warn — H10 honesty); `_prepare_15s_primary_dataset` A 4 / 70 lines (fail-closed parent fatals).

### 2.3 Other D+/E functions

| Symbol | CC | Classification |
|---|---|---|
| `load_ohlcv` | D 25 | Profile gate + canonical parse + DST localize. Single public entry. Not promoted. |
| `_read_explicit_profile` | D 24 | Seven-way vendor dispatch. Matches `FORMAT_PROFILES`. Not promoted. |
| `validate_roll_metadata` | E 31 | Three-method validator; R7 warning on segmented. Single-purpose. Not promoted. |
| `save_dataset` | E 34 | Canonical parquet + raw/subtimeframe preserve-or-conflict + derive-mode provenance guard. **QI-01-02.** |

### 2.4 Format-profile allow-list (R17 SoT check)

**Runtime SoT holds for labels.** `study.builder.bind_format_profile_labels` `getattr` returns the live `loader.FORMAT_PROFILE_LABELS` object (`builder_runtime_is_loader=true`). Fallback dict **equals** loader labels today. `api.validate_run_spec` hardcoded set **equals** `FORMAT_PROFILES` (7 tokens). Page `DERIVE_15S_SUPPORTED_PROFILES` equals `api._DERIVE_15S_SUPPORTED_PROFILES` (`quantower_history_exporter` only).

**Literal copies still exist** (loader tuple + labels, builder fallback, api set, page derive frozenset, api `_DERIVE_15S_*`). AGENT_GUIDE R17 documents the `getattr` fallback as intentional. Drift risk is real if one copy is edited. QI-01-06.

### 2.5 Broad-except classification

| Site | Class |
|---|---|
| `loader._profile_timestamp` / `load_ohlcv` `except Exception` → DST nonexistent/ambiguous → `DataValidationError`; else re-raise | *narrow-guard OK* for naive spring-forward / fall-back. H11 mixed-offset **re-raises raw pandas `ValueError`** ("pass `utc=True`") — *fails §3.2.3* (untyped; hint is not an operator control). QI-01-04 |
| `quantower_ticks._localize_utc` same pattern | *narrow-guard OK* (ticks localize naive stamps) |
| `pages/1_Data.py` | **no** `except Exception`. Upload catch is `(DataValidationError, ValueError)` → `st.error(str(exc))`. 15s / subtf / ticks fail closed. Legacy primary never raises on fatal OHLCV (H10) |
| `local_store.py` | no `except Exception`. JSON/OSError skips on inventory; typed `ValueError` on sidecar conflict / derive-without-subtf |

### 2.6 Render-tree extraction candidates (descriptive; not an implementation)

```
pages/1_Data.py
├── helpers (_default_source_timezone … _render_roll_assumptions) — already extracted; 2 remain D-grade
└── module-level script (after last helper ~411 lines)
    ├── local saved datasets (load/delete/refresh)
    ├── instrument / source / format / ingestion-mode widgets
    ├── Sample vs Upload
    ├── 15s-primary: _prepare + _install + diagnostics
    ├── legacy primary: load_ohlcv → validate → tag_session → ALWAYS install
    ├── subtimeframe / tick / rolls
    └── save_dataset
```

---

## 3. Application-quality readout (§3.2 per entry point)

Entry points: Data page (Composer A helpers), `api.load_dataset` / `_load_15s_primary_experiment_data` (Composer B; CLI / Study / Assistant share this path), `local_store.save_dataset`/`load_dataset`.

### 3.1 Checklist

| # | Check | Data page (helpers) | API / CLI / Study / Assistant | Verdict |
|---|---|---|---|---|
| 1 Happy | `sample_data/ES_sample_1m.csv` + vendor fixtures (NT, Sierra, QT 1m, Databento) | 12 / 2 / 2 / 2 / 2 rows, session tagged, clean | same | Pass |
| 2 Empty / 1 bar | 0-row header-only; 1-row | both install, no exception, 0 issues | both accept | Pass (no crash). 0-row is a silent empty frame, not a typed refusal |
| 3 Malformed | see §3.2 matrix | fatals **warn + install** on legacy primary | fatals **ValueError** | **H10 diverge** |
| 4 Stale-state | `_clear_dataset_dependent_state` pops levels/signals/trades/batteries/ticks/provenance | present | n/a | Handoff QI-10: does **not** pop `signal_settings` / `signal_settings_hash` (QI-3 already noted) |
| 5 Composer parity | same CSV through UI helper vs `api.load_dataset` | matrix | matrix | Clean/gap/vendor/15s-HL **parity**. Fatal OHLCV **diverge** (H10). Mixed-offset **both fail** (H11) |
| 6 Honesty | `_render_dataset_summary` always `st.success("Loaded N bars.")` then `st.warning` on issues | success-then-warn on fatals | API raises, no success | H10 honesty |
| 7 Persistence | save → load hash | sample 12-row hash equal; 15s parent+subtf hash equal; schema **2**; v1 still in `SUPPORTED_DATASET_SCHEMA_VERSIONS` | store is shared | Pass. Store does **not** re-validate fatals (H10 persist) |
| 8 Perf envelope | CAI `realistic` (780 1m bars) ingest+validate+tag+save+load | wall **0.0268 s**, max RSS 147524 KB (process) | same store path | Informational only. Overnight gap flagged `significant_gaps` (not fatal). Not a backtest claim |
| 9 Operability | `dataset_id`, `ingestion_provenance`, dropped/sparse diagnostics, roll warnings | 15s provenance + sparse/drop tables | API provenance in experiment state | 15s operability good. Legacy fatals have no identity/provenance flag that they are API-illegal |
| 10 Copy | "Native 1m never auto-deduped" on page + USER_GUIDE | present | n/a | H10 fork itself is **not** named in USER_GUIDE. H11 `utc=True` hint is not an operator control |

### 3.2 Parity matrix (input defect × composer × outcome)

UI = `load_ohlcv` → `validate_ohlcv` → `tag_session` (legacy primary; always `_set_active_dataset_state`). API = `api.load_dataset`. CLI/Study/Assistant = API via `run_experiment`. 15s-primary UI = `_prepare_15s_primary_dataset`; API = `_load_15s_primary_experiment_data`.

| Defect | UI primary | API / CLI / Study / Assistant | 15s-primary UI | 15s-primary API | Diverge? |
|---|---|---|---|---|---|
| Clean 1m / vendor happy | install, 0 fatals | accept | n/a | n/a | no |
| Duplicate timestamp | **install** + fatal `duplicate_timestamps` | **reject** `Dataset validation failed: 1 duplicate timestamps` | n/a (native 1m) | n/a | **yes — H10** |
| `high < low` | **install** + HL + OC-range fatals | **reject** | source validate **reject** | **reject** same message | primary **yes**; 15s **no** |
| Open/close outside H/L | **install** | **reject** | reject if in source | reject | primary **yes** |
| Negative volume | **install** | **reject** | reject | reject | primary **yes** |
| Missing bar (gap > 3×) | install; issues `significant_gaps` (+ `non_monotonic_before_sort` on this fixture) | **accept** (gaps not fatal) | n/a | n/a | no |
| Mixed-offset DST-aware (`01:59-05:00` then `03:00-04:00`) | **load ValueError** "pass utc=True" | **same ValueError** | n/a | n/a | no (both over-closed) — **H11** |
| Naive DST-crossing (`01:59` then `03:00` local) | accept | accept | n/a | n/a | no |
| Mixed-offset on QT profile | **same ValueError** at `_profile_timestamp` (UTC-normalize never reached) | same | n/a | n/a | no — H11 also hits vendor parse |
| 15s misaligned last open (`:46`) | n/a | n/a | accept; **1** parent, **1** dropped | accept; 1 parent | no (locked S1 drop) |
| 15s `high < low` | n/a | n/a | reject `15-second source validation failed` | reject same | no |
| 15s + `format_profile=canonical` | n/a | n/a | reject allow-list | validate_run_spec rejects | no |
| Empty (0 rows) | install 0 | accept 0 | n/a | n/a | no |
| 1 bar | install | accept | n/a | n/a | no |

H10 persist: UI-installed duplicate frame `save_dataset` → reload **5 rows, 1 duplicate**. Store does not re-run `FATAL_OHLCV_CODES`.

### 3.3 Sessions, rolls, ticks, store

- **`tag_session` vs `trading_session_date`.** Thanksgiving-week fixture: `14:00` on 2026-11-26 is still **RTH** (`rth_end=16:00`; no holiday/early-close calendar). `16:00` is ETH. Sunday `18:30` is ETH with `trading_session_date=2026-11-30`; Monday `09:30` is RTH with the same session date. Clocks differ at ETH open. Matches AH §2 item 3 and ASSUMPTIONS “no exchange holiday schedule”. Data layer emits only `session`.
- **Rolls.** `single_contract` valid (warn: no contract column). `external_continuous` valid with unknown adjustment/rule (warnings). `segmented_contracts` valid + R7 “does not adjust OHLC” warning. Matches AUDIT §7 (no silent roll synthesizer).
- **Ticks.** Parser + trusted-root helpers exist; attach is optional and not an ingestion mode (USER_GUIDE). Tick-gated levels → QI-2.
- **Store.** Writes dataset schema **2**; loads v1 and v2. 15s save keeps `ingestion_provenance.ingestion_mode=15s_primary_derive_1m` and `derivation_policy=observed_aligned_15s_to_1m_v2`. Corrupt `meta.json` is skipped by `_scan_dataset_metadata` (narrow-guard). Derive-mode provenance without subtf sidecar is refused.

---

## 4. Prior-audit carry-over status

| Item | Status this slice | Evidence |
|---|---|---|
| **H9** `dataset_id` omits ingest story | **Still open; locked current contract** (`AUDIT_FINAL` §5.1 item 9). Bindings already partition | Identical parent OHLC from 15s-derived vs native 1m → **same** `compute_dataset_id` / `DataIdentity.dataset_id()`. `format_profile` excluded. `source_binding_key` **differs** (source-file hash + `ingestion_mode` / `derivation_policy`). First-draft hash prefixes withdrawn (not reproducible from the published four-bar recipe). Finding QI-01-05 |
| **H10** Data-page fatal OHLCV vs API | **Still present; parked composer fork** (AH §2.1 / AH8). 15s-primary parent path *does* fail-closed | Matrix §3.2. Legacy primary always `tag_session` + `_set_active_dataset_state`. `FATAL_OHLCV_CODES` used on 15s parent and lower-TF, **not** on legacy primary. Store persists duplicates. Finding QI-01-03 |
| **H11** Canonical mixed-offset DST | **Still present; parked fail-closed** (AH §8). Exception untyped. Naive local DST-crossing **works** | `01:59:00-05:00` then `03:00:00-04:00` → pandas 3 `ValueError: Mixed timezones detected. Pass utc=True…` on **canonical and QT-aware**. `utc=True` parses to `06:59Z` / `07:00Z`. Operator cannot pass that flag. Naive `01:59`/`03:00` local accepts on UI helper and `api.load_dataset`. No named test. Findings QI-01-04 (Design limitation), QI-01-07 |
| **W13** micros / R17 | **Closed-verified** (status only) | Vendor happy-path 4/4 profiles load; `FORMAT_PROFILES` is the live catalog |

Locked S1 (do not invert): 15s-primary = QT exporter + `observed_aligned_15s_to_1m_v2`; OHLC-identical 15s resolve lowest volume; native 1m never auto-deduped; omit `ingestion_mode` → `primary`.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Axis | Class | Sev | Conf | Title |
|---|---|---|---|---|---|
| QI-01-01 | code | Maintainability risk | Medium | Verified | `pages/1_Data.py` MI 0.00; D-grade subtf/tick renderers; ~411-line module-level script |
| QI-01-02 | code | Maintainability risk | Medium | Verified | `local_store.py` MI 0.00; `save_dataset` E(34) / 144 lines sidecar/provenance branches |
| QI-01-03 | app | Design limitation | Medium | n/a | H10: legacy primary UI installs fatal OHLCV; API/CLI/Study/Assistant reject |
| QI-01-04 | app | Design limitation | Medium | n/a | H11: parked fail-closed mixed-offset DST CSV (untyped pandas `ValueError`, `utc=True` hint) |
| QI-01-05 | app | Design limitation | Medium | n/a | H9: `dataset_id` still omits `ingestion_mode` / `format_profile`; bindings do not |
| QI-01-06 | code | Maintainability risk | Low | Verified | `format_profile` allow-list is runtime-equal but copied in 5 literals |
| QI-01-07 | code | Test-quality gap | Medium | Verified | No committed H10/H11 cross-composer test (lock-the-fork / mixed-offset recipe) |

No Critical. No High. H9/H10/H11 are carry-over status only: H9 = locked `AUDIT_FINAL` §5.1 item 9; H10 = parked AH §2.1 composer fork; H11 = parked AH §8 fail-closed. None is classified above Medium / `n/a`. H11 is not a §5 “must reject mixed offsets” lock; UTC-normalize stays a parked design choice, not a QI High defect.

---

## 6. Positive verification

What was checked and is fine — do not re-audit:

1. **Vendor R17 happy path** (NinjaTrader, Sierra, Quantower History Exporter 1m, Databento trades) loads on UI helper and `api.load_dataset` with session tags. Sample CSV 12 bars, clean.
2. **15s-primary fail-closed on source fatals** and on `format_profile=canonical`. UI and API reject `high < low` with the same `15-second source validation failed` prefix. Misaligned minute is **dropped**, not synthesized (1 parent / 1 dropped) — locked S1 observed.
3. **Naive DST-crossing local stamps** (`01:59` then `03:00` America/New_York) load on canonical and QT. Named tests already cover naive ambiguous/nonexistent Berlin stamps (`test_load_ohlcv_reports_*_dst_timestamps`).
4. **`dataset_id` parity helper still matches** `DataIdentity.dataset_id()` ↔ `compute_dataset_id` when content+instrument+interval+tz match (H9 probe). `source_binding_key` includes mode/policy. Specific hex prefixes from the first draft are withdrawn.
5. **Store round-trip** on throwaway store: sample hash-identical; 15s parent+`subtimeframe.parquet` hash-identical; schema v2 write / v1+v2 read; derive provenance persisted; derive-without-subtf refused; corrupt meta skipped.
6. **`tag_session` is wall-clock only** (`09:30`–`16:00`). No holiday/early-close calendar — matches ASSUMPTIONS. `session` ≠ `trading_session_date` at ETH open (AH §2 item 3).
7. **Rolls do not rewrite OHLC.** Segmented path emits the R7 discontinuity warning. AUDIT §7 “no silent continuous-contract synthesizer” still holds.
8. **`FATAL_OHLCV_CODES` is a single frozenset on the page** and matches `api.load_dataset` fatal set. 15s parent uses it. Legacy primary does not (H10).
9. **Gaps are not fatal** on either composer (missing-bar and CAI overnight). `significant_gaps` is diagnostic.
10. **Scoped ingest suite 243 passed ×2** (`PYTHONHASHSEED=0` and default). Full `pytest -q` before **and** after this slice: 3966 passed, 5 skipped (135.26 s / 128.26 s). Porcelain: only the two `docs/quality/` files. No Streamlit / private-import leaks in QI-1 library modules.
11. Nothing in this slice was verified as a correct backtest, metric, or Study result.

---

## 7. Handoffs to other slices

| To | Observation (not a QI-1 finding) |
|---|---|
| QI-2 | `local_store` levels namespace (`save_levels` / `load_levels` / active hash). Tick-gated APOC / rolling POC refusals. `trading_session_date` lives in `levels/session_date.py`. Holiday-unaware `session` tags feed RTH-gated levels. |
| QI-3 | `_clear_dataset_dependent_state` pops `signals` but not `signal_settings` / `signal_settings_hash`. |
| QI-4 | 0-row / fatal-OHLCV frames can reach `simulate_trades` on Composer A if the operator continues from Data. R12 `parse_interval` is the loader helper. |
| QI-6 | `api.load_dataset` is the H10 Composer B side. `validate_run_spec` format-profile **literal** (QI-01-06). `DataIdentity` / `source_binding_key` / `data_artifact_key` (H9; artifact key includes `format_profile`, not `ingestion_mode`). |
| QI-7 | Studies `getattr` fallback for `FORMAT_PROFILE_LABELS` (intentional R17). 15s file without `ingestion_mode` remains `primary` (locked omit). |
| QI-10 | 170 `st.session_state` lines; module-level page; leftover `signal_settings*` after dataset clear; classic `AppTest` feasibility for page 1. |
| QI-11 | Add H10 tests that **lock the current fork** (fail if UI starts rejecting or API starts accepting). Add H11 mixed-offset canonical recipe. Mutation on `loader.py` / `derive.py`. |
| QI-13 | USER_GUIDE Data H2 does not name the H10 fork or H11 mixed-offset over-close. ASSUMPTIONS documents native-1m diagnostic-only dups, not API reject. |
| QI-14 | CAI realistic ingest 0.027 s on this VM (780 bars). Overnight `significant_gaps` is expected. |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | H10 parked-fork sentence (UI warn vs API fatal); H11 mixed-offset over-close; H9 identity omit |
| `docs/USER_GUIDE.md` Data H2 | Same three; `utc=True` is not an operator control; holiday/early-close wall-clock reminder |
| `docs/AGENT_GUIDE.md` R17 | Single SoT for `FORMAT_PROFILES` if QR deletes literals; H10/H11 named-test list |
| `docs/ARCHITECTURE.md` | `dataset_id` vs `source_binding_key` vs `data_artifact_key` (H9); Data-page fatal vs API |
| `docs/METRICS_GLOSSARY.md` | none (no metrics in this slice) |

---

## Appendix A — probe script (pasted; not committed)

Isolation wrapper:

```bash
export THESISTESTER_STORE_DIR=/tmp/qi1-store-probes
mkdir -p "$THESISTESTER_STORE_DIR"
unset OPENAI_API_KEY XAI_API_KEY
PYTHONPATH=/workspace python3 /tmp/qi01_probes.py
```

UI primary helper used for the matrix (mirrors the legacy primary install path):

```python
raw = load_ohlcv(path, **loader_kw)
report = validate_ohlcv(raw)
fatals = [i.code for i in report.issues if i.code in FATAL_OHLCV_CODES]
df = tag_session(raw, "ES")  # always installed
```

H11 recipe (canonical):

```text
timestamp,open,high,low,close,volume
2026-03-08 01:59:00-05:00,100,101,99,100.5,10
2026-03-08 03:00:00-04:00,100.5,102,100,101.5,20
```

H9 recipe: four on-grid 15s QT bars → `derive_complete_parent_ohlcv` → `tag_session`; write the parent OHLC as a naive 1m CSV; compare `compute_dataset_id` and `source_binding_key`.

Full transcript: `/tmp/qi1-probe-results.json`.

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
