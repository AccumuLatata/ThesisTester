"""Phase 5 — Bar-by-bar backtest engine.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration.

Design notes
------------
- Simple triggers (touch / reject / break / reclaim) enter at next-bar open
  to avoid look-ahead bias.
- ``3c`` signals with ``status="filled"`` enter at ``retrace_entry_price`` on
  ``entry_bar_index``. ``status="void"`` rows are skipped.
- When both SL and TP are reachable within the same OHLC bar the engine
  exits at SL (SL-first / pessimistic rule), because intrabar event order
  is unknowable from OHLC data alone.
- Phase 5 is a single-risk-config backtest only; SL/TP grid search belongs
  to Phase 6.
"""
from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Trade output schema
# ---------------------------------------------------------------------------

_TRADE_COLUMNS: list[str] = [
    "trade_id",
    "signal_id",
    "trigger",
    "direction",
    "entry_timestamp",
    "entry_bar_index",
    "theoretical_entry_price",
    "entry_price",
    "entry_model",
    "exit_timestamp",
    "exit_bar_index",
    "theoretical_exit_price",
    "exit_price",
    "exit_reason",
    "stop_price",
    "target_price",
    "stop_loss_ticks",
    "take_profit_ticks",
    "gross_pnl_points",
    "gross_pnl_currency",
    "commission_cost",
    "slippage_cost",
    "net_pnl_currency",
    "pnl_points",
    "pnl_currency",
    "r_multiple",
    "bars_held",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "trigger_variant",
    "is_muted",
    "is_sfp",
    "inside_candle_count",
    "level_source_mode",
    "mae_points",
    "mfe_points",
    "status",
]


