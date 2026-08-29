"""Tick Last×Volume prior-profile table (TV2).

Builds a tiny ``PriorProfileTable`` from TV1 session chunks. Allocation is
Last × Volume; the 70% expander is ``profile._compute_profile`` (not copied).
Period keys match ``compute_profile_levels`` (session date → ``W-SUN`` / ``M``).
Parquet persists ``str(key)``; load reconstructs ``datetime.date`` / ``Period[W-SUN]``
/ ``Period[M]`` so ``period_key.map(...)`` joins those dtypes.

TV3 joins this table onto the 1m frame via ``map_shifted_prior_profile``.
Typical 1m allocation is no longer used for ``pd*`` / ``pw*`` / ``pm*`` VA.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import (
    TICK_FORMAT_PROFILE,
    TickChunk,
    iter_tick_files,
)
from thesistester.levels.profile import (
    _bucket_prices,
    _compute_profile,
    _validate_aggregation_ticks,
)

VA_SOURCE_TICK_LAST: Final[str] = "tick_last"
TICK_SOURCE_NONE: Final[str] = "none"
# Session cut is instrument eth_start in exchange_tz (TV1). Identity must
# change if that policy ever changes.
SESSION_CUT_POLICY_ID: Final[str] = "cme_eth_start_v1"
# Identity-only keys injected into the settings dict hashed by
# compute_levels_settings_hash. Never passed to compute_all_levels.
LEVELS_TICK_IDENTITY_KEYS: Final[tuple[str, ...]] = ("tick_source_id", "va_source")
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
        missing = [
            column for column in PRIOR_PROFILE_TABLE_COLUMNS if column not in self.frame.columns
        ]
        if missing:
            raise ValueError(f"PriorProfileTable missing columns: {missing}")

    def to_parquet(self, path: str | Path) -> None:
        """Persist ``str(key)`` of the native period-key objects (parquet cannot store Period)."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        persist = self.frame.copy()
        persist["period_key"] = persist["period_key"].map(_period_key_text)
        persist.to_parquet(path, index=False)

    @classmethod
    def from_parquet(cls, path: str | Path) -> PriorProfileTable:
        frame = pd.read_parquet(path)
        return cls(frame=_normalize_table_frame(frame))

    def family_rows(self, family: str) -> pd.DataFrame:
        if family not in PRIOR_PROFILE_FAMILIES:
            raise ValueError(f"Unknown prior-profile family: {family}")
        out = self.frame.loc[self.frame["family"].astype(str).eq(family)].copy()
        if not out.empty:
            out["period_key"] = _period_keys_for_join(out["period_key"], family).to_numpy()
        return out


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


