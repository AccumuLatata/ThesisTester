# QI-02 — Levels engine and point-in-time surface

**Slice:** QI-2 (research-only)
**Status:** Completed
**Audited commit:** `32ad34c` (`32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc`) — `main` after [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) (QI-11)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1, vulture 2.16
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi02-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 8 (C/H/M/L = 0/0/5/3)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day.
**After-edit `pytest -q`:** 3,966 passed, 5 skipped in 127.38 s — same pass/fail/skip as before (133.81 s). Wall-time delta is noise. `git status --porcelain` after the run: clean (only the two `docs/quality/` files were ever staged).

**Review corrections (evidence re-measured on the same `32ad34c` product files):** `_sync_levels_widget_state` is **87** physical lines (278–364), not 88; H4 probe flags are plane-equal (OR / Stage-6 gates / `poc_windows` / agg ticks 4/8/10), not full-dict equal — `normalize_levels_config` sorts `sma_timeframes` / `ema_timeframes` / `pivot_timeframes`; fingerprint inner keys are the page helper’s dict, not an `ARCHITECTURE.md` contract-table row; profile identity stamps are `attach_tick_identity` **and** `attach_rolling_poc_identity`; PIT §9 OR is M2 / §7 item 12 named (not “no”); DST `ONH` finite is **120** (same gate as `RTH_Open`), not 80; close-as-tick `POC_rolling_30min` finite is **0** (same unreadable path that leaves `APOC` vacuous), not 3. `iso25010` tokens were already §A.5-legal; H4 stays Design limitation / `confidence=n/a` / Medium. `trading_session_date` arithmetic, tick bins 4/8/10, and QT-parity were not re-audited.

Locked inputs treated as premises (not re-audited): `AUDIT_FINAL.md` §5 on `origin/cursor/audit-final-merge-3a8e`; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1 (omitted levels keys = product `DEFAULT_LEVELS_SETTINGS`). `trading_session_date` arithmetic, tick bin sizes 4/8/10, and QT-parity (AP/RP) were not re-audited.

This report does **not** call any backtest, metric, or Study result correct. Vocabulary is plan §3.3. Future-shock language is prefix-identity only.

## Commands run (verbatim)

```bash
python3 --version
git fetch origin main
git rev-parse HEAD
git log -1 --format='%h %ad %s' --date=short

export THESISTESTER_STORE_DIR=/tmp/qi02-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no

radon cc thesistester/levels pages/2_Levels.py \
  thesistester/visualization/levels_chart.py -s -n D --total-average
radon mi thesistester/levels pages/2_Levels.py \
  thesistester/visualization/levels_chart.py -s
vulture thesistester/levels pages/2_Levels.py \
  thesistester/visualization/levels_chart.py --min-confidence 60
rg -n 'except Exception|except:' thesistester/levels pages/2_Levels.py \
  thesistester/visualization/levels_chart.py
rg -c 'st\.session_state' pages/2_Levels.py
rg -n 'type: ignore|noqa' thesistester/levels pages/2_Levels.py \
  thesistester/visualization/levels_chart.py

# probes
export THESISTESTER_STORE_DIR=/tmp/qi02-store-probes
PYTHONPATH=/workspace python3 /tmp/qi02_probes.py

# scoped suite twice
pytest -q -p no:cacheprovider \
  tests/test_r3_point_in_time.py tests/test_session_levels.py \
  tests/test_stage1_level_plumbing.py tests/test_stage2_pivot_levels.py \
  tests/test_stage3_session_vwap.py tests/test_stage4_single_prints.py \
  tests/test_stage5_apoc_levels.py tests/test_stage6_levels_ui_settings.py \
  tests/test_levels_page_helpers.py tests/test_prev30m_vwap.py \
  tests/test_wvwap_mvwap.py tests/test_dvwap_cme_session.py \
  tests/test_phase3_levels.py tests/test_apoc_tick_source.py \
  tests/test_rolling_poc_tick_source.py tests/test_tick_vap_cutover.py \
  tests/visualization/test_levels_chart.py
PYTHONHASHSEED=0 pytest -q -p no:cacheprovider <same files>

export THESISTESTER_STORE_DIR=/tmp/qi02-store-after
pytest -q --tb=no
git status --porcelain
```

