"""tests/test_otf.py — Comprehensive tests for the pure OTF calculation engine.

Tests the production engine in ``thesistester/engine/otf.py`` against the
contract in ``docs/otf-filter.md`` and the deterministic fixtures in
``tests/fixtures/otf_fixtures.py``.

Contract reference: docs/otf-filter.md — OTF v1 Behavioral Contract
Contract version:   v1
"""
from __future__ import annotations

import datetime
from typing import Any

import pandas as pd
import pytest

from tests.fixtures.otf_fixtures import (
    DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    OTF_DOWN_ESTABLISHED,
    OTF_EQUAL_HIGH,
    OTF_EQUAL_LOW,
    OTF_INSUFFICIENT_HISTORY,
    OTF_LOOKAHEAD_SAFETY,
    OTF_LOOKAHEAD_SOURCE_BARS,
    OTF_NEUTRAL,
    OTF_OVERNIGHT_SESSION,
    OTF_REVERSAL_UP_TO_DOWN,
    OTF_SEQUENCE_BREAK_DOWN,
    OTF_SEQUENCE_BREAK_UP,
    OTF_SESSION_BOUNDARY,
    OTF_UP_ESTABLISHED,
    TZ,
    _bars_to_df,
)
from thesistester.engine.otf import (
    OTF_CANONICAL_TIMEFRAMES,
    OTF_SUPPORTED_TIMEFRAMES,
    _OUTPUT_COLUMNS,
    calculate_otf_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TZ = TZ  # "America/New_York"


def _expand_to_1m(bars: list[dict], source_tz: str = _TZ) -> pd.DataFrame:
    """Expand a list of 5-minute OHLCV bar dicts into 1-minute source bars.

    For each 5m bar (O, H, L, C, V), produces 5 one-minute bars whose OHLCV
    aggregates to exactly (O, H, L, C) after ``resample_ohlcv(df, "5min")``:

    - Minute 0: open=O, high=H, low=L, close=O, vol=V/5
    - Minutes 1-3: all fields = midpoint = (O+C)/2, vol=V/5
    - Minute 4: open=C, high=C, low=C, close=C, vol=V/5

    The 5m bar timestamp is used as the *start* of the 5-minute slot.
    """
    rows: list[dict] = []
    for bar in bars:
        start_ts: pd.Timestamp = bar["timestamp"]
        O = bar["open"]
        H = bar["high"]
        L = bar["low"]
        C = bar["close"]
        V = bar["volume"]
        mid = (O + C) / 2.0

        # Minute 0: captures open, high, low
        rows.append(
            {
                "timestamp": start_ts,
                "open": O,
                "high": H,
                "low": L,
                "close": O,
                "volume": V / 5,
            }
        )
        # Minutes 1-3: flat at midpoint (won't break H/L extremes)
        for m in range(1, 4):
            rows.append(
                {
                    "timestamp": start_ts + pd.Timedelta(minutes=m),
                    "open": mid,
                    "high": mid,
                    "low": mid,
                    "close": mid,
                    "volume": V / 5,
                }
            )
        # Minute 4: captures close
        rows.append(
            {
                "timestamp": start_ts + pd.Timedelta(minutes=4),
                "open": C,
                "high": C,
                "low": C,
                "close": C,
                "volume": V / 5,
            }
        )

    return pd.DataFrame(rows).reset_index(drop=True)


def _run_scenario_5m(scenario: dict) -> pd.DataFrame:
    """Feed a scenario's bars (already at 5m resolution) as 1m source to the engine."""
    src = _expand_to_1m(scenario["bars"])
    return calculate_otf_state(
        src,
        "5m",
        minimum_consecutive_bars=scenario.get(
            "minimum_consecutive_bars", DEFAULT_MINIMUM_CONSECUTIVE_BARS
        ),
        eth_start=scenario.get("eth_start"),
    )


def _run_scenario_overnight(scenario: dict) -> pd.DataFrame:
    """Run overnight session test using synthetic 1-minute source data.

    Creates 1-minute source bars that:
    - Span the overnight session from Mon 22:00 ET through Tue 01:00 ET
      (all in trading_session_date = 2026-01-06, the Tuesday session)
    - Have strictly increasing lows → OTF up is established within the session
    - Are followed by bars at Tue 18:00 ET (start of the Wed session = 2026-01-07)
    - Verify midnight does NOT reset state, but 18:00 ET DOES reset state

    The scenario parameter is used for eth_start / exchange_tz metadata.
    """
    tz = scenario.get("exchange_tz", "America/New_York")
    eth_start = scenario.get("eth_start")

    rows: list[dict] = []
    # Monday 22:00 ET through Tuesday 01:00 ET: 180 minutes
    base = pd.Timestamp("2026-01-05 22:00", tz=tz)
    for i in range(180):
        ts = base + pd.Timedelta(minutes=i)
        rows.append(
            {
                "timestamp": ts,
                "open": 100.0 + i * 0.01,
                "high": 102.0 + i * 0.01,
                "low":  99.0 + i * 0.01,   # strictly increasing → builds OTF up
                "close": 101.0 + i * 0.01,
                "volume": 500,
            }
        )
    # Tuesday 18:00 ET: true session boundary — reset to unknown
    base2 = pd.Timestamp("2026-01-06 18:00", tz=tz)
    for i in range(60):
        ts = base2 + pd.Timedelta(minutes=i)
        rows.append(
            {
                "timestamp": ts,
                "open": 200.0,
                "high": 202.0,
                "low": 198.0,
                "close": 201.0,
                "volume": 500,
            }
        )
    df = pd.DataFrame(rows)
    return calculate_otf_state(
        df,
        "30m",
        minimum_consecutive_bars=scenario.get(
            "minimum_consecutive_bars", DEFAULT_MINIMUM_CONSECUTIVE_BARS
        ),
        eth_start=eth_start,
    )


def _make_1m_source(
    timestamps: list[pd.Timestamp],
    *,
    high_offset: float = 1.0,
    low_offset: float = 1.0,
    close_offset: float = 0.5,
    volume: float = 500.0,
) -> pd.DataFrame:
    """Build deterministic 1-minute source rows for the provided timestamps."""
    rows = []
    for i, ts in enumerate(timestamps):
        open_ = 100.0 + i * 0.1
        close = open_ + close_offset
        rows.append(
            {
                "timestamp": ts,
                "open": open_,
                "high": open_ + high_offset,
                "low": open_ - low_offset,
                "close": close,
                "volume": volume,
            }
        )
    return pd.DataFrame(rows)


def _minute_range(
    start: str,
    count: int,
    *,
    tz: str = _TZ,
    step_minutes: int = 1,
) -> list[pd.Timestamp]:
    """Return a list of tz-aware timestamps at a fixed minute cadence."""
    base = pd.Timestamp(start, tz=tz)
    return [base + pd.Timedelta(minutes=step_minutes * i) for i in range(count)]


# ---------------------------------------------------------------------------
# 1. OTF Up — established at bar 3
# ---------------------------------------------------------------------------


class TestOtfUpEstablished:
    def test_up_established_at_correct_bar(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        # bar 3 (index 3) should be "up"
        row = result.iloc[3]
        assert row["otf_state"] == "up"

    def test_up_run_at_bar_3_equals_minimum(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert result.iloc[3]["up_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS

    def test_up_extends_at_bar_4(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert result.iloc[4]["otf_state"] == "up"
        assert result.iloc[4]["up_run"] == 4

    def test_first_bar_is_unknown(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert result.iloc[0]["otf_state"] == "unknown"

    def test_second_bar_is_neutral(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert result.iloc[1]["otf_state"] == "neutral"

    def test_down_run_stays_zero_throughout(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert (result["down_run"] == 0).all()

    def test_sequence_length_reflects_up_run(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        for _, row in result.iterrows():
            if row["otf_state"] == "up":
                assert row["otf_sequence_length"] == row["up_run"]


# ---------------------------------------------------------------------------
# 2. OTF Down — established at bar 3
# ---------------------------------------------------------------------------


class TestOtfDownEstablished:
    def test_down_established_at_correct_bar(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        assert result.iloc[3]["otf_state"] == "down"

    def test_down_run_at_bar_3_equals_minimum(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        assert result.iloc[3]["down_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS

    def test_down_extends_at_bar_4(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        assert result.iloc[4]["otf_state"] == "down"
        assert result.iloc[4]["down_run"] == 4

    def test_first_bar_is_unknown(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        assert result.iloc[0]["otf_state"] == "unknown"

    def test_up_run_stays_zero_throughout(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        assert (result["up_run"] == 0).all()

    def test_sequence_length_reflects_down_run(self) -> None:
        result = _run_scenario_5m(OTF_DOWN_ESTABLISHED)
        for _, row in result.iterrows():
            if row["otf_state"] == "down":
                assert row["otf_sequence_length"] == row["down_run"]


# ---------------------------------------------------------------------------
# 3. Neutral / two-sided behavior
# ---------------------------------------------------------------------------


class TestNeutral:
    def test_neutral_after_first_bar(self) -> None:
        result = _run_scenario_5m(OTF_NEUTRAL)
        for i in range(1, len(result)):
            assert result.iloc[i]["otf_state"] == "neutral"

    def test_first_bar_unknown(self) -> None:
        result = _run_scenario_5m(OTF_NEUTRAL)
        assert result.iloc[0]["otf_state"] == "unknown"

    def test_no_run_reaches_threshold(self) -> None:
        result = _run_scenario_5m(OTF_NEUTRAL)
        assert (result["up_run"] < DEFAULT_MINIMUM_CONSECUTIVE_BARS).all()
        assert (result["down_run"] < DEFAULT_MINIMUM_CONSECUTIVE_BARS).all()

    def test_sequence_length_is_zero(self) -> None:
        result = _run_scenario_5m(OTF_NEUTRAL)
        for _, row in result.iterrows():
            if row["otf_state"] in ("neutral", "unknown"):
                assert row["otf_sequence_length"] == 0


# ---------------------------------------------------------------------------
# 4. Up sequence break
# ---------------------------------------------------------------------------


class TestSequenceBreakUp:
    def test_up_established_at_bar_3(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_UP)
        assert result.iloc[3]["otf_state"] == "up"

    def test_break_resets_to_neutral_at_bar_4(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_UP)
        assert result.iloc[4]["otf_state"] == "neutral"

    def test_up_run_resets_to_zero_at_break(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_UP)
        assert result.iloc[4]["up_run"] == 0


# ---------------------------------------------------------------------------
# 5. Down sequence break
# ---------------------------------------------------------------------------


class TestSequenceBreakDown:
    def test_down_established_at_bar_3(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_DOWN)
        assert result.iloc[3]["otf_state"] == "down"

    def test_break_resets_to_neutral_at_bar_4(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_DOWN)
        assert result.iloc[4]["otf_state"] == "neutral"

    def test_down_run_resets_to_zero_at_break(self) -> None:
        result = _run_scenario_5m(OTF_SEQUENCE_BREAK_DOWN)
        assert result.iloc[4]["down_run"] == 0


# ---------------------------------------------------------------------------
# 6. Reversal (Up → Down)
# ---------------------------------------------------------------------------


class TestReversal:
    def test_up_established_at_bar_3(self) -> None:
        result = _run_scenario_5m(OTF_REVERSAL_UP_TO_DOWN)
        assert result.iloc[3]["otf_state"] == "up"

    def test_up_broken_at_bar_4(self) -> None:
        result = _run_scenario_5m(OTF_REVERSAL_UP_TO_DOWN)
        assert result.iloc[4]["otf_state"] == "neutral"
        assert result.iloc[4]["up_run"] == 0

    def test_down_established_at_bar_6(self) -> None:
        result = _run_scenario_5m(OTF_REVERSAL_UP_TO_DOWN)
        assert result.iloc[6]["otf_state"] == "down"

    def test_reversal_requires_building_opposite_sequence(self) -> None:
        result = _run_scenario_5m(OTF_REVERSAL_UP_TO_DOWN)
        # bars 5 and 6: down_run builds
        assert result.iloc[5]["otf_state"] in ("neutral", "down")
        assert result.iloc[6]["down_run"] >= DEFAULT_MINIMUM_CONSECUTIVE_BARS


# ---------------------------------------------------------------------------
# 7. Equal-high and equal-low resets
# ---------------------------------------------------------------------------


class TestEqualHighLow:
    def test_equal_low_resets_up_run(self) -> None:
        result = _run_scenario_5m(OTF_EQUAL_LOW)
        # find bar where equal low appears (bar 2 in fixture)
        # up_run should be positive at bar 1, reset at bar 2
        assert result.iloc[1]["up_run"] >= 1
        assert result.iloc[2]["up_run"] == 0

    def test_equal_high_resets_down_run(self) -> None:
        result = _run_scenario_5m(OTF_EQUAL_HIGH)
        assert result.iloc[1]["down_run"] >= 1
        assert result.iloc[2]["down_run"] == 0


# ---------------------------------------------------------------------------
# 8. Insufficient history (single bar → unknown)
# ---------------------------------------------------------------------------


class TestInsufficientHistory:
    def test_single_source_bar_returns_unknown(self) -> None:
        """A dataset with only one completed HTF bar returns unknown."""
        result = _run_scenario_5m(OTF_INSUFFICIENT_HISTORY)
        assert len(result) == 1
        assert result.iloc[0]["otf_state"] == "unknown"

    def test_single_bar_runs_are_zero(self) -> None:
        result = _run_scenario_5m(OTF_INSUFFICIENT_HISTORY)
        assert result.iloc[0]["up_run"] == 0
        assert result.iloc[0]["down_run"] == 0

    def test_single_bar_reference_is_nat(self) -> None:
        result = _run_scenario_5m(OTF_INSUFFICIENT_HISTORY)
        assert pd.isna(result.iloc[0]["otf_reference_timestamp"])


# ---------------------------------------------------------------------------
# 9. Configurable minimum_consecutive_bars
# ---------------------------------------------------------------------------


class TestConfigurableMinimum:
    def _bars_up(self, n_bars: int, min_bars: int) -> pd.DataFrame:
        """Create n_bars 5m bars with strictly increasing lows and run engine."""
        rows: list[dict] = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(n_bars):
            for m in range(5):
                ts = base + pd.Timedelta(minutes=i * 5 + m)
                o = 100.0 + i * 0.5
                h = o + 2.0
                lv = o - 1.0  # strictly increasing across bars
                c = o + 0.5
                rows.append(
                    {"timestamp": ts, "open": o, "high": h, "low": lv, "close": c, "volume": 200}
                )
        # Sentinel: ensure last bar's close is reached
        last_ts = base + pd.Timedelta(minutes=n_bars * 5)
        rows.append(
            {"timestamp": last_ts, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1}
        )
        df = pd.DataFrame(rows)
        return calculate_otf_state(df, "5m", minimum_consecutive_bars=min_bars)

    def test_minimum_2_establishes_up_at_bar_2(self) -> None:
        result = self._bars_up(5, 2)
        assert result.iloc[2]["otf_state"] == "up"
        assert result.iloc[2]["up_run"] == 2

    def test_minimum_4_does_not_establish_up_at_bar_3(self) -> None:
        result = self._bars_up(4, 4)
        assert result.iloc[3]["otf_state"] == "neutral"

    def test_minimum_4_establishes_up_at_bar_4(self) -> None:
        result = self._bars_up(6, 4)
        assert result.iloc[4]["otf_state"] == "up"
        assert result.iloc[4]["up_run"] == 4


# ---------------------------------------------------------------------------
# 10. Session reset using trading_session_date()
# ---------------------------------------------------------------------------


class TestSessionReset:
    def test_session_2_first_bar_is_unknown(self) -> None:
        result = _run_scenario_5m(OTF_SESSION_BOUNDARY)
        # Bar 4 in fixture = first bar of session 2
        # In the expanded 1m source, the 5m bars resample to give 6 HTF rows
        session_dates = result["trading_session_date"].unique()
        assert len(session_dates) == 2, f"Expected 2 sessions, got {session_dates}"
        # First bar of session 2 must be unknown
        sess2_rows = result[result["trading_session_date"] == sorted(session_dates)[1]]
        assert sess2_rows.iloc[0]["otf_state"] == "unknown"

    def test_session_1_reaches_up(self) -> None:
        result = _run_scenario_5m(OTF_SESSION_BOUNDARY)
        session_dates = sorted(result["trading_session_date"].unique())
        sess1_rows = result[result["trading_session_date"] == session_dates[0]]
        assert sess1_rows.iloc[-1]["otf_state"] == "up"

    def test_session_2_first_bar_runs_are_zero(self) -> None:
        result = _run_scenario_5m(OTF_SESSION_BOUNDARY)
        session_dates = sorted(result["trading_session_date"].unique())
        sess2_rows = result[result["trading_session_date"] == session_dates[1]]
        first = sess2_rows.iloc[0]
        assert first["up_run"] == 0
        assert first["down_run"] == 0

    def test_session_2_reference_timestamp_is_nat(self) -> None:
        result = _run_scenario_5m(OTF_SESSION_BOUNDARY)
        session_dates = sorted(result["trading_session_date"].unique())
        sess2_rows = result[result["trading_session_date"] == session_dates[1]]
        assert pd.isna(sess2_rows.iloc[0]["otf_reference_timestamp"])


# ---------------------------------------------------------------------------
# 11. Overnight continuation across midnight and reset at eth_start
# ---------------------------------------------------------------------------


class TestOvernightSession:
    def test_midnight_does_not_reset_state(self) -> None:
        """OTF up sequence continues across midnight within the same futures session."""
        result = _run_scenario_overnight(OTF_OVERNIGHT_SESSION)
        # Find bar 2 (midnight bar, 00:00 ET on 2026-01-06)
        midnight_ts = pd.Timestamp("2026-01-06 00:00", tz=_TZ)
        # The HTF bar whose bar_start_timestamp == midnight should be in same session
        # as bars before midnight
        sessions = result["trading_session_date"].unique()
        assert len(sessions) == 2, f"Expected 2 sessions, got: {sessions}"
        # Midnight should be in first session (2026-01-06)
        date_2026_01_06 = datetime.date(2026, 1, 6)
        sess1 = result[result["trading_session_date"] == date_2026_01_06]
        # Should have more than 1 bar in session 1 (including post-midnight bars)
        assert len(sess1) > 1

    def test_eth_start_boundary_resets_state(self) -> None:
        """OTF state resets at 18:00 ET, the true futures session boundary."""
        result = _run_scenario_overnight(OTF_OVERNIGHT_SESSION)
        date_2026_01_07 = datetime.date(2026, 1, 7)
        sess2 = result[result["trading_session_date"] == date_2026_01_07]
        assert len(sess2) >= 1
        assert sess2.iloc[0]["otf_state"] == "unknown"

    def test_up_established_before_midnight(self) -> None:
        """The sequence spans midnight and reaches 'up' within the session."""
        result = _run_scenario_overnight(OTF_OVERNIGHT_SESSION)
        date_2026_01_06 = datetime.date(2026, 1, 6)
        sess1 = result[result["trading_session_date"] == date_2026_01_06]
        # At least one bar should be 'up'
        assert (sess1["otf_state"] == "up").any()

    def test_session_dates_are_correct_for_overnight_bars(self) -> None:
        """trading_session_date is correctly assigned using eth_start."""
        result = _run_scenario_overnight(OTF_OVERNIGHT_SESSION)
        # bars at 22:00 and 23:00 on 2026-01-05 belong to session 2026-01-06
        # bar at 18:00 on 2026-01-06 belongs to session 2026-01-07
        date_2026_01_06 = datetime.date(2026, 1, 6)
        date_2026_01_07 = datetime.date(2026, 1, 7)
        assert date_2026_01_06 in result["trading_session_date"].values
        assert date_2026_01_07 in result["trading_session_date"].values


# ---------------------------------------------------------------------------
# 12. Resampling at 5m, 15m, and 30m
# ---------------------------------------------------------------------------


class TestTimeframeResampling:
    def _make_source(self, n_minutes: int) -> pd.DataFrame:
        """Create n_minutes of 1-minute strictly-increasing-low bars."""
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(n_minutes):
            ts = base + pd.Timedelta(minutes=i)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0 + i * 0.1,
                    "high": 101.0 + i * 0.1,
                    "low": 99.0 + i * 0.1,
                    "close": 100.5 + i * 0.1,
                    "volume": 500,
                }
            )
        return pd.DataFrame(rows)

    def test_5m_produces_correct_bar_count(self) -> None:
        # Source rows 09:00-09:19 are 20 start-labelled 1m bars whose final
        # bar closes at 09:20, so four 5m buckets are complete with no sentinel.
        src = self._make_source(20)
        result = calculate_otf_state(src, "5m")
        assert len(result) == 4

    def test_15m_produces_correct_bar_count(self) -> None:
        src = self._make_source(45)
        result = calculate_otf_state(src, "15m")
        assert len(result) == 3

    def test_30m_produces_correct_bar_count(self) -> None:
        src = self._make_source(90)
        result = calculate_otf_state(src, "30m")
        assert len(result) == 3

    def test_5m_bar_close_equals_start_plus_5m(self) -> None:
        src = self._make_source(20)
        result = calculate_otf_state(src, "5m")
        for _, row in result.iterrows():
            expected = row["bar_start_timestamp"] + pd.Timedelta("5m")
            assert row["bar_close_timestamp"] == expected

    def test_15m_bar_close_equals_start_plus_15m(self) -> None:
        src = self._make_source(45)
        result = calculate_otf_state(src, "15m")
        for _, row in result.iterrows():
            expected = row["bar_start_timestamp"] + pd.Timedelta("15m")
            assert row["bar_close_timestamp"] == expected

    def test_30m_bar_close_equals_start_plus_30m(self) -> None:
        src = self._make_source(90)
        result = calculate_otf_state(src, "30m")
        for _, row in result.iterrows():
            expected = row["bar_start_timestamp"] + pd.Timedelta("30m")
            assert row["bar_close_timestamp"] == expected


class TestTimeframeApi:
    @pytest.mark.parametrize(
        ("timeframe", "source_minutes", "expected_bars"),
        [("5m", 20, 4), ("15m", 45, 3), ("30m", 90, 3)],
    )
    def test_canonical_public_timeframes_are_accepted(
        self,
        timeframe: str,
        source_minutes: int,
        expected_bars: int,
    ) -> None:
        timestamps = _minute_range("2026-01-05 09:00", source_minutes)
        result = calculate_otf_state(_make_1m_source(timestamps), timeframe)
        assert len(result) == expected_bars

    @pytest.mark.parametrize(
        ("canonical", "alias", "source_minutes"),
        [("5m", "5min", 20), ("15m", "15min", 45), ("30m", "30min", 90)],
    )
    def test_alias_results_match_canonical_results(
        self,
        canonical: str,
        alias: str,
        source_minutes: int,
    ) -> None:
        source = _make_1m_source(_minute_range("2026-01-05 09:00", source_minutes))
        canonical_result = calculate_otf_state(source, canonical)
        alias_result = calculate_otf_state(source, alias)
        pd.testing.assert_frame_equal(canonical_result, alias_result)

    def test_supported_timeframe_constant_uses_canonical_labels(self) -> None:
        assert OTF_CANONICAL_TIMEFRAMES == frozenset({"5m", "15m", "30m"})
        assert OTF_SUPPORTED_TIMEFRAMES == frozenset(
            {"5m", "15m", "30m", "5min", "15min", "30min"}
        )


# ---------------------------------------------------------------------------
# 13. Bar start / close / availability timestamps
# ---------------------------------------------------------------------------


class TestTimestampSemantics:
    def _make_source_5m(self) -> pd.DataFrame:
        rows = []
        base = pd.Timestamp("2026-01-05 09:25", tz=_TZ)
        for i in range(10):
            ts = base + pd.Timedelta(minutes=i)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0 + i * 0.05,
                    "close": 100.0,
                    "volume": 100,
                }
            )
        return pd.DataFrame(rows)

    def test_availability_timestamp_equals_bar_close_timestamp(self) -> None:
        src = self._make_source_5m()
        result = calculate_otf_state(src, "5m")
        assert (result["availability_timestamp"] == result["bar_close_timestamp"]).all()

    def test_bar_start_is_not_availability(self) -> None:
        src = self._make_source_5m()
        result = calculate_otf_state(src, "5m")
        for _, row in result.iterrows():
            assert row["bar_start_timestamp"] != row["availability_timestamp"], (
                "bar_start_timestamp must not equal availability_timestamp "
                "(availability = bar_close = start + duration)"
            )

    def test_first_completed_bar_starts_at_09_25(self) -> None:
        src = self._make_source_5m()
        result = calculate_otf_state(src, "5m")
        expected_start = pd.Timestamp("2026-01-05 09:25", tz=_TZ)
        assert result.iloc[0]["bar_start_timestamp"] == expected_start

    def test_first_completed_bar_closes_at_09_30(self) -> None:
        src = self._make_source_5m()
        result = calculate_otf_state(src, "5m")
        expected_close = pd.Timestamp("2026-01-05 09:30", tz=_TZ)
        assert result.iloc[0]["bar_close_timestamp"] == expected_close

    def test_first_completed_bar_available_at_09_30(self) -> None:
        src = self._make_source_5m()
        result = calculate_otf_state(src, "5m")
        avail = result.iloc[0]["availability_timestamp"]
        assert avail == pd.Timestamp("2026-01-05 09:30", tz=_TZ)


# ---------------------------------------------------------------------------
# 14. Partial first session-bucket policy
# ---------------------------------------------------------------------------


class TestPartialFirstBucketPolicy:
    def test_partial_first_bucket_is_discarded(self) -> None:
        """A partial first HTF bucket (source starts mid-bucket) is discarded."""
        # Source starts at 09:31 — within the 09:30 5m bucket
        rows = []
        base = pd.Timestamp("2026-01-05 09:31", tz=_TZ)
        for i in range(10):
            ts = base + pd.Timedelta(minutes=i)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0 + i,
                    "high": 102.0 + i,
                    "low": 99.0 + i,
                    "close": 101.0 + i,
                    "volume": 500,
                }
            )
        src = pd.DataFrame(rows)
        result = calculate_otf_state(src, "5m")
        # The 09:30 bucket starts before 09:31 → should be discarded
        if len(result) > 0:
            first_start = result.iloc[0]["bar_start_timestamp"]
            assert first_start >= pd.Timestamp("2026-01-05 09:31", tz=_TZ), (
                f"Partial first bucket not discarded: {first_start}"
            )

    def test_full_first_bucket_is_retained(self) -> None:
        """A bucket whose start equals the first source bar's timestamp is retained."""
        rows = []
        # Start exactly on a 5m boundary
        base = pd.Timestamp("2026-01-05 09:30", tz=_TZ)
        for i in range(10):
            ts = base + pd.Timedelta(minutes=i)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "volume": 500,
                }
            )
        src = pd.DataFrame(rows)
        result = calculate_otf_state(src, "5m")
        assert len(result) >= 1
        first_start = result.iloc[0]["bar_start_timestamp"]
        assert first_start == pd.Timestamp("2026-01-05 09:30", tz=_TZ)


# ---------------------------------------------------------------------------
# 15. Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_dataframe_returns_empty_result(self) -> None:
        empty = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        result = calculate_otf_state(empty, "5m")
        assert result.empty

    def test_empty_result_has_correct_columns(self) -> None:
        empty = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        result = calculate_otf_state(empty, "5m")
        for col in _OUTPUT_COLUMNS:
            assert col in result.columns


# ---------------------------------------------------------------------------
# 16. Missing columns
# ---------------------------------------------------------------------------


class TestMissingColumns:
    @pytest.mark.parametrize(
        "missing_col",
        ["timestamp", "open", "high", "low", "close", "volume"],
    )
    def test_missing_required_column_raises(self, missing_col: str) -> None:
        cols = {"timestamp", "open", "high", "low", "close", "volume"}
        cols.discard(missing_col)
        df = pd.DataFrame(columns=list(cols))
        with pytest.raises(ValueError, match=missing_col):
            calculate_otf_state(df, "5m")


# ---------------------------------------------------------------------------
# 17. Invalid or duplicate timestamps
# ---------------------------------------------------------------------------


class TestInvalidTimestamps:
    def _base_df(self) -> pd.DataFrame:
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        rows = []
        for i in range(5):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 500,
                }
            )
        return pd.DataFrame(rows)

    def test_duplicate_timestamps_raise(self) -> None:
        df = self._base_df()
        df.iloc[2, df.columns.get_loc("timestamp")] = df.iloc[1]["timestamp"]
        with pytest.raises(ValueError, match="monotonically"):
            calculate_otf_state(df, "5m")

    def test_non_monotonic_timestamps_raise(self) -> None:
        df = self._base_df()
        # Swap rows 2 and 3 to break monotonicity
        ts2 = df.iloc[2]["timestamp"]
        ts3 = df.iloc[3]["timestamp"]
        df.iloc[2, df.columns.get_loc("timestamp")] = ts3
        df.iloc[3, df.columns.get_loc("timestamp")] = ts2
        with pytest.raises(ValueError, match="monotonically"):
            calculate_otf_state(df, "5m")


# ---------------------------------------------------------------------------
# 18. OHLCV validation
# ---------------------------------------------------------------------------


class TestOhlcvValidation:
    def _base_df(self) -> pd.DataFrame:
        return _make_1m_source(_minute_range("2026-01-05 09:00", 5))

    def test_missing_ohlc_raises(self) -> None:
        df = self._base_df()
        df.loc[0, "open"] = None
        with pytest.raises(ValueError, match="OHLC"):
            calculate_otf_state(df, "5m")

    def test_non_numeric_volume_raises(self) -> None:
        df = self._base_df()
        df = df.astype({"volume": "object"})
        df.loc[0, "volume"] = "bad"
        with pytest.raises(ValueError, match="volume"):
            calculate_otf_state(df, "5m")

    def test_high_below_low_raises(self) -> None:
        df = self._base_df()
        df.loc[0, "high"] = df.loc[0, "low"] - 1
        with pytest.raises(ValueError, match="high < low"):
            calculate_otf_state(df, "5m")

    def test_open_close_outside_range_raises(self) -> None:
        df = self._base_df()
        df.loc[0, "high"] = df.loc[0, "open"] - 0.1
        with pytest.raises(ValueError, match="outside high/low"):
            calculate_otf_state(df, "5m")

    def test_negative_volume_raises(self) -> None:
        df = self._base_df()
        df.loc[0, "volume"] = -1
        with pytest.raises(ValueError, match="negative volume"):
            calculate_otf_state(df, "5m")


# ---------------------------------------------------------------------------
# 19. Timezone-aware input
# ---------------------------------------------------------------------------


class TestTimezoneAwareInput:
    def test_timezone_aware_timestamps_accepted(self) -> None:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz="America/New_York")
        for i in range(10):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 500,
                }
            )
        df = pd.DataFrame(rows)
        result = calculate_otf_state(df, "5m")
        assert not result.empty
        # Output timestamps should be timezone-aware
        assert result["bar_start_timestamp"].dt.tz is not None

    def test_output_preserves_timezone(self) -> None:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz="America/Chicago")
        for i in range(10):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 500,
                }
            )
        df = pd.DataFrame(rows)
        result = calculate_otf_state(df, "5m")
        tz = result["bar_start_timestamp"].dt.tz
        assert tz is not None


