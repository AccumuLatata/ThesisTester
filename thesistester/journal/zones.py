"""Zone attribution on the previous completed 1m bar (JS1).

Calls ``detect_confluence_zones`` on an already-built 1m levels frame.
Does not call ``simulate_trades``, ``compute_all_levels``, or
``generate_signals``. Does not reuse TJ6 ``_expected_previous_open``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
import hashlib
import json
import math

import pandas as pd
import yaml

from thesistester.engine.confluence import detect_confluence_zones
from thesistester.journal.schema import (
    APPROACH_FROM_ABOVE,
    APPROACH_FROM_BELOW,
    APPROACH_INSIDE,
    APPROACH_UNKNOWN,
    DEFAULT_ZONE_MAX_CONFLUENCES,
    DEFAULT_ZONE_MIN_CONFLUENCES,
    DEFAULT_ZONE_TOLERANCE_TICKS,
    JOIN_BAR_SECONDS,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    RECON_RECONCILED,
    ZONE_OUTPUT_COLUMNS,
    ZONE_REL_ABOVE,
    ZONE_REL_BELOW,
    ZONE_REL_INSIDE,
    ZONE_REL_NONE,
    JournalIngestError,
)
from thesistester.levels.session_date import trading_session_date

_PARENT_DELTA = pd.Timedelta(minutes=1)
_BAR_15S = pd.Timedelta(seconds=JOIN_BAR_SECONDS)
_ZONES_PARQUET = "journal_zones.parquet"
_ZONES_JSON = "zones.json"


def previous_completed_1m_open(entry_ts: pd.Timestamp) -> pd.Timestamp:
    """1m bar open with ``open + 1min <= entry``. Exact ``09:30:00`` → ``09:29``.

    Timestamps are bar opens. Do not use TJ6 ``_expected_previous_open``
    (that helper returns ``09:28`` at an exact ``09:30:00`` fill).
    """
    stamp = _as_utc(entry_ts)
    return stamp.floor("min") - _PARENT_DELTA


def previous_completed_15s_opens(entry_ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The two completed 15s bar opens immediately before ``entry``."""
    stamp = _as_utc(entry_ts)
    last = stamp.floor(f"{JOIN_BAR_SECONDS}s") - _BAR_15S
    return last - _BAR_15S, last


