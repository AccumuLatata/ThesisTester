# Level Catalog Contract — Implementation Plan (LC)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-18  
**Status:** **LC0 — plan lock.** LC1–LC4 not started.  
**Series code:** **LC** (Level Catalog)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  

**Inputs:** 2026-08-18 levels-catalog audit (compute vs StudySpec vs Assistant vs suggested defaults). Engine already emits prior-profile twins and `Pivot_1m_*` columns. Catalogs do not match.

**Does not reopen:** R9–R22 milestone text; AH0–AH6; RS execute/in-process runner; SB emit language; SIA ingest defaults; SW clocks; Help-corpus *path* moves; `compute_all_levels` additive keyword defaults; profile typical-price approximation; new level-family compute (developing H/L, IB, rolling VAH/VAL, …).

**Related living docs (amend only the sentence that is newly true, in the PR that makes it true):**  
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/STUDY_RUNNER.md`, `docs/ARCHITECTURE.md` (catalog ownership only), `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md` (one catalog sentence if it currently overclaims).

**Help corpus:** paths stay frozen (`docs/README.md` maintenance rule 2). Do **not** add a new Help H2 for this series.

---

## 1. Purpose

The level **engine** is ahead of the level **catalog**.

Eight prior-profile columns are computed on every levels frame and are already selectable on Levels / Setup Builder / Signals, but StudySpec fail-closed rejects them. Pivot StudySpec tokens are spelled differently from the columns the engine emits, so a validated study can run with that core silently dropped (study expand sets min=max=N, so the cell zeros). Suggested defaults advertise `VWAP_rolling_1h`; Assistant omitted-key defaults also expand widget catalogs (`15min`/`1h` VWAP, `1h`/`4h` POC, SMA 9/20/100) that product defaults do not compute.

This series makes the **token contract complete and correct** for what the engine already emits. It does **not** add new price series.

Series complete when:

1. Every always-on prior-profile column is a StudySpec token.
2. Every pivot token equals the emitted column name.
3. Suggested / Assistant catalogs cannot advertise a token that default settings do not imply (unless a live frame or explicit `study.levels` window supplies it).
4. Headless `api.generate_signals` / `run_experiment` / study cells fail-close on missing global-cluster columns the same way anchor-rules already does. Classic Signals saved-setup blockers stay; the confluence library stays permissive.

---

## 2. Locked contracts (do not invert)

An LC PR that “simplifies” any of these is out of scope and must be rejected.

1. **Engine column strings for existing families stay as emitted today.** Do **not** rename `Pivot_1m_High` → `Pivot_1min_High`. Do **not** rename `dSinglePrint_30m_*`. Catalogs move to the engine, not the other way around.
2. **`compute_all_levels` keyword defaults stay additive / mostly-off** for Stage 1–8 gates (`pivots_enabled=False`, …). Product defaults live in `DEFAULT_LEVELS_SETTINGS`. Do **not** flip those API defaults in this series.
3. **Profile math stays the bar typical-price MVP** `(H+L+C)/3` into one tick bin, 70% VA, `shift(1)` prior period. No VAP rewrite.
4. **`detect_confluence_zones` library contract stays permissive** (missing columns skipped; all-missing → empty frame). LC4 fail-closes at the **API / generate_signals** boundary only — same pattern as today’s anchor-rules missing-column `ValueError`.
5. **`validate_setup_config` still cannot see a levels frame.** It keeps rejecting `BASE_COLUMNS` and hit diagnostics (AH6). Column-existence checks stay in `api.py` when a frame is present.
6. **Hit flags stay non-levels:** `prev30mVWAP_hit_m1` / `prev30mVWAP_hit_m5` remain in `NON_LEVEL_OUTPUT_COLUMNS`.
7. **Gated families stay gated in StudySpec:** `prev30mVWAP*` and `Pivot_*` are admitted only when the matching enable flags are true after `{**DEFAULT_LEVELS_SETTINGS, **study.levels}` merge. LC2 changes the *spelling* of pivot tokens, not the gate.
8. **Rolling VWAP/POC tokens are never static.** They appear only from `vwap_windows` / `poc_windows`.
9. **No `LEVEL_ENGINE_VERSION` bump.** LC does not change computed columns or cache identity. Persisted snapshots stay valid.
10. **Goldens are not regenerated.** No `engine/backtest.py`, no `intrabar.py`, no golden parquet/CSV edits.
11. **Help-corpus paths stay frozen.**
12. **Parked compute stays parked** (§8). Do not emit `dHigh`, `RTH_High`, `dVAH`, `VAH_rolling_*`, IB, `OR_Mid`, `pVWAP`, or `15min` MAs in this series.

### 2.1 Product decisions locked by this plan

| Topic | Decision | Not in this series |
|---|---|---|
| Prior-profile twins | Admit all nine compute columns: `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC` | Developing `dVAH`/`dVAL`/`dPOC`; rolling VAH/VAL |
| Pivot spelling | Engine labels win: `Pivot_1m_*` `Pivot_5m_*` `Pivot_30m_*` `Pivot_4h_*` | Renaming engine columns to `1min`; classic floor pivots (PP/R1) |
| Suggested VWAP | Drop `VWAP_rolling_1h` from `SUGGESTED_DEFAULT_LEVELS`. Replace with `VWAP_rolling_30min` (implied by default `vwap_windows`) | Adding `1h` to `DEFAULT_LEVELS_SETTINGS.vwap_windows` (changes every new levels frame) |
| Suggested profile | Keep `pdPOC` only. Admission ≠ default-selected | Adding `pdVAH`/`pdVAL` to suggested defaults |
| Assistant catalog | After LC3, options = `closed_level_token_set(settings)` ∪ live columns ∪ already-selected. Omitted keys use DEFAULT merge, not widget catalogs | Advertising `INDICATOR_LENGTH_OPTIONS` / `VWAP_WINDOW_OPTIONS` / `POC_WINDOW_OPTIONS` when settings omit keys |
| Missing columns | API `generate_signals` / `run_experiment` global_cluster raises like anchor-rules | Changing `detect_confluence_zones` to raise |
| Dual defaults | Document `compute_all_levels` vs `DEFAULT_LEVELS_SETTINGS`; do not flip | OR 30→15 on the raw API; enabling gates on the raw API |
| Stale StudySpecs that used `Pivot_1min_*` | LC2 fail-closes at validate (honest). One-line ASSUMPTIONS note | Compatibility alias / silent rewrite |

---

## 3. Executive summary

| Item | Decision |
|---|---|
| Feature name | Level Catalog Contract (LC) |
| What changes | Shared static catalog; eight missing prior-profile tokens; pivot token spelling; suggested-default ⊆ default closed set; Assistant options from the same closed set; API global-cluster missing-column fail-closed |
| What must not change | Emitted column names; profile/session/pivot **values**; golden trades; `LEVEL_ENGINE_VERSION`; `compute_all_levels` kwargs defaults; hit-flag eligibility; Help paths |
| Engine / golden impact | **None** on `simulate_trades` / level **values**. LC1–LC3 are catalog/schema/UI-option only. LC4 is API admission only |
| Series complete when | LC1–LC4 acceptance checklists are green; goldens unchanged |

**Feasibility:** High. Columns already exist and are PIT-tested (`tests/test_phase3_levels.py`, `tests/test_r3_point_in_time.py`, `tests/test_stage2_pivot_levels.py`). Risk is list-drift and “while we’re here” new families.

### 3.1 In-scope vs out (entire series)

| In LC1–LC4 | Explicitly out |
|---|---|
| Admit `pdVAH`/`pdVAL` + week/month VAH/VAL/**POC** | Developing session H/L/EQ (`dHigh`…) |
| Shared `thesistester/levels/catalog.py` for static names | Rewriting `profile.py` / `sessions.py` math |
| Pivot tokens = `_PIVOT_COLUMN_LABELS` | Renaming pivot **columns** |
| Suggested `VWAP_rolling_1h` → `VWAP_rolling_30min`; Assistant omitted-key loops → `closed_level_token_set` | Default `vwap_windows` += `1h` |
| Assistant catalog = closed set ∪ live ∪ selected (DEFAULT-implied MAs/windows) | New MA timeframes (`15min`); keeping widget catalogs as omitted-key token sources |
| API global-cluster missing-column raise | `detect_confluence_zones` raise; engine second-check |
| Probe tests that fail on `main` | Golden regen; `LEVEL_ENGINE_VERSION` bump |
| One honesty sentence per living doc that currently overclaims | Help H2; PIT table rewrite; VAP upgrade |

---

## 4. Verified defects (normative)

Reproduce on current `main` (`aca66dc` at plan lock). These are the LC probes’ red-to-green targets.

### 4.1 D1 — Prior-profile twins computed, not StudySpec tokens

`thesistester/levels/profile.py` `_map_prior_profile_levels` always emits `{prefix}VAH/{prefix}VAL/{prefix}POC` for `pd`/`pw`/`pm`. `compute_all_levels` always joins that frame (no gate).

`STUDY_STATIC_LEVEL_NAMES` / `SESSION_LEVEL_CATALOG` / `SUGGESTED_DEFAULT_LEVELS` include **`pdPOC` only**.

```text
pdVAH pdVAL pdPOC   →  StudySpec admits pdPOC only
pwVAH pwVAL pwPOC   →  none
pmVAH pmVAL pmPOC   →  none
```

Setup Builder sees them via `available_level_columns` (frame-driven). Study Builder / `validate_study_spec` reject `core_level: [pdVAH]` as unknown.

### 4.2 D2 — Pivot token ≠ emitted column

Engine (`thesistester/levels/pivots.py`):

```text
_PIVOT_COLUMN_LABELS = {"1min": "1m", "5min": "5m", "30min": "30m", "4h": "4h"}
# emits Pivot_{label}_High / _Low
```

`closed_level_token_set` does `Pivot_{timeframe}_High` using the **settings** string (`1min`), not the label.

| Settings TF | StudySpec / Assistant token (wrong) | Engine column (truth) |
|---|---|---|
| `1min` | `Pivot_1min_High` | `Pivot_1m_High` |
| `5min` | `Pivot_5min_High` | `Pivot_5m_High` |
| `30min` | `Pivot_30min_High` | `Pivot_30m_High` |
| `4h` | `Pivot_4h_High` | `Pivot_4h_High` (only match) |

`tests/study/test_study_schema.py::test_closed_level_token_set_gates_pivots_and_prev30m_on_flags` currently **locks the wrong spelling**.

`detect_confluence_zones` then **drops** missing names. A StudySpec with `core_level: Pivot_1min_High` validates. Study expand then sets `min_confluences = max_confluences = len(selected_levels)` (`thesistester/study/expand.py`). A missing core therefore zeros the **entire cell** (not a thinner cluster): with one partner, N=2 and only the partner column present → empty `confluence_zones` → empty trades. Headless `run_experiment` / `api.generate_signals` inherit the same silent drop (D4).

### 4.3 D3 — Suggested / Assistant catalogs advertise tokens default settings do not imply

Two independent sources. LC3 must close both.

**D3a — Setup suggested list.** `SUGGESTED_DEFAULT_LEVELS` includes `VWAP_rolling_1h`. `DEFAULT_LEVELS_SETTINGS["vwap_windows"]` is `["30min", "4h"]`. `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` therefore does **not** contain `VWAP_rolling_1h`. `schema._static_catalog_names` already strips rolling names from `SUGGESTED_DEFAULT_LEVELS` so StudySpec does not admit `1h` statically — but Setup `default_selected_levels` still prefers it (and silently skips it when the column is absent from a product-default frame).

**D3b — Assistant omitted-key widget catalogs** (`build_confluence_level_options` when the key is absent / `levels_settings=None`). Verified on `main`:

| Omitted key | Assistant fallback today | Product `DEFAULT_LEVELS_SETTINGS` | Tokens advertised that defaults do not imply |
|---|---|---|---|
| `vwap_windows` | `VWAP_WINDOW_OPTIONS` = `15min`/`30min`/`1h`/`4h` | `["30min", "4h"]` | `VWAP_rolling_15min`, `VWAP_rolling_1h` |
| `poc_windows` | `POC_WINDOW_OPTIONS` = `30min`/`1h`/`4h` | `["30min"]` | `POC_rolling_1h`, `POC_rolling_4h` |
| `sma_lengths` | `INDICATOR_LENGTH_OPTIONS` = 9/20/21/50/100/200 | `[50, 200]` | `SMA_9_30min`, `SMA_20_30min`, `SMA_21_30min`, `SMA_100_30min` |
| `sma_timeframes` | `("30min",)` | `["1min", "5min", "30min"]` | (under-advertises `SMA_50_1min` / `SMA_50_5min`) |
| `ema_lengths` / `ema_timeframes` | lengths from `INDICATOR_LENGTH_OPTIONS`; timeframes default `()` | `[9, 21]` × `["1min", "5min", "30min"]` | no `EMA_*` at all when settings are omitted |

`_add(SUGGESTED_DEFAULT_LEVELS)` also injects D3a’s `VWAP_rolling_1h`. Swapping only the suggested list (D3a) and leaving these loops does **not** close D3. LC3 rewrite to `closed_level_token_set` is the required fix.

**Expected LC3 default-picker delta** (intentional; lock it in LC3-P2): drop widget-only tokens (`VWAP_rolling_15min`/`1h`, `POC_rolling_1h`/`4h`, `SMA_9/20/21/100_30min`); add product-implied tokens (`SMA_50_1min`/`5min`/`30min`, `SMA_200_*`, `EMA_9_*`, `EMA_21_*`). `INDICATOR_LENGTH_OPTIONS` / `VWAP_WINDOW_OPTIONS` / `POC_WINDOW_OPTIONS` stay **widget catalogs** for the settings editors.

### 4.4 D4 — Global-cluster missing columns are silent (headless / study)

`thesistester/api.py` raises `Setup references unavailable level columns` for **anchor_rules** only. Global-cluster calls `detect_confluence_zones`, which skips absent names (`tests/test_phase4_engine.py::test_missing_selected_columns_returns_empty_with_schema`). `api.generate_signals` returns that empty frame under the key **`confluence_zones`** (not `zones`).

`run_experiment` and study execute (`thesistester/study/execute.py`) call `api.generate_signals`. After LC4 they inherit the raise. That is intended: a cell that names a column the frame lacks becomes an explicit per-cell failure instead of empty trades.

Classic Signals (`pages/6_Signals.py`) already fail-closes **saved** global-cluster setups via `_saved_setup_generation_blockers` / `_saved_setup_compatibility_issues`. The live picker is frame-driven (`available_level_columns`). **Do not edit** `pages/6_Signals.py` in LC4. Do not treat “optional Signals same-PR” as a license to fork messages or call the library raise.

Static StudySpec tokens whose **compute** gates are off (`dVWAP_RTH` with `session_vwap_enabled=False`, `APOC` with `apoc_enabled=False`, single prints off) are already admitted at validate. After LC4, selecting them while the gate is off fail-closes at generate. That is honesty, not a new StudySpec gate. Do not start gating those families in `closed_level_token_set` in this series.

---

## 5. Fix order

Honesty and contract first. Not “add features first.”

| Order | PR | Closes | Why this order |
|---|---|---|---|
| **LC0** | This plan + docs index | — | Contract lock before any code |
| **LC1** | Shared static catalog + admit eight prior-profile twins | D1 | StudySpec can name columns the engine already computes. Shared module stops list drift |
| **LC2** | Pivot tokens = engine labels | D2 | Validated studies must name a real column. After LC1 so catalog.py is the edit locus |
| **LC3** | Suggested ⊆ default closed set; Assistant uses `closed_level_token_set` | D3 | One implication function. Depends on LC1+LC2 so the closed set is already complete and correctly spelled |
| **LC4** | API global-cluster missing-column fail-closed | D4 | Defense in depth after tokens are correct. Do not change the confluence library |

Do **not** start: emitting new level families, flipping `compute_all_levels` defaults, adding `1h` to product `vwap_windows`, aliasing `Pivot_1min_*`, regenerating goldens.

---

## 6. Global regression gates (every LC PR)

Copy into each PR body as the “regression safety” paragraph.

1. **Probe first.** Land the failing test that encodes the defect in the same PR as the fix. The test must fail on current `main` and pass after the fix.
2. **Golden-master.** `tests/test_golden_master.py` and `tests/test_otf_golden.py` stay green. No `GOLDEN_REGEN`.
3. **No engine-value change.** Do not edit `profile.py` math, `sessions.py` math, `pivots.py` **emit** strings, or `simulate_trades`. LC2 may **read** `_PIVOT_COLUMN_LABELS`; it must not change it.
4. **Narrow diff.** One defect family per PR. Parked items → handoff note, not extra files.
5. **Same-PR docs.** One living-doc honesty sentence. No drive-by USER_GUIDE rewrites.
6. **No Help path moves. No `LEVEL_ENGINE_VERSION` bump.**
7. **§4.2 checklist:** unit tests deterministic; goldens preserved; docs; CI green; small surface.

Suggested local gate (implementer, not CI-only):

```bash
pytest -q tests/test_golden_master.py tests/test_otf_golden.py tests/study/test_study_schema.py tests/test_phase3_levels.py tests/test_stage2_pivot_levels.py
# plus the probe file named in that PR
```

---

## 7. Per-PR specifications

### 7.0 LC0 — Plan lock + docs index

**Status:** This PR  
**Closes:** —

#### Change

1. Add this file.
2. Index it in `docs/README.md` (normative contracts list).
3. Add an **LC** row to the `docs/ENGINEERING_ROADMAP.md` top status table **and** a late-body LC stub (milestone table). Mark ✅ on the stub row in each landed LC PR.

#### Files

| Touch | Do not touch |
|---|---|
| `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md` | Any `thesistester/` or `tests/` |
| `docs/README.md` (one bullet) | USER_GUIDE; Help paths |
| `docs/ENGINEERING_ROADMAP.md` (top status-table row + LC stub) | ASSUMPTIONS / STUDY_RUNNER (those wait for LC1–LC4) |

#### Acceptance

- [ ] Plan is the series SoT; implementers do not re-audit locked layers
- [ ] README + roadmap **top status table** + late-body stub index the plan
- [ ] Diff is docs-only

---

### 7.1 LC1 — Shared static catalog + prior-profile twins

**Status:** Not started  
**Closes:** D1  

#### Defect (verified)

See §4.1. `closed_level_token_set({})` / default merge contains `pdPOC` and not `pdVAH` / `pwPOC` / `pmVAL` / ….

#### Change (surgical)

1. Add `thesistester/levels/catalog.py` as the **only** static name list:
   - `SESSION_STRUCTURAL_LEVEL_NAMES` — exact `ordered` tuple from `compute_session_levels` (`sessions.py` lines 519–550).
   - `PRIOR_PROFILE_LEVEL_NAMES` — `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC`.
   - `SESSION_VWAP_LEVEL_NAMES` — re-export `SESSION_VWAP_COLUMNS` from `session_vwap.py` (or the same two strings).
   - `SINGLE_PRINT_LEVEL_NAMES` — re-export `SINGLE_PRINT_COLUMNS` from `tpo.py`.
   - `APOC_LEVEL_NAMES` — `APOC`, `pAPOC`.
   - `STATIC_STUDY_LEVEL_NAMES` = union of the above (frozenset).
2. `thesistester/study/schema.py`: delete `_static_catalog_names` / the inline set. `STUDY_STATIC_LEVEL_NAMES = STATIC_STUDY_LEVEL_NAMES`. Keep the rolling-strip comment as a one-liner pointing at catalog (rolling still must not be in the static set).
3. `thesistester/assistant/workspace.py`: keep the existing `SESSION_LEVEL_CATALOG` **order**. Replace the lone `pdPOC` entry with the nine-name `PRIOR_PROFILE_LEVEL_NAMES` block (`pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC`). Do **not** `sorted()` the tuple — that would scramble the session-first catalog (APOC before AsiaHigh) and violate “Assistant LC1 delta is profile twins only.”

   Keep `prev30mVWAP` and the **current** `Pivot_1min_*` … strings in LC1. Pivot spelling is LC2.
4. Do **not** add the twins to `SUGGESTED_DEFAULT_LEVELS` (LC3 owns suggested).
5. Re-export `STATIC_STUDY_LEVEL_NAMES` / `PRIOR_PROFILE_LEVEL_NAMES` from `thesistester/levels/__init__.py` if needed by tests; do not grow a grab-bag.
6. Docs: `STUDY_RUNNER.md` § Closed level token set lists the nine prior-profile names explicitly. `ASSUMPTIONS_AND_LIMITATIONS.md` one sentence: prior VAH/VAL/POC (day/week/month) are StudySpec tokens; math remains typical-price MVP.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/levels/catalog.py` (**new**) | `profile.py` math; `sessions.py` math |
| `thesistester/study/schema.py` (import static set) | `closed_level_token_set` implication rules except that static set grows |
| `thesistester/assistant/workspace.py` (`SESSION_LEVEL_CATALOG`) | `build_confluence_level_options` logic (LC3) |
| `thesistester/levels/__init__.py` (optional re-export) | `setup.py` suggested list (LC3) |
| `tests/study/test_study_schema.py` | Goldens; `engine/` |
| `tests/test_phase3_levels.py` (optional membership assert only) | `LEVEL_ENGINE_VERSION` |
| `docs/STUDY_RUNNER.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | USER_GUIDE H2 |

#### Probe tests (must exist)

| ID | Recipe | Assert |
|---|---|---|
| LC1-P1 | `validate_study_spec` of the existing mini study with `factors.core_level: ["pdVAH"]` (partners unchanged) | Fail on `main` (`Unknown core_level token`); pass after LC1 |
| LC1-P2 | Same for `pwPOC` and `pmVAL` as `core_level` (one test, parametrize) | Same red→green |
| LC1-P3 | `closed_level_token_set({"vwap_windows": [], "poc_windows": [], "pivots_enabled": False, "prev30m_vwap_enabled": False})` | Contains all nine `PRIOR_PROFILE_LEVEL_NAMES`; still excludes `VWAP_rolling_*`, `Pivot_*`, `prev30mVWAP` |
| LC1-P4 | `compute_profile_levels` on the existing phase-3 fixture | All nine names present as columns (already true; lock it) |
| LC1-P5 | `STUDY_STATIC_LEVEL_NAMES == STATIC_STUDY_LEVEL_NAMES` | Identity; no second list |

#### Acceptance

- [ ] P1–P5 fail on unpatched `main` where applicable and pass after
- [ ] Existing `test_static_catalog_excludes_suggested_rolling_vwap` still green
- [ ] Existing phase-3 / R3 PIT profile tests green (values unchanged)
- [ ] Goldens green; no regen; no `LEVEL_ENGINE_VERSION` bump
- [ ] Diff does not edit `pivots.py` emit labels, suggested defaults, or API missing-column behavior
- [ ] `pdVAH` appears in Study Builder token catalog under default draft levels (manual or builder unit: `builder_token_catalog` contains `pdVAH`)

#### Out of LC1

Pivot spelling; suggested-list edit; Assistant options rewrite; API fail-closed; developing profiles.

---

### 7.2 LC2 — Pivot token contract

**Status:** Not started  
**Closes:** D2  

#### Defect (verified)

See §4.2. Schema test currently asserts `Pivot_1min_High`.

#### Change (surgical)

1. Add `pivot_column_names(timeframes: Iterable[str]) -> tuple[str, ...]` in `thesistester/levels/catalog.py` (or a thin helper next to `_PIVOT_COLUMN_LABELS` in `pivots.py` and import it). **Must** use `_PIVOT_COLUMN_LABELS`; must not re-spell `1m`/`5m`/`30m`.
2. `closed_level_token_set`: when pivots are enabled, `tokens.update(pivot_column_names(settings["pivot_timeframes"]))` instead of `f"Pivot_{label}_High"` on the raw TF string.
3. Replace Assistant `SESSION_LEVEL_CATALOG` pivot entries with `pivot_column_names(("1min", "5min", "30min", "4h"))`.
4. Rewrite `test_closed_level_token_set_gates_pivots_and_prev30m_on_flags` to assert `Pivot_1m_High` in / `Pivot_1min_High` **out**.
5. Docs: `STUDY_RUNNER.md` + one ASSUMPTIONS sentence: StudySpec pivot tokens are `Pivot_1m_*` / `Pivot_5m_*` / `Pivot_30m_*` / `Pivot_4h_*`. Hand-edited YAML that used `Pivot_1min_*` fails closed at validate.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/levels/catalog.py` (helper) | `_PIVOT_COLUMN_LABELS` values; emit loop body |
| `thesistester/levels/pivots.py` only if the helper is defined there and re-exported | Confirmation math; timeframes supported |
| `thesistester/study/schema.py` (`closed_level_token_set` pivot branch) | MA / rolling implication |
| `thesistester/assistant/workspace.py` (catalog tuple) | `build_confluence_level_options` (LC3) |
| `tests/study/test_study_schema.py` | `tests/test_stage2_pivot_levels.py` value asserts (already `Pivot_1m_*`) |
| `docs/STUDY_RUNNER.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Goldens; USER_GUIDE |

#### Probe tests (must exist)

| ID | Recipe | Assert |
|---|---|---|
| LC2-P1 | `closed_level_token_set({"pivots_enabled": True, "pivot_timeframes": ["1min"]})` | `Pivot_1m_High` / `Pivot_1m_Low` in; `Pivot_1min_High` out |
| LC2-P2 | `compute_pivot_levels(..., enabled=True, pivot_timeframes=["1min","5min","30min","4h"])` column set | Equals `pivot_column_names(...)` exactly (`compute_pivot_levels` returns only `Pivot_*` columns; do not subtract OHLCV) |
| LC2-P3 | `validate_study_spec` mini study with `core_level: ["Pivot_1min_High"]` and default-on pivots | Fail closed after LC2 (unknown token). On `main` this **passes** validate — that is the defect |
| LC2-P4 | Same with `core_level: ["Pivot_1m_High"]` | Fail on `main`; pass after LC2 |
| LC2-P5 | `SESSION_LEVEL_CATALOG` | Contains `Pivot_1m_High`; does not contain `Pivot_1min_High` |

#### Acceptance

- [ ] P1–P5 red→green as specified
- [ ] Stage-2 pivot value tests unchanged (same column names they already use)
- [ ] Goldens green; no engine-value change
- [ ] ASSUMPTIONS notes the intentional StudySpec break for `Pivot_1min_*`
- [ ] Diff does not add a compatibility alias

#### Out of LC2

Suggested VWAP; Assistant `closed_level_token_set` unification; API raise; new pivot timeframes.

---

### 7.3 LC3 — Suggested defaults + Assistant closed-set unification

**Status:** Not started  
**Closes:** D3  

#### Defect (verified)

See §4.3 (D3a + D3b). Assistant `build_confluence_level_options` always `_add(SUGGESTED_DEFAULT_LEVELS)` and, when keys are omitted, expands from `VWAP_WINDOW_OPTIONS` / `POC_WINDOW_OPTIONS` / `INDICATOR_LENGTH_OPTIONS` / `sma_timeframes=("30min",)` / `ema_timeframes=()` rather than `DEFAULT_LEVELS_SETTINGS`. Swapping only the suggested 1h token leaves D3b open.

#### Change (surgical)

1. `SUGGESTED_DEFAULT_LEVELS`: replace `"VWAP_rolling_1h"` with `"VWAP_rolling_30min"`. Do **not** add `pdVAH` here.
2. Add `assert_suggested_defaults_implied()` test: every suggested name is in `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` **or** is a session/profile static name (all suggested session names already are). After the 1h→30min swap, the rolling name must be in the default closed set.
3. Rewrite `build_confluence_level_options` to:

   ```text
   closed_level_token_set(levels_settings or {})
   ∪ available_columns
   ∪ already-selected draft tokens
   ```

   Preserve “explicit empty windows/lengths stay empty” — that is already `closed_level_token_set` merge semantics (`[]` overrides DEFAULT).
4. Remove the now-redundant SMA/EMA/VWAP/POC/prev30m manual loops **if** they duplicate `closed_level_token_set`. Keep `coerce_window_label` / widget helpers.
5. Update `tests/test_assistant_workspace.py` comments that say suggested may still include `VWAP_rolling_1h`. Assert default options contain `VWAP_rolling_30min` and `VWAP_rolling_4h`, not `VWAP_rolling_1h`, when settings are omitted or default. When `vwap_windows: ["1h"]`, `VWAP_rolling_1h` remains selectable.
6. Docs: ASSUMPTIONS / STUDY_RUNNER one sentence — suggested Setup defaults are a subset of the default closed token set; `1h` rolling VWAP is opt-in via `vwap_windows`.

#### Product lock

- Setup Builder **new** default selection may now include `VWAP_rolling_30min` when that column exists (it does under product defaults). Saved setups unchanged.
- Assistant default picker (`levels_settings=None`) = `closed_level_token_set({})` (DEFAULT merge). That **drops** widget-only tokens (`VWAP_rolling_15min`/`1h`, `POC_rolling_1h`/`4h`, `SMA_9/20/21/100_30min`) and **adds** product-implied MA tokens (`SMA_50_1min`/`5min`/`30min`, `SMA_200_*`, `EMA_9_*`, `EMA_21_*`). Today’s omitted-key path advertises no `EMA_*` and only 30min SMA TFs — the expansion is intentional.
- `INDICATOR_LENGTH_OPTIONS` / `VWAP_WINDOW_OPTIONS` / `POC_WINDOW_OPTIONS` remain **widget catalogs** for the Levels / Assistant settings editors. They are not implied tokens.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/setup.py` (`SUGGESTED_DEFAULT_LEVELS`) | `DEFAULT_LEVELS_SETTINGS` windows |
| `thesistester/assistant/workspace.py` (`build_confluence_level_options`) | Levels page widgets |
| `tests/test_assistant_workspace.py` | Engine; goldens |
| `tests/test_setup_config.py` if suggested-default tests exist | `validate_setup_config` eligibility rules |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/STUDY_RUNNER.md` | USER_GUIDE H2 |

#### Probe tests (must exist)

| ID | Recipe | Assert |
|---|---|---|
| LC3-P1 | `set(SUGGESTED_DEFAULT_LEVELS) <= closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` | Fail on `main` (`VWAP_rolling_1h`); pass after |
| LC3-P2 | `build_confluence_level_options(levels_settings=None)` after LC1+LC2 | Has `VWAP_rolling_30min`, `VWAP_rolling_4h`, `POC_rolling_30min`, `pdVAH`, `Pivot_1m_High`, `SMA_50_1min`, `SMA_50_5min`, `SMA_50_30min`, `EMA_21_30min`. No `VWAP_rolling_1h`, `VWAP_rolling_15min`, `POC_rolling_1h`, `POC_rolling_4h`, `SMA_9_30min`, `SMA_20_30min`, `SMA_100_30min`, `Pivot_1min_High` |
| LC3-P3 | `levels_settings={"vwap_windows": [], "sma_lengths": [], "ema_lengths": [], "poc_windows": []}` (other keys default-merge) | No `VWAP_rolling_*` / `POC_rolling_*` / `SMA_*` / `EMA_*` from those empty lists; static `dVWAP_RTH` still present |
| LC3-P4 | `levels_settings={"vwap_windows": ["1h"]}` | `VWAP_rolling_1h` present |
| LC3-P5 | `default_selected_levels` on a frame that has product-default columns | Includes `VWAP_rolling_30min` when present; does not require `VWAP_rolling_1h` |

#### Acceptance

- [ ] P1–P5 red→green
- [ ] Existing “explicit empty windows do not expand to full catalog” tests updated to the closed-set semantics and still protect that lock
- [ ] Goldens green
- [ ] Diff does not add `1h` to `DEFAULT_LEVELS_SETTINGS`

#### Out of LC3

API missing-column raise; changing product `vwap_windows`; adding VAH to suggested.

---

### 7.4 LC4 — API global-cluster missing-column fail-closed

**Status:** Not started  
**Closes:** D4  

#### Defect (verified)

See §4.4. After LC2, a well-formed StudySpec cannot name `Pivot_1min_High`. Hand-edited RunSpecs / Assistant drafts can still list a column the frame lacks; global-cluster then silently under-counts confluence.

#### Change (surgical)

1. In `thesistester/api.py`, extract the existing anchor-rules missing-column check into a helper (e.g. `_require_level_columns(levels, names)`).
2. Call it for **global_cluster** `selected_levels` before `detect_confluence_zones`, same `ValueError` text: `Setup references unavailable level columns: [...]`.
3. Do **not** change `detect_confluence_zones` (library tests keep the empty-frame contract).
4. Do **not** edit `pages/6_Signals.py`. Saved-setup missing columns are already blocked by `_saved_setup_generation_blockers`. Live selection is frame-driven. Do not fork UI messages to match the API `ValueError`.
5. ASSUMPTIONS one sentence: missing selected/anchor level columns fail closed at `api.generate_signals` / `run_experiment` / study cells; they are not silent drops. Classic Signals saved-setup blockers stay as they are.

#### Files

| Touch | Do not touch |
|---|---|
| `thesistester/api.py` | `thesistester/engine/confluence.py` |
| Tests around `api.generate_signals` / `run_experiment` / existing API setup tests | `test_phase4_engine.py` missing-column empty-frame test; `pages/6_Signals.py` |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Study schema (already fail-closed on unknown **tokens**) |

#### Probe tests (must exist)

| ID | Recipe | Assert |
|---|---|---|
| LC4-P1 | `api.generate_signals` with a levels frame that has `ONH`, `selected_levels=["ONH", "Pivot_1min_High"]`, `confluence_mode="global_cluster"`, `min_confluences=2` | Raises `ValueError` matching `unavailable level columns` and names `Pivot_1min_High`. On `main` this returns **empty** `confluence_zones` (key is not `zones`; N=2 and only `ONH` present) |
| LC4-P2 | Same with `selected_levels=["ONH"]` only | Unchanged `confluence_zones` vs today’s ONH-only behavior (empty when `min_confluences=2`) |
| LC4-P3 | Anchor-rules missing column (existing) | Same raise, same wording family |
| LC4-P4 | `detect_confluence_zones(..., ["missingA","missingB"])` | Still empty schema frame (library unchanged) |

#### Acceptance

- [ ] P1–P4 as specified
- [ ] Goldens green (they do not select missing names)
- [ ] Diff does not edit confluence greedy algorithm

#### Out of LC4

Rejecting unknown tokens in `validate_setup_config` without a frame; changing library skip behavior; editing `pages/6_Signals.py`; gating `dVWAP_*` / `APOC` / single prints in StudySpec.

---

## 8. Parked (explicitly not this series)

These were real audit findings. They are **new compute or default-policy**, not catalog correctness. Do not sneak them into LC1–LC4.

| ID | Finding | Why parked | Later series hint |
|---|---|---|---|
| P-A | Developing `dHigh`/`dLow`/`dEQ` (+ week/month) | New columns; PIT + session gates | Future level-family plan |
| P-B | Developing `RTH_High`/`RTH_Low` | New columns; we have `RTH_Open` + `pRTH_*` only | Same |
| P-C | Developing `dVAH`/`dVAL`/`dPOC` | New columns; prior-only today | Same |
| P-D | Rolling VAH/VAL (`_rolling_poc` already computes then discards) | New columns + cost (Python loop) | Opt-in family; not a rename |
| P-E | `OR_Mid`, IB (60m), VA-mid ≠ `pdEQ` | New columns | Same |
| P-F | `pVWAP` / `pRTH_VWAP` / ETH-only VWAP | New columns; classifier mentions `ETH_VWAP` today | Same |
| P-G | MA `15min` TF; shared TF vocabulary | Product expansion; trigger/OTF already have 15 | Indicator plan |
| P-H | Flip `compute_all_levels` OR=30 / gates-off / agg=1 to product 15 / on / 4-8-10. Also: `compute_profile_levels(rolling_windows=None)` uses `DEFAULT_ROLLING_POC_WINDOWS` = `30min`/`1h`/`4h` vs product `poc_windows=["30min"]` | Breaks the additive API contract | Never in LC; document only |
| P-I | `session_vwap_anchor` vestigial | Dead setting; harmless | Cleanup PR later |
| P-J | `value_area_pct` passed into rolling POC unused | API wart; changing it could imply VA rolling | With P-D if ever |
| P-K | Compatibility alias `Pivot_1min_*` → `Pivot_1m_*` | Hides the contract; rejected in §2.1 | Never |

LC3 docs may **list** P-A–P-F as known absences in ASSUMPTIONS (one short bullet list). That is honesty, not implementation.

---

## 9. Shared catalog module (normative shape)

`thesistester/levels/catalog.py` is introduced in LC1 and only extended in LC2.

```text
SESSION_STRUCTURAL_LEVEL_NAMES  # tuple, same order as the local `ordered` list in compute_session_levels
PRIOR_PROFILE_LEVEL_NAMES       # tuple, pd then pw then pm, VAH/VAL/POC
STATIC_STUDY_LEVEL_NAMES        # frozenset, no rolling, no MA, no Pivot, no prev30m
pivot_column_names(timeframes)  # LC2; uses pivots._PIVOT_COLUMN_LABELS
```

`closed_level_token_set` stays in `thesistester/study/schema.py` (StudySpec validation API). It **imports** static names and `pivot_column_names` from catalog. Do not move StudySpec validation into the levels package.

Invariant tests (LC1 + LC2):

```text
STATIC_STUDY_LEVEL_NAMES == STUDY_STATIC_LEVEL_NAMES
PRIOR_PROFILE_LEVEL_NAMES ⊆ columns(compute_profile_levels(...))
SESSION_STRUCTURAL_LEVEL_NAMES == the local `ordered` list in
  compute_session_levels (sessions.py; not a module attribute)
