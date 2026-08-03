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
  **Record and discuss this run** (implemented in later milestones).
- Automatic `all_executions` ledger recording remains deferred to CAI-7 and
  stays opt-in.

## Fixtures and commands

| Fixture | Bars | Levels intent | Use |
|---|---:|---|---|
| `small` | 60 | Cheap RTH hour; no rolling POC | CI smoke + exhaustive harness structure |
| `realistic` | 780 | Two RTH sessions; `poc_windows=["30min"]` | Informational benchmark only |

Source of truth:

- Fixtures: `tests/fixtures/cai_baseline.py`
- Harness: `tests/benchmarks/cai_cold_path.py`
- Smoke tests: `tests/benchmarks/test_cai_cold_path.py`

Commands:

```bash
# Informational baseline (small + realistic)
python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5

# CI smoke only covers the small fixture structure (via pytest)
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

### Realistic fixture (780 bars, rolling POC `30min`)

| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|---:|
| `load_dataset` | 12.573 | 12.666 | 0.7% |
| `compute_levels` | 1293.267 | 1294.099 | 70.9% |
| `generate_signals` | 322.610 | 332.232 | 17.7% |
| `run_backtest` | 156.016 | 156.043 | 8.6% |
| `build_research_bundle` | 35.205 | 35.511 | 1.9% |
| `run_experiment_end_to_end` | 1824.623 | 1843.264 | 100% |

## Interpretation for later milestones

1. On the realistic fixture, **levels dominate** cold recomputation. CAI-2/CAI-3
   artifact reuse should target canonical data + levels first.
2. CSV reload itself is currently cheap relative to levels; source-content
   identity checks remain mandatory even if parse time is small.
3. Signal generation can be non-trivial once confluence density is high. Signal
   caching stays deferred until after levels-cache impact is measured
   (CAI-10 decision).
4. Any warm-path optimization must prove equal canonical bundle hashes against
   this cold path; timing improvements alone are never acceptance criteria.

## Non-goals of CAI-0

- No production cache read/write.
- No Assistant or classic UI behavior change.
- No golden-master regeneration.
- No CI performance threshold.
