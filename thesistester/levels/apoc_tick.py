"""A-period Tick–Tick–Last profile table for APOC (AP2).

This is **not** ``PriorProfileTable``. Full-session tick VAP (``pd*`` / ``pw*`` /
``pm*``) remains a separate TV-series object. APOC tick identity hashes the
same Quantower files plus an A-period policy token so a VA table id cannot
collide with, or substitute for, an A-period source.

Production tick math is imported from :mod:`thesistester.levels.apoc_candidates`
(``select_a_period_rows``, ``compute_tick_last_volume_profile``). Do not add a
second histogram here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import (
    TICK_FORMAT_PROFILE,
    TickChunk,
    TickIngestError,
    iter_tick_files,
)
from thesistester.levels.apoc_candidates import (
    APOCProfileInputError,
    TICK_LAST_VOLUME_V1,
    TYPICAL_MVP_V1,
    compute_tick_last_volume_profile,
    select_a_period_rows,
)
from thesistester.levels.tick_vap import TICK_SOURCE_NONE, compute_tick_source_id

# Must match ``apoc.A_PERIOD_MINUTES`` (re-exported from this module).
A_PERIOD_MINUTES: Final[int] = 30
APOC_A_PERIOD_POLICY_ID: Final[str] = "rth_a_period_30m_v1"

APOC_PROFILE_SOURCE_TYPICAL_MVP_V1: Final[str] = TYPICAL_MVP_V1
APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1: Final[str] = TICK_LAST_VOLUME_V1
APOC_PROFILE_SOURCES: Final[frozenset[str]] = frozenset(
    {
        APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
        APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    }
)

APOC_ALLOCATION_TYPICAL_HLC3: Final[str] = "typical_hlc3_full_volume"
APOC_ALLOCATION_LAST_TIMES_VOLUME: Final[str] = "last_times_volume"

# Identity-only keys injected into the settings dict hashed by
# compute_levels_settings_hash. Never passed to compute_all_levels.
LEVELS_APOC_IDENTITY_KEYS: Final[tuple[str, ...]] = (
    "apoc_algorithm_version",
    "apoc_allocation",
    "apoc_tick_source_id",
)

_SOURCE_META: Final[dict[str, tuple[str, str]]] = {
    APOC_PROFILE_SOURCE_TYPICAL_MVP_V1: (
        APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
        APOC_ALLOCATION_TYPICAL_HLC3,
    ),
    APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1: (
        APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
        APOC_ALLOCATION_LAST_TIMES_VOLUME,
    ),
}


@dataclass(frozen=True)
class APeriodTickProfileTable:
    """RTH session date → A-period Last×Volume POC.

    Missing sessions resolve to ``NaN``. This table is never a prior-VA
    object and must not be constructed from ``PriorProfileTable``.
    """

    poc_by_session: Mapping[date, float]
    n_ticks_by_session: Mapping[date, int]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "poc_by_session", MappingProxyType(dict(self.poc_by_session)))
        object.__setattr__(
            self, "n_ticks_by_session", MappingProxyType(dict(self.n_ticks_by_session))
        )

    def poc_for(self, session_date: date) -> float:
        # ``datetime`` is a ``date`` subclass; using it as a dict key would miss.
        if isinstance(session_date, datetime):
            key = session_date.date()
        elif isinstance(session_date, date):
            key = session_date
        else:
            key = pd.Timestamp(session_date).date()
        value = self.poc_by_session.get(key)
        if value is None:
            return float("nan")
        return float(value)


def empty_a_period_tick_profile_table(
    *,
    source_id: str = TICK_SOURCE_NONE,
) -> APeriodTickProfileTable:
    """Return an empty table so every session emits ``NaN`` APOC."""
    return APeriodTickProfileTable(
        poc_by_session={},
        n_ticks_by_session={},
        source_id=source_id,
    )


def _resolve_tick_path_list(
    paths: Sequence[str | Path] | str | Path | None,
) -> list[Path]:
    """Normalize a tick-path argument to a list of non-empty paths.

    A bare ``str`` / ``Path`` is one file. Iterating a string as a sequence
    would hash individual characters and desync identity from ingest.
    """
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        text = str(paths).strip()
        return [Path(text)] if text else []
    return [Path(path) for path in paths if str(path).strip()]


def compute_apoc_tick_source_id(
    paths: Sequence[str | Path] | str | Path | None,
    *,
    format_profile: str = TICK_FORMAT_PROFILE,
) -> str:
    """Content identity for A-period tick inputs.

    Hashes the same files as VA ``tick_source_id``, then mixes in the A-period
    policy so a full-session VA table id is never reused as APOC identity.
    Missing/empty paths return ``none``.
    """
    resolved = _resolve_tick_path_list(paths)
    if not resolved:
        return TICK_SOURCE_NONE
    try:
        base = compute_tick_source_id(resolved, format_profile=format_profile)
    except OSError:
        return TICK_SOURCE_NONE
    if base == TICK_SOURCE_NONE:
        return TICK_SOURCE_NONE
    hasher = sha256()
    hasher.update(b"apoc_a_period_tick\0")
    hasher.update(base.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(APOC_A_PERIOD_POLICY_ID.encode("utf-8"))
    return hasher.hexdigest()


def attach_apoc_identity(
    settings: dict[str, Any],
    *,
    tick_paths: Sequence[str | Path] | str | Path | None = None,
    apoc_tick_source_id: str | None = None,
    format_profile: str = TICK_FORMAT_PROFILE,
) -> dict[str, Any]:
    """Put APOC source / algorithm / allocation / tick-input id in the hash dict.

    Implicit typical (key omitted) is a no-op so pre-AP2 settings hashes and
    persisted typical APOC identity stay unchanged. Identity keys attach only
    when ``apoc_profile_source`` is explicit.
    """
    attached = dict(settings)
    if "apoc_profile_source" not in attached:
        return attached
    source = str(attached.get("apoc_profile_source") or APOC_PROFILE_SOURCE_TYPICAL_MVP_V1)
    algorithm, allocation = _SOURCE_META.get(
        source,
        (source, "unknown"),
    )
    attached["apoc_algorithm_version"] = algorithm
    attached["apoc_allocation"] = allocation
    if source == APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1:
        attached["apoc_tick_source_id"] = (
            apoc_tick_source_id
            if apoc_tick_source_id
            else compute_apoc_tick_source_id(tick_paths, format_profile=format_profile)
        )
    else:
        attached["apoc_tick_source_id"] = TICK_SOURCE_NONE
    return attached


def resolve_apoc_profile_source(value: object | None) -> str:
    """Return a supported versioned source, or raise."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return APOC_PROFILE_SOURCE_TYPICAL_MVP_V1
    source = str(value)
    if source not in APOC_PROFILE_SOURCES:
        raise ValueError(
            f"Unsupported apoc_profile_source: {source!r}. "
            f"Supported sources: {sorted(APOC_PROFILE_SOURCES)}"
        )
    return source


