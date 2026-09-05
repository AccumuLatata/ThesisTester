"""R3 point-in-time (PIT) regression tests — future-shock pattern.

Each test follows the same pattern:
  1. Build a base dataset through timestamp T.
  2. Compute levels/signals through T.
  3. Append "future shock" bars with extreme high/low/volume values.
  4. Recompute on the extended dataset.
  5. Assert that all outputs at or before T are unchanged.

This verifies that no future data leaks backward into historical bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from datetime import date

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import TickChunk
from thesistester.data.sessions import tag_session
from thesistester.engine.anchor_confluence import detect_anchor_confluence_zones
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.engine.naked import flag_naked_levels
from thesistester.engine.signals import generate_signals
from thesistester.levels import compute_indicator_levels, compute_profile_levels
from thesistester.levels.session_date import trading_session_date
from thesistester.levels.sessions import compute_session_levels
from thesistester.levels.tick_vap import build_prior_profile_table


TZ = "America/New_York"
TICK = 0.25  # ES tick size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ohlcv_bar(
    ts: pd.Timestamp, open_: float, high: float, low: float, close: float, vol: float
) -> dict:
    return {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close, "volume": vol}


def _build_df(bars: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(bars)


def _rth_ts(date: str, time: str) -> pd.Timestamp:
    """Return a tz-aware timestamp in America/New_York."""
    return pd.Timestamp(f"{date} {time}", tz=TZ)


def _standard_bars(start_date: str, n: int, base_price: float = 4000.0) -> list[dict]:
    """Generate n 1-minute RTH bars starting at 09:30 on start_date."""
    bars = []
    ts = pd.Timestamp(f"{start_date} 09:30:00", tz=TZ)
    for i in range(n):
        p = base_price + i * 0.5
        bars.append(
            _ohlcv_bar(ts + pd.Timedelta(minutes=i), p, p + 0.25, p - 0.25, p + 0.1, 100.0 + i)
        )
    return bars


def _extreme_future_bars(after_ts: pd.Timestamp, n: int = 5) -> list[dict]:
    """Generate n bars immediately after after_ts with extreme prices/volume."""
    bars = []
    for i in range(n):
        ts = after_ts + pd.Timedelta(minutes=i + 1)
        bars.append(_ohlcv_bar(ts, 99999.0, 199999.0, 1.0, 99999.0, 9_999_999.0))
    return bars


# ---------------------------------------------------------------------------
# A. Prior session levels — future-shock test
# ---------------------------------------------------------------------------


def test_prior_session_levels_future_shock():
    """pdHigh/pdLow/pdOpen/pdEQ at or before T must not change after future bars are added."""
    # Day 1 bars: 09:30..10:30 (61 bars)
    day1_bars = _standard_bars("2026-06-02", 61, base_price=4000.0)
    # Day 2 bars: 09:30..10:30
    day2_bars = _standard_bars("2026-06-03", 61, base_price=4100.0)

    base = _build_df(day1_bars + day2_bars)
    base = tag_session(base)
    result_base = compute_session_levels(base, instrument="ES")

    # T = last bar of day 2
    T = base["timestamp"].iloc[-1]
    out_before = result_base[result_base["timestamp"] <= T][
        ["timestamp", "pdHigh", "pdLow", "pdOpen", "pdEQ"]
    ].copy()

    # Future shock: add day 3 with extreme values
    day3_extreme = _extreme_future_bars(T, n=10)
    extended = _build_df(day1_bars + day2_bars + day3_extreme)
    extended = tag_session(extended)
    result_extended = compute_session_levels(extended, instrument="ES")

    out_after = result_extended[result_extended["timestamp"] <= T][
        ["timestamp", "pdHigh", "pdLow", "pdOpen", "pdEQ"]
    ].copy()

    pd.testing.assert_frame_equal(
        out_before.reset_index(drop=True),
        out_after.reset_index(drop=True),
        check_exact=False,
    )


def test_prth_high_low_future_shock():
    """pRTH_High/pRTH_Low at or before T must not change after future bars are added."""
    day1_bars = _standard_bars("2026-06-02", 61, base_price=4000.0)
    day2_bars = _standard_bars("2026-06-03", 61, base_price=4100.0)

    base = tag_session(_build_df(day1_bars + day2_bars))
    result_base = compute_session_levels(base, instrument="ES")

    T = base["timestamp"].iloc[-1]
    out_before = result_base[result_base["timestamp"] <= T][
        ["timestamp", "pRTH_High", "pRTH_Low", "pRTH_Open"]
    ].copy()

    day3_extreme = _extreme_future_bars(T, n=10)
    extended = tag_session(_build_df(day1_bars + day2_bars + day3_extreme))
    result_extended = compute_session_levels(extended, instrument="ES")

    out_after = result_extended[result_extended["timestamp"] <= T][
        ["timestamp", "pRTH_High", "pRTH_Low", "pRTH_Open"]
    ].copy()

    pd.testing.assert_frame_equal(
        out_before.reset_index(drop=True),
        out_after.reset_index(drop=True),
        check_exact=False,
    )


def test_prth_high_low_available_from_next_session_eth_open():
    """pRTH_High/Low are visible from the first bar of the next session (ungated)."""
    bars = [
        _ohlcv_bar(
            pd.Timestamp("2026-06-02 09:30:00", tz=TZ), 4000.0, 4050.0, 3990.0, 4020.0, 100.0
        ),
        _ohlcv_bar(
            pd.Timestamp("2026-06-02 15:59:00", tz=TZ), 4020.0, 4060.0, 3980.0, 4030.0, 90.0
        ),
        _ohlcv_bar(
            pd.Timestamp("2026-06-02 18:00:00", tz=TZ), 4100.0, 4110.0, 4090.0, 4105.0, 50.0
        ),
        _ohlcv_bar(
            pd.Timestamp("2026-06-03 09:30:00", tz=TZ), 4120.0, 4130.0, 4115.0, 4125.0, 80.0
        ),
    ]
    result = compute_session_levels(tag_session(_build_df(bars)), instrument="ES")

    during_prior = result[result["timestamp"] <= pd.Timestamp("2026-06-02 15:59:00", tz=TZ)]
    assert during_prior["pRTH_High"].isna().all()
    assert during_prior["pRTH_Low"].isna().all()

    next_session = result[result["timestamp"] >= pd.Timestamp("2026-06-02 18:00:00", tz=TZ)]
    assert np.allclose(next_session["pRTH_High"].to_numpy(), [4060.0] * len(next_session))
    assert np.allclose(next_session["pRTH_Low"].to_numpy(), [3980.0] * len(next_session))


def test_rth_open_not_visible_before_rth():
    """RTH_Open must be NaN for ETH bars and available from the first RTH bar."""
    # ETH bar at 06:00, then RTH bars starting at 09:30
    eth_ts = pd.Timestamp("2026-06-02 06:00:00", tz=TZ)
    rth_ts_first = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)

    bars = [
        _ohlcv_bar(eth_ts, 4000.0, 4001.0, 3999.0, 4000.5, 50.0),
        _ohlcv_bar(rth_ts_first, 4002.0, 4003.0, 4001.0, 4002.5, 200.0),
        _ohlcv_bar(rth_ts_first + pd.Timedelta(minutes=1), 4003.0, 4004.0, 4002.0, 4003.5, 180.0),
    ]
    df = _build_df(bars)
    df = tag_session(df)
    result = compute_session_levels(df, instrument="ES")

    eth_row = result[result["timestamp"] == eth_ts].iloc[0]
    rth_row = result[result["timestamp"] == rth_ts_first].iloc[0]

    assert pd.isna(eth_row["RTH_Open"]), "RTH_Open must be NaN before RTH starts"
    assert rth_row["RTH_Open"] == pytest.approx(4002.0), "RTH_Open must equal first RTH bar open"


def test_overnight_levels_gated():
    """ONH/ONL must be NaN during ETH and available from first RTH bar only."""
    eth_ts = pd.Timestamp("2026-06-02 18:00:00", tz=TZ)  # overnight start
    eth_ts2 = pd.Timestamp("2026-06-03 06:00:00", tz=TZ)
    rth_ts_first = pd.Timestamp("2026-06-03 09:30:00", tz=TZ)

    bars = [
        _ohlcv_bar(eth_ts, 4000.0, 4050.0, 3950.0, 4010.0, 100.0),
        _ohlcv_bar(eth_ts2, 4010.0, 4060.0, 3990.0, 4020.0, 80.0),
        _ohlcv_bar(rth_ts_first, 4020.0, 4025.0, 4015.0, 4022.0, 300.0),
    ]
    df = _build_df(bars)
    df = tag_session(df)
    result = compute_session_levels(df, instrument="ES")

    eth_row_1 = result[result["timestamp"] == eth_ts].iloc[0]
    eth_row_2 = result[result["timestamp"] == eth_ts2].iloc[0]
    rth_row = result[result["timestamp"] == rth_ts_first].iloc[0]

    assert pd.isna(eth_row_1["ONH"]), "ONH must be NaN during ETH"
    assert pd.isna(eth_row_2["ONH"]), "ONH must still be NaN during ETH"
    assert not pd.isna(rth_row["ONH"]), "ONH must be available at first RTH bar"
    assert rth_row["ONH"] == pytest.approx(4060.0)
    assert rth_row["ONL"] == pytest.approx(3950.0)


def test_opening_range_not_visible_before_or_end():
    """OR_High/OR_Low must be NaN before the opening-range window has closed."""
    rth_start = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)
    or_end = pd.Timestamp("2026-06-02 10:00:00", tz=TZ)  # 30-min OR

    bars = []
    for i in range(35):
        ts = rth_start + pd.Timedelta(minutes=i)
        p = 4000.0 + i
        bars.append(_ohlcv_bar(ts, p, p + 0.5, p - 0.5, p + 0.25, 100.0))

    df = _build_df(bars)
    df = tag_session(df)
    result = compute_session_levels(df, instrument="ES", opening_range_minutes=30)

    # All bars before or_end must have NaN OR levels
    before = result[result["timestamp"] < or_end]
    assert before["OR_High"].isna().all(), "OR_High must be NaN before OR window ends"
    assert before["OR_Low"].isna().all(), "OR_Low must be NaN before OR window ends"

    # First bar at or_end and later must have valid OR levels
    at_or_after = result[result["timestamp"] >= or_end]
    assert not at_or_after["OR_High"].isna().all(), "OR_High must be available after OR ends"


def test_asia_levels_gated_until_close():
    """AsiaHigh/AsiaLow must be NaN during Asia and available from asia_end clock gate."""
    asia_start = pd.Timestamp("2026-06-02 20:00:00", tz=TZ)
    asia_mid = pd.Timestamp("2026-06-02 22:30:00", tz=TZ)
    asia_close = pd.Timestamp("2026-06-03 00:00:00", tz=TZ)
    pre_rth = pd.Timestamp("2026-06-03 08:00:00", tz=TZ)

    bars = [
        _ohlcv_bar(asia_start, 4000.0, 4050.0, 3990.0, 4010.0, 100.0),
        _ohlcv_bar(asia_mid, 4010.0, 4060.0, 3980.0, 4020.0, 80.0),
        _ohlcv_bar(asia_close, 4020.0, 4025.0, 4015.0, 4022.0, 90.0),
        _ohlcv_bar(pre_rth, 4022.0, 4030.0, 4010.0, 4028.0, 70.0),
    ]
    df = tag_session(_build_df(bars))
    result = compute_session_levels(df, instrument="ES")

    during = result[result["timestamp"] < asia_close]
    assert during["AsiaHigh"].isna().all(), "AsiaHigh must be NaN during Asia"
    assert during["AsiaLow"].isna().all(), "AsiaLow must be NaN during Asia"

    at_close = result[result["timestamp"] == asia_close].iloc[0]
    assert at_close["AsiaHigh"] == pytest.approx(4060.0)
    assert at_close["AsiaLow"] == pytest.approx(3980.0)

    later = result[result["timestamp"] == pre_rth].iloc[0]
    assert later["AsiaHigh"] == pytest.approx(4060.0)
    assert later["AsiaLow"] == pytest.approx(3980.0)


def test_asia_levels_future_shock_append_does_not_change_prior():
    """Appending extreme post-Asia bars must not change AsiaHigh/AsiaLow already emitted."""
    asia_start = pd.Timestamp("2026-06-02 20:00:00", tz=TZ)
    asia_mid = pd.Timestamp("2026-06-02 22:00:00", tz=TZ)
    asia_close = pd.Timestamp("2026-06-03 00:00:00", tz=TZ)

    base_bars = [
        _ohlcv_bar(asia_start, 4000.0, 4050.0, 3990.0, 4010.0, 100.0),
        _ohlcv_bar(asia_mid, 4010.0, 4060.0, 3980.0, 4020.0, 80.0),
        _ohlcv_bar(asia_close, 4020.0, 4025.0, 4015.0, 4022.0, 90.0),
    ]
    base = tag_session(_build_df(base_bars))
    r_base = compute_session_levels(base, instrument="ES")

    shock = _ohlcv_bar(pd.Timestamp("2026-06-03 09:30:00", tz=TZ), 5000.0, 9999.0, 1.0, 5000.0, 1e9)
    extended = tag_session(_build_df(base_bars + [shock]))
    r_ext = compute_session_levels(extended, instrument="ES")

    base_cut = r_base[r_base["timestamp"] <= asia_close].reset_index(drop=True)
    ext_cut = r_ext[r_ext["timestamp"] <= asia_close].reset_index(drop=True)
    pd.testing.assert_series_equal(base_cut["AsiaHigh"], ext_cut["AsiaHigh"], check_names=False)
    pd.testing.assert_series_equal(base_cut["AsiaLow"], ext_cut["AsiaLow"], check_names=False)


def test_london_levels_gated_until_close():
    """LondonHigh/LondonLow must be NaN during London and available from london_end clock gate."""
    london_start = pd.Timestamp("2026-06-03 02:00:00", tz=TZ)
    london_mid = pd.Timestamp("2026-06-03 03:30:00", tz=TZ)
    london_close = pd.Timestamp("2026-06-03 05:00:00", tz=TZ)
    pre_rth = pd.Timestamp("2026-06-03 08:00:00", tz=TZ)

    bars = [
        _ohlcv_bar(london_start, 4000.0, 4050.0, 3990.0, 4010.0, 100.0),
        _ohlcv_bar(london_mid, 4010.0, 4060.0, 3980.0, 4020.0, 80.0),
        _ohlcv_bar(london_close, 4020.0, 4025.0, 4015.0, 4022.0, 90.0),
        _ohlcv_bar(pre_rth, 4022.0, 4030.0, 4010.0, 4028.0, 70.0),
    ]
    df = tag_session(_build_df(bars))
    result = compute_session_levels(df, instrument="ES")

    during = result[result["timestamp"] < london_close]
    assert during["LondonHigh"].isna().all(), "LondonHigh must be NaN during London"
    assert during["LondonLow"].isna().all(), "LondonLow must be NaN during London"

    at_close = result[result["timestamp"] == london_close].iloc[0]
    assert at_close["LondonHigh"] == pytest.approx(4060.0)
    assert at_close["LondonLow"] == pytest.approx(3980.0)

    later = result[result["timestamp"] == pre_rth].iloc[0]
    assert later["LondonHigh"] == pytest.approx(4060.0)
    assert later["LondonLow"] == pytest.approx(3980.0)


def test_london_levels_future_shock_append_does_not_change_prior():
    """Appending extreme post-London bars must not change LondonHigh/LondonLow already emitted."""
    london_start = pd.Timestamp("2026-06-03 02:00:00", tz=TZ)
    london_mid = pd.Timestamp("2026-06-03 03:30:00", tz=TZ)
    london_close = pd.Timestamp("2026-06-03 05:00:00", tz=TZ)

    base_bars = [
        _ohlcv_bar(london_start, 4000.0, 4050.0, 3990.0, 4010.0, 100.0),
        _ohlcv_bar(london_mid, 4010.0, 4060.0, 3980.0, 4020.0, 80.0),
        _ohlcv_bar(london_close, 4020.0, 4025.0, 4015.0, 4022.0, 90.0),
    ]
    base = tag_session(_build_df(base_bars))
    r_base = compute_session_levels(base, instrument="ES")

    shock = _ohlcv_bar(pd.Timestamp("2026-06-03 09:30:00", tz=TZ), 5000.0, 9999.0, 1.0, 5000.0, 1e9)
    extended = tag_session(_build_df(base_bars + [shock]))
    r_ext = compute_session_levels(extended, instrument="ES")

    base_cut = r_base[r_base["timestamp"] <= london_close].reset_index(drop=True)
    ext_cut = r_ext[r_ext["timestamp"] <= london_close].reset_index(drop=True)
    pd.testing.assert_series_equal(base_cut["LondonHigh"], ext_cut["LondonHigh"], check_names=False)
    pd.testing.assert_series_equal(base_cut["LondonLow"], ext_cut["LondonLow"], check_names=False)


# ---------------------------------------------------------------------------
# A. Prior session levels — future shock test (pdHigh unchanged when future day added)
# ---------------------------------------------------------------------------


def test_prior_session_pdHigh_unchanged_on_future_day_append():
    """pdHigh for day D must not change when a day D+1 with extreme prices is appended."""
    day1 = _standard_bars("2026-06-02", 30, base_price=4000.0)
    day2 = _standard_bars("2026-06-03", 30, base_price=4100.0)

    base = _build_df(day1 + day2)
    base = tag_session(base)
    r_base = compute_session_levels(base, instrument="ES")

    # Day-2 bars' pdHigh should equal day-1's high
    day2_rows = r_base[r_base["timestamp"].dt.date == pd.Timestamp("2026-06-03").date()]
    pdHigh_day2 = day2_rows["pdHigh"].iloc[0]

    # Append extreme day 3
    T = base["timestamp"].iloc[-1]
    day3_extreme = _extreme_future_bars(T, n=30)
    extended = _build_df(day1 + day2 + day3_extreme)
    extended = tag_session(extended)
    r_ext = compute_session_levels(extended, instrument="ES")

    day2_rows_ext = r_ext[r_ext["timestamp"].dt.date == pd.Timestamp("2026-06-03").date()]
    pdHigh_day2_ext = day2_rows_ext["pdHigh"].iloc[0]

    assert pdHigh_day2 == pytest.approx(pdHigh_day2_ext), (
        f"pdHigh for day 2 changed after appending future day 3: {pdHigh_day2} → {pdHigh_day2_ext}"
    )


# ---------------------------------------------------------------------------
# B. Prior profile levels — future-shock tests
# ---------------------------------------------------------------------------


def _profile_bars(date: str, prices: list[float], volumes: list[float]) -> list[dict]:
    bars = []
    rth = pd.Timestamp(f"{date} 09:30:00", tz=TZ)
    for i, (p, v) in enumerate(zip(prices, volumes)):
        ts = rth + pd.Timedelta(minutes=i * 30)
        bars.append(_ohlcv_bar(ts, p, p + 0.25, p - 0.25, p, v))
    return bars


def _tick_table_from_bars(df: pd.DataFrame, *, instrument: str = "ES"):
    """Tick Last = close (H≠L fixtures still use close as the tick print)."""
    inst = INSTRUMENTS[instrument]
    work = df.sort_values("timestamp").reset_index(drop=True).copy()
    local_ts = work["timestamp"].dt.tz_convert(TZ)
    work["session_date"] = trading_session_date(local_ts, inst.eth_start)
    chunks: list[TickChunk] = []
    for session, group in work.groupby("session_date", sort=True):
        stamps = pd.to_datetime(group["timestamp"], utc=True)
        ticks = pd.DataFrame(
            {
                "timestamp": stamps,
                "price": group["close"].to_numpy(dtype="float64"),
                "volume": group["volume"].to_numpy(dtype="float64"),
            }
        )
        chunks.append(
            TickChunk(
                session_date=session if isinstance(session, date) else pd.Timestamp(session).date(),
                ticks=ticks,
                source_paths=("r3-synthetic",),
                filename_window_mismatch=False,
                warnings=(),
                first_row_utc=pd.Timestamp(stamps.min()),
                last_row_utc=pd.Timestamp(stamps.max()),
                filename_window_start=None,
                filename_window_end=None,
            )
        )
    return build_prior_profile_table(chunks, instrument=instrument)


def test_prior_day_profile_future_shock():
    """Prior-day tick VAP (pdVAH/pdVAL/pdPOC) at T must not change
    when a later tick session is appended."""
    day1 = _profile_bars(
        "2026-06-02", [4000.0, 4005.0, 4010.0, 4005.0], [200.0, 500.0, 300.0, 400.0]
    )
    day2 = _profile_bars(
        "2026-06-03", [4010.0, 4015.0, 4008.0, 4012.0], [150.0, 600.0, 250.0, 350.0]
    )

    base = _build_df(day1 + day2)
    table_base = _tick_table_from_bars(base)
    r_base = compute_profile_levels(base, instrument="ES", prior_profile_table=table_base)

    first_day = r_base[r_base["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert first_day["pdPOC"].isna().all()

    day2_rows = r_base[r_base["timestamp"].dt.date == pd.Timestamp("2026-06-03").date()]
    pdVAH_before = day2_rows["pdVAH"].dropna().iloc[0]
    pdVAL_before = day2_rows["pdVAL"].dropna().iloc[0]
    pdPOC_before = day2_rows["pdPOC"].dropna().iloc[0]

    T = base["timestamp"].iloc[-1]
    day3_extreme = _extreme_future_bars(T, n=10)
    extended = _build_df(day1 + day2 + day3_extreme)
    # Same table on a longer 1m frame: VA is not recomputed from 1m close.
    r_same_table = compute_profile_levels(extended, instrument="ES", prior_profile_table=table_base)
    # Rebuilt table that includes the later tick session.
    r_ext = compute_profile_levels(
        extended, instrument="ES", prior_profile_table=_tick_table_from_bars(extended)
    )

    for frame in (r_same_table, r_ext):
        day2_rows_ext = frame[frame["timestamp"].dt.date == pd.Timestamp("2026-06-03").date()]
        assert day2_rows_ext["pdVAH"].dropna().iloc[0] == pytest.approx(pdVAH_before)
        assert day2_rows_ext["pdVAL"].dropna().iloc[0] == pytest.approx(pdVAL_before)
        assert day2_rows_ext["pdPOC"].dropna().iloc[0] == pytest.approx(pdPOC_before)


def test_prior_week_profile_future_shock():
    """Prior-week tick VAP (pwVAH/pwVAL/pwPOC) must not change
    when later ticks from the current (still-incomplete) week are added."""
    week1_bars = []
    for day in ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]:
        week1_bars += _profile_bars(day, [4000.0, 4005.0, 4010.0], [200.0, 500.0, 300.0])

    week2_bars = _profile_bars("2026-06-08", [4050.0, 4055.0], [300.0, 400.0])

    base = _build_df(week1_bars + week2_bars)
    table_base = _tick_table_from_bars(base)
    r_base = compute_profile_levels(base, instrument="ES", prior_profile_table=table_base)

    week2_rows = r_base[r_base["timestamp"].dt.date == pd.Timestamp("2026-06-08").date()]
    pw_before = week2_rows[["pwVAH", "pwVAL", "pwPOC"]].dropna(subset=["pwPOC"]).iloc[0]

    T = base["timestamp"].iloc[-1]
    more_week2 = _extreme_future_bars(T, n=5)
    extended = _build_df(week1_bars + week2_bars + more_week2)
    r_same_table = compute_profile_levels(extended, instrument="ES", prior_profile_table=table_base)
    r_ext = compute_profile_levels(
        extended, instrument="ES", prior_profile_table=_tick_table_from_bars(extended)
    )

    for frame in (r_same_table, r_ext):
        week2_rows_ext = frame[frame["timestamp"].dt.date == pd.Timestamp("2026-06-08").date()]
        pw_after = week2_rows_ext[["pwVAH", "pwVAL", "pwPOC"]].dropna(subset=["pwPOC"]).iloc[0]
        assert pw_before["pwPOC"] == pytest.approx(pw_after["pwPOC"])
        assert pw_before["pwVAH"] == pytest.approx(pw_after["pwVAH"])
        assert pw_before["pwVAL"] == pytest.approx(pw_after["pwVAL"])


def test_rolling_poc_future_shock():
    """Rolling POC at bar T must not change when future bars are appended."""
    bars = _profile_bars(
        "2026-06-02", [4000.0, 4005.0, 4010.0, 4008.0, 4003.0], [100.0, 300.0, 200.0, 400.0, 150.0]
    )

    base = _build_df(bars)
    r_base = compute_profile_levels(base, instrument="ES", rolling_windows=["1h"])

    T = base["timestamp"].iloc[-1]
    poc_before = r_base["POC_rolling_1h"].tolist()

    # Append extreme future bars
    future = _extreme_future_bars(T, n=5)
    extended = _build_df(bars + future)
    r_ext = compute_profile_levels(extended, instrument="ES", rolling_windows=["1h"])

    # Bars up to T (first len(bars) rows)
    poc_after = r_ext["POC_rolling_1h"].iloc[: len(bars)].tolist()

    assert poc_before == pytest.approx(poc_after, nan_ok=True), (
        "Rolling POC values before T changed after future bars appended"
    )


# ---------------------------------------------------------------------------
# B. Rolling indicators — future-shock test
# ---------------------------------------------------------------------------


def test_rolling_indicators_future_shock():
    """SMA/EMA/VWAP values at bar T must not change when future bars are appended."""
    bars = _standard_bars("2026-06-02", 60, base_price=4000.0)
    base = _build_df(bars)

    r_base = compute_indicator_levels(
        base,
        sma_lengths=[5, 20],
        ema_lengths=[5, 20],
        vwap_windows=["15min", "30min"],
    )

    T = base["timestamp"].iloc[-1]
    cols = [c for c in r_base.columns if c.startswith(("SMA_", "EMA_", "VWAP_"))]
    snapshot_before = r_base[cols].copy()

    future = _extreme_future_bars(T, n=10)
    extended = _build_df(bars + future)
    r_ext = compute_indicator_levels(
        extended,
        sma_lengths=[5, 20],
        ema_lengths=[5, 20],
        vwap_windows=["15min", "30min"],
    )

    snapshot_after = r_ext[cols].iloc[: len(bars)].copy()

    pd.testing.assert_frame_equal(
        snapshot_before.reset_index(drop=True),
        snapshot_after.reset_index(drop=True),
        check_exact=False,
        atol=1e-10,
    )


# ---------------------------------------------------------------------------
# C. Naked levels — future-shock test
# ---------------------------------------------------------------------------


def test_naked_flags_future_shock():
    """Naked flags at bar T must not change because of touches after T."""
    # A level at 4010.0 that price never touches in the base dataset.
    bars = _standard_bars("2026-06-02", 10, base_price=4000.0)  # max high ~ 4004.5
    base = _build_df(bars)
    # Manually inject a constant level column
    base["test_level"] = 4010.0

    r_base = flag_naked_levels(
        base, level_columns=["test_level"], tick_size=TICK, touch_tolerance_ticks=0
    )
    naked_before = r_base["test_level_naked"].tolist()

    assert all(naked_before), "Level at 4010 should be naked in all base bars (price < 4010)"

    # Future shock: add bars that touch 4010.0
    T = base["timestamp"].iloc[-1]
    future_touching = []
    for i in range(5):
        ts = T + pd.Timedelta(minutes=i + 1)
        future_touching.append(_ohlcv_bar(ts, 4010.0, 4012.0, 4009.0, 4011.0, 500.0))

    extended = pd.concat([base, pd.DataFrame(future_touching)], ignore_index=True)
    # Propagate the level column to future bars
    extended["test_level"] = 4010.0

    r_ext = flag_naked_levels(
        extended, level_columns=["test_level"], tick_size=TICK, touch_tolerance_ticks=0
    )

    naked_after = r_ext["test_level_naked"].iloc[: len(bars)].tolist()

    assert naked_before == naked_after, (
        "Naked flags before T changed after future touching bars were appended"
    )


def test_naked_flags_cleared_only_on_touching_bar():
    """Naked flag is cleared at the bar that touches the level, not before."""
    level_price = 4005.0
    bars = [
        # Bar 0: level forms (no prior bar with this level), price far from level → naked
        _ohlcv_bar(_rth_ts("2026-06-02", "09:30"), 4000.0, 4001.0, 3999.0, 4000.5, 100.0),
        # Bar 1: price still below level → naked
        _ohlcv_bar(_rth_ts("2026-06-02", "09:31"), 4001.0, 4002.0, 4000.0, 4001.5, 100.0),
        # Bar 2: price touches level (high >= level) → naked clears
        _ohlcv_bar(_rth_ts("2026-06-02", "09:32"), 4004.0, 4006.0, 4003.0, 4005.5, 100.0),
        # Bar 3: after touch → not naked
        _ohlcv_bar(_rth_ts("2026-06-02", "09:33"), 4005.0, 4006.0, 4004.0, 4005.0, 100.0),
    ]
    df = _build_df(bars)
    df["test_level"] = level_price

    r = flag_naked_levels(df, level_columns=["test_level"], tick_size=TICK)
    naked = r["test_level_naked"].tolist()

    assert naked[0] is True or naked[0] == 1, "Bar 0 should be naked (level just formed)"
    assert naked[1] is True or naked[1] == 1, "Bar 1 should still be naked"
    assert naked[2] is False or naked[2] == 0, "Bar 2 should not be naked (touched)"
    assert naked[3] is False or naked[3] == 0, "Bar 3 should not be naked (already tested)"


# ---------------------------------------------------------------------------
# D. Confluence zones — future-shock test
# ---------------------------------------------------------------------------


def test_confluence_zones_future_shock():
    """Confluence zones at bar T must not change when future bars/levels are appended."""
    bars = _standard_bars("2026-06-02", 20, base_price=4000.0)
    base = _build_df(bars)
    # Add two level columns with stable values
    base["level_A"] = 4005.0
    base["level_B"] = 4005.25  # within 2-tick tolerance of level_A

    zones_before = detect_confluence_zones(
        base,
        level_columns=["level_A", "level_B"],
        tick_size=TICK,
        tolerance_ticks=2,
        min_confluences=2,
    )

    # Future shock: append bars with extreme levels
    T = base["timestamp"].iloc[-1]
    future = _extreme_future_bars(T, n=5)
    future_df = pd.DataFrame(future)
    future_df["level_A"] = 4005.0
    future_df["level_B"] = 4005.25

    extended = pd.concat([base, future_df], ignore_index=True)
    zones_after = detect_confluence_zones(
        extended,
        level_columns=["level_A", "level_B"],
        tick_size=TICK,
        tolerance_ticks=2,
        min_confluences=2,
    )

    # Zones at or before T must be the same
    zones_after_before_T = (
        zones_after[zones_after["timestamp"] <= T] if not zones_after.empty else pd.DataFrame()
    )

    if not zones_before.empty and not zones_after_before_T.empty:
        # Compare zone counts per bar
        before_counts = zones_before.groupby("timestamp").size()
        after_counts = zones_after_before_T.groupby("timestamp").size()
        pd.testing.assert_series_equal(before_counts, after_counts, check_names=False)
    elif zones_before.empty:
        assert zones_after_before_T.empty, "Zones appeared for T bars after appending future data"


def test_anchor_confluence_future_shock():
    """Anchor confluence zones at bar T must not change after future bars with extreme levels."""
    bars = _standard_bars("2026-06-02", 10, base_price=4000.0)
    base = _build_df(bars)
    base["anchor"] = 4004.0
    base["conf_level"] = 4004.5  # within 4 ticks

    rules = [{"level": "conf_level", "tolerance_ticks": 4.0, "required": False}]

    zones_before = detect_anchor_confluence_zones(
        base,
        anchor_level="anchor",
        confluence_rules=rules,
        tick_size=TICK,
        min_valid_confluences=1,
    )

    T = base["timestamp"].iloc[-1]
    future = _extreme_future_bars(T, n=5)
    future_df = pd.DataFrame(future)
    future_df["anchor"] = 4004.0
    future_df["conf_level"] = 4004.5

    extended = pd.concat([base, future_df], ignore_index=True)
    zones_after = detect_anchor_confluence_zones(
        extended,
        anchor_level="anchor",
        confluence_rules=rules,
        tick_size=TICK,
        min_valid_confluences=1,
    )

    before_T = (
        zones_before[zones_before["timestamp"] <= T] if not zones_before.empty else pd.DataFrame()
    )
    after_T = (
        zones_after[zones_after["timestamp"] <= T] if not zones_after.empty else pd.DataFrame()
    )

    assert len(before_T) == len(after_T), (
        f"Anchor zone count for bars ≤ T changed: {len(before_T)} → {len(after_T)}"
    )


# ---------------------------------------------------------------------------
# E. Signals — future-shock tests
# ---------------------------------------------------------------------------


def _make_zones_df(bar_indices: list[int], timestamps: list[pd.Timestamp]) -> pd.DataFrame:
    """Create minimal zones DataFrame for signal generation tests."""
    rows = []
    for bar_idx, ts in zip(bar_indices, timestamps):
        rows.append(
            {
                "timestamp": ts,
                "bar_index": bar_idx,
                "zone_low": 4004.5,
                "zone_high": 4005.5,
                "zone_mid": 4005.0,
                "level_count": 2,
                "level_names": "level_A|level_B",
                "level_prices": "4004.5|4005.5",
            }
        )
    return pd.DataFrame(rows)


def test_signals_touch_future_shock():
    """Touch signals generated at or before T must not change when future bars are appended."""
    # Create bars where some bars touch zone [4004.5, 4005.5]
    bars = []
    ts0 = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)
    prices = [4000.0, 4002.0, 4005.0, 4003.0, 4001.0]  # bar 2 touches the zone
    for i, p in enumerate(prices):
        bars.append(_ohlcv_bar(ts0 + pd.Timedelta(minutes=i), p, p + 0.5, p - 0.5, p + 0.1, 100.0))

    df = _build_df(bars)

    # Zone present at bar 2
    zones = _make_zones_df([2], [ts0 + pd.Timedelta(minutes=2)])

    sigs_before = generate_signals(df, zones, trigger="touch", direction="both", tick_size=TICK)

    T = df["timestamp"].iloc[-1]
    future = _extreme_future_bars(T, n=5)
    extended = pd.concat([df, _build_df(future)], ignore_index=True)

    # Zones unchanged (still only at bar 2)
    sigs_after = generate_signals(
        extended, zones, trigger="touch", direction="both", tick_size=TICK
    )

    # Signals at or before T must be the same
    sigs_before_T = (
        sigs_before[sigs_before["bar_index"] < len(bars)]
        if not sigs_before.empty
        else pd.DataFrame()
    )
    sigs_after_T = (
        sigs_after[sigs_after["bar_index"] < len(bars)] if not sigs_after.empty else pd.DataFrame()
    )

    assert len(sigs_before_T) == len(sigs_after_T), (
        f"Signal count before T changed: {len(sigs_before_T)} → {len(sigs_after_T)}"
    )
    if not sigs_before_T.empty and not sigs_after_T.empty:
        for col in ["bar_index", "trigger", "direction"]:
            assert sigs_before_T[col].tolist() == sigs_after_T[col].tolist(), (
                f"Column {col!r} changed after future shock"
            )


def test_signals_fade_future_shock():
    """Fade signals at or before T must not change when 50 future bars are appended."""
    bars = []
    ts0 = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)
    # bar 0 close above zone; bar 2 touches [4004.5, 4005.5] from above.
    specs = [
        (4006.0, 4006.4, 4005.8, 4006.1),
        (4006.0, 4006.3, 4005.7, 4006.0),
        (4005.8, 4006.0, 4004.6, 4005.0),
        (4005.0, 4005.2, 4004.8, 4004.9),
        (4004.9, 4005.1, 4004.7, 4004.8),
    ]
    for i, (o, h, l, c) in enumerate(specs):
        bars.append(_ohlcv_bar(ts0 + pd.Timedelta(minutes=i), o, h, l, c, 100.0))

    df = _build_df(bars)
    zones = _make_zones_df([2], [ts0 + pd.Timedelta(minutes=2)])
    sigs_before = generate_signals(df, zones, trigger="fade", direction="both", tick_size=TICK)
    assert not sigs_before.empty
    assert list(sigs_before["direction"]) == ["long"]
    assert list(sigs_before["approach_side"]) == ["above"]

    T = df["timestamp"].iloc[-1]
    future = _extreme_future_bars(T, n=50)
    extended = pd.concat([df, _build_df(future)], ignore_index=True)
    sigs_after = generate_signals(extended, zones, trigger="fade", direction="both", tick_size=TICK)
    before_T = sigs_before[sigs_before["bar_index"] < len(bars)].reset_index(drop=True)
    after_T = sigs_after[sigs_after["bar_index"] < len(bars)].reset_index(drop=True)
    compare_cols = ["bar_index", "trigger", "direction", "approach_side", "entry_reference_price"]
    pd.testing.assert_frame_equal(before_T[compare_cols], after_T[compare_cols], check_exact=True)


def test_confirm_3bar_not_backdated():
    """_check_confirm_3bar signals must be timestamped at bar 3, not at bar 1 (arrival).

    confirm_3bar is an internal helper; this test calls it directly to verify the
    point-in-time guarantee that signals are not backdated to the arrival bar.
    """
    from thesistester.engine.signals import _check_confirm_3bar

    ts0 = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)

    # Bar layout:
    #   Bar 0 (arrival): low touches zone [4004.5, 4005.5], close above zone
    #   Bar 1 (reversal): close > bar0 close (long condition)
    #   Bar 2 (bar3): activation + entry: low retraces, high extends
    #   Bar 3: extra bar
    bars = [
        _ohlcv_bar(ts0, 4006.0, 4007.0, 4004.0, 4006.5, 100.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=1), 4007.0, 4008.0, 4006.0, 4007.5, 100.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=2), 4007.0, 4009.0, 4005.0, 4007.0, 100.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=3), 4007.5, 4009.0, 4006.5, 4008.0, 100.0),
    ]
    df = _build_df(bars)
    # Add required trigger columns (base trigger path)
    df["base_end_timestamp"] = df["timestamp"]
    df["trigger_bar_end_timestamp"] = df["timestamp"]

    zone = pd.Series(
        {
            "zone_low": 4004.5,
            "zone_high": 4005.5,
            "zone_mid": 4005.0,
            "level_count": 2,
            "level_names": "level_A|level_B",
            "level_prices": "4004.5|4005.5",
        }
    )

    results = _check_confirm_3bar(
        df=df,
        zone=zone,
        bar1_idx=0,
        direction="long",
        signal_id_start=0,
        naked_count=0,
        naked_req="any",
        tick_size=TICK,
        params={"activation_retrace_ticks": 0, "entry_offset_ticks": 0},
    )

    for sig in results:
        # Signal bar_index must be bar3_idx = 2, not bar1_idx = 0
        assert int(sig["bar_index"]) >= 2, (
            f"confirm_3bar signal backdated to arrival bar: bar_index={sig['bar_index']}"
        )
        assert sig["timestamp"] >= ts0 + pd.Timedelta(minutes=2), (
            f"confirm_3bar timestamp earlier than bar 3: {sig['timestamp']}"
        )


def test_3c_signals_not_backdated():
    """3c signals must be timestamped at entry bar or reversal bar, never at arrival bar."""
    ts0 = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)

    # Arrival at bar 0, reversal at bar 1, entry fill at bar 2 or later
    bars = [
        # Bar 0: arrival (low touches level 4005, close > 4005)
        _ohlcv_bar(ts0, 4006.0, 4007.0, 4004.5, 4006.5, 100.0),
        # Bar 1: reversal (close > bar0 high)
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=1), 4007.5, 4009.0, 4007.0, 4008.5, 200.0),
        # Bar 2: retraces to retrace level (entry fill)
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=2), 4008.0, 4008.5, 4006.0, 4007.5, 150.0),
        # Bar 3: extra
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=3), 4007.5, 4008.0, 4007.0, 4007.5, 100.0),
        # Bar 4: extra
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=4), 4007.0, 4007.5, 4006.5, 4007.0, 100.0),
    ]
    df = _build_df(bars)

    zone_row = {
        "timestamp": ts0,
        "bar_index": 0,
        "zone_low": 4004.5,
        "zone_high": 4005.5,
        "zone_mid": 4005.0,
        "level_count": 1,
        "level_names": "test_level",
        "level_prices": "4005.0",
    }
    zones = pd.DataFrame([zone_row])

    sigs = generate_signals(
        df,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 4.0, "max_entry_wait_bars_after_reversal": 5},
    )

    if not sigs.empty:
        for _, sig in sigs.iterrows():
            # bar_index must be >= 1 (reversal) for any 3c signal
            assert int(sig["bar_index"]) >= 1, (
                f"3c signal at bar_index=0 (arrival bar): backdated! bar_index={sig['bar_index']}"
            )
            arrival_idx = sig.get("arrival_bar_index", 0)
            assert int(sig["bar_index"]) >= int(arrival_idx), (
                f"3c signal bar_index {sig['bar_index']} is before arrival_bar_index {arrival_idx}"
            )


def test_3c_signals_before_T_unchanged_after_future_bars():
    """3c signals at or before T must not change when future unrelated bars are appended."""
    ts0 = pd.Timestamp("2026-06-02 09:30:00", tz=TZ)

    bars = [
        _ohlcv_bar(ts0, 4006.0, 4007.0, 4004.5, 4006.5, 100.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=1), 4007.5, 4009.0, 4007.0, 4008.5, 200.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=2), 4008.0, 4008.5, 4006.0, 4007.5, 150.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=3), 4007.5, 4008.0, 4007.0, 4007.5, 100.0),
        _ohlcv_bar(ts0 + pd.Timedelta(minutes=4), 4007.0, 4007.5, 4006.5, 4007.0, 100.0),
    ]
    df = _build_df(bars)

    zones = pd.DataFrame(
        [
            {
                "timestamp": ts0,
                "bar_index": 0,
                "zone_low": 4004.5,
                "zone_high": 4005.5,
                "zone_mid": 4005.0,
                "level_count": 1,
                "level_names": "test_level",
                "level_prices": "4005.0",
            }
        ]
    )

    sigs_before = generate_signals(
        df,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 4.0, "max_entry_wait_bars_after_reversal": 5},
    )

    T = df["timestamp"].iloc[-1]
    future = _extreme_future_bars(T, n=10)
    extended = pd.concat([df, _build_df(future)], ignore_index=True)

    sigs_after = generate_signals(
        extended,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 4.0, "max_entry_wait_bars_after_reversal": 5},
    )

    # Only compare signals whose bar_index falls within the original dataset
    sigs_b = (
        sigs_before[sigs_before["bar_index"] < len(bars)].reset_index(drop=True)
        if not sigs_before.empty
        else pd.DataFrame()
    )
    sigs_a = (
        sigs_after[sigs_after["bar_index"] < len(bars)].reset_index(drop=True)
        if not sigs_after.empty
        else pd.DataFrame()
    )

    assert len(sigs_b) == len(sigs_a), (
        f"3c signal count for bars ≤ T changed after future bars: {len(sigs_b)} → {len(sigs_a)}"
    )
    if not sigs_b.empty and not sigs_a.empty:
        for col in ["bar_index", "direction", "status"]:
            assert sigs_b[col].tolist() == sigs_a[col].tolist(), (
                f"3c column {col!r} changed after future shock"
            )
