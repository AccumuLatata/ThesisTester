# Tick VAP — Implementation Plan (TV)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-24  
**Status:** Series complete (TV0–TV4). TV4 landed Data page / Study Builder `tick_paths` + Help honesty.  
**Series code:** **TV** (Tick volume-at-price)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  

**Inputs:** desk brief *ThesisTester: volume-profile gap vs Quantower* (21 Aug 2026, investigation only); session-20 MNQ evidence in that brief; current `profile.py` typical-price MVP; LC4 missing-column fail-closed at `api.generate_signals`.

**Does not reopen:** R9–R22 milestone text; AH / RS execute semantics; SIA ingest defaults; SW clocks; WMV `dVWAP*` math; AO detector; LC catalog token *names*; kill-list / fresh-round StudySpec; Help-corpus *path* moves; `simulate_trades` / R12 / 3c / touch.

**Amends:** LC locked contract #3 (prior-profile allocation) — TV3 added the one-line pointer on the LC plan. This file is the living SoT for `pd*` / `pw*` / `pm*` VA allocation. Living honesty docs (`ASSUMPTIONS_AND_LIMITATIONS.md`, `POINT_IN_TIME_GUARANTEES.md`, `METRICS_GLOSSARY.md`) were updated in TV3; Help/UI copy landed in TV4.

