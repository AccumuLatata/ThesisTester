"""B-19 / QI-05-13 / C12: ``validation_summary()`` four-key freeze.

Phase 8 is unversioned. Do not add ``schema_version`` or any fifth key.
Empty / no-valid-trade paths return the same four keys (null metrics
``None`` not NaN, plus ``insufficient``) without raising (QI-5 §6.2 /
QI-4 §6.4).
"""

from __future__ import annotations

import pandas as pd

from thesistester.analytics.validation import validation_summary

VALIDATION_SUMMARY_KEYS = frozenset({"bootstrap", "permutation", "trade_count", "grid_overfit"})

_BOOTSTRAP_NULL_KEYS = ("observed_avg_r", "ci_lower", "ci_upper", "probability_positive")
_PERMUTATION_NULL_KEYS = ("observed_avg_r", "p_value_positive")


def _assert_frozen(result: dict) -> None:
    assert isinstance(result, dict)
    assert set(result) == VALIDATION_SUMMARY_KEYS
    assert "schema_version" not in result
    for key, value in result.items():
        assert isinstance(value, dict), key
        assert "schema_version" not in value, key


def _assert_empty_null_metrics(result: dict) -> None:
    """QI-5 §6.2 / QI-4 §6.4: empty path is insufficient + None, not NaN."""
    _assert_frozen(result)
    trade_count = result["trade_count"]
    assert trade_count["trade_count"] == 0
    assert trade_count["status"] == "insufficient"
    bootstrap = result["bootstrap"]
    for key in _BOOTSTRAP_NULL_KEYS:
        assert bootstrap[key] is None, (key, bootstrap[key])
    permutation = result["permutation"]
    for key in _PERMUTATION_NULL_KEYS:
        assert permutation[key] is None, (key, permutation[key])


def test_validation_summary_four_key_freeze():
    """QI-5 §6.2: populated trades still use the frozen four-key set."""
    trades = pd.DataFrame({"r_multiple": [1.0, 0.5, -0.5, 2.0, -1.0]})
    result = validation_summary(
        trades,
        n_bootstrap=20,
        n_permutations=20,
        random_state=0,
    )
    _assert_frozen(result)
    assert result["trade_count"]["trade_count"] == 5
    assert result["grid_overfit"]["risk_level"] == "none"


def test_validation_summary_empty_trades_same_four_keys():
    """QI-5 §6.2: 0-row trades do not raise and stay on the four-key freeze."""
    result = validation_summary(
        pd.DataFrame({"r_multiple": []}),
        n_bootstrap=10,
        n_permutations=10,
        random_state=0,
    )
    _assert_empty_null_metrics(result)


def test_validation_summary_all_nan_trades_same_four_keys():
    """QI-5 §6.2: dropna/n==0 is a different branch from ``DataFrame.empty``."""
    result = validation_summary(
        pd.DataFrame({"r_multiple": [float("nan"), float("nan")]}),
        n_bootstrap=10,
        n_permutations=10,
        random_state=0,
    )
    _assert_empty_null_metrics(result)


def test_validation_summary_with_grid_same_four_keys():
    """Optional grid still must not grow the top-level key set."""
    trades = pd.DataFrame({"r_multiple": [1.0, -0.5, 0.5]})
    grid = pd.DataFrame(
        {
            "stop_loss_ticks": [8, 10],
            "take_profit_ticks": [16, 20],
            "expectancy_r": [0.2, 0.1],
        }
    )
    result = validation_summary(
        trades,
        grid=grid,
        n_bootstrap=10,
        n_permutations=10,
        random_state=0,
    )
    _assert_frozen(result)
    assert result["grid_overfit"]["valid_cell_count"] == 2
    assert "schema_version" not in result["grid_overfit"]
