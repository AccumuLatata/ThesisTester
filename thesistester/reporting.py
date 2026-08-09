"""Phase 9 reporting/export helpers for reproducible research artifacts."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from math import isinf, isnan
from typing import Any, Mapping

import numpy as np
import pandas as pd

from thesistester.analytics.confluence_attribution import (
    EXACT_COMBO_KEY_COL,
    LEVEL_COUNT_BUCKET_COL,
    LEVEL_NAME_COL,
    MEMBERSHIP_DOUBLE_COUNT_WARNING,
    PAIR_KEY_COL,
    PAIR_MODE_COL,
    PAIRWISE_DOUBLE_COUNT_WARNING,
    confluence_attribution_summary,
    prepare_exact_combo_display,
    resolve_confluence_mode,
    resolve_signal_setup_for_attribution,
)
from .timezone_display import convert_dataframe_timestamps_for_display, timezone_contract


_CONFLUENCE_COMBO_TOP_N_DEFAULT = 15

_CAVEATS = [
    "Research output only; not trading advice.",
    "Backtests are based on historical data and assumptions.",
    "OHLC bars cannot reveal true intrabar event order; selected deterministic models are assumptions, and lower-timeframe replay retains residual within-sub-bar ambiguity.",
    "Grid search can overfit; validation diagnostics are descriptive only.",
    "No guarantee of future performance.",
]


def _dash_if_none(value: Any) -> Any:
    """Return ``'—'`` when *value* is ``None``; otherwise return *value* unchanged.

    Preserves ``0`` as ``0``, empty strings as empty strings, and any
    other falsy-but-not-None values as themselves.
    """
    return "—" if value is None else value


def _json_safe_float(value: float) -> float | None:
    if isnan(value) or isinf(value):
        return None
    return value


def to_jsonable(obj: Any) -> Any:
    """Convert mixed Python/pandas/numpy objects into JSON-safe structures."""
    if obj is None:
        return None

    if obj is pd.NA or obj is pd.NaT:
        return None

    non_scalar_types = (list, tuple, set, Mapping, pd.DataFrame, pd.Series, np.ndarray)
    try:
        if not isinstance(obj, non_scalar_types) and pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(obj, (pd.Timestamp, datetime, date, time)):
        return obj.isoformat()

    if isinstance(obj, np.datetime64):
        return pd.Timestamp(obj).isoformat()

    if isinstance(obj, np.timedelta64):
        return pd.Timedelta(obj).isoformat()

    if isinstance(obj, pd.Timedelta):
        return obj.isoformat()

    if isinstance(obj, pd.DataFrame):
        return dataframe_to_json_records(obj)

    if isinstance(obj, pd.Series):
        return {str(k): to_jsonable(v) for k, v in obj.to_dict().items()}

    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]

    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())

    if isinstance(obj, np.generic):
        return to_jsonable(obj.item())

    if isinstance(obj, float):
        return _json_safe_float(obj)

    return obj


def dataframe_to_csv_bytes(df: pd.DataFrame | None) -> bytes:
    """Return UTF-8 CSV bytes for a DataFrame."""
    if df is None or df.empty:
        return b""
    return df.to_csv(index=False).encode("utf-8")


def dataframe_to_json_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Return JSON-safe DataFrame rows as list-of-dicts records."""
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    return [to_jsonable(record) for record in records]


def _table_records(
    session_state: Mapping[str, Any],
    key: str,
    *,
    display_timezone: str,
    canonical_timezone: str,
) -> list[dict[str, Any]]:
    value = session_state.get(key)
    if isinstance(value, pd.DataFrame):
        converted, _ = convert_dataframe_timestamps_for_display(
            value,
            display_timezone=display_timezone,
            canonical_timezone=canonical_timezone,
        )
        return dataframe_to_json_records(converted)
    return []


def _table_count(session_state: Mapping[str, Any], key: str) -> int:
    value = session_state.get(key)
    if isinstance(value, pd.DataFrame):
        return int(len(value))
    return 0