# ---------------------------------------------------------------------------
# 19. Timezone-naive input with and without session_timezone
# ---------------------------------------------------------------------------


class TestTimezoneNaive:
    def _naive_source(self, n: int = 10) -> pd.DataFrame:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00")  # no tz
        for i in range(n):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0 + i * 0.1,
                    "high": 101.0 + i * 0.1,
                    "low": 99.0 + i * 0.1,
                    "close": 100.5 + i * 0.1,
                    "volume": 500,
                }
            )
        return pd.DataFrame(rows)

    def test_naive_without_session_timezone_raises(self) -> None:
        df = self._naive_source()
        with pytest.raises(ValueError, match="timezone-naive"):
            calculate_otf_state(df, "5m", session_timezone=None)

    def test_naive_with_session_timezone_succeeds(self) -> None:
        df = self._naive_source()
        result = calculate_otf_state(df, "5m", session_timezone="America/New_York")
        assert not result.empty

    def test_naive_with_session_timezone_output_is_aware(self) -> None:
        df = self._naive_source()
        result = calculate_otf_state(df, "5m", session_timezone="UTC")
        assert result["bar_start_timestamp"].dt.tz is not None


# ---------------------------------------------------------------------------
# 20. Unsupported timeframe
# ---------------------------------------------------------------------------


