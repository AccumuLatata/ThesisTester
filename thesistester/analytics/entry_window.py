"""Post-hoc Focus helpers for entry windows (SW1) + re-exports (C1).

Admission/normalize/contains live in :mod:`thesistester.entry_window_policy`
so the engine can import them without circular imports through analytics.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics.metrics import (
    equity_curve,
    summarize_trades,
    summarize_trades_by_direction,
)
from thesistester.analytics.time_analysis import add_time_buckets, summarize_by_group
from thesistester.entry_window_policy import (
    RTH_SEGMENT_LABELS,
    RTH_SEGMENTS,
    disabled_entry_window,
    entry_window_contains,
    entry_window_from_bucket,
    format_entry_window_label,
    normalize_entry_window,
    rth_segment_for_minute,
)

# Focus / Promote UI may select only these Time Analysis group columns.
FOCUSABLE_GROUP_COLS = (
    "entry_rth_segment",
    "entry_hour_bucket",
    "entry_30min_bucket",
)

FOCUS_HONESTY_BANNER = (
    "Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."
)
FOCUS_EQUITY_CAVEAT = "Equity/drawdown rebuilt from the filtered trade subset only (subset replay)."
ADMIT_HONESTY_BANNER = "Constrained re-simulation — only in-window entries were admitted."
PROMOTE_ARMED_BANNER = "Entry window armed. Run Backtest to re-simulate under this constraint."
FOCUS_STATUS_BADGE = "Focus · post-hoc subset"
ADMIT_ARMED_STATUS_BADGE = "Admit · armed (pending re-sim)"
ADMIT_APPLIED_STATUS_BADGE = "Admit · constrained re-sim"
ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING = (
    "Entry window is a fixed Admit constraint across all cells/folds — "
    "not a swept Grid/WFA axis. No per-fold time-bucket reselection."
)
OUTSIDE_ENTRY_WINDOW_REASON = "outside_entry_window"


def partition_skip_counts(skipped_signals: pd.DataFrame | None) -> dict[str, int]:
    """Split skip diagnostics into entry-window vs other (exposure) reasons.

    Returns counts suitable for Backtest captions. Unknown/missing
    ``skip_reason`` values are counted as ``other``.
    """
    if skipped_signals is None or not isinstance(skipped_signals, pd.DataFrame):
        return {
            "total": 0,
            "outside_entry_window": 0,
            "other": 0,
        }
    total = int(len(skipped_signals))
    if total == 0 or "skip_reason" not in skipped_signals.columns:
        return {
            "total": total,
            "outside_entry_window": 0,
            "other": total,
        }
    reasons = skipped_signals["skip_reason"].astype(str)
    window_n = int((reasons == OUTSIDE_ENTRY_WINDOW_REASON).sum())
    return {
        "total": total,
        "outside_entry_window": window_n,
        "other": total - window_n,
    }


def entry_focus_bucket_values(
    trades: pd.DataFrame | None,
    group_col: str,
    *,
    exchange_tz: str = "America/New_York",
    bucket_tz: str | None = None,
) -> list[str]:
    """Return Focus/Promote bucket labels from **entry**-time bucketing (C2).

    Time Analysis charts may group by ``exit_timestamp`` while still labeling
    columns ``entry_*``. Focus/Promote options must not reuse that exit
    partition — membership and Promote sample counts always use entry time.
    """
    col = str(group_col).strip()
    if col not in FOCUSABLE_GROUP_COLS:
        return []
    if trades is None or not isinstance(trades, pd.DataFrame) or trades.empty:
        return []
    if "entry_timestamp" not in trades.columns:
        return []
    bucketed = add_time_buckets(
        trades,
        timestamp_col="entry_timestamp",
        exchange_tz=exchange_tz,
        bucket_tz=bucket_tz or exchange_tz,
        session_tz=exchange_tz,
    )
    if col not in bucketed.columns:
        return []
    grouped = summarize_by_group(bucketed, group_cols=[col], min_trades=1)
    if grouped.empty or col not in grouped.columns:
        return []
    return grouped[col].dropna().astype(str).drop_duplicates().tolist()


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

    # clock_range — reuse shared membership predicate (C2–C5).
    mask = working[timestamp_col].map(
        lambda ts: entry_window_contains(ts, window, exchange_tz=exchange_tz)
    )
    return working.loc[mask.astype(bool)].copy()


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
        "focus_entry_window": normalize_entry_window(entry_window, exchange_tz=exchange_tz),
    }
    if include_direction:
        result["focused_direction_summary"] = summarize_trades_by_direction(focused)
    return result


def backtest_widget_state_from_entry_window(
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
) -> dict[str, Any]:
    """Map a normalized entry_window to Backtest Admit widget session keys.

    Always writes the full Admit widget key set so a mode switch (RTH ↔ clock)
    cannot leave stale opposite-mode values from a prior Promote.
    """
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    if not window["enabled"]:
        return {"backtest_entry_window_enabled": False}
    # Defaults for the inactive mode keep Streamlit widgets coherent if the
    # user flips mode after Promote.
    state: dict[str, Any] = {
        "backtest_entry_window_enabled": True,
        "backtest_entry_window_mode": window["mode"],
        "backtest_entry_window_timezone": window["timezone"] or exchange_tz,
        "backtest_entry_window_rth_segments": ["rth_open_30m"],
        "backtest_entry_window_start_time": "09:30",
        "backtest_entry_window_end_time": "10:00",
    }
    if window["mode"] == "rth_segments":
        state["backtest_entry_window_rth_segments"] = list(window["rth_segments"])
    else:
        state["backtest_entry_window_start_time"] = window["start_time"]
        state["backtest_entry_window_end_time"] = window["end_time"]
    return state


def promote_entry_window(
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    trade_count_after: int | None = None,
    trade_count_before: int | None = None,
    min_trades: int = 10,
    source: str = "promote",
    thin_sample_confirmed: bool = False,
) -> dict[str, Any]:
    """Build an armed Admit handoff payload (SW4) — no simulation.

    Raises ``ValueError`` when the window is disabled, invalid, or when a
    thin-sample Promote is attempted without confirmation.
    """
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    if not window["enabled"]:
        raise ValueError("Cannot promote a disabled entry_window.")
    # C5: Promote writes an explicit IANA timezone into the normalized dict.
    if not window.get("timezone"):
        raise ValueError("Promoted entry_window must include an explicit timezone (C5).")

    after = 0 if trade_count_after is None else int(trade_count_after)
    before = after if trade_count_before is None else int(trade_count_before)
    sample_warning = after < int(min_trades)
    if sample_warning and not thin_sample_confirmed:
        raise ValueError(
            "Thin-sample Promote requires confirmation "
            f"(trade_count_after={after} < min_trades={int(min_trades)})."
        )

    provenance = {
        "source": str(source),
        "sample_warning": bool(sample_warning),
        "trade_count_after": after,
        "trade_count_before": before,
        "min_trades": int(min_trades),
        "thin_sample_confirmed": bool(thin_sample_confirmed and sample_warning),
        "label": format_entry_window_label(window),
        "armed_banner": PROMOTE_ARMED_BANNER,
        "status": "armed",
    }
    return {
        "entry_window": window,
        "backtest_widget_state": backtest_widget_state_from_entry_window(
            window, exchange_tz=exchange_tz
        ),
        "entry_window_armed": True,
        "entry_window_promote_provenance": provenance,
    }


def apply_promote_to_session_state(session_state: Any, payload: dict[str, Any]) -> None:
    """Apply a Promote payload onto a session_state-like mapping (overwrite widgets)."""
    if not isinstance(payload, dict) or "entry_window" not in payload:
        raise ValueError("Promote payload must include entry_window.")
    session_state["entry_window"] = payload["entry_window"]
    session_state["entry_window_armed"] = bool(payload.get("entry_window_armed", True))
    session_state["entry_window_promote_provenance"] = dict(
        payload.get("entry_window_promote_provenance") or {}
    )
    for key, value in (payload.get("backtest_widget_state") or {}).items():
        session_state[key] = value


def pick_inherited_entry_window_source(
    *candidates: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Prefer the first *enabled* Admit window among session candidates.

    Disabled dicts are truthy in Python, so ``a or b`` silently prefers a
    disabled Backtest ``entry_window`` over an enabled ``grid_entry_window``.
    """
    fallback: dict[str, Any] | None = None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if fallback is None:
            fallback = candidate
        if candidate.get("enabled"):
            return candidate
    return fallback


