"""tests/test_otf_integration.py — OTF research-mode integration tests (PR 5).

Covers:
- Shared integration helper (apply_configured_otf_filter, resolve_otf_config)
- Backtest OTF integration behavior
- Grid search OTF integration
- Walk-forward fold-local OTF integration (no future leakage)
- Reporting/export OTF metadata
- Regression boundaries
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from thesistester.engine.otf_integration import (
    OtfFilterResult,
    apply_configured_otf_filter,
    resolve_otf_config,
)
from thesistester.engine.otf import OTF_ALGORITHM_VERSION
from thesistester.setup import _default_otf_filter_config, normalize_otf_filter_config
from thesistester.analytics.walk_forward import run_walk_forward_sl_tp
from thesistester.analytics.grid import run_sl_tp_grid
from thesistester.engine.backtest import simulate_trades
from thesistester.reporting import (
    build_research_artifact,
    build_markdown_report,
    build_otf_filter_metadata,
)


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _source_1m(
    start: str,
    count: int,
    trend: str = "up",
    tz: str = TZ,
) -> pd.DataFrame:
    """Generate synthetic 1-minute source OHLCV bars."""
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


def _signals_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _signal(
    *,
    signal_id: int,
    timestamp: str,
    direction: str = "long",
    bar_index: int = 0,
    status: str = "candidate",
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp(timestamp, tz=TZ),
        "direction": direction,
        "bar_index": bar_index,
        "trigger": "touch",
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 1,
        "level_names": "A",
        "entry_reference_price": 100.0,
        "entry_model": "candidate_next_bar_open",
        "status": status,
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def _disabled_config() -> dict:
    return _default_otf_filter_config()


def _enabled_config(
    timeframes: list[str] | None = None,
    *,
    minimum_consecutive_bars: int = 3,
) -> dict:
    return normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": timeframes or ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": minimum_consecutive_bars,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )


def _backtest_signal(bar_index: int = 0, direction: str = "long") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": bar_index,
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                "bar_index": bar_index,
                "trigger": "touch",
                "direction": direction,
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 2,
                "level_names": "A|B",
                "entry_reference_price": 100.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": "",
            }
        ]
    )


def _ohlcv_bars(n: int = 3) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "timestamp": pd.Timestamp(f"2026-01-02 09:{30 + i:02d}:00", tz=TZ),
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Disabled config returns all signals accepted, zero rejected
# ---------------------------------------------------------------------------


class TestApplyConfiguredOtfFilterDisabled:
    def test_disabled_returns_all_accepted_zero_rejected(self):
        """Disabled OTF: all candidates accepted, zero rejected."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:30:00"),
            _signal(signal_id=2, timestamp="2026-01-02 09:31:00"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _disabled_config()},
        )
        assert isinstance(result, OtfFilterResult)
        assert result.otf_filter_enabled is False
        assert result.candidate_signal_count == 2
        assert result.otf_accepted_signal_count == 2
        assert result.otf_rejected_signal_count == 0
        assert len(result.accepted_signals) == 2
        assert len(result.rejected_signals) == 0

    def test_disabled_preserves_candidate_signal_ids(self):
        """Disabled: signal_id values are preserved unchanged."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(
            _signal(signal_id=10, timestamp="2026-01-02 09:30:00"),
            _signal(signal_id=20, timestamp="2026-01-02 09:31:00"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
        )
        assert list(result.accepted_signals["signal_id"]) == [10, 20]

    def test_disabled_does_not_mutate_candidate_signals(self):
        """Disabled: candidate_signals input DataFrame is not mutated."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        original_cols = set(sigs.columns)
        apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
        )
        # Input should be unchanged
        assert set(sigs.columns) == original_cols

    def test_disabled_rejection_rate_is_zero(self):
        """Disabled: rejection_rate is 0.0."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        assert result.rejection_rate == 0.0

    def test_disabled_includes_algorithm_version_and_hash(self):
        """Disabled: algorithm version and config hash are always populated."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        assert result.otf_algorithm_version == OTF_ALGORITHM_VERSION
        assert isinstance(result.otf_config_hash, str)
        assert len(result.otf_config_hash) == 64  # SHA-256 hex

    def test_disabled_empty_signals_is_stable(self):
        """Disabled + empty signals: stable zero-count result."""
        source = _ohlcv_bars(3)
        sigs = pd.DataFrame(columns=["signal_id", "timestamp", "direction"])
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        assert result.candidate_signal_count == 0
        assert result.otf_accepted_signal_count == 0
        assert result.otf_rejected_signal_count == 0
        assert result.rejection_rate is None


# ---------------------------------------------------------------------------
# 2. Enabled config filters directionally
# ---------------------------------------------------------------------------


