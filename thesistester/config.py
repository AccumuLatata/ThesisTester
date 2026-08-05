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
    eth_start: str = ""
    # Asia session window in exchange_tz wall-clock time (half-open [start, end)).
    # Default ICT-style Asia: 20:00 → 00:00. Not rolling; levels emit only after close.
    asia_start: str = "20:00"
    asia_end: str = "00:00"


# Confirmed primary instruments (futures).
INSTRUMENTS: dict[str, Instrument] = {
    "ES": Instrument("ES", "E-mini S&P 500", tick_size=0.25, point_value=50.0, eth_start="18:00"),
    "NQ": Instrument(
        "NQ", "E-mini Nasdaq-100", tick_size=0.25, point_value=20.0, eth_start="18:00"
    ),
    "MES": Instrument(
        "MES", "Micro E-mini S&P 500", tick_size=0.25, point_value=5.0, eth_start="18:00"
    ),
    "MNQ": Instrument(
        "MNQ",
        "Micro E-mini Nasdaq-100",
        tick_size=0.25,
        point_value=2.0,
        eth_start="18:00",
    ),
}

TIMEZONE_OPTIONS: list[str] = [
    "America/New_York",
    "UTC",
    "Europe/Berlin",
    "Europe/London",
    "America/Chicago",
]

# Canonical OHLCV contract (lower-cased on load).
REQUIRED_COLUMNS: list[str] = ["timestamp", "open", "high", "low", "close", "volume"]
