"""Bounded classic-page summaries for Assistant inspect capabilities (CAI-9).

Summaries are JSON-safe scalars/counts only. They never return DataFrames or
unbounded sample arrays. Charts remain owned by classic pages.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

import pandas as pd

from thesistester.reporting import to_jsonable
from thesistester.research_identity import (
    LevelsIdentity,
    identities_from_payload,
    try_page_levels_identity,
)
from thesistester.setup import is_setup_eligible_level_column

# Hard caps for distribution / column listings in assistant payloads.
_MAX_COLUMNS = 64
_MAX_DISTRIBUTION_KEYS = 24
_MAX_FAMILY_COLUMNS = 16
_MAX_MAPPING_KEYS = 48
_MAX_LIST_ITEMS = 12

_OHLCV_META = frozenset(
    {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "session",
        "contract",
        "datetime",
        "date",
        "time",
    }
)

_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "session",
        (
            "ONH",
            "ONL",
            "AsiaHigh",
            "AsiaLow",
            "OR_",
            "RTH_",
            "dOpen",
            "wOpen",
            "mOpen",
            "pdOpen",
            "prevSettlement",
            "pON",
            "pRTH",
        ),
    ),
    ("vwap", ("VWAP", "dVWAP", "session_vwap", "ETH_VWAP")),
    ("profile", ("POC", "VAH", "VAL", "APOC", "pAPOC", "VPOC")),
    ("sma", ("SMA_", "sma_")),
    ("ema", ("EMA_", "ema_")),
    ("pivot", ("PIVOT", "pivot", "PP", "R1", "R2", "S1", "S2")),
    ("single_print", ("SP_", "single_print", "SinglePrint")),
)


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    return None


def _is_dataframe(value: Any) -> bool:
    return isinstance(value, pd.DataFrame)


def _canonicalize_jsonable(value: Any) -> Any:
    """Deterministic JSON-safe structure with sorted object keys."""
    value = to_jsonable(value)
    if isinstance(value, dict):
        return {str(key): _canonicalize_jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_canonicalize_jsonable(item) for item in value]
    return value


def _finalize_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize a page summary for stable evidence / inspect payloads."""
    finalized = _canonicalize_jsonable(payload)
    if not isinstance(finalized, dict):
        raise TypeError("page summary must canonicalize to an object")
    return finalized


def _bound_mapping(value: Any, *, max_keys: int = _MAX_MAPPING_KEYS) -> dict[str, Any]:
    """JSON-safe mapping: drop nested lists longer than cap; truncate key count."""
    mapping = _as_mapping(value)
    if mapping is None:
        return {}
    out: dict[str, Any] = {}
    # Sorted iteration keeps truncation + evidence paths stable across
    # live session vs bundle JSON key order.
    ordered_items = sorted(mapping.items(), key=lambda item: str(item[0]))
    for index, (key, raw) in enumerate(ordered_items):
        if index >= max_keys:
            out["_truncated_keys"] = len(mapping) - max_keys
            break
        if isinstance(raw, (list, tuple)):
            items = list(raw)
            if len(items) > _MAX_LIST_ITEMS:
                out[str(key)] = {
                    "count": len(items),
                    "sample": to_jsonable(items[:_MAX_LIST_ITEMS]),
                    "truncated": True,
                }
            else:
                out[str(key)] = to_jsonable(items)
            continue
        if isinstance(raw, Mapping):
            nested = _as_mapping(raw) or {}
            # Keep one level of scalars only for nested diagnostics.
            nested_out: dict[str, Any] = {}
            nested_items = sorted(nested.items(), key=lambda item: str(item[0]))
            for n_index, (n_key, n_val) in enumerate(nested_items):
                if n_index >= max_keys:
                    nested_out["_truncated_keys"] = len(nested) - max_keys
                    break
                if isinstance(n_val, (list, tuple, Mapping)):
                    continue
                nested_out[str(n_key)] = to_jsonable(n_val)
            out[str(key)] = nested_out
            continue
        out[str(key)] = to_jsonable(raw)
    return out


def _value_counts(series: pd.Series) -> dict[str, int]:
    counts = Counter(str(v) for v in series.dropna().tolist())
    ranked = counts.most_common(_MAX_DISTRIBUTION_KEYS)
    out = {key: int(count) for key, count in ranked}
    if len(counts) > _MAX_DISTRIBUTION_KEYS:
        out["_other"] = int(
            sum(count for _, count in counts.most_common()[_MAX_DISTRIBUTION_KEYS:])
        )
    return out


def _classify_level_families(columns: list[str]) -> dict[str, Any]:
    families: dict[str, list[str]] = {name: [] for name, _ in _FAMILY_RULES}
    families["other"] = []
    for column in columns:
        matched = False
        for family, prefixes in _FAMILY_RULES:
            if any(
                column.startswith(prefix) or column == prefix.rstrip("_") for prefix in prefixes
            ):
                families[family].append(column)
                matched = True
                break
        if not matched:
            families["other"].append(column)
    summary: dict[str, Any] = {}
    for family, cols in families.items():
        if not cols:
            continue
        summary[family] = {
            "count": len(cols),
            "columns": cols[:_MAX_FAMILY_COLUMNS],
            "truncated": len(cols) > _MAX_FAMILY_COLUMNS,
        }
    return summary