Probe script lives under `/tmp/qi02_probes.py` (not committed). Transcript: `/tmp/qi02-probe-results.json`.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-0 exclusive ownership; 22 files)**

| Path | Role in this slice |
|---|---|
| `thesistester/levels/all.py` | `compute_all_levels` orchestrator |
| `thesistester/levels/sessions.py` | Structural session family |
| `thesistester/levels/session_date.py` | `trading_session_date` (read only; arithmetic not re-audited) |
| `thesistester/levels/indicators.py` | SMA/EMA/rolling VWAP |
| `thesistester/levels/pivots.py` | Confirmed pivots |
| `thesistester/levels/session_vwap.py` | dVWAP / wVWAP / mVWAP |
| `thesistester/levels/tpo.py` | TPO single prints |
| `thesistester/levels/profile.py` | Prior VA join + dead `_rolling_poc` |
| `thesistester/levels/apoc.py` + `apoc_tick.py` + `apoc_candidates.py` | APOC / pAPOC |
| `thesistester/levels/rolling_poc_tick.py` + `rolling_poc_candidates.py` | Tick rolling POC |
| `thesistester/levels/tick_vap.py` + `tick_requirements.py` | Prior-profile table + refuse strings |
| `thesistester/levels/prev30m_vwap.py` | prev30m stack + hit diagnostics |
| `thesistester/levels/defaults.py` + `catalog.py` + `common.py` | Product defaults, static tokens, tz helper |
| `thesistester/levels/__init__.py` | Re-exports |
| `thesistester/visualization/levels_chart.py` | Chart builder |
| `pages/2_Levels.py` | Classic Levels page |

Read-as-spec (QI-13 owns): `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/ARCHITECTURE.md` session-key / Stage-6 notes, `docs/USER_GUIDE.md` §Levels, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/AGENT_GUIDE.md`.

Read-as-call-site only (not owned): `thesistester/research_identity.py` `normalize_levels_config`; `thesistester/api.py` `compute_levels`; `thesistester/study/schema.py` named-token refuse; `thesistester/study/builder.py` Advanced-OFF pop; `thesistester/persistence/local_store.py` `LEVEL_ENGINE_VERSION` / settings hash (QI-1).

**Skipped**

- `trading_session_date` arithmetic, tick bins 4/8/10, QT-parity (AP/RP locked).
- Mutation / coverage XML re-measure — QI-11 / QI-0 (`levels/common.py` 59% already in QI-11-01).
- Browser `AppTest` of page 2 — no product change; §3.2 via static copy + `/tmp` probes. Handoff QI-10.
- Persistence namespace round-trip of `local_store.py` — QI-1 exclusive.

---

## 2. Code-quality readout

152 blocks in scope. Average CC **A (4.69)**.

### 2.1 Metric table (QI-2 files only)

| Metric | Value | Trigger hit? |
|---|---|---|
| F-grade (CC ≥ 41) | none | no |
| E-grade (21–40, CC 39) | `pages/2_Levels.py` `_sync_levels_widget_state` **E (39)** · 87 physical lines | Yes — QI-02-04 |
| D-grade | `compute_prev30m_vwap_levels` **D (23)** · 157 lines | Read; not promoted (single-purpose, dedicated suite) |
| C-grade (read) | `_compute_hit_columns` 20 · `compute_apoc_levels` 19 · `_compute_single_prints` 16 · `_session_window_high_low` 14 · `_two_pointer_poc` 12 · `_compute_profile` 12 · `_saved_levels_label` 12 | no finding |
| Physical lines > 150 | `compute_prev30m_vwap_levels` 157 · page 2 is 919 / 9 defs | page trigger |
| MI | `pages/2_Levels.py` **C (7.24)** · all library modules A (32.6–100). `common.py` 60.74 | page < 20 |
| Broad `except` | 1: `pages/2_Levels.py` `_calculate_levels_transaction` | *fails §3.2.3* — QI-02-05 |
| `vulture` ≥60 | 30 candidates. Real unused-in-product: `profile._rolling_poc`. Cross-module false friends: `attach_*_identity`, `LEVELS_*_IDENTITY_KEYS`, `tick_requirements.*`, `catalog.named_*` / `pivot_column_names` (used by API/Study/QI-7) | QI-02-07 |
| Streamlit in library (QI-2) | 0 | none |
| Cross-module private imports | 0 in scope | none |
| `st.session_state` matching lines | page 2: **70** | QI-10 graph |
| `# noqa` / `# type: ignore` | 1 (`rolling_poc_candidates.py` `# type: ignore[arg-type]`) | none |
| Coverage (QI-0) | `common.py` **59%** (QI-11-01). Other QI-2 library modules ≥ 80% (`all.py` / `indicators` / `pivots` / `session_vwap` / `tpo` / `session_date` / `defaults` 100%) | handoff QI-11 |

