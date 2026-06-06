import numpy as np
import pandas as pd

from thesistester.data.sessions import tag_session
from thesistester.levels.sessions import compute_session_levels


TZ = "America/New_York"


def _sample_two_day_df() -> pd.DataFrame:
    ts = pd.to_datetime(
        [
            "2026-06-01 09:30:00",
            "2026-06-01 09:31:00",
            "2026-06-01 16:30:00",
            "2026-06-02 08:00:00",
            "2026-06-02 09:30:00",
            "2026-06-02 09:31:00",
        ]
    ).tz_localize(TZ)

    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0, 101.0, 102.0, 104.0, 105.0, 106.0],
            "high": [101.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0, 103.0, 104.0, 105.0],
            "close": [100.5, 102.0, 103.0, 104.5, 105.5, 106.5],
            "volume": [10, 11, 12, 13, 14, 15],
        }
    )
    return tag_session(df, "ES")


def test_dopen_uses_first_open_per_calendar_day():
    levels = compute_session_levels(_sample_two_day_df(), instrument="ES")

    day2 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert np.allclose(day2["dOpen"].to_numpy(), [104.0, 104.0, 104.0])


def test_prior_day_levels_use_completed_prior_day_only():
    levels = compute_session_levels(_sample_two_day_df(), instrument="ES")

    day1 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-01").date()]
    assert day1["pdHigh"].isna().all()
    assert day1["pdLow"].isna().all()
    assert day1["pdEQ"].isna().all()

    day2 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert np.allclose(day2["pdHigh"].to_numpy(), [104.0, 104.0, 104.0])
    assert np.allclose(day2["pdLow"].to_numpy(), [99.0, 99.0, 99.0])
    assert np.allclose(day2["pdEQ"].to_numpy(), [101.5, 101.5, 101.5])


def test_rth_open_matches_first_rth_bar_open():
    levels = compute_session_levels(_sample_two_day_df(), instrument="ES")

    day2 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert day2.iloc[1]["timestamp"] == pd.Timestamp("2026-06-02 09:30:00", tz=TZ)
    assert np.isnan(day2.iloc[0]["RTH_Open"])
    assert np.allclose(day2["RTH_Open"].to_numpy()[1:], [105.0, 105.0])


def test_overnight_levels_are_hidden_until_rth_open():
    levels = compute_session_levels(_sample_two_day_df(), instrument="ES")

    day2 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    pre_rth = day2.iloc[0]
    first_rth = day2.iloc[1]

    # Causality-safe semantics: expose completed ONH/ONL only once RTH has started.
    assert np.isnan(pre_rth["ONH"])
    assert np.isnan(pre_rth["ONL"])
    assert first_rth["ONH"] == 105.0
    assert first_rth["ONL"] == 101.0


def test_opening_range_waits_until_window_completes():
    ts = pd.date_range("2026-06-02 09:30:00", periods=8, freq="1min", tz=TZ)
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100, 101, 102, 103, 104, 105, 106, 107],
            "high": [101, 103, 104, 105, 106, 108, 109, 110],
            "low": [99, 100, 101, 102, 103, 104, 105, 106],
            "close": [100.5, 102, 103, 104, 105, 107, 108, 109],
            "volume": [1, 1, 1, 1, 1, 1, 1, 1],
        }
    )
    levels = compute_session_levels(tag_session(df, "ES"), instrument="ES", opening_range_minutes=5)

    pre_complete = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 09:34:00", tz=TZ)].iloc[0]
    post_complete = levels[levels["timestamp"] == pd.Timestamp("2026-06-02 09:35:00", tz=TZ)].iloc[0]

    assert np.isnan(pre_complete["OR_High"])
    assert np.isnan(pre_complete["OR_Low"])
    assert post_complete["OR_High"] == 106
    assert post_complete["OR_Low"] == 99


def test_prev_settlement_falls_back_to_prior_day_close():
    levels = compute_session_levels(_sample_two_day_df(), instrument="ES")

    day2 = levels[levels["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert np.allclose(day2["prevSettlement"].to_numpy(), [103.0, 103.0, 103.0])


def test_causality_columns_match_batch_vs_incremental():
    ts = pd.to_datetime(
        [
            "2026-06-01 09:30:00",
            "2026-06-01 09:31:00",
            "2026-06-01 16:30:00",
            "2026-06-02 08:00:00",
            "2026-06-02 09:30:00",
            "2026-06-02 09:31:00",
            "2026-06-02 09:32:00",
            "2026-06-02 09:33:00",
            "2026-06-02 09:34:00",
            "2026-06-02 09:35:00",
        ]
    ).tz_localize(TZ)
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5],
            "volume": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        }
    )
    tagged = tag_session(df, "ES")
    cols = ["RTH_Open", "ONH", "ONL", "OR_High", "OR_Low", "pdHigh", "pdLow"]

    batch = compute_session_levels(tagged, instrument="ES", opening_range_minutes=5)
    for i in range(len(tagged)):
        incremental = compute_session_levels(tagged.iloc[: i + 1], instrument="ES", opening_range_minutes=5)
        row_batch = batch.iloc[i]
        row_incremental = incremental.iloc[-1]
        for col in cols:
            if np.isnan(row_batch[col]):
                assert np.isnan(row_incremental[col]), f"{col} mismatch at row {i}"
            else:
                assert row_incremental[col] == row_batch[col], f"{col} mismatch at row {i}"
