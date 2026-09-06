"""TJ3 JournalTrade pairing — plan §3.0 / §3.3 / §5 TJ3."""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from thesistester.journal import (
    DEFAULT_JOURNAL_RISK_TICKS,
    JOURNAL_TRADE_COLUMNS,
    JournalIngestError,
    TRADESVIZ_EXECUTIONS_PROFILE,
    load_tradesviz_executions,
    pair_journal_trades,
)
from thesistester.journal import pair as pair_mod
from thesistester.journal.schema import PAIR_METHOD_FIFO, PAIR_METHOD_SPREAD

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "journal" / "tradesviz_executions_synthetic.csv"
)
HEADER = (
    "date,symbol,side,currency,underlying,asset_type,price,quantity,"
    "commission,fees,stop_loss,profit_target,tags,notes,spread_id"
)


def _load_csv(path: Path) -> pd.DataFrame:
    return load_tradesviz_executions(path, profile=TRADESVIZ_EXECUTIONS_PROFILE)


def _write_csv(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "executions.csv"
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    return path


def _pair(tmp_path: Path, *rows: str, **kwargs):
    return pair_journal_trades(_load_csv(_write_csv(tmp_path, *rows)), **kwargs)


def test_pair_kwargs_are_keyword_only() -> None:
    params = inspect.signature(pair_journal_trades).parameters
    assert params["include_manual"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["journal_risk_ticks"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["include_manual"].default is False
    assert params["journal_risk_ticks"].default == DEFAULT_JOURNAL_RISK_TICKS == 10


def test_clean_2fill_spread_id(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:03:25+0000,MNQM26,buy,USD,MNQ,future,29584.0,1.0,0.0,0.0,N/A,N/A,,,rt2",
        "2026-05-14T14:03:49+0000,MNQM26,sell,USD,MNQ,future,29585.0,1.0,0.0,0.0,N/A,N/A,,,rt2",
    )
    assert list(trades.columns) == list(JOURNAL_TRADE_COLUMNS)
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["trade_id"] == "jt:rt2:0"
    assert row["pair_method"] == PAIR_METHOD_SPREAD
    assert row["direction"] == "long"
    assert row["qty"] == 1
    assert row["status"] == "closed"
    assert row["gross_pnl_points"] == pytest.approx(1.0)
    assert row["gross_pnl_currency"] == pytest.approx(2.0)
    assert row["commission_cost"] is None
    assert row["slippage_cost"] is None
    assert row["day_fee_allocation"] is None
    assert row["net_pnl_currency"] == pytest.approx(2.0)
    assert row["fee_ticks"] is None
    assert row["net_ticks"] == pytest.approx(4.0)
    assert row["hold_seconds"] == pytest.approx(24.0)
    assert row["r_multiple"] == pytest.approx(2.0 / 5.0)
    assert row["r_multiple_declared"] is None
    assert row["journal_risk_ticks"] == 10
    assert row["bars_held"] is None
    assert pd.isna(row["mae_points"]) or row["mae_points"] is None


def test_4fill_scale_in_fifo_inside_group() -> None:
    fills = _load_csv(FIXTURE)
    trades = pair_journal_trades(fills)
    scale = trades[trades["source_group_id"] == "scaleIn4"]
    assert len(scale) == 2
    assert (scale["pair_method"] == PAIR_METHOD_SPREAD).all()
    assert list(scale["lot_seq"]) == [0, 1]
    assert list(scale["qty"]) == [1, 1]
    assert list(scale["entry_price"]) == [29584.0, 29584.25]
    assert list(scale["exit_price"]) == [29585.00, 29585.25]
    assert scale.iloc[0]["exit_fill_id"] != scale.iloc[1]["exit_fill_id"]
    assert list(scale["trade_id"]) == ["jt:scaleIn4:0", "jt:scaleIn4:1"]


def test_qty2_cover_against_two_1lot_opens(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,cover2",
        "2026-05-14T14:00:01+0000,MNQM26,buy,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,cover2",
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,102.00,2.0,0.0,0.0,N/A,N/A,,,cover2",
    )
    assert len(trades) == 2
    assert list(trades["lot_seq"]) == [0, 1]
    assert list(trades["qty"]) == [1, 1]
    assert list(trades["entry_price"]) == [100.0, 101.0]
    assert list(trades["exit_price"]) == [102.0, 102.0]
    assert trades.iloc[0]["exit_fill_id"] == trades.iloc[1]["exit_fill_id"]
    assert (trades["pair_method"] == PAIR_METHOD_SPREAD).all()


def test_qty2_vs_qty2_is_one_trade(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-28T14:01:28+0000,MNQU26,buy,USD,MNQ,future,29989.75,2.0,0.0,0.0,N/A,N/A,,,sepMNQ",
        "2026-05-28T14:01:50+0000,MNQU26,sell,USD,MNQ,future,29983.00,2.0,0.0,0.0,N/A,N/A,,,sepMNQ",
    )
    assert len(trades) == 1
    assert trades.iloc[0]["qty"] == 2
    assert trades.iloc[0]["gross_pnl_points"] == pytest.approx(-6.75)
    assert trades.iloc[0]["gross_pnl_currency"] == pytest.approx(-27.0)
    assert trades.iloc[0]["net_ticks"] == pytest.approx(-54.0)


def test_non_netting_group_falls_to_fifo_and_leftover_is_open(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,N/A,,,odd",
        "2026-05-14T14:00:01+0000,MNQM26,buy,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,odd",
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,102.0,1.0,0.0,0.0,N/A,N/A,,,odd",
    )
    assert list(trades["pair_method"]) == [PAIR_METHOD_FIFO, PAIR_METHOD_FIFO]
    closed = trades[trades["status"] == "closed"]
    opened = trades[trades["status"] == "open"]
    assert len(closed) == 1
    assert len(opened) == 1
    assert opened.iloc[0]["qty"] == 1
    assert opened.iloc[0]["entry_price"] == 101.0
    assert pd.isna(opened.iloc[0]["exit_timestamp"])
    assert opened.iloc[0]["gross_pnl_currency"] is None
    assert opened.iloc[0]["hold_seconds"] is None
    assert str(opened.iloc[0]["trade_id"]).startswith("jt:fifo:MNQ:JUN:2026:")


def test_missing_spread_id_is_fifo_fallback(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,sell,USD,MNQ,future,200.0,1.0,0.0,0.0,N/A,N/A,,,",
        "2026-05-14T14:00:08+0000,MNQM26,buy,USD,MNQ,future,199.0,1.0,0.0,0.0,N/A,N/A,,,",
    )
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["pair_method"] == PAIR_METHOD_FIFO
    assert row["direction"] == "short"
    assert row["gross_pnl_points"] == pytest.approx(1.0)
    assert row["source_group_id"] is None


def test_cross_through_zero_spread_falls_to_fifo(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,N/A,,,flip",
        "2026-05-14T14:00:01+0000,MNQM26,sell,USD,MNQ,future,101.0,2.0,0.0,0.0,N/A,N/A,,,flip",
        "2026-05-14T14:00:02+0000,MNQM26,buy,USD,MNQ,future,100.5,1.0,0.0,0.0,N/A,N/A,,,flip",
    )
    assert (trades["pair_method"] == PAIR_METHOD_FIFO).all()
    assert list(trades["direction"]) == ["long", "short"]
    assert list(trades["status"]) == ["closed", "closed"]


def test_tags_notes_and_declared_sl_tp_propagate(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        '2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,99.0,110.0,"pdVAL,ITR-C","<p>note</p>",tagged',
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,tagged",
    )
    row = trades.iloc[0]
    assert row["tags"] == ("pdVAL", "ITR-C")
    assert row["notes_text"] == "note"
    assert row["stop_price"] == 99.0
    assert row["target_price"] == 110.0
    assert row["r_multiple_declared"] == pytest.approx(2.0 / (1.0 * 2.0 * 1))
    assert row["r_multiple"] == pytest.approx(2.0 / 5.0)


def test_r_multiple_declared_absent_without_stop(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,110.0,,,noStop",
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,noStop",
    )
    assert trades.iloc[0]["target_price"] == 110.0
    assert trades.iloc[0]["r_multiple_declared"] is None
    assert trades.iloc[0]["stop_price"] is None


def test_r_multiple_denominator_includes_qty(tmp_path: Path) -> None:
    one = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,N/A,,,q1",
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,q1",
    ).iloc[0]
    two = _pair(
        tmp_path,
        "2026-05-14T15:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,2.0,0.0,0.0,N/A,N/A,,,q2",
        "2026-05-14T15:00:10+0000,MNQM26,sell,USD,MNQ,future,101.0,2.0,0.0,0.0,N/A,N/A,,,q2",
    ).iloc[0]
    assert one["r_multiple"] == pytest.approx(two["r_multiple"])
    assert two["gross_pnl_currency"] == pytest.approx(2.0 * one["gross_pnl_currency"])
    assert two["net_ticks"] == pytest.approx(2.0 * one["net_ticks"])
    risk_two = 10 * 0.25 * 2.0 * 2
    assert two["r_multiple"] == pytest.approx(two["net_pnl_currency"] / risk_two)


def test_mes_point_value_and_hold_seconds(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-06-12T13:30:00+0000,MESU26,buy,USD,MES,future,6010.50,1.0,0.0,0.0,N/A,N/A,,,mesSep",
        "2026-06-12T13:30:20+0000,MESU26,sell,USD,MES,future,6011.00,1.0,0.0,0.0,N/A,N/A,,,mesSep",
    )
    row = trades.iloc[0]
    assert row["instrument"] == "MES"
    assert row["gross_pnl_points"] == pytest.approx(0.5)
    assert row["gross_pnl_currency"] == pytest.approx(2.5)
    assert row["net_ticks"] == pytest.approx(2.0)
    assert row["hold_seconds"] == pytest.approx(20.0)
    assert row["r_multiple"] == pytest.approx(2.5 / (10 * 0.25 * 5.0 * 1))


def test_manual_rows_excluded_by_default() -> None:
    trades = pair_journal_trades(_load_csv(FIXTURE))
    assert (trades["instrument"] != "stock").all()
    notes = " ".join(str(text) for text in trades["notes_text"])
    assert "confluence" not in notes
    assert "manualTagged" not in set(trades["source_group_id"].dropna())


def test_include_manual_pairs_qty_positive_manual(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-07-08T14:57:00+0000,MNQ,sell,USD,MNQ,stock,29212.5,1.0,0.0,0.0,29100.0,29300.0,ITR-C,hello,man1",
        "2026-07-08T14:57:20+0000,MNQ,buy,USD,MNQ,stock,29200.0,1.0,0.0,0.0,N/A,N/A,,,man1",
        include_manual=True,
    )
    assert len(trades) == 1
    assert trades.iloc[0]["direction"] == "short"
    assert trades.iloc[0]["tags"] == ("ITR-C",)
    assert trades.iloc[0]["r_multiple_declared"] is not None


def test_journal_risk_ticks_override(tmp_path: Path) -> None:
    trades = _pair(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,N/A,,,r20",
        "2026-05-14T14:00:10+0000,MNQM26,sell,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,r20",
        journal_risk_ticks=20,
    )
    assert trades.iloc[0]["journal_risk_ticks"] == 20
    assert trades.iloc[0]["r_multiple"] == pytest.approx(2.0 / 10.0)


def test_invalid_journal_risk_ticks_fails(tmp_path: Path) -> None:
    fills = _load_csv(
        _write_csv(
            tmp_path,
            "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.0,1.0,0.0,0.0,N/A,N/A,,,x",
            "2026-05-14T14:00:01+0000,MNQM26,sell,USD,MNQ,future,101.0,1.0,0.0,0.0,N/A,N/A,,,x",
        )
    )
    with pytest.raises(JournalIngestError, match="journal_risk_ticks"):
        pair_journal_trades(fills, journal_risk_ticks=0)
    with pytest.raises(JournalIngestError, match="journal_risk_ticks"):
        pair_journal_trades(fills, journal_risk_ticks=10.0)  # type: ignore[arg-type]


def test_pair_does_not_import_engine_or_simulate_trades() -> None:
    source = Path(pair_mod.__file__).read_text(encoding="utf-8")
    assert "import simulate_trades" not in source
    assert "from thesistester.engine" not in source
    assert "compute_all_levels" not in source


def test_amp_ps_is_not_a_pairing_source() -> None:
    source = Path(pair_mod.__file__).read_text(encoding="utf-8")
    assert "AmpStatement" not in source
    assert "ps_pairs" not in source
    assert "amp_statement" not in source
