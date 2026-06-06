"""Research bundle export/import helpers."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd

from thesistester import __version__

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_KIND = "thesistester_research_bundle"
MANIFEST_FILENAME = "manifest.json"

_DATASET_META_KEYS = (
    "dataset_id",
    "instrument",
    "base_interval",
    "source_timezone",
    "exchange_timezone",
)
_LEVELS_META_KEYS = ("levels_settings", "levels_data_fingerprint")
_SIGNALS_META_KEYS = (
    "signal_context",
    "last_signal_setup",
    "signal_settings",
    "signal_settings_hash",
)
_BACKTEST_META_KEYS = ("trade_summary",)
_GRID_META_KEYS = ("best_grid_result",)
_VALIDATION_META_KEYS = ("validation_summary",)
_MANAGED_RESEARCH_KEYS = {
    "data",
    "dataset_id",
    "instrument",
    "base_interval",
    "source_timezone",
    "exchange_timezone",
    "levels",
    "session_levels",
    "levels_settings",
    "levels_data_fingerprint",
    "signals",
    "confluence_zones",
    "naked_flags",
    "signal_context",
    "last_signal_setup",
    "signal_settings",
    "signal_settings_hash",
    "trades",
    "trade_summary",
    "equity_curve",
    "grid_results",
    "best_grid_result",
    "time_bucketed_trades",
    "time_grouped_summary",
    "validation_summary",
}

_KNOWN_FILES = {
    MANIFEST_FILENAME,
    "dataset.parquet",
    "dataset_meta.json",
    "levels.parquet",
    "session_levels.parquet",
    "levels_meta.json",
    "signals.parquet",
    "confluence_zones.parquet",
    "naked_flags.parquet",
    "signals_meta.json",
    "trades.parquet",
    "trade_summary.json",
    "equity_curve.parquet",
    "grid_results.parquet",
    "best_grid_result.json",
    "validation_summary.json",
}

_SECTION_REQUIRED_FILES = {
    "dataset": ("dataset.parquet", "dataset_meta.json"),
    "levels": ("levels.parquet", "session_levels.parquet", "levels_meta.json"),
    "signals": ("signals.parquet", "confluence_zones.parquet", "naked_flags.parquet", "signals_meta.json"),
    "backtest": ("trades.parquet", "trade_summary.json", "equity_curve.parquet"),
    "grid": ("grid_results.parquet", "best_grid_result.json"),
    "validation": ("validation_summary.json",),
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [
            {str(k): _normalize_json_value(v) for k, v in row.items()}
            for row in value.to_dict(orient="records")
        ]

    if isinstance(value, pd.Series):
        return {str(k): _normalize_json_value(v) for k, v in value.to_dict().items()}

    if isinstance(value, pd.Index):
        return [_normalize_json_value(item) for item in value.tolist()]

    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except (AttributeError, ValueError, TypeError):
            pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(k): _normalize_json_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]

    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return None if pd.isna(value) else value

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return str(value)


def _to_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _normalize_json_value(payload),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _is_dataframe(value: Any) -> bool:
    return isinstance(value, pd.DataFrame)


def _manifest_base() -> dict[str, Any]:
    return {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "created_at": _utcnow_iso(),
        "app_version": __version__,
        "included": {
            "dataset": False,
            "levels": False,
            "signals": False,
            "backtest": False,
            "grid": False,
            "validation": False,
        },
        "session_keys": [],
    }


def build_research_bundle(session_state: Mapping[str, Any]) -> bytes:
    """Build a zip bundle for supported research artifacts from session_state."""
    manifest = _manifest_base()
    included_keys: set[str] = set()
    files: dict[str, bytes] = {}

    data = session_state.get("data")
    if _is_dataframe(data):
        files["dataset.parquet"] = _to_parquet_bytes(data)
        files["dataset_meta.json"] = _to_json_bytes({key: session_state.get(key) for key in _DATASET_META_KEYS})
        manifest["included"]["dataset"] = True
        included_keys.update({"data", *_DATASET_META_KEYS})

    levels = session_state.get("levels")
    session_levels = session_state.get("session_levels")
    if _is_dataframe(levels) and _is_dataframe(session_levels):
        files["levels.parquet"] = _to_parquet_bytes(levels)
        files["session_levels.parquet"] = _to_parquet_bytes(session_levels)
        files["levels_meta.json"] = _to_json_bytes({key: session_state.get(key) for key in _LEVELS_META_KEYS})
        manifest["included"]["levels"] = True
        included_keys.update({"levels", "session_levels", *_LEVELS_META_KEYS})

    signals = session_state.get("signals")
    confluence_zones = session_state.get("confluence_zones")
    naked_flags = session_state.get("naked_flags")
    if _is_dataframe(signals) and _is_dataframe(confluence_zones) and _is_dataframe(naked_flags):
        files["signals.parquet"] = _to_parquet_bytes(signals)
        files["confluence_zones.parquet"] = _to_parquet_bytes(confluence_zones)
        files["naked_flags.parquet"] = _to_parquet_bytes(naked_flags)
        files["signals_meta.json"] = _to_json_bytes({key: session_state.get(key) for key in _SIGNALS_META_KEYS})
        manifest["included"]["signals"] = True
        included_keys.update({"signals", "confluence_zones", "naked_flags", *_SIGNALS_META_KEYS})

    trades = session_state.get("trades")
    equity_curve = session_state.get("equity_curve")
    if _is_dataframe(trades) and _is_dataframe(equity_curve):
        files["trades.parquet"] = _to_parquet_bytes(trades)
        files["equity_curve.parquet"] = _to_parquet_bytes(equity_curve)
        files["trade_summary.json"] = _to_json_bytes({key: session_state.get(key) for key in _BACKTEST_META_KEYS})
        manifest["included"]["backtest"] = True
        included_keys.update({"trades", "equity_curve", *_BACKTEST_META_KEYS})

    grid_results = session_state.get("grid_results")
    if _is_dataframe(grid_results):
        files["grid_results.parquet"] = _to_parquet_bytes(grid_results)
        files["best_grid_result.json"] = _to_json_bytes({key: session_state.get(key) for key in _GRID_META_KEYS})
        manifest["included"]["grid"] = True
        included_keys.update({"grid_results", *_GRID_META_KEYS})

    if session_state.get("validation_summary") is not None:
        files["validation_summary.json"] = _to_json_bytes(
            {"validation_summary": session_state.get("validation_summary")}
        )
        manifest["included"]["validation"] = True
        included_keys.update(_VALIDATION_META_KEYS)

    manifest["session_keys"] = sorted(included_keys)
    files[MANIFEST_FILENAME] = _to_json_bytes(manifest)

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            zf.writestr(name, files[name])
    return output.getvalue()


def _read_uploaded_bytes(uploaded_file: Any) -> bytes:
    if isinstance(uploaded_file, bytes):
        return uploaded_file
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()
    if hasattr(uploaded_file, "read"):
        data = uploaded_file.read()
        if not isinstance(data, bytes):
            raise ValueError("Uploaded bundle content must be bytes.")
        return data
    raise ValueError("Unsupported uploaded bundle object.")


def _read_json_from_zip(zf: zipfile.ZipFile, filename: str) -> dict[str, Any]:
    try:
        raw = zf.read(filename)
    except KeyError as exc:
        raise ValueError(f"Bundle is missing required file '{filename}'.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Bundle JSON is invalid for '{filename}'.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Bundle JSON for '{filename}' must be an object.")
    return payload


def _read_parquet_from_zip(zf: zipfile.ZipFile, filename: str) -> pd.DataFrame:
    try:
        raw = zf.read(filename)
    except KeyError as exc:
        raise ValueError(f"Bundle is missing required file '{filename}'.") from exc
    try:
        return pd.read_parquet(io.BytesIO(raw))
    except Exception as exc:  # pragma: no cover - pandas/pyarrow exception types vary
        raise ValueError(f"Bundle parquet is invalid for '{filename}'.") from exc


def load_research_bundle(uploaded_file: Any) -> dict[str, Any]:
    """Load and validate a research bundle zip into an in-memory payload."""
    raw = _read_uploaded_bytes(uploaded_file)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw), mode="r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid research bundle zip file.") from exc

    with zf:
        names = set(zf.namelist())
        if MANIFEST_FILENAME not in names:
            raise ValueError("Bundle is missing manifest.json.")

        manifest = _read_json_from_zip(zf, MANIFEST_FILENAME)
        if manifest.get("kind") != BUNDLE_KIND:
            raise ValueError("Invalid bundle kind in manifest.")
        if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
            raise ValueError("Unsupported bundle schema version.")

        included = manifest.get("included")
        if not isinstance(included, dict):
            raise ValueError("Manifest 'included' must be an object.")

        for section, required_files in _SECTION_REQUIRED_FILES.items():
            if included.get(section):
                for filename in required_files:
                    if filename not in names:
                        raise ValueError(
                            f"Manifest includes '{section}' but bundle is missing '{filename}'."
                        )

        session_values: dict[str, Any] = {}

        if included.get("dataset"):
            session_values["data"] = _read_parquet_from_zip(zf, "dataset.parquet")
            dataset_meta = _read_json_from_zip(zf, "dataset_meta.json")
            for key in _DATASET_META_KEYS:
                if key in dataset_meta:
                    session_values[key] = dataset_meta[key]

        if included.get("levels"):
            session_values["levels"] = _read_parquet_from_zip(zf, "levels.parquet")
            session_values["session_levels"] = _read_parquet_from_zip(zf, "session_levels.parquet")
            levels_meta = _read_json_from_zip(zf, "levels_meta.json")
            for key in _LEVELS_META_KEYS:
                if key in levels_meta:
                    session_values[key] = levels_meta[key]

        if included.get("signals"):
            session_values["signals"] = _read_parquet_from_zip(zf, "signals.parquet")
            session_values["confluence_zones"] = _read_parquet_from_zip(zf, "confluence_zones.parquet")
            session_values["naked_flags"] = _read_parquet_from_zip(zf, "naked_flags.parquet")
            signals_meta = _read_json_from_zip(zf, "signals_meta.json")
            for key in _SIGNALS_META_KEYS:
                if key in signals_meta:
                    session_values[key] = signals_meta[key]

        if included.get("backtest"):
            session_values["trades"] = _read_parquet_from_zip(zf, "trades.parquet")
            session_values["equity_curve"] = _read_parquet_from_zip(zf, "equity_curve.parquet")
            backtest_meta = _read_json_from_zip(zf, "trade_summary.json")
            if "trade_summary" in backtest_meta:
                session_values["trade_summary"] = backtest_meta["trade_summary"]

        if included.get("grid"):
            session_values["grid_results"] = _read_parquet_from_zip(zf, "grid_results.parquet")
            grid_meta = _read_json_from_zip(zf, "best_grid_result.json")
            if "best_grid_result" in grid_meta:
                session_values["best_grid_result"] = grid_meta["best_grid_result"]

        if included.get("validation"):
            validation_meta = _read_json_from_zip(zf, "validation_summary.json")
            if "validation_summary" in validation_meta:
                session_values["validation_summary"] = validation_meta["validation_summary"]

    return {
        "manifest": manifest,
        "session_values": session_values,
        "known_files_in_bundle": sorted(name for name in names if name in _KNOWN_FILES),
    }


def apply_research_bundle_to_session(bundle: Mapping[str, Any], session_state: Any) -> dict[str, Any]:
    """Apply loaded bundle values to Streamlit session state."""
    session_values = bundle.get("session_values")
    if not isinstance(session_values, dict):
        raise ValueError("Bundle payload is missing session values.")

    cleared_keys: list[str] = []
    for key in _MANAGED_RESEARCH_KEYS:
        if key in session_state:
            cleared_keys.append(key)
        session_state.pop(key, None)

    restored_keys: list[str] = []
    for key, value in session_values.items():
        session_state[key] = value
        restored_keys.append(key)

    return {
        "cleared_keys": sorted(cleared_keys),
        "cleared_count": len(cleared_keys),
        "restored_keys": restored_keys,
        "restored_count": len(restored_keys),
    }
