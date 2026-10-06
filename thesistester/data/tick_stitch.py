"""Tick-stitch plan schema and offline verify (TS1).

Parse an ordered, non-overlapping segment plan and fail closed against a
directory of Quantower Tick–Tick–Last CSVs. This is **not** an ingest path:
``load_ohlcv``, ``iter_tick_files``, and study execute do not call it.

Header contract is the tick loader's (semicolon, ``utf-8-sig``, alias, then
``_require_tick_columns`` / ``_REQUIRED_TICK_COLUMNS``). First and last
parseable ``Time left`` are taken by seek, not by ``_peek_tick_file`` (that
reads every timestamp and content-hashes the file). Filename windows are
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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from thesistester.data.loader import DataValidationError
from thesistester.data.quantower_ticks import (
    TickIngestError,
    _REQUIRED_TICK_COLUMNS,
    _aliased_column_name,
    _localize_utc,
    _read_tick_csv,
    _require_tick_columns,
)

_SEEK_TAIL_BYTES: Final[int] = 1024 * 1024
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
    plan_path = Path(path)
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
    if isinstance(plan, (str, Path)):
        segments = load_tick_stitch_plan(plan)
    elif plan and all(isinstance(item, TickStitchSegment) for item in plan):
        segments = tuple(plan)  # type: ignore[arg-type]
    else:
        segments = parse_tick_stitch_plan(list(plan))

    root_dir = Path(root)
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
    except TickIngestError as exc:
        raise TickStitchError(str(exc)) from exc
    missing = [column for column in _REQUIRED_TICK_COLUMNS if column not in header.columns]
    if missing:
        raise TickStitchError(
            f"Quantower Tick–Tick–Last profile is missing required columns: {missing} in {path}"
        )


def _timestamp_column_index(header_line: str) -> int:
    fields = header_line.rstrip("\r\n").split(";")
    for index, field in enumerate(fields):
        if _aliased_column_name(field) == "timestamp":
            return index
    raise TickStitchError("Header has no Time left / timestamp column after alias.")


def _seek_first_last_timestamps(path: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header_line = handle.readline()
        if not header_line:
            raise TickStitchError(f"Tick file has no header: {path}")
        ts_index = _timestamp_column_index(header_line)
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