class TestUnsupportedTimeframe:
    @pytest.mark.parametrize("bad_tf", ["1m", "10m", "1h", "4h", "invalid"])
    def test_unsupported_timeframe_raises(self, bad_tf: str) -> None:
        rows = [
            {
                "timestamp": pd.Timestamp("2026-01-05 09:00", tz=_TZ),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 500,
            }
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="timeframe"):
            calculate_otf_state(df, bad_tf)


# ---------------------------------------------------------------------------
# 21. Completed-bucket coverage and source-interval validation
# ---------------------------------------------------------------------------


class TestCompletedBucketCoverage:
    def test_5m_bucket_is_complete_without_next_bucket_sentinel(self) -> None:
        source = _make_1m_source(_minute_range("2026-01-05 09:00", 5))
        result = calculate_otf_state(source, "5m")
        assert len(result) == 1
        assert result.iloc[0]["bar_start_timestamp"] == pd.Timestamp(
            "2026-01-05 09:00", tz=_TZ
        )
        assert result.iloc[0]["bar_close_timestamp"] == pd.Timestamp(
            "2026-01-05 09:05", tz=_TZ
        )

    def test_5m_bucket_is_excluded_until_final_source_bar_is_present(self) -> None:
        source = _make_1m_source(_minute_range("2026-01-05 09:00", 4))
        result = calculate_otf_state(source, "5m")
        assert result.empty

    def test_15m_bucket_is_complete_without_next_bucket_sentinel(self) -> None:
        source = _make_1m_source(_minute_range("2026-01-05 09:00", 15))
        result = calculate_otf_state(source, "15m")
        assert len(result) == 1
        assert result.iloc[0]["bar_close_timestamp"] == pd.Timestamp(
            "2026-01-05 09:15", tz=_TZ
        )

    def test_30m_bucket_is_complete_without_next_bucket_sentinel(self) -> None:
        source = _make_1m_source(_minute_range("2026-01-05 09:00", 30))
        result = calculate_otf_state(source, "30m")
        assert len(result) == 1
        assert result.iloc[0]["bar_close_timestamp"] == pd.Timestamp(
            "2026-01-05 09:30", tz=_TZ
        )

    @pytest.mark.parametrize("missing_index", [0, 2, 4])
    def test_missing_required_source_coverage_excludes_5m_bucket(
        self,
        missing_index: int,
    ) -> None:
        timestamps = _minute_range("2026-01-05 09:00", 5)
        del timestamps[missing_index]
        result = calculate_otf_state(_make_1m_source(timestamps), "5m")
        assert result.empty

    def test_large_gap_spanning_bucket_close_excludes_incomplete_buckets(self) -> None:
        timestamps = [
            pd.Timestamp("2026-01-05 09:00", tz=_TZ),
            pd.Timestamp("2026-01-05 09:01", tz=_TZ),
            pd.Timestamp("2026-01-05 09:02", tz=_TZ),
            pd.Timestamp("2026-01-05 09:08", tz=_TZ),
            pd.Timestamp("2026-01-05 09:09", tz=_TZ),
        ]
        result = calculate_otf_state(_make_1m_source(timestamps), "5m")
        assert result.empty


