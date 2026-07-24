"""tests/test_otf_filter.py — Pure OTF signal-eligibility filter tests (PR 3)."""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine import apply_otf_filter
from thesistester.engine.otf_filter import select_signal_decision_timestamp


TZ = "America/New_York"


def _source_1m(
    start: str,
    count: int,
    *,
    trend: str = "up",
    tz: str = TZ,
) -> pd.DataFrame:
    base = pd.Timestamp(start, tz=tz)
    rows: list[dict] = []

    for i in range(count):
        ts = base + pd.Timedelta(minutes=i)
        if trend == "up":
            anchor = 100.0 + i * 0.05
        elif trend == "down":
            anchor = 100.0 - i * 0.05
        else:
            anchor = 100.0 + (0.05 if i % 2 else -0.05)

        rows.append(
            {
                "timestamp": ts,
                "open": anchor,
                "high": anchor + 1.0,
                "low": anchor - 1.0,
                "close": anchor + 0.25,
                "volume": 100.0 + i,
            }
        )

    return pd.DataFrame(rows)


def _signals(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _signal(
    *,
    signal_id: int,
    timestamp: object,
    direction: str,
    trigger_timestamp: object | None = None,
    trigger: str = "touch",
    status: str = "candidate",
    notes: str = "",
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": timestamp,
        "trigger_timestamp": trigger_timestamp,
        "direction": direction,
        "trigger": trigger,
        "status": status,
        "notes": notes,
    }


class TestValidation:
    def test_disabled_with_no_timeframes_succeeds(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(src, sig, enabled=False, timeframes=())
        assert len(accepted) == 1
        assert rejected.empty

    def test_enabled_with_no_timeframes_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="enabled=True requires at least one selected timeframe"):
            apply_otf_filter(src, sig, enabled=True, timeframes=())

    def test_unsupported_timeframe_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="Unsupported OTF timeframe"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("10m",))

    def test_duplicate_timeframes_after_alias_normalization_raise(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="Duplicate OTF timeframe"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m", "5min"))

    def test_invalid_alignment_mode_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="alignment_mode must be 'all'"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), alignment_mode="any")

    @pytest.mark.parametrize("value", [0, -1, 1.5, True])
    def test_invalid_minimum_threshold_raises(self, value: object) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="minimum_consecutive_bars"):
            apply_otf_filter(
                src,
                sig,
                enabled=True,
                timeframes=("5m",),
                minimum_consecutive_bars=value,  # type: ignore[arg-type]
            )

    def test_invalid_session_reset_mode_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="session_reset must be 'session'"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), session_reset="none")

    def test_missing_direction_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = pd.DataFrame([{"signal_id": 1, "timestamp": pd.Timestamp("2026-01-05 09:35", tz=TZ)}])
        with pytest.raises(ValueError, match="direction"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))

    def test_invalid_direction_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="flat"))
        with pytest.raises(ValueError, match="long'/'short"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))

    def test_invalid_or_missing_decision_timestamp_raises(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        bad = _signals(_signal(signal_id=1, timestamp="not-a-timestamp", direction="long"))
        with pytest.raises(ValueError, match="invalid"):
            apply_otf_filter(src, bad, enabled=True, timeframes=("5m",))


class TestDisabledRegression:
    def test_disabled_returns_all_candidates_accepted_and_none_rejected(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(
            _signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long", notes="alpha"),
            _signal(signal_id=2, timestamp=pd.Timestamp("2026-01-05 09:36", tz=TZ), direction="short", notes="beta"),
        )

        accepted, rejected = apply_otf_filter(src, sig, enabled=False, timeframes=())

        assert list(accepted["signal_id"]) == [1, 2]
        assert rejected.empty
        assert accepted["otf_filter_enabled"].eq(False).all()
        assert accepted["otf_filter_passed"].eq(True).all()
        assert accepted["otf_filter_reason"].isna().all()

    def test_disabled_path_preserves_original_rows_values_and_order(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(
            _signal(signal_id=7, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long", status="candidate", notes="n1"),
            _signal(signal_id=9, timestamp=pd.Timestamp("2026-01-05 09:36", tz=TZ), direction="short", status="candidate", notes="n2"),
        )
        accepted, _ = apply_otf_filter(src, sig, enabled=False)

        pd.testing.assert_frame_equal(
            accepted[sig.columns].reset_index(drop=True),
            sig.reset_index(drop=True),
        )

    def test_disabled_does_not_call_otf_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))

        called = {"count": 0}

        def _boom(*_args, **_kwargs):
            called["count"] += 1
            raise AssertionError("calculate_otf_state should not be called when disabled")

        monkeypatch.setattr("thesistester.engine.otf_filter.calculate_otf_state", _boom)

        accepted, rejected = apply_otf_filter(src, sig, enabled=False)
        assert len(accepted) == 1
        assert rejected.empty
        assert called["count"] == 0

    def test_empty_signals_return_stable_empty_outputs(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = pd.DataFrame(columns=["signal_id", "timestamp", "direction", "status", "notes"])

        accepted, rejected = apply_otf_filter(src, sig, enabled=False)

        assert accepted.empty
        assert rejected.empty
        assert list(accepted.columns) == list(rejected.columns)


class TestDirectionalEligibilitySingleTimeframe:
    @pytest.mark.parametrize(
        "trend,decision_ts,direction,expected_pass,expected_state",
        [
            ("up", "2026-01-05 09:50", "long", True, "up"),
            ("down", "2026-01-05 09:50", "long", False, "down"),
            ("up", "2026-01-05 09:40", "long", False, "neutral"),
            ("up", "2026-01-05 09:34", "long", False, "unknown"),
            ("down", "2026-01-05 09:50", "short", True, "down"),
            ("up", "2026-01-05 09:50", "short", False, "up"),
            ("down", "2026-01-05 09:40", "short", False, "neutral"),
            ("down", "2026-01-05 09:34", "short", False, "unknown"),
        ],
    )
    def test_single_timeframe_directional_contract(
        self,
        trend: str,
        decision_ts: str,
        direction: str,
        expected_pass: bool,
        expected_state: str,
    ) -> None:
        src = _source_1m("2026-01-05 09:30", 40, trend=trend)
        sig = _signals(
            _signal(signal_id=1, timestamp=pd.Timestamp(decision_ts, tz=TZ), direction=direction)
        )

        accepted, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m",),
            minimum_consecutive_bars=3,
        )

        output = accepted if expected_pass else rejected
        assert len(output) == 1
        assert output.iloc[0]["otf_5m_state"] == expected_state
        assert bool(output.iloc[0]["otf_filter_passed"]) is expected_pass


class TestMultiTimeframeAllMode:
    def test_long_all_selected_up_passes(self) -> None:
        src = _source_1m("2026-01-05 09:30", 200, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 11:10", tz=TZ), direction="long"))

        accepted, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m", "15m", "30m"),
            minimum_consecutive_bars=1,
        )

        assert len(accepted) == 1
        assert rejected.empty
        assert accepted.iloc[0]["otf_5m_state"] == "up"
        assert accepted.iloc[0]["otf_15m_state"] == "up"
        assert accepted.iloc[0]["otf_30m_state"] == "up"

    def test_long_with_unknown_timeframe_rejects(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ), direction="long"))

        accepted, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m", "30m"),
            minimum_consecutive_bars=1,
        )

        assert accepted.empty
        assert len(rejected) == 1
        assert "30m OTF state is unknown" in str(rejected.iloc[0]["otf_filter_reason"])

    def test_short_all_selected_down_passes(self) -> None:
        src = _source_1m("2026-01-05 09:30", 200, trend="down")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 11:10", tz=TZ), direction="short"))

        accepted, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m", "15m", "30m"),
            minimum_consecutive_bars=1,
        )

        assert len(accepted) == 1
        assert rejected.empty
        assert accepted.iloc[0]["otf_5m_state"] == "down"
        assert accepted.iloc[0]["otf_15m_state"] == "down"
        assert accepted.iloc[0]["otf_30m_state"] == "down"

    def test_short_with_opposing_timeframe_rejects(self) -> None:
        src = _source_1m("2026-01-05 09:30", 200, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 11:10", tz=TZ), direction="short"))

        accepted, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m", "15m"),
            minimum_consecutive_bars=1,
        )

        assert accepted.empty
        assert len(rejected) == 1
        assert "must be down for short" in str(rejected.iloc[0]["otf_filter_reason"])

    def test_reason_uses_selected_timeframe_order(self) -> None:
        src = _source_1m("2026-01-05 09:30", 200, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 11:10", tz=TZ), direction="short"))

        _, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("30m", "5m"),
            minimum_consecutive_bars=1,
        )

        reason = str(rejected.iloc[0]["otf_filter_reason"])
        assert reason.startswith("30m OTF state is up")