### 2.2 Family compute signatures (no shared protocol)

There is **no** common ABC, `enabled=` convention, or identity-stamping hook on the family functions. `compute_all_levels` is a sequential join of independently signed helpers:

| Family | Gate | `instrument` | `tick_paths` | Identity stamp |
|---|---|---|---|---|
| `compute_session_levels` | always-on | yes | no | none |
| `compute_indicator_levels` | empty-list omit | **no** | no | none |
| `compute_profile_levels` | empty `rolling_windows` skip POC; VA only if table | yes | yes | `attach_tick_identity` + `attach_rolling_poc_identity` (caller) |
| `compute_pivot_levels` | `enabled=False` | yes | no | none |
| `compute_session_vwap_levels` | `enabled=False` | yes | no | none |
| `compute_tpo_levels` | `single_prints_enabled=False`; `apoc_enabled=True` **raises** | yes | no | none |
| `compute_apoc_levels` | `enabled=False` | yes | yes | `attach_apoc_identity` (caller) |
| `compute_prev30m_vwap_levels` | `enabled=False` | yes | no | none |

Keyword names also drift: `poc_windows` (orchestrator/product) vs `rolling_windows` (profile); `prev30m_vwap_validity_periods` vs `validity_periods`; `session_vwap_anchor` vs `anchor`. QI-02-08.

`sessions.py` keeps a private `_require_tz_aware_timestamp` that is **not** `common.require_tz_aware_timestamp` (probe `same_object=false`). Handoff QI-11 for the untested `common.py` path.

### 2.3 `LEVEL_ENGINE_VERSION` / identity-key discipline

`LEVEL_ENGINE_VERSION` lives in QI-1 `local_store.py` and is **11**. APOC / rolling-POC / VA tick identity is **not** a version bump: `attach_apoc_identity` / `attach_rolling_poc_identity` / `attach_tick_identity` inject eight hashed keys. Probe on `32ad34c`:

- product-only hash prefix `8a3dd3346e092620`
- after stamps `0634f566b68d035f`
- version still 11

Enforcement is **convention + tests** (`test_apoc_tick_source.py`, `test_rolling_poc_tick_source.py`, `test_tick_vap_cutover.py` all `assert LEVEL_ENGINE_VERSION == 11`). There is no mechanical “new identity key ⇒ no version bump” linter. Not promoted: the convention holds on this tree and is already asserted. Handoff QI-1 / QI-12 if QR wants a contract test that the version constant is the only bump site.

### 2.4 Dead / non-default bodies

| Body | Status |
|---|---|
| `profile._rolling_poc` | Defined; **not** called from `compute_profile_levels`. vulture unused. Documented dead (RP2). Typical never silently returns. |
| `apoc._compute_a_period_poc` | Still the `typical_mvp_v1` else-branch. `resolve_apoc_profile_source` accepts it for Stage-5 tests. `normalize_levels_config({"apoc_profile_source":"typical_mvp_v1"})` **rejects**. Direct `compute_apoc_levels(..., apoc_profile_source=typical_mvp_v1)` still emits `APOC`/`pAPOC`. |
| `compute_tpo_levels(..., apoc_enabled=True)` | Raises redirect `ValueError` (not a second APOC path). |

`_rolling_poc` is the only documented-dead **production-shaped** loop. QI-02-07.

### 2.5 Broad-except classification

| Site | Class |
|---|---|
| `pages/2_Levels.py` `_calculate_levels_transaction` `except Exception` → status dict + `st.code(traceback)` | *fails §3.2.3* (raw traceback in the UI). Exception is **not** swallowed; prior levels are retained. QI-02-05 |
| `_load_saved_levels_into_session` `except (FileNotFoundError, ValueError, OSError)` | *narrow-guard OK* |
| `_saved_levels_label` / `_sync` `except (TypeError, ValueError)` on validity int | *narrow-guard OK* |

