"""Deterministic fixtures for B-3 default-on branch goldens (QI-11-02).

Recipes come from AH1 flatten, AH5 3c ``sl_first``, exit-management BE/trail,
and DA3 opposite-direction ``legacy``. AH1/AH5 unit probes stay the live probes.
"""

from __future__ import annotations

import pandas as pd

from thesistester.data.sessions import tag_session

INSTRUMENT = "NQ"
TIMEZONE = "America/New_York"


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TIMEZONE),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _touch_signal(
    bar_index: int,
    *,
    signal_id: int,
    timestamp: str,
    direction: str = "long",
    entry_ref: float = 100.0,
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp(timestamp, tz=TIMEZONE),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": entry_ref,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def generate_flatten_on_dataset() -> pd.DataFrame:
    """AH1-P1 clocks: Mon ETH then Tue RTH through session close."""
    frame = pd.DataFrame(
        [
            _bar("2026-01-05 18:29", 100.0, 100.25, 99.75, 100.0),
            _bar("2026-01-05 18:30", 100.0, 100.25, 99.75, 100.0),
            _bar("2026-01-06 01:59", 100.0, 100.25, 99.75, 100.0),
            _bar("2026-01-06 02:00", 100.0, 100.25, 99.75, 100.0),
            _bar("2026-01-06 15:59", 100.0, 100.25, 99.75, 100.0),
            _bar("2026-01-06 16:00", 100.0, 100.25, 99.75, 100.0),
        ]
    )
    return tag_session(frame, INSTRUMENT)


def generate_flatten_on_signals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _touch_signal(0, signal_id=1, timestamp="2026-01-05 18:29"),
            _touch_signal(2, signal_id=2, timestamp="2026-01-06 01:59"),
        ]
    )


def generate_three_c_sl_first_dataset() -> pd.DataFrame:
    """AH5-P1 parent: pre-retrace low must not SL a 3c fill at 100."""
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=2, freq="5min", tz=TIMEZONE),
            "open": [100.0, 97.0],
            "high": [101.0, 103.0],
            "low": [99.0, 97.0],
            "close": [100.0, 101.0],
            "volume": [1000, 1000],
        }
    )
    return tag_session(frame, INSTRUMENT)


def generate_three_c_sl_first_signals() -> pd.DataFrame:
    filled = {
        "signal_id": 1,
        "timestamp": pd.Timestamp("2026-01-05 09:35", tz=TIMEZONE),
        "bar_index": 1,
        "entry_bar_index": 1,
        "retrace_entry_price": 100.0,
        "trigger": "3c",
        "direction": "long",
        "status": "filled",
        "zone_low": 99.0,
        "zone_high": 101.0,
        "zone_mid": 100.0,
        "level_count": 1,
        "level_names": "A",
        "entry_reference_price": 100.0,
        "entry_model": "3c_retrace_market",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "filled",
    }
    void = {
        **filled,
        "signal_id": 2,
        "timestamp": pd.Timestamp("2026-01-05 09:30", tz=TIMEZONE),
        "bar_index": 0,
        "entry_bar_index": 0,
        "status": "void",
        "notes": "void",
    }
    return pd.DataFrame([filled, void])


def generate_be_dataset() -> pd.DataFrame:
    rows = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.5, 99.5, 100.5),
        (100.5, 101.5, 100.0, 100.5),
    ]
    return _ohlc_session("2026-01-05 09:30", rows)


def generate_trail_dataset() -> pd.DataFrame:
    rows = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 103.0, 99.5, 102.0),
        (102.0, 102.5, 101.0, 101.5),
    ]
    return _ohlc_session("2026-01-05 10:30", rows)


def generate_be_trail_signal() -> pd.DataFrame:
    return pd.DataFrame([_touch_signal(0, signal_id=1, timestamp="2026-01-05 09:30")])


def generate_trail_signal() -> pd.DataFrame:
    return pd.DataFrame([_touch_signal(0, signal_id=1, timestamp="2026-01-05 10:30")])


def generate_opposite_direction_legacy_dataset() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:31", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:32", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:35", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:36", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:37", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:40", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:41", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:42", 100.0, 101.0, 99.0, 100.0),
        ]
    )
    return tag_session(frame, INSTRUMENT)


def generate_opposite_direction_legacy_signals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _touch_signal(0, signal_id=0, timestamp="2026-01-02 09:30", direction="long"),
            _touch_signal(0, signal_id=1, timestamp="2026-01-02 09:30", direction="short"),
            _touch_signal(3, signal_id=2, timestamp="2026-01-02 09:35", direction="long"),
            _touch_signal(3, signal_id=3, timestamp="2026-01-02 09:35", direction="short"),
            _touch_signal(6, signal_id=4, timestamp="2026-01-02 09:40", direction="long"),
            _touch_signal(6, signal_id=5, timestamp="2026-01-02 09:40", direction="short"),
        ]
    )


def _ohlc_session(start: str, rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=len(rows), freq="1min", tz=TIMEZONE),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [100] * len(rows),
        }
    )
    return tag_session(frame, INSTRUMENT)
