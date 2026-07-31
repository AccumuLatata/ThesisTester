"""R10 tests: MAE/MFE excursion analytics and SL/TP calibration."""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.excursions import (
    add_excursion_r_columns,
    edge_ratio_summary,
    excursion_distribution,
    excursion_quadrant_counts,
    excursion_summary,
    sl_tp_hit_probability_grid,
)

TICK_SIZE = 0.25


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4],
            "direction": ["long", "long", "short", "short"],
            "trigger": ["touch", "reject", "touch", "reject"],
            "entry_timestamp": pd.to_datetime(
                [
                    "2026-06-01 09:31",
                    "2026-06-01 10:05",
                    "2026-06-01 11:15",
                    "2026-06-01 15:10",
                ]
            ).tz_localize("America/New_York"),
            "mae_points": [1.0, 0.5, 1.25, 0.0],
            "mfe_points": [2.0, 1.0, 2.0, 0.5],
            "stop_loss_ticks": [4.0, 4.0, 4.0, 4.0],
            "r_multiple": [-1.0, 1.0, -0.5, 0.5],
            "bars_held": [1, 2, 6, 12],
        }
    )


def test_empty_trades_are_safe():
    empty = pd.DataFrame()

    normalized = add_excursion_r_columns(empty, TICK_SIZE)
    assert normalized.empty
    assert {"risk_points", "mae_r", "mfe_r", "edge_ratio_r", "giveback_r"}.issubset(
        normalized.columns
    )
    assert excursion_distribution(empty, TICK_SIZE).empty
    assert excursion_quadrant_counts(empty, TICK_SIZE).empty
    assert sl_tp_hit_probability_grid(empty, TICK_SIZE, [1.0], [1.0]).empty
    assert edge_ratio_summary(empty, TICK_SIZE)["trade_count"] == 0
    assert excursion_summary(empty, TICK_SIZE)["available"] is False


def test_r_normalization_is_hand_computed():
    normalized = add_excursion_r_columns(_trades(), TICK_SIZE)

    # risk_points = 4 ticks * 0.25 = 1 point for every fixture trade.
    assert normalized["risk_points"].tolist() == [1.0, 1.0, 1.0, 1.0]
    assert normalized["mae_r"].tolist() == [1.0, 0.5, 1.25, 0.0]
    assert normalized["mfe_r"].tolist() == [2.0, 1.0, 2.0, 0.5]
    assert normalized["giveback_r"].tolist() == [3.0, 0.0, 2.5, 0.0]
    assert normalized.loc[0, "edge_ratio_r"] == 2.0
    assert pd.isna(normalized.loc[3, "edge_ratio_r"])


def test_distribution_overall_and_by_direction_trigger():
    overall = excursion_distribution(_trades(), TICK_SIZE)
    assert overall.to_dict(orient="records") == [
        {
            "group": "all",
            "trade_count": 4,
            "mean_mae_r": 0.6875,
            "median_mae_r": 0.75,
            "p25_mae_r": 0.375,
            "p75_mae_r": 1.0625,
            "p95_mae_r": 1.2125,
            "mean_mfe_r": 1.375,
            "median_mfe_r": 1.5,
            "p25_mfe_r": 0.875,
            "p75_mfe_r": 2.0,
            "p95_mfe_r": 2.0,
            "mean_edge_ratio_r": pytest.approx(1.8666666666666665),
            "median_edge_ratio_r": 2.0,
            "avg_r": 0.0,
            "avg_bars_held": 5.25,
            "sample_warning": False,
        }
    ]

    grouped = excursion_distribution(
        _trades(), TICK_SIZE, group_cols=["direction", "trigger"], min_trades=2
    )
    assert grouped[["direction", "trigger", "trade_count", "sample_warning"]].to_dict(
        orient="records"
    ) == [
        {"direction": "long", "trigger": "reject", "trade_count": 1, "sample_warning": True},
        {"direction": "long", "trigger": "touch", "trade_count": 1, "sample_warning": True},
        {"direction": "short", "trigger": "reject", "trade_count": 1, "sample_warning": True},
        {"direction": "short", "trigger": "touch", "trade_count": 1, "sample_warning": True},
    ]


