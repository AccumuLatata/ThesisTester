"""Shared entry-window policy (Focus + Admit) — engine-safe, no analytics imports.

Lives outside ``thesistester.analytics`` so ``simulate_trades`` can import it
without circular imports through ``analytics.grid``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Canonical RTH segment bounds (C1). Time Analysis and Focus/Admit must share
# these exact minute intervals — do not redefine elsewhere.
RTH_SEGMENTS: tuple[tuple[int, int, str], ...] = (
    (0, 570, "pre_rth"),  # < 09:30
    (570, 600, "rth_open_30m"),  # 09:30 – 09:59
    (600, 690, "rth_morning"),  # 10:00 – 11:29
    (690, 810, "rth_midday"),  # 11:30 – 13:29
    (810, 900, "rth_afternoon"),  # 13:30 – 14:59
    (900, 960, "rth_power_hour"),  # 15:00 – 15:59
    (960, 1440, "post_rth"),  # 16:00+
)
RTH_SEGMENT_LABELS: tuple[str, ...] = tuple(label for _, _, label in RTH_SEGMENTS)

_VALID_MODES = frozenset({"rth_segments", "clock_range"})


def rth_segment_for_minute(minute: int) -> str:
    """Return the RTH segment label for a minute-of-day (0–1439)."""
    value = int(minute)
    for start, end, label in RTH_SEGMENTS:
        if start <= value < end:
            return label
    return "post_rth"


def _parse_clock_to_minutes(
    value: str,
    *,
    field_name: str,
    allow_end_of_day: bool = False,
) -> int:
    text = str(value).strip()
    if allow_end_of_day and text in {"24:00", "24:00:00"}:
        return 1440
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"{field_name} must be HH:MM or HH:MM:SS, got {value!r}.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError as exc:
        raise ValueError(f"{field_name} must be HH:MM or HH:MM:SS, got {value!r}.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"{field_name} is out of range: {value!r}.")
    return hour * 60 + minute


def _minutes_to_hhmm(minute_of_day: int) -> str:
    hour, minute = divmod(int(minute_of_day), 60)
    return f"{hour:02d}:{minute:02d}"


def disabled_entry_window(*, timezone: str | None = None) -> dict[str, Any]:
    """Return a normalized disabled entry-window config (legacy / no filter)."""
    return {
        "enabled": False,
        "mode": "rth_segments",
        "rth_segments": [],
        "start_time": None,
        "end_time": None,
        "timezone": timezone,
    }


def normalize_entry_window(
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
) -> dict[str, Any]:
    """Validate and normalize an entry-window config (C1–C5)."""
    if entry_window is None:
        return disabled_entry_window(timezone=exchange_tz)

    if not isinstance(entry_window, dict):
        raise ValueError("entry_window must be a dict or None.")

    enabled = bool(entry_window.get("enabled", False))
    timezone = entry_window.get("timezone")
    if timezone is None or (isinstance(timezone, str) and not timezone.strip()):
        timezone = exchange_tz
    timezone = str(timezone).strip()

    if not enabled:
        return disabled_entry_window(timezone=timezone)

    mode = str(entry_window.get("mode") or "rth_segments").strip()
    if mode not in _VALID_MODES:
        raise ValueError(f"entry_window.mode must be one of {sorted(_VALID_MODES)}.")

    if mode == "rth_segments":
        raw_segments = entry_window.get("rth_segments") or []
        if not isinstance(raw_segments, (list, tuple)) or not raw_segments:
            raise ValueError(
                "entry_window.rth_segments must be a non-empty list when enabled (C3)."
            )
        segments: list[str] = []
        for label in raw_segments:
            name = str(label).strip()
            if name not in RTH_SEGMENT_LABELS:
                raise ValueError(
                    f"Unknown RTH segment {name!r}. Expected one of {list(RTH_SEGMENT_LABELS)}."
                )
            if name not in segments:
                segments.append(name)
        return {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": segments,
            "start_time": None,
            "end_time": None,
            "timezone": timezone,
        }

    start_raw = entry_window.get("start_time")
    end_raw = entry_window.get("end_time")
    if start_raw is None or end_raw is None:
        raise ValueError(
            "entry_window.start_time and end_time are required when mode='clock_range'."
        )
    start_m = _parse_clock_to_minutes(str(start_raw), field_name="start_time")
    end_m = _parse_clock_to_minutes(str(end_raw), field_name="end_time", allow_end_of_day=True)
    if end_m <= start_m:
        raise ValueError(
            "entry_window clock range must be half-open [start, end) with "
            "end > start (no overnight wrap in v1; C4)."
        )
    return {
        "enabled": True,
        "mode": "clock_range",
        "rth_segments": [],
        "start_time": _minutes_to_hhmm(start_m),
        "end_time": "24:00" if end_m == 1440 else _minutes_to_hhmm(end_m),
        "timezone": timezone,
    }


def entry_window_from_bucket(
    group_col: str,
    value: Any,
    *,
    exchange_tz: str = "America/New_York",
    bucket_tz: str | None = None,
) -> dict[str, Any]:
    """Map a Time Analysis group selection to a normalized entry_window (C5)."""
    col = str(group_col).strip()
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("bucket value must not be empty.")
    label = str(value).strip()
    if not label:
        raise ValueError("bucket value must not be empty.")

    if col == "entry_rth_segment":
        return normalize_entry_window(
            {
                "enabled": True,
                "mode": "rth_segments",
                "rth_segments": [label],
                "timezone": exchange_tz,
            },
            exchange_tz=exchange_tz,
        )

    tz = bucket_tz or exchange_tz
    if col == "entry_hour_bucket":
        start_m = _parse_clock_to_minutes(label, field_name="entry_hour_bucket")
        if start_m % 60 != 0:
            raise ValueError(f"entry_hour_bucket must be on the hour, got {label!r}.")
        end_m = start_m + 60
        if end_m > 1440:
            raise ValueError(f"entry_hour_bucket out of range: {label!r}.")
        return normalize_entry_window(
            {
                "enabled": True,
                "mode": "clock_range",
                "start_time": _minutes_to_hhmm(start_m),
                "end_time": "24:00" if end_m == 1440 else _minutes_to_hhmm(end_m),
                "timezone": tz,
            },
            exchange_tz=exchange_tz,
        )

    if col == "entry_30min_bucket":
        start_m = _parse_clock_to_minutes(label, field_name="entry_30min_bucket")
        if start_m % 30 != 0:
            raise ValueError(f"entry_30min_bucket must align to 00 or 30 minutes, got {label!r}.")
        end_m = start_m + 30
        return normalize_entry_window(
            {
                "enabled": True,
                "mode": "clock_range",
                "start_time": _minutes_to_hhmm(start_m),
                "end_time": "24:00" if end_m == 1440 else _minutes_to_hhmm(end_m),
                "timezone": tz,
            },
            exchange_tz=exchange_tz,
        )

    raise ValueError(
        f"Unsupported Focus bucket column {col!r}. "
        "Use entry_rth_segment, entry_hour_bucket, or entry_30min_bucket."
    )


def _local_timestamp(ts: Any, timezone: str) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize(timezone)
    return stamp.tz_convert(timezone)


def entry_window_contains(
    local_ts: Any,
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
) -> bool:
    """Return whether *local_ts* is inside the normalized window (C2–C5)."""
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    if not window["enabled"]:
        return True

    tz = str(window["timezone"] or exchange_tz)
    stamp = _local_timestamp(local_ts, tz)
    minute = int(stamp.hour) * 60 + int(stamp.minute)

    if window["mode"] == "rth_segments":
        session_stamp = _local_timestamp(local_ts, exchange_tz)
        session_minute = int(session_stamp.hour) * 60 + int(session_stamp.minute)
        return rth_segment_for_minute(session_minute) in set(window["rth_segments"])

    start_m = _parse_clock_to_minutes(str(window["start_time"]), field_name="start_time")
    end_m = _parse_clock_to_minutes(
        str(window["end_time"]), field_name="end_time", allow_end_of_day=True
    )
    return start_m <= minute < end_m


def format_entry_window_label(entry_window: dict[str, Any] | None) -> str:
    """Short human label for UI captions."""
    if not entry_window or not entry_window.get("enabled"):
        return "disabled"
    mode = entry_window.get("mode")
    if mode == "rth_segments":
        segs = entry_window.get("rth_segments") or []
        return "RTH: " + ", ".join(str(s) for s in segs)
    return (
        f"{entry_window.get('start_time')}–{entry_window.get('end_time')} "
        f"({entry_window.get('timezone')})"
    )
