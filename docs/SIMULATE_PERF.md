# `simulate_trades` performance baseline (R22)

## Purpose

This is an informational, reproducible serial baseline for the engine hot path.
It is not a CI performance threshold: wall time varies with hardware, Python,
pandas, and browser-independent system load. Any future acceleration PR must
repeat these scenarios, report its environment, and prove exact serial parity
on golden and feature fixtures.

## Method

Command:

```bash
python3 -m tests.benchmarks.run
```

The runner performs one warmup plus five `time.perf_counter()` repetitions per
scenario, reporting median and nearest-rank p95 wall time. Fixtures are
deterministic synthetic 1-minute OHLCV (`tests/benchmarks/fixtures.py`):

- Parent bars have narrow ranges and wide brackets, so the configured holding
  cap isolates serial exit-walk work instead of early bracket exits.
- Signals alternate long/short and use the legacy `touch` next-open path.
- Grid timing uses nine independent `simulate_trades` calls (3×3 SL/TP).

## Recorded baseline

Recorded on the R22 implementation environment: CPython 3.12, pandas 3.0.5,
NumPy 2.4.6, Linux 6.12.

| Scenario | Bars | Signals | Holding cap | Median ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| `simulate_trades` | 500 | 10 | 50 | 4.645 | 4.714 |
| `simulate_trades` | 500 | 100 | 50 | 27.019 | 27.045 |
| `simulate_trades` | 2,000 | 100 | 200 | 52.943 | 53.294 |
| `run_sl_tp_grid_3x3` | 500 | 50 | 50 | 204.473 | 205.082 |

The grid result demonstrates the expected multiplicative cost: each grid cell
replays the serial engine. R15/R16/R19 and walk-forward work compound that
cost. R22 therefore isolates the parent-bar resolution boundary but does not
introduce acceleration yet: the current measurements establish a reproducible
ruler, while a Numba/vectorized/parallel path would require an explicit
serial-parity implementation and measurement PR.

## R22 core boundary

`thesistester.engine.sim_core` owns immutable parent-bar OHLC snapshots and
one-bar bracket resolution. `simulate_trades` remains the sole public
orchestrator for admission, caps, MAE/MFE, costs, trade records, and
diagnostics. This keeps any future hot-loop acceleration constrained to the
small internal boundary while preserving exact legacy semantics.