**Related living docs (amend only the sentence that is newly true, in the PR that makes it true):**  
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/METRICS_GLOSSARY.md`, `docs/STUDY_RUNNER.md`, `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md`.

---

## 1. Purpose

Accumu fades Quantower `VAH` / `VAL` / `POC` on MNQ (10-tick scalp). ThesisTester already emits the same *names* (`pdVAH` / `pdVAL` / `pdPOC`, `pw*`, `pm*`) from a **different object**: each 1m bar’s entire volume dumped onto typical `(H+L+C)/3`, then binned. Session marks and `dVWAP` already match the chart on 15s → 1m. Prior VA does not. On CME session 20 Aug 2026 the shipped engine was **+20.75 / +8.25 / −12.75** vs Quantower — one to two full scalp zones.

This series makes those nine tokens **tick volume-at-price** (Last × Volume, same 70% expander, same CME session cut). 15s stays the OHLC / study clock. Ticks are an ingest input for VA columns only.

Series complete when:

1. Quantower Tick–Tick–Last files (one or many monthly CSVs) can be read, session-chunked, and combined without loading a multi-year tick frame into pandas.
2. `pdVAH` / `pdVAL` / `pdPOC` (and `pw*` / `pm*` VA) are tick VAP, joined onto the already-derived 1m frame via the existing `shift(1)` prior-period map.
3. No ticks → those nine columns are **absent**. Named-VA studies refuse generate. Named-VA cells are `failed`, never `ok` + empty zones.
4. `dVWAP`, ONH / opens / OR, touch / 3c / R12, and rolling POC / APOC typical-price math are unchanged.
5. `LEVEL_ENGINE_VERSION` is 11. Old typical-price VA cells are a different research object.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Tick VAP (prior-profile allocation) |
| What ticks are used for | `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC` |
| What ticks are **not** used for | OHLC / derive 1m; `ONH`/`ONL`/opens/OR/Asia/London; `dVWAP`/`dVWAP_RTH`/`wVWAP`/`mVWAP`; touch / 3c / R12 / study bar loop; APOC / rolling POC |
| 15s path | Unchanged: `ingestion_mode: 15s_primary_derive_1m` remains the OHLC product path |
| Default without ticks | **Omit** the nine VA columns. Do **not** emit 1m-typical under those names |
| Parked typical proxy | `va_source: typical_mvp` only if it ships later as **different column names** (`pdVAH_typical` …). Not this series |
| Day bin (product) | Product key `prior_day_profile_aggregation_ticks`: **4 → 1** in TV3 (Quantower row-size match; 4-tick tick-VAP still misses session-20 POC by 12.75). `compute_all_levels` / `compute_profile_levels` kwargs stay `prior_*_aggregation_ticks` (no `_profile_`); API already maps the product key → kwarg |
| Week / month bins | Stay **8 / 10** until a QT weekly/monthly fixture exists. Same object type; **not** QT-locked |
| Engine version | `LEVEL_ENGINE_VERSION` **10 → 11** in TV3 |
| Study schema | Stays `1`. Additive `dataset.tick_paths` |
| Goldens | **No regeneration.** `run_legacy_pipeline` never calls `compute_all_levels` |
| Farm | Must not block. Studies that do not name VA tokens keep running on 15s-only |
| Series complete when | TV1–TV4 acceptance checklists are green |

**Feasibility:** High. `_compute_profile` already takes a price/volume stream; the 70% expander and `shift(1)` map stay. The work is a new tick loader, a tiny prior-profile table, fail-closed wiring, and an honest identity bump. Risk is watering fail-closed back into a silent typical fallback, or putting ticks on the simulation clock.

### 2.1 In-scope vs out

| In TV1–TV4 | Explicitly out (entire series) |
|---|---|
| Quantower Tick–Tick–Last ingest + monthly combine | Replacing `15s_primary_derive_1m` |
| Session-chunk by row timestamps (never filename) | `pd.read_csv` of 40–60 GB; 12 workers holding raw ticks |
| Tick Last×Volume → same `_compute_profile` expander | Tick replay of touch / 3c / R12 / OR / opens |
| Persist a **tiny** prior-profile table (not raw ticks) | Switching `dVWAP*` onto tick VWAP |
| Fail-closed: no ticks → no VA columns → named-VA refuse / `failed` | Silent 1m-typical fallback under `pdVA*` / `pw*` / `pm*` |
| Product day aggregation 4 → 1 | Treating 8-tick weekly as a substitute for tick allocation |
| `LEVEL_ENGINE_VERSION` 11 | Developing `dVAH` / `dVAL` / `dPOC` |
| Honesty docs + optional env-gated session-20 hook | APOC / rolling-POC VAP rewrite |
| | Bid/ask / aggressor VAP; TPO letters |
| | `OR_High` 4.00 15s-vs-chart gap; `prevSettlement` ≠ CME settle |
| | Kill-list / fresh-round / flatten / OTF matrix |
| | Golden regen; Help-path moves |

---

## 3. Locked product definition

### 3.1 The object

After TV3, `pdVAH` / `pdVAL` / `pdPOC` means:

> Frozen 70% value-area high / low / POC of the **prior completed CME session**, built from Quantower **Last × Volume** ticks, binned at `instrument_tick_size * prior_day_profile_aggregation_ticks` (product default **1**), expanded with the existing `_compute_profile` neighbor-volume rule. Mapped onto the current session’s 1m bars with the existing `shift(1)` period key (`trading_session_date`).

`pw*` / `pm*` are the same object on the existing `W-SUN` / `M` keys derived from `trading_session_date`. Week/month product bins stay 8 / 10 until a Quantower HTF fixture exists. They are **not** a live-map acceptance lock.

They are **not** 1m typical-price VA. They are **not** TPO. They are **not** developing `dVAH`.

### 3.2 What already matches (do not retick)

Desk session 20 (MNQ, 15s engine, product OR 15):

| Token | Verdict | TV action |
|---|---|---|
| `ONH` / `ONL` / `dOpen` / `RTH_Open` | Chart-real (label nits aside) | Untouched |
| `OR_Low` | Exact 29338.5 | Untouched |
| `OR_High` | 4.00 off; **not in either 15s file** | Out of scope (file vs chart, not 1m math) |
| `dVWAP` @ 10:00 NY | 29484.34 vs QT ~29484.50 | Untouched. Do **not** switch to tick VWAP |
| `prevSettlement` | Last RTH 1m close ≠ CME/QT settle | Out of scope (different definition) |
| `APOC` / `pAPOC` / `POC_rolling_*` | Still 1m typical | Untouched; honesty must say so |

### 3.3 Evidence lock (session 20 Aug 2026, MNQ)

Quantower target (Accumu recompute #2): **29453.25 / 29266.75 / 29366.75**.

| Source | VAH | VAL | POC | vs QT |
|---|---:|---:|---:|---|
| Engine 1m typical, 4-tick (today) | 29474.00 | 29275.00 | 29354.00 | +20.75 / +8.25 / −12.75 |
| Tick VAP, **1-tick** | 29456.50 | 29265.00 | 29370.00 | **+3.25 / −1.75 / +3.25** |
| Tick VAP, 4-tick | 29455.00 | 29264.00 | 29354.00 | +1.75 / −2.75 / **−12.75** |

Ticks close the allocation gap. Residual ~2–3 pts is VA walk / Last vs bid-ask / exact session template — acceptable vs 20 pts. **4-tick tick-VAP still misses POC by a full zone** because the 1.00 MNQ grid dominates. That is why product day aggregation becomes 1.

Wrong-window ticks (07:28–07:28 NY) did **not** reproduce QT. Window is part of the object.

### 3.4 Two knobs (do not conflate)

1. **Bin width** (`aggregation_ticks`) = grid size after allocation.  
2. **Allocation** = where each unit of volume is placed *before* binning.

8-tick `pw*` coarsens the grid. It still dumps 1m typical today. Coarser bins hide some of the miss; they do not remove it. TV changes allocation. Bin width is a separate product setting.

### 3.5 Session cut (normative)

- Instrument `eth_start` in `exchange_tz` (MNQ: 18:00 America/New_York) → next `eth_start`.
- In US DST that is 22:00 UTC → 22:00 UTC. **Do not hardcode UTC.**
- Filename labels (e.g. `10:00:00 PM` UTC) are **not** the cut. One export labeled 22:00 UTC contained **20:00 UTC** rows (16:00 NY).
- Loader must record first/last *row* timestamps. If the filename window disagrees, keep the rows and write a provenance warning. If the session cut is empty, that session contributes no histogram.
- Official engine `pd*` remains **ETH+RTH** (full CME session). RTH-only typical VAH 29451 was a false near-miss. Do not add an RTH-only `pdVA*` in this series.

### 3.6 Quantower tick file contract

| Field | Lock |
|---|---|
| Vendor profile | Quantower History Exporter **Tick – Tick – Last** only |
| Delimiter | `;` |
| Columns (normalized) | `Aggressor flag`; `Price`; `Volume`; `Time left` |
| Timestamp | `Time left`, **UTC** (13:30 UTC = 09:30 NY RTH open) |
| Price used | `Price` (Last). Ignore aggressor / bid / ask |
| Volume | `Volume` as float; drop rows with `volume <= 0` or unparseable price |
| One file or many | Many monthly files concatenated **in time order** |
| Do not use | Existing `format_profile: tick_capture` / `second_capture` — those run `_aggregate_capture_rows` into OHLCV and would recreate the allocation error |
| Do not use | `load_ohlcv` as the tick VAP path |

Synthetic CI fixtures may be a minimal `;` CSV with those four headers. Do **not** commit the 91 MB session-20 file.

### 3.7 Fail-closed ladder (normative — do not water down)

All four layers are required. Layer 3 (LC4) and layer 4 (`execute_study_cell` already returns `status=failed` on any `run_experiment` exception, including the LC4 `ValueError`) **already exist**. TV3 adds layers 1 and 2, must not weaken 3 or 4, and must add a regression test that the LC4 raise is recorded as `failed` (not a new fail path).

| Layer | When | Required outcome |
|---|---|---|
| 1. Author / generate | StudySpec (or `run_experiment` setup) **names** any of the nine VA tokens **and** `dataset.tick_paths` is missing/empty | `StudySpecError` / refuse **before** workers spawn / before expansion artifacts. Reason text must include `VA requires ticks` |
| 2. Engine emission | `compute_profile_levels` / `compute_all_levels` / product `compute_levels` have no prior-profile table | The nine columns are **absent**. Rolling POC still emits |
| 3. API signals (LC4) | Setup `selected_levels` / anchor names a missing column | Existing `ValueError`: `Setup references unavailable level columns: …` |
| 4. Study cell | A cell still runs and hits missing named VA | Ledger / index `status=failed` with the refuse reason. **Never** `ok` + 0 trades / empty zones |

Forbidden:

- Emitting the nine columns from 1m typical when ticks are absent.
- A missing-column path that returns `ok` (the `global_cluster` foot-gun named in the brief). LC4 already raises at `generate_signals`; study execute must record that as `failed`.
- An opt-in `va_source: typical_mvp` that writes the **same** token names or shares `LEVEL_ENGINE_VERSION` 11 identity with tick VAP.

15s-only runs that do **not** name VA tokens still get ONH, opens, OR, `dVWAP`, rolling POC, APOC. That is the farm-safe path.

### 3.8 Partial tick coverage

- Missing `tick_paths` + named VA → refuse (layer 1).
- Present `tick_paths` + a prior period with no ticks → that period’s prior VA is `NaN` (same as today’s first-period `NaN`). Do **not** fill from 1m typical.
- A 2y 1m file with one month of ticks is legal. Most `pd*` will be `NaN`. That is honest, not a fallback.
- Parked: `tick_coverage: require_full_range`. Not this series.

### 3.9 Aggregation (normative)

Two names. Do not conflate them (same dual-ownership as WMV product vs `compute_all_levels` kwargs).

| Product / API / `DEFAULT_LEVELS_SETTINGS` key | `compute_all_levels` / `compute_profile_levels` kwarg | Kwarg default | Product today | Product after TV3 |
|---|---|---:|---:|---:|
| `prior_day_profile_aggregation_ticks` | `prior_day_aggregation_ticks` | 1 | **4** | **1** |
| `prior_week_profile_aggregation_ticks` | `prior_week_aggregation_ticks` | 1 | 8 | 8 |
| `prior_month_profile_aggregation_ticks` | `prior_month_aggregation_ticks` | 1 | 10 | 10 |
| `value_area_pct` | `value_area_pct` | 0.70 | 0.70 | 0.70 |

`api.py` already maps `prior_*_profile_aggregation_ticks` → `prior_*_aggregation_ticks`. TV3 changes only the **product** day default (4 → 1). Do **not** rename the kwargs. Do not change week/month product defaults without a QT fixture.

### 3.10 §4 exception (identity cutover)

§4 rules 1 and 3 say new behavior is keyword-only / default-off and defaults reproduce legacy. That is the correct rule for **new families**. This series **replaces the allocation identity** of an existing always-on family that currently shares live-map names with a different object.

Allowed exception, locked:

- Golden-master legacy mode is untouched (§4.1 / §8.1).
- Session marks, VWAP, rolling POC, APOC, signals, and fills keep legacy values when their inputs are unchanged.
- The nine VA columns change both **values** (when ticks exist) and **presence** (absent without ticks).
- That change is versioned (`LEVEL_ENGINE_VERSION` 11) and fail-closed. It is **not** hidden behind a default-on typical fallback.

A PR that “preserves legacy `pdVAH` by keeping 1m typical when ticks are omitted” is out of scope and must be rejected.

---

## 4. Architecture (normative)

```text
15s Quantower HE  ──► derive 1m ──► session / VWAP / OR / rolling POC / APOC
                                      │
