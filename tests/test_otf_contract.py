"""OTF v1 contract tests — fixture integrity and state-vector validation.

These tests verify that:

1. Every OHLCV fixture satisfies basic integrity rules (valid prices,
   timezone-aware timestamps, correct column names, positive volume).

2. Every expected-state vector is consistent with the OTF v1 behavioral
   contract documented in docs/otf-filter.md.  The consistency checks are
   derived DIRECTLY from the OHLCV bar values; they do not invoke a
   production OTF engine.  This ensures the fixtures themselves are
   self-describing and unambiguous, and that a future production
   implementation can be verified against them without circular dependencies.

3. Look-ahead safety contract vectors reflect the correct completed-bar
   availability rule.

4. Directional eligibility and alignment vectors are internally consistent.

Reference: docs/otf-filter.md — OTF v1 Behavioral Contract
Contract version: v1
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests.fixtures.otf_fixtures import (
    ALL_OHLCV_SCENARIOS,
    DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    OTF_ALL_TIMEFRAME_ALIGNMENT,
    OTF_DIRECTIONAL_ELIGIBILITY,
    OTF_DOWN_ESTABLISHED,
    OTF_EQUAL_HIGH,
    OTF_EQUAL_LOW,
    OTF_INSUFFICIENT_HISTORY,
    OTF_LOOKAHEAD_SAFETY,
    OTF_NEUTRAL,
    OTF_OVERNIGHT_SESSION,
    OTF_REVERSAL_UP_TO_DOWN,
    OTF_SEQUENCE_BREAK_DOWN,
    OTF_SEQUENCE_BREAK_UP,
    OTF_SESSION_BOUNDARY,
    OTF_UP_ESTABLISHED,
    SUPPORTED_TIMEFRAMES,
    TZ,
    VALID_STATES,
    _bars_to_df,
)

from thesistester.data.resample import resample_ohlcv
from thesistester.levels.session_date import trading_session_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_valid_ohlcv_bar(bar: dict, bar_index: int, scenario: str) -> None:
    """Assert that a single bar dict satisfies OHLCV integrity rules."""
    ctx = f"scenario={scenario!r}, bar_index={bar_index}"

    assert "timestamp" in bar, f"Missing 'timestamp' column — {ctx}"
    assert "open" in bar,      f"Missing 'open' column — {ctx}"
    assert "high" in bar,      f"Missing 'high' column — {ctx}"
    assert "low" in bar,       f"Missing 'low' column — {ctx}"
    assert "close" in bar,     f"Missing 'close' column — {ctx}"
    assert "volume" in bar,    f"Missing 'volume' column — {ctx}"

    ts = bar["timestamp"]
    assert isinstance(ts, pd.Timestamp), f"timestamp must be pd.Timestamp — {ctx}"
    assert ts.tzinfo is not None, f"timestamp must be timezone-aware — {ctx}"

    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    vol = bar["volume"]

    assert h >= l, f"high({h}) < low({l}) — {ctx}"
    assert h >= o >= 0, f"open({o}) outside [0, high({h})] — {ctx}"
    assert h >= c >= 0, f"close({c}) outside [0, high({h})] — {ctx}"
    assert l >= 0, f"low({l}) is negative — {ctx}"
    assert vol > 0, f"volume({vol}) must be positive — {ctx}"


def _check_valid_state_vector(vec: dict, scenario: str) -> None:
    """Assert that a single expected-state dict has a valid structure."""
    ctx = f"scenario={scenario!r}"
    assert "bar_index" in vec, f"Missing 'bar_index' — {ctx}"
    assert "state" in vec, f"Missing 'state' — {ctx}"
    assert "up_run" in vec, f"Missing 'up_run' — {ctx}"
    assert "down_run" in vec, f"Missing 'down_run' — {ctx}"
    assert vec["state"] in VALID_STATES, (
        f"state={vec['state']!r} is not in VALID_STATES={VALID_STATES} — {ctx}"
    )
    assert isinstance(vec["bar_index"], int) and vec["bar_index"] >= 0, (
        f"bar_index must be a non-negative int — {ctx}"
    )
    assert isinstance(vec["up_run"], int) and vec["up_run"] >= 0, (
        f"up_run must be a non-negative int — {ctx}"
    )
    assert isinstance(vec["down_run"], int) and vec["down_run"] >= 0, (
        f"down_run must be a non-negative int — {ctx}"
    )


# ---------------------------------------------------------------------------
# Section 1 — Fixture Integrity
# ---------------------------------------------------------------------------


class TestFixtureIntegrity:
    """Verify that every OHLCV fixture satisfies structural integrity rules."""

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_all_bars_are_valid_ohlcv(self, scenario_name: str) -> None:
        """Every bar in every scenario must satisfy OHLCV invariants."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        for i, bar in enumerate(scenario["bars"]):
            _check_valid_ohlcv_bar(bar, i, scenario_name)

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_timestamps_are_monotonically_increasing(self, scenario_name: str) -> None:
        """Bars must be ordered chronologically with no duplicate timestamps."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        bars = scenario["bars"]
        for i in range(1, len(bars)):
            prev_ts = bars[i - 1]["timestamp"]
            curr_ts = bars[i]["timestamp"]
            assert curr_ts > prev_ts, (
                f"scenario={scenario_name!r}: bar {i} timestamp {curr_ts} is not "
                f"after bar {i-1} timestamp {prev_ts}"
            )

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_expected_states_cover_all_bars(self, scenario_name: str) -> None:
        """Each scenario must have one expected_state entry per bar."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        bars = scenario["bars"]
        states = scenario["expected_states"]
        assert len(states) == len(bars), (
            f"scenario={scenario_name!r}: {len(states)} state vectors for "
            f"{len(bars)} bars — must match 1:1"
        )

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_state_vector_indices_are_sequential(self, scenario_name: str) -> None:
        """bar_index values in expected_states must be 0, 1, 2, …"""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        for expected_idx, vec in enumerate(scenario["expected_states"]):
            assert vec["bar_index"] == expected_idx, (
                f"scenario={scenario_name!r}: expected_states[{expected_idx}]['bar_index'] "
                f"should be {expected_idx}, got {vec['bar_index']}"
            )

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_all_expected_states_are_valid(self, scenario_name: str) -> None:
        """Every expected-state dict must have valid fields and values."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        for vec in scenario["expected_states"]:
            _check_valid_state_vector(vec, scenario_name)

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_bars_can_be_converted_to_dataframe(self, scenario_name: str) -> None:
        """Bars must be convertible to a DataFrame with the expected columns."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        df = _bars_to_df(scenario["bars"])
        expected_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        assert expected_cols.issubset(set(df.columns)), (
            f"scenario={scenario_name!r}: DataFrame missing columns "
            f"{expected_cols - set(df.columns)}"
        )
        assert len(df) == len(scenario["bars"])

    def test_lookahead_source_bars_are_valid_ohlcv(self) -> None:
        """Look-ahead safety fixture bars must satisfy OHLCV integrity."""
        scenario = OTF_LOOKAHEAD_SAFETY
        for i, bar in enumerate(scenario["bars"]):
            _check_valid_ohlcv_bar(bar, i, "lookahead_safety")

    def test_lookahead_source_bars_are_monotonically_increasing(self) -> None:
        """Look-ahead source bars must be chronological."""
        bars = OTF_LOOKAHEAD_SAFETY["bars"]
        for i in range(1, len(bars)):
            assert bars[i]["timestamp"] > bars[i - 1]["timestamp"]

    def test_supported_timeframes(self) -> None:
        """SUPPORTED_TIMEFRAMES must contain exactly 5m, 15m, and 30m."""
        assert set(SUPPORTED_TIMEFRAMES) == {"5m", "15m", "30m"}

    def test_valid_states_vocabulary(self) -> None:
        """VALID_STATES must contain exactly the four v1 state names."""
        assert VALID_STATES == frozenset({"up", "down", "neutral", "unknown"})