class TestSourceIntervalValidation:
    def _make_5m_bars(self) -> pd.DataFrame:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(5):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=5 * i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 500,
                }
            )
        return pd.DataFrame(rows)

    def test_equal_source_target_raises(self) -> None:
        df = self._make_5m_bars()
        with pytest.raises(ValueError, match="strictly finer"):
            calculate_otf_state(df, "5m")

    def test_coarser_source_raises(self) -> None:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(4):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=15 * i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 500,
                }
            )
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="strictly finer"):
            calculate_otf_state(df, "5m")

    def test_target_timeframe_must_be_divisible_by_source_interval(self) -> None:
        source = _make_1m_source(
            _minute_range("2026-01-05 09:00", 6, step_minutes=2)
        )
        with pytest.raises(ValueError, match="exactly divisible"):
            calculate_otf_state(source, "5m")

    def test_unknown_interval_raises(self) -> None:
        source = _make_1m_source([pd.Timestamp("2026-01-05 09:00", tz=_TZ)])
        with pytest.raises(ValueError, match="Could not infer"):
            calculate_otf_state(source, "5m")

    def test_irregular_timestamps_that_break_interval_trust_raise(self) -> None:
        timestamps = [
            pd.Timestamp("2026-01-05 09:00", tz=_TZ),
            pd.Timestamp("2026-01-05 09:01", tz=_TZ),
            pd.Timestamp("2026-01-05 09:02:30", tz=_TZ),
            pd.Timestamp("2026-01-05 09:03:30", tz=_TZ),
            pd.Timestamp("2026-01-05 09:04:30", tz=_TZ),
        ]
        with pytest.raises(ValueError, match="trustworthy inferred source interval"):
            calculate_otf_state(_make_1m_source(timestamps), "5m")