class TestPointInTimeAlignment:
    def test_before_first_completed_bar_is_unknown(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:34", tz=TZ), direction="long"))

        _, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))

        row = rejected.iloc[0]
        assert row["otf_5m_state"] == "unknown"
        assert row["otf_5m_sequence_length"] == 0
        assert pd.isna(row["otf_5m_reference_timestamp"])

    def test_signal_exactly_at_htf_close_can_use_that_bar(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))

        _, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))
        row = rejected.iloc[0]

        assert row["otf_5m_reference_timestamp"] == pd.Timestamp("2026-01-05 09:35", tz=TZ)

    def test_between_htf_closes_uses_latest_prior_completed_bar(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:37", tz=TZ), direction="long"))

        _, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))
        row = rejected.iloc[0]

        assert row["otf_5m_reference_timestamp"] == pd.Timestamp("2026-01-05 09:35", tz=TZ)

    def test_future_data_does_not_change_prior_metadata_or_eligibility(self) -> None:
        base = _source_1m("2026-01-05 09:30", 120, trend="up")
        future = _source_1m("2026-01-05 11:30", 60, trend="down")
        extended = pd.concat([base, future], ignore_index=True)

        sig = _signals(
            _signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 10:10", tz=TZ), direction="long"),
            _signal(signal_id=2, timestamp=pd.Timestamp("2026-01-05 10:40", tz=TZ), direction="long"),
        )

        acc_base, rej_base = apply_otf_filter(base, sig, enabled=True, timeframes=("5m", "15m"), minimum_consecutive_bars=1)
        acc_ext, rej_ext = apply_otf_filter(extended, sig, enabled=True, timeframes=("5m", "15m"), minimum_consecutive_bars=1)

        left = pd.concat([acc_base, rej_base], ignore_index=True).sort_values("signal_id").reset_index(drop=True)
        right = pd.concat([acc_ext, rej_ext], ignore_index=True).sort_values("signal_id").reset_index(drop=True)

        cols = [
            "signal_id",
            "otf_5m_state",
            "otf_5m_sequence_length",
            "otf_5m_reference_timestamp",
            "otf_15m_state",
            "otf_15m_sequence_length",
            "otf_15m_reference_timestamp",
            "otf_filter_passed",
            "otf_filter_reason",
        ]
        pd.testing.assert_frame_equal(left[cols], right[cols])

    def test_appending_bars_after_signal_time_does_not_change_historical_result(self) -> None:
        base = _source_1m("2026-01-05 09:30", 20, trend="up")
        append_only_future = _source_1m("2026-01-05 10:00", 120, trend="up")
        extended = pd.concat([base, append_only_future], ignore_index=True)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ), direction="long"))

        _, rej_base = apply_otf_filter(base, sig, enabled=True, timeframes=("30m",), minimum_consecutive_bars=1)
        _, rej_ext = apply_otf_filter(extended, sig, enabled=True, timeframes=("30m",), minimum_consecutive_bars=1)

        pd.testing.assert_series_equal(
            rej_base.iloc[0][["otf_30m_state", "otf_30m_sequence_length", "otf_30m_reference_timestamp", "otf_filter_reason"]],
            rej_ext.iloc[0][["otf_30m_state", "otf_30m_sequence_length", "otf_30m_reference_timestamp", "otf_filter_reason"]],
        )

    def test_5m_15m_30m_alignment_is_independently_correct(self) -> None:
        src = _source_1m("2026-01-05 09:30", 180, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 10:16", tz=TZ), direction="long"))

        _, rejected = apply_otf_filter(
            src,
            sig,
            enabled=True,
            timeframes=("5m", "15m", "30m"),
            minimum_consecutive_bars=1,
        )
        row = rejected.iloc[0]

        assert row["otf_5m_reference_timestamp"] == pd.Timestamp("2026-01-05 10:15", tz=TZ)
        assert row["otf_15m_reference_timestamp"] == pd.Timestamp("2026-01-05 10:15", tz=TZ)
        assert row["otf_30m_reference_timestamp"] == pd.Timestamp("2026-01-05 10:00", tz=TZ)

    def test_dst_spring_forward_alignment_is_causal(self) -> None:
        ts = pd.date_range("2024-03-10 06:50", periods=40, freq="1min", tz="UTC").tz_convert(TZ)
        src = pd.DataFrame(
            {
                "timestamp": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 100.0,
            }
        )
        decision = pd.Timestamp("2024-03-10 03:05", tz=TZ)
        sig = _signals(_signal(signal_id=1, timestamp=decision, direction="long"))

        accepted, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), minimum_consecutive_bars=1)
        row = (accepted if not accepted.empty else rejected).iloc[0]
        ref_ts = row["otf_5m_reference_timestamp"]

        assert ref_ts <= decision

    def test_dst_fall_back_repeated_hour_alignment_is_causal(self) -> None:
        ts = pd.date_range("2024-11-03 05:40", periods=70, freq="1min", tz="UTC").tz_convert(TZ)
        src = pd.DataFrame(
            {
                "timestamp": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.2,
                "volume": 100.0,
            }
        )
        first = pd.Timestamp("2024-11-03 05:55", tz="UTC").tz_convert(TZ)
        second = pd.Timestamp("2024-11-03 06:10", tz="UTC").tz_convert(TZ)
        sig = _signals(
            _signal(signal_id=1, timestamp=first, direction="long"),
            _signal(signal_id=2, timestamp=second, direction="long"),
        )

        accepted, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), minimum_consecutive_bars=1)
        out = pd.concat([accepted, rejected], ignore_index=True).sort_values("signal_id").reset_index(drop=True)

        assert out.loc[0, "otf_signal_decision_timestamp"].utcoffset() != out.loc[1, "otf_signal_decision_timestamp"].utcoffset()
        assert out.loc[0, "otf_5m_reference_timestamp"] <= out.loc[0, "otf_signal_decision_timestamp"]
        assert out.loc[1, "otf_5m_reference_timestamp"] <= out.loc[1, "otf_signal_decision_timestamp"]


