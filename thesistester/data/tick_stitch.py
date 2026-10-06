"""Tick-stitch plan schema, verify (TS1), session stream (TS2), clip/guard (TS3).

Parse an ordered, non-overlapping segment plan and fail closed against a
directory of Quantower Tick–Tick–Last CSVs. ``iter_stitch_sessions`` is a
sibling of ``iter_tick_files``, not a monkey-patch. This is **not** an
ingest path: ``load_ohlcv``, ``iter_tick_files``, and study execute do not
call it.

Header contract is the tick loader's (semicolon, ``utf-8-sig``, alias, then
``_require_tick_columns`` / ``_REQUIRED_TICK_COLUMNS``). The timestamp-column
index uses the same pandas header parse as ``_read_tick_csv`` so quoted
headers the loader accepts are not rejected. First and last parseable
``Time left`` are taken by seek, not by ``_peek_tick_file`` (that reads
every timestamp and content-hashes the file). Filename windows are
ignored. The same basename may appear more than once with disjoint trims;
``_reject_duplicate_files`` / unique-``tick_paths`` do not run here.

Farm census (unique-file count / segment count / unique-byte sum) is an
optional expected-lock the caller passes. It is never hardcoded in this
module.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from thesistester.data.loader import DataValidationError
from thesistester.data.quantower_ticks import (
    TickChunk,
    TickIngestError,
    _REQUIRED_TICK_COLUMNS,
    _aliased_column_name,
    _build_chunk,
    _instrument,
    _is_timestamp_header,
    _localize_utc,
    _read_tick_csv,
    _require_tick_columns,
    _session_end_utc,
    _unused_empty_column,
)

_SEEK_TAIL_BYTES: Final[int] = 1024 * 1024
_STREAM_CHUNKSIZE: Final[int] = 100_000
_BAR_INTERVAL: Final[pd.Timedelta] = pd.Timedelta(seconds=15)
HOURLY_HOLE_TOLERANCE: Final[pd.Timedelta] = pd.Timedelta(seconds=5)
# Locked §5 TS3 allowlist (1). X1 is not a member. Empty-in-both
# Thanksgiving / weekend / daily-halt gaps (2) do not fail: those hours
# have no 15s bars, so the per-hour predicates never run. Inter-file
# weekends listed in stitch meta (4) are not invented here — stitch meta
# is not in the repo. Callers pass them as ``allowed_intervals``.
_ALLOWLIST_UTC: Final[tuple[tuple[pd.Timestamp, pd.Timestamp], ...]] = (
    (
        pd.Timestamp("2025-11-28 02:00:00", tz="UTC"),
        pd.Timestamp("2025-11-28 13:30:00", tz="UTC"),
    ),
)
_REQUIRED_SEGMENT_FIELDS: Final[tuple[str, ...]] = (
    "filename",
    "size_bytes",
    "effective_first_utc",
    "effective_last_utc",
    "file_first_utc",
    "file_last_utc",
)


class TickStitchError(DataValidationError):
    """Raised when a stitch plan fails closed verification."""


@dataclass(frozen=True)
class TickStitchSegment:
    """One ordered trim window over a single tick CSV basename."""

    filename: str
    size_bytes: int
    effective_first_utc: pd.Timestamp
    effective_last_utc: pd.Timestamp
    file_first_utc: pd.Timestamp
    file_last_utc: pd.Timestamp
    mtime: object | None = None


@dataclass(frozen=True)
class TickStitchCensus:
    """Optional expected-lock. Farm values are supplied by the caller, never here."""

    unique_files: int
    segments: int
    unique_bytes: int


@dataclass(frozen=True)
class TickStitchVerifyResult:
    """Verified plan census (from the plan, after disk checks)."""

    segments: tuple[TickStitchSegment, ...]
    unique_files: int
    unique_bytes: int


def load_tick_stitch_plan(path: str | Path) -> tuple[TickStitchSegment, ...]:
    """Load an ordered segment array from a JSON file."""
    plan_path = Path(path).expanduser()
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TickStitchError(f"Unable to load stitch plan {plan_path}: {exc}") from exc
    return parse_tick_stitch_plan(payload)


def parse_tick_stitch_plan(payload: object) -> tuple[TickStitchSegment, ...]:
    """Parse an ordered array of stitch segments. Fail closed on schema errors."""
    if not isinstance(payload, list) or not payload:
        raise TickStitchError("Stitch plan must be a non-empty JSON array of segments.")
    segments: list[TickStitchSegment] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise TickStitchError(f"segments[{index}] must be a mapping.")
        missing = [field for field in _REQUIRED_SEGMENT_FIELDS if field not in raw]
        if missing:
            raise TickStitchError(f"segments[{index}] missing required fields: {missing}.")
        filename = raw["filename"]
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise TickStitchError(
                f"segments[{index}].filename must be a basename only; got {filename!r}."
            )
        size_bytes = raw["size_bytes"]
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise TickStitchError(
                f"segments[{index}].size_bytes must be a non-negative int; got {size_bytes!r}."
            )
        effective_first = _utc_us(
            raw["effective_first_utc"],
            field=f"segments[{index}].effective_first_utc",
        )
        effective_last = _utc_us(
            raw["effective_last_utc"],
            field=f"segments[{index}].effective_last_utc",
        )
        file_first = _utc_us(
            raw["file_first_utc"],
            field=f"segments[{index}].file_first_utc",
        )
        file_last = _utc_us(
            raw["file_last_utc"],
            field=f"segments[{index}].file_last_utc",
        )
        if effective_first > effective_last:
            raise TickStitchError(
                f"segments[{index}] effective window is inverted "
                f"({effective_first} > {effective_last})."
            )
        if file_first > file_last:
            raise TickStitchError(
                f"segments[{index}] file range is inverted ({file_first} > {file_last})."
            )
        segments.append(
            TickStitchSegment(
                filename=filename,
                size_bytes=size_bytes,
                effective_first_utc=effective_first,
                effective_last_utc=effective_last,
                file_first_utc=file_first,
                file_last_utc=file_last,
                mtime=raw.get("mtime"),
            )
        )
    return tuple(segments)


def verify_tick_stitch_plan(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
    root: str | Path,
    *,
    expected_census: TickStitchCensus | None = None,
) -> TickStitchVerifyResult:
    """Fail closed if the plan does not match files under ``root``.

    ``root`` is an operator argument (local NVMe copies). It is never a
    hardcoded home directory. Same basename may appear more than once.
    """
    segments = _coerce_segments(plan)
    root_dir = Path(root).expanduser()
    if not root_dir.is_dir():
        raise TickStitchError(f"Tick stitch root is not a directory: {root_dir}")

    file_bounds: dict[str, tuple[int, pd.Timestamp, pd.Timestamp]] = {}
    unique_sizes: dict[str, int] = {}
    for index, segment in enumerate(segments):
        prior_size = unique_sizes.get(segment.filename)
        if prior_size is not None and prior_size != segment.size_bytes:
            raise TickStitchError(
                f"segments[{index}] size_bytes {segment.size_bytes} conflicts with "
                f"earlier {segment.filename} size_bytes {prior_size}."
            )
        unique_sizes[segment.filename] = segment.size_bytes
        if segment.filename not in file_bounds:
            file_bounds[segment.filename] = _verify_file(root_dir, segment)
        size, first, last = file_bounds[segment.filename]
        if size != segment.size_bytes:
            raise TickStitchError(
                f"segments[{index}] size_bytes {segment.size_bytes} != "
                f"stat().st_size {size} for {segment.filename}."
            )
        if first != segment.file_first_utc or last != segment.file_last_utc:
            raise TickStitchError(
                f"segments[{index}] file_first/last "
                f"{segment.file_first_utc}/{segment.file_last_utc} != "
                f"seek {first}/{last} for {segment.filename}."
            )
        if segment.effective_first_utc < first or segment.effective_last_utc > last:
            raise TickStitchError(
                f"segments[{index}] effective window "
                f"[{segment.effective_first_utc}, {segment.effective_last_utc}] "
                f"is outside file range [{first}, {last}]."
            )

    for index in range(len(segments) - 1):
        left = segments[index]
        right = segments[index + 1]
        if left.effective_last_utc >= right.effective_first_utc:
            raise TickStitchError(
                f"segments[{index}] effective_last {left.effective_last_utc} is not "
                f"strictly before segments[{index + 1}] effective_first "
                f"{right.effective_first_utc}."
            )

    unique_bytes = sum(unique_sizes.values())
    unique_files = len(unique_sizes)
    if expected_census is not None:
        _assert_census(
            expected_census,
            unique_files=unique_files,
            segments=len(segments),
            unique_bytes=unique_bytes,
        )
    return TickStitchVerifyResult(
        segments=segments,
        unique_files=unique_files,
        unique_bytes=unique_bytes,
    )


def iter_stitch_sessions(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
    root: str | Path,
    *,
    instrument: str = "MNQ",
) -> Iterator[TickChunk]:
    """Yield CME session chunks from a stitch plan. Nobody calls this yet (TS2).

    Walk segments in plan order. Consecutive same-filename windows share one
    chunked ``pd.read_csv``. Inclusive trim: keep
    ``effective_first <= timestamp <= effective_last``. Session dates use
    ``trading_session_date`` / ``_session_end_utc`` (not UTC midnight).
    Same-ms prints and ``Aggressor=None`` with ``volume > 0`` are kept;
    ``volume <= 0`` is dropped. Does not call ``_file_sha256``,
    ``_peek_tick_file``, or ``compute_tick_source_id``. Parse failures on
    the yield path raise ``TickStitchError`` (not a bare ``TickIngestError``).
    Missing basenames fail closed before the first yield.
    """
    # Lazy: session_date → levels/__init__ → this package via apoc_tick.
    from thesistester.levels.session_date import trading_session_date

    segments = _coerce_segments(plan)
    root_dir = Path(root).expanduser()
    if not root_dir.is_dir():
        raise TickStitchError(f"Tick stitch root is not a directory: {root_dir}")
    inst = _instrument(instrument)
    _preflight_stitch_files(root_dir, segments)

    open_parts: dict[date, list[pd.DataFrame]] = {}
    open_paths: dict[date, list[str]] = {}

    def flush_ready(next_ts: pd.Timestamp | None) -> Iterator[TickChunk]:
        ready = [
            session
            for session in list(open_parts)
            if next_ts is None or next_ts >= _session_end_utc(session, inst)
        ]
        for session in sorted(ready):
            yield _build_chunk(
                session,
                parts=open_parts.pop(session),
                source_paths=tuple(dict.fromkeys(open_paths.pop(session))),
                filename_window_mismatch=False,
                warnings=(),
                filename_window_start=None,
                filename_window_end=None,
            )

    for run in _consecutive_filename_runs(segments):
        path = root_dir / run[0].filename
        _check_header_contract(path)
        for kept in _iter_trimmed_chunks(path, run):
            local_ts = kept["timestamp"].dt.tz_convert(inst.exchange_tz)
            kept = kept.copy()
            kept["_session_date"] = trading_session_date(local_ts, inst.eth_start)
            for session_key, part in kept.groupby(kept["_session_date"], sort=False):
                session = (
                    session_key
                    if isinstance(session_key, date)
                    else pd.Timestamp(session_key).date()
                )
                first_ts = pd.Timestamp(part["timestamp"].iloc[0])
                yield from flush_ready(first_ts)
                open_parts.setdefault(session, []).append(
                    part[["timestamp", "price", "volume"]].reset_index(drop=True)
                )
                open_paths.setdefault(session, []).append(str(path))

    yield from flush_ready(None)


def clip_ticks_to_15s_bars(
    ticks: pd.DataFrame,
    bar_timestamps: pd.Series | Sequence[object],
) -> pd.DataFrame:
    """Drop ticks whose ``floor(ts, 15s)`` is not a present 15s bar.

    Left-closed, right-open (§4.4). Does not impute missing bars. Tests and
    the future parent reducer call this; ``iter_stitch_sessions`` does not.
    """
    if ticks.empty:
        return ticks.copy()
    if "timestamp" not in ticks.columns:
        raise TickStitchError("clip_ticks_to_15s_bars requires a timestamp column.")
    stamps = _as_utc_us_series(ticks["timestamp"])
    bar_index = pd.DatetimeIndex(_as_utc_us_series(pd.Series(list(bar_timestamps))))
    keep = stamps.dt.floor("15s").isin(bar_index)
    return ticks.loc[keep.to_numpy()].reset_index(drop=True)


def guard_hourly_tick_holes(
    ticks: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    allowed_intervals: Sequence[tuple[object, object]] | None = None,
) -> None:
    """Fail closed on unexpected ≥5s holes versus 15s bars with volume.

    Not an execute hook (TS3). X1 is not an allowlist bypass: an unfilled
    X1 hour with 15s volume fails. The 2025-11-28 CME outage
    ``[02:00, 13:30)`` UTC is allowlisted as a half-open interval, not as
    whole clock hours — a cut-short after 13:30 still fails. Hours with
    ticks but no 15s bars do not fail.

    ``allowed_intervals`` is the §5 TS3 (4) hook: extra half-open UTC
    ``(start, end)`` pairs supplied by the caller (stitch-meta inter-file
    weekends). This function does not invent those dates. They merge with
    the locked 11-28 interval. A hole fails unless ``[hole_start, hole_end)``
    is contained in the merged allowlist.
    """
    if "timestamp" not in bars.columns or "volume" not in bars.columns:
        raise TickStitchError("guard_hourly_tick_holes requires bars timestamp and volume.")
    if bars.empty:
        return
    allowed = _normalize_allowlist(allowed_intervals)
    bar_work = pd.DataFrame(
        {
            "timestamp": _as_utc_us_series(bars["timestamp"]),
            "volume": pd.to_numeric(bars["volume"], errors="coerce"),
        }
    )
    bar_work = bar_work.dropna(subset=["timestamp"])
    if bar_work.empty:
        return
    tick_stamps = (
        _as_utc_us_series(ticks["timestamp"])
        if not ticks.empty and "timestamp" in ticks.columns
        else pd.Series(dtype="datetime64[us, UTC]")
    )
    bar_work["hour"] = bar_work["timestamp"].dt.floor("h")
    tick_hours = (
        tick_stamps.dt.floor("h") if len(tick_stamps) else pd.Series(dtype="datetime64[us, UTC]")
    )
    for hour, hour_bars in bar_work.groupby("hour", sort=True):
        hour_ts = _utc_us(hour, field="hour")
        hour_ticks = tick_stamps.loc[tick_hours == hour_ts] if len(tick_stamps) else tick_stamps
        _guard_one_hour(hour_ts, hour_ticks, hour_bars, allowed)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m thesistester.data.tick_stitch verify PLAN ROOT``."""
    parser = argparse.ArgumentParser(prog="python -m thesistester.data.tick_stitch")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Fail-closed stitch plan verification")
    verify.add_argument("plan", type=Path, help="Path to tick_stitch_plan.json")
    verify.add_argument("root", type=Path, help="Directory of local tick CSV copies")
    args = parser.parse_args(argv)
    if args.command != "verify":
        raise AssertionError(f"Unhandled command: {args.command}")
    try:
        result = verify_tick_stitch_plan(args.plan, args.root)
    except TickStitchError as exc:
        print(str(exc), file=sys.stderr)
        return os.EX_DATAERR
    print(
        f"Verified {len(result.segments)} segment(s), "
        f"{result.unique_files} unique file(s), "
        f"{result.unique_bytes} unique byte(s)."
    )
    return os.EX_OK