---

## 3. Application-quality readout (checklist §3.2)

Entry points: Levels page (`pages/2_Levels.py`), `api.compute_levels`, library `compute_all_levels`, Study validate (named tokens; QI-7 owns emit).

| # | Check | Levels page | `api.compute_levels` | Library `compute_all_levels` |
|---|---|---|---|---|
| 1 | Happy path | First-visit widgets = product ON. Calculate calls library **without** `tick_paths` → refuse (disclosed in `USER_GUIDE` §Levels). Untick APOC + empty POC windows is the no-tick path | Product fill then refuse if APOC or POC windows in play and no ticks | Keyword defaults: OR 30, gates False; POC windows default-on inside `compute_profile_levels` still refuse without ticks |
| 2 | Empty / minimal | Page `st.stop` if no `data`. Empty tz-aware frame: `compute_session_levels` returns all structural columns (probe) | Not separately driven | One-bar tagged ES: structural columns present, no exception |
| 3 | Malformed | `_parse_lengths` → `st.error` + stop (typed). Naive timestamps: `ValueError: Input 'timestamp' must be timezone-aware` | Same engine raise | Same |
| 4 | Stale-state | Page helper `_levels_data_fingerprint` keys: `instrument/rows/timestamp_min/max/columns` plus copies of session `base_interval/source_timezone/exchange_timezone`. `ARCHITECTURE.md` names the `levels_data_fingerprint` dict and `.rows`, not an inner-key contract table. Data drift → warning + `st.stop`. Settings drift → info, no stop. Failed calc retains prior levels | Cache miss ≠ stale UI | n/a |
| 5 | Composer parity | Tags `session` before compute. Does **not** call `normalize_levels_config` (two-composer lock) | `normalize_levels_config` product fill; **does not** tag missing `session` (untagged `RTH_Open` finite=0 vs tagged 2) | Fourth plane: keyword defaults |
| 6 | Honesty | Advanced expander caption: defaults enable families. USER_GUIDE lists families, not catalog tokens (QI-02-06). No confirmatory “proven” copy on this page | API errors are typed `ValueError` | Library refuse strings |
| 7 | Persistence | Save/load via QI-1 `local_store`. Snapshot helper setdefaults **OFF / ticks 1** (H4 plane 3) | Artifact identity uses stamped settings | n/a |
| 8 | Performance | Cost warning ≥ 3,000 bars + POC windows. Probe wall ~0.17 s on 138-bar golden-style fixture | same engine | Handoff QI-14 |
| 9 | Operability | Settings hash shown truncated; calc status has dataset / hash / rows / duration / error type | `cache_status` on result | none |
| 10 | Copy | “Advanced opt-in” vs product-default-on is the H4 mental-model trap | omit-means-on | omit-means-library-off |

### 3.1 Tick-gated refusals (UI / API / Study)

Shared substrings `APOC requires ticks` and `rolling POC requires ticks` exist. **Full strings are not identical** (QI-02-03).

| Composer | Trigger | Observed message (`32ad34c`) |
|---|---|---|
| UI / library (product-like kwargs, no ticks) | `compute_all_levels` profile step first | `rolling POC requires ticks: tick_paths is missing or empty` |
| API `compute_levels(config={})` | preflight `product_tick_family_message` | `APOC requires ticks and rolling POC requires ticks: tick_paths is missing or empty` |
| Study named `APOC` | `validate_study_spec(normalize_study_spec(...))` | `APOC requires ticks: study.dataset.tick_paths is missing or empty (named ['APOC'])` |
| Study named `POC_rolling_30min` | same | `rolling POC requires ticks: study.dataset.tick_paths is missing or empty (named ['POC_rolling_30min'])` |

UI page never passes `tick_paths` and has no tick widget. Data-page attach is not read (USER_GUIDE). First-visit Calculate with product defaults therefore **always** refuses, then shows the traceback expander (QI-02-05).

Study refuses at **validate** (named tokens only). Product-default APOC/POC with no named tick tokens is turned off by `disable_unneeded_tick_families` (QI-7). That is a third refuse *timing*, not a silent typical fallback.