class TestDecisionTimestampSelection:
    def test_base_simple_trigger_uses_timestamp_fallback(self) -> None:
        sig = _signals(
            _signal(
                signal_id=1,
                timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ),
                trigger_timestamp=pd.NaT,
                direction="long",
                trigger="touch",
            )
        )
        out = select_signal_decision_timestamp(sig)
        assert out.iloc[0] == pd.Timestamp("2026-01-05 09:40", tz=TZ)

    def test_non_base_simple_trigger_uses_trigger_timestamp(self) -> None:
        sig = _signals(
            _signal(
                signal_id=1,
                timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ),
                trigger_timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ),
                direction="long",
                trigger="touch",
            )
        )
        out = select_signal_decision_timestamp(sig)
        assert out.iloc[0] == pd.Timestamp("2026-01-05 09:40", tz=TZ)

    def test_base_3c_uses_decision_timestamp(self) -> None:
        sig = _signals(
            _signal(
                signal_id=1,
                timestamp=pd.Timestamp("2026-01-05 09:45", tz=TZ),
                trigger_timestamp=pd.Timestamp("2026-01-05 09:45", tz=TZ),
                direction="long",
                trigger="3c",
            )
        )
        out = select_signal_decision_timestamp(sig)
        assert out.iloc[0] == pd.Timestamp("2026-01-05 09:45", tz=TZ)

    def test_non_base_3c_uses_trigger_timestamp(self) -> None:
        sig = _signals(
            _signal(
                signal_id=1,
                timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ),
                trigger_timestamp=pd.Timestamp("2026-01-05 09:50", tz=TZ),
                direction="long",
                trigger="3c",
            )
        )
        out = select_signal_decision_timestamp(sig)
        assert out.iloc[0] == pd.Timestamp("2026-01-05 09:50", tz=TZ)

    def test_null_trigger_timestamp_falls_back_to_timestamp(self) -> None:
        sig = _signals(
            _signal(
                signal_id=1,
                timestamp=pd.Timestamp("2026-01-05 09:40", tz=TZ),
                trigger_timestamp=None,
                direction="long",
            )
        )
        out = select_signal_decision_timestamp(sig)
        assert out.iloc[0] == pd.Timestamp("2026-01-05 09:40", tz=TZ)


