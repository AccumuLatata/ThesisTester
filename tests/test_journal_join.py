"""TJ5 15s/1m/tick join — plan §3.0 / §3.5 / §5 TJ5."""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from thesistester.journal import (
    TRADESVIZ_EXECUTIONS_PROFILE,
    join_journal_bars,
    load_tradesviz_executions,
    pair_journal_trades,
)
from thesistester.journal import join as join_mod
from thesistester.journal.schema import (
    FLAG_EXCURSION_UNAVAILABLE,
    FLAG_MISSING_BAR,
    FLAG_PRICE_OUTSIDE_BAR,
    FLAG_ROLL_MISMATCH,
    JOIN_RESOLUTION_15S,
    JOIN_RESOLUTION_TICK,
    JournalIngestError,
)

HEADER = (
    "date,symbol,side,currency,underlying,asset_type,price,quantity,"
    "commission,fees,stop_loss,profit_target,tags,notes,spread_id"
)
UTC = "UTC"


def _pair(tmp_path: Path, *rows: str) -> pd.DataFrame:
    path = tmp_path / "executions.csv"
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    fills = load_tradesviz_executions(path, profile=TRADESVIZ_EXECUTIONS_PROFILE)
    return pair_journal_trades(fills)


def _ohlcv(
    rows: list[tuple[str, float, float, float, float]], *, contract: str | None = None
) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(stamp, tz=UTC),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            }
            for stamp, open_, high, low, close in rows
        ]
    )
    if contract is not None:
        frame["contract"] = contract
    return frame


def _minute_14() -> pd.DataFrame:
    """Four 15s bars covering 14:00–14:01 UTC plus the next minute."""
    bars = _ohlcv(
        [
            ("2026-05-14T14:00:00", 100.00, 100.50, 99.75, 100.25),
            ("2026-05-14T14:00:15", 100.25, 102.00, 99.00, 101.00),
            ("2026-05-14T14:00:30", 101.00, 103.00, 98.50, 100.50),
            ("2026-05-14T14:00:45", 100.50, 101.50, 100.00, 101.00),
            ("2026-05-14T14:01:00", 101.00, 101.25, 100.75, 101.00),
        ]
    )
    return bars


def _parent_14() -> pd.DataFrame:
    return _ohlcv(
        [
            ("2026-05-14T14:00:00", 100.00, 103.00, 98.50, 101.00),
            ("2026-05-14T14:01:00", 101.00, 101.25, 100.75, 101.00),
        ]
    )


def _same_bar_rows() -> tuple[str, str]:
    return (
        "2026-05-14T14:00:03+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,j1",
        "2026-05-14T14:00:12+0000,MNQM26,sell,USD,MNQ,future,100.25,1.0,0.0,0.0,N/A,N/A,,,j1",
    )


def _held_rows() -> tuple[str, str]:
    return (
        "2026-05-14T14:00:03+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,j2",
        "2026-05-14T14:00:48+0000,MNQM26,sell,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,j2",
    )