def test_quadrant_classification_counts_and_pct():
    quadrants = excursion_quadrant_counts(_trades(), TICK_SIZE)
    by_label = quadrants.set_index("quadrant")

    assert by_label.loc["neither_threshold_reached", "count"] == 1
    assert by_label.loc["target_without_full_stop", "count"] == 1
    assert by_label.loc["stop_without_target", "count"] == 0
    assert by_label.loc["both_stop_and_target_reached", "count"] == 2
    assert by_label.loc["both_stop_and_target_reached", "pct"] == 0.5
    assert by_label.loc["target_without_full_stop", "avg_r"] == 1.0


def test_sl_tp_grid_stop_first_rule_counts_ambiguous_as_stop():
    grid = sl_tp_hit_probability_grid(_trades(), TICK_SIZE, [1.0], [1.5])
    row = grid.iloc[0].to_dict()

    assert row["stop_r"] == 1.0
    assert row["target_r"] == 1.5
    assert row["evaluated_trade_count"] == 4
    assert row["ambiguous_count"] == 2
    assert row["target_hit_count"] == 0
    assert row["stop_hit_count"] == 2
    assert row["unresolved_count"] == 2
    assert row["target_hit_probability"] == 0.0


def test_sl_tp_grid_target_first_and_exclude_ambiguous_rules():
    target_first = sl_tp_hit_probability_grid(
        _trades(), TICK_SIZE, [1.0], [1.5], both_hit_rule="target_first"
    ).iloc[0]
    assert target_first["target_hit_count"] == 2
    assert target_first["target_hit_probability"] == 0.5

    exclude = sl_tp_hit_probability_grid(
        _trades(), TICK_SIZE, [1.0], [1.5], both_hit_rule="exclude_ambiguous"
    ).iloc[0]
    assert exclude["evaluated_trade_count"] == 2
    assert exclude["ambiguous_count"] == 2
    assert exclude["target_hit_probability"] == 0.0


def test_edge_ratio_decay_proxy_by_bars_held():
    summary = edge_ratio_summary(_trades(), TICK_SIZE, bars_held_bins=(1, 3, 10))

    assert summary["trade_count"] == 4
    assert summary["mean_mfe_r"] == 1.375
    assert summary["mean_edge_ratio_r"] == pytest.approx(1.8666666666666665)
    assert summary["decay_by_bars_held"] == [
        {
            "bars_held_bucket": "1-1",
            "trade_count": 1,
            "mean_mfe_r": 2.0,
            "mean_mae_r": 1.0,
            "mean_edge_ratio_r": 2.0,
        },
        {
            "bars_held_bucket": "2-3",
            "trade_count": 1,
            "mean_mfe_r": 1.0,
            "mean_mae_r": 0.5,
            "mean_edge_ratio_r": 2.0,
        },
        {
            "bars_held_bucket": "4-10",
            "trade_count": 1,
            "mean_mfe_r": 2.0,
            "mean_mae_r": 1.25,
            "mean_edge_ratio_r": 1.6,
        },
        {
            "bars_held_bucket": ">10",
            "trade_count": 1,
            "mean_mfe_r": 0.5,
            "mean_mae_r": 0.0,
            "mean_edge_ratio_r": None,
        },
    ]


def test_excursion_summary_contract_is_stable():
    summary = excursion_summary(
        _trades(),
        TICK_SIZE,
        group_cols=["direction"],
        stop_r_grid=[1.0],
        target_r_grid=[1.5],
        min_trades=2,
    )

    assert set(summary) == {
        "schema_version",
        "available",
        "trade_count",
        "config",
        "overall",
        "grouped",
        "quadrants",
        "calibration_grid",
        "edge_ratio",
        "caveat",
    }
    assert summary["schema_version"] == 1
    assert summary["available"] is True
    assert summary["trade_count"] == 4
    assert summary["config"]["group_cols"] == ["direction"]
    assert summary["config"]["both_hit_rule"] == "stop_first"
    assert len(summary["overall"]) == 1
    assert len(summary["grouped"]) == 2
    assert len(summary["quadrants"]) == 4
    assert len(summary["calibration_grid"]) == 1


def test_invalid_inputs_raise_clear_errors():
    with pytest.raises(ValueError, match="tick_size"):
        add_excursion_r_columns(_trades(), 0.0)

    with pytest.raises(ValueError, match="both_hit_rule"):
        sl_tp_hit_probability_grid(_trades(), TICK_SIZE, [1.0], [1.0], both_hit_rule="random")

    with pytest.raises(ValueError, match="threshold"):
        excursion_quadrant_counts(_trades(), TICK_SIZE, mae_r_threshold=0)