# ---------------------------------------------------------------------------
# 22. Caller input is not mutated
# ---------------------------------------------------------------------------


class TestCallerInputNotMutated:
    def test_input_dataframe_not_mutated(self) -> None:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(10):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 500,
                }
            )
        df = pd.DataFrame(rows)
        original_cols = list(df.columns)
        original_shape = df.shape
        calculate_otf_state(df, "5m")
        assert list(df.columns) == original_cols
        assert df.shape == original_shape
        assert "otf_state" not in df.columns

    def test_alias_normalization_does_not_modify_caller_dataframe(self) -> None:
        df = _make_1m_source(_minute_range("2026-01-05 09:00", 20))
        original = df.copy(deep=True)
        calculate_otf_state(df, "5min")
        pd.testing.assert_frame_equal(df, original)


# ---------------------------------------------------------------------------
# 23. Deterministic output schema and dtypes
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def _run(self) -> pd.DataFrame:
        rows = []
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(10):
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 100.0 + i,
                    "high": 101.0 + i,
                    "low": 99.0 + i,
                    "close": 100.5 + i,
                    "volume": 500,
                }
            )
        return calculate_otf_state(pd.DataFrame(rows), "5m")

    def test_required_output_columns_present(self) -> None:
        result = self._run()
        for col in _OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing output column: {col}"

    def test_otf_state_is_string(self) -> None:
        result = self._run()
        for state in result["otf_state"]:
            assert isinstance(state, str)
            assert state in {"up", "down", "neutral", "unknown"}

    def test_up_run_and_down_run_are_non_negative_integers(self) -> None:
        result = self._run()
        assert (result["up_run"] >= 0).all()
        assert (result["down_run"] >= 0).all()

    def test_otf_sequence_length_is_non_negative(self) -> None:
        result = self._run()
        assert (result["otf_sequence_length"] >= 0).all()

    def test_bar_start_and_close_are_timezone_aware(self) -> None:
        result = self._run()
        assert result["bar_start_timestamp"].dt.tz is not None
        assert result["bar_close_timestamp"].dt.tz is not None
        assert result["availability_timestamp"].dt.tz is not None