def _coerce_segments(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
) -> tuple[TickStitchSegment, ...]:
    if isinstance(plan, (str, Path)):
        return load_tick_stitch_plan(plan)
    # Materialize first. A generator would be consumed by the type check
    # and then verify zero segments — fail-open.
    items = list(plan)
    if items and all(isinstance(item, TickStitchSegment) for item in items):
        return tuple(items)
    return parse_tick_stitch_plan(items)


def _preflight_stitch_files(root_dir: Path, segments: Sequence[TickStitchSegment]) -> None:
    """Fail closed on a missing basename before any session is yielded."""
    seen: set[str] = set()
    for segment in segments:
        if segment.filename in seen:
            continue
        seen.add(segment.filename)
        path = root_dir / segment.filename
        if not path.is_file():
            raise TickStitchError(f"Tick file does not exist: {path}")


def _consecutive_filename_runs(
    segments: Sequence[TickStitchSegment],
) -> Iterator[tuple[TickStitchSegment, ...]]:
    index = 0
    while index < len(segments):
        end = index + 1
        while end < len(segments) and segments[end].filename == segments[index].filename:
            end += 1
        yield tuple(segments[index:end])
        index = end


def _normalize_tick_chunk(raw: pd.DataFrame, path: Path) -> pd.DataFrame:
    keep = [column for column in raw.columns if not _unused_empty_column(column, raw[column])]
    raw = raw.loc[:, keep]
    columns = [_aliased_column_name(column) for column in raw.columns]
    raw.columns = columns
    duplicates = sorted(name for name, count in Counter(raw.columns).items() if count > 1)
    if duplicates:
        raise TickStitchError(
            f"Duplicate columns after alias normalization: {duplicates} in {path}"
        )
    try:
        _require_tick_columns(raw, path)
    except TickIngestError as exc:
        raise TickStitchError(str(exc)) from exc
    return raw


