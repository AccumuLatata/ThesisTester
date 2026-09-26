# Worker memory — implementation plan (MW)

**Document type:** Implementation plan (fully scoped PRs). This file is the review copy of the finished plan.
**Date:** 2026-09-26
**Status:** **Plan only.** No runtime change ships in the PR that adds this document. Implementation has not started.
**Series code:** **MW** (worker memory). Not WMV (`wVWAP` / `mVWAP`).
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 and §4.2, plus the stricter locks in §3 of this file. The MW locks add constraints. They do not weaken §4.1, the byte lock on `tests/fixtures/golden/README.md` (`test_existing_golden_files_byte_identical`), or the rule that legacy goldens are never regenerated without `GOLDEN_REGEN`.
**Farm code the measurements describe:** commit `59a4652`. The same memory shape was confirmed on `9cd53af` (spawn, discarded load-time context, sequential replica loop, per-minute DataFrame map). Re-check call sites if `main` moves; the contracts below are the behavior, not the line numbers. **MW0 is not recorded at `59a4652`.** It is recorded, flag off, at the exact commit MW1 branches from. That commit must first reproduce the `59a4652` reference-cell result (§9). `main` has moved since `59a4652`, including QR E-9 (vectorized 15s→1m derive) and QR E-10 (vectorized `sl_first` walk).

This document supersedes the investigation notes. These locks are the contract, not optional commentary:

1. The process-local context cache is content-addressed and cleared at the end of `execute_study_cell`. It is not keyed by `id()` or any address. It is also not keyed by `DataIdentity.dataset_id()` or `hash_dataframe` (§10.2). The digest is order-sensitive and covers only the columns prepare reads.
2. `canonical_bundle_hash` is a fail-closed check. PR MW2 keeps `hash_dataframe` identical. Raw parquet bytes are not a study decision.
3. A full-CSV stage trace on the farm is a hard gate before MW1. The §9 equality pre-step is recorded first. The trace picks the PR order. §8.1 rules are mutually exclusive; the first match wins.
4. The lazy group frame carries `timestamp` plus OHLC. `resolve_subtimeframe_bar` writes `exit_subbar_timestamp` from `sub_bar["timestamp"]`. A float64 OHLC array alone changes trades.
5. MW0 does not edit `tests/fixtures/golden/README.md`. That file is byte-locked. The pointer lives under `tests/fixtures/memory_parity/` and in `ENGINEERING_PROPOSAL.md` §4.1.

---

## 1. Purpose

Cut private per-worker RSS far enough that **16 study workers** fit on the farm PC (AMD Ryzen 9 9950X, 16 cores / 32 threads, 64 GB RAM, ~59 GiB usable, Ubuntu 26.04) without changing a research result.

Today a Program B Run 2 cell uses about **6.5 GiB** RSS alone. Under six workers the recorded per-worker figure was **7.58 GB** (7.06 GiB) and the machine peaked at **41.3 GB** (38.5 GiB). Six times 7.58 GB is 45.5 GB; the measured total is lower. Those six-worker figures were recorded in decimal GB. Every threshold and the 16-worker budget in this file are GiB, the same unit as `MemAvailable`. The worker-count gate, which is not in this repo, therefore stops around 6–8 workers and leaves cores idle. A cell takes about **3.2–4.2 h**. The same cell on one Apple M1 Pro core took 14,518 s versus 11,042 s on one farm core (**1.31×**), so the workload may also be memory-bound.

**Target:** per-worker peak RSS **≤ 3.3 GiB** so `16 × 3.3 GiB = 52.8 GiB` fits in ~59 GiB usable, with a preferred landing near **2.5 GiB**. Wall time of a cell may not exceed **105%** of the flag-off run. Faster is acceptable.

**Reference cell (known result, identical on macOS and Linux):**

`progB_r2_smoke_ONH_SMA50_5min_c0000_anchor_rules_fade_1min_SMA_50_5min_otfOff_a73c63ebfa`

Spec: `examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml`. ONH × SMA_50_5min, `anchor_rules`, fade at 1min, stop/target 80/80 ticks, 50 random-baseline replicas, `random_state` 42, grid / validation / walk-forward off. Input: one 15-second MNQ Quantower History Exporter file, 2024-08-01 through 2026-08-07, ingestion `15s_primary_derive_1m`, `subtimeframe_conservative`. Known result: **59 trades, E=0.0805**.

---

## 2. Non-goals (forbidden)

This is a resource refactor. The engine, the research logic, and the app's scope stay as they are. If a memory saving requires any of the following, it is rejected. The rejected list in §7 is the closed set from the investigation; do not reopen those items inside an MW PR.

- Signals, levels, indicators, entry/exit rules, fills, stops/targets, costs, trade selection.
- Random-baseline logic, RNG seeds, and the **order** of random draws (`numpy.random.SeedSequence.spawn` in `vs_random_benchmark`).
- Study definitions, cell naming/hashing, CLI flags, config options, output schemas, file formats, ledger format, resume behaviour.
- `resolve_subtimeframe_bar` (the fill walker). The new context must hand it the same 4-row frame it already reads.
- Any cleanup, refactor, or feature that is not required to hit the RSS target under the locks in §3.

`THESISTESTER_MEMORY_PATH` is an environment switch, not a CLI flag and not a StudySpec key. See §4.

---

## 3. Locks that every MW PR keeps