class TestPreservationAndAuditability:
    def test_original_columns_values_status_notes_and_signal_ids_are_preserved(self) -> None:
        src = _source_1m("2026-01-05 09:30", 60, trend="down")
        sig = _signals(
            _signal(signal_id=11, timestamp=pd.Timestamp("2026-01-05 09:50", tz=TZ), direction="long", status="candidate", notes="keep me"),
            _signal(signal_id=12, timestamp=pd.Timestamp("2026-01-05 09:51", tz=TZ), direction="short", status="candidate", notes="keep me too"),
        )
        sig_before = sig.copy(deep=True)
        src_before = src.copy(deep=True)

        accepted, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), minimum_consecutive_bars=3)
        combined = pd.concat([accepted, rejected], ignore_index=True).sort_values("signal_id").reset_index(drop=True)
        original = sig_before.sort_values("signal_id").reset_index(drop=True)

        pd.testing.assert_frame_equal(combined[sig_before.columns], original)
        assert list(combined["signal_id"]) == [11, 12]
        assert combined.loc[0, "status"] == "candidate"
        assert combined.loc[0, "notes"] == "keep me"
        assert combined.loc[0, "otf_filter_reason"] is not None
        assert combined.loc[0, "notes"] == "keep me"

        pd.testing.assert_frame_equal(sig, sig_before)
        pd.testing.assert_frame_equal(src, src_before)

    def test_rejected_rows_are_preserved_separately_from_execution_skips(self) -> None:
        src = _source_1m("2026-01-05 09:30", 40, trend="down")
        sig = _signals(
            _signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:50", tz=TZ), direction="long"),
            _signal(signal_id=2, timestamp=pd.Timestamp("2026-01-05 09:50", tz=TZ), direction="short"),
        )

        accepted, rejected = apply_otf_filter(src, sig, enabled=True, timeframes=("5m",), minimum_consecutive_bars=3)

        assert list(accepted["signal_id"]) == [2]
        assert list(rejected["signal_id"]) == [1]
        assert rejected.iloc[0]["status"] == "candidate"
        assert "skip_reason" not in rejected.columns

    def test_canonical_and_alias_timeframes_produce_identical_output(self) -> None:
        src = _source_1m("2026-01-05 09:30", 120, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 10:20", tz=TZ), direction="long"))

        acc_c, rej_c = apply_otf_filter(src, sig, enabled=True, timeframes=("5m", "15m"), minimum_consecutive_bars=1)
        acc_a, rej_a = apply_otf_filter(src, sig, enabled=True, timeframes=("5min", "15min"), minimum_consecutive_bars=1)

        pd.testing.assert_frame_equal(acc_c.reset_index(drop=True), acc_a.reset_index(drop=True))
        pd.testing.assert_frame_equal(rej_c.reset_index(drop=True), rej_a.reset_index(drop=True))


class TestDisabledIsATrueNoOp:
    """Disabled mode must short-circuit after only the `enabled` bool check."""

    def _empty_src(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def test_disabled_ignores_unsupported_timeframe(self) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False, timeframes=("10m",))
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_ignores_duplicate_canonical_and_alias_timeframes(self) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False, timeframes=("5m", "5min"))
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_ignores_invalid_alignment_mode(self) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(
            self._empty_src(), sig, enabled=False, timeframes=("5m",), alignment_mode="any"
        )
        assert len(accepted) == 1
        assert rejected.empty

    @pytest.mark.parametrize("value", [0, -1, 1.5, True])
    def test_disabled_ignores_invalid_minimum_consecutive_bars(self, value: object) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(
            self._empty_src(), sig, enabled=False, timeframes=("5m",),
            minimum_consecutive_bars=value,  # type: ignore[arg-type]
        )
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_ignores_invalid_session_reset(self) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(
            self._empty_src(), sig, enabled=False, timeframes=("5m",), session_reset="none"
        )
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_does_not_require_direction_column(self) -> None:
        sig = pd.DataFrame([{"signal_id": 1, "timestamp": pd.Timestamp("2026-01-05 09:35", tz=TZ)}])
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False)
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_does_not_require_timestamp_column(self) -> None:
        sig = pd.DataFrame([{"signal_id": 1, "value": 42}])
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False)
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_does_not_inspect_source_df(self) -> None:
        # pass obviously invalid source — should succeed without inspection
        invalid_src = pd.DataFrame([{"junk": 1}])
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        accepted, rejected = apply_otf_filter(invalid_src, sig, enabled=False)
        assert len(accepted) == 1
        assert rejected.empty

    def test_disabled_does_not_call_otf_engine_with_any_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[object] = []

        def _boom(*args: object, **kwargs: object) -> object:
            called.append((args, kwargs))
            raise AssertionError("OTF engine must not be called when disabled")

        monkeypatch.setattr("thesistester.engine.otf_filter.calculate_otf_state", _boom)

        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        apply_otf_filter(self._empty_src(), sig, enabled=False, timeframes=("unsupported_tf",))
        assert len(called) == 0

    def test_disabled_preserves_all_original_signal_rows_and_values(self) -> None:
        sig = _signals(
            _signal(signal_id=3, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long", notes="n3"),
            _signal(signal_id=7, timestamp=pd.Timestamp("2026-01-05 09:36", tz=TZ), direction="short", notes="n7"),
        )
        sig_before = sig.copy(deep=True)
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False)

        pd.testing.assert_frame_equal(
            accepted[sig.columns].reset_index(drop=True),
            sig_before.reset_index(drop=True),
        )
        assert rejected.empty
        # original not mutated
        pd.testing.assert_frame_equal(sig, sig_before)

    def test_non_bool_enabled_raises_before_disabled_return(self) -> None:
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="enabled must be a bool"):
            apply_otf_filter(self._empty_src(), sig, enabled="no")  # type: ignore[arg-type]

    def test_disabled_with_empty_signals_and_no_timeframes_returns_empty_accepted_rejected(self) -> None:
        sig = pd.DataFrame(columns=["signal_id", "timestamp", "direction"])
        accepted, rejected = apply_otf_filter(self._empty_src(), sig, enabled=False)
        assert accepted.empty
        assert rejected.empty
        assert list(accepted.columns) == list(rejected.columns)


