"""Deterministic intrabar SL/TP resolution models for R12."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import time
from typing import Literal

import pandas as pd

from thesistester.data.loader import infer_base_interval

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


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, object]) -> None:
    """Append scoped debug evidence while profiling subtimeframe preparation."""
    with open("/opt/cursor/logs/debug.log", "a", encoding="utf-8") as log_file:
        log_file.write(
            json.dumps(
                {
                    "hypothesisId": hypothesis_id,
                    "location": location,
                    "message": message,
                    "data": data,
                    "timestamp": time.time_ns() // 1_000_000,
                }
            )
            + "\n"
        )


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


@dataclass(frozen=True)
class SubtimeframeContext:
    """Validated parent-to-sub-bar mapping."""

    parent_interval: pd.Timedelta
    sub_interval: pd.Timedelta
    groups: dict[int, pd.DataFrame]
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
    for start, end in zip(vertices, vertices[1:]):
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
    for index, (start, end) in enumerate(zip(vertices, vertices[1:])):
        if _between(entry_price, start, end):
            return [entry_price, end, *vertices[index + 2 :]]
    return []


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
        kind: Literal["SL", "TP"] = "SL" if stop_hit else "TP"
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
) -> SubtimeframeContext:
    """Validate strict lower-timeframe coverage and reconcile parent OHLC."""
    started_at = time.perf_counter()
    # region agent log
    _debug_log(
        "A",
        "intrabar.py:249",
        "strict context entry",
        {
            "parent_rows": len(parent),
            "subtimeframe_rows": 0 if subtimeframe is None else len(subtimeframe),
        },
    )
    # endregion agent log
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

    parent_interval = infer_base_interval(parent["timestamp"])
    sub_interval = infer_base_interval(subtimeframe["timestamp"])
    if parent_interval is None or sub_interval is None:
        raise ValueError("parent and subtimeframe data require at least two timestamp intervals")
    if sub_interval <= pd.Timedelta(0) or sub_interval >= parent_interval:
        raise ValueError("subtimeframe interval must be strictly finer than parent interval")
    ratio = parent_interval / sub_interval
    expected_count = int(ratio)
    if ratio != expected_count:
        raise ValueError("parent interval must be an exact multiple of subtimeframe interval")
    # region agent log
    _debug_log(
        "A",
        "intrabar.py:283",
        "strict context intervals validated",
        {
            "parent_interval_ns": int(parent_interval.value),
            "sub_interval_ns": int(sub_interval.value),
            "expected_count": expected_count,
            "validation_elapsed_ms": round((time.perf_counter() - started_at) * 1_000, 3),
        },
    )
    # endregion agent log

    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    groups: dict[int, pd.DataFrame] = {}
    grouping_elapsed = 0.0
    validation_elapsed = 0.0
    for index, start in enumerate(parent_utc):
        grouping_started_at = time.perf_counter()
        end = start + parent_interval
        group_start = sub_utc.searchsorted(start, side="left")
        group_end = sub_utc.searchsorted(end, side="left")
        group = sub_reset.iloc[group_start:group_end].copy()
        grouping_elapsed += time.perf_counter() - grouping_started_at
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
        candidate_validation_started_at = time.perf_counter()
        if not bool(parent_finite.iloc[index]):
            raise ValueError("parent OHLC contains non-finite values")
        if not bool(parent_invariant.iloc[index]):
            raise ValueError("parent OHLC invariants are invalid")
        if not bool(sub_finite.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC contains non-finite values")
        if not bool(sub_invariant.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC invariants are invalid")
        validation_elapsed += time.perf_counter() - candidate_validation_started_at
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
    # region agent log
    _debug_log(
        "B",
        "intrabar.py:347",
        "strict context loop timings",
        {
            "group_count": len(groups),
            "grouping_elapsed_ms": round(grouping_elapsed * 1_000, 3),
            "numeric_validation_elapsed_ms": round(validation_elapsed * 1_000, 3),
        },
    )
    # endregion agent log
    # region agent log
    _debug_log(
        "C",
        "intrabar.py:357",
        "strict context exit",
        {
            "group_count": len(groups),
            "total_elapsed_ms": round((time.perf_counter() - started_at) * 1_000, 3),
        },
    )
    # endregion agent log
    return SubtimeframeContext(parent_interval, sub_interval, groups)


def prepare_subtimeframe_conservative_context(
    parent: pd.DataFrame,
    subtimeframe: pd.DataFrame | None,
    *,
    tick_size: float,
) -> SubtimeframeContext:
    """Prepare replayable groups and retain SL-first fallback reasons.

    Unlike :func:`prepare_subtimeframe_context`, incomplete or misaligned
    lower-bar groups are not replayed. Every replayed group still satisfies the
    exact strict R12 contract; invalid OHLC or an OHLC mismatch remains fatal.
    """
    started_at = time.perf_counter()
    # region agent log
    _debug_log(
        "D",
        "intrabar.py:374",
        "conservative context entry",
        {
            "parent_rows": len(parent),
            "subtimeframe_rows": 0 if subtimeframe is None else len(subtimeframe),
        },
    )
    # endregion agent log
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

    parent_interval = infer_base_interval(parent["timestamp"])
    sub_interval = infer_base_interval(subtimeframe["timestamp"])
    if parent_interval is None or sub_interval is None:
        raise ValueError("parent and subtimeframe data require at least two timestamp intervals")
    if sub_interval <= pd.Timedelta(0) or sub_interval >= parent_interval:
        raise ValueError("subtimeframe interval must be strictly finer than parent interval")
    ratio = parent_interval / sub_interval
    expected_count = int(ratio)
    if ratio != expected_count:
        raise ValueError("parent interval must be an exact multiple of subtimeframe interval")
    # region agent log
    _debug_log(
        "D",
        "intrabar.py:408",
        "conservative context intervals validated",
        {
            "parent_interval_ns": int(parent_interval.value),
            "sub_interval_ns": int(sub_interval.value),
            "expected_count": expected_count,
            "validation_elapsed_ms": round((time.perf_counter() - started_at) * 1_000, 3),
        },
    )
    # endregion agent log

    parent_reset = parent.reset_index(drop=True)
    sub_reset = subtimeframe.reset_index(drop=True)
    parent_utc = pd.to_datetime(parent_reset["timestamp"], utc=True)
    sub_utc = pd.to_datetime(sub_reset["timestamp"], utc=True)
    parent_finite, parent_invariant = _ohlc_validation_masks(parent_reset)
    sub_finite, sub_invariant = _ohlc_validation_masks(sub_reset)
    tolerance = float(tick_size) * 1e-6
    groups: dict[int, pd.DataFrame] = {}
    fallback_reasons: dict[int, str] = {}
    grouping_elapsed = 0.0
    validation_elapsed = 0.0
    for index, start in enumerate(parent_utc):
        grouping_started_at = time.perf_counter()
        end = start + parent_interval
        group_start = sub_utc.searchsorted(start, side="left")
        group_end = sub_utc.searchsorted(end, side="left")
        group = sub_reset.iloc[group_start:group_end].copy()
        grouping_elapsed += time.perf_counter() - grouping_started_at
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
        candidate_validation_started_at = time.perf_counter()
        if not bool(parent_finite.iloc[index]):
            raise ValueError("parent OHLC contains non-finite values")
        if not bool(parent_invariant.iloc[index]):
            raise ValueError("parent OHLC invariants are invalid")
        if not bool(sub_finite.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC contains non-finite values")
        if not bool(sub_invariant.iloc[group_start:group_end].all()):
            raise ValueError("subtimeframe OHLC invariants are invalid")
        validation_elapsed += time.perf_counter() - candidate_validation_started_at
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
    # region agent log
    _debug_log(
        "E",
        "intrabar.py:483",
        "conservative context loop classifications and timings",
        {
            "group_count": len(groups),
            "fallback_count": len(fallback_reasons),
            "grouping_elapsed_ms": round(grouping_elapsed * 1_000, 3),
            "numeric_validation_elapsed_ms": round(validation_elapsed * 1_000, 3),
        },
    )
    # endregion agent log
    # region agent log
    _debug_log(
        "F",
        "intrabar.py:496",
        "conservative context exit",
        {
            "group_count": len(groups),
            "fallback_count": len(fallback_reasons),
            "total_elapsed_ms": round((time.perf_counter() - started_at) * 1_000, 3),
        },
    )
    # endregion agent log
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