def test_join_kwargs_are_keyword_only() -> None:
    params = inspect.signature(join_journal_bars).parameters
    for name in (
        "data",
        "subtimeframe_data",
        "ticks",
        "join_resolution",
        "roll_metadata",
        "series_contract",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["join_resolution"].default == JOIN_RESOLUTION_15S


def test_same_bar_exit_is_excursion_unavailable(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    joined = join_journal_bars(trades, data=_parent_14(), subtimeframe_data=_minute_14())
    row = joined.iloc[0]
    assert row["resolution"] == JOIN_RESOLUTION_15S
    assert row["bars_held"] == 0
    assert row["mae_points"] is None
    assert row["mfe_points"] is None
    assert FLAG_EXCURSION_UNAVAILABLE in row["join_flags"]
    assert row["entry_bar_open"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)
    assert row["exit_bar_open"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)
    assert row["parent_1m_ts"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)


def test_bars_held_and_mae_mfe_ignore_entry_bar(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_held_rows())
    # Entry bar 14:00:00 has a tight range; intermediate bars are the excursion source.
    joined = join_journal_bars(trades, data=_parent_14(), subtimeframe_data=_minute_14())
    row = joined.iloc[0]
    assert row["bars_held"] == 2
    assert row["mae_points"] == pytest.approx(1.5)  # 100 - 98.50
    assert row["mfe_points"] == pytest.approx(3.0)  # 103 - 100
    assert row["join_flags"] == ()
    assert row["entry_bar_open"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)
    assert row["exit_bar_open"] == pd.Timestamp("2026-05-14T14:00:45", tz=UTC)
    assert row["parent_1m_ts"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)


def test_missing_bar(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T15:00:03+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,m",
        "2026-05-14T15:00:12+0000,MNQM26,sell,USD,MNQ,future,100.25,1.0,0.0,0.0,N/A,N/A,,,m",
    )
    joined = join_journal_bars(trades, data=_parent_14(), subtimeframe_data=_minute_14())
    assert FLAG_MISSING_BAR in joined.iloc[0]["join_flags"]
    assert joined.iloc[0]["entry_bar_open"] is None
    assert joined.iloc[0]["bars_held"] is None


def test_price_outside_bar(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:03+0000,MNQM26,buy,USD,MNQ,future,110.00,1.0,0.0,0.0,N/A,N/A,,,p",
        "2026-05-14T14:00:12+0000,MNQM26,sell,USD,MNQ,future,110.25,1.0,0.0,0.0,N/A,N/A,,,p",
    )
    joined = join_journal_bars(trades, data=_parent_14(), subtimeframe_data=_minute_14())
    assert FLAG_PRICE_OUTSIDE_BAR in joined.iloc[0]["join_flags"]


def test_roll_mismatch_without_metadata(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    bars = _minute_14()
    bars["contract"] = "MNQU26"
    parent = _parent_14()
    parent["contract"] = "MNQU26"
    joined = join_journal_bars(trades, data=parent, subtimeframe_data=bars)
    assert FLAG_ROLL_MISMATCH in joined.iloc[0]["join_flags"]
    assert joined.iloc[0]["contract_month"] == "JUN"


def test_segmented_metadata_without_gap_stays_mismatch(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    bars = _minute_14()
    bars["contract"] = "MNQU26"
    parent = _parent_14()
    parent["contract"] = "MNQU26"
    meta = {"roll_method": "segmented_contracts", "valid": True, "roll_gaps": []}
    joined = join_journal_bars(
        trades,
        data=parent,
        subtimeframe_data=bars,
        roll_metadata=meta,
    )
    assert FLAG_ROLL_MISMATCH in joined.iloc[0]["join_flags"]


def test_segmented_gap_covers_only_matching_session(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    bars = _minute_14()
    bars["contract"] = "MNQU26"
    parent = _parent_14()
    parent["contract"] = "MNQU26"
    covering = {
        "roll_method": "segmented_contracts",
        "valid": True,
        "roll_gaps": [
            {
                "previous_contract": "MNQM26",
                "next_contract": "MNQU26",
                "roll_timestamp": "2026-05-14T13:00:00+00:00",
            }
        ],
    }
    other_pair = {
        "roll_method": "segmented_contracts",
        "valid": True,
        "roll_gaps": [
            {
                "previous_contract": "MESH26",
                "next_contract": "MESM26",
                "roll_timestamp": "2026-05-14T13:00:00+00:00",
            }
        ],
    }
    future_gap = {
        "roll_method": "segmented_contracts",
        "valid": True,
        "roll_gaps": [
            {
                "previous_contract": "MNQM26",
                "next_contract": "MNQU26",
                "roll_timestamp": "2026-06-01T00:00:00+00:00",
            }
        ],
    }
    covered = join_journal_bars(trades, data=parent, subtimeframe_data=bars, roll_metadata=covering)
    assert FLAG_ROLL_MISMATCH not in covered.iloc[0]["join_flags"]
    for meta in (other_pair, future_gap):
        joined = join_journal_bars(trades, data=parent, subtimeframe_data=bars, roll_metadata=meta)
        assert FLAG_ROLL_MISMATCH in joined.iloc[0]["join_flags"]


def test_roll_metadata_covers_continuous_day(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    bars = _minute_14()
    bars["contract"] = "MNQU26"
    parent = _parent_14()
    parent["contract"] = "MNQU26"
    meta = {"roll_method": "external_continuous", "valid": True, "adjustment_method": "none"}
    joined = join_journal_bars(
        trades,
        data=parent,
        subtimeframe_data=bars,
        roll_metadata=meta,
    )
    assert FLAG_ROLL_MISMATCH not in joined.iloc[0]["join_flags"]


def test_tick_and_15s_share_parent_and_stamp_resolution(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_held_rows())
    ticks = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2026-05-14T14:00:03", tz=UTC),  # == entry; must not walk
                pd.Timestamp("2026-05-14T14:00:10", tz=UTC),
                pd.Timestamp("2026-05-14T14:00:20", tz=UTC),
                pd.Timestamp("2026-05-14T14:00:40", tz=UTC),
                pd.Timestamp("2026-05-14T14:00:48", tz=UTC),  # == exit; not < exit
            ],
            "price": [100.00, 99.50, 104.00, 100.50, 101.00],
        }
    )
    bars = _minute_14()
    parent = _parent_14()
    at_15s = join_journal_bars(trades, data=parent, subtimeframe_data=bars)
    at_tick = join_journal_bars(
        trades,
        data=parent,
        subtimeframe_data=bars,
        ticks=ticks,
        join_resolution=JOIN_RESOLUTION_TICK,
    )
    assert at_15s.iloc[0]["parent_1m_ts"] == at_tick.iloc[0]["parent_1m_ts"]
    assert at_15s.iloc[0]["resolution"] == JOIN_RESOLUTION_15S
    assert at_tick.iloc[0]["resolution"] == JOIN_RESOLUTION_TICK
    assert at_15s.iloc[0]["mae_points"] == pytest.approx(1.5)
    assert at_tick.iloc[0]["mae_points"] == pytest.approx(0.5)
    assert at_tick.iloc[0]["mfe_points"] == pytest.approx(4.0)
    assert at_15s.iloc[0]["bars_held"] == at_tick.iloc[0]["bars_held"] == 2


def test_tick_resolution_requires_session_prints(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_held_rows())
    other_day = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-05-15T14:00:10", tz=UTC)],
            "price": [100.0],
        }
    )
    with pytest.raises(JournalIngestError, match="no Last prints"):
        join_journal_bars(
            trades,
            data=_parent_14(),
            subtimeframe_data=_minute_14(),
            ticks=other_day,
            join_resolution=JOIN_RESOLUTION_TICK,
        )


def test_tick_walk_skips_entry_print(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_held_rows())
    ticks = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2026-05-14T14:00:03", tz=UTC),
                pd.Timestamp("2026-05-14T14:00:04", tz=UTC),
            ],
            "price": [90.00, 100.25],
        }
    )
    joined = join_journal_bars(
        trades,
        data=_parent_14(),
        subtimeframe_data=_minute_14(),
        ticks=ticks,
        join_resolution=JOIN_RESOLUTION_TICK,
    )
    # 90.00 is at entry_timestamp and must not create a 10-point MAE.
    assert joined.iloc[0]["mae_points"] == pytest.approx(0.0)
    assert joined.iloc[0]["mfe_points"] == pytest.approx(0.25)


def test_join_does_not_import_engine_or_derive() -> None:
    source = Path(join_mod.__file__).read_text(encoding="utf-8")
    assert "from thesistester.engine" not in source
    assert "import simulate_trades" not in source
    assert "compute_all_levels(" not in source
    assert "derive_complete_parent_ohlcv(" not in source


def test_naive_bar_timestamp_fails_closed(tmp_path: Path) -> None:
    trades = _pair(tmp_path, *_same_bar_rows())
    bars = _minute_14()
    bars["timestamp"] = bars["timestamp"].dt.tz_localize(None)
    with pytest.raises(JournalIngestError, match="naive timestamp"):
        join_journal_bars(trades, data=_parent_14(), subtimeframe_data=bars)


def test_open_trade_joins_entry_only(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:03+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,open1",
    )
    joined = join_journal_bars(trades, data=_parent_14(), subtimeframe_data=_minute_14())
    row = joined.iloc[0]
    assert row["status"] == "open"
    assert row["entry_bar_open"] == pd.Timestamp("2026-05-14T14:00:00", tz=UTC)
    assert row["exit_bar_open"] is None
    assert row["bars_held"] is None
    assert row["mae_points"] is None
    assert FLAG_EXCURSION_UNAVAILABLE not in row["join_flags"]