# ---------------------------------------------------------------------------
# 24. Look-ahead and drift safety: unfinished bars do not affect earlier output
# ---------------------------------------------------------------------------


class TestLookaheadSafety:
    """Prove that in-progress bars cannot affect earlier OTF output.

    These tests use the production engine directly (not fixture vectors alone).
    They verify the append-data invariance property required by the PR spec.
    """

    def _make_source_from_lookahead(self) -> pd.DataFrame:
        """Reconstruct the look-ahead fixture as a full 1-minute source DataFrame."""
        return pd.DataFrame(OTF_LOOKAHEAD_SOURCE_BARS)

    def _make_linear_source(
        self,
        minutes: int,
        *,
        start: str = "2026-01-05 09:00",
    ) -> pd.DataFrame:
        return _make_1m_source(_minute_range(start, minutes))

    def _assert_historical_rows_equal(
        self,
        before: pd.DataFrame,
        after: pd.DataFrame,
        cutoff: pd.Timestamp,
    ) -> None:
        columns = [
            "bar_start_timestamp",
            "bar_close_timestamp",
            "availability_timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trading_session_date",
            "otf_state",
            "otf_sequence_length",
            "up_run",
            "down_run",
            "otf_reference_timestamp",
        ]
        before_rows = before[before["availability_timestamp"] <= cutoff][columns].reset_index(
            drop=True
        )
        after_rows = after[after["availability_timestamp"] <= cutoff][columns].reset_index(
            drop=True
        )
        pd.testing.assert_frame_equal(before_rows, after_rows)

    def test_5m_inprogress_bar_not_in_output_before_close(self) -> None:
        """At 09:33 the 09:30–09:35 bar must not appear in completed results."""
        all_bars = self._make_source_from_lookahead()
        # Slice source data as seen at 09:33
        cutoff = pd.Timestamp("2026-01-05 09:33", tz=_TZ)
        partial = all_bars[all_bars["timestamp"] <= cutoff].copy()
        result = calculate_otf_state(partial, "5m")
        # The last observed 1m source row is labelled 09:33 and becomes available
        # at 09:34.  Bar C closes at 09:35 > 09:34, so it is still incomplete.
        # Only bar A (closes 09:25) and bar B (closes 09:30) should appear.
        assert len(result) == 2, (
            f"Expected 2 completed bars (A and B), got {len(result)}: "
            f"{result['bar_start_timestamp'].tolist()}"
        )
        # Verify bar C is not in the output
        bar_starts = set(result["bar_start_timestamp"].dt.strftime("%H:%M").tolist())
        assert "09:30" not in bar_starts, (
            "In-progress bar C (09:30) must not appear in output at 09:33"
        )

    def test_15m_inprogress_bar_not_in_output(self) -> None:
        """An in-progress 15m bar does not appear in completed output."""
        src = self._make_linear_source(20)
        result = calculate_otf_state(src, "15m")
        assert len(result) == 1, f"Expected 1 completed bar, got {len(result)}"
        assert result.iloc[0]["bar_close_timestamp"] == pd.Timestamp(
            "2026-01-05 09:15", tz=_TZ
        )

    def test_30m_inprogress_bar_not_in_output(self) -> None:
        """An in-progress 30m bar does not appear in completed output."""
        src = self._make_linear_source(50)
        result = calculate_otf_state(src, "30m")
        assert len(result) == 1, f"Expected 1 completed 30m bar, got {len(result)}"
        assert result.iloc[0]["bar_close_timestamp"] == pd.Timestamp(
            "2026-01-05 09:30", tz=_TZ
        )

    @pytest.mark.parametrize(
        ("timeframe", "base_minutes", "full_minutes", "cutoff"),
        [
            ("5m", 10, 20, pd.Timestamp("2026-01-05 09:10", tz=_TZ)),
            ("15m", 30, 45, pd.Timestamp("2026-01-05 09:30", tz=_TZ)),
            ("30m", 60, 90, pd.Timestamp("2026-01-05 10:00", tz=_TZ)),
        ],
    )
    def test_appending_bars_does_not_change_complete_historical_rows(
        self,
        timeframe: str,
        base_minutes: int,
        full_minutes: int,
        cutoff: pd.Timestamp,
    ) -> None:
        before = calculate_otf_state(self._make_linear_source(base_minutes), timeframe)
        after = calculate_otf_state(self._make_linear_source(full_minutes), timeframe)
        self._assert_historical_rows_equal(before, after, cutoff)

    @pytest.mark.parametrize(
        ("timeframe", "base_minutes", "shock_end"),
        [("5m", 10, 30), ("15m", 30, 60), ("30m", 60, 120)],
    )
    def test_future_highs_lows_do_not_alter_historical_rows(
        self,
        timeframe: str,
        base_minutes: int,
        shock_end: int,
    ) -> None:
        before_source = self._make_linear_source(base_minutes)
        before = calculate_otf_state(before_source, timeframe)

        shocked = before_source.to_dict("records")
        base = pd.Timestamp("2026-01-05 09:00", tz=_TZ)
        for i in range(base_minutes, shock_end):
            shocked.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=i),
                    "open": 200.0,
                    "high": 400.0,
                    "low": 1.0,
                    "close": 200.0,
                    "volume": 500,
                }
            )
        after = calculate_otf_state(pd.DataFrame(shocked), timeframe)
        self._assert_historical_rows_equal(
            before,
            after,
            before["availability_timestamp"].max(),
        )

    def test_bar_available_exactly_at_close_timestamp(self) -> None:
        """A bar whose close timestamp equals the latest source availability is included.

        Contract §6.3: 'A higher-timeframe bar that closes exactly at T is
        available for signals at T.'

        Here the last observed 1m bar is labelled 09:04 and becomes available at
        09:05.  The 5m bar ending at 09:05 is therefore complete without any
        separate 09:05 source row.
        """
        result = calculate_otf_state(self._make_linear_source(5), "5m")
        assert len(result) == 1, f"Expected 1 completed bar, got {len(result)}"
        avail = result.iloc[0]["availability_timestamp"]
        close = result.iloc[0]["bar_close_timestamp"]
        assert avail == close
        assert avail == pd.Timestamp("2026-01-05 09:05", tz=_TZ)

    def test_future_bars_in_new_session_do_not_change_prior_session_rows(self) -> None:
        before = calculate_otf_state(self._make_linear_source(10), "5m")
        after_rows = self._make_linear_source(10).to_dict("records")
        after_rows.extend(
            self._make_linear_source(10, start="2026-01-06 09:00").to_dict("records")
        )
        after = calculate_otf_state(pd.DataFrame(after_rows), "5m")
        self._assert_historical_rows_equal(
            before,
            after,
            pd.Timestamp("2026-01-05 09:10", tz=_TZ),
        )

    def test_incomplete_bucket_remains_excluded_until_all_source_rows_arrive(self) -> None:
        incomplete = calculate_otf_state(self._make_linear_source(4), "5m")
        complete = calculate_otf_state(self._make_linear_source(5), "5m")
        assert incomplete.empty
        assert len(complete) == 1

    def test_session_boundary_reset_does_not_leak_prior_counters(self) -> None:
        """Prior-session up_run/down_run must not appear in the new session."""
        result = _run_scenario_5m(OTF_SESSION_BOUNDARY)
        session_dates = sorted(result["trading_session_date"].unique())
        sess2 = result[result["trading_session_date"] == session_dates[1]]
        first = sess2.iloc[0]
        assert first["up_run"] == 0, "Prior-session up_run leaked into new session"
        assert first["down_run"] == 0, "Prior-session down_run leaked into new session"
        assert first["otf_state"] == "unknown"


