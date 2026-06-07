"""Small local filesystem persistence helpers for datasets, setups, and computed levels."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from thesistester import __version__
from thesistester.setup import normalize_trigger_timeframe

PERSISTENCE_SCHEMA_VERSION = 1
LEVEL_ENGINE_VERSION = 3
SIGNAL_RUN_SCHEMA_VERSION = 1
SETUP_SCHEMA_VERSION = 1
STORE_ENV_VAR = "THESISTESTER_STORE_DIR"
DEFAULT_STORE_DIR_NAME = ".thesistester_store"
SIGNALS_PARQUET_NAME = "signals.parquet"
CONFLUENCE_ZONES_PARQUET_NAME = "confluence_zones.parquet"
NAKED_FLAGS_PARQUET_NAME = "naked_flags.parquet"
_SETUP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_store_root() -> Path:
    """Return the local persistence root directory."""
    raw_path = os.environ.get(STORE_ENV_VAR)
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return (_repo_root() / DEFAULT_STORE_DIR_NAME).resolve()


def _datasets_root() -> Path:
    return get_store_root() / "datasets"


def _levels_root() -> Path:
    return get_store_root() / "levels"


def _signals_root() -> Path:
    return get_store_root() / "signals"


def _setups_root() -> Path:
    return get_store_root() / "setups"


def _dataset_manifest_path() -> Path:
    return _datasets_root() / "manifest.json"


def _ui_state_path() -> Path:
    return get_store_root() / "ui_state.json"


def _dataset_dir(dataset_id: str) -> Path:
    return _datasets_root() / dataset_id


def _levels_dir(dataset_id: str, settings_hash: str) -> Path:
    return _levels_root() / dataset_id / settings_hash


def _signal_run_dir(
    dataset_id: str,
    levels_settings_hash: str,
    signal_settings_hash: str,
) -> Path:
    return _signals_root() / dataset_id / levels_settings_hash / signal_settings_hash


def _setup_dir(setup_id: str) -> Path:
    return _setups_root() / _validate_setup_id(setup_id)


def _validate_setup_id(setup_id: str) -> str:
    if not isinstance(setup_id, str):
        raise ValueError("setup_id must be a non-empty string.")
    normalized = setup_id.strip()
    if not normalized:
        raise ValueError("setup_id must be a non-empty string.")
    if not _SETUP_ID_RE.fullmatch(normalized):
        raise ValueError(f"Invalid setup_id: {setup_id}")
    return normalized


def _signal_run_files_exist(signal_run_dir: Path) -> bool:
    return (
        (signal_run_dir / SIGNALS_PARQUET_NAME).exists()
        and (signal_run_dir / CONFLUENCE_ZONES_PARQUET_NAME).exists()
        and (signal_run_dir / NAKED_FLAGS_PARQUET_NAME).exists()
    )


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


def _load_ui_state() -> dict[str, Any]:
    path = _ui_state_path()
    if not path.exists():
        return {}
    try:
        payload = _read_json(path)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_ui_state(payload: dict[str, Any]) -> None:
    _write_json(_ui_state_path(), payload)


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


def compute_setup_id() -> str:
    """Return a random setup identifier."""
    return uuid4().hex


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _normalize_signal_settings_for_hash(settings: dict) -> dict:
    normalized = dict(settings)
    selected_levels = normalized.get("selected_levels")
    if isinstance(selected_levels, list):
        normalized["selected_levels"] = sorted(str(level) for level in selected_levels)
    rules = normalized.get("confluence_rules")
    if isinstance(rules, list):
        normalized_rules = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            normalized_rules.append(
                {
                    "level": str(rule.get("level", "")),
                    "tolerance_ticks": _safe_float(rule.get("tolerance_ticks", 0.0), default=0.0),
                    "required": bool(rule.get("required", False)),
                }
            )
        normalized["confluence_rules"] = sorted(
            normalized_rules,
            key=lambda item: (item["level"], item["tolerance_ticks"], item["required"]),
        )
    trigger_params = normalized.get("trigger_params")
    if isinstance(trigger_params, dict):
        normalized["trigger_params"] = dict(trigger_params)
    normalized["trigger_timeframe"] = normalize_trigger_timeframe(
        normalized.get("trigger_timeframe")
    )
    setup_snapshot = normalized.get("setup_snapshot")
    if isinstance(setup_snapshot, dict):
        normalized["setup_snapshot"] = dict(setup_snapshot)
    return normalized


def compute_signal_settings_hash(settings: dict) -> str:
    """Return a deterministic hash for signal settings."""
    normalized = _normalize_signal_settings_for_hash(settings)
    return hashlib.sha256(_stable_json_bytes(normalized)).hexdigest()


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


def save_setup(
    setup_config: dict[str, Any],
    *,
    setup_id: str | None = None,
    dataset_id: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    """Persist a setup config and return metadata."""
    if not isinstance(setup_config, dict):
        raise ValueError("setup_config must be a dictionary.")

    raw_setup_id = setup_id if setup_id is not None else setup_config.get("setup_id")
    if raw_setup_id is None:
        resolved_setup_id = compute_setup_id()
    else:
        resolved_setup_id = _validate_setup_id(raw_setup_id)
    setup_dir = _setup_dir(resolved_setup_id)
    setup_dir.mkdir(parents=True, exist_ok=True)
    meta_path = setup_dir / "meta.json"

    existing_created_at: str | None = None
    if meta_path.exists():
        try:
            existing = _read_json(meta_path)
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict):
            existing_created_at = existing.get("created_at")

    resolved_dataset_id = dataset_id
    if resolved_dataset_id is None:
        raw_dataset_id = setup_config.get("dataset_id")
        if isinstance(raw_dataset_id, str) and raw_dataset_id.strip():
            resolved_dataset_id = raw_dataset_id.strip()

    resolved_instrument = instrument or setup_config.get("instrument")
    if resolved_instrument is not None:
        resolved_instrument = str(resolved_instrument)

    created_at = existing_created_at or _utcnow_iso()
    metadata = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "kind": "setup",
        "setup_id": resolved_setup_id,
        "dataset_id": resolved_dataset_id,
        "instrument": resolved_instrument,
        "name": str(setup_config.get("name", "")).strip() or "Untitled setup",
        "description": str(setup_config.get("description", "")).strip(),
        "created_at": created_at,
        "updated_at": _utcnow_iso(),
        "app_version": __version__,
        "setup_config": _normalize_json_value(
            {
                **setup_config,
                "setup_id": resolved_setup_id,
                "dataset_id": resolved_dataset_id,
            }
        ),
    }
    _write_json(meta_path, metadata)
    metadata["path"] = str(setup_dir)
    return metadata


def list_saved_setups(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """Return setup metadata sorted newest-first by updated timestamp."""
    setups_root = _setups_root()
    if not setups_root.exists():
        return []

    items: list[dict[str, Any]] = []
    for meta_path in sorted(setups_root.glob("*/meta.json")):
        try:
            meta = _read_json(meta_path)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(meta, dict):
            continue
        if meta.get("schema_version") != SETUP_SCHEMA_VERSION:
            continue
        if meta.get("kind") != "setup":
            continue
        setup_id = meta.get("setup_id")
        if not isinstance(setup_id, str) or not setup_id:
            continue
        if dataset_id is not None and meta.get("dataset_id") != dataset_id:
            continue
        setup_config = meta.get("setup_config")
        if not isinstance(setup_config, dict):
            continue
        meta["path"] = str(meta_path.parent)
        items.append(meta)

    items.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )
    return items


def load_setup(setup_id: str) -> dict[str, Any]:
    """Load saved setup metadata by id."""
    meta_path = _setup_dir(setup_id) / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Saved setup not found: {setup_id}")

    metadata = _read_json(meta_path)
    if metadata.get("schema_version") != SETUP_SCHEMA_VERSION:
        raise ValueError(f"Unsupported setup schema version: {metadata.get('schema_version')}")
    if metadata.get("kind") != "setup":
        raise ValueError(f"Unsupported persisted artifact kind: {metadata.get('kind')}")
    if not isinstance(metadata.get("setup_config"), dict):
        raise ValueError("Saved setup payload is invalid.")
    metadata["path"] = str(meta_path.parent)
    return metadata


def delete_setup(setup_id: str) -> None:
    """Delete a saved setup."""
    setup_dir = _setup_dir(setup_id)
    if setup_dir.exists():
        shutil.rmtree(setup_dir)


def list_datasets() -> list[dict[str, Any]]:
    """Return saved dataset metadata sorted newest-first."""
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
    """Delete a saved dataset, linked levels, and linked signal runs."""
    dataset_dir = _dataset_dir(dataset_id)
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)

    related_levels_dir = _levels_root() / dataset_id
    if related_levels_dir.exists():
        shutil.rmtree(related_levels_dir)

    related_signals_dir = _signals_root() / dataset_id
    if related_signals_dir.exists():
        shutil.rmtree(related_signals_dir)

    if get_active_dataset_id() == dataset_id:
        clear_active_dataset_id()
    clear_active_levels_hash(dataset_id)
    _refresh_dataset_manifest()


def get_active_dataset_id() -> str | None:
    """Return the persisted active dataset id from UI state."""
    active_dataset_id = _load_ui_state().get("active_dataset_id")
    return active_dataset_id if isinstance(active_dataset_id, str) and active_dataset_id else None


def set_active_dataset_id(dataset_id: str) -> None:
    """Persist the active dataset id in UI state."""
    payload = _load_ui_state()
    payload["active_dataset_id"] = dataset_id
    _write_ui_state(payload)


def clear_active_dataset_id() -> None:
    """Clear the persisted active dataset id in UI state."""
    payload = _load_ui_state()
    payload.pop("active_dataset_id", None)
    _write_ui_state(payload)


def get_active_levels_hash(dataset_id: str) -> str | None:
    """Return persisted active levels hash for a dataset id."""
    payload = _load_ui_state()
    active_levels = payload.get("active_levels_hash_by_dataset")
    if not isinstance(active_levels, dict):
        return None
    settings_hash = active_levels.get(dataset_id)
    return settings_hash if isinstance(settings_hash, str) and settings_hash else None


def set_active_levels_hash(dataset_id: str, settings_hash: str) -> None:
    """Persist active levels hash for a dataset id."""
    payload = _load_ui_state()
    active_levels = payload.get("active_levels_hash_by_dataset")
    if not isinstance(active_levels, dict):
        active_levels = {}
    active_levels[dataset_id] = settings_hash
    payload["active_levels_hash_by_dataset"] = active_levels
    _write_ui_state(payload)


def clear_active_levels_hash(dataset_id: str) -> None:
    """Clear persisted active levels hash for a dataset id."""
    payload = _load_ui_state()
    active_levels = payload.get("active_levels_hash_by_dataset")
    if not isinstance(active_levels, dict):
        return
    active_levels.pop(dataset_id, None)
    payload["active_levels_hash_by_dataset"] = active_levels
    _write_ui_state(payload)


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


def save_signal_run(
    *,
    dataset_id: str,
    levels_settings_hash: str,
    signal_settings: dict,
    signals: pd.DataFrame,
    confluence_zones: pd.DataFrame,
    naked_flags: pd.DataFrame,
    signal_context: dict | None,
    last_signal_setup: dict | None,
) -> dict[str, Any]:
    """Persist generated signals for a dataset/levels/settings combination."""
    signal_settings_hash = compute_signal_settings_hash(signal_settings)
    signal_run_dir = _signal_run_dir(dataset_id, levels_settings_hash, signal_settings_hash)
    signal_run_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "schema_version": SIGNAL_RUN_SCHEMA_VERSION,
        "kind": "signal_run",
        "dataset_id": dataset_id,
        "levels_settings_hash": levels_settings_hash,
        "signal_settings_hash": signal_settings_hash,
        "signal_settings": _normalize_json_value(signal_settings),
        "signal_context": _normalize_json_value(signal_context or {}),
        "last_signal_setup": _normalize_json_value(last_signal_setup or {}),
        "rows": {
            "signals": int(len(signals)),
            "confluence_zones": int(len(confluence_zones)),
            "naked_flags": int(len(naked_flags)),
        },
        "columns": {
            "signals": [str(column) for column in signals.columns],
            "confluence_zones": [str(column) for column in confluence_zones.columns],
            "naked_flags": [str(column) for column in naked_flags.columns],
        },
        "created_at": _utcnow_iso(),
        "app_version": __version__,
    }
    _canonicalize_dataframe(signals).to_parquet(signal_run_dir / SIGNALS_PARQUET_NAME, index=False)
    _canonicalize_dataframe(confluence_zones).to_parquet(
        signal_run_dir / CONFLUENCE_ZONES_PARQUET_NAME,
        index=False,
    )
    _canonicalize_dataframe(naked_flags).to_parquet(
        signal_run_dir / NAKED_FLAGS_PARQUET_NAME,
        index=False,
    )
    _write_json(signal_run_dir / "meta.json", metadata)
    metadata["path"] = str(signal_run_dir)
    return metadata


def list_saved_signal_runs(
    dataset_id: str | None = None,
    levels_settings_hash: str | None = None,
) -> list[dict[str, Any]]:
    """Return metadata for saved signal runs."""
    signals_root = _signals_root()
    if dataset_id is not None:
        dataset_dirs = [signals_root / dataset_id]
    else:
        dataset_dirs = [path for path in signals_root.iterdir()] if signals_root.exists() else []

    items: list[dict[str, Any]] = []
    for dataset_dir in dataset_dirs:
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            continue
        if levels_settings_hash is not None:
            levels_dirs = [dataset_dir / levels_settings_hash]
        else:
            levels_dirs = [path for path in dataset_dir.iterdir() if path.is_dir()]
        for levels_dir in levels_dirs:
            if not levels_dir.exists() or not levels_dir.is_dir():
                continue
            for meta_path in sorted(levels_dir.glob("*/meta.json")):
                try:
                    meta = _read_json(meta_path)
                except (json.JSONDecodeError, OSError):
                    continue
                signal_run_dir = meta_path.parent
                if not _signal_run_files_exist(signal_run_dir):
                    continue
                meta["path"] = str(signal_run_dir)
                items.append(meta)

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def find_matching_signal_run(
    *,
    dataset_id: str,
    levels_settings_hash: str,
    signal_settings: dict,
) -> dict[str, Any] | None:
    """Return saved signal-run metadata with an exact settings hash match."""
    signal_settings_hash = compute_signal_settings_hash(signal_settings)
    meta_path = _signal_run_dir(dataset_id, levels_settings_hash, signal_settings_hash) / "meta.json"
    if not meta_path.exists():
        return None

    try:
        metadata = _read_json(meta_path)
    except (json.JSONDecodeError, OSError):
        return None
    if metadata.get("schema_version") != SIGNAL_RUN_SCHEMA_VERSION:
        return None
    if metadata.get("kind") != "signal_run":
        return None
    metadata["path"] = str(meta_path.parent)
    return metadata


def load_signal_run(
    dataset_id: str,
    levels_settings_hash: str,
    signal_settings_hash: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load a saved signal run and metadata."""
    signal_run_dir = _signal_run_dir(dataset_id, levels_settings_hash, signal_settings_hash)
    meta_path = signal_run_dir / "meta.json"
    signals_path = signal_run_dir / SIGNALS_PARQUET_NAME
    confluence_path = signal_run_dir / CONFLUENCE_ZONES_PARQUET_NAME
    naked_path = signal_run_dir / NAKED_FLAGS_PARQUET_NAME
    if not meta_path.exists() or not _signal_run_files_exist(signal_run_dir):
        raise FileNotFoundError(
            "Saved signal run not found for "
            f"dataset_id={dataset_id} levels_settings_hash={levels_settings_hash} "
            f"signal_settings_hash={signal_settings_hash}"
        )

    metadata = _read_json(meta_path)
    if metadata.get("schema_version") != SIGNAL_RUN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported signal-run schema version: {metadata.get('schema_version')}")
    if metadata.get("kind") != "signal_run":
        raise ValueError(f"Unsupported persisted artifact kind: {metadata.get('kind')}")

    signals_df = pd.read_parquet(signals_path)
    confluence_df = pd.read_parquet(confluence_path)
    naked_df = pd.read_parquet(naked_path)
    metadata["path"] = str(signal_run_dir)
    return signals_df, confluence_df, naked_df, metadata


def delete_signal_run(dataset_id: str, levels_settings_hash: str, signal_settings_hash: str) -> None:
    """Delete a saved signal run."""
    signal_run_dir = _signal_run_dir(dataset_id, levels_settings_hash, signal_settings_hash)
    if signal_run_dir.exists():
        shutil.rmtree(signal_run_dir)

    levels_dir = signal_run_dir.parent
    if levels_dir.exists() and not any(levels_dir.iterdir()):
        levels_dir.rmdir()

    dataset_dir = levels_dir.parent
    if dataset_dir.exists() and not any(dataset_dir.iterdir()):
        dataset_dir.rmdir()
