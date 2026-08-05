"""Deterministic grid/time ranking projections for results Q&A (RQ-2).

Projections are JSON-safe tables with stable paths under
``results.projections.*``. They must be merged only into an ephemeral turn
context — never written back into research bundles.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from thesistester.assistant.explainer import EvidencePacket
from thesistester.reporting import to_jsonable

DEFAULT_GRID_METRIC = "expectancy_r"
DEFAULT_TIME_METRIC = "avg_r"
DEFAULT_TOP_N = 5
DEFAULT_GRID_MIN_TRADES = 1
DEFAULT_TIME_MIN_TRADES = 10
DEFAULT_TIME_BUCKET_COL = "entry_rth_segment"

_GRID_RANKING_METRICS = frozenset(
    {"expectancy_r", "total_r", "profit_factor", "win_rate", "sharpe_like_r"}
)
_TIME_RANKING_METRICS = frozenset(
    {
        "avg_r",
        "median_r",
        "total_r",
        "profit_factor",
        "win_rate",
        "expectancy_r",
        "trade_count",
    }
)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _as_packet_dict(packet_or_mapping: EvidencePacket | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(packet_or_mapping, EvidencePacket):
        return packet_or_mapping.to_dict()
    return dict(packet_or_mapping)


def _is_packet_like(value: Any) -> bool:
    if isinstance(value, EvidencePacket):
        return True
    if not isinstance(value, Mapping):
        return False
    return "results" in value or "assumptions" in value or "provenance" in value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sanitize_grid_metric(metric: Any) -> str | None:
    """Return an allowlisted grid ranking metric, or ``None`` when invalid."""
    if not isinstance(metric, str):
        return None
    name = metric.strip()
    if name in _GRID_RANKING_METRICS:
        return name
    return None


def resolve_grid_ranking_defaults(
    packet: EvidencePacket | Mapping[str, Any],
) -> tuple[str, str, int]:
    """Return ``(metric, metric_source_path, min_trades)`` from packet assumptions.

    Prefers ``results.best_grid_result.ranking_metric`` when present and
    allowlisted, else ``assumptions.grid.ranking_metric``, else
    ``expectancy_r``. Unknown metric names fall through the preference chain
    so rankings never advertise an unsanitized metric. The model must never
    choose the ranking metric.
    """
    payload = _as_packet_dict(packet)
    results = _as_mapping(payload.get("results")) or {}
    assumptions = _as_mapping(payload.get("assumptions")) or {}
    best = _as_mapping(results.get("best_grid_result")) or {}
    grid_cfg = _as_mapping(assumptions.get("grid")) or {}

    metric_name = _sanitize_grid_metric(best.get("ranking_metric"))
    if metric_name is not None:
        metric_path = "results.best_grid_result.ranking_metric"
    else:
        metric_name = _sanitize_grid_metric(grid_cfg.get("ranking_metric"))
        if metric_name is not None:
            metric_path = "assumptions.grid.ranking_metric"
        else:
            metric_name = DEFAULT_GRID_METRIC
            metric_path = "assumptions.grid.ranking_metric"

    min_trades_raw = grid_cfg.get("min_trades", DEFAULT_GRID_MIN_TRADES)
    try:
        min_trades = int(min_trades_raw)
    except (TypeError, ValueError):
        min_trades = DEFAULT_GRID_MIN_TRADES
    if min_trades < 1:
        min_trades = DEFAULT_GRID_MIN_TRADES
    return metric_name, metric_path, min_trades


def _oos_status(packet_dict: Mapping[str, Any]) -> str:
    results = _as_mapping(packet_dict.get("results")) or {}
    return "present" if _as_mapping(results.get("walk_forward_summary")) is not None else "missing"


def _grid_rows_from_source(
    packet_or_grid: EvidencePacket | Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(packet_or_grid, Sequence) and not isinstance(
        packet_or_grid, (str, bytes, bytearray)
    ):
        rows: list[dict[str, Any]] = []
        for item in packet_or_grid:
            if isinstance(item, Mapping):
                rows.append(dict(item))
        return rows
    if not _is_packet_like(packet_or_grid):
        return []
    payload = _as_packet_dict(packet_or_grid)  # type: ignore[arg-type]
    results = _as_mapping(payload.get("results")) or {}
    best = _as_mapping(results.get("best_grid_result"))
    if best is None:
        return []
    return [dict(best)]


def project_grid_rankings(
    packet_or_grid: EvidencePacket | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    top_n: int = DEFAULT_TOP_N,
    metric: str | None = None,
    min_trades: int | None = None,
) -> dict[str, Any]:
    """Rank SL/TP grid candidates deterministically.

    ``packet_or_grid`` may be an ``EvidencePacket`` / packet dict (uses
    ``best_grid_result`` as the candidate set) or a sequence of grid row
    mappings (full ``grid_results``). Metric defaults come from the packet when
    available; otherwise ``expectancy_r``.
    """
    top = _positive_int(top_n, default=DEFAULT_TOP_N)
    metric_source_path = "assumptions.grid.ranking_metric"
    resolved_min = DEFAULT_GRID_MIN_TRADES
    packet_dict: dict[str, Any] | None = None
    if _is_packet_like(packet_or_grid):
        packet_dict = _as_packet_dict(packet_or_grid)  # type: ignore[arg-type]
        default_metric, metric_source_path, resolved_min = resolve_grid_ranking_defaults(
            packet_dict
        )
        chosen_metric = _sanitize_grid_metric(metric) or default_metric
    else:
        chosen_metric = _sanitize_grid_metric(metric) or DEFAULT_GRID_METRIC
    if min_trades is not None:
        try:
            resolved_min = int(min_trades)
        except (TypeError, ValueError):
            resolved_min = DEFAULT_GRID_MIN_TRADES
        if resolved_min < 1:
            resolved_min = DEFAULT_GRID_MIN_TRADES
    if chosen_metric not in _GRID_RANKING_METRICS:
        chosen_metric = DEFAULT_GRID_METRIC

    source_rows = _grid_rows_from_source(packet_or_grid)
    eligible: list[tuple[float, float, float, dict[str, Any]]] = []
    for row in source_rows:
        trade_count = _finite_number(row.get("trade_count"))
        if trade_count is None or trade_count < resolved_min:
            continue
        metric_value = _finite_number(row.get(chosen_metric))
        if metric_value is None:
            continue
        stop = _finite_number(row.get("stop_loss_ticks"))
        target = _finite_number(row.get("take_profit_ticks"))
        stop_key = stop if stop is not None else float("inf")
        target_key = target if target is not None else float("inf")
        eligible.append((metric_value, stop_key, target_key, row))

    # Highest metric first; ties → lower SL then lower TP (matches best_grid_result).
    eligible.sort(key=lambda item: (-item[0], item[1], item[2]))
    ranked = eligible[:top]
    rows: list[dict[str, Any]] = []
    by_rank: dict[str, dict[str, Any]] = {}
    for index, (metric_value, _stop, _tp, row) in enumerate(ranked, start=1):
        projected = {
            "rank": index,
            "stop_loss_ticks": to_jsonable(row.get("stop_loss_ticks")),
            "take_profit_ticks": to_jsonable(row.get("take_profit_ticks")),
            "trade_count": to_jsonable(row.get("trade_count")),
            "metric_value": to_jsonable(metric_value),
            chosen_metric: to_jsonable(row.get(chosen_metric)),
        }
        rows.append(projected)
        by_rank[str(index)] = projected

    return {
        "metric": chosen_metric,
        "metric_source_path": metric_source_path,
        "min_trades": resolved_min,
        "candidate_count": len(source_rows),
        "eligible_count": len(eligible),
        "selection_scope": "in_sample_grid",
        "oos_status": _oos_status(packet_dict) if packet_dict is not None else "unknown",
        "best": by_rank.get("1"),
        "by_rank": by_rank,
        "rows": rows,
    }


def _time_rows_from_summary(
    time_grouped_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(time_grouped_summary, Mapping):
        # Accept {"groups": [...]} from TIME.analyze payload.
        groups = time_grouped_summary.get("groups")
        if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes)):
            return [dict(item) for item in groups if isinstance(item, Mapping)]
        return []
    if isinstance(time_grouped_summary, Sequence) and not isinstance(
        time_grouped_summary, (str, bytes)
    ):
        return [dict(item) for item in time_grouped_summary if isinstance(item, Mapping)]
    return []


def project_time_rankings(
    time_grouped_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    bucket_col: str = DEFAULT_TIME_BUCKET_COL,
    metric: str = DEFAULT_TIME_METRIC,
    min_trades: int = DEFAULT_TIME_MIN_TRADES,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Rank time buckets deterministically for ephemeral results context."""
    if not isinstance(bucket_col, str) or not bucket_col.strip():
        raise ValueError("bucket_col must be a non-empty string.")
    chosen_metric = (
        metric.strip() if isinstance(metric, str) and metric.strip() else DEFAULT_TIME_METRIC
    )
    if chosen_metric not in _TIME_RANKING_METRICS:
        chosen_metric = DEFAULT_TIME_METRIC
    top = _positive_int(top_n, default=DEFAULT_TOP_N)
    try:
        resolved_min = int(min_trades)
    except (TypeError, ValueError):
        resolved_min = DEFAULT_TIME_MIN_TRADES
    if resolved_min < 1:
        resolved_min = DEFAULT_TIME_MIN_TRADES

    source_rows = _time_rows_from_summary(time_grouped_summary)
    eligible: list[tuple[float, int, dict[str, Any]]] = []
    for row in source_rows:
        trade_count = _finite_number(row.get("trade_count"))
        if trade_count is None:
            continue
        # Ranking excludes under-threshold buckets; sample_warning remains on row.
        if trade_count < resolved_min:
            continue
        metric_value = _finite_number(row.get(chosen_metric))
        if metric_value is None:
            continue
        eligible.append((metric_value, int(trade_count), row))

    eligible.sort(key=lambda item: (-item[0], -item[1], str(item[2].get(bucket_col, ""))))
    ranked = eligible[:top]
    rows: list[dict[str, Any]] = []
    by_rank: dict[str, dict[str, Any]] = {}
    for index, (metric_value, _count, row) in enumerate(ranked, start=1):
        sample_warning = row.get("sample_warning")
        if not isinstance(sample_warning, bool):
            trade_count = _finite_number(row.get("trade_count")) or 0.0
            sample_warning = trade_count < resolved_min
        projected = {
            "rank": index,
            "bucket": to_jsonable(row.get(bucket_col)),
            "bucket_col": bucket_col,
            "trade_count": to_jsonable(row.get("trade_count")),
            "metric_value": to_jsonable(metric_value),
            chosen_metric: to_jsonable(row.get(chosen_metric)),
            "sample_warning": sample_warning,
        }
        rows.append(projected)
        by_rank[str(index)] = projected

    return {
        "bucket_col": bucket_col,
        "metric": chosen_metric,
        "min_trades": resolved_min,
        "candidate_count": len(source_rows),
        "eligible_count": len(eligible),
        "selection_scope": "in_sample_time_buckets",
        "best": by_rank.get("1"),
        "by_rank": by_rank,
        "rows": rows,
    }