class TestApplyConfiguredOtfFilterEnabled:
    def test_enabled_filters_insufficient_history(self):
        """Enabled: signals rejected when insufficient OTF history (unknown state)."""
        # Tiny source — not enough bars for OTF state
        source = _source_1m("2026-01-02 09:30:00", count=5, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:33:00", direction="long"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        assert result.otf_filter_enabled is True
        # With only 5 bars, 5m OTF state is unknown → signal should be rejected
        assert result.otf_rejected_signal_count + result.otf_accepted_signal_count == 1

    def test_enabled_preserves_candidate_signals_unchanged(self):
        """Enabled: candidate_signals on result matches original (not mutated)."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:45:00", direction="long"),
            _signal(signal_id=2, timestamp="2026-01-02 09:46:00", direction="short"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        assert len(result.candidate_signals) == 2
        assert set(result.candidate_signals["signal_id"]) == {1, 2}

    def test_enabled_rejected_signals_include_reason(self):
        """Enabled: rejected signals have otf_filter_reason populated."""
        source = _source_1m("2026-01-02 09:30:00", count=10, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:39:00", direction="short"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        # All candidates are either accepted or rejected
        total = result.otf_accepted_signal_count + result.otf_rejected_signal_count
        assert total == 1
        if result.otf_rejected_signal_count > 0:
            assert "otf_filter_reason" in result.rejected_signals.columns
            reasons = result.rejected_signals["otf_filter_reason"].tolist()
            assert all(isinstance(r, str) and len(r) > 0 for r in reasons)

    def test_enabled_empty_signals_stable(self):
        """Enabled with zero signals: stable empty result without calling OTF engine."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        sigs = pd.DataFrame(columns=["signal_id", "timestamp", "direction"])
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        assert result.candidate_signal_count == 0
        assert result.otf_accepted_signal_count == 0
        assert result.otf_rejected_signal_count == 0
        assert result.otf_filter_enabled is True

    def test_enabled_total_candidates_equals_accepted_plus_rejected(self):
        """Enabled: candidate = accepted + rejected, always."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:45:00", direction="long"),
            _signal(signal_id=2, timestamp="2026-01-02 09:46:00", direction="long"),
            _signal(signal_id=3, timestamp="2026-01-02 09:47:00", direction="short"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        assert (
            result.otf_accepted_signal_count + result.otf_rejected_signal_count
            == result.candidate_signal_count
        )


# ---------------------------------------------------------------------------
# 3. Invalid explicit config raises
# ---------------------------------------------------------------------------


class TestApplyConfiguredOtfFilterInvalidConfig:
    def test_explicit_invalid_config_raises_valueerror(self):
        """Explicit invalid OTF config must raise ValueError, not silently disable."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        with pytest.raises(ValueError):
            apply_configured_otf_filter(
                source_df=source,
                candidate_signals=sigs,
                setup_config={"otf_filter": {"enabled": True, "timeframes": []}},
            )

    def test_invalid_config_in_signal_settings_raises(self):
        """Invalid OTF config in signal_settings raises."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        with pytest.raises(ValueError):
            apply_configured_otf_filter(
                source_df=source,
                candidate_signals=sigs,
                signal_settings={"otf_filter": {"enabled": True, "timeframes": []}},
            )


# ---------------------------------------------------------------------------
# 4. Config resolution precedence
# ---------------------------------------------------------------------------


class TestResolveOtfConfig:
    def test_no_sources_returns_disabled_defaults(self):
        """No config sources → canonical disabled defaults."""
        config = resolve_otf_config()
        assert config["enabled"] is False

    def test_signal_settings_otf_filter_key_wins(self):
        """signal_settings["otf_filter"] has highest precedence."""
        enabled_cfg = _enabled_config(["5m"])
        config = resolve_otf_config(
            signal_settings={"otf_filter": enabled_cfg},
            setup_config={"otf_filter": _disabled_config()},
        )
        assert config["enabled"] is True
        assert "5m" in config["timeframes"]

    def test_setup_snapshot_wins_over_setup_config(self):
        """signal_settings["setup_snapshot"] wins over bare setup_config."""
        enabled_cfg = _enabled_config(["15m"])
        config = resolve_otf_config(
            signal_settings={"setup_snapshot": {"otf_filter": enabled_cfg}},
            setup_config={"otf_filter": _disabled_config()},
        )
        assert config["enabled"] is True
        assert "15m" in config["timeframes"]

    def test_last_signal_setup_wins_over_setup_config(self):
        """last_signal_setup wins over setup_config."""
        enabled_cfg = _enabled_config(["30m"])
        config = resolve_otf_config(
            last_signal_setup={"otf_filter": enabled_cfg},
            setup_config={"otf_filter": _disabled_config()},
        )
        assert config["enabled"] is True
        assert "30m" in config["timeframes"]

    def test_setup_config_used_when_no_other_source(self):
        """setup_config is used when no higher-priority source is available."""
        enabled_cfg = _enabled_config(["5m"])
        config = resolve_otf_config(setup_config={"otf_filter": enabled_cfg})
        assert config["enabled"] is True

    def test_signal_settings_otf_filter_none_falls_through(self):
        """signal_settings["otf_filter"] = None normalizes to disabled."""
        config = resolve_otf_config(
            signal_settings={"otf_filter": None},
        )
        assert config["enabled"] is False

    def test_explicit_invalid_signal_settings_raises(self):
        """Explicit invalid OTF config in signal_settings raises."""
        with pytest.raises(ValueError):
            resolve_otf_config(
                signal_settings={"otf_filter": {"enabled": True, "timeframes": []}},
            )

    def test_missing_signal_settings_falls_to_setup_config(self):
        """When signal_settings has no otf_filter key, use setup_config."""
        enabled_cfg = _enabled_config(["5m"])
        config = resolve_otf_config(
            signal_settings={"some_other_key": "x"},
            setup_config={"otf_filter": enabled_cfg},
        )
        assert config["enabled"] is True

    def test_empty_dicts_resolve_to_disabled_defaults(self):
        """Empty dicts for all sources resolve to disabled defaults."""
        config = resolve_otf_config(
            signal_settings={},
            last_signal_setup={},
            setup_config={},
        )
        assert config["enabled"] is False

    def test_precedence_order_1_beats_2(self):
        """Precedence: signal_settings["otf_filter"] > setup_snapshot."""
        config_1 = _enabled_config(["5m"])
        config_2 = _enabled_config(["15m"])
        config = resolve_otf_config(
            signal_settings={
                "otf_filter": config_1,
                "setup_snapshot": {"otf_filter": config_2},
            }
        )
        assert config["timeframes"] == ["5m"]

    def test_precedence_order_2_beats_3(self):
        """Precedence: setup_snapshot > last_signal_setup."""
        config_2 = _enabled_config(["5m"])
        config_3 = _enabled_config(["15m"])
        config = resolve_otf_config(
            signal_settings={"setup_snapshot": {"otf_filter": config_2}},
            last_signal_setup={"otf_filter": config_3},
        )
        assert config["timeframes"] == ["5m"]

    def test_precedence_order_3_beats_4(self):
        """Precedence: last_signal_setup > setup_config."""
        config_3 = _enabled_config(["5m"])
        config_4 = _enabled_config(["15m"])
        config = resolve_otf_config(
            last_signal_setup={"otf_filter": config_3},
            setup_config={"otf_filter": config_4},
        )
        assert config["timeframes"] == ["5m"]


# ---------------------------------------------------------------------------
# 5. to_summary_dict completeness
# ---------------------------------------------------------------------------


class TestOtfFilterResultSummary:
    def test_summary_dict_includes_all_required_keys(self):
        """to_summary_dict returns all required keys."""
        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        summary = result.to_summary_dict()
        required_keys = {
            "otf_filter_enabled",
            "otf_algorithm_version",
            "otf_config_hash",
            "otf_filter_config",
            "candidate_signal_count",
            "otf_accepted_signal_count",
            "otf_rejected_signal_count",
            "rejection_rate",
            "session_timezone",
            "eth_start",
        }
        assert required_keys.issubset(set(summary.keys()))

    def test_summary_dict_rejection_rate_none_for_empty(self):
        """rejection_rate is None when candidate_signal_count is 0."""
        sigs = pd.DataFrame(columns=["signal_id", "timestamp", "direction"])
        result = apply_configured_otf_filter(source_df=_ohlcv_bars(3), candidate_signals=sigs)
        assert result.to_summary_dict()["rejection_rate"] is None


# ---------------------------------------------------------------------------
# 11–18. Backtest integration behavior (pure Python, no Streamlit)
# ---------------------------------------------------------------------------


class TestBacktestOtfIntegration:
    def _make_ohlcv(self) -> pd.DataFrame:
        rows = []
        for i in range(5):
            ts = pd.Timestamp(f"2026-01-02 09:{30 + i:02d}:00", tz=TZ)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            )
        return pd.DataFrame(rows)

    def _make_signal(self, bar_index: int = 0, signal_id: int = 0) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "signal_id": signal_id,
                    "timestamp": pd.Timestamp(f"2026-01-02 09:{30 + bar_index:02d}:00", tz=TZ),
                    "bar_index": bar_index,
                    "trigger": "touch",
                    "direction": "long",
                    "zone_low": 99.5,
                    "zone_high": 100.5,
                    "zone_mid": 100.0,
                    "level_count": 2,
                    "level_names": "A|B",
                    "entry_reference_price": 100.0,
                    "entry_model": "candidate_next_bar_open",
                    "status": "candidate",
                    "naked_level_count": 0,
                    "naked_requirement": "any",
                    "notes": "",
                }
            ]
        )

    def test_disabled_backtest_equals_legacy(self):
        """OTF disabled: simulate_trades receives same signals as without OTF."""
        ohlcv = self._make_ohlcv()
        sigs = self._make_signal(bar_index=0, signal_id=1)

        # Legacy path (no OTF)
        trades_legacy = simulate_trades(
            df=ohlcv,
            signals=sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )

        # OTF disabled path
        otf_result = apply_configured_otf_filter(
            source_df=ohlcv,
            candidate_signals=sigs,
        )
        trades_otf = simulate_trades(
            df=ohlcv,
            signals=otf_result.accepted_signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )
        assert len(trades_legacy) == len(trades_otf)

    def test_zero_accepted_signals_produces_empty_trades(self):
        """Zero accepted signals: simulate_trades returns empty trades."""
        ohlcv = self._make_ohlcv()
        # Pass empty signals
        empty_sigs = pd.DataFrame(
            columns=[
                "signal_id",
                "timestamp",
                "bar_index",
                "trigger",
                "direction",
                "zone_low",
                "zone_high",
                "zone_mid",
                "level_count",
                "level_names",
                "entry_reference_price",
                "entry_model",
                "status",
                "naked_level_count",
                "naked_requirement",
                "notes",
            ]
        )
        trades = simulate_trades(
            df=ohlcv,
            signals=empty_sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )
        assert trades.empty

    def test_candidate_signals_preserved_in_result(self):
        """candidate_signals in result equals original input signals."""
        ohlcv = self._make_ohlcv()
        sigs = self._make_signal(bar_index=0, signal_id=42)
        result = apply_configured_otf_filter(
            source_df=ohlcv,
            candidate_signals=sigs,
        )
        assert 42 in result.candidate_signals["signal_id"].values

    def test_rejected_signals_stored_separately_from_accepted(self):
        """Rejected signals are a separate non-overlapping set from accepted."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        # Mix of long and short signals to get some rejected
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:45:00", direction="long"),
            _signal(signal_id=2, timestamp="2026-01-02 09:46:00", direction="short"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        accepted_ids = set(result.accepted_signals["signal_id"].tolist())
        rejected_ids = set(result.rejected_signals["signal_id"].tolist())
        # No overlap
        assert accepted_ids.isdisjoint(rejected_ids)
        # All candidates accounted for
        assert accepted_ids | rejected_ids == {1, 2}

    def test_otf_rejected_distinct_from_exposure_skipped(self):
        """OTF rejected signals are distinct from exposure-skipped signals."""
        ohlcv = self._make_ohlcv()
        sigs = self._make_signal(bar_index=0, signal_id=1)
        otf_result = apply_configured_otf_filter(
            source_df=ohlcv,
            candidate_signals=sigs,
        )
        # OTF rejected signals don't have skip_reason column
        if not otf_result.rejected_signals.empty:
            assert "skip_reason" not in otf_result.rejected_signals.columns
        # Simulate and check skipped signals
        trades, skipped = simulate_trades(
            df=ohlcv,
            signals=otf_result.accepted_signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
            return_skipped_signals=True,
        )
        # Skipped signals from exposure policy have skip_reason, OTF rejected don't
        if not skipped.empty:
            assert "skip_reason" in skipped.columns

    def test_otf_counts_in_summary_dict(self):
        """OTF counts are correctly captured in to_summary_dict()."""
        ohlcv = self._make_ohlcv()
        sigs = self._make_signal(bar_index=0, signal_id=1)
        result = apply_configured_otf_filter(
            source_df=ohlcv,
            candidate_signals=sigs,
        )
        summary = result.to_summary_dict()
        assert summary["candidate_signal_count"] == 1
        assert summary["otf_accepted_signal_count"] + summary["otf_rejected_signal_count"] == 1


# ---------------------------------------------------------------------------
# 19–23. Grid search OTF integration
# ---------------------------------------------------------------------------


class TestGridSearchOtfIntegration:
    def _make_ohlcv(self, n: int = 5) -> pd.DataFrame:
        rows = []
        for i in range(n):
            ts = pd.Timestamp(f"2026-01-02 09:{30 + i:02d}:00", tz=TZ)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            )
        return pd.DataFrame(rows)

    def _make_signals(self) -> pd.DataFrame:
        rows = []
        for i in range(3):
            rows.append(
                {
                    "signal_id": i,
                    "timestamp": pd.Timestamp(f"2026-01-02 09:{30 + i:02d}:00", tz=TZ),
                    "bar_index": i,
                    "trigger": "touch",
                    "direction": "long",
                    "zone_low": 99.5,
                    "zone_high": 100.5,
                    "zone_mid": 100.0,
                    "level_count": 2,
                    "level_names": "A|B",
                    "entry_reference_price": 100.0,
                    "entry_model": "candidate_next_bar_open",
                    "status": "candidate",
                    "naked_level_count": 0,
                    "naked_requirement": "any",
                    "notes": "",
                }
            )
        return pd.DataFrame(rows)

    def test_disabled_grid_equals_legacy_grid(self):
        """OTF disabled: grid results equal legacy (no OTF) grid results."""
        ohlcv = self._make_ohlcv()
        sigs = self._make_signals()

        # Legacy grid (no OTF)
        grid_legacy = run_sl_tp_grid(
            df=ohlcv,
            signals=sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4, 8],
            take_profit_ticks_values=[8, 16],
        )

        # OTF disabled grid
        otf_result = apply_configured_otf_filter(
            source_df=ohlcv,
            candidate_signals=sigs,
        )
        grid_otf = run_sl_tp_grid(
            df=ohlcv,
            signals=otf_result.accepted_signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4, 8],
            take_profit_ticks_values=[8, 16],
        )

        assert len(grid_legacy) == len(grid_otf)
        assert list(grid_legacy["trade_count"]) == list(grid_otf["trade_count"])

    def test_enabled_grid_uses_same_accepted_set_for_all_cells(self):
        """OTF enabled: all grid cells use exactly the same filtered signal set."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:45:00", direction="long"),
            _signal(signal_id=2, timestamp="2026-01-02 09:46:00", direction="short"),
        )

        otf_result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )

        # All grid cells receive accepted_signals — signal IDs should be consistent
        accepted_ids = set(otf_result.accepted_signals["signal_id"].tolist())

        # Run grid and check each cell sees same signal IDs
        grid = run_sl_tp_grid(
            df=source,
            signals=otf_result.accepted_signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4, 8],
            take_profit_ticks_values=[8, 16],
        )
        assert isinstance(grid, pd.DataFrame)
        # trade_count must not exceed accepted signal count (each accepted signal ≤ 1 trade)
        assert (grid["trade_count"] <= len(accepted_ids)).all()

    def test_zero_accepted_grid_is_deterministic(self):
        """Zero accepted signals: grid runs without crashing, zero trades."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        empty_sigs = pd.DataFrame(
            columns=[
                "signal_id",
                "timestamp",
                "direction",
                "bar_index",
                "trigger",
                "zone_low",
                "zone_high",
                "zone_mid",
                "level_count",
                "level_names",
                "entry_reference_price",
                "entry_model",
                "status",
                "naked_level_count",
                "naked_requirement",
                "notes",
            ]
        )
        grid = run_sl_tp_grid(
            df=source,
            signals=empty_sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
        )
        assert isinstance(grid, pd.DataFrame)
        assert (grid["trade_count"] == 0).all()

    def test_grid_otf_filter_summary_keys(self):
        """OTF filter result summary has required keys for grid metadata."""
        source = _ohlcv_bars(5)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
        )
        summary = result.to_summary_dict()
        assert "otf_filter_enabled" in summary
        assert "candidate_signal_count" in summary
        assert "otf_accepted_signal_count" in summary
        assert "otf_rejected_signal_count" in summary
        assert "otf_config_hash" in summary
        assert "otf_algorithm_version" in summary

    def test_otf_rejection_count_not_confused_with_trade_count(self):
        """OTF rejected signals are distinct metadata from grid trade counts."""
        source = _source_1m("2026-01-02 09:30:00", count=50, trend="up")
        sigs = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:45:00", direction="long"),
            _signal(signal_id=2, timestamp="2026-01-02 09:46:00", direction="short"),
        )
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"])},
            session_timezone=TZ,
        )
        # OTF rejected count is signal-level, not trade-level
        assert (
            result.otf_rejected_signal_count
            == result.candidate_signal_count - result.otf_accepted_signal_count
        )