### 3.2 Settings-plane map (H4)

| Plane | How you get it | OR | Stage-6 gates | Prior VA agg ticks | Session tag |
|---|---|---|---|---|---|
| **P1 Product** | `DEFAULT_LEVELS_SETTINGS` / `normalize_levels_config({})` / first-visit page widgets / Study Advanced OFF (pops five keys) then normalize / sparse YAML `{sma_lengths:[50,200]}` through `compute_levels` | 15 | all **True**; `poc_windows=["30min"]` | 4 / 8 / 10 | UI tags; API/Study do **not** |
| **P2 Library** | bare `compute_all_levels(df)` keyword defaults | **30** | all **False** | kwargs 1 / 1 / 1 | optional; missing → session levels NaN |
| **P3 Snapshot helper** | `pages/2_Levels.py` `_normalize_levels_settings({})` on old snapshots | unset | all **False** | **1 / 1 / 1** | n/a (compare-only) |

Probe flags (plane columns only): `product_eq_normalize_empty_plane=true`, `study_off_eq_norm_plane=true`, `advanced_off_same_as_sparse=true`, `snapshot_empty_gates_off=true`. Full-dict `DEFAULT_LEVELS_SETTINGS == normalize({})` is **false**: normalize sorts `sma_timeframes` / `ema_timeframes` / `pivot_timeframes` (`['1min','5min','30min']` → `['1min','30min','5min']`; pivot `4h` before `5min`). That sort is not a fourth settings plane.

AH §2 item 9 locks P1 omit-means-product-on. P2/P3 are the residual dual normalizers named in `AUDIT_FINAL` H4. QI-02-01.

---

## 4. Prior-audit carry-over status

| Item | Status on `32ad34c` | Notes |
|---|---|---|
| **H4** product-default levels planes | **Open** (locked as design) | Three planes still present. Study Advanced OFF still omits keys → product ON. Sparse YAML through `compute_levels` identical to empty normalize. Snapshot helper still OFF / ticks 1. QI-02-01 |
| **§5.5 / M2** PIT future-shock rows for `dOpen*` / `prevSettlement` / `pm` profile / asserted `pw*`/`pm*` | **Still no committed append-FS asserts** | Generated probe: prefix-identical on golden-style (finite n>0 for all named gaps) and DST-week (pm* vacuous — fixture stays in March). QI-02-02. Do not treat probe pass as a committed regression gate |

Closed AH items assigned elsewhere were not re-opened.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Axis | Class | Sev | Conf | One-line |
|---|---|---|---|---|---|
| QI-02-01 | both | Design limitation | Medium | n/a | H4: three settings planes; omit/Advanced-OFF still product-on |
| QI-02-02 | both | Test-quality gap | Medium | Verified | §5.5 / M2 columns lack committed append-FS; generated probe prefix-identical |
| QI-02-03 | app | UX/operability gap | Medium | Verified | Tick refuse strings + timing differ UI vs API vs Study |
| QI-02-04 | code | Maintainability risk | Medium | Verified | `_sync_levels_widget_state` E(39), 87 lines; snapshot helper is a third default table |
| QI-02-05 | app | UX/operability gap | Medium | Verified | Calculate `except Exception` renders raw traceback |
| QI-02-06 | app | Documentation drift | Low | Verified | USER_GUIDE §Levels omits most catalog tokens / Asia / London / ONH |
| QI-02-07 | code | Maintainability risk | Low | Verified | `_rolling_poc` dead; `typical_mvp_v1` still a live else-branch |
| QI-02-08 | code | Maintainability risk | Low | Verified | Family compute signatures / gate / identity hooks are ad-hoc |

No Critical / High. Locked-contract rows are Design limitation ≤ Medium with `confidence=n/a`.

---

## 6. Positive verification

What was checked and is fine, so later slices do not re-do this work:

