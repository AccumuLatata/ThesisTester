"""Deterministic grid/time/deep-trade projections for results Q&A (RQ-2 / RI-9).

Projections are JSON-safe tables with stable paths under
``results.projections.*``. They must be merged only into an ephemeral turn
context — never written back into research bundles. Deep-trade projections are
built from already-loaded trade table rows (never full parquet to the model).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from thesistester.assistant.explainer import EvidencePacket
from thesistester.execution_defaults import DIRECTIONAL_METRIC_OPTIONS
from thesistester.reporting import to_jsonable

DEFAULT_GRID_METRIC = "expectancy_r"
DEFAULT_TIME_METRIC = "avg_r"
DEFAULT_TOP_N = 5
DEFAULT_GRID_MIN_TRADES = 1
DEFAULT_TIME_MIN_TRADES = 10
DEFAULT_TIME_BUCKET_COL = "entry_rth_segment"
# RI-9 §6 caps (freeze).
EXIT_REASON_TOP_N = 12
EXTREME_TRADES_N = 5

# When the preferred bucket column is absent from exported time rows (common
# when Time Analysis grouped by hour/30m), fall through in this order.
_TIME_BUCKET_COL_FALLBACKS: tuple[str, ...] = (
    "entry_rth_segment",
    "entry_30min_bucket",
    "entry_hour_bucket",
)

# Aggregate + directional grid columns (classic Grid Search may record either).
_GRID_RANKING_METRICS = frozenset(DIRECTIONAL_METRIC_OPTIONS) | {"sharpe_like_r"}
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


def _all_wins_profit_factor_inf(row: Mapping[str, Any], metric: str) -> bool:
    """True when a JSON-null profit-factor cell is an all-wins +inf sample."""
    if metric == "profit_factor":
        win_rate = _finite_number(row.get("win_rate"))
        trade_count = _finite_number(row.get("trade_count"))
        return (
            win_rate is not None and win_rate >= 1.0 and trade_count is not None and trade_count > 0
        )
    if metric == "long_profit_factor":
        win_rate = _finite_number(row.get("long_win_rate"))
        trade_count = _finite_number(row.get("long_trade_count"))
        return (
            win_rate is not None and win_rate >= 1.0 and trade_count is not None and trade_count > 0
        )
    if metric == "short_profit_factor":
        win_rate = _finite_number(row.get("short_win_rate"))
        trade_count = _finite_number(row.get("short_trade_count"))
        return (
            win_rate is not None and win_rate >= 1.0 and trade_count is not None and trade_count > 0
        )
    if metric == "min_direction_profit_factor":
        long_wr = _finite_number(row.get("long_win_rate"))
        short_wr = _finite_number(row.get("short_win_rate"))
        long_tc = _finite_number(row.get("long_trade_count"))
        short_tc = _finite_number(row.get("short_trade_count"))
        return (
            long_wr is not None
            and long_wr >= 1.0
            and short_wr is not None
            and short_wr >= 1.0
            and long_tc is not None
            and long_tc > 0
            and short_tc is not None
            and short_tc > 0
        )
    return False


def _ranking_metric_value(row: Mapping[str, Any], metric: str) -> float | None:
    """Return a comparable ranking value, preserving engine +inf profit factors.

    Research bundles JSON-coerce ``float('inf')`` to ``null``. When the metric
    is a profit-factor column and the matching side/sample is all-wins, treat
    null as +inf so re-ranking matches ``best_grid_result``.
    """
    raw = row.get(metric)
    if isinstance(raw, float) and raw == float("inf"):
        return float("inf")
    number = _finite_number(raw)
    if number is not None:
        return number
    if (
        raw is None
        and metric.endswith("profit_factor")
        and _all_wins_profit_factor_inf(row, metric)
    ):
        return float("inf")
    return None


def _jsonable_metric_value(value: float | None) -> Any:
    if value is None or value == float("inf") or value == float("-inf"):
        return None
    return to_jsonable(value)


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _capped_positive_int(value: Any, *, default: int, cap: int) -> int:
    """Parse a positive int and clamp to the frozen §6 upper bound."""
    return min(_positive_int(value, default=default), cap)


_EXIT_REASON_KEYS: tuple[str, ...] = (
    "exit_reason",
    "ExitReason",
    "exitReason",
    "reason",
)
_R_MULTIPLE_KEYS: tuple[str, ...] = (
    "r_multiple",
    "r_mult",
    "R",
    "r",
)


def _row_exit_reason_label(row: Mapping[str, Any]) -> str | None:
    """Return a string exit-reason label, or None when absent/non-string."""
    for key in _EXIT_REASON_KEYS:
        reason = row.get(key)
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    return None


def _row_r_multiple(row: Mapping[str, Any]) -> float | None:
    for key in _R_MULTIPLE_KEYS:
        raw_r = row.get(key)
        if raw_r is None:
            continue
        try:
            return float(raw_r)
        except (TypeError, ValueError):
            continue
    return None


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _sanitize_grid_metric(metric: Any) -> str | None:
    """Return an allowlisted grid ranking metric, or ``None`` when invalid."""
    if not isinstance(metric, str):
        return None
    name = metric.strip()
    if name in _GRID_RANKING_METRICS:
        return name
    return None


def resolve_grid_side_filters(
    packet: EvidencePacket | Mapping[str, Any],
) -> tuple[int | None, int | None]:
    """Return optional ``(min_long_trades, min_short_trades)`` from assumptions."""
    payload = _as_packet_dict(packet)
    assumptions = _as_mapping(payload.get("assumptions")) or {}
    grid_cfg = _as_mapping(assumptions.get("grid")) or {}
    return (
        _optional_positive_int(grid_cfg.get("min_long_trades")),
        _optional_positive_int(grid_cfg.get("min_short_trades")),
    )


def resolve_grid_ranking_defaults(
    packet: EvidencePacket | Mapping[str, Any],
) -> tuple[str, str, int]:
    """Return ``(metric, metric_source_path, min_trades)`` from packet assumptions.

    Prefers ``results.best_grid_result.ranking_metric`` when present and
    allowlisted (aggregate or directional), else
    ``assumptions.grid.ranking_metric``, else ``expectancy_r``. Unknown metric
    names fall through the preference chain so rankings never advertise an
    unsanitized metric. The model must never choose the ranking metric.
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
            # Default path must not keep pointing at a rejected/bogus assumptions
            # value — ephemeral context syncs this path to expectancy_r.
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


