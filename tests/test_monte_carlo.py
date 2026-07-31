"""R11 tests: Monte Carlo trade-sequence diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.analytics.monte_carlo import (
    monte_carlo_block_resample,
    monte_carlo_reshuffle,
    monte_carlo_skip,
    monte_carlo_summary,
    path_metrics_from_r,
)


def _trades(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": list(range(1, len(values) + 1)),
            "exit_timestamp": pd.date_range(
                "2026-06-01 09:35", periods=len(values), freq="5min", tz="America/New_York"
            ),
            "r_multiple": values,
        }
    )


def test_path_metrics_are_hand_computed_with_zero_anchor():
    metrics = path_metrics_from_r([-1.0, 2.0, -0.5, -0.25, 1.0])

    assert metrics == {
        "final_r": 1.25,
        "max_drawdown_r": 1.0,
        "max_loss_streak": 2,
    }


def test_empty_and_missing_r_multiple_are_safe():
    empty_summary = monte_carlo_summary(pd.DataFrame(), n_simulations=10)
    assert empty_summary["schema_version"] == 1
    assert empty_summary["available"] is False
    assert empty_summary["methods"] == {}

    missing = monte_carlo_reshuffle(pd.DataFrame({"x": [1]}), n_simulations=10)
    assert missing["trade_count"] == 0
    assert missing["simulated"]["final_r"] == {}


def test_reshuffle_is_seed_deterministic_and_preserves_final_r():
    trades = _trades([1.0, -0.5, 2.0, -1.0])
    first = monte_carlo_reshuffle(
        trades, n_simulations=25, random_state=7, drawdown_thresholds_r=[1.0]
    )
    second = monte_carlo_reshuffle(
        trades, n_simulations=25, random_state=7, drawdown_thresholds_r=[1.0]
    )

    assert first == second
    assert first["observed"] == {"final_r": 1.5, "max_drawdown_r": 1.0, "max_loss_streak": 1}
    assert first["simulated"]["final_r"] == {
        "p05": 1.5,
        "p25": 1.5,
        "p50": 1.5,
        "p75": 1.5,
        "p95": 1.5,
    }
    assert first["probability_drawdown_exceeds"][0]["threshold_r"] == 1.0
    assert 0.0 <= first["probability_drawdown_exceeds"][0]["probability"] <= 1.0


def test_skip_zero_fraction_matches_observed_final_r_distribution():
    trades = _trades([1.0, -0.5, 2.0])
    result = monte_carlo_skip(trades, skip_fraction=0.0, n_simulations=10, random_state=11)

    assert result["skip_fraction"] == 0.0
    assert result["simulated"]["final_r"] == {
        "p05": 2.5,
        "p25": 2.5,
        "p50": 2.5,
        "p75": 2.5,
        "p95": 2.5,
    }
    assert len(result["equity_fan"]["trade_index"]) == 3


def test_skip_fraction_validation():
    with pytest.raises(ValueError, match="skip_fraction"):
        monte_carlo_skip(_trades([1.0]), skip_fraction=1.0)


def test_block_resample_is_seed_deterministic_and_reports_block_length():
    trades = _trades([1.0, -1.0, -1.0, 2.0, -0.5])
    first = monte_carlo_block_resample(trades, block_length=2, n_simulations=20, random_state=3)
    second = monte_carlo_block_resample(trades, block_length=2, n_simulations=20, random_state=3)

    assert first == second
    assert first["block_length"] == 2
    assert first["trade_count"] == 5
    assert len(first["equity_fan"]["p05"]) == 5


def test_block_resample_preserves_streaks_better_than_reshuffle_fixture():
    # A single clustered loss run is partially preserved by fixed blocks but
    # dispersed by pure reshuffling.
    trades = _trades([1.0, 1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0])
    block = monte_carlo_block_resample(trades, block_length=4, n_simulations=500, random_state=42)
    reshuffle = monte_carlo_reshuffle(trades, n_simulations=500, random_state=42)

    observed_streak = block["observed"]["max_loss_streak"]
    block_median = block["simulated"]["max_loss_streak"]["p50"]
    reshuffle_median = reshuffle["simulated"]["max_loss_streak"]["p50"]
    assert abs(block_median - observed_streak) <= abs(reshuffle_median - observed_streak)


def test_summary_contract_and_fan_shape_are_stable():
    summary = monte_carlo_summary(
        _trades([1.0, -0.5, 2.0, -1.0]),
        methods=["reshuffle", "skip", "block_resample"],
        n_simulations=30,
        skip_fraction=0.25,
        block_length=2,
        drawdown_thresholds_r=[0.5, 1.0],
        random_state=5,
    )

    assert set(summary) == {
        "schema_version",
        "available",
        "trade_count",
        "config",
        "observed_equity",
        "methods",
        "caveat",
    }
    assert summary["schema_version"] == 1
    assert summary["available"] is True
    assert summary["trade_count"] == 4
    assert summary["config"]["methods"] == ["reshuffle", "skip", "block_resample"]
    assert summary["config"]["block_length"] == 2
    assert set(summary["methods"]) == {"reshuffle", "skip", "block_resample"}
    assert summary["observed_equity"]["cum_r"] == [1.0, 0.5, 2.5, 1.5]
    for result in summary["methods"].values():
        assert "simulation_paths" not in result
        assert len(result["equity_fan"]["trade_index"]) == 4
        for row in result["probability_drawdown_exceeds"]:
            assert 0.0 <= row["probability"] <= 1.0


def test_include_paths_is_opt_in():
    result = monte_carlo_reshuffle(_trades([1.0, -1.0]), n_simulations=3, include_paths=True)

    assert "simulation_paths" in result
    assert np.asarray(result["simulation_paths"]).shape == (3, 2)
