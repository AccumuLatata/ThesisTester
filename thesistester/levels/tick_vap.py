"""Tick Last×Volume prior-profile table (TV2).

Builds a tiny ``PriorProfileTable`` from TV1 session chunks. Allocation is
Last × Volume; the 70% expander is ``profile._compute_profile`` (not copied).
Period keys match ``compute_profile_levels`` (session date → ``W-SUN`` / ``M``).

This module does **not** change ``compute_profile_levels`` emission. Typical
``pdVA*`` / ``pw*`` / ``pm*`` stay on the 1m path until TV3.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import TickChunk
from thesistester.levels.profile import (
    _bucket_prices,
    _compute_profile,
    _validate_aggregation_ticks,
)

VA_SOURCE_TICK_LAST: Final[str] = "tick_last"
PRIOR_PROFILE_FAMILIES: Final[tuple[str, ...]] = ("pd", "pw", "pm")
PRIOR_PROFILE_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    "family",
    "period_key",
    "VAH",
    "VAL",
    "POC",
    "n_ticks",
    "sum_volume",
    "period_start",
    "period_end",
    "aggregation_ticks",
    "value_area_pct",
    "va_source",
)


@dataclass(frozen=True)
class PriorProfileTable:
    """Session / week / month tick-VAP scalars for a later 1m join."""

    frame: pd.DataFrame

    def __post_init__(self) -> None:
        missing = [column for column in PRIOR_PROFILE_TABLE_COLUMNS if column not in self.frame.columns]
        if missing:
            raise ValueError(f"PriorProfileTable missing columns: {missing}")

    def to_parquet(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.frame.to_parquet(path, index=False)

    @classmethod
    def from_parquet(cls, path: str | Path) -> PriorProfileTable:
        frame = pd.read_parquet(path)
        return cls(frame=_normalize_table_frame(frame))

    def family_rows(self, family: str) -> pd.DataFrame:
        if family not in PRIOR_PROFILE_FAMILIES:
            raise ValueError(f"Unknown prior-profile family: {family}")
        return self.frame.loc[self.frame["family"].eq(family)].copy()


def build_prior_profile_table(
    chunks: Iterable[TickChunk],
    *,
    instrument: str = "MNQ",
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = 1,
    prior_week_aggregation_ticks: int = 1,
    prior_month_aggregation_ticks: int = 1,
) -> PriorProfileTable:
    """Accumulate Last×Volume histograms per session, then expand pd/pw/pm VA."""
    if instrument not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {instrument}")
    if not 0 < value_area_pct <= 1:
        raise ValueError("value_area_pct must be in (0, 1].")
    day_agg = _validate_aggregation_ticks(
        "prior_day_aggregation_ticks", prior_day_aggregation_ticks
    )
    week_agg = _validate_aggregation_ticks(
        "prior_week_aggregation_ticks", prior_week_aggregation_ticks
    )
    month_agg = _validate_aggregation_ticks(
        "prior_month_aggregation_ticks", prior_month_aggregation_ticks
    )
    inst = INSTRUMENTS[instrument]
    sessions = [_session_histogram(chunk, tick_size=inst.tick_size) for chunk in chunks]
    sessions = [item for item in sessions if item is not None]
    rows: list[dict[str, object]] = []
    rows.extend(
        _family_rows(
            sessions,
            family="pd",
            period_attr="day_key",
            aggregation_ticks=day_agg,
            tick_size=inst.tick_size * day_agg,
            value_area_pct=value_area_pct,
        )
    )
    rows.extend(
        _family_rows(
            sessions,
            family="pw",
            period_attr="week_key",
            aggregation_ticks=week_agg,
            tick_size=inst.tick_size * week_agg,
            value_area_pct=value_area_pct,
        )
    )
    rows.extend(
        _family_rows(
            sessions,
            family="pm",
            period_attr="month_key",
            aggregation_ticks=month_agg,
            tick_size=inst.tick_size * month_agg,
            value_area_pct=value_area_pct,
        )
    )
    return PriorProfileTable(frame=_normalize_table_frame(pd.DataFrame(rows)))


def map_shifted_prior_profile(
    period_key: pd.Series,
    table: PriorProfileTable,
    *,
    family: str,
) -> pd.DataFrame:
    """Map each period key to the **prior** period's VAH/VAL/POC (``shift(1)``)."""
    if family not in PRIOR_PROFILE_FAMILIES:
        raise ValueError(f"Unknown prior-profile family: {family}")
    fam = table.family_rows(family)
    if fam.empty:
        empty = pd.DataFrame(
            {
                f"{family}VAH": pd.Series(pd.NA, index=period_key.index, dtype="float64"),
                f"{family}VAL": pd.Series(pd.NA, index=period_key.index, dtype="float64"),
                f"{family}POC": pd.Series(pd.NA, index=period_key.index, dtype="float64"),
            }
        )
        return empty
    ordered = fam.sort_values("period_key").set_index("period_key")[["VAH", "VAL", "POC"]]
    shifted = ordered.shift(1)
    lookup = period_key.map(_format_period_key)
    return pd.DataFrame(
        {
            f"{family}VAH": lookup.map(shifted["VAH"]),
            f"{family}VAL": lookup.map(shifted["VAL"]),
            f"{family}POC": lookup.map(shifted["POC"]),
        },
        index=period_key.index,
        dtype="float64",
    )


