"""Portable datetime-unit canonicalization for MW0 capture/compare.

Pandas 2 (CI py3.10) emits ``datetime64[ns, tz]``; pandas 3 (py3.11/3.12)
emits ``datetime64[us, tz]``. Product ``hash_dataframe`` includes
``str(dtype)``, so the raw ``canonical_bundle_hash`` is not stable across
the CI matrix even when instants, tz, and numeric bits match.

This module is tooling-only. It does not loosen equality: instants must
survive unit conversion or capture/compare abort. Numeric dtypes, tz, and
float64 bits stay bit-identical. Farm same-commit MW equality still
compares every gated field; the stored digest is the product zip walk
after parquet datetime units are normalized to nanoseconds.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

import numpy as np
import pandas as pd

CANONICAL_DATETIME_UNIT = "ns"


class CanonicalizeError(ValueError):
    """Datetime-unit conversion is not invertible; stop and report."""


def _tz_label(dtype: Any) -> str | None:
    if isinstance(dtype, pd.DatetimeTZDtype):
        return str(dtype.tz)
    return None


def _utc_ns_int64(series: pd.Series) -> np.ndarray:
    """UTC epoch integers in nanoseconds.

    ``DatetimeIndex.asi8`` is unit-native (us series yield microseconds).
    Always project through ``datetime64[ns, UTC]`` before reading ``asi8``.
    """
    utc = pd.to_datetime(series, utc=True)
    as_ns = utc.astype(pd.DatetimeTZDtype(unit="ns", tz="UTC"))
    return pd.DatetimeIndex(as_ns).asi8


def _is_datetime_series(series: pd.Series) -> bool:
    dtype = series.dtype
    return isinstance(dtype, pd.DatetimeTZDtype) or bool(pd.api.types.is_datetime64_dtype(dtype))


def _target_datetime_dtype(series: pd.Series, *, unit: str) -> Any:
    dtype = series.dtype
    if isinstance(dtype, pd.DatetimeTZDtype):
        return pd.DatetimeTZDtype(unit=unit, tz=dtype.tz)
    return np.dtype(f"datetime64[{unit}]")


def canonicalize_datetime_series(
    series: pd.Series,
    *,
    unit: str = CANONICAL_DATETIME_UNIT,
    column: str | None = None,
) -> pd.Series:
    """Convert a datetime series to ``unit`` without changing instants or tz.

    Raises ``CanonicalizeError`` if the conversion drops timezone or if any
    finite instant is not representable in the target unit (and back).
    """
    if not _is_datetime_series(series):
        return series
    target = _target_datetime_dtype(series, unit=unit)
    try:
        converted = series.astype(target)
    except (TypeError, ValueError) as exc:
        where = f" column={column!r}" if column else ""
        raise CanonicalizeError(f"cannot astype datetime{where} to {target}: {exc}") from exc
    if _tz_label(series.dtype) != _tz_label(converted.dtype):
        where = f" column={column!r}" if column else ""
        raise CanonicalizeError(
            f"datetime canonicalize{where} dropped tz "
            f"{_tz_label(series.dtype)!r} -> {_tz_label(converted.dtype)!r}"
        )
    left_ns = _utc_ns_int64(series)
    right_ns = _utc_ns_int64(converted)
    if not np.array_equal(left_ns, right_ns):
        where = f" column={column!r}" if column else ""
        raise CanonicalizeError(
            f"datetime canonicalize{where} is not invertible to unit={unit!r}; "
            "stop and report — do not loosen the compare"
        )
    original_unit = getattr(series.dtype, "unit", None)
    if original_unit and original_unit != unit:
        try:
            back = converted.astype(_target_datetime_dtype(series, unit=str(original_unit)))
        except (TypeError, ValueError) as exc:
            where = f" column={column!r}" if column else ""
            raise CanonicalizeError(
                f"datetime canonicalize{where} failed inverse astype: {exc}"
            ) from exc
        if not np.array_equal(left_ns, _utc_ns_int64(back)):
            where = f" column={column!r}" if column else ""
            raise CanonicalizeError(
                f"datetime canonicalize{where} lost precision converting "
                f"{original_unit} -> {unit} -> {original_unit}"
            )
    return converted


def canonicalize_frame_datetimes(
    frame: pd.DataFrame,
    *,
    unit: str = CANONICAL_DATETIME_UNIT,
) -> pd.DataFrame:
    """Return a copy with every datetime column normalized to ``unit``."""
    out = frame.copy()
    for column in out.columns:
        if _is_datetime_series(out[column]):
            out[column] = canonicalize_datetime_series(out[column], unit=unit, column=str(column))
    return out


def _is_string_family(series: pd.Series) -> bool:
    if pd.api.types.is_string_dtype(series.dtype) and not pd.api.types.is_object_dtype(
        series.dtype
    ):
        return True
    if not (pd.api.types.is_object_dtype(series.dtype) or str(series.dtype) == "str"):
        return False
    non_null = [value for value in series.tolist() if value is not None and not pd.isna(value)]
    if not non_null:
        return False
    return all(isinstance(value, str) for value in non_null)


def portable_dtype_label(series: pd.Series) -> str:
    """Dtype label that is stable across pandas 2/3 datetime units and str/object."""
    if _is_datetime_series(series):
        normalized = canonicalize_datetime_series(series)
        tz = _tz_label(normalized.dtype)
        if tz is not None:
            return f"datetime64[{CANONICAL_DATETIME_UNIT}, {tz}]"
        return f"datetime64[{CANONICAL_DATETIME_UNIT}]"
    if _is_string_family(series):
        return "string"
    return str(series.dtype)


def _product_sort_frame(frame: pd.DataFrame) -> pd.DataFrame:
    from thesistester.persistence import local_store

    sorter = getattr(local_store, "_canonicalize_dataframe", None)
    if sorter is not None:
        return sorter(frame)
    out = frame.copy()
    if "timestamp" in out.columns:
        out = out.sort_values("timestamp")
    return out.reset_index(drop=True)


def _product_stable_json_bytes(payload: Any) -> bytes:
    from thesistester.persistence.local_store import _stable_json_bytes

    return _stable_json_bytes(payload)


def portable_hash_dataframe(frame: pd.DataFrame) -> str:
    """Product ``hash_dataframe`` projection with portable datetime/string labels.

    Zero-row frames hash column names only. Empty parquet reloads as typed
    columns on pandas 2 and all-object on pandas 3; those ghost dtypes are
    not values.
    """
    hasher = hashlib.sha256()
    hasher.update(_product_stable_json_bytes(list(frame.columns)))
    hasher.update(f"rows={len(frame)}".encode("utf-8"))
    if len(frame) == 0:
        return hasher.hexdigest()
    normalized = canonicalize_frame_datetimes(frame)
    canonical = _product_sort_frame(normalized)
    hasher.update(
        _product_stable_json_bytes(
            {column: portable_dtype_label(canonical[column]) for column in canonical.columns}
        )
    )
    row_hashes = pd.util.hash_pandas_object(canonical, index=False).to_numpy(dtype="uint64")
    hasher.update(row_hashes.tobytes())
    return hasher.hexdigest()


def _rewrite_identity_hashes(
    value: Any,
    *,
    data_content_hash: str | None,
    dataset_id: str | None,
    source_content_hash: str | None,
) -> Any:
    """Replace product ``hash_dataframe`` identity strings with portable digests.

    ``research_identity.json`` / ``dataset_meta.json`` / subtimeframe provenance
    embed ``hash_dataframe`` / ``hash_source_frame`` (both include
    ``str(dtype)``). Those strings move across the CI pandas-major axis even
    when parquet values, tz, and numeric bits match. The parquet members stay
    in the walk; the replacement keeps the JSON fields as a real gate on the
    same frames.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key == "data_content_hash" and data_content_hash is not None:
                out[key] = data_content_hash
            elif key == "dataset_id" and dataset_id is not None:
                out[key] = dataset_id
            elif key == "source_content_hash" and source_content_hash is not None:
                out[key] = source_content_hash
            else:
                out[key] = _rewrite_identity_hashes(
                    item,
                    data_content_hash=data_content_hash,
                    dataset_id=dataset_id,
                    source_content_hash=source_content_hash,
                )
        return out
    if isinstance(value, list):
        return [
            _rewrite_identity_hashes(
                item,
                data_content_hash=data_content_hash,
                dataset_id=dataset_id,
                source_content_hash=source_content_hash,
            )
            for item in value
        ]
    return value