tick_paths[]      ──► TV1 loader ──► session-chunk (row timestamps)
                                      │
                                 TV2 histograms (Last×Volume per period)
                                      │
                                 _compute_profile (unchanged expander)
                                      │
                                 PriorProfileTable (tiny parquet)
                                      │
                                 TV3 join via existing shift(1) map
                                      ▼
                                 1m frame + pd*/pw*/pm* VA columns
                                      │
                                 study workers load 1m + table only
```

### 4.1 New modules

| Module | Owner PR | Responsibility |
|---|---|---|
| `thesistester/data/quantower_ticks.py` | TV1 | Parse one or many Tick–Tick–Last files; iterate session chunks; never aggregate to OHLC |
| `thesistester/levels/tick_vap.py` | TV2 | Build `PriorProfileTable` from chunks; persist/load parquet; call `_compute_profile` |
| `compute_profile_levels` kwarg `prior_profile_table=` | TV3 | If `None`, omit the nine columns; if set, map them. Rolling POC unchanged |

Do **not** add an `ingestion/` package. Do **not** teach `load_ohlcv` to return ticks. Do **not** store the 2y tick frame on `st.session_state`.

### 4.2 `PriorProfileTable` (locked shape)

A small, typed table — kilobytes, not gigabytes:

| Column | Meaning |
|---|---|
| `family` | `pd` / `pw` / `pm` |
| `period_key` | Join key **identical** to `compute_profile_levels`: day = `trading_session_date(...)` values (`datetime.date`); week = `to_period("W-SUN")`; month = `to_period("M")`. Parquet persists `str(key)` of those pandas objects and TV2 reconstructs the same dtype on load so `period_key.map(...)` joins. Week/month restore must pass explicit `freq` (`W-SUN` / `M`) — pandas 3.x parses `YYYY-MM-DD/YYYY-MM-DD` as minutes without it. Do **not** invent a second calendar or a “week-start date” alias |
| `VAH` `VAL` `POC` | Floats from `_compute_profile` |
| `n_ticks` `sum_volume` | Provenance |
| `period_start` `period_end` | First/last tick used (tz-aware) |
| `aggregation_ticks` | Bin multiple used for that family |
| `value_area_pct` | Must be 0.70 unless settings say otherwise |
| `va_source` | Literal `"tick_last"` |

Join semantics = today’s `_map_prior_profile_levels`: period *T* bars receive period *T−1* scalars. First period is `NaN`.

Optional research sidecar (not required for workers): per-session histograms. If written, they must not be opened by study workers.

### 4.3 RAM / runtime

| Constraint | Lock |
|---|---|
| One session | ~80–90 MB CSV / ~2.2–2.3M ticks is acceptable in one process |
| Full 2y as one pandas object | **Forbidden** (~40–60 GB / ~1.2B ticks) |
| Algorithm | For each file, for each session chunk: accumulate `bin → volume`, discard tick rows |
| Week / month | Merge **day histograms**, then expand. Do not re-read ticks |
| Study workers | Never reopen tick CSV. Read `PriorProfileTable` parquet + derived 1m |
| First ingest | Tens of minutes to a couple of hours for 24 months on the research box, then parquet |
| Cell time | Unchanged order of magnitude (still 1m bars, 8–12 workers) |

### 4.4 Identity

| Identity | After TV3 |
|---|---|
| `dataset_id` | Still the 15s/1m OHLCV identity (do not fold ticks into the 1m dataset hash) |
| Tick source id | SHA-256 over **sorted** tick file content hashes + profile id `quantower_tick_last` + session-cut policy id |
| Levels settings hash | Must include tick source id (or explicit `"none"`), aggregation ticks, `value_area_pct`, `va_source=tick_last`. `compute_levels_settings_hash` hashes the **settings dict only** — those fields must be keys **inside** that dict. A side-channel hash is a cache-collision defect |
| `LEVEL_ENGINE_VERSION` | **11** — invalidates persisted typical-price VA snapshots |
| Study identity hash | Changes when `tick_paths` is added (expected) |

Same 1m file without ticks vs with ticks must produce **different** levels identities. A cache hit that serves typical VA under version 11 is a defect.

### 4.5 Study pre-pass (normative)

`run_study` / `run_experiment` must not let 12 workers parse ticks.

Locked sequence:

1. Layer-1 refuse if VA tokens are named and `tick_paths` is missing/empty (**before** workers / before expansion artifacts).
2. When `tick_paths` is present: build or reuse `PriorProfileTable` **once** (parent process or first `compute_levels` write).
3. Persist next to the study ledger (`study.prior_profile.parquet`) and/or the levels artifact.
4. Each cell receives `dataset.prior_profile_table_path` (or equivalent) and **must not** reopen `tick_paths`.

`cache_policy=read_write` alone is not sufficient unless tests prove workers cannot miss and re-parse. Prefer an explicit table path on the expansion artifact.

### 4.6 Dataset keys

Add first-class:

```text
dataset.tick_paths: [<path>, ...]   # required for named VA; order irrelevant (loader sorts by first-row time)
dataset.tick_format_profile: quantower_tick_last   # optional; default that literal; reject others
```

`ingestion_mode` stays `15s_primary_derive_1m` (or `primary`). Ticks are **not** an ingestion mode and must not replace 15s.

API `_DATASET_KEYS` must admit the new keys (closed set today). Study schema validates shape when present; do **not** suddenly close every undocumented `dataset_extra` key in this series.

Launch / expand path pinning: `tick_paths` is a **list**. Extend `thesistester/study/launch.py` and `expand.py` (`_DATASET_PATH_KEYS` is a pair of scalar keys today). Missing tick files → refuse launch (same posture as missing `dataset.path`).

---

## 5. Setup and Study (locked)

Tokens stay in `PRIOR_PROFILE_LEVEL_NAMES` / `STUDY_STATIC_LEVEL_NAMES`. Do **not** remove them from the catalog (that would make a VA study an “unknown token” instead of “VA requires ticks”).

| Surface | After TV3 |
|---|---|
| `closed_level_token_set` | Still contains the nine names |
| `SUGGESTED_DEFAULT_LEVELS` | **Unchanged.** Today it already contains `pdPOC` (not `pdVAH` — `tests/test_setup_config.py` locks that). After omit, the existing `preferred = [c for c in SUGGESTED if c in columns]` intersection **drops** `pdPOC` on a 15s-only frame. That is correct, not a TV3 bug. Do **not** add `pdVAH` / `pdVAL`. TV4 honesty must say suggested `pdPOC` appears only when the column exists |
| StudySpec `core_level: [pdVAH]` without `tick_paths` | `StudySpecError` (`VA requires ticks`) |
| Same spec **with** existing tick files | Validates; generate proceeds |
| `validate_setup_config` | Still frame-blind (LC lock). Column existence stays in `api._require_level_columns` |
| Classic 15s-only Levels page | Frame **omits** the nine columns until ticks are attached |
| Classic Setup that still lists `pdVAH` | LC4 `generate_signals` raise; do not emit empty-ok |

`schema_version` stays `1`.

**Named-VA consumers already on this tree (TV3 must not surprise-break CI):**

| Surface | Today | TV3 lock |
|---|---|---|
| Study-unit fixtures | Dozens of tests use `core_level: [pdPOC]` / `pdVAH` as a *stand-in* legal token (`tests/study/test_study_schema.py`, `test_study_expand.py`, `test_study_builder.py`, `test_study_promote.py`, `test_study_execute.py`, `test_study_report.py`, `test_study_tools.py`, `test_study_launch.py`, `test_ah2_study_path_pin.py`, `tests/test_wvwap_mvwap.py`) | Layer-1 at `validate_study_spec` **will fail these**. Migrate stand-in cores to a non-VA static token (`ONH` unless the test is about prior-profile). Keep dedicated named-VA-without-ticks tests that expect `VA requires ticks` |
| Teaching example | `examples/studies/pdPOC_ma_confluence_battery.yaml` + agent routines (`ROUTINE_STAGE_FIRST.md`) | This **is** a named-VA study. Add `dataset.tick_paths` (list of strings). Validate/expand succeed when the key is a non-empty list; launch still refuses missing files (same posture as `dataset.path`). Do **not** silently change the core to `ONH` |
| `SUGGESTED_DEFAULT_LEVELS` | Contains `pdPOC` | Unchanged; intersection drops it when the column is absent |

`thesistester/data/__init__.py` re-exports derive/rolls helpers, **not** loaders. TV1 must **not** add a drive-by `load_ohlcv` / tick-loader export.

---

## 6. Point-in-time guarantees

Normative PIT claims (tested in TV2/TV3):

1. Period *T* VA uses only ticks with `timestamp` inside period *T*.
2. Bars in period *T+1* receive period *T* scalars (`shift(1)`). Period *T* bars never see period *T+1* ticks.
3. Appending a later session’s ticks must not change any earlier row’s `pd*` / `pw*` / `pm*`.
4. Mid-range truncation of the **1m** frame must not recompute VA from “end of dataframe” — VA comes from the table, not from 1m close.
5. Rolling POC / APOC / `dVWAP*` / session marks on the same fixture stay **series-equal** to pre-TV3 outputs when their gates/settings match.

Register the new prior-VA rows in `docs/POINT_IN_TIME_GUARANTEES.md` in TV3. Existing typical-price `pdVAH` future-shock tests in `tests/test_r3_point_in_time.py` are rewritten in TV3 to the tick-table path (or to “columns absent”).

---

## 7. Regression-safety framework mapping

Maps to `ENGINEERING_PROPOSAL.md` §4:

| Rule | Application here |
|---|---|
| 1. Additive-only | Tick loader and table are additive. VA **identity** is the locked §3.10 exception |
| 2. Golden-masters | `run_legacy_pipeline` never calls `compute_all_levels`; goldens stay untouched. No `GOLDEN_REGEN` |
| 3. Opt-in default-off | New family gates stay default-off. VA cutover is fail-closed omit, not a new on-switch for typical |
| 4. Schema / engine version | `LEVEL_ENGINE_VERSION = 11`; `PriorProfileTable` carries `va_source=tick_last` |
| 5. Future-shock PIT | §6 tests on the tick table |
| 6. `session_state` stability | No new required keys. Optional tick-path widget keys only in TV4, recorded in `ARCHITECTURE.md` there |
| 7. Determinism | Pure pandas/numpy; file order canonicalized by first-row time; no randomness |
| 8. Same-PR docs | §9 list per PR |
| 9. CI green | Full pytest + ruff. Session-20 file is **not** a CI fixture |
| 10. Honesty | Typical ≠ tick VAP; APOC/rolling POC still typical; residual ~2–3 pts documented |

### 7.1 Non-regression contract (normative)

| Surface | Required outcome |
|---|---|
| `dVWAP_RTH` / `dVWAP` / `wVWAP` / `mVWAP` | **Value-identical** on overlapping rows |
| Session marks / OR / Asia / London / opens | **Value-identical** |
| `POC_rolling_*` | **Value-identical** (still 1m typical) |
| `APOC` / `pAPOC` | **Value-identical** (still 1m typical) |
| Signal / 3c / OTF / `simulate_trades` / R12 | **Untouched** |
| `_compute_profile` expander | **Value-identical** on the existing typical fixtures when fed the same price/volume vectors |
| `SUGGESTED_DEFAULT_LEVELS` | **Unchanged** (already contains `pdPOC`; do not add `pdVAH`) |
| Study schema version | Stays `1` |
| Goldens | No regen |
| Farm studies that do not name VA tokens | Still generate on 15s-only |

**Allowed intentional deltas (TV3):**

1. Nine VA columns absent without a tick table (were always-on typical).
2. Nine VA columns are tick VAP when a table is present (different numbers).
3. Product `prior_day_profile_aggregation_ticks` 4 → 1.
4. `LEVEL_ENGINE_VERSION` 10 → 11.
5. StudySpec / `run_experiment` refuse named VA without `tick_paths`.
6. Stand-in `pdPOC` study fixtures migrate to a non-VA core; `pdPOC_ma_confluence_battery.yaml` gains `tick_paths`.

**Forbidden:**

- Typical fallback under the same names.
- Tick stream on the simulation clock.
- Renaming `compute_all_levels` / `compute_profile_levels` kwargs to the product `*_profile_*` keys.
- `load_ohlcv` / `tick_capture` as the VAP path.
- Golden / `simulate_trades` / R12 / 3c edits.
- Help-path moves. Drive-by assistant/CAI/RUX edits.
- Changing week/month product bins without a QT fixture.
- Developing VA, bid-ask VAP, `typical_mvp` same-name alias.

---

## 8. Scoped PRs

Five PRs. Do not merge TV*+1 before TV*. Do not implement engine cutover in TV0–TV2. Do not put Data-page widgets in TV3.

### TV0 — Plan lock (this PR)

| Field | Value |
|---|---|
| **Title** | `TV0: lock tick-VAP implementation plan` |
| **Scope** | `docs/TICK_VAP_IMPLEMENTATION_PLAN.md`; index lines in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md` |
| **Behavior** | Documentation only. No `.py` changes |
| **Regression** | Docs-only; no goldens; no `LEVEL_ENGINE_VERSION` |
| **Acceptance** | Plan contains locked object (§3), fail-closed ladder (§3.7), architecture (§4), PIT (§6), fully scoped TV1–TV4 (§8), test plan (§10), copy-ready prompts (§11) |
| **Out of scope** | Any engine / ingest / UI / test implementation |