def _levels_identity_payload(state: Mapping[str, Any]) -> dict[str, Any] | None:
    identity = try_page_levels_identity(state)
    if identity is not None:
        return to_jsonable(identity.to_dict())
    raw = state.get("levels_identity")
    if isinstance(raw, Mapping):
        try:
            return to_jsonable(LevelsIdentity.from_dict(raw).to_dict())
        except (TypeError, ValueError):
            return to_jsonable(dict(raw))
    data, levels = identities_from_payload(state)
    if levels is not None:
        return to_jsonable(levels.to_dict())
    if data is not None:
        return {"data_identity": to_jsonable(data.to_dict())}
    return None


def summarize_levels_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only levels summary: configuration, identity, families, columns."""
    levels = state.get("levels")
    session_levels = state.get("session_levels")
    settings = _as_mapping(state.get("levels_settings")) or {}
    available = _is_dataframe(levels) or bool(settings)
    if not available:
        return _finalize_summary(
            {"available": False, "reason": "No levels frame or levels_settings in evidence."}
        )

    level_columns: list[str] = []
    if _is_dataframe(levels):
        # Diagnostics (e.g. prev30mVWAP_hit_m*) are not setup-eligible price levels.
        level_columns = [
            str(c)
            for c in levels.columns
            if str(c) not in _OHLCV_META and is_setup_eligible_level_column(str(c))
        ]
    identity = _levels_identity_payload(state)
    return _finalize_summary(
        {
            "available": True,
            "configuration": _bound_mapping(settings),
            "identity": identity,
            "row_count": int(len(levels)) if _is_dataframe(levels) else None,
            "session_levels_row_count": int(len(session_levels))
            if _is_dataframe(session_levels)
            else None,
            "level_column_count": len(level_columns),
            "level_columns": level_columns[:_MAX_COLUMNS],
            "level_columns_truncated": len(level_columns) > _MAX_COLUMNS,
            "families": _classify_level_families(level_columns),
            "charts": "owned_by_classic_levels_page",
        }
    )


def summarize_signals_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only signals summary: count, zones, trigger/direction distributions."""
    signals = state.get("signals")
    zones = state.get("confluence_zones")
    naked = state.get("naked_flags")
    if not _is_dataframe(signals):
        return _finalize_summary({"available": False, "reason": "No signals frame in evidence."})

    trigger_dist: dict[str, int] = {}
    direction_dist: dict[str, int] = {}
    status_dist: dict[str, int] = {}
    if "trigger" in signals.columns:
        trigger_dist = _value_counts(signals["trigger"])
    if "direction" in signals.columns:
        direction_dist = _value_counts(signals["direction"])
    if "status" in signals.columns:
        status_dist = _value_counts(signals["status"])

    setup = (
        _as_mapping(state.get("last_signal_setup")) or _as_mapping(state.get("setup_config")) or {}
    )
    return _finalize_summary(
        {
            "available": True,
            "signal_count": int(len(signals)),
            "zone_count": int(len(zones)) if _is_dataframe(zones) else None,
            "naked_flag_count": int(len(naked)) if _is_dataframe(naked) else None,
            "trigger_distribution": trigger_dist,
            "direction_distribution": direction_dist,
            "status_distribution": status_dist,
            "setup": {
                "name": setup.get("name"),
                "trigger": setup.get("trigger"),
                "direction": setup.get("direction"),
                "tolerance_ticks": setup.get("tolerance_ticks"),
                "selected_levels": to_jsonable(
                    list(setup.get("selected_levels") or [])[:_MAX_LIST_ITEMS]
                ),
                "confluence_mode": setup.get("confluence_mode"),
            },
            "charts": "owned_by_classic_signals_page",
        }
    )