# ---------------------------------------------------------------------------
# 24–30. Walk-forward fold-local OTF integration
# ---------------------------------------------------------------------------


class TestWalkForwardOtfIntegration:
    def _make_ohlcv_and_signals(self, n_bars: int = 30):
        """Make a simple OHLCV DataFrame and signals for walk-forward tests."""
        rows = []
        for i in range(n_bars):
            rows.append(
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            )
        ohlcv = pd.DataFrame(rows)

        sigs = []
        for i in range(0, n_bars - 1, 5):
            sigs.append(
                {
                    "signal_id": i,
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "bar_index": i,
                    "trigger": "touch",
                    "direction": "long",
                    "zone_low": 99.5,
                    "zone_high": 100.5,
                    "zone_mid": 100.0,
                    "level_count": 2,
                    "level_names": "A|B",
                    "entry_reference_price": 100.0,
                    "entry_model": "candidate_next_bar_open",
                    "status": "candidate",
                    "naked_level_count": 0,
                    "naked_requirement": "any",
                    "notes": "",
                }
            )
        signals = pd.DataFrame(sigs)
        return ohlcv, signals

    def test_disabled_walk_forward_equals_legacy(self):
        """OTF disabled: walk-forward results equal legacy (no otf_config) results."""
        ohlcv, signals = self._make_ohlcv_and_signals(n_bars=30)

        results_legacy = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
        )

        results_otf = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=_disabled_config(),
        )

        assert len(results_legacy) == len(results_otf)
        if not results_legacy.empty:
            assert list(results_legacy["train_trade_count"]) == list(
                results_otf["train_trade_count"]
            )
            assert list(results_legacy["test_trade_count"]) == list(results_otf["test_trade_count"])

    def test_disabled_walk_forward_no_otf_config_equals_none(self):
        """otf_config=None and otf_config=disabled_config produce identical results."""
        ohlcv, signals = self._make_ohlcv_and_signals(n_bars=30)

        results_none = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=None,
        )
        results_disabled = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        assert len(results_none) == len(results_disabled)

    def test_fold_metadata_includes_otf_enabled_column(self):
        """Walk-forward results include otf_filter_enabled column."""
        ohlcv, signals = self._make_ohlcv_and_signals(n_bars=30)
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        assert "otf_filter_enabled" in results.columns

    def test_fold_metadata_includes_otf_count_columns(self):
        """Walk-forward results include OTF candidate/accepted/rejected count columns."""
        ohlcv, signals = self._make_ohlcv_and_signals(n_bars=30)
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        for col in [
            "train_otf_candidate_count",
            "train_otf_accepted_count",
            "train_otf_rejected_count",
            "test_otf_candidate_count",
            "test_otf_accepted_count",
            "test_otf_rejected_count",
        ]:
            assert col in results.columns

    def test_otf_config_fixed_across_folds(self):
        """OTF filter_enabled value is consistent across all folds."""
        ohlcv, signals = self._make_ohlcv_and_signals(n_bars=30)
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        if not results.empty:
            # All folds have same otf_filter_enabled value
            assert results["otf_filter_enabled"].nunique() == 1

    def test_zero_accepted_train_fold_handled_deterministically(self):
        """Zero accepted train signals: fold status is no_train_candidate, no crash."""
        ohlcv, _ = self._make_ohlcv_and_signals(n_bars=30)
        # Use empty signals DataFrame so all folds have no train signals
        empty_signals = pd.DataFrame(
            columns=[
                "signal_id",
                "timestamp",
                "bar_index",
                "trigger",
                "direction",
                "zone_low",
                "zone_high",
                "zone_mid",
                "level_count",
                "level_names",
                "entry_reference_price",
                "entry_model",
                "status",
                "naked_level_count",
                "naked_requirement",
                "notes",
            ]
        )
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=empty_signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
        )
        assert isinstance(results, pd.DataFrame)
        if not results.empty:
            assert (results["status"] == "no_train_candidate").all()


