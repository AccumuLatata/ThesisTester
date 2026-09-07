"""JS1 zone attribution — plan §3.0 / §3.1 / §5 JS1."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.journal import (
    ZONES_HONESTY,
    attribute_journal_zones,
    build_journal_report,
    canonical_zone_params_hash,
    previous_completed_1m_open,
    zone_files,
)
from thesistester.journal import levels as levels_mod
from thesistester.journal import zones as zones_mod
from thesistester.journal.schema import (
    JOURNAL_TICK_SIZE,
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    ZONE_COUNT_1,
    ZONE_REL_ABOVE,
    ZONE_REL_BELOW,
    ZONE_REL_INSIDE,
    ZONE_REL_NONE,
    JournalIngestError,
)

UTC = "UTC"


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _trade(
    *,
    entry: str,
    price: float,
    recon: str | None = RECON_RECONCILED,
    trade_id: str = "jt:t1:1",
    net_ticks: float = 1.0,
    resolution: str = "15s",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": date(2026, 5, 14),
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "direction": "long",
        "qty": 1,
        "status": "closed",
        "net_ticks": net_ticks,
        "resolution": resolution,
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


def _params(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "level_columns": ["pdHigh", "pdVAL"],
        "tolerance_ticks": 2,
        "min_confluences": 2,
        "max_confluences": 5,
    }
    payload.update(overrides)
    return payload


def _frame_three() -> pd.DataFrame:
    """09:28 / 09:29 / 09:30 with distinct tokens. 09:29 is 1 tick apart."""
    return _levels(
        [
            {
                "timestamp": "2026-05-14T09:28:00",
                "pdHigh": 80.00,
                "pdVAL": 70.00,
                "pdLow": 60.00,
            },
            {
                "timestamp": "2026-05-14T09:29:00",
                "pdHigh": 100.25,
                "pdVAL": 100.00,
                "pdLow": 90.00,
            },
            {
                "timestamp": "2026-05-14T09:30:00",
                "pdHigh": 200.00,
                "pdVAL": 190.00,
                "pdLow": 180.00,
            },
        ]
    )


def _write_params(path: Path, params: dict[str, object]) -> Path:
    path.write_text(
        "\n".join(
            [
                f"level_columns: {params['level_columns']}",
                f"tolerance_ticks: {params['tolerance_ticks']}",
                f"min_confluences: {params['min_confluences']}",
                f"max_confluences: {params['max_confluences']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_attribute_journal_zones_is_keyword_only() -> None:
    params = inspect.signature(attribute_journal_zones).parameters
    assert params["trades"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ("levels", "zone_params", "bars", "allow_unreconciled", "tick_size"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_zones_module_does_not_call_engine_mutators() -> None:
    source = Path("thesistester/journal/zones.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "thesistester.engine.confluence" in imported
    assert "detect_confluence_zones" in source
    assert "compute_all_levels(" not in source
    assert "simulate_trades(" not in source
    assert "generate_signals(" not in source
    assert "_expected_previous_open(" not in source
    assert "while j <" not in source


def test_exact_minute_fill_uses_previous_open_not_tj6_helper() -> None:
    entry = _ts("2026-05-14T09:30:00")
    assert previous_completed_1m_open(entry) == _ts("2026-05-14T09:29:00")
    tj6 = levels_mod._expected_previous_open(entry)
    assert tj6 == _ts("2026-05-14T09:28:00")
    assert previous_completed_1m_open(entry) != tj6


def test_hand_built_zone_relations() -> None:
    frame = _frame_three()
    params = _params()
    trades = _trades(
        _trade(entry="2026-05-14T09:30:00", price=100.10, trade_id="inside"),
        _trade(entry="2026-05-14T09:30:15", price=100.50, trade_id="above"),
        _trade(entry="2026-05-14T09:30:20", price=110.00, trade_id="none"),
    )
    out = attribute_journal_zones(trades, levels=frame, zone_params=params)
    by_id = out.set_index("trade_id")
    assert by_id.loc["inside", "entry_zone_relation"] == ZONE_REL_INSIDE
    assert by_id.loc["inside", "zone_level_count"] == 2
    assert by_id.loc["inside", "zone_width_ticks"] == pytest.approx(1.0)
    assert by_id.loc["inside", "zone_level_names"] == "pdVAL|pdHigh"
    assert by_id.loc["above", "entry_zone_relation"] == ZONE_REL_ABOVE
    assert by_id.loc["none", "entry_zone_relation"] == ZONE_REL_NONE
    assert by_id.loc["none", "zone_id"] is None or pd.isna(by_id.loc["none", "zone_id"])
    assert by_id.loc["none", "nearest_zone_distance_ticks"] == pytest.approx(
        (110.00 - 100.125) / JOURNAL_TICK_SIZE
    )
    assert by_id.loc["inside", "entry_offset_ticks"] == pytest.approx(
        (100.10 - 100.125) / JOURNAL_TICK_SIZE
    )
    assert (
        pd.isna(by_id.loc["none", "entry_offset_ticks"])
        or by_id.loc["none", "entry_offset_ticks"] is None
    )
    # Containing 09:30 prices (200/190) must not be used.
    assert by_id.loc["inside", "zone_high"] == pytest.approx(100.25)
    # TJ6 helper would have read 09:28 (80/70) — must not.
    assert by_id.loc["inside", "zone_low"] == pytest.approx(100.00)


def test_one_row_call_matches_full_session_slice() -> None:
    frame = _frame_three()
    params = _params()
    columns = list(params["level_columns"])
    full = detect_confluence_zones(frame, columns, JOURNAL_TICK_SIZE, 2, 2, 5)
    row = frame.loc[frame["timestamp"] == _ts("2026-05-14T09:29:00")]
    one = detect_confluence_zones(row, columns, JOURNAL_TICK_SIZE, 2, 2, 5)
    full_slice = full.loc[full["timestamp"] == _ts("2026-05-14T09:29:00")].reset_index(drop=True)
    one = one.reset_index(drop=True)
    for column in ("zone_low", "zone_high", "zone_mid", "level_count", "level_names"):
        pd.testing.assert_series_equal(full_slice[column], one[column], check_names=False)
    attributed = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=100.10)),
        levels=frame,
        zone_params=params,
    )
    assert attributed.iloc[0]["zone_low"] == pytest.approx(float(one.iloc[0]["zone_low"]))
    assert attributed.iloc[0]["zone_high"] == pytest.approx(float(one.iloc[0]["zone_high"]))


def test_gap_is_no_zone_not_stale_walkback() -> None:
    frame = _levels(
        [
            {
                "timestamp": "2026-05-14T09:27:00",
                "pdHigh": 100.25,
                "pdVAL": 100.00,
            },
            {
                "timestamp": "2026-05-14T09:30:00",
                "pdHigh": 110.25,
                "pdVAL": 110.00,
            },
        ]
    )
    out = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=100.10)),
        levels=frame,
        zone_params=_params(),
    )
    assert out.iloc[0]["entry_zone_relation"] == ZONE_REL_NONE
    assert out.iloc[0]["zone_id"] is None or pd.isna(out.iloc[0]["zone_id"])


def test_containing_minute_is_never_used() -> None:
    frame = _frame_three()
    out = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:30", price=195.00)),
        levels=frame,
        zone_params=_params(),
    )
    # 195 is inside the 09:30 200/190 cluster, outside the 09:29 100.25/100 cluster.
    assert out.iloc[0]["entry_zone_relation"] == ZONE_REL_NONE
    assert out.iloc[0]["zone_low"] == pytest.approx(100.00)


def test_future_shock_does_not_change_zone_columns() -> None:
    frame = _frame_three()
    trades = _trades(_trade(entry="2026-05-14T09:30:00", price=100.10))
    first = attribute_journal_zones(trades, levels=frame, zone_params=_params())
    future = pd.concat(
        [
            frame,
            _levels(
                [
                    {
                        "timestamp": "2026-05-14T09:31:00",
                        "pdHigh": 50.25,
                        "pdVAL": 50.00,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    second = attribute_journal_zones(trades, levels=future, zone_params=_params())
    zone_cols = [
        "zone_params_hash",
        "zone_id",
        "zone_low",
        "zone_high",
        "zone_mid",
        "zone_width_ticks",
        "zone_level_count",
        "zone_level_names",
        "entry_zone_relation",
        "entry_offset_ticks",
        "nearest_zone_distance_ticks",
    ]
    pd.testing.assert_frame_equal(first[zone_cols], second[zone_cols], check_dtype=False)


def test_two_param_hashes_are_not_averaged() -> None:
    frame = _frame_three()
    tight = _params(tolerance_ticks=2)
    wide = _params(tolerance_ticks=10)
    trades = _trades(
        *[
            _trade(entry="2026-05-14T09:30:00", price=100.10, trade_id=f"t{index}")
            for index in range(30)
        ]
    )
    a = attribute_journal_zones(trades, levels=frame, zone_params=tight)
    b = attribute_journal_zones(trades, levels=frame, zone_params=wide)
    assert a.iloc[0]["zone_params_hash"] != b.iloc[0]["zone_params_hash"]
    combined = pd.concat([a, b], ignore_index=True)
    report = build_journal_report(trades, zones=combined, include_small_n=True)
    hashes = set(report.q3_zones_relation["zone_params_hash"])
    assert hashes == {a.iloc[0]["zone_params_hash"], b.iloc[0]["zone_params_hash"]}
    assert canonical_zone_params_hash(tight) == a.iloc[0]["zone_params_hash"]


def test_q3_zones_hides_n_below_30_unless_toggled() -> None:
    frame = _frame_three()
    trades = _trades(
        *[
            _trade(entry="2026-05-14T09:30:00", price=100.10, trade_id=f"t{index}")
            for index in range(12)
        ]
    )
    zones = attribute_journal_zones(trades, levels=frame, zone_params=_params())
    hidden = build_journal_report(trades, zones=zones, include_small_n=False)
    assert hidden.q3_zones_relation.empty
    shown = build_journal_report(trades, zones=zones, include_small_n=True)
    assert not shown.q3_zones_relation.empty
    assert shown.captions["q3_zones"] == ZONES_HONESTY
    assert "zone_params_hash" in shown.q3_zones_relation.columns


def test_approach_side_from_two_completed_15s_bars() -> None:
    frame = _frame_three()
    bars = pd.DataFrame(
        {
            "timestamp": [
                _ts("2026-05-14T09:29:30"),
                _ts("2026-05-14T09:29:45"),
                _ts("2026-05-14T09:30:00"),
            ],
            "close": [101.00, 100.50, 100.20],
        }
    )
    out = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=100.10)),
        levels=frame,
        zone_params=_params(),
        bars=bars,
    )
    assert out.iloc[0]["approach_side"] == "from_above"
    missing = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=100.10)),
        levels=frame,
        zone_params=_params(),
    )
    assert missing.iloc[0]["approach_side"] == "unknown"


def test_unreconciled_refused_unless_overridden() -> None:
    frame = _frame_three()
    trades = _trades(_trade(entry="2026-05-14T09:30:00", price=100.10, recon=RECON_AMP_MISSING))
    with pytest.raises(JournalIngestError, match="not reconciled"):
        attribute_journal_zones(trades, levels=frame, zone_params=_params())
    out = attribute_journal_zones(
        trades, levels=frame, zone_params=_params(), allow_unreconciled=True
    )
    assert out.iloc[0]["entry_zone_relation"] == ZONE_REL_INSIDE


def test_positional_levels_argument_is_rejected() -> None:
    with pytest.raises(TypeError):
        attribute_journal_zones(
            _trades(_trade(entry="2026-05-14T09:30:00", price=100.10)), _frame_three()
        )  # type: ignore[misc]


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    trades_path = tmp_path / "journal_trades.parquet"
    levels_path = tmp_path / "levels.parquet"
    params_path = _write_params(tmp_path / "zone_params.yaml", _params())
    raw = _trades(_trade(entry="2026-05-14T09:30:00", price=100.10))
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    _frame_three().to_parquet(levels_path, index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "zones",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--zone-params",
            str(params_path),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads((out / "zones.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["zone_params"]["tolerance_ticks"] == 2
    assert payload["trade_count"] == 1
    frame = pd.read_parquet(out / "journal_zones.parquet")
    assert frame.iloc[0]["entry_zone_relation"] == ZONE_REL_INSIDE
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "zones",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--zone-params",
            str(params_path),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "zones.json").exists()


def test_zone_files_is_keyword_only() -> None:
    params = inspect.signature(zone_files).parameters
    for name in ("trades", "levels", "zone_params", "output_dir", "bars", "allow_unreconciled"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_params_file_requires_level_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tolerance_ticks: 2\n", encoding="utf-8")
    with pytest.raises(JournalIngestError, match="level_columns"):
        zones_mod.load_zone_params(path)


def test_containing_zone_wins_over_closer_foreign_mid() -> None:
    """A fill inside 100–101 must not be stolen by a tighter 101.1 cluster."""
    frame = _levels(
        [
            {
                "timestamp": "2026-05-14T09:29:00",
                "L1": 100.00,
                "L2": 101.00,
                "L3": 101.10,
                "L4": 101.10,
            }
        ]
    )
    params = _params(
        level_columns=["L1", "L2", "L3", "L4"],
        tolerance_ticks=4,
    )
    out = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=101.00)),
        levels=frame,
        zone_params=params,
    )
    row = out.iloc[0]
    assert row["entry_zone_relation"] == ZONE_REL_INSIDE
    assert row["zone_low"] == pytest.approx(100.00)
    assert row["zone_high"] == pytest.approx(101.00)
    assert row["zone_level_names"] == "L1|L2"
    assert row["zone_id"] is not None and not pd.isna(row["zone_id"])


def test_nearest_zone_distance_is_absolute() -> None:
    frame = _frame_three()
    below = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=90.00, trade_id="below")),
        levels=frame,
        zone_params=_params(),
    )
    assert below.iloc[0]["entry_zone_relation"] == ZONE_REL_NONE
    assert below.iloc[0]["nearest_zone_distance_ticks"] == pytest.approx(
        abs(90.00 - 100.125) / JOURNAL_TICK_SIZE
    )
    assert below.iloc[0]["nearest_zone_distance_ticks"] > 0
    above = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=110.00, trade_id="above")),
        levels=frame,
        zone_params=_params(),
    )
    assert above.iloc[0]["nearest_zone_distance_ticks"] == pytest.approx(
        abs(110.00 - 100.125) / JOURNAL_TICK_SIZE
    )


def test_one_level_zone_appears_in_count_cut() -> None:
    frame = _levels([{"timestamp": "2026-05-14T09:29:00", "pdHigh": 100.00}])
    params = _params(level_columns=["pdHigh"], min_confluences=1)
    trades = _trades(
        *[
            _trade(entry="2026-05-14T09:30:00", price=100.00, trade_id=f"t{index}")
            for index in range(30)
        ]
    )
    zones = attribute_journal_zones(trades, levels=frame, zone_params=params)
    assert set(zones["zone_level_count"]) == {1}
    report = build_journal_report(trades, zones=zones, include_small_n=False)
    assert list(report.q3_zones_count["zone_level_count"]) == [ZONE_COUNT_1]
    assert int(report.q3_zones_count.iloc[0]["n"]) == 30


def test_missing_entry_timestamp_is_refused() -> None:
    frame = _frame_three()
    trades = _trades(_trade(entry="2026-05-14T09:30:00", price=100.10))
    trades.loc[0, "entry_timestamp"] = pd.NaT
    with pytest.raises(JournalIngestError, match="entry_timestamp"):
        attribute_journal_zones(trades, levels=frame, zone_params=_params())


def test_below_within_tol_uses_same_tolerance() -> None:
    frame = _frame_three()
    out = attribute_journal_zones(
        _trades(_trade(entry="2026-05-14T09:30:00", price=99.75)),
        levels=frame,
        zone_params=_params(),
    )
    assert out.iloc[0]["entry_zone_relation"] == ZONE_REL_BELOW
    assert out.iloc[0]["zone_id"] is not None and not pd.isna(out.iloc[0]["zone_id"])
    assert pd.isna(out.iloc[0]["nearest_zone_distance_ticks"]) or (
        out.iloc[0]["nearest_zone_distance_ticks"] is None
    )