class TestEnabledEmptySignals:
    """enabled=True with empty signals must return stable empty schemas without calling OTF engine."""

    def _source(self) -> pd.DataFrame:
        return _source_1m("2026-01-05 09:30", 30)

    def _empty_signals(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["signal_id", "timestamp", "direction", "status"])

    def test_returns_two_empty_dataframes(self) -> None:
        sig = self._empty_signals()
        accepted, rejected = apply_otf_filter(
            self._source(), sig, enabled=True, timeframes=("5m",)
        )
        assert accepted.empty
        assert rejected.empty

    def test_accepted_and_rejected_schemas_are_identical(self) -> None:
        sig = self._empty_signals()
        accepted, rejected = apply_otf_filter(
            self._source(), sig, enabled=True, timeframes=("5m", "15m")
        )
        assert list(accepted.columns) == list(rejected.columns)

    def test_selected_timeframe_metadata_columns_are_present(self) -> None:
        sig = self._empty_signals()
        accepted, _ = apply_otf_filter(
            self._source(), sig, enabled=True, timeframes=("5m", "15m")
        )
        for tf in ("5m", "15m"):
            assert f"otf_{tf}_state" in accepted.columns
            assert f"otf_{tf}_sequence_length" in accepted.columns
            assert f"otf_{tf}_reference_timestamp" in accepted.columns
        assert "otf_signal_decision_timestamp" in accepted.columns
        assert "otf_filter_enabled" in accepted.columns
        assert "otf_filter_passed" in accepted.columns
        assert "otf_filter_reason" in accepted.columns

    def test_unselected_timeframe_metadata_columns_are_absent(self) -> None:
        sig = self._empty_signals()
        accepted, _ = apply_otf_filter(
            self._source(), sig, enabled=True, timeframes=("5m",)
        )
        assert "otf_15m_state" not in accepted.columns
        assert "otf_30m_state" not in accepted.columns

    def test_no_direction_or_timestamp_columns_required_to_return_safely(self) -> None:
        # Completely empty DataFrame — no columns at all
        sig = pd.DataFrame()
        accepted, rejected = apply_otf_filter(
            self._source(), sig, enabled=True, timeframes=("5m",)
        )
        assert accepted.empty
        assert rejected.empty

    def test_otf_engine_is_not_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[object] = []

        def _record(*args: object, **kwargs: object) -> object:
            called.append((args, kwargs))
            raise AssertionError("OTF engine must not be called for empty signals")

        monkeypatch.setattr("thesistester.engine.otf_filter.calculate_otf_state", _record)

        sig = self._empty_signals()
        apply_otf_filter(self._source(), sig, enabled=True, timeframes=("5m",))
        assert len(called) == 0

    def test_invalid_config_still_raises_before_empty_return(self) -> None:
        sig = self._empty_signals()
        with pytest.raises(ValueError, match="enabled=True requires at least one selected timeframe"):
            apply_otf_filter(self._source(), sig, enabled=True, timeframes=())

    def test_caller_owned_dataframes_not_mutated(self) -> None:
        sig = self._empty_signals()
        src = self._source()
        sig_before = sig.copy(deep=True)
        src_before = src.copy(deep=True)
        apply_otf_filter(src, sig, enabled=True, timeframes=("5m",))
        pd.testing.assert_frame_equal(sig, sig_before)
        pd.testing.assert_frame_equal(src, src_before)


