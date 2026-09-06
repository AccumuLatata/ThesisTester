"""Level attribution and tag verification on an already-built 1m frame (TJ6).

Consumes ``frame.columns ∩ closed_level_token_set(settings)``. Frozen tokens
use the containing minute; developing tokens use the previous completed 1m
bar. Does not call ``simulate_trades`` or ``compute_all_levels``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
import json
import math

import pandas as pd
import yaml

from thesistester.journal.schema import (
    ATTRIBUTION_OUTPUT_COLUMNS,
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    LEVEL_CONTEXT_AT_LEVEL,
    LEVEL_CONTEXT_BETWEEN,
    LEVEL_CONTEXT_NO_FRAME,
    RECON_RECONCILED,
    TAG_ALIGN_ALL,
    TAG_ALIGN_NONE,
    TAG_ALIGN_PARTIAL,
    TAG_ALIGN_UNVERIFIABLE,
    TAG_CLASS_LEVEL,
    TAG_CLASS_UNMAPPED,
    JournalIngestError,
)
from thesistester.journal.tags import TagMapping, resolve_tag
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import StudySpecError, closed_level_token_set

_PARENT_DELTA = pd.Timedelta(minutes=1)
_DEVELOPING_EXACT: frozenset[str] = frozenset({"dVWAP", "dVWAP_RTH", "wVWAP", "mVWAP", "APOC"})
_DEVELOPING_PREFIXES: tuple[str, ...] = (
    "SMA_",
    "EMA_",
    "VWAP_rolling_",
    "POC_rolling_",
)


def is_developing_token(token: str) -> bool:
    """True for developing tokens that must not use the current minute's close."""
    name = str(token)
    if name in _DEVELOPING_EXACT:
        return True
    return name.startswith(_DEVELOPING_PREFIXES)


def attribute_journal_trades(
    trades: pd.DataFrame,
    *,
    levels: pd.DataFrame,
    levels_settings: Mapping[str, object] | None = None,
    level_tolerance_ticks: float = DEFAULT_LEVEL_TOLERANCE_TICKS,
    tag_tolerance_ticks: float = DEFAULT_TAG_TOLERANCE_TICKS,
    allow_unreconciled: bool = False,
    tick_size: float = JOURNAL_TICK_SIZE,
) -> pd.DataFrame:
    """Attribute every entry to nearby tokens and verify level-class tags.

    ``levels``, ``levels_settings``, ``level_tolerance_ticks``,
    ``tag_tolerance_ticks``, ``allow_unreconciled``, and ``tick_size`` are
    keyword-only. Default tolerances are 10 ticks. Days that are not
    ``reconciled`` fail closed unless ``allow_unreconciled=True``.
    """
    level_tol = _as_tolerance(level_tolerance_ticks, name="level_tolerance_ticks")
    tag_tol = _as_tolerance(tag_tolerance_ticks, name="tag_tolerance_ticks")
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    tick = _as_positive_tick(tick_size)
    closed = _closed_tokens(levels_settings)
    frame = _normalize_levels(levels)
    tokens = tuple(column for column in frame.columns if column in closed)
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    work = _coerce_trades(trades)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    if work.empty:
        out = work.copy()
        for column in ATTRIBUTION_OUTPUT_COLUMNS:
            out[column] = pd.Series(dtype="object")
        return out

    stamps = frame["timestamp"]
    rows: list[dict[str, object]] = []
    for raw in work.to_dict(orient="records"):
        rows.append(
            _attribute_trade(
                raw,
                stamps=stamps,
                frame=frame,
                tokens=tokens,
                level_tol=level_tol,
                tag_tol=tag_tol,
                tick=tick,
            )
        )
    return _rows_to_frame(work, rows)


