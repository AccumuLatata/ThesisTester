# Tick stitch → VA / APOC — implementation plan (TS)

**Document type:** Implementation plan (fully scoped PRs). This file is the review copy of the plan. **This PR ships no runtime, no packet, no config, and no data.**
**Date:** 2026-10-06
**Status:** Plan lock. No study. No code in the plan PR.
**Series code:** **TS** (Tick Stitch for VA + APOC). Not TV (Tick VAP, landed). Not AP (A-period source, landed). Not RP (rolling POC). Not MW.
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist.
**Parity baseline:** `main` / farm production `0ebc149406f91ae71447561d9c42184b130ca0ac` (#610). Re-checked 2026-10-06: `origin/main` is still this commit. If `main` moves before TS5 lands, keep **behaviour** parity against `0ebc1494` (same outputs except wall-clock timestamps) and name the new SHA in the TS5 PR. Code facts in §2.1 were re-read on that tree; where an earlier draft named the wrong symbol, call chain, bin default, or env var, this text is the lock.

**Inputs (attached to the planning chat; farm copies under `~/thesistester/_scratch/`):**

| Artifact | Role |
|---|---|
| `tick_stitch_plan.json` | Ordered, non-overlapping segment array (46 segments) |
| `tick_stitch_meta.json` / `tick_stitch_list.md` / `.json` | Coverage, holes, exclusions, include list (39 files, 36,415,038,585 bytes ≈ 33.9 GiB) |
| `tick_stitch_patch_notes.md` | Patches A/B (2026-10-06) and D/E + X1 (same day) |
| `tick_quality_report.md` / `.json` | Pre-patch drift/coverage sample (40 segments / 37 files). **Hole list is stale.** Drift result is not. |
| `Plan_Tick_Lauf_Program_B.md` | Earlier German design notes. **Background only.** This file wins on any conflict. |

**Does not reopen:** TV1–TV4 object (Last×Volume, 70% expander, `shift(1)` prior map, bins 4/8/10, fail-closed without ticks). AP2/AP3 A-period definition (`[RTH_open, RTH_open+30min)` in `exchange_tz`, `tick_last_volume_v1`). RP2 sliding POC. MW worker-memory flag. 15s ingest / 1m derive. `simulate_trades`. Golden regeneration. Roll synthesis. Building 15s bars from ticks.

**Amends (in the PR that makes the sentence true):** `ASSUMPTIONS_AND_LIMITATIONS.md`, `POINT_IN_TIME_GUARANTEES.md`, `ARCHITECTURE.md`, `PROGRAM_B_OPERATOR_RUNBOOK.md`, `ENGINEERING_ROADMAP.md`. `docs/README.md` gets its index link in **this** PR: `tests/test_docs_index_shelves.py::test_top_level_docs_are_indexed` fails on an unlinked `docs/*.md`. TS6 updates that bullet’s status; it does not add the first link.

---

## 1. Purpose

Program B Run 2 (15-second fade, 898 cells) is finished. The next run computes **Value Area (VA) and APOC from ticks** for the same window as that 15s run. Everything else stays on the existing 15s bars.

Ticks are an ingest input for nine prior-profile tokens (`pdVAH` `pdVAL` `pdPOC` `pw*` `pm*`) and for `APOC` / `pAPOC`. They are **not** a second bar clock.

Series complete when:

1. A stitch plan (ordered trim windows over untouched Rithmic Tick–Tick–Last CSVs) can be verified and streamed per CME session without loading all ticks into a worker.
2. X1 `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)` UTC is filled from 15s residual volume-at-price, flagged, and impact-tested. APOC that day is untouched. The right edge is exclusive (§6.1).
3. An hourly hole guard refuses a cut-short export.
4. With the tick option **off**, Run 2 15s cells reproduce `0ebc1494` bit-identically (wall-clock timestamps excepted).
5. Farm copy is NVMe-only; workers never read `/mnt/nas-trading`. Two one-cell pilots in order: pdPOC, then APOC, before the 253-cell tick packet.

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
| Expected holes | No action and no fill: 2025-11-28 CME outage. 15s coverage ends ~02:24:15 UTC, tick coverage ends ~02:44 UTC, both empty through 13:30:00 UTC. Thanksgiving weekends the same. |
| X1 | **Fill** only `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)` UTC from 15s residual VAP. Per-day quality flag. **Keep APOC** (A-period is `[14:30, 15:00)` UTC, outside the hole). `tick_stitch_meta.json` policy `exclude_tick_full_session_VA` is **superseded**. |
| Default | Stitch / fill / new dataset keys **off**. `dataset.path`, `load_ohlcv`, 15s ingest, and 1m derive are not edited. |
| Workers | Farm launch passes `--workers 12`. Committed Run 2 YAML stays `workers: 1`; do not edit that field (it would rewrite the 15s packet). Documented VmHWM: MW0 full-run flag-on **3.73 GiB**; production 12-worker **3.85–4.46 GiB** (`docs/WORKER_MEMORY_IMPLEMENTATION_PLAN.md`). No worker may open or content-hash farm tick CSVs, or `list()` sessions. |
| Rolls | `thesistester/data/rolls.py` stays idle. No contract column → no roll logic. |
| Goldens | No regeneration. `LEVEL_ENGINE_VERSION` stays 11. Identity moves via additive keys. |
| Packets | Hand-edits of generated YAML are not durable. Change `generate_program_b_yaml.py` + validator together. |
| Revert | Each PR independently revertible. `main` stays green. |

### 2.1 Verified code facts (re-checked on `0ebc1494`)

| Fact | Where |
|---|---|
| Before the first yield, `iter_tick_files` calls `_peek_tick_file` on **every** path. That reads the entire timestamp column, then SHA-256s the whole file (`_file_sha256`, 1 MiB blocks). It then parses each file in full. Same-session rows from every contributing file are concatenated (`_build_chunk`). No trim windows. No same-ms dedupe. `_resolve_paths` rejects a repeated path; `_reject_duplicate_files` rejects byte-identical content. | `thesistester/data/quantower_ticks.py` |
| Filename window regex is `M_D_YYYY` AM/PM only. Dot names (`1.2.25`, `26.9.24`) return `None`. | `parse_quantower_tick_filename_window` |
| Prior-profile VA is one parent pass → parquet, then injected as `prior_profile_table_path`. The function is `_prepare_study_prior_profile`. | `study/execute.py` → `build_prior_profile_table_from_paths` |
| Library defaults on `build_prior_profile_table` / `build_prior_profile_table_from_paths` / `compute_all_levels` are aggregation **1/1/1**. Product and Program B lock are **4/8/10**. Bin width is `tick_size × aggregation` (MNQ 1.00 / 2.00 / 2.50 points) and is applied when the table is **built**. `compute_profile_levels` does not re-bin on join. `_prepare_study_prior_profile` merges `DEFAULT_LEVELS_SETTINGS` (4/8/10) when study levels omit those keys. The footgun is calling `build_prior_profile_table_from_paths` or `compute_all_levels` without aggregation kwargs: those signatures default to 1/1/1. | `tick_vap.py` defaults; `defaults.py`; `generate_program_b_yaml.py` `LOCKED_AGGREGATION`; `profile.py` docstring |
| APOC rebuilds from `tick_paths` via `list(iter_tick_files(...))` when `apoc_tick_table` is omitted. `compute_levels` always does that rebuild when APOC is enabled. It has **no** `apoc_tick_table` parameter. | `apoc_tick.py:240`, `apoc.py:232`, `api.py` `compute_levels` |
| `run_experiment` still resolves `tick_paths` and passes them into `compute_levels` when `prior_profile_table_path` is already set. The comment there is explicit: a prior-VA parquet is not APOC input. | `api.py` experiment levels block |
| `attach_apoc_identity` / `attach_rolling_poc_identity` / `_tick_source_id_from_dataset` content-hash `tick_paths` unless a precomputed id is passed. That hash is `compute_tick_source_id` (sorted whole-file digests + profile + `cme_eth_start_v1`), not a hash of the path strings. Same bytes with a different trim **collide**. | `apoc_tick.py`, `rolling_poc_tick.py`, `research_identity.py`, `tick_vap.py` |
| `dataset_has_tick_paths` is true only for a non-blank `tick_paths` list. `prior_profile_table_path` does not satisfy APOC or rolling POC. `product_tick_family_preflight` refuses APOC-on / rolling-on before any table is considered. StudySpec validation (`study/schema.py`) requires `tick_paths` for named VA **and** named APOC, and it runs before the parent injects parquet paths. `api.py` named-VA accepts `prior_profile_table_path` via `dataset_has_tick_inputs`; `api.py` named-APOC does not. | `tick_requirements.py`, `study/schema.py`, `api.py` |
| Rolling POC `list(iter_tick_files(...))` then concatenates every tick. `poc_windows is None` is **not** off: `compute_profile_levels` substitutes `("30min", "1h", "4h")` and then requires ticks. Explicit `poc_windows: []` is off. `normalize_levels_config` keeps an explicit `[]`; omitting the key merges the product default `["30min"]`. | `rolling_poc_tick.py:180`, `profile.py`, `research_identity.py` |
| Program B tick packet sets `poc_windows: ["30min"]` even though rolling POC is not a Program B core. 15s packet sets `poc_windows: []`. Validator **requires** `['30min']` on the tick packet today. | `generate_program_b_yaml.py` `_levels`; `validate_program_b_yaml.py` |
| Tick placeholder is `data/mnq_tick_last.csv`. Launch refuses missing files. Validator requires exact `TICK_PATHS`. | `generate_program_b_yaml.py:109`, `validate_program_b_yaml.py:162` |
| Product VA bins are 4 / 8 / 10. Value area 70%. MNQ `tick_size` 0.25, `eth_start` 18:00, `rth_start` 09:30, `exchange_tz` America/New_York. | `levels/defaults.py`, `config.py` |
| A-period is `[RTH_open, RTH_open+30min)` in exchange time. 2025-11-07 is US standard time → `[14:30, 15:00)` UTC. | `apoc_candidates.select_a_period_rows` |
| There is no `THESISTESTER_MEMORY_PARITY_CSV`. Parity capture is `capture_operator.py` (`--csv`, `--output-dir`, `--cells`, `--run-label`) then `compare_captures`. `stage_trace.py` is the VmHWM trace, not that gate. `farm_reference/full` is the smoke cell only. Linux captures must not be compared to a macOS run. | `capture_operator.py`, `compare.py`, `cells.py` `FULL_CELL`; `ENGINEERING_PROPOSAL.md` §4.1 |
| `study run` has no `--cell` filter. `progB_w0_va.yaml` expands nine cores, first `pdPOC`. | `study/cli_study.py`; `progB_w0_va.yaml` |

The current loader cannot express the stitch (same file, five disjoint windows on `1e2d3445…`, 6,684,663,701 bytes) and cannot run on 34 GiB inside a 4.5 GiB worker.

### 2.2 Quality-report vs current stitch

`tick_quality_report.md` was generated **2026-10-05 19:42** on the **pre-patch** plan (40 segments, 37 includes). It is evidence of **no timezone or price-scale drift** and of bar-level noise, not of current holes.

| Check | Use in this series |
|---|---|
| Exact OHLC 98.065%, close 99.039%, vol exact 96.109% on 78,205 bars; best shift 0 s / 0 ms; median close ratio 1.0 | Tolerance lock for any tick→15s **bar** compare. Session VA is not required to match 15s typical. |
| Σvol ticks/15s 0.997–1.000 (source 0.997312–1.000276) | Do not expect bar-exact volume. |
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
3. Same header contract as the loader: semicolon, BOM allowed (`utf-8-sig`). After alias, `_require_tick_columns` checks `("timestamp", "price", "volume")` (`_REQUIRED_TICK_COLUMNS`). Do not invent a second header grammar.
4. First and last parseable `Time left` equal `file_first_utc` / `file_last_utc` (seek, no full parse, and **not** `_peek_tick_file` — that reads every timestamp and hashes the file before returning).
5. Effective bounds lie inside the file range (or equal it).
6. Segments are strictly ordered: `seg[i].effective_last < seg[i+1].effective_first` (microsecond).
7. No two effective windows overlap.

Fail closed on any mismatch. Do not “repair” the plan at runtime.

Farm census is a **separate** expected-lock, not a property of every plan. When the caller passes it (farm plan only): unique-file count 39, segment count 46, `sum(unique size_bytes) == 36415038585`. TS1 synthetic plans (including one file with two disjoint windows) must verify **without** that lock. Hardcoding 39/46 inside `verify_tick_stitch_plan` would make the fixture suite fail.

Identity for a verified tree: SHA-256 of (canonical plan JSON + per-file content hashes + X1 fill-policy token + `dataset.tick_stitch_x1_burst_included` + clip policy token + session-cut policy `cme_eth_start_v1`). This is **not** `compute_tick_source_id` over a naive path list (that API hashes whole files and would collide with a different trim). Stitch-on identity is `tick_stitch_source_id` only. `compute_tick_source_id` is unchanged when the stitch is off.

### 4.3 Stream per session (parent only)

New iterator, name locked as `iter_stitch_sessions(plan, root, *, instrument="MNQ")` → `TickChunk`.

Trim lock (inclusive, matches the schema above): keep a row iff `effective_first <= timestamp <= effective_last`. At microsecond resolution that is the same set as `[effective_first, effective_last + 1µs)`. Do **not** use `[effective_first, effective_last)`. A timestamp equal to `effective_last` belongs to that segment; the next segment starts at a strictly later `effective_first`, so the two windows cannot both claim it.

Algorithm:

1. Walk segments in **plan order**. Plan order is time order. Do not sort files by `first_row_utc`.
2. Read with `pd.read_csv` row chunks, never `pd.read_csv(path)` of a whole farm file.
3. One sequential read may cover a run of **consecutive** segments that share a filename. A later disjoint window of that same file is a later read (seek or re-scan). Do not group every window of a filename and emit them before intervening segments: the mega file’s five windows are disjoint, and D/E fill files sit in the gaps. Emitting all mega-file windows first would apply later-session ticks before the fill and break session yield.
4. Assign `trading_session_date` (existing helper, `eth_start` in `exchange_tz`). Do not hardcode 22:00 UTC. Session end is the same helper the current loader uses (`_session_end_utc`: `eth_start` on the session date in `exchange_tz`), not UTC midnight.
5. Yield a session when the next kept row (or EOF) is past that session’s end. Discard the raw tick frame after the caller reduces it.
6. Keep same-millisecond prints. Do not drop `Aggressor=None` when `volume > 0`. Rows with `volume <= 0` stay dropped, as `_parse_tick_file` / `_session_histogram` already do.
7. Never call `_file_sha256`, `_peek_tick_file`, `compute_tick_source_id`, `attach_apoc_identity`, or `attach_rolling_poc_identity` on the yield path. Hashes belong to verify / the parent identity stamp.

Parent reductions (one pass, this order):

- **Clip** (§4.4), then **X1 fill** (§6), then **hourly guard** (§5 TS3). The guard sees post-fill ticks. Running it before the fill fails the X1 hour (15s bars exist, ticks do not) and aborts the study the fill was meant to repair. X1 is not an allowlist bypass.
- **VA:** `_session_histogram` (Last×Volume → 1-tick bin → drop ticks) then `_family_rows` / `_compute_profile`, with the **study** aggregation: day/week/month **4/8/10**, `value_area_pct` 0.70. Do not call `build_prior_profile_table_from_paths` on its 1/1/1 defaults.
- **APOC:** keep only rows that survive `select_a_period_rows`; run `compute_tick_last_volume_profile`; drop the rest. Do not feed X1 synthetics into this side (they are timestamped inside `[17:58:14.581, 19:00:00.009)` UTC, outside `[14:30, 15:00)` UTC).

Workers receive two small parquets (`prior_profile_table_path`, new `apoc_tick_table_path`). They do not receive tick CSVs.

### 4.4 Clip to 15s windows

After trim, drop any tick whose timestamp is not inside a 15s bar interval that exists on the Run 2 15s frame (left-closed, right-open, `floor(ts, 15s)` equals a bar timestamp present in the CSV).

This removes:

- the seven 1-lot halt prints at 21:00:00.0xx / 22:00:00.0xx on quarterly-roll Tuesdays (quality report residual risk 5);
- ticks that sit in 15s weekend/holiday edge gaps (quality report: 15s often drops the last 15s bar before a break).

It does **not** impute 15s-missing bars. The 2025-11-28 outage (15s ends ~02:24:15 UTC, ticks end ~02:44 UTC, both empty through 13:30:00 UTC) stays empty. Segments 0–1 (2024-06-02 → 07-30, 1,940,338,542 bytes) predate the 15s window and are dropped by clip, but are still copied for the 39/46 census.

### 4.5 RAM budget

| Process | May hold | Must not hold |
|---|---|---|
| Verify CLI | One file’s first/last seek buffers; running sha256 block (1 MiB) | All 34 GiB decoded |
| Study parent (stitch on) | One CSV chunk + current session histogram + A-period accumulator + the two output tables + the 15s bar index (timestamps + volume; OHLC only for the X1 window) | All sessions’ raw ticks; a second copy of the mega file; every window of one file buffered across an intervening segment |
| Study worker (12×) | Existing 15s + levels + two scalar tables (documented VmHWM 3.73 GiB full-run; 3.85–4.46 GiB at 12 workers) | Any farm tick CSV; `list(iter_tick_files)`; `compute_tick_source_id` / APOC / rolling identity hashes of farm paths |

The 15s bar index is loaded once on the parent via `load_ohlcv` on the Run 2 CSV (344,135,035 bytes; `COLUMN_ALIASES` maps `time left` → timestamp): timestamps + volume for every bar, OHLC only for bars inside the X1 window. That read is the index cost; it is not a second 34 GiB tick scan. Cache the two parent parquets keyed by stitch identity + 4/8/10 bins + `dataset.tick_stitch_x1_burst_included` so the 8 studies + 2 pilots do not re-verify or re-stream 34 GiB each time.

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
| **Files** | `docs/TICK_VA_APOC_IMPLEMENTATION_PLAN.md` and one index bullet in `docs/README.md` |
| **Tests** | `tests/test_docs_index_shelves.py::test_top_level_docs_are_indexed` |
| **Acceptance** | No runtime. `git diff` against `0ebc1494` is those two files. The index bullet is the shelf link required by the orphan test, not a behaviour claim. |

---

### TS1 — Stitch-plan schema + verify (no engine)

| | |
|---|---|
| **Scope** | Parse and verify a stitch plan against a directory of tick CSVs. Fail closed. No call from `load_ohlcv`, `iter_tick_files`, or study execute. |
| **Files** | `thesistester/data/tick_stitch.py` (new); `thesistester/cli.py` or `python -m thesistester.data.tick_stitch verify` entry; `tests/test_tick_stitch.py`; `tests/fixtures/tick_stitch/` (tiny synthetic CSVs + a 3-segment plan). Optional: commit the **farm plan JSON only** (no tick bytes) under `examples/studies/program_b_run2/tick_stitch_plan.json` — see open question Q1. |
| **Forbidden** | Edits to `quantower_ticks.py` behaviour, `loader.py`, `derive.py`, packets, `dataset.path`. |
| **Tests** | Synthetic: size mismatch fails; first/last mismatch fails; overlap fails; mis-order fails; same file / two disjoint windows passes **without** the farm census lock; unique-file byte sum asserted on the fixture; filename window is ignored. Farm census (39 / 46 / 36,415,038,585) is asserted only when that expected-lock is passed. Verify does not call `_peek_tick_file`. |
| **Acceptance** | `iter_tick_files` tests still pass unchanged. Verify is a no-op unless invoked. |

---

### TS2 — Session streamer (opt-in, nobody calls it yet)

| | |
|---|---|
| **Scope** | `iter_stitch_sessions` as specified in §4.3. Reuse `TickChunk`. Do not replace `iter_tick_files`. |
| **Files** | `thesistester/data/tick_stitch.py`; `tests/test_tick_stitch_stream.py` |
| **Tests** | Inclusive trim: timestamp `== effective_last` is kept; timestamp `== effective_last + 1µs` is dropped; handover `effective_last < next.effective_first` so the boundary row is in exactly one segment. Same-ms pair kept (two prints, both volumes); `Aggressor=None` + `volume>0` kept; `volume<=0` dropped. Consecutive same-file windows are one read. A fixture with **another file’s segment between two windows of the mega file** yields in plan order (the later mega window is not emitted before the fill). Session date uses `trading_session_date`, not UTC midnight. Streamer does not call `_file_sha256` / `_peek_tick_file` / `compute_tick_source_id`. |
| **Acceptance** | Importing the module does not change study or Levels output. No execute wiring. |

---

### TS3 — 15s clip + hourly hole guard

| | |
|---|---|
| **Scope** | Clip (§4.4). Per-hour compare: if the 15s frame has at least one bar in hour `H` and the stitched+clipped ticks have none, or the last tick in `H` ends before the last 15s bar in `H` by ≥ 5 s **and** that bar has volume, **fail** unless the interval is on the allowlist. Also fail a head-of-hour hole (first tick ≥ 5 s after the first 15s bar with volume in that hour) and a mid-hour gap (any tick gap ≥ 5 s spanning 15s bars with volume). Allowlist unchanged. X1 is still not a bypass. |
| **Allowlist (locked)** | (1) 2025-11-28 CME outage, empty through 13:30:00 UTC. 15s coverage ends ~02:24:15 and tick coverage ends ~02:44; both sources are missing across that span (also empty in the 15s frame). Do not fill it (§4.4). (2) Thanksgiving / weekend / daily-halt gaps already empty in **both** sources. (3) X1 is **not** an allowlist bypass. TS3’s direct guard call on an unfilled X1 hour **fails**. After the TS4 fill, that hour must **pass**. (4) Inter-file weekends listed in stitch meta. |
| **Files** | `thesistester/data/tick_stitch.py` (or `tick_stitch_guard.py`); `tests/test_tick_stitch_guard.py` |
| **Tests** | Halt 1-lot print at 22:00:00.050 is clipped away. Synthetic cut-short hour (ticks end 14:51:52, 15s has bars to 15:00) **fails**. Head-of-hour (first tick ≥ 5 s after the first 15s bar with volume) **fails**. Mid-hour tick gap ≥ 5 s spanning 15s bars with volume **fails**. 11-28 allowlisted hole does **not** fail. Hour with ticks but no 15s (roll-Tuesday 21:00 print) does **not** fail after clip. |
| **Acceptance** | Still not wired into execute. Guard is a function tests call. |

The guard exists so a future Quantower chunk truncation cannot slip into a study the way holes A–E did.

---

### TS4 — X1 15s residual fill + impact test

See §6 for the fill design (normative). This PR implements it and the impact test. Still no study execute wiring.

| | |
|---|---|
| **Scope** | Residual 15s VAP fill for the X1 window only. Per-session quality flag. APOC path rejects synthetics. |
| **Files** | `thesistester/levels/tick_x1_fill.py` (new, small); hook from the stitch reducer; `tests/test_tick_x1_fill.py`; synthetic 15s+tick fixture shaped like 11-07 (shared empty 16:49–17:58, 10k-tick island, burst bars, 59 min empty). **Do not** commit farm ticks. |
| **Tests** | Fill timestamps lie only in `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)`. Residual volume = `max(0, 15s_vol − tick_vol)` per 15s bar; 10k-island bar does not double-count. Synthetics never appear in `select_a_period_rows` for 2025-11-07. Shared 16:49–17:58 gap is **not** filled. Flag `x1_15s_residual_fill` is true only for trade date 2025-11-07. Hourly guard passes the X1 hour after the fill. **CI impact test** (`tests/test_tick_x1_fill.py`, synthetic fixture): three variants — ticks-only, fill-without-burst, fill-with-burst — none of which is a product default. Assert the three triples are emitted and that APOC 2025-11-07 is identical across variants. Do **not** assert a preferred VA number. **Parent-only farm impact command** (NVMe stitch, not a worker, not CI): emits the real 2025-11-07 `VAH`/`VAL`/`POC` for those three variants plus downstream 2025-11-10 `pd*` and the W-SUN week `pw*` deltas. Accumu picks the `dataset.tick_stitch_x1_burst_included` value from that farm report before the tick packet is frozen. The fill takes that bool explicitly (no silent default). |
| **Acceptance** | No silent burst default. The fill takes `dataset.tick_stitch_x1_burst_included` as an explicit argument. Accumu sets it from the farm impact report before the tick packet is frozen (§8, Q9). The missing-key reject is not this PR: TS5 `study/schema.py` and TS6 `validate_program_b_yaml.py`. TS4 hooks into the TS5 reducer: revert TS5 first (stops the call), then TS4 (deletes the fill module). Reverting TS4 while TS5 still calls it is not a clean revert. |

---

### TS5 — Parent tables + execute wiring + named parity test

First engine/study touch. Default remains bit-identical to `0ebc1494`.

| | |
|---|---|
| **Scope** | If `dataset.tick_stitch_plan` is absent: **zero** behaviour change. If present: `dataset.tick_stitch_x1_burst_included` (bool) is required and `study/schema.py` rejects a missing value. Parent runs verify → stream → clip → X1 fill → hourly guard → write `PriorProfileTable` parquet (existing, aggregation **4/8/10** from the study levels) **and** `APeriodTickProfileTable` parquet (new path), cached by stitch identity + 4/8/10 bins + `dataset.tick_stitch_x1_burst_included` (§4.5). Inject both paths **and precomputed source ids** onto every cell. The worker call chain is `execute_study_cell` → `run_experiment` → `compute_levels` → `compute_all_levels`. It is not a direct `compute_apoc_levels` call. `compute_levels` must grow an `apoc_tick_table` / path argument and, when that table is present, must not call `build_a_period_tick_profile_table`. `product_tick_family_preflight`, `study/schema.py::_require_ticks_for_named_va`, `api.py::_require_ticks_for_named_va`, and `_require_ticks_for_named_apoc_and_rolling` (both `study/schema.py` and `api.py`) must treat `tick_stitch_plan` with no `tick_paths`, and the injected APOC table, as tick input. Today schema `_require_ticks_for_named_va` and both APOC/rolling gates use `dataset_has_tick_paths` only; api `_require_ticks_for_named_va` uses `dataset_has_tick_inputs`. A leftover `tick_paths` list is opened and content-hashed inside every worker (`api.py` `compute_levels` and the experiment levels block). Expanded stitch cells must not carry farm CSV paths. Identity stamps are the parent’s precomputed ids, not a worker-side `compute_tick_source_id`. |
| **Files** | `thesistester/study/execute.py` (parent prepare + inject, beside `_prepare_study_prior_profile`); `thesistester/api.py` (`compute_levels` + `run_experiment` table/id threading); `thesistester/levels/tick_requirements.py` (stitch plan or injected APOC table counts as tick input); `thesistester/study/schema.py` / `launch.py` / `expand.py` (additive keys `tick_stitch_plan` and `dataset.tick_stitch_x1_burst_included` — bool, required when `tick_stitch_plan` is set, `schema.py` rejects missing — plus `apoc_tick_table_path` and `apoc_tick_source_id`); `api.py` `_DATASET_KEYS` (closed allowlist; `expand.py` calls `validate_run_spec` on every expanded run) must add `tick_stitch_plan`, `tick_stitch_x1_burst_included`, `apoc_tick_table_path`, and `apoc_tick_source_id`; `compute_levels` gains an `apoc_tick_source_id` kwarg forwarded to `attach_apoc_identity` (today that call does not pass it; empty or omitted `tick_paths` make `compute_apoc_tick_source_id` return `none` without hashing files, so the precomputed id is what keeps stitch-on APOC identity off that `none` token and off a farm-path hash); `thesistester/research_identity.py` (hash the new keys when present; do not content-hash farm paths on the worker); `tests/test_ts_run2_parity.py` (**named parity test**, below); docs sentences that are newly true. |
| **Forbidden** | Changing `dataset.path`, `load_ohlcv`, `prepare_15s_source_for_derivation`, `derive_complete_parent_ohlcv`, MW flag semantics, `poc_windows` on the **15s** packet. |
| **Tests** | CI merge gate is §5.1 (a)(b)(c), not the `HOOK_POINTS` symbol check. pdPOC and APOC specs with `tick_stitch_plan` and no `tick_paths` validate. `validate_run_spec` accepts the new `_DATASET_KEYS` and still rejects an unknown dataset key. `compute_levels(..., apoc_tick_source_id=...)` forwards that id to `attach_apoc_identity` and does not call `compute_apoc_tick_source_id` when `tick_paths` is omitted. Unit: stitch absent → `apoc_tick_table_path` absent → APOC still builds from fixture `tick_paths` as today. Stitch present on a tiny fixture → worker-side `iter_tick_files`, `build_a_period_tick_profile_table`, and `compute_tick_source_id` are not called (monkeypatch sentinels). Parent table uses 4/8/10, not the 1/1/1 library defaults. Explicit `poc_windows: []` does not enter `compute_rolling_poc_tick_levels`; omitting the key must not be the “off” switch under test (product default is `["30min"]`). Future-shock: append a later session’s ticks → prior `pd*` / `APOC` unchanged (`tests/test_r3_point_in_time.py` pattern). |
| **Acceptance** | §5.1 (a)(b)(c) green (TS5 merge gate). `schema.py` rejects a stitch plan with no `dataset.tick_stitch_x1_burst_included`. Farm `capture_operator` + `compare_captures` is the §8 gate, not this merge gate. Existing MW0 / fade / VA / APOC tests green. |

#### 5.1 Named parity test (lock)

**CI merge gate** (`tests/test_ts_run2_parity.py`). `HOOK_POINTS` in `tests/fixtures/memory_parity/compat.py` only checks that those symbols exist. It is not this gate. All three of the following are required:

(a) `test_stitch_absent_call_sentinels`. Stitch key omitted: `verify_tick_stitch_plan`, `iter_stitch_sessions`, the X1 fill, the hourly guard, and the new parent prepare are not called. The `compute_levels` keywords actually passed equal the `0ebc1494` set (`instrument`, `config`, `cache_policy`, `data_identity`, `store_root`, `tick_paths`, `tick_format_profile`, `prior_profile_table`, `prior_profile_table_path`, `tick_source_id`); `apoc_tick_table` and `apoc_tick_source_id` stay at default and are not supplied. No new always-on keys in `attach_apoc_identity`, `attach_rolling_poc_identity`, `attach_tick_identity`, or the dict hashed by `compute_levels_settings_hash`.

(b) `test_stitch_absent_tick_paths_va_apoc_match_0ebc1494`. With `tick_paths` and the stitch absent, VA (prior profile) and APOC outputs and their identity/hash values are byte-identical to values pinned from `0ebc1494`.

(c) `test_stitch_absent_index_has_no_data_quality_keys`. No `data_quality.*` keys on stitch-absent cell index rows.

**Leak points** (every row is caught by at least one gate):

| Hook | What misses it | Gate |
|---|---|---|
| `verify_tick_stitch_plan` / `iter_stitch_sessions` / X1 fill / hourly guard / new parent prepare called while the stitch key is absent | `HOOK_POINTS` only checks the symbol exists | (a) |
| `compute_levels` kwargs or defaults differ from the `0ebc1494` set | `HOOK_POINTS` does not compare signatures | (a) |
| New always-on keys in `attach_*_identity` or `compute_levels_settings_hash` | Trade frames can stay put while the settings hash moves | (a) and (b) |
| Farm `compare_captures` on the ONH smoke cell and the Wave-0 ONH solo (`apoc_enabled: false`; no named VA) | Those cells never build a prior profile or APOC | (b) |
| `data_quality.*` on the cell index | `compare_captures` compares trades, replica bits, `SUMMARY_METRIC_KEYS`, `DA5_KEYS`, ledger status/error/bundle_path, and `canonical_bundle_hash` | (c) |

**Farm gate (§8):** `capture_operator` + `compare_captures`, zero tolerance. Parity runs use production `THESISTESTER_MEMORY_PATH=array` (farm measurement env in `docs/WORKER_MEMORY_IMPLEMENTATION_PLAN.md` §17; the library default stays unset unless the value is exactly `array`).

**Cells replayed on the farm:**

1. `examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml` — the MW0 full reference cell (`progB_r2_smoke_ONH_SMA50_5min_c0000_anchor_rules_fade_1min_SMA_50_5min_otfOff_*`, 59 trades, E=0.0805 on the farm CSV).
2. Wave-0 ONH solo from a one-anchor spec copy of `examples/studies/program_b_run2/progB_w0_solo.yaml` (ONH, `min_valid: 0`). `study run` has no `--cell`. Do not launch the 39-anchor file.

Both cells set `apoc_enabled: false` and do not name a VA core, so this farm compare does not exercise prior-profile VA or APOC. `compare_captures` does not compare `data_quality.*` keys. Those two gaps are CI gates (b) and (c).

**Assert (farm only):** MW0 `compare_captures` in full mode. Do not write a second equality helper. That compare is bit-identical trades (every column, including `exit_subbar_timestamp`, dtypes, units, timezone), ordered replica bits, DA5 non-null where the reference is non-null, and the portable bundle hash stored on the capture as `canonical_bundle_hash`. Ledger wall-clock timestamps are stored and not compared. `NaN` equals `NaN`. No tolerance.

**What actually has a frozen capture.** `tests/fixtures/memory_parity/farm_reference/full` is the smoke cell only (`FULL_CELL`, 59 trades, E=0.0805). The six `short/` cells are not this test. Wave-0 `progB_w0_solo` ONH is **not** in `farm_reference`. Do not add it there: `test_farm_reference_bytes_match_official_pins` locks `farm_reference.sha256`.

**CI vs farm.** The full real-CSV smoke is ~3–4 h and is **not** a default CI job. There is no `THESISTESTER_MEMORY_PARITY_CSV`. `stage_trace.py` is the VmHWM trace (`--csv`, `--output-json`, `--run-label`); it is not the parity gate.

- CI: §5.1 (a)(b)(c) (merge gate). `HOOK_POINTS` symbol existence is not the gate.
- Farm, smoke: `python tests/fixtures/memory_parity/capture_operator.py --csv <farm 15s CSV> --output-dir <dir> --cells full --run-label <label>`, then `compare_captures` against `farm_reference/full`. Linux only. `THESISTESTER_MEMORY_PATH=array`. Do not compare a macOS capture to that tree (`ENGINEERING_PROPOSAL.md` §4.1).
- Farm, Wave-0 ONH solo: one-anchor spec copy (no `--cell`), side-by-side of the `0ebc1494` tree and the TS5 tree, stitch key omitted, same `compare_captures` rules, same env. Do not commit the capture.

A second test, `test_stitch_plan_absent_does_not_change_tick_source_id_none`, asserts identity keys stay `none` on 15s-only Run 2 specs.

---

### TS6 — Packet opt-in + docs (revertible packet PR)

| | |
|---|---|
| **Scope** | Generator / validator / Run 2 **tick** packet only. 15s packet (`manifest.yaml`, 20 / 898) stays byte-stable except if the generator rewrite would touch shared helpers — then split the helper so 15s YAML hashes do not change. |
| **Files** | `examples/studies/program_b/generate_program_b_yaml.py`; `validate_program_b_yaml.py`; regenerated `examples/studies/program_b_run2/manifest_tick.yaml` + 8 tick YAMLs; `tests/study/test_program_b_yaml.py`; `docs/PROGRAM_B_OPERATOR_RUNBOOK.md`; `docs/ASSUMPTIONS_AND_LIMITATIONS.md`; `docs/ARCHITECTURE.md`; `docs/ENGINEERING_ROADMAP.md`; `docs/README.md` (update the TS bullet’s status; the link itself landed in TS0). |
| **Packet locks** | `dataset.path` **unchanged** (same 15s CSV). `workers: 1` **unchanged** in generated YAML; 12 is a launch flag only. New additive `dataset.tick_stitch_plan` pointing at the committed or farm-local plan JSON. `dataset.tick_stitch_x1_burst_included` (bool) is required when `tick_stitch_plan` is set; `validate_program_b_yaml.py` rejects a missing value. Do **not** emit `data/mnq_tick_last.csv`. Do **not** require that placeholder to exist. `poc_windows: []` written explicitly on the **Run 2** tick packet (an omitted key becomes the product default `["30min"]`, and `None` inside `compute_profile_levels` becomes `30min`+`1h`+`4h`). Ticks feed VA + APOC only; rolling POC on 34 GiB would `list()` all ticks per worker. Today’s validator requires `poc_windows: ['30min']` on every tick packet (`validate_program_b_yaml.py`). Scope that change to Run 2 locks. Run 1 (`examples/studies/program_b/`) keeps `['30min']`. `apoc_enabled: true` only on APOC studies, as today. `TICK_GATED_SET` unchanged. |
| **Launch** | `study/launch.py` resolves each unique stitch filename under the operator NVMe root. Pass that root as env `THESISTESTER_TICK_STITCH_ROOT` and/or CLI `study run --tick-stitch-root` (neither exists on `0ebc1494`; `study run` today takes the study path plus `--output-dir`, `--workers`, `--confirm`, `--force`). Never a packet or cell field. Missing file refuses. SMB path refuses. |
| **Tests** | `test_program_b_run2_tick_manifest_validates` updated to the new key. 15s `test_program_b_run2_manifest_expands_898_with_run2_locks` still asserts `"tick_paths" not in dataset` and no stitch key. Generate-matches-committed for **15s** files still holds. Wave-7 provenance still `tick_last_volume_v1`. `test_program_b_wave7_identity_hashes_are_pinned` gets an intentional Run 2 w7 re-pin (it pins both `examples/studies/program_b/` and `program_b_run2/`; Run 1 pins stay). Split `test_program_b_tick_levels_keep_aggregation_and_rolling` so the `poc_windows` check is by root: Run 1 keeps `['30min']`; Run 2 is `[]`. Assert the Run 1 touch packet (`examples/studies/program_b/`, generator default `--trigger touch` and `--output-dir` = that directory) regenerates byte-identically. |
| **Acceptance** | Reverting TS6 restores the placeholder packet. TS5 code remains default-off. No study is launched by this PR. |

Farm steps through the impact report and the Q9 decision run after TS1–TS5 merge, not inside those PRs. The TS6 packet is the §8 step that records explicit `dataset.tick_stitch_x1_burst_included`; it is not a prerequisite of the impact report.

---

## 6. X1 fill design (normative)

**Supersedes** `tick_stitch_meta.json` `exclusions[0]` (`exclude_tick_full_session_VA` → NaN on 11-07 VA and 11-10 pVA).

### 6.1 Window

Fill **only** `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)` UTC.

Do **not** fill the shared empty gap ~16:49–17:58 UTC (both 15s and ticks are empty; that is a real feed hole, not a tick-only hole).

### 6.2 Residual allocation

For each 15s bar `b` whose timestamp (left edge) lies in the X1 window (the 17:58:00 bar is excluded from the fill because its left edge is before the window `[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)`):

```
tick_vol[b] = Σ Volume of stitched ticks with floor(ts, 15s) == b.timestamp
residual    = max(0, b.volume − tick_vol[b])
```

If `residual == 0`, no synthetic. Else one synthetic Last×Volume print:

- `price = (np.round(typical / tick_size) * tick_size).round(10)` where `typical = (H+L+C)/3` and `tick_size` is 0.25. That is `_bucket_prices`, not a separate Python `round` contract.
- `volume = residual`
- `timestamp = b.timestamp + 7.5s` (interior to the bar; session_date is still 2025-11-07)

Volume is conserved to 15s residual within `VOLUME_CONSERVATION_ATOL` already used by AP1 (`1e-9`).

Why **typical**, not uniform-range: AP1 rejected `bar_range_uniform_volume_v1` as a production APOC source (2/4 vs tick 4/4). A replay bar can have a wide high–low; smearing ~280k contracts across that range would invent a fake profile. Typical is a single documented, already-implemented allocation. It is **degraded**. The quality flag exists so no one treats 11-07 `pd*` as a clean tick object.

Why **residual**, not full 15s volume: the island `2025-11-07 18:00:53.022`–`18:00:54.037` is 10,000 real ticks / 11,505 contracts (patch notes). Adding the 15s bar on top would double-count.

### 6.3 Burst (18:00:45–18:01:30 UTC)

15s that day is itself degraded: ~280k contracts print in 18:00:45–18:01:30, which the quality report flags as a replay dump. That interval sits **inside** the X1 window and **overlaps** the 10k-tick island.

**No product default for the burst.** Include it via the same residual rule, or leave those bars at residual 0. That volume is the only 15s evidence for the hole; dropping it omits on the order of 10%+ of session volume. Accumu picks from the impact report before the tick packet is frozen (§8, Q9). Config key `dataset.tick_stitch_x1_burst_included` is required when `tick_stitch_plan` is set and is explicit; a missing value is a validator error, not a silent true or false.

**Honesty:** those synthetics are tagged `x1_burst` in the session quality record. They land on a handful of typical prices, so they can move POC.

**Impact test (TS4)** must print all three variants so the desk can see the move:

| Variant | 11-07 `pdVAH/VAL/POC` | 11-10 `pd*` | `pw*` of the W-SUN week containing 11-07 | 11-07 `APOC` |
|---|---|---|---|---|
| ticks-only (no fill) | report | report | report | **identical** |
| fill, burst bars residual = 0 | report | report | report | **identical** |
| fill-with-burst | report | report | report | **identical** |

`pm*` for 2025-11 also moves; not required by the prompt — see Q6.

### 6.4 APOC isolation

`select_a_period_rows` for 2025-11-07 is `[09:30, 10:00)` America/New_York = `[14:30, 15:00)` UTC (standard time). The fill window starts 17:58 UTC. Synthetics must not be concatenated into the APOC accumulator. `pAPOC` on 2025-11-10 may use the untouched 11-07 APOC.

### 6.5 Quality flag

Study-level booleans (not a per-date redesign) on the study cell index row written by `execute_study_cell` (not trade-frame columns, not level prices). `data_quality.*` is written only on stitch-on cells. TS6b persists those keys on `results_index.csv` when any row carries them; stitch-off keeps the `0ebc1494` header:

```text
data_quality.x1_15s_residual_fill = true   # 2025-11-07 only
data_quality.x1_burst_included    = <explicit>   # cell-output flag; value is dataset.tick_stitch_x1_burst_included (no silent default)
data_quality.shared_gap_1649_1758 = true   # not filled; both sources empty
```

Named-VA cells on 11-07 / 11-10 remain `ok` if the profile is finite. The flag is how the run is read, not a `failed` cell.

---

## 7. Parity, regression, tolerances

| Gate | Tolerance | Applies to |
|---|---|---|
| CI §5.1 (a)(b)(c) (TS5 merge gate); farm `capture_operator` + `compare_captures` (zero tolerance, §8) | **None** on the farm compare. `HOOK_POINTS` is symbol existence only. Parity runs use production `THESISTESTER_MEMORY_PATH=array`. Smoke vs `farm_reference/full`. Wave-0 ONH solo is a one-anchor spec copy (no `--cell`), side-by-side vs `0ebc1494`, not a new committed capture. Those ONH cells do not exercise VA/APOC. | §5.1 / §8 |
| Existing golden / fade / MW / TV / AP / RP tests | Existing (no regen) | Default-off tree |
| Tick → 15s **bar** OHLC compare (optional diagnostic, not a merge gate) | exact OHLC ≥ 98%, close ≥ 99%; **not** bar-exact volume (sampled 96.1%) | Farm stitch QC only |
| Session Σvol ticks/15s | 0.997–1.000 (source 0.997312–1.000276) after clip is informational | Not a VA equality claim |
| X1 impact test | Report-only; APOC identity across variants is exact | TS4 |
| Hourly guard | Fail on unexpected ≥ 5 s hole with 15s volume | TS3 |

`LEVEL_ENGINE_VERSION` stays 11. Stitch-on identity is `tick_stitch_source_id` only. Off → existing `none`, or `compute_tick_source_id` when `tick_paths` is set (whole-file content hashes, not a hash of the path list).

---

## 8. Farm sequence (after TS1–TS5 merge, not inside those PRs)

Order is mandatory: **0 confirm no study is running → copy to NVMe → sha256/verify → QC re-run → farm impact report → Q9 decision by Accumu → TS6 packet with explicit `dataset.tick_stitch_x1_burst_included` → stitch-off parity → pdPOC pilot → APOC pilot → full `manifest_tick.yaml`.**

0. **Confirm no study is running.**
1. **Copy.** 39 unique CSVs from `/mnt/nas-trading/thesistester/chart_exports/tick_data/` to farm NVMe (suggested `~/thesistester/data/ticks/` — Q2), including segments 0–1 which clip drops (§4.4). `cp`/`rsync` of **untouched** bytes. Do not concatenate. The 15s CSV is already local (`~/thesistester/data/`, 344,135,035 bytes). Do not re-point `dataset.path`. The parent streamer accepts only that tick root. Workers do not open it. Do not rewrite generated `workers: 1`; the full run passes `--workers 12`.
2. **sha256/verify.** `sha256sum` each NVMe file; size must match the plan (`36,415,038,585` unique-file bytes). Store the digest sidecar next to the plan. Re-run `verify_tick_stitch_plan`.
3. **QC re-run (hard gate; Q7 resolved).** Re-run `tick_quality_report` on the 46-segment plan. Any unexpected hole other than X1 = **stop**. This step is before parity and before the pilots.
4. **Farm impact report.** Parent-only command on the NVMe stitch (TS4). Emits the real 2025-11-07 `VAH`/`VAL`/`POC` for ticks-only, fill-without-burst, and fill-with-burst, plus downstream 2025-11-10 `pd*` and the W-SUN week `pw*` deltas. The synthetic fixture test stays the CI test.
5. **Q9 decision by Accumu.** Sets explicit `dataset.tick_stitch_x1_burst_included`. A missing value stops the sequence.
6. **TS6 packet** with that explicit value. Generated YAML stays `workers: 1`. The NVMe root is not written into the packet or the cells (§ TS6 Launch).
7. **Stitch-off parity.** `capture_operator` + `compare_captures`, zero tolerance, production `THESISTESTER_MEMORY_PATH=array` (§5.1). Smoke cell vs `farm_reference/full`. Wave-0 ONH solo is a one-anchor spec copy (no `--cell`), side-by-side against a `0ebc1494` run, not against `farm_reference` (that cell is not in the locked tree). Any delta other than ledger wall-clock → **stop**.
8. **pdPOC pilot.** One tick-gated cell only: `pdPOC` (first core of `progB_r2_w0_va`). `study run` has no `--cell` flag, and `progB_w0_va.yaml` expands nine cores — do not launch that file. Use a one-anchor spec copied from it with `core_level: [pdPOC]` only and `workers: 1` (same value as the APOC copy; committed Run 2 YAML is `workers: 1`). That copy is not a hand-edit of the generated packet. It must set `poc_windows: []` explicitly (omitting the key merges the product default `["30min"]`, which makes each worker `list()` every tick). After TS6, generated Run 2 tick YAML is already `poc_windows: []`. Run 1 tick YAML keeps `['30min']`. The copy must not put farm CSV paths on the cell. Confirm parent RSS, no SMB open (`lsof` / `nfsstat`), X1 flag present on 11-07, prior-profile table has the 11-07 POC row (= 11-10 pdPOC). The VA pilot does not enable APOC. Not a full-packet result.
9. **APOC pilot.** Same stitch plan and `workers: 1`: one-anchor spec with `core_level: [APOC]` (`APOC_LEVEL_NAMES` in `thesistester/levels/catalog.py`), `poc_windows: []`, no farm CSV paths on the cell. Pass: the cell runs to completion; workers never open or content-hash farm tick CSVs (same sentinel as the TS5 table injection); `MemAvailable` stays ≥ 6 GiB; APOC on a few spot-check sessions matches a direct parent-side computation from the stitch.
10. **Full `manifest_tick.yaml`.** 8 studies / 253 cells, one study at a time, 12 workers, Notion/logging as Run 2. Soft-resume. Do not `--force`. A one-cell pilot can't show 12-worker peak RAM; watch `MemAvailable` on the first full study (same 6 GiB abort).

Two one-cell pilots in order: pdPOC, then APOC. Both must pass before `manifest_tick.yaml`.

If verify, the QC re-run, or parity fails, do not start the pilots.

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
3. **Q3 — Resolved.** Two one-cell pilots in order: pdPOC, then APOC (§8).
4. **Q4 — Parent RSS cap during the 34 GiB stream?** Operational abort at `MemAvailable < 6 GiB` is proposed. Confirm the number; it is not a unit-testable CI gate.
5. **Q5 — sha256 in the plan JSON?** The farm plan has sizes and first/last, not content hashes. TS1 can compute a sidecar at verify time. Should that sidecar be committed?
6. **Q6 — Impact-test `pm*`?** The fill also moves November 2025 `pm*` and December prior-month VA. The required triple is 11-07 VA / 11-10 `pd*` / that week’s `pw*`. Add `pm*` or not?
7. **Q7 — Resolved (hard gate).** Re-run `tick_quality_report` on the 46-segment plan before parity and before the pilots (§8). Any unexpected hole other than X1 = stop. The attached report is pre-patch (40/37). Drift result should still hold; hole A/B/D/E should now be gone. Farm ops, not a code PR.
8. **Q8 — Resolved.** Omit `tick_paths` on stitch cells. `tick_stitch_plan` is the tick input. A non-path `tick_paths` token is refused by `launch.py` (the pinned path must be an existing file). A leftover path list is opened and content-hashed inside `compute_levels`. Expanded cells do not carry farm CSV paths.
9. **Q9 — X1 burst include?** **Resolved.** Decided by Accumu 2026-10-07: `tick_stitch_x1_burst_included = false` (without burst), from farm impact report `farm_impact.json` sha256 `04fab0a7ce3aa90ed296a64e760b532348e9e9ed6796c0ffedaa67f5aaca4da3` (run 2026-10-06 at `84e7ccc0`). Burst excluded vs ticks-only: 11-07 VA VAH/VAL/POC −146/−156/−248, `pw*` POC 0, `pm*` POC 0. With the burst, `pw*` POC would move −960 and Nov `pm*` POC −410. `study/schema.py` (TS5) and `validate_program_b_yaml.py` (TS6) reject a missing value when `tick_stitch_plan` is set.

---

## 11. Documentation map (later PRs)

| When | Doc | Sentence that becomes true |
|---|---|---|
| TS5 | `ARCHITECTURE.md` | Additive `dataset.tick_stitch_plan` / `apoc_tick_table_path`; workers do not hold farm ticks. |
| TS5 | `POINT_IN_TIME_GUARANTEES.md` | Clip and the X1 fill still join through `shift(1)`; no future session enters the prior profile. |
| TS4–TS5 | `ASSUMPTIONS_AND_LIMITATIONS.md` | 11-07 VA is 15s-residual-filled and flagged; APOC that day is clean ticks; clip to 15s windows. |
| TS6 | `PROGRAM_B_OPERATOR_RUNBOOK.md` | Tick packet launch: NVMe root, verify, stitch-off parity, pilot, then 253 cells. |
| TS6 | `ENGINEERING_ROADMAP.md` + `docs/README.md` | Roadmap row, and the TS index bullet’s status (the link landed in TS0). |

`METRICS_GLOSSARY.md` only if a new named statistic is emitted (the quality flag is provenance, not a KPI).

---

## 12. Per-PR §4.2 checklist (copy into each TS PR body)

- Unit tests for the new function, deterministic, no farm CSV. This series adds no randomness, so no new `random_state`.
- Golden-master / fade artifacts untouched. `tests/fixtures/memory_parity/farm_reference/` and `farm_reference.sha256` untouched. `LEVEL_ENGINE_VERSION` stays 11. Generated YAML keeps `workers: 1`.
- Default-off: stitch key absent → `0ebc1494` behaviour. TS5 merge gate is §5.1 (a) call sentinels, (b) fixture VA/APOC byte-identity vs pins from `0ebc1494`, (c) no `data_quality.*` on stitch-absent index rows. `HOOK_POINTS` only checks symbol existence. Farm `capture_operator` + `compare_captures` (§8) does not exercise VA/APOC and does not compare `data_quality.*`.
- Docs in the same PR for any sentence that became true (`METRICS_GLOSSARY.md` only if a named statistic is added).
- CI green. Small surface. One logical commit unless the reviewer asks otherwise.
- Regression paragraph: which named test proves default-off identity, and that tick VA/APOC differences are **out** of that claim.

TS6b: §8 step 8 pdPOC pilot at 3b81b1f8 found data_quality.* dropped by _write_results_index; Accumu option A 2026-10-07; pilot re-run after merge
