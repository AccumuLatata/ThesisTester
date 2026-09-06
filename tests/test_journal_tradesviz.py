"""TJ1 TradesViz executions loader — plan §3.0 / §3.1 / §5 TJ1."""

from __future__ import annotations

from datetime import date
import inspect
from pathlib import Path

import pandas as pd
import pytest

from thesistester.journal import (
    FILL_RECORD_COLUMNS,
    JournalIngestError,
    TRADESVIZ_EXECUTIONS_PROFILE,
    load_tradesviz_executions,
)
from thesistester.journal.schema import FLAG_MANUAL_NO_QTY
from thesistester.journal.tradesviz import strip_notes_html
from thesistester.levels.session_date import trading_session_date

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "journal" / "tradesviz_executions_synthetic.csv"
)
PROFILE = TRADESVIZ_EXECUTIONS_PROFILE
HEADER = (
    "date,symbol,side,currency,underlying,asset_type,price,quantity,"
    "commission,fees,stop_loss,profit_target,tags,notes,spread_id"
)


def _load(path=FIXTURE, **kwargs):
    return load_tradesviz_executions(path, profile=PROFILE, **kwargs)


def _write_csv(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "executions.csv"
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    return path


def test_profile_is_keyword_only_and_required():
    params = inspect.signature(load_tradesviz_executions).parameters
    assert params["profile"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["profile"].default is inspect.Parameter.empty


def test_wrong_profile_fails_closed(tmp_path):
    path = _write_csv(
        tmp_path,
        "2026-05-14T14:03:25+0000,MNQM26,buy,USD,MNQ,future,29584.0,1.0,0.0,0.0,N/A,N/A,,,g1",
    )
    with pytest.raises(JournalIngestError, match="no autodetect"):
        load_tradesviz_executions(path, profile="quantower_trades")


def test_synthetic_fixture_shape_and_kinds():
    frame = _load()
    assert list(frame.columns) == list(FILL_RECORD_COLUMNS)
    assert "commission" not in frame.columns
    assert "fees" not in frame.columns
    assert set(frame["source"].unique()) == {"tradesviz"}
    imported = frame[frame["entry_kind"] == "imported"]
    manual = frame[frame["entry_kind"] == "manual"]
    assert len(imported) == 10
    assert len(manual) == 2
    assert (imported["instrument"].isin(["MNQ", "MES"])).all()
    assert imported["qty"].notna().all()


def test_commission_and_fees_are_read_and_discarded():
    """Row 0 of the fixture carries commission=99 / fees=12.5 — must not leak."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "99.0,12.5" in raw
    frame = _load()
    assert list(frame.columns) == list(FILL_RECORD_COLUMNS)
    first = frame.iloc[0]
    assert first["price"] == 29584.0
    assert first["qty"] == 1
    assert first["source_group_id"] == "scaleIn4"
    # The discarded 99 / 12.5 must not appear as a numeric cell.
    numeric = pd.concat([frame["price"], frame["qty"].dropna(), frame["declared_stop"].dropna()])
    assert 99.0 not in set(numeric.astype(float))
    assert 12.5 not in set(numeric.astype(float))


def test_four_fill_spread_id_preserved():
    frame = _load()
    group = frame[frame["source_group_id"] == "scaleIn4"]
    assert len(group) == 4
    assert list(group["side"]) == ["buy", "buy", "sell", "sell"]
    assert list(group["qty"]) == [1, 1, 1, 1]
    assert group["entry_kind"].eq("imported").all()
    assert group["contract_month"].eq("JUN").all()
    assert group["contract_year"].eq(2026).all()


def test_manual_tagged_row_keeps_tags_sl_tp_and_stripped_notes():
    frame = _load()
    tagged = frame.loc[frame["source_group_id"] == "manualTagged"]
    assert tagged["entry_kind"].iloc[0] == "manual"
    assert tagged["instrument"].iloc[0] == "MNQ"
    # Column-wise access keeps Python None (row-wise Series.iloc coerces to NaN).
    assert tagged["contract_month"].iloc[0] is None
    assert tagged["contract_year"].iloc[0] is None
    assert tagged["qty"].iloc[0] == 1
    assert tagged["tags"].iloc[0] == ("pdVAL_retest", "ITR-C")
    assert tagged["declared_stop"].iloc[0] == 29100.0
    assert tagged["declared_target"].iloc[0] == 29300.0
    assert tagged["notes_text"].iloc[0] == "confluence [image] note"
    assert "<img" not in tagged["notes_text"].iloc[0]


def test_quantity_zero_manual_row_flagged():
    frame = _load()
    zero = frame.loc[frame["source_group_id"] == "manualZero"]
    assert zero["entry_kind"].iloc[0] == "manual"
    assert zero["qty"].iloc[0] is None
    assert FLAG_MANUAL_NO_QTY in zero["flags"].iloc[0]
    assert zero["notes_text"].iloc[0] == ""


def test_session_date_eth_1805_et_is_next_calendar_date():
    """Sunday 2026-05-17 18:05 ET (22:05 UTC) is Monday's CME session."""
    frame = _load()
    eth = frame[frame["source_group_id"] == "eth1805"]
    assert eth["timestamp"].iloc[0].isoformat() == "2026-05-17T22:05:00+00:00"
    local = eth["timestamp"].dt.tz_convert("America/New_York")
    assert local.iloc[0].isoformat() == "2026-05-17T18:05:00-04:00"
    expected = trading_session_date(local, "18:00")
    assert list(eth["session_date"]) == [date(2026, 5, 18), date(2026, 5, 18)]
    assert list(expected) == [date(2026, 5, 18), date(2026, 5, 18)]
    # Calendar NY date would have been 17 May — that is the bug this lock prevents.
    assert local.dt.date.iloc[0] == date(2026, 5, 17)


def test_rth_import_session_date_matches_calendar_when_before_eth():
    frame = _load()
    scale = frame[frame["source_group_id"] == "scaleIn4"]
    assert set(scale["session_date"]) == {date(2026, 5, 14)}


def test_mnqu26_and_mesu26_symbol_map():
    frame = _load()
    mnq_sep = frame[frame["source_group_id"] == "sepMNQ"].iloc[0]
    assert mnq_sep["instrument"] == "MNQ"
    assert mnq_sep["contract_month"] == "SEP"
    assert mnq_sep["contract_year"] == 2026
    assert mnq_sep["qty"] == 2
    mes = frame[frame["source_group_id"] == "mesSep"].iloc[0]
    assert mes["instrument"] == "MES"
    assert mes["contract_month"] == "SEP"
    assert mes["contract_year"] == 2026


def test_timestamps_are_utc_aware():
    frame = _load()
    assert str(frame["timestamp"].dtype).endswith(", UTC]")
    assert frame["timestamp"].dt.tz is not None


def test_fill_id_is_deterministic():
    first = _load()
    second = _load()
    assert list(first["fill_id"]) == list(second["fill_id"])
    assert first["fill_id"].is_unique
    assert first["fill_id"].iloc[0].startswith("tv:000000:")


def test_naive_date_fails_closed(tmp_path):
    path = _write_csv(
        tmp_path,
        "2026-05-14T14:03:25,MNQM26,buy,USD,MNQ,future,29584.0,1.0,0.0,0.0,N/A,N/A,,,g1",
    )
    with pytest.raises(JournalIngestError, match="explicit UTC offset"):
        _load(path)


def test_unknown_symbol_fails_closed(tmp_path):
    path = _write_csv(
        tmp_path,
        "2026-05-14T14:03:25+0000,ESM26,buy,USD,ES,future,5000.0,1.0,0.0,0.0,N/A,N/A,,,g1",
    )
    with pytest.raises(JournalIngestError, match="unknown symbol"):
        _load(path)


def test_missing_commission_column_fails_closed(tmp_path):
    path = tmp_path / "no_commission.csv"
    path.write_text(
        "date,symbol,side,currency,underlying,asset_type,price,quantity,"
        "fees,stop_loss,profit_target,tags,notes,spread_id\n"
        "2026-05-14T14:03:25+0000,MNQM26,buy,USD,MNQ,future,29584.0,1.0,"
        "0.0,N/A,N/A,,,g1\n",
        encoding="utf-8",
    )
    with pytest.raises(JournalIngestError, match="commission"):
        _load(path)


def test_imported_zero_qty_fails_closed(tmp_path):
    path = _write_csv(
        tmp_path,
        "2026-05-14T14:03:25+0000,MNQM26,buy,USD,MNQ,future,29584.0,0.0,0.0,0.0,N/A,N/A,,,g1",
    )
    with pytest.raises(JournalIngestError, match="imported fill quantity"):
        _load(path)


def test_strip_notes_html_replaces_img_and_never_fetches():
    assert (
        strip_notes_html('<p><img src="/viewfile/nGASZtw4S" class="w-auto"><br></p>') == "[image]"
    )
    assert strip_notes_html("plain") == "plain"
    assert strip_notes_html("") == ""


def test_loader_does_not_import_engine_or_levels_compute():
    import thesistester.journal.tradesviz as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "from thesistester.engine" not in source
    assert "import thesistester.engine" not in source
    assert "compute_all_levels" not in source
    assert "from thesistester.engine.backtest" not in source