1. **Before `pytest -q`:** 3,966 passed, 5 skipped in 133.81 s (`32ad34c`, py3.12 / pandas 3.0.5). **After** the two `docs/quality/` files: **3,966 passed, 5 skipped** in 127.38 s (identical pass/fail/skip).
2. **Scoped levels suites twice** (`-p no:cacheprovider` and `PYTHONHASHSEED=0`): **453 passed, 1 skipped** both times (11.79 s / 11.76 s).
3. **Generated future-shock** (append 8 extreme bars + rebuilt tick table): **all 59 emitted columns prefix-identical** on the golden-style May/June fixture (138 rows; §5.5 columns finite). Same on the DST-week fixture (123 rows; `pm*` vacuous). Structural-only (no ticks) also prefix-identical; `pmVA*` absent without a table — documented TV3 omit.
4. **`LEVEL_ENGINE_VERSION` stays 11**; identity stamps change the settings hash (documented AP/RP/TV3 rule; tests assert the constant).
5. **`typical_mvp_v1` cannot be selected** via `normalize_levels_config` / product keys. No silent typical fallback on the product path.
6. **`_rolling_poc` is not the product path.** Missing ticks refuse; no typical POC.
7. **Fingerprint helper keys** on page 2 are `instrument/rows/timestamp_min/max/columns` plus the three session TZ/interval keys the contract table already lists as fingerprint consumers. Failed Calculate retains prior `levels` / identity (atomic transaction).
8. **Catalog `STATIC_STUDY_LEVEL_NAMES` (49)** ⊆ `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`.
9. **Empty tz-aware + one-bar + naive-ts** paths: empty/one-bar emit structural columns; naive fails closed with a typed message.
10. **Isolation:** throwaway `/tmp` store; no API keys; no desk PII.

This is **not** a claim that goldens, fills, or Studies are correct.

---

## 7. Handoffs to other slices

| To | Observation (not a finding) |
|---|---|
| QI-1 | `LEVEL_ENGINE_VERSION` and `compute_levels_settings_hash` live in `local_store.py`. Levels-namespace load refuses on version drift. Snapshot bytes not opened here |
| QI-3 | Page 2 does not clear `signals` on recalc (QI-03 already noted). Developing-level H14 is QI-3 |
| QI-6 | `normalize_levels_config` + `api.compute_levels` preflight / identity attach. API does not `tag_session`. Composer fork is locked (AH §2.1) |
| QI-7 | Study Advanced OFF pops five keys then product-fill (H4). Named-token refuse vs product-default `disable_unneeded_tick_families` |
| QI-10 | 70 `session_state` lines; fingerprint / `_pending_levels_widget_sync_settings`; classic `AppTest` feasibility |
| QI-11 | `levels/common.py` 59% already QI-11-01. Generated FS in this report is `/tmp` only — committing it is QR-B / QI-11 |
| QI-13 | `POINT_IN_TIME_GUARANTEES.md` Tests column still over-reads `pw*`/`pm*` structural and lists `dOpen*` / `prevSettlement` / `pm` profile as `—`. USER_GUIDE §Levels token list. M2 wording |
| QI-14 | Probe wall ~0.17 s / 138 bars with tick table; CAI `realistic` not re-timed |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | H4 omit-means-product-on / Advanced-OFF sentence if QR labels the planes |
| `docs/ARCHITECTURE.md` | Snapshot helper OFF vs product ON; tick-refuse composer strings; Stage-6 sync |
| `docs/USER_GUIDE.md` §Levels | Catalog completeness (Asia/London/ONH/dOpen/prevSettlement); first-visit Calculate refuse |
| `docs/AGENT_GUIDE.md` | Identity-stamp / no-version-bump convention if mechanized |
| `docs/POINT_IN_TIME_GUARANTEES.md` | Tests column for §5.5 rows (QI-13 owns the file) |
| `docs/METRICS_GLOSSARY.md` | none (no new metrics) |

---

## 9. Column-level PIT coverage table

`has_test` = a committed **append-future-shock** assert on that column (gating-only tests are noted). `probe_*` = `/tmp/qi02_probes.py` on `32ad34c`. Finite counts are non-null values on the **base** frame (vacuous = 0 finite, still prefix-identical).

Golden-style fixture: May 29 + June 2–3 2026, ETH+RTH, synthetic Quantower ticks from bar close, product-like gates, `prev30m` N=2, `pivot_timeframes=["1min"]`. DST fixture: 2026-03-06 / 03-09 / 03-10 (US spring-forward week).