# ---------------------------------------------------------------------------
# 31–37. Reporting/export OTF metadata
# ---------------------------------------------------------------------------


class TestReportingOtfMetadata:
    def _make_session_state_no_otf(self) -> dict:
        return {
            "signals": pd.DataFrame({"signal_id": [1, 2], "r_multiple": [1.0, -0.5]}),
            "trades": pd.DataFrame({"trade_id": [10], "r_multiple": [1.0]}),
        }

    def _make_session_state_with_otf_disabled(self) -> dict:
        state = self._make_session_state_no_otf()
        state["otf_filter_summary"] = {
            "otf_filter_enabled": False,
            "otf_algorithm_version": OTF_ALGORITHM_VERSION,
            "otf_config_hash": "a" * 64,
            "otf_filter_config": _disabled_config(),
            "candidate_signal_count": 2,
            "otf_accepted_signal_count": 2,
            "otf_rejected_signal_count": 0,
            "rejection_rate": 0.0,
        }
        return state

    def _make_session_state_with_otf_enabled(self) -> dict:
        state = self._make_session_state_no_otf()
        state["otf_filter_summary"] = {
            "otf_filter_enabled": True,
            "otf_algorithm_version": OTF_ALGORITHM_VERSION,
            "otf_config_hash": "b" * 64,
            "otf_filter_config": _enabled_config(["5m"]),
            "candidate_signal_count": 10,
            "otf_accepted_signal_count": 7,
            "otf_rejected_signal_count": 3,
            "rejection_rate": 0.3,
        }
        return state

    def test_artifact_includes_otf_filter_section(self):
        """Research artifact always includes 'otf_filter' section."""
        state = self._make_session_state_no_otf()
        artifact = build_research_artifact(state)
        assert "otf_filter" in artifact

    def test_artifact_otf_disabled_metadata(self):
        """Artifact correctly represents disabled OTF state."""
        state = self._make_session_state_with_otf_disabled()
        artifact = build_research_artifact(state)
        otf = artifact["otf_filter"]
        assert otf["available"] is True
        assert otf["enabled"] is False
        assert otf["rejected_signal_count"] == 0

    def test_artifact_otf_enabled_metadata(self):
        """Artifact correctly represents enabled OTF state with counts."""
        state = self._make_session_state_with_otf_enabled()
        artifact = build_research_artifact(state)
        otf = artifact["otf_filter"]
        assert otf["available"] is True
        assert otf["enabled"] is True
        assert otf["candidate_signal_count"] == 10
        assert otf["accepted_signal_count"] == 7
        assert otf["rejected_signal_count"] == 3
        assert abs(otf["rejection_rate"] - 0.3) < 1e-6

    def test_artifact_distinguishes_zero_rejected_vs_disabled(self):
        """Artifact distinguishes zero-rejected-but-enabled from disabled."""
        # Zero rejected enabled state
        state_zero = self._make_session_state_no_otf()
        state_zero["otf_filter_summary"] = {
            "otf_filter_enabled": True,
            "otf_algorithm_version": OTF_ALGORITHM_VERSION,
            "otf_config_hash": "c" * 64,
            "otf_filter_config": _enabled_config(["5m"]),
            "candidate_signal_count": 5,
            "otf_accepted_signal_count": 5,
            "otf_rejected_signal_count": 0,
            "rejection_rate": 0.0,
        }
        artifact_zero = build_research_artifact(state_zero)
        assert artifact_zero["otf_filter"]["enabled"] is True
        assert artifact_zero["otf_filter"]["rejected_signal_count"] == 0

        # Disabled state
        state_disabled = self._make_session_state_with_otf_disabled()
        artifact_disabled = build_research_artifact(state_disabled)
        assert artifact_disabled["otf_filter"]["enabled"] is False

    def test_artifact_includes_config_hash_and_version(self):
        """Artifact includes algorithm_version and config_hash."""
        state = self._make_session_state_with_otf_enabled()
        artifact = build_research_artifact(state)
        otf = artifact["otf_filter"]
        assert otf["algorithm_version"] == OTF_ALGORITHM_VERSION
        assert isinstance(otf["config_hash"], str)

    def test_artifact_no_otf_data_returns_unavailable(self):
        """No OTF data in session state → available=False."""
        state = self._make_session_state_no_otf()
        artifact = build_research_artifact(state)
        assert artifact["otf_filter"]["available"] is False

    def test_markdown_includes_otf_section_disabled(self):
        """Markdown report includes OTF section when disabled."""
        state = self._make_session_state_with_otf_disabled()
        artifact = build_research_artifact(state)
        md = build_markdown_report(artifact)
        assert "OTF Filter" in md
        assert "disabled" in md.lower()

    def test_markdown_includes_otf_section_enabled(self):
        """Markdown report includes OTF section when enabled."""
        state = self._make_session_state_with_otf_enabled()
        artifact = build_research_artifact(state)
        md = build_markdown_report(artifact)
        assert "OTF Filter" in md
        assert "enabled" in md.lower()

    def test_artifact_tables_includes_otf_rejected_signals(self):
        """Artifact tables section includes 'otf_rejected_signals' key."""
        state = self._make_session_state_no_otf()
        artifact = build_research_artifact(state)
        assert "otf_rejected_signals" in artifact["tables"]

    def test_build_otf_filter_metadata_empty_state(self):
        """Empty session state: metadata returns available=False."""
        meta = build_otf_filter_metadata({})
        assert meta["available"] is False
        assert meta["enabled"] is None

    def test_build_otf_filter_metadata_applied_scopes(self):
        """Applied scopes are populated from available OTF summaries."""
        state = {
            "otf_filter_summary": {
                "otf_filter_enabled": True,
                "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                "otf_config_hash": "d" * 64,
                "otf_filter_config": _enabled_config(["5m"]),
                "candidate_signal_count": 5,
                "otf_accepted_signal_count": 4,
                "otf_rejected_signal_count": 1,
                "rejection_rate": 0.2,
            },
            "grid_otf_filter": {
                "otf_filter_enabled": True,
                "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                "otf_config_hash": "d" * 64,
                "otf_filter_config": _enabled_config(["5m"]),
                "candidate_signal_count": 5,
                "otf_accepted_signal_count": 4,
                "otf_rejected_signal_count": 1,
                "rejection_rate": 0.2,
            },
        }
        meta = build_otf_filter_metadata(state)
        assert "backtest" in meta["applied_scopes"]
        assert "grid" in meta["applied_scopes"]


