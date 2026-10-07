"""Tick-stitch plan schema, verify (TS1), session stream (TS2), clip/guard (TS3), X1 fill hook (TS4), parent tables (TS5).

Parse an ordered, non-overlapping segment plan and fail closed against a
directory of Quantower Tick–Tick–Last CSVs. ``iter_stitch_sessions`` is a
sibling of ``iter_tick_files``, not a monkey-patch. This is **not** an
ingest path: ``load_ohlcv`` and ``iter_tick_files`` do not call it. The
TS5 parent reducer (``build_stitch_parent_tables``) is the only execute
hook; workers never stream farm ticks.

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
from hashlib import sha256
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
# 11-28 CME outage stays [02:00, 13:30). The 14 single-bar windows are
# the §8 step-3 farm QC unexpected empty 15s volume bars (Accumu QC
# gate option A, 2026-10-06). Each is [bar_ts, bar_ts+15s) UTC.
_ALLOWLIST_UTC: Final[tuple[tuple[pd.Timestamp, pd.Timestamp], ...]] = (
    (
        pd.Timestamp("2025-11-28 02:00:00", tz="UTC"),
        pd.Timestamp("2025-11-28 13:30:00", tz="UTC"),
    ),
    # 2025-11-07 16:33:15, bar-assignment mismatch (214 lots)
    (
        pd.Timestamp("2025-11-07 16:33:15", tz="UTC"),
        pd.Timestamp("2025-11-07 16:33:30", tz="UTC"),
    ),
    # 2025-11-07 16:39:30, bar-assignment mismatch (43)
    (
        pd.Timestamp("2025-11-07 16:39:30", tz="UTC"),
        pd.Timestamp("2025-11-07 16:39:45", tz="UTC"),
    ),
    # 2025-12-24 06:40:45, bar-assignment mismatch (3)
    (
        pd.Timestamp("2025-12-24 06:40:45", tz="UTC"),
        pd.Timestamp("2025-12-24 06:41:00", tz="UTC"),
    ),
    # 2025-12-24 06:41:30, bar-assignment mismatch (5)
    (
        pd.Timestamp("2025-12-24 06:41:30", tz="UTC"),
        pd.Timestamp("2025-12-24 06:41:45", tz="UTC"),
    ),
    # 2025-12-24 07:55:00, bar-assignment mismatch (1)
    (
        pd.Timestamp("2025-12-24 07:55:00", tz="UTC"),
        pd.Timestamp("2025-12-24 07:55:15", tz="UTC"),
    ),
    # 2025-12-24 11:02:30, bar-assignment mismatch (2)
    (
        pd.Timestamp("2025-12-24 11:02:30", tz="UTC"),
        pd.Timestamp("2025-12-24 11:02:45", tz="UTC"),
    ),
    # 2025-12-24 11:56:00, bar-assignment mismatch (1)
    (
        pd.Timestamp("2025-12-24 11:56:00", tz="UTC"),
        pd.Timestamp("2025-12-24 11:56:15", tz="UTC"),
    ),
    # 2025-12-26 06:49:45, bar-assignment mismatch (1)
    (
        pd.Timestamp("2025-12-26 06:49:45", tz="UTC"),
        pd.Timestamp("2025-12-26 06:50:00", tz="UTC"),
    ),
    # 2025-12-26 09:46:30, bar-assignment mismatch (11)
    (
        pd.Timestamp("2025-12-26 09:46:30", tz="UTC"),
        pd.Timestamp("2025-12-26 09:46:45", tz="UTC"),
    ),
    # 2025-12-26 11:23:15, bar-assignment mismatch (1)
    (
        pd.Timestamp("2025-12-26 11:23:15", tz="UTC"),
        pd.Timestamp("2025-12-26 11:23:30", tz="UTC"),
    ),
    # 2026-01-23 03:53:15, bar-assignment mismatch (2)
    (
        pd.Timestamp("2026-01-23 03:53:15", tz="UTC"),
        pd.Timestamp("2026-01-23 03:53:30", tz="UTC"),
    ),
    # 2026-03-24 17:55:30, tick freeze (44.5 s tick gap mid-US session, 547 lots)
    (
        pd.Timestamp("2026-03-24 17:55:30", tz="UTC"),
        pd.Timestamp("2026-03-24 17:55:45", tz="UTC"),
    ),
    # 2026-04-16 20:39:15, bar-assignment mismatch (49)
    (
        pd.Timestamp("2026-04-16 20:39:15", tz="UTC"),
        pd.Timestamp("2026-04-16 20:39:30", tz="UTC"),
    ),
    # 2026-04-16 20:46:15, dual-feed outage (both feeds out 20:44–22:36;
    # ticks stamped 20:47:11.877, which has no 15s bar; 1,511 lots)
    (
        pd.Timestamp("2026-04-16 20:46:15", tz="UTC"),
        pd.Timestamp("2026-04-16 20:46:30", tz="UTC"),
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
# §4.2 stitch-on identity tokens. Not ``compute_tick_source_id`` over a path list.
X1_FILL_POLICY_TOKEN: Final[str] = "x1_15s_residual_v1"
CLIP_POLICY_TOKEN: Final[str] = "clip_15s_present_bars_v1"
HOURLY_GUARD_POLICY_TOKEN: Final[str] = "hourly_guard_allowlist_qc14_v1"
TICK_STITCH_ROOT_ENV: Final[str] = "THESISTESTER_TICK_STITCH_ROOT"
_NAS_TRADING_MARKER: Final[tuple[str, str]] = ("mnt", "nas-trading")


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


@dataclass(frozen=True)
class StitchParentTables:
    """Parent-only VA + APOC tables for worker injection (TS5)."""

    prior_profile_table: object
    apoc_tick_table: object
    tick_source_id: str
    apoc_tick_source_id: str
    data_quality: dict[str, bool]


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
    """Yield CME session chunks from a stitch plan.

    TS5 parent ``build_stitch_parent_tables`` is the execute hook. Workers
    never call this. TS4 ``farm-impact`` is also parent-only.

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
    the TS5 parent reducer call this; ``iter_stitch_sessions`` does not.
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

    Mid-hour: a tick gap ≥5s fails only when it fully contains at least
    one 15s volume bar ``[t, t+15s)`` (no clipped tick inside that bar).
    Head-of-hour (Accumu option A, 2026-10-06): same containment rule on
    the stretch from the first volume-bar left edge to the first clipped
    tick. A ``bar_ts + 7.5s`` fill does not trip head or mid-hour.
    Cut-short stays a left-edge offset check.

    ``allowed_intervals`` is the §5 TS3 (4) hook: extra half-open UTC
    ``(start, end)`` pairs supplied by the caller (stitch-meta inter-file
    weekends). This function does not invent those dates. They merge with
    the locked allowlist (11-28 plus 14 QC single-bar intervals). Accumu
    option A (2026-10-06): a hole is excused when every whole empty 15s
    volume bar ``[t, t+15s)`` in it lies inside an allowed interval. A
    hole with no whole empty bar already passes under the TS3 containment
    rule. The fail rule for holes outside allowed intervals is unchanged;
    11-28 stays ``[02:00, 13:30)`` (a whole empty bar after 13:30 still
    fails).
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