def _project_grid_row(
    row: Mapping[str, Any],
    *,
    rank: int,
    metric: str,
    metric_value: float | None,
) -> dict[str, Any]:
    return {
        "rank": rank,
        "stop_loss_ticks": to_jsonable(row.get("stop_loss_ticks")),
        "take_profit_ticks": to_jsonable(row.get("take_profit_ticks")),
        "trade_count": to_jsonable(row.get("trade_count")),
        "metric_value": _jsonable_metric_value(metric_value),
        metric: to_jsonable(row.get(metric)),
    }


def _pin_recorded_grid_best(
    projection: dict[str, Any],
    packet_dict: Mapping[str, Any],
    *,
    metric: str,
    top_n: int,
) -> dict[str, Any]:
    """Ensure ``best`` matches packet ``best_grid_result`` when present.

    Re-ranking JSON grid tables can disagree with the engine-selected winner
    (infinite profit factors become null; directional filters may be absent).
    Discuss results must not advertise a different SL/TP as ``best``.
    """
    results = _as_mapping(packet_dict.get("results")) or {}
    recorded = _as_mapping(results.get("best_grid_result"))
    if recorded is None:
        return projection
    stop = to_jsonable(recorded.get("stop_loss_ticks"))
    target = to_jsonable(recorded.get("take_profit_ticks"))
    current = projection.get("best")
    if (
        isinstance(current, Mapping)
        and current.get("stop_loss_ticks") == stop
        and current.get("take_profit_ticks") == target
    ):
        return projection

    metric_value = _ranking_metric_value(recorded, metric)
    pinned = _project_grid_row(
        recorded,
        rank=1,
        metric=metric,
        metric_value=metric_value,
    )
    pinned["recorded_selection"] = True
    others = [
        dict(row)
        for row in projection.get("rows") or ()
        if not (row.get("stop_loss_ticks") == stop and row.get("take_profit_ticks") == target)
    ]
    rows = [pinned]
    for index, row in enumerate(others, start=2):
        if index > top_n:
            break
        row["rank"] = index
        rows.append(row)
    by_rank = {str(row["rank"]): row for row in rows}
    prior_eligible = int(projection.get("eligible_count") or 0)
    updated = dict(projection)
    updated["best"] = pinned
    updated["rows"] = rows
    updated["by_rank"] = by_rank
    updated["recorded_best_pinned"] = True
    # Recorded winner may sit outside re-rank filters; keep eligible_count honest.
    updated["eligible_count"] = max(prior_eligible, 1)
    if prior_eligible == 0:
        updated["recorded_best_outside_rerank_filter"] = True
    return updated