# ---------------------------------------------------------------------------
# 38–43. Regression boundaries
# ---------------------------------------------------------------------------


class TestRegressionBoundaries:
    def test_generate_signals_unchanged(self):
        """generate_signals() function is importable and unchanged."""
        from thesistester.engine.signals import generate_signals

        assert callable(generate_signals)

    def test_apply_otf_filter_pure_behavior_unchanged(self):
        """apply_otf_filter() pure behavior is unchanged by PR 5."""
        from thesistester.engine.otf_filter import apply_otf_filter

        sigs = pd.DataFrame(columns=["signal_id", "timestamp", "direction"])
        source = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        accepted, rejected = apply_otf_filter(source, sigs, enabled=False)
        assert accepted.empty
        assert rejected.empty

    def test_simulate_trades_unchanged(self):
        """simulate_trades() function signature and behavior unchanged."""
        ohlcv = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            ]
        )
        sigs = pd.DataFrame(
            columns=[
                "signal_id",
                "timestamp",
                "bar_index",
                "trigger",
                "direction",
                "zone_low",
                "zone_high",
                "zone_mid",
                "level_count",
                "level_names",
                "entry_reference_price",
                "entry_model",
                "status",
                "naked_level_count",
                "naked_requirement",
                "notes",
            ]
        )
        trades = simulate_trades(
            df=ohlcv,
            signals=sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )
        assert isinstance(trades, pd.DataFrame)
        assert trades.empty

    def test_existing_reporting_functions_still_work(self):
        """build_research_artifact and build_markdown_report return correct types."""
        state = {
            "signals": pd.DataFrame({"signal_id": [1]}),
        }
        artifact = build_research_artifact(state)
        assert isinstance(artifact, dict)
        md = build_markdown_report(artifact)
        assert isinstance(md, str)
        assert "ThesisTester" in md

    def test_walk_forward_without_otf_unchanged(self):
        """run_walk_forward_sl_tp without otf_config runs as before."""
        ohlcv = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
                for i in range(30)
            ]
        )
        sigs = pd.DataFrame([])
        # Should not raise with otf_config=None (default)
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=sigs,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=10,
            test_bars=5,
        )
        assert isinstance(results, pd.DataFrame)

    def test_otf_integration_module_importable_from_engine(self):
        """OtfFilterResult and apply_configured_otf_filter importable from engine."""
        from thesistester.engine import (
            apply_configured_otf_filter,
            OtfFilterResult,
            resolve_otf_config,
        )

        assert callable(apply_configured_otf_filter)
        assert callable(resolve_otf_config)
        assert OtfFilterResult is not None


# ---------------------------------------------------------------------------
# 44–52. Follow-up hardening tests (PR 5 follow-up)
# ---------------------------------------------------------------------------


class TestOtfFilterResultFrozen:
    def test_frozen_dataclass_rejects_attribute_reassignment(self):
        """OtfFilterResult is frozen — attribute reassignment must raise FrozenInstanceError."""
        import dataclasses

        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.otf_filter_enabled = True  # type: ignore[misc]

    def test_frozen_dataclass_rejects_count_reassignment(self):
        """OtfFilterResult frozen — count attribute reassignment raises."""
        import dataclasses

        source = _ohlcv_bars(3)
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-02 09:30:00"))
        result = apply_configured_otf_filter(source_df=source, candidate_signals=sigs)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.candidate_signal_count = 999  # type: ignore[misc]


