"""Phase 2 — prev30mVWAP early-window hit R analytics (plan §10.7)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.analytics.prev30m_vwap_hit import (
    HIT_M1_AT_ENTRY,
    HIT_M5_AT_ENTRY,
    attach_prev30m_hit_flags,
    filter_prev30m_trades,
    prev30m_hit_contingency,
    prev30m_hit_r_summary,
    summarize_r_by_hit_flag,
)
from thesistester.levels import compute_prev30m_vwap_levels
from thesistester.levels.prev30m_vwap import COL_HIT_M1, COL_PREV30M_VWAP


TZ = "America/New_York"


def _bar(ts: pd.Timestamp, *, high: float, low: float, close: float, volume: float = 10.0) -> dict:
    return {
        "timestamp": ts,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _levels_with_hits() -> pd.DataFrame:
    """Two brackets: freeze at 18:30; hit_m1=1 and hit_m5=1 after windows complete."""
    rows = []
    for i in range(30):
        ts = pd.Timestamp("2026-06-01 18:00", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_bar(ts, high=100, low=99, close=99.5))
    # Bracket 1: touch at 18:30 (in m1 window), then miss
    rows.append(_bar(pd.Timestamp("2026-06-01 18:30", tz=TZ), high=100, low=99, close=99.5))
    for i in range(1, 10):
        ts = pd.Timestamp("2026-06-01 18:30", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_bar(ts, high=110, low=109, close=109.5))
    ohlcv = pd.DataFrame(rows)
    hits = compute_prev30m_vwap_levels(ohlcv, instrument="ES", enabled=True)
    return ohlcv.join(hits)


def _trades(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# §10.7
# ---------------------------------------------------------------------------


def test_empty_trades_safe():
    levels = _levels_with_hits()
    summary = prev30m_hit_r_summary(pd.DataFrame(), levels, instrument="ES")
    assert summary["available"] is False or summary["trade_count"] == 0
    assert summarize_r_by_hit_flag(pd.DataFrame(), HIT_M1_AT_ENTRY).empty
    assert prev30m_hit_contingency(pd.DataFrame()).empty
    assert attach_prev30m_hit_flags(pd.DataFrame(), levels).empty or list(
        attach_prev30m_hit_flags(pd.DataFrame(columns=["entry_timestamp"]), levels).columns
    )


def test_empty_trades_none_safe():
    levels = _levels_with_hits()
    summary = prev30m_hit_r_summary(None, levels, instrument="ES")  # type: ignore[arg-type]
    assert summary["trade_count"] == 0
    assert summary["by_hit_m1"].empty
    assert summary["by_hit_m5"].empty
    assert summary["contingency"].empty


def test_grouped_r_by_hit_m1_and_m5():
    levels = _levels_with_hits()
    # Entry in bracket 1 after both windows finalized (18:35+) → hit flags 1/1
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP|OR_High",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:37", tz=TZ),
                "r_multiple": 2.0,
                "level_names": "prev30mVWAP",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:38", tz=TZ),
                "r_multiple": -1.0,
                "level_names": "prev30mVWAP",
            },
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["available"] is True
    assert summary["trade_count"] == 3

    by_m1 = summary["by_hit_m1"]
    assert not by_m1.empty
    assert set(by_m1.columns) >= {"trade_count", "avg_r", "median_r"}
    hit_row = by_m1[by_m1[HIT_M1_AT_ENTRY] == 1.0].iloc[0]
    assert hit_row["trade_count"] == 3
    assert hit_row["avg_r"] == pytest.approx((1.0 + 2.0 - 1.0) / 3.0)
    assert hit_row["median_r"] == pytest.approx(1.0)

    by_m5 = summary["by_hit_m5"]
    assert not by_m5.empty
    assert by_m5[by_m5[HIT_M5_AT_ENTRY] == 1.0].iloc[0]["trade_count"] == 3


def test_joint_contingency_counts():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 0.5,
                "level_names": "prev30mVWAP",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:37", tz=TZ),
                "r_multiple": -0.5,
                "level_names": "prev30mVWAP",
            },
        ]
    )
    flagged = attach_prev30m_hit_flags(trades, levels, instrument="ES")
    contingency = prev30m_hit_contingency(flagged)
    assert not contingency.empty
    assert contingency["trade_count"].sum() == 2
    # Both finalized hits are 1 → single joint cell
    assert contingency.iloc[0][HIT_M1_AT_ENTRY] == pytest.approx(1.0)
    assert contingency.iloc[0][HIT_M5_AT_ENTRY] == pytest.approx(1.0)


def test_filters_to_prev30m_setup_trades_only():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 3.0,
                "level_names": "OR_High",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:37", tz=TZ),
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            },
        ]
    )
    scoped = filter_prev30m_trades(trades)
    assert len(scoped) == 1
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["trade_count"] == 1


def test_uses_finalized_bracket_flags_not_in_window_nan():
    """Entry at 18:30 (in-window NaN on levels) still gets finalized flag via lookup."""
    levels = _levels_with_hits()
    # Confirm levels row at 18:30 has NaN hit_m1 (PIT in-window)
    row_1830 = levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-01 18:30", tz=TZ)].iloc[0]
    assert np.isnan(row_1830[COL_HIT_M1])

    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:30", tz=TZ),
                "r_multiple": 1.5,
                "level_names": COL_PREV30M_VWAP,
            }
        ]
    )
    flagged = attach_prev30m_hit_flags(trades, levels, instrument="ES")
    # Finalized bracket flag is 1 even though the entry bar itself was NaN on levels
    assert flagged.iloc[0][HIT_M1_AT_ENTRY] == pytest.approx(1.0)
    assert flagged.iloc[0][HIT_M5_AT_ENTRY] == pytest.approx(1.0)


def test_missing_hit_columns_on_levels_unavailable():
    levels = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-06-01 18:30", tz=TZ)],
            "close": [100.0],
        }
    )
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            }
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["available"] is False


def test_no_level_names_column_analyzes_all_trades():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 1.0,
            }
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["trade_count"] == 1


def test_unavailable_when_no_finalized_flags_attach():
    """Missing entry timestamps must not look like a successful empty analysis."""
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            }
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["available"] is False
    assert summary["trade_count"] == 0
    assert summary["by_hit_m1"].empty
    assert summary["by_hit_m5"].empty


def test_timezone_naive_entry_is_unavailable_not_crash():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36"),  # naive
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            }
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    assert summary["available"] is False
    assert summary["trade_count"] == 0


def test_contingency_matches_r_group_universe_when_r_nan():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:37", tz=TZ),
                "r_multiple": np.nan,
                "level_names": "prev30mVWAP",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:38", tz=TZ),
                "r_multiple": -0.5,
                "level_names": "prev30mVWAP",
            },
        ]
    )
    summary = prev30m_hit_r_summary(trades, levels, instrument="ES")
    # Analyzable by flag attachment (all three have finalized flags).
    assert summary["available"] is True
    assert summary["trade_count"] == 3
    # R-group and contingency share the R-valid universe (2 trades).
    by_m1 = summary["by_hit_m1"]
    assert by_m1[by_m1[HIT_M1_AT_ENTRY] == 1.0].iloc[0]["trade_count"] == 2
    assert summary["contingency"]["trade_count"].sum() == 2


def test_attach_preserves_trade_index():
    levels = _levels_with_hits()
    trades = _trades(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-06-01 18:36", tz=TZ),
                "r_multiple": 1.0,
                "level_names": "prev30mVWAP",
            }
        ]
    )
    trades.index = pd.Index(["trade-A"], name="trade_id")
    flagged = attach_prev30m_hit_flags(trades, levels, instrument="ES")
    assert list(flagged.index) == ["trade-A"]
    assert flagged.index.name == "trade_id"


def test_summarize_skips_zero_count_flag_groups():
    trades = _trades(
        [
            {
                HIT_M1_AT_ENTRY: 1.0,
                "r_multiple": np.nan,
            }
        ]
    )
    by_m1 = summarize_r_by_hit_flag(trades, HIT_M1_AT_ENTRY)
    assert by_m1.empty
