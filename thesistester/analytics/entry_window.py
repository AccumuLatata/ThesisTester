"""Shared entry-window config + post-hoc Focus helpers (SW1).

Pure functions only — no Streamlit, no ``simulate_trades``. Engine admission
(SW2) must reuse :func:`normalize_entry_window` and
:func:`entry_window_contains` so Focus and Admit share C1–C5 semantics.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics.metrics import (
    equity_curve,
    summarize_trades,
    summarize_trades_by_direction,
)
from thesistester.analytics.time_analysis import (
    RTH_SEGMENT_LABELS,
    RTH_SEGMENTS,
    add_time_buckets,
    rth_segment_for_minute,
)

FOCUS_HONESTY_BANNER = (
    "Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."
)
FOCUS_EQUITY_CAVEAT = (
    "Equity/drawdown rebuilt from the filtered trade subset only (subset replay)."
)

_VALID_MODES = frozenset({"rth_segments", "clock_range"})


def _parse_clock_to_minutes(
    value: str,
    *,
    field_name: str,
    allow_end_of_day: bool = False,
) -> int:
    text = str(value).strip()
    # Sentinel for exclusive end at midnight next day (hour bucket 23:00).
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
    """Validate and normalize an entry-window config (C1–C5).

    Missing / ``None`` / ``enabled=False`` → disabled legacy config.
    """
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
                "entry_window.rth_segments must be a non-empty list when enabled "
                "(C3)."
            )
        segments: list[str] = []
        for label in raw_segments:
            name = str(label).strip()
            if name not in RTH_SEGMENT_LABELS:
                raise ValueError(
                    f"Unknown RTH segment {name!r}. "
                    f"Expected one of {list(RTH_SEGMENT_LABELS)}."
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
            "entry_window.start_time and end_time are required when "
            "mode='clock_range'."
        )
    start_m = _parse_clock_to_minutes(str(start_raw), field_name="start_time")
    end_m = _parse_clock_to_minutes(
        str(end_raw), field_name="end_time", allow_end_of_day=True
    )
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
            raise ValueError(
                f"entry_30min_bucket must align to 00 or 30 minutes, got {label!r}."
            )
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
        # RTH segments always use exchange/session TZ (C5), even if config
        # timezone was set for labeling — re-localize via exchange_tz.
        session_stamp = _local_timestamp(local_ts, exchange_tz)
        session_minute = int(session_stamp.hour) * 60 + int(session_stamp.minute)
        return rth_segment_for_minute(session_minute) in set(window["rth_segments"])

    start_m = _parse_clock_to_minutes(str(window["start_time"]), field_name="start_time")
    end_m = _parse_clock_to_minutes(
        str(window["end_time"]), field_name="end_time", allow_end_of_day=True
    )
    return start_m <= minute < end_m


def filter_trades_by_entry_window(
    trades: pd.DataFrame | None,
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    timestamp_col: str = "entry_timestamp",
    bucket_tz: str | None = None,
) -> pd.DataFrame:
    """Return trades whose entry timestamp falls inside *entry_window*."""
    if trades is None:
        return pd.DataFrame()

    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    if trades.empty or not window["enabled"]:
        return trades.copy()

    if timestamp_col not in trades.columns:
        raise ValueError(f"trades missing required column {timestamp_col!r}.")

    # Prefer segment column when already present and mode is rth_segments —
    # still re-bucket when needed so C5 session TZ is enforced.
    working = trades
    if window["mode"] == "rth_segments":
        if "entry_rth_segment" not in working.columns:
            working = add_time_buckets(
                working,
                timestamp_col=timestamp_col,
                exchange_tz=exchange_tz,
                bucket_tz=bucket_tz or exchange_tz,
                session_tz=exchange_tz,
            )
        mask = working["entry_rth_segment"].isin(window["rth_segments"])
        return working.loc[mask].copy()

    tz = str(window["timezone"] or exchange_tz)
    start_m = _parse_clock_to_minutes(str(window["start_time"]), field_name="start_time")
    end_m = _parse_clock_to_minutes(
        str(window["end_time"]), field_name="end_time", allow_end_of_day=True
    )

    ts = working[timestamp_col]
    if getattr(ts.dt, "tz", None) is None:
        local = ts.dt.tz_localize(tz)
    else:
        local = ts.dt.tz_convert(tz)
    minute = local.dt.hour * 60 + local.dt.minute
    mask = (minute >= start_m) & (minute < end_m)
    return working.loc[mask].copy()


def focus_provenance(
    entry_window: dict[str, Any] | None,
    *,
    trade_count_before: int,
    trade_count_after: int,
    min_trades: int = 10,
    exchange_tz: str = "America/New_York",
) -> dict[str, Any]:
    """Build Focus metadata for banners / export (includes sample_warning)."""
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    after = int(trade_count_after)
    return {
        "mode": "focus",
        "entry_window": window,
        "trade_count_before": int(trade_count_before),
        "trade_count_after": after,
        "sample_warning": bool(window["enabled"] and after < int(min_trades)),
        "min_trades": int(min_trades),
        "honesty_banner": FOCUS_HONESTY_BANNER,
        "equity_caveat": FOCUS_EQUITY_CAVEAT,
        "subset_replay_equity": True,
    }


def summarize_focused_trades(
    trades: pd.DataFrame | None,
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    timestamp_col: str = "entry_timestamp",
    bucket_tz: str | None = None,
    min_trades: int = 10,
    include_direction: bool = True,
) -> dict[str, Any]:
    """Filter trades and compute full summary + equity for Focus (SW1)."""
    before = 0 if trades is None else int(len(trades))
    focused = filter_trades_by_entry_window(
        trades,
        entry_window,
        exchange_tz=exchange_tz,
        timestamp_col=timestamp_col,
        bucket_tz=bucket_tz,
    )
    summary = summarize_trades(focused)
    curve = equity_curve(focused)
    provenance = focus_provenance(
        entry_window,
        trade_count_before=before,
        trade_count_after=int(len(focused)),
        min_trades=min_trades,
        exchange_tz=exchange_tz,
    )
    result: dict[str, Any] = {
        "focused_trades": focused,
        "focused_trade_summary": summary,
        "focused_equity_curve": curve,
        "focus_provenance": provenance,
        "focus_entry_window": normalize_entry_window(
            entry_window, exchange_tz=exchange_tz
        ),
    }
    if include_direction:
        result["focused_direction_summary"] = summarize_trades_by_direction(focused)
    return result


def format_entry_window_label(entry_window: dict[str, Any] | None) -> str:
    """Short human label for UI captions."""
    if not entry_window or not entry_window.get("enabled"):
        return "disabled"
    mode = entry_window.get("mode")
    if mode == "rth_segments":
        segs = entry_window.get("rth_segments") or []
        return "RTH: " + ", ".join(str(s) for s in segs)
    return f"{entry_window.get('start_time')}–{entry_window.get('end_time')} ({entry_window.get('timezone')})"


# Re-export shared vocabulary for convenience (C1).
__all__ = [
    "FOCUS_EQUITY_CAVEAT",
    "FOCUS_HONESTY_BANNER",
    "RTH_SEGMENT_LABELS",
    "RTH_SEGMENTS",
    "disabled_entry_window",
    "entry_window_contains",
    "entry_window_from_bucket",
    "filter_trades_by_entry_window",
    "focus_provenance",
    "format_entry_window_label",
    "normalize_entry_window",
    "rth_segment_for_minute",
    "summarize_focused_trades",
]
