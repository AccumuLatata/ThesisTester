"""TJ4 daily recon + CLI — plan §3.4 / §5 TJ4."""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.journal import (
    TRADESVIZ_EXECUTIONS_PROFILE,
    load_tradesviz_executions,
    parse_amp_statement_text,
    quantize_price,
    reconcile_journal,
)
from thesistester.journal import reconcile as recon_mod
from thesistester.journal.amp_statement import parse_amp_statement_text as parse_amp
from thesistester.journal.schema import (
    RECON_AMP_MISSING,
    RECON_JOURNAL_MISSING,
    RECON_MULTISET_MISMATCH,
    RECON_PNL_MISMATCH,
    RECON_RECONCILED,
)
from thesistester.journal.reconcile import load_amp_statement_file

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "journal"
GOLDEN_TV = FIXTURES / "tradesviz_mnq_20260527_40fill.csv"
GOLDEN_AMP = FIXTURES / "amp_mnq_20260527_40fill.txt"
AMP_12JUN = FIXTURES / "amp_mnq_20260612_journal_missing.txt"
HEADER = (
    "date,symbol,side,currency,underlying,asset_type,price,quantity,"
    "commission,fees,stop_loss,profit_target,tags,notes,spread_id"
)


def _load_tv(path: Path = GOLDEN_TV):
    return load_tradesviz_executions(path, profile=TRADESVIZ_EXECUTIONS_PROFILE)


def _write_csv(tmp_path: Path, *rows: str, name: str = "executions.csv") -> Path:
    path = tmp_path / name
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    return path


def _tiny_amp(
    *,
    day: str = "14-MAY-26",
    buy: float = 100.00,
    sell: float = 101.00,
    ps: float = 2.00,
    extra_fee: str | None = None,
) -> str:
    extra = f"    LIQUIDATION FEE              {extra_fee} DR\n" if extra_fee else ""
    fee_total = 1.24 + (float(extra_fee) if extra_fee else 0.0)
    return f"""\
                              DAILY STATEMENT
     REDACTED CLIENT                                 {day}
                           T R A D E S C O N F I R M A T I O N S
 {day} 19000001 CME 1        MNQ Future JUN 26         {buy:.2f} USD
 {day} 19000002 CME        1 MNQ Future JUN 26         {sell:.2f} USD
 TOTAL                  1      1 EX- 18-JUN-26
                                             AVERAGE LONG {buy:.5f}
                                             AVERAGE SHORT {sell:.5f}
                                P U R C H A S E & S A L E
 {day} 19000002 CME      1 MNQ Future JUN 26           {sell:.2f} USD
 {day} 19000001 CME 1     MNQ Future JUN 26            {buy:.2f} USD
 TOTAL                  1     1 EX- 18-JUN-26         P&S         USD     {ps:.2f} CR
                      Account Summary as of 05/14/26
   TOTAL COMMISSION & FEES       {fee_total:.2f} DR
    EXCHANGE                     0.70 DR
    NFA                          0.04 DR
    CLEARING CLIENT              0.26 DR
    RITHMIC TRF                  0.20 DR
    COMMISSION                   0.04 DR
{extra}   OPEN TRADE EQUITY             0.00 CR
"""


