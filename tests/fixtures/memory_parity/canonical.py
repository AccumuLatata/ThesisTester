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
    """Product ``hash_dataframe`` projection with portable datetime/string labels."""
    normalized = canonicalize_frame_datetimes(frame)
    canonical = _product_sort_frame(normalized)
    row_hashes = pd.util.hash_pandas_object(canonical, index=False).to_numpy(dtype="uint64")
    hasher = hashlib.sha256()
    hasher.update(_product_stable_json_bytes(list(canonical.columns)))
    hasher.update(
        _product_stable_json_bytes(
            {column: portable_dtype_label(canonical[column]) for column in canonical.columns}
        )
    )
    hasher.update(row_hashes.tobytes())
    return hasher.hexdigest()


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
    """Product ``canonical_bundle_hash`` walk with portable parquet projection.

    JSON members keep the product normalization (sorted keys, ``created_at``
    stripped). Parquet members use ``portable_hash_dataframe`` so datetime
    unit (and pandas-major ``str`` vs ``object`` labels) cannot move the
    digest when values, tz, and numeric dtypes match.
    """
    from thesistester.research_bundle import (
        MANIFEST_FILENAME,
        _CANONICAL_HASH_EXCLUDED_FILES,
    )

    member_hashes: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as archive:
        for name in sorted(archive.namelist()):
            if name in _CANONICAL_HASH_EXCLUDED_FILES:
                continue
            payload = archive.read(name)
            if name.endswith(".parquet"):
                digest = portable_hash_dataframe(pd.read_parquet(io.BytesIO(payload)))
            elif name.endswith(".json"):
                value = json.loads(payload.decode("utf-8"))
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
                digest = hashlib.sha256(payload).hexdigest()
            member_hashes[name] = digest
    projection = json.dumps(
        member_hashes,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(projection).hexdigest()