def project_grid_rankings(
    packet_or_grid: EvidencePacket | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    top_n: int = DEFAULT_TOP_N,
    metric: str | None = None,
    min_trades: int | None = None,
    min_long_trades: int | None = None,
    min_short_trades: int | None = None,
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
    side_long = _optional_positive_int(min_long_trades)
    side_short = _optional_positive_int(min_short_trades)
    if _is_packet_like(packet_or_grid):
        packet_dict = _as_packet_dict(packet_or_grid)  # type: ignore[arg-type]
        default_metric, metric_source_path, resolved_min = resolve_grid_ranking_defaults(
            packet_dict
        )
        chosen_metric = _sanitize_grid_metric(metric) or default_metric
        if side_long is None and side_short is None:
            side_long, side_short = resolve_grid_side_filters(packet_dict)
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
        if side_long is not None:
            long_count = _finite_number(row.get("long_trade_count"))
            if long_count is None or long_count < side_long:
                continue
        if side_short is not None:
            short_count = _finite_number(row.get("short_trade_count"))
            if short_count is None or short_count < side_short:
                continue
        metric_value = _ranking_metric_value(row, chosen_metric)
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
        projected = _project_grid_row(
            row,
            rank=index,
            metric=chosen_metric,
            metric_value=metric_value,
        )
        rows.append(projected)
        by_rank[str(index)] = projected

    projection = {
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
    if side_long is not None:
        projection["min_long_trades"] = side_long
    if side_short is not None:
        projection["min_short_trades"] = side_short
    if packet_dict is not None:
        projection = _pin_recorded_grid_best(
            projection,
            packet_dict,
            metric=chosen_metric,
            top_n=top,
        )
    return projection


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


def _has_usable_bucket_label(rows: Sequence[Mapping[str, Any]], column: str) -> bool:
    """True when *column* has at least one non-empty, non-null label on *rows*."""
    for row in rows:
        if column not in row:
            continue
        value = row.get(column)
        if value is None:
            continue
        if isinstance(value, float) and value != value:  # NaN
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "nan", "null"}:
            return True
    return False


def resolve_time_bucket_col(
    time_grouped_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    preferred: str = DEFAULT_TIME_BUCKET_COL,
) -> str:
    """Resolve the grouping column with a usable label on exported time rows.

    Prefers ``preferred`` when that column has a non-null label. Otherwise falls
    through ``_TIME_BUCKET_COL_FALLBACKS`` so hour/30m exports from Time
    Analysis still produce a non-null ``best.bucket`` label even if a preferred
    key is present but empty/null on every row.
    """
    preferred_col = (
        preferred.strip()
        if isinstance(preferred, str) and preferred.strip()
        else DEFAULT_TIME_BUCKET_COL
    )
    source_rows = _time_rows_from_summary(time_grouped_summary)
    if not source_rows:
        return preferred_col
    if _has_usable_bucket_label(source_rows, preferred_col):
        return preferred_col
    for candidate in _TIME_BUCKET_COL_FALLBACKS:
        if _has_usable_bucket_label(source_rows, candidate):
            return candidate
    return preferred_col


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
    resolved_bucket_col = resolve_time_bucket_col(
        source_rows,
        preferred=bucket_col,
    )
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

    eligible.sort(key=lambda item: (-item[0], -item[1], str(item[2].get(resolved_bucket_col, ""))))
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
            "bucket": to_jsonable(row.get(resolved_bucket_col)),
            "bucket_col": resolved_bucket_col,
            "trade_count": to_jsonable(row.get("trade_count")),
            "metric_value": to_jsonable(metric_value),
            chosen_metric: to_jsonable(row.get(chosen_metric)),
            "sample_warning": sample_warning,
        }
        rows.append(projected)
        by_rank[str(index)] = projected

    return {
        "bucket_col": resolved_bucket_col,
        "metric": chosen_metric,
        "min_trades": resolved_min,
        "candidate_count": len(source_rows),
        "eligible_count": len(eligible),
        "selection_scope": "in_sample_time_buckets",
        "best": by_rank.get("1"),
        "by_rank": by_rank,
        "rows": rows,
    }