def apply_x1_residual_fill(
    ticks: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    tick_stitch_x1_burst_included: bool,
    session_date: date,
    tick_size: float,
):
    """TS4 hook for the TS5 reducer: clip → fill → guard. Lazy import.

    ``tick_stitch_x1_burst_included`` has no silent default. TS5 parent
    ``build_stitch_parent_tables`` is the only execute hook. Burst-off
    allowlist is :func:`x1_burst_guard_allowed_intervals`.
    """
    from thesistester.levels.tick_x1_fill import fill_x1_15s_residual

    return fill_x1_15s_residual(
        ticks,
        bars,
        tick_stitch_x1_burst_included=tick_stitch_x1_burst_included,
        session_date=session_date,
        tick_size=tick_size,
    )


def x1_burst_guard_allowed_intervals(
    tick_stitch_x1_burst_included: bool,
    *,
    session_date: date | None = None,
):
    """TS5 parent passes this into ``guard_hourly_tick_holes`` (Accumu option A)."""
    from thesistester.levels.tick_x1_fill import x1_burst_guard_allowed_intervals as impl

    return impl(tick_stitch_x1_burst_included, session_date=session_date)


def hourly_guard_allowed_intervals(
    tick_stitch_x1_burst_included: bool,
    *,
    session_date: date | None = None,
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    """Locked allowlist (11-28 plus 14 QC bars) plus burst-off when burst is off."""
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = list(_ALLOWLIST_UTC)
    if not tick_stitch_x1_burst_included:
        intervals.extend(x1_burst_guard_allowed_intervals(False, session_date=session_date))
    return tuple(intervals)


def refuse_nas_trading_paths(*paths: str | Path) -> None:
    """Workers and the parent refuse ``/mnt/nas-trading`` (NVMe / CI only)."""
    for raw in paths:
        parts = Path(raw).expanduser().parts
        for index in range(len(parts) - 1):
            if (
                parts[index] == _NAS_TRADING_MARKER[0]
                and parts[index + 1] == _NAS_TRADING_MARKER[1]
            ):
                raise TickStitchError(
                    "tick stitch refuses /mnt/nas-trading "
                    "(NVMe stitch only; workers never read farm SMB)."
                )


def resolve_tick_stitch_root(plan_path: str | Path) -> Path:
    """Env ``THESISTESTER_TICK_STITCH_ROOT`` if set, else the plan parent."""
    raw = os.environ.get(TICK_STITCH_ROOT_ENV)
    if raw and str(raw).strip():
        return Path(raw).expanduser()
    return Path(plan_path).expanduser().resolve().parent


def compute_tick_stitch_source_id(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
    root: str | Path,
    *,
    tick_stitch_x1_burst_included: bool,
) -> str:
    """SHA-256 of plan JSON + per-file hashes + fill/clip/session-cut tokens + burst.

    This is **not** ``compute_tick_source_id`` over a naive path list. Stitch-on
    identity is ``tick_stitch_source_id`` only.
    """
    if type(tick_stitch_x1_burst_included) is not bool:
        raise TickStitchError(
            "tick_stitch_x1_burst_included must be an explicit bool "
            "(no silent default; Q9 is Accumu's call)."
        )
    refuse_nas_trading_paths(root, plan if isinstance(plan, (str, Path)) else root)
    segments = _coerce_segments(plan)
    root_dir = Path(root).expanduser()
    from thesistester.levels.tick_vap import SESSION_CUT_POLICY_ID
    from thesistester.persistence.execution_artifacts import source_content_hash

    hasher = sha256()
    hasher.update(_canonical_plan_json_bytes(plan, segments))
    hasher.update(b"\0")
    unique: dict[str, Path] = {}
    for segment in segments:
        unique.setdefault(segment.filename, root_dir / segment.filename)
    for name in sorted(unique):
        path = unique[name]
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(source_content_hash(path).encode("utf-8"))
        hasher.update(b"\0")
    hasher.update(X1_FILL_POLICY_TOKEN.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(b"true" if tick_stitch_x1_burst_included else b"false")
    hasher.update(b"\0")
    hasher.update(CLIP_POLICY_TOKEN.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(SESSION_CUT_POLICY_ID.encode("utf-8"))
    return hasher.hexdigest()


def build_stitch_parent_tables(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
    root: str | Path,
    bars: pd.DataFrame,
    *,
    instrument: str,
    tick_stitch_x1_burst_included: bool,
    value_area_pct: float,
    prior_day_aggregation_ticks: int,
    prior_week_aggregation_ticks: int,
    prior_month_aggregation_ticks: int,
) -> StitchParentTables:
    """Verify → stream → clip → X1 fill → hourly guard → VA/APOC tables.

    Parent RAM: one session of ticks + the current histogram + A-period
    scalars. Workers never see farm CSV paths. Burst-off still uses the
    locked allowlist (11-28 plus 14 QC bars) plus
    ``x1_burst_guard_allowed_intervals``. Allowed intervals excuse a hole
    when every whole empty 15s volume bar in it lies inside an allowed
    interval (Accumu option A).
    """
    if type(tick_stitch_x1_burst_included) is not bool:
        raise TickStitchError(
            "tick_stitch_x1_burst_included must be an explicit bool "
            "(no silent default; Q9 is Accumu's call)."
        )
    refuse_nas_trading_paths(root, plan if isinstance(plan, (str, Path)) else root)
    from thesistester.config import INSTRUMENTS
    from thesistester.levels.apoc_candidates import (
        APOCProfileInputError,
        compute_tick_last_volume_profile,
        select_a_period_rows,
    )
    from thesistester.levels.apoc_tick import (
        A_PERIOD_MINUTES,
        APOC_A_PERIOD_POLICY_ID,
        APeriodTickProfileTable,
    )
    from thesistester.levels.session_date import trading_session_date
    from thesistester.levels.tick_vap import _session_histogram
    from thesistester.levels.tick_x1_fill import (
        _chunk_from_ticks,
        _table_from_histograms,
        reject_x1_synthetics,
    )

    if instrument not in INSTRUMENTS:
        raise TickStitchError(f"Unsupported instrument: {instrument!r}")
    inst = INSTRUMENTS[instrument]
    verify_tick_stitch_plan(plan, root)
    stitch_id = compute_tick_stitch_source_id(
        plan,
        root,
        tick_stitch_x1_burst_included=tick_stitch_x1_burst_included,
    )
    apoc_id = _apoc_id_from_stitch(stitch_id, APOC_A_PERIOD_POLICY_ID)
    if bars.empty or "timestamp" not in bars.columns:
        raise TickStitchError("build_stitch_parent_tables requires 15s bars with timestamp.")
    bar_work = bars.copy()
    bar_work["timestamp"] = pd.to_datetime(bar_work["timestamp"], utc=True)
    bar_local = bar_work["timestamp"].dt.tz_convert(inst.exchange_tz)
    bar_sessions = trading_session_date(bar_local, inst.eth_start)
    histograms: list[Any] = []
    poc_by_session: dict[date, float] = {}
    n_ticks_by_session: dict[date, int] = {}
    x1_fill = False
    shared_gap = False
    for chunk in iter_stitch_sessions(plan, root, instrument=instrument):
        clipped = clip_ticks_to_15s_bars(chunk.ticks, bar_work["timestamp"])
        filled, quality = apply_x1_residual_fill(
            clipped,
            bar_work,
            tick_stitch_x1_burst_included=tick_stitch_x1_burst_included,
            session_date=chunk.session_date,
            tick_size=inst.tick_size,
        )
        session_bars = bar_work.loc[bar_sessions.eq(chunk.session_date).to_numpy()]
        guard_hourly_tick_holes(
            filled,
            session_bars,
            allowed_intervals=hourly_guard_allowed_intervals(
                tick_stitch_x1_burst_included,
                session_date=chunk.session_date,
            ),
        )
        hist = _session_histogram(
            _chunk_from_ticks(chunk.session_date, filled),
            tick_size=inst.tick_size,
        )
        if hist is not None:
            histograms.append(hist)
        cleaned = reject_x1_synthetics(filled)
        try:
            selected = select_a_period_rows(
                cleaned,
                session_date=chunk.session_date,
                exchange_tz=inst.exchange_tz,
                rth_start=inst.rth_start,
                period_minutes=A_PERIOD_MINUTES,
            )
            if selected.empty:
                poc_by_session[chunk.session_date] = float("nan")
                n_ticks_by_session[chunk.session_date] = 0
            else:
                result = compute_tick_last_volume_profile(selected, tick_size=inst.tick_size)
                poc_by_session[chunk.session_date] = float(result.poc)
                n_ticks_by_session[chunk.session_date] = int(result.source_rows)
        except APOCProfileInputError:
            poc_by_session[chunk.session_date] = float("nan")
            n_ticks_by_session[chunk.session_date] = 0
        x1_fill = x1_fill or bool(quality.x1_15s_residual_fill)
        shared_gap = shared_gap or bool(quality.shared_gap_1649_1758)
    prior = _table_from_histograms(
        histograms,
        instrument=instrument,
        value_area_pct=value_area_pct,
        prior_day_aggregation_ticks=prior_day_aggregation_ticks,
        prior_week_aggregation_ticks=prior_week_aggregation_ticks,
        prior_month_aggregation_ticks=prior_month_aggregation_ticks,
    )
    apoc = APeriodTickProfileTable(
        poc_by_session=poc_by_session,
        n_ticks_by_session=n_ticks_by_session,
        source_id=apoc_id,
    )
    return StitchParentTables(
        prior_profile_table=prior,
        apoc_tick_table=apoc,
        tick_source_id=stitch_id,
        apoc_tick_source_id=apoc_id,
        data_quality={
            "data_quality.x1_15s_residual_fill": x1_fill,
            "data_quality.x1_burst_included": tick_stitch_x1_burst_included,
            "data_quality.shared_gap_1649_1758": shared_gap,
        },
    )


def _apoc_id_from_stitch(stitch_id: str, policy_id: str) -> str:
    hasher = sha256()
    hasher.update(b"apoc_a_period_tick\0")
    hasher.update(stitch_id.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(policy_id.encode("utf-8"))
    return hasher.hexdigest()


def _canonical_plan_json_bytes(
    plan: str | Path | Sequence[Mapping[str, Any]] | Sequence[TickStitchSegment],
    segments: Sequence[TickStitchSegment],
) -> bytes:
    if isinstance(plan, (str, Path)):
        payload = json.loads(Path(plan).expanduser().read_text(encoding="utf-8"))
    else:
        payload = [
            {
                "filename": segment.filename,
                "size_bytes": segment.size_bytes,
                "effective_first_utc": str(segment.effective_first_utc),
                "effective_last_utc": str(segment.effective_last_utc),
                "file_first_utc": str(segment.file_first_utc),
                "file_last_utc": str(segment.file_last_utc),
                "mtime": segment.mtime,
            }
            for segment in segments
        ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


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
    """Locked 11-28 plus 14 QC single-bar intervals, and caller §5 TS3 (4) pairs."""
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


def _empty_volume_bars_allowlisted(
    bars: pd.DataFrame,
    allowed: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
) -> bool:
    """True iff every bar ``[t, t+15s)`` lies inside one allowed interval.

    Accumu option A (2026-10-06). Empty ``bars`` means no whole empty
    15s volume bar (already a TS3 pass for mid/head).
    """
    if bars.empty:
        return True
    for raw in bars["timestamp"]:
        # Same UTC-µs SoT as the guard (`_utc_us`): naive → UTC, aware → UTC.
        # `pd.Timestamp(raw)` alone can stay naive and then raise on tz compare.
        start = _utc_us(raw, field="empty_volume_bar.timestamp")
        if not _interval_allowlisted(start, start + _BAR_INTERVAL, allowed):
            return False
    return True


def _guard_one_hour(
    hour: pd.Timestamp,
    hour_ticks: pd.Series,
    hour_bars: pd.DataFrame,
    allowed: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    if hour_ticks.empty:
        vol_empty = hour_bars.loc[hour_bars["volume"].fillna(0) > 0]
        if not vol_empty.empty and _empty_volume_bars_allowlisted(vol_empty, allowed):
            return
        raise TickStitchError(
            f"Hour {hour.isoformat()} has 15s bars but no stitched+clipped ticks."
        )
    vol_bars = hour_bars.loc[hour_bars["volume"].fillna(0) > 0].sort_values("timestamp")
    last_bar = hour_bars.sort_values("timestamp").iloc[-1]
    last_tick = pd.Timestamp(hour_ticks.max())
    last_bar_ts = pd.Timestamp(last_bar["timestamp"])
    if float(last_bar["volume"] or 0) > 0 and (last_bar_ts - last_tick) >= HOURLY_HOLE_TOLERANCE:
        cut_empty = vol_bars.loc[vol_bars["timestamp"] > last_tick]
        if not _empty_volume_bars_allowlisted(cut_empty, allowed):
            raise TickStitchError(
                f"Hour {hour.isoformat()} is cut short: last tick {last_tick.isoformat()} "
                f"is ≥5s before last 15s bar {last_bar_ts.isoformat()}."
            )
    if not vol_bars.empty:
        first_vol = pd.Timestamp(vol_bars["timestamp"].iloc[0])
        first_tick = pd.Timestamp(hour_ticks.min())
        if first_tick - first_vol >= HOURLY_HOLE_TOLERANCE:
            # Same containment as mid-hour, but the stretch includes the
            # first volume-bar left edge: [t, t+15s) ⊆ [first_vol, first_tick).
            head_spanning = vol_bars.loc[
                (vol_bars["timestamp"] >= first_vol)
                & (vol_bars["timestamp"] + _BAR_INTERVAL <= first_tick)
            ]
            if not head_spanning.empty and not _empty_volume_bars_allowlisted(
                head_spanning, allowed
            ):
                raise TickStitchError(
                    f"Hour {hour.isoformat()} has a head-of-hour hole: first tick "
                    f"{first_tick.isoformat()} is after a whole 15s volume bar "
                    f"starting {first_vol.isoformat()} with no tick."
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
        # Fully spanned: [bar_ts, bar_ts+15s) ⊆ (prev_ts, next_ts].
        spanning = vol_bars.loc[
            (vol_bars["timestamp"] > prev_ts) & (vol_bars["timestamp"] + _BAR_INTERVAL <= next_ts)
        ]
        if not spanning.empty and not _empty_volume_bars_allowlisted(spanning, allowed):
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
