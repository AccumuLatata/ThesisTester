"""Run the committed R22 informational benchmark scenarios."""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable

from thesistester.analytics.grid import run_sl_tp_grid
from thesistester.engine.backtest import simulate_trades

from .fixtures import benchmark_ohlcv, benchmark_signals


def _timed_ms(operation: Callable[[], object], *, repeats: int) -> dict[str, float]:
    samples: list[float] = []
    operation()  # warm up imports and one-time interpreter specialization
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1_000)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(sorted(samples)[max(0, int(len(samples) * 0.95) - 1)], 3),
    }


def run_benchmarks(*, repeats: int = 5) -> list[dict[str, Any]]:
    """Return serial wall-time measurements; intended for manual R22 baselines."""
    rows: list[dict[str, Any]] = []
    for bar_count, signal_count, max_holding_bars in (
        (500, 10, 50),
        (500, 100, 50),
        (2_000, 100, 200),
    ):
        data = benchmark_ohlcv(bars=bar_count)
        signals = benchmark_signals(bars=bar_count, signal_count=signal_count)
        timing = _timed_ms(
            lambda: simulate_trades(
                data,
                signals,
                tick_size=0.25,
                point_value=5.0,
                stop_loss_ticks=100,
                take_profit_ticks=100,
                max_holding_bars=max_holding_bars,
            ),
            repeats=repeats,
        )
        rows.append(
            {
                "scenario": "simulate_trades",
                "bar_count": bar_count,
                "signal_count": signal_count,
                "max_holding_bars": max_holding_bars,
                **timing,
            }
        )

    data = benchmark_ohlcv(bars=500)
    signals = benchmark_signals(bars=500, signal_count=50)
    timing = _timed_ms(
        lambda: run_sl_tp_grid(
            data,
            signals,
            tick_size=0.25,
            point_value=5.0,
            stop_loss_ticks_values=[80, 100, 120],
            take_profit_ticks_values=[80, 100, 120],
            max_holding_bars=50,
        ),
        repeats=repeats,
    )
    rows.append(
        {
            "scenario": "run_sl_tp_grid_3x3",
            "bar_count": 500,
            "signal_count": 50,
            "max_holding_bars": 50,
            **timing,
        }
    )
    return rows


if __name__ == "__main__":
    for row in run_benchmarks():
        print(row)
