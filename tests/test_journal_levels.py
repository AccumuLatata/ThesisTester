"""TJ6 level attribution + tag map — plan §3.0 / §3.6 / §5 TJ6."""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.journal import (
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    attribute_journal_trades,
    load_tag_map,
    mapped_engine_tokens,
    resolve_tag,
    write_attribution_artifacts,
)
from thesistester.journal import levels as levels_mod
from thesistester.journal.schema import (
    JOURNAL_TICK_SIZE,
    LEVEL_CONTEXT_AT_LEVEL,
    LEVEL_CONTEXT_BETWEEN,
    LEVEL_CONTEXT_NO_FRAME,
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    TAG_ALIGN_ALL,
    TAG_ALIGN_NONE,
    TAG_ALIGN_PARTIAL,
    TAG_ALIGN_UNVERIFIABLE,
    TAG_CLASS_CONFIRM,
    TAG_CLASS_CONTEXT,
    TAG_CLASS_LEVEL,
    TAG_CLASS_UNMAPPED,
    JournalIngestError,
)
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import closed_level_token_set

UTC = "UTC"


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _trade(
    *,
    entry: str,
    price: float,
    tags: tuple[str, ...] = (),
    recon: str | None = RECON_RECONCILED,
    trade_id: str = "jt:t1:1",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": date(2026, 5, 14),
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "tags": tags,
        "direction": "long",
        "qty": 1,
        "status": "closed",
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def _trades(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _levels(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["timestamp"] = [_ts(str(value)) for value in frame["timestamp"]]
    return frame


def _frame_14() -> pd.DataFrame:
    """Hand-built 1m frame: 13:59 / 14:00 / 14:01."""
    return _levels(
        [
            {
                "timestamp": "2026-05-14T13:59:00",
                "pdHigh": 99.00,
                "pdLow": 80.00,
                "pdVAL": 98.00,
                "pwVAH": 97.00,
                "pRTH_High": 96.00,
                "dVWAP": 90.00,
                "APOC": 91.00,
            },
            {
                "timestamp": "2026-05-14T14:00:00",
                "pdHigh": 100.00,
                "pdLow": 90.00,
                "pdVAL": 99.50,
                "pwVAH": 103.00,
                "pRTH_High": 100.25,
                "dVWAP": 100.00,
                "APOC": 100.50,
            },
            {
                "timestamp": "2026-05-14T14:01:00",
                "pdHigh": 101.00,
                "pdLow": 90.00,
                "pdVAL": 110.00,
                "pwVAH": 104.00,
                "pRTH_High": 108.00,
                "dVWAP": 200.00,
                "APOC": 201.00,
            },
        ]
    )


def test_attribute_kwargs_are_keyword_only() -> None:
    params = inspect.signature(attribute_journal_trades).parameters
    for name in (
        "levels",
        "levels_settings",
        "level_tolerance_ticks",
        "tag_tolerance_ticks",
        "allow_unreconciled",
        "tick_size",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["level_tolerance_ticks"].default == DEFAULT_LEVEL_TOLERANCE_TICKS
    assert params["tag_tolerance_ticks"].default == DEFAULT_TAG_TOLERANCE_TICKS
    assert params["allow_unreconciled"].default is False


def test_journal_levels_does_not_import_engine() -> None:
    import thesistester.journal.levels as loaded
    import thesistester.journal.tags as tags_loaded

    assert "thesistester.engine" not in getattr(loaded, "__dict__", {})
    assert "compute_all_levels" not in loaded.__dict__
    assert "simulate_trades" not in loaded.__dict__
    assert "compute_all_levels" not in tags_loaded.__dict__
    assert "thesistester.levels.all" not in loaded.__dict__


def test_mapped_tokens_are_in_default_closed_set() -> None:
    closed = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    tokens = mapped_engine_tokens()
    assert tokens
    missing = sorted(tokens - closed)
    assert missing == []
    for token in (
        "EMA_9_1min",
        "SMA_50_5min",
        "EMA_21_5min",
        "VWAP_rolling_4h",
        "prev30mVWAP",
        "mVWAP",
        "APOC",
    ):
        assert token in closed
        assert token in tokens


def test_tag_map_is_data_not_code() -> None:
    payload = load_tag_map()
    assert isinstance(payload.get("exact"), dict)
    assert resolve_tag("pdH").token == "pdHigh"
    assert resolve_tag("pdH").tag_class == TAG_CLASS_LEVEL
    assert resolve_tag("pdH_RTH").token == "pRTH_High"
    assert resolve_tag("pdH_RTH").qualifier is None
    stripped = resolve_tag("pdVAL_retest")
    assert stripped.token == "pdVAL"
    assert stripped.qualifier == "_retest"
    assert resolve_tag("p30POC").tag_class == TAG_CLASS_UNMAPPED
    assert resolve_tag("p30POC").token is None
    assert resolve_tag("ITR").tag_class == TAG_CLASS_CONTEXT
    assert resolve_tag("5m21EMA").tag_class == TAG_CLASS_CONFIRM
    assert resolve_tag("5m21EMA").token == "EMA_21_5min"
    unknown = resolve_tag("notADeskTag")
    assert unknown.tag_class == TAG_CLASS_UNMAPPED
    assert unknown.raw == "notADeskTag"


def test_at_level_between_levels_and_no_frame() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(entry="2026-05-14T14:00:24", price=100.00, trade_id="jt:at:1"),
        _trade(entry="2026-05-14T14:00:24", price=110.00, trade_id="jt:between:1"),
        _trade(entry="2026-05-14T15:00:24", price=100.00, trade_id="jt:none:1"),
    )
    out = attribute_journal_trades(trades, levels=frame)
    at_row = out.loc[out["trade_id"] == "jt:at:1"].iloc[0]
    between = out.loc[out["trade_id"] == "jt:between:1"].iloc[0]
    missing = out.loc[out["trade_id"] == "jt:none:1"].iloc[0]
    assert at_row["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    assert "pdHigh" in list(at_row["levels_within_tolerance"])
    assert at_row["nearest_level_token"] == "pdHigh"
    assert at_row["nearest_level_distance_ticks"] == pytest.approx(0.0)
    assert between["level_context"] == LEVEL_CONTEXT_BETWEEN
    assert list(between["levels_within_tolerance"]) == []
    assert between["nearest_level_token"] == "pwVAH"
    assert between["nearest_level_distance_ticks"] == pytest.approx(28.0)
    assert missing["level_context"] == LEVEL_CONTEXT_NO_FRAME
    assert list(missing["levels_within_tolerance"]) == []
    assert missing["nearest_level_token"] is None


def test_developing_token_uses_previous_completed_minute() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:01:10", price=100.00))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    nearby = list(row["levels_within_tolerance"])
    assert "dVWAP" in nearby
    assert "APOC" in nearby
    assert row["nearest_level_token"] == "dVWAP"
    assert row["nearest_level_distance_ticks"] == pytest.approx(0.0)
    # Current-minute developing values are 200 / 201 — using them would miss.
    assert 200.0 not in {abs(float(row["nearest_level_distance_ticks"]))}


def test_frozen_token_uses_containing_minute() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:01:10", price=101.00))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert row["nearest_level_token"] == "pdHigh"
    assert row["nearest_level_distance_ticks"] == pytest.approx(0.0)


def test_missing_previous_developing_bar_omits_token() -> None:
    frame = _levels(
        [
            {
                "timestamp": "2026-05-14T14:00:00",
                "pdHigh": 100.00,
                "dVWAP": 100.00,
            }
        ]
    )
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("dVWAP",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert "dVWAP" not in list(row["levels_within_tolerance"])
    assert row["nearest_level_token"] == "pdHigh"
    verify = row["tag_verifications"][0]
    assert verify["token"] == "dVWAP"
    assert verify["tag_level_missing"] is True
    assert row["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE


def test_unmapped_tags_are_counted_never_dropped() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "p30POC", "ITR", "mystery"),
        )
    )
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert list(row["unmapped_tags"]) == ["p30POC", "mystery"]
    assert "ITR" not in list(row["unmapped_tags"])
    assert row["tag_alignment"] == TAG_ALIGN_ALL
    assert resolve_tag("pdH").raw == "pdH"


def test_alignment_classes_and_intent_mismatch() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "pdH_RTH"),
            trade_id="jt:all:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "pdLow"),
            trade_id="jt:partial:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdLow",),
            trade_id="jt:none:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdVAL",),
            trade_id="jt:missing:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("ITR", "5m21EMA"),
            trade_id="jt:unver:1",
        ),
    )
    slim = frame.drop(columns=["pdVAL"])
    out = attribute_journal_trades(trades, levels=slim)
    all_row = out.loc[out["trade_id"] == "jt:all:1"].iloc[0]
    assert all_row["tag_alignment"] == TAG_ALIGN_ALL
    assert all_row["intent_mismatch"] is False
    partial = out.loc[out["trade_id"] == "jt:partial:1"].iloc[0]
    assert partial["tag_alignment"] == TAG_ALIGN_PARTIAL
    assert partial["intent_mismatch"] is False
    none_row = out.loc[out["trade_id"] == "jt:none:1"].iloc[0]
    assert none_row["tag_alignment"] == TAG_ALIGN_NONE
    assert none_row["intent_mismatch"] is True
    missing = out.loc[out["trade_id"] == "jt:missing:1"].iloc[0]
    assert missing["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert missing["tag_verifications"][0]["tag_level_missing"] is True
    assert missing["intent_mismatch"] is True
    unver = out.loc[out["trade_id"] == "jt:unver:1"].iloc[0]
    assert unver["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert unver["intent_mismatch"] is False


def test_tagged_a_but_at_b_when_named_level_is_far() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("pdVAL",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    # pdVAL at 99.50 is 2 ticks — aligned at default 10, so tighten tag tolerance.
    tight = attribute_journal_trades(
        trades, levels=frame, tag_tolerance_ticks=1.0, level_tolerance_ticks=10.0
    )
    row = tight.iloc[0]
    assert row["tag_alignment"] == TAG_ALIGN_NONE
    assert row["intent_mismatch"] is True
    assert "pdHigh" in list(row["levels_within_tolerance"])


def test_confirm_and_context_tags_do_not_drive_alignment() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("ITR-C", "5m50SMA")))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert row["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert row["tag_verifications"] == []
    assert list(row["unmapped_tags"]) == []


def test_refuses_unreconciled_days_by_default() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, recon=RECON_AMP_MISSING))
    with pytest.raises(JournalIngestError, match="not reconciled"):
        attribute_journal_trades(trades, levels=frame)
    out = attribute_journal_trades(trades, levels=frame, allow_unreconciled=True)
    assert out.iloc[0]["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    missing_col = trades.drop(columns=["recon_status"])
    with pytest.raises(JournalIngestError, match="not reconciled"):
        attribute_journal_trades(missing_col, levels=frame)


def test_positional_levels_argument_is_rejected() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    with pytest.raises(TypeError):
        attribute_journal_trades(trades, frame)  # type: ignore[misc]


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    trades_path = tmp_path / "journal_trades.parquet"
    levels_path = tmp_path / "levels.parquet"
    raw = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "p30POC", "mystery"),
        )
    )
    raw["tags"] = raw["tags"].map(list)
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    _frame_14().to_parquet(levels_path, index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "attribute",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads((out / "attribution.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["unmapped_tag_counts"] == {"mystery": 1, "p30POC": 1}
    assert payload["unmapped_tag_total"] == 2
    frame = pd.read_parquet(out / "journal_attribution.parquet")
    assert frame.iloc[0]["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "attribute",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "attribution.json").exists()


def test_write_helpers_are_keyword_only_on_files() -> None:
    params = inspect.signature(levels_mod.attribute_files).parameters
    for name in (
        "trades",
        "levels",
        "output_dir",
        "levels_settings",
        "level_tolerance_ticks",
        "tag_tolerance_ticks",
        "allow_unreconciled",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_tick_size_matches_journal_lock() -> None:
    assert JOURNAL_TICK_SIZE == 0.25
    frame = _levels([{"timestamp": "2026-05-14T14:00:00", "pdHigh": 100.25}])
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    out = attribute_journal_trades(trades, levels=frame)
    assert out.iloc[0]["nearest_level_distance_ticks"] == pytest.approx(-1.0)


def test_write_attribution_round_trip(tmp_path: Path) -> None:
    trades = attribute_journal_trades(
        _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("pdH",))),
        levels=_frame_14(),
    )
    paths = write_attribution_artifacts(tmp_path / "out", trades)
    assert paths["journal_attribution.parquet"].is_file()
    loaded = pd.read_parquet(paths["journal_attribution.parquet"])
    assert loaded.iloc[0]["nearest_level_token"] == "pdHigh"
