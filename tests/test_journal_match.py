"""TJ8 named-cell match + forward ledger — plan §3.0 / §3.8 / §5 TJ8."""

from __future__ import annotations

import inspect
import io
import json
from datetime import date
from pathlib import Path
import zipfile

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.journal import (
    build_forward_ledger,
    load_named_cell,
    match_journal_to_cell,
)
from thesistester.journal import match as match_mod
from thesistester.journal.schema import (
    DEFAULT_MATCH_TICKS,
    DEFAULT_MATCH_WINDOW_SECONDS,
    MATCH_DISCRETIONARY_ONLY,
    MATCH_EXECUTED_CELL,
    MATCH_NEAR_LEVEL,
    MATCH_PRODUCT_MISMATCH,
    MATCH_SYSTEMATIC_UNFILLED,
    MISMATCH_HOLD,
    MISMATCH_RISK,
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    JournalIngestError,
)
from thesistester.research_bundle import canonical_bundle_hash

UTC = "UTC"


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _journal(
    *,
    trade_id: str = "jt:t1:1",
    entry: str = "2026-05-14T14:00:03",
    price: float = 100.00,
    direction: str = "long",
    instrument: str = "MNQ",
    session: date = date(2026, 5, 14),
    hold_seconds: float = 24.0,
    journal_risk_ticks: float = 10.0,
    net_ticks: float | None = 2.0,
    recon: str | None = RECON_RECONCILED,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": instrument,
        "session_date": session,
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "direction": direction,
        "qty": 1,
        "hold_seconds": hold_seconds,
        "journal_risk_ticks": journal_risk_ticks,
        "net_ticks": net_ticks,
        "status": "closed",
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def _sys(
    *,
    trade_id: str = "sys:1",
    signal_id: str = "sig:1",
    entry: str = "2026-05-14T14:00:10",
    price: float = 100.00,
    theoretical: float = 100.00,
    direction: str = "long",
    sl: float = 10.0,
    bars_held: int = 1,
    zone_low: float = 99.75,
    zone_high: float = 100.25,
) -> dict[str, object]:
    return {
        "trade_id": trade_id,
        "signal_id": signal_id,
        "direction": direction,
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "theoretical_entry_price": theoretical,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_mid": (zone_low + zone_high) / 2,
        "stop_loss_ticks": sl,
        "bars_held": bars_held,
        "r_multiple": 0.2,
    }


def _signal(
    *,
    signal_id: str = "sig:open",
    stamp: str = "2026-05-14T15:00:00",
    direction: str = "long",
    price: float = 101.00,
) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "timestamp": _ts(stamp),
        "direction": direction,
        "entry_price": price,
        "theoretical_entry_price": price,
        "zone_low": price - 0.25,
        "zone_high": price + 0.25,
        "zone_mid": price,
    }


def _match(journal: list[dict[str, object]], systematic: list[dict[str, object]], **kwargs):
    defaults = {
        "cell_id": "cell_a",
        "instrument": "MNQ",
        "stop_loss_ticks": 10.0,
        "bar_seconds": 60.0,
    }
    defaults.update(kwargs)
    return match_journal_to_cell(
        pd.DataFrame(journal),
        systematic_trades=pd.DataFrame(systematic),
        **defaults,
    )


def _write_bundle(
    path: Path,
    *,
    trades: pd.DataFrame,
    signals: pd.DataFrame | None = None,
    instrument: str = "MNQ",
    sl: float = 10.0,
    expectancy_r: float = 0.2,
    interval: str = "1min",
) -> str:
    trade_buf = io.BytesIO()
    trades.to_parquet(trade_buf, index=False)
    parts: dict[str, bytes] = {
        "trades.parquet": trade_buf.getvalue(),
        "trade_summary.json": json.dumps(
            {"expectancy_r": expectancy_r, "stop_loss_ticks": sl}
        ).encode("utf-8"),
        "dataset_meta.json": json.dumps(
            {"instrument": instrument, "base_interval": interval}
        ).encode("utf-8"),
    }
    if signals is not None:
        sig_buf = io.BytesIO()
        signals.to_parquet(sig_buf, index=False)
        parts["signals.parquet"] = sig_buf.getvalue()
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return canonical_bundle_hash(path.read_bytes())


