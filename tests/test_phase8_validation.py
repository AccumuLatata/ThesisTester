"""Phase 8 tests: statistical validation and robustness diagnostics."""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.validation import (
    bootstrap_expectancy_ci,
    grid_overfit_diagnostics,
    permutation_test_expectancy,
    trade_count_diagnostics,
    validation_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trades(r_multiples: list[float]) -> pd.DataFrame:
    """Build a minimal trade DataFrame with r_multiple values."""
    return pd.DataFrame({"r_multiple": r_multiples})


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame({"r_multiple": []})


# ---------------------------------------------------------------------------
# A. bootstrap_expectancy_ci
# ---------------------------------------------------------------------------


def test_bootstrap_empty_trades_returns_safe_values():
    """Empty trade set must return a dict with None values, not raise."""
    result = bootstrap_expectancy_ci(_empty_trades(), n_bootstrap=100)
    assert result["trade_count"] == 0
    assert result["observed_avg_r"] is None
    assert result["ci_lower"] is None
    assert result["ci_upper"] is None
    assert result["probability_positive"] is None
    assert result["bootstrap_means"] == []


def test_bootstrap_deterministic_with_fixed_seed():
    """Same seed must produce identical CI bounds across two calls."""
    trades = _trades([1.0, 2.0, -0.5, 1.5, -1.0, 0.5])
    r1 = bootstrap_expectancy_ci(trades, n_bootstrap=100, random_state=7)
    r2 = bootstrap_expectancy_ci(trades, n_bootstrap=100, random_state=7)
    assert r1["ci_lower"] == pytest.approx(r2["ci_lower"])
    assert r1["ci_upper"] == pytest.approx(r2["ci_upper"])
    assert r1["bootstrap_means"] == r2["bootstrap_means"]


def test_bootstrap_positive_trades_positive_observed_avg():
    """All-positive trades must have a positive observed_avg_r."""
    trades = _trades([1.0, 2.0, 3.0, 1.5])
    result = bootstrap_expectancy_ci(trades, n_bootstrap=100, random_state=0)
    assert result["observed_avg_r"] is not None
    assert result["observed_avg_r"] > 0


def test_bootstrap_ci_keys_exist_and_bounds_ordered():
    """Result must contain expected keys and ci_lower <= ci_upper."""
    trades = _trades([0.5, -0.5, 1.0, -1.0, 2.0])
    result = bootstrap_expectancy_ci(trades, n_bootstrap=100, random_state=1)
    for key in (
        "trade_count", "observed_avg_r", "ci_lower", "ci_upper",
        "confidence", "n_bootstrap", "probability_positive", "bootstrap_means",
    ):
        assert key in result, f"Missing key: {key}"
    assert result["ci_lower"] <= result["ci_upper"]


# ---------------------------------------------------------------------------
# B. permutation_test_expectancy
# ---------------------------------------------------------------------------


def test_permutation_empty_trades_returns_safe_values():
    """Empty trade set must return a dict with None values, not raise."""
    result = permutation_test_expectancy(_empty_trades(), n_permutations=100)
    assert result["trade_count"] == 0
    assert result["observed_avg_r"] is None
    assert result["p_value_positive"] is None
    assert result["permuted_means"] == []


def test_permutation_deterministic_with_fixed_seed():
    """Same seed must produce identical p-values across two calls."""
    trades = _trades([1.0, 1.5, -0.5, 0.5, 2.0])
    r1 = permutation_test_expectancy(trades, n_permutations=100, random_state=99)
    r2 = permutation_test_expectancy(trades, n_permutations=100, random_state=99)
    assert r1["p_value_positive"] == pytest.approx(r2["p_value_positive"])
    assert r1["permuted_means"] == r2["permuted_means"]


def test_permutation_positive_trades_positive_observed_avg():
    """All-positive trades must have a positive observed_avg_r."""
    trades = _trades([1.0, 2.0, 3.0])
    result = permutation_test_expectancy(trades, n_permutations=100, random_state=0)
    assert result["observed_avg_r"] is not None
    assert result["observed_avg_r"] > 0


def test_permutation_p_value_between_0_and_1():
    """p_value_positive must be a float in [0, 1]."""
    trades = _trades([1.0, -1.0, 0.5, -0.5, 2.0, -2.0])
    result = permutation_test_expectancy(trades, n_permutations=100, random_state=3)
    p = result["p_value_positive"]
    assert p is not None
    assert 0.0 <= p <= 1.0


# ---------------------------------------------------------------------------
# C. trade_count_diagnostics
# ---------------------------------------------------------------------------


def test_trade_count_below_soft_threshold_is_insufficient():
    """Fewer trades than min_trades_soft → status 'insufficient'."""
    trades = _trades([1.0] * 10)
    result = trade_count_diagnostics(trades, min_trades_soft=30, min_trades_hard=100)
    assert result["status"] == "insufficient"
    assert result["trade_count"] == 10


def test_trade_count_between_thresholds_is_limited():
    """Trades between soft and hard thresholds → status 'limited'."""
    trades = _trades([1.0] * 50)
    result = trade_count_diagnostics(trades, min_trades_soft=30, min_trades_hard=100)
    assert result["status"] == "limited"
    assert result["trade_count"] == 50


def test_trade_count_above_hard_threshold_is_reasonable():
    """Trades at or above min_trades_hard → status 'reasonable'."""
    trades = _trades([1.0] * 150)
    result = trade_count_diagnostics(trades, min_trades_soft=30, min_trades_hard=100)
    assert result["status"] == "reasonable"
    assert result["trade_count"] == 150


# ---------------------------------------------------------------------------
# D. grid_overfit_diagnostics
# ---------------------------------------------------------------------------


def test_grid_overfit_empty_grid_risk_none():
    """Empty grid → risk_level 'none'."""
    result = grid_overfit_diagnostics(pd.DataFrame())
    assert result["risk_level"] == "none"


def test_grid_overfit_large_grid_risk_at_least_medium():
    """Grid with >= 25 valid cells → risk_level 'medium' or 'high'."""
    # Build a grid with 30 rows and an expectancy_r column
    import numpy as np
    rng = np.random.default_rng(0)
    grid = pd.DataFrame({
        "stop_loss_ticks": list(range(30)),
        "take_profit_ticks": [10] * 30,
        "expectancy_r": rng.uniform(-0.5, 1.5, 30).tolist(),
    })
    result = grid_overfit_diagnostics(grid, selected_metric="expectancy_r")
    assert result["risk_level"] in ("medium", "high")


def test_grid_overfit_very_large_grid_risk_high():
    """Grid with >= 100 valid cells → risk_level 'high'."""
    import numpy as np
    rng = np.random.default_rng(1)
    grid = pd.DataFrame({
        "stop_loss_ticks": list(range(100)),
        "take_profit_ticks": [10] * 100,
        "expectancy_r": rng.uniform(-0.5, 1.5, 100).tolist(),
    })
    result = grid_overfit_diagnostics(grid, selected_metric="expectancy_r")
    assert result["risk_level"] == "high"


def test_grid_overfit_output_contains_expected_keys():
    """Result must contain all documented output keys."""
    import numpy as np
    rng = np.random.default_rng(2)
    grid = pd.DataFrame({
        "stop_loss_ticks": [4, 6, 8],
        "take_profit_ticks": [8, 12, 16],
        "expectancy_r": rng.uniform(0, 1, 3).tolist(),
    })
    result = grid_overfit_diagnostics(grid)
    for key in (
        "grid_cell_count", "valid_cell_count", "best_metric",
        "median_metric", "mean_metric", "top_n_mean_metric",
        "best_vs_median_delta", "risk_level", "message",
    ):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# E. validation_summary
# ---------------------------------------------------------------------------


def test_validation_summary_returns_expected_top_level_keys():
    """validation_summary must return bootstrap, permutation, trade_count, grid_overfit."""
    trades = _trades([1.0, 0.5, -0.5, 2.0, -1.0])
    result = validation_summary(
        trades,
        n_bootstrap=100,
        n_permutations=100,
        random_state=0,
    )
    for key in ("bootstrap", "permutation", "trade_count", "grid_overfit"):
        assert key in result, f"Missing top-level key: {key}"


def test_validation_summary_with_grid():
    """validation_summary accepts an optional grid and populates grid_overfit."""
    import numpy as np
    trades = _trades([1.0, -0.5, 0.5])
    rng = np.random.default_rng(5)
    grid = pd.DataFrame({
        "stop_loss_ticks": list(range(30)),
        "take_profit_ticks": [10] * 30,
        "expectancy_r": rng.uniform(-0.5, 1.5, 30).tolist(),
    })
    result = validation_summary(trades, grid=grid, n_bootstrap=50, n_permutations=50)
    assert result["grid_overfit"]["valid_cell_count"] == 30