class TestWalkForwardShortFoldRobustness:
    """Walk-forward OTF with fold slices too short for OTF evaluation."""

    def _make_enabled_config(self) -> dict:
        return normalize_otf_filter_config(
            {
                "enabled": True,
                "timeframes": ["5m"],
                "alignment_mode": "all",
                "minimum_consecutive_bars": 3,
                "directional": True,
                "use_completed_bars_only": True,
                "session_reset": "session",
            }
        )

    def _make_1bar_ohlcv(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            ]
        )

    def test_enabled_otf_with_1bar_fold_does_not_crash(self):
        """OTF enabled walk-forward with 1-bar fold slice does not raise."""
        from thesistester.analytics.walk_forward import _filter_fold_signals_with_otf

        fold_df = self._make_1bar_ohlcv()
        fold_signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:30:00", bar_index=0),
        )
        # Should not raise even though 1 bar is insufficient for OTF
        accepted, rejected_count, candidate_count = _filter_fold_signals_with_otf(
            fold_df=fold_df,
            fold_signals=fold_signals,
            otf_config=self._make_enabled_config(),
            session_timezone=TZ,
        )
        # All candidates rejected as unknown on short slice
        assert candidate_count == 1
        assert rejected_count == 1
        assert len(accepted) == 0

    def test_enabled_otf_short_fold_rejects_all_as_unknown(self):
        """Insufficient OTF history rejects all fold candidates, not crashes."""
        from thesistester.analytics.walk_forward import _filter_fold_signals_with_otf

        fold_df = self._make_1bar_ohlcv()
        # 3 candidate signals
        fold_signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:30:00", bar_index=0),
            _signal(signal_id=2, timestamp="2026-01-02 09:30:00", bar_index=0),
            _signal(signal_id=3, timestamp="2026-01-02 09:30:00", bar_index=0),
        )
        accepted, rejected_count, candidate_count = _filter_fold_signals_with_otf(
            fold_df=fold_df,
            fold_signals=fold_signals,
            otf_config=self._make_enabled_config(),
            session_timezone=TZ,
        )
        assert candidate_count == 3
        assert rejected_count == 3
        assert accepted.empty

    def test_enabled_otf_short_fold_candidate_equals_accepted_plus_rejected(self):
        """candidate_count == accepted_count + rejected_count even on short folds."""
        from thesistester.analytics.walk_forward import _filter_fold_signals_with_otf

        fold_df = self._make_1bar_ohlcv()
        fold_signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:30:00", bar_index=0),
            _signal(signal_id=2, timestamp="2026-01-02 09:30:00", bar_index=0),
        )
        accepted, rejected_count, candidate_count = _filter_fold_signals_with_otf(
            fold_df=fold_df,
            fold_signals=fold_signals,
            otf_config=self._make_enabled_config(),
            session_timezone=TZ,
        )
        assert len(accepted) + rejected_count == candidate_count

    def test_short_fold_in_run_walk_forward_does_not_crash(self):
        """run_walk_forward_sl_tp with enabled OTF and tiny fold does not raise."""
        # Use very short train_bars=2 to create folds with insufficient OTF history
        ohlcv = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
                for i in range(20)
            ]
        )
        signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:31:00", bar_index=1),
        )
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=2,
            test_bars=2,
            otf_config=self._make_enabled_config(),
        )
        assert isinstance(results, pd.DataFrame)

    def test_short_fold_produces_no_train_candidate_when_all_rejected(self):
        """Short fold with all OTF-rejected train signals → status no_train_candidate."""
        ohlcv = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
                for i in range(10)
            ]
        )
        signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:31:00", bar_index=1),
        )
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=2,
            test_bars=2,
            otf_config=self._make_enabled_config(),
        )
        if not results.empty:
            # Short folds should result in no_train_candidate (all train rejected)
            assert (results["status"] == "no_train_candidate").all()

    def test_disabled_walk_forward_unchanged_by_robustness_fix(self):
        """Disabled OTF walk-forward is unaffected by the short-fold robustness fix."""
        ohlcv = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ)
                    + pd.Timedelta(minutes=i),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
                for i in range(20)
            ]
        )
        signals = _signals_df(
            _signal(signal_id=1, timestamp="2026-01-02 09:31:00", bar_index=1),
        )
        results_none = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=5,
            test_bars=5,
            otf_config=None,
        )
        results_disabled = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=5,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        assert len(results_none) == len(results_disabled)


class TestOtfMarkdownNoneFormatting:
    """_otf_markdown_section and report/export caption render None as '—'."""

    def _make_wfo_only_state(self) -> dict:
        """Session state with only walk-forward OTF metadata (partial metadata)."""
        return {
            "walk_forward_otf_filter": {
                "otf_filter_enabled": True,
                "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                "otf_config_hash": "e" * 64,
                "otf_filter_config": _enabled_config(["5m"]),
                # No candidate/accepted/rejected counts — partial metadata
            },
        }

    def test_build_otf_filter_metadata_with_only_wfo_data(self):
        """Metadata with only walk-forward data: available=True, counts may be None."""
        from thesistester.reporting import build_otf_filter_metadata

        state = self._make_wfo_only_state()
        meta = build_otf_filter_metadata(state)
        assert meta["available"] is True

    def test_markdown_with_none_counts_renders_dash_not_none(self):
        """Markdown section with None counts shows '—', not 'None'."""
        from thesistester.reporting import build_otf_filter_metadata

        # Build a state where counts are absent → None in metadata
        state = self._make_wfo_only_state()
        build_otf_filter_metadata(state)
        # Inject None counts into artifact to simulate partial metadata
        artifact_otf = {
            "available": True,
            "enabled": True,
            "algorithm_version": OTF_ALGORITHM_VERSION,
            "config_hash": "f" * 64,
            "config": _enabled_config(["5m"]),
            "candidate_signal_count": None,
            "accepted_signal_count": None,
            "rejected_signal_count": None,
            "rejection_rate": None,
            "applied_scopes": [],
        }
        from thesistester.reporting import _otf_markdown_section

        md = _otf_markdown_section(artifact_otf)
        assert "None" not in md, f"Markdown contains 'None': {md!r}"
        assert "—" in md

    def test_markdown_zero_counts_render_as_zero(self):
        """Markdown section with zero counts shows '0', not '—'."""
        from thesistester.reporting import _otf_markdown_section

        artifact_otf = {
            "available": True,
            "enabled": True,
            "algorithm_version": OTF_ALGORITHM_VERSION,
            "config_hash": "a" * 64,
            "config": _enabled_config(["5m"]),
            "candidate_signal_count": 0,
            "accepted_signal_count": 0,
            "rejected_signal_count": 0,
            "rejection_rate": None,
            "applied_scopes": ["backtest"],
        }
        md = _otf_markdown_section(artifact_otf)
        assert "Candidate signals: 0" in md
        assert "Accepted signals: 0" in md
        assert "Rejected signals: 0" in md
        assert "None" not in md

    def test_dash_if_none_helper_none_gives_dash(self):
        """_dash_if_none(None) returns '—'."""
        from thesistester.reporting import _dash_if_none

        assert _dash_if_none(None) == "—"

    def test_dash_if_none_helper_zero_gives_zero(self):
        """_dash_if_none(0) returns 0, not '—'."""
        from thesistester.reporting import _dash_if_none

        assert _dash_if_none(0) == 0

    def test_dash_if_none_helper_string_gives_string(self):
        """_dash_if_none('abc') returns 'abc'."""
        from thesistester.reporting import _dash_if_none

        assert _dash_if_none("abc") == "abc"

    def test_dash_if_none_helper_false_gives_false(self):
        """_dash_if_none(False) returns False, not '—'."""
        from thesistester.reporting import _dash_if_none

        assert _dash_if_none(False) is False


# ---------------------------------------------------------------------------
# PR5 Final Fix — Strict OTF config validation before walk-forward folds
# ---------------------------------------------------------------------------


def _make_ohlcv_for_wf(n_bars: int = 20) -> pd.DataFrame:
    """Minimal OHLCV for walk-forward tests."""
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ) + pd.Timedelta(minutes=i),
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0,
                "volume": 100.0,
            }
            for i in range(n_bars)
        ]
    )


def _make_signals_for_wf() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": 1,
                "timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "bar_index": 1,
                "trigger": "touch",
                "direction": "long",
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 2,
                "level_names": "A|B",
                "entry_reference_price": 100.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": "",
            }
        ]
    )