def test_match_kwargs_are_keyword_only() -> None:
    params = inspect.signature(match_journal_to_cell).parameters
    for name in (
        "systematic_trades",
        "cell_id",
        "instrument",
        "stop_loss_ticks",
        "bar_seconds",
        "systematic_signals",
        "match_window_seconds",
        "match_ticks",
        "allow_unreconciled",
        "tick_size",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["match_window_seconds"].default == DEFAULT_MATCH_WINDOW_SECONDS
    assert params["match_ticks"].default == DEFAULT_MATCH_TICKS


def test_journal_match_does_not_import_engine_or_index_keys() -> None:
    assert "simulate_trades" not in match_mod.__dict__
    assert "compute_all_levels" not in match_mod.__dict__
    assert "STUDY_INDEX_KEYS" not in match_mod.__dict__
    assert "R18_INDEX_METRIC_KEYS" not in match_mod.__dict__
    source = Path(match_mod.__file__).read_text(encoding="utf-8")
    assert "from thesistester.engine" not in source
    assert "import thesistester.engine" not in source
    assert "from thesistester.study.execute" not in source
    assert "import thesistester.study.execute" not in source


def test_executed_cell_requires_hold_and_risk() -> None:
    out = _match([_journal()], [_sys()])
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_EXECUTED_CELL
    assert journal["product_mismatch_dimension"] is None
    assert journal["counterpart_id"] == "sys:1"


def test_product_mismatch_names_hold() -> None:
    out = _match([_journal(hold_seconds=180.0)], [_sys(bars_held=1)])
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_PRODUCT_MISMATCH
    assert journal["product_mismatch_dimension"] == MISMATCH_HOLD


def test_product_mismatch_names_risk() -> None:
    out = _match([_journal(journal_risk_ticks=10.0)], [_sys(sl=80.0)], stop_loss_ticks=80.0)
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_PRODUCT_MISMATCH
    assert journal["product_mismatch_dimension"] == MISMATCH_RISK


def test_product_mismatch_names_hold_and_risk() -> None:
    out = _match(
        [_journal(hold_seconds=180.0, journal_risk_ticks=10.0)],
        [_sys(sl=80.0, bars_held=1)],
        stop_loss_ticks=80.0,
    )
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_PRODUCT_MISMATCH
    assert journal["product_mismatch_dimension"] == f"{MISMATCH_HOLD},{MISMATCH_RISK}"


def test_near_level_when_price_matches_but_time_does_not() -> None:
    out = _match(
        [_journal(entry="2026-05-14T16:00:03")],
        [_sys(entry="2026-05-14T14:00:10")],
    )
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_NEAR_LEVEL


def test_discretionary_only_when_no_level_or_time() -> None:
    out = _match(
        [_journal(entry="2026-05-14T16:00:03", price=120.00)],
        [_sys()],
    )
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_DISCRETIONARY_ONLY


def test_systematic_unfilled_leftover_signal() -> None:
    out = match_journal_to_cell(
        pd.DataFrame([_journal()]),
        systematic_trades=pd.DataFrame([_sys()]),
        systematic_signals=pd.DataFrame(
            [_signal(), _signal(signal_id="sig:1", stamp="2026-05-14T14:00:10")]
        ),
        cell_id="cell_a",
        instrument="MNQ",
        stop_loss_ticks=10.0,
    )
    unfilled = out.loc[out["match_class"] == MATCH_SYSTEMATIC_UNFILLED]
    assert set(unfilled["signal_id"]) == {"sig:open"}
    assert MATCH_EXECUTED_CELL in set(out["match_class"])


def test_wrong_direction_is_not_executed() -> None:
    out = _match([_journal(direction="long")], [_sys(direction="short")])
    journal = out.loc[out["side"] == "journal"].iloc[0]
    assert journal["match_class"] == MATCH_DISCRETIONARY_ONLY


def test_refuses_unreconciled_days() -> None:
    with pytest.raises(JournalIngestError, match="not reconciled"):
        _match([_journal(recon=RECON_AMP_MISSING)], [_sys()])
    out = _match([_journal(recon=RECON_AMP_MISSING)], [_sys()], allow_unreconciled=True)
    assert MATCH_EXECUTED_CELL in set(out["match_class"])


def test_positional_args_rejected() -> None:
    with pytest.raises(TypeError):
        match_journal_to_cell(pd.DataFrame([_journal()]), pd.DataFrame([_sys()]))  # type: ignore[misc]


def test_hash_verified_bundle_and_mismatch(tmp_path: Path) -> None:
    bundle = tmp_path / "cell.research.zip"
    digest = _write_bundle(bundle, trades=pd.DataFrame([_sys()]))
    cell = load_named_cell(bundle=bundle, expected_hash=digest)
    assert cell.bundle_hash == digest
    assert cell.instrument == "MNQ"
    assert cell.stop_loss_ticks == 10.0
    assert cell.bar_seconds == 60.0
    with pytest.raises(JournalIngestError, match="hash mismatch"):
        load_named_cell(bundle=bundle, expected_hash="0" * 64)


def test_refuses_corpus_index(tmp_path: Path) -> None:
    index = tmp_path / "results_index.csv"
    index.write_text("run_name,bundle_path\n", encoding="utf-8")
    with pytest.raises(JournalIngestError, match="named cell"):
        load_named_cell(bundle=index)


def test_forward_ledger_adherence_and_live_since() -> None:
    matched = _match(
        [
            _journal(trade_id="jt:a:1", net_ticks=4.0),
            _journal(
                trade_id="jt:b:1",
                entry="2026-05-15T14:00:03",
                session=date(2026, 5, 15),
                net_ticks=6.0,
            ),
        ],
        [
            _sys(trade_id="sys:1", signal_id="sig:1"),
            _sys(trade_id="sys:2", signal_id="sig:2", entry="2026-05-14T15:00:00"),
            _sys(trade_id="sys:3", signal_id="sig:3", entry="2026-05-15T14:00:10"),
        ],
        systematic_signals=pd.DataFrame(
            [
                _signal(signal_id="sig:1", stamp="2026-05-14T14:00:10"),
                _signal(signal_id="sig:2", stamp="2026-05-14T15:00:00"),
                _signal(signal_id="sig:3", stamp="2026-05-15T14:00:10", price=100.00),
            ]
        ),
    )
    all_days = build_forward_ledger(matched, live_since=None, cell_expectancy_ticks=2.0)
    assert [row["session_date"] for row in all_days] == ["2026-05-14", "2026-05-15"]
    first = all_days[0]
    assert first["executed_cell"] == 1
    assert first["systematic_unfilled"] == 1
    assert first["adherence"] == pytest.approx(0.5)
    assert first["live_net_ticks"] == pytest.approx(4.0)
    assert first["cell_expectancy_ticks"] == pytest.approx(2.0)
    forward = build_forward_ledger(matched, live_since=date(2026, 5, 15), cell_expectancy_ticks=2.0)
    assert [row["session_date"] for row in forward] == ["2026-05-15"]
    assert forward[0]["cumulative_n"] == 1


def test_ledger_does_not_write_promotion_registry(tmp_path: Path) -> None:
    bundle = tmp_path / "cell.research.zip"
    digest = _write_bundle(
        bundle,
        trades=pd.DataFrame([_sys()]),
        signals=pd.DataFrame([_signal(signal_id="sig:1", stamp="2026-05-14T14:00:10")]),
    )
    registry = tmp_path / "promotion.yaml"
    registry.write_text(
        yaml.safe_dump({"cells": [{"run_name": "cell", "live_since": "2026-05-14"}]}),
        encoding="utf-8",
    )
    before = registry.read_bytes()
    mtime = registry.stat().st_mtime_ns
    trades_path = tmp_path / "journal_trades.parquet"
    raw = pd.DataFrame([_journal()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "match",
            "--trades",
            str(trades_path),
            "--bundle",
            str(bundle),
            "--bundle-hash",
            digest,
            "--live-declarations",
            str(registry),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    assert registry.read_bytes() == before
    assert registry.stat().st_mtime_ns == mtime
    payload = json.loads((out / "match.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["cell"]["bundle_hash"] == digest
    assert "named-cell" in payload["honesty"]
    frame = pd.read_parquet(out / "journal_matches.parquet")
    assert MATCH_EXECUTED_CELL in set(frame["match_class"])


def test_cli_refuses_studies_output_dir(tmp_path: Path) -> None:
    bundle = tmp_path / "cell.research.zip"
    _write_bundle(bundle, trades=pd.DataFrame([_sys()]))
    trades_path = tmp_path / "journal_trades.parquet"
    raw = pd.DataFrame([_journal()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    forbidden = tmp_path / "results" / "studies" / "oops"
    code = cli_main(
        [
            "journal",
            "match",
            "--trades",
            str(trades_path),
            "--bundle",
            str(bundle),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code == 2
    assert not (forbidden / "match.json").exists()
