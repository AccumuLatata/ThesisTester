"""Deterministic OHLCV fixtures and OTF v1 contract test vectors.

These fixtures cover every scenario documented in docs/otf-filter.md and
docs/otf-filter-roadmap.md (Phase 1).  They are designed to be used by
tests/test_otf_contract.py to verify fixture integrity and contract
consistency without implementing a production OTF engine.

Contract reference: docs/otf-filter.md — OTF v1 Behavioral Contract
Contract version:   v1
Last updated:       2026-07-23
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default session timezone for all fixtures.
TZ = "America/New_York"

#: Valid OTF state vocabulary (OTF v1 contract §3.1).
VALID_STATES = frozenset({"up", "down", "neutral", "unknown"})

#: OTF v1 default minimum consecutive bars to establish a directional state.
DEFAULT_MINIMUM_CONSECUTIVE_BARS = 3

#: OTF v1 algorithm version identifier (reserved; not yet hashed in production).
OTF_CONTRACT_VERSION = "v1"

#: Supported higher-timeframe labels.
SUPPORTED_TIMEFRAMES = ("5m", "15m", "30m")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar(
    ts: str,
    o: float,
    h: float,
    l: float,
    c: float,
    vol: float = 1000.0,
) -> dict:
    """Return a single OHLCV bar dict with a timezone-aware timestamp."""
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    """Convert a list of bar dicts into a DataFrame with a reset integer index."""
    return pd.DataFrame(bars).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scenario 1 — Established OTF Up
#
# Rule (§3.2): up_run increments each time current bar low > previous bar low.
# Rule (§3.4): state becomes "up" when up_run >= minimum_consecutive_bars.
#
# With minimum_consecutive_bars = 3:
#   bar 0: anchor — no previous bar → state = "unknown"
#   bar 1: L(1)=99.5 > L(0)=99.0 → up_run=1 → state = "neutral"
#   bar 2: L(2)=100.0 > L(1)=99.5 → up_run=2 → state = "neutral"
#   bar 3: L(3)=100.5 > L(2)=100.0 → up_run=3 → state = "up"
#   bar 4: L(4)=101.0 > L(3)=100.5 → up_run=4 → state = "up" (extended)
# ---------------------------------------------------------------------------

OTF_UP_ESTABLISHED: dict = {
    "scenario": "up_established",
    "description": "Five 5-minute bars with strictly increasing lows; OTF up is established at bar 3.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor
        _bar("2026-01-05 09:35", 100.5, 102.0, 99.5, 101.5),  # bar 1
        _bar("2026-01-05 09:40", 101.5, 103.0, 100.0, 102.5),  # bar 2
        _bar("2026-01-05 09:45", 102.5, 104.0, 100.5, 103.5),  # bar 3 → up
        _bar("2026-01-05 09:50", 103.5, 105.0, 101.0, 104.5),  # bar 4 → up (extended)
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 2, "state": "neutral", "up_run": 2, "down_run": 0},
        {"bar_index": 3, "state": "up", "up_run": 3, "down_run": 0},
        {"bar_index": 4, "state": "up", "up_run": 4, "down_run": 0},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 2 — Established OTF Down
#
# Rule (§3.3): down_run increments each time current bar high < previous bar high.
# Rule (§3.4): state becomes "down" when down_run >= minimum_consecutive_bars.
#
# With minimum_consecutive_bars = 3:
#   bar 0: anchor → state = "unknown"
#   bar 1: H(1)=104.0 < H(0)=105.0 → down_run=1 → state = "neutral"
#   bar 2: H(2)=103.0 < H(1)=104.0 → down_run=2 → state = "neutral"
#   bar 3: H(3)=102.0 < H(2)=103.0 → down_run=3 → state = "down"
#   bar 4: H(4)=101.0 < H(3)=102.0 → down_run=4 → state = "down" (extended)
# ---------------------------------------------------------------------------

OTF_DOWN_ESTABLISHED: dict = {
    "scenario": "down_established",
    "description": "Five 5-minute bars with strictly decreasing highs; OTF down is established at bar 3.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 103.0, 105.0, 101.0, 104.0),  # bar 0: anchor
        _bar("2026-01-05 09:35", 102.0, 104.0, 100.0, 103.0),  # bar 1
        _bar("2026-01-05 09:40", 101.0, 103.0, 99.0, 102.0),  # bar 2
        _bar("2026-01-05 09:45", 100.0, 102.0, 98.0, 101.0),  # bar 3 → down
        _bar("2026-01-05 09:50", 99.0, 101.0, 97.0, 100.0),  # bar 4 → down (extended)
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 0, "down_run": 1},
        {"bar_index": 2, "state": "neutral", "up_run": 0, "down_run": 2},
        {"bar_index": 3, "state": "down", "up_run": 0, "down_run": 3},
        {"bar_index": 4, "state": "down", "up_run": 0, "down_run": 4},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 3 — Neutral / Two-Sided Conditions
#
# Rule (§3.5): state = "neutral" when no directional run meets the threshold.
#
# Alternating higher-low / lower-high bars prevent any run from reaching 3:
#   bar 0: anchor → unknown
#   bar 1: H(1)=105 > H(0)=104, L(1)=101 > L(0)=100 → up_run=1, down_run=0
#   bar 2: H(2)=104.5 < H(1)=105, L(2)=100.5 < L(1)=101 → up_run=0, down_run=1
#   bar 3: H(3)=105.5 > H(2)=104.5, L(3)=101.5 > L(2)=100.5 → up_run=1, down_run=0
#   bar 4: H(4)=104.0 < H(3)=105.5, L(4)=100.0 < L(3)=101.5 → up_run=0, down_run=1
# ---------------------------------------------------------------------------

OTF_NEUTRAL: dict = {
    "scenario": "neutral",
    "description": "Alternating direction bars; no run reaches minimum → neutral throughout.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 102.0, 104.0, 100.0, 102.5),  # bar 0: anchor
        _bar("2026-01-05 09:35", 103.0, 105.0, 101.0, 104.0),  # bar 1: up tendency
        _bar("2026-01-05 09:40", 102.5, 104.5, 100.5, 103.0),  # bar 2: down tendency
        _bar("2026-01-05 09:45", 103.5, 105.5, 101.5, 104.5),  # bar 3: up tendency
        _bar("2026-01-05 09:50", 102.0, 104.0, 100.0, 102.5),  # bar 4: down tendency
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 2, "state": "neutral", "up_run": 0, "down_run": 1},
        {"bar_index": 3, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 4, "state": "neutral", "up_run": 0, "down_run": 1},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 4 — Sequence Break (Up → Neutral)
#
# Rule (§3.6): up_run resets to 0 when current bar low <= previous bar low.
#
#   bars 0–3: establish OTF up (up_run grows to 3)
#   bar 4: L(4)=99.0 < L(3)=100.5 → up_run resets to 0 → state = "neutral"
# ---------------------------------------------------------------------------

OTF_SEQUENCE_BREAK_UP: dict = {
    "scenario": "sequence_break_up",
    "description": "OTF up established at bar 3, then broken at bar 4 by a lower low.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor
        _bar("2026-01-05 09:35", 100.5, 102.0, 99.5, 101.5),  # bar 1
        _bar("2026-01-05 09:40", 101.5, 103.0, 100.0, 102.5),  # bar 2
        _bar("2026-01-05 09:45", 102.5, 104.0, 100.5, 103.5),  # bar 3 → up
        _bar("2026-01-05 09:50", 103.0, 105.0, 99.0, 101.0),  # bar 4: break (L=99 < 100.5)
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 2, "state": "neutral", "up_run": 2, "down_run": 0},
        {"bar_index": 3, "state": "up", "up_run": 3, "down_run": 0},
        {"bar_index": 4, "state": "neutral", "up_run": 0, "down_run": 0},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 5 — Sequence Break (Down → Neutral)
#
# Rule (§3.6): down_run resets to 0 when current bar high >= previous bar high.
#
#   bars 0–3: establish OTF down (down_run grows to 3)
#   bar 4: H(4)=104.0 > H(3)=102.0 → down_run resets to 0 → state = "neutral"
# ---------------------------------------------------------------------------

OTF_SEQUENCE_BREAK_DOWN: dict = {
    "scenario": "sequence_break_down",
    "description": "OTF down established at bar 3, then broken at bar 4 by a higher high.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 103.0, 105.0, 101.0, 104.0),  # bar 0: anchor
        _bar("2026-01-05 09:35", 102.0, 104.0, 100.0, 103.0),  # bar 1
        _bar("2026-01-05 09:40", 101.0, 103.0, 99.0, 102.0),  # bar 2
        _bar("2026-01-05 09:45", 100.0, 102.0, 98.0, 101.0),  # bar 3 → down
        _bar("2026-01-05 09:50", 102.0, 104.0, 100.0, 103.0),  # bar 4: break (H=104 > 102)
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 0, "down_run": 1},
        {"bar_index": 2, "state": "neutral", "up_run": 0, "down_run": 2},
        {"bar_index": 3, "state": "down", "up_run": 0, "down_run": 3},
        {"bar_index": 4, "state": "neutral", "up_run": 1, "down_run": 0},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 6 — Reversal (Up → Down)
#
# Rule (§3.7): After an up sequence breaks, down_run begins building if bars
# subsequently post lower highs.  down state is reached when down_run >= min.
#
#   bars 0–3: establish OTF up
#   bar 4: up_run=0 (L drops), down_run=1 (H drops too)
#   bar 5: down_run=2
#   bar 6: down_run=3 → state = "down"
# ---------------------------------------------------------------------------

OTF_REVERSAL_UP_TO_DOWN: dict = {
    "scenario": "reversal_up_to_down",
    "description": "OTF up established, then reverses to OTF down across bars 4–6.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor
        _bar("2026-01-05 09:35", 100.5, 102.0, 99.5, 101.5),  # bar 1
        _bar("2026-01-05 09:40", 101.5, 103.0, 100.0, 102.5),  # bar 2
        _bar("2026-01-05 09:45", 102.5, 104.0, 100.5, 103.5),  # bar 3 → up
        _bar(
            "2026-01-05 09:50", 101.0, 103.0, 98.0, 100.0
        ),  # bar 4: L<prev, H<prev → up_run=0, down_run=1
        _bar("2026-01-05 09:55", 99.0, 102.0, 97.0, 99.0),  # bar 5: H<prev → down_run=2
        _bar("2026-01-05 10:00", 98.0, 101.0, 96.0, 98.0),  # bar 6: H<prev → down_run=3 → down
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 2, "state": "neutral", "up_run": 2, "down_run": 0},
        {"bar_index": 3, "state": "up", "up_run": 3, "down_run": 0},
        {"bar_index": 4, "state": "neutral", "up_run": 0, "down_run": 1},
        {"bar_index": 5, "state": "neutral", "up_run": 0, "down_run": 2},
        {"bar_index": 6, "state": "down", "up_run": 0, "down_run": 3},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 7 — Equal Low (does NOT qualify as higher low)
#
# Rule (§3.8): Strict inequality required.  B.low == P.low is NOT a higher low.
# up_run resets to 0 on equal low.
#
#   bar 0: anchor
#   bar 1: L(1)=99.5 > L(0)=99.0 → up_run=1
#   bar 2: L(2)=99.5 == L(1)=99.5 → up_run=0 (equal low breaks sequence)
#   bar 3: L(3)=100.0 > L(2)=99.5 → up_run=1
# ---------------------------------------------------------------------------

OTF_EQUAL_LOW: dict = {
    "scenario": "equal_low",
    "description": "Equal low at bar 2 is not a higher low; up_run resets to 0.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor
        _bar("2026-01-05 09:35", 100.5, 102.0, 99.5, 101.5),  # bar 1: L=99.5 > 99.0 → up_run=1
        _bar("2026-01-05 09:40", 101.0, 103.0, 99.5, 102.0),  # bar 2: L=99.5 == 99.5 → up_run=0
        _bar("2026-01-05 09:45", 102.0, 104.0, 100.0, 103.0),  # bar 3: L=100.0 > 99.5 → up_run=1
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0},
        {"bar_index": 2, "state": "neutral", "up_run": 0, "down_run": 0},
        {"bar_index": 3, "state": "neutral", "up_run": 1, "down_run": 0},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 8 — Equal High (does NOT qualify as lower high)
#
# Rule (§3.8): Strict inequality required.  B.high == P.high is NOT a lower high.
# down_run resets to 0 on equal high.
#
#   bar 0: anchor
#   bar 1: H(1)=104.0 < H(0)=105.0 → down_run=1
#   bar 2: H(2)=104.0 == H(1)=104.0 → down_run=0 (equal high breaks sequence)
#   bar 3: H(3)=103.0 < H(2)=104.0 → down_run=1
# ---------------------------------------------------------------------------

OTF_EQUAL_HIGH: dict = {
    "scenario": "equal_high",
    "description": "Equal high at bar 2 is not a lower high; down_run resets to 0.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 103.0, 105.0, 101.0, 104.0),  # bar 0: anchor
        _bar("2026-01-05 09:35", 102.0, 104.0, 100.0, 103.0),  # bar 1: H=104.0 < 105.0 → down_run=1
        _bar(
            "2026-01-05 09:40", 102.5, 104.0, 100.5, 103.5
        ),  # bar 2: H=104.0 == 104.0 → down_run=0
        _bar("2026-01-05 09:45", 101.5, 103.0, 99.5, 102.0),  # bar 3: H=103.0 < 104.0 → down_run=1
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
        {"bar_index": 1, "state": "neutral", "up_run": 0, "down_run": 1},
        {"bar_index": 2, "state": "neutral", "up_run": 0, "down_run": 0},
        {"bar_index": 3, "state": "neutral", "up_run": 0, "down_run": 1},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 9 — Insufficient History (single bar)
#
# Rule (§3.9): When fewer than 2 completed bars are available (no previous bar
# to compare), state = "unknown".
# ---------------------------------------------------------------------------

OTF_INSUFFICIENT_HISTORY: dict = {
    "scenario": "insufficient_history",
    "description": "Only one bar — no comparison possible — state is unknown.",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: only bar
    ],
    "expected_states": [
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 10 — Session Boundary (up sequence does NOT carry across sessions)
#
# Rule (§3.10): At each new trading-session boundary up_run and down_run reset
# to 0 and state resets to "unknown".  OTF state does NOT carry across
# trading sessions in v1 (session_reset=True).
#
# "Session boundary" is determined by trading_session_date() using the
# instrument's exchange_tz and eth_start.  For ES/NQ futures:
#   eth_start = "18:00" (America/New_York)
#
# Session 1 (09:30 bars, 2026-01-05, trading_session_date 2026-01-05):
#   bars 0–3: establish OTF up
# Session 2 (09:30 bars, 2026-01-06, trading_session_date 2026-01-06):
#   bar 4 (first bar of new session): state = "unknown", up_run = 0
#   bar 5: up_run begins building from 0
# ---------------------------------------------------------------------------

OTF_SESSION_BOUNDARY: dict = {
    "scenario": "session_boundary",
    "description": (
        "OTF up from session 1 does not carry into session 2; resets to unknown. "
        "trading_session_date changes from 2026-01-05 to 2026-01-06 when a new "
        "RTH bar (09:30 ET) appears on the next calendar day."
    ),
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        # --- Session 1: trading_session_date 2026-01-05 (RTH bars) ---
        _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor s1
        _bar("2026-01-05 09:35", 100.5, 102.0, 99.5, 101.5),  # bar 1: up_run=1
        _bar("2026-01-05 09:40", 101.5, 103.0, 100.0, 102.5),  # bar 2: up_run=2
        _bar("2026-01-05 09:45", 102.5, 104.0, 100.5, 103.5),  # bar 3: up_run=3 → up
        # --- Session 2: trading_session_date 2026-01-06 (new day) ---
        _bar("2026-01-06 09:30", 103.5, 105.0, 101.0, 104.5),  # bar 4: first bar → unknown
        _bar("2026-01-06 09:35", 104.5, 106.0, 101.5, 105.5),  # bar 5: up_run=1
    ],
    "expected_states": [
        # Session 1
        {"bar_index": 0, "state": "unknown", "up_run": 0, "down_run": 0, "session": 1},
        {"bar_index": 1, "state": "neutral", "up_run": 1, "down_run": 0, "session": 1},
        {"bar_index": 2, "state": "neutral", "up_run": 2, "down_run": 0, "session": 1},
        {"bar_index": 3, "state": "up", "up_run": 3, "down_run": 0, "session": 1},
        # Session 2 — reset
        {"bar_index": 4, "state": "unknown", "up_run": 0, "down_run": 0, "session": 2},
        {"bar_index": 5, "state": "neutral", "up_run": 1, "down_run": 0, "session": 2},
    ],
}


# ---------------------------------------------------------------------------
# Scenario 11 — Look-Ahead Safety (1-minute source bars)
#
# Rule (§3.11): For a signal at timestamp T, only completed HTF bars with
# close_time <= T are available.  The in-progress HTF bar (close_time > T)
# must NOT be used.
#
# These are 1-minute source bars.  Two complete 5-minute bars exist:
#   5m bar A: 09:25–09:30 closes at 09:30 → available for signals at T >= 09:30
#   5m bar B: 09:30–09:35 closes at 09:35 → NOT available for signal at T = 09:33
#
# For a signal at 09:33 (during the 09:30–09:35 5m bar):
#   - 5m bar B is still in progress → final high/low UNKNOWN
#   - Only 5m bar A is available
#   - OTF state is computed using only bar A (and earlier bars)
#
# The fixture records signal timestamps, the last available completed 5m bar
# at each signal time, and the expected OTF reference bar index.
# ---------------------------------------------------------------------------

#: 1-minute source bars spanning two complete and one partial 5-minute periods.
OTF_LOOKAHEAD_SOURCE_BARS: list[dict] = [
    # 5m bar A: 09:20–09:25 (closes 09:25)
    _bar("2026-01-05 09:20", 99.5, 99.8, 99.2, 99.6),
    _bar("2026-01-05 09:21", 99.6, 99.9, 99.4, 99.8),
    _bar("2026-01-05 09:22", 99.8, 100.0, 99.5, 99.9),
    _bar("2026-01-05 09:23", 99.9, 100.1, 99.6, 100.0),
    _bar("2026-01-05 09:24", 100.0, 100.2, 99.7, 100.1),
    # 5m bar B: 09:25–09:30 (closes 09:30)
    _bar("2026-01-05 09:25", 100.1, 100.5, 100.0, 100.4),
    _bar("2026-01-05 09:26", 100.4, 100.7, 100.2, 100.6),
    _bar("2026-01-05 09:27", 100.6, 101.0, 100.4, 100.9),
    _bar("2026-01-05 09:28", 100.9, 101.2, 100.7, 101.1),
    _bar("2026-01-05 09:29", 101.1, 101.5, 100.8, 101.3),
    # 5m bar C: 09:30–09:35 (in progress; closes 09:35)
    _bar("2026-01-05 09:30", 101.3, 103.0, 101.0, 102.5),  # eventual high 103 unknown at 09:31
    _bar("2026-01-05 09:31", 102.5, 104.0, 102.0, 103.8),  # 09:31 < 09:35 — bar C not complete
    _bar("2026-01-05 09:32", 103.8, 105.0, 103.0, 104.5),  # future high of bar C
    _bar("2026-01-05 09:33", 104.5, 105.5, 104.0, 105.0),
    _bar("2026-01-05 09:34", 105.0, 106.0, 104.5, 105.8),
]

OTF_LOOKAHEAD_SAFETY: dict = {
    "scenario": "lookahead_safety",
    "description": (
        "1-minute source bars spanning two complete 5m bars and one in-progress 5m bar.  "
        "A signal at 09:33 must use only the completed 5m bar ending at 09:30, "
        "never the in-progress bar whose eventual high/low is not yet known."
    ),
    "source_interval": "1m",
    "target_timeframe": "5m",
    "bars": OTF_LOOKAHEAD_SOURCE_BARS,
    # Explicit HTF interval definitions (see docs/otf-filter.md §6.1).
    # bar_start_timestamp  = pandas resampled row label (left-labeled bucket start)
    # bar_close_timestamp  = bar_start_timestamp + 5 minutes
    # availability_timestamp = bar_close_timestamp  (bar available after close)
    # IMPORTANT: the resampled row label is NOT the availability timestamp.
    "htf_intervals": [
        {
            "bar_label": "5m_bar_A",
            "bar_start_timestamp": "2026-01-05 09:20",
            "bar_close_timestamp": "2026-01-05 09:25",
            "availability_timestamp": "2026-01-05 09:25",
            "resampled_row_label": "2026-01-05 09:20",
            "note": "Resampled row label (09:20) != availability (09:25)",
        },
        {
            "bar_label": "5m_bar_B",
            "bar_start_timestamp": "2026-01-05 09:25",
            "bar_close_timestamp": "2026-01-05 09:30",
            "availability_timestamp": "2026-01-05 09:30",
            "resampled_row_label": "2026-01-05 09:25",
            "note": "Resampled row label (09:25) != availability (09:30)",
        },
        {
            "bar_label": "5m_bar_C",
            "bar_start_timestamp": "2026-01-05 09:30",
            "bar_close_timestamp": "2026-01-05 09:35",
            "availability_timestamp": "2026-01-05 09:35",
            "resampled_row_label": "2026-01-05 09:30",
            "note": "In-progress bar: final high/low unknown until 09:35; resampled row label (09:30) != availability (09:35)",
        },
    ],
    # Key contract assertions for look-ahead safety:
    "lookahead_vectors": [
        {
            "signal_timestamp": "2026-01-05 09:31",  # during 5m bar C
            "last_completed_5m_bar_start": "2026-01-05 09:25",
            "last_completed_5m_close_time": "2026-01-05 09:30",
            "in_progress_5m_bar_start": "2026-01-05 09:30",
            "in_progress_5m_close_time": "2026-01-05 09:35",
            "must_not_use_bar_C_high": True,
            "must_not_use_bar_C_low": True,
        },
        {
            "signal_timestamp": "2026-01-05 09:33",
            "last_completed_5m_bar_start": "2026-01-05 09:25",
            "last_completed_5m_close_time": "2026-01-05 09:30",
            "in_progress_5m_bar_start": "2026-01-05 09:30",
            "in_progress_5m_close_time": "2026-01-05 09:35",
            "must_not_use_bar_C_high": True,
            "must_not_use_bar_C_low": True,
        },
        {
            "signal_timestamp": "2026-01-05 09:35",  # exactly at 5m close
            "last_completed_5m_bar_start": "2026-01-05 09:30",
            "last_completed_5m_close_time": "2026-01-05 09:35",
            "in_progress_5m_bar_start": "2026-01-05 09:35",
            "in_progress_5m_close_time": "2026-01-05 09:40",
            "must_not_use_bar_C_high": False,  # bar C is now complete at 09:35
            "must_not_use_bar_C_low": False,
        },
    ],
}


# ---------------------------------------------------------------------------
# Scenario 12 — Directional Eligibility
#
# Rule (§3.12): Long signal passes only when every selected timeframe is "up".
#               Short signal passes only when every selected timeframe is "down".
#               neutral or unknown states reject regardless of direction.
#
# These vectors encode the expected filter outcome for each (state, direction)
# combination, for a single-timeframe selection with "all" alignment mode.
# ---------------------------------------------------------------------------

OTF_DIRECTIONAL_ELIGIBILITY: dict = {
    "scenario": "directional_eligibility",
    "description": "Filter pass/fail for each (OTF state, signal direction) combination.",
    "alignment_mode": "all",
    "vectors": [
        {"otf_state": "up", "signal_direction": "long", "passes": True, "reason": None},
        {
            "otf_state": "up",
            "signal_direction": "short",
            "passes": False,
            "reason": "long signal required for OTF up; short direction rejected",
        },
        {"otf_state": "down", "signal_direction": "short", "passes": True, "reason": None},
        {
            "otf_state": "down",
            "signal_direction": "long",
            "passes": False,
            "reason": "short signal required for OTF down; long direction rejected",
        },
        {
            "otf_state": "neutral",
            "signal_direction": "long",
            "passes": False,
            "reason": "OTF state is neutral; no directional bias",
        },
        {
            "otf_state": "neutral",
            "signal_direction": "short",
            "passes": False,
            "reason": "OTF state is neutral; no directional bias",
        },
        {
            "otf_state": "unknown",
            "signal_direction": "long",
            "passes": False,
            "reason": "OTF state is unknown; insufficient history",
        },
        {
            "otf_state": "unknown",
            "signal_direction": "short",
            "passes": False,
            "reason": "OTF state is unknown; insufficient history",
        },
    ],
}


# ---------------------------------------------------------------------------
# Scenario 13 — All-Timeframe Alignment ("all" mode)
#
# Rule (§3.13): In "all" alignment mode every selected timeframe must agree
# with the signal direction.  A single disagreeing timeframe rejects the signal.
#
# These vectors test the combination logic independently of state calculation.
# ---------------------------------------------------------------------------

OTF_ALL_TIMEFRAME_ALIGNMENT: dict = {
    "scenario": "all_timeframe_alignment",
    "description": "Multi-timeframe 'all' alignment vectors for long and short signals.",
    "alignment_mode": "all",
    "vectors": [
        # Long signal — all three up → pass
        {
            "signal_direction": "long",
            "timeframe_states": {"5m": "up", "15m": "up", "30m": "up"},
            "passes": True,
            "reason": None,
        },
        # Long signal — one timeframe neutral → fail
        {
            "signal_direction": "long",
            "timeframe_states": {"5m": "up", "15m": "neutral", "30m": "up"},
            "passes": False,
            "reason": "15m OTF state is neutral; all timeframes must be up for long",
        },
        # Long signal — one timeframe down → fail
        {
            "signal_direction": "long",
            "timeframe_states": {"5m": "up", "15m": "up", "30m": "down"},
            "passes": False,
            "reason": "30m OTF state is down; all timeframes must be up for long",
        },
        # Long signal — one timeframe unknown → fail
        {
            "signal_direction": "long",
            "timeframe_states": {"5m": "up", "15m": "unknown", "30m": "up"},
            "passes": False,
            "reason": "15m OTF state is unknown; all timeframes must be up for long",
        },
        # Short signal — all three down → pass
        {
            "signal_direction": "short",
            "timeframe_states": {"5m": "down", "15m": "down", "30m": "down"},
            "passes": True,
            "reason": None,
        },
        # Short signal — one timeframe neutral → fail
        {
            "signal_direction": "short",
            "timeframe_states": {"5m": "down", "15m": "down", "30m": "neutral"},
            "passes": False,
            "reason": "30m OTF state is neutral; all timeframes must be down for short",
        },
        # Short signal — one timeframe up → fail
        {
            "signal_direction": "short",
            "timeframe_states": {"5m": "down", "15m": "up", "30m": "down"},
            "passes": False,
            "reason": "15m OTF state is up; all timeframes must be down for short",
        },
        # Single-timeframe selection — only 15m selected, 15m=up → long passes
        {
            "signal_direction": "long",
            "timeframe_states": {"15m": "up"},
            "passes": True,
            "reason": None,
        },
    ],
}


# ---------------------------------------------------------------------------
# Scenario 14 — Overnight Futures Session (midnight is NOT a session boundary)
#
# Rule (§3.10): Session boundaries are determined by trading_session_date()
# from thesistester/levels/session_date.py, applied in the instrument's
# exchange-local timezone using the configured eth_start.
#
# For ES/NQ futures (eth_start = "18:00", exchange_tz = "America/New_York"):
#   - A bar at or after 18:00 ET on day D belongs to the session for day D+1.
#   - A bar before 18:00 ET on day D belongs to the session for day D.
#   - MIDNIGHT (00:00 ET) IS NOT a session boundary.
#
# This fixture demonstrates that an OTF sequence continues across midnight
# without resetting, and that the TRUE session boundary at 18:00 ET is where
# the reset occurs.
#
# Bars and their trading_session_date (eth_start="18:00", tz="America/New_York"):
#   bar 0: 2026-01-05 22:00 ET  → base 2026-01-05, time>=18:00 → session 2026-01-06
#   bar 1: 2026-01-05 23:00 ET  → base 2026-01-05, time>=18:00 → session 2026-01-06
#   bar 2: 2026-01-06 00:00 ET  → base 2026-01-06, time<18:00  → session 2026-01-06 ← midnight crossed
#   bar 3: 2026-01-06 00:30 ET  → base 2026-01-06, time<18:00  → session 2026-01-06
#   bar 4: 2026-01-06 18:00 ET  → base 2026-01-06, time>=18:00 → session 2026-01-07 ← reset
#
# OTF state:
#   bar 0: anchor → unknown
#   bar 1: L(1)=99.5 > L(0)=99.0 → up_run=1, neutral
#   bar 2: L(2)=100.0 > L(1)=99.5 → up_run=2, neutral  (midnight crossed; same session)
#   bar 3: L(3)=100.5 > L(2)=100.0 → up_run=3, UP      (still session 2026-01-06)
#   bar 4: session 2026-01-07 → reset → unknown
# ---------------------------------------------------------------------------

OTF_OVERNIGHT_SESSION: dict = {
    "scenario": "overnight_session",
    "description": (
        "ES futures overnight session spanning midnight. "
        "eth_start='18:00' ET means bars at 22:00 and 23:00 Monday ET and "
        "at 00:00 and 00:30 Tuesday ET all belong to trading_session_date=2026-01-06 (Tuesday). "
        "Midnight (00:00 ET) is NOT a session boundary. "
        "The OTF up sequence continues across midnight without resetting. "
        "The true session boundary at 18:00 ET Tuesday resets state to unknown."
    ),
    "instrument": "ES",
    "eth_start": "18:00",
    "exchange_tz": "America/New_York",
    "minimum_consecutive_bars": DEFAULT_MINIMUM_CONSECUTIVE_BARS,
    "session_reset": True,
    "bars": [
        # --- trading_session_date 2026-01-06 (Tuesday) ---
        # Monday 2026-01-05 22:00 ET: time=22:00 >= 18:00 → session 2026-01-06
        _bar("2026-01-05 22:00", 100.0, 101.0, 99.0, 100.5),  # bar 0: anchor
        # Monday 2026-01-05 23:00 ET: time=23:00 >= 18:00 → session 2026-01-06
        _bar("2026-01-05 23:00", 100.5, 102.0, 99.5, 101.5),  # bar 1
        # Tuesday 2026-01-06 00:00 ET: MIDNIGHT; time=00:00 < 18:00 → session 2026-01-06 (unchanged)
        _bar("2026-01-06 00:00", 101.5, 103.0, 100.0, 102.5),  # bar 2 ← midnight, same session
        # Tuesday 2026-01-06 00:30 ET: time=00:30 < 18:00 → session 2026-01-06
        _bar("2026-01-06 00:30", 102.5, 104.0, 100.5, 103.5),  # bar 3 → up
        # --- trading_session_date 2026-01-07 (Wednesday) — session boundary ---
        # Tuesday 2026-01-06 18:00 ET: time=18:00 >= 18:00 → session 2026-01-07 ← reset
        _bar("2026-01-06 18:00", 103.5, 105.0, 101.0, 104.5),  # bar 4: first bar of new session
    ],
    "expected_states": [
        # Session 2026-01-06 (Tuesday)
        {
            "bar_index": 0,
            "state": "unknown",
            "up_run": 0,
            "down_run": 0,
            "trading_session_date": "2026-01-06",
        },
        {
            "bar_index": 1,
            "state": "neutral",
            "up_run": 1,
            "down_run": 0,
            "trading_session_date": "2026-01-06",
        },
        # bar 2: midnight has passed, but trading_session_date is still 2026-01-06 → no reset
        {
            "bar_index": 2,
            "state": "neutral",
            "up_run": 2,
            "down_run": 0,
            "trading_session_date": "2026-01-06",
        },
        {
            "bar_index": 3,
            "state": "up",
            "up_run": 3,
            "down_run": 0,
            "trading_session_date": "2026-01-06",
        },
        # Session 2026-01-07 (Wednesday) — reset at 18:00 ET Tuesday
        {
            "bar_index": 4,
            "state": "unknown",
            "up_run": 0,
            "down_run": 0,
            "trading_session_date": "2026-01-07",
        },
    ],
}


# ---------------------------------------------------------------------------
# Registry of all scenarios for iteration in tests
# ---------------------------------------------------------------------------

ALL_OHLCV_SCENARIOS: dict[str, dict] = {
    "up_established": OTF_UP_ESTABLISHED,
    "down_established": OTF_DOWN_ESTABLISHED,
    "neutral": OTF_NEUTRAL,
    "sequence_break_up": OTF_SEQUENCE_BREAK_UP,
    "sequence_break_down": OTF_SEQUENCE_BREAK_DOWN,
    "reversal_up_to_down": OTF_REVERSAL_UP_TO_DOWN,
    "equal_low": OTF_EQUAL_LOW,
    "equal_high": OTF_EQUAL_HIGH,
    "insufficient_history": OTF_INSUFFICIENT_HISTORY,
    "session_boundary": OTF_SESSION_BOUNDARY,
    "overnight_session": OTF_OVERNIGHT_SESSION,
}

ALL_VECTOR_SCENARIOS: dict[str, dict] = {
    "lookahead_safety": OTF_LOOKAHEAD_SAFETY,
    "directional_eligibility": OTF_DIRECTIONAL_ELIGIBILITY,
    "all_timeframe_alignment": OTF_ALL_TIMEFRAME_ALIGNMENT,
}
