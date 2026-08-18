"""tests/test_otf_validation.py — OTF statistical validation helper tests (PR 6).

Covers:
- Matrix structure and determinism
- Train/OOS split correctness
- Metrics computation
- Zero-trade robustness
- Ranking/selection uses train metrics only
- Delta columns
- Disabled row matches no-OTF simulation
- Input immutability
- Invalid train_fraction raises
"""

from __future__ import annotations


import pandas as pd
import pytest

from thesistester.analytics.otf_validation import (
    OTF_V1_DEFAULTS,
    _MATRIX_SPECS,
    _add_train_ranking,
    _chronological_train_oos_sets,
    _train_price_split_bar,
    build_otf_matrix_configs,
    run_otf_validation_matrix,
)
from thesistester.engine.otf import OTF_ALGORITHM_VERSION
from thesistester.setup import _default_otf_filter_config

TZ = "America/New_York"
TICK = 0.25
PV = 50.0
SL_TICKS = 8
TP_TICKS = 16


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _source_bars(
    start: str = "2026-01-02 09:00",
    count: int = 240,
    trend: str = "up",
    tz: str = TZ,
) -> pd.DataFrame:
    """Generate synthetic 1-minute OHLCV bars for a single RTH session."""
    timestamps = pd.date_range(start, periods=count, freq="1min", tz=tz)
    rows = []
    price = 100.0
    for ts in timestamps:
        if trend == "up":
            o, h, l, c = price, price + 1.0, price - 0.5, price + 0.8
        elif trend == "down":
            o, h, l, c = price, price + 0.5, price - 1.0, price - 0.8
        else:
            o, h, l, c = price, price + 0.5, price - 0.5, price
        rows.append(
            {
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100.0,
            }
        )
        price += 0.1 if trend == "up" else -0.1
    return pd.DataFrame(rows)


def _signals(n: int = 20, direction: str = "long", tz: str = TZ) -> pd.DataFrame:
    """Generate n synthetic candidate signals."""
    rows = []
    base = pd.Timestamp("2026-01-02 10:00:00", tz=tz)
    for i in range(n):
        rows.append(
            {
                "signal_id": i,
                "timestamp": base + pd.Timedelta(minutes=i * 5),
                "bar_index": i,
                "direction": direction,
                "trigger": "touch",
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "A",
                "entry_reference_price": 100.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": "",
            }
        )
    return pd.DataFrame(rows)


