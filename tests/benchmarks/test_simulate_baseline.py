"""Smoke tests for reproducible, non-gating R22 benchmark workloads."""

from __future__ import annotations

from .run import run_benchmarks


def test_r22_benchmark_scenarios_are_deterministic_and_complete():
    first = run_benchmarks(repeats=1)
    second = run_benchmarks(repeats=1)

    assert [row["scenario"] for row in first] == [
        "simulate_trades",
        "simulate_trades",
        "simulate_trades",
        "run_sl_tp_grid_3x3",
    ]
    assert [
        (row["scenario"], row["bar_count"], row["signal_count"], row["max_holding_bars"])
        for row in first
    ] == [
        (row["scenario"], row["bar_count"], row["signal_count"], row["max_holding_bars"])
        for row in second
    ]
    assert all(row["median_ms"] >= 0 for row in first)
