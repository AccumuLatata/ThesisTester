"""Small local filesystem persistence helpers for datasets and computed levels."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from thesistester import __version__

PERSISTENCE_SCHEMA_VERSION = 1
LEVEL_ENGINE_VERSION = 1
STORE_ENV_VAR = "THESISTESTER_STORE_DIR"
DEFAULT_STORE_DIR = ".thesistester_store"


def get_store_root() -> Path:
    """Return the local persistence root directory."""
    raw_path = os.environ.get(STORE_ENV_VAR, DEFAULT_STORE_DIR)
    return Path(raw_path).expanduser().resolve()


def _datasets_root() -> Path:
    return get_store_root() / "datasets"


def _levels_root() -> Path:
    return get_store_root() / "levels"


def _dataset_manifest_path() -> Path:
    return _datasets_root() / "manifest.json"


def _dataset_dir(dataset_id: str) -> Path:
    return _datasets_root() / dataset_id


def _levels_dir(dataset_id: str, settings_hash: str) -> Path:
    return _levels_root() / dataset_id / settings_hash


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_parent(path)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_json_value(value: Any) -> Any:
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except (AttributeError, ValueError, TypeError):
            pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(val) for key, val in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if pd.isna(value):
        return None
    return str(value)


def _stable_json_bytes(payload: Any) -> bytes:
    normalized = _normalize_json_value(payload)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _canonicalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" in out.columns:
        out = out.sort_values("timestamp")
    return out.reset_index(drop=True)


def _hash_dataframe(df: pd.DataFrame) -> str:
    canonical = _canonicalize_dataframe(df)
    row_hashes = pd.util.hash_pandas_object(canonical, index=False).to_numpy(dtype="uint64")
    hasher = hashlib.sha256()
    hasher.update(_stable_json_bytes(list(canonical.columns)))
    hasher.update(_stable_json_bytes({column: str(dtype) for column, dtype in canonical.dtypes.items()}))
    hasher.update(row_hashes.tobytes())
    return hasher.hexdigest()


def _timestamp_to_string(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def compute_dataset_id(
    df: pd.DataFrame,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
) -> str:
    """Return a deterministic identifier for a canonical dataset."""
    hasher = hashlib.sha256()
    hasher.update(_hash_dataframe(df).encode("utf-8"))
    hasher.update(
        _stable_json_bytes(
            {
                "instrument": instrument,
                "base_interval": base_interval,
                "source_timezone": source_timezone,
                "exchange_timezone": exchange_timezone,
            }
        )
    )
    return hasher.hexdigest()


def compute_levels_settings_hash(settings: dict) -> str:
    """Return a deterministic hash for level settings."""
    return hashlib.sha256(_stable_json_bytes(settings)).hexdigest()


def _dataset_metadata(
    df: pd.DataFrame,
    *,
    dataset_id: str,
    name: str,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    canonical = _canonicalize_dataframe(df)
    timestamp_min = None
    timestamp_max = None
    if not canonical.empty and "timestamp" in canonical.columns:
        timestamp_min = _timestamp_to_string(canonical["timestamp"].min())
        timestamp_max = _timestamp_to_string(canonical["timestamp"].max())

    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "kind": "dataset",
        "dataset_id": dataset_id,
        "name": name,
        "instrument": instrument,
        "rows": int(len(canonical)),
        "timestamp_min": timestamp_min,
        "timestamp_max": timestamp_max,
        "columns": [str(column) for column in canonical.columns],
        "base_interval": base_interval,
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        "created_at": created_at or _utcnow_iso(),
        "app_version": __version__,
    }


def _scan_dataset_metadata() -> list[dict[str, Any]]:
    datasets_root = _datasets_root()
    if not datasets_root.exists():
        return []

    items: list[dict[str, Any]] = []
    for meta_path in sorted(datasets_root.glob("*/meta.json")):
        try:
            meta = _read_json(meta_path)
        except (json.JSONDecodeError, OSError):
            continue
        dataset_dir = meta_path.parent
        if not (dataset_dir / "canonical.parquet").exists():
            continue
        meta["path"] = str(dataset_dir)
        items.append(meta)
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def _refresh_dataset_manifest() -> list[dict[str, Any]]:
    items = _scan_dataset_metadata()
    _write_json(
        _dataset_manifest_path(),
        {
            "schema_version": PERSISTENCE_SCHEMA_VERSION,
            "kind": "datasets_manifest",
            "updated_at": _utcnow_iso(),
            "datasets": items,
        },
    )
    return items


def save_dataset(
    df: pd.DataFrame,
    *,
    name: str,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
) -> dict[str, Any]:
    """Persist a canonical dataset and return its metadata."""
    canonical = _canonicalize_dataframe(df)
    dataset_id = compute_dataset_id(
        canonical,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    dataset_dir = _dataset_dir(dataset_id)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    metadata = _dataset_metadata(
        canonical,
        dataset_id=dataset_id,
        name=name,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    canonical.to_parquet(dataset_dir / "canonical.parquet", index=False)
    _write_json(dataset_dir / "meta.json", metadata)
    _refresh_dataset_manifest()
    metadata["path"] = str(dataset_dir)
    return metadata


def list_datasets() -> list[dict[str, Any]]:
    """Return saved dataset metadata sorted newest-first."""
    manifest_path = _dataset_manifest_path()
    if manifest_path.exists():
        try:
            manifest = _read_json(manifest_path)
            datasets = manifest.get("datasets")
            if isinstance(datasets, list):
                return datasets
        except (json.JSONDecodeError, OSError):
            pass
    return _refresh_dataset_manifest()


def load_dataset(dataset_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load a saved dataset and its metadata."""
    dataset_dir = _dataset_dir(dataset_id)
    parquet_path = dataset_dir / "canonical.parquet"
    meta_path = dataset_dir / "meta.json"
    if not parquet_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Saved dataset not found: {dataset_id}")

    metadata = _read_json(meta_path)
    if metadata.get("schema_version") != PERSISTENCE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported dataset schema version: {metadata.get('schema_version')}")

    df = pd.read_parquet(parquet_path)
    metadata["path"] = str(dataset_dir)
    return df, metadata