# ---------------------------------------------------------------------------
# 25. session_reset validation
# ---------------------------------------------------------------------------


class TestSessionResetValidation:
    def test_invalid_session_reset_raises(self) -> None:
        rows = [
            {
                "timestamp": pd.Timestamp("2026-01-05 09:00", tz=_TZ),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 500,
            }
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="session_reset"):
            calculate_otf_state(df, "5m", session_reset="carry")


# ---------------------------------------------------------------------------
# 26. minimum_consecutive_bars validation
# ---------------------------------------------------------------------------


class TestMinimumConsecutiveBarsValidation:
    def test_zero_minimum_raises(self) -> None:
        rows = [
            {
                "timestamp": pd.Timestamp("2026-01-05 09:00", tz=_TZ),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 500,
            }
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="minimum_consecutive_bars"):
            calculate_otf_state(df, "5m", minimum_consecutive_bars=0)

    def test_negative_minimum_raises(self) -> None:
        rows = [
            {
                "timestamp": pd.Timestamp("2026-01-05 09:00", tz=_TZ),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 500,
            }
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="minimum_consecutive_bars"):
            calculate_otf_state(df, "5m", minimum_consecutive_bars=-1)


# ---------------------------------------------------------------------------
# 27. otf_reference_timestamp semantics
# ---------------------------------------------------------------------------


class TestOtfReferenceTimestamp:
    def test_first_bar_reference_is_nat(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        assert pd.isna(result.iloc[0]["otf_reference_timestamp"])

    def test_second_bar_reference_is_first_bar_close(self) -> None:
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        first_close = result.iloc[0]["bar_close_timestamp"]
        second_ref = result.iloc[1]["otf_reference_timestamp"]
        assert second_ref == first_close

    def test_reference_is_bar_close_not_start(self) -> None:
        """otf_reference_timestamp must be the bar_close_timestamp of the previous bar."""
        result = _run_scenario_5m(OTF_UP_ESTABLISHED)
        for i in range(1, len(result)):
            ref = result.iloc[i]["otf_reference_timestamp"]
            prev_close = result.iloc[i - 1]["bar_close_timestamp"]
            assert ref == prev_close, (
                f"Row {i}: otf_reference_timestamp {ref} != "
                f"prev bar_close_timestamp {prev_close}"
            )
