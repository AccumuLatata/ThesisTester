"""Deterministic intrabar SL/TP resolution models for R12."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from typing import Literal

import numpy as np
import pandas as pd

from thesistester.data.loader import infer_base_interval, parse_interval

IntrabarModel = Literal[
    "sl_first",
    "path_open_proximity",
    "subtimeframe",
    "subtimeframe_conservative",
]
VALID_INTRABAR_MODELS = frozenset(
    {"sl_first", "path_open_proximity", "subtimeframe", "subtimeframe_conservative"}
)
_REQUIRED_OHLC = ("timestamp", "open", "high", "low", "close")


@dataclass(frozen=True)
class IntrabarResolution:
    """Resolved bracket event within one parent bar."""

    exit_kind: Literal["SL", "TP"] | None
    resolution: str
    parent_both_hit: bool
    ambiguous: bool = False
    proximity_tie: bool = False
    exit_subbar_timestamp: pd.Timestamp | None = None
    subtimeframe_fallback: bool = False


MEMORY_PATH_ENV = "THESISTESTER_MEMORY_PATH"
MEMORY_PATH_ARRAY = "array"
_SLOT_DIGEST_COLUMNS = ("timestamp", "open", "high", "low", "close")


def memory_path_is_array() -> bool:
    """Return True only when ``THESISTESTER_MEMORY_PATH=array``.

    Unset, empty, or any other value is the flag-off path. Read at the call
    site; do not cache. This is the single reader for the switch.
    """
    return os.environ.get(MEMORY_PATH_ENV) == MEMORY_PATH_ARRAY


class PackedSubtimeframeGroups(Mapping[int, pd.DataFrame]):
    """Lazy parent-index → one-frame mapping over packed OHLC + timestamps.

    ``__getitem__`` / ``.get`` build one frame and do not store it. Columns
    are exactly ``timestamp``, ``open``, ``high``, ``low``, ``close``.
    """

    def __init__(
        self,
        *,
        timestamps: pd.Series,
        ohlc: np.ndarray,
        starts: np.ndarray,
        counts: np.ndarray,
        parent_indexes: np.ndarray,
    ) -> None:
        self._timestamps = timestamps
        self._ts_dtype = timestamps.dtype
        self._ohlc = ohlc
        self._starts = np.asarray(starts, dtype=np.int64)
        self._counts = np.asarray(counts, dtype=np.int32)
        self._parent_indexes = np.asarray(parent_indexes, dtype=np.int64)
        self._by_parent = {
            int(parent_index): position
            for position, parent_index in enumerate(self._parent_indexes)
        }

    def __getitem__(self, parent_index: int) -> pd.DataFrame:
        position = self._by_parent.get(int(parent_index))
        if position is None:
            raise KeyError(parent_index)
        return self._materialize(position)

    def __iter__(self):
        return (int(index) for index in self._parent_indexes)

    def __len__(self) -> int:
        return int(self._parent_indexes.size)

    def __contains__(self, parent_index: object) -> bool:
        try:
            return int(parent_index) in self._by_parent
        except (TypeError, ValueError):
            return False

    def _materialize(self, position: int) -> pd.DataFrame:
        start = int(self._starts[position])
        count = int(self._counts[position])
        index = pd.RangeIndex(count)
        sl = slice(start, start + count)
        return pd.DataFrame(
            {
                "timestamp": pd.Series(
                    self._timestamps.iloc[sl].to_numpy(),
                    dtype=self._ts_dtype,
                    index=index,
                ),
                "open": pd.Series(self._ohlc[sl, 0], dtype="float64", index=index),
                "high": pd.Series(self._ohlc[sl, 1], dtype="float64", index=index),
                "low": pd.Series(self._ohlc[sl, 2], dtype="float64", index=index),
                "close": pd.Series(self._ohlc[sl, 3], dtype="float64", index=index),
            },
            index=index,
        )


@dataclass(frozen=True)
class SubtimeframeContext:
    """Validated parent-to-sub-bar mapping."""

    parent_interval: pd.Timedelta
    sub_interval: pd.Timedelta
    groups: Mapping[int, pd.DataFrame]
    fallback_reasons: dict[int, str] = field(default_factory=dict)

    def fallback_diagnostics(self, parent: pd.DataFrame) -> list[dict[str, object]]:
        """Return serializable reasons for parent bars without replayable sub-bars."""
        return [
            {
                "bar_index": index,
                "timestamp": str(parent["timestamp"].iloc[index]),
                "reason": reason,
            }
            for index, reason in sorted(self.fallback_reasons.items())
        ]


@dataclass(frozen=True)
class SubtimeframeCompatibilityReport:
    """Read-only full-series lower-timeframe compatibility result."""

    parent_interval: pd.Timedelta
    sub_interval: pd.Timedelta
    parent_bar_count: int
    compatible_parent_count: int
    issues: tuple[dict[str, object], ...]

    @property
    def is_strictly_compatible(self) -> bool:
        return not self.issues

    @property
    def conservative_eligible(self) -> bool:
        return all(
            issue["issue_code"] in {"incomplete_coverage", "timestamp_misalignment"}
            for issue in self.issues
        )

    def to_frame(self) -> pd.DataFrame:
        """Return a stable, downloadable issue table."""
        columns = [
            "bar_index",
            "timestamp",
            "issue_code",
            "detail",
            "expected_sub_bars",
            "observed_sub_bars",
            "mismatch_fields",
        ]
        return pd.DataFrame(self.issues, columns=columns)


def validate_intrabar_model(model: str) -> str:
    """Return a supported model or raise a clear configuration error."""
    if model not in VALID_INTRABAR_MODELS:
        raise ValueError(
            f"intrabar_model must be one of {sorted(VALID_INTRABAR_MODELS)!r}, got {model!r}"
        )
    return model


def _hits(
    *,
    low: float,
    high: float,
    stop_price: float,
    target_price: float,
    direction: str,
) -> tuple[bool, bool]:
    if direction == "long":
        return low <= stop_price, high >= target_price
    return high >= stop_price, low <= target_price


def _between(value: float, start: float, end: float) -> bool:
    return min(start, end) <= value <= max(start, end)


def _event_at_price(
    price: float,
    *,
    stop_price: float,
    target_price: float,
    direction: str,
) -> Literal["SL", "TP"] | None:
    if direction == "long":
        if price <= stop_price:
            return "SL"
        if price >= target_price:
            return "TP"
    else:
        if price >= stop_price:
            return "SL"
        if price <= target_price:
            return "TP"
    return None


def _first_event_on_path(
    vertices: list[float],
    *,
    stop_price: float,
    target_price: float,
    direction: str,
) -> Literal["SL", "TP"] | None:
    at_start = _event_at_price(
        vertices[0],
        stop_price=stop_price,
        target_price=target_price,
        direction=direction,
    )
    if at_start is not None:
        return at_start
    for start, end in zip(vertices, vertices[1:], strict=False):
        candidates: list[tuple[float, int, Literal["SL", "TP"]]] = []
        if _between(stop_price, start, end):
            candidates.append((abs(stop_price - start), 0, "SL"))
        if _between(target_price, start, end):
            candidates.append((abs(target_price - start), 1, "TP"))
        if candidates:
            return min(candidates)[2]
    return None


def _path_after_entry(vertices: list[float], entry_price: float | None) -> list[float]:
    if entry_price is None:
        return vertices
    for index, (start, end) in enumerate(zip(vertices, vertices[1:], strict=False)):
        if _between(entry_price, start, end):
            return [entry_price, end, *vertices[index + 2 :]]
    return []


def _sl_first_hits_after_entry(
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    stop_price: float,
    target_price: float,
    direction: str,
    entry_price: float,
) -> tuple[bool, bool]:
    """Range SL/TP hits required on every OHLC path that contains ``entry_price``.

    Reuses ``_path_after_entry``. Does not pick a first event — ``sl_first``
    stays a range rule. A hit that exists only on the pre-entry side of one
    pessimistic path is ignored.
    """
    paths = (
        [open_price, high, low, close],
        [open_price, low, high, close],
    )
    stop_hits: list[bool] = []
    target_hits: list[bool] = []
    for vertices in paths:
        active = _path_after_entry(vertices, entry_price)
        if not active:
            continue
        stop_hit, target_hit = _hits(
            low=min(active),
            high=max(active),
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
        )
        stop_hits.append(stop_hit)
        target_hits.append(target_hit)
    if not stop_hits:
        return False, False
    return all(stop_hits), all(target_hits)


def _ohlc_validation_masks(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return per-row finite and OHLC-invariant validation masks.

    Numeric coercion is intentionally performed once per source frame. Callers
    still evaluate the masks only after a parent group's coverage and timestamp
    alignment have passed, preserving strict and conservative error semantics.
    """
    numeric = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    finite = numeric.map(lambda value: math.isfinite(float(value))).all(axis=1)
    invalid_range = (numeric["high"] < numeric[["open", "close"]].max(axis=1)) | (
        numeric["low"] > numeric[["open", "close"]].min(axis=1)
    )
    invalid_range |= numeric["high"] < numeric["low"]
    return finite, ~invalid_range


