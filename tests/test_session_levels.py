import numpy as np
import pandas as pd

from thesistester.data.sessions import tag_session
from thesistester.levels.session_date import trading_session_date
from thesistester.levels.sessions import compute_session_levels


TZ = "America/New_York"


def _build_df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([row[0] for row in rows]).tz_localize(TZ),
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [1.0] * len(rows),
        }
    )


def _date(ts: str) -> object:
    return pd.Timestamp(ts).date()


def test_trading_session_date_helper_behavior():
    local_ts = pd.Series(
        pd.to_datetime(
            [
                "2026-06-01 17:59:00",
                "2026-06-01 18:00:00",
                "2026-06-01 23:59:00",
                "2026-06-02 00:00:00",
                "2026-06-02 09:30:00",
            ]
        ).tz_localize(TZ)
    )

    calendar = trading_session_date(local_ts, None)
    assert list(calendar) == [
        _date("2026-06-01"),
        _date("2026-06-01"),
        _date("2026-06-01"),
        _date("2026-06-02"),
        _date("2026-06-02"),
    ]

    session = trading_session_date(local_ts, "18:00")
    assert list(session) == [
        _date("2026-06-01"),
        _date("2026-06-02"),
        _date("2026-06-02"),
        _date("2026-06-02"),
        _date("2026-06-02"),
    ]


