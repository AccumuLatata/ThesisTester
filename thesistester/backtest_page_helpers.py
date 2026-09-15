"""Classic Backtest persist/display helpers (QR A-2 / QI-04-06, D-3 / QI-04-05).

Kept out of ``pages/7_Backtest.py`` so tests can persist a ``return_result``
diagnostic without importing the Streamlit page. D-3 grows this module with
H7 cutoff, H15 OTF-clock assembly, setup-context, and chart-clip helpers.
The DA1 session key is additive and unhashed (AH §2 item 8). AH4 decision
landed in A-7 (QI-06-03): clear-only via ``_MANAGED_RESEARCH_KEYS`` on bundle
apply; not hashed and not exported. Dataset-switch clear is A-8.

Helpers are Streamlit-free (C-8). Render modules take ``st`` as an argument.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, MutableMapping
from typing import Any

import pandas as pd

from thesistester.visualization import coerce_timestamp_series

DIRECTION_COLLISION_SESSION_KEY = "direction_collision_diagnostic"


def effective_no_new_entries_after(
    flat_by_session_close: bool,
    no_new_entries_after: str,
) -> str | None:
    """H7 locked fork: UI/Grid force None unless flatten is on.

    ``api.run_backtest`` still applies a YAML cutoff when flatten is off
    (skip ``after_entry_cutoff``). Empty / whitespace cutoff is None.
    """
    return (no_new_entries_after.strip() or None) if flat_by_session_close else None


def assemble_otf_filter_clocks(
    exchange_timezone: str | None,
    instrument: Any,
) -> dict[str, Any]:
    """H15: OTF clocks use Data-page exchange TZ, not the Session TZ widget.

    ``session_timezone`` is the already-resolved Data-page / instrument
    ``exchange_timezone``. ``eth_start`` comes from the instrument (or None).
    """
    return {
        "session_timezone": exchange_timezone,
        "eth_start": instrument.eth_start if instrument else None,
    }


def signal_setup_context(signals: Any, signal_context: dict | None) -> str | None:
    """Caption for the saved-setup identity of the candidate signal table."""
    setup_names: list[str] = []
    if "setup_name" in signals.columns:
        setup_names = [
            str(name).strip()
            for name in signals["setup_name"].dropna().unique().tolist()
            if str(name).strip()
        ]

    context = signal_context or {}
    if len(setup_names) > 1:
        return f"Backtesting signals from multiple saved setups: {', '.join(setup_names)}"

    setup_name = setup_names[0] if len(setup_names) == 1 else context.get("setup_name")
    setup_caption = context.get("setup_caption")

    if setup_name and setup_caption:
        return f"Backtesting signals from saved setup: {setup_name} • {setup_caption}"
    if setup_name:
        return f"Backtesting signals from saved setup: {setup_name}"
    if setup_caption:
        return f"Backtesting generated signals • {setup_caption}"
    return None


def clip_trades_for_chart(trades_df: Any, *, start: Any, end: Any) -> Any:
    """Inclusive overlap clip of trades against a visualization window."""
    if trades_df is None:
        return None

    out = trades_df.copy(deep=True)
    if out.empty or (start is None and end is None):
        return out
    if "entry_timestamp" not in out.columns or "exit_timestamp" not in out.columns:
        return out

    start_ts = pd.to_datetime(start, errors="coerce") if start is not None else None
    end_ts = pd.to_datetime(end, errors="coerce") if end is not None else None
    if pd.isna(start_ts):
        start_ts = None
    if pd.isna(end_ts):
        end_ts = None
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    if start_ts is None and end_ts is None:
        return out

    entry_ts = coerce_timestamp_series(out["entry_timestamp"])
    exit_ts = coerce_timestamp_series(out["exit_timestamp"])
    effective_entry = entry_ts.fillna(exit_ts)
    effective_exit = exit_ts.fillna(entry_ts)
    mask = effective_entry.notna() & effective_exit.notna()
    if start_ts is not None:
        mask &= effective_exit >= start_ts
    if end_ts is not None:
        mask &= effective_entry <= end_ts
    return out.loc[mask].copy(deep=True)


def format_metric(v: Any, fmt: str = ".2f", fallback: str = "—") -> str:
    """KPI formatter. NaN / non-numeric → fallback."""
    if v is None:
        return fallback
    try:
        v_float = float(v)
        if math.isnan(v_float):
            return fallback
        return format(v_float, fmt)
    except (TypeError, ValueError):
        return fallback


def format_metric_int(v: Any) -> int:
    """Integer KPI formatter. Invalid → 0."""
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def format_win_rate(v: Any) -> str:
    """Win-rate KPI formatter (one decimal percent)."""
    return format_metric(v, ".1%") if v is not None else "—"


def _as_diagnostic_mapping(source: Any) -> Mapping[str, Any]:
    """Prefer ``.direction_collision_diagnostic`` / nested key over ``source``."""
    attr = getattr(source, "direction_collision_diagnostic", None)
    if isinstance(attr, Mapping):
        return attr
    if isinstance(source, Mapping):
        nested = source.get(DIRECTION_COLLISION_SESSION_KEY)
        if isinstance(nested, Mapping):
            return nested
        if "candidate_pairs" in source:
            return source
    return {}


def persist_direction_collision_diagnostic(
    session_state: MutableMapping[str, Any],
    source: Any,
) -> dict[str, Any]:
    """Store DA1 ``direction_collision_diagnostic`` after a ``return_result`` run."""
    diagnostic = dict(_as_diagnostic_mapping(source))
    session_state[DIRECTION_COLLISION_SESSION_KEY] = diagnostic
    return diagnostic


def format_direction_collision_caption(diagnostic: Mapping[str, Any] | None) -> str:
    """Skip-table caption for the stored DA1 pair counts. Not a P&L claim."""
    if not isinstance(diagnostic, Mapping) or "candidate_pairs" not in diagnostic:
        return "DA1 same-bar opposite-direction diagnostic was not stored for this run."
    pairs = diagnostic.get("candidate_pairs", 0)
    policy = diagnostic.get("policy", "legacy")
    share = diagnostic.get("accepted_trade_share_from_pairs", 0.0)
    return (
        f"DA1 same-bar opposite pairs: {pairs} candidate pair(s) · "
        f"resolved long/short/none: "
        f"{diagnostic.get('resolved_long', 0)}/"
        f"{diagnostic.get('resolved_short', 0)}/"
        f"{diagnostic.get('resolved_none', 0)} · "
        f"accepted-trade share from pairs: {share} · "
        f"policy `{policy}`. "
        "Same-bar opposite-direction counts only — not an admission gate "
        "and not proof of fill quality. "
        "Visible under `allow_all` even when the skip table is empty. "
        "Diagnostic only — not a hashed bundle member."
    )