def _resolve_bar_intervals(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame,
    *,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> tuple[pd.Timedelta, pd.Timedelta]:
    """Resolve parent/sub bar intervals from overrides or timestamp inference."""
    resolved_parent = parse_interval(parent_interval)
    if resolved_parent is None:
        resolved_parent = infer_base_interval(parent["timestamp"])
    resolved_sub = parse_interval(sub_interval)
    if resolved_sub is None:
        resolved_sub = infer_base_interval(subtimeframe["timestamp"])
    if resolved_parent is None or resolved_sub is None:
        raise ValueError("parent and subtimeframe data require at least two timestamp intervals")
    if resolved_sub <= pd.Timedelta(0) or resolved_sub >= resolved_parent:
        raise ValueError("subtimeframe interval must be strictly finer than parent interval")
    ratio = resolved_parent / resolved_sub
    if ratio != int(ratio):
        raise ValueError("parent interval must be an exact multiple of subtimeframe interval")
    return resolved_parent, resolved_sub


class _ContextSlot:
    """Single process-local cache entry. Active only inside ``execute_study_cell``."""

    __slots__ = ("active", "key", "context")

    def __init__(self) -> None:
        self.active = False
        self.key: str | None = None
        self.context: SubtimeframeContext | None = None


_SLOT = _ContextSlot()


def enter_context_slot() -> None:
    """Activate the one-entry slot. Replaces any previous entry."""
    _SLOT.active = True
    _SLOT.key = None
    _SLOT.context = None


def clear_context_slot() -> None:
    """Deactivate and drop the slot. Safe to call when already empty."""
    _SLOT.active = False
    _SLOT.key = None
    _SLOT.context = None


def context_slot_is_active() -> bool:
    return bool(_SLOT.active)


def _series_order_bytes(series: pd.Series) -> bytes:
    values = series.to_numpy(copy=False)
    if values.dtype == object:
        hasher = hashlib.sha256()
        for item in values:
            hasher.update(repr(item).encode("utf-8"))
            hasher.update(b"\0")
        return hasher.digest()
    return np.ascontiguousarray(values).tobytes()


def _ohlc_order_digest(frame: pd.DataFrame) -> str:
    hasher = hashlib.sha256()
    for column in _SLOT_DIGEST_COLUMNS:
        series = frame[column]
        hasher.update(column.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(series.dtype).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(_series_order_bytes(series))
    return hasher.hexdigest()


def compute_context_slot_key(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame,
    *,
    parent_interval: pd.Timedelta,
    sub_interval: pd.Timedelta,
    tick_size: float,
    model: str,
) -> str:
    """SHA-256 of canonical JSON: order-sensitive OHLC digests + resolved ns + tick + model."""
    payload = {
        "model": model,
        "parent_digest": _ohlc_order_digest(parent),
        "parent_interval_ns": int(parent_interval.value),
        "sub_digest": _ohlc_order_digest(subtimeframe),
        "sub_interval_ns": int(sub_interval.value),
        "tick_size": repr(float(tick_size)),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _slot_lookup(key: str) -> SubtimeframeContext | None:
    if not _SLOT.active:
        return None
    if _SLOT.key == key and _SLOT.context is not None:
        return _SLOT.context
    return None


def _slot_publish(key: str, context: SubtimeframeContext) -> None:
    if not _SLOT.active:
        return
    _SLOT.key = key
    _SLOT.context = context


def _require_prepare_frames(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    model: Literal["subtimeframe", "subtimeframe_conservative"],
) -> pd.DataFrame:
    if subtimeframe is None:
        raise ValueError(f"intrabar_model={model!r} requires subtimeframe_data")
    for label, frame in (("parent", parent), ("subtimeframe", subtimeframe)):
        missing = [column for column in _REQUIRED_OHLC if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} data missing required columns: {missing}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if timestamps.isna().any():
            raise ValueError(f"{label} data contains invalid timestamps")
        if timestamps.duplicated().any():
            raise ValueError(f"{label} data contains duplicate timestamps")
        if not timestamps.is_monotonic_increasing:
            raise ValueError(f"{label} data timestamps must be sorted")
    return subtimeframe


def _pack_sub_ohlc(sub_reset: pd.DataFrame) -> np.ndarray:
    packed = np.empty((len(sub_reset), 4), dtype=np.float64)
    packed[:, 0] = pd.to_numeric(sub_reset["open"], errors="coerce").to_numpy(dtype=np.float64)
    packed[:, 1] = pd.to_numeric(sub_reset["high"], errors="coerce").to_numpy(dtype=np.float64)
    packed[:, 2] = pd.to_numeric(sub_reset["low"], errors="coerce").to_numpy(dtype=np.float64)
    packed[:, 3] = pd.to_numeric(sub_reset["close"], errors="coerce").to_numpy(dtype=np.float64)
    return packed


def _prepare_array_context(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    tick_size: float,
    parent_interval: pd.Timedelta | str | None,
    sub_interval: pd.Timedelta | str | None,
    model: Literal["subtimeframe", "subtimeframe_conservative"],
) -> SubtimeframeContext:
    """Flag-on path: same predicates, packed arrays, optional one-entry slot."""
    subtimeframe = _require_prepare_frames(parent, subtimeframe, model=model)
    resolved_parent, resolved_sub = _resolve_bar_intervals(
        parent,
        subtimeframe,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
    )
    slot_key: str | None = None
    if _SLOT.active:
        slot_key = compute_context_slot_key(
            parent,
            subtimeframe,
            parent_interval=resolved_parent,
            sub_interval=resolved_sub,
            tick_size=tick_size,
            model=model,
        )
        hit = _slot_lookup(slot_key)
        if hit is not None:
            return hit

    expected_count = int(resolved_parent / resolved_sub)
    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    conservative = model == "subtimeframe_conservative"
    starts: list[int] = []
    counts: list[int] = []
    parent_indexes: list[int] = []
    fallback_reasons: dict[int, str] = {}
    for index, start in enumerate(parent_utc):
        end = start + resolved_parent
        group_start = int(sub_utc.searchsorted(start, side="left"))
        group_end = int(sub_utc.searchsorted(end, side="left"))
        group = sub_reset.iloc[group_start:group_end]
        if len(group) != expected_count:
            if conservative:
                fallback_reasons[index] = (
                    f"incomplete coverage: expected {expected_count}, observed {len(group)}"
                )
                continue
            raise ValueError(
                "incomplete subtimeframe coverage for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}: "
                f"expected {expected_count}, observed {len(group)}"
            )
        actual_timestamps = pd.to_datetime(group["timestamp"], utc=True).tolist()
        expected_timestamps = [
            start + offset * resolved_sub for offset in range(expected_count)
        ]
        if actual_timestamps != expected_timestamps:
            if conservative:
                fallback_reasons[index] = "timestamps are not exactly aligned"
                continue
            raise ValueError(
                "subtimeframe timestamps are not exactly aligned for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}"
            )
        if not bool(parent_finite.iloc[index]):
            raise ValueError("parent OHLC contains non-finite values")
        if not bool(parent_invariant.iloc[index]):
            raise ValueError("parent OHLC invariants are invalid")
        if not bool(sub_finite.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC contains non-finite values")
        if not bool(sub_invariant.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC invariants are invalid")
        parent_row = parent_reset.iloc[index]
        comparisons = {
            "open": (float(group["open"].iloc[0]), float(parent_row["open"])),
            "high": (float(group["high"].max()), float(parent_row["high"])),
            "low": (float(group["low"].min()), float(parent_row["low"])),
            "close": (float(group["close"].iloc[-1]), float(parent_row["close"])),
        }
        mismatches = [
            key
            for key, (actual, expected) in comparisons.items()
            if abs(actual - expected) > tolerance
        ]
        if mismatches:
            raise ValueError(
                "subtimeframe OHLC does not reconcile for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}: {mismatches}"
            )
        parent_indexes.append(index)
        starts.append(group_start)
        counts.append(group_end - group_start)

    context = SubtimeframeContext(
        resolved_parent,
        resolved_sub,
        PackedSubtimeframeGroups(
            timestamps=sub_reset["timestamp"].reset_index(drop=True),
            ohlc=_pack_sub_ohlc(sub_reset),
            starts=np.asarray(starts, dtype=np.int64),
            counts=np.asarray(counts, dtype=np.int32),
            parent_indexes=np.asarray(parent_indexes, dtype=np.int64),
        ),
        fallback_reasons=fallback_reasons,
    )
    if slot_key is not None:
        _slot_publish(slot_key, context)
    return context


def inspect_subtimeframe_compatibility(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    tick_size: float,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> SubtimeframeCompatibilityReport:
    """Scan every parent bar without changing R12 execution semantics."""
    if subtimeframe is None:
        raise ValueError("subtimeframe compatibility requires subtimeframe_data")
    for label, frame in (("parent", parent), ("subtimeframe", subtimeframe)):
        missing = [column for column in _REQUIRED_OHLC if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} data missing required columns: {missing}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if timestamps.isna().any():
            raise ValueError(f"{label} data contains invalid timestamps")
        if timestamps.duplicated().any():
            raise ValueError(f"{label} data contains duplicate timestamps")
        if not timestamps.is_monotonic_increasing:
            raise ValueError(f"{label} data timestamps must be sorted")

    parent_interval, sub_interval = _resolve_bar_intervals(
        parent,
        subtimeframe,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
    )
    expected_count = int(parent_interval / sub_interval)

    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    issues: list[dict[str, object]] = []
    for index, start in enumerate(parent_utc):
        end = start + parent_interval
        group_start = sub_utc.searchsorted(start, side="left")
        group_end = sub_utc.searchsorted(end, side="left")
        group = sub_reset.iloc[group_start:group_end]
        issue: dict[str, object] = {
            "bar_index": index,
            "timestamp": str(parent_reset["timestamp"].iloc[index]),
            "expected_sub_bars": expected_count,
            "observed_sub_bars": len(group),
            "mismatch_fields": "",
        }
        if len(group) != expected_count:
            issue.update(
                issue_code="incomplete_coverage",
                detail=f"expected {expected_count}, observed {len(group)}",
            )
        else:
            actual = pd.to_datetime(group["timestamp"], utc=True).tolist()
            expected = [start + offset * sub_interval for offset in range(expected_count)]
            if actual != expected:
                issue.update(
                    issue_code="timestamp_misalignment",
                    detail="lower timestamps are not exactly aligned",
                )
            elif not bool(parent_finite.iloc[index]):
                issue.update(issue_code="parent_nonfinite_ohlc", detail="parent OHLC is non-finite")
            elif not bool(parent_invariant.iloc[index]):
                issue.update(
                    issue_code="parent_invalid_ohlc", detail="parent OHLC invariants are invalid"
                )
            elif not bool(sub_finite.iloc[group_start:group_end].all()):
                issue.update(
                    issue_code="subtimeframe_nonfinite_ohlc",
                    detail="lower OHLC is non-finite",
                )
            elif not bool(sub_invariant.iloc[group_start:group_end].all()):
                issue.update(
                    issue_code="subtimeframe_invalid_ohlc",
                    detail="lower OHLC invariants are invalid",
                )
            else:
                parent_row = parent_reset.iloc[index]
                comparisons = {
                    "open": (float(group["open"].iloc[0]), float(parent_row["open"])),
                    "high": (float(group["high"].max()), float(parent_row["high"])),
                    "low": (float(group["low"].min()), float(parent_row["low"])),
                    "close": (float(group["close"].iloc[-1]), float(parent_row["close"])),
                }
                mismatches = [
                    key
                    for key, (actual_value, expected_value) in comparisons.items()
                    if abs(actual_value - expected_value) > tolerance
                ]
                if mismatches:
                    issue.update(
                        issue_code="ohlc_mismatch",
                        detail="lower aggregate does not reconcile to parent OHLC",
                        mismatch_fields=",".join(mismatches),
                    )
                else:
                    continue
        issues.append(issue)
    return SubtimeframeCompatibilityReport(
        parent_interval,
        sub_interval,
        len(parent_reset),
        len(parent_reset) - len(issues),
        tuple(issues),
    )


def resolve_ohlc_bar(
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    stop_price: float,
    target_price: float,
    direction: str,
    model: str,
    entry_price: float | None = None,
) -> IntrabarResolution:
    """Resolve one parent OHLC bar under SL-first or open-proximity path."""
    validate_intrabar_model(model)
    stop_hit, target_hit = _hits(
        low=low,
        high=high,
        stop_price=stop_price,
        target_price=target_price,
        direction=direction,
    )
    both_hit = stop_hit and target_hit
    if not stop_hit and not target_hit:
        return IntrabarResolution(None, "no_hit", False)
    if model == "sl_first":
        if entry_price is not None:
            # Conservative fallback omits entry_price and stays on the
            # unclipped sl_first return below (still SL-kills).
            clipped_stop, clipped_target = _sl_first_hits_after_entry(
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                stop_price=stop_price,
                target_price=target_price,
                direction=direction,
                entry_price=entry_price,
            )
            if not clipped_stop and not clipped_target:
                return IntrabarResolution(None, "no_hit", both_hit)
            kind: Literal["SL", "TP"] = "SL" if clipped_stop else "TP"
            clipped_both = clipped_stop and clipped_target
            return IntrabarResolution(
                kind,
                "legacy_sl_first" if clipped_both else "single_hit",
                both_hit,
                ambiguous=clipped_both,
            )
        kind = "SL" if stop_hit else "TP"
        return IntrabarResolution(
            kind,
            "legacy_sl_first" if both_hit else "single_hit",
            both_hit,
            ambiguous=both_hit,
        )
    if model != "path_open_proximity":
        raise ValueError("resolve_ohlc_bar does not accept subtimeframe without sub-bars")
    if not both_hit and entry_price is None:
        kind = "SL" if stop_hit else "TP"
        return IntrabarResolution(kind, "intrabar_path_single_hit", False)

    distance_high = abs(high - open_price)
    distance_low = abs(open_price - low)
    if distance_high == distance_low:
        candidate_paths = (
            [open_price, high, low, close],
            [open_price, low, high, close],
        )
        outcomes = {
            _first_event_on_path(
                active_vertices,
                stop_price=stop_price,
                target_price=target_price,
                direction=direction,
            )
            for vertices in candidate_paths
            if (active_vertices := _path_after_entry(vertices, entry_price))
        }
        kind = "SL" if "SL" in outcomes else ("TP" if outcomes == {"TP"} else None)
        return IntrabarResolution(
            kind,
            "intrabar_path_proximity_tie_sl_first",
            both_hit,
            ambiguous=True,
            proximity_tie=True,
        )
    if distance_high < distance_low:
        vertices = [open_price, high, low, close]
        resolution = "intrabar_path_open_high_low_close"
    else:
        vertices = [open_price, low, high, close]
        resolution = "intrabar_path_open_low_high_close"
    active_vertices = _path_after_entry(vertices, entry_price)
    kind = (
        _first_event_on_path(
            active_vertices,
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
        )
        if active_vertices
        else None
    )
    return IntrabarResolution(kind, resolution, both_hit)


def prepare_subtimeframe_context(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    tick_size: float,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> SubtimeframeContext:
    """Validate strict lower-timeframe coverage and reconcile parent OHLC."""
    if memory_path_is_array():
        return _prepare_array_context(
            parent,
            subtimeframe,
            tick_size=tick_size,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            model="subtimeframe",
        )
    if subtimeframe is None:
        raise ValueError("intrabar_model='subtimeframe' requires subtimeframe_data")
    for label, frame in (("parent", parent), ("subtimeframe", subtimeframe)):
        missing = [column for column in _REQUIRED_OHLC if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} data missing required columns: {missing}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if timestamps.isna().any():
            raise ValueError(f"{label} data contains invalid timestamps")
        if timestamps.duplicated().any():
            raise ValueError(f"{label} data contains duplicate timestamps")
        if not timestamps.is_monotonic_increasing:
            raise ValueError(f"{label} data timestamps must be sorted")

    parent_interval, sub_interval = _resolve_bar_intervals(
        parent,
        subtimeframe,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
    )
    expected_count = int(parent_interval / sub_interval)

    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    groups: dict[int, pd.DataFrame] = {}
    for index, start in enumerate(parent_utc):
        end = start + parent_interval
        group_start = sub_utc.searchsorted(start, side="left")
        group_end = sub_utc.searchsorted(end, side="left")
        group = sub_reset.iloc[group_start:group_end].copy()
        if len(group) != expected_count:
            raise ValueError(
                "incomplete subtimeframe coverage for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}: "
                f"expected {expected_count}, observed {len(group)}"
            )
        actual_timestamps = pd.to_datetime(group["timestamp"], utc=True).tolist()
        expected_timestamps = [start + offset * sub_interval for offset in range(expected_count)]
        if actual_timestamps != expected_timestamps:
            raise ValueError(
                "subtimeframe timestamps are not exactly aligned for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}"
            )
        if not bool(parent_finite.iloc[index]):
            raise ValueError("parent OHLC contains non-finite values")
        if not bool(parent_invariant.iloc[index]):
            raise ValueError("parent OHLC invariants are invalid")
        if not bool(sub_finite.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC contains non-finite values")
        if not bool(sub_invariant.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC invariants are invalid")
        parent_row = parent_reset.iloc[index]
        comparisons = {
            "open": (float(group["open"].iloc[0]), float(parent_row["open"])),
            "high": (float(group["high"].max()), float(parent_row["high"])),
            "low": (float(group["low"].min()), float(parent_row["low"])),
            "close": (float(group["close"].iloc[-1]), float(parent_row["close"])),
        }
        mismatches = [
            key
            for key, (actual, expected) in comparisons.items()
            if abs(actual - expected) > tolerance
        ]
        if mismatches:
            raise ValueError(
                "subtimeframe OHLC does not reconcile for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}: {mismatches}"
            )
        groups[index] = group.reset_index(drop=True)
    return SubtimeframeContext(parent_interval, sub_interval, groups)


def prepare_subtimeframe_conservative_context(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    tick_size: float,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
) -> SubtimeframeContext:
    """Prepare replayable groups and retain SL-first fallback reasons.

    Unlike :func:`prepare_subtimeframe_context`, incomplete or misaligned
    lower-bar groups are not replayed. Every replayed group still satisfies the
    exact strict R12 contract; invalid OHLC or an OHLC mismatch remains fatal.

    Optional ``parent_interval`` / ``sub_interval`` overrides (Timedelta or
    compact labels like ``15s`` / ``1min``) are required for sparse 15s-primary
    sources where gap-mode inference would coarsen to the parent interval.
    """
    if memory_path_is_array():
        return _prepare_array_context(
            parent,
            subtimeframe,
            tick_size=tick_size,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            model="subtimeframe_conservative",
        )
    if subtimeframe is None:
        raise ValueError("intrabar_model='subtimeframe_conservative' requires subtimeframe_data")
    for label, frame in (("parent", parent), ("subtimeframe", subtimeframe)):
        missing = [column for column in _REQUIRED_OHLC if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} data missing required columns: {missing}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if timestamps.isna().any():
            raise ValueError(f"{label} data contains invalid timestamps")
        if timestamps.duplicated().any():
            raise ValueError(f"{label} data contains duplicate timestamps")
        if not timestamps.is_monotonic_increasing:
            raise ValueError(f"{label} data timestamps must be sorted")

    parent_interval, sub_interval = _resolve_bar_intervals(
        parent,
        subtimeframe,
        parent_interval=parent_interval,
        sub_interval=sub_interval,
    )
    expected_count = int(parent_interval / sub_interval)

    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    groups: dict[int, pd.DataFrame] = {}
    fallback_reasons: dict[int, str] = {}
    for index, start in enumerate(parent_utc):
        end = start + parent_interval
        group_start = sub_utc.searchsorted(start, side="left")
        group_end = sub_utc.searchsorted(end, side="left")
        group = sub_reset.iloc[group_start:group_end].copy()
        if len(group) != expected_count:
            fallback_reasons[index] = (
                f"incomplete coverage: expected {expected_count}, observed {len(group)}"
            )
            continue
        actual_timestamps = pd.to_datetime(group["timestamp"], utc=True).tolist()
        expected_timestamps = [start + offset * sub_interval for offset in range(expected_count)]
        if actual_timestamps != expected_timestamps:
            fallback_reasons[index] = "timestamps are not exactly aligned"
            continue
        if not bool(parent_finite.iloc[index]):
            raise ValueError("parent OHLC contains non-finite values")
        if not bool(parent_invariant.iloc[index]):
            raise ValueError("parent OHLC invariants are invalid")
        if not bool(sub_finite.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC contains non-finite values")
        if not bool(sub_invariant.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC invariants are invalid")
        parent_row = parent_reset.iloc[index]
        comparisons = {
            "open": (float(group["open"].iloc[0]), float(parent_row["open"])),
            "high": (float(group["high"].max()), float(parent_row["high"])),
            "low": (float(group["low"].min()), float(parent_row["low"])),
            "close": (float(group["close"].iloc[-1]), float(parent_row["close"])),
        }
        mismatches = [
            key
            for key, (actual, expected) in comparisons.items()
            if abs(actual - expected) > tolerance
        ]
        if mismatches:
            raise ValueError(
                "subtimeframe OHLC does not reconcile for parent timestamp "
                f"{parent_reset['timestamp'].iloc[index]}: {mismatches}"
            )
        groups[index] = group.reset_index(drop=True)
    return SubtimeframeContext(
        parent_interval,
        sub_interval,
        groups,
        fallback_reasons=fallback_reasons,
    )


def resolve_subtimeframe_bar(
    sub_bars: pd.DataFrame,
    *,
    stop_price: float,
    target_price: float,
    direction: str,
    parent_low: float,
    parent_high: float,
    entry_price: float | None = None,
) -> IntrabarResolution:
    """Walk observed sub-bars chronologically; residual same-sub-bar ties are SL-first."""
    parent_stop, parent_target = _hits(
        low=parent_low,
        high=parent_high,
        stop_price=stop_price,
        target_price=target_price,
        direction=direction,
    )
    parent_both = parent_stop and parent_target
    active = entry_price is None
    entry_subbar_ambiguous = False
    for _, sub_bar in sub_bars.iterrows():
        low = float(sub_bar["low"])
        high = float(sub_bar["high"])
        activated_this_subbar = False
        if not active:
            active = low <= float(entry_price) <= high
            if not active:
                continue
            activated_this_subbar = True
        stop_hit, target_hit = _hits(
            low=low,
            high=high,
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
        )
        if activated_this_subbar:
            if stop_hit:
                return IntrabarResolution(
                    "SL",
                    "subtimeframe_entry_subbar_pessimistic",
                    parent_both,
                    ambiguous=True,
                    exit_subbar_timestamp=pd.Timestamp(sub_bar["timestamp"]),
                )
            if target_hit:
                entry_subbar_ambiguous = True
                continue
        if stop_hit and target_hit:
            return IntrabarResolution(
                "SL",
                "subtimeframe_residual_sl_first",
                parent_both,
                ambiguous=True,
                exit_subbar_timestamp=pd.Timestamp(sub_bar["timestamp"]),
            )
        if stop_hit or target_hit:
            return IntrabarResolution(
                "SL" if stop_hit else "TP",
                (
                    "subtimeframe_sequence_after_entry_ambiguity"
                    if entry_subbar_ambiguous
                    else "subtimeframe_sequence"
                ),
                parent_both,
                ambiguous=entry_subbar_ambiguous,
                exit_subbar_timestamp=pd.Timestamp(sub_bar["timestamp"]),
            )
    return IntrabarResolution(
        None,
        ("no_hit_after_entry_ambiguity" if entry_subbar_ambiguous else "no_hit_after_entry"),
        parent_both,
        ambiguous=entry_subbar_ambiguous,
    )
