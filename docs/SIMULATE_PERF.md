# `simulate_trades` performance baseline (R22)

## Purpose

This is an informational, reproducible serial baseline for the engine hot path.
It is not a CI performance threshold: wall time varies with hardware, Python,
pandas, and browser-independent system load. Any future acceleration PR must
repeat these scenarios, report its environment, and prove exact serial parity
on golden and feature fixtures.

For classic/Assistant cold-path stage timings (CSV load, levels, signals,
backtest, bundle), see `docs/CAI_BASELINE.md` (`CAI-0`). That baseline also is
informational only and must not become a CI performance gate.

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

Recorded on the C-20 `BarData` float64 environment: CPython 3.12.3,
pandas 3.0.5, NumPy 2.5.3, Linux 6.12. Prior C-19 extract ruler was
4.683 / 28.257 / 55.204 / 206.236 ms median on the same host class.

| Scenario | Bars | Signals | Holding cap | Median ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| `simulate_trades` | 500 | 10 | 50 | 4.863 | 4.880 |
| `simulate_trades` | 500 | 100 | 50 | 30.166 | 31.435 |
| `simulate_trades` | 2,000 | 100 | 200 | 59.234 | 59.378 |
| `run_sl_tp_grid_3x3` | 500 | 50 | 50 | 214.443 | 214.711 |

The grid result demonstrates the expected multiplicative cost: each grid cell
replays the serial engine. R15/R16/R19 and walk-forward work compound that
cost. R22 therefore isolates the parent-bar resolution boundary but does not
introduce acceleration yet: the current measurements establish a reproducible
ruler, while a Numba/vectorized/parallel path would require an explicit
serial-parity implementation and measurement PR.

## R22 core boundary

`thesistester.engine.sim_core` owns immutable parent-bar OHLC snapshots
as write-protected ``float64`` arrays (C-20 / QI-14-09), one-bar
bracket resolution, and the C-19 serial P7 walk (`walk_trade_exit`,
`compute_session_close_cap`). `BarData.at()` still yields Python
``float`` scalars so `resolve_ohlc_bar` math is unchanged. Non-numpy
OHLC dtypes keep C-19 ``float()`` fail-closed.
`simulate_trades` remains the sole public orchestrator for admission,
skip/exit labels, costs, trade records, and diagnostics. `sim_core`
still holds no admission or P&L. This keeps any future hot-loop
acceleration (E-10) constrained to the small internal boundary while
preserving exact legacy semantics. The ruler above is re-timed on the
C-20 storage change.