# ---------------------------------------------------------------------------
# Section 2 — First-Bar Rule (§3.1 / §3.9)
# ---------------------------------------------------------------------------


class TestFirstBarRule:
    """The first bar of a session must always produce state='unknown'."""

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_first_bar_state_is_unknown(self, scenario_name: str) -> None:
        """Bar 0 (first bar of session) must have state='unknown'."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        first = scenario["expected_states"][0]
        assert first["state"] == "unknown", (
            f"scenario={scenario_name!r}: first bar state should be 'unknown', "
            f"got {first['state']!r}"
        )

    @pytest.mark.parametrize("scenario_name", list(ALL_OHLCV_SCENARIOS))
    def test_first_bar_runs_are_zero(self, scenario_name: str) -> None:
        """Bar 0 must have up_run=0 and down_run=0 (no previous bar to compare)."""
        scenario = ALL_OHLCV_SCENARIOS[scenario_name]
        first = scenario["expected_states"][0]
        assert first["up_run"] == 0, (
            f"scenario={scenario_name!r}: first bar up_run should be 0"
        )
        assert first["down_run"] == 0, (
            f"scenario={scenario_name!r}: first bar down_run should be 0"
        )


# ---------------------------------------------------------------------------
# Section 3 — OTF Up Contract (§3.2, §3.4)
# ---------------------------------------------------------------------------


class TestOtfUpContract:
    """Verify OTF up scenarios against the contract's strict higher-low rule."""

    def test_up_established_at_bar_3(self) -> None:
        """State becomes 'up' at bar 3 (after 3 consecutive higher lows)."""
        s = OTF_UP_ESTABLISHED["expected_states"]
        assert s[3]["state"] == "up"
        assert s[3]["up_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS

    def test_up_extends_beyond_minimum(self) -> None:
        """State remains 'up' when up_run exceeds minimum_consecutive_bars."""
        s = OTF_UP_ESTABLISHED["expected_states"]
        assert s[4]["state"] == "up"
        assert s[4]["up_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS + 1

    def test_bars_before_up_are_neutral(self) -> None:
        """Bars 1 and 2 have insufficient run to be 'up'; they should be 'neutral'."""
        s = OTF_UP_ESTABLISHED["expected_states"]
        assert s[1]["state"] == "neutral"
        assert s[2]["state"] == "neutral"

    def test_up_ohlcv_each_bar_has_higher_low(self) -> None:
        """OHLCV consistency: every bar contributing to up_run must have
        strictly higher low than the preceding bar."""
        bars = OTF_UP_ESTABLISHED["bars"]
        states = OTF_UP_ESTABLISHED["expected_states"]
        min_bars = OTF_UP_ESTABLISHED["minimum_consecutive_bars"]
        for i, vec in enumerate(states):
            if vec["up_run"] >= 1:
                assert bars[i]["low"] > bars[i - 1]["low"], (
                    f"up_run={vec['up_run']} at bar {i} but "
                    f"low({bars[i]['low']}) <= prev_low({bars[i-1]['low']})"
                )
            if vec["state"] == "up":
                # Verify the most recent min_bars bars each have higher lows.
                for j in range(i - min_bars + 1, i + 1):
                    assert bars[j]["low"] > bars[j - 1]["low"], (
                        f"state='up' at bar {i} but bar {j} low is not strictly "
                        f"higher than bar {j-1} low"
                    )


# ---------------------------------------------------------------------------
# Section 4 — OTF Down Contract (§3.3, §3.4)
# ---------------------------------------------------------------------------


class TestOtfDownContract:
    """Verify OTF down scenarios against the contract's strict lower-high rule."""

    def test_down_established_at_bar_3(self) -> None:
        """State becomes 'down' at bar 3 (after 3 consecutive lower highs)."""
        s = OTF_DOWN_ESTABLISHED["expected_states"]
        assert s[3]["state"] == "down"
        assert s[3]["down_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS

    def test_down_extends_beyond_minimum(self) -> None:
        """State remains 'down' when down_run exceeds minimum_consecutive_bars."""
        s = OTF_DOWN_ESTABLISHED["expected_states"]
        assert s[4]["state"] == "down"
        assert s[4]["down_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS + 1

    def test_bars_before_down_are_neutral(self) -> None:
        """Bars 1 and 2 are 'neutral' (run not yet met)."""
        s = OTF_DOWN_ESTABLISHED["expected_states"]
        assert s[1]["state"] == "neutral"
        assert s[2]["state"] == "neutral"

    def test_down_ohlcv_each_bar_has_lower_high(self) -> None:
        """OHLCV consistency: every bar contributing to down_run must have
        strictly lower high than the preceding bar."""
        bars = OTF_DOWN_ESTABLISHED["bars"]
        states = OTF_DOWN_ESTABLISHED["expected_states"]
        min_bars = OTF_DOWN_ESTABLISHED["minimum_consecutive_bars"]
        for i, vec in enumerate(states):
            if vec["down_run"] >= 1:
                assert bars[i]["high"] < bars[i - 1]["high"], (
                    f"down_run={vec['down_run']} at bar {i} but "
                    f"high({bars[i]['high']}) >= prev_high({bars[i-1]['high']})"
                )
            if vec["state"] == "down":
                for j in range(i - min_bars + 1, i + 1):
                    assert bars[j]["high"] < bars[j - 1]["high"], (
                        f"state='down' at bar {i} but bar {j} high is not strictly "
                        f"lower than bar {j-1} high"
                    )


# ---------------------------------------------------------------------------
# Section 5 — Neutral State (§3.5)
# ---------------------------------------------------------------------------


class TestNeutralState:
    """Verify neutral-state scenarios."""

    def test_neutral_bars_never_reach_up_state(self) -> None:
        """No bar in the neutral scenario should reach state='up'."""
        for vec in OTF_NEUTRAL["expected_states"]:
            assert vec["state"] != "up", (
                f"bar {vec['bar_index']} unexpectedly reached 'up' in neutral scenario"
            )

    def test_neutral_bars_never_reach_down_state(self) -> None:
        """No bar in the neutral scenario should reach state='down'."""
        for vec in OTF_NEUTRAL["expected_states"]:
            assert vec["state"] != "down", (
                f"bar {vec['bar_index']} unexpectedly reached 'down' in neutral scenario"
            )

    def test_neutral_runs_never_reach_minimum(self) -> None:
        """In the neutral scenario, neither up_run nor down_run ever reaches
        minimum_consecutive_bars."""
        min_bars = OTF_NEUTRAL["minimum_consecutive_bars"]
        for vec in OTF_NEUTRAL["expected_states"]:
            assert vec["up_run"] < min_bars, (
                f"bar {vec['bar_index']}: up_run={vec['up_run']} reached minimum"
            )
            assert vec["down_run"] < min_bars, (
                f"bar {vec['bar_index']}: down_run={vec['down_run']} reached minimum"
            )


# ---------------------------------------------------------------------------
# Section 6 — Sequence Break (§3.6)
# ---------------------------------------------------------------------------


class TestSequenceBreak:
    """Verify that a sequence break returns state to neutral and resets the run."""

    def test_up_break_at_bar_4_resets_up_run(self) -> None:
        """After OTF up is broken at bar 4, up_run must be 0."""
        s = OTF_SEQUENCE_BREAK_UP["expected_states"]
        assert s[4]["up_run"] == 0
        assert s[4]["state"] == "neutral"

    def test_up_break_ohlcv_low_not_higher(self) -> None:
        """Bar 4 must have a low <= bar 3 low (confirming the break trigger)."""
        bars = OTF_SEQUENCE_BREAK_UP["bars"]
        assert bars[4]["low"] <= bars[3]["low"], (
            "Break fixture: bar 4 low should be <= bar 3 low to justify break"
        )

    def test_down_break_at_bar_4_resets_down_run(self) -> None:
        """After OTF down is broken at bar 4, down_run must be 0."""
        s = OTF_SEQUENCE_BREAK_DOWN["expected_states"]
        assert s[4]["down_run"] == 0

    def test_down_break_ohlcv_high_not_lower(self) -> None:
        """Bar 4 must have a high >= bar 3 high (confirming the break trigger)."""
        bars = OTF_SEQUENCE_BREAK_DOWN["bars"]
        assert bars[4]["high"] >= bars[3]["high"], (
            "Break fixture: bar 4 high should be >= bar 3 high to justify break"
        )

    def test_state_was_up_before_break(self) -> None:
        """Bar 3 (pre-break) must be 'up'."""
        s = OTF_SEQUENCE_BREAK_UP["expected_states"]
        assert s[3]["state"] == "up"

    def test_state_was_down_before_break(self) -> None:
        """Bar 3 (pre-break) must be 'down'."""
        s = OTF_SEQUENCE_BREAK_DOWN["expected_states"]
        assert s[3]["state"] == "down"


# ---------------------------------------------------------------------------
# Section 7 — Reversal (§3.7)
# ---------------------------------------------------------------------------


class TestReversal:
    """Verify that the up-to-down reversal scenario transitions correctly."""

    def test_reversal_up_at_bar_3(self) -> None:
        """State is 'up' at bar 3 in the reversal scenario."""
        s = OTF_REVERSAL_UP_TO_DOWN["expected_states"]
        assert s[3]["state"] == "up"

    def test_reversal_breaks_up_at_bar_4(self) -> None:
        """Bar 4 breaks the up sequence."""
        s = OTF_REVERSAL_UP_TO_DOWN["expected_states"]
        assert s[4]["state"] == "neutral"
        assert s[4]["up_run"] == 0

    def test_reversal_down_established_at_bar_6(self) -> None:
        """State becomes 'down' at bar 6 (3 consecutive lower highs)."""
        s = OTF_REVERSAL_UP_TO_DOWN["expected_states"]
        assert s[6]["state"] == "down"
        assert s[6]["down_run"] == DEFAULT_MINIMUM_CONSECUTIVE_BARS

    def test_reversal_ohlcv_down_bars_have_lower_highs(self) -> None:
        """Bars 4, 5, 6 must each have strictly lower high than their predecessor."""
        bars = OTF_REVERSAL_UP_TO_DOWN["bars"]
        for i in range(4, 7):
            assert bars[i]["high"] < bars[i - 1]["high"], (
                f"Reversal: bar {i} high({bars[i]['high']}) should be < "
                f"bar {i-1} high({bars[i-1]['high']})"
            )


# ---------------------------------------------------------------------------
# Section 8 — Equal High / Equal Low (§3.8)
# ---------------------------------------------------------------------------


class TestEqualHighLow:
    """Verify that equal highs and equal lows break their respective sequences."""

    def test_equal_low_resets_up_run(self) -> None:
        """Equal low at bar 2 must reset up_run to 0 (not a higher low)."""
        s = OTF_EQUAL_LOW["expected_states"]
        assert s[2]["up_run"] == 0
        assert s[2]["state"] == "neutral"

    def test_equal_low_ohlcv_confirmed(self) -> None:
        """Bar 2 and bar 1 must have exactly equal lows in the equal-low fixture."""
        bars = OTF_EQUAL_LOW["bars"]
        assert bars[2]["low"] == bars[1]["low"], (
            f"Equal-low fixture: bar 2 low ({bars[2]['low']}) != "
            f"bar 1 low ({bars[1]['low']})"
        )

    def test_up_run_before_equal_low_was_positive(self) -> None:
        """up_run at bar 1 must be positive before the equal low at bar 2."""
        s = OTF_EQUAL_LOW["expected_states"]
        assert s[1]["up_run"] >= 1

    def test_equal_high_resets_down_run(self) -> None:
        """Equal high at bar 2 must reset down_run to 0 (not a lower high)."""
        s = OTF_EQUAL_HIGH["expected_states"]
        assert s[2]["down_run"] == 0
        assert s[2]["state"] == "neutral"

    def test_equal_high_ohlcv_confirmed(self) -> None:
        """Bar 2 and bar 1 must have exactly equal highs in the equal-high fixture."""
        bars = OTF_EQUAL_HIGH["bars"]
        assert bars[2]["high"] == bars[1]["high"], (
            f"Equal-high fixture: bar 2 high ({bars[2]['high']}) != "
            f"bar 1 high ({bars[1]['high']})"
        )

    def test_down_run_before_equal_high_was_positive(self) -> None:
        """down_run at bar 1 must be positive before the equal high at bar 2."""
        s = OTF_EQUAL_HIGH["expected_states"]
        assert s[1]["down_run"] >= 1


# ---------------------------------------------------------------------------
# Section 9 — Insufficient History (§3.9)
# ---------------------------------------------------------------------------


class TestInsufficientHistory:
    """Verify insufficient-history fixture returns unknown for single bar."""

    def test_single_bar_state_is_unknown(self) -> None:
        """A single bar must produce state='unknown'."""
        s = OTF_INSUFFICIENT_HISTORY["expected_states"]
        assert len(s) == 1
        assert s[0]["state"] == "unknown"

    def test_single_bar_runs_are_zero(self) -> None:
        """A single bar must have up_run=0 and down_run=0."""
        s = OTF_INSUFFICIENT_HISTORY["expected_states"]
        assert s[0]["up_run"] == 0
        assert s[0]["down_run"] == 0


# ---------------------------------------------------------------------------
# Section 10 — Session Boundary (§3.10)
# ---------------------------------------------------------------------------


class TestSessionBoundary:
    """Verify that OTF state resets at session boundary."""

    def test_session_1_reaches_up(self) -> None:
        """Session 1 must reach state='up' at bar 3."""
        s = OTF_SESSION_BOUNDARY["expected_states"]
        assert s[3]["state"] == "up"
        assert s[3].get("session") == 1

    def test_session_2_first_bar_is_unknown(self) -> None:
        """First bar of session 2 (bar 4) must be state='unknown'."""
        s = OTF_SESSION_BOUNDARY["expected_states"]
        assert s[4]["state"] == "unknown"
        assert s[4].get("session") == 2

    def test_session_2_first_bar_runs_are_zero(self) -> None:
        """Runs must be zero at start of session 2."""
        s = OTF_SESSION_BOUNDARY["expected_states"]
        assert s[4]["up_run"] == 0
        assert s[4]["down_run"] == 0

    def test_session_2_second_bar_is_neutral(self) -> None:
        """Bar 5 (second bar of session 2) has insufficient run → neutral."""
        s = OTF_SESSION_BOUNDARY["expected_states"]
        assert s[5]["state"] == "neutral"
        assert s[5].get("session") == 2

    def test_session_boundary_dates_differ(self) -> None:
        """Bar 3 (session 1) and bar 4 (session 2) must be on different dates."""
        bars = OTF_SESSION_BOUNDARY["bars"]
        date_s1 = bars[3]["timestamp"].date()
        date_s2 = bars[4]["timestamp"].date()
        assert date_s1 != date_s2, (
            "Session boundary fixture: bars 3 and 4 should be on different dates"
        )


# ---------------------------------------------------------------------------
# Section 10b — Overnight Session (§3.10 — futures eth_start convention)
# ---------------------------------------------------------------------------


class TestOvernightSession:
    """Verify that midnight does not reset OTF state for futures instruments.

    ThesisTester uses trading_session_date(local_ts, eth_start) from
    thesistester/levels/session_date.py to determine session boundaries.
    For ES/NQ futures (eth_start='18:00', exchange_tz='America/New_York'),
    the session boundary is at 18:00 ET, NOT at midnight.

    These tests use the production trading_session_date() function directly
    to verify that the fixture's expected_states match the repository's
    session-date convention.  This is fixture-verification only; no
    competing session algorithm is implemented here.
    """

    def test_bars_span_midnight(self) -> None:
        """Overnight fixture must include bars before and after midnight ET."""
        bars = OTF_OVERNIGHT_SESSION["bars"]
        timestamps_et = [b["timestamp"].tz_convert("America/New_York") for b in bars]
        dates = [ts.date() for ts in timestamps_et]
        # bars 0–1 are on 2026-01-05 (Monday), bars 2–4 are on 2026-01-06 (Tuesday)
        assert any(d.isoformat() == "2026-01-05" for d in dates), (
            "Overnight fixture must have bars on 2026-01-05 (Monday evening)"
        )
        assert any(d.isoformat() == "2026-01-06" for d in dates), (
            "Overnight fixture must have bars on 2026-01-06 (after midnight)"
        )

    def test_midnight_does_not_reset_state(self) -> None:
        """Bar 2 (00:00 ET, after midnight) must NOT reset OTF state.

        Bar 2 is at 2026-01-06 00:00 ET which is after midnight but still
        within the Tuesday trading session.  The expected state is 'neutral'
        (not 'unknown'), confirming that midnight is not a session boundary.
        """
        s = OTF_OVERNIGHT_SESSION["expected_states"]
        bar_2 = s[2]
        # Bar 2 is the midnight bar
        bars = OTF_OVERNIGHT_SESSION["bars"]
        ts_et = bars[2]["timestamp"].tz_convert("America/New_York")
        assert ts_et.hour == 0 and ts_et.minute == 0, (
            f"Test setup: bar 2 should be at 00:00 ET, got {ts_et}"
        )
        assert bar_2["state"] != "unknown", (
            "Midnight bar (00:00 ET) must not produce 'unknown' state — "
            "midnight is not a session boundary for ES/NQ futures"
        )
        assert bar_2["state"] == "neutral", (
            f"Midnight bar must continue OTF sequence as 'neutral', got {bar_2['state']!r}"
        )
        assert bar_2["up_run"] == 2, (
            f"up_run must continue across midnight (expected 2), got {bar_2['up_run']}"
        )

    def test_session_boundary_at_1800_resets_state(self) -> None:
        """Bar 4 (18:00 ET Tuesday) is the true session boundary; state must reset to 'unknown'."""
        bars = OTF_OVERNIGHT_SESSION["bars"]
        s = OTF_OVERNIGHT_SESSION["expected_states"]
        bar_4 = s[4]
        ts_et = bars[4]["timestamp"].tz_convert("America/New_York")
        assert ts_et.hour == 18 and ts_et.minute == 0, (
            f"Test setup: bar 4 should be at 18:00 ET, got {ts_et}"
        )
        assert bar_4["state"] == "unknown", (
            "Bar at 18:00 ET (eth_start boundary) must reset OTF state to 'unknown'"
        )
        assert bar_4["up_run"] == 0, (
            f"up_run must be 0 after session reset, got {bar_4['up_run']}"
        )
        assert bar_4["down_run"] == 0, (
            f"down_run must be 0 after session reset, got {bar_4['down_run']}"
        )

    def test_fixture_uses_exchange_local_timestamps(self) -> None:
        """All overnight fixture bars must use timezone-aware timestamps in America/New_York."""
        bars = OTF_OVERNIGHT_SESSION["bars"]
        for i, bar in enumerate(bars):
            ts = bar["timestamp"]
            assert ts.tzinfo is not None, f"Bar {i} timestamp must be timezone-aware"
            ts_et = ts.tz_convert("America/New_York")
            assert str(ts_et.tz) == "America/New_York", (
                f"Bar {i} should be representable in America/New_York"
            )

    def test_session_assignment_matches_trading_session_date(self) -> None:
        """Expected trading_session_date values must match the production helper.

        This verifies the fixture against thesistester/levels/session_date.py::
        trading_session_date().  It does not reimplement session logic; it
        calls the production function directly.
        """
        bars = OTF_OVERNIGHT_SESSION["bars"]
        eth_start = OTF_OVERNIGHT_SESSION["eth_start"]
        exchange_tz = OTF_OVERNIGHT_SESSION["exchange_tz"]

        timestamps_et = pd.Series(
            [b["timestamp"].tz_convert(exchange_tz) for b in bars]
        )
        computed_dates = trading_session_date(timestamps_et, eth_start)

        expected = OTF_OVERNIGHT_SESSION["expected_states"]
        for i, (computed, vec) in enumerate(zip(computed_dates, expected)):
            expected_date = vec["trading_session_date"]
            assert str(computed) == expected_date, (
                f"Bar {i}: production trading_session_date={computed!r} "
                f"does not match fixture expected_states trading_session_date={expected_date!r}"
            )

    def test_all_pre_boundary_bars_share_session_date(self) -> None:
        """Bars 0–3 (before the 18:00 ET boundary) must all have the same trading_session_date."""
        s = OTF_OVERNIGHT_SESSION["expected_states"]
        dates = {vec["trading_session_date"] for vec in s[:4]}
        assert len(dates) == 1, (
            f"Bars 0–3 should all share one trading_session_date, got: {dates}"
        )
        assert "2026-01-06" in dates

    def test_boundary_bar_has_different_session_date(self) -> None:
        """Bar 4 (18:00 ET boundary) must have a different trading_session_date than bars 0–3."""
        s = OTF_OVERNIGHT_SESSION["expected_states"]
        pre_boundary_date = s[0]["trading_session_date"]
        boundary_date = s[4]["trading_session_date"]
        assert boundary_date != pre_boundary_date, (
            f"Bar 4 should have a different trading_session_date ({boundary_date!r}) "
            f"than bars 0–3 ({pre_boundary_date!r})"
        )
        assert boundary_date == "2026-01-07"


# ---------------------------------------------------------------------------
# Section 11 — Look-Ahead Safety (§3.11)
# ---------------------------------------------------------------------------


class TestLookaheadSafety:
    """Verify look-ahead safety contract vectors."""

    def test_vectors_present(self) -> None:
        """The look-ahead fixture must have at least one vector."""
        assert len(OTF_LOOKAHEAD_SAFETY["lookahead_vectors"]) >= 1

    @pytest.mark.parametrize(
        "vector",
        OTF_LOOKAHEAD_SAFETY["lookahead_vectors"],
        ids=[v["signal_timestamp"] for v in OTF_LOOKAHEAD_SAFETY["lookahead_vectors"]],
    )
    def test_signal_timestamp_precedes_inprogress_bar_close(self, vector: dict) -> None:
        """Signal timestamp must be strictly before the in-progress bar's close time
        for vectors where must_not_use_bar_C_high is True."""
        sig_ts = pd.Timestamp(vector["signal_timestamp"], tz=TZ)
        in_progress_close = pd.Timestamp(vector["in_progress_5m_close_time"], tz=TZ)
        if vector["must_not_use_bar_C_high"]:
            assert sig_ts < in_progress_close, (
                f"Signal at {sig_ts} should be before in-progress bar close "
                f"{in_progress_close} when must_not_use_bar_C_high=True"
            )

    @pytest.mark.parametrize(
        "vector",
        OTF_LOOKAHEAD_SAFETY["lookahead_vectors"],
        ids=[v["signal_timestamp"] for v in OTF_LOOKAHEAD_SAFETY["lookahead_vectors"]],
    )
    def test_last_completed_bar_close_at_or_before_signal(self, vector: dict) -> None:
        """Last completed HTF bar's close time must be <= signal timestamp."""
        sig_ts = pd.Timestamp(vector["signal_timestamp"], tz=TZ)
        last_close = pd.Timestamp(vector["last_completed_5m_close_time"], tz=TZ)
        assert last_close <= sig_ts, (
            f"Last completed bar close {last_close} must be <= signal timestamp {sig_ts}"
        )

    def test_at_5m_close_bar_becomes_available(self) -> None:
        """A 5m bar is available exactly at its close time (signal_timestamp == close_time)."""
        # The third vector has signal_timestamp == in-progress becomes completed
        vec = next(
            v for v in OTF_LOOKAHEAD_SAFETY["lookahead_vectors"]
            if not v["must_not_use_bar_C_high"]
        )
        sig_ts = pd.Timestamp(vec["signal_timestamp"], tz=TZ)
        last_close = pd.Timestamp(vec["last_completed_5m_close_time"], tz=TZ)
        assert sig_ts == last_close, (
            f"At exact close time the bar should become available: "
            f"signal_timestamp={sig_ts}, last_completed_close={last_close}"
        )

    def test_source_interval_is_1m(self) -> None:
        """The look-ahead fixture uses 1-minute source bars."""
        assert OTF_LOOKAHEAD_SAFETY["source_interval"] == "1m"

    def test_target_timeframe_is_5m(self) -> None:
        """The look-ahead fixture targets 5-minute OTF."""
        assert OTF_LOOKAHEAD_SAFETY["target_timeframe"] == "5m"

    def test_inprogress_bar_has_higher_final_values(self) -> None:
        """The in-progress 5m bar (bars 10–14, 09:30–09:35) reaches higher
        values by close than were visible at 09:31, demonstrating why
        look-ahead use would violate the contract."""
        bars = OTF_LOOKAHEAD_SAFETY["bars"]
        # bar at index 10 is the first 1m bar of the in-progress 5m period (09:30)
        # bar at index 14 is the last 1m bar (09:34) of that 5m period
        bar_10_high = bars[10]["high"]  # partial view at 09:30
        bar_14_high = bars[14]["high"]  # final high at 09:34 (= eventual 5m bar high)
        assert bar_14_high > bar_10_high, (
            "In-progress 5m bar should have a higher eventual high than its first "
            "1m bar, demonstrating look-ahead risk"
        )

    def test_htf_intervals_present(self) -> None:
        """The look-ahead fixture must define explicit HTF interval timestamps."""
        assert "htf_intervals" in OTF_LOOKAHEAD_SAFETY
        assert len(OTF_LOOKAHEAD_SAFETY["htf_intervals"]) == 3

    def test_htf_interval_start_plus_duration_equals_close(self) -> None:
        """bar_close_timestamp must equal bar_start_timestamp + 5 minutes for every interval."""
        for interval in OTF_LOOKAHEAD_SAFETY["htf_intervals"]:
            start = pd.Timestamp(interval["bar_start_timestamp"], tz=TZ)
            close = pd.Timestamp(interval["bar_close_timestamp"], tz=TZ)
            assert close == start + pd.Timedelta(minutes=5), (
                f"Interval {interval['bar_label']}: "
                f"bar_close_timestamp ({close}) != bar_start_timestamp ({start}) + 5min"
            )

    def test_availability_timestamp_equals_close_timestamp(self) -> None:
        """availability_timestamp must equal bar_close_timestamp for every interval."""
        for interval in OTF_LOOKAHEAD_SAFETY["htf_intervals"]:
            close = pd.Timestamp(interval["bar_close_timestamp"], tz=TZ)
            avail = pd.Timestamp(interval["availability_timestamp"], tz=TZ)
            assert avail == close, (
                f"Interval {interval['bar_label']}: "
                f"availability_timestamp ({avail}) != bar_close_timestamp ({close})"
            )

    def test_resampled_row_label_is_start_not_close(self) -> None:
        """Resampled row label must equal bar_start_timestamp, not bar_close_timestamp."""
        for interval in OTF_LOOKAHEAD_SAFETY["htf_intervals"]:
            label = pd.Timestamp(interval["resampled_row_label"], tz=TZ)
            start = pd.Timestamp(interval["bar_start_timestamp"], tz=TZ)
            close = pd.Timestamp(interval["bar_close_timestamp"], tz=TZ)
            assert label == start, (
                f"Interval {interval['bar_label']}: "
                f"resampled_row_label ({label}) must equal bar_start_timestamp ({start})"
            )
            assert label != close, (
                f"Interval {interval['bar_label']}: "
                f"resampled_row_label ({label}) must NOT equal bar_close_timestamp ({close}) — "
                "the row label cannot be used as the availability timestamp"
            )

    def test_actual_resample_5m_uses_close_timestamp_for_otf_availability(self) -> None:
        """Actual 5m resampler output must use bar close, not row label, for OTF availability."""
        expected_labels = [
            pd.Timestamp(interval["bar_start_timestamp"], tz=TZ)
            for interval in OTF_LOOKAHEAD_SAFETY["htf_intervals"]
        ]
        source_df = _bars_to_df(OTF_LOOKAHEAD_SAFETY["bars"])
        resampled = resample_ohlcv(source_df, "5min").copy()

        assert str(resampled["timestamp"].dt.tz) == TZ
        assert resampled["timestamp"].tolist() == expected_labels

        resampled["bar_close_timestamp"] = (
            resampled["timestamp"] + pd.Timedelta(minutes=5)
        )
        resampled["availability_timestamp"] = resampled["bar_close_timestamp"]

        signal_0933 = pd.Timestamp("2026-01-05 09:33", tz=TZ)
        eligible_0933 = resampled.loc[
            resampled["availability_timestamp"] <= signal_0933
        ].reset_index(drop=True)
        assert eligible_0933["timestamp"].tolist() == expected_labels[:2]

        bar_0930 = resampled.loc[
            resampled["timestamp"] == pd.Timestamp("2026-01-05 09:30", tz=TZ)
        ].iloc[0]
        assert bar_0930["bar_close_timestamp"] == pd.Timestamp("2026-01-05 09:35", tz=TZ)
        assert bar_0930["timestamp"] not in eligible_0933["timestamp"].tolist()

        last_eligible_0933 = eligible_0933.iloc[-1]
        assert last_eligible_0933["timestamp"] == pd.Timestamp("2026-01-05 09:25", tz=TZ)
        assert bar_0930["high"] not in eligible_0933["high"].tolist()
        assert bar_0930["low"] not in eligible_0933["low"].tolist()

        signal_0935 = pd.Timestamp("2026-01-05 09:35", tz=TZ)
        eligible_0935 = resampled.loc[
            resampled["availability_timestamp"] <= signal_0935
        ].reset_index(drop=True)
        assert eligible_0935["timestamp"].tolist() == expected_labels
        assert eligible_0935.iloc[-1]["timestamp"] == bar_0930["timestamp"]
        assert eligible_0935.iloc[-1]["high"] == bar_0930["high"]
        assert eligible_0935.iloc[-1]["low"] == bar_0930["low"]

    def test_signal_before_close_cannot_use_inprogress_bar(self) -> None:
        """A signal strictly before bar_close_timestamp must not use that bar.

        Confirms the rule: available_bars = {bar : availability_timestamp <= signal_T}
        """
        # Signal at 09:33 — bar C availability is 09:35 → not available
        bar_c = next(
            iv for iv in OTF_LOOKAHEAD_SAFETY["htf_intervals"]
            if iv["bar_label"] == "5m_bar_C"
        )
        signal_ts = pd.Timestamp("2026-01-05 09:33", tz=TZ)
        avail = pd.Timestamp(bar_c["availability_timestamp"], tz=TZ)
        assert signal_ts < avail, (
            f"Signal at {signal_ts} should be before bar C availability ({avail})"
        )

    def test_signal_at_exact_close_can_use_bar(self) -> None:
        """A signal exactly at bar_close_timestamp can use that completed bar.

        Confirms the boundary rule: bar.availability_timestamp == T is available.
        """
        bar_b = next(
            iv for iv in OTF_LOOKAHEAD_SAFETY["htf_intervals"]
            if iv["bar_label"] == "5m_bar_B"
        )
        # Boundary case for bar B: a signal exactly at 09:30 can use bar B.
        signal_at_bar_b_close = pd.Timestamp("2026-01-05 09:30", tz=TZ)
        avail_b = pd.Timestamp(bar_b["bar_close_timestamp"], tz=TZ)
        assert signal_at_bar_b_close == avail_b, (
            f"Signal exactly at bar B close ({signal_at_bar_b_close}) should == "
            f"bar B availability ({avail_b})"
        )

    def test_vector_bar_start_timestamps_present(self) -> None:
        """Each lookahead_vector must include last_completed_5m_bar_start."""
        for vec in OTF_LOOKAHEAD_SAFETY["lookahead_vectors"]:
            assert "last_completed_5m_bar_start" in vec, (
                f"Vector for signal {vec['signal_timestamp']!r} missing "
                "'last_completed_5m_bar_start'"
            )


# ---------------------------------------------------------------------------
# Section 12 — Directional Eligibility (§3.12)
# ---------------------------------------------------------------------------


class TestDirectionalEligibility:
    """Verify the directional filter eligibility contract vectors."""

    def test_up_long_passes(self) -> None:
        """OTF up + long signal must pass."""
        vec = next(
            v for v in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]
            if v["otf_state"] == "up" and v["signal_direction"] == "long"
        )
        assert vec["passes"] is True

    def test_up_short_fails(self) -> None:
        """OTF up + short signal must fail."""
        vec = next(
            v for v in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]
            if v["otf_state"] == "up" and v["signal_direction"] == "short"
        )
        assert vec["passes"] is False

    def test_down_short_passes(self) -> None:
        """OTF down + short signal must pass."""
        vec = next(
            v for v in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]
            if v["otf_state"] == "down" and v["signal_direction"] == "short"
        )
        assert vec["passes"] is True

    def test_down_long_fails(self) -> None:
        """OTF down + long signal must fail."""
        vec = next(
            v for v in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]
            if v["otf_state"] == "down" and v["signal_direction"] == "long"
        )
        assert vec["passes"] is False

    def test_neutral_always_fails(self) -> None:
        """OTF neutral must fail for both directions."""
        for vec in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]:
            if vec["otf_state"] == "neutral":
                assert vec["passes"] is False, (
                    f"neutral state should always fail, got passes=True for "
                    f"direction={vec['signal_direction']!r}"
                )

    def test_unknown_always_fails(self) -> None:
        """OTF unknown must fail for both directions."""
        for vec in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]:
            if vec["otf_state"] == "unknown":
                assert vec["passes"] is False, (
                    f"unknown state should always fail, got passes=True for "
                    f"direction={vec['signal_direction']!r}"
                )

    def test_passing_vectors_have_no_reason(self) -> None:
        """Passing vectors must have reason=None (no rejection message needed)."""
        for vec in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]:
            if vec["passes"]:
                assert vec["reason"] is None, (
                    f"Passing vector should have reason=None, got {vec['reason']!r}"
                )

    def test_failing_vectors_have_reason(self) -> None:
        """Failing vectors must have a non-empty rejection reason."""
        for vec in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]:
            if not vec["passes"]:
                assert vec["reason"] is not None and len(vec["reason"]) > 0, (
                    f"Failing vector for state={vec['otf_state']!r}, "
                    f"direction={vec['signal_direction']!r} must have a reason"
                )

    def test_all_valid_states_covered(self) -> None:
        """Every valid state must appear in the eligibility vectors."""
        covered = {v["otf_state"] for v in OTF_DIRECTIONAL_ELIGIBILITY["vectors"]}
        assert covered == VALID_STATES