def test_reconcile_kwargs_are_keyword_only() -> None:
    params = inspect.signature(reconcile_journal).parameters
    assert params["include_manual"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["journal_risk_ticks"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["pnl_tolerance"].kind is inspect.Parameter.KEYWORD_ONLY


def test_27_may_redacted_golden_reconciles() -> None:
    fills = _load_tv()
    stmt = parse_amp_statement_text(GOLDEN_AMP.read_text(encoding="utf-8"))
    assert stmt.session_date == date(2026, 5, 27)
    assert len(stmt.fills) == 40
    assert stmt.average_long == 30132.875
    assert stmt.average_short == 30133.55
    assert stmt.ps_usd == 27.0
    trades, days = reconcile_journal(fills, (stmt,))
    assert len(days) == 1
    day = days[0]
    assert day.status == RECON_RECONCILED
    assert day.session_date == date(2026, 5, 27)
    assert day.instrument == "MNQ"
    assert day.journal_fill_count == 40
    assert day.amp_fill_count == 40
    assert day.journal_gross_usd == pytest.approx(27.0)
    assert day.amp_ps_usd == pytest.approx(27.0)
    assert day.fee_total_usd == pytest.approx(24.80)
    assert day.day_fees_extra == 0.0
    closed = trades[trades["status"] == "closed"]
    assert len(closed) == 20
    assert (closed["recon_status"] == RECON_RECONCILED).all()
    assert closed["commission_cost"].astype(float).eq(1.24).all()
    assert closed["fee_ticks"].astype(float).eq(2.48).all()
    assert closed["day_fee_allocation"].astype(float).eq(0.0).all()
    assert closed["net_pnl_currency"].sum() == pytest.approx(27.0 - 24.80)
    assert "commission" not in trades.columns


def test_quantize_price_uses_tick_not_round2() -> None:
    assert quantize_price(30133.50) == 30133.50
    assert quantize_price(30133.60) == 30133.50
    assert quantize_price(30133.70) == 30133.75


def test_journal_missing_12jun_pattern() -> None:
    fills = _load_tv()
    may = parse_amp_statement_text(GOLDEN_AMP.read_text(encoding="utf-8"))
    jun = parse_amp_statement_text(AMP_12JUN.read_text(encoding="utf-8"))
    _, days = reconcile_journal(fills, (may, jun))
    by_date = {day.session_date: day for day in days}
    assert by_date[date(2026, 5, 27)].status == RECON_RECONCILED
    assert by_date[date(2026, 6, 12)].status == RECON_JOURNAL_MISSING
    assert by_date[date(2026, 6, 12)].amp_fill_count == 2
    assert by_date[date(2026, 6, 12)].journal_fill_count == 0


def test_amp_missing_synthetic_date() -> None:
    fills = load_tradesviz_executions(
        FIXTURES / "tradesviz_executions_synthetic.csv",
        profile=TRADESVIZ_EXECUTIONS_PROFILE,
    )
    stmt = parse_amp_statement_text(GOLDEN_AMP.read_text(encoding="utf-8"))
    _, days = reconcile_journal(fills, (stmt,))
    statuses = {(day.session_date, day.instrument): day.status for day in days}
    assert statuses[(date(2026, 5, 27), "MNQ")] == RECON_JOURNAL_MISSING
    assert (date(2026, 5, 14), "MNQ") in statuses
    assert statuses[(date(2026, 5, 14), "MNQ")] == RECON_AMP_MISSING


def test_multiset_mismatch(tmp_path: Path) -> None:
    tv = _write_csv(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,m1",
        "2026-05-14T14:00:02+0000,MNQM26,sell,USD,MNQ,future,102.00,1.0,0.0,0.0,N/A,N/A,,,m1",
    )
    amp = tmp_path / "amp.txt"
    amp.write_text(_tiny_amp(buy=100.00, sell=101.00, ps=2.00), encoding="utf-8")
    trades, days = reconcile_journal(_load_tv(tv), (parse_amp(amp.read_text()),))
    assert days[0].status == RECON_MULTISET_MISMATCH
    assert trades.iloc[0]["commission_cost"] is None


def test_pnl_mismatch_when_ps_disagrees(tmp_path: Path) -> None:
    tv = _write_csv(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,p1",
        "2026-05-14T14:00:02+0000,MNQM26,sell,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,p1",
    )
    amp = tmp_path / "amp.txt"
    amp.write_text(_tiny_amp(buy=100.00, sell=101.00, ps=99.00), encoding="utf-8")
    _, days = reconcile_journal(_load_tv(tv), (parse_amp(amp.read_text()),))
    assert days[0].status == RECON_PNL_MISMATCH
    assert days[0].journal_gross_usd == pytest.approx(2.0)


def test_liquidation_fee_allocates_across_day_trades(tmp_path: Path) -> None:
    tv = _write_csv(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,liq",
        "2026-05-14T14:00:02+0000,MNQM26,sell,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,liq",
    )
    amp = tmp_path / "amp.txt"
    amp.write_text(_tiny_amp(buy=100.00, sell=101.00, ps=2.00, extra_fee="2.50"), encoding="utf-8")
    trades, days = reconcile_journal(_load_tv(tv), (parse_amp(amp.read_text()),))
    assert days[0].status == RECON_RECONCILED
    assert days[0].day_fees_extra == pytest.approx(2.50)
    row = trades.iloc[0]
    assert row["commission_cost"] == pytest.approx(1.24)
    assert row["day_fee_allocation"] == pytest.approx(2.50)
    assert row["net_pnl_currency"] == pytest.approx(2.0 - 1.24 - 2.50)
    assert row["fee_ticks"] == pytest.approx(2.48)


def test_liquidation_fee_splits_equally_across_two_trades(tmp_path: Path) -> None:
    tv = _write_csv(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,a",
        "2026-05-14T14:00:02+0000,MNQM26,sell,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,a",
        "2026-05-14T14:00:04+0000,MNQM26,buy,USD,MNQ,future,100.00,1.0,0.0,0.0,N/A,N/A,,,b",
        "2026-05-14T14:00:06+0000,MNQM26,sell,USD,MNQ,future,101.00,1.0,0.0,0.0,N/A,N/A,,,b",
    )
    amp = tmp_path / "amp.txt"
    amp.write_text(
        """\
                              DAILY STATEMENT
     REDACTED CLIENT                                 14-MAY-26
                           T R A D E S C O N F I R M A T I O N S
 14-MAY-26 19000001 CME 1        MNQ Future JUN 26         100.00 USD
 14-MAY-26 19000002 CME        1 MNQ Future JUN 26         101.00 USD
 14-MAY-26 19000003 CME 1        MNQ Future JUN 26         100.00 USD
 14-MAY-26 19000004 CME        1 MNQ Future JUN 26         101.00 USD
 TOTAL                  2      2 EX- 18-JUN-26
                                             AVERAGE LONG 100.00000
                                             AVERAGE SHORT 101.00000
                                P U R C H A S E & S A L E
 14-MAY-26 19000002 CME      1 MNQ Future JUN 26           101.00 USD
 14-MAY-26 19000001 CME 1     MNQ Future JUN 26            100.00 USD
 14-MAY-26 19000004 CME      1 MNQ Future JUN 26           101.00 USD
 14-MAY-26 19000003 CME 1     MNQ Future JUN 26            100.00 USD
 TOTAL                  2     2 EX- 18-JUN-26         P&S         USD     4.00 CR
                      Account Summary as of 05/14/26
   TOTAL COMMISSION & FEES       4.98 DR
    EXCHANGE                     1.40 DR
    NFA                          0.08 DR
    CLEARING CLIENT              0.52 DR
    RITHMIC TRF                  0.40 DR
    COMMISSION                   0.08 DR
    LIQUIDATION FEE              2.50 DR
   OPEN TRADE EQUITY             0.00 CR
""",
        encoding="utf-8",
    )
    trades, days = reconcile_journal(_load_tv(tv), (parse_amp(amp.read_text()),))
    assert days[0].status == RECON_RECONCILED
    assert days[0].day_fees_extra == pytest.approx(2.50)
    assert len(trades) == 2
    assert trades["day_fee_allocation"].astype(float).eq(1.25).all()
    assert trades["commission_cost"].astype(float).eq(1.24).all()
    assert trades["net_pnl_currency"].sum() == pytest.approx(4.0 - 2.48 - 2.50)


def test_commission_scales_with_qty(tmp_path: Path) -> None:
    tv = _write_csv(
        tmp_path,
        "2026-05-14T14:00:00+0000,MNQM26,buy,USD,MNQ,future,100.00,2.0,0.0,0.0,N/A,N/A,,,q2",
        "2026-05-14T14:00:02+0000,MNQM26,sell,USD,MNQ,future,101.00,2.0,0.0,0.0,N/A,N/A,,,q2",
    )
    amp = tmp_path / "amp.txt"
    amp.write_text(
        """\
                              DAILY STATEMENT
     REDACTED CLIENT                                 14-MAY-26
                           T R A D E S C O N F I R M A T I O N S
 14-MAY-26 19000001 CME 2        MNQ Future JUN 26         100.00 USD
 14-MAY-26 19000002 CME        2 MNQ Future JUN 26         101.00 USD
 TOTAL                  2      2 EX- 18-JUN-26
                                             AVERAGE LONG 100.00000
                                             AVERAGE SHORT 101.00000
                                P U R C H A S E & S A L E
 14-MAY-26 19000002 CME      2 MNQ Future JUN 26           101.00 USD
 14-MAY-26 19000001 CME 2     MNQ Future JUN 26            100.00 USD
 TOTAL                  2     2 EX- 18-JUN-26         P&S         USD     4.00 CR
                      Account Summary as of 05/14/26
   TOTAL COMMISSION & FEES       2.48 DR
    EXCHANGE                     1.40 DR
    NFA                          0.08 DR
    CLEARING CLIENT              0.52 DR
    RITHMIC TRF                  0.40 DR
    COMMISSION                   0.08 DR
   OPEN TRADE EQUITY             0.00 CR
""",
        encoding="utf-8",
    )
    trades, days = reconcile_journal(_load_tv(tv), (parse_amp(amp.read_text()),))
    assert days[0].status == RECON_RECONCILED
    row = trades.iloc[0]
    assert int(row["qty"]) == 2
    assert row["gross_pnl_currency"] == pytest.approx(4.0)
    assert row["commission_cost"] == pytest.approx(2.48)
    assert row["fee_ticks"] == pytest.approx(4.96)
    assert row["r_multiple"] == pytest.approx((4.0 - 2.48) / (10 * 0.25 * 2.0 * 2))


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "reconcile",
            "--executions",
            str(GOLDEN_TV),
            "--statements",
            str(GOLDEN_AMP),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    recon = json.loads((out / "reconcile.json").read_text(encoding="utf-8"))
    assert recon["schema_version"] == "journal/v1"
    assert recon["days"][0]["status"] == RECON_RECONCILED
    assert recon["days"][0]["journal_gross_usd"] == 27.0
    frame = pd.read_parquet(out / "journal_trades.parquet")
    assert len(frame) == 20
    assert "recon_status" in frame.columns
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "reconcile",
            "--executions",
            str(GOLDEN_TV),
            "--statements",
            str(GOLDEN_AMP),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "reconcile.json").exists()


def test_write_helpers_are_keyword_only_on_files() -> None:
    params = inspect.signature(recon_mod.reconcile_files).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())


def test_pair_does_not_import_engine() -> None:
    source = Path(recon_mod.__file__).read_text(encoding="utf-8")
    assert "from thesistester.engine" not in source
    assert "import simulate_trades" not in source
    assert "results/studies" in source


def test_fixtures_are_redacted() -> None:
    blob = GOLDEN_AMP.read_text(encoding="utf-8") + GOLDEN_TV.read_text(encoding="utf-8")
    blob += AMP_12JUN.read_text(encoding="utf-8")
    for token in ("Florian", "Richling", "Ahornergasse", "212106", "Wien"):
        assert token not in blob


def test_load_amp_text_file_roundtrip() -> None:
    stmt = load_amp_statement_file(GOLDEN_AMP)
    assert stmt.session_date == date(2026, 5, 27)
    assert len(stmt.fills) == 40
