"""OTF statistical validation helper (PR 6).

Provides :func:`run_otf_validation_matrix` — a pure, research-safe helper that
evaluates the fixed OTF comparison matrix on a chronological train/OOS split.

Methodology
-----------
- Five fixed OTF configurations are compared (no_otf, 15m, 30m, 15m+30m,
  5m+15m+30m).
- Candidate signals are split chronologically (default 70/30 train/OOS).
- OTF filtering is applied independently and point-in-time safely using the
  existing ``apply_otf_filter()`` engine.
- Trades are simulated separately for train and OOS periods.
- Ranking, if used, is based on train metrics only; OOS metrics never affect
  selection.

⚠️ This module is diagnostic only.  Results are not proof of edge.  Do not
select an OTF configuration for production use based on full-dataset results.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..engine.otf import OTF_ALGORITHM_VERSION
from ..engine.otf_filter import apply_otf_filter
from ..engine.backtest import simulate_trades
from ..analytics.metrics import summarize_trades
from ..setup import normalize_otf_filter_config, _default_otf_filter_config
from ..persistence.local_store import compute_otf_config_hash


# ---------------------------------------------------------------------------
# Fixed OTF comparison matrix
# ---------------------------------------------------------------------------

#: Internal row-identity column. Survives ``apply_otf_filter()`` enabled-path
#: ``reset_index(drop=True)`` so train/OOS membership does not depend on the
#: pandas index.
_ROW_ID_COL = "_otf_validation_row_id"

#: Keys reserved by ``run_otf_validation_matrix`` / ``simulate_trades``; stripped
#: from ``execution_kwargs`` so callers cannot trigger duplicate-kwarg failures
#: that would be swallowed into empty-trade results.
_RESERVED_EXECUTION_KEYS = frozenset(
    {"tick_size", "point_value", "stop_loss_ticks", "take_profit_ticks"}
)

#: OTF v1 default parameters used for all enabled configurations.
OTF_V1_DEFAULTS: dict[str, Any] = {
    "alignment_mode": "all",
    "minimum_consecutive_bars": 3,
    "session_reset": "session",
}

#: Fixed comparison matrix — deterministic and stable.  Do not reorder.
_MATRIX_SPECS: list[dict[str, Any]] = [
    {"label": "no_otf", "enabled": False, "timeframes": []},
    {"label": "otf_15m", "enabled": True, "timeframes": ["15m"]},
    {"label": "otf_30m", "enabled": True, "timeframes": ["30m"]},
    {"label": "otf_15m_30m", "enabled": True, "timeframes": ["15m", "30m"]},
    {"label": "otf_5m_15m_30m", "enabled": True, "timeframes": ["5m", "15m", "30m"]},
]


def build_otf_matrix_configs() -> list[dict[str, Any]]:
    """Return canonical configs for all five fixed OTF matrix entries.

    Each entry is a dict with keys:

    - ``label`` — deterministic string label.
    - ``otf_config`` — normalized OTF filter config dict.
    - ``config_hash`` — deterministic SHA-256 hash of the config.

    The list order matches :data:`_MATRIX_SPECS`.  Call this function to
    obtain stable labels and hashes for audit purposes.
    """
    result: list[dict[str, Any]] = []
    for spec in _MATRIX_SPECS:
        label = spec["label"]
        if spec["enabled"]:
            raw: dict[str, Any] = {
                "enabled": True,
                "timeframes": list(spec["timeframes"]),
                **OTF_V1_DEFAULTS,
            }
            config = normalize_otf_filter_config(raw)
        else:
            config = _default_otf_filter_config()
        result.append(
            {
                "label": label,
                "otf_config": config,
                "config_hash": compute_otf_config_hash(config),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stamp_row_ids(signals: pd.DataFrame) -> pd.DataFrame:
    """Deep-copy *signals* and stamp a stable positional row-id column."""
    out = signals.copy(deep=True)
    out[_ROW_ID_COL] = range(len(out))
    return out


def _drop_row_id(df: pd.DataFrame) -> pd.DataFrame:
    """Return *df* without the internal row-id column (copy when present)."""
    if df is None or df.empty or _ROW_ID_COL not in df.columns:
        return df
    return df.drop(columns=[_ROW_ID_COL])


def _chronological_train_oos_sets(
    signals: pd.DataFrame,
    train_fraction: float,
) -> tuple[frozenset, frozenset]:
    """Return ``(train_id_set, oos_id_set)`` for a chronological split.

    Signals are sorted chronologically by ``timestamp`` then ``bar_index``
    then positional order.  Membership prefers :data:`_ROW_ID_COL` when
    present so the sets remain valid after ``apply_otf_filter()`` resets the
    pandas index on the enabled path.  Falls back to index labels when the
    row-id column is absent (direct helper unit tests).
    """
    if signals.empty:
        return frozenset(), frozenset()

    sort_cols = [c for c in ("timestamp", "bar_index") if c in signals.columns]
    if sort_cols:
        ordered = signals.sort_values(sort_cols, kind="stable")
    else:
        ordered = signals

    if _ROW_ID_COL in ordered.columns:
        sorted_ids = ordered[_ROW_ID_COL].tolist()
    else:
        sorted_ids = ordered.index.tolist()

    n = len(sorted_ids)
    n_train = max(0, min(n, int(n * train_fraction)))

    return frozenset(sorted_ids[:n_train]), frozenset(sorted_ids[n_train:])


def _filter_period(df: pd.DataFrame, period_set: frozenset) -> pd.DataFrame:
    """Return rows of *df* belonging to *period_set* (row-id or index)."""
    if df is None or df.empty or not period_set:
        return df.iloc[0:0].copy() if df is not None else pd.DataFrame()
    if _ROW_ID_COL in df.columns:
        return df[df[_ROW_ID_COL].isin(period_set)].copy()
    return df[df.index.isin(period_set)].copy()


def _count_period(df: pd.DataFrame | None, period_set: frozenset) -> int:
    if df is None or df.empty or not period_set:
        return 0
    if _ROW_ID_COL in df.columns:
        return int(df[_ROW_ID_COL].isin(period_set).sum())
    return int(df.index.isin(period_set).sum())


def _period_metrics(
    trades: pd.DataFrame | None,
) -> dict[str, Any]:
    """Compute trade-period metrics from a trade DataFrame.

    Returns a flat dict.  All values are ``None`` when *trades* is empty.
    """
    summary = summarize_trades(trades if trades is not None else pd.DataFrame())

    long_count = 0
    short_count = 0
    if trades is not None and not trades.empty and "direction" in trades.columns:
        long_count = int((trades["direction"] == "long").sum())
        short_count = int((trades["direction"] == "short").sum())

    return {
        "trade_count": summary.get("trade_count", 0),
        "expectancy_r": summary.get("expectancy_r"),
        "total_r": summary.get("total_r"),
        "avg_r": summary.get("avg_r"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown_r": summary.get("max_drawdown_r"),
        "win_rate": summary.get("win_rate"),
        "long_trade_count": long_count,
        "short_trade_count": short_count,
    }


def _simulate(
    source_df: pd.DataFrame,
    accepted: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    execution_kwargs: dict[str, Any],
) -> pd.DataFrame:
    """Run ``simulate_trades`` on accepted signals; return empty df on failure."""
    from ..engine.backtest import _empty_trades_df  # type: ignore[attr-defined]

    if accepted is None or accepted.empty:
        return _empty_trades_df()
    try:
        result = simulate_trades(
            source_df,
            accepted,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=stop_loss_ticks,
            take_profit_ticks=take_profit_ticks,
            **execution_kwargs,
        )
    except Exception:  # pragma: no cover — defensive; caller controls inputs
        return _empty_trades_df()
    # simulate_trades can return a tuple when return_skipped_signals=True
    if isinstance(result, tuple):
        return result[0]
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_otf_validation_matrix(
    *,
    source_df: pd.DataFrame,
    candidate_signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    train_fraction: float = 0.7,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    setup_config: dict | None = None,
    signal_settings: dict | None = None,
    execution_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Evaluate the fixed OTF comparison matrix on a train/OOS split.

    For each of the five fixed OTF configurations, this function:

    1. Applies OTF filtering independently to *all* candidate signals
       (point-in-time safe; uses ``availability_timestamp`` from OTF engine).
    2. Splits accepted/rejected signals chronologically into train and OOS.
    3. Simulates trades separately for train and OOS accepted signals.
    4. Computes metrics for train, OOS, and full periods.

    Configuration selection, if any, must use train metrics only.  OOS
    metrics must never influence the train-selected configuration.

    Parameters
    ----------
    source_df:
        Canonical OHLCV DataFrame (columns: timestamp, open, high, low,
        close, volume).  The full dataset is used for OTF state calculation;
        only signals in each period drive the trade simulation.
    candidate_signals:
        All candidate signals to evaluate.  Not mutated.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES).
    point_value:
        Dollar value per full point (e.g. 50 for ES).
    stop_loss_ticks:
        Fixed SL distance in ticks.
    take_profit_ticks:
        Fixed TP distance in ticks.
    train_fraction:
        Fraction of signals (by chronological order) to use as the train
        period.  Default 0.7 (70%).  Must be in ``(0.0, 1.0)``.
    session_timezone:
        Exchange/session timezone label (e.g. ``"America/New_York"``).
        Required when signals use timezone-naive timestamps.
    eth_start:
        ETH session start time (e.g. ``"18:00"``).  Passed to the OTF
        engine for session-reset boundary detection.  ``None`` uses engine
        defaults.
    setup_config:
        Active setup config.  Currently unused; reserved for future signal
        filtering improvements.
    signal_settings:
        Signal-run metadata.  Currently unused; reserved for future use.
    execution_kwargs:
        Additional keyword arguments forwarded to :func:`simulate_trades`
        (e.g. ``commission_per_side``, ``slippage_ticks``).  Must not
        include ``tick_size``, ``point_value``, ``stop_loss_ticks``, or
        ``take_profit_ticks``.

    Returns
    -------
    pd.DataFrame
        One row per OTF configuration.  Columns are documented in the
        problem statement.  All metric columns are ``None`` when no trades
        were simulated.  The DataFrame includes a ``train_rank`` column
        (rank by ``train_expectancy_r``, ascending=False, 1=best) and an
        ``is_train_selected`` boolean column indicating the single
        highest-ranked train row.

    Raises
    ------
    ValueError
        If ``train_fraction`` is not in ``(0.0, 1.0)``, or if any matrix
        config fails normalization (should not occur for fixed configs).

    Notes
    -----
    ⚠️ **Diagnostic only.**  Results are not proof of edge.  Do not select
    an OTF configuration for production use based on full-dataset results.
    OOS metrics must only be used for evaluation, not selection.
    """
    if not (0.0 < train_fraction < 1.0):
        raise ValueError(f"train_fraction must be in (0.0, 1.0), got {train_fraction!r}")

    raw_exec_kw: dict[str, Any] = dict(execution_kwargs) if execution_kwargs else {}
    exec_kw = {
        key: value for key, value in raw_exec_kw.items() if key not in _RESERVED_EXECUTION_KEYS
    }

    # Deep copy + stable row ids so train/OOS membership survives filter
    # index resets on the enabled path. Input DataFrame is never mutated.
    candidates = _stamp_row_ids(candidate_signals)

    # Chronological train/OOS split on stamped row ids.
    train_set, oos_set = _chronological_train_oos_sets(candidates, train_fraction)

    matrix_entries = build_otf_matrix_configs()
    rows: list[dict[str, Any]] = []

    for entry in matrix_entries:
        label: str = entry["label"]
        otf_cfg: dict[str, Any] = entry["otf_config"]
        cfg_hash: str = entry["config_hash"]
        enabled: bool = bool(otf_cfg.get("enabled", False))
        timeframes: list[str] = list(otf_cfg.get("timeframes", []))

        # Apply OTF filter to all candidate signals.
        try:
            accepted_full, rejected_full = apply_otf_filter(
                source_df,
                candidates,
                enabled=enabled,
                timeframes=timeframes,
                alignment_mode=str(otf_cfg.get("alignment_mode", "all")),
                minimum_consecutive_bars=int(otf_cfg.get("minimum_consecutive_bars", 3)),
                session_timezone=session_timezone,
                eth_start=eth_start,
                session_reset=str(otf_cfg.get("session_reset", "session")),
            )
        except Exception as exc:
            raise ValueError(f"OTF filter failed for configuration '{label}': {exc}") from exc

        # Full-period counts.
        n_candidates = len(candidates)
        n_accepted = len(accepted_full)
        n_rejected = len(rejected_full)
        rejection_rate: float | None = n_rejected / n_candidates if n_candidates > 0 else None

        # Split into train/OOS periods by stamped row id (not pandas index).
        accepted_train = _drop_row_id(_filter_period(accepted_full, train_set))
        accepted_oos = _drop_row_id(_filter_period(accepted_full, oos_set))
        rejected_train = _drop_row_id(_filter_period(rejected_full, train_set))
        rejected_oos = _drop_row_id(_filter_period(rejected_full, oos_set))

        train_candidates = _count_period(candidates, train_set)
        oos_candidates = _count_period(candidates, oos_set)
        train_accepted = len(accepted_train)
        oos_accepted = len(accepted_oos)
        train_rejected = len(rejected_train)
        oos_rejected = len(rejected_oos)

        # Simulate trades.
        train_trades = _simulate(
            source_df,
            accepted_train,
            tick_size,
            point_value,
            stop_loss_ticks,
            take_profit_ticks,
            exec_kw,
        )
        oos_trades = _simulate(
            source_df,
            accepted_oos,
            tick_size,
            point_value,
            stop_loss_ticks,
            take_profit_ticks,
            exec_kw,
        )

        # Compute metrics.
        tm = _period_metrics(train_trades)
        om = _period_metrics(oos_trades)

        rows.append(
            {
                # Identity
                "configuration_label": label,
                "otf_filter_enabled": enabled,
                "otf_timeframes": ",".join(timeframes) if timeframes else "",
                "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                "otf_config_hash": cfg_hash,
                # Full-period counts
                "candidate_signal_count": n_candidates,
                "accepted_signal_count": n_accepted,
                "rejected_signal_count": n_rejected,
                "rejection_rate": rejection_rate,
                # Train counts
                "train_candidate_signal_count": train_candidates,
                "train_accepted_signal_count": train_accepted,
                "train_rejected_signal_count": train_rejected,
                # Train metrics
                "train_trade_count": tm["trade_count"],
                "train_expectancy_r": tm["expectancy_r"],
                "train_total_r": tm["total_r"],
                "train_avg_r": tm["avg_r"],
                "train_profit_factor": tm["profit_factor"],
                "train_max_drawdown_r": tm["max_drawdown_r"],
                "train_win_rate": tm["win_rate"],
                "train_long_trade_count": tm["long_trade_count"],
                "train_short_trade_count": tm["short_trade_count"],
                # OOS counts
                "oos_candidate_signal_count": oos_candidates,
                "oos_accepted_signal_count": oos_accepted,
                "oos_rejected_signal_count": oos_rejected,
                # OOS metrics
                "oos_trade_count": om["trade_count"],
                "oos_expectancy_r": om["expectancy_r"],
                "oos_total_r": om["total_r"],
                "oos_avg_r": om["avg_r"],
                "oos_profit_factor": om["profit_factor"],
                "oos_max_drawdown_r": om["max_drawdown_r"],
                "oos_win_rate": om["win_rate"],
                "oos_long_trade_count": om["long_trade_count"],
                "oos_short_trade_count": om["short_trade_count"],
            }
        )

    df = pd.DataFrame(rows)

    # Compute delta columns relative to no_otf baseline.
    _add_delta_columns(df)

    # Rank by train_expectancy_r (train metrics only; OOS never influences rank).
    _add_train_ranking(df)

    return df


