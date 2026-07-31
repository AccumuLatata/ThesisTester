"""Deterministic synthetic NQ fixture used by the legacy golden gate."""

from __future__ import annotations

import pandas as pd

from thesistester.data.sessions import tag_session

INSTRUMENT = "NQ"
TIMEZONE = "America/New_York"
SESSION_DATES = ("2026-01-05", "2026-01-06", "2026-01-07")
BARS_PER_SESSION = 6


def generate_dataset() -> pd.DataFrame:
    """Build three small RTH sessions with deliberate both-hit bars."""
    rows: list[dict[str, object]] = []
    templates = (
        (0.0, 0.50, -0.50, 0.25),
        (0.0, 5.00, -3.00, 1.00),
        (1.0, 1.50, 0.50, 1.25),
        (1.0, 4.00, -5.00, 0.00),
        (0.0, 0.50, -0.50, 0.25),
        (0.0, 5.00, -1.00, 4.00),
    )
    for session_index, session_date in enumerate(SESSION_DATES):
        base = 21000.0 + session_index * 10.0
        timestamps = pd.date_range(
            f"{session_date} 09:30",
            periods=BARS_PER_SESSION,
            freq="1min",
            tz=TIMEZONE,
        )
        for bar_index, (open_delta, high_delta, low_delta, close_delta) in enumerate(templates):
            rows.append(
                {
                    "timestamp": timestamps[bar_index],
                    "open": base + open_delta,
                    "high": base + high_delta,
                    "low": base + low_delta,
                    "close": base + close_delta,
                    "volume": 1000 + session_index * 100 + bar_index,
                }
            )
    return tag_session(pd.DataFrame(rows), INSTRUMENT)


def generate_signals() -> pd.DataFrame:
    """Return fixed simple-trigger signals aligned to the generated dataset."""
    rows: list[dict[str, object]] = []
    signal_id = 1
    for session_index in range(len(SESSION_DATES)):
        offset = session_index * BARS_PER_SESSION
        for bar_offset, direction in ((0, "long"), (2, "short"), (4, "long")):
            rows.append(
                {
                    "signal_id": signal_id,
                    "bar_index": offset + bar_offset,
                    "trigger": "touch",
                    "direction": direction,
                    "zone_low": 20999.75 + session_index * 10.0,
                    "zone_high": 21000.25 + session_index * 10.0,
                    "zone_mid": 21000.0 + session_index * 10.0,
                    "level_count": 2,
                    "level_names": "dOpen|RTH_Open",
                    "status": "candidate",
                }
            )
            signal_id += 1
    return pd.DataFrame(rows)
