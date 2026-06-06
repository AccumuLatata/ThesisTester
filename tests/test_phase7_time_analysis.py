"""Phase 7 tests: add_time_buckets, summarize_by_group, pivot_time_metric."""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.time_analysis import (
    add_time_buckets,
    pivot_time_metric,
    summarize_by_group,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIME_BUCKET_COLS = [
    "entry_date",
    "entry_time",
    "entry_hour",
    "entry_minute",
    "entry_hour_bucket",
    "entry_30min_bucket",
    "entry_rth_segment",
]

_GROUP_SUMMARY_COLS = [
    "trade_count",
    "win_rate",
    "loss_rate",
    "avg_r",
    "median_r",
    "total_r",
    "profit_factor",
    "avg_win_r",
    "avg_loss_r",
    "max_drawdown_r",
    "best_trade_r",
    "worst_trade_r",
    "sample_warning",
]


def _make_trades(timestamps_ny: list[str], r_multiples: list[float]) -> pd.DataFrame:
    """Build a minimal trade DataFrame with tz-naive NY timestamps."""
    ts = pd.to_datetime(timestamps_ny).tz_localize("America/New_York")
    return pd.DataFrame({
        "trade_id": list(range(len(r_multiples))),
        "entry_timestamp": ts,
        "r_multiple": r_multiples,
    })


# ---------------------------------------------------------------------------
# A. add_time_buckets
# ---------------------------------------------------------------------------


def test_add_time_buckets_adds_expected_columns():
    """Output must contain all seven time-bucket columns."""
    trades = _make_trades(["2026-06-02 10:00"], [1.0])
    result = add_time_buckets(trades)
    for col in _TIME_BUCKET_COLS:
        assert col in result.columns, f"Missing column: {col}"


def test_timezone_aware_timestamps_convert_to_exchange_timezone():
    """UTC-aware 13:30 should become 09:30 America/New_York."""
    ts_utc = pd.Timestamp("2026-06-02 13:30:00", tz="UTC")
    trades = pd.DataFrame({
        "trade_id": [0],
        "entry_timestamp": [ts_utc],
        "r_multiple": [1.0],
    })
    result = add_time_buckets(trades, exchange_tz="America/New_York")
    row = result.iloc[0]
    assert row["entry_hour"] == 9
    assert row["entry_minute"] == 30
    assert row["entry_hour_bucket"] == "09:00"
    assert row["entry_30min_bucket"] == "09:30"
    assert row["entry_rth_segment"] == "rth_open_30m"


def test_timezone_naive_timestamps_localize_to_exchange_timezone():
    """Tz-naive 10:00 should be treated as 10:00 America/New_York."""
    ts_naive = pd.Timestamp("2026-06-02 10:00:00")
    trades = pd.DataFrame({
        "trade_id": [0],
        "entry_timestamp": [ts_naive],
        "r_multiple": [1.0],
    })
    result = add_time_buckets(trades, exchange_tz="America/New_York")
    row = result.iloc[0]
    assert row["entry_hour"] == 10
    assert row["entry_minute"] == 0
    assert row["entry_rth_segment"] == "rth_morning"


def test_bucket_labels_are_string_clock_format():
    trades = _make_trades(
        ["2026-06-02 09:05", "2026-06-02 09:35", "2026-06-02 10:00"],
        [1.0, -1.0, 0.5],
    )
    result = add_time_buckets(trades)
    assert result["entry_hour_bucket"].map(type).eq(str).all()
    assert result["entry_30min_bucket"].map(type).eq(str).all()
    assert set(result["entry_30min_bucket"]) == {"09:00", "09:30", "10:00"}
    assert result["entry_30min_bucket"].str.match(r"^\d{2}:\d{2}$").all()


def test_bucket_timezone_changes_labels():
    trades = _make_trades(["2026-06-02 09:30"], [1.0])
    ny = add_time_buckets(
        trades,
        bucket_tz="America/New_York",
        session_tz="America/New_York",
    )
    utc = add_time_buckets(
        trades,
        bucket_tz="UTC",
        session_tz="America/New_York",
    )
    assert ny["entry_30min_bucket"].iloc[0] == "09:30"
    assert utc["entry_30min_bucket"].iloc[0] == "13:30"


def test_rth_segment_remains_session_based_when_bucket_timezone_changes():
    trades = _make_trades(["2026-06-02 09:30"], [1.0])
    result = add_time_buckets(
        trades,
        bucket_tz="UTC",
        session_tz="America/New_York",
    )
    assert result["entry_rth_segment"].iloc[0] == "rth_open_30m"


def test_add_time_buckets_exchange_tz_call_is_backward_compatible():
    trades = _make_trades(
        ["2026-06-02 09:30", "2026-06-02 11:40"],
        [1.0, -0.5],
    )
    legacy = add_time_buckets(trades, exchange_tz="America/New_York")
    explicit = add_time_buckets(
        trades,
        exchange_tz="America/New_York",
        bucket_tz="America/New_York",
        session_tz="America/New_York",
    )
    pd.testing.assert_frame_equal(
        legacy[_TIME_BUCKET_COLS].reset_index(drop=True),
        explicit[_TIME_BUCKET_COLS].reset_index(drop=True),
    )


def test_grouped_summary_bucket_timezone_changes_labels_not_trade_count():
    trades = _make_trades(
        [
            "2026-06-02 09:30",
            "2026-06-02 10:00",
            "2026-06-02 15:30",
        ],
        [1.0, -1.0, 0.5],
    )
    grouped_ny = summarize_by_group(
        add_time_buckets(
            trades,
            bucket_tz="America/New_York",
            session_tz="America/New_York",
        ),
        "entry_30min_bucket",
    )
    grouped_utc = summarize_by_group(
        add_time_buckets(
            trades,
            bucket_tz="UTC",
            session_tz="America/New_York",
        ),
        "entry_30min_bucket",
    )
    assert set(grouped_ny["entry_30min_bucket"]) != set(grouped_utc["entry_30min_bucket"])
    assert grouped_ny["trade_count"].sum() == grouped_utc["trade_count"].sum() == len(trades)


def test_rth_segment_boundaries():
    """Each boundary timestamp maps to the expected RTH segment."""
    times = [
        "2026-06-02 09:29",  # pre_rth
        "2026-06-02 09:30",  # rth_open_30m
        "2026-06-02 10:00",  # rth_morning
        "2026-06-02 11:30",  # rth_midday
        "2026-06-02 13:30",  # rth_afternoon
        "2026-06-02 15:00",  # rth_power_hour
        "2026-06-02 16:00",  # post_rth
    ]
    expected_segments = [
        "pre_rth",
        "rth_open_30m",
        "rth_morning",
        "rth_midday",
        "rth_afternoon",
        "rth_power_hour",
        "post_rth",
    ]
    ts = pd.to_datetime(times).tz_localize("America/New_York")
    trades = pd.DataFrame({
        "trade_id": list(range(len(times))),
        "entry_timestamp": ts,
        "r_multiple": [0.0] * len(times),
    })
    result = add_time_buckets(trades, exchange_tz="America/New_York")
    assert list(result["entry_rth_segment"]) == expected_segments


def test_add_time_buckets_empty_returns_expected_columns():
    """Empty input must return an empty DataFrame with all bucket columns."""
    result = add_time_buckets(pd.DataFrame())
    assert result.empty
    for col in _TIME_BUCKET_COLS:
        assert col in result.columns, f"Missing column in empty result: {col}"


# ---------------------------------------------------------------------------
# B. summarize_by_group
# ---------------------------------------------------------------------------


def _bucketed_trades() -> pd.DataFrame:
    """Small bucketed trade set for grouping tests."""
    trades = _make_trades(
        [
            "2026-06-02 09:35",  # rth_open_30m
            "2026-06-02 09:50",  # rth_open_30m
            "2026-06-02 11:40",  # rth_midday
        ],
        [1.0, -1.0, 2.0],
    )
    return add_time_buckets(trades)


def test_summarize_by_group_single_column():
    """One-column grouping returns correct per-group metrics."""
    bucketed = _bucketed_trades()
    grouped = summarize_by_group(bucketed, "entry_rth_segment")

    open_row = grouped[grouped["entry_rth_segment"] == "rth_open_30m"].iloc[0]
    assert open_row["trade_count"] == 2
    assert open_row["win_rate"] == pytest.approx(0.5)
    assert open_row["avg_r"] == pytest.approx(0.0)
    assert open_row["total_r"] == pytest.approx(0.0)

    midday_row = grouped[grouped["entry_rth_segment"] == "rth_midday"].iloc[0]
    assert midday_row["trade_count"] == 1
    assert midday_row["avg_r"] == pytest.approx(2.0)


def test_summarize_by_group_two_columns():
    """Two-column grouping produces one row per unique combination."""
    trades = _make_trades(
        [
            "2026-06-02 09:35",
            "2026-06-02 09:50",
            "2026-06-02 11:40",
            "2026-06-02 11:45",
        ],
        [1.0, -1.0, 2.0, -0.5],
    )
    bucketed = add_time_buckets(trades)
    bucketed["direction"] = ["long", "short", "long", "short"]

    grouped = summarize_by_group(bucketed, ["entry_rth_segment", "direction"])

    assert "entry_rth_segment" in grouped.columns
    assert "direction" in grouped.columns
    # Each of the 4 trades has a distinct (segment, direction) combo
    assert len(grouped) == 4
    assert grouped["trade_count"].sum() == 4


def test_sample_warning_true_below_threshold():
    """Groups with fewer trades than min_trades must have sample_warning=True."""
    bucketed = _bucketed_trades()
    grouped = summarize_by_group(bucketed, "entry_rth_segment", min_trades=3)

    # rth_open_30m has 2 trades → below 3 → warning
    open_row = grouped[grouped["entry_rth_segment"] == "rth_open_30m"].iloc[0]
    assert open_row["sample_warning"] == True  # noqa: E712  (numpy bool compatible)

    # rth_midday has 1 trade → below 3 → warning too
    midday_row = grouped[grouped["entry_rth_segment"] == "rth_midday"].iloc[0]
    assert midday_row["sample_warning"] == True  # noqa: E712


def test_group_drawdown_anchored_at_zero():
    """A group with a single losing trade must show max_drawdown_r = 1.0."""
    trades = _make_trades(["2026-06-02 09:35"], [-1.0])
    bucketed = add_time_buckets(trades)
    grouped = summarize_by_group(bucketed, "entry_rth_segment")
    row = grouped.iloc[0]
    assert row["max_drawdown_r"] == pytest.approx(1.0)


def test_summarize_by_group_empty_returns_expected_columns():
    """Empty input must return an empty DataFrame with all expected columns."""
    result = summarize_by_group(pd.DataFrame(), "entry_rth_segment")
    assert result.empty
    expected_cols = ["entry_rth_segment"] + _GROUP_SUMMARY_COLS
    for col in expected_cols:
        assert col in result.columns, f"Missing column in empty result: {col}"


# ---------------------------------------------------------------------------
# C. pivot_time_metric
# ---------------------------------------------------------------------------


def _simple_grouped() -> pd.DataFrame:
    """Minimal grouped DataFrame for pivot tests."""
    return pd.DataFrame({
        "entry_hour_bucket": ["10:00", "09:00", "11:00"],
        "avg_r": [1.0, 2.0, -0.5],
        "trade_count": [3, 5, 2],
    })


def test_pivot_time_metric_one_dimensional_sorts_index():
    """1-D pivot must return values sorted by index."""
    grouped = _simple_grouped()
    pivot = pivot_time_metric(grouped, index_col="entry_hour_bucket", metric="avg_r")
    assert list(pivot.index) == ["09:00", "10:00", "11:00"]
    assert pivot.loc["09:00", "avg_r"] == pytest.approx(2.0)
    assert pivot.loc["10:00", "avg_r"] == pytest.approx(1.0)


def test_pivot_time_metric_two_dimensional_shape():
    """2-D pivot must have segments as rows and directions as columns."""
    grouped = pd.DataFrame({
        "entry_rth_segment": ["rth_open_30m", "rth_open_30m", "rth_midday"],
        "direction": ["long", "short", "long"],
        "avg_r": [1.5, -0.5, 2.0],
    })
    pivot = pivot_time_metric(
        grouped,
        index_col="entry_rth_segment",
        metric="avg_r",
        column_col="direction",
    )
    assert set(pivot.columns) == {"long", "short"}
    assert set(pivot.index) == {"rth_open_30m", "rth_midday"}
    assert pivot.loc["rth_open_30m", "long"] == pytest.approx(1.5)
    assert pivot.loc["rth_open_30m", "short"] == pytest.approx(-0.5)
    assert pivot.loc["rth_midday", "long"] == pytest.approx(2.0)


def test_pivot_time_metric_empty_input():
    """Empty input must return an empty DataFrame without raising."""
    result = pivot_time_metric(pd.DataFrame(), index_col="x", metric="avg_r")
    assert result.empty