| Lock | Rule |
|---|---|
| Flag | `THESISTESTER_MEMORY_PATH=array` opts in. Unset, empty, or any other value is the current path. Default stays off until the full reference cell matches on Linux and macOS. Unsetting the variable is the rollback. No code change. |
| Flag is invisible | The variable is not written into `cache_provenance`, the hashed bundle, the ledger, the study identity, or the index, except where the index already stores values that are themselves unchanged. |
| RNG | `SeedSequence.spawn` order and `random_entry_signals` are not edited. The context build does not draw. |
| Walker | `resolve_subtimeframe_bar` is not edited. |
| Equality | Trades (every column), ordered `replica_expectancies`, summary metrics, DA5 index fields, and `canonical_bundle_hash` are bit-identical. Float64 compared as bits. `NaN` equals `NaN`. No tolerance. |
| Platforms | The golden suite passes on Linux and macOS before the operator default may flip. |
| Speed | Per-cell wall time ≤ 105% of the flag-off run on the same machine. |
| Resume | A half-finished flag-off study resumes flag-on. Finished cells are not recomputed. Pending cells are not skipped. Ledger records of finished cells are not rewritten. |
| Mix | A study with some cells flag-off and some flag-on matches an all-flag-off study on trades, replica stats, canonical hash, and ledger fields (new cells' wall-clock timestamps excepted; see MW2). |
| Existing results | Finished bundles and a partly finished ledger stay valid. Names, hashes, and resume rules do not change. |
| Shared data | Read-only. A crashing worker cannot corrupt it. Stale bytes fail a content hash. Shared files are cleaned up with the artifact store. |
| Existing tests | Stay green. Each MW PR adds the parity test named in its section. |

§4.2 of the engineering proposal still applies: unit test, golden preserved, docs in the same PR (`ARCHITECTURE.md`, `ASSUMPTIONS_AND_LIMITATIONS.md`, and `PROGRAM_B_OPERATOR_RUNBOOK.md` for the worker cap), small surface, regression paragraph in the PR body.

---

## 4. The switch

One environment variable.

```text
THESISTESTER_MEMORY_PATH=array
```

Read it in one place and pass a boolean down. Do not read it from StudySpec, CLI, or `cache_policy`. Do not add a value to `cache_outcome`. The artifact cache (`read_write` / `data_hit` / `levels_hit`) is a different mechanism and stays as it is.

MW1 and MW2 both sit behind this one switch. MW-L, if the trace requires it, is also behind the switch **or** is a pure allocation change that is bit-identical with the flag off. Prefer the switch if there is any doubt. MW3 is behind the same switch.

---

## 5. What one worker holds

Each cell is its own process. `thesistester/study/execute.py` builds the pool with `multiprocessing.get_context("spawn")` and does **not** pass `max_tasks_per_child`. On Python 3.10 that argument does not exist and the worker lives until the pool closes. On 3.11 and 3.12 the default is also unlimited reuse. One worker therefore runs many cells. With `workers: 1` there is no pool: `execute_study_cell` is called in a loop in the parent, so that process runs every cell. `thesistester/cli.py` batch mode is the same pattern (`executor.map` of `_execute_run`, no `max_tasks_per_child`).

`spawn` means no copy-on-write of the parent's numpy buffers. `cache_outcome=data_hit` still re-reads the CSV and re-derives the 15-second frame inside `_load_15s_primary_experiment_data`, then discards the context it just built. Only the 1-minute parent may be replaced from the parquet artifact, and only when `binding.identity.dataset_id()` equals the derived parent's `dataset_id()`. `levels_hit` loads another private copy of the levels frame. Decoded frames are private. Six workers at 41.3 GB total is six private heaps (6 × 7.58 GB = 45.5 GB; the measured total is a bit lower).

The smoke YAML's `levels` block is shared by every Program B cell. `compute_all_levels` emits **70 columns** even for the ONH × SMA_50_5min cell: session structure, SMA 50/200 and EMA 9/21 on 1/5/30min, rolling VWAP 30min/4h, pivots on 1min/5min/30min/4h, session VWAP, four single-print columns, `prev30mVWAP` plus two hit columns, plus OHLCV and `session`. Measured dtypes: 68 float64, one timezone-aware datetime, one string. `poc_windows` is empty and `apoc_enabled` is false on this 15-second packet, so those families are absent.

`subtimeframe_conservative` stores every **complete** parent minute as its own DataFrame. Incomplete minutes become a short fallback string and are not a frame. The function is `prepare_subtimeframe_conservative_context` in `thesistester/engine/intrabar.py`:

- `group = sub_reset.iloc[group_start:group_end].copy()`
- on success, `groups[index] = group.reset_index(drop=True)`

That function runs:

1. Once inside `_load_15s_primary_experiment_data`. The return value is discarded. The call still validates and still allocates.
2. Once inside the real backtest (`simulate_trades` → `prepare_subtimeframe_conservative_context`).
3. Once per random replica.

`vs_random_benchmark` in `thesistester/analytics/overfitting.py` loops `for child in seed_sequence.spawn(int(n_replicas))` and keeps a list of expectancy floats. It does not keep 50 trade frames or 50 maps. For the reference cell that is **1 + 1 + 50 = 52** builds. A 0-trade cell pays only the load-time build: `simulate_trades` returns before building a context when `signals` is empty, and the null baseline returns before the loop when there are no trades.

`_cell_bars` prefers the levels frame over `data`. Replicas therefore call `simulate_trades` with the wide levels frame as `df` and the 15-second frame as `subtimeframe_data`. The context depends on parent OHLC and sub-bar OHLC, not on level columns.

Calendar bound used for the planning count: 2024-08-01 00:00 ET through 2026-08-07 00:00 ET, CME 18:00–17:00 with the 17:00–18:00 halt, weekends out, holidays still in: **725,880** one-minute bars and **2,903,520** dense 15-second bars. That ET bound is the session-hour estimate only. The smoke YAML sets `source_timezone: UTC`. Slice keys in §9.2 are UTC. The farm trace, not this count, is the gate.

---

## 6. Measured breakdown

The vendor CSV was not on the investigation machine (4 CPUs, 15 GiB RAM). Slopes below are synthetic 15-second bars run through the real prepare / levels / naked / trigger functions. They are the planning numbers. The farm trace in §8 replaces them as the acceptance gate.

### 6.1 Per-minute DataFrame map

Fresh process, no tracemalloc, RSS added by `prepare_subtimeframe_conservative_context` after the bars already exist:

| Complete parent minutes | RSS added | Per minute |
|---:|---:|---:|
| 4,000 | 17.3 MiB | 4.42 KiB |
| 16,000 | 65.8 MiB | 4.21 KiB |
| 64,000 | 267.4 MiB | 4.28 KiB |
| 128,000 | 537.2 MiB | 4.30 KiB |

Slope from 16k to 128k: **4.310 KiB RSS per complete minute**. A dense full calendar is **2.98 GiB** for one map. At about 75% of minutes complete (the fraction that makes 52 builds land in the observed 3.2–4.2 h), the live map is about **2.24 GiB**.

A second and third build in the same process, after `del` and `gc.collect()`, reused that small-object arena. RSS stayed flat (64k minutes: 429,568 KiB, then 429,712, then 429,756). Large numeric arrays did **not** fit in those holes: holding 312.5 MiB of float64 blocks raised RSS by that amount, and the following map rebuild added only ~6 MiB. So:

- Rebuilding the map costs **time**, not a second copy, when the previous map was freed and nothing else filled the holes.
- Level frames and other large numeric blocks allocate **on top of** the map's arena.

Build time, same path, no tracemalloc: **475 µs per minute** (32,000 minutes in 15.2 s). Fifty-two dense builds are about 5.0 h. The observed 3.2–4.2 h cell matches roughly 70–85% of minutes becoming a group. At 75% that is about **3.7 h** of allocator work, which is most of the cell.

memray on 16,000 groups: 1,057,487 allocations, about 850k of them in pandas (Index, datetime box, Arrow string). One group's `memory_usage(deep=True)` was 0.36 KiB. The resident cost is the DataFrame object, not the four OHLC rows.

### 6.2 Other holders (synthetic, scaled to 725,880 parent minutes)

Levels on one 1,380-bar session: 70 columns, **563.22 bytes/row** deep. Scaled:

| Holder | Full-window deep size | Coexists with the map? |
|---|---:|---|
| 15-second source + 1-minute parent | ~0.20 GiB | Yes. The operator's load plateau is ~0.8 GiB and includes the Quantower CSV re-parse in `load_ohlcv` |
| Levels frame | 0.38 GiB | Yes |
| `flag_naked_levels` | 0.38 GiB | Yes. `out = df.reset_index(drop=True).copy()` copies every column, then adds `<level>_naked` bools. `naked_only` is false on the smoke cell and the copy is still made and stored |
| 1-minute trigger frame | ~0.40 GiB | During `generate_signals`. `trigger_timeframe: 1min` is not `"base"`, so `_prepare_trigger_dataframe` copies the level columns |
| One replica's trades and the expectancy list | Negligible | 59 trades; 50 floats |
| Bundle parquet bytes while replicas run | ~0.2–0.4 GiB | Held because `execute_study_cell` keeps `state` and the zip bytes until the replicas finish |

A 4-session pipeline (5,520 parent minutes) showed naked deep memory matching the levels frame (72 columns vs 70) and the context adding the per-minute cost on top of those frames.

### 6.3 How 6.5 GiB is composed

**Solo 6.5 GiB** = one map arena (about 2.2–3.0 GiB at realistic completeness) + load plateau and frame copies (about 1.6–2.2 GiB) + about **1.5–2.5 GiB that the synthetic run cannot assign**, because the vendor file was absent. That remainder is why §8 is a gate and not a footnote.

The Quantower path in `load_ohlcv` (`format_profile != "canonical"`) reads the file, projects to required columns, writes those columns to a `StringIO` via `to_csv`, and parses that text again. That is a real second materialization. Whether it is still resident after `_load_15s_primary_experiment_data` returns is exactly what `R_load` measures.

---

## 7. Options

### 7.1 Ranked

| Order | Change | PR | Private RSS removed | After this step (planned split) |
|---|---|---|---:|---|
| 1 | One array-backed context, built once per cell, reused by the load-time check, the backtest, and all 50 replicas. Cleared at cell end | MW1 | 2.2–3.0 GiB, and most of the 3–4 h | Planning estimate **3.4–4.6 GiB**. Not enough for 16 workers. Farm gate is §8.2, relative to `R_signals` |
| 2 | Stop holding full-width copies in naked flags and 1-minute trigger prep. Drop those objects after the bundle is built, before the replica loop. `hash_dataframe` unchanged | MW2 | ~0.8–1.2 GiB | Planning estimate **2.4–3.4 GiB**. Clears 3.3 GiB only when §8.1's capacity check passed. Farm gate is §8.2 |
| 3 | Read-only `.npy` memmap of parent, source, and levels | MW3, optional | Per-process RSS barely moves. Unique machine RAM drops by the shared pages | Only if unique RAM is still tight after MW2, or CSV re-parse dominates startup |

MW1 is required. MW2 is required before the gate may go to 16. MW1 alone leaves a worker near 4 GiB, and `16 × 4 GiB = 64 GiB` does not fit in 59 GiB usable. MW-L (loader) is inserted by the §8 rule, not by default.

Why MW1 cannot change a result: `resolve_subtimeframe_bar` is untouched and still receives a frame whose `timestamp`, `open`, `high`, `low`, `close`, index, and dtypes of those columns match today's group. `exit_subbar_timestamp` is that timestamp. Prepare still raises on the same OHLC mismatches and still records the same fallback reasons. The replica loop and `SeedSequence.spawn` are untouched. The context is read-only after prepare. Building it once is valid because the build does not consume the RNG.

Why MW2 cannot change a result: every frame written into the bundle or the levels artifact has the same `hash_dataframe` as the flag-off frame (columns, `str(dtype)`, row hashes). That keeps `canonical_bundle_hash` identical. The replica path needs `timestamp` plus OHLC, in the same order and bits as the levels frame the backtest used, plus the 15-second frame. It does not need level columns. Dropping objects after `build_research_bundle` returns, and after the index row has hashed those bytes, does not change the zip that was already produced. A projection that drops `timestamp` nulls DA5, because `random_baseline_fields` catches the prepare error.

Why MW3 cannot change a result: the memmap is float64, opened read-only, and accepted only when its hash equals the existing `DataIdentity` / `LevelsIdentity` for that input and levels settings. Workers never write it. A crash cannot corrupt a read-only file. A hash miss rebuilds the file.

### 7.2 Rejected

- **float32** on prices, indicators, stops, or R. Those values feed fills and expectancy.
- **Computing only ONH and SMA_50_5min.** That changes the levels artifact, the bundle frame, and the cache identity. The other columns are part of the study output.
- **Changing replica count, seed, or draw order, or running replicas in parallel.** Parallel replicas raise the peak. The spawn order is the null.
- **Editing `resolve_subtimeframe_bar` or the exit walk.** That is the fill path.
- **`fork` plus copy-on-write.** Workers are `spawn` on purpose. macOS fork is unsafe, and the golden suite has to pass on macOS. A later write copies the page privately anyway.
- **`multiprocessing.shared_memory` as the store.** A dead worker leaks the segment, and macOS unlink behavior differs. A read-only file in the existing artifact store does not have that lifetime.
- **Persisted dtype changes** (session string to categorical, narrower on-disk level floats). `hash_dataframe` includes `str(dtype)`, so the canonical hash would move. An internal offset table inside the context is allowed; it is not persisted. The start offset is `int64`. A count may be `int32`. An `int32` start would wrap on a longer source and attach the wrong sub-bars.
- **Skipping the load-time validation.** The same mismatches must still raise. The array path runs the same checks without a DataFrame per minute.
- **Keying the context cache by `id()` or any memory address.** Addresses are reused after GC. See §10.
- **Leaving the context cache alive across cells in one worker.** Cleared at the end of `execute_study_cell` at the latest. See §10.
- **Treating `canonical_bundle_hash` as informational.** Journal ingest and the assistant refuse a mismatch. See §11.
- **Doing the StringIO loader change inside MW1 or MW2 by default.** It is MW-L, and only if §8 says so. It is an ingestion path.

---

## 8. Hard gate before MW1 — full-CSV stage trace

No MW1 (and no MW-L, and no MW2) code is written until this trace has been run on the **farm CSV** at the exact commit MW1 will branch from, flag off, one process. That is the same commit as MW0 (§9), after the §9 pre-step has matched `59a4652`. A short synthetic prefix cannot see a loader buffer that scales with the real file. The trace is an operator measurement. It is not a product change and it is not required to land in git before the numbers exist. Record the numbers in the MW1 PR body so the order decision is reviewable.

Stop points, **full file**, `VmRSS` after `gc.collect()`:

| Name | When |
|---|---|
| `R_load` | Immediately after `_load_15s_primary_experiment_data` returns. The discarded context has been freed |
| `R_signals` | After `generate_signals` returns |
| `R_ctx` | While the first `simulate_trades` context is alive |
| `R_done` | After that call returns and `gc.collect()` |

`map_step = R_ctx − R_signals`.

Do not run all 50 replicas for this split. The synthetic rebuild test showed a second map does not raise RSS once the first map's arena exists. One live context plus the held frames is the peak shape. The 50-replica **timing** is a separate measurement in §14.

### 8.1 Decision rule

Apply the first matching rule. The rules are mutually exclusive. `R_load ≥ 4.0 GiB` together with `map_step ≥ 1.5 GiB` is rule 2, not rule 1: the map is still a large step, so MW1 stays first.

1. **Loader is the peak.** `R_load ≥ 4.0 GiB` and `map_step < 0.5 GiB`. Do MW-L before MW1. Do not treat MW1 → MW2 as the order. After MW-L, rerun this trace and apply this section again. The peak is the loader. Removing the map would not move it.
2. **Loader still resident, map still large.** `R_load ≥ 2.0 GiB` and `map_step ≥ 1.5 GiB`, and rule 1 did not match. This includes `R_load ≥ 4.0 GiB` when the map step is also large. MW1 first, then MW-L, then MW2. The Quantower parse or the `StringIO` re-read is still resident after load returns. MW-L is specified in §12. The post-MW-L trace re-enters this section before MW2.
3. **Planned split.** All three hold: `R_load ≤ 1.2 GiB`, `map_step` between 1.5 and 3.5 GiB, and `R_ctx` between 5.5 and 8.0 GiB. Keep MW1 → MW2. No MW-L. Then apply the capacity check in the next paragraph.
4. **Anything else stops the series.** Examples: `R_load` between 1.2 and 2.0 GiB, `map_step` between 0.5 and 1.5 GiB while `R_load ≥ 2.0 GiB`, or `R_ctx` outside 5.5–8.0 GiB on a split that otherwise looks planned. Write the four numbers down and revise this plan before coding. Do not guess.

**Capacity check, rule 3 only.** MW2's stated removal is about 0.8–1.2 GiB of full-width copies on top of `R_signals`. If `R_signals > 4.5 GiB`, then `R_signals − 1.2 GiB > 3.3 GiB`: the copies can leave and the worker still cannot fit 16-wide. Stop and revise this plan before MW1. Do not spend MW1 and MW2 on a path that cannot hit §1. Rule 2 does not use this check until the post-MW-L trace comes back through rule 3.

### 8.2 Ranges the farm confirms or rejects

The §6 bands **3.4–4.6 GiB** (after MW1) and **2.4–3.4 GiB** (after MW2) are planning estimates for the synthetic split. They are not the reject threshold. Under rule 3, `R_signals = R_ctx − map_step` can sit anywhere from 2.0 to 6.5 GiB, so a fixed 3.4–4.6 band would reject a correct MW1 when `R_signals` is 2.2 GiB and accept nothing useful when `R_signals` is 6.0 GiB. Gate on the trace.

| Point | Accept | Reject the savings claim |
|---|---|---|
| After MW1 (map gone, full-width copies still held) | peak in `[R_signals, R_signals + 0.4 GiB]` | below `R_signals − 0.3 GiB` or above `R_signals + 1.0 GiB` |
| After MW2 (those copies released, `hash_dataframe` unchanged) | peak ≤ 3.3 GiB, and at least 0.4 GiB under `R_signals` | above `R_signals − 0.4 GiB` (the copies did not leave), or above 3.6 GiB |

A MW1 peak inside its band may still be above 3.3 GiB. That does not fail MW1. It keeps the 16-worker gate closed until MW2. Sixteen workers stay blocked until a flag-on smoke peak is ≤ 3.3 GiB. See §14. A peak above 3.6 GiB after MW2 blocks that gate even if the copies did leave.

---

## 9. MW0 — Golden capture

**Depends on:** the equality pre-step below. The §8 trace may run in parallel only after that pre-step passes, and only on this same commit. Recorded with the flag off (the flag does not exist yet) at the **exact commit MW1 branches from**. Later MW PRs match these outputs. They do not regenerate them. They do not move the pin.

The numbers in §5 and §6 were measured at `59a4652`. MW PRs branch from current `main`, which has moved (QR E-9, QR E-10). The golden follows the branch commit. The known result stays the `59a4652` result.

**Mandatory pre-step, before MW0 is recorded.** On that commit, flag off, Linux, one process, the full reference cell must reproduce the `59a4652` result: **59 trades, E=0.0805**, and the same trade rows and the same `replica_expectancies` bits as the `59a4652` run. If it does not, **stop the series and report**. Do not record MW0. Do not start MW1, MW-L, or MW2. A short-window match is not this pre-step.

**Goal:** a reference suite that fails on any bit difference.

**Non-goals:** no engine change, no memory-path code, no `GOLDEN_REGEN` of the existing legacy golden set under `tests/fixtures/golden/`. MW goldens are a new suite. Do not rewrite `trades_legacy.*` or `legacy_bundle_hash.txt`.

### 9.1 What is stored

For every cell:

- Trades, every column.
- The ordered `replica_expectancies` list (the in-memory list from `vs_random_benchmark`, not only the four DA5 summary floats).
- Summary metrics: `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, `profit_factor`, `win_rate`.
- DA5 index fields: `random_null_expectancy_r`, `random_null_std_r`, `random_p_value_ge`, `expectancy_minus_null_r`.
- The ledger cell record: `status`, `error`, `bundle_path`. Wall-clock `started_at` / `finished_at` are stored and are **not** part of equality across machines.
- `canonical_bundle_hash`.

Compare float64 as bits. `NaN` equals `NaN`. No tolerance. The bundle hash **is** part of MW equality because §11 shows it is a decision. Raw zip bytes are not part of equality: the manifest `created_at` is stripped inside `canonical_bundle_hash` and two flag-off runs of the same cell already differ in zip bytes.

### 9.2 Cells

Short window: the same Quantower file, cut on **UTC** timestamps because the smoke YAML sets `source_timezone: UTC`. The inclusive start is `2024-08-01 00:00:00+00:00` and the exclusive end is `2024-10-01 00:00:00+00:00`. Save that slice once so the dataset hash is stable. Do not cut on `America/New_York` midnight. The §5 "ET" minute count is a planning estimate of CME hours, not this slice key.

All six use MNQ, `15s_primary_derive_1m`, `subtimeframe_conservative`, `tolerance_ticks: 10`, `min_valid_confluences: 1`, `naked_only: false`, commission 0.5 per side, slippage 1 tick, flatten 16:00 `America/New_York`, grid / validation / walk-forward off, `n_replicas=50`, `random_state=42`, `anchor_rules`, direction `both`, `single_position`. Those match the smoke constants. Do not drop tolerance to 0 to manufacture a 0-trade cell.

`same_bar_opposite_direction` is per cell, not an escape hatch:

| Cells | Policy | Why |
|---|---|---|
| 1–4 and 6 | `raise` | The reference cell's policy. If a short-window cell raises, stop and report. Do not switch the policy to obtain trades |
| 5 | `legacy` | Engine default. `3c` can emit two directions on one bar; `raise` aborts the cell and then it does not exercise fills |

| # | Entry | Anchor × partner | Stop/target | Why it is here |
|---|---|---|---|---|
| 1 | `fade` @ 1min | `ONH` × `SMA_50_5min` | 80/80 | The reference configuration, short window |
| 2 | `touch` | `pdHigh` × `EMA_9_1min` | 40/80 | Other entry, other bracket |
| 3 | `break` | `OR_High` × `VWAP_rolling_30min` | 20/60 | Other anchor family |
| 4 | `continuation` | `LondonHigh` × `Pivot_5m_High` | 80/40 | Approach-side twin of fade, asymmetric bracket |
| 5 | `3c` | `ONL` × `SMA_200_1min` | 60/60 | Different signal machinery. Policy `legacy` |
| 6 | `fade`, UTC `[2024-08-01, 2024-08-04)` | `ONH` × `SMA_200_30min` | 80/80 | 0 trades. Three UTC days are fewer than 200 thirty-minute bars, so `SMA_200_30min` stays NaN and `anchor_rules` emits no candidate. Random fields stay null |

If cell 6 produces any trade, the slice is wrong. Do not record it as the 0-trade golden. Do not change tolerance, the pair, or the policy to force a zero.

Plus the full reference cell named in §1, on the full CSV. Known **59 trades, E=0.0805**. Run it on Linux and on macOS. It is too slow for CI. The operator script runs it once per platform before the flag may become the operator default. CI runs a committed synthetic multi-day 15-second fixture that exercises prepare and one replica loop, plus the shape of cell 6.

### 9.3 Files

- New suite under `tests/fixtures/memory_parity/` (do not put MW bytes into the legacy golden directory). Include `tests/fixtures/memory_parity/README.md` stating that the legacy set is not rewritten.
- A recorder script, explicit regenerate flag, default is compare-only.
- An operator script that slices the farm CSV on the UTC bounds in §9.2 and runs the six short cells plus, when asked, the full cell.
- A short pointer in `docs/ENGINEERING_PROPOSAL.md` §4.1. That is the place `test_existing_golden_files_byte_identical` names for new golden docs. **Do not edit** `tests/fixtures/golden/README.md`. The test byte-locks every file that already exists under `tests/fixtures/golden/`, including that README (B-1). An MW0 PR that touches it fails the suite.
- This plan's status line, updated when MW0 lands.

### 9.4 Acceptance

- The §9 pre-step passed on Linux: the full reference cell on the MW1 branch commit matches the `59a4652` trades and `replica_expectancies` bits (59 trades, E=0.0805).
- Recorder at that same commit is deterministic on the synthetic fixture across two runs (canonical hash equal).
- Compare mode fails if any trade field, replica float, DA5 field, or canonical hash differs.
- Existing pytest suite stays green. No product behavior change, so no new runtime flag in MW0.

---

## 10. MW1 — Array context, one slot per cell

**Depends on:** §8 decision is "MW1 → MW2 as planned" or "MW-L after MW1". If the decision is "MW-L before MW1", do §12 first and rerun §8. Also depends on MW0 outputs existing.

**Goal:** delete the per-minute DataFrame map. Keep one read-only OHLC array plus an integer offset table. Build it once per cell. Reuse it for the load-time validation, the backtest, and the 50 replicas. Clear it before the worker accepts another cell.

**Non-goals:** do not edit `resolve_subtimeframe_bar`. Do not edit `vs_random_benchmark`'s loop or seeds. Do not change levels, signals, or fills. Do not share the array across cells. Do not add a CLI flag. Do not change `hash_dataframe` inputs. MW2's copy removal is not in this PR. MW-L is not in this PR unless §8 put the loader first, in which case MW-L has already landed.

### 10.1 Behavior

When the flag is off, `prepare_subtimeframe_context` and `prepare_subtimeframe_conservative_context` stay on the current dict-of-frames path: the existing function body, not a second implementation that is supposed to match it. No cache object is created. `groups` stays a `dict`. `tests/test_intrabar.py` compares that dict.

When the flag is on, every caller of those two functions uses the array storage below, including `data_subtimeframe_page_helpers.py` and CLI `run_batch`. The study slot (§10.2) is the only cache. Callers outside `execute_study_cell` build one array context per prepare call and do not keep it.

- Prepare validates with the same predicates (duplicate timestamps, monotonicity, expected sub-bar count, alignment, finite OHLC, parent/sub reconcile within `tick_size * 1e-6`). The same errors are raised. The same fallback reasons are stored for the conservative model. `_REQUIRED_OHLC` is `timestamp`, `open`, `high`, `low`, `close`. Prepare does not read `volume` or `session`.
- Storage is three pieces, and not a float64 OHLC block alone:
  - `open` / `high` / `low` / `close` as one `float64` array, shape `(n_sub_bars, 4)`, same bits as the source frame.
  - `timestamp` as a timezone-aware `datetime64[ns]` array, same timezone and values as the source column. `resolve_subtimeframe_bar` reads `sub_bar["timestamp"]` and the trade column `exit_subbar_timestamp` is `pd.Timestamp` of that value. Omitting it changes the trade frame and `canonical_bundle_hash`.
  - An `int64` start offset and an `int32` count per parent bar. Fallback parent indexes are absent from the mapping. This file's offsets fit in `int32`; the contract is still `int64` so a longer source cannot wrap.
- Do not cache `volume` or `session`. The current `.copy()` keeps them because it slices the whole source row. The walker never reads them. A per-sub-bar string `session` column would put back the RSS this PR removes.
- `SubtimeframeContext.groups` remains a mapping. `__getitem__` and `.get` build **one** frame for that parent index and the caller discards it after `resolve_subtimeframe_bar` returns. The frame is not stored. Its columns are exactly `timestamp`, `open`, `high`, `low`, `close`. OHLC dtypes are `float64`. The timestamp dtype matches the source, including timezone. The index is a `RangeIndex` starting at 0 with length equal to the count (4 on a complete 15-second minute). Missing keys raise `KeyError` on `__getitem__` and return `None` on `.get`, same as `dict`. `__len__` and iteration follow the parent indexes that have a group.
- Flag-on parity against flag-off is timestamp, OHLC, that index, those dtypes, and the fallback reason strings. It is not "every column of the old copy".
- The strict model (`prepare_subtimeframe_context`) uses the same storage behind the same flag, so a later `intrabar_model: subtimeframe` cell does not keep the old map. Program B uses conservative. Both are in this PR because they share the dict-of-frames shape.

### 10.2 Cache slot

A worker runs more than one cell (§5). The slot is therefore not keyed by `id()`, `id(frame)`, or any address.

**Single slot**, not a growing dict. One entry. Replaced when the key differs. Deleted in a `finally`.

**Key**, SHA-256 of canonical JSON, computed inside prepare from the frames and intervals it already receives. Prepare cannot see instrument, source timezone, or exchange timezone, so the key does not call `DataIdentity`.

- Order-sensitive digest of the parent columns `timestamp`, `open`, `high`, `low`, `close`, in row order, including `str(dtype)`. Do not sort first.
- Order-sensitive digest of the same five columns on the subtimeframe frame, in row order. Do not include `volume`. Prepare does not read it. The 15-second frame is not inside `DataIdentity`. A parent-only key is wrong.
- `str(parent_interval)`, `str(sub_interval)`, `repr(float(tick_size))` using the same float that prepare already uses, and the model name: `subtimeframe` or `subtimeframe_conservative`.

`LevelsIdentity` is not part of the key. The context does not read level columns.

Do **not** use `DataIdentity.dataset_id()` or `hash_dataframe` as this key.

- `dataset_id()` hashes the whole frame through `hash_dataframe`, then mixes in instrument, base interval, and the two timezones. The load-time parent is OHLCV plus `session`. The backtest parent is the levels frame: `compute_all_levels` joins level columns onto the copy `compute_session_levels` sorts by timestamp. Those two dataset ids differ, so a `dataset_id` key misses on the real backtest and the 50 replicas rebuild or, worse, share a context built for a different column set. The earlier sentence that said this key makes the backtest hit the load-time slot was wrong.
- `hash_dataframe` sorts by timestamp before hashing (`_canonicalize_dataframe` in `thesistester/persistence/local_store.py`). Groups are indexed by row position (`groups[bar_index]` in `sim_core.py`). An order-insensitive hash can hit across a permuted frame and attach the wrong sub-bars to a parent index. That changes fills and `exit_subbar_timestamp`.

A hit requires the order-sensitive digests to match. The load-time parent and the levels frame hit only when timestamp and OHLC bits and row order match. Prepare already rejects a non-monotonic parent, and `compute_session_levels` sorts by timestamp, so a levels frame built from that parent matches when the OHLC bits match. A mismatch misses and rebuilds. That rebuild is correct. Do not force the hit. Publish the slot only after prepare returns. A raise must not leave a partial entry.

**Lifetime:** `execute_study_cell` enters the slot at the start of the `try` and clears it in `finally`, including on exception, before the function returns. That is the latest legal clear. The next task in that process starts empty. The load-time prepare, `simulate_trades`, and the 50 replicas all run inside that one call, so they share the slot.

`run_experiment` and CLI `_execute_run` do **not** enter the slot. They keep a per-call build (the array build when the flag is on, the dict build when it is off). That is deliberate: a module-global cache that is always on would leak across CLI batch tasks. The lookup inside prepare is a no-op unless the slot is active.

**Lookup.** Every prepare call while the slot is active computes this content key and compares it to the key stored in the slot. That is the load-time call, the `simulate_trades` call, and all 50 replica calls. A hit reuses the array. A miss replaces the slot. There is no second lookup and no "already filled, skip the hash" path.

Object identity is rejected. `id(df)`, the `id` of a column, a cached pointer, and any address are not the key and are not a hint that skips the hash. The parent object used at load time and the levels frame are different objects. An identity check misses. The order-sensitive OHLC digest is what makes the backtest and the replicas hit the slot built during load, and only when the bits match. Load is inside `execute_study_cell`, so the slot is active for that first build.

**Hash cost, measured on a different function.** `hash_dataframe` on synthetic 7-column frames (timestamp, OHLC, volume, session), real function, this investigation machine: **0.133 µs/row** at 725,880 rows (0.096 s) and **0.130 µs/row** at 1,451,760 rows. The slope is flat from 20k rows up. That function is **not** the slot key. It sorts, it hashes every column, and on the levels frame it would hash about 70 columns, so the old "0.5 s per prepare, 25 s per cell" figure is neither the key's cost nor a safe thing to call here. The slot digest is five columns, unsorted. Treat 25 s as a loose upper bound only. One dict-of-frames rebuild is minutes (~475 µs per complete minute). Re-time the real key on the farm only if the §14 wall-clock gate (≤ 105% of flag off) is within a minute of failing. On a 3.2–4.2 h cell, even the loose bound is inside that margin.

### 10.3 Files

- `thesistester/engine/intrabar.py` — both prepare functions, `SubtimeframeContext` storage, the lazy mapping, the slot.
- `thesistester/study/execute.py` — enter/clear the slot around `execute_study_cell` only.
- Tests named in §10.4.
- Docs: `docs/ARCHITECTURE.md` (worker memory and the flag), `docs/ASSUMPTIONS_AND_LIMITATIONS.md` (resource note: flag off is the default; 16 workers are not claimed yet), `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` (do not raise workers on this flag until §14), `docs/ENGINEERING_ROADMAP.md` (one status row; §4.2). This plan's status line.

Do not edit `thesistester/engine/sim_core.py`, `resolve_subtimeframe_bar`, `thesistester/analytics/overfitting.py`, or `thesistester/engine/backtest.py` except if a call site must pass an already-built context. Prefer the slot inside prepare so `backtest.py` and `overfitting.py` stay unchanged. If a call-site edit turns out to be required, it still must not change the walker and it must be a default-off branch.

### 10.4 Tests

1. **Group parity.** On a synthetic multi-day 15-second frame with some complete minutes and some sparse minutes, every group's `timestamp`, `open`, `high`, `low`, `close`, index, and dtypes of those columns from the flag-on mapping equal the flag-off prepare. Fallback reason strings equal. The same OHLC mismatch still raises, with the same error type. `volume` and `session` are not part of this equality. A second frame with the same rows in a different order must not reuse the first frame's groups.
2. **Trade parity.** `simulate_trades` on that frame, flag on vs flag off, bit-identical trades, including a `subtimeframe_conservative` run with slippage, commission, and flatten 16:00 `America/New_York`.
3. **Replica parity.** `vs_random_benchmark` with `n_replicas=50` and `random_state=42`, flag on vs flag off: `replica_expectancies` bit-identical and in the same order. This is the proof the slot did not consume or reorder draws.
4. **Two cells, one process.** Call `execute_study_cell` for cell A, then cell B, flag on, in one process. A and B use different OHLC (different prices, same shape) so a stale context changes fills. In a fresh process, run only B. B's trades, ordered `replica_expectancies`, and `canonical_bundle_hash` are bit-identical to the fresh run. This is the test that fails if the slot is keyed by `id()` or is not cleared.
5. **Flag off regression.** With the variable unset, the two-cell test still matches a pre-MW1 run of B on the synthetic fixture (MW0 synthetic golden).
6. **MW0 short cells**, flag on vs the recorded flag-off outputs, on the farm script. CI runs the synthetic subset.

### 10.5 Why this cannot change a result

The walker reads the same timestamp and OHLC in the same order, so `exit_subbar_timestamp` does not move. Validation raises on the same rows. The RNG stream is not touched. The slot cannot outlive the cell, and a failed prepare does not publish it. The flag-off path is the current code.

### 10.6 Savings and acceptance

- Expected RSS: the §8.2 MW1 band, `[R_signals, R_signals + 0.4 GiB]`. The 3.4–4.6 GiB figure is only the §6 planning estimate. Reject MW1's savings claim outside the §8.2 reject rule.
- Expected speed: a large drop, because the 52 map builds are most of the 4 h. The acceptance bar is only "not more than 5% slower." A slower result blocks the flag.
- Existing tests green. MW0 synthetic compare green with the flag on and with it off.
- Revert: unset the variable. The new code remains, unused.

---

## 11. MW2 — Full-width copies, hash-identical

**Depends on:** MW1 landed and its farm RSS is inside the §8.2 MW1 band (or the band was explicitly revised in this file). MW0 outputs exist.

**Goal:** remove the private copies that still sit on top of the array context, without moving `canonical_bundle_hash`.

**Non-goals:** do not drop level columns from the emitted levels frame. Do not change dtypes. Do not skip naked-flag computation when the bundle still contains `naked_flags.parquet`. Do not recompute finished cells. Do not null DA5 on resume.

### 11.1 What the code actually decides

Verified against the study, journal, and assistant paths. This section is the contract. The earlier note that "the bundle hash is informational" is **withdrawn**.

`hash_dataframe` (`thesistester/persistence/local_store.py`) sorts by `timestamp` when that column exists, then hashes column names, `str(dtype)` for every column, and `pd.util.hash_pandas_object`. A dtype change or a column change changes the hash even when the float values look the same. A pure row reorder does not. That is why §10.2 refuses it as the context-slot key: the slot is positional, and this hash is not. MW2 still has to keep this function's output identical on every frame the bundle and the levels artifact store.

`canonical_bundle_hash` (`thesistester/research_bundle.py`) hashes logical contents. Each `.parquet` member is loaded and passed through `hash_dataframe`. JSON members are normalized with sorted keys. Manifest `created_at` is removed. `cache_provenance` is in the `clear_only` bundle section with `hashed=False`, so it is not part of the hash. Raw zip bytes and raw parquet bytes are not the digest.

| Reader | What it uses | Is it a decision? |
|---|---|---|
| `cells_to_run` in `thesistester/study/ledger.py` | `status == "ok"` and `output_dir / bundle_path` is a file | **Yes.** Skip vs re-run. Bytes and hash are not read |
| Ledger cell record | `status`, `started_at`, `finished_at`, `error`, `bundle_path` | No hash field. Resume copies the record and rewrites only cells in the todo list |
| `results_index.csv` column `bundle_hash` | `canonical_bundle_hash` at write time. Recomputed from the zip only when an index row is missing and `_index_row_from_existing_bundle` rebuilds it | Stored. Not a skip test. A changed hash changes the column |
| DA5 columns on that index | Written by `random_baseline_fields` after the bundle. Not inside the zip (`replica_expectancies` is not persisted) | Resume **keeps** an existing index row, including DA5. DA5 becomes null only if the row is missing and is rebuilt from the zip. MW2 must not take that rebuild path for a cell that already has a row |
| Journal `load_named_cell` | `canonical_bundle_hash` vs the expected `bundle_hash` | **Yes.** Mismatch raises `JournalIngestError` |
| Assistant `require_run_bundle_hash` and the orchestrator | Same canonical hash vs provenance | **Yes.** Mismatch refuses the run. A match can reuse a completed run |
| Study report / viewer | Index column and zip members | Display and ranking. No skip |
| Execution-artifact cache | `hash_dataframe` of the parent and of the levels frame | **Yes.** Mismatch is a cache miss, not a study-cell skip |
| `cache_outcome` / `cache_provenance` | Outcome string on the index. Provenance is unhashed | Not a skip test. MW2 does not change the string |

Nothing in the study resume path compares raw parquet bytes. Two runs already differ in zip bytes because of `created_at`. Equality is `canonical_bundle_hash`, which follows `hash_dataframe`.

### 11.2 Behavior

Flag off: `flag_naked_levels`, `_prepare_trigger_dataframe`, and the post-bundle lifetime of `state` stay as they are.

Flag on:

- `flag_naked_levels` still **returns** a frame that `hash_dataframe`s equal to today's return (all original columns, same dtypes, plus the naked bools). It must not keep a second full-width copy alive for the rest of the cell if the bundle writer can receive the frame and then drop it. If the only way to build that frame is one temporary copy, the copy ends when `build_research_bundle` returns.
- `_prepare_trigger_dataframe`, for a trigger timeframe that does not resample (the smoke cell's `1min` on a 1-minute parent), must not deep-copy every level column into a long-lived object. The signal frame that is actually written still `hash_dataframe`s equal to the flag-off signals frame.
- After `build_research_bundle` returns inside `execute_study_cell`, and after `build_index_row_from_state` has hashed those zip bytes, release `naked_flags`, confluence zones, signals, and the wide levels frame **before** `random_baseline_fields`. Do not drop `trades` or `subtimeframe_data`. `_cell_bars` today prefers `levels`, and the cell backtest used that frame. The flag-on path passes a projection of **that** frame, not a different object, with columns `timestamp`, `open`, `high`, `low`, `close` only. Same length, same row order, same timestamp values, and the same OHLC bits. `random_entry_signals` draws bar indexes from `len(df) - 1`, so a shorter frame changes `replica_expectancies` even when the remaining prices match. `simulate_trades` reads `timestamp` for the flatten clock and prepare reads it as a required column. Without it, prepare raises, `random_baseline_fields` swallows the exception and returns null DA5, and bit parity fails. Do not substitute `state["data"]` unless its timestamp and OHLC bits equal the levels frame. `volume` and the level columns are not passed. The 15-second frame is passed unchanged. Because the MW1 key is the order-sensitive timestamp-plus-OHLC digest, the replica prepares hit the slot built for the backtest. Do this only after the bundle bytes are in hand, so the zip is already fixed.
- Do not delete or rewrite an existing zip during resume. `cells_to_run` already skips `ok` cells whose file exists. MW2 does not touch that function's predicate.

### 11.3 Files

- `thesistester/engine/naked.py`
- `thesistester/engine/signals.py` (`_prepare_trigger_dataframe` and the 1-minute path only; do not retune trigger rules)
- `thesistester/study/execute.py` (release after the bundle is built, before `random_baseline_fields`; the MW1 slot `finally` still clears the context)
- Tests in §11.4
- The same three docs as MW1, updated with the measured MW2 RSS once the farm run exists. Until then, the docs say the gate is still closed.

Do not edit ledger format, `cells_to_run`, study naming, or `hash_dataframe` itself.

### 11.4 Tests

1. **Frame hash.** Flag on vs flag off, same inputs: `hash_dataframe` equal for levels (unchanged in this PR, asserted so a drive-by edit fails), naked flags, signals, and trades. `canonical_bundle_hash` equal.
2. **MW0 suite**, flag on, full equality including the canonical hash.
3. **Resume.** Write a two-cell study flag off. Stop after cell 1 is `ok` and cell 2 is `pending`. Record cell 1's ledger dict, the zip bytes, and the index row including DA5. Resume flag on.
   - Cell 1's ledger dict is equal, including timestamps.
   - Cell 1's zip bytes are equal.
   - Cell 1 is absent from the todo list (not recomputed).
   - Cell 2 is executed once (not skipped).
   - Cell 2's trades, DA5 fields, and `canonical_bundle_hash` match a flag-off run of cell 2 alone.
   - Cell 2's `started_at` / `finished_at` are present and are **not** compared to the flag-off run.
4. **Mixed study.** Cells 1 flag off and cell 2 flag on match an all-flag-off study on the equality set in §3. This can be the same fixture as test 3.
5. **Cache miss safety.** A levels artifact written flag on still verifies under `hash_dataframe` against the flag-off levels frame. `cache_outcome` for a warm store stays `levels_hit` / `data_hit` as it does flag off. The MW flag does not appear in that string.

### 11.5 Why this cannot change a result

The written frames hash the same, so the canonical bundle hash, journal check, assistant check, and artifact cache see the same identity. Resume still keys off file existence. The replica loop still draws in the same order; it only loses its grip on columns it does not read. The walker is still untouched.

### 11.6 Savings and acceptance

- Expected RSS: the §8.2 MW2 rule. The 2.4–3.4 GiB figure is only the §6 planning estimate. A farm peak above **3.6 GiB**, or a peak that did not fall at least 0.4 GiB under `R_signals`, rejects the claim and blocks 16 workers.
- Sixteen workers become legal only after §14, and only if the smoke peak is ≤ 3.3 GiB.
- Speed still ≤ 105% of flag off.
- Revert: unset the variable.

---

## 12. MW-L — Loader residency (conditional)

**Depends on:** the §8 rule that names this PR. It is not on the default critical path.

**Goal:** after `_load_15s_primary_experiment_data` returns, the Quantower `StringIO` re-parse and the raw profile frame are not still the multi-GiB resident set.

**Non-goals:** do not change canonical column values, timestamp timezone rules, DST handling, duplicate-15s resolution, or derivation policy `observed_aligned_15s_to_1m_v2`. Do not change `format_profile` behavior for profiles other than the one the farm file uses unless the same `hash_dataframe` proof covers them. The comment in `load_ohlcv` about mixed `-04:00`/`-05:00` offsets is a behavior lock: whatever replaces `to_csv` + `StringIO` must keep that UTC normalization.

### 12.1 Behavior

The current non-canonical branch builds `canonical_input`, stringifies timestamps, and calls `load_ohlcv` on `io.StringIO(canonical_input.to_csv(...))`. MW-L removes that text round-trip only behind the MW flag, unless a flag-off implementation is proven `hash_dataframe`-identical on the MW0 parent and source frames, in which case it may be unconditional. Prefer the flag if the proof is only on MNQ 15-second files.

`hash_dataframe` of the returned canonical parent, and of the 15-second source after `prepare_15s_source_for_derivation`, must match the flag-off frames on the MW0 short window and on the synthetic fixture.

### 12.2 Files

- `thesistester/data/loader.py` (the non-canonical re-entry only)
- A test that the parent and source hashes match
- No study, ledger, or bundle-schema edits

### 12.3 Acceptance

- Re-run §8 after MW-L. `R_load` must fall below 2.0 GiB or the PR does not count.
- MW0 hashes still match.
- If this PR landed **before** MW1 because `R_load ≥ 4.0 GiB` and `map_step < 0.5 GiB`, the new trace is what allows MW1 to start.

---

## 13. MW3 — Read-only memmap (optional)

**Depends on:** MW2 farm peak known. Do this only if unique machine RAM is still tight after MW2, or if 16 workers re-parsing the CSV dominates startup. Skip it if §14 already passes at 16 workers.

**Goal:** one on-disk float64 copy of the parent, the 15-second source, and the levels frame, opened read-only by each worker.

**Non-goals:** do not delete the parquet artifact cache. The flag-off path still uses parquet. Do not use `multiprocessing.shared_memory`. Do not switch the pool to `fork`. Do not expect per-process RSS to drop by the file size: Linux counts a shared mapping in every process's RSS. The §14 gate uses `MemAvailable`, not `N × RSS`, once this PR exists.

### 13.1 Behavior

Publish `parent.npy`, `source.npy`, and `levels.npy` (plus a small sidecar for the timestamp and the string `session` column) beside the existing artifacts. Names are the existing `data_artifact_key` / `levels_artifact_key` plus a fixed suffix. Open with `mmap_mode="r"` and `writeable=False`. Accept the mapping only when `hash_dataframe` of the mapped values equals the identity already stored for that artifact. A miss or a mismatch deletes the stale npy and rebuilds it. A crashing worker cannot write the file.

The sidecar for timestamps and `session` must round-trip to the same `hash_dataframe` as the parquet frame. If that cannot be done without a dtype change, do not ship MW3.

### 13.2 Files

- `thesistester/persistence/execution_artifacts.py` and `execution_artifact_ops.py` (publish/verify only; additive files)
- `thesistester/api.py` load path, flag on, after the parquet identity check succeeds
- Tests: hash match, stale file rejected, flag off never opens the npy
- Docs: the gate formula in the runbook gains the `MemAvailable` sentence from §14

### 13.3 Acceptance

- Flag-off behavior unchanged (parquet only).
- Flag-on `canonical_bundle_hash` still matches MW0.
- A tampered npy is a miss, not a silent read.
- Unique RAM (`MemAvailable` drop) falls by about `(workers − 1)` times the mapped resident size. Per-worker RSS may not fall. That is expected. Do not "fix" it by multiplying RSS.

---

## 14. Farm rollout and the worker gate

The gate script is **not in this repository**. Change it only after the measurements below. Do not hard-code 6.5 GiB anymore once a flag-on number exists.

Order:

1. **§9 pre-step**, on the commit MW1 will branch from, flag off, Linux, one process. The full reference cell equals the `59a4652` trades and `replica_expectancies` bits (59 trades, E=0.0805). A miss stops the series. Do not record MW0 and do not run the §8 trace as a substitute for this step.
2. **§8 trace and MW0**, both on that same commit, only after step 1 passes. The trace is flag off, full CSV, one process. Record `R_load`, `R_signals`, `R_ctx`, `R_done`, and `map_step` in the MW1 PR. MW0 may be recorded in parallel with the trace. The trace does not block MW0. MW0 does not block the trace. Both block MW1.
3. **MW1** (or MW-L first if §8.1 rule 1 says so). Parity: short suite, flag off vs on, Linux then macOS. Exact equality, including `canonical_bundle_hash` and `exit_subbar_timestamp`. Then the full reference cell, both machines, both flag states. Only a match allows `THESISTESTER_MEMORY_PATH=array` on the farm. The farm RSS must sit in the §8.2 MW1 band.
4. **Speed**, same full cell, both flags. Wall time ≤ 105% of flag off. Expect a large drop. A slower result blocks the flag.
5. **MW-L between MW1 and MW2** only if §8.1 rule 2 inserted it. Rule 1 already ran it before MW1, at step 3. Re-trace, then re-apply §8.1 before MW2.
6. **MW2.** Repeat the short-suite parity and the resume test on the farm. Then the full reference cell again if MW2 could touch OHLC bytes passed into `simulate_trades` (it can). Both machines.
7. **Capacity**, flag on, after parity. One smoke cell, then a real multi-cell study, at **6, 12, and 16** workers. Record per-worker peak RSS, minimum `MemAvailable`, and cells/hour.
   - Pass: minimum `MemAvailable` during the 16-worker run stays above **4 GiB**, and no worker RSS exceeds **3.3 GiB**. Sixteen workers at that cap are `16 × 3.3 GiB = 52.8 GiB`, inside ~59 GiB usable.
   - If worker RSS is over 3.3 GiB, keep the gate at the measured fit. Do not turn on MW3 just to satisfy an `N × RSS` formula.
8. **MW3** only under §13. Repeat the 16-worker run. Budget with the drop in `MemAvailable`. Quote per-worker RSS as a leak check, not as the capacity number.

**Gate formula** after MW2, before MW3:

```text
workers = min(16, floor((MemAvailable_at_idle_GiB − 4) / smoke_peak_RSS_GiB))
```

Use the **flag-on** smoke peak. Leave at least 4 GiB for the OS. Sixteen workers is one process per core. SMT is not required; each cell is single-threaded.

After MW3, if mappings are shared, stop using `N × smoke RSS` as the capacity ceiling. Use idle `MemAvailable` minus 4 GiB, divided by the **private** RSS (smoke RSS minus the mapped file's resident size, measured once). If that private number cannot be measured cleanly, stay on the MW2 formula. A shared mapping that is still counted 16 times will refuse a run that actually fits.

**Farm commit.** The farm may move off `59a4652` onto the MW1 branch commit only between studies, or after the §9 equality pre-step has been shown. It must not move in the middle of a study, and it must not move before that equality is on record.

---

## 15. PR sequence (locked)

| Step | ID | Ships runtime code? | Blocks |
|---|---|---|---|
| Equality pre-step §9 | — | No | The §8 trace, MW0, and every later step. A miss stops the series |
| Operator trace §8 | — | No | MW1, MW-L, MW2. Does not block MW0. May run in parallel with MW0 after the pre-step |
| Golden capture | MW0 | No (fixtures and scripts only) | Every later MW PR's parity test. Does not block the trace |
| Array context | MW1 | Yes, flag default off | MW2 |
| Loader, only if §8.1 says so | MW-L | Yes | The next step named by §8.1 |
| Full-width copies | MW2 | Yes, same flag | The 16-worker gate |
| Memmap | MW3 | Yes, same flag, optional | Nothing, if §14 already passes |

Each implementation PR:

- States which §8 branch it is on.
- Points at the MW0 outputs it matched.
- Says how to revert (unset `THESISTESTER_MEMORY_PATH`).
- Updates the docs named for that step in §16. Runtime PRs also update `ENGINEERING_ROADMAP.md` with a status row (§4.2). MW0 does not edit `tests/fixtures/golden/README.md`.
- Does not regenerate the legacy golden set.
- Does not edit `resolve_subtimeframe_bar`, `SeedSequence` usage, study naming, ledger keys, or CLI arguments.

The PR that adds **this file** is not MW0. It adds the plan and one index row in `docs/README.md`. No runtime code.

---

## 16. Docs each implementation PR touches

| PR | Docs |
|---|---|
| MW0 | `tests/fixtures/memory_parity/README.md`, a short pointer in `ENGINEERING_PROPOSAL.md` §4.1, and this file's status line. Not `tests/fixtures/golden/README.md` |
| MW1 | `ARCHITECTURE.md`, `ASSUMPTIONS_AND_LIMITATIONS.md`, `PROGRAM_B_OPERATOR_RUNBOOK.md`, a status row in `ENGINEERING_ROADMAP.md` (§4.2), this file's status line. Include the §8 numbers |
| MW-L | `ASSUMPTIONS_AND_LIMITATIONS.md` only if the loader's resident set is now a documented limit. This file's status line |
| MW2 | The same docs as MW1, with the measured peak, including the roadmap status row. This file's status line. Do not tell operators to run 16 workers until §14 passes |
| MW3 | Runbook gate formula. `ARCHITECTURE.md` one paragraph on the read-only files |

`ENGINEERING_ROADMAP.md` gets a status row only when an implementation PR lands, not in the plan PR.
