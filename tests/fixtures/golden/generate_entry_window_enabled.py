"""Deterministic RTH fixture for the enabled entry_window golden gate (SW2)."""

from __future__ import annotations

import pandas as pd

from thesistester.data.sessions import tag_session

INSTRUMENT = "NQ"
TIMEZONE = "America/New_York"
ENTRY_WINDOW = {
    "enabled": True,
    "mode": "rth_segments",
    "rth_segments": ["rth_open_30m"],
    "timezone": TIMEZONE,
}

_SESSION_START = "2026-06-02 09:25:00"
_SESSION_MINUTES = 60  # through 10:24


def generate_entry_window_enabled_dataset() -> pd.DataFrame:
    """1-minute NQ bars spanning pre-open, open 30m, and morning."""
    timestamps = pd.date_range(
        _SESSION_START,
        periods=_SESSION_MINUTES,
        freq="1min",
        tz=TIMEZONE,
    )
    rows: list[dict[str, object]] = []
    price = 21000.0
    for index, ts in enumerate(timestamps):
        open_ = price
        high = price + 1.5
        low = price - 1.5
        close = price + 0.25
        rows.append(
            {
                "timestamp": ts,
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(1000 + index),
            }
        )
        price += 0.25
    return tag_session(pd.DataFrame(rows), INSTRUMENT)


def generate_entry_window_enabled_signals(
    data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Fixed candidates: in-window, boundary, and out-of-window next-bar cases."""
    source = generate_entry_window_enabled_dataset() if data is None else data
    # Decision timestamps (signal bars). Entry is next-bar open.
    specs = (
        (1, "2026-06-02 09:29:00", "long", "entry_0930_open_accept"),
        (2, "2026-06-02 09:45:00", "short", "entry_0946_open_accept"),
        (3, "2026-06-02 09:59:00", "long", "entry_1000_morning_reject"),
        (4, "2026-06-02 10:10:00", "short", "entry_1011_morning_reject"),
    )
    rows: list[dict[str, object]] = []
    for signal_id, ts_text, direction, note in specs:
        ts = pd.Timestamp(ts_text, tz=TIMEZONE)
        matches = source.index[source["timestamp"] == ts]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one bar at {ts_text}, found {len(matches)}")
        bar_index = int(matches[0])
        rows.append(
            {
                "signal_id": signal_id,
                "timestamp": ts,
                "bar_index": bar_index,
                "trigger": "touch",
                "direction": direction,
                "zone_low": 20990.0,
                "zone_high": 21010.0,
                "zone_mid": 21000.0,
                "level_count": 1,
                "level_names": "A",
                "entry_reference_price": 21000.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": note,
            }
        )
    return pd.DataFrame(rows)
