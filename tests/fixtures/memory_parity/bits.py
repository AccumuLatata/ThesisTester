"""Float64 bit identity for MW equality (NaN equals NaN; no tolerance)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pandas as pd

SUMMARY_METRIC_KEYS: tuple[str, ...] = (
    "trade_count",
    "expectancy_r",
    "total_r",
    "max_drawdown_r",
    "profit_factor",
    "win_rate",
)

DA5_KEYS: tuple[str, ...] = (
    "random_null_expectancy_r",
    "random_null_std_r",
    "random_p_value_ge",
    "expectancy_minus_null_r",
)

LEDGER_EQUALITY_KEYS: tuple[str, ...] = ("status", "error", "bundle_path")
LEDGER_STORED_EXCLUDED_KEYS: tuple[str, ...] = ("started_at", "finished_at")

PRESTEP_GATES: tuple[str, ...] = (
    "trades",
    "replica_expectancies",
    "trade_count",
    "expectancy_r",
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value is pd.NA:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if isinstance(value, (str, bytes, bool)):
            return False
        return bool(pd.isna(value)) and not isinstance(value, (float, np.floating))
    except (TypeError, ValueError):
        return False


def float64_hex(value: Any) -> str | None:
    """Return the IEEE-754 float64 bit pattern as 16 lowercase hex digits."""
    if _is_missing(value):
        return None
    bits = np.float64(value).view(np.uint64)
    return f"{int(bits):016x}"


def hex_to_float64(hex_bits: str) -> float:
    bits = np.uint64(int(hex_bits, 16))
    return float(bits.view(np.float64))


def replica_hex_list(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        hex_bits = float64_hex(value)
        if hex_bits is None:
            raise ValueError("replica_expectancies must be finite-or-NaN float64 values")
        out.append(hex_bits)
    return out


def replica_from_hex(hex_bits: Sequence[str]) -> list[float]:
    return [hex_to_float64(item) for item in hex_bits]


def encode_optional_float(value: Any) -> dict[str, Any]:
    if _is_missing(value):
        return {"hex": None, "is_null": True}
    return {"hex": float64_hex(value), "is_null": False}


def decode_optional_float(payload: Any) -> float | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        if payload.get("is_null"):
            return None
        hex_bits = payload.get("hex")
        if hex_bits is None:
            return None
        return hex_to_float64(str(hex_bits))
    return float(payload)


def hex_equal(left: str | None, right: str | None) -> bool:
    return left == right