### TV1 — Tick loader + monthly combine

| Field | Value |
|---|---|
| **Title** | `TV1: add Quantower tick-last loader` |
| **Scope** | New `thesistester/data/quantower_ticks.py`; `tests/test_quantower_ticks.py`; tiny synthetic `;` fixtures under `tests/fixtures/ticks/`. Do **not** add an export to `thesistester/data/__init__.py` (that package does not re-export loaders) |
| **Behavior** | Parse Tick–Tick–Last; combine many files in first-row time order; iterate CME session chunks from **row** timestamps; record filename-vs-row mismatch as warning metadata; never call `_aggregate_capture_rows` / `load_ohlcv` |
| **Regression** | No `profile.py` / `all.py` / `api.py` / study / golden / `LEVEL_ENGINE_VERSION` touch |
| **Acceptance** | §10.1 tests green; full `pytest -q` / ruff |
| **Out of scope** | VAP math; `compute_profile_levels`; Data page; StudySpec keys; product defaults |

**TV1 file-level checklist**

1. New loader with an explicit profile id `quantower_tick_last`.
2. Required columns after alias normalize: price, volume, timestamp (`Time left`). Aggressor optional and unused.
3. `source_tz` default UTC; convert to instrument `exchange_tz` only for session membership; keep a UTC series for provenance.
4. `iter_tick_files(paths) -> Iterator[TickChunk]` where each chunk is one CME session (or a file slice that the caller session-cuts). Must not materialize all files.
5. Combine: sort files by first parsed timestamp; reject overlapping duplicate row identity if detected (same timestamp+price+volume+file-index) only when it is an exact duplicate file; do not silently drop real prints.
6. Empty file / missing columns / unparseable time → `DataValidationError` (or a dedicated `TickIngestError` subclass).
7. Unit tests: two monthly stubs concatenate in order; session cut at 18:00 NY; filename says 22:00 UTC but rows start 20:00 UTC → rows win + warning flag; volume≤0 dropped.