def resolve_inherited_entry_window(
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    armed: bool = False,
) -> dict[str, Any]:
    """Resolve session/API entry_window for Grid / WFA / sensitivity (SW5).

    Returns a JSON-safe dict with simulate kwargs and UI warning metadata.
    Disabled / missing windows yield ``simulate_entry_window=None`` (legacy).
    """
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    enabled = bool(window.get("enabled"))
    return {
        "entry_window": window if enabled else None,
        "entry_window_normalized": window,
        "entry_window_exchange_tz": exchange_tz,
        "enabled": enabled,
        "armed": bool(armed) and enabled,
        "label": format_entry_window_label(window),
        "warning": ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING if enabled else None,
    }


def clear_armed_entry_window(session_state: Any) -> None:
    """Disarm a pending Admit window without clearing Focus overlays.

    Only mutates Admit arming state when a Promote is still pending
    (``entry_window_armed``). Applied constrained-run windows are left intact.
    """
    was_armed = bool(session_state.pop("entry_window_armed", False))
    session_state.pop("entry_window_promote_provenance", None)
    if not was_armed:
        return
    session_state["backtest_entry_window_enabled"] = False
    current = session_state.get("entry_window")
    timezone = current.get("timezone") if isinstance(current, dict) else None
    session_state["entry_window"] = disabled_entry_window(timezone=timezone)


