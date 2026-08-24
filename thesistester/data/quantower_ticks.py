"""Quantower Tick–Tick–Last ingest for prior-profile VAP (TV1).

This module reads History Exporter tick files and yields one CME session
chunk at a time. It is **not** an OHLCV loader: it never aggregates prints
into bars and must not be used as a substitute for the canonical bar loader.

Stamps are UTC on disk. Session membership uses the instrument ``eth_start``
in ``exchange_tz`` (row timestamps, never the filename window). Filename
labels are compared to first/last rows and recorded as warning metadata
when they disagree.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import hashlib
import re
from typing import Final

import pandas as pd
from pandas.errors import EmptyDataError

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import DataValidationError, normalize_column_name
from thesistester.levels.session_date import trading_session_date

TICK_FORMAT_PROFILE: Final[str] = "quantower_tick_last"

_TICK_COLUMN_ALIASES: Final[dict[str, str]] = {
    "time left": "timestamp",
    "date time": "timestamp",
    "datetime": "timestamp",
    "volume(from bar)": "volume",
    "volume (from bar)": "volume",
}
_REQUIRED_TICK_COLUMNS: Final[tuple[str, ...]] = ("timestamp", "price", "volume")

# Quantower export names embed ``M_D_YYYY hmmss AM-M_D_YYYY hmmss PM``.
_FILENAME_WINDOW_RE = re.compile(
    r"(?P<m1>\d{1,2})_(?P<d1>\d{1,2})_(?P<y1>\d{4})\s+"
    r"(?P<hms1>\d{5,6})\s*(?P<ap1>AM|PM)-"
    r"(?P<m2>\d{1,2})_(?P<d2>\d{1,2})_(?P<y2>\d{4})\s+"
    r"(?P<hms2>\d{5,6})\s*(?P<ap2>AM|PM)",
    flags=re.IGNORECASE,
)


class TickIngestError(DataValidationError):
    """Raised when a Quantower tick-last file cannot be ingested."""


@dataclass(frozen=True)
class TickChunk:
    """One CME session of Last × Volume prints."""

    session_date: date
    ticks: pd.DataFrame
    source_paths: tuple[str, ...]
    filename_window_mismatch: bool
    warnings: tuple[str, ...]
    first_row_utc: pd.Timestamp
    last_row_utc: pd.Timestamp
    filename_window_start: pd.Timestamp | None
    filename_window_end: pd.Timestamp | None
    format_profile: str = TICK_FORMAT_PROFILE


@dataclass(frozen=True)
class _FileMeta:
    path: Path
    first_row_utc: pd.Timestamp
    filename_window_start: pd.Timestamp | None
    filename_window_end: pd.Timestamp | None
    content_sha256: str


@dataclass(frozen=True)
class _ParsedTickFile:
    ticks: pd.DataFrame
    filename_window_mismatch: bool
    warnings: tuple[str, ...]
    filename_window_start: pd.Timestamp | None
    filename_window_end: pd.Timestamp | None


def iter_tick_files(
    paths: str | Path | Sequence[str | Path],
    *,
    instrument: str = "MNQ",
    source_tz: str = "UTC",
) -> Iterator[TickChunk]:
    """Yield CME session chunks from one or many Tick–Tick–Last CSVs.

    Files are combined in **first-row timestamp** order, not path order.
    Only one source file is fully materialized at a time; completed sessions
    are yielded before the next file is read.
    """
    inst = _instrument(instrument)
    resolved = _resolve_paths(paths)
    metas = [_peek_tick_file(path, source_tz=source_tz) for path in resolved]
    _reject_duplicate_files(metas)
    metas = sorted(metas, key=lambda item: (item.first_row_utc, str(item.path)))

    open_parts: dict[date, list[pd.DataFrame]] = {}
    open_paths: dict[date, list[str]] = {}
    open_mismatch: dict[date, bool] = {}
    open_warnings: dict[date, list[str]] = {}
    open_fn_start: dict[date, pd.Timestamp | None] = {}
    open_fn_end: dict[date, pd.Timestamp | None] = {}

    for index, meta in enumerate(metas):
        parsed = _parse_tick_file(meta.path, instrument=instrument, source_tz=source_tz)
        file_warnings = list(parsed.warnings)
        for session_key, part in parsed.ticks.groupby(parsed.ticks["_session_date"], sort=True):
            session = (
                session_key if isinstance(session_key, date) else pd.Timestamp(session_key).date()
            )
            open_parts.setdefault(session, []).append(
                part[["timestamp", "price", "volume"]].reset_index(drop=True)
            )
            open_paths.setdefault(session, []).append(str(meta.path))
            open_mismatch[session] = bool(
                open_mismatch.get(session, False) or parsed.filename_window_mismatch
            )
            open_warnings.setdefault(session, []).extend(file_warnings)
            file_warnings = []
            if open_fn_start.get(session) is None:
                open_fn_start[session] = parsed.filename_window_start
            open_fn_end[session] = parsed.filename_window_end

        next_first = metas[index + 1].first_row_utc if index + 1 < len(metas) else None
        ready = [
            session
            for session in list(open_parts)
            if next_first is None or next_first >= _session_end_utc(session, inst)
        ]
        for session in sorted(ready):
            yield _build_chunk(
                session,
                parts=open_parts.pop(session),
                source_paths=tuple(open_paths.pop(session)),
                filename_window_mismatch=open_mismatch.pop(session),
                warnings=tuple(dict.fromkeys(open_warnings.pop(session))),
                filename_window_start=open_fn_start.pop(session, None),
                filename_window_end=open_fn_end.pop(session, None),
            )


def parse_quantower_tick_filename_window(
    filename: str,
    *,
    source_tz: str = "UTC",
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Return the UTC window embedded in a Quantower tick export name, if any."""
    match = _FILENAME_WINDOW_RE.search(Path(filename).name)
    if match is None:
        return None
    start = _filename_stamp(
        match.group("y1"),
        match.group("m1"),
        match.group("d1"),
        match.group("hms1"),
        match.group("ap1"),
        source_tz=source_tz,
    )
    end = _filename_stamp(
        match.group("y2"),
        match.group("m2"),
        match.group("d2"),
        match.group("hms2"),
        match.group("ap2"),
        source_tz=source_tz,
    )
    return start, end