def summarize_backtest_state(
    state: Mapping[str, Any],
    *,
    cost_assumptions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only backtest summary: KPIs, costs, intrabar policy, caveats.

    ``cost_assumptions`` (e.g. evidence-packet ``costs_exposure``) overrides
    session/bundle keys so inspect and evidence caveats stay parity-aligned.
    """
    trade_summary = _as_mapping(state.get("trade_summary"))
    trades = state.get("trades")
    if trade_summary is None and not _is_dataframe(trades):
        return _finalize_summary(
            {"available": False, "reason": "No trade_summary or trades in evidence."}
        )

    kpi_keys = (
        "trade_count",
        "win_rate",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_r",
        "avg_r",
        "total_r",
        "sharpe_like_r",
        "sortino_like_r",
    )
    kpis: dict[str, Any] = {}
    summary = trade_summary or {}
    for key in kpi_keys:
        if key in summary:
            kpis[key] = to_jsonable(summary[key])
    if "trade_count" not in kpis and _is_dataframe(trades):
        kpis["trade_count"] = int(len(trades))

    costs = _as_mapping(state.get("backtest_execution_costs")) or {}
    backtest_config = _as_mapping(state.get("backtest_config")) or {}
    nested_backtest = _as_mapping(state.get("backtest")) or {}
    hints = _as_mapping(cost_assumptions) or {}
    intrabar_policy = _as_mapping(state.get("backtest_intrabar_policy")) or {}
    intrabar_diag = _as_mapping(state.get("backtest_intrabar_diagnostic")) or {}
    exposure = _as_mapping(state.get("exposure_policy")) or {}

    caveats: list[str] = []
    trade_count = kpis.get("trade_count")
    if isinstance(trade_count, (int, float)) and trade_count < 30:
        caveats.append("low_sample")

    def _first_cost(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    commission = _first_cost(
        hints.get("commission_per_side"),
        costs.get("commission_per_side"),
        backtest_config.get("commission_per_side"),
        nested_backtest.get("commission_per_side"),
    )
    slippage = _first_cost(
        hints.get("slippage_ticks"),
        costs.get("slippage_ticks"),
        backtest_config.get("slippage_ticks"),
        nested_backtest.get("slippage_ticks"),
    )
    # Match explainer caveats: only explicit zeros (missing costs ≠ zero_costs).
    if commission == 0 and slippage == 0:
        caveats.append("zero_costs")
    ambiguous = intrabar_diag.get("ambiguous") or intrabar_diag.get("intrabar_ambiguous_count")
    if isinstance(ambiguous, (int, float)) and ambiguous > 0:
        caveats.append("intrabar_ambiguity")

    return _finalize_summary(
        {
            "available": True,
            "kpis": kpis,
            "costs": {
                "commission_per_side": to_jsonable(commission),
                "slippage_ticks": to_jsonable(slippage),
                "raw": _bound_mapping(costs),
            },
            "intrabar_policy": _bound_mapping(intrabar_policy)
            or {"model": backtest_config.get("intrabar_model")},
            "intrabar_diagnostic": _bound_mapping(intrabar_diag),
            "exposure_policy": _bound_mapping(exposure)
            or {"policy": backtest_config.get("exposure_policy")},
            "caveats": caveats,
            "charts": "owned_by_classic_backtest_page",
        }
    )


def summarize_grid_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only grid summary: candidate selection evidence."""
    best = _as_mapping(state.get("best_grid_result"))
    grid_results = state.get("grid_results")
    grid_config = _as_mapping(state.get("grid_config")) or {}
    if best is None and not _is_dataframe(grid_results) and not grid_config:
        return _finalize_summary({"available": False, "reason": "No grid results in evidence."})

    selection_keys = (
        "stop_loss_ticks",
        "take_profit_ticks",
        "trade_count",
        "expectancy_r",
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "ranking_metric",
        "tp_sl_ratio",
    )
    selected: dict[str, Any] = {}
    if best is not None:
        for key in selection_keys:
            if key in best:
                selected[key] = to_jsonable(best[key])
        # Prefer a compact scalar snapshot over the full metric row.
        selected["metric_snapshot"] = {
            key: to_jsonable(best[key])
            for key in (
                "expectancy_r",
                "profit_factor",
                "total_r",
                "sharpe_like_r",
                "min_direction_expectancy_r",
            )
            if key in best
        }

    return _finalize_summary(
        {
            "available": True,
            "best_cell": selected,
            "grid_config": _bound_mapping(grid_config),
            "candidate_count": int(len(grid_results)) if _is_dataframe(grid_results) else None,
            "selection_caveat": "grid_selection" if best is not None else None,
            "charts": "owned_by_classic_grid_page",
        }
    )


def summarize_validation_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only validation / OOS summary (bounded scalars only)."""
    validation = _as_mapping(state.get("validation_summary"))
    walk_forward = _as_mapping(state.get("walk_forward_summary"))
    monte_carlo = _as_mapping(state.get("monte_carlo_summary"))
    overfitting = _as_mapping(state.get("overfitting_summary"))
    if validation is None and walk_forward is None and monte_carlo is None and overfitting is None:
        return _finalize_summary(
            {"available": False, "reason": "No validation or walk-forward evidence."}
        )

    oos_present = walk_forward is not None
    oos_status = None
    if walk_forward is not None:
        oos_status = walk_forward.get("status") or walk_forward.get("oos_status")
        if oos_status is None and walk_forward.get("fold_count") is not None:
            oos_status = "present"

    return _finalize_summary(
        {
            "available": True,
            "validation": _bound_mapping(validation),
            "walk_forward": _bound_mapping(walk_forward),
            "monte_carlo": _bound_mapping(monte_carlo),
            "overfitting": _bound_mapping(overfitting),
            "oos_evidence": {
                "present": oos_present,
                "status": oos_status,
            },
            "charts": "owned_by_classic_validation_page",
        }
    )


def summarize_grid_validation_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Combined grid + validation summary for product-completeness views."""
    return _finalize_summary(
        {
            "grid": summarize_grid_state(state),
            "validation": summarize_validation_state(state),
        }
    )
