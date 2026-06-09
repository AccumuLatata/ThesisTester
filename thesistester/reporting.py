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
            "backtest_cost_config": to_jsonable(
                session_state.get("backtest_cost_config")
                or {"commission_per_side": 0.0, "slippage_ticks": 0.0}
            ),
        },
        "results": {
            "signal_count": _table_count(session_state, "signals"),
            "trade_count": _table_count(session_state, "trades"),
            "trade_summary": to_jsonable(session_state.get("trade_summary")),
            "best_grid_result": to_jsonable(session_state.get("best_grid_result")),
            "validation_summary": to_jsonable(session_state.get("validation_summary")),
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


def build_markdown_report(artifact: dict[str, Any]) -> str:
    """Build a concise markdown report from a research artifact."""
    metadata = artifact.get("metadata", {}) if isinstance(artifact, Mapping) else {}
    config = artifact.get("configuration", {}) if isinstance(artifact, Mapping) else {}
    results = artifact.get("results", {}) if isinstance(artifact, Mapping) else {}
    tables = artifact.get("tables", {}) if isinstance(artifact, Mapping) else {}

    setup = config.get("setup_config") or {}
    cost_config = config.get("backtest_cost_config") or {}
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

    is_cost_config = isinstance(cost_config, Mapping)
    commission_val = cost_config.get("commission_per_side", 0.0) if is_cost_config else 0.0
    slip_val = cost_config.get("slippage_ticks", 0.0) if is_cost_config else 0.0
    if commission_val or slip_val:
        cost_note = "net-of-cost"
    else:
        cost_note = "gross (zero costs)"

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
        "## Execution Cost Assumptions",
        f"- Commission per side: ${_fmt_number(commission_val, '.4f')}",
        f"- Slippage: {_fmt_number(slip_val, '.4f')} tick(s)",
        f"- Metrics basis: {cost_note}",
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