def _add_delta_columns(df: pd.DataFrame) -> None:
    """Add delta columns relative to the no_otf baseline row (in-place)."""
    no_otf_mask = df["configuration_label"] == "no_otf"
    if not no_otf_mask.any():
        df["rejection_rate_delta_vs_no_otf"] = None
        df["oos_expectancy_delta_vs_no_otf"] = None
        df["oos_trade_count_delta_vs_no_otf"] = None
        return

    no_otf_row = df[no_otf_mask].iloc[0]
    base_rejection_rate = no_otf_row["rejection_rate"]
    base_oos_expectancy = no_otf_row["oos_expectancy_r"]
    base_oos_trade_count = no_otf_row["oos_trade_count"]

    def _delta(col: pd.Series, base: Any) -> pd.Series:
        if base is None or pd.isna(base):
            return pd.Series([None] * len(col), index=col.index)
        try:
            base_f = float(base)
        except (TypeError, ValueError):
            return pd.Series([None] * len(col), index=col.index)
        return col.apply(
            lambda v: (float(v) - base_f) if v is not None and not pd.isna(v) else None
        )

    df["rejection_rate_delta_vs_no_otf"] = _delta(df["rejection_rate"], base_rejection_rate)
    df["oos_expectancy_delta_vs_no_otf"] = _delta(df["oos_expectancy_r"], base_oos_expectancy)
    df["oos_trade_count_delta_vs_no_otf"] = _delta(df["oos_trade_count"], base_oos_trade_count)


def _add_train_ranking(df: pd.DataFrame) -> None:
    """Add train ranking columns using train_expectancy_r (in-place).

    Ranking uses train metrics only.  OOS metrics never influence selection.
    ``selected_by_train_metric`` names the metric used.  ``train_rank`` is
    1-based (1 = best).  ``is_train_selected`` is True for exactly one row.
    """
    df["selected_by_train_metric"] = "train_expectancy_r"

    metric_col = df["train_expectancy_r"]
    non_null = metric_col.dropna()

    if non_null.empty:
        df["train_rank"] = None
        df["is_train_selected"] = False
        return

    # Rank ascending=False so highest expectancy = rank 1.
    ranks = metric_col.rank(method="min", ascending=False, na_option="bottom")
    df["train_rank"] = ranks.apply(lambda r: int(r) if not pd.isna(r) else None)

    # Select the row with rank == 1.  If tied, first occurrence wins.
    best_idx = metric_col.idxmax()
    df["is_train_selected"] = df.index == best_idx