def portable_dataset_id(
    dataset: pd.DataFrame,
    *,
    instrument: Any,
    base_interval: Any,
    source_timezone: Any,
    exchange_timezone: Any,
) -> str:
    """``compute_dataset_id`` using ``portable_hash_dataframe``."""
    hasher = hashlib.sha256()
    hasher.update(portable_hash_dataframe(dataset).encode("utf-8"))
    hasher.update(
        _product_stable_json_bytes(
            {
                "instrument": instrument,
                "base_interval": base_interval,
                "source_timezone": source_timezone,
                "exchange_timezone": exchange_timezone,
            }
        )
    )
    return hasher.hexdigest()


def _identity_meta_from_members(json_members: dict[str, Any]) -> dict[str, Any]:
    for name in ("dataset_meta.json", "research_identity.json"):
        payload = json_members.get(name)
        if not isinstance(payload, dict):
            continue
        if name == "research_identity.json":
            nested = payload.get("data_identity")
            if isinstance(nested, dict):
                payload = nested
        meta = {
            key: payload.get(key)
            for key in ("instrument", "base_interval", "source_timezone", "exchange_timezone")
        }
        if any(value is not None for value in meta.values()):
            return meta
    return {}


def _manifest_projection(value: dict[str, Any]) -> dict[str, Any]:
    from thesistester.research_bundle import (
        _CONFLUENCE_COMBO_FRAME_KEYS,
        _CONFLUENCE_COMBO_SUMMARY_KEY,
    )

    projected = dict(value)
    projected.pop("created_at", None)
    included = projected.get("included")
    if isinstance(included, dict) and "confluence_combo" in included:
        included = dict(included)
        included.pop("confluence_combo", None)
        projected["included"] = included
    session_keys = projected.get("session_keys")
    if isinstance(session_keys, list):
        projected["session_keys"] = sorted(
            key
            for key in session_keys
            if key != _CONFLUENCE_COMBO_SUMMARY_KEY and key not in _CONFLUENCE_COMBO_FRAME_KEYS
        )
    return projected


