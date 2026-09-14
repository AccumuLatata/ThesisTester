"""B-19 / QI-05-13 / C12: ``validation_summary()`` four-key freeze.

Phase 8 is unversioned. Do not add ``schema_version`` or any fifth key.
Empty trades return the same four keys (null metrics + ``insufficient``).
"""

from __future__ import annotations

import pandas as pd

from thesistester.analytics.validation import validation_summary

VALIDATION_SUMMARY_KEYS = frozenset({"bootstrap", "permutation", "trade_count", "grid_overfit"})


def _assert_frozen(result: dict) -> None:
    assert set(result) == VALIDATION_SUMMARY_KEYS
    assert "schema_version" not in result


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


def test_validation_summary_empty_trades_same_four_keys():
    """QI-5 §6.2: empty trades do not raise and stay on the four-key freeze."""
    result = validation_summary(
        pd.DataFrame({"r_multiple": []}),
        n_bootstrap=10,
        n_permutations=10,
        random_state=0,
    )
    _assert_frozen(result)
    assert result["trade_count"]["status"] == "insufficient"
    assert result["bootstrap"]["observed_avg_r"] is None
    assert result["permutation"]["p_value_positive"] is None


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
