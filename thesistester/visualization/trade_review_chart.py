"""Read-only, bounded single-trade review charts."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import plotly.graph_objects as go

from .backtest_chart import build_backtest_candlestick_chart


def trade_excursion_price_levels(trade: Mapping[str, Any]) -> dict[str, float | None]:
    """Derive terminal MAE/MFE price-envelope levels from a completed trade."""
    entry = pd.to_numeric(pd.Series([trade.get("entry_price")]), errors="coerce").iloc[0]
    mae = pd.to_numeric(pd.Series([trade.get("mae_points")]), errors="coerce").iloc[0]
    mfe = pd.to_numeric(pd.Series([trade.get("mfe_points")]), errors="coerce").iloc[0]
    if pd.isna(entry):
        return {"entry_price": None, "mae_price": None, "mfe_price": None}
    if str(trade.get("direction", "")).lower() == "short":
        return {
            "entry_price": float(entry),
            "mae_price": float(entry + mae) if pd.notna(mae) else None,
            "mfe_price": float(entry - mfe) if pd.notna(mfe) else None,
        }
    return {
        "entry_price": float(entry),
        "mae_price": float(entry - mae) if pd.notna(mae) else None,
        "mfe_price": float(entry + mfe) if pd.notna(mfe) else None,
    }


def _append_shapes(fig: go.Figure, shapes: list[dict[str, Any]]) -> None:
    existing = list(fig.layout.shapes) if fig.layout.shapes else []
    fig.update_layout(shapes=[*existing, *shapes])


def build_trade_review_chart(
    ohlcv_df: pd.DataFrame,
    trade: pd.Series,
    *,
    levels: pd.DataFrame | None = None,
    confluence_zones: pd.DataFrame | None = None,
    show_sessions: bool = True,
    show_levels: bool = True,
    show_confluence_zones: bool = True,
    show_sl_tp: bool = True,
    show_mae_mfe: bool = True,
    show_final_stop: bool = False,
) -> go.Figure:
    """Build a single-trade review chart from already-windowed data.

    MAE/MFE are terminal bar-extreme envelopes, not a reconstructed intrabar
    path. The function copies input frames through the existing chart builder.
    """
    trade_frame = pd.DataFrame([trade.copy(deep=True)])
    fig = build_backtest_candlestick_chart(
        ohlcv_df,
        trade_frame,
        levels=levels,
        confluence_zones=confluence_zones,
        show_sessions=show_sessions,
        show_levels=show_levels,
        show_confluence_zones=show_confluence_zones,
        show_sl_tp=show_sl_tp,
    )
    entry_ts = pd.to_datetime(trade.get("entry_timestamp"), errors="coerce", format="mixed")
    exit_ts = pd.to_datetime(trade.get("exit_timestamp"), errors="coerce", format="mixed")
    if pd.isna(entry_ts) or pd.isna(exit_ts):
        return fig

    shapes: list[dict[str, Any]] = []
    if show_mae_mfe:
        excursions = trade_excursion_price_levels(trade)
        entry_price = excursions["entry_price"]
        for label, color, price in (
            ("MAE envelope", "rgba(220, 20, 60, 0.16)", excursions["mae_price"]),
            ("MFE envelope", "rgba(46, 139, 87, 0.16)", excursions["mfe_price"]),
        ):
            if entry_price is None or price is None:
                continue
            shapes.append(
                {
                    "type": "rect",
                    "x0": entry_ts,
                    "x1": exit_ts,
                    "y0": min(entry_price, price),
                    "y1": max(entry_price, price),
                    "fillcolor": color,
                    "line": {"width": 0},
                    "layer": "below",
                    "name": label,
                }
            )
    if show_final_stop:
        final_stop = pd.to_numeric(
            pd.Series([trade.get("final_stop_price")]), errors="coerce"
        ).iloc[0]
        if pd.notna(final_stop):
            shapes.append(
                {
                    "type": "line",
                    "x0": entry_ts,
                    "x1": exit_ts,
                    "y0": float(final_stop),
                    "y1": float(final_stop),
                    "line": {"color": "darkorange", "width": 1.2, "dash": "dash"},
                    "name": "Final managed stop",
                }
            )
    _append_shapes(fig, shapes)
    fig.update_layout(title=f"Trade review #{trade.get('trade_id', '—')}")
    return fig