def portable_canonical_bundle_hash(bundle_bytes: bytes) -> str:
    """Product ``canonical_bundle_hash`` walk with portable parquet + identity JSON.

    JSON members keep the product normalization (sorted keys, ``created_at``
    stripped). Parquet members use ``portable_hash_dataframe``. Identity
    strings that the product derived from ``hash_dataframe`` are rewritten
    from those portable parquet digests so the CI pandas-major axis cannot
    move the gated hash when values match.
    """
    from thesistester.research_bundle import (
        MANIFEST_FILENAME,
        _CANONICAL_HASH_EXCLUDED_FILES,
    )

    parquet_frames: dict[str, pd.DataFrame] = {}
    json_members: dict[str, Any] = {}
    other_payloads: dict[str, bytes] = {}
    names: list[str] = []
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as archive:
        for name in sorted(archive.namelist()):
            if name in _CANONICAL_HASH_EXCLUDED_FILES:
                continue
            names.append(name)
            payload = archive.read(name)
            if name.endswith(".parquet"):
                parquet_frames[name] = pd.read_parquet(io.BytesIO(payload))
            elif name.endswith(".json"):
                json_members[name] = json.loads(payload.decode("utf-8"))
            else:
                other_payloads[name] = payload

    dataset = parquet_frames.get("dataset.parquet")
    source = parquet_frames.get("subtimeframe_data.parquet")
    meta = _identity_meta_from_members(json_members)
    portable_data_hash = portable_hash_dataframe(dataset) if dataset is not None else None
    portable_source_hash = portable_hash_dataframe(source) if source is not None else None
    portable_id = None
    if dataset is not None:
        portable_id = portable_dataset_id(
            dataset,
            instrument=meta.get("instrument"),
            base_interval=meta.get("base_interval"),
            source_timezone=meta.get("source_timezone"),
            exchange_timezone=meta.get("exchange_timezone"),
        )

    member_hashes: dict[str, str] = {}
    for name in names:
        if name in parquet_frames:
            digest = portable_hash_dataframe(parquet_frames[name])
        elif name in json_members:
            value = _rewrite_identity_hashes(
                json_members[name],
                data_content_hash=portable_data_hash,
                dataset_id=portable_id,
                source_content_hash=portable_source_hash,
            )
            if name == MANIFEST_FILENAME and isinstance(value, dict):
                value = _manifest_projection(value)
            normalized = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            digest = hashlib.sha256(normalized).hexdigest()
        else:
            digest = hashlib.sha256(other_payloads[name]).hexdigest()
        member_hashes[name] = digest
    projection = json.dumps(
        member_hashes,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(projection).hexdigest()