def consume_armed_entry_window_after_run(
    session_state: Any,
    normalized_entry_window: dict[str, Any],
) -> None:
    """Update session Admit state after a successful Backtest Run (SW4).

    A pending Promote is consumed only when the run actually applied Admit
    (``normalized_entry_window["enabled"]``). An all-day re-sim with the Admit
    toggle off preserves the armed window and provenance.
    """
    was_armed = bool(session_state.get("entry_window_armed"))
    admit_applied = bool(
        isinstance(normalized_entry_window, dict) and normalized_entry_window.get("enabled")
    )
    if admit_applied or not was_armed:
        session_state["entry_window"] = normalized_entry_window
    if was_armed and admit_applied:
        session_state["entry_window_armed"] = False
        promote_prov = session_state.get("entry_window_promote_provenance")
        if isinstance(promote_prov, dict):
            session_state["entry_window_promote_provenance"] = {
                **promote_prov,
                "status": "applied",
            }


__all__ = [
    "ADMIT_APPLIED_STATUS_BADGE",
    "ADMIT_ARMED_STATUS_BADGE",
    "ADMIT_HONESTY_BANNER",
    "ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING",
    "FOCUSABLE_GROUP_COLS",
    "FOCUS_EQUITY_CAVEAT",
    "FOCUS_HONESTY_BANNER",
    "FOCUS_STATUS_BADGE",
    "OUTSIDE_ENTRY_WINDOW_REASON",
    "PROMOTE_ARMED_BANNER",
    "RTH_SEGMENT_LABELS",
    "RTH_SEGMENTS",
    "apply_promote_to_session_state",
    "backtest_widget_state_from_entry_window",
    "clear_armed_entry_window",
    "consume_armed_entry_window_after_run",
    "disabled_entry_window",
    "entry_focus_bucket_values",
    "entry_window_contains",
    "entry_window_from_bucket",
    "filter_trades_by_entry_window",
    "focus_provenance",
    "format_entry_window_label",
    "normalize_entry_window",
    "partition_skip_counts",
    "pick_inherited_entry_window_source",
    "promote_entry_window",
    "resolve_inherited_entry_window",
    "rth_segment_for_minute",
    "summarize_focused_trades",
]