### TV2 — Prior-profile table (library only)

| Field | Value |
|---|---|
| **Title** | `TV2: build tick VAP prior-profile table` |
| **Scope** | New `thesistester/levels/tick_vap.py`; persist/load helpers (same module or `thesistester/persistence/` only if an existing artifact helper is the natural home — prefer the new module); `tests/test_tick_vap.py`; reuse `_compute_profile` from `profile.py` (**do not copy** the expander) |
| **Behavior** | From TV1 chunks, accumulate Last×Volume histograms per day/week/month key; run `_compute_profile`; return `PriorProfileTable`. Persist parquet. `compute_all_levels` **still emits typical VA** (cutover is TV3) |
| **Regression** | Expander bit-identical on existing typical price/volume vectors (`tests/test_phase3_levels.py` vectors fed through `_compute_profile` directly). No `LEVEL_ENGINE_VERSION`. No `all.py` emission change |
| **Acceptance** | §10.2 tests green; expander isolation; week/month merge-from-day-histograms proven |
| **Out of scope** | Fail-closed omit; StudySpec; product day-bin 4→1; Data page |

**TV2 file-level checklist**

1. `build_prior_profile_table(chunks, instrument, aggregation ticks, value_area_pct) -> PriorProfileTable`.
2. Day / week / month keys **copied** from `compute_profile_levels` (`trading_session_date` → `W-SUN` / `M`). Do not invent a second calendar.
3. Persist `to_parquet` / `from_parquet` round-trip with the locked columns.
4. Hand-computed 1-tick fixture: two sessions, known prints, assert VAH/VAL/POC and `shift(1)` *mapping function* (table only; 1m join is TV3).
5. Prove week histogram equals concatenating constituent day histograms.
6. Do not import Streamlit. Do not open 15s files.

### TV3 — Identity cutover + fail-closed + version 11