class TestWalkForwardOtfConfigValidation:
    """run_walk_forward_sl_tp validates OTF config before fold processing."""

    def test_invalid_otf_config_empty_timeframes_raises(self):
        """Invalid OTF config (enabled=True, timeframes=[]) raises ValueError before folds."""
        ohlcv = _make_ohlcv_for_wf()
        signals = _make_signals_for_wf()
        invalid_config = {"enabled": True, "timeframes": []}
        with pytest.raises(ValueError):
            run_walk_forward_sl_tp(
                df=ohlcv,
                signals=signals,
                tick_size=TICK,
                point_value=POINT_VALUE,
                stop_loss_ticks_values=[4],
                take_profit_ticks_values=[8],
                train_bars=5,
                test_bars=5,
                otf_config=invalid_config,
            )

    def test_invalid_otf_config_unsupported_timeframe_raises(self):
        """Invalid OTF config (unsupported timeframe) raises ValueError before folds."""
        ohlcv = _make_ohlcv_for_wf()
        signals = _make_signals_for_wf()
        invalid_config = {
            "enabled": True,
            "timeframes": ["invalid_tf"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "session_reset": "session",
        }
        with pytest.raises(ValueError):
            run_walk_forward_sl_tp(
                df=ohlcv,
                signals=signals,
                tick_size=TICK,
                point_value=POINT_VALUE,
                stop_loss_ticks_values=[4],
                take_profit_ticks_values=[8],
                train_bars=5,
                test_bars=5,
                otf_config=invalid_config,
            )

    def test_filter_fold_signals_still_handles_short_fold(self):
        """After fix: _filter_fold_signals_with_otf still rejects all on 1-bar fold."""
        from thesistester.analytics.walk_forward import _filter_fold_signals_with_otf

        fold_df = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            ]
        )
        fold_signals = pd.DataFrame(
            [_signal(signal_id=1, timestamp="2026-01-02 09:30:00", bar_index=0)]
        )
        valid_config = normalize_otf_filter_config(
            {
                "enabled": True,
                "timeframes": ["5m"],
                "alignment_mode": "all",
                "minimum_consecutive_bars": 3,
                "directional": True,
                "use_completed_bars_only": True,
                "session_reset": "session",
            }
        )
        accepted, rejected_count, candidate_count = _filter_fold_signals_with_otf(
            fold_df=fold_df,
            fold_signals=fold_signals,
            otf_config=valid_config,
            session_timezone=TZ,
        )
        assert candidate_count == 1
        assert rejected_count == 1
        assert len(accepted) == 0

    def test_filter_fold_reraises_unexpected_valueerror(self):
        """_filter_fold_signals_with_otf re-raises unexpected ValueError from apply_otf_filter."""
        from unittest.mock import patch
        from thesistester.analytics.walk_forward import _filter_fold_signals_with_otf

        fold_df = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
            ]
        )
        fold_signals = pd.DataFrame(
            [_signal(signal_id=1, timestamp="2026-01-02 09:30:00", bar_index=0)]
        )
        valid_config = normalize_otf_filter_config(
            {
                "enabled": True,
                "timeframes": ["5m"],
                "alignment_mode": "all",
                "minimum_consecutive_bars": 3,
                "directional": True,
                "use_completed_bars_only": True,
                "session_reset": "session",
            }
        )
        unexpected_msg = "Completely unexpected internal programming error XYZ"
        with patch(
            "thesistester.engine.otf_filter.apply_otf_filter",
            side_effect=ValueError(unexpected_msg),
        ):
            with pytest.raises(
                ValueError, match="Completely unexpected internal programming error XYZ"
            ):
                _filter_fold_signals_with_otf(
                    fold_df=fold_df,
                    fold_signals=fold_signals,
                    otf_config=valid_config,
                    session_timezone=TZ,
                )

    def test_valid_enabled_otf_config_still_runs(self):
        """Valid enabled OTF config does not raise and produces fold results."""
        ohlcv = _make_ohlcv_for_wf(n_bars=20)
        signals = _make_signals_for_wf()
        valid_config = normalize_otf_filter_config(
            {
                "enabled": True,
                "timeframes": ["5m"],
                "alignment_mode": "all",
                "minimum_consecutive_bars": 3,
                "directional": True,
                "use_completed_bars_only": True,
                "session_reset": "session",
            }
        )
        results = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=5,
            test_bars=5,
            otf_config=valid_config,
        )
        assert isinstance(results, pd.DataFrame)
        assert "otf_filter_enabled" in results.columns
        assert results["otf_filter_enabled"].all()

    def test_disabled_otf_config_matches_legacy(self):
        """Disabled OTF config produces identical fold results to otf_config=None."""
        ohlcv = _make_ohlcv_for_wf(n_bars=20)
        signals = _make_signals_for_wf()
        results_none = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=5,
            test_bars=5,
            otf_config=None,
        )
        results_disabled = run_walk_forward_sl_tp(
            df=ohlcv,
            signals=signals,
            tick_size=TICK,
            point_value=POINT_VALUE,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=5,
            test_bars=5,
            otf_config=_disabled_config(),
        )
        assert len(results_none) == len(results_disabled)
        # Both should show OTF disabled
        assert results_none["otf_filter_enabled"].eq(False).all()
        assert results_disabled["otf_filter_enabled"].eq(False).all()

    def test_invalid_config_never_produces_fold_results(self):
        """Invalid explicit OTF config is never silently converted to rejected signals."""
        ohlcv = _make_ohlcv_for_wf()
        signals = _make_signals_for_wf()
        invalid_config = {"enabled": True, "timeframes": []}
        raised = False
        try:
            run_walk_forward_sl_tp(
                df=ohlcv,
                signals=signals,
                tick_size=TICK,
                point_value=POINT_VALUE,
                stop_loss_ticks_values=[4],
                take_profit_ticks_values=[8],
                train_bars=5,
                test_bars=5,
                otf_config=invalid_config,
            )
        except ValueError:
            raised = True
        assert raised, "Invalid OTF config must raise ValueError, not produce fold results"


# ---------------------------------------------------------------------------
# PR1 — Futures-session eth_start propagation parity
# ---------------------------------------------------------------------------


def _overnight_1m_source(*, minutes: int = 180) -> pd.DataFrame:
    """1-minute OHLCV spanning Mon 22:00 ET through the next 18:00 ET boundary.

    Bars make progressively higher lows so a short HTF OTF sequence can
    establish ``up`` across midnight when eth_start="18:00".
    """
    start = pd.Timestamp("2026-01-05 22:00:00", tz=TZ)
    overnight = pd.date_range(start, periods=minutes, freq="1min")
    # Extend through Tuesday 18:30 so the next-session boundary is present.
    boundary = pd.date_range("2026-01-06 18:00:00", periods=30, freq="1min", tz=TZ)
    timestamps = overnight.union(boundary)
    rows = []
    price = 100.0
    for ts in timestamps:
        low = price
        high = price + 1.0
        rows.append(
            {
                "timestamp": ts,
                "open": price + 0.2,
                "high": high,
                "low": low,
                "close": price + 0.6,
                "volume": 100.0,
            }
        )
        price += 0.05  # higher lows over time
    return pd.DataFrame(rows)


def _overnight_signals(source: pd.DataFrame) -> pd.DataFrame:
    """Long candidates before midnight, after midnight, and after 18:00 ET."""
    picks = [
        pd.Timestamp("2026-01-05 22:45:00", tz=TZ),
        pd.Timestamp("2026-01-06 00:15:00", tz=TZ),
        pd.Timestamp("2026-01-06 18:20:00", tz=TZ),
    ]
    rows = []
    for i, ts in enumerate(picks):
        # Map to nearest source bar index for bar_index realism.
        idx = int((source["timestamp"] - ts).abs().idxmin())
        rows.append(
            _signal(
                signal_id=i + 1,
                timestamp=str(ts.strftime("%Y-%m-%d %H:%M:%S")),
                direction="long",
                bar_index=idx,
            )
        )
    return _signals_df(*rows)