pivot_column_names(tfs) == columns(compute_pivot_levels(..., pivot_timeframes=tfs, enabled=True))
  # compute_pivot_levels returns only Pivot_* columns — do not subtract OHLCV
```

---

## 10. Documentation map (per PR)

| PR | Living doc sentence |
|---|---|
| LC0 | README + roadmap index only |
| LC1 | STUDY_RUNNER closed-set lists nine prior-profile tokens; ASSUMPTIONS: they are tokens, typical-price MVP unchanged |
| LC2 | STUDY_RUNNER + ASSUMPTIONS: pivot tokens are `1m`/`5m`/`30m`/`4h`; `1min` YAML fails closed |
| LC3 | ASSUMPTIONS: suggested ⊆ default closed set; `1h` rolling is opt-in |
| LC4 | ASSUMPTIONS: missing columns fail closed at API generate |

Do not rewrite `POINT_IN_TIME_GUARANTEES.md` (already documents `Pivot_1m_*` and `pdVAH`). Do not add a USER_GUIDE H2.

Roadmap LC row: mark ✅ on each landed PR in that PR.

---

## 11. Regression-safety appendix (series)

| Risk | Mitigation |
|---|---|
| Silent zone empty from wrong pivot token | LC2 + LC4 |
| Second static list drifts again | `catalog.py` + identity tests LC1-P5 / LC2-P2 |
| Suggested 1h / widget-catalog 15min·1h compute nothing | LC3-P1 + LC3-P2 negatives |
| Engine values change | File deny-list; phase-3 / stage-2 / golden gates |
| Cache invalidation surprise | No `LEVEL_ENGINE_VERSION` bump |
| Scope creep into new families | §8 parked table |
| Stale `Pivot_1min_*` StudySpec | Intentional fail-closed; no alias |

---

## 12. Copy-ready implementer prompts

Use one prompt per PR. Do not combine LC1–LC4.

### LC1

```text
Implement LC1 only from docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md §7.1.

