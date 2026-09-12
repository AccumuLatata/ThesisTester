# QI-03 — Setup, confluence, signals, triggers, OTF

**Slice:** QI-3 (research-only)
**Status:** Completed
**Audited commit:** `e30cc48` (`e30cc48c3e3b97af3e95f932be9ce27e28598328`) — `main` after [#479](https://github.com/AccumuLatata/ThesisTester/pull/479) (QI-0)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi03-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 12 (C/H/M/L = 0/3/6/3)
**Time spent:** one agent run on 2026-09-12.

Locked inputs treated as premises (not re-audited): `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1. `_check_touch`, candidate sort key, and 3c four-rule math were not re-audited (DA0 / AUDIT S3).

## Commands run (verbatim)

```bash
python3 --version
git rev-parse HEAD
git log -1 --format='%h %ad %s' --date=short

export THESISTESTER_STORE_DIR=/tmp/qi03-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no

radon cc thesistester/setup.py thesistester/engine/signals.py \
  thesistester/engine/signals_3c.py thesistester/engine/confluence.py \
  thesistester/engine/anchor_confluence.py thesistester/engine/naked.py \
  thesistester/engine/candidate_level.py thesistester/engine/otf.py \
  thesistester/engine/otf_filter.py thesistester/engine/otf_integration.py \
  thesistester/engine/__init__.py thesistester/visualization/signals_chart.py \
  thesistester/visualization/chart_window.py pages/3_Setup_Builder.py \
  pages/6_Signals.py -s -n D --total-average
radon mi <same files> -s
vulture <same files> --min-confidence 60
rg -n 'except Exception|except:' <same files>
rg -c 'st\.session_state' pages/3_Setup_Builder.py pages/6_Signals.py
rg -n 'confirm_3bar' thesistester pages docs

# probes
export THESISTESTER_STORE_DIR=/tmp/qi03-store-probes
PYTHONPATH=/workspace python3 /tmp/qi03_probes.py

# scoped suite twice (identical file set)
pytest -q -p no:cacheprovider tests/test_setup_config.py \
  tests/test_setup_builder_helpers.py tests/test_phase4_engine.py \
  tests/test_signals_3c.py tests/test_signals_3c_trigger_timeframe.py \
  tests/test_signals_fade.py tests/test_signals_page_helpers.py \
  tests/test_signals_trigger_timeframe_dst.py \
  tests/visualization/test_signals_chart.py tests/test_ah6_base_columns.py
PYTHONHASHSEED=0 pytest -q -p no:cacheprovider <same files>

export THESISTESTER_STORE_DIR=/tmp/qi03-store-after
pytest -q --tb=no
git status --porcelain
```

Probe script lives under `/tmp/qi03_probes.py` (not committed). Transcript: `/tmp/qi03-probe-results.json`.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-0 exclusive ownership; 15 files)**

| Path | Role in this slice |
|---|---|
| `thesistester/setup.py` | Canonical build/validate/normalize |
| `thesistester/engine/signals.py` | `generate_signals`, `_check_*`, `_project_zones_to_trigger_df`, leftover `confirm_3bar` |
| `thesistester/engine/signals_3c.py` | Base + HTF 3c detectors |
| `thesistester/engine/confluence.py` | `global_cluster` zones |
| `thesistester/engine/anchor_confluence.py` | `anchor_rules` zones |
| `thesistester/engine/naked.py` | Per-level naked flags |
| `thesistester/engine/candidate_level.py` | 3c adapters |
| `thesistester/engine/otf.py` | OTF state machine |
| `thesistester/engine/otf_filter.py` | Pure filter |
| `thesistester/engine/otf_integration.py` | Resolve + apply wrapper |
| `thesistester/engine/__init__.py` | Re-exports (incl. QI-4 symbols; not dual-owned) |
| `thesistester/visualization/signals_chart.py` | `build_signals_chart` |
| `thesistester/visualization/chart_window.py` | Time-window helpers |
| `pages/3_Setup_Builder.py` | Setup authoring + library CRUD |
| `pages/6_Signals.py` | Classic generate path |

Read-as-spec (QI-13 owns): `docs/otf-filter.md`, `docs/ARCHITECTURE.md` session/OTF notes, `docs/USER_GUIDE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/AGENT_GUIDE.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md` (DA0).

Read-as-call-site only (not owned): `thesistester/api.py` `build_setup` / `generate_signals`; `thesistester/study/expand.py` `_build_setup_for_cell`; `pages/14_Research_Assistant.py` min-valid widget; `thesistester/engine/backtest.py` leftover `confirm_3bar` fill; `pages/1_Data.py` dataset-clear of `signals`.

**Skipped**

- Mutation testing of `generate_signals` — QI-11.
- Full-suite coverage XML re-measure — QI-0 numbers reused (`signals.py` 84%, `signals_3c.py` 86%, `setup.py` 89%).
- `mypy` / `bandit` this run (binaries not on PATH; QI-0 already recorded repo-wide 163 mypy errors / bandit High+Medium elsewhere). No QI-3-specific security finding.
- Re-audit of `_check_touch`, candidate sort key, 3c four-rule math.
- Browser AppTest of pages 3/6 — no product change; §3.2 items verified via static copy + `/tmp` probes. Handoff QI-10 for classic `AppTest` feasibility.

---

## 2. Code-quality readout

158 blocks in scope. Average CC **B (7.37)**.

### 2.1 Metric table (QI-3 files only)

| Metric | Value | Trigger hit? |
|---|---|---|
| F-grade (CC ≥ 41) | `generate_signals` **120** · `validate_setup_config` **69** · `detect_3c_setups_with_trigger_timeframe` **59** · `detect_3c_setups` **55** · `_sync_editor_widget_state` **47** | Yes — mandatory findings QI-03-01…04 |
| D-grade (21–40) | `build_signals_chart` 29 · `detect_anchor_confluence_zones` 27 · `detect_confluence_zones` 21 | Read; not promoted (single-purpose) |
| Physical lines > 150 | `generate_signals` 588 · `detect_3c_setups_with_trigger_timeframe` 297 · `_sync_editor_widget_state` 223 · `detect_3c_setups` 205 · `validate_setup_config` 204 · `build_signals_chart` 185 | Yes |
| MI | `signals.py` **0.00** · `3_Setup_Builder.py` **0.00** · `6_Signals.py` **0.00** · `setup.py` 14.80 · others A (23.9–100) | Yes — structural |
| Broad `except` | 3: `otf_filter.py` (re-raises `ValueError`) · `pages/6_Signals.py` generate · `pages/6_Signals.py` chart | Classified below |
| `vulture` ≥60 | 13 candidates. Real unused: `_check_confirm_3bar`, `_normalize_confirm_3bar_params`, `pages/6` `ANCHOR_DIAGNOSTIC_COLUMNS`, `_get_stored_signal_settings`. False friends: `apply_configured_otf_filter` / `to_summary_dict` / `classify_zone_triggers` (used by QI-4/6/8) | confirm_3bar → QI-03-07 |
| Streamlit in library (QI-3) | 0 | none |
| Cross-module private imports | 0 in scope | none |
| `st.session_state` matching lines | page 3: **82** · page 6: **60** | QI-10 graph |
| `# noqa` / `# type: ignore` | 5 (float coercion + pandas `== False`) | none |
| Coverage (QI-0) | all QI-3 library modules ≥ 76% (`chart_window` 76%; rest ≥ 84%) | none < 70% |

### 2.2 Trigger protocol (not a shared protocol)

There is **no ABC, dispatch table, or common protocol class**. Public set is lockstep:

```text
thesistester/engine/signals.py VALID_TRIGGERS
thesistester/setup.py         VALID_TRIGGERS
= {touch, reject, break, reclaim, 3c, fade, continuation}
```

| Family | Symbols | Wiring |
|---|---|---|
| Simple | `_check_touch` / `_check_reject` / `_check_break` / `_check_reclaim` | `if/elif` inside `generate_signals` |
| Approach-side | `_check_fade` / `_check_continuation` → `_check_approach_side_trigger` | First-class tokens, not fade-variants |
| 3c | `detect_3c_setups` / `detect_3c_setups_with_trigger_timeframe` + `from_*_zones` | Separate pipeline; `_project_zones_to_trigger_df` only on non-base 3c |
| Legacy | `_check_confirm_3bar` | **Not** in `VALID_TRIGGERS`; not called by `generate_signals` |

`generate_signals` phases: gate → param normalize → `_prepare_trigger_dataframe` → zone-level naked admission → 3c / approach / simple branch → DataFrame. Extraction loci (descriptive): TF prep, zone admission, 3c row-mapper (base vs HTF loops are near-duplicates), simple dispatch table. **Not an implementation.**

`confluence_mode`: two detectors (`detect_confluence_zones` vs `detect_anchor_confluence_zones`) with no shared abstraction. Engine `generate_signals` does not call either — it consumes a pre-built `zones` frame. API + page 6 both branch on mode before calling the engine.

### 2.3 Broad-except classification

| Site | Class |
|---|---|
| `otf_filter.py` `pd.to_datetime(..., errors="raise")` → `ValueError` | *narrow-guard OK* |
| `pages/6_Signals.py` generate `except Exception` + `st.exception` | *hides defect* in the §3.2.3 sense (raw traceback in UI) — QI-03-05 |
| `pages/6_Signals.py` chart `except Exception` | same |

### 2.4 D-grade notes (classified, not findings)

- `detect_confluence_zones` / `detect_anchor_confluence_zones`: one algorithm each; CC is the greedy/rule loop.
- `build_signals_chart` (185 lines): hover/window/overlay branches. Visualization-only (page caption). Handoff QI-14 if chart rerender cost matters.

---

## 3. Application-quality readout (§3.2 + QI-3 checks)

Entry points: Setup Builder (page 3), Signals (page 6), engine `generate_signals`, `setup.build_setup_config` / `validate_setup_config`. API/Study/CLI/Assistant consume the same `setup.py` contract via QI-6/QI-7 (call-site inventory below).

### 3.1 Checklist

| # | Check | Result |
|---|---|---|
| 1 | Happy path on synthetic / CAI | `detect_confluence_zones` + `generate_signals(touch, both)` on CAI realistic (780 bars) → 780 zones / 1560 signal rows in 0.18 s. **Not** a claim that those signals or any downstream backtest are correct. |
| 2 | Empty / minimal | Empty `zones` → 0-row frame whose columns **equal** `_SIGNAL_COLUMNS` (51). Empty setup name → `"Setup name must not be empty."` |
| 3 | Malformed | `trigger="not_a_trigger"` / `"confirm_3bar"` and `direction="sideways"` fail closed (`ValueError` / validate error list). Page 6 generate wraps remaining exceptions in `st.exception` (QI-03-05). |
| 4 | Stale-state | Dataset load pops `signals` (QI-1). Setup Builder save / Set active does **not** pop `signals`. Levels page does not mention `signals`. Page 6 invalidates only on **save** via `_validate_signal_artifact_identity_for_save`. QI-03-12 + QI-10 handoff. |
| 5 | Composer parity | Trigger table §3.2. AO1 `min_valid=0` table §3.3. Signals generate **bypasses** `api.build_setup` (AH §2 two-composer lock — recorded as maintainability, not a collapse proposal). |
| 6 | Honesty | No confirmatory p-value / “proven” copy on pages 3/6. OTF stored-not-applied copy is present (quote §3.4). DA0 **missing** at direction widgets (QI-03-08). Naked zone-level **missing** on Setup Builder (QI-03-09). |
| 7 | Persistence | Setup library save→load under `/tmp` store: all 15 execution keys including `min_valid_confluences=0` round-tripped; save adds `setup_id` / `dataset_id` / OTF hash+version; delete empties the namespace. |
| 8 | Perf envelope | CAI realistic: zones 0.030 s, `generate_signals` 0.151 s. Informational; not compared as a correctness claim vs `SIMULATE_PERF.md`. Handoff QI-14. |
| 9 | Operability | OTF hash/version caption on Signals. Signal table **omits** `trigger_timestamp` / 3c fields (QI-03-11). |
| 10 | Copy consistency | Trigger tokens identical on pages 3/6. Naked labels differ (“Naked only” vs “Naked / untested levels only”). Admit copy lives on Setup Builder only (correct). |

### 3.2 Exit: trigger × composer parity

Probe: `/tmp/qi03_probes.py` section `triggers` on `e30cc48`. `accepted` = no validate errors and no `ValueError` from `generate_signals` / `api.build_setup`.

| Trigger | Engine `generate_signals` | `validate_setup_config` | `api.build_setup` | UI picker p3/p6 | Study expand → `build_setup` | CLI / Assistant (via API) |
|---|---|---|---|---|---|---|
| `touch` | accepted | accepted | accepted | listed | same gate | same gate |
| `reject` | accepted | accepted | accepted | listed | same | same |
| `break` | accepted | accepted | accepted | listed | same | same |
| `reclaim` | accepted | accepted | accepted | listed | same | same |
| `fade` | accepted | accepted | accepted | listed | same | same |
| `continuation` | accepted | accepted | accepted | listed | same | same |
| `3c` | accepted | accepted | accepted | listed | same | same |
| `confirm_3bar` | **rejected** | **rejected** | **rejected** | absent | rejected | rejected |
| unknown | rejected | rejected | rejected | n/a | rejected | rejected |

`VALID_TRIGGERS` lockstep engine ↔ setup: **true**. Fade/continuation are first-class (DA4), not touch variants.

`simulate_trades` still has `elif trigger == "confirm_3bar"` (QI-4). WFA special-cases `confirm_3bar` entry index (QI-5). Those are leftover **fill** paths for hand-built rows (`tests/test_ah5_sl_first_3c_entry.py`), not generation.

### 3.3 Exit: setup-normalization call-site inventory

Canonical: `thesistester/setup.py` `build_setup_config` + `validate_setup_config` + `normalize_trigger_timeframe` / `normalize_otf_filter_config` / `_normalize_3c_params` / `_normalize_approach_side_params`.

| # | File · symbol | Composer | Role | Uses `build_setup_config`? | Notes |
|---|---|---|---|---|---|
| 1 | `setup.build_setup_config` | library | Build + normalize | — | Defaults `confluence_mode=global_cluster`, `min_valid=1`, TF `base`, OTF/entry_window canonical |
| 2 | `setup.validate_setup_config` | library | Validate (errors list, no raise) | — | F 69. Rejects `BASE_COLUMNS`/`close` (AH6/H3 still true; `tests/test_ah6_base_columns.py`) |
| 3 | `pages/3._build_current_editor_config` | UI Setup | Build | **Yes** | Then attaches `setup_id`/`dataset_id` |
| 4 | `pages/3._sync_editor_widget_state` | UI Setup | Widget sync + soft fallback | No | F 47; `_safe_*` parallel to validator |
| 5 | `pages/3._default_editor_config` / `_seed_editor_config` | UI Setup | Default-fill / hydrate | Partial (OTF/entry_window helpers) | Parallel product defaults |
| 6 | `pages/3` save | UI Setup | Validate → `save_setup` | Yes (via #3) | |
| 7 | `pages/6` saved-setup generate | UI Signals | Consume saved dict | **No** | Coerces with `_safe_*`; global_cluster **forces `min_valid=1`**; 3c uses local `_normalize_3c_params` |
| 8 | `pages/6` manual generate | UI Signals | Inline widgets | **No** | Third authoring copy; anchor-only sets `min_valid=0` |
| 9 | `pages/6._normalize_3c_params` | UI Signals | Normalize | Duplicate of `setup._normalize_3c_params` + `_source_mode` | |
| 10 | `api.build_setup` | API/CLI/Assistant | Filter `_SETUP_EXECUTION_KEYS` → #1 → #2 | **Yes** | QI-6 owned |
| 11 | `api.validate_run_spec` setup section | API | Schema + range + #10 | Yes | Duplicates some numeric ranges. QI-6 |
| 12 | `api.generate_signals` | API | Validate + zones + engine | No BSC (validate only) | QI-6 |
| 13 | `study.expand._build_setup_for_cell` | Study | Assemble kwargs → #10 | Indirect | `global_cluster` **hardcodes `min_valid=1`**. QI-7 |
| 14 | `study.schema` / `builder._emit_constants` | Study | Spec constants | No | QI-7 |
| 15 | `pages/15` widgets | Study UI | Constants/factors | No | `min_valid` widget min 0. QI-7 |
| 16 | `pages/14` Assistant form | Assistant | Draft merge | No | `min_value=1` — cannot author AO1. QI-9 |
| 17 | `persistence.save_setup` | store | Canonicalize OTF/entry_window | No validate | QI-1 owned file; QI-3 consumes |

**AO1 `min_valid_confluences: 0` (probe `ao1`)**

| Path | Outcome |
|---|---|
| `build_setup_config` | stores `0` |
| `validate_setup_config` | `[]` (empty rules allowed iff min_valid==0) |
| `api.build_setup` | accepted, `min_valid=0` |
| `api.generate_signals` (ONH-only frame) | ran; 780 zones, 6 signal rows, **no** `otf_*` columns |
| Study expand `anchor_rules` + empty partners | accepted, `min_valid=0` |
| Study expand `global_cluster` + constants `0` | **emits `1`** (QI-7) |
| Assistant widget | `min_value=1` (QI-9) |
| Setup Builder / Signals manual | sets `0` when no partners |

### 3.4 OTF stored-not-applied (copy verified)

Page caption (`pages/6_Signals.py`):

> "Detect confluence zones and generate candidate entry signals. OTF admission is applied later in Backtest, Grid, and Walk-forward — not on this page."

Saved-setup caption: *"Signals keep the complete candidate population."* Matches `ARCHITECTURE.md` §OTF composition and AH §2 item 4.

Probe: engine `generate_signals` output has **zero** `otf_*` columns. `apply_configured_otf_filter` with disabled config accepted 2/2 candidates.

### 3.5 Signals table vs `_SIGNAL_COLUMNS`

Contract: 51 columns in `thesistester/engine/signals.py` `_SIGNAL_COLUMNS`. `ARCHITECTURE.md` points at that list (DA4: `approach_side` is **not** in the contract).

Page 6 display subset (18 names): includes post-engine `setup_name` (not in contract). Omits 33 contract columns including `trigger_timestamp`, `trigger_timeframe`, `tested_level_price`, and the 3c field set. Preview subset — operability gap for HTF/H14 (QI-03-11).

### 3.6 Setup library CRUD

Namespace: `{THESISTESTER_STORE_DIR}/setups/{setup_id}/meta.json` (`schema_version=1`, `kind=setup`). Operations: `save_setup` / `load_setup` / `list_saved_setups` / `delete_setup`. Probe round-trip of an AO1 config: 15/15 exec keys identical; listed=1; after delete=0. Fail-closed copy on page 3 for unavailable levels / validate errors / invalid OTF on load.

### 3.7 DA0 and naked labels

DA0 (`touch` + `both` + `single_position` is long-only) is documented in `USER_GUIDE.md` Exposure table and `ASSUMPTIONS` §4b. **Not** on page 3 or page 6 direction `selectbox` (no `help=`). QI-03-08.

Naked admission is zone-scoped (`_naked_count` on `level_names` at zone `bar_index`; 3c per-level flags are metadata after zone filter). Signals manual radio help: *"'any': at least one level in the zone must be naked."* Setup Builder toggle/radio have **no** help and no “zone” wording. QI-03-09.

---

## 4. Prior-audit carry-over status

| Item | Status this slice | Evidence |
|---|---|---|
| **H14** HTF stale developing levels | **Still open** (reproduced, not re-audited as a new defect class) | Probe `h14`: 5-min window 09:30–09:35, `dVWAP` at minute 1 = **5200.125**, at `base_end` = **5200.500**, Δ = **0.375** points. `_project_zones_to_trigger_df` remaps `bar_index`→0 and `timestamp`→HTF end, **prices unchanged**. Simple `touch`+`5min` on the early-window zone → **0** rows (not in `trigger_rows_by_base_end`). Same zone at `base_end` → 2 rows. `3c`+`5min` on the early zone → 1 row with `zone_mid`/`tested_level_price` still **5200.125**. Decision T is HTF close (not a future-bar leak). Finding QI-03-06. |
| **§5.5 `confirm_3bar` delete?** | **Still present; dead for generation; alive for hand-built fill** | Helpers + `_normalize_confirm_3bar_params` remain. Not in `VALID_TRIGGERS`. Rejected by engine/validate/`build_setup`. UI pickers omit it. `vulture` marks helpers unused. `simulate_trades` / WFA / AH5 tests still consume hand-built rows. Finding QI-03-07. |
| **H3 / AH6 `BASE_COLUMNS`** | **Closed-verified** (probe tests exist; not re-audited) | `validate_setup_config` still rejects `close` and all `BASE_COLUMNS`. `tests/test_ah6_base_columns.py` present (P1–P3 + parametrized). Not a finding. |

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Axis | Class | Sev | Conf | Title |
|---|---|---|---|---|---|
| QI-03-01 | code | Maintainability risk | High | Verified | `generate_signals` F(120) / MI 0.00 / 588 lines / ad-hoc trigger branches |
| QI-03-02 | code | Maintainability risk | High | Verified | 3c detectors F(55/59) + duplicated HTF mapping loop |
| QI-03-03 | code | Maintainability risk | High | Verified | `validate_setup_config` F(69) is the five-composer setup contract |
| QI-03-04 | code | Maintainability risk | Medium | Verified | `_sync_editor_widget_state` F(47); Setup Builder MI 0.00 |
| QI-03-05 | both | Maintainability risk | Medium | Verified | Signals page MI 0.00; generate/chart `except Exception` + `st.exception` |
| QI-03-06 | app | Design limitation | Medium | Verified | H14 still open: non-base 3c keeps early-window developing-level prices |
| QI-03-07 | code | Design limitation | Low | Verified | `confirm_3bar` residual (L3 / §5.5 still open) |
| QI-03-08 | app | UX/operability gap | Medium | Verified | DA0 long-only lock not disclosed at direction widgets |
| QI-03-09 | app | UX/operability gap | Low | Verified | Naked admission is zone-level; Setup Builder does not say so |
| QI-03-10 | code | Maintainability risk | Medium | Verified | Setup normalization fan-out (BSC vs page-6 inline vs Study/API copies) |
| QI-03-11 | app | UX/operability gap | Low | Verified | Signals table hides HTF/3c contract columns |
| QI-03-12 | app | UX/operability gap | Medium | Strong | Changing setup does not invalidate in-session `signals` |

No Critical. No Verified defect that contradicts a locked contract. H14/L3 are status of known open items.

---

## 6. Positive verification

What was checked and is fine — do not re-audit:

1. **`VALID_TRIGGERS` lockstep** engine ↔ setup. All seven public triggers accepted by `validate_setup_config`, engine `generate_signals`, and `api.build_setup`. Fade/continuation are first-class.
2. **`confirm_3bar` cannot be generated** on UI / validate / engine / `build_setup`. Product generation is closed.
3. **OTF is not applied at signal generation.** Engine output has no `otf_*` columns. Signals page copy states stored-not-applied. Matches AH §2 item 4 / `ARCHITECTURE.md` / `docs/otf-filter.md`.
4. **AO1 `min_valid_confluences: 0`** is accepted by `build_setup_config`, `validate_setup_config`, `api.build_setup`, and Study expand `anchor_rules` + empty partners. Setup Builder / Signals manual set 0 when no partners.
5. **Setup library CRUD** under throwaway store: save→load preserves execution keys including AO1; delete removes the row.
6. **Empty zones** return a schema-stable empty `_SIGNAL_COLUMNS` frame. Bad trigger/direction fail closed with typed messages.
7. **H3/AH6 still holds:** `BASE_COLUMNS` / `close` rejected in `validate_setup_config`; AH6 probe tests exist.
8. **Simple HTF vs 3c zone handling matches the audit description:** simple triggers keep only `base_end` zones; 3c projects intra-window zones and keeps their prices. (Status of H14, not a new class.)
9. **`generate_signals` determinism** on the CAI realistic fixture: two runs, identical SHA-256 of CSV bytes. Scoped suite 366 passed ×2 with `PYTHONHASHSEED=0` and default.
10. **No Streamlit import and no private-import leaks** in QI-3 library modules. `otf_filter` broad-except is a narrow pandas→`ValueError` translation.
11. **Naked filter is documented in the engine docstring** as zone-level (`any`/`all` on `level_names`). Signals manual radio repeats that.
12. Nothing in this slice was verified as a correct backtest, metric, or Study result.

---

## 7. Handoffs to other slices

| To | Observation (not a QI-3 finding) |
|---|---|
| QI-1 | `save_setup` / `load_setup` live in `local_store.py`. Dataset clear pops `signals` but not `signal_settings` / `signal_settings_hash`. |
| QI-2 | Levels recalc does not clear signal artifacts. |
| QI-4 | `simulate_trades` leftover `confirm_3bar` fill (`bar3_stop_limit_fill`); DA0 occupancy is an exposure/admission concern at Backtest widgets. |
| QI-5 | `walk_forward.py` special-cases `confirm_3bar` entry-bar index. |
| QI-6 | Owns `api.build_setup`, `validate_run_spec` setup section (duplicate ranges), `api.generate_signals`. Classic Signals does not call these (AH §2 lock). |
| QI-7 | `_build_setup_for_cell` hardcodes `min_valid=1` for `global_cluster`. Studies page does not call `build_setup_config`. |
| QI-8 | `classify_zone_triggers` / `_classify_zone_triggers_detail` consumed by journal; vulture false friend. |
| QI-9 | Assistant setup form `st.number_input(..., min_value=1)` cannot author AO1 `min_valid=0`. |
| QI-10 | Session-key graph for `setup_config`, `signals`, `signal_settings*`; stale-state matrix; classic `AppTest` feasibility. |
| QI-11 | Mutation sample on `generate_signals` / `signals_3c`; page-helper vs AppTest coverage of pages 3/6. |
| QI-13 | DA0 / naked / H14 / confirm_3bar living-doc wording; USER_GUIDE Setup/Signals H2 vs widgets. |
| QI-14 | `generate_signals` 0.15 s on CAI realistic (780 bars / 1560 rows); chart CC 29. |

---

## 8. Docs that would need amending in QR (list only)

| Doc | Why QR might touch it |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | H14 first-class if left as-is; confirm_3bar residual; DA0 already §4b |
| `docs/ARCHITECTURE.md` | Signal display vs `_SIGNAL_COLUMNS`; stale `signals` after setup change; session keys `signal_settings*` leftover after dataset clear |
| `docs/USER_GUIDE.md` | DA0 at Setup/Signals direction; zone-level naked on Setup Builder; OTF copy already OK |
| `docs/AGENT_GUIDE.md` | Setup-normalization single source of truth; trigger protocol if QR-C extracts one |
| `docs/otf-filter.md` | No change required for stored-not-applied (already true) |
| `docs/POINT_IN_TIME_GUARANTEES.md` | confirm_3bar / H14 wording if QR deletes or snaps projection |
| `docs/ANCHOR_CONFLUENCE.md` | AO1 Assistant/Study global_cluster divergences (if those slices fix) |
| `docs/METRICS_GLOSSARY.md` | Only if QR adds a signal-table glossary (none today for preview columns) |

**Not amended in this slice.**

---

## 9. Probe excerpts (not committed)

H14 quantification (drifting session VWAP, 5-min trigger, zone at minute 1):

```python
# /tmp/qi03_probes.py — h14
work["dVWAP"] = compute_session_vwap_levels(frame, instrument="ES", enabled=True)["dVWAP"]
trig = _prepare_trigger_dataframe(work, "5min")
win = trig.iloc[0]  # 2026-06-02 09:30 → 09:35
early, end = int(win["base_start_bar_index"]) + 1, int(win["base_end_bar_index"])
# early_dVWAP=5200.125  end_dVWAP=5200.500  staleness=0.375
projected = _project_zones_to_trigger_df(zone_at_early, trig)
# prices_unchanged True; timestamp=HTF end; bar_index=0
generate_signals(..., trigger="touch", trigger_timeframe="5min")  # 0 rows
generate_signals(..., trigger="3c", trigger_timeframe="5min")     # 1 row @ 5200.125
```

Trigger parity + AO1 + CRUD + empty schema: same script sections `triggers`, `ao1`, `crud`, `empty_malformed`, `otf`. Full JSON: `/tmp/qi03-probe-results.json`.

### Suite identity (guardrail 2)

| Run | Result |
|---|---|
| Before (`/tmp/qi03-store-before`) | **3966 passed, 5 skipped** in 153.47 s, exit 0 |
| After (`/tmp/qi03-store-after`) | **3966 passed, 5 skipped** in 145.19 s, exit 0. Same pass/fail/skip. |

Scoped QI-3-related files: **366 passed** in 2.03 s and 1.86 s (`PYTHONHASHSEED=0`). Identical pass/fail/skip.
