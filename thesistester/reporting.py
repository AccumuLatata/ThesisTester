"""Phase 9 reporting/export helpers for reproducible research artifacts."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from math import isinf, isnan
from typing import Any, Mapping

import numpy as np
import pandas as pd
from .timezone_display import convert_dataframe_timestamps_for_display, timezone_contract


_CAVEATS = [
    "Research output only; not trading advice.",
    "Backtests are based on historical data and assumptions.",
    "OHLC bars cannot resolve true intrabar event order; SL-first pessimistic rule is used where applicable.",
    "Grid search can overfit; validation diagnostics are descriptive only.",
    "No guarantee of future performance.",
]


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


def build_research_artifact(session_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build a consolidated JSON-safe research artifact from session state."""
    setup_config = session_state.get("setup_config")
    instrument = session_state.get("instrument")
    if instrument is None and isinstance(setup_config, Mapping):
        instrument = setup_config.get("instrument")

    contract = timezone_contract(dict(session_state))
    canonical_timezone = (
        contract.get("canonical_engine_timezone")
        or "America/New_York"
    )
    display_timezone = (
        contract.get("display_export_timezone")
        or canonical_timezone
    )

    artifact = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "app": "ThesisTester",
            "schema_version": "1.0",
        },
        "timezone_contract": contract,
        "configuration": {
            "instrument": to_jsonable(instrument),
            "setup_config": to_jsonable(setup_config),
            "last_signal_setup": to_jsonable(session_state.get("last_signal_setup")),
            "walk_forward_config": to_jsonable(session_state.get("walk_forward_config")),
        },
        "results": {
            "signal_count": _table_count(session_state, "signals"),
            "trade_count": _table_count(session_state, "trades"),
            "trade_summary": to_jsonable(session_state.get("trade_summary")),
            "best_grid_result": to_jsonable(session_state.get("best_grid_result")),
            "validation_summary": to_jsonable(session_state.get("validation_summary")),
            "walk_forward_summary": to_jsonable(session_state.get("walk_forward_summary")),
        },
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
        },
        "caveats": list(_CAVEATS),
    }
    return to_jsonable(artifact)


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
    backtest_results_available = _has_nonempty_value(session_state.get("trades")) or _has_nonempty_value(
        session_state.get("trade_summary")
    )
    grid_results_available = _has_nonempty_value(session_state.get("grid_results")) or _has_nonempty_value(
        session_state.get("best_grid_result")
    )

    backtest_costs = session_state.get("backtest_execution_costs")
    grid_costs = session_state.get("grid_execution_costs")
    backtest_available = (
        backtest_results_available
        and isinstance(backtest_costs, Mapping)
        and len(backtest_costs) > 0
    )
    grid_available = (
        grid_results_available
        and isinstance(grid_costs, Mapping)
        and len(grid_costs) > 0
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

    section += (
        "\n### Grid Search\n"
        f"- Available: {'yes' if grid.get('available') else 'no'}\n"
    )
    if grid.get("available"):
        section += (
            f"- Commission per side: {grid.get('commission_per_side', 0.0):.4f}\n"
            f"- Slippage ticks per side: {grid.get('slippage_ticks', 0.0):.4f}\n"
            f"- Metrics basis: {grid.get('metrics_basis', '—')}\n"
        )
    return section


def build_session_exit_policy_assumptions(session_state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return scoped session-exit assumptions for current backtest/grid export data."""
    backtest_results_available = _has_nonempty_value(session_state.get("trades")) or _has_nonempty_value(
        session_state.get("trade_summary")
    )
    grid_results_available = _has_nonempty_value(session_state.get("grid_results")) or _has_nonempty_value(
        session_state.get("best_grid_result")
    )

    backtest_policy = session_state.get("backtest_session_exit_policy")
    grid_policy = session_state.get("grid_session_exit_policy")
    backtest_available = (
        backtest_results_available
        and isinstance(backtest_policy, Mapping)
        and len(backtest_policy) > 0
    )
    grid_available = (
        grid_results_available
        and isinstance(grid_policy, Mapping)
        and len(grid_policy) > 0
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

    section += (
        "\n### Grid Search\n"
        f"- Available: {'yes' if grid.get('available') else 'no'}\n"
    )
    if grid.get("available"):
        section += (
            f"- Flat by session close: {'yes' if grid.get('flat_by_session_close') else 'no'}\n"
            f"- Session close time: {grid.get('session_close_time', '—') or '—'}\n"
            f"- Session timezone: {grid.get('session_timezone', '—') or '—'}\n"
            f"- No new entries after: {grid.get('no_new_entries_after', '—') or '—'}\n"
        )
    return section


def build_exposure_policy_assumptions(session_state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return scoped exposure-policy assumptions for current backtest/grid export data."""
    backtest_results_available = _has_nonempty_value(session_state.get("trades")) or _has_nonempty_value(
        session_state.get("trade_summary")
    )
    grid_results_available = _has_nonempty_value(session_state.get("grid_results")) or _has_nonempty_value(
        session_state.get("best_grid_result")
    )

    backtest_policy = session_state.get("exposure_policy")
    grid_policy = session_state.get("grid_exposure_policy")
    skipped_signals = session_state.get("skipped_signals")

    backtest_available = (
        backtest_results_available
        and isinstance(backtest_policy, Mapping)
        and len(backtest_policy) > 0
    )
    grid_available = (
        grid_results_available
        and isinstance(grid_policy, Mapping)
        and len(grid_policy) > 0
    )

    skipped_signal_count = (
        int(len(skipped_signals))
        if isinstance(skipped_signals, pd.DataFrame)
        else 0
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
                "cooldown_bars_after_exit": int(
                    backtest_policy.get("cooldown_bars_after_exit", 0)
                ),
                "skipped_signal_count": skipped_signal_count,
            }
        )
    if grid_available:
        assumptions["grid"].update(
            {
                "exposure_policy": to_jsonable(grid_policy.get("exposure_policy")),
                "cooldown_bars_after_exit": int(
                    grid_policy.get("cooldown_bars_after_exit", 0)
                ),
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

    section += (
        "\n### Grid Search\n"
        f"- Available: {'yes' if grid.get('available') else 'no'}\n"
    )
    if grid.get("available"):
        section += (
            f"- Exposure policy: {grid.get('exposure_policy') or '—'}\n"
            f"- Cooldown bars after exit: {grid.get('cooldown_bars_after_exit', '—')}\n"
        )

    return section


def build_markdown_report(artifact: dict[str, Any]) -> str:
    """Build a concise markdown report from a research artifact."""
    metadata = artifact.get("metadata", {}) if isinstance(artifact, Mapping) else {}
    config = artifact.get("configuration", {}) if isinstance(artifact, Mapping) else {}
    results = artifact.get("results", {}) if isinstance(artifact, Mapping) else {}
    tables = artifact.get("tables", {}) if isinstance(artifact, Mapping) else {}

    setup = config.get("setup_config") or {}
    trade_summary = results.get("trade_summary") or {}
    best_grid = results.get("best_grid_result") or {}
    validation = results.get("validation_summary") or {}

    selected_levels = setup.get("selected_levels") if isinstance(setup, Mapping) else None
    levels_str = ", ".join(selected_levels) if isinstance(selected_levels, list) and selected_levels else "—"

    grid_metric_name, grid_metric_value = _best_grid_metric(best_grid)

    bootstrap = validation.get("bootstrap") if isinstance(validation, Mapping) else {}
    permutation = validation.get("permutation") if isinstance(validation, Mapping) else {}
    trade_count_diag = validation.get("trade_count") if isinstance(validation, Mapping) else {}
    grid_overfit = validation.get("grid_overfit") if isinstance(validation, Mapping) else {}

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
        "## Caveats",
    ]

    for caveat in artifact.get("caveats", []):
        lines.append(f"- {caveat}")

    return "\n".join(lines).strip() + "\n"