Work regression-safe (docs/ENGINEERING_PROPOSAL.md §4 / §4.1 / §4.2). Same-PR docs.
Do not rename engine columns. Do not edit profile/session math. Do not bump
LEVEL_ENGINE_VERSION. Do not edit SUGGESTED_DEFAULT_LEVELS, pivot spelling,
build_confluence_level_options, api.py missing-column behavior, goldens, or engine/.

Add thesistester/levels/catalog.py with STATIC_STUDY_LEVEL_NAMES including all nine
prior-profile twins (pd/pw/pm × VAH/VAL/POC). Point STUDY_STATIC_LEVEL_NAMES at it.
Replace the lone pdPOC entry in SESSION_LEVEL_CATALOG with the nine-name
PRIOR_PROFILE block (preserve existing order; do not sorted()). Keep
existing Pivot_1min_* strings until LC2.

Land probe tests LC1-P1–P5 (must fail on main, pass after). Run
pytest -q tests/study/test_study_schema.py tests/test_phase3_levels.py
tests/test_golden_master.py tests/test_otf_golden.py
Update STUDY_RUNNER.md closed-set + one ASSUMPTIONS sentence.
```

### LC2

```text
Implement LC2 only from docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md §7.2.

Work regression-safe (§4). Do not change _PIVOT_COLUMN_LABELS or emitted column
strings. Catalogs and closed_level_token_set must use pivot_column_names() so
tokens are Pivot_1m_* / Pivot_5m_* / Pivot_30m_* / Pivot_4h_*.
No compatibility alias for Pivot_1min_*. No LEVEL_ENGINE_VERSION bump. No goldens.