def delete_dataset(dataset_id: str) -> None:
    """Delete a saved dataset and any saved levels linked to it."""
    dataset_dir = _dataset_dir(dataset_id)
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)

    related_levels_dir = _levels_root() / dataset_id
    if related_levels_dir.exists():
        shutil.rmtree(related_levels_dir)

    _refresh_dataset_manifest()


def save_levels(
    *,
    dataset_id: str,
    levels: pd.DataFrame,
    session_levels: pd.DataFrame,
    levels_settings: dict,
    levels_data_fingerprint: dict,
) -> dict[str, Any]:
    """Persist computed levels for a specific dataset/settings combination."""
    settings_hash = compute_levels_settings_hash(levels_settings)
    levels_dir = _levels_dir(dataset_id, settings_hash)
    levels_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "kind": "levels",
        "engine_version": LEVEL_ENGINE_VERSION,
        "dataset_id": dataset_id,
        "settings_hash": settings_hash,
        "levels_settings": _normalize_json_value(levels_settings),
        "levels_data_fingerprint": _normalize_json_value(levels_data_fingerprint),
        "rows": int(len(levels)),
        "levels_columns": [str(column) for column in levels.columns],
        "session_levels_columns": [str(column) for column in session_levels.columns],
        "created_at": _utcnow_iso(),
        "app_version": __version__,
    }
    _canonicalize_dataframe(levels).to_parquet(levels_dir / "levels.parquet", index=False)
    _canonicalize_dataframe(session_levels).to_parquet(
        levels_dir / "session_levels.parquet",
        index=False,
    )
    _write_json(levels_dir / "meta.json", metadata)
    metadata["path"] = str(levels_dir)
    return metadata


def list_saved_levels(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """Return metadata for saved levels entries."""
    levels_root = _levels_root()
    if dataset_id is not None:
        candidate_dirs = [levels_root / dataset_id]
    else:
        candidate_dirs = [path for path in levels_root.iterdir()] if levels_root.exists() else []

    items: list[dict[str, Any]] = []
    for dataset_dir in candidate_dirs:
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            continue
        for meta_path in sorted(dataset_dir.glob("*/meta.json")):
            try:
                meta = _read_json(meta_path)
            except (json.JSONDecodeError, OSError):
                continue
            levels_dir = meta_path.parent
            if not (levels_dir / "levels.parquet").exists():
                continue
            if not (levels_dir / "session_levels.parquet").exists():
                continue
            meta["path"] = str(levels_dir)
            items.append(meta)
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def find_matching_levels(
    *,
    dataset_id: str,
    levels_settings: dict,
) -> dict[str, Any] | None:
    """Return matching saved-level metadata when schema and engine versions match."""
    settings_hash = compute_levels_settings_hash(levels_settings)
    meta_path = _levels_dir(dataset_id, settings_hash) / "meta.json"
    if not meta_path.exists():
        return None

    metadata = _read_json(meta_path)
    if metadata.get("schema_version") != PERSISTENCE_SCHEMA_VERSION:
        return None
    if metadata.get("engine_version") != LEVEL_ENGINE_VERSION:
        return None
    metadata["path"] = str(meta_path.parent)
    return metadata


def load_levels(dataset_id: str, settings_hash: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load saved levels and metadata."""
    levels_dir = _levels_dir(dataset_id, settings_hash)
    meta_path = levels_dir / "meta.json"
    levels_path = levels_dir / "levels.parquet"
    session_levels_path = levels_dir / "session_levels.parquet"
    if not meta_path.exists() or not levels_path.exists() or not session_levels_path.exists():
        raise FileNotFoundError(
            f"Saved levels not found for dataset_id={dataset_id} settings_hash={settings_hash}"
        )

    metadata = _read_json(meta_path)
    if metadata.get("schema_version") != PERSISTENCE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported levels schema version: {metadata.get('schema_version')}")
    if metadata.get("engine_version") != LEVEL_ENGINE_VERSION:
        raise ValueError(f"Unsupported levels engine version: {metadata.get('engine_version')}")

    levels_df = pd.read_parquet(levels_path)
    session_levels_df = pd.read_parquet(session_levels_path)
    metadata["path"] = str(levels_dir)
    return levels_df, session_levels_df, metadata


def delete_levels(dataset_id: str, settings_hash: str) -> None:
    """Delete saved levels for a dataset/settings combination."""
    levels_dir = _levels_dir(dataset_id, settings_hash)
    if levels_dir.exists():
        shutil.rmtree(levels_dir)

    dataset_dir = levels_dir.parent
    if dataset_dir.exists() and not any(dataset_dir.iterdir()):
        dataset_dir.rmdir()