def build_ephemeral_results_context(
    packet: EvidencePacket | Mapping[str, Any],
    *,
    grid_rows: Sequence[Mapping[str, Any]] | None = None,
    time_grouped_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    grid_top_n: int = DEFAULT_TOP_N,
    time_top_n: int = DEFAULT_TOP_N,
    time_bucket_col: str = DEFAULT_TIME_BUCKET_COL,
    time_metric: str = DEFAULT_TIME_METRIC,
    time_min_trades: int = DEFAULT_TIME_MIN_TRADES,
) -> dict[str, Any]:
    """Copy a packet dict and attach ``results.projections.*`` for one turn."""
    context = _as_packet_dict(packet)
    results = context.get("results")
    if not isinstance(results, dict):
        results = {}
        context["results"] = results
    else:
        results = dict(results)
        context["results"] = results

    metric, metric_path, min_trades = resolve_grid_ranking_defaults(context)
    # Empty authoritative grid tables (common when no grid search ran) must not
    # suppress fallback to ``results.best_grid_result`` on the packet.
    usable_grid_rows: list[dict[str, Any]] | None = None
    if grid_rows is not None:
        usable_grid_rows = [dict(item) for item in grid_rows if isinstance(item, Mapping)]
        if not usable_grid_rows:
            usable_grid_rows = None
    if usable_grid_rows is not None:
        grid_projection = project_grid_rankings(
            usable_grid_rows,
            top_n=grid_top_n,
            metric=metric,
            min_trades=min_trades,
        )
        grid_projection["metric_source_path"] = metric_path
        grid_projection["oos_status"] = _oos_status(context)
    else:
        grid_projection = project_grid_rankings(
            context,
            top_n=grid_top_n,
            metric=metric,
            min_trades=min_trades,
        )

    time_source = time_grouped_summary
    if time_source is None:
        existing = results.get("time_grouped_summary")
        if isinstance(existing, (Mapping, Sequence)) and not isinstance(existing, (str, bytes)):
            time_source = existing

    projections: dict[str, Any] = {"grid_rankings": grid_projection}
    if time_source is not None:
        if not isinstance(results.get("time_grouped_summary"), (Mapping, Sequence)) or isinstance(
            results.get("time_grouped_summary"), (str, bytes)
        ):
            results["time_grouped_summary"] = to_jsonable(time_source)
        projections["time_rankings"] = project_time_rankings(
            time_source,
            bucket_col=time_bucket_col,
            metric=time_metric,
            min_trades=time_min_trades,
            top_n=time_top_n,
        )

    results["projections"] = projections
    return context
