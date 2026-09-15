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

Recorded on the E-10 vectorized fixed-bracket ``sl_first`` walk:
CPython 3.12.3, pandas 3.0.5, NumPy 2.5.3, Linux 6.12. Prior C-20
``BarData`` float64 ruler was 4.863 / 30.166 / 59.234 / 214.443 ms
median on the same host class. Prior C-19 extract ruler was
4.683 / 28.257 / 55.204 / 206.236 ms.

| Scenario | Bars | Signals | Holding cap | Median ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| `simulate_trades` | 500 | 10 | 50 | 3.917 | 3.956 |
| `simulate_trades` | 500 | 100 | 50 | 20.571 | 20.708 |
| `simulate_trades` | 2,000 | 100 | 200 | 21.746 | 21.788 |
| `run_sl_tp_grid_3x3` | 500 | 50 | 50 | 171.542 | 171.751 |

The walk-heavy `2,000 × 100 × 200` case is **2.7×** the C-20 serial
ruler (59.234 → 21.746 ms). Smaller cases stay admission-dominated
(~1.2–1.5×). The 3×3 grid remains nine independent `simulate_trades`
calls (admission never parallelized); its 1.25× gain is the per-cell
walk, not a parallel grid. R15/R16/R19 and walk-forward still multiply
that serial admission × walk cost.

E-10 (QI-14-03) accelerates only the fixed-bracket ``sl_first`` P7 walk
inside `sim_core.walk_trade_exit`. R13, `path_open_proximity`,
subtimeframe, and 3c/confirm_3bar entry-bar clipping stay on the C-19
serial loop. Outputs must stay byte-identical to that serial reference
(golden + B-3 families; `tests/test_sim_core.py` walk equality). No
`GOLDEN_REGEN`. Numba and multi-process grid/MC replicas are still
out of scope.

## R22 core boundary

`thesistester.engine.sim_core` owns immutable parent-bar OHLC snapshots
as write-protected ``float64`` arrays (C-20 / QI-14-09), one-bar
bracket resolution, the C-19 serial P7 walk, and the E-10 vectorized
fixed-bracket ``sl_first`` walk (`walk_trade_exit`,
`compute_session_close_cap`). `BarData.at()` still yields Python
``float`` scalars so `resolve_ohlc_bar` math is unchanged. Non-numpy
OHLC dtypes keep C-19 ``float()`` fail-closed.
`simulate_trades` remains the sole public orchestrator for admission,
skip/exit labels, costs, trade records, and diagnostics. `sim_core`
still holds no admission or P&L. The ruler above is re-timed on the
E-10 walk.
