"""Typed configuration: instrument presets and data contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    tick_size: float
    point_value: float
    exchange_tz: str = "America/New_York"
    rth_start: str = "09:30"
    rth_end: str = "16:00"


# Confirmed primary instruments (futures).
INSTRUMENTS: dict[str, Instrument] = {
    "ES": Instrument("ES", "E-mini S&P 500", tick_size=0.25, point_value=50.0),
    "NQ": Instrument("NQ", "E-mini Nasdaq-100", tick_size=0.25, point_value=20.0),
}

# Canonical OHLCV contract (lower-cased on load).
REQUIRED_COLUMNS: list[str] = ["timestamp", "open", "high", "low", "close", "volume"]
