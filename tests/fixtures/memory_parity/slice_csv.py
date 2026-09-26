"""Slice a Quantower History Exporter 15s CSV on UTC bounds (row bytes kept)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SHORT_WINDOW_START_UTC = pd.Timestamp("2024-08-01 00:00:00+00:00")
SHORT_WINDOW_END_UTC = pd.Timestamp("2024-10-01 00:00:00+00:00")
CELL6_WINDOW_START_UTC = SHORT_WINDOW_START_UTC
CELL6_WINDOW_END_UTC = pd.Timestamp("2024-08-04 00:00:00+00:00")

SHORT_SLICE_NAME = "mnq_15s_utc_20240801_20241001.csv"
CELL6_SLICE_NAME = "mnq_15s_utc_20240801_20240804.csv"


def parse_quantower_time_left_utc(value: str) -> pd.Timestamp:
    """Parse a History Exporter ``Time left`` cell as UTC (smoke YAML TZ)."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty Time left value")
    parsed = pd.to_datetime(text, errors="raise", format="mixed")
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")
    return pd.Timestamp(parsed)


def slice_quantower_csv_utc(
    source: Path,
    dest: Path,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> dict[str, int]:
    """Keep original header + rows whose Time left is in ``[start, end)``.

    Rows are copied verbatim so the saved slice is a stable dataset. The
    timestamp column is the first semicolon field (``Time left``).
    """
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("slice bounds must be timezone-aware UTC")
    source = Path(source)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    skipped = 0
    with source.open("r", encoding="utf-8", newline="") as handle:
        header = handle.readline()
        if not header:
            raise ValueError(f"empty Quantower CSV: {source}")
        with dest.open("w", encoding="utf-8", newline="") as out:
            out.write(header if header.endswith("\n") else header + "\n")
            for line in handle:
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue
                time_left = raw.split(";", 1)[0]
                stamp = parse_quantower_time_left_utc(time_left)
                if start_utc <= stamp < end_utc:
                    out.write(raw + "\n")
                    kept += 1
                else:
                    skipped += 1
    if kept == 0:
        raise ValueError(
            f"UTC slice [{start_utc}, {end_utc}) of {source} kept 0 rows; "
            "stop and report — do not record MW0 from an empty slice"
        )
    return {"kept": kept, "skipped": skipped, "bytes": dest.stat().st_size}