| Field | Value |
|---|---|
| **Title** | `TV3: emit tick VAP as pd/pw/pm VA and fail closed without ticks` |
| **Scope** | `thesistester/levels/profile.py`; `thesistester/levels/all.py`; `thesistester/levels/defaults.py` (product day key `prior_day_profile_aggregation_ticks` 4→1 only; do not rename `prior_day_aggregation_ticks` kwargs); `thesistester/persistence/local_store.py` (`LEVEL_ENGINE_VERSION = 11` + tick source **key** in the settings dict hashed by `compute_levels_settings_hash`); `thesistester/api.py` (`_DATASET_KEYS`, `compute_levels` / `run_experiment` wiring, layer-1 refuse); `thesistester/study/schema.py` (layer-1); `thesistester/study/launch.py` + `expand.py` (list path pin); `thesistester/study/execute.py` (**pre-pass table only** — cell `failed` already exists); rewrite typical-pinning + stand-in-`pdPOC` tests listed below; `examples/studies/pdPOC_ma_confluence_battery.yaml` `tick_paths`; living engine docs in §9.2 |
| **Likely test edits** | `tests/test_phase3_levels.py` (prior-VA tests need a table or assert omit); `tests/test_r3_point_in_time.py` (prior-VA future-shock); `tests/test_session_levels.py` if it pins `pdVA*`; `tests/test_stage1_level_plumbing.py` (membership of always-on columns); study-unit fixtures that use `pdPOC`/`pdVAH` as a stand-in core (migrate to `ONH` except dedicated refuse tests) — see §5 table; `examples/studies/pdPOC_ma_confluence_battery.yaml` (`tick_paths`); new `tests/test_tick_vap_cutover.py` |
| **Behavior** | No table → nine columns absent; rolling POC remains. Table present → nine columns are tick VAP. Named VA without `tick_paths` refuses. Product day bin 1. Version 11 |
| **Regression** | §7.1 isolation; goldens untouched; farm 15s-only non-VA studies still generate |
| **Acceptance** | §10.3–10.4 green; `pytest -q` of the listed files plus `tests/test_golden_master.py` plus full `pytest -q` / ruff |
| **Out of scope** | Data-page / Study Builder widgets; USER_GUIDE how-to; thesis compiler; `typical_mvp`; week/month bin changes; APOC rewrite |

**TV3 file-level checklist**

1. `compute_profile_levels(..., prior_profile_table=None)`. `None` → do not join the nine columns. Table → join via existing `_map_prior_profile_levels` key/shift semantics (adapt to read scalars from the table instead of allocating 1m typical).
2. Delete the 1m-typical allocation path for `pd*` / `pw*` / `pm*` only. Keep typical prices **only** for rolling POC.
3. `compute_all_levels` threads the new kwarg. Keyword defaults for gates stay off.
4. Product `prior_day_profile_aggregation_ticks` 4 → 1. Comment why (session-20 POC).
5. `LEVEL_ENGINE_VERSION = 11`. Levels identity includes tick source id or explicit “none”.
6. `dataset.tick_paths` + optional `tick_format_profile` on API dataset. Unknown profile → fail closed.
7. Study validate: if any factor token ∈ `PRIOR_PROFILE_LEVEL_NAMES` and tick paths empty → `StudySpecError` containing `VA requires ticks`. Migrate stand-in `pdPOC` fixtures to `ONH` (§5). Add `tick_paths` on `pdPOC_ma_confluence_battery.yaml`.
8. `run_experiment` / `compute_levels`: same refuse when the setup/selected levels name VA and no table/paths.
9. `run_study` pre-pass builds the table once; workers get the parquet path. Do **not** rewrite `execute_study_cell`’s existing Exception → `failed` path; add a test that LC4’s `Setup references unavailable level columns:` is recorded as `failed`.
10. Launch refuses missing tick files when the key is present.
11. Rewrite tests that assumed always-on typical `pdVAH`. Do **not** preserve those expected numbers under the old names.
12. Same-PR docs in §9.2. One-line LC plan amendment: contract #3 superseded by TV for prior-profile allocation.
13. Optional: `tests/test_tick_vap_session20.py` **skips** unless `THESISTESTER_QT_TICK_FIXTURE` points at the `b9bd9777` file. Expected 1-tick band: within a few points of 29453.25 / 29266.75 / 29366.75. 4-tick must stay near 29455 / 29264 / 29354, **not** 29474 / 29275. `dVWAP` @ 10:00 NY remains ~29484.34.

### TV4 — Authoring UX + Help honesty

| Field | Value |
|---|---|
| **Title** | `TV4: tick-path authoring + VA honesty copy` |
| **Scope** | `pages/1_Data.py` (optional multi-file tick attach; no 15s replacement); `thesistester/study/builder.py` + Studies Build tab (first-class `tick_paths`); `docs/USER_GUIDE.md`; `docs/STUDY_RUNNER.md`; `docs/ARCHITECTURE.md` (widget/`session_state` keys if any); `docs/ASSUMPTIONS_AND_LIMITATIONS.md` remaining Help-facing sentences if TV3 left a pointer; `README.md` if it still claims typical VA is the live object; tests for emit/schema of `tick_paths` only |
| **Behavior** | Operator can attach tick files beside 15s. Copy states: no ticks → no `pdVA*`; those names are Quantower-style tick VAP; APOC/rolling POC remain typical |
| **Regression** | No engine math; no `LEVEL_ENGINE_VERSION`; no goldens. New-draft default **does not** require ticks (farm stays 15s-only). Builder emit includes `tick_paths` only when the operator set them |
| **Acceptance** | Emit/load round-trip; 15s-only new draft still valid; Help sentences match §3.1 / §3.7 |
| **Out of scope** | Engine expander; day-bin; session-20 fixture in git; thesis-compiler family unless an existing regex already claims “VAH” as typical |

TV4 may not fold into TV3. Engine-identity review stays separate from Streamlit/Help copy.

---

## 9. Documentation updates

### 9.1 Same PR as TV0 (index only)

| Doc | Update |
|---|---|
| `docs/README.md` | Add this plan under normative engine/data contracts |
| `docs/ENGINEERING_ROADMAP.md` | Table row + series stub (TV0 locked, TV1–TV4 pending) |
| `docs/AGENT_GUIDE.md` | One pointer next to WMV / AO |
| This doc | Status = TV0 plan lock |

### 9.2 Same PR as TV3 (engine contract)

| Doc | Update |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Prior-profile is tick VAP when ticks provided; **absent** otherwise; not 1m typical under these names; APOC/rolling POC still typical; day bin 1; `LEVEL_ENGINE_VERSION` 11; residual ~2–3 pts |
| `docs/POINT_IN_TIME_GUARANTEES.md` | Replace typical-allocation prior-VA rows with tick-table PIT |
| `docs/METRICS_GLOSSARY.md` | `pdVAH` / `pdVAL` / `pdPOC` / `pw*` / `pm*` = tick Last×Volume VAP, prior period, 70% expander |
| `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md` | One-line amendment of locked contract #3 |
| `docs/ENGINEERING_ROADMAP.md` | Mark TV1–TV3 landed when each merges (TV3 PR marks TV3) |
| This doc | Status → TV3 implemented |