| Column | has committed append-FS? | probe golden (finite) | probe DST (finite) | §5.5 open-Q / M2 named? |
|---|---|---|---|---|
| `pdHigh` `pdLow` `pdOpen` `pdEQ` | yes (`test_prior_session_levels_future_shock`) | pass (92) | pass | no |
| `pwHigh` `pwLow` `pwOpen` `pwEQ` | **no** (value tests only; PIT Tests column says “Same” as `pd*` — over-read) | pass (92) | pass (82) | **yes** (§5.5 + M2) |
| `pmHigh` `pmLow` `pmOpen` `pmEQ` | **no** | pass (92) | vacuous (0) | **yes** (§5.5 + M2) |
| `dOpen` `wOpen` `mOpen` | **no** (`—` in PIT table) | pass (138) | pass (123) | **yes** (§5.5) |
| `prevSettlement` | **no** (`—`) | pass (92) | pass (82) | **yes** (§5.5) |
| `pRTH_High` `pRTH_Low` `pRTH_Open` | yes | pass (92) | pass | no |
| `pONH` `pONL` | no (previous-session suite, not append-FS) | pass (92) | pass | no |
| `ONH` `ONL` | gating only | pass (135) | pass (120) | **yes** (M2 weaker-than-Causal; not §5.5 add-FS list) |
| `RTH_Open` | gating only | pass (135) | pass (120) | **yes** (M2 weaker-than-Causal; not §5.5 add-FS list) |
| `OR_High` `OR_Low` | gating only | pass (90) | pass (75) | **yes** (M2 + §7 item 12 add-FS; omitted from the §5.5 sentence) |
| `AsiaHigh` `AsiaLow` | yes | vacuous (0) | vacuous | no |
| `LondonHigh` `LondonLow` | yes | vacuous (0) | vacuous | no |
| `pdVAH` `pdVAL` `pdPOC` | yes | pass (92) | pass | no |
| `pwVAH` `pwVAL` `pwPOC` | yes | pass (92) | pass | no |
| `pmVAH` `pmVAL` `pmPOC` | **no** | pass (92) | vacuous (0) | **yes** (§5.5 `pm` profile) |
| `POC_rolling_30min` | yes (1h named in R3; 30min via rolling-POC suite) | pass (0) | pass (0) | no |
| `SMA_5_1min` `EMA_5_1min` `VWAP_rolling_30min` | yes (family) | pass | pass | no |
| `Pivot_1m_*` | yes | vacuous (0) on this short right-window | vacuous | no |
| `dVWAP_RTH` `dVWAP` `wVWAP` `mVWAP` | yes | pass | pass | no |
| TPO four scalars | yes | mixed finite | pass | no |
| `APOC` `pAPOC` | yes | vacuous (0) on close-as-tick synthetic | vacuous | no |
| `prev30mVWAP` `_2` `hit_m1` `hit_m5` | yes | pass (47 / 2 / 42 / 30) | pass | no |

**Reading:** no prefix mismatch was observed. Vacuous cells are fixture limits, not leaks. Close-as-tick synthetic files that are not Quantower Last×Volume leave `APOC` / `pAPOC` / `POC_rolling_30min` all-NaN (0 finite) while still prefix-identical; a Quantower-shaped close CSV makes those families finite (review check only — not the committed gate). The honesty gap is the **committed Tests column** (`AUDIT_FINAL` M2 / §5.5 / §7 item 12), not a reproduced look-ahead on this tree.

---

## 10. Probe scripts (pasted; not committed)

Future-shock core (full script `/tmp/qi02_probes.py`):

```python
T = df["timestamp"].max()
# append 8 extreme bars; rebuild tick CSV + PriorProfileTable
base = compute_all_levels(df, **kwargs)
extended = compute_all_levels(ext, **kwargs_ext)
prefix = extended[extended["timestamp"] <= T].reset_index(drop=True)
for col in level_columns:
    pd.testing.assert_series_equal(
        pd.Series(base[col].to_numpy()),
        pd.Series(prefix[col].to_numpy()),
        check_names=False, check_dtype=False,
    )
```

H4 / refuse isolation:

```bash
export THESISTESTER_STORE_DIR=/tmp/qi02-store-probes
unset OPENAI_API_KEY XAI_API_KEY
PYTHONPATH=/workspace python3 /tmp/qi02_probes.py
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