def build_entry_window_metadata(session_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build entry-window (Focus / Admit) metadata for research export (SW6).

    Distinguishes post-hoc Focus from constrained Admit re-sim and exports
    promote / grid inheritance provenance. Focus alone is never framed as
    deployable edge evidence.
    """
    from thesistester.analytics.entry_window import (
        ADMIT_HONESTY_BANNER,
        FOCUS_EQUITY_CAVEAT,
        FOCUS_HONESTY_BANNER,
        format_entry_window_label,
    )
    from thesistester.entry_window_policy import normalize_entry_window

    admit_raw = session_state.get("entry_window")
    focus_raw = session_state.get("focus_entry_window")
    focus_provenance = session_state.get("focus_provenance")
    promote_provenance = session_state.get("entry_window_promote_provenance")
    grid_raw = session_state.get("grid_entry_window")
    armed = session_state.get("entry_window_armed")

    def _as_window(raw: Any) -> dict[str, Any] | None:
        """Normalize or fail closed — never export an invalid window as enabled."""
        if not isinstance(raw, Mapping) or not raw:
            return None
        try:
            return normalize_entry_window(dict(raw))
        except ValueError:
            return None

    admit = _as_window(admit_raw)
    focus_window = _as_window(focus_raw)
    grid_window = _as_window(grid_raw)
    focus_prov = dict(focus_provenance) if isinstance(focus_provenance, Mapping) else None
    promote_prov = dict(promote_provenance) if isinstance(promote_provenance, Mapping) else None
    # Prefer session focus_entry_window; fall back to provenance.entry_window (SW7).
    if focus_window is None and focus_prov is not None:
        focus_window = _as_window(focus_prov.get("entry_window"))

    admit_enabled = bool(admit.get("enabled")) if isinstance(admit, Mapping) else False
    # Fail closed: only a normalized focus_window counts as enabled (SW7 fallback
    # already hydrates from provenance.entry_window when session key is missing).
    # Do not OR raw provenance.enabled — invalid drafts must not look like Focus.
    focus_enabled = (
        bool(focus_window.get("enabled")) if isinstance(focus_window, Mapping) else False
    )
    grid_enabled = bool(grid_window.get("enabled")) if isinstance(grid_window, Mapping) else False
    armed_pending = bool(armed)

    # Disabled placeholder dicts alone are not "available" evidence — avoid
    # showing an Entry Window checklist green for routine all-day runs.
    available = bool(
        admit_enabled or focus_enabled or grid_enabled or promote_prov is not None or armed_pending
    )

    honesty_notes = [
        FOCUS_HONESTY_BANNER,
        FOCUS_EQUITY_CAVEAT,
        ADMIT_HONESTY_BANNER,
        "Focus is a post-hoc subset — not proof of deployable edge. "
        "Promote and re-simulate (Admit) before treating a window as constrained evidence.",
    ]

    return {
        "available": bool(available),
        "admit": {
            "enabled": admit_enabled if admit is not None else None,
            "armed": bool(armed) if armed is not None else False,
            "entry_window": to_jsonable(admit),
            "label": format_entry_window_label(admit) if admit_enabled else None,
            "honesty_banner": ADMIT_HONESTY_BANNER if admit_enabled else None,
        },
        "focus": {
            "enabled": focus_enabled
            if (focus_window is not None or focus_prov is not None)
            else None,
            "entry_window": to_jsonable(focus_window),
            "label": format_entry_window_label(focus_window) if focus_enabled else None,
            "provenance": to_jsonable(focus_prov),
            "honesty_banner": FOCUS_HONESTY_BANNER if focus_enabled else None,
            "equity_caveat": FOCUS_EQUITY_CAVEAT if focus_enabled else None,
            "is_post_hoc": True,
            "is_not_admit": True,
        },
        "promote": {
            "available": promote_prov is not None,
            "provenance": to_jsonable(promote_prov),
        },
        "grid": {
            "enabled": grid_enabled if grid_window is not None else None,
            "entry_window": to_jsonable(grid_window),
            "label": (format_entry_window_label(grid_window) if grid_enabled else None),
        },
        "honesty_notes": honesty_notes,
    }


def build_otf_filter_metadata(session_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build OTF filter metadata section from session state.

    Reads OTF filter results stored by backtest, grid-search, and
    walk-forward integration.  Returns a scoped metadata dict that
    distinguishes disabled, enabled-with-rejections, enabled-zero-rejected,
    and unavailable states.

    Session-state keys consumed
    ---------------------------
    - ``otf_filter_result`` / ``otf_filter_summary`` — backtest scope
    - ``grid_otf_filter`` — grid-search scope
    - ``walk_forward_otf_filter`` — walk-forward scope
    """
    applied_scopes: list[str] = []

    # Prefer the full result object; fall back to the summary dict
    backtest_summary = session_state.get("otf_filter_summary")
    backtest_result = session_state.get("otf_filter_result")
    if backtest_result is not None and hasattr(backtest_result, "to_summary_dict"):
        backtest_summary = backtest_result.to_summary_dict()

    grid_summary = session_state.get("grid_otf_filter")
    wf_summary = session_state.get("walk_forward_otf_filter")

    # Determine primary summary (backtest > grid > walk-forward)
    primary: dict[str, Any] | None = None
    if isinstance(backtest_summary, Mapping) and len(backtest_summary) > 0:
        primary = dict(backtest_summary)
        applied_scopes.append("backtest")
    if isinstance(grid_summary, Mapping) and len(grid_summary) > 0:
        applied_scopes.append("grid")
        if primary is None:
            primary = dict(grid_summary)
    if isinstance(wf_summary, Mapping) and len(wf_summary) > 0:
        applied_scopes.append("walk_forward")
        if primary is None:
            primary = dict(wf_summary)

    if primary is None:
        return {
            "available": False,
            "enabled": None,
            "config": None,
            "algorithm_version": None,
            "config_hash": None,
            "candidate_signal_count": None,
            "accepted_signal_count": None,
            "rejected_signal_count": None,
            "rejection_rate": None,
            "applied_scopes": [],
        }

    enabled = bool(primary.get("otf_filter_enabled", False))
    candidate_count = primary.get("candidate_signal_count")
    accepted_count = primary.get("otf_accepted_signal_count")
    rejected_count = primary.get("otf_rejected_signal_count")

    rejection_rate: float | None = None
    if (
        isinstance(candidate_count, (int, float))
        and isinstance(rejected_count, (int, float))
        and candidate_count > 0
    ):
        rejection_rate = float(rejected_count) / float(candidate_count)

    # otf_history_policy is WFO-only. Backtest/grid summaries are preferred for
    # counts/config but never carry this field — fall back to walk-forward scopes
    # so a prior backtest/grid run cannot blank a completed WFO policy.
    history_policy = primary.get("otf_history_policy")
    if history_policy is None and isinstance(wf_summary, Mapping):
        history_policy = wf_summary.get("otf_history_policy")
    if history_policy is None:
        wf_config = session_state.get("walk_forward_config")
        if isinstance(wf_config, Mapping):
            history_policy = wf_config.get("otf_history_policy")
    if history_policy is None:
        wf_run_summary = session_state.get("walk_forward_summary")
        if isinstance(wf_run_summary, Mapping):
            history_policy = wf_run_summary.get("otf_history_policy")

    return {
        "available": True,
        "enabled": enabled,
        "config": to_jsonable(primary.get("otf_filter_config")),
        "algorithm_version": primary.get("otf_algorithm_version"),
        "config_hash": primary.get("otf_config_hash"),
        "candidate_signal_count": candidate_count,
        "accepted_signal_count": accepted_count,
        "rejected_signal_count": rejected_count,
        "rejection_rate": rejection_rate,
        "session_timezone": primary.get("session_timezone"),
        "eth_start": primary.get("eth_start"),
        "otf_history_policy": history_policy,
        "applied_scopes": applied_scopes,
    }


def build_research_artifact(session_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build a consolidated JSON-safe research artifact from session state."""
    setup_config = session_state.get("setup_config")
    instrument = session_state.get("instrument")
    if instrument is None and isinstance(setup_config, Mapping):
        instrument = setup_config.get("instrument")

    contract = timezone_contract(dict(session_state))
    canonical_timezone = contract.get("canonical_engine_timezone") or "America/New_York"
    display_timezone = contract.get("display_export_timezone") or canonical_timezone

    artifact = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "app": "ThesisTester",
            "schema_version": "1.0",
        },
        "timezone_contract": contract,
        "configuration": {
            "instrument": to_jsonable(instrument),
            "format_profile": to_jsonable(session_state.get("format_profile", "canonical")),
            "raw_capture": {
                "raw_interval": to_jsonable(session_state.get("raw_interval")),
                "raw_rows": _table_count(session_state, "raw_data"),
            },
            "setup_config": to_jsonable(setup_config),
            "last_signal_setup": to_jsonable(session_state.get("last_signal_setup")),
            "walk_forward_config": to_jsonable(session_state.get("walk_forward_config")),
            "roll_policy": to_jsonable(session_state.get("roll_policy")),
        },
        "data_quality": {
            "roll_validation": to_jsonable(session_state.get("roll_validation")),
        },
        "results": {
            "signal_count": _table_count(session_state, "signals"),
            "trade_count": _table_count(session_state, "trades"),
            "trade_summary": to_jsonable(session_state.get("trade_summary")),
            "best_grid_result": to_jsonable(session_state.get("best_grid_result")),
            "validation_summary": to_jsonable(session_state.get("validation_summary")),
            "walk_forward_summary": to_jsonable(session_state.get("walk_forward_summary")),
            "walk_forward_warnings": to_jsonable(session_state.get("walk_forward_warnings")),
            "excursion_summary": to_jsonable(session_state.get("excursion_summary")),
            "monte_carlo_summary": to_jsonable(session_state.get("monte_carlo_summary")),
            "noise_summary": to_jsonable(session_state.get("noise_summary")),
            "overfitting_summary": to_jsonable(session_state.get("overfitting_summary")),
            "sensitivity_summary": to_jsonable(session_state.get("sensitivity_summary")),
            "portfolio_summary": to_jsonable(session_state.get("portfolio_summary")),
            "backtest_intrabar_diagnostic": to_jsonable(
                session_state.get("backtest_intrabar_diagnostic")
            ),
            "backtest_exit_management_diagnostic": to_jsonable(
                session_state.get("backtest_exit_management_diagnostic")
            ),
        },
        "intrabar": {
            "backtest_policy": to_jsonable(session_state.get("backtest_intrabar_policy")),
            "backtest_diagnostic": to_jsonable(session_state.get("backtest_intrabar_diagnostic")),
            "grid_policy": to_jsonable(session_state.get("grid_intrabar_policy")),
        },
        "exit_management": {
            "backtest_policy": to_jsonable(session_state.get("backtest_exit_management_policy")),
            "backtest_diagnostic": to_jsonable(
                session_state.get("backtest_exit_management_diagnostic")
            ),
            "grid_policy": to_jsonable(session_state.get("grid_exit_management_policy")),
        },
        "otf_filter": to_jsonable(build_otf_filter_metadata(session_state)),
        "entry_window": to_jsonable(build_entry_window_metadata(session_state)),
        "tables": {
            "signals": _table_records(
                session_state,
                "signals",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "trades": _table_records(
                session_state,
                "trades",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "equity_curve": _table_records(
                session_state,
                "equity_curve",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "grid_results": _table_records(
                session_state,
                "grid_results",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "time_grouped_summary": _table_records(
                session_state,
                "time_grouped_summary",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "walk_forward_results": _table_records(
                session_state,
                "walk_forward_results",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "walk_forward_oos_trades": _table_records(
                session_state,
                "walk_forward_oos_trades",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "walk_forward_stitched_equity": _table_records(
                session_state,
                "walk_forward_stitched_equity",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "wfa_matrix": _table_records(
                session_state,
                "wfa_matrix",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "otf_rejected_signals": _table_records(
                session_state,
                "otf_rejected_signals",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "otf_validation_matrix": _table_records(
                session_state,
                "otf_validation_matrix",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "excursion_grouped_summary": _table_records(
                session_state,
                "excursion_grouped_summary",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "excursion_calibration_grid": _table_records(
                session_state,
                "excursion_calibration_grid",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
            "excursion_quadrant_summary": _table_records(
                session_state,
                "excursion_quadrant_summary",
                display_timezone=display_timezone,
                canonical_timezone=canonical_timezone,
            ),
        },
        "caveats": list(_CAVEATS),
    }
    # Add OTF validation section only when results are available so existing
    # artifact structure is unchanged when validation has not been run.
    otf_val_matrix = session_state.get("otf_validation_matrix")
    otf_val_summary = session_state.get("otf_validation_summary")
    otf_val_config = session_state.get("otf_validation_config")
    if isinstance(otf_val_matrix, pd.DataFrame) and not otf_val_matrix.empty:
        artifact["otf_validation"] = {
            "available": True,
            "summary": to_jsonable(otf_val_summary) if otf_val_summary else None,
            "config": to_jsonable(otf_val_config) if otf_val_config else None,
        }

    # PR 5b: confluence combo diagnostic — omit entirely when unavailable so
    # legacy artifacts/reports stay identical without combo data.
    confluence_combo = build_confluence_combo_report_block(session_state)
    if confluence_combo is not None:
        artifact["confluence_combo"] = confluence_combo
        tables = artifact.get("tables")
        if isinstance(tables, dict):
            combo_tables = confluence_combo.get("tables") or {}
            if isinstance(combo_tables, Mapping):
                for name, rows in combo_tables.items():
                    tables[f"confluence_{name}"] = rows

    return to_jsonable(artifact)


def _top_n_by_abs_total_r(frame: pd.DataFrame | None, n: int) -> pd.DataFrame:
    """Presentation sort for report tables: ``|total_r|`` desc, then trade_count."""
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    if "total_r" not in frame.columns:
        return frame.head(max(int(n), 0)).copy()
    work = frame.copy()
    work["__abs_total_r__"] = pd.to_numeric(work["total_r"], errors="coerce").abs()
    if "trade_count" in work.columns:
        work = work.sort_values(
            ["__abs_total_r__", "trade_count"],
            ascending=[False, False],
            kind="mergesort",
        )
    else:
        work = work.sort_values("__abs_total_r__", ascending=False, kind="mergesort")
    return work.drop(columns=["__abs_total_r__"]).head(max(int(n), 0)).reset_index(drop=True)


def build_confluence_combo_report_block(
    session_state: Mapping[str, Any],
    *,
    min_trades: int = 10,
    top_n: int = _CONFLUENCE_COMBO_TOP_N_DEFAULT,
) -> dict[str, Any] | None:
    """Recompute confluence combo attribution for report export.

    Resolves mode/anchor from session keys (including ``signal_settings`` when
    present), matching Backtest. Returns ``None`` when unavailable so callers
    can omit the block entirely.
    """
    trades = session_state.get("trades")
    if not isinstance(trades, pd.DataFrame) or trades.empty:
        return None
    if "level_names" not in trades.columns:
        return None

    identity = resolve_signal_setup_for_attribution(
        signal_settings=session_state.get("signal_settings"),
        last_signal_setup=session_state.get("last_signal_setup"),
        setup_config=session_state.get("setup_config"),
        signal_context=session_state.get("signal_context"),
    )
    mode = resolve_confluence_mode(identity, trades)
    anchor: str | None = None
    if mode == "anchor_rules":
        raw_anchor = identity.get("anchor_level")
        if isinstance(raw_anchor, str) and raw_anchor.strip():
            anchor = raw_anchor.strip()

    try:
        summary = confluence_attribution_summary(
            trades,
            min_trades=min_trades,
            anchor_level=anchor,
            confluence_mode=mode,
        )
    except (TypeError, ValueError, KeyError):
        return None

    if not summary.get("available"):
        return None

    exact = summary.get("by_exact_combo")
    if isinstance(exact, pd.DataFrame):
        exact = prepare_exact_combo_display(
            exact,
            anchor_level=anchor,
            confluence_mode=mode,
        )
    membership = summary.get("by_membership")
    level_count = summary.get("by_level_count")
    pairs = summary.get("by_pairs")

    exact_top = _top_n_by_abs_total_r(
        exact if isinstance(exact, pd.DataFrame) else None,
        top_n,
    )
    membership_top = _top_n_by_abs_total_r(
        membership if isinstance(membership, pd.DataFrame) else None,
        top_n,
    )
    pairs_top = _top_n_by_abs_total_r(
        pairs if isinstance(pairs, pd.DataFrame) else None,
        top_n,
    )
    level_count_full = (
        level_count.copy()
        if isinstance(level_count, pd.DataFrame)
        else pd.DataFrame()
    )

    return {
        "available": True,
        "trade_count": int(summary.get("trade_count") or 0),
        "nonempty_combo_trade_count": int(summary.get("nonempty_combo_trade_count") or 0),
        "empty_level_names_count": int(summary.get("empty_level_names_count") or 0),
        "pair_mode": summary.get("pair_mode"),
        "confluence_mode": mode,
        "anchor_level": anchor,
        "warnings": list(summary.get("warnings") or []),
        "top_n": int(top_n),
        "tables": {
            "exact_combo": to_jsonable(exact_top),
            "level_count": to_jsonable(level_count_full),
            "membership": to_jsonable(membership_top),
            "pairs": to_jsonable(pairs_top),
        },
    }


def _fmt_number(value: Any, fmt: str = ".4f", fallback: str = "—") -> str:
    if value is None:
        return fallback
    try:
        return format(float(value), fmt)
    except (TypeError, ValueError):
        return fallback


def _fmt_pct(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    try:
        return format(float(value), ".1%")
    except (TypeError, ValueError):
        return fallback


def _best_grid_metric(best_grid: Mapping[str, Any] | None) -> tuple[str | None, Any]:
    if not isinstance(best_grid, Mapping):
        return None, None
    for key in ("expectancy_r", "avg_r", "total_r", "win_rate", "profit_factor"):
        if key in best_grid and best_grid.get(key) is not None:
            return key, best_grid.get(key)
    return None, None


def _has_nonempty_value(value: Any) -> bool:
    """Return True when a value exists and is non-empty (including DataFrames)."""
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, (list, tuple, set, Mapping)):
        return len(value) > 0
    return True


def _metrics_basis(commission_per_side: float, slippage_ticks: float) -> str:
    """Return metrics basis label based on whether any execution costs are enabled."""
    return (
        "net-of-cost"
        if commission_per_side > 0.0 or slippage_ticks > 0.0
        else "gross==net (zero costs)"
    )


def build_execution_cost_assumptions(session_state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return scoped execution-cost assumptions for current backtest/grid export data.

    Availability is true only when both the corresponding result scope is present in
    session state and a non-empty matching `*_execution_costs` mapping exists.
    """
    backtest_results_available = _has_nonempty_value(
        session_state.get("trades")
    ) or _has_nonempty_value(session_state.get("trade_summary"))
    grid_results_available = _has_nonempty_value(
        session_state.get("grid_results")
    ) or _has_nonempty_value(session_state.get("best_grid_result"))

    backtest_costs = session_state.get("backtest_execution_costs")
    grid_costs = session_state.get("grid_execution_costs")
    backtest_available = (
        backtest_results_available
        and isinstance(backtest_costs, Mapping)
        and len(backtest_costs) > 0
    )
    grid_available = (
        grid_results_available and isinstance(grid_costs, Mapping) and len(grid_costs) > 0
    )

    assumptions: dict[str, dict[str, Any]] = {
        "backtest": {
            "available": backtest_available,
            "commission_per_side": None,
            "slippage_ticks": None,
            "metrics_basis": None,
        },
        "grid": {
            "available": grid_available,
            "commission_per_side": None,
            "slippage_ticks": None,
            "metrics_basis": None,
        },
    }

    if backtest_available:
        commission_per_side = float(backtest_costs.get("commission_per_side", 0.0))
        slippage_ticks = float(backtest_costs.get("slippage_ticks", 0.0))
        assumptions["backtest"].update(
            {
                "commission_per_side": commission_per_side,
                "slippage_ticks": slippage_ticks,
                "metrics_basis": _metrics_basis(commission_per_side, slippage_ticks),
            }
        )
    if grid_available:
        commission_per_side = float(grid_costs.get("commission_per_side", 0.0))
        slippage_ticks = float(grid_costs.get("slippage_ticks", 0.0))
        assumptions["grid"].update(
            {
                "commission_per_side": commission_per_side,
                "slippage_ticks": slippage_ticks,
                "metrics_basis": _metrics_basis(commission_per_side, slippage_ticks),
            }
        )

    return assumptions


def execution_cost_assumptions_markdown(assumptions: Mapping[str, Mapping[str, Any]]) -> str:
    """Render scoped execution-cost assumptions as markdown report section text."""
    backtest = assumptions.get("backtest", {})
    grid = assumptions.get("grid", {})

    section = (
        "\n## Execution Cost Assumptions\n"
        "\n### Backtest\n"
        f"- Available: {'yes' if backtest.get('available') else 'no'}\n"
    )
    if backtest.get("available"):
        section += (
            f"- Commission per side: {backtest.get('commission_per_side', 0.0):.4f}\n"
            f"- Slippage ticks per side: {backtest.get('slippage_ticks', 0.0):.4f}\n"
            f"- Metrics basis: {backtest.get('metrics_basis', '—')}\n"
        )

    section += f"\n### Grid Search\n- Available: {'yes' if grid.get('available') else 'no'}\n"
    if grid.get("available"):
        section += (
            f"- Commission per side: {grid.get('commission_per_side', 0.0):.4f}\n"
            f"- Slippage ticks per side: {grid.get('slippage_ticks', 0.0):.4f}\n"
            f"- Metrics basis: {grid.get('metrics_basis', '—')}\n"
        )
    return section


def build_session_exit_policy_assumptions(
    session_state: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return scoped session-exit assumptions for current backtest/grid export data."""
    backtest_results_available = _has_nonempty_value(
        session_state.get("trades")
    ) or _has_nonempty_value(session_state.get("trade_summary"))
    grid_results_available = _has_nonempty_value(
        session_state.get("grid_results")
    ) or _has_nonempty_value(session_state.get("best_grid_result"))

    backtest_policy = session_state.get("backtest_session_exit_policy")
    grid_policy = session_state.get("grid_session_exit_policy")
    backtest_available = (
        backtest_results_available
        and isinstance(backtest_policy, Mapping)
        and len(backtest_policy) > 0
    )
    grid_available = (
        grid_results_available and isinstance(grid_policy, Mapping) and len(grid_policy) > 0
    )

    assumptions: dict[str, dict[str, Any]] = {
        "backtest": {
            "available": backtest_available,
            "flat_by_session_close": False,
            "session_close_time": None,
            "session_timezone": None,
            "no_new_entries_after": None,
        },
        "grid": {
            "available": grid_available,
            "flat_by_session_close": False,
            "session_close_time": None,
            "session_timezone": None,
            "no_new_entries_after": None,
        },
    }

    if backtest_available:
        assumptions["backtest"].update(
            {
                "flat_by_session_close": bool(backtest_policy.get("flat_by_session_close", False)),
                "session_close_time": to_jsonable(backtest_policy.get("session_close_time")),
                "session_timezone": to_jsonable(backtest_policy.get("session_timezone")),
                "no_new_entries_after": to_jsonable(backtest_policy.get("no_new_entries_after")),
            }
        )
    if grid_available:
        assumptions["grid"].update(
            {
                "flat_by_session_close": bool(grid_policy.get("flat_by_session_close", False)),
                "session_close_time": to_jsonable(grid_policy.get("session_close_time")),
                "session_timezone": to_jsonable(grid_policy.get("session_timezone")),
                "no_new_entries_after": to_jsonable(grid_policy.get("no_new_entries_after")),
            }
        )

    return assumptions


def session_exit_policy_assumptions_markdown(assumptions: Mapping[str, Mapping[str, Any]]) -> str:
    """Render scoped session-exit assumptions as markdown report section text."""
    backtest = assumptions.get("backtest", {})
    grid = assumptions.get("grid", {})

    section = (
        "\n## Session Exit Policy Assumptions\n"
        "\n### Backtest\n"
        f"- Available: {'yes' if backtest.get('available') else 'no'}\n"
    )
    if backtest.get("available"):
        section += (
            f"- Flat by session close: {'yes' if backtest.get('flat_by_session_close') else 'no'}\n"
            f"- Session close time: {backtest.get('session_close_time', '—') or '—'}\n"
            f"- Session timezone: {backtest.get('session_timezone', '—') or '—'}\n"
            f"- No new entries after: {backtest.get('no_new_entries_after', '—') or '—'}\n"
        )

    section += f"\n### Grid Search\n- Available: {'yes' if grid.get('available') else 'no'}\n"
    if grid.get("available"):
        section += (
            f"- Flat by session close: {'yes' if grid.get('flat_by_session_close') else 'no'}\n"
            f"- Session close time: {grid.get('session_close_time', '—') or '—'}\n"
            f"- Session timezone: {grid.get('session_timezone', '—') or '—'}\n"
            f"- No new entries after: {grid.get('no_new_entries_after', '—') or '—'}\n"
        )
    return section


def build_exposure_policy_assumptions(
    session_state: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return scoped exposure-policy assumptions for current backtest/grid export data."""
    backtest_results_available = _has_nonempty_value(
        session_state.get("trades")
    ) or _has_nonempty_value(session_state.get("trade_summary"))
    grid_results_available = _has_nonempty_value(
        session_state.get("grid_results")
    ) or _has_nonempty_value(session_state.get("best_grid_result"))

    backtest_policy = session_state.get("exposure_policy")
    grid_policy = session_state.get("grid_exposure_policy")
    skipped_signals = session_state.get("skipped_signals")

    backtest_available = (
        backtest_results_available
        and isinstance(backtest_policy, Mapping)
        and len(backtest_policy) > 0
    )
    grid_available = (
        grid_results_available and isinstance(grid_policy, Mapping) and len(grid_policy) > 0
    )

    skipped_signal_count = (
        int(len(skipped_signals)) if isinstance(skipped_signals, pd.DataFrame) else 0
    )

    assumptions: dict[str, dict[str, Any]] = {
        "backtest": {
            "available": backtest_available,
            "exposure_policy": None,
            "cooldown_bars_after_exit": None,
            "skipped_signal_count": 0,
        },
        "grid": {
            "available": grid_available,
            "exposure_policy": None,
            "cooldown_bars_after_exit": None,
        },
    }

    if backtest_available:
        assumptions["backtest"].update(
            {
                "exposure_policy": to_jsonable(backtest_policy.get("exposure_policy")),
                "cooldown_bars_after_exit": int(backtest_policy.get("cooldown_bars_after_exit", 0)),
                "skipped_signal_count": skipped_signal_count,
            }
        )
    if grid_available:
        assumptions["grid"].update(
            {
                "exposure_policy": to_jsonable(grid_policy.get("exposure_policy")),
                "cooldown_bars_after_exit": int(grid_policy.get("cooldown_bars_after_exit", 0)),
            }
        )

    return assumptions


def exposure_policy_assumptions_markdown(assumptions: Mapping[str, Mapping[str, Any]]) -> str:
    """Render scoped exposure-policy assumptions as markdown report section text."""
    backtest = assumptions.get("backtest", {})
    grid = assumptions.get("grid", {})

    section = (
        "\n## Exposure Policy Assumptions\n"
        "\n### Backtest\n"
        f"- Available: {'yes' if backtest.get('available') else 'no'}\n"
    )
    if backtest.get("available"):
        section += (
            f"- Exposure policy: {backtest.get('exposure_policy') or '—'}\n"
            f"- Cooldown bars after exit: {backtest.get('cooldown_bars_after_exit', '—')}\n"
            f"- Skipped signal count: {backtest.get('skipped_signal_count', 0)}\n"
        )

    section += f"\n### Grid Search\n- Available: {'yes' if grid.get('available') else 'no'}\n"
    if grid.get("available"):
        section += (
            f"- Exposure policy: {grid.get('exposure_policy') or '—'}\n"
            f"- Cooldown bars after exit: {grid.get('cooldown_bars_after_exit', '—')}\n"
        )

    return section


def _entry_window_markdown_section(entry_meta: Mapping[str, Any] | None) -> str:
    """Render Focus / Admit entry-window metadata as a markdown report section."""
    if not isinstance(entry_meta, Mapping) or not entry_meta.get("available"):
        return (
            "\n## Entry Window (Focus / Admit)\n"
            "- Status: not available (no Focus/Admit window data in session)\n"
        )

    admit = entry_meta.get("admit") if isinstance(entry_meta.get("admit"), Mapping) else {}
    focus = entry_meta.get("focus") if isinstance(entry_meta.get("focus"), Mapping) else {}
    promote = entry_meta.get("promote") if isinstance(entry_meta.get("promote"), Mapping) else {}
    grid = entry_meta.get("grid") if isinstance(entry_meta.get("grid"), Mapping) else {}

    lines = [
        "\n## Entry Window (Focus / Admit)\n",
        "- **Honesty:** Focus is a post-hoc trade subset — not a constrained "
        "re-simulation and not proof of deployable edge. Admit requires "
        "re-simulation under `entry_window`.\n",
    ]

    if focus.get("enabled"):
        focus_prov = focus.get("provenance") if isinstance(focus.get("provenance"), Mapping) else {}
        lines.append("- Focus status: enabled (post-hoc subset)\n")
        lines.append(f"- Focus window: {_dash_if_none(focus.get('label'))}\n")
        lines.append(
            f"- Focus trades: {_dash_if_none(focus_prov.get('trade_count_after'))} / "
            f"{_dash_if_none(focus_prov.get('trade_count_before'))} "
            f"(sample_warning={_dash_if_none(focus_prov.get('sample_warning'))})\n"
        )
        if focus.get("honesty_banner"):
            lines.append(f"- Focus banner: {focus.get('honesty_banner')}\n")
    else:
        lines.append("- Focus status: disabled / not set\n")

    if admit.get("enabled"):
        armed = "yes" if admit.get("armed") else "no"
        lines.append(f"- Admit status: enabled (armed={armed})\n")
        lines.append(f"- Admit window: {_dash_if_none(admit.get('label'))}\n")
        if admit.get("honesty_banner"):
            lines.append(f"- Admit banner: {admit.get('honesty_banner')}\n")
    else:
        lines.append("- Admit status: disabled / not set (legacy all-day admission)\n")

    if promote.get("available"):
        promote_prov = (
            promote.get("provenance") if isinstance(promote.get("provenance"), Mapping) else {}
        )
        lines.append(
            f"- Promote provenance: source={_dash_if_none(promote_prov.get('source'))}, "
            f"status={_dash_if_none(promote_prov.get('status'))}\n"
        )
    if grid.get("enabled"):
        lines.append(f"- Grid inherited window: {_dash_if_none(grid.get('label'))}\n")

    return "".join(lines)


def _otf_markdown_section(otf_meta: Mapping[str, Any] | None) -> str:
    """Render OTF filter metadata as a markdown report section."""
    if not isinstance(otf_meta, Mapping) or not otf_meta.get("available"):
        return "\n## OTF Filter\n- Status: not available (no OTF filter data in session)\n"

    enabled = otf_meta.get("enabled")
    if enabled is None:
        return "\n## OTF Filter\n- Status: not available\n"

    if not enabled:
        return (
            "\n## OTF Filter\n"
            "- Status: disabled\n"
            "- All candidate signals passed through to simulation unchanged.\n"
        )

    config = otf_meta.get("config") or {}
    timeframes = config.get("timeframes", []) if isinstance(config, Mapping) else []
    tf_str = ", ".join(timeframes) if timeframes else "—"
    min_bars = _dash_if_none(
        config.get("minimum_consecutive_bars") if isinstance(config, Mapping) else None
    )
    algorithm_version = _dash_if_none(otf_meta.get("algorithm_version"))
    config_hash = otf_meta.get("config_hash") or "—"
    config_hash_short = str(config_hash)[:12] if config_hash != "—" else "—"
    candidate_count = _dash_if_none(otf_meta.get("candidate_signal_count"))
    accepted_count = _dash_if_none(otf_meta.get("accepted_signal_count"))
    rejected_count = _dash_if_none(otf_meta.get("rejected_signal_count"))
    rejection_rate = otf_meta.get("rejection_rate")
    applied_scopes = otf_meta.get("applied_scopes") or []

    rejection_rate_str = format(float(rejection_rate), ".1%") if rejection_rate is not None else "—"

    return (
        "\n## OTF Filter\n"
        "- Status: enabled\n"
        f"- Selected timeframes: {tf_str}\n"
        f"- Minimum consecutive bars: {min_bars}\n"
        f"- Algorithm version: {algorithm_version}\n"
        f"- Config hash (prefix): {config_hash_short}\n"
        f"- Applied to scopes: {', '.join(applied_scopes) or '—'}\n"
        f"- Candidate signals: {candidate_count}\n"
        f"- Accepted signals: {accepted_count}\n"
        f"- Rejected signals: {rejected_count}\n"
        f"- Rejection rate: {rejection_rate_str}\n"
        "- Note: OTF rejected signals are distinct from exposure-policy skips "
        "and 3c void signal status.\n"
    )


def _markdown_records_table(
    rows: Any,
    columns: list[str],
    *,
    pct_cols: set[str] | None = None,
    number_cols: set[str] | None = None,
) -> str:
    """Render list-of-dict records as a compact markdown table."""
    if not isinstance(rows, list) or not rows:
        return "_No rows._\n"
    pct_cols = pct_cols or set()
    number_cols = number_cols or set()
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cells: list[str] = []
        for col in columns:
            val = row.get(col)
            if val is None:
                cells.append("—")
            elif col in pct_cols:
                cells.append(_fmt_pct(val))
            elif col in number_cols or isinstance(val, float):
                cells.append(_fmt_number(val))
            elif isinstance(val, bool):
                cells.append("yes" if val else "no")
            else:
                cells.append(str(val).replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    if len(lines) == 2:
        return "_No rows._\n"
    return "\n".join(lines) + "\n"


def _confluence_combo_markdown_section(block: Mapping[str, Any] | None) -> str:
    """Render confluence combo attribution as a markdown report section.

    Returns an empty string when unavailable so existing report output is
    unchanged (OTF-validation omit style).
    """
    if not isinstance(block, Mapping) or not block.get("available"):
        return ""

    tables = block.get("tables") if isinstance(block.get("tables"), Mapping) else {}
    warnings = [str(w) for w in list(block.get("warnings") or []) if w]
    top_n = int(block.get("top_n") or _CONFLUENCE_COMBO_TOP_N_DEFAULT)
    mode = _dash_if_none(block.get("confluence_mode"))
    anchor = _dash_if_none(block.get("anchor_level"))
    pair_mode = _dash_if_none(block.get("pair_mode"))

    metric_number_cols = {"avg_r", "median_r", "total_r"}
    metric_pct_cols = {"win_rate"}

    lines = [
        "## Confluence Combo Attribution",
        "⚠️ **Diagnostic only — observed traded combinations from recorded "
        "`level_names`, not all theoretical subsets. Sorting by total R invites "
        "selection effects; not proof of future edge.**",
        "",
        f"- Analyzable trades: {_dash_if_none(block.get('trade_count'))}",
        f"- Non-empty combos: {_dash_if_none(block.get('nonempty_combo_trade_count'))}",
        f"- Empty level_names rows: {_dash_if_none(block.get('empty_level_names_count'))}",
        f"- Confluence mode: {mode}",
        f"- Anchor level: {anchor}",
        f"- Pair mode: {pair_mode}",
        "",
    ]

    if warnings:
        lines.append("### Warnings")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(
        [
            f"### Exact combo (top {top_n} by |total_r|)",
            "Rows are canonical observed combinations; `A|B` and `B|A` merge.",
            "",
            _markdown_records_table(
                tables.get("exact_combo"),
                [
                    "display_combo",
                    EXACT_COMBO_KEY_COL,
                    "trade_count",
                    "win_rate",
                    "avg_r",
                    "median_r",
                    "total_r",
                    "sample_warning",
                ],
                pct_cols=metric_pct_cols,
                number_cols=metric_number_cols,
            ).rstrip(),
            "",
            "### Parsed level count",
            "View-C parsed distinct token count from `level_names` "
            "(not stored zone `level_count`).",
            "",
            _markdown_records_table(
                tables.get("level_count"),
                [
                    LEVEL_COUNT_BUCKET_COL,
                    "trade_count",
                    "win_rate",
                    "avg_r",
                    "median_r",
                    "total_r",
                    "sample_warning",
                ],
                pct_cols=metric_pct_cols,
                number_cols=metric_number_cols,
            ).rstrip(),
            "",
            f"### Membership (top {top_n} by |total_r|)",
            f"⚠️ {MEMBERSHIP_DOUBLE_COUNT_WARNING}",
            "",
            _markdown_records_table(
                tables.get("membership"),
                [
                    LEVEL_NAME_COL,
                    "trade_count",
                    "win_rate",
                    "avg_r",
                    "median_r",
                    "total_r",
                    "sample_warning",
                ],
                pct_cols=metric_pct_cols,
                number_cols=metric_number_cols,
            ).rstrip(),
            "",
            f"### Soft pairs (top {top_n} by |total_r|)",
            f"⚠️ {PAIRWISE_DOUBLE_COUNT_WARNING}",
            "",
            _markdown_records_table(
                tables.get("pairs"),
                [
                    PAIR_KEY_COL,
                    PAIR_MODE_COL,
                    "trade_count",
                    "win_rate",
                    "avg_r",
                    "median_r",
                    "total_r",
                    "sample_warning",
                ],
                pct_cols=metric_pct_cols,
                number_cols=metric_number_cols,
            ).rstrip(),
            "",
        ]
    )
    return "\n".join(lines)


def _otf_validation_markdown_section(otf_val: Mapping[str, Any] | None) -> str:
    """Render OTF validation results as a markdown report section.

    Returns an empty string when OTF validation has not been run so existing
    report output is unchanged.
    """
    if not isinstance(otf_val, Mapping) or not otf_val.get("available"):
        return ""

    summary = otf_val.get("summary") or {}
    config = otf_val.get("config") or {}

    try:
        train_frac_str = format(float(config.get("train_fraction")), ".0%")
    except (TypeError, ValueError):
        train_frac_str = "—"
    try:
        oos_frac_str = format(float(config.get("oos_fraction")), ".0%")
    except (TypeError, ValueError):
        oos_frac_str = "—"
    sl_ticks = _dash_if_none(config.get("sl_ticks"))
    tp_ticks = _dash_if_none(config.get("tp_ticks"))
    session_tz = _dash_if_none(config.get("session_timezone"))

    selected_label = _dash_if_none(summary.get("selected_train_config"))
    selected_oos = summary.get("selected_oos_expectancy_r")
    selected_oos_str = _fmt_number(selected_oos) if selected_oos is not None else "—"
    train_metric = _dash_if_none(summary.get("selected_by_train_metric"))

    section = (
        "\n## OTF Validation Matrix\n"
        "⚠️ **Diagnostic only — not proof of edge.  Do not select an OTF "
        "configuration for production use based on these results.**\n\n"
        "### Configurations tested\n"
        "1. no_otf — OTF filter disabled (baseline)\n"
        "2. otf_15m — 15m only\n"
        "3. otf_30m — 30m only\n"
        "4. otf_15m_30m — 15m + 30m\n"
        "5. otf_5m_15m_30m — 5m + 15m + 30m\n"
        "\n### Split methodology\n"
        f"- Train fraction: {train_frac_str}\n"
        f"- OOS fraction: {oos_frac_str}\n"
        f"- SL ticks: {sl_ticks}\n"
        f"- TP ticks: {tp_ticks}\n"
        f"- Session timezone: {session_tz}\n"
        "\n### Selection (train metrics only)\n"
        f"- Selection metric: {train_metric}\n"
        f"- Train-selected configuration: {selected_label}\n"
        f"- OOS expectancy (train-selected config): {selected_oos_str} R\n"
        "\n### Caveats\n"
        "- Configuration selection uses train metrics only; OOS metrics are "
        "provided for evaluation only.\n"
        "- OOS performance is not proof of edge.\n"
        "- Lower trade count alone is not an improvement.\n"
        "- Multiple-comparison caution: comparing 5 configurations increases "
        "the risk of spurious results.\n"
        "- Minimum sample-size caution: small trade counts make all metrics "
        "unreliable.\n"
        "- See the full OTF validation matrix in the artifact tables section.\n"
    )
    return section


def build_markdown_report(artifact: dict[str, Any]) -> str:
    """Build a concise markdown report from a research artifact."""
    metadata = artifact.get("metadata", {}) if isinstance(artifact, Mapping) else {}
    config = artifact.get("configuration", {}) if isinstance(artifact, Mapping) else {}
    data_quality = artifact.get("data_quality", {}) if isinstance(artifact, Mapping) else {}
    results = artifact.get("results", {}) if isinstance(artifact, Mapping) else {}
    tables = artifact.get("tables", {}) if isinstance(artifact, Mapping) else {}
    otf_meta = artifact.get("otf_filter") if isinstance(artifact, Mapping) else None
    entry_window_meta = artifact.get("entry_window") if isinstance(artifact, Mapping) else None

    setup = config.get("setup_config") or {}
    trade_summary = results.get("trade_summary") or {}
    best_grid = results.get("best_grid_result") or {}
    validation = results.get("validation_summary") or {}
    excursion = results.get("excursion_summary") or {}
    monte_carlo = results.get("monte_carlo_summary") or {}
    noise = results.get("noise_summary") or {}
    overfitting = results.get("overfitting_summary") or {}
    sensitivity = results.get("sensitivity_summary") or {}
    portfolio = results.get("portfolio_summary") or {}
    walk_forward = results.get("walk_forward_summary") or {}
    intrabar = artifact.get("intrabar", {}) if isinstance(artifact, Mapping) else {}
    intrabar_policy = intrabar.get("backtest_policy", {}) if isinstance(intrabar, Mapping) else {}
    intrabar_diagnostic = (
        intrabar.get("backtest_diagnostic", {}) if isinstance(intrabar, Mapping) else {}
    )
    exit_management = artifact.get("exit_management", {}) if isinstance(artifact, Mapping) else {}
    exit_mgmt_policy = (
        exit_management.get("backtest_policy", {}) if isinstance(exit_management, Mapping) else {}
    )
    exit_mgmt_diagnostic = (
        exit_management.get("backtest_diagnostic", {})
        if isinstance(exit_management, Mapping)
        else {}
    )

    selected_levels = setup.get("selected_levels") if isinstance(setup, Mapping) else None
    levels_str = (
        ", ".join(selected_levels) if isinstance(selected_levels, list) and selected_levels else "—"
    )

    grid_metric_name, grid_metric_value = _best_grid_metric(best_grid)

    bootstrap = validation.get("bootstrap") if isinstance(validation, Mapping) else {}
    permutation = validation.get("permutation") if isinstance(validation, Mapping) else {}
    trade_count_diag = validation.get("trade_count") if isinstance(validation, Mapping) else {}
    grid_overfit = validation.get("grid_overfit") if isinstance(validation, Mapping) else {}
    roll_policy = config.get("roll_policy") if isinstance(config, Mapping) else {}
    roll_validation = (
        data_quality.get("roll_validation") if isinstance(data_quality, Mapping) else {}
    )

    lines = [
        "# ThesisTester Research Report",
        "",
        "## Metadata",
        f"- Generated at: {metadata.get('generated_at', '—')}",
        f"- App: {metadata.get('app', 'ThesisTester')}",
        f"- Schema version: {metadata.get('schema_version', '—')}",
        "",
        "## Setup Configuration",
        f"- Instrument: {config.get('instrument', '—')}",
        f"- Setup name: {setup.get('name', '—') if isinstance(setup, Mapping) else '—'}",
        f"- Selected levels: {levels_str}",
        f"- Trigger: {setup.get('trigger', '—') if isinstance(setup, Mapping) else '—'}",
        f"- Direction: {setup.get('direction', '—') if isinstance(setup, Mapping) else '—'}",
        f"- Naked only: {setup.get('naked_only', '—') if isinstance(setup, Mapping) else '—'}",
        (
            f"- Confluence settings: min={setup.get('min_confluences', '—')}, "
            f"max={setup.get('max_confluences', '—')}, "
            f"tolerance_ticks={setup.get('tolerance_ticks', '—')}"
            if isinstance(setup, Mapping)
            else "- Confluence settings: —"
        ),
        "",
        "## Signal Summary",
        f"- Signal count: {results.get('signal_count', 0)}",
        f"- Signal table rows exported: {len(tables.get('signals', [])) if isinstance(tables.get('signals', []), list) else 0}",
        "",
        "## Backtest Summary",
        f"- Trade count: {results.get('trade_count', 0)}",
        f"- Win rate: {_fmt_pct(trade_summary.get('win_rate') if isinstance(trade_summary, Mapping) else None)}",
        f"- Avg R: {_fmt_number(trade_summary.get('avg_r') if isinstance(trade_summary, Mapping) else None)}",
        f"- Total R: {_fmt_number(trade_summary.get('total_r') if isinstance(trade_summary, Mapping) else None)}",
        f"- Profit factor: {_fmt_number(trade_summary.get('profit_factor') if isinstance(trade_summary, Mapping) else None)}",
        f"- Max drawdown R: {_fmt_number(trade_summary.get('max_drawdown_r') if isinstance(trade_summary, Mapping) else None)}",
        "",
        "### Intrabar Resolution",
        f"- Model: {intrabar_policy.get('intrabar_model', 'sl_first') if isinstance(intrabar_policy, Mapping) else 'sl_first'}",
        f"- Same-bar both-hit exits: {intrabar_diagnostic.get('same_bar_both_hit_count', 0) if isinstance(intrabar_diagnostic, Mapping) else 0}",
        f"- Residual ambiguous resolutions: {intrabar_diagnostic.get('ambiguous_resolution_count', 0) if isinstance(intrabar_diagnostic, Mapping) else 0}",
        f"- Lower-data fallback parent bars: {intrabar_diagnostic.get('subtimeframe_fallback_parent_count', 0) if isinstance(intrabar_diagnostic, Mapping) else 0}",
        f"- Lower-data fallback exits: {intrabar_diagnostic.get('subtimeframe_fallback_exit_count', 0) if isinstance(intrabar_diagnostic, Mapping) else 0}",
        "- Deterministic OHLC paths are assumptions, not reconstructed market paths.",
        "",
        "### Exit Management",
        f"- Break-even after R: {exit_mgmt_policy.get('breakeven_after_r', 'off') if isinstance(exit_mgmt_policy, Mapping) else 'off'}",
        f"- Trailing after R: {exit_mgmt_policy.get('trailing_after_r', 'off') if isinstance(exit_mgmt_policy, Mapping) else 'off'}",
        f"- BE exits: {exit_mgmt_diagnostic.get('be_exit_count', 0) if isinstance(exit_mgmt_diagnostic, Mapping) else 0}",
        f"- TRAIL exits: {exit_mgmt_diagnostic.get('trail_exit_count', 0) if isinstance(exit_mgmt_diagnostic, Mapping) else 0}",
        "",
        "## Walk-Forward / OOS Diagnostics",
        f"- Fold mode: {(config.get('walk_forward_config') or {}).get('fold_mode', 'bars') if isinstance(config.get('walk_forward_config'), Mapping) else 'bars'}",
        f"- Window mode: {(config.get('walk_forward_config') or {}).get('window_mode', 'rolling') if isinstance(config.get('walk_forward_config'), Mapping) else 'rolling'}",
        f"- Valid folds: {walk_forward.get('valid_fold_count', 0) if isinstance(walk_forward, Mapping) else 0}",
        f"- Median OOS expectancy R: {_fmt_number(walk_forward.get('median_test_expectancy_r') if isinstance(walk_forward, Mapping) else None)}",
        f"- Median expectancy retention ratio: {_fmt_number(walk_forward.get('median_retention_ratio_expectancy') if isinstance(walk_forward, Mapping) else None)}",
        f"- Stitched OOS total R: {_fmt_number(walk_forward.get('stitched_oos_total_r') if isinstance(walk_forward, Mapping) else None)}",
        f"- Stitched OOS status: {walk_forward.get('stitched_oos_status', 'unavailable') if isinstance(walk_forward, Mapping) else 'unavailable'}",
        "",
        "## Overfitting-Detection Battery",
        f"- PBO: {_fmt_pct((overfitting.get('pbo') or {}).get('pbo') if isinstance(overfitting, Mapping) else None)}",
        f"- Deflated Sharpe probability: {_fmt_pct((overfitting.get('deflated_sharpe') or {}).get('dsr') if isinstance(overfitting, Mapping) else None)}",
        f"- Vs-random p-value: {_fmt_number((overfitting.get('vs_random') or {}).get('p_value_greater_or_equal') if isinstance(overfitting, Mapping) else None)}",
        "- CSCV, DSR, and vs-random are diagnostics on declared historical trials/nulls, not proof of future edge.",
        "",
        "### Advanced Risk Metrics",
        f"- Sharpe-like R: {_fmt_number(trade_summary.get('sharpe_like_r') if isinstance(trade_summary, Mapping) else None)}",
        f"- Sortino-like R: {_fmt_number(trade_summary.get('sortino_like_r') if isinstance(trade_summary, Mapping) else None)}",
        f"- Ulcer index R: {_fmt_number(trade_summary.get('ulcer_index_r') if isinstance(trade_summary, Mapping) else None)}",
        f"- Recovery factor: {_fmt_number(trade_summary.get('recovery_factor') if isinstance(trade_summary, Mapping) else None)}",
        f"- Tail ratio: {_fmt_number(trade_summary.get('tail_ratio') if isinstance(trade_summary, Mapping) else None)}",
        f"- Outlier dependency ratio: {_fmt_number(trade_summary.get('outlier_dependency_ratio') if isinstance(trade_summary, Mapping) else None)}",
        "",
        "## Grid Search Summary",
        f"- Grid rows exported: {len(tables.get('grid_results', [])) if isinstance(tables.get('grid_results', []), list) else 0}",
        f"- Best SL ticks: {best_grid.get('stop_loss_ticks', '—') if isinstance(best_grid, Mapping) else '—'}",
        f"- Best TP ticks: {best_grid.get('take_profit_ticks', '—') if isinstance(best_grid, Mapping) else '—'}",
        f"- Best metric: {grid_metric_name or '—'} = {_fmt_number(grid_metric_value)}",
        "",
        "## Time Analysis Summary",
        f"- Grouped summary rows exported: {len(tables.get('time_grouped_summary', [])) if isinstance(tables.get('time_grouped_summary', []), list) else 0}",
        "",
        "## Validation Diagnostics",
        f"- Bootstrap CI: [{_fmt_number(bootstrap.get('ci_lower') if isinstance(bootstrap, Mapping) else None)}, {_fmt_number(bootstrap.get('ci_upper') if isinstance(bootstrap, Mapping) else None)}]",
        f"- P(mean R > 0): {_fmt_pct(bootstrap.get('probability_positive') if isinstance(bootstrap, Mapping) else None)}",
        f"- Permutation p-value (positive): {_fmt_number(permutation.get('p_value_positive') if isinstance(permutation, Mapping) else None)}",
        f"- Trade-count status: {trade_count_diag.get('status', '—') if isinstance(trade_count_diag, Mapping) else '—'}",
        f"- Grid overfit risk: {grid_overfit.get('risk_level', '—') if isinstance(grid_overfit, Mapping) else '—'}",
        "",
    ]

    if isinstance(excursion, Mapping) and excursion.get("available"):
        edge_ratio = excursion.get("edge_ratio") if isinstance(excursion, Mapping) else {}
        config_exc = excursion.get("config") if isinstance(excursion, Mapping) else {}
        lines.extend(
            [
                "## Excursion Analytics",
                "⚠️ Diagnostic only — terminal bar-level MAE/MFE cannot prove intrabar order.",
                "",
                f"- Trades with excursions: {excursion.get('trade_count', 0)}",
                f"- Mean MAE (R): {_fmt_number(edge_ratio.get('mean_mae_r') if isinstance(edge_ratio, Mapping) else None)}",
                f"- Mean MFE (R): {_fmt_number(edge_ratio.get('mean_mfe_r') if isinstance(edge_ratio, Mapping) else None)}",
                f"- Mean edge ratio: {_fmt_number(edge_ratio.get('mean_edge_ratio_r') if isinstance(edge_ratio, Mapping) else None)}",
                f"- Median edge ratio: {_fmt_number(edge_ratio.get('median_edge_ratio_r') if isinstance(edge_ratio, Mapping) else None)}",
                f"- Calibration both-hit rule: {config_exc.get('both_hit_rule', '—') if isinstance(config_exc, Mapping) else '—'}",
                f"- Grouped summary rows exported: {len(tables.get('excursion_grouped_summary', [])) if isinstance(tables.get('excursion_grouped_summary', []), list) else 0}",
                f"- Calibration grid rows exported: {len(tables.get('excursion_calibration_grid', [])) if isinstance(tables.get('excursion_calibration_grid', []), list) else 0}",
                "",
            ]
        )

    if isinstance(monte_carlo, Mapping) and monte_carlo.get("available"):
        mc_methods = monte_carlo.get("methods") if isinstance(monte_carlo, Mapping) else {}
        mc_config = monte_carlo.get("config") if isinstance(monte_carlo, Mapping) else {}
        lines.extend(
            [
                "## Monte Carlo Path Robustness",
                "⚠️ Diagnostic only — resamples the realized trade sequence and does not prove edge.",
                "",
                f"- Trades: {monte_carlo.get('trade_count', 0)}",
                f"- Simulations per method: {mc_config.get('n_simulations', '—') if isinstance(mc_config, Mapping) else '—'}",
                f"- Methods: {', '.join(mc_methods.keys()) if isinstance(mc_methods, Mapping) else '—'}",
            ]
        )
        if isinstance(mc_methods, Mapping):
            for method_name, method in mc_methods.items():
                observed = method.get("observed", {}) if isinstance(method, Mapping) else {}
                simulated = method.get("simulated", {}) if isinstance(method, Mapping) else {}
                max_dd = (
                    simulated.get("max_drawdown_r", {}) if isinstance(simulated, Mapping) else {}
                )
                loss_streak = (
                    simulated.get("max_loss_streak", {}) if isinstance(simulated, Mapping) else {}
                )
                lines.extend(
                    [
                        f"- {method_name}: observed final R {_fmt_number(observed.get('final_r') if isinstance(observed, Mapping) else None)}, "
                        f"P95 max DD {_fmt_number(max_dd.get('p95') if isinstance(max_dd, Mapping) else None)}, "
                        f"P95 loss streak {_fmt_number(loss_streak.get('p95') if isinstance(loss_streak, Mapping) else None, '.0f')}",
                    ]
                )
        lines.append("")

    if isinstance(noise, Mapping) and noise.get("available"):
        replicas = noise.get("replicas") if isinstance(noise, Mapping) else {}
        noise_config = noise.get("config") if isinstance(noise, Mapping) else {}
        expectancy = replicas.get("expectancy_r", {}) if isinstance(replicas, Mapping) else {}
        persistence = (
            replicas.get("trade_persistence_rate", {}) if isinstance(replicas, Mapping) else {}
        )
        lines.extend(
            [
                "## Price-Series Noise Test",
                "⚠️ Diagnostic only — perturbs OHLC input and reruns the full pipeline; it does not prove edge.",
                "",
                f"- Replicas: {replicas.get('n_completed', 0) if isinstance(replicas, Mapping) else 0}",
                f"- Noise: {noise_config.get('noise_fraction', '—') if isinstance(noise_config, Mapping) else '—'} × {noise_config.get('scale_basis', '—') if isinstance(noise_config, Mapping) else '—'}",
                f"- P50 expectancy R: {_fmt_number(expectancy.get('p50') if isinstance(expectancy, Mapping) else None)}",
                f"- P50 trade persistence: {_fmt_pct(persistence.get('p50') if isinstance(persistence, Mapping) else None)}",
                "",
            ]
        )

    if isinstance(sensitivity, Mapping) and sensitivity.get("available"):
        profiles = sensitivity.get("parameters") if isinstance(sensitivity, Mapping) else []
        fragile_count = sensitivity.get("fragile_parameter_count", 0)
        lines.extend(
            [
                "## Parameter Sensitivity (SPP-lite)",
                "⚠️ Diagnostic only — local one-at-a-time execution-parameter changes do not measure interactions or prove edge.",
                "",
                f"- Parameters profiled: {len(profiles) if isinstance(profiles, list) else 0}",
                f"- Fragile parameters: {fragile_count}",
                f"- Baseline expectancy R: {_fmt_number((sensitivity.get('baseline') or {}).get('expectancy_r') if isinstance(sensitivity.get('baseline'), Mapping) else None)}",
                "",
            ]
        )

    if isinstance(portfolio, Mapping) and portfolio.get("available"):
        portfolio_metrics = portfolio.get("portfolio_metrics") or {}
        admission = portfolio.get("admission") or {}
        lines.extend(
            [
                "## Multi-Setup Portfolio",
                "⚠️ Diagnostic only — post-hoc completed-trade merge, not a capital or fill simulation.",
                "",
                f"- Setup count: {len((portfolio.get('config') or {}).get('setup_ids', []))}",
                f"- Portfolio total R: {_fmt_number(portfolio_metrics.get('total_r') if isinstance(portfolio_metrics, Mapping) else None)}",
                f"- Portfolio max drawdown R: {_fmt_number(portfolio_metrics.get('max_drawdown_r') if isinstance(portfolio_metrics, Mapping) else None)}",
                f"- Admitted / skipped trades: {admission.get('admitted_trade_count', 0) if isinstance(admission, Mapping) else 0} / {admission.get('skipped_trade_count', 0) if isinstance(admission, Mapping) else 0}",
                "",
            ]
        )

    if isinstance(roll_policy, Mapping) or isinstance(roll_validation, Mapping):
        lines.extend(
            [
                "## Futures Roll Assumptions",
                f"- Roll method: {roll_policy.get('roll_method', '—') if isinstance(roll_policy, Mapping) else '—'}",
                f"- Contract count: {roll_validation.get('contract_count', '—') if isinstance(roll_validation, Mapping) else '—'}",
                f"- Adjustment method: {roll_policy.get('adjustment_method', '—') if isinstance(roll_policy, Mapping) else '—'}",
                f"- Roll rule: {roll_policy.get('roll_rule', '—') if isinstance(roll_policy, Mapping) else '—'}",
                f"- Warning count: {len(roll_validation.get('warnings', [])) if isinstance(roll_validation, Mapping) and isinstance(roll_validation.get('warnings'), list) else 0}",
                f"- Roll gap count: {roll_validation.get('roll_gap_count', 0) if isinstance(roll_validation, Mapping) else 0}",
                "",
            ]
        )

    # Entry window (Focus / Admit) section
    lines.append(_entry_window_markdown_section(entry_window_meta).strip())
    lines.append("")

    # OTF filter section
    lines.append(_otf_markdown_section(otf_meta).strip())
    lines.append("")

    # OTF validation section — omit entirely when validation was not run.
    otf_val = artifact.get("otf_validation") if isinstance(artifact, Mapping) else None
    otf_val_section = _otf_validation_markdown_section(otf_val).strip()
    if otf_val_section:
        lines.append(otf_val_section)
        lines.append("")

    # Confluence combo attribution — omit entirely when unavailable.
    confluence_combo = (
        artifact.get("confluence_combo") if isinstance(artifact, Mapping) else None
    )
    confluence_section = _confluence_combo_markdown_section(confluence_combo).strip()
    if confluence_section:
        lines.append(confluence_section)
        lines.append("")

    lines.append("## Caveats")

    for caveat in artifact.get("caveats", []):
        lines.append(f"- {caveat}")

    return "\n".join(lines).strip() + "\n"