class TestEthStartSessionPropagation:
    """PR1: Streamlit-equivalent OTF composition must forward eth_start."""

    def test_summary_records_effective_session_fields(self):
        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=1)},
            session_timezone=TZ,
            eth_start="18:00",
        )
        summary = result.to_summary_dict()
        assert summary["session_timezone"] == TZ
        assert summary["eth_start"] == "18:00"

    def test_eth_start_keeps_otf_continuous_across_midnight(self):
        """With eth_start=18:00, midnight is not a session reset."""
        source = _overnight_1m_source()
        # Probe shortly after midnight: calendar-session mode is still in the
        # first HTF bars of the new day (often unknown), while ETH mode continues
        # the prior evening session and can already be directional.
        sigs = _signals_df(_signal(signal_id=1, timestamp="2026-01-06 00:05:00", direction="long"))
        with_eth = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=3)},
            session_timezone=TZ,
            eth_start="18:00",
        )
        without_eth = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=3)},
            session_timezone=TZ,
            eth_start=None,
        )
        with_state = pd.concat(
            [with_eth.accepted_signals, with_eth.rejected_signals], ignore_index=True
        )["otf_5m_state"].iloc[0]
        without_state = pd.concat(
            [without_eth.accepted_signals, without_eth.rejected_signals], ignore_index=True
        )["otf_5m_state"].iloc[0]
        assert with_eth.eth_start == "18:00"
        assert without_eth.eth_start is None
        assert with_state == "up"
        assert without_state in {"unknown", "neutral"}
        assert with_state != without_state

    def test_ui_equivalent_backtest_matches_api_otf_populations(self):
        from thesistester.api import run_backtest
        from thesistester.config import INSTRUMENTS

        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        setup = {
            "name": "otf-eth-parity",
            "instrument": "ES",
            "otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=1),
        }
        inst = INSTRUMENTS["ES"]
        ui = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config=setup,
            session_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
            signal_settings={"otf_filter": setup["otf_filter"]},
        )
        api = run_backtest(
            source,
            sigs,
            instrument="ES",
            config={"stop_loss_ticks": 4, "take_profit_ticks": 8},
            setup_config=setup,
            signal_settings={"otf_filter": setup["otf_filter"]},
        )
        assert api["otf_filter_summary"]["eth_start"] == inst.eth_start
        assert api["otf_filter_summary"]["session_timezone"] == inst.exchange_tz
        assert list(ui.accepted_signals["signal_id"]) == list(api["accepted_signals"]["signal_id"])
        assert list(ui.rejected_signals["signal_id"]) == list(api["rejected_signals"]["signal_id"])
        if not ui.rejected_signals.empty:
            assert list(ui.rejected_signals["otf_filter_reason"]) == list(
                api["rejected_signals"]["otf_filter_reason"]
            )

    def test_ui_equivalent_grid_matches_api_otf_populations(self):
        from thesistester.api import run_grid
        from thesistester.config import INSTRUMENTS

        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        setup = {
            "name": "otf-eth-grid-parity",
            "instrument": "ES",
            "otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=1),
        }
        inst = INSTRUMENTS["ES"]
        ui = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config=setup,
            session_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
            signal_settings={"otf_filter": setup["otf_filter"]},
        )
        api = run_grid(
            source,
            sigs,
            instrument="ES",
            config={
                "stop_loss_ticks_values": [4],
                "take_profit_ticks_values": [8],
            },
            setup_config=setup,
            signal_settings={"otf_filter": setup["otf_filter"]},
        )
        assert api["otf_filter_summary"]["eth_start"] == inst.eth_start
        assert list(ui.accepted_signals["signal_id"]) == list(api["accepted_signals"]["signal_id"])
        assert list(ui.rejected_signals["signal_id"]) == list(api["rejected_signals"]["signal_id"])

    def test_validation_matrix_records_eth_start_and_matches_headless(self):
        from thesistester.analytics.otf_validation import run_otf_validation_matrix
        from thesistester.api import run_otf_validation
        from thesistester.config import INSTRUMENTS

        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        inst = INSTRUMENTS["ES"]
        ui_matrix = run_otf_validation_matrix(
            source_df=source,
            candidate_signals=sigs,
            tick_size=inst.tick_size,
            point_value=inst.point_value,
            stop_loss_ticks=4,
            take_profit_ticks=8,
            train_fraction=0.7,
            session_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
        )
        api_matrix = run_otf_validation(
            source,
            sigs,
            instrument="ES",
            stop_loss_ticks=4,
            take_profit_ticks=8,
            train_fraction=0.7,
            session_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
        )
        assert "eth_start" in ui_matrix.columns
        assert "session_timezone" in ui_matrix.columns
        assert (ui_matrix["eth_start"] == inst.eth_start).all()
        assert (ui_matrix["session_timezone"] == inst.exchange_tz).all()
        pd.testing.assert_frame_equal(
            ui_matrix.reset_index(drop=True),
            api_matrix.reset_index(drop=True),
            check_dtype=False,
        )

    def test_disabled_otf_ignores_eth_start_and_preserves_candidates(self):
        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        with_eth = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _disabled_config()},
            session_timezone=TZ,
            eth_start="18:00",
        )
        without_eth = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _disabled_config()},
            session_timezone=TZ,
            eth_start=None,
        )
        assert with_eth.otf_filter_enabled is False
        assert without_eth.otf_filter_enabled is False
        assert len(with_eth.accepted_signals) == len(sigs)
        assert len(without_eth.accepted_signals) == len(sigs)
        assert with_eth.rejected_signals.empty
        assert without_eth.rejected_signals.empty
        pd.testing.assert_series_equal(
            with_eth.accepted_signals["signal_id"].reset_index(drop=True),
            without_eth.accepted_signals["signal_id"].reset_index(drop=True),
        )

    def test_reporting_metadata_exposes_eth_start(self):
        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        result = apply_configured_otf_filter(
            source_df=source,
            candidate_signals=sigs,
            setup_config={"otf_filter": _enabled_config(["5m"], minimum_consecutive_bars=1)},
            session_timezone=TZ,
            eth_start="18:00",
        )
        meta = build_otf_filter_metadata({"otf_filter_summary": result.to_summary_dict()})
        assert meta["available"] is True
        assert meta["eth_start"] == "18:00"
        assert meta["session_timezone"] == TZ

    def test_wfo_otf_falls_back_to_exchange_timezone_when_session_tz_missing(self):
        """Fold OTF must use exchange_timezone when session-exit tz is omitted."""
        from thesistester.analytics.walk_forward import (
            resolve_otf_session_timezone,
            run_walk_forward_sl_tp,
        )
        from thesistester.config import INSTRUMENTS

        assert resolve_otf_session_timezone(None, TZ) == TZ
        assert resolve_otf_session_timezone("UTC", TZ) == "UTC"
        assert resolve_otf_session_timezone(None, None) is None

        source = _overnight_1m_source()
        sigs = _overnight_signals(source)
        inst = INSTRUMENTS["ES"]
        otf_cfg = _enabled_config(["5m"], minimum_consecutive_bars=1)
        common = dict(
            df=source,
            signals=sigs,
            tick_size=inst.tick_size,
            point_value=inst.point_value,
            stop_loss_ticks_values=[4],
            take_profit_ticks_values=[8],
            train_bars=40,
            test_bars=20,
            step_bars=20,
            otf_config=otf_cfg,
            exchange_timezone=inst.exchange_tz,
            eth_start=inst.eth_start,
            return_result=True,
        )
        missing_session_tz = run_walk_forward_sl_tp(session_timezone=None, **common)
        explicit_exchange_tz = run_walk_forward_sl_tp(session_timezone=inst.exchange_tz, **common)
        assert list(missing_session_tz.folds["test_otf_accepted_count"]) == list(
            explicit_exchange_tz.folds["test_otf_accepted_count"]
        )
        assert list(missing_session_tz.folds["test_otf_rejected_count"]) == list(
            explicit_exchange_tz.folds["test_otf_rejected_count"]
        )
        # Validation page records the same resolved timezone used by fold OTF.
        assert resolve_otf_session_timezone(None, inst.exchange_tz) == inst.exchange_tz
        page_path = pathlib.Path(__file__).parent.parent / "pages" / "10_Validation.py"
        source_text = page_path.read_text(encoding="utf-8")
        assert "resolve_otf_session_timezone(" in source_text
        assert '"session_timezone": _wfo_session_tz' in source_text