def _sync_ephemeral_ranking_metric_source(
    context: dict[str, Any],
    *,
    metric: str,
    metric_path: str,
) -> None:
    """Align citable ranking-metric fields with the metric actually used.

    Rewrites the resolved source path and any rejected
    ``results.best_grid_result.ranking_metric`` so grounded replies cannot cite
    a bogus best-row metric while projections rank by a sanitized value.
    """
    assumptions = context.get("assumptions")
    if not isinstance(assumptions, dict):
        assumptions = dict(assumptions) if isinstance(assumptions, Mapping) else {}
        context["assumptions"] = assumptions
    else:
        assumptions = dict(assumptions)
        context["assumptions"] = assumptions
    grid_cfg = assumptions.get("grid")
    if not isinstance(grid_cfg, dict):
        grid_cfg = dict(grid_cfg) if isinstance(grid_cfg, Mapping) else {}
    else:
        grid_cfg = dict(grid_cfg)
    assumptions["grid"] = grid_cfg
    if metric_path == "assumptions.grid.ranking_metric" or "ranking_metric" in grid_cfg:
        grid_cfg["ranking_metric"] = metric

    results = context.get("results")
    if not isinstance(results, dict):
        return
    best = results.get("best_grid_result")
    if not isinstance(best, Mapping):
        return
    if "ranking_metric" not in best and metric_path != "results.best_grid_result.ranking_metric":
        return
    best_copy = dict(best)
    best_copy["ranking_metric"] = metric
    results["best_grid_result"] = best_copy