Land LC2-P1–P5. Rewrite test_closed_level_token_set_gates_pivots_and_prev30m_on_flags
to lock the engine spelling. Update STUDY_RUNNER.md + ASSUMPTIONS (1min YAML fails closed).
Run pytest -q tests/study/test_study_schema.py tests/test_stage2_pivot_levels.py
tests/test_golden_master.py tests/test_otf_golden.py
```

### LC3

```text
Implement LC3 only from docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md §7.3.

Work regression-safe (§4). Replace SUGGESTED_DEFAULT_LEVELS VWAP_rolling_1h with
VWAP_rolling_30min. Do not add 1h to DEFAULT_LEVELS_SETTINGS. Do not add pdVAH
to suggested. Rewrite build_confluence_level_options to
closed_level_token_set(settings) ∪ available_columns ∪ selected.
Do not keep VWAP_WINDOW_OPTIONS / POC_WINDOW_OPTIONS / INDICATOR_LENGTH_OPTIONS
as omitted-key token sources (they stay widget catalogs only).
Keep explicit-empty window semantics. Update assistant workspace tests (including
the VWAP_rolling_1h comment). Land LC3-P1–P5 (P2 must lock the widget-catalog
negatives and the DEFAULT-implied MA positives). Same-PR ASSUMPTIONS/STUDY_RUNNER sentence.
No engine/, no goldens, no LEVEL_ENGINE_VERSION.
```

### LC4

```text
Implement LC4 only from docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md §7.4.

Work regression-safe (§4). In thesistester/api.py, fail-closed global_cluster
selected_levels that are absent from the levels frame using the same ValueError
as anchor_rules. Do not change detect_confluence_zones. Do not edit engine/confluence.py.
Do not edit pages/6_Signals.py (saved-setup blockers already exist).
Land LC4-P1–P4 (P1 asserts the confluence_zones key and min_confluences=2).
One ASSUMPTIONS sentence. Goldens unchanged.
```

---

## 13. Suggested PR titles

| PR | Title |
|---|---|
| LC0 | `LC0: lock level catalog contract plan` |
| LC1 | `LC1: admit prior-profile VAH/VAL/POC twins as StudySpec tokens` |
| LC2 | `LC2: align pivot StudySpec tokens with Pivot_1m/5m/30m columns` |
| LC3 | `LC3: suggested/Assistant catalogs ⊆ default closed token set` |
| LC4 | `LC4: fail-closed missing global-cluster level columns at API` |

Each PR body must include the §6 regression-safety paragraph and that PR’s probe table.