def compute_tick_source_id(
    paths: Sequence[str | Path] | None,
    *,
    format_profile: str = "quantower_tick_last",
) -> str:
    """SHA-256 of sorted tick-file content hashes + profile + session-cut policy.

    Missing/empty paths return the explicit ``none`` token so the settings
    hash still contains ``tick_source_id``.
    """
    if not paths:
        return TICK_SOURCE_NONE
    resolved = [Path(path) for path in paths]
    if not resolved:
        return TICK_SOURCE_NONE
    # Lazy: execution_artifacts → local_store → engine.otf → levels.
    from thesistester.persistence.execution_artifacts import source_content_hash

    hasher = sha256()
    for digest in sorted(source_content_hash(path) for path in resolved):
        hasher.update(digest.encode("utf-8"))
        hasher.update(b"\0")
    hasher.update(str(format_profile).encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(SESSION_CUT_POLICY_ID.encode("utf-8"))
    return hasher.hexdigest()


def resolve_tick_format_profile(value: object | None) -> str:
    """Default ``quantower_tick_last``; any other profile is fail-closed."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return TICK_FORMAT_PROFILE
    profile = str(value)
    if profile != TICK_FORMAT_PROFILE:
        raise ValueError(
            f"Unsupported tick_format_profile: {profile!r}; expected {TICK_FORMAT_PROFILE!r}"
        )
    return profile


def dataset_has_tick_inputs(dataset: dict[str, Any] | None) -> bool:
    """True when tick files or a persisted prior-profile table are present."""
    if not dataset:
        return False
    paths = dataset.get("tick_paths")
    if isinstance(paths, list) and any(str(item).strip() for item in paths):
        return True
    table_path = dataset.get("prior_profile_table_path")
    return isinstance(table_path, (str, Path)) and bool(str(table_path).strip())


def build_prior_profile_table_from_paths(
    paths: Sequence[str | Path],
    *,
    instrument: str,
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = 1,
    prior_week_aggregation_ticks: int = 1,
    prior_month_aggregation_ticks: int = 1,
    format_profile: str = TICK_FORMAT_PROFILE,
) -> PriorProfileTable:
    """Load tick-last files and build the prior-profile table (parent / API path)."""
    resolve_tick_format_profile(format_profile)
    chunks = iter_tick_files(paths, instrument=instrument)
    return build_prior_profile_table(
        chunks,
        instrument=instrument,
        value_area_pct=value_area_pct,
        prior_day_aggregation_ticks=prior_day_aggregation_ticks,
        prior_week_aggregation_ticks=prior_week_aggregation_ticks,
        prior_month_aggregation_ticks=prior_month_aggregation_ticks,
    )


def attach_tick_identity(
    settings: dict[str, Any],
    *,
    tick_source_id: str | None = None,
) -> dict[str, Any]:
    """Put tick identity keys inside the settings dict used for the levels hash."""
    attached = dict(settings)
    attached["tick_source_id"] = tick_source_id if tick_source_id else TICK_SOURCE_NONE
    attached["va_source"] = VA_SOURCE_TICK_LAST
    return attached


def compute_table_source_id(table: PriorProfileTable) -> str:
    """Content identity for a table when tick files are not on the call.

    Must not return ``none`` — a present table and a missing table are
    different research objects (cache-collision if they share ``none``).
    """
    hasher = sha256()
    hasher.update(b"prior_profile_table\0")
    if table.frame.empty:
        hasher.update(b"empty")
        return hasher.hexdigest()
    persist = table.frame.loc[
        :,
        [
            "family",
            "period_key",
            "VAH",
            "VAL",
            "POC",
            "aggregation_ticks",
            "value_area_pct",
            "va_source",
        ],
    ].copy()
    persist["period_key"] = persist["period_key"].map(_period_key_text)
    persist = persist.sort_values(["family", "period_key"]).reset_index(drop=True)
    hasher.update(persist.to_csv(index=False).encode("utf-8"))
    return hasher.hexdigest()


def compute_table_path_source_id(path: str | Path) -> str:
    """SHA-256 of a persisted prior-profile parquet (fallback tick identity)."""
    from thesistester.persistence.execution_artifacts import source_content_hash

    return source_content_hash(path)


def map_shifted_prior_profile(
    period_key: pd.Series,
    table: PriorProfileTable,
    *,
    family: str,
) -> pd.DataFrame:
    """Map each 1m period key to the **prior 1m period's** table scalars.

    Join semantics match pre-TV3 ``_map_prior_profile_levels``: unique period
    keys come from the 1m frame (sorted), then ``shift(1)``. Scalars are
    looked up on the tick table; a prior period with no ticks is ``NaN``.
    Shifting the table's present rows would fill a gap from an earlier
    session — forbidden by TV §3.8.
    """
    if family not in PRIOR_PROFILE_FAMILIES:
        raise ValueError(f"Unknown prior-profile family: {family}")
    keys = _period_keys_for_join(period_key, family)
    empty = pd.DataFrame(
        {
            f"{family}VAH": pd.Series(index=period_key.index, dtype="float64"),
            f"{family}VAL": pd.Series(index=period_key.index, dtype="float64"),
            f"{family}POC": pd.Series(index=period_key.index, dtype="float64"),
        }
    )
    if keys.empty:
        return empty
    periods = _typed_period_index(pd.Index(keys.unique()).sort_values(), family)
    fam = table.family_rows(family)
    if fam.empty:
        aligned = pd.DataFrame(
            {
                "VAH": pd.Series(float("nan"), index=periods, dtype="float64"),
                "VAL": pd.Series(float("nan"), index=periods, dtype="float64"),
                "POC": pd.Series(float("nan"), index=periods, dtype="float64"),
            }
        )
    else:
        ordered = fam.copy()
        ordered["period_key"] = _period_keys_for_join(ordered["period_key"], family).to_numpy()
        ordered = ordered.sort_values("period_key").drop_duplicates(
            subset=["period_key"], keep="last"
        )
        lookup = ordered.set_index("period_key")[["VAH", "VAL", "POC"]]
        lookup.index = _typed_period_index(lookup.index, family)
        aligned = lookup.reindex(periods)
    shifted = aligned.shift(1)
    return pd.DataFrame(
        {
            f"{family}VAH": keys.map(shifted["VAH"]),
            f"{family}VAL": keys.map(shifted["VAL"]),
            f"{family}POC": keys.map(shifted["POC"]),
        },
        index=period_key.index,
        dtype="float64",
    )


def _as_session_date(value: object) -> date:
    """Coerce TV1 ``session_date`` / join keys to ``datetime.date``.

    ``pd.Timestamp`` is a ``datetime.date`` subclass, so ``str(timestamp)`` is
    ``YYYY-MM-DD 00:00:00`` and will not join ``trading_session_date`` keys.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if "T" in text or " " in text:
            return pd.Timestamp(text).date()
        return date.fromisoformat(text)
    return pd.Timestamp(value).date()


def _period_key_text(value: object) -> str:
    """Persist form: ``str(key)`` of the ``compute_profile_levels`` objects."""
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, str):
        return value
    return _as_session_date(value).isoformat()


