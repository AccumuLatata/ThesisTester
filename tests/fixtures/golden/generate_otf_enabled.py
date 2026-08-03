"""Deterministic overnight ES/NQ-style fixture for the enabled-OTF golden gate.

Produces 1-minute OHLCV spanning an ETH overnight session that crosses midnight
and the next 18:00 ET boundary, plus fixed long/short candidate signals that
exercise accepted and rejected OTF outcomes.
"""

from __future__ import annotations

import pandas as pd

from thesistester.data.sessions import tag_session

INSTRUMENT = "NQ"
TIMEZONE = "America/New_York"
ETH_START = "18:00"
OTF_TIMEFRAMES = ["5m"]
MINIMUM_CONSECUTIVE_BARS = 3

# Overnight: Mon 22:00 → Tue 01:00, then Tue 18:00 → 18:40 for the next session.
_OVERNIGHT_START = "2026-01-05 22:00:00"
_OVERNIGHT_MINUTES = 180  # through 01:00 Tue
_BOUNDARY_START = "2026-01-06 18:00:00"
_BOUNDARY_MINUTES = 40


def generate_otf_enabled_dataset() -> pd.DataFrame:
    """Build 1-minute OHLCV with up, down, and post-boundary cold-start periods."""
    overnight = pd.date_range(
        _OVERNIGHT_START,
        periods=_OVERNIGHT_MINUTES,
        freq="1min",
        tz=TIMEZONE,
    )
    boundary = pd.date_range(
        _BOUNDARY_START,
        periods=_BOUNDARY_MINUTES,
        freq="1min",
        tz=TIMEZONE,
    )
    timestamps = overnight.union(boundary)

    rows: list[dict[str, object]] = []
    # Segment A (0–89): steadily higher lows → OTF up on 5m once established.
    # Segment B (90–179): steadily lower highs → OTF down.
    # Segment C (boundary): fresh session → unknown / early neutral.
    price = 21000.0
    for index, ts in enumerate(timestamps):
        if index < _OVERNIGHT_MINUTES // 2:
            low = price
            high = price + 1.25
            open_ = price + 0.25
            close = price + 0.75
            price += 0.05
        elif index < _OVERNIGHT_MINUTES:
            high = price
            low = price - 1.25
            open_ = price - 0.25
            close = price - 0.75
            price -= 0.05
        else:
            # New session after 18:00 — small inside bars; insufficient for up/down.
            open_ = price
            high = price + 0.25
            low = price - 0.25
            close = price + 0.05
            price += 0.01
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
    return tag_session(pd.DataFrame(rows), INSTRUMENT)


def generate_otf_enabled_signals() -> pd.DataFrame:
    """Fixed candidates covering accept/reject paths for long and short."""
    # Decision times chosen after enough completed 5m history in each regime.
    specs = (
        # Established OTF up (long accepts, short rejects).
        (1, "2026-01-05 22:45:00", "long", "up_accept"),
        (2, "2026-01-05 22:45:00", "short", "up_reject_opposing"),
        # Established OTF down (short accepts, long rejects).
        (3, "2026-01-05 23:45:00", "short", "down_accept"),
        (4, "2026-01-05 23:45:00", "long", "down_reject_opposing"),
        # Post-midnight continuation still in ETH Tuesday session (up may still hold
        # or transition — fixture uses early down segment after 23:30; 00:20 is down).
        (5, "2026-01-06 00:20:00", "short", "down_after_midnight_accept"),
        # Fresh session after 18:00 ET → insufficient directional history reject.
        (6, "2026-01-06 18:10:00", "long", "post_boundary_reject"),
    )
    rows: list[dict[str, object]] = []
    for signal_id, ts, direction, note in specs:
        timestamp = pd.Timestamp(ts, tz=TIMEZONE)
        rows.append(
            {
                "signal_id": signal_id,
                "timestamp": timestamp,
                "bar_index": signal_id - 1,
                "trigger": "touch",
                "direction": direction,
                "zone_low": 20999.75,
                "zone_high": 21000.25,
                "zone_mid": 21000.0,
                "level_count": 2,
                "level_names": "dOpen|RTH_Open",
                "entry_reference_price": 21000.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": note,
            }
        )
    return pd.DataFrame(rows)


def otf_enabled_setup_config() -> dict:
    """Canonical enabled OTF setup used by the golden pipeline."""
    return {
        "name": "otf_enabled_golden",
        "instrument": INSTRUMENT,
        "otf_filter": {
            "enabled": True,
            "timeframes": list(OTF_TIMEFRAMES),
            "alignment_mode": "all",
            "minimum_consecutive_bars": MINIMUM_CONSECUTIVE_BARS,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        },
    }
