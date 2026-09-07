"""Trigger inference on the previous completed 1m bar and 15s_proxy (JS2).

Calls ``classify_zone_triggers`` via ``_classify_zone_triggers_detail``
(prepare + delegate). Does not call
``simulate_trades``, ``generate_signals``, or ``_check_confirm_3bar``.
Does not compare JS1 ``approach_side`` to fade ``_approach_side``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import math

import pandas as pd

from thesistester.engine.signals import _classify_zone_triggers_detail
from thesistester.journal.schema import (
    JOIN_BAR_SECONDS,
    JOURNAL_STORE_SCHEMA,
    RECON_RECONCILED,
    TRIGGER_NONE,
    TRIGGER_OUTPUT_COLUMNS,
    TRIGGER_RESOLUTION_15S_PROXY,
    TRIGGER_RESOLUTION_1M,
    TRIGGERS_HONESTY,
    JournalIngestError,
    decode_trigger_labels,
    encode_trigger_labels,
)
from thesistester.journal.zones import (
    _as_date,
    _as_optional_str,
    _as_utc,
    _as_utc_series,
    _load_table,
    _trades_for_parquet,
    previous_completed_15s_opens,
    previous_completed_1m_open,
)

_PARENT_DELTA = pd.Timedelta(minutes=1)
_TRIGGERS_PARQUET = "journal_triggers.parquet"
_TRIGGERS_JSON = "triggers.json"
_DIRECTIONAL = frozenset({"reject", "break", "reclaim"})
_IMPLIED = frozenset({"fade", "continuation"})
_TRADE_SIDES = frozenset({"long", "short"})


def infer_journal_triggers(
    zones: pd.DataFrame,
    *,
    bars: pd.DataFrame,
    bars_15s: pd.DataFrame | None = None,
    allow_unreconciled: bool = False,
    trigger_params: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Infer engine trigger labels on the previous completed 1m and 15s bars.

    ``bars``, ``bars_15s``, ``allow_unreconciled``, and ``trigger_params``
    are keyword-only. 1m and ``15s_proxy`` are stamped separately and never
    averaged. Unreconciled days fail closed unless ``allow_unreconciled=True``.
    """
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    work = _coerce_zones(zones)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    frame_1m = _normalize_ohlcv(bars, name="bars", grid="1m")
    frame_15s = (
        None if bars_15s is None else _normalize_ohlcv(bars_15s, name="bars_15s", grid="15s")
    )
    params = None if trigger_params is None else dict(trigger_params)
    if work.empty:
        out = work.copy()
        for column in TRIGGER_OUTPUT_COLUMNS:
            out[column] = pd.Series(dtype="object")
        return out
    rows: list[dict[str, object]] = []
    for raw in work.to_dict(orient="records"):
        rows.append(
            _infer_trade(
                raw,
                frame_1m=frame_1m,
                frame_15s=frame_15s,
                trigger_params=params,
            )
        )
    return _rows_to_frame(work, rows)