def build_a_period_tick_profile_table(
    tick_paths: Sequence[str | Path] | str | Path | None,
    *,
    instrument: str,
    source_tz: str = "UTC",
    format_profile: str = TICK_FORMAT_PROFILE,
) -> APeriodTickProfileTable:
    """Load Quantower Tick–Tick–Last files and build the A-period POC table.

    Missing, unreadable, or malformed inputs fail closed to an empty table
    (``NaN`` APOC/pAPOC). They never fall back to typical-price allocation.
    """
    resolved = _resolve_tick_path_list(tick_paths)
    source_id = compute_apoc_tick_source_id(resolved, format_profile=format_profile)
    if not resolved:
        return empty_a_period_tick_profile_table(source_id=source_id)
    try:
        chunks = list(iter_tick_files(resolved, instrument=instrument, source_tz=source_tz))
    except (TickIngestError, OSError, ValueError):
        return empty_a_period_tick_profile_table(source_id=source_id)
    return build_a_period_tick_profile_table_from_chunks(
        chunks,
        instrument=instrument,
        source_id=source_id,
    )


def build_a_period_tick_profile_table_from_chunks(
    chunks: Iterable[TickChunk],
    *,
    instrument: str,
    source_id: str = TICK_SOURCE_NONE,
) -> APeriodTickProfileTable:
    """Aggregate already-loaded session chunks into A-period Last×Volume POCs."""
    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  Supported instruments: {sorted(INSTRUMENTS)}"
        )
    inst = INSTRUMENTS[instrument]
    parts: dict[date, list[pd.DataFrame]] = {}
    for chunk in chunks:
        if chunk.ticks is None or chunk.ticks.empty:
            parts.setdefault(chunk.session_date, [])
            continue
        parts.setdefault(chunk.session_date, []).append(chunk.ticks)

    poc_by_session: dict[date, float] = {}
    n_ticks_by_session: dict[date, int] = {}
    for session_date, frames in parts.items():
        if not frames:
            poc_by_session[session_date] = float("nan")
            n_ticks_by_session[session_date] = 0
            continue
        ticks = pd.concat(frames, ignore_index=True)
        try:
            selected = select_a_period_rows(
                ticks,
                session_date=session_date,
                exchange_tz=inst.exchange_tz,
                rth_start=inst.rth_start,
                period_minutes=A_PERIOD_MINUTES,
            )
            result = compute_tick_last_volume_profile(selected, tick_size=inst.tick_size)
        except APOCProfileInputError:
            poc_by_session[session_date] = float("nan")
            n_ticks_by_session[session_date] = 0
            continue
        poc_by_session[session_date] = float(result.poc)
        n_ticks_by_session[session_date] = int(result.source_rows)
    return APeriodTickProfileTable(
        poc_by_session=poc_by_session,
        n_ticks_by_session=n_ticks_by_session,
        source_id=source_id,
    )
