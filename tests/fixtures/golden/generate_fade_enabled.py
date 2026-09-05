"""Deterministic one-zone fixture for the enabled fade golden (DA4)."""

from __future__ import annotations

import pandas as pd

from thesistester.data.sessions import tag_session
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.engine.signals import generate_signals

INSTRUMENT = "NQ"
TIMEZONE = "America/New_York"
TICK_SIZE = 0.25
LEVEL_A = 21000.00
LEVEL_B = 21000.50
_SESSION_START = "2026-06-02 09:30:00"
_SESSION_MINUTES = 16


def generate_fade_enabled_dataset() -> pd.DataFrame:
    """1-minute NQ bars with a fixed two-level zone and known fade geometries."""
    timestamps = pd.date_range(
        _SESSION_START,
        periods=_SESSION_MINUTES,
        freq="1min",
        tz=TIMEZONE,
    )
    # Default: sit above the zone. Overlay named approach/touch bars.
    closes = [21002.00] * _SESSION_MINUTES
    highs = [21002.50] * _SESSION_MINUTES
    lows = [21001.50] * _SESSION_MINUTES
    opens = [21002.00] * _SESSION_MINUTES

    # Bar 0: above (first bar — no fade even if later bars touch).
    # Bar 1: approach from above + touch → fade long.
    opens[1] = 21001.75
    highs[1] = 21002.00
    lows[1] = 21000.10
    closes[1] = 21000.80
    # Bar 2: entry bar for the long — stay entirely above the zone.
    opens[2] = 21001.80
    highs[2] = 21002.20
    lows[2] = 21001.40
    closes[2] = 21001.90
    # Bar 4: sit entirely below the zone so only the next bar can fade-short.
    opens[4] = 20998.50
    highs[4] = 20999.70
    lows[4] = 20997.50
    closes[4] = 20998.00
    # Bar 5: approach from below + touch → fade short.
    opens[5] = 20998.20
    highs[5] = 21000.40
    lows[5] = 20997.80
    closes[5] = 21000.20
    # Bar 6: entry bar for the short — stay entirely below the zone.
    opens[6] = 20998.20
    highs[6] = 20999.00
    lows[6] = 20997.80
    closes[6] = 20998.40
    # Remaining bars stay at the default above-zone quiet path so the
    # recorded family is exactly one fade-long and one fade-short.

    rows: list[dict[str, object]] = []
    for index, ts in enumerate(timestamps):
        rows.append(
            {
                "timestamp": ts,
                "open": float(opens[index]),
                "high": float(highs[index]),
                "low": float(lows[index]),
                "close": float(closes[index]),
                "volume": float(1000 + index),
                "LVL_A": LEVEL_A,
                "LVL_B": LEVEL_B,
            }
        )
    return tag_session(pd.DataFrame(rows), INSTRUMENT)


def generate_fade_enabled_zones(data: pd.DataFrame | None = None) -> pd.DataFrame:
    source = generate_fade_enabled_dataset() if data is None else data
    return detect_confluence_zones(
        source,
        level_columns=["LVL_A", "LVL_B"],
        tick_size=TICK_SIZE,
        tolerance_ticks=2,
        min_confluences=2,
        max_confluences=2,
    )


def generate_fade_enabled_signals(data: pd.DataFrame | None = None) -> pd.DataFrame:
    source = generate_fade_enabled_dataset() if data is None else data
    zones = generate_fade_enabled_zones(source)
    return generate_signals(
        source,
        zones,
        trigger="fade",
        direction="both",
        tick_size=TICK_SIZE,
    )
