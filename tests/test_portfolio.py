from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.portfolio import portfolio_summary, setup_correlation_matrices


def _trades(rows: list[tuple[int, int, str, float]]) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 09:30", periods=10, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        [
            {
                "trade_id": index,
                "entry_bar_index": entry,
                "exit_bar_index": exit_,
                "entry_timestamp": timestamps[0] + pd.Timedelta(minutes=entry),
                "exit_timestamp": timestamps[0] + pd.Timedelta(minutes=exit_),
                "direction": direction,
                "r_multiple": r_multiple,
                "pnl_currency": r_multiple * 10.0,
            }
            for index, (entry, exit_, direction, r_multiple) in enumerate(rows)
        ]
    )


def test_disjoint_allow_all_portfolio_equals_sum_of_parts():
    summary = portfolio_summary(
        {"A": _trades([(0, 1, "long", 1.0)]), "B": _trades([(2, 3, "short", 2.0)])},
        instrument="ES",
        bar_count=10,
    )

    assert summary["admission"]["admitted_trade_count"] == 2
    assert summary["portfolio_metrics"]["total_r"] == 3.0
    assert summary["portfolio_equity_curve"]["cum_r"].tolist() == [1.0, 3.0]
    assert summary["portfolio_equity_curve"]["cum_pnl_currency"].tolist() == [10.0, 30.0]


def test_single_position_rejects_deterministic_overlap():
    summary = portfolio_summary(
        {"A": _trades([(0, 2, "long", 1.0)]), "B": _trades([(1, 3, "long", 2.0)])},
        instrument="ES",
        exposure_policy="single_position",
        bar_count=10,
    )

    assert summary["portfolio_trades"]["setup_id"].tolist() == ["A"]
    skipped = summary["portfolio_skipped_trades"].iloc[0]
    assert skipped["setup_id"] == "B"
    assert skipped["skip_reason"] == "overlapping_position"
    assert skipped["blocking_trade_id"] == "A:0"


def test_single_direction_and_cooldown_follow_r4_semantics():
    directional = portfolio_summary(
        {
            "A": _trades([(0, 1, "long", 1.0)]),
            "B": _trades([(0, 1, "short", 0.5)]),
            "C": _trades([(0, 1, "long", 2.0)]),
        },
        instrument="ES",
        exposure_policy="single_direction",
        bar_count=10,
    )
    assert directional["portfolio_metrics"]["total_r"] == 1.5
    assert directional["portfolio_skipped_trades"]["skip_reason"].tolist() == [
        "overlapping_direction"
    ]

    cooldown = portfolio_summary(
        {"A": _trades([(0, 1, "long", 1.0)]), "B": _trades([(2, 3, "short", 2.0)])},
        instrument="ES",
        exposure_policy="single_position",
        cooldown_bars_after_exit=1,
        bar_count=10,
    )
    assert cooldown["admission"]["skipped_trade_count"] == 1
    assert cooldown["portfolio_skipped_trades"]["skip_reason"].tolist() == ["cooldown_active"]


def test_correlation_matches_pandas_reference():
    candidates = pd.concat(
        [
            _trades([(0, 0, "long", 1.0), (1, 1, "long", -1.0), (2, 2, "long", 2.0)]).assign(
                setup_id="A"
            ),
            _trades([(0, 0, "short", 0.5), (1, 1, "short", -0.5), (2, 2, "short", 1.0)]).assign(
                setup_id="B"
            ),
        ],
        ignore_index=True,
    )
    returns, _ = setup_correlation_matrices(candidates, ["A", "B"])
    reference = pd.DataFrame({"A": [1.0, -1.0, 2.0], "B": [0.5, -0.5, 1.0]}).corr()

    pd.testing.assert_frame_equal(returns, reference)


def test_portfolio_rejects_non_shared_bar_index_range():
    with pytest.raises(ValueError, match="parent bar-index"):
        portfolio_summary(
            {
                "A": _trades([(0, 1, "long", 1.0)]),
                "B": _trades([(100, 101, "short", 1.0)]),
            },
            instrument="ES",
            bar_count=10,
        )
