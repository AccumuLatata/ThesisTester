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
typical-price `_rolling_poc`. The recorded tables below are the F-10
tick-gated snapshot from `--fixture both --repeats 5` (QI-14-02 /
QI-14-07). The retired CAI-0 typical-price `compute_levels` ~71% share
is not the live envelope.

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

Recorded on the F-10 environment: CPython 3.12.3, pandas 3.0.5, NumPy 2.5.3,
Linux 6.12. Command: `python3 -m tests.benchmarks.cai_cold_path --fixture both
--repeats 5`. One warmup plus five `time.perf_counter()` repetitions per
stage; median and nearest-rank p95. Isolated-stage shares are
`stage_median / e2e_median` and need not sum to 100%. Wall times are
informational (not a CI gate).

### Small fixture (60 bars, no rolling POC)

| Stage | Median ms | P95 ms |
|---|---:|---:|
| `load_dataset` | 7.124 | 7.580 |
| `compute_levels` | 108.453 | 108.673 |
| `generate_signals` | 25.848 | 25.888 |
| `run_backtest` | 18.720 | 19.017 |
| `build_research_bundle` | 56.811 | 56.959 |
| `run_experiment_end_to_end` | 167.811 | 167.834 |

### Realistic fixture (780 bars; tick-gated `poc_windows=[]`)

| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|---:|
| `load_dataset` | 12.768 | 12.802 | 1.7% |
| `compute_levels` | 196.582 | 197.351 | 26.1% |
| `generate_signals` | 344.582 | 362.596 | 45.7% |
| `run_backtest` | 167.712 | 184.815 | 22.3% |
| `build_research_bundle` | 75.566 | 76.358 | 10.0% |
| `run_experiment_end_to_end` | 753.330 | 757.082 | 100% |

## Interpretation for later milestones

1. On the live tick-gated table, **signals dominate** isolated-stage share
   (`generate_signals` > `compute_levels`). The retired CAI-0 typical-price
   snapshot (`poc_windows=["30min"]`, `compute_levels` ~71% of e2e) is
   historical only (QI-14-01 / QI-14-02).
2. CSV reload remains cheap relative to compute stages; source-content
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

- The live F-10 table is signal-dominated (`generate_signals` share >
  `compute_levels`). CAI-3 data/levels reuse stays the first cache
  surface. CAI-10 still says no second signal cache yet.
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
`--repeats 5`). It is a C-14→C-15 delta footnote, not the live envelope
(F-10 tables above).

| Stage | Before (C-14 / `#561`) median ms | After (C-15) median ms |
|---|---:|---:|
| `generate_signals` | 331.765 | 352.338 |
| `run_experiment_end_to_end` | 756.672 | 748.973 |

Do not treat these rows as a CI gate.

## DEFAULT merge (H4 / QI-14-04)

Omitted levels-family keys still merge product DEFAULT (`omit` ⇒ on).
`cai_levels_config()` is an explicit fixture override, not a flip of that
merge. Do not treat a missing key as disabled.

## Non-goals of CAI-0

- No production cache read/write.
- No Assistant or classic UI behavior change.
- No golden-master regeneration.
- No CI performance threshold.