def write_attribution_artifacts(
    output_dir: str | Path,
    trades: pd.DataFrame,
    *,
    level_tolerance_ticks: float = DEFAULT_LEVEL_TOLERANCE_TICKS,
    tag_tolerance_ticks: float = DEFAULT_TAG_TOLERANCE_TICKS,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Write ``journal_attribution.parquet`` + ``attribution.json``. Not under ``results/studies/``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / "journal_attribution.parquet"
    json_path = out / "attribution.json"
    counts = _unmapped_counts(trades)
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "level_tolerance_ticks": float(level_tolerance_ticks),
        "tag_tolerance_ticks": float(tag_tolerance_ticks),
        "allow_unreconciled": bool(allow_unreconciled),
        "trade_count": int(len(trades)),
        "unmapped_tag_counts": dict(sorted(counts.items())),
        "unmapped_tag_total": int(sum(counts.values())),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _trades_for_parquet(trades).to_parquet(parquet_path, index=False)
    return {"journal_attribution.parquet": parquet_path, "attribution.json": json_path}


def attribute_files(
    *,
    trades: str | Path,
    levels: str | Path,
    output_dir: str | Path,
    levels_settings: str | Path | None = None,
    level_tolerance_ticks: float = DEFAULT_LEVEL_TOLERANCE_TICKS,
    tag_tolerance_ticks: float = DEFAULT_TAG_TOLERANCE_TICKS,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Load trades + a 1m levels frame, attribute, and write artifacts."""
    attributed = attribute_journal_trades(
        _load_table(trades, name="trades"),
        levels=_load_table(levels, name="levels"),
        levels_settings=_load_settings(levels_settings),
        level_tolerance_ticks=level_tolerance_ticks,
        tag_tolerance_ticks=tag_tolerance_ticks,
        allow_unreconciled=allow_unreconciled,
    )
    return write_attribution_artifacts(
        output_dir,
        attributed,
        level_tolerance_ticks=level_tolerance_ticks,
        tag_tolerance_ticks=tag_tolerance_ticks,
        allow_unreconciled=allow_unreconciled,
    )


def _closed_tokens(levels_settings: Mapping[str, object] | None) -> frozenset[str]:
    settings = dict(DEFAULT_LEVELS_SETTINGS if levels_settings is None else levels_settings)
    try:
        return closed_level_token_set(settings)
    except StudySpecError as exc:
        raise JournalIngestError(f"invalid levels_settings: {exc}") from exc


def _normalize_levels(levels: pd.DataFrame) -> pd.DataFrame:
    if levels is None or not isinstance(levels, pd.DataFrame):
        raise JournalIngestError("levels must be a DataFrame")
    if "timestamp" not in levels.columns:
        raise JournalIngestError("levels frame missing timestamp")
    if levels.empty:
        raise JournalIngestError("levels has no bars")
    work = levels.copy()
    work["timestamp"] = _as_utc_series(work["timestamp"])
    _assert_1m_grid(work["timestamp"])
    work = work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if work["timestamp"].duplicated().any():
        raise JournalIngestError("levels has duplicate bar opens")
    return work


def _coerce_trades(trades: pd.DataFrame) -> pd.DataFrame:
    needed = {"entry_timestamp", "entry_price"}
    missing = sorted(needed.difference(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["entry_timestamp"] = _as_utc_series(work["entry_timestamp"])
    work["entry_price"] = pd.to_numeric(work["entry_price"], errors="coerce")
    if work["entry_price"].isna().any() or not work["entry_price"].map(_is_finite).all():
        raise JournalIngestError("trades frame has non-finite entry_price")
    if "tags" not in work.columns:
        work["tags"] = [() for _ in range(len(work))]
    else:
        work["tags"] = work["tags"].map(_as_tags)
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_optional_str)
    if "session_date" in work.columns:
        work["session_date"] = work["session_date"].map(_as_date)
    return work


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal attribute refuses days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal attribute refuses days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _attribute_trade(
    raw: Mapping[str, object],
    *,
    stamps: pd.Series,
    frame: pd.DataFrame,
    tokens: Sequence[str],
    level_tol: float,
    tag_tol: float,
    tick: float,
) -> dict[str, object]:
    entry_ts = _as_utc(raw["entry_timestamp"])
    entry_price = float(raw["entry_price"])
    containing = _containing_bar(stamps, frame, entry_ts)
    previous = None if containing is None else _previous_completed_bar(stamps, frame, entry_ts)
    distances = (
        []
        if containing is None
        else _token_distances(
            tokens,
            containing=containing,
            previous=previous,
            entry_price=entry_price,
            tick=tick,
        )
    )
    nearby = [token for token, distance in distances if abs(distance) <= level_tol]
    nearest_token: str | None = None
    nearest_distance: float | None = None
    if distances:
        nearest_token, nearest_distance = distances[0]
    if containing is None or not distances:
        context = LEVEL_CONTEXT_NO_FRAME
    elif nearby:
        context = LEVEL_CONTEXT_AT_LEVEL
    else:
        context = LEVEL_CONTEXT_BETWEEN

    mappings = [resolve_tag(tag) for tag in _as_tags(raw.get("tags"))]
    unmapped = [item.raw for item in mappings if item.tag_class == TAG_CLASS_UNMAPPED]
    verifications: list[dict[str, object]] = []
    aligned = 0
    verifiable = 0
    level_tags = 0
    for mapping in mappings:
        if mapping.tag_class != TAG_CLASS_LEVEL:
            continue
        level_tags += 1
        record = _verify_tag(
            mapping,
            containing=containing,
            previous=previous,
            entry_price=entry_price,
            tick=tick,
            tag_tol=tag_tol,
        )
        verifications.append(record)
        if record["tag_level_missing"]:
            continue
        verifiable += 1
        if record["tag_aligned"]:
            aligned += 1
    alignment = _tag_alignment(level_tags=level_tags, verifiable=verifiable, aligned=aligned)
    intent_mismatch = bool(level_tags > 0 and aligned == 0 and nearby)
    return {
        **dict(raw),
        "levels_within_tolerance": nearby,
        "nearest_level_token": nearest_token,
        "nearest_level_distance_ticks": nearest_distance,
        "level_context": context,
        "tag_alignment": alignment,
        "intent_mismatch": intent_mismatch,
        "unmapped_tags": unmapped,
        "tag_verifications": verifications,
    }


def _token_distances(
    tokens: Sequence[str],
    *,
    containing: pd.Series | None,
    previous: pd.Series | None,
    entry_price: float,
    tick: float,
) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []
    for token in tokens:
        value = _lookup_token(token, containing=containing, previous=previous)
        if value is None:
            continue
        found.append((token, (entry_price - value) / tick))
    found.sort(key=lambda item: (abs(item[1]), item[0]))
    return found


def _verify_tag(
    mapping: TagMapping,
    *,
    containing: pd.Series | None,
    previous: pd.Series | None,
    entry_price: float,
    tick: float,
    tag_tol: float,
) -> dict[str, object]:
    token = mapping.token
    if token is None or containing is None:
        return {
            "raw": mapping.raw,
            "token": token,
            "qualifier": mapping.qualifier,
            "tag_distance_ticks": None,
            "tag_aligned": False,
            "tag_level_missing": True,
        }
    value = _lookup_token(token, containing=containing, previous=previous)
    if value is None:
        return {
            "raw": mapping.raw,
            "token": token,
            "qualifier": mapping.qualifier,
            "tag_distance_ticks": None,
            "tag_aligned": False,
            "tag_level_missing": True,
        }
    distance = (entry_price - value) / tick
    return {
        "raw": mapping.raw,
        "token": token,
        "qualifier": mapping.qualifier,
        "tag_distance_ticks": distance,
        "tag_aligned": abs(distance) <= tag_tol,
        "tag_level_missing": False,
    }


def _lookup_token(
    token: str,
    *,
    containing: pd.Series | None,
    previous: pd.Series | None,
) -> float | None:
    row = previous if is_developing_token(token) else containing
    if row is None or token not in row.index:
        return None
    return _finite_level(row[token])


def _tag_alignment(*, level_tags: int, verifiable: int, aligned: int) -> str:
    if level_tags == 0 or verifiable == 0:
        return TAG_ALIGN_UNVERIFIABLE
    if aligned == verifiable and aligned == level_tags:
        return TAG_ALIGN_ALL
    if aligned == 0:
        return TAG_ALIGN_NONE
    return TAG_ALIGN_PARTIAL


def _containing_bar(
    stamps: pd.Series, frame: pd.DataFrame, entry_ts: pd.Timestamp
) -> pd.Series | None:
    if stamps.empty:
        return None
    index = int(stamps.searchsorted(entry_ts, side="right")) - 1
    if index < 0:
        return None
    open_ts = stamps.iloc[index]
    if open_ts <= entry_ts < open_ts + _PARENT_DELTA:
        return frame.iloc[index]
    return None


def _previous_completed_bar(
    stamps: pd.Series, frame: pd.DataFrame, entry_ts: pd.Timestamp
) -> pd.Series | None:
    if stamps.empty:
        return None
    cutoff = entry_ts - _PARENT_DELTA
    index = int(stamps.searchsorted(cutoff, side="left")) - 1
    if index < 0:
        return None
    return frame.iloc[index]


def _finite_level(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_tolerance(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise JournalIngestError(f"{name} must be a non-negative number (got {value!r})")
    return float(value)


def _as_positive_tick(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise JournalIngestError(f"tick_size must be a positive number (got {value!r})")
    if not math.isfinite(float(value)):
        raise JournalIngestError(f"tick_size must be a positive number (got {value!r})")
    return float(value)


def _as_utc_series(values: pd.Series) -> pd.Series:
    converted = [_as_utc(value) for value in values]
    return pd.Series(pd.to_datetime(converted, utc=True), index=values.index)


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise JournalIngestError("timestamp is missing")
    if stamp.tzinfo is None:
        raise JournalIngestError(f"naive timestamp is not allowed ({stamp!r})")
    return stamp.tz_convert("UTC")


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"invalid session_date {value!r}") from exc


def _as_tags(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        if isinstance(value, (str, bytes)):
            raise TypeError
        if pd.isna(value):
            return ()
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    if hasattr(value, "tolist"):
        return _as_tags(value.tolist())
    try:
        items = list(value)
    except TypeError:
        return (str(value),)
    return tuple(str(item) for item in items if str(item).strip())


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _is_finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _assert_1m_grid(stamps: pd.Series) -> None:
    if (stamps.dt.microsecond != 0).any() or (stamps.dt.nanosecond != 0).any():
        raise JournalIngestError("levels timestamps must be whole-second bar opens")
    if (stamps.dt.second != 0).any():
        raise JournalIngestError("levels timestamps must be 1-minute bar opens")


def _rows_to_frame(trades: pd.DataFrame, rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    keep = [column for column in trades.columns if column in frame.columns]
    extra = [column for column in ATTRIBUTION_OUTPUT_COLUMNS if column in frame.columns]
    ordered = keep + [column for column in extra if column not in keep]
    out = frame.loc[:, ordered]
    out["entry_timestamp"] = pd.Series(out["entry_timestamp"], dtype="datetime64[ns, UTC]")
    for column in (
        "levels_within_tolerance",
        "nearest_level_token",
        "nearest_level_distance_ticks",
        "unmapped_tags",
        "tag_verifications",
        "intent_mismatch",
    ):
        out[column] = pd.Series([row[column] for row in rows], dtype="object")
    return out


def _trades_for_parquet(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    if "tags" in frame.columns:
        frame["tags"] = frame["tags"].map(lambda tags: list(tags) if tags is not None else [])
    if "session_date" in frame.columns:
        frame["session_date"] = frame["session_date"].map(
            lambda value: _as_date(value).isoformat() if _as_date(value) is not None else None
        )
    if "unmapped_tags" in frame.columns:
        frame["unmapped_tags"] = frame["unmapped_tags"].map(
            lambda tags: list(tags) if tags is not None else []
        )
    if "levels_within_tolerance" in frame.columns:
        frame["levels_within_tolerance"] = frame["levels_within_tolerance"].map(
            lambda tokens: list(tokens) if tokens is not None else []
        )
    return frame


def _unmapped_counts(trades: pd.DataFrame) -> Counter[str]:
    counts: Counter[str] = Counter()
    if "unmapped_tags" not in trades.columns:
        return counts
    for raw in trades["unmapped_tags"]:
        for tag in _as_tags(raw):
            counts[tag] += 1
    return counts


def _load_table(path: str | Path, *, name: str) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"{name} file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".parquet":
        frame = pd.read_parquet(source)
    elif suffix == ".csv":
        frame = pd.read_csv(source)
    else:
        raise JournalIngestError(f"{name} must be .parquet or .csv (got {source.suffix})")
    if not isinstance(frame, pd.DataFrame):
        raise JournalIngestError(f"{name} did not load as a DataFrame")
    return frame


def _load_settings(path: str | Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"levels_settings not found: {source}")
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    elif suffix == ".json":
        payload = json.loads(text)
    else:
        raise JournalIngestError("levels_settings must be .yaml, .yml, or .json")
    if not isinstance(payload, Mapping):
        raise JournalIngestError("levels_settings must be a mapping")
    return dict(payload)


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal attribute must not write into results/studies/")
    return resolved