### 9.3 Same PR as TV4 (Help / UI)

| Doc | Update |
|---|---|
| `docs/USER_GUIDE.md` | How to attach Quantower tick exports; VA requires ticks; 15s still the bar clock |
| `docs/STUDY_RUNNER.md` | `dataset.tick_paths`; generate refuse text |
| `docs/ARCHITECTURE.md` | Data / Study Builder keys only if TV4 adds them |
| This doc | Status → series complete ✅ |

Do **not** reopen archived `docs/archive/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md` beyond a pointer if a reviewer asks. Living contract is this file.

---

## 10. Test plan (normative)

New files:

```text
tests/test_quantower_ticks.py      # TV1
tests/test_tick_vap.py             # TV2
tests/test_tick_vap_cutover.py     # TV3
tests/test_tick_vap_session20.py   # TV3, skip-if-no-env
```

Hand-compute expected VAH/VAL/POC. Do not snapshot opaque frames. Do not commit the 91 MB export.

### 10.1 TV1

1. Parse a 4-column `;` stub; UTC 13:30 → 09:30 NY membership.
2. Two files concatenate in first-row time order.
3. Session iterator cuts at 18:00 NY, not at filename `10:00:00 PM`.
4. Filename/row mismatch sets a warning flag; rows still load.
5. `volume <= 0` and NaN price dropped.
6. Missing `Price` / `Time left` raises.
7. Loader does not import `pages` / Streamlit and does not call `load_ohlcv`.

### 10.2 TV2

8. Hand-computed 1-tick two-session table (known Last/Volume prints).
9. `_compute_profile(typical_vectors)` matches current phase-3 expected triples (expander isolation).
10. Week table = merge of day histograms, not a second pass over ticks.
11. Parquet round-trip equality on locked columns.
12. Empty chunk → no row for that period (not typical fill).

### 10.3 TV3 isolation / cutover

13. `compute_profile_levels(df)` without a table → no `pdVAH`…`pmPOC`; `POC_rolling_30min` still present and value-equal to pre-change on the same fixture.
14. `compute_all_levels(..., session_vwap_enabled=True)` `dVWAP*` series-equal to a frozen vector from current formulas.
15. Session marks on `tests/test_session_levels.py` fixtures value-equal.
16. With a table, `shift(1)` maps prior session tick VAP onto the next session’s 1m rows; first session `NaN`.
17. Future-shock: append a later tick session → earlier `pd*` unchanged.
18. Product default day aggregation is 1; `DEFAULT_LEVELS_SETTINGS` week/month remain 8/10.
19. `LEVEL_ENGINE_VERSION == 11`.
20. Named `pdVAH` StudySpec without `tick_paths` raises `VA requires ticks`. Stand-in study fixtures that are not about prior-profile use `ONH` and still validate without ticks.
21. Same named-VA spec with a temp tick file validates. `pdPOC_ma_confluence_battery.yaml` expands once `tick_paths` is a non-empty list.
22. `generate_signals` with `selected_levels=["pdVAH"]` on a no-table frame raises the LC4 `Setup references unavailable level columns:` error.
23. Study cell executor records `failed`, not `ok`, when that raise occurs (`execute_study_cell` already does this — assert it).
24. 15s-only StudySpec whose factors are `ONH` / `dVWAP` still validates and does not require ticks.
25. Goldens: `tests/test_golden_master.py` unchanged.

### 10.4 TV3 optional desk hook

26. If `THESISTESTER_QT_TICK_FIXTURE` is the `b9bd9777` session-20 file: 1-tick VAP within a few points of **29453.25 / 29266.75 / 29366.75**; `dVWAP` @ 10:00 NY ~29484.34; OR 15 / ONH / `RTH_Open` / `dOpen` unchanged vs the 15s engine.

### 10.5 TV4

27. Builder emit with operator-selected tick paths writes `dataset.tick_paths` as a list of strings.
28. New draft without ticks omits the key and still emits valid 15s-primary YAML.
29. Launch pin resolves relative `tick_paths` the same way as `dataset.path`.

---

## 11. Copy-ready implementation prompts

### 11.1 TV1

```text
Implement TV1 from docs/TICK_VAP_IMPLEMENTATION_PLAN.md.

Work regression-safe (docs/ENGINEERING_PROPOSAL.md §4). Add
thesistester/data/quantower_ticks.py for Quantower History Exporter
Tick–Tick–Last (semicolon; Aggressor flag; Price; Volume; Time left;
stamps UTC). Accept one path or many monthly paths. Concatenate in
first-row time order. Iterate CME session chunks using instrument
eth_start in exchange_tz (row timestamps, never the filename window).
Record filename-vs-row mismatch as warning metadata.

Do not call load_ohlcv or _aggregate_capture_rows. Do not touch
profile.py, all.py, api.py, study/, goldens, or LEVEL_ENGINE_VERSION.

Add tests/test_quantower_ticks.py for §10.1. Tiny fixtures only.
Same-PR: mark TV1 landed on this plan + ENGINEERING_ROADMAP only if
you also update those two docs; otherwise leave status to TV0 until
TV3 docs pass.

PR body must include a Regression safety paragraph: loader-only;
no level values; no goldens.
```

### 11.2 TV2

```text
Implement TV2 from docs/TICK_VAP_IMPLEMENTATION_PLAN.md.

Work regression-safe. Add thesistester/levels/tick_vap.py that builds
PriorProfileTable from TV1 session chunks. Reuse
thesistester.levels.profile._compute_profile (do not copy the
expander). Period keys must match compute_profile_levels
(trading_session_date → W-SUN / M). Accumulate bin→volume per
session, discard tick rows, merge day histograms for week/month.
Persist/load parquet with the locked columns. va_source is tick_last.

Do not change compute_profile_levels emission (typical VA still
on). No LEVEL_ENGINE_VERSION. No api/study/Data page.

Add tests/test_tick_vap.py for §10.2 including expander isolation
on existing typical vectors. PR Regression safety: library-only;
expander bit-identical; no goldens.
```

### 11.3 TV3