def write_trigger_artifacts(
    output_dir: str | Path,
    trades: pd.DataFrame,
    *,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Write ``journal_triggers.parquet`` + ``triggers.json``. Not under ``results/studies/``."""
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / _TRIGGERS_PARQUET
    json_path = out / _TRIGGERS_JSON
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "honesty": TRIGGERS_HONESTY,
        "allow_unreconciled": allow_unreconciled,
        "trade_count": int(len(trades)),
        "n_with_zone": int(_n_with_zone(trades)),
        "trigger_counts_1m": dict(sorted(_label_counts(trades, "inferred_triggers_1m").items())),
        "trigger_counts_15s_proxy": dict(
            sorted(_label_counts(trades, "inferred_triggers_15s").items())
        ),
        "resolution_1m": TRIGGER_RESOLUTION_1M,
        "resolution_15s": TRIGGER_RESOLUTION_15S_PROXY,
        "note": "1m and 15s_proxy are never averaged",
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _trades_for_parquet(trades).to_parquet(parquet_path, index=False)
    return {_TRIGGERS_PARQUET: parquet_path, _TRIGGERS_JSON: json_path}


def trigger_files(
    *,
    zones: str | Path,
    bars: str | Path,
    output_dir: str | Path,
    bars_15s: str | Path | None = None,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Load JS1 zones + OHLCV frames, infer triggers, and write artifacts."""
    inferred = infer_journal_triggers(
        _load_table(zones, name="zones"),
        bars=_load_table(bars, name="bars"),
        bars_15s=None if bars_15s is None else _load_table(bars_15s, name="bars_15s"),
        allow_unreconciled=allow_unreconciled,
    )
    return write_trigger_artifacts(
        output_dir,
        inferred,
        allow_unreconciled=allow_unreconciled,
    )


def _infer_trade(
    raw: Mapping[str, object],
    *,
    frame_1m: pd.DataFrame,
    frame_15s: pd.DataFrame | None,
    trigger_params: dict[str, object] | None,
) -> dict[str, object]:
    row = dict(raw)
    zone_id = _as_optional_str(raw.get("zone_id"))
    entry_ts = _as_utc(raw["entry_timestamp"])
    wanted_1m = previous_completed_1m_open(entry_ts)
    lag = (entry_ts - (wanted_1m + _PARENT_DELTA)).total_seconds()
    labels_1m: tuple[str, ...] = ()
    labels_15s: tuple[str, ...] = ()
    implied: dict[str, str] = {}
    if zone_id is not None:
        direction = str(raw.get("direction") or "")
        if direction not in _TRADE_SIDES:
            raise JournalIngestError(
                "journal triggers requires direction 'long' or 'short' when zone_id is set"
            )
        zone = _zone_from_row(raw)
        hist_1m = frame_1m.loc[frame_1m["timestamp"] <= wanted_1m].reset_index(drop=True)
        idx_1m = _index_of_timestamp(hist_1m, wanted_1m)
        if idx_1m is not None:
            # classify_zone_triggers delegates here; one call returns labels + implied.
            labels_1m, implied = _classify_zone_triggers_detail(
                hist_1m,
                zone,
                idx_1m,
                direction,
                trigger_timeframe="base",
                trigger_params=trigger_params,
            )
        if frame_15s is not None:
            _first, last_15 = previous_completed_15s_opens(entry_ts)
            hist_15 = frame_15s.loc[frame_15s["timestamp"] <= last_15].reset_index(drop=True)
            idx_15 = _index_of_timestamp(hist_15, last_15)
            if idx_15 is not None:
                labels_15s, _implied_15s = _classify_zone_triggers_detail(
                    hist_15,
                    zone,
                    idx_15,
                    direction,
                    trigger_timeframe="base",
                    trigger_params=trigger_params,
                )
    row["inferred_triggers_1m"] = encode_trigger_labels(labels_1m)
    row["inferred_triggers_15s"] = encode_trigger_labels(labels_15s)
    row["trigger_bar_lag_seconds"] = float(lag)
    row["trigger_direction_consistent"] = _direction_consistent(
        labels_1m, implied, str(raw.get("direction") or "")
    )
    row["trigger_resolution_1m"] = TRIGGER_RESOLUTION_1M
    row["trigger_resolution_15s"] = TRIGGER_RESOLUTION_15S_PROXY
    return row


def _direction_consistent(
    labels: tuple[str, ...],
    implied: Mapping[str, str],
    direction: str,
) -> bool | None:
    if not labels or set(labels) <= {"touch"}:
        return None
    if any(name in _DIRECTIONAL for name in labels):
        return True
    matches = [
        implied[name] == direction for name in labels if name in _IMPLIED and name in implied
    ]
    if any(matches):
        return True
    if any(name in _IMPLIED for name in labels):
        return False
    return None


def _zone_from_row(raw: Mapping[str, object]) -> pd.Series:
    low = raw.get("zone_low")
    high = raw.get("zone_high")
    if not _is_finite(low) or not _is_finite(high):
        raise JournalIngestError("zone row is missing finite zone_low/zone_high")
    mid = raw.get("zone_mid")
    if not _is_finite(mid):
        mid = (float(low) + float(high)) / 2.0
    names = raw.get("zone_level_names")
    count = raw.get("zone_level_count")
    return pd.Series(
        {
            "zone_low": float(low),
            "zone_high": float(high),
            "zone_mid": float(mid),
            "level_count": 0 if not _is_finite(count) else int(count),
            "level_names": (
                ""
                if names is None or (isinstance(names, float) and math.isnan(names))
                else str(names)
            ),
        }
    )


def _index_of_timestamp(frame: pd.DataFrame, stamp: pd.Timestamp) -> int | None:
    if frame.empty or "timestamp" not in frame.columns:
        return None
    matches = frame.index[frame["timestamp"] == stamp]
    if len(matches) != 1:
        return None
    return int(matches[0])


def _coerce_zones(zones: pd.DataFrame) -> pd.DataFrame:
    if zones is None or not isinstance(zones, pd.DataFrame):
        raise JournalIngestError("zones must be a DataFrame")
    needed = {"entry_timestamp"}
    missing = sorted(needed.difference(zones.columns))
    if missing:
        raise JournalIngestError("zones frame missing columns: " + ", ".join(missing))
    work = zones.copy()
    work["entry_timestamp"] = _as_utc_series(work["entry_timestamp"])
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_optional_str)
    if "session_date" in work.columns:
        work["session_date"] = work["session_date"].map(_as_date)
    if "resolution" in work.columns:
        work["resolution"] = work["resolution"].map(_as_optional_str)
    if "zone_id" in work.columns:
        work["zone_id"] = work["zone_id"].map(_as_optional_str)
    if "direction" in work.columns:
        work["direction"] = work["direction"].map(_as_optional_str)
    return work


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal triggers refuses days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal triggers refuses days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _normalize_ohlcv(bars: pd.DataFrame, *, name: str, grid: str) -> pd.DataFrame:
    if bars is None or not isinstance(bars, pd.DataFrame):
        raise JournalIngestError(f"{name} must be a DataFrame")
    needed = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(needed.difference(bars.columns))
    if missing:
        raise JournalIngestError(f"{name} frame missing columns: " + ", ".join(missing))
    frame = bars.copy().reset_index(drop=True)
    frame["timestamp"] = _as_utc_series(frame["timestamp"])
    if frame["timestamp"].duplicated().any():
        raise JournalIngestError(f"{name} frame has duplicate timestamps")
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[["open", "high", "low", "close"]].isna().any().any():
        raise JournalIngestError(f"{name} frame has non-finite OHLC")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    if grid == "1m" and not frame["timestamp"].map(lambda value: value == value.floor("min")).all():
        raise JournalIngestError("1m bars timestamps must be 1-minute bar opens")
    if grid == "15s":
        freq = f"{JOIN_BAR_SECONDS}s"
        if not frame["timestamp"].map(lambda value: value == value.floor(freq)).all():
            raise JournalIngestError("15s bars timestamps must be 15-second bar opens")
    return frame


def _rows_to_frame(trades: pd.DataFrame, rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    for column in TRIGGER_OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    ordered = [column for column in trades.columns if column in frame.columns]
    extra = [column for column in TRIGGER_OUTPUT_COLUMNS if column not in ordered]
    return frame.loc[:, ordered + extra]


def _label_counts(trades: pd.DataFrame, column: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    if column not in trades.columns:
        return counts
    filter_zone_id = "zone_id" in trades.columns
    for raw in trades.to_dict(orient="records"):
        if filter_zone_id and _as_optional_str(raw.get("zone_id")) is None:
            continue
        labels = decode_trigger_labels(raw.get(column))
        if not labels:
            counts[TRIGGER_NONE] += 1
            continue
        for label in labels:
            counts[label] += 1
    return counts


def _n_with_zone(trades: pd.DataFrame) -> int:
    if "zone_id" not in trades.columns:
        return 0
    return int(sum(1 for value in trades["zone_id"] if _as_optional_str(value) is not None))


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal triggers must not write into results/studies/")
    return resolved


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
