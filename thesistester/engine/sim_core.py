"""Internal array-backed primitives for the serial trade-simulation hot path.

This module intentionally has no public execution API. It narrows the future
optimization boundary while preserving `simulate_trades` orchestration and
trade semantics in `backtest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from .intrabar import resolve_ohlc_bar, resolve_subtimeframe_bar


@dataclass(frozen=True)
class BarValues:
    """Numeric OHLC values for one parent bar."""

    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class BarData:
    """Immutable parent-bar arrays shared by every trade exit walk."""

    open: tuple[float, ...]
    high: tuple[float, ...]
    low: tuple[float, ...]
    close: tuple[float, ...]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "BarData":
        """Snapshot validated parent OHLC values without mutating the frame."""
        return cls(
            open=tuple(float(value) for value in frame["open"]),
            high=tuple(float(value) for value in frame["high"]),
            low=tuple(float(value) for value in frame["low"]),
            close=tuple(float(value) for value in frame["close"]),
        )

    def at(self, index: int) -> BarValues:
        """Return one parent bar's values at the existing integer bar index."""
        return BarValues(
            open=self.open[index],
            high=self.high[index],
            low=self.low[index],
            close=self.close[index],
        )


def resolve_trade_bar(
    bars: BarData,
    *,
    bar_index: int,
    intrabar_model: str,
    subtimeframe_context: Any,
    stop_price: float,
    target_price: float,
    direction: str,
    entry_activation_price: float | None,
):
    """Resolve one trade's bracket event against an immutable parent bar.

    The returned intrabar resolution is intentionally the existing engine
    object. Future acceleration can replace only this boundary after proving
    serial parity for every supported model.
    """
    bar = bars.at(bar_index)
    if intrabar_model in {"subtimeframe", "subtimeframe_conservative"}:
        sub_bars = subtimeframe_context.groups.get(bar_index)
        if sub_bars is not None:
            resolution = resolve_subtimeframe_bar(
                sub_bars,
                stop_price=stop_price,
                target_price=target_price,
                direction=direction,
                parent_low=bar.low,
                parent_high=bar.high,
                entry_price=entry_activation_price,
            )
        else:
            resolution = replace(
                resolve_ohlc_bar(
                    open_price=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    stop_price=stop_price,
                    target_price=target_price,
                    direction=direction,
                    model="sl_first",
                    entry_price=entry_activation_price,
                ),
                resolution="subtimeframe_conservative_fallback_sl_first",
                subtimeframe_fallback=True,
            )
    else:
        resolution = resolve_ohlc_bar(
            open_price=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
            model=intrabar_model,
            entry_price=entry_activation_price,
        )
    return bar, resolution