def _instrument(name: str):
    if name not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {name}")
    return INSTRUMENTS[name]


def _resolve_paths(paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        items = [Path(paths)]
    else:
        items = [Path(path) for path in paths]
    if not items:
        raise TickIngestError("tick_paths must contain at least one Tick–Tick–Last file.")
    resolved: list[Path] = []
    seen: set[Path] = set()
    for path in items:
        full = path.expanduser().resolve()
        if not full.is_file():
            raise TickIngestError(f"Tick file does not exist: {path}")
        if full in seen:
            raise TickIngestError(f"Duplicate tick path: {full}")
        seen.add(full)
        resolved.append(full)
    return resolved


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _reject_duplicate_files(metas: Sequence[_FileMeta]) -> None:
    by_hash: dict[str, Path] = {}
    for meta in metas:
        prior = by_hash.get(meta.content_sha256)
        if prior is not None:
            raise TickIngestError(
                "Exact duplicate tick file rejected "
                f"({prior} and {meta.path} have identical content)."
            )
        by_hash[meta.content_sha256] = meta.path


def _read_tick_csv(path: Path, *, nrows: int | None = None) -> pd.DataFrame:
    try:
        raw = pd.read_csv(path, sep=";", nrows=nrows, dtype=str, encoding="utf-8-sig")
    except EmptyDataError as exc:
        raise TickIngestError(f"Tick file is empty: {path}") from exc
    raw = raw.dropna(axis=1, how="all")
    if raw.empty:
        raise TickIngestError(f"Tick file is empty: {path}")
    columns = [normalize_column_name(column) for column in raw.columns]
    raw.columns = [_TICK_COLUMN_ALIASES.get(column, column) for column in columns]
    duplicates = sorted(name for name, count in Counter(raw.columns).items() if count > 1)
    if duplicates:
        raise TickIngestError(
            f"Duplicate columns after alias normalization: {duplicates} in {path}"
        )
    return raw


def _require_tick_columns(raw: pd.DataFrame, path: Path) -> None:
    missing = [column for column in _REQUIRED_TICK_COLUMNS if column not in raw.columns]
    if missing:
        raise TickIngestError(
            "Quantower Tick–Tick–Last profile is missing required columns: "
            f"{missing}. Detected columns after normalization: {list(raw.columns)} in {path}"
        )


def _localize_utc(values: pd.Series, *, source_tz: str, path: Path) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if parsed.isna().any():
        raise TickIngestError(f"Unparseable values in tick timestamp column: {path}")
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize(source_tz)
    return parsed.dt.tz_convert("UTC")


def _peek_tick_file(path: Path, *, source_tz: str) -> _FileMeta:
    raw = _read_tick_csv(path, nrows=1)
    _require_tick_columns(raw, path)
    first = _localize_utc(raw["timestamp"], source_tz=source_tz, path=path).iloc[0]
    window = parse_quantower_tick_filename_window(path.name, source_tz=source_tz)
    window_start = window_end = None
    if window is not None:
        window_start, window_end = window
    return _FileMeta(
        path=path,
        first_row_utc=pd.Timestamp(first),
        filename_window_start=window_start,
        filename_window_end=window_end,
        content_sha256=_file_sha256(path),
    )


def _parse_tick_file(path: Path, *, instrument: str, source_tz: str) -> _ParsedTickFile:
    inst = _instrument(instrument)
    raw = _read_tick_csv(path)
    _require_tick_columns(raw, path)

    stamps = _localize_utc(raw["timestamp"], source_tz=source_tz, path=path)
    prices = pd.to_numeric(raw["price"], errors="coerce")
    volumes = pd.to_numeric(raw["volume"], errors="coerce")
    valid = prices.notna() & volumes.notna() & (volumes > 0)
    work = pd.DataFrame(
        {
            "timestamp": stamps.loc[valid].to_numpy(),
            "price": prices.loc[valid].to_numpy(dtype="float64"),
            "volume": volumes.loc[valid].to_numpy(dtype="float64"),
        }
    )
    if work.empty:
        raise TickIngestError(f"Tick file has no usable Last×Volume rows: {path}")

    work = work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    local_ts = work["timestamp"].dt.tz_convert(inst.exchange_tz)
    work["_session_date"] = trading_session_date(local_ts, inst.eth_start)

    window = parse_quantower_tick_filename_window(path.name, source_tz=source_tz)
    warnings: list[str] = []
    mismatch = False
    window_start = window_end = None
    first = pd.Timestamp(stamps.iloc[0])
    last = pd.Timestamp(stamps.iloc[-1])
    if window is not None:
        window_start, window_end = window
        if first != window_start or last != window_end:
            mismatch = True
            warnings.append(
                "filename window does not match first/last row timestamps "
                f"(filename {window_start}–{window_end}; rows {first}–{last})"
            )
    return _ParsedTickFile(
        ticks=work,
        filename_window_mismatch=mismatch,
        warnings=tuple(warnings),
        filename_window_start=window_start,
        filename_window_end=window_end,
    )


def _session_end_utc(session: date, inst) -> pd.Timestamp:
    eth = _eth_time(inst.eth_start)
    if eth is None:
        wall = datetime.combine(session + timedelta(days=1), time(0, 0))
    else:
        wall = datetime.combine(session, eth)
    return pd.Timestamp(wall).tz_localize(inst.exchange_tz).tz_convert("UTC")


def _eth_time(eth_start: str | None) -> time | None:
    if eth_start is None:
        return None
    value = str(eth_start).strip()
    if not value:
        return None
    return pd.to_datetime(value).time()


def _filename_stamp(
    year: str,
    month: str,
    day: str,
    hms: str,
    ampm: str,
    *,
    source_tz: str,
) -> pd.Timestamp:
    padded = hms.zfill(6)
    hour = int(padded[:2])
    minute = int(padded[2:4])
    second = int(padded[4:6])
    meridiem = ampm.upper()
    if hour == 12:
        hour = 0 if meridiem == "AM" else 12
    elif meridiem == "PM":
        hour += 12
    naive = datetime(int(year), int(month), int(day), hour, minute, second)
    return pd.Timestamp(naive, tz=source_tz).tz_convert("UTC")


def _build_chunk(
    session: date,
    *,
    parts: list[pd.DataFrame],
    source_paths: tuple[str, ...],
    filename_window_mismatch: bool,
    warnings: tuple[str, ...],
    filename_window_start: pd.Timestamp | None,
    filename_window_end: pd.Timestamp | None,
) -> TickChunk:
    ticks = pd.concat(parts, ignore_index=True).sort_values("timestamp", kind="mergesort")
    ticks = ticks.reset_index(drop=True)
    first = pd.Timestamp(ticks["timestamp"].iloc[0])
    last = pd.Timestamp(ticks["timestamp"].iloc[-1])
    return TickChunk(
        session_date=session,
        ticks=ticks,
        source_paths=source_paths,
        filename_window_mismatch=filename_window_mismatch,
        warnings=warnings,
        first_row_utc=first,
        last_row_utc=last,
        filename_window_start=filename_window_start,
        filename_window_end=filename_window_end,
    )
