# CAI-0 Cold-Path Baseline

## Purpose

This is the informational baseline for Classic/Assistant Integration milestone
`CAI-0`. It freezes the current headless cold path before artifact reuse is
introduced:

```text
CSV path → load_dataset → compute_levels → generate_signals → run_backtest
         → build_research_bundle
```

Wall times are **not** a CI pass/fail threshold. They vary with hardware,
Python, and package versions. Correctness continues to rely on existing
API/CLI/Assistant canonical-hash parity and golden-master gates.

## Recording policy decision (CAI-0)

Initial classic-to-thesis attachment uses **manual record-after-run**:

- Exploration on classic pages remains untracked by default.
- After a completed Backtest, the user explicitly chooses
  **Record and discuss this run** (CAI-6:
  `AssistantOrchestrator.register_external_bundle_run`).
- Opt-in `all_executions` ledger recording (CAI-7:
  `thesistester/classic_ledger.py`) persists every Backtest attempt under an
  active thesis — including failed and cancelled terminals.

## Fixtures and commands

| Fixture | Bars | Levels intent | Use |
|---|---:|---|---|
| `small` | 60 | Cheap RTH hour; no rolling POC | CI smoke + exhaustive harness structure |
| `realistic` | 780 | Two RTH sessions; tick-gated `poc_windows=[]` | Informational benchmark only |

`--fixture both` / `--fixture realistic` run on the tick-gated path. The
harness calls `compute_levels` only after `disable_unneeded_tick_families`
on named setup tokens (selected / anchor / rules). Do not revive
typical-price `_rolling_poc`. The recorded tables below are the CAI-0
typical-price snapshot; **F-10** re-records them on this path (QI-14-01 /
QI-14-02).

Source of truth:

- Fixtures: `tests/fixtures/cai_baseline.py`
- Harness: `tests/benchmarks/cai_cold_path.py`
- Smoke tests: `tests/benchmarks/test_cai_cold_path.py`

Commands:

```bash
# Informational baseline (small + realistic)
python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5

# CI smoke: small + realistic harness structure (via pytest)
python3 -m pytest tests/benchmarks/test_cai_cold_path.py -q
```

Established API/CLI/Assistant parity remains:

```bash
python3 -m pytest tests/test_assistant_execution_parity.py -q
```

## Recorded baseline

Recorded on the CAI-0 implementation environment: CPython 3.12.3, pandas 3.0.5,
NumPy 2.4.4, Linux 6.12. One warmup plus five `time.perf_counter()` repetitions
per stage; median and nearest-rank p95.

### Small fixture (60 bars, no rolling POC)

| Stage | Median ms | P95 ms |
|---|---:|---:|
| `load_dataset` | 6.984 | 6.990 |
| `compute_levels` | 95.309 | 95.338 |
| `generate_signals` | 24.440 | 24.504 |
| `run_backtest` | 17.638 | 17.652 |
| `build_research_bundle` | 17.006 | 17.026 |
| `run_experiment_end_to_end` | 149.799 | 151.222 |

### Realistic fixture (780 bars; CAI-0 table used typical-price rolling POC `30min`)

| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|---:|
| `load_dataset` | 12.573 | 12.666 | 0.7% |
| `compute_levels` | 1293.267 | 1294.099 | 70.9% |
| `generate_signals` | 322.610 | 332.232 | 17.7% |
| `run_backtest` | 156.016 | 156.043 | 8.6% |
| `build_research_bundle` | 35.205 | 35.511 | 1.9% |
| `run_experiment_end_to_end` | 1824.623 | 1843.264 | 100% |

## Interpretation for later milestones

1. On the CAI-0 typical-price snapshot, **levels dominate** cold recomputation.
   The current tick-gated path is signal-dominated (QI-14 §9.3). F-10
   re-records; do not treat the table above as the live envelope.
2. CSV reload itself is currently cheap relative to levels; source-content
   identity checks remain mandatory even if parse time is small.
3. Signal generation can be non-trivial once confluence density is high. Signal
   caching stays deferred until after levels-cache impact is measured
   (CAI-10 decision).
4. Any warm-path optimization must prove equal canonical bundle hashes against
   this cold path; timing improvements alone are never acceptance criteria.

## CAI-10 warm-path measurement and signal-cache decision

Harness: `tests/benchmarks/cai_warm_path.py` (smoke:
`tests/benchmarks/test_cai_warm_path.py`).

**Decision (CAI-10):** do **not** add a second signal-artifact cache layer yet.

Rationale:

- The CAI-0 table above still shows levels ~71% of e2e (typical-price rolling
  POC). That path is gone. Current tick-gated realistic is signal-dominated
  (QI-14 §9.3). CAI-3 data/levels reuse stays the first cache surface until
  F-10 re-records; CAI-10 still says no second signal cache yet.
- Warm-path harness proves cold↔warm canonical bundle-hash equality and reports
  end-to-end speedup informationally. A signal second layer is warranted only
  after warm runs still show a large `generate_signals` share once levels hits
  are routine.
- Recommendation string from the harness:
  `measure_warm_signal_share_before_second_layer` (or
  `prioritize_levels_cache_effectiveness_first` when warm is not yet clearly
  faster). Neither is a CI gate.

Retention/ops for the existing levels/data cache land in
`thesistester/persistence/execution_artifacts.py` (inspect/evict/rebind) and
must never auto-delete user snapshots, bundles, or thesis records.

## C-15 `iterrows` replacement (QI-14-05)

C-15 replaces `iterrows` with column arrays / `iloc` behind the C-14
`generate_signals` helpers (`_index_trigger_rows_by_base_end`, zone-naked
admission, 3c HTF `trigger_bar_index → base_end` map via
`_index_base_end_by_trigger_bar`, and `_project_zones_to_trigger_df`).
Empty trigger frames stay an empty map (no column access). Nullable
dtypes were **not** changed;
`generate_signals` hashes stay identical to C-14. Timing below is
informational on this image (CPython 3.12.3, tick-gated realistic,
`--repeats 5`). It does **not** replace the CAI-0 historical table above.

| Stage | Before (C-14 / `#561`) median ms | After (C-15) median ms |
|---|---:|---:|
| `generate_signals` | 331.765 | 352.338 |
| `run_experiment_end_to_end` | 756.672 | 748.973 |

F-10 still re-records the live envelope. Do not treat these rows as a CI gate.

## DEFAULT merge (H4 / QI-14-04)

Omitted levels-family keys still merge product DEFAULT (`omit` ⇒ on).
`cai_levels_config()` is an explicit fixture override, not a flip of that
merge. Do not treat a missing key as disabled.

## Non-goals of CAI-0

- No production cache read/write.
- No Assistant or classic UI behavior change.
- No golden-master regeneration.
- No CI performance threshold.