class TestNormalizeOtfTimeframe:
    """normalize_otf_timeframe must be the single authoritative normalization."""

    def test_canonical_values_normalize_to_themselves(self) -> None:
        from thesistester.engine import normalize_otf_timeframe

        assert normalize_otf_timeframe("5m") == "5m"
        assert normalize_otf_timeframe("15m") == "15m"
        assert normalize_otf_timeframe("30m") == "30m"

    def test_aliases_normalize_to_canonical_values(self) -> None:
        from thesistester.engine import normalize_otf_timeframe

        assert normalize_otf_timeframe("5min") == "5m"
        assert normalize_otf_timeframe("15min") == "15m"
        assert normalize_otf_timeframe("30min") == "30m"

    def test_unsupported_values_raise_value_error(self) -> None:
        from thesistester.engine import normalize_otf_timeframe

        with pytest.raises(ValueError, match="Unsupported OTF timeframe"):
            normalize_otf_timeframe("1m")
        with pytest.raises(ValueError, match="Unsupported OTF timeframe"):
            normalize_otf_timeframe("10m")
        with pytest.raises(ValueError, match="Unsupported OTF timeframe"):
            normalize_otf_timeframe("1h")

    def test_otf_engine_canonical_and_alias_outputs_are_identical(self) -> None:
        """calculate_otf_state with canonical and alias timeframes must produce the same result."""
        src = _source_1m("2026-01-05 09:30", 120, trend="up")
        from thesistester.engine.otf import calculate_otf_state

        result_canonical = calculate_otf_state(src, "5m", minimum_consecutive_bars=1)
        result_alias = calculate_otf_state(src, "5min", minimum_consecutive_bars=1)
        pd.testing.assert_frame_equal(result_canonical.reset_index(drop=True), result_alias.reset_index(drop=True))

    def test_filter_canonical_and_alias_outputs_are_identical(self) -> None:
        """apply_otf_filter with canonical and alias timeframes must produce the same result."""
        src = _source_1m("2026-01-05 09:30", 120, trend="up")
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 10:20", tz=TZ), direction="long"))

        acc_c, rej_c = apply_otf_filter(src, sig, enabled=True, timeframes=("15m",), minimum_consecutive_bars=1)
        acc_a, rej_a = apply_otf_filter(src, sig, enabled=True, timeframes=("15min",), minimum_consecutive_bars=1)

        # Both alias and canonical normalize to 15m, so schemas and values are identical.
        pd.testing.assert_frame_equal(acc_c.reset_index(drop=True), acc_a.reset_index(drop=True))
        pd.testing.assert_frame_equal(rej_c.reset_index(drop=True), rej_a.reset_index(drop=True))

    def test_duplicate_normalized_timeframes_raise_when_enabled(self) -> None:
        src = _source_1m("2026-01-05 09:30", 20)
        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        with pytest.raises(ValueError, match="Duplicate OTF timeframe"):
            apply_otf_filter(src, sig, enabled=True, timeframes=("5m", "5min"))

    def test_disabled_mode_does_not_invoke_normalization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[object] = []
        original = __import__(
            "thesistester.engine.otf_filter", fromlist=["normalize_otf_timeframe"]
        ).normalize_otf_timeframe

        def _spy(tf: str) -> str:
            called.append(tf)
            return original(tf)

        monkeypatch.setattr("thesistester.engine.otf_filter.normalize_otf_timeframe", _spy)

        sig = _signals(_signal(signal_id=1, timestamp=pd.Timestamp("2026-01-05 09:35", tz=TZ), direction="long"))
        apply_otf_filter(
            pd.DataFrame(), sig, enabled=False, timeframes=("5m", "unsupported")
        )
        assert len(called) == 0

