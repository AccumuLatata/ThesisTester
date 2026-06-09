"""Futures roll methodology helpers."""
from __future__ import annotations

from typing import Any

import pandas as pd

ROLL_METHODS = {
    "single_contract",
    "external_continuous",
    "segmented_contracts",
}

CONTRACT_COLUMN_CANDIDATES = [
    "contract",
    "symbol",
    "ticker",
    "instrument",
    "expiry",
    "expiration",
]

ADJUSTMENT_METHODS = {
    "unknown",
    "back_adjusted",
    "ratio_adjusted",
    "panama",
    "none",
}

ROLL_RULES = {
    "unknown",
    "volume",
    "open_interest",
    "calendar",
    "first_notice",
    "last_trade",
}


def detect_contract_column(df: pd.DataFrame) -> str | None:
    """Return likely contract identifier column name, if found."""
    lower_map = {str(col).lower(): str(col) for col in df.columns}
    for candidate in CONTRACT_COLUMN_CANDIDATES:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def _sorted_for_roll_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Return internal analysis frame sorted by timestamp when available."""
    if "timestamp" not in df.columns:
        return df.copy(deep=True).reset_index(drop=True)
    out = df.copy(deep=True)
    out = out.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return out


def detect_contract_segments(df: pd.DataFrame, contract_column: str = "contract") -> pd.DataFrame:
    """Detect contiguous contract segments in timestamp order."""
    columns = [
        "segment_id",
        "contract",
        "start_timestamp",
        "end_timestamp",
        "start_row",
        "end_row",
        "row_count",
    ]
    if contract_column not in df.columns:
        return pd.DataFrame(columns=columns)

    ordered = _sorted_for_roll_analysis(df)
    contract_series = ordered[contract_column].astype("string")
    segment_start = contract_series.ne(contract_series.shift(1)).fillna(True)
    segment_ids = segment_start.cumsum()

    segments: list[dict[str, Any]] = []
    for segment_id, segment in ordered.groupby(segment_ids, sort=True):
        start_row = int(segment.index.min())
        end_row = int(segment.index.max())
        first = segment.iloc[0]
        last = segment.iloc[-1]
        segments.append(
            {
                "segment_id": int(segment_id),
                "contract": None if pd.isna(first[contract_column]) else str(first[contract_column]),
                "start_timestamp": first.get("timestamp"),
                "end_timestamp": last.get("timestamp"),
                "start_row": start_row,
                "end_row": end_row,
                "row_count": int(len(segment)),
            }
        )

    out = pd.DataFrame(segments, columns=columns)
    if out.empty:
        return out
    return out


def compute_roll_gaps(
    df: pd.DataFrame,
    contract_column: str = "contract",
    tick_size: float | None = None,
) -> list[dict[str, Any]]:
    """Compute roll boundary price gaps between consecutive contract segments."""
    required = {contract_column, "open", "close"}
    if not required.issubset(df.columns):
        return []

    ordered = _sorted_for_roll_analysis(df)
    contract_series = ordered[contract_column].astype("string")
    roll_boundary_positions = contract_series.ne(contract_series.shift(1)).fillna(True)
    boundary_indices = [int(i) for i in ordered.index[roll_boundary_positions].tolist() if int(i) > 0]

    tick = float(tick_size) if tick_size is not None else None
    use_ticks = tick is not None and tick > 0

    gaps: list[dict[str, Any]] = []
    for idx in boundary_indices:
        previous_row = ordered.iloc[idx - 1]
        next_row = ordered.iloc[idx]

        previous_close = pd.to_numeric(previous_row.get("close"), errors="coerce")
        next_open = pd.to_numeric(next_row.get("open"), errors="coerce")
        if pd.isna(previous_close) or pd.isna(next_open):
            continue

        price_gap = float(next_open - previous_close)
        gaps.append(
            {
                "previous_contract": None
                if pd.isna(previous_row.get(contract_column))
                else str(previous_row.get(contract_column)),
                "next_contract": None
                if pd.isna(next_row.get(contract_column))
                else str(next_row.get(contract_column)),
                "roll_timestamp": next_row.get("timestamp"),
                "previous_close": float(previous_close),
                "next_open": float(next_open),
                "price_gap": price_gap,
                "price_gap_ticks": (price_gap / tick) if use_ticks else None,
            }
        )
    return gaps


def _contracts_from_column(df: pd.DataFrame, contract_column: str) -> list[str]:
    if contract_column not in df.columns:
        return []
    values = df[contract_column].dropna().astype("string")
    if values.empty:
        return []
    return [str(v) for v in values.drop_duplicates().tolist()]


def _json_safe_timestamp(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def validate_roll_metadata(
    df: pd.DataFrame,
    roll_method: str,
    contract_column: str = "contract",
    adjustment_method: str = "unknown",
    roll_rule: str = "unknown",
    tick_size: float | None = None,
) -> dict[str, Any]:
    """Validate user-declared futures roll assumptions against dataset metadata."""
    warnings: list[str] = []
    valid = True
    adjustment_method_text = str("unknown" if adjustment_method is None else adjustment_method).strip()
    roll_rule_text = str("unknown" if roll_rule is None else roll_rule).strip()

    if roll_method not in ROLL_METHODS:
        warnings.append(f"Unsupported roll method '{roll_method}'.")
        valid = False

    detected_contract_column = contract_column if contract_column in df.columns else None
    contracts = _contracts_from_column(df, contract_column)
    contract_count = len(contracts) if detected_contract_column is not None else None

    if roll_method == "single_contract":
        if detected_contract_column is None:
            warnings.append("No contract column found; treating dataset as single-contract by assumption.")
        elif contract_count is not None and contract_count > 1:
            warnings.append(
                "Dataset contains multiple contracts but roll method is single_contract."
            )
            valid = False

    elif roll_method == "external_continuous":
        if adjustment_method_text == "unknown":
            warnings.append("External continuous adjustment_method is unknown.")
        if roll_rule_text == "unknown":
            warnings.append("External continuous roll_rule is unknown.")
        if adjustment_method_text not in ADJUSTMENT_METHODS:
            warnings.append(f"Unrecognized adjustment_method '{adjustment_method_text}'.")
        if roll_rule_text == "":
            warnings.append("Roll rule is empty.")
        if contract_count is not None and contract_count > 1:
            warnings.append(
                "Multiple explicit contracts found; provider continuity assumptions may mix symbols."
            )

    elif roll_method == "segmented_contracts":
        if detected_contract_column is None:
            warnings.append("Segmented contracts require a contract identifier column.")
            valid = False
        else:
            if contract_count is not None and contract_count < 2:
                warnings.append("Segmented contracts validation requires at least two distinct contracts.")
                valid = False
            if "timestamp" not in df.columns:
                warnings.append("Segmented contracts validation requires a timestamp column.")
                valid = False
            elif not df["timestamp"].is_monotonic_increasing:
                warnings.append("Input timestamps were not monotonic; roll analysis used sorted timestamps.")
        warnings.append(
            "R7 does not adjust OHLC prices across roll gaps; metrics may include roll discontinuities."
        )

    if roll_method == "segmented_contracts" and {contract_column, "open", "close", "timestamp"}.issubset(df.columns):
        roll_gaps = compute_roll_gaps(df, contract_column=contract_column, tick_size=tick_size)
    else:
        roll_gaps = []
        if roll_method == "segmented_contracts" and contract_column in df.columns:
            if not {"open", "close", "timestamp"}.issubset(df.columns):
                warnings.append("Missing open/close/timestamp columns; roll gaps not computed.")

    return {
        "roll_method": roll_method,
        "valid": bool(valid),
        "warnings": warnings,
        "contract_column": detected_contract_column,
        "contract_count": contract_count,
        "contracts": contracts,
        "adjustment_method": adjustment_method_text if roll_method == "external_continuous" else None,
        "roll_rule": roll_rule_text if roll_method == "external_continuous" else None,
        "roll_gap_count": len(roll_gaps),
        "roll_gaps": [
            {
                **gap,
                "roll_timestamp": _json_safe_timestamp(gap.get("roll_timestamp")),
            }
            for gap in roll_gaps
        ],
    }
