"""Deterministic on-disk capture layout for one MW0 cell."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .bits import (
    DA5_KEYS,
    LEDGER_EQUALITY_KEYS,
    SUMMARY_METRIC_KEYS,
    encode_optional_float,
    replica_hex_list,
)
from .canonical import canonicalize_frame_datetimes

TRADES_NAME = "trades.parquet"
REPLICA_NAME = "replica_expectancies.json"
SUMMARY_NAME = "summary.json"
DA5_NAME = "da5.json"
LEDGER_NAME = "ledger.json"
HASH_NAME = "canonical_bundle_hash.txt"
META_NAME = "meta.json"
DTYPES_NAME = "trades_dtypes.json"


def cell_dir(root: Path, cell_id: str) -> Path:
    return Path(root) / "cells" / cell_id


def _dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def describe_series_dtype(series: pd.Series) -> dict[str, Any]:
    dtype = series.dtype
    payload: dict[str, Any] = {
        "name": str(dtype),
        "kind": str(getattr(dtype, "kind", type(dtype).__name__)),
    }
    if isinstance(dtype, pd.DatetimeTZDtype):
        unit = getattr(dtype, "unit", None)
        payload.update(
            {
                "family": "datetime-tz",
                "unit": str(unit) if unit is not None else None,
                "tz": str(dtype.tz),
            }
        )
        return payload
    if pd.api.types.is_datetime64_dtype(dtype):
        payload.update(
            {
                "family": "datetime-naive",
                "unit": str(getattr(dtype, "unit", None) or str(dtype)),
                "tz": None,
            }
        )
        return payload
    if pd.api.types.is_float_dtype(dtype):
        payload["family"] = "float"
        return payload
    if pd.api.types.is_integer_dtype(dtype):
        payload["family"] = "integer"
        return payload
    if pd.api.types.is_bool_dtype(dtype):
        payload["family"] = "boolean"
        return payload
    payload["family"] = "other"
    return payload


def write_trades(path: Path, trades: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trades = canonicalize_frame_datetimes(trades)
    trades.to_parquet(path, index=False)
    _dump_json(
        path.with_name(DTYPES_NAME),
        {
            "columns": list(trades.columns),
            "dtypes": {column: describe_series_dtype(trades[column]) for column in trades.columns},
            "row_count": int(len(trades)),
        },
    )


def read_trades(path: Path) -> pd.DataFrame:
    return canonicalize_frame_datetimes(pd.read_parquet(path))


def write_capture(
    dest: Path,
    *,
    cell_id: str,
    trades: pd.DataFrame,
    replica_expectancies: list[Any],
    summary: Mapping[str, Any],
    da5: Mapping[str, Any],
    ledger: Mapping[str, Any],
    canonical_hash: str,
    meta: Mapping[str, Any],
) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    write_trades(dest / TRADES_NAME, trades)
    _dump_json(
        dest / REPLICA_NAME,
        {
            "count": len(replica_expectancies),
            "dtype": "float64",
            "hex_bits": replica_hex_list(replica_expectancies),
        },
    )
    summary_payload = {key: encode_optional_float(summary.get(key)) for key in SUMMARY_METRIC_KEYS}
    if "trade_count" in summary:
        count = summary["trade_count"]
        summary_payload["trade_count"] = None if count is None else int(count)
    _dump_json(dest / SUMMARY_NAME, summary_payload)
    _dump_json(dest / DA5_NAME, {key: encode_optional_float(da5.get(key)) for key in DA5_KEYS})
    stored_ledger = {
        key: ledger.get(key) for key in (*LEDGER_EQUALITY_KEYS, "started_at", "finished_at")
    }
    _dump_json(dest / LEDGER_NAME, stored_ledger)
    (dest / HASH_NAME).write_text(str(canonical_hash).strip() + "\n", encoding="utf-8")
    _dump_json(dest / META_NAME, {"cell_id": cell_id, **dict(meta)})
    return dest


def load_capture(dest: Path) -> dict[str, Any]:
    dest = Path(dest)
    trades = read_trades(dest / TRADES_NAME)
    replica = _load_json(dest / REPLICA_NAME)
    summary = _load_json(dest / SUMMARY_NAME)
    da5 = _load_json(dest / DA5_NAME)
    ledger = _load_json(dest / LEDGER_NAME)
    canonical = (dest / HASH_NAME).read_text(encoding="utf-8").strip()
    meta = _load_json(dest / META_NAME) if (dest / META_NAME).is_file() else {}
    dtypes = _load_json(dest / DTYPES_NAME) if (dest / DTYPES_NAME).is_file() else {}
    return {
        "dir": dest,
        "cell_id": meta.get("cell_id") or dest.name,
        "trades": trades,
        "replica": replica,
        "summary": summary,
        "da5": da5,
        "ledger": ledger,
        "canonical_bundle_hash": canonical,
        "meta": meta,
        "dtypes": dtypes,
    }


def list_cell_ids(root: Path) -> list[str]:
    cells = Path(root) / "cells"
    if not cells.is_dir():
        return []
    return sorted(path.name for path in cells.iterdir() if path.is_dir())
