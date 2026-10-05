# Tick stitch → VA / APOC — implementation plan (TS)

**Document type:** Implementation plan (fully scoped PRs). This file is the review copy of the plan. **This PR ships no runtime, no packet, no config, and no data.**
**Date:** 2026-10-05
**Status:** Plan lock. No study. No code in the plan PR.
**Series code:** **TS** (Tick Stitch for VA + APOC). Not TV (Tick VAP, landed). Not AP (A-period source, landed). Not RP (rolling POC). Not MW.
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist.
**Parity baseline:** `main` / farm production `0ebc149406f91ae71447561d9c42184b130ca0ac` (#610). Checked 2026-10-05: `origin/main` has not moved past this commit. If `main` moves before TS5 lands, keep **behaviour** parity against `0ebc1494` (same outputs except wall-clock timestamps) and name the new SHA in the TS5 PR.

**Inputs (attached to the planning chat; farm copies under `~/thesistester/_scratch/`):**

| Artifact | Role |
|---|---|
| `tick_stitch_plan.json` | Ordered, non-overlapping segment array (46 segments) |
| `tick_stitch_meta.json` / `tick_stitch_list.md` / `.json` | Coverage, holes, exclusions, include list (39 files, 36,415,038,585 bytes ≈ 33.9 GiB) |
| `tick_stitch_patch_notes.md` | Patches A/B (2026-10-06) and D/E + X1 (same day) |
| `tick_quality_report.md` / `.json` | Pre-patch drift/coverage sample (40 segments / 37 files). **Hole list is stale.** Drift result is not. |
| `Plan_Tick_Lauf_Program_B.md` | Earlier German design notes. **Background only.** This file wins on any conflict. |

**Does not reopen:** TV1–TV4 object (Last×Volume, 70% expander, `shift(1)` prior map, bins 4/8/10, fail-closed without ticks). AP2/AP3 A-period definition (`[RTH_open, RTH_open+30min)` in `exchange_tz`, `tick_last_volume_v1`). RP2 sliding POC. MW worker-memory flag. 15s ingest / 1m derive. `simulate_trades`. Golden regeneration. Roll synthesis. Building 15s bars from ticks.

**Amends (in the PR that makes the sentence true, never in this plan PR):** `ASSUMPTIONS_AND_LIMITATIONS.md`, `POINT_IN_TIME_GUARANTEES.md`, `ARCHITECTURE.md`, `PROGRAM_B_OPERATOR_RUNBOOK.md`, `ENGINEERING_ROADMAP.md`, `docs/README.md` (index row only).

---

## 1. Purpose

Program B Run 2 (15-second fade, 898 cells) is finished. The next run computes **Value Area (VA) and APOC from ticks** for the same window as that 15s run. Everything else stays on the existing 15s bars.

Ticks are an ingest input for nine prior-profile tokens (`pdVAH` `pdVAL` `pdPOC` `pw*` `pm*`) and for `APOC` / `pAPOC`. They are **not** a second bar clock.

Series complete when:

1. A stitch plan (ordered trim windows over untouched Rithmic Tick–Tick–Last CSVs) can be verified and streamed per CME session without loading all ticks into a worker.
2. X1 (2025-11-07 17:58:14.581–19:00:00.009 UTC) is filled from 15s residual volume-at-price, flagged, and impact-tested. APOC that day is untouched.
3. An hourly hole guard refuses a cut-short export.
4. With the tick option **off**, Run 2 15s cells reproduce `0ebc1494` bit-identically (wall-clock timestamps excepted).
5. Farm copy is NVMe-only; workers never read `/mnt/nas-trading`. A small pilot study runs before the 253-cell tick packet.

---

## 2. Fixed decisions (do not reopen)

| Lock | Rule |
|---|---|
| Bars | Existing MNQ 15s CSV (`quantower_history_exporter`, UTC, `15s_primary_derive_1m`, 344,135,035 bytes, `2024-07-31 22:00:00`–`2026-08-06 20:59:45` UTC). Do not rebuild bars from ticks. |
| Tick input | Stitch plan: 39 include files, 46 segments, ~33.9 GiB. Do **not** merge into one CSV. Do **not** create `data/mnq_tick_last.csv`. |
| Filenames | Lie. Trust segment bounds. `parse_quantower_tick_filename_window` matches only `M_D_YYYY` and is unused on the stitch path. |
| Header | `Aggressor flag;Price;Volume;Time left;`. Naive timestamps = UTC. No bid/ask, no contract column. |
| Same-ms prints | Real trades. No global dedupe. Overlaps removed only by segment trims. |
| Clip | Ticks clipped to 15s session/bar windows (drops halt-time 1-lot prints and 15s-missing edge bars). |
| Expected holes | No action: 2025-11-28 02:24/02:44–13:30 UTC (also missing in 15s) and Thanksgiving weekends. |
| X1 | **Fill** 2025-11-07 17:58:14.581–19:00:00.009 UTC from 15s residual VAP. Per-day quality flag. **Keep APOC** (A-period outside the hole). `tick_stitch_meta.json` policy `exclude_tick_full_session_VA` is **superseded**. |
| Default | Stitch / fill / new dataset keys **off**. `dataset.path`, `load_ohlcv`, 15s ingest, and 1m derive are not edited. |
| Workers | 12. Peak ≈ 3.7–4.5 GiB each. No worker may open farm tick CSVs or `list()` all sessions. |
| Rolls | `data/rolls.py` stays idle. No contract column → no roll logic. |
| Goldens | No regeneration. `LEVEL_ENGINE_VERSION` stays 11. Identity moves via additive keys. |
| Packets | Hand-edits of generated YAML are not durable. Change `generate_program_b_yaml.py` + validator together. |
| Revert | Each PR independently revertible. `main` stays green. |

### 2.1 Verified code facts (re-checked on `0ebc1494`)

| Fact | Where |
|---|---|
| `iter_tick_files` hashes each whole file in `_peek_tick_file` before the first yield, concatenates same-session row overlaps, rejects byte-identical files, ignores trim windows. | `thesistester/data/quantower_ticks.py` |
| Filename window regex is `M_D_YYYY` AM/PM only. Dot names (`1.2.25`, `26.9.24`) return `None`. | `parse_quantower_tick_filename_window` |
| Prior-day VA is already a once-per-parent histogram → parquet. | `study/execute.py` `_prepare_prior_profile_table` → `build_prior_profile_table_from_paths` |
| APOC rebuilds from `tick_paths` via `list(iter_tick_files(...))` when `apoc_tick_table` is omitted. | `apoc_tick.py:240`, `apoc.py:232` |
| Rolling POC also `list(iter_tick_files(...))` then concatenates all ticks. | `rolling_poc_tick.py:180` |
| Program B tick packet sets `poc_windows: ["30min"]` even though rolling POC is not a Program B core. 15s packet sets `poc_windows: []`. | `generate_program_b_yaml.py` `_levels` |
| Tick placeholder is `data/mnq_tick_last.csv`. Launch refuses missing files. Validator requires exact `TICK_PATHS`. | `generate_program_b_yaml.py:109`, `validate_program_b_yaml.py:162` |
| Product VA bins are 4 / 8 / 10. Value area 70%. MNQ `tick_size` 0.25, `eth_start` 18:00, `rth_start` 09:30, `exchange_tz` America/New_York. | `levels/defaults.py`, `config.py` |
| A-period is `[RTH_open, RTH_open+30min)` in exchange time. 2025-11-07 is US standard time → 14:30–15:00 UTC. | `apoc_candidates.select_a_period_rows`, stitch meta |

The current loader cannot express the stitch (same file, five disjoint windows on `1e2d3445…`, 6,684,663,701 bytes) and cannot run on 34 GiB inside a 4.5 GiB worker.

### 2.2 Quality-report vs current stitch

`tick_quality_report.md` was generated **2026-10-05 19:42** on the **pre-patch** plan (40 segments, 37 includes). It is evidence of **no timezone or price-scale drift** and of bar-level noise, not of current holes.

| Check | Use in this series |
|---|---|
| Exact OHLC 98.065%, close 99.039%, vol exact 96.109% on 78,205 bars; best shift 0 s / 0 ms; median close ratio 1.0 | Tolerance lock for any tick→15s **bar** compare. Session VA is not required to match 15s typical. |
| Σvol ticks/15s 0.997–1.000 | Do not expect bar-exact volume. |
| Holes A/B (fixable) and D/E (then open) | **Closed** by stitch patches 1–2. Do not re-open. |
| Hole C / X1 | Still the only unexpected residual. **Fill**, do not exclude. |

Current SoT: **46 segments, 39 include files**, coverage `2024-07-31 22:00:00.056` → `2026-08-06 20:59:45` UTC.

---

## 3. What ticks change (honesty — not “parity”)

Tick VA / APOC **will** differ from any previous typical-price or incomplete-`tick_paths` object. That difference is the research point. It must not be hidden inside a parity claim.

| Surface | Stays on 15s | Moves to stitch ticks | Why it differs |
|---|---|---|---|
| OHLC, derive 1m, touch/fade/3c, fills, costs, flatten, DA5 replicas | yes | no | Untouched paths |
| `ONH`/`ONL`/opens/OR/Asia/London, `dVWAP*`/`wVWAP`/`mVWAP`, pivots, TPO SP, `prev30mVWAP` | yes | no | TV/AP locks |
| `pd*` / `pw*` / `pm*` | — | Last×Volume over the stitch, clipped to 15s windows, 70% expander, bins 4/8/10 | Different allocation than 1m typical; residual ~0.03–0.27% session volume vs 15s |
| `APOC` / `pAPOC` | — | A-period Last×Volume from the same stitch | Already the product source; farm files replace the placeholder |
| 2025-11-07 session VA | — | Real ticks **plus** 15s residual fill in 17:58:14.581–19:00:00.009 | Degraded, flagged |
| 2025-11-10 `pd*` | — | Prior session = filled 11-07 | Mechanical `shift(1)` |
| `pw*` on the first session of the week after the W-SUN week that contains 2025-11-07 | — | That week’s histogram includes the fill | Mechanical week merge |
| `APOC` 2025-11-07 and `pAPOC` 2025-11-10 | — | Real A-period ticks only | Fill must not enter `select_a_period_rows` |
| `POC_rolling_*` | off on this run | **not computed from farm ticks** | See §5 TS6 |

Parity means: stitch key absent → Run 2 15s cells match `0ebc1494`. It does **not** mean tick VA equals 15s typical VA.

---

## 4. Stitch read, verify, and stream (RAM)

### 4.1 Plan schema (read-only contract)

`tick_stitch_plan.json` is an ordered array of segments. Required fields already present:

- `filename` (basename only)
- `size_bytes`
- `effective_first_utc` / `effective_last_utc` (inclusive trim)
- `file_first_utc` / `file_last_utc` (advisory; verify against seek)
- `mtime` (advisory; not used for ordering)

Same `filename` may appear more than once with disjoint trims. That is required (mega file, D/E fills). The existing `_reject_duplicate_files` / unique-`tick_paths` rules must **not** run on this path.

Root on disk is an operator directory of **local NVMe copies**, never `/mnt/nas-trading`.

### 4.2 Verify (offline, before any study)

A CLI / library `verify_tick_stitch_plan(plan, root)` must, for every segment:

1. File exists under `root / filename`.
2. `stat().st_size == size_bytes`.
3. Header is the Quantower tick-last semicolon header (BOM allowed).
4. First and last parseable `Time left` equal `file_first_utc` / `file_last_utc` (seek, no full parse).
5. Effective bounds lie inside the file range (or equal it).
6. Segments are strictly ordered: `seg[i].effective_last < seg[i+1].effective_first` (microsecond).
7. No two effective windows overlap.
8. Unique-file count is 39; segment count is 46; `sum(unique size_bytes) == 36,415,038,585`.

Fail closed on any mismatch. Do not “repair” the plan at runtime.

Identity for a verified tree: SHA-256 of (canonical plan JSON + per-file content hashes + X1 fill-policy token + clip policy token + session-cut policy `cme_eth_start_v1`). This is **not** `compute_tick_source_id` over a naive path list (that API hashes whole files and would collide with a different trim). New helper; old helper unchanged when stitch is off.

### 4.3 Stream per session (parent only)

New iterator, name locked as `iter_stitch_sessions(plan, root, *, instrument="MNQ")` → `TickChunk`.

Algorithm:

1. Group segments by `filename`. One sequential chunked read per unique file (`pd.read_csv` in row chunks, not `pd.read_csv(path)` of the whole mega file).
2. Keep a row iff its UTC timestamp is inside **any** of that file’s effective windows (half-open at the right edge if needed to match `effective_last + 1µs` handovers already in the plan).
3. Do not sort across files by `first_row_utc` independently of plan order; plan order **is** time order.
4. Assign `trading_session_date` (existing helper, `eth_start` in `exchange_tz`). Do not hardcode 22:00 UTC.
5. Yield a session when the next row (or EOF) is past that session’s end. Discard the raw tick frame after the caller reduces it.
6. Keep same-millisecond prints. Do not drop `Aggressor=None` when `volume > 0`.
7. Never hash the file on the yield path. Hashes belong to verify / identity.

Parent reductions (one pass):

- **VA:** `_session_histogram` already in `tick_vap.py` (Last×Volume → bin → drop ticks). Then existing `_family_rows` / `_compute_profile`.
- **APOC:** keep only rows that survive `select_a_period_rows`; run `compute_tick_last_volume_profile`; drop the rest. Do not feed X1 synthetics into this side (they are timestamped inside 17:58–19:00 UTC).
- **Hourly guard / clip:** see §6 and §4.4.

Workers receive two small parquets (`prior_profile_table_path`, new `apoc_tick_table_path`). They do not receive tick CSVs.

### 4.4 Clip to 15s windows

After trim, drop any tick whose timestamp is not inside a 15s bar interval that exists on the Run 2 15s frame (left-closed, right-open, `floor(ts, 15s)` equals a bar timestamp present in the CSV).

This removes:

- the seven 1-lot halt prints at 21:00:00.0xx / 22:00:00.0xx on quarterly-roll Tuesdays (quality report residual risk 5);
- ticks that sit in 15s weekend/holiday edge gaps (quality report: 15s often drops the last 15s bar before a break).

It does **not** impute 15s-missing bars. Expected 2025-11-28 02:24/02:44–13:30 stays empty.

### 4.5 RAM budget

| Process | May hold | Must not hold |
|---|---|---|
| Verify CLI | One file’s first/last seek buffers; running sha256 block (1 MiB) | All 34 GiB decoded |
| Study parent (stitch on) | One CSV chunk + current session histogram + A-period accumulator + the two output tables | All sessions’ raw ticks; a second copy of the mega file |
| Study worker (12×) | Existing 15s + levels + two scalar tables (≈ 3.7–4.5 GiB today) | Any farm tick CSV; `list(iter_tick_files)` |

Operational abort (farm, not a unit test): if `MemAvailable` would fall below **6 GiB** during the parent stream, stop. Do not raise worker count.

`iter_tick_files` remains the CI / Data-page path for small fixtures. The stitch iterator is a sibling, not a monkey-patch.

---

## 5. PR sequence

Smallest independently revertible steps. Each PR is reviewed by a separate review agent. No merge on red. Nothing deploys to the farm while a study is running.

Shared green suite (every PR after TS0; do not delete or xfail):

`tests/test_loader.py`, `tests/test_derive.py`, `tests/test_vendor_loaders.py`, `tests/test_15s_primary_persistence.py`, `tests/test_intrabar.py`, `tests/test_mw1_array_context.py`, `tests/test_memory_parity.py`, `tests/test_quantower_ticks.py`, `tests/test_tick_vap.py`, `tests/test_tick_vap_cutover.py`, `tests/test_tick_vap_session20.py`, `tests/test_tick_family_composer_parity.py`, `tests/test_apoc_tick_source.py`, `tests/test_rolling_poc_tick_source.py`, `tests/test_fade_golden.py`, `tests/test_golden_master.py`, `tests/study/test_program_b_yaml.py`.

Golden files under `tests/fixtures/golden/` are not regenerated.

---

### TS0 — this PR (plan only)

| | |
|---|---|
| **Scope** | Land this file. No runtime. |
| **Files** | `docs/TICK_VA_APOC_IMPLEMENTATION_PLAN.md` only |
| **Tests** | None (no code) |
| **Acceptance** | One markdown file. `git diff` against `0ebc1494` is that file alone. |

---

### TS1 — Stitch-plan schema + verify (no engine)

| | |
|---|---|
| **Scope** | Parse and verify a stitch plan against a directory of tick CSVs. Fail closed. No call from `load_ohlcv`, `iter_tick_files`, or study execute. |
| **Files** | `thesistester/data/tick_stitch.py` (new); `thesistester/cli.py` or `python -m thesistester.data.tick_stitch verify` entry; `tests/test_tick_stitch.py`; `tests/fixtures/tick_stitch/` (tiny synthetic CSVs + a 3-segment plan). Optional: commit the **farm plan JSON only** (no tick bytes) under `examples/studies/program_b_run2/tick_stitch_plan.json` — see open question Q1. |
| **Forbidden** | Edits to `quantower_ticks.py` behaviour, `loader.py`, `derive.py`, packets, `dataset.path`. |
| **Tests** | Synthetic: size mismatch fails; first/last mismatch fails; overlap fails; mis-order fails; same file / two disjoint windows passes; unique-file byte sum asserted on the fixture; filename window is ignored. |
| **Acceptance** | `iter_tick_files` tests still pass unchanged. Verify is a no-op unless invoked. |

---

### TS2 — Session streamer (opt-in, nobody calls it yet)

| | |
|---|---|
| **Scope** | `iter_stitch_sessions` as specified in §4.3. Reuse `TickChunk`. Do not replace `iter_tick_files`. |
| **Files** | `thesistester/data/tick_stitch.py`; `tests/test_tick_stitch_stream.py` |
| **Tests** | Trim exclusivity (row on the wrong side of `effective_last` is dropped); handover `last < next.first`; same-ms pair kept (two prints, both volumes); `Aggressor=None` + `volume>0` kept; mega-shaped fixture (one file, two disjoint windows) is read **once**; session_date uses `trading_session_date`, not UTC midnight; streamer does not call `_file_sha256` / `_peek_tick_file`. |
| **Acceptance** | Importing the module does not change study or Levels output. No execute wiring. |

---

### TS3 — 15s clip + hourly hole guard

| | |
|---|---|
| **Scope** | Clip (§4.4). Per-hour compare: if the 15s frame has at least one bar in hour `H` and the stitched+clipped ticks have none, or the last tick in `H` ends before the last 15s bar in `H` by ≥ 5 s **and** that bar has volume, **fail** unless the interval is on the allowlist. |
| **Allowlist (locked)** | (1) 2025-11-28 02:24:15–13:30:00 UTC (CME outage; 15s starts ~02:24, ticks ~02:44). (2) Thanksgiving / weekend / daily-halt gaps already empty in **both** sources. (3) X1 fill window — handled in TS4, not as a silent pass. (4) Inter-file weekends listed in stitch meta. |
| **Files** | `thesistester/data/tick_stitch.py` (or `tick_stitch_guard.py`); `tests/test_tick_stitch_guard.py` |
| **Tests** | Halt 1-lot print at 22:00:00.050 is clipped away. Synthetic cut-short hour (ticks end 14:51:52, 15s has bars to 15:00) **fails**. 11-28 allowlisted hole does **not** fail. Hour with ticks but no 15s (roll-Tuesday 21:00 print) does **not** fail after clip. |
| **Acceptance** | Still not wired into execute. Guard is a function tests call. |

The guard exists so a future Quantower chunk truncation cannot slip into a study the way holes A–E did.

---

### TS4 — X1 15s residual fill + impact test

See §6 for the fill design (normative). This PR implements it and the impact test. Still no study execute wiring.

| | |
|---|---|
| **Scope** | Residual 15s VAP fill for the X1 window only. Per-session quality flag. APOC path rejects synthetics. |
| **Files** | `thesistester/levels/tick_x1_fill.py` (new, small); hook from the stitch reducer; `tests/test_tick_x1_fill.py`; synthetic 15s+tick fixture shaped like 11-07 (shared empty 16:49–17:58, 10k-tick island, burst bars, 59 min empty). **Do not** commit farm ticks. |
| **Tests** | Fill timestamps lie only in `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)`. Residual volume = `max(0, 15s_vol − tick_vol)` per 15s bar; 10k-island bar does not double-count. Synthetics never appear in `select_a_period_rows` for 2025-11-07. Shared 16:49–17:58 gap is **not** filled. Flag `x1_15s_residual_fill` is true only for trade date 2025-11-07. **Impact test (required):** report `pd*` for 2025-11-07, `pd*` on 2025-11-10 (prior-day), and `pw*` for the W-SUN week that contains 2025-11-07, under three variants — ticks-only, fill-without-burst, fill-with-burst (product default). Assert the three triples are emitted and that APOC 2025-11-07 is identical across variants. Do **not** assert a preferred VA number; the report is the artifact. |
| **Acceptance** | Default product path is fill-with-burst + flag. Reverting this PR restores “no fill” without touching TS1–TS3. |

---

### TS5 — Parent tables + execute wiring + named parity test

First engine/study touch. Default remains bit-identical to `0ebc1494`.

| | |
|---|---|
| **Scope** | If `dataset.tick_stitch_plan` is absent: **zero** behaviour change. If present (later packets): parent runs verify → stream → clip → guard → X1 fill → write `PriorProfileTable` parquet (existing) **and** `APeriodTickProfileTable` parquet (new path). Inject both onto every cell. Workers call `compute_apoc_levels(..., apoc_tick_table=...)` and `compute_profile_levels(..., prior_profile_table=...)`. Workers must not call `iter_tick_files` / `iter_stitch_sessions` / `build_a_period_tick_profile_table(tick_paths=farm)`. |
| **Files** | `thesistester/study/execute.py` (parent prepare + inject); `thesistester/study/schema.py` / `launch.py` / `expand.py` / `api.py` (additive key `tick_stitch_plan`, optional `apoc_tick_table_path`); `thesistester/research_identity.py` (hash the new keys when present); `tests/test_ts_run2_parity.py` (**named parity test**, below); docs sentences that are newly true. |
| **Forbidden** | Changing `dataset.path`, `load_ohlcv`, `prepare_15s_source_for_derivation`, `derive_complete_parent_ohlcv`, MW flag semantics, `poc_windows` on the **15s** packet. |
| **Tests** | Named parity test §5.1. Unit: stitch absent → `apoc_tick_table_path` absent → APOC still builds from fixture `tick_paths` as today. Stitch present on a tiny fixture → worker-side `iter_tick_files` is not called (monkeypatch sentinel). Future-shock: append a later session’s ticks → prior `pd*` / `APOC` unchanged (`tests/test_r3_point_in_time.py` pattern). |
| **Acceptance** | `test_stitch_plan_absent_replays_run2_15s_smoke` green. Existing MW0 / fade / VA / APOC tests green. |

#### 5.1 Named parity test (lock)

**Name:** `tests/test_ts_run2_parity.py::test_stitch_plan_absent_replays_run2_15s_smoke`

**Cells replayed:**

1. `examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml` — the MW0 full reference cell (`progB_r2_smoke_ONH_SMA50_5min_c0000_anchor_rules_fade_1min_SMA_50_5min_otfOff_*`, 59 trades, E=0.0805 on the farm CSV).
2. First Wave-0 15s solo cell from `examples/studies/program_b_run2/progB_w0_solo.yaml` (ONH, `min_valid: 0`).

**Assert (stitch key omitted, code after TS5):** trade frames bit-identical (every column, including `exit_subbar_timestamp`, dtypes, units, timezone), `replica_expectancies` ordered-identical, DA5 fields non-null where the reference is non-null, `canonical_bundle_hash` identical. Wall-clock / ledger timestamps may differ. `NaN` equals `NaN`. No tolerance.

**CI vs farm:** the full real-CSV smoke is ~3–4 h and is **not** a default CI job. CI must (a) prove the execute/API call graph is unchanged when `tick_stitch_plan` is omitted (hook audit, same style as `test_memory_parity.py` hook points), and (b) when `THESISTESTER_MEMORY_PARITY_CSV` (or the existing MW0 env) is set, compare against `tests/fixtures/memory_parity/farm_reference/`. Farm gate before any tick study: run both cells flag-off / stitch-off against the `0ebc1494` reference.

A second test, `test_stitch_plan_absent_does_not_change_tick_source_id_none`, asserts identity keys stay `none` on 15s-only Run 2 specs.

---

### TS6 — Packet opt-in + docs (revertible packet PR)

| | |
|---|---|
| **Scope** | Generator / validator / Run 2 **tick** packet only. 15s packet (`manifest.yaml`, 20 / 898) stays byte-stable except if the generator rewrite would touch shared helpers — then split the helper so 15s YAML hashes do not change. |
| **Files** | `examples/studies/program_b/generate_program_b_yaml.py`; `validate_program_b_yaml.py`; regenerated `examples/studies/program_b_run2/manifest_tick.yaml` + 8 tick YAMLs; `tests/study/test_program_b_yaml.py`; `docs/PROGRAM_B_OPERATOR_RUNBOOK.md`; `docs/ASSUMPTIONS_AND_LIMITATIONS.md`; `docs/ARCHITECTURE.md`; `docs/ENGINEERING_ROADMAP.md`; `docs/README.md` (one index row). |
| **Packet locks** | `dataset.path` **unchanged** (same 15s CSV). New additive `dataset.tick_stitch_plan` pointing at the committed or farm-local plan JSON. Do **not** emit `data/mnq_tick_last.csv`. Do **not** require that placeholder to exist. `poc_windows: []` on the tick packet (ticks feed VA + APOC only; rolling POC on 34 GiB would `list()` all ticks per worker). `apoc_enabled: true` only on APOC studies, as today. `TICK_GATED_SET` unchanged. |
| **Launch** | `study/launch.py` resolves each unique stitch filename under the operator NVMe root. Missing file refuses. SMB path refuses. |
| **Tests** | `test_program_b_run2_tick_manifest_validates` updated to the new key. 15s `test_program_b_run2_manifest_expands_898_with_run2_locks` still asserts `"tick_paths" not in dataset` and no stitch key. Generate-matches-committed for **15s** files still holds. Wave-7 provenance still `tick_last_volume_v1`. |
| **Acceptance** | Reverting TS6 restores the placeholder packet. TS5 code remains default-off. No study is launched by this PR. |

Farm deploy steps in §8 are executed **after** TS1–TS6 merge, not inside a PR.

---

## 6. X1 fill design (normative)

**Supersedes** `tick_stitch_meta.json` `exclusions[0]` (`exclude_tick_full_session_VA` → NaN on 11-07 VA and 11-10 pVA).

### 6.1 Window

Fill **only** `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)` UTC.

Do **not** fill the shared empty gap ~16:49–17:58 UTC (both 15s and ticks are empty; that is a real feed hole, not a tick-only hole).

### 6.2 Residual allocation

For each 15s bar `b` whose timestamp (left edge) lies in the X1 window:

```
tick_vol[b] = Σ Volume of stitched ticks with floor(ts, 15s) == b.timestamp
residual    = max(0, b.volume − tick_vol[b])
```

If `residual == 0`, no synthetic. Else one synthetic Last×Volume print:

- `price = round((H+L+C)/3 / tick_size) * tick_size` (MNQ 0.25), same snap as `_bucket_prices`
- `volume = residual`
- `timestamp = b.timestamp + 7.5s` (interior to the bar; session_date is still 2025-11-07)

Volume is conserved to 15s residual within `VOLUME_CONSERVATION_ATOL` already used by AP1 (`1e-9`).

Why **typical**, not uniform-range: AP1 rejected `bar_range_uniform_volume_v1` as a production APOC source (2/4 vs tick 4/4). A replay bar can have a wide high–low; smearing ~280k contracts across that range would invent a fake profile. Typical is a single documented, already-implemented allocation. It is **degraded**. The quality flag exists so no one treats 11-07 `pd*` as a clean tick object.

Why **residual**, not full 15s volume: the island `2025-11-07 18:00:53.022`–`18:00:54.037` is 10,000 real ticks / 11,505 contracts (patch notes). Adding the 15s bar on top would double-count.

### 6.3 Burst (18:00:45–18:01:30 UTC)

15s that day is itself degraded: ~280k contracts print in 18:00:45–18:01:30, which the quality report flags as a replay dump. That interval sits **inside** the X1 window and **overlaps** the 10k-tick island.

**Product default: include the burst via the same residual rule.** The prompt requires the hole to be filled from 15s VAP; that volume is the only 15s evidence. Dropping it would silently omit on the order of 10%+ of session volume.

**Honesty:** those synthetics are tagged `x1_burst` in the session quality record. They land on a handful of typical prices, so they can move POC.

**Impact test (TS4)** must print all three variants so the desk can see the move:

| Variant | 11-07 `pdVAH/VAL/POC` | 11-10 `pd*` | `pw*` of the W-SUN week containing 11-07 | 11-07 `APOC` |
|---|---|---|---|---|
| ticks-only (no fill) | report | report | report | **identical** |
| fill, burst bars residual = 0 | report | report | report | **identical** |
| fill-with-burst (default) | report | report | report | **identical** |

`pm*` for 2025-11 also moves; not required by the prompt — see Q6.

### 6.4 APOC isolation

`select_a_period_rows` for 2025-11-07 is `[09:30, 10:00)` America/New_York = `[14:30, 15:00)` UTC (standard time). The fill window starts 17:58 UTC. Synthetics must not be concatenated into the APOC accumulator. `pAPOC` on 2025-11-10 may use the untouched 11-07 APOC.

### 6.5 Quality flag

Per trade date, persist (table column or sidecar, additive):

```text
data_quality.x1_15s_residual_fill = true   # 2025-11-07 only
data_quality.x1_burst_included    = true   # default product path
data_quality.shared_gap_1649_1758 = true   # not filled; both sources empty
```

Named-VA cells on 11-07 / 11-10 remain `ok` if the profile is finite. The flag is how the run is read, not a `failed` cell.

---

## 7. Parity, regression, tolerances

| Gate | Tolerance | Applies to |
|---|---|---|
| `test_stitch_plan_absent_replays_run2_15s_smoke` | **None.** Bit-identical vs `0ebc1494` / MW0 farm_reference. | Run 2 15s smoke + Wave-0 ONH solo |
| Existing golden / fade / MW / TV / AP / RP tests | Existing (no regen) | Default-off tree |
| Tick → 15s **bar** OHLC compare (optional diagnostic, not a merge gate) | exact OHLC ≥ 98%, close ≥ 99%; **not** bar-exact volume (sampled 96.1%) | Farm stitch QC only |
| Session Σvol ticks/15s | 0.997–1.001 after clip is informational | Not a VA equality claim |
| X1 impact test | Report-only; APOC identity across variants is exact | TS4 |
| Hourly guard | Fail on unexpected ≥ 5 s hole with 15s volume | TS3 |

`LEVEL_ENGINE_VERSION` stays 11. Stitch + fill change `tick_source_id` / a new `tick_stitch_source_id` when the option is on. Off → existing `none` / file-list hashes.

---

## 8. Farm deployment (after merge, not a PR)

Order is mandatory: **merge TS1–TS6 → stitch-off parity → small pilot → full tick packet.**

1. **Copy.** 39 unique CSVs from `/mnt/nas-trading/thesistester/chart_exports/tick_data/` to farm NVMe (suggested `~/thesistester/data/ticks/` — Q2). `cp`/`rsync` of **untouched** bytes. Do not concatenate. Workers and the parent streamer accept only that root.
2. **Checksums.** `sha256sum` each NVMe file; size must match the plan (`36,415,038,585` unique-file bytes). Store the digest sidecar next to the plan. Re-run `verify_tick_stitch_plan`.
3. **15s CSV** already local (`~/thesistester/data/`, 344,135,035 bytes). Do not re-point `dataset.path`.
4. **Parity (stitch off).** Replay the two cells in §5.1 on this tree vs the `0ebc1494` farm_reference. Any delta other than wall-clock → **stop**.
5. **Pilot.** One tick-gated cell only: `progB_r2_w0_va` / `pdPOC` solo (first VA cell). Confirm parent RSS, worker RSS ≤ 4.5 GiB, no SMB open (`lsof` / `nfsstat`), X1 flag present on 11-07, APOC table has a finite 11-07 POC. Not a full-packet result.
6. **Full run.** `manifest_tick.yaml` (8 studies / 253 cells), one study at a time, 12 workers, Notion/logging as Run 2. Soft-resume. Do not `--force`.

If verify or parity fails, do not start the pilot.

---

## 9. Non-goals (forbidden in this series)

- Building 15s/1m bars from ticks; a tick-vs-15s bar “comparison gate” as a production ingest switch (German notes PR 2). Diagnostic-only compares are allowed on the farm.
- Merging CSVs; writing `data/mnq_tick_last.csv`.
- Global same-ms dedupe.
- Filling expected holes or the 16:49–17:58 shared gap.
- Re-opening X1 as a NaN exclusion.
- Rolling-POC from farm ticks; enabling `poc_windows` on the tick packet.
- Roll detection without a contract column.
- Workers reading `/mnt/nas-trading`.
- Silent typical fallback for named VA / APOC.
- Golden regen; `LEVEL_ENGINE_VERSION` bump.
- Hand-editing generated Run 2 YAML.
- Launching a study from a TS PR.

---

## 10. Open questions

Listed instead of guessing. Implementation PRs must not invent answers.

1. **Q1 — Commit the farm `tick_stitch_plan.json`?** The 46-segment JSON has no tick bytes and would make TS1 verify reviewable. Alternative: farm-local only (`~/thesistester/_scratch/tick_stitch_plan.json`) and the packet points there. Prefer commit, but the desk owns the path.
2. **Q2 — NVMe destination?** German notes used `~/thesistester/data/ticks/`. Confirm before the copy. The code should take a root argument, not hardcode a home directory.
3. **Q3 — Pilot cell?** This plan recommends `progB_r2_w0_va` `pdPOC` solo. Confirm or name another single cell.
4. **Q4 — Parent RSS cap during the 34 GiB stream?** Operational abort at `MemAvailable < 6 GiB` is proposed. Confirm the number; it is not a unit-testable CI gate.
5. **Q5 — sha256 in the plan JSON?** The farm plan has sizes and first/last, not content hashes. TS1 can compute a sidecar at verify time. Should that sidecar be committed?
6. **Q6 — Impact-test `pm*`?** The fill also moves November 2025 `pm*` and December prior-month VA. The required triple is 11-07 VA / 11-10 `pd*` / that week’s `pw*`. Add `pm*` or not?
7. **Q7 — Re-run the quality report on the 46-segment plan before the pilot?** The attached report is pre-patch (40/37). Drift result should still hold; hole A/B/D/E should now be gone. Farm ops, not a code PR — confirm it is a hard gate.
8. **Q8 — Launch schema: stitch plan *instead of* `tick_paths`, or in addition?** Today named VA/APOC refuse without `tick_paths`. Cleanest: stitch plan counts as tick input and `tick_paths` is omitted on the tick packet. That is a validator/schema change in TS6. Confirm so TS5 can implement `dataset_has_tick_paths` accordingly.

---

## 11. Documentation map (later PRs)

| When | Doc | Sentence that becomes true |
|---|---|---|
| TS5 | `ARCHITECTURE.md` | Additive `dataset.tick_stitch_plan` / `apoc_tick_table_path`; workers do not hold farm ticks. |
| TS4–TS5 | `ASSUMPTIONS_AND_LIMITATIONS.md` | 11-07 VA is 15s-residual-filled and flagged; APOC that day is clean ticks; clip to 15s windows. |
| TS6 | `PROGRAM_B_OPERATOR_RUNBOOK.md` | Tick packet launch: NVMe root, verify, stitch-off parity, pilot, then 253 cells. |
| TS6 | `ENGINEERING_ROADMAP.md` + `docs/README.md` | TS series row. |

`METRICS_GLOSSARY.md` only if a new named statistic is emitted (the quality flag is provenance, not a KPI).

---

## 12. Per-PR §4.2 checklist (copy into each TS PR body)

- Unit tests for the new function, deterministic, no farm CSV.
- Golden-master / fade / MW0 artifacts untouched.
- Default-off: stitch key absent → `0ebc1494` behaviour.
- Docs in the same PR for any sentence that became true.
- CI green. Small surface. One logical commit unless the reviewer asks otherwise.
- Regression paragraph: which named test proves default-off identity, and that tick VA/APOC differences are **out** of that claim.