def canonical_zone_params_hash(params: Mapping[str, object]) -> str:
    """SHA-256 of the declared level columns + tolerance + min/max."""
    payload = {
        "level_columns": list(params["level_columns"]),
        "max_confluences": int(params["max_confluences"]),
        "min_confluences": int(params["min_confluences"]),
        "tolerance_ticks": float(params["tolerance_ticks"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_zone_params(
    path: str | Path,
    *,
    available_columns: Sequence[str] | None = None,
) -> dict[str, object]:
    """Load a declared zone-parameter file. Missing keys use study defaults."""
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"zone-params not found: {source}")
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            raw = yaml.safe_load(text)
        elif suffix == ".json":
            raw = json.loads(text)
        else:
            raise JournalIngestError("zone-params must be .yaml, .yml, or .json")
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise JournalIngestError(f"zone-params is not valid {suffix}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise JournalIngestError("zone-params must be a mapping")
    return normalize_zone_params(raw, available_columns=available_columns)


def normalize_zone_params(
    raw: Mapping[str, object],
    *,
    available_columns: Sequence[str] | None = None,
) -> dict[str, object]:
    """Validate declared params. Does not search tolerances to maximise n."""
    columns_raw = raw.get("level_columns", raw.get("levels"))
    if columns_raw is None:
        raise JournalIngestError("zone-params must declare level_columns (or levels)")
    if not isinstance(columns_raw, (list, tuple)):
        raise JournalIngestError("zone-params level_columns must be a list")
    columns = [str(item).strip() for item in columns_raw]
    if not columns or any(not item for item in columns):
        raise JournalIngestError("zone-params level_columns must be non-empty strings")
    if len(columns) != len(set(columns)):
        raise JournalIngestError("zone-params level_columns must be unique")
    if available_columns is not None:
        unknown = [item for item in columns if item not in set(available_columns)]
        if unknown and not any(item in set(available_columns) for item in columns):
            raise JournalIngestError(
                "zone-params level_columns are absent from the levels frame: " + ", ".join(unknown)
            )
    tolerance = _as_tolerance(
        raw.get("tolerance_ticks", DEFAULT_ZONE_TOLERANCE_TICKS),
        name="tolerance_ticks",
    )
    min_conf = _as_positive_int(
        raw.get("min_confluences", DEFAULT_ZONE_MIN_CONFLUENCES),
        name="min_confluences",
        minimum=1,
    )
    max_conf = _as_positive_int(
        raw.get("max_confluences", DEFAULT_ZONE_MAX_CONFLUENCES),
        name="max_confluences",
        minimum=1,
        maximum=5,
    )
    if max_conf < min_conf:
        raise JournalIngestError("zone-params max_confluences must be >= min_confluences")
    return {
        "level_columns": columns,
        "tolerance_ticks": tolerance,
        "min_confluences": min_conf,
        "max_confluences": max_conf,
    }


def attribute_journal_zones(
    trades: pd.DataFrame,
    *,
    levels: pd.DataFrame,
    zone_params: Mapping[str, object],
    bars: pd.DataFrame | None = None,
    allow_unreconciled: bool = False,
    tick_size: float = JOURNAL_TICK_SIZE,
) -> pd.DataFrame:
    """Attribute every entry to the engine zone on the previous completed 1m bar.

    ``levels``, ``zone_params``, ``bars``, ``allow_unreconciled``, and
    ``tick_size`` are keyword-only. Unreconciled days fail closed unless
    ``allow_unreconciled=True``.
    """
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    tick = _as_positive_tick(tick_size)
    params = normalize_zone_params(zone_params, available_columns=list(levels.columns))
    digest = canonical_zone_params_hash(params)
    frame = _normalize_levels(levels)
    work = _coerce_trades(trades)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    bars_frame = None if bars is None else _normalize_bars(bars)
    if work.empty:
        out = work.copy()
        for column in ZONE_OUTPUT_COLUMNS:
            out[column] = pd.Series(dtype="object")
        return out

    stamps = frame["timestamp"]
    session_zones = detect_confluence_zones(
        frame,
        list(params["level_columns"]),
        tick,
        float(params["tolerance_ticks"]),
        int(params["min_confluences"]),
        int(params["max_confluences"]),
    )
    by_bar = _zones_by_timestamp(session_zones)
    rows: list[dict[str, object]] = []
    for raw in work.to_dict(orient="records"):
        rows.append(
            _attribute_trade(
                raw,
                stamps=stamps,
                frame=frame,
                by_bar=by_bar,
                params=params,
                digest=digest,
                tick=tick,
                bars=bars_frame,
            )
        )
    return _rows_to_frame(work, rows)


def write_zone_artifacts(
    output_dir: str | Path,
    trades: pd.DataFrame,
    *,
    params: Mapping[str, object],
    zone_params_hash: str,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Write ``journal_zones.parquet`` + ``zones.json``. Not under ``results/studies/``."""
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / _ZONES_PARQUET
    json_path = out / _ZONES_JSON
    relations = _relation_counts(trades)
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "zone_params": {
            "level_columns": list(params["level_columns"]),
            "tolerance_ticks": float(params["tolerance_ticks"]),
            "min_confluences": int(params["min_confluences"]),
            "max_confluences": int(params["max_confluences"]),
        },
        "zone_params_hash": zone_params_hash,
        "allow_unreconciled": allow_unreconciled,
        "trade_count": int(len(trades)),
        "relation_counts": dict(sorted(relations.items())),
        "omitted_no_zone": int(relations.get(ZONE_REL_NONE, 0)),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _trades_for_parquet(trades).to_parquet(parquet_path, index=False)
    return {_ZONES_PARQUET: parquet_path, _ZONES_JSON: json_path}


def zone_files(
    *,
    trades: str | Path,
    levels: str | Path,
    zone_params: str | Path,
    output_dir: str | Path,
    bars: str | Path | None = None,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Load trades + a 1m levels frame, attribute zones, and write artifacts."""
    levels_frame = _load_table(levels, name="levels")
    params = load_zone_params(zone_params, available_columns=list(levels_frame.columns))
    attributed = attribute_journal_zones(
        _load_table(trades, name="trades"),
        levels=levels_frame,
        zone_params=params,
        bars=None if bars is None else _load_table(bars, name="bars"),
        allow_unreconciled=allow_unreconciled,
    )
    return write_zone_artifacts(
        output_dir,
        attributed,
        params=params,
        zone_params_hash=canonical_zone_params_hash(params),
        allow_unreconciled=allow_unreconciled,
    )


def _attribute_trade(
    raw: Mapping[str, object],
    *,
    stamps: pd.Series,
    frame: pd.DataFrame,
    by_bar: Mapping[pd.Timestamp, pd.DataFrame],
    params: Mapping[str, object],
    digest: str,
    tick: float,
    bars: pd.DataFrame | None,
) -> dict[str, object]:
    entry_ts = _as_utc(raw["entry_timestamp"])
    entry_price = float(raw["entry_price"])
    expected = previous_completed_1m_open(entry_ts)
    previous = _lookup_bar(stamps, frame, expected)
    empty = _empty_zone_fields(digest)
    if previous is None:
        empty["approach_side"] = APPROACH_UNKNOWN
        return {**dict(raw), **empty}
    bar_ts = _as_utc(previous["timestamp"])
    zones = by_bar.get(bar_ts)
    if zones is None or zones.empty:
        empty["approach_side"] = APPROACH_UNKNOWN
        return {**dict(raw), **empty}
    picked = _pick_zone(zones, entry_price=entry_price)
    relation = _relation(
        entry_price,
        zone_low=float(picked["zone_low"]),
        zone_high=float(picked["zone_high"]),
        tolerance_ticks=float(params["tolerance_ticks"]),
        tick=tick,
    )
    mid = float(picked["zone_mid"])
    offset = (entry_price - mid) / tick
    at_zone = relation != ZONE_REL_NONE
    session = _session_of(raw, entry_ts)
    approach = _approach_side(
        bars,
        entry_ts=entry_ts,
        zone_low=float(picked["zone_low"]),
        zone_high=float(picked["zone_high"]),
    )
    return {
        **dict(raw),
        "zone_params_hash": digest,
        "zone_id": _zone_id(session, bar_ts, picked) if at_zone else None,
        "zone_low": float(picked["zone_low"]),
        "zone_high": float(picked["zone_high"]),
        "zone_mid": mid,
        "zone_width_ticks": (float(picked["zone_high"]) - float(picked["zone_low"])) / tick,
        "zone_level_count": int(picked["level_count"]),
        "zone_level_names": str(picked["level_names"]),
        "entry_zone_relation": relation,
        "entry_offset_ticks": offset if at_zone else None,
        "approach_side": approach,
        "nearest_zone_distance_ticks": abs(offset) if not at_zone else None,
    }


def _pick_zone(zones: pd.DataFrame, *, entry_price: float) -> pd.Series:
    """Prefer a zone that contains the fill; else nearest mid.

    Closest-mid first can label an in-zone fill ``below_within_tol`` of a
    tighter foreign cluster. Containing wins; among that class (or among
    all zones when none contain), tie-break by mid distance, ``zone_low``,
    then ``level_names``.
    """
    ranked = zones.copy()
    ranked["_dist"] = (ranked["zone_mid"].map(float) - entry_price).abs()
    ranked["_low"] = ranked["zone_low"].map(float)
    ranked["_high"] = ranked["zone_high"].map(float)
    ranked["_names"] = ranked["level_names"].map(str)
    inside = ranked.loc[(ranked["_low"] <= entry_price) & (entry_price <= ranked["_high"])]
    candidates = inside if not inside.empty else ranked
    candidates = candidates.sort_values(["_dist", "_low", "_names"], kind="mergesort")
    return candidates.iloc[0]


def _relation(
    entry_price: float,
    *,
    zone_low: float,
    zone_high: float,
    tolerance_ticks: float,
    tick: float,
) -> str:
    if zone_low <= entry_price <= zone_high:
        return ZONE_REL_INSIDE
    edge_tol = tolerance_ticks * tick
    if entry_price > zone_high and (entry_price - zone_high) <= edge_tol:
        return ZONE_REL_ABOVE
    if entry_price < zone_low and (zone_low - entry_price) <= edge_tol:
        return ZONE_REL_BELOW
    return ZONE_REL_NONE


def _approach_side(
    bars: pd.DataFrame | None,
    *,
    entry_ts: pd.Timestamp,
    zone_low: float,
    zone_high: float,
) -> str:
    if bars is None or bars.empty:
        return APPROACH_UNKNOWN
    earlier_open, last_open = previous_completed_15s_opens(entry_ts)
    stamps = bars["timestamp"]
    earlier = _lookup_bar(stamps, bars, earlier_open)
    last = _lookup_bar(stamps, bars, last_open)
    if earlier is None or last is None:
        return APPROACH_UNKNOWN
    # Origin of the two-bar approach (not the last close; not fade _approach_side).
    close = _finite_close(earlier.get("close"))
    if close is None:
        return APPROACH_UNKNOWN
    if close > zone_high:
        return APPROACH_FROM_ABOVE
    if close < zone_low:
        return APPROACH_FROM_BELOW
    return APPROACH_INSIDE


def _zones_by_timestamp(zones: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    if zones is None or zones.empty:
        return {}
    work = zones.copy()
    work["timestamp"] = _as_utc_series(work["timestamp"])
    grouped: dict[pd.Timestamp, pd.DataFrame] = {}
    for stamp, group in work.groupby("timestamp", sort=False):
        grouped[_as_utc(stamp)] = group.reset_index(drop=True)
    return grouped


def _lookup_bar(
    stamps: pd.Series,
    frame: pd.DataFrame,
    expected: pd.Timestamp,
) -> pd.Series | None:
    if stamps.empty:
        return None
    index = int(stamps.searchsorted(expected, side="left"))
    if index >= len(stamps) or stamps.iloc[index] != expected:
        return None
    return frame.iloc[index]


def _empty_zone_fields(digest: str) -> dict[str, object]:
    return {
        "zone_params_hash": digest,
        "zone_id": None,
        "zone_low": None,
        "zone_high": None,
        "zone_mid": None,
        "zone_width_ticks": None,
        "zone_level_count": None,
        "zone_level_names": None,
        "entry_zone_relation": ZONE_REL_NONE,
        "entry_offset_ticks": None,
        "approach_side": APPROACH_UNKNOWN,
        "nearest_zone_distance_ticks": None,
    }


def _zone_id(session: date, bar_ts: pd.Timestamp, zone: Mapping[str, object]) -> str:
    return (
        f"{session.isoformat()}:{bar_ts.isoformat()}:"
        f"{float(zone['zone_low']):.10g}:{float(zone['zone_high']):.10g}"
    )


def _session_of(raw: Mapping[str, object], entry_ts: pd.Timestamp) -> date:
    value = raw.get("session_date")
    parsed = _as_date(value)
    if parsed is not None:
        return parsed
    local = entry_ts.tz_convert("America/New_York")
    return trading_session_date(local, eth_start="18:00")


def _coerce_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    needed = {"entry_timestamp", "entry_price"}
    missing = sorted(needed.difference(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["entry_timestamp"] = _as_utc_series(work["entry_timestamp"])
    if work["entry_timestamp"].isna().any():
        raise JournalIngestError("trades frame has missing entry_timestamp")
    work["entry_price"] = pd.to_numeric(work["entry_price"], errors="coerce")
    if (
        work["entry_price"].isna().any()
        or not work["entry_price"].map(_is_finite).all()
        or not (work["entry_price"] > 0).all()
    ):
        raise JournalIngestError("trades frame has non-finite or non-positive entry_price")
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_optional_str)
    if "session_date" in work.columns:
        work["session_date"] = work["session_date"].map(_as_date)
    if "resolution" in work.columns:
        work["resolution"] = work["resolution"].map(_as_optional_str)
    return work


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal zones refuses days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal zones refuses days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _normalize_levels(levels: pd.DataFrame) -> pd.DataFrame:
    if levels is None or not isinstance(levels, pd.DataFrame):
        raise JournalIngestError("levels must be a DataFrame")
    if "timestamp" not in levels.columns:
        raise JournalIngestError("levels frame missing timestamp")
    frame = levels.copy().reset_index(drop=True)
    frame["timestamp"] = _as_utc_series(frame["timestamp"])
    if frame["timestamp"].duplicated().any():
        raise JournalIngestError("levels frame has duplicate timestamps")
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    _assert_1m_grid(frame["timestamp"])
    return frame


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars, pd.DataFrame):
        raise JournalIngestError("bars must be a DataFrame")
    if "timestamp" not in bars.columns:
        raise JournalIngestError("bars frame missing timestamp")
    if "close" not in bars.columns:
        raise JournalIngestError("bars frame missing close")
    frame = bars.copy().reset_index(drop=True)
    frame["timestamp"] = _as_utc_series(frame["timestamp"])
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return frame


def _assert_1m_grid(stamps: pd.Series) -> None:
    if stamps.empty:
        return
    if not stamps.map(lambda value: value == value.floor("min")).all():
        raise JournalIngestError("levels timestamps must be 1-minute bar opens")


def _rows_to_frame(trades: pd.DataFrame, rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    for column in ZONE_OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    ordered = [column for column in trades.columns if column in frame.columns]
    extra = [column for column in ZONE_OUTPUT_COLUMNS if column not in ordered]
    return frame.loc[:, ordered + extra]


def _trades_for_parquet(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    if "session_date" in frame.columns:
        frame["session_date"] = frame["session_date"].map(
            lambda value: value.isoformat() if isinstance(value, date) else value
        )
    return frame


def _relation_counts(trades: pd.DataFrame) -> Counter[str]:
    if "entry_zone_relation" not in trades.columns:
        return Counter()
    return Counter(str(value) for value in trades["entry_zone_relation"] if value is not None)


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


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal zones must not write into results/studies/")
    return resolved


def _as_tolerance(value: object, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or number < 0:
        raise JournalIngestError(f"{name} must be a finite number >= 0")
    return number


def _as_positive_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int | None = None,
) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"{name} must be an integer") from exc
    if number < minimum:
        raise JournalIngestError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise JournalIngestError(f"{name} must be <= {maximum}")
    return number


def _as_positive_tick(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError("tick_size must be a finite number > 0") from exc
    if not math.isfinite(number) or number <= 0:
        raise JournalIngestError("tick_size must be a finite number > 0")
    return number


def _as_utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True)


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp


def _as_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _as_optional_str(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _finite_close(value: object) -> float | None:
    if not _is_finite(value):
        return None
    return float(value)


def _is_finite(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