def _restore_period_key(family: str, value: object) -> date | pd.Period:
    """Rebuild the dtype ``compute_profile_levels`` uses for ``period_key.map``."""
    family = str(family)
    if family == "pd":
        return _as_session_date(value)
    text = _period_key_text(value)
    if family == "pw":
        # pandas 3.x parses ``YYYY-MM-DD/YYYY-MM-DD`` as minutes without freq.
        return pd.Period(text, freq="W-SUN")
    if family == "pm":
        return pd.Period(text, freq="M")
    raise ValueError(f"Unknown prior-profile family: {family}")


def _period_keys_for_join(values: pd.Series, family: str) -> pd.Series:
    """Typed keys that ``period_key.map(...)`` accepts after parquet."""
    if values.empty:
        if family == "pw":
            return pd.Series(pd.PeriodIndex([], freq="W-SUN"), index=values.index)
        if family == "pm":
            return pd.Series(pd.PeriodIndex([], freq="M"), index=values.index)
        return pd.Series(dtype=object, index=values.index)
    restored = [_restore_period_key(family, value) for value in values]
    if family == "pw":
        return pd.Series(pd.PeriodIndex(restored, freq="W-SUN"), index=values.index)
    if family == "pm":
        return pd.Series(pd.PeriodIndex(restored, freq="M"), index=values.index)
    return pd.Series(restored, index=values.index, dtype=object)


def _typed_period_index(index: pd.Index, family: str) -> pd.Index:
    if family == "pw":
        return pd.PeriodIndex(index, freq="W-SUN")
    if family == "pm":
        return pd.PeriodIndex(index, freq="M")
    return pd.Index([_as_session_date(value) for value in index], dtype=object)


def _period_keys_from_session_date(session_date: date) -> tuple[str, str, str]:
    """Same construction as ``compute_profile_levels`` after ``trading_session_date``."""
    session_date = _as_session_date(session_date)
    day_key_ts = pd.to_datetime(session_date)
    week_key = day_key_ts.to_period("W-SUN")
    month_key = day_key_ts.to_period("M")
    return session_date.isoformat(), str(week_key), str(month_key)


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
    day_key, week_key, month_key = _period_keys_from_session_date(
        _as_session_date(chunk.session_date)
    )
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
        session_date=_as_session_date(chunk.session_date),
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
        empty["family"] = empty["family"].astype("string")
        empty["period_key"] = pd.Series(dtype=object)
        empty["VAH"] = empty["VAH"].astype("float64")
        empty["VAL"] = empty["VAL"].astype("float64")
        empty["POC"] = empty["POC"].astype("float64")
        empty["n_ticks"] = empty["n_ticks"].astype("int64")
        empty["sum_volume"] = empty["sum_volume"].astype("float64")
        empty["aggregation_ticks"] = empty["aggregation_ticks"].astype("int64")
        empty["value_area_pct"] = empty["value_area_pct"].astype("float64")
        empty["va_source"] = empty["va_source"].astype("string")
        empty["period_start"] = pd.Series(dtype="datetime64[ns, UTC]")
        empty["period_end"] = pd.Series(dtype="datetime64[ns, UTC]")
        return empty
    out = frame.loc[:, list(PRIOR_PROFILE_TABLE_COLUMNS)].copy()
    out["family"] = out["family"].astype("string")
    out["va_source"] = out["va_source"].astype("string")
    if not out["va_source"].astype(str).eq(VA_SOURCE_TICK_LAST).all():
        raise ValueError("PriorProfileTable va_source must be tick_last")
    out["period_key"] = [
        _restore_period_key(str(family), key)
        for family, key in zip(out["family"], out["period_key"], strict=True)
    ]
    for column in ("VAH", "VAL", "POC", "sum_volume", "value_area_pct"):
        out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
    out["n_ticks"] = pd.to_numeric(out["n_ticks"], errors="coerce").astype("int64")
    out["aggregation_ticks"] = pd.to_numeric(out["aggregation_ticks"], errors="coerce").astype(
        "int64"
    )
    out["period_start"] = pd.to_datetime(out["period_start"], utc=True)
    out["period_end"] = pd.to_datetime(out["period_end"], utc=True)
    return out.reset_index(drop=True)