def _source_and_signals_for_validation() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return source_df and candidate signals suitable for matrix validation."""
    source = _source_bars(count=240, trend="up")
    sigs = _signals(n=20, direction="long")
    return source, sigs


# ---------------------------------------------------------------------------
# 1. Matrix contains exactly the five required configurations
# ---------------------------------------------------------------------------


def test_matrix_has_five_entries():
    configs = build_otf_matrix_configs()
    assert len(configs) == 5


def test_matrix_labels_are_correct():
    configs = build_otf_matrix_configs()
    labels = [c["label"] for c in configs]
    assert labels == [
        "no_otf",
        "otf_15m",
        "otf_30m",
        "otf_15m_30m",
        "otf_5m_15m_30m",
    ]


# ---------------------------------------------------------------------------
# 2. Labels are deterministic
# ---------------------------------------------------------------------------


def test_matrix_labels_deterministic():
    labels_a = [c["label"] for c in build_otf_matrix_configs()]
    labels_b = [c["label"] for c in build_otf_matrix_configs()]
    assert labels_a == labels_b


# ---------------------------------------------------------------------------
# 3. No-OTF row has disabled config
# ---------------------------------------------------------------------------


def test_no_otf_row_is_disabled():
    configs = build_otf_matrix_configs()
    no_otf = configs[0]
    assert no_otf["label"] == "no_otf"
    assert not no_otf["otf_config"]["enabled"]
    assert no_otf["otf_config"]["timeframes"] == []
    assert no_otf["otf_config"] == _default_otf_filter_config()


# ---------------------------------------------------------------------------
# 4. Enabled rows have correct timeframes
# ---------------------------------------------------------------------------


def test_enabled_rows_have_correct_timeframes():
    configs = build_otf_matrix_configs()
    expected = {
        "otf_15m": ["15m"],
        "otf_30m": ["30m"],
        "otf_15m_30m": ["15m", "30m"],
        "otf_5m_15m_30m": ["5m", "15m", "30m"],
    }
    for cfg in configs:
        if cfg["label"] in expected:
            assert cfg["otf_config"]["enabled"] is True
            assert cfg["otf_config"]["timeframes"] == expected[cfg["label"]]


# ---------------------------------------------------------------------------
# 5. Config hashes are present and stable
# ---------------------------------------------------------------------------


def test_config_hashes_present():
    configs = build_otf_matrix_configs()
    for cfg in configs:
        assert "config_hash" in cfg
        h = cfg["config_hash"]
        assert isinstance(h, str) and len(h) > 0


def test_config_hashes_stable():
    configs_a = build_otf_matrix_configs()
    configs_b = build_otf_matrix_configs()
    for a, b in zip(configs_a, configs_b):
        assert a["config_hash"] == b["config_hash"]


def test_config_hashes_unique():
    configs = build_otf_matrix_configs()
    hashes = [c["config_hash"] for c in configs]
    assert len(set(hashes)) == len(hashes), "All config hashes must be unique"


# ---------------------------------------------------------------------------
# 6. Candidate / accepted / rejected counts reconcile
# ---------------------------------------------------------------------------


def test_counts_reconcile():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    for _, row in result.iterrows():
        total = row["candidate_signal_count"]
        acc = row["accepted_signal_count"]
        rej = row["rejected_signal_count"]
        assert acc + rej == total, (
            f"Counts don't reconcile for {row['configuration_label']}: {acc} + {rej} != {total}"
        )

        # Train/OOS split reconciles within candidate count
        t_acc = row["train_accepted_signal_count"]
        t_rej = row["train_rejected_signal_count"]
        o_acc = row["oos_accepted_signal_count"]
        o_rej = row["oos_rejected_signal_count"]

        t_cand = row["train_candidate_signal_count"]
        o_cand = row["oos_candidate_signal_count"]

        assert t_cand + o_cand == total
        assert t_acc + t_rej == t_cand
        assert o_acc + o_rej == o_cand


def test_enabled_train_oos_split_survives_nondefault_index():
    """Enabled OTF path resets pandas index; split must use stable row ids.

    Regression: membership via ``df.index.isin(train_set)`` after
    ``apply_otf_filter(..., enabled=True)`` emptied train/OOS partitions when
    candidate signals used a non-default index.
    """
    source, sigs = _source_and_signals_for_validation()
    sigs = sigs.copy()
    sigs.index = range(1000, 1000 + len(sigs))

    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )

    for _, row in result.iterrows():
        label = row["configuration_label"]
        total = row["candidate_signal_count"]
        t_cand = row["train_candidate_signal_count"]
        o_cand = row["oos_candidate_signal_count"]
        t_acc = row["train_accepted_signal_count"]
        t_rej = row["train_rejected_signal_count"]
        o_acc = row["oos_accepted_signal_count"]
        o_rej = row["oos_rejected_signal_count"]

        assert t_cand + o_cand == total, label
        assert t_acc + t_rej == t_cand, label
        assert o_acc + o_rej == o_cand, label
        assert t_acc + o_acc == row["accepted_signal_count"], label
        assert t_rej + o_rej == row["rejected_signal_count"], label

        if row["otf_filter_enabled"]:
            # Non-trivial enabled configs must not collapse all period counts.
            assert t_cand > 0 and o_cand > 0, label


def test_reserved_execution_kwargs_are_stripped():
    """Reserved simulate_trades kwargs in execution_kwargs must not abort runs."""
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
        execution_kwargs={
            "tick_size": 999.0,
            "point_value": 1.0,
            "stop_loss_ticks": 1,
            "take_profit_ticks": 1,
        },
    )
    assert len(result) == 5
    no_otf = result[result["configuration_label"] == "no_otf"].iloc[0]
    assert no_otf["train_candidate_signal_count"] > 0


# ---------------------------------------------------------------------------
# 7. Rejection rate is correct
# ---------------------------------------------------------------------------


def test_rejection_rate_correct():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    for _, row in result.iterrows():
        n = row["candidate_signal_count"]
        rej = row["rejected_signal_count"]
        rate = row["rejection_rate"]
        if n > 0:
            assert abs(rate - rej / n) < 1e-9, (
                f"Rejection rate mismatch for {row['configuration_label']}"
            )
        else:
            assert rate is None


def test_no_otf_row_rejection_rate_is_zero():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    no_otf_row = result[result["configuration_label"] == "no_otf"].iloc[0]
    assert no_otf_row["rejection_rate"] == 0.0
    assert no_otf_row["rejected_signal_count"] == 0
    assert no_otf_row["accepted_signal_count"] == no_otf_row["candidate_signal_count"]


# ---------------------------------------------------------------------------
# 8. Zero-trade rows do not crash
# ---------------------------------------------------------------------------


def test_zero_signals_does_not_crash():
    source = _source_bars(count=240)
    empty_sigs = _signals(n=0)
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=empty_sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    assert len(result) == 5
    for _, row in result.iterrows():
        assert row["candidate_signal_count"] == 0
        assert row["accepted_signal_count"] == 0
        assert row["train_trade_count"] == 0
        assert row["oos_trade_count"] == 0


def test_zero_trade_metrics_are_none_or_zero():
    source = _source_bars(count=240)
    empty_sigs = _signals(n=0)
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=empty_sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    for _, row in result.iterrows():
        assert row["train_expectancy_r"] is None
        assert row["oos_expectancy_r"] is None


# ---------------------------------------------------------------------------
# 9. Train/OOS split is chronological
# ---------------------------------------------------------------------------


def test_train_oos_split_is_chronological():
    sigs = _signals(n=10, direction="long")
    train_set, oos_set = _chronological_train_oos_sets(sigs, 0.7)

    # Sort by timestamp to get expected order
    sorted_idx = sigs.sort_values("timestamp", kind="stable").index.tolist()
    n_train = int(10 * 0.7)  # = 7

    expected_train = frozenset(sorted_idx[:n_train])
    expected_oos = frozenset(sorted_idx[n_train:])

    assert train_set == expected_train
    assert oos_set == expected_oos


def test_train_oos_sets_are_disjoint():
    sigs = _signals(n=20)
    train_set, oos_set = _chronological_train_oos_sets(sigs, 0.7)
    assert len(train_set & oos_set) == 0


def test_train_oos_sets_cover_all_rows():
    sigs = _signals(n=20)
    train_set, oos_set = _chronological_train_oos_sets(sigs, 0.7)
    all_idx = frozenset(sigs.index.tolist())
    assert train_set | oos_set == all_idx


def test_train_candidate_count_matches_fraction():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        train_fraction=0.7,
        session_timezone=TZ,
    )
    n = len(sigs)
    n_train_expected = int(n * 0.7)
    for _, row in result.iterrows():
        assert row["train_candidate_signal_count"] == n_train_expected
        assert row["oos_candidate_signal_count"] == n - n_train_expected


# ---------------------------------------------------------------------------
# 10. Train metrics and OOS metrics are separate
# ---------------------------------------------------------------------------


def test_train_and_oos_metric_columns_exist():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    required_train = [
        "train_trade_count",
        "train_expectancy_r",
        "train_total_r",
        "train_avg_r",
        "train_profit_factor",
        "train_max_drawdown_r",
        "train_win_rate",
    ]
    required_oos = [
        "oos_trade_count",
        "oos_expectancy_r",
        "oos_total_r",
        "oos_avg_r",
        "oos_profit_factor",
        "oos_max_drawdown_r",
        "oos_win_rate",
    ]
    for col in required_train + required_oos:
        assert col in result.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# 11 & 12. Ranking uses train metrics only; OOS never affects selection
# ---------------------------------------------------------------------------


def test_train_rank_column_present():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    assert "train_rank" in result.columns
    assert "is_train_selected" in result.columns
    assert "selected_by_train_metric" in result.columns


def test_is_train_selected_exactly_one():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    selected_count = result["is_train_selected"].sum()
    assert selected_count == 1, f"Expected exactly 1 train-selected row, got {selected_count}"


def test_train_selected_has_best_train_expectancy():
    """Selected row must have the highest train_expectancy_r."""
    # Build a synthetic DataFrame and verify ranking picks the right row.
    df = pd.DataFrame(
        {
            "configuration_label": ["no_otf", "otf_15m", "otf_30m"],
            "train_expectancy_r": [0.1, 0.5, 0.3],
            "oos_expectancy_r": [0.4, 0.0, 0.2],  # OOS should NOT influence
            "train_rank": [None, None, None],
            "is_train_selected": [False, False, False],
            "selected_by_train_metric": ["train_expectancy_r"] * 3,
            "oos_trade_count": [10, 5, 8],  # irrelevant for selection
        }
    )
    _add_train_ranking(df)
    selected = df[df["is_train_selected"]]
    assert len(selected) == 1
    assert selected.iloc[0]["configuration_label"] == "otf_15m"
    assert int(selected.iloc[0]["train_rank"]) == 1


def test_train_rank_uses_train_metric_not_oos():
    """Changing OOS expectancy must NOT change which row is train-selected."""
    df_base = pd.DataFrame(
        {
            "configuration_label": ["no_otf", "otf_15m"],
            "train_expectancy_r": [0.2, 0.4],
            "oos_expectancy_r": [0.8, 0.1],  # OOS reversed
            "train_rank": [None, None],
            "is_train_selected": [False, False],
            "selected_by_train_metric": ["train_expectancy_r"] * 2,
            "oos_trade_count": [10, 5],
        }
    )
    _add_train_ranking(df_base)
    # otf_15m has better train expectancy; must be selected regardless of OOS
    selected = df_base[df_base["is_train_selected"]]
    assert selected.iloc[0]["configuration_label"] == "otf_15m"


# ---------------------------------------------------------------------------
# 13. Invalid train_fraction raises
# ---------------------------------------------------------------------------


def test_invalid_train_fraction_zero_raises():
    source, sigs = _source_and_signals_for_validation()
    with pytest.raises(ValueError, match="train_fraction"):
        run_otf_validation_matrix(
            source_df=source,
            candidate_signals=sigs,
            tick_size=TICK,
            point_value=PV,
            stop_loss_ticks=SL_TICKS,
            take_profit_ticks=TP_TICKS,
            train_fraction=0.0,
            session_timezone=TZ,
        )


def test_invalid_train_fraction_one_raises():
    source, sigs = _source_and_signals_for_validation()
    with pytest.raises(ValueError, match="train_fraction"):
        run_otf_validation_matrix(
            source_df=source,
            candidate_signals=sigs,
            tick_size=TICK,
            point_value=PV,
            stop_loss_ticks=SL_TICKS,
            take_profit_ticks=TP_TICKS,
            train_fraction=1.0,
            session_timezone=TZ,
        )


def test_invalid_train_fraction_negative_raises():
    source, sigs = _source_and_signals_for_validation()
    with pytest.raises(ValueError, match="train_fraction"):
        run_otf_validation_matrix(
            source_df=source,
            candidate_signals=sigs,
            tick_size=TICK,
            point_value=PV,
            stop_loss_ticks=SL_TICKS,
            take_profit_ticks=TP_TICKS,
            train_fraction=-0.1,
            session_timezone=TZ,
        )


def test_valid_train_fractions_accepted():
    source, sigs = _source_and_signals_for_validation()
    for frac in (0.5, 0.7, 0.8):
        result = run_otf_validation_matrix(
            source_df=source,
            candidate_signals=sigs,
            tick_size=TICK,
            point_value=PV,
            stop_loss_ticks=SL_TICKS,
            take_profit_ticks=TP_TICKS,
            train_fraction=frac,
            session_timezone=TZ,
        )
        assert len(result) == 5


# ---------------------------------------------------------------------------
# 14. Input DataFrames are not mutated
# ---------------------------------------------------------------------------


def test_source_df_not_mutated():
    source, sigs = _source_and_signals_for_validation()
    source_before = source.copy(deep=True)
    run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    pd.testing.assert_frame_equal(source, source_before)


def test_candidate_signals_not_mutated():
    source, sigs = _source_and_signals_for_validation()
    sigs_before = sigs.copy(deep=True)
    run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    pd.testing.assert_frame_equal(sigs, sigs_before)


# ---------------------------------------------------------------------------
# 15. Disabled row matches legacy no-OTF simulation
# ---------------------------------------------------------------------------


def test_no_otf_row_same_as_legacy_simulation():
    """no_otf accepted_signal_count must equal all candidate signals."""
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    no_otf = result[result["configuration_label"] == "no_otf"].iloc[0]
    assert no_otf["accepted_signal_count"] == len(sigs)
    assert no_otf["rejected_signal_count"] == 0
    assert bool(no_otf["otf_filter_enabled"]) is False


# ---------------------------------------------------------------------------
# Required columns are all present
# ---------------------------------------------------------------------------


def test_all_required_columns_present():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    required_cols = [
        "configuration_label",
        "otf_filter_enabled",
        "otf_timeframes",
        "otf_algorithm_version",
        "otf_config_hash",
        "session_timezone",
        "eth_start",
        "candidate_signal_count",
        "accepted_signal_count",
        "rejected_signal_count",
        "rejection_rate",
        "train_candidate_signal_count",
        "train_accepted_signal_count",
        "train_rejected_signal_count",
        "train_trade_count",
        "train_expectancy_r",
        "train_total_r",
        "train_avg_r",
        "train_profit_factor",
        "train_max_drawdown_r",
        "train_win_rate",
        "oos_candidate_signal_count",
        "oos_accepted_signal_count",
        "oos_rejected_signal_count",
        "oos_trade_count",
        "oos_expectancy_r",
        "oos_total_r",
        "oos_avg_r",
        "oos_profit_factor",
        "oos_max_drawdown_r",
        "oos_win_rate",
        "rejection_rate_delta_vs_no_otf",
        "oos_expectancy_delta_vs_no_otf",
        "oos_trade_count_delta_vs_no_otf",
        "train_rank",
        "is_train_selected",
        "selected_by_train_metric",
    ]
    for col in required_cols:
        assert col in result.columns, f"Missing required column: {col}"


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Session boundary metadata is recorded
# ---------------------------------------------------------------------------


def test_matrix_records_session_timezone_and_eth_start():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
        eth_start="18:00",
    )
    assert (result["session_timezone"] == TZ).all()
    assert (result["eth_start"] == "18:00").all()


# OTF algorithm version is correct
# ---------------------------------------------------------------------------


def test_otf_algorithm_version_correct():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    for _, row in result.iterrows():
        assert row["otf_algorithm_version"] == OTF_ALGORITHM_VERSION


# ---------------------------------------------------------------------------
# Matrix spec stability (regression guard)
# ---------------------------------------------------------------------------


def test_matrix_spec_order_stable():
    labels = [s["label"] for s in _MATRIX_SPECS]
    assert labels == [
        "no_otf",
        "otf_15m",
        "otf_30m",
        "otf_15m_30m",
        "otf_5m_15m_30m",
    ]


def test_v1_defaults_contain_required_keys():
    required = {"alignment_mode", "minimum_consecutive_bars", "session_reset"}
    assert required.issubset(OTF_V1_DEFAULTS.keys())
    assert OTF_V1_DEFAULTS["alignment_mode"] == "all"
    assert OTF_V1_DEFAULTS["minimum_consecutive_bars"] == 3
    assert OTF_V1_DEFAULTS["session_reset"] == "session"


# ---------------------------------------------------------------------------
# 16 / 17. Build config defaults are deterministic; train fraction validation
# ---------------------------------------------------------------------------


def test_build_otf_matrix_configs_deterministic():
    a = build_otf_matrix_configs()
    b = build_otf_matrix_configs()
    assert a == b


# ---------------------------------------------------------------------------
# Delta columns are correct
# ---------------------------------------------------------------------------


def test_delta_columns_for_no_otf_are_zero_or_none():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    no_otf = result[result["configuration_label"] == "no_otf"].iloc[0]
    # no_otf delta vs itself should be exactly 0
    assert no_otf["rejection_rate_delta_vs_no_otf"] is not None
    assert abs(float(no_otf["rejection_rate_delta_vs_no_otf"])) < 1e-9


# ---------------------------------------------------------------------------
# Regression: simulate_trades unchanged
# ---------------------------------------------------------------------------


def test_simulate_trades_still_works_directly():
    """simulate_trades behavior is not affected by otf_validation import."""
    from thesistester.engine.backtest import simulate_trades

    source = _source_bars(count=120)
    sigs = _signals(n=5)
    trades = simulate_trades(
        source,
        sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
    )
    assert isinstance(trades, pd.DataFrame)


# ---------------------------------------------------------------------------
# Return type is a DataFrame with 5 rows
# ---------------------------------------------------------------------------


def test_result_is_dataframe_with_five_rows():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# AH3 — train price prefix (C3)
# ---------------------------------------------------------------------------


def _flat_bars(
    count: int, *, spike_at: int | None = None, spike_high: float = 110.0
) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-02 09:00", periods=count, freq="1min", tz=TZ)
    rows = []
    for i, ts in enumerate(timestamps):
        high = spike_high if spike_at is not None and i >= spike_at else 100.0
        rows.append(
            {
                "timestamp": ts,
                "open": 100.0,
                "high": high,
                "low": 100.0,
                "close": 100.0,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


def _signal_at(source: pd.DataFrame, *, signal_id: int, bar_index: int) -> dict:
    row = _signals(n=1).iloc[0].to_dict()
    row["signal_id"] = signal_id
    row["bar_index"] = bar_index
    row["timestamp"] = source.iloc[bar_index]["timestamp"]
    return row


def test_ah3_p1_oos_spike_does_not_inflate_train_expectancy(monkeypatch):
    """OOS-only spike must not lift train_expectancy_r (fails on full-frame leak)."""
    from thesistester.analytics import otf_validation as ov
    from thesistester.analytics.metrics import summarize_trades
    from thesistester.engine.backtest import simulate_trades

    n_bars = 30
    oos_bar = 18
    spike_at = 22
    source = _flat_bars(n_bars, spike_at=spike_at)
    train_sig = _signal_at(source, signal_id=0, bar_index=2)
    oos_sig = _signal_at(source, signal_id=1, bar_index=oos_bar)
    sigs = pd.DataFrame([train_sig, oos_sig])
    train_only = pd.DataFrame([train_sig])

    leak_trades = simulate_trades(
        source,
        train_only,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
    )
    prefix_trades = simulate_trades(
        source.iloc[:oos_bar],
        train_only,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
    )
    leak_r = summarize_trades(leak_trades).get("expectancy_r")
    prefix_r = summarize_trades(prefix_trades).get("expectancy_r")
    assert leak_r is not None and prefix_r is not None
    assert leak_r != prefix_r

    seen_lens: list[int] = []
    real_filter = ov.apply_otf_filter

    def _spy(source_df, *args, **kwargs):
        seen_lens.append(len(source_df))
        return real_filter(source_df, *args, **kwargs)

    monkeypatch.setattr(ov, "apply_otf_filter", _spy)

    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        train_fraction=0.7,
        session_timezone=TZ,
    )
    no_otf = result[result["configuration_label"] == "no_otf"].iloc[0]
    assert no_otf["train_expectancy_r"] == prefix_r
    assert no_otf["train_expectancy_r"] != leak_r
    assert seen_lens == [n_bars] * 5
    assert int(result["is_train_selected"].sum()) == 1
    selected = result[result["is_train_selected"]].iloc[0]
    assert selected["train_expectancy_r"] == result["train_expectancy_r"].max()


def test_ah3_p2_no_oos_uses_full_train_prices():
    empty = pd.DataFrame()
    assert _train_price_split_bar(empty, 30) == 30
    assert _train_price_split_bar(pd.DataFrame({"timestamp": []}), 12) == 12

    source = _flat_bars(24)
    sigs = pd.DataFrame([_signal_at(source, signal_id=0, bar_index=3)])
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        train_fraction=0.7,
        session_timezone=TZ,
    )
    # One signal → n_train = int(0.7) = 0; all OOS. Train empty; OOS = today.
    from thesistester.analytics.metrics import summarize_trades
    from thesistester.engine.backtest import simulate_trades

    oos_trades = simulate_trades(
        source,
        sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
    )
    expected_oos = summarize_trades(oos_trades).get("expectancy_r")
    no_otf = result[result["configuration_label"] == "no_otf"].iloc[0]
    assert no_otf["train_trade_count"] == 0
    assert no_otf["train_expectancy_r"] is None
    assert no_otf["oos_expectancy_r"] == expected_oos


def test_ah3_p3_ranking_still_uses_train_columns_only():
    source, sigs = _source_and_signals_for_validation()
    result = run_otf_validation_matrix(
        source_df=source,
        candidate_signals=sigs,
        tick_size=TICK,
        point_value=PV,
        stop_loss_ticks=SL_TICKS,
        take_profit_ticks=TP_TICKS,
        session_timezone=TZ,
    )
    assert (result["selected_by_train_metric"] == "train_expectancy_r").all()
    assert int(result["is_train_selected"].sum()) == 1
    selected = result[result["is_train_selected"]].iloc[0]
    ranked = result.dropna(subset=["train_expectancy_r"])
    assert selected["train_expectancy_r"] == ranked["train_expectancy_r"].max()


def test_ah3_p4_otf_validation_does_not_import_walk_forward():
    import ast
    from pathlib import Path

    source = Path("thesistester/analytics/otf_validation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "walk_forward" not in alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "walk_forward" not in node.module