def test_dopen_uses_eth_session_start_not_midnight():
    df = _build_df(
        [
            ("2026-06-01 18:00:00", 100.0, 101.0, 99.0, 100.0),
            ("2026-06-01 23:00:00", 101.0, 102.0, 100.0, 101.0),
            ("2026-06-02 00:00:00", 102.0, 103.0, 101.0, 102.0),
            ("2026-06-02 08:00:00", 103.0, 104.0, 102.0, 103.0),
            ("2026-06-02 09:30:00", 104.0, 105.0, 103.0, 104.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")

    assert np.allclose(levels["dOpen"].to_numpy(), [100.0, 100.0, 100.0, 100.0, 100.0])


def test_prior_day_structural_levels_use_completed_trading_session():
    df = _build_df(
        [
            ("2026-06-01 18:00:00", 100.0, 101.0, 99.0, 100.0),
            ("2026-06-02 09:30:00", 110.0, 120.0, 109.0, 115.0),
            ("2026-06-02 15:59:00", 116.0, 121.0, 108.0, 119.0),
            ("2026-06-02 18:00:00", 200.0, 201.0, 198.0, 199.0),
            ("2026-06-03 09:30:00", 210.0, 220.0, 207.0, 215.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")
    session2 = levels[levels["timestamp"] >= pd.Timestamp("2026-06-02 18:00:00", tz=TZ)]

    assert np.allclose(session2["pdOpen"].to_numpy(), [100.0, 100.0])
    assert np.allclose(session2["pdHigh"].to_numpy(), [121.0, 121.0])
    assert np.allclose(session2["pdLow"].to_numpy(), [99.0, 99.0])
    assert np.allclose(session2["pdEQ"].to_numpy(), [110.0, 110.0])


def test_weekly_levels_use_trading_session_week_keys():
    df = _build_df(
        [
            ("2026-06-05 09:30:00", 300.0, 350.0, 290.0, 340.0),
            ("2026-06-05 15:59:00", 320.0, 360.0, 280.0, 330.0),
            ("2026-06-07 18:00:00", 400.0, 410.0, 390.0, 405.0),
            ("2026-06-08 09:30:00", 420.0, 430.0, 415.0, 425.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")
    new_week = levels[levels["timestamp"] >= pd.Timestamp("2026-06-07 18:00:00", tz=TZ)]

    assert np.allclose(new_week["wOpen"].to_numpy(), [400.0, 400.0])
    assert np.allclose(new_week["pwOpen"].to_numpy(), [300.0, 300.0])
    assert np.allclose(new_week["pwHigh"].to_numpy(), [360.0, 360.0])
    assert np.allclose(new_week["pwLow"].to_numpy(), [280.0, 280.0])
    assert np.allclose(new_week["pwEQ"].to_numpy(), [320.0, 320.0])


def test_monthly_levels_use_trading_session_month_keys():
    df = _build_df(
        [
            ("2026-06-30 09:30:00", 500.0, 550.0, 490.0, 540.0),
            ("2026-06-30 15:59:00", 520.0, 560.0, 480.0, 530.0),
            ("2026-06-30 18:00:00", 600.0, 610.0, 590.0, 605.0),
            ("2026-07-01 09:30:00", 620.0, 630.0, 615.0, 625.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")
    new_month = levels[levels["timestamp"] >= pd.Timestamp("2026-06-30 18:00:00", tz=TZ)]

    assert np.allclose(new_month["mOpen"].to_numpy(), [600.0, 600.0])
    assert np.allclose(new_month["pmOpen"].to_numpy(), [500.0, 500.0])
    assert np.allclose(new_month["pmHigh"].to_numpy(), [560.0, 560.0])
    assert np.allclose(new_month["pmLow"].to_numpy(), [480.0, 480.0])
    assert np.allclose(new_month["pmEQ"].to_numpy(), [520.0, 520.0])


def test_opening_range_not_visible_on_new_session_eth_bar():
    df = _build_df(
        [
            ("2026-06-02 18:00:00", 100.0, 101.0, 99.0, 100.0),
            ("2026-06-03 09:30:00", 101.0, 103.0, 100.0, 102.0),
            ("2026-06-03 09:31:00", 102.0, 104.0, 101.0, 103.0),
            ("2026-06-03 09:32:00", 103.0, 105.0, 102.0, 104.0),
            ("2026-06-03 09:33:00", 104.0, 106.0, 103.0, 105.0),
            ("2026-06-03 09:34:00", 105.0, 107.0, 104.0, 106.0),
            ("2026-06-03 09:35:00", 106.0, 108.0, 105.0, 107.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES", opening_range_minutes=5)

    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-02 18:00:00", tz=TZ), "OR_High"]).all()
    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-02 18:00:00", tz=TZ), "OR_Low"]).all()
    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-03 09:34:00", tz=TZ), "OR_High"]).all()
    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-03 09:34:00", tz=TZ), "OR_Low"]).all()
    row = levels[levels["timestamp"] == pd.Timestamp("2026-06-03 09:35:00", tz=TZ)].iloc[0]
    assert row["OR_High"] == 107.0
    assert row["OR_Low"] == 100.0


def test_opening_range_availability_is_clock_based_not_first_rth_bar():
    # First RTH bar is 09:31 (09:30 missing due to data gap).
    # Clock-based OR (5-min) completes at 09:35 ET regardless.
    # OR should be visible at 09:35, NOT at 09:36 (which is what first-bar+offset gives).
    # OR values are computed from bars inside [09:30, 09:35) that exist: 09:31–09:34.
    df = _build_df(
        [
            ("2026-06-02 18:00:00", 90.0, 91.0, 89.0, 90.0),
            ("2026-06-03 09:31:00", 100.0, 103.0, 100.0, 102.0),
            ("2026-06-03 09:32:00", 101.0, 104.0, 101.0, 103.0),
            ("2026-06-03 09:33:00", 102.0, 105.0, 102.0, 104.0),
            ("2026-06-03 09:34:00", 103.0, 106.0, 103.0, 105.0),
            ("2026-06-03 09:35:00", 104.0, 107.0, 104.0, 106.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES", opening_range_minutes=5)

    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-03 09:34:00", tz=TZ), "OR_High"]).all()
    assert pd.isna(levels.loc[levels["timestamp"] == pd.Timestamp("2026-06-03 09:34:00", tz=TZ), "OR_Low"]).all()

    row_35 = levels[levels["timestamp"] == pd.Timestamp("2026-06-03 09:35:00", tz=TZ)].iloc[0]
    assert row_35["OR_High"] == 106.0  # max high of 09:31–09:34 bars
    assert row_35["OR_Low"] == 100.0   # min low of 09:31–09:34 bars


def test_rth_open_causality_is_preserved():
    df = _build_df(
        [
            ("2026-06-01 18:00:00", 100.0, 101.0, 99.0, 100.0),
            ("2026-06-02 08:00:00", 101.0, 102.0, 100.0, 101.0),
            ("2026-06-02 09:30:00", 102.0, 103.0, 101.0, 102.0),
            ("2026-06-02 09:31:00", 103.0, 104.0, 102.0, 103.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")

    pre_rth = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 08:00:00", tz=TZ)].iloc[0]
    first_rth = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 09:30:00", tz=TZ)].iloc[0]
    later_rth = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 09:31:00", tz=TZ)].iloc[0]
    assert np.isnan(pre_rth["RTH_Open"])
    assert first_rth["RTH_Open"] == 102.0
    assert later_rth["RTH_Open"] == 102.0


def test_overnight_levels_exclude_post_rth_contamination_and_stay_hidden_pre_rth():
    df = _build_df(
        [
            ("2026-06-02 16:30:00", 90.0, 999.0, 1.0, 90.0),
            ("2026-06-02 18:00:00", 100.0, 110.0, 100.0, 105.0),
            ("2026-06-03 08:00:00", 106.0, 120.0, 95.0, 100.0),
            ("2026-06-03 09:30:00", 110.0, 130.0, 90.0, 120.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")

    assert np.isnan(levels.iloc[1]["ONH"])
    assert np.isnan(levels.iloc[2]["ONH"])
    assert np.isnan(levels.iloc[1]["ONL"])
    assert np.isnan(levels.iloc[2]["ONL"])

    first_rth = levels.iloc[3]
    assert first_rth["ONH"] == 120.0
    assert first_rth["ONL"] == 95.0


def test_prev_settlement_fallback_uses_prior_rth_close_not_post_rth():
    # Previous session has RTH close at 15:59 (close=111.0) and a post-RTH/pre-ETH bar
    # at 16:59 (close=999.0). The new session starts at 18:00.
    # prevSettlement on the new session must be 111.0 (last RTH close), not 999.0.
    df = _build_df(
        [
            ("2026-06-01 18:00:00", 100.0, 101.0, 99.0, 100.0),
            ("2026-06-02 15:59:00", 110.0, 112.0, 109.0, 111.0),
            ("2026-06-02 16:59:00", 120.0, 125.0, 119.0, 999.0),
            ("2026-06-02 18:00:00", 200.0, 201.0, 198.0, 199.0),
        ]
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES")
    new_session_bar = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 18:00:00", tz=TZ)].iloc[0]
    assert new_session_bar["prevSettlement"] == 111.0, (
        f"prevSettlement should be last RTH close (111.0), not post-RTH bar (999.0), got {new_session_bar['prevSettlement']}"
    )

    # When an explicit settlement value exists for the completed prior trading session,
    # use it instead of the RTH close.
    with_settlement = tag_session(df.copy(), "ES")
    with_settlement["settlement"] = [np.nan, np.nan, 124.5, np.nan]
    levels_with_settlement = compute_session_levels(with_settlement, instrument="ES")
    new_session_bar = levels_with_settlement[levels_with_settlement["timestamp"] == pd.Timestamp("2026-06-02 18:00:00", tz=TZ)].iloc[0]
    assert new_session_bar["prevSettlement"] == 124.5


def test_batch_vs_incremental_causality_matches_with_eth_session_boundaries():
    df = _build_df(
        [
            ("2026-05-31 18:00:00", 90.0, 91.0, 89.0, 90.5),
            ("2026-06-01 09:30:00", 92.0, 94.0, 91.0, 93.0),
            ("2026-06-01 23:59:00", 94.0, 95.0, 93.0, 94.5),
            ("2026-06-02 00:00:00", 95.0, 96.0, 94.0, 95.5),
            ("2026-06-02 08:00:00", 96.0, 97.0, 95.0, 96.5),
            ("2026-06-02 09:30:00", 97.0, 99.0, 96.0, 98.0),
            ("2026-06-02 09:35:00", 98.0, 100.0, 97.0, 99.0),
            ("2026-06-02 18:00:00", 120.0, 121.0, 119.0, 120.5),
        ]
    )
    tagged = tag_session(df, "ES")
    batch = compute_session_levels(tagged, instrument="ES", opening_range_minutes=5)
    cols = [
        "dOpen",
        "wOpen",
        "mOpen",
        "pdOpen",
        "pdHigh",
        "pdLow",
        "pdEQ",
        "pwOpen",
        "pwHigh",
        "pwLow",
        "pwEQ",
        "pmOpen",
        "pmHigh",
        "pmLow",
        "pmEQ",
        "RTH_Open",
        "ONH",
        "ONL",
        "OR_High",
        "OR_Low",
        "prevSettlement",
    ]

    for i in range(len(tagged)):
        incremental = compute_session_levels(tagged.iloc[: i + 1], instrument="ES", opening_range_minutes=5)
        row_batch = batch.iloc[i]
        row_incremental = incremental.iloc[-1]
        for col in cols:
            if pd.isna(row_batch[col]):
                assert pd.isna(row_incremental[col]), f"{col} mismatch at row {i}"
            else:
                assert row_incremental[col] == row_batch[col], f"{col} mismatch at row {i}"