def _period_keys_from_session_date(session_date: date) -> tuple[str, str, str]:
    """Same construction as ``compute_profile_levels`` after ``trading_session_date``."""
    day_key = session_date
    day_key_ts = pd.to_datetime(day_key)
    week_key = day_key_ts.to_period("W-SUN")
    month_key = day_key_ts.to_period("M")
    return str(day_key), str(week_key), str(month_key)


def _format_period_key(value: object) -> str:
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(pd.Timestamp(value).date())


@dataclass(frozen=True)
class _SessionHistogram:
    session_date: date
    day_key: str
    week_key: str
    month_key: str
    histogram: pd.Series
    n_ticks: int
    sum_volume: float
    period_start: pd.Timestamp
    period_end: pd.Timestamp


def _session_histogram(chunk: TickChunk, *, tick_size: float) -> _SessionHistogram | None:
    ticks = chunk.ticks
    if ticks is None or ticks.empty:
        return None
    work = ticks.loc[:, ["timestamp", "price", "volume"]].copy()
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce")
    work = work.dropna(subset=["price", "volume"])
    work = work.loc[work["volume"] > 0]
    if work.empty:
        return None
    work["bin"] = _bucket_prices(work["price"], tick_size)
    histogram = work.groupby("bin", sort=True)["volume"].sum()
    day_key, week_key, month_key = _period_keys_from_session_date(chunk.session_date)
    start = pd.Timestamp(work["timestamp"].min())
    end = pd.Timestamp(work["timestamp"].max())
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    else:
        start = start.tz_convert("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    else:
        end = end.tz_convert("UTC")
    # Tick rows are discarded after this return; only the histogram is kept.
    return _SessionHistogram(
        session_date=chunk.session_date,
        day_key=day_key,
        week_key=week_key,
        month_key=month_key,
        histogram=histogram,
        n_ticks=int(len(work)),
        sum_volume=float(work["volume"].sum()),
        period_start=start,
        period_end=end,
    )


def _merge_histograms(items: Iterable[_SessionHistogram]) -> pd.Series:
    return pd.concat([item.histogram for item in items], axis=0).groupby(level=0).sum().sort_index()


def _family_rows(
    sessions: list[_SessionHistogram],
    *,
    family: str,
    period_attr: str,
    aggregation_ticks: int,
    tick_size: float,
    value_area_pct: float,
) -> list[dict[str, object]]:
    grouped: dict[str, list[_SessionHistogram]] = {}
    for session in sessions:
        grouped.setdefault(getattr(session, period_attr), []).append(session)
    rows: list[dict[str, object]] = []
    for period_key, members in grouped.items():
        histogram = _merge_histograms(members)
        vah, val, poc = _compute_profile(
            histogram.index.to_numpy(),
            histogram.to_numpy(),
            tick_size=tick_size,
            value_area_pct=value_area_pct,
        )
        rows.append(
            {
                "family": family,
                "period_key": period_key,
                "VAH": float(vah) if pd.notna(vah) else float("nan"),
                "VAL": float(val) if pd.notna(val) else float("nan"),
                "POC": float(poc) if pd.notna(poc) else float("nan"),
                "n_ticks": int(sum(item.n_ticks for item in members)),
                "sum_volume": float(sum(item.sum_volume for item in members)),
                "period_start": min(item.period_start for item in members),
                "period_end": max(item.period_end for item in members),
                "aggregation_ticks": int(aggregation_ticks),
                "value_area_pct": float(value_area_pct),
                "va_source": VA_SOURCE_TICK_LAST,
            }
        )
    return rows


def _normalize_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        empty = pd.DataFrame(columns=list(PRIOR_PROFILE_TABLE_COLUMNS))
        empty["VAH"] = empty["VAH"].astype("float64")
        empty["VAL"] = empty["VAL"].astype("float64")
        empty["POC"] = empty["POC"].astype("float64")
        empty["n_ticks"] = empty["n_ticks"].astype("int64")
        empty["sum_volume"] = empty["sum_volume"].astype("float64")
        empty["aggregation_ticks"] = empty["aggregation_ticks"].astype("int64")
        empty["value_area_pct"] = empty["value_area_pct"].astype("float64")
        empty["period_start"] = pd.Series(dtype="datetime64[ns, UTC]")
        empty["period_end"] = pd.Series(dtype="datetime64[ns, UTC]")
        return empty
    out = frame.loc[:, list(PRIOR_PROFILE_TABLE_COLUMNS)].copy()
    out["family"] = out["family"].astype("string")
    out["period_key"] = out["period_key"].astype("string")
    out["va_source"] = out["va_source"].astype("string")
    for column in ("VAH", "VAL", "POC", "sum_volume", "value_area_pct"):
        out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
    out["n_ticks"] = pd.to_numeric(out["n_ticks"], errors="coerce").astype("int64")
    out["aggregation_ticks"] = pd.to_numeric(out["aggregation_ticks"], errors="coerce").astype(
        "int64"
    )
    out["period_start"] = pd.to_datetime(out["period_start"], utc=True)
    out["period_end"] = pd.to_datetime(out["period_end"], utc=True)
    return out.reset_index(drop=True)