def _empty_trades_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_TRADE_COLUMNS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def simulate_trades(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    max_holding_bars: int | None = None,
    allow_same_bar_exit: bool = True,
    commission_per_side: float = 0.0,
    slippage_ticks: float = 0.0,
) -> pd.DataFrame:
    """Simulate bar-by-bar trades from Phase 4 candidate signals.

    Parameters
    ----------
    df:
        Canonical OHLCV DataFrame (``timestamp``, ``open``, ``high``,
        ``low``, ``close``, ``volume``).  Will be reset-indexed internally.
    signals:
        Phase 4 signal DataFrame from ``generate_signals``.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES/NQ).
    point_value:
        Dollar value per point (e.g. 50 for ES, 20 for NQ).
    stop_loss_ticks:
        Fixed stop-loss distance in ticks from entry.  Must be > 0.
    take_profit_ticks:
        Fixed take-profit distance in ticks from entry.
    max_holding_bars:
        If provided, force-close at this many bars after entry (TIME exit).
        ``None`` means hold until SL/TP or end of data.
    allow_same_bar_exit:
        If ``True`` (default), SL/TP checks begin on the entry bar itself.
        This matters for ``confirm_3bar`` filled entries where the bar is
        already closed.  Uses the SL-first pessimistic rule when both are
        reachable in the same bar.

    Returns
    -------
    pd.DataFrame
        One row per executed trade.  Returns an empty DataFrame with the
        correct schema when no trades are produced.

    Raises
    ------
    ValueError
        If ``stop_loss_ticks <= 0`` or cost inputs are negative.
    """
    if stop_loss_ticks <= 0:
        raise ValueError(
            f"stop_loss_ticks must be > 0, got {stop_loss_ticks!r}"
        )
    if tick_size <= 0:
        raise ValueError(f"tick_size must be > 0, got {tick_size!r}")
    if point_value <= 0:
        raise ValueError(f"point_value must be > 0, got {point_value!r}")
    if commission_per_side < 0:
        raise ValueError(
            f"commission_per_side must be >= 0, got {commission_per_side!r}"
        )
    if slippage_ticks < 0:
        raise ValueError(
            f"slippage_ticks must be >= 0, got {slippage_ticks!r}"
        )

    if signals is None or signals.empty:
        return _empty_trades_df()

    df_reset = df.reset_index(drop=True)
    n_bars = len(df_reset)

    sl_pts = float(stop_loss_ticks) * float(tick_size)
    tp_pts = float(take_profit_ticks) * float(tick_size)
    slip_pts = float(slippage_ticks) * float(tick_size)
    total_commission_cost = 2.0 * float(commission_per_side)
    risk_currency = float(stop_loss_ticks) * float(tick_size) * float(point_value)

    trades: list[dict] = []
    trade_id = 0

    for _, sig in signals.iterrows():
        trigger = str(sig["trigger"])
        direction = str(sig["direction"])
        bar_idx = int(sig["bar_index"])

        # ------------------------------------------------------------------
        # Determine entry bar and price
        # ------------------------------------------------------------------
        if trigger == "3c":
            if str(sig.get("status", "")) != "filled":
                # Void 3c signals are skipped.
                continue
            entry_bar_index = int(sig["entry_bar_index"])
            if entry_bar_index >= n_bars:
                continue
            theoretical_entry_price = float(sig["retrace_entry_price"])
            entry_model = "3c_retrace_market"
        elif trigger == "confirm_3bar":
            if str(sig.get("status", "")) != "filled":
                continue
            entry_bar_index = bar_idx
            theoretical_entry_price = float(sig["entry_reference_price"])
            entry_model = "bar3_stop_limit_fill"
        else:
            # Simple triggers enter at next-bar open (no look-ahead).
            entry_bar_index = bar_idx + 1
            if entry_bar_index >= n_bars:
                continue
            theoretical_entry_price = float(df_reset["open"].iloc[entry_bar_index])
            entry_model = "next_bar_open"

        if direction == "long":
            entry_price = theoretical_entry_price + slip_pts
        else:
            entry_price = theoretical_entry_price - slip_pts

        entry_ts = df_reset["timestamp"].iloc[entry_bar_index]

        # ------------------------------------------------------------------
        # Fixed SL / TP prices
        # ------------------------------------------------------------------
        if direction == "long":
            stop_price = entry_price - sl_pts
            target_price = entry_price + tp_pts
        else:
            stop_price = entry_price + sl_pts
            target_price = entry_price - tp_pts

        # ------------------------------------------------------------------
        # Bar-by-bar exit walk
        # ------------------------------------------------------------------
        exit_bar_index: int | None = None
        theoretical_exit_price: float | None = None
        exit_price: float | None = None
        exit_reason: str | None = None

        # MAE / MFE tracking (adverse / favorable excursion in points)
        mae_pts = 0.0  # worst excursion against position
        mfe_pts = 0.0  # best excursion in favour of position

        start_bar = entry_bar_index if allow_same_bar_exit else entry_bar_index + 1

        max_bar = n_bars - 1
        if max_holding_bars is not None:
            max_bar = min(max_bar, entry_bar_index + max_holding_bars - 1)

        for b in range(start_bar, max_bar + 1):
            bar = df_reset.iloc[b]
            bar_low = float(bar["low"])
            bar_high = float(bar["high"])

            # Track MAE / MFE
            if direction == "long":
                excursion_adverse = entry_price - bar_low
                excursion_favorable = bar_high - entry_price
            else:
                excursion_adverse = bar_high - entry_price
                excursion_favorable = entry_price - bar_low

            mae_pts = max(mae_pts, excursion_adverse)
            mfe_pts = max(mfe_pts, excursion_favorable)

            # Exit checks
            if direction == "long":
                stop_hit = bar_low <= stop_price
                target_hit = bar_high >= target_price
            else:
                stop_hit = bar_high >= stop_price
                target_hit = bar_low <= target_price

            if stop_hit and target_hit:
                # SL-first pessimistic rule
                exit_bar_index = b
                theoretical_exit_price = stop_price
                exit_reason = "SL"
                break
            elif stop_hit:
                exit_bar_index = b
                theoretical_exit_price = stop_price
                exit_reason = "SL"
                break
            elif target_hit:
                exit_bar_index = b
                theoretical_exit_price = target_price
                exit_reason = "TP"
                break

        if exit_bar_index is None:
            # No SL/TP hit — TIME or EOD
            if max_holding_bars is not None and (max_bar - entry_bar_index + 1) >= max_holding_bars:
                exit_bar_index = max_bar
                theoretical_exit_price = float(df_reset["close"].iloc[max_bar])
                exit_reason = "TIME"
            else:
                exit_bar_index = n_bars - 1
                theoretical_exit_price = float(df_reset["close"].iloc[n_bars - 1])
                exit_reason = "EOD"

        if direction == "long":
            exit_price = float(theoretical_exit_price) - slip_pts
        else:
            exit_price = float(theoretical_exit_price) + slip_pts

        exit_ts = df_reset["timestamp"].iloc[exit_bar_index]

        # ------------------------------------------------------------------
        # P&L and R calculation
        # ------------------------------------------------------------------
        if direction == "long":
            theoretical_pnl_points = float(theoretical_exit_price) - theoretical_entry_price
            gross_pnl_points = float(exit_price) - entry_price
        else:
            theoretical_pnl_points = theoretical_entry_price - float(theoretical_exit_price)
            gross_pnl_points = entry_price - float(exit_price)

        gross_pnl_currency = gross_pnl_points * float(point_value)
        # Cost modeling is adverse-only: any favorable rounding/noise is floored at 0.
        slippage_cost = max(
            0.0,
            (theoretical_pnl_points - gross_pnl_points) * float(point_value),
        )
        # gross_pnl_currency already reflects entry+exit slippage via slipped fills.
        # Net P&L subtracts round-turn commissions on top of that gross value.
        net_pnl_currency = gross_pnl_currency - total_commission_cost
        r_multiple = net_pnl_currency / risk_currency  # risk_currency is > 0

        bars_held = exit_bar_index - entry_bar_index + 1

        trades.append(
            {
                "trade_id": trade_id,
                "signal_id": int(sig["signal_id"]),
                "trigger": trigger,
                "direction": direction,
                "entry_timestamp": entry_ts,
                "entry_bar_index": entry_bar_index,
                "theoretical_entry_price": theoretical_entry_price,
                "entry_price": entry_price,
                "entry_model": entry_model,
                "exit_timestamp": exit_ts,
                "exit_bar_index": exit_bar_index,
                "theoretical_exit_price": float(theoretical_exit_price),
                "exit_price": float(exit_price),
                "exit_reason": exit_reason,
                "stop_price": stop_price,
                "target_price": target_price,
                "stop_loss_ticks": stop_loss_ticks,
                "take_profit_ticks": take_profit_ticks,
                "gross_pnl_points": gross_pnl_points,
                "gross_pnl_currency": gross_pnl_currency,
                "commission_cost": total_commission_cost,
                "slippage_cost": slippage_cost,
                "net_pnl_currency": net_pnl_currency,
                "pnl_points": gross_pnl_points,
                "pnl_currency": net_pnl_currency,
                "r_multiple": r_multiple,
                "bars_held": bars_held,
                "zone_low": sig.get("zone_low"),
                "zone_high": sig.get("zone_high"),
                "zone_mid": sig.get("zone_mid"),
                "level_count": sig.get("level_count"),
                "level_names": sig.get("level_names"),
                "trigger_variant": sig.get("trigger_variant"),
                "is_muted": sig.get("is_muted"),
                "is_sfp": sig.get("is_sfp"),
                "inside_candle_count": sig.get("inside_candle_count"),
                "level_source_mode": sig.get("level_source_mode"),
                "mae_points": mae_pts,
                "mfe_points": mfe_pts,
                "status": "closed",
            }
        )
        trade_id += 1

    if not trades:
        return _empty_trades_df()
    return pd.DataFrame(trades)