```text
Implement TV3 from docs/TICK_VAP_IMPLEMENTATION_PLAN.md.

Work regression-safe with the locked §3.10 exception: do NOT keep
1m-typical pdVAH/pdVAL/pdPOC/pw*/pm* when ticks are absent.

compute_profile_levels(prior_profile_table=None) omits the nine VA
columns and still emits rolling POC from 1m typical. When a table
is provided, join via existing shift(1) period semantics. Delete
typical allocation for those nine names only.

Wire dataset.tick_paths through api._DATASET_KEYS, compute_levels,
run_experiment. StudySpec layer-1: named VA tokens without tick_paths
raises StudySpecError containing "VA requires ticks". run_study
builds PriorProfileTable once; workers never reopen tick CSV; LC4
missing-column raises become cell status=failed, not ok.

DEFAULT_LEVELS_SETTINGS prior_day_profile_aggregation_ticks 4 → 1
(product key). Do not rename compute_all_levels kwargs
(prior_day_aggregation_ticks). Week/month stay 8/10.
LEVEL_ENGINE_VERSION 10 → 11. Tick source id or explicit none must
be a key inside the settings dict hashed by compute_levels_settings_hash.

Rewrite tests/test_phase3_levels.py and tests/test_r3_point_in_time.py
prior-VA cases. Migrate stand-in pdPOC study fixtures to ONH (§5).
Add tick_paths on examples/studies/pdPOC_ma_confluence_battery.yaml.
Add tests/test_tick_vap_cutover.py for §10.3.
Optional skip-if-no-env session-20 hook. No golden regen. No Data
page widgets. No APOC rewrite. No tick VWAP.

Same-PR docs: ASSUMPTIONS, POINT_IN_TIME_GUARANTEES, METRICS_GLOSSARY,
one-line LC contract #3 amendment, roadmap TV3 status.

PR body must include a Regression safety paragraph: goldens untouched
(run_legacy_pipeline never calls compute_all_levels); dVWAP/session
marks/rolling POC/APOC value-identical; farm non-VA 15s studies still
generate; cache bump is the VA identity change.
```

### 11.4 TV4

```text
Implement TV4 from docs/TICK_VAP_IMPLEMENTATION_PLAN.md.

No engine math, no LEVEL_ENGINE_VERSION, no goldens. Add Data-page
and Study Builder controls to attach one-or-many Quantower tick-last
files beside the existing 15s path. New drafts do not require ticks.
Emit dataset.tick_paths only when set. Pin/launch missing tick files
fail closed.

Update USER_GUIDE, STUDY_RUNNER, ARCHITECTURE widget keys.
Honesty: pdVA* is tick VAP; no ticks → no those columns; APOC and
rolling POC remain typical; studies keep walking 1m.

Keep Help paths unchanged. Mark this plan series complete.
```

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Silent typical fallback under the same names | §3.7 + §3.10; reject any PR that emits typical into `pdVAH` |
| Ticks on the simulation clock | Explicit non-goal; no `simulate_trades` / 3c / R12 edits |
| 12 workers × 2y ticks | Session histograms + `PriorProfileTable`; study pre-pass |
| Filename window ≠ rows | Rows win; warning metadata; session-20 wrong-window fixture as a negative test |
| 4-tick POC still non-transferable | Product day bin → 1 in TV3 |
| Week/month claimed as QT-real | Honesty: same object type, not QT-locked |
| `tick_capture` reused | Forbidden; new profile id `quantower_tick_last` |
| LC4 `ok`+0-trades foot-gun | Layer 1 refuse + layer 4 `failed` |
| Farm blocked | Non-VA 15s studies never require ticks |
| Golden brittleness | No `compute_all_levels` in legacy pipeline; no regen |
| Session-20 91 MB in git | Env-gated optional test only |
| Cache serves typical VA after v11 | Tick source id in levels identity; version 11 |
| Partial coverage silently filled | `NaN` only; no typical fill |
| Drive-by APOC “fix” | Out of scope; isolation tests |

---

## 13. Explicit non-goals

- Tick-derived OHLC, OR, ONH, opens, Asia/London
- Tick `dVWAP*` / `wVWAP` / `mVWAP`
- Touch / 3c / R12 on ticks
- Developing `dVAH` / `dVAL` / `dPOC`
- APOC / rolling-POC allocation change
- Bid/ask / aggressor VAP; TPO
- `va_source: typical_mvp` same-name alias
- 8-tick weekly as a substitute for tick allocation
- `OR_High` 4.00 file-vs-chart gap; CME official settlement
- Kill-list / fresh-round / flatten leak / OTF matrix / Study path identity
- Golden regeneration; Help-path moves
- In-process study execute; new factor axes; `schema_version` bump
- Loading the full 2y tick frame into pandas
- Blocking the farm on this series

---

## 14. Per-PR acceptance checklist (§4.2)

Mandatory for TV0 (docs):

- [ ] Plan locks object, fail-closed ladder, architecture, and TV1–TV4 scopes
- [ ] Indexed from README / roadmap / AGENT_GUIDE
- [ ] No `.py` changes

Mandatory for TV1:

- [ ] Session-chunk + monthly combine tests
- [ ] Filename ≠ rows proven
- [ ] No profile/API/golden touch
- [ ] PR body has a Regression safety paragraph

Mandatory for TV2:

- [ ] Hand-computed table values
- [ ] Expander isolation
- [ ] Parquet round-trip
- [ ] No emission cutover
- [ ] PR body has a Regression safety paragraph

Mandatory for TV3 (engine):

- [ ] Omit-without-table + tick-table join + `shift(1)`
- [ ] Future-shock PIT
- [ ] `dVWAP*` / session marks / rolling POC / APOC isolation
- [ ] Layer-1 refuse + LC4 + cell `failed` (assert existing execute path)
- [ ] Stand-in `pdPOC` study fixtures migrated; teaching example has `tick_paths`
- [ ] Day bin 1 (product key); kwargs still `prior_*_aggregation_ticks`; version 11
- [ ] Legacy golden-masters preserved
- [ ] Docs updated in the same PR
- [ ] PR body has a Regression safety paragraph
- [ ] Narrow surface; no drive-by refactors

Mandatory for TV4 (copy / authoring):

- [x] tick_paths emit/load; 15s-only draft still valid
- [x] Help/USER_GUIDE honesty
- [x] No engine or golden touch

---

## 15. Desk vs CI fixtures

| Role | Location | In git? |
|---|---|---|
| CI tick stubs | `tests/fixtures/ticks/` | Yes (tiny) |
| Session-20 ticks (`b9bd9777`) | Research PC Quantower export | **No** — env `THESISTESTER_QT_TICK_FIXTURE` |
| Wrong-window ticks (`48f94f7c`) | Research PC | **No** — optional negative test |
| 15s wider / 2y 15s | Existing research paths | Unchanged; not required for TV1–TV2 |

If engineering does **not** ship TV3, the honest product choice in the brief stands: leave `pd*` / `pw*` / `pm*` VA **off the live map** (or label them engine-only). Do not mix “green VA cell” with “I will fade Quantower VAH.”