def _iter_trimmed_chunks(
    path: Path,
    run: Sequence[TickStitchSegment],
) -> Iterator[pd.DataFrame]:
    windows = [(segment.effective_first_utc, segment.effective_last_utc) for segment in run]
    # Latest effective_last in this run. Plan order is time order (§4.3), so
    # this equals windows[-1][1]; max is the stop condition either way.
    last_end = max(last for _, last in windows)
    try:
        reader = pd.read_csv(
            path,
            sep=";",
            dtype=str,
            encoding="utf-8-sig",
            chunksize=_STREAM_CHUNKSIZE,
        )
    except (OSError, EmptyDataError, ParserError, ValueError) as exc:
        raise TickStitchError(f"Unable to read tick file {path}: {exc}") from exc
    try:
        for raw in reader:
            if raw.empty:
                continue
            chunk = _normalize_tick_chunk(raw, path)
            try:
                stamps = _localize_utc(chunk["timestamp"], source_tz="UTC", path=path)
            except TickIngestError as exc:
                raise TickStitchError(str(exc)) from exc
            stamps = stamps.dt.tz_convert("UTC").dt.floor("us")
            if stamps.min() > last_end:
                break
            prices = pd.to_numeric(chunk["price"], errors="coerce")
            volumes = pd.to_numeric(chunk["volume"], errors="coerce")
            usable = prices.notna() & volumes.notna() & (volumes > 0)
            in_window = pd.Series(False, index=chunk.index)
            for first, last in windows:
                in_window = in_window | ((stamps >= first) & (stamps <= last))
            keep = usable & in_window
            if not keep.any():
                continue
            yield pd.DataFrame(
                {
                    "timestamp": stamps.loc[keep].reset_index(drop=True),
                    "price": prices.loc[keep].to_numpy(dtype="float64"),
                    "volume": volumes.loc[keep].to_numpy(dtype="float64"),
                }
            )
    except TickStitchError:
        raise
    except (OSError, EmptyDataError, ParserError, ValueError) as exc:
        raise TickStitchError(f"Unable to read tick file {path}: {exc}") from exc
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()