def _trade_row_dicts(
    trade_rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if trade_rows is None:
        return []
    return [dict(item) for item in trade_rows if isinstance(item, Mapping)]


def project_exit_reason_counts(
    trade_rows: Sequence[Mapping[str, Any]] | None,
    *,
    top_n: int = EXIT_REASON_TOP_N,
) -> dict[str, Any] | None:
    """Bounded exit-reason histogram (RI-9 §6). Top N reasons + other."""
    rows = _trade_row_dicts(trade_rows)
    if not rows:
        return None
    cap = _capped_positive_int(top_n, default=EXIT_REASON_TOP_N, cap=EXIT_REASON_TOP_N)
    counts: dict[str, int] = {}
    resolved_labels = 0
    for row in rows:
        label = _row_exit_reason_label(row)
        if label is None:
            label = "unknown"
        else:
            resolved_labels += 1
        counts[label] = counts.get(label, 0) + 1
    # No resolvable string labels → not usable exit-structure evidence.
    if resolved_labels == 0:
        return None
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    top = ranked[:cap]
    other = ranked[cap:]
    return {
        "total_trades": int(sum(counts.values())),
        "unique_reason_count": int(len(counts)),
        "top_n": cap,
        "reasons": [{"exit_reason": reason, "count": int(count)} for reason, count in top],
        "other_count": int(sum(count for _, count in other)),
        "other_unique_count": int(len(other)),
    }


def project_extreme_trades(
    trade_rows: Sequence[Mapping[str, Any]] | None,
    *,
    n: int = EXTREME_TRADES_N,
) -> dict[str, Any] | None:
    """Worst/best R trades summary (RI-9 §6). N≤5 each; R + exit_reason only.

    Timestamps are intentionally omitted from the model-facing projection object
    (ISO datetimes launder ungroundable year/day digits through the auditor).
    """
    rows = _trade_row_dicts(trade_rows)
    if not rows:
        return None
    cap = _capped_positive_int(n, default=EXTREME_TRADES_N, cap=EXTREME_TRADES_N)
    usable: list[dict[str, Any]] = []
    for row in rows:
        r_value = _row_r_multiple(row)
        if r_value is None:
            continue
        item: dict[str, Any] = {"r_multiple": r_value}
        reason = _row_exit_reason_label(row)
        if reason is not None:
            item["exit_reason"] = reason
        usable.append(item)
    if not usable:
        return None
    best = sorted(usable, key=lambda item: item["r_multiple"], reverse=True)[:cap]
    worst = sorted(usable, key=lambda item: item["r_multiple"])[:cap]
    return {"best": best, "worst": worst, "n": cap}


def project_streak_summary(
    packet_or_mapping: EvidencePacket | Mapping[str, Any],
    trade_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Max consecutive wins/losses (RI-9 §6). Prefer trade_summary; else compute."""
    context = _as_packet_dict(packet_or_mapping)
    results = context.get("results")
    summary = _as_mapping(results.get("trade_summary")) if isinstance(results, Mapping) else None
    if summary is not None:
        wins = summary.get("max_consecutive_wins")
        losses = summary.get("max_consecutive_losses")
        out: dict[str, Any] = {"source": "trade_summary"}
        if isinstance(wins, (int, float)) and not isinstance(wins, bool):
            out["max_consecutive_wins"] = int(wins)
        if isinstance(losses, (int, float)) and not isinstance(losses, bool):
            out["max_consecutive_losses"] = int(losses)
        if "max_consecutive_wins" in out or "max_consecutive_losses" in out:
            return out

    rows = _trade_row_dicts(trade_rows)
    if not rows:
        return None
    max_wins = 0
    max_losses = 0
    cur_wins = 0
    cur_losses = 0
    for row in rows:
        r_value = _row_r_multiple(row)
        if r_value is None:
            cur_wins = 0
            cur_losses = 0
            continue
        if r_value > 0:
            cur_wins += 1
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif r_value < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0
    return {
        "source": "trades",
        "max_consecutive_wins": int(max_wins),
        "max_consecutive_losses": int(max_losses),
    }


def build_ephemeral_results_context(
    packet: EvidencePacket | Mapping[str, Any],
    *,
    grid_rows: Sequence[Mapping[str, Any]] | None = None,
    time_grouped_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    trade_rows: Sequence[Mapping[str, Any]] | None = None,
    grid_top_n: int = DEFAULT_TOP_N,
    time_top_n: int = DEFAULT_TOP_N,
    time_bucket_col: str = DEFAULT_TIME_BUCKET_COL,
    time_metric: str = DEFAULT_TIME_METRIC,
    time_min_trades: int = DEFAULT_TIME_MIN_TRADES,
    exit_reason_top_n: int = EXIT_REASON_TOP_N,
    extreme_trades_n: int = EXTREME_TRADES_N,
    grid_table_status: str | None = None,
    grid_table_warning: str | None = None,
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
    _sync_ephemeral_ranking_metric_source(
        context,
        metric=metric,
        metric_path=metric_path,
    )
    min_long, min_short = resolve_grid_side_filters(context)
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
            min_long_trades=min_long,
            min_short_trades=min_short,
        )
        grid_projection["metric_source_path"] = metric_path
        grid_projection["oos_status"] = _oos_status(context)
        grid_projection = _pin_recorded_grid_best(
            grid_projection,
            context,
            metric=metric,
            top_n=_positive_int(grid_top_n, default=DEFAULT_TOP_N),
        )
    else:
        grid_projection = project_grid_rankings(
            context,
            top_n=grid_top_n,
            metric=metric,
            min_trades=min_trades,
            min_long_trades=min_long,
            min_short_trades=min_short,
        )

    if isinstance(grid_table_status, str) and grid_table_status.strip():
        grid_projection["bundle_tables_status"] = grid_table_status.strip()
    if isinstance(grid_table_warning, str) and grid_table_warning.strip():
        grid_projection["bundle_tables_warning"] = grid_table_warning.strip()

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

    # RI-9: bounded deep-trade projections from loaded trade rows / packet streaks.
    usable_trades = _trade_row_dicts(trade_rows)
    exit_counts = project_exit_reason_counts(usable_trades, top_n=exit_reason_top_n)
    if exit_counts is not None:
        projections["exit_reason_counts"] = exit_counts
    extremes = project_extreme_trades(usable_trades, n=extreme_trades_n)
    if extremes is not None:
        projections["extreme_trades"] = extremes
    streaks = project_streak_summary(context, usable_trades or None)
    if streaks is not None:
        projections["streak_summary"] = streaks

    results["projections"] = projections
    return context