# ---------------------------------------------------------------------------
# Section 13 — All-Timeframe Alignment (§3.13)
# ---------------------------------------------------------------------------


class TestAllTimeframeAlignment:
    """Verify the 'all' alignment-mode contract vectors."""

    def test_all_up_long_passes(self) -> None:
        """All timeframes up + long signal must pass."""
        vec = next(
            v for v in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]
            if v["signal_direction"] == "long"
            and all(s == "up" for s in v["timeframe_states"].values())
        )
        assert vec["passes"] is True

    def test_any_non_up_long_fails(self) -> None:
        """Long signal fails if any timeframe is not 'up'."""
        failing = [
            v for v in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]
            if v["signal_direction"] == "long"
            and not all(s == "up" for s in v["timeframe_states"].values())
        ]
        assert len(failing) > 0, "No long-fail vectors present"
        for vec in failing:
            assert vec["passes"] is False

    def test_all_down_short_passes(self) -> None:
        """All timeframes down + short signal must pass."""
        vec = next(
            v for v in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]
            if v["signal_direction"] == "short"
            and all(s == "down" for s in v["timeframe_states"].values())
        )
        assert vec["passes"] is True

    def test_any_non_down_short_fails(self) -> None:
        """Short signal fails if any timeframe is not 'down'."""
        failing = [
            v for v in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]
            if v["signal_direction"] == "short"
            and not all(s == "down" for s in v["timeframe_states"].values())
        ]
        assert len(failing) > 0, "No short-fail vectors present"
        for vec in failing:
            assert vec["passes"] is False

    def test_single_timeframe_selection_long_passes(self) -> None:
        """Single selected timeframe (15m=up) is sufficient for long pass."""
        vec = next(
            v for v in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]
            if v["signal_direction"] == "long"
            and set(v["timeframe_states"].keys()) == {"15m"}
            and v["timeframe_states"]["15m"] == "up"
        )
        assert vec["passes"] is True

    def test_alignment_mode_is_all(self) -> None:
        """The alignment mode for this fixture must be 'all'."""
        assert OTF_ALL_TIMEFRAME_ALIGNMENT["alignment_mode"] == "all"

    def test_failing_vectors_have_reasons(self) -> None:
        """Every failing vector must supply a reason."""
        for vec in OTF_ALL_TIMEFRAME_ALIGNMENT["vectors"]:
            if not vec["passes"]:
                assert vec["reason"] is not None and len(vec["reason"]) > 0