def _as_utc_us_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed", utc=True)
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize("UTC")
    else:
        parsed = parsed.dt.tz_convert("UTC")
    return parsed.dt.floor("us")


def _normalize_allowlist(
    extra: Sequence[tuple[object, object]] | None,
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    """Locked 11-28 interval plus caller-supplied §5 TS3 (4) pairs."""
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = list(_ALLOWLIST_UTC)
    if extra:
        for index, item in enumerate(extra):
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise TickStitchError(f"allowed_intervals[{index}] must be a (start, end) pair.")
            start = _utc_us(item[0], field=f"allowed_intervals[{index}].start")
            end = _utc_us(item[1], field=f"allowed_intervals[{index}].end")
            if start >= end:
                raise TickStitchError(
                    f"allowed_intervals[{index}] is inverted or empty ({start} >= {end})."
                )
            intervals.append((start, end))
    return _merge_utc_intervals(tuple(intervals))


def _merge_utc_intervals(
    intervals: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    if not intervals:
        return ()
    ordered = sorted(intervals, key=lambda pair: (pair[0], pair[1]))
    merged: list[list[pd.Timestamp]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def _interval_allowlisted(
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
) -> bool:
    """True iff ``[start, end)`` is contained in one merged allowlist interval."""
    if end <= start:
        return True
    for allow_start, allow_end in allowed:
        if allow_start <= start and end <= allow_end:
            return True
    return False


def _guard_one_hour(
    hour: pd.Timestamp,
    hour_ticks: pd.Series,
    hour_bars: pd.DataFrame,
    allowed: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    if hour_ticks.empty:
        span_start = pd.Timestamp(hour_bars["timestamp"].min())
        span_end = pd.Timestamp(hour_bars["timestamp"].max()) + _BAR_INTERVAL
        if _interval_allowlisted(span_start, span_end, allowed):
            return
        raise TickStitchError(
            f"Hour {hour.isoformat()} has 15s bars but no stitched+clipped ticks."
        )
    vol_bars = hour_bars.loc[hour_bars["volume"].fillna(0) > 0].sort_values("timestamp")
    last_bar = hour_bars.sort_values("timestamp").iloc[-1]
    last_tick = pd.Timestamp(hour_ticks.max())
    last_bar_ts = pd.Timestamp(last_bar["timestamp"])
    if float(last_bar["volume"] or 0) > 0 and (last_bar_ts - last_tick) >= HOURLY_HOLE_TOLERANCE:
        if not _interval_allowlisted(last_tick, last_bar_ts, allowed):
            raise TickStitchError(
                f"Hour {hour.isoformat()} is cut short: last tick {last_tick.isoformat()} "
                f"is ≥5s before last 15s bar {last_bar_ts.isoformat()}."
            )
    if not vol_bars.empty:
        first_vol = pd.Timestamp(vol_bars["timestamp"].iloc[0])
        first_tick = pd.Timestamp(hour_ticks.min())
        if first_tick - first_vol >= HOURLY_HOLE_TOLERANCE:
            if not _interval_allowlisted(first_vol, first_tick, allowed):
                raise TickStitchError(
                    f"Hour {hour.isoformat()} has a head-of-hour hole: first tick "
                    f"{first_tick.isoformat()} is ≥5s after first 15s bar with volume "
                    f"{first_vol.isoformat()}."
                )
    ordered = hour_ticks.sort_values().reset_index(drop=True)
    if len(ordered) < 2:
        return
    gaps = ordered.diff().iloc[1:]
    for offset, gap in enumerate(gaps):
        if pd.isna(gap) or gap < HOURLY_HOLE_TOLERANCE:
            continue
        prev_ts = pd.Timestamp(ordered.iloc[offset])
        next_ts = pd.Timestamp(ordered.iloc[offset + 1])
        spanning = vol_bars.loc[
            (vol_bars["timestamp"] < next_ts) & (vol_bars["timestamp"] + _BAR_INTERVAL > prev_ts)
        ]
        if not spanning.empty and not _interval_allowlisted(prev_ts, next_ts, allowed):
            raise TickStitchError(
                f"Hour {hour.isoformat()} has a mid-hour tick gap ≥5s "
                f"({prev_ts.isoformat()} → {next_ts.isoformat()}) spanning 15s bars "
                "with volume."
            )


def _utc_us(value: object, *, field: str) -> pd.Timestamp:
    try:
        parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    except (TypeError, ValueError) as exc:
        raise TickStitchError(f"Unparseable {field}: {value!r}") from exc
    if pd.isna(parsed):
        raise TickStitchError(f"Unparseable {field}: {value!r}")
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.floor("us")


def _assert_census(
    expected: TickStitchCensus,
    *,
    unique_files: int,
    segments: int,
    unique_bytes: int,
) -> None:
    if (
        unique_files != expected.unique_files
        or segments != expected.segments
        or unique_bytes != expected.unique_bytes
    ):
        raise TickStitchError(
            "Stitch census mismatch: "
            f"unique_files {unique_files}!={expected.unique_files}, "
            f"segments {segments}!={expected.segments}, "
            f"unique_bytes {unique_bytes}!={expected.unique_bytes}."
        )


def _verify_file(root: Path, segment: TickStitchSegment) -> tuple[int, pd.Timestamp, pd.Timestamp]:
    path = root / segment.filename
    if not path.is_file():
        raise TickStitchError(f"Tick file does not exist: {path}")
    size = path.stat().st_size
    _check_header_contract(path)
    first, last = _seek_first_last_timestamps(path)
    return size, first, last


def _check_header_contract(path: Path) -> None:
    try:
        header = _read_tick_csv(path, nrows=0)
        _require_tick_columns(header, path)
    except (TickIngestError, OSError, EmptyDataError, ParserError, ValueError) as exc:
        raise TickStitchError(str(exc)) from exc
    missing = [column for column in _REQUIRED_TICK_COLUMNS if column not in header.columns]
    if missing:
        raise TickStitchError(
            f"Quantower Tick–Tick–Last profile is missing required columns: {missing} in {path}"
        )


def _timestamp_column_index(path: Path) -> int:
    """Column index from the loader's pandas header parse, not a raw split.

    §4.2.3: same header grammar as ``_read_tick_csv`` (semicolon, utf-8-sig,
    alias). A raw ``split(';')`` rejects quoted headers the loader accepts.
    The index is taken *before* unused empty columns are dropped so it still
    matches on-disk field positions.
    """
    try:
        raw = pd.read_csv(path, sep=";", nrows=0, dtype=str, encoding="utf-8-sig")
    except (OSError, EmptyDataError, ParserError, ValueError) as exc:
        raise TickStitchError(f"Unable to read tick header {path}: {exc}") from exc
    matches = [index for index, column in enumerate(raw.columns) if _is_timestamp_header(column)]
    if len(matches) != 1:
        raise TickStitchError(
            f"Header has no unique Time left / timestamp column after alias in {path}"
        )
    return matches[0]


def _seek_first_last_timestamps(path: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    ts_index = _timestamp_column_index(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header_line = handle.readline()
        if not header_line:
            raise TickStitchError(f"Tick file has no header: {path}")
        first: pd.Timestamp | None = None
        for line in handle:
            first = _parse_line_timestamp(line, ts_index, path=path)
            if first is not None:
                break
    if first is None:
        raise TickStitchError(f"No parseable Time left in {path}")
    last = _seek_last_timestamp(path, ts_index)
    return first, last


def _seek_last_timestamp(path: Path, ts_index: int) -> pd.Timestamp:
    size = path.stat().st_size
    tail = min(size, _SEEK_TAIL_BYTES)
    with path.open("rb") as handle:
        handle.seek(size - tail)
        raw = handle.read(tail)
    if size > tail:
        text = raw.decode("utf-8", errors="replace")
        newline = text.find("\n")
        if newline == -1:
            raise TickStitchError(f"No complete line in seek tail of {path}")
        text = text[newline + 1 :]
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        newline = text.find("\n")
        if newline == -1:
            raise TickStitchError(f"Tick file has no data rows: {path}")
        text = text[newline + 1 :]
    last: pd.Timestamp | None = None
    for line in text.splitlines():
        parsed = _parse_line_timestamp(line, ts_index, path=path)
        if parsed is not None:
            last = parsed
    if last is None:
        raise TickStitchError(f"No parseable Time left in seek tail of {path}")
    return last


def _parse_line_timestamp(line: str, ts_index: int, *, path: Path) -> pd.Timestamp | None:
    fields = line.rstrip("\r\n").split(";")
    if ts_index >= len(fields):
        return None
    text = fields[ts_index].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    if pd.isna(parsed):
        return None
    try:
        localized = _localize_utc(pd.Series([parsed]), source_tz="UTC", path=path)
    except TickIngestError:
        return None
    return pd.Timestamp(localized.iloc[0]).tz_convert("UTC").floor("us")


if __name__ == "__main__":
    raise SystemExit(main())
