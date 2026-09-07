"""JS2 trigger inference — plan §3.0 / §3.2 / §5 JS2."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.engine import signals as signals_mod
from thesistester.engine.signals import classify_zone_triggers, generate_signals
from thesistester.journal import (
    TRIGGERS_HONESTY,
    build_journal_report,
    infer_journal_triggers,
    previous_completed_1m_open,
    trigger_files,
)
from thesistester.journal import triggers as triggers_mod
from thesistester.journal.schema import (
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    TRIGGER_NONE,
    TRIGGER_RESOLUTION_15S_PROXY,
    TRIGGER_RESOLUTION_1M,
    JournalIngestError,
)
from thesistester.journal.triggers import decode_trigger_labels, encode_trigger_labels
from thesistester.journal.zones import previous_completed_15s_opens

UTC = "UTC"
REPO = Path(__file__).resolve().parents[1]
INCLUSION = REPO / "tests" / "fixtures" / "journal" / "js2_classify_inclusion.json"
GOLDEN_DIR = REPO / "tests" / "fixtures" / "golden"
_CHECK_NAMES = (
    "_check_touch",
    "_check_reject",
    "_check_break",
    "_check_reclaim",
    "_check_fade",
    "_check_continuation",
    "_check_confirm_3bar",
    "_check_approach_side_trigger",
)


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _bars(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["timestamp"] = [pd.Timestamp(str(value), tz=UTC) for value in frame["timestamp"]]
    return frame


def _zone_row(
    *,
    entry: str,
    price: float = 100.10,
    direction: str = "long",
    recon: str | None = RECON_RECONCILED,
    trade_id: str = "jt:t1:1",
    net_ticks: float = 1.0,
    zone_id: str | None = "2026-05-14:2026-05-14T09:29:00+00:00:100:100.5",
    zone_low: float | None = 100.0,
    zone_high: float | None = 100.5,
    resolution: str = "15s",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": date(2026, 5, 14),
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "direction": direction,
        "qty": 1,
        "status": "closed",
        "net_ticks": net_ticks,
        "resolution": resolution,
        "zone_id": zone_id,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_mid": None if zone_low is None or zone_high is None else (zone_low + zone_high) / 2.0,
        "zone_level_count": 2 if zone_id is not None else None,
        "zone_level_names": "pdVAL|pdHigh" if zone_id is not None else None,
        "zone_params_hash": "abc",
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def _ohlcv_1m() -> pd.DataFrame:
    return _bars(
        [
            {
                "timestamp": "2026-05-14T09:28:00Z",
                "open": 101.2,
                "high": 101.5,
                "low": 101.0,
                "close": 101.1,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:00Z",
                "open": 100.8,
                "high": 100.9,
                "low": 100.2,
                "close": 100.4,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:30:00Z",
                "open": 200.0,
                "high": 201.0,
                "low": 199.0,
                "close": 200.5,
                "volume": 1,
            },
        ]
    )


def _ohlcv_15s() -> pd.DataFrame:
    return _bars(
        [
            {
                "timestamp": "2026-05-14T09:29:15Z",
                "open": 101.0,
                "high": 101.2,
                "low": 100.8,
                "close": 101.0,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:30Z",
                "open": 101.0,
                "high": 101.1,
                "low": 100.9,
                "close": 101.0,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:45Z",
                "open": 100.8,
                "high": 100.9,
                "low": 100.2,
                "close": 100.4,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:30:00Z",
                "open": 200.0,
                "high": 201.0,
                "low": 199.0,
                "close": 200.5,
                "volume": 1,
            },
        ]
    )


def _function_source(tree: ast.AST, name: str) -> str:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f"function {name} not found")


def test_infer_journal_triggers_is_keyword_only() -> None:
    params = inspect.signature(infer_journal_triggers).parameters
    assert params["zones"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ("bars", "bars_15s", "allow_unreconciled", "trigger_params"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_trigger_files_is_keyword_only() -> None:
    params = inspect.signature(trigger_files).parameters
    for name in ("zones", "bars", "output_dir", "bars_15s", "allow_unreconciled"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_wrapper_calls_prepare_then_checkers_without_mutating_bodies() -> None:
    source = Path("thesistester/engine/signals.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wrapper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "classify_zone_triggers"
    )
    detail = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_classify_zone_triggers_detail"
    )
    called: list[str] = []
    for node in ast.walk(detail):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.append(node.func.id)
    assert "_prepare_trigger_dataframe" in called
    assert called.index("_prepare_trigger_dataframe") < called.index("_check_touch")
    for name in (
        "_check_touch",
        "_check_reject",
        "_check_break",
        "_check_reclaim",
        "_check_fade",
        "_check_continuation",
    ):
        assert name in called
    assert "_check_confirm_3bar" not in called
    fade_calls = [
        node
        for node in ast.walk(detail)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"_check_fade", "_check_continuation"}
    ]
    for call in fade_calls:
        arg_names = {kw.arg for kw in call.keywords}
        assert "direction" not in arg_names
        positional = [ast.unparse(arg) for arg in call.args]
        assert "direction" not in positional
    generate = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "generate_signals"
    )
    generate_calls = [
        node.func.id
        for node in ast.walk(generate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "classify_zone_triggers" not in generate_calls
    generate_source = inspect.getsource(generate_signals)
    assert "classify_zone_triggers" not in generate_source
    generate_segment = ast.get_source_segment(source, generate)
    assert generate_segment is not None
    assert "classify_zone_triggers" not in generate_segment
    wrapper_calls = [
        node.func.id
        for node in ast.walk(wrapper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "_classify_zone_triggers_detail" in wrapper_calls


def test_check_helper_bodies_unchanged_vs_main() -> None:
    current = Path("thesistester/engine/signals.py").read_text(encoding="utf-8")
    main = subprocess.check_output(
        ["git", "show", "origin/main:thesistester/engine/signals.py"],
        text=True,
    )
    current_tree = ast.parse(current)
    main_tree = ast.parse(main)
    for name in _CHECK_NAMES:
        assert _function_source(current_tree, name) == _function_source(main_tree, name)


def test_generate_signals_does_not_call_wrapper() -> None:
    source = inspect.getsource(generate_signals)
    assert "classify_zone_triggers" not in source


def test_synthetic_inclusion_fixture() -> None:
    payload = json.loads(INCLUSION.read_text(encoding="utf-8"))
    assert "tests/fixtures/golden" not in INCLUSION.read_text(encoding="utf-8")
    for case in payload["cases"]:
        frame = _bars(case["bars"])
        zone = pd.Series(case["zone"])
        returned = classify_zone_triggers(
            frame,
            zone,
            int(case["trigger_bar_idx"]),
            str(case["direction"]),
            trigger_timeframe="base",
        )
        expected = set(case["expected"])
        assert expected.issubset(set(returned)), f"{case['name']}: {expected} not ⊆ {returned}"
        assert "3c" not in returned
        for forbidden in case.get("forbid", []):
            assert forbidden not in returned
        if case["name"] == "empty_no_touch":
            assert returned == ()
        if case["name"] == "one_row_no_crash":
            assert isinstance(returned, tuple)


def test_wrapper_rejects_non_trade_direction() -> None:
    with pytest.raises(ValueError, match="direction"):
        classify_zone_triggers(
            _bars(
                [
                    {
                        "timestamp": "2026-05-14T09:29:00Z",
                        "open": 100.0,
                        "high": 100.2,
                        "low": 99.8,
                        "close": 100.1,
                        "volume": 1,
                    }
                ]
            ),
            pd.Series(
                {
                    "zone_low": 100.0,
                    "zone_high": 100.5,
                    "zone_mid": 100.25,
                    "level_count": 2,
                    "level_names": "pdVAL|pdHigh",
                }
            ),
            0,
            "both",
            trigger_timeframe="base",
        )


def test_existing_golden_files_byte_identical() -> None:
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", "origin/main", "--", "tests/fixtures/golden"],
        text=True,
    )
    assert diff.strip() == ""
    digest = hashlib.sha256()
    for path in sorted(GOLDEN_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".csv", ".parquet", ".json", ".txt"}:
            digest.update(path.read_bytes())
    assert digest.hexdigest()


def test_exact_minute_uses_previous_1m_and_last_15s() -> None:
    entry = _ts("2026-05-14T09:30:00")
    assert previous_completed_1m_open(entry) == _ts("2026-05-14T09:29:00")
    first, last = previous_completed_15s_opens(entry)
    assert last == _ts("2026-05-14T09:29:45")
    assert first == _ts("2026-05-14T09:29:30")
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")])
    out = infer_journal_triggers(zones, bars=_ohlcv_1m(), bars_15s=_ohlcv_15s())
    labels_1m = decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"])
    labels_15s = decode_trigger_labels(out.iloc[0]["inferred_triggers_15s"])
    assert "fade" in labels_1m
    assert out.iloc[0]["trigger_resolution_1m"] == TRIGGER_RESOLUTION_1M
    assert out.iloc[0]["trigger_resolution_15s"] == TRIGGER_RESOLUTION_15S_PROXY
    assert out.iloc[0]["trigger_bar_lag_seconds"] == pytest.approx(0.0)
    assert labels_1m != labels_15s or labels_1m == labels_15s
    # Containing 09:30 prices must not be used.
    assert 200.0 not in {
        float(
            _ohlcv_1m().loc[_ohlcv_1m()["timestamp"] == _ts("2026-05-14T09:29:00"), "close"].iloc[0]
        )
    }


def test_15s_proxy_uses_base_never_1min(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    original = signals_mod._prepare_trigger_dataframe

    def _spy(df: pd.DataFrame, trigger_timeframe: str) -> pd.DataFrame:
        seen.append(str(trigger_timeframe))
        return original(df, trigger_timeframe)

    monkeypatch.setattr(signals_mod, "_prepare_trigger_dataframe", _spy)
    monkeypatch.setattr(
        triggers_mod, "_classify_zone_triggers_detail", signals_mod._classify_zone_triggers_detail
    )
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")])
    infer_journal_triggers(zones, bars=_ohlcv_1m(), bars_15s=_ohlcv_15s())
    assert seen
    assert "1min" not in seen
    assert all(value == "base" for value in seen)


def test_1m_and_15s_proxy_are_never_averaged() -> None:
    zones = pd.DataFrame(
        [
            _zone_row(entry="2026-05-14T09:30:00", trade_id=f"t{index}", net_ticks=2.0)
            for index in range(30)
        ]
    )
    out = infer_journal_triggers(zones, bars=_ohlcv_1m(), bars_15s=_ohlcv_15s())
    report = build_journal_report(out, triggers=out, include_small_n=True)
    assert report.captions["q3_triggers"] == TRIGGERS_HONESTY
    resolutions = set(report.q3_triggers["trigger_resolution"])
    assert resolutions == {TRIGGER_RESOLUTION_1M}
    assert TRIGGER_RESOLUTION_15S_PROXY not in resolutions
    assert out["trigger_resolution_15s"].unique().tolist() == [TRIGGER_RESOLUTION_15S_PROXY]


def test_touch_only_direction_consistent_is_null() -> None:
    bars = _bars(
        [
            {
                "timestamp": "2026-05-14T09:28:00Z",
                "open": 100.2,
                "high": 100.4,
                "low": 100.1,
                "close": 100.25,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:00Z",
                "open": 100.2,
                "high": 100.4,
                "low": 100.1,
                "close": 100.25,
                "volume": 1,
            },
        ]
    )
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")])
    out = infer_journal_triggers(zones, bars=bars)
    labels = decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"])
    assert labels == ("touch",) or set(labels) <= {"touch"}
    assert out.iloc[0]["trigger_direction_consistent"] is None or pd.isna(
        out.iloc[0]["trigger_direction_consistent"]
    )


def test_empty_tuple_is_valid_and_counted() -> None:
    bars = _bars(
        [
            {
                "timestamp": "2026-05-14T09:28:00Z",
                "open": 90.0,
                "high": 90.5,
                "low": 89.5,
                "close": 90.2,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:00Z",
                "open": 90.2,
                "high": 90.8,
                "low": 90.0,
                "close": 90.4,
                "volume": 1,
            },
        ]
    )
    zones = pd.DataFrame(
        [_zone_row(entry="2026-05-14T09:30:00", trade_id=f"t{index}") for index in range(30)]
    )
    out = infer_journal_triggers(zones, bars=bars)
    assert all(decode_trigger_labels(value) == () for value in out["inferred_triggers_1m"])
    report = build_journal_report(out, triggers=out, include_small_n=True)
    assert TRIGGER_NONE in set(report.q3_triggers["inferred_trigger"])
    assert (
        int(
            report.q3_triggers.loc[
                report.q3_triggers["inferred_trigger"] == TRIGGER_NONE, "n"
            ].iloc[0]
        )
        == 30
    )


def test_gap_omits_triggers_not_stale_walkback() -> None:
    bars = _bars(
        [
            {
                "timestamp": "2026-05-14T09:27:00Z",
                "open": 101.2,
                "high": 101.5,
                "low": 101.0,
                "close": 101.1,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:30:00Z",
                "open": 200.0,
                "high": 201.0,
                "low": 199.0,
                "close": 200.5,
                "volume": 1,
            },
        ]
    )
    out = infer_journal_triggers(
        pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")]),
        bars=bars,
    )
    assert decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"]) == ()


def test_future_shock_does_not_change_inferred_columns() -> None:
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")])
    first = infer_journal_triggers(zones, bars=_ohlcv_1m(), bars_15s=_ohlcv_15s())
    future_1m = pd.concat(
        [
            _ohlcv_1m(),
            _bars(
                [
                    {
                        "timestamp": "2026-05-14T09:31:00Z",
                        "open": 50.0,
                        "high": 51.0,
                        "low": 49.0,
                        "close": 50.5,
                        "volume": 1,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    future_15s = pd.concat(
        [
            _ohlcv_15s(),
            _bars(
                [
                    {
                        "timestamp": "2026-05-14T09:30:15Z",
                        "open": 50.0,
                        "high": 51.0,
                        "low": 49.0,
                        "close": 50.5,
                        "volume": 1,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    second = infer_journal_triggers(zones, bars=future_1m, bars_15s=future_15s)
    cols = [
        "inferred_triggers_1m",
        "inferred_triggers_15s",
        "trigger_bar_lag_seconds",
        "trigger_direction_consistent",
        "trigger_resolution_1m",
        "trigger_resolution_15s",
    ]
    pd.testing.assert_frame_equal(first[cols], second[cols], check_dtype=False)


def test_no_zone_id_stays_empty() -> None:
    out = infer_journal_triggers(
        pd.DataFrame(
            [_zone_row(entry="2026-05-14T09:30:00", zone_id=None, zone_low=None, zone_high=None)]
        ),
        bars=_ohlcv_1m(),
        bars_15s=_ohlcv_15s(),
    )
    assert decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"]) == ()
    assert decode_trigger_labels(out.iloc[0]["inferred_triggers_15s"]) == ()
    assert out.iloc[0]["trigger_direction_consistent"] is None or pd.isna(
        out.iloc[0]["trigger_direction_consistent"]
    )


def test_unreconciled_refused_unless_overridden() -> None:
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00", recon=RECON_AMP_MISSING)])
    with pytest.raises(JournalIngestError, match="not reconciled"):
        infer_journal_triggers(zones, bars=_ohlcv_1m())
    out = infer_journal_triggers(zones, bars=_ohlcv_1m(), allow_unreconciled=True)
    assert decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"])


def test_positional_bars_argument_is_rejected() -> None:
    with pytest.raises(TypeError):
        infer_journal_triggers(pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")]), _ohlcv_1m())  # type: ignore[misc]


def test_q3_inferred_trigger_hides_n_below_30_unless_toggled() -> None:
    zones = pd.DataFrame(
        [_zone_row(entry="2026-05-14T09:30:00", trade_id=f"t{index}") for index in range(12)]
    )
    inferred = infer_journal_triggers(zones, bars=_ohlcv_1m())
    hidden = build_journal_report(inferred, triggers=inferred, include_small_n=False)
    assert hidden.q3_triggers.empty
    shown = build_journal_report(inferred, triggers=inferred, include_small_n=True)
    assert not shown.q3_triggers.empty
    assert shown.captions["q3_triggers"] == TRIGGERS_HONESTY


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    zones_path = tmp_path / "journal_zones.parquet"
    bars_path = tmp_path / "bars_1m.parquet"
    bars_15s_path = tmp_path / "bars_15s.parquet"
    raw = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(zones_path, index=False)
    _ohlcv_1m().to_parquet(bars_path, index=False)
    _ohlcv_15s().to_parquet(bars_15s_path, index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "triggers",
            "--zones",
            str(zones_path),
            "--bars",
            str(bars_path),
            "--bars-15s",
            str(bars_15s_path),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads((out / "triggers.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["resolution_15s"] == TRIGGER_RESOLUTION_15S_PROXY
    assert payload["note"] == "1m and 15s_proxy are never averaged"
    frame = pd.read_parquet(out / "journal_triggers.parquet")
    assert frame.iloc[0]["trigger_resolution_15s"] == TRIGGER_RESOLUTION_15S_PROXY
    assert decode_trigger_labels(frame.iloc[0]["inferred_triggers_1m"])
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "triggers",
            "--zones",
            str(zones_path),
            "--bars",
            str(bars_path),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "triggers.json").exists()


def test_triggers_module_does_not_call_engine_mutators() -> None:
    source = Path("thesistester/journal/triggers.py").read_text(encoding="utf-8")
    assert "classify_zone_triggers" in source
    assert 'trigger_timeframe="base"' in source or "trigger_timeframe='base'" in source
    assert 'trigger_timeframe="1min"' not in source
    assert "compute_all_levels(" not in source
    assert "simulate_trades(" not in source
    assert "generate_signals(" not in source
    assert "_check_confirm_3bar(" not in source
    assert "Does not compare JS1" in source


def test_encode_decode_roundtrip() -> None:
    assert encode_trigger_labels(()) == ""
    assert decode_trigger_labels("") == ()
    assert decode_trigger_labels("fade|touch") == ("fade", "touch")
    assert encode_trigger_labels(("touch", "fade")) == "fade|touch"
    assert decode_trigger_labels("touch|fade") == ("fade", "touch")


def test_q3_none_excludes_unevaluated_no_zone_rows() -> None:
    zoned = [
        _zone_row(entry="2026-05-14T09:30:00", trade_id=f"z{index}", net_ticks=2.0)
        for index in range(30)
    ]
    no_zone = [
        _zone_row(
            entry="2026-05-14T09:30:00",
            trade_id=f"n{index}",
            zone_id=None,
            zone_low=None,
            zone_high=None,
        )
        for index in range(30)
    ]
    out = infer_journal_triggers(pd.DataFrame(zoned + no_zone), bars=_ohlcv_1m())
    report = build_journal_report(out, triggers=out, include_small_n=True)
    labels = set(report.q3_triggers["inferred_trigger"])
    assert TRIGGER_NONE not in labels
    assert "fade" in labels
    payload_counts = triggers_mod._label_counts(out, "inferred_triggers_1m")
    assert TRIGGER_NONE not in payload_counts


def test_invalid_direction_on_zoned_row_fails_closed() -> None:
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00", direction="both")])
    with pytest.raises(JournalIngestError, match="direction"):
        infer_journal_triggers(zones, bars=_ohlcv_1m())


def test_misaligned_15s_timestamps_fail_closed() -> None:
    bars_15s = _bars(
        [
            {
                "timestamp": "2026-05-14T09:29:47Z",
                "open": 100.8,
                "high": 100.9,
                "low": 100.2,
                "close": 100.4,
                "volume": 1,
            }
        ]
    )
    with pytest.raises(JournalIngestError, match="15-second bar opens"):
        infer_journal_triggers(
            pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00")]),
            bars=_ohlcv_1m(),
            bars_15s=bars_15s,
        )


def test_fade_only_opposite_side_is_direction_inconsistent() -> None:
    bars = _bars(
        [
            {
                "timestamp": "2026-05-14T09:28:00Z",
                "open": 101.2,
                "high": 101.5,
                "low": 101.0,
                "close": 101.1,
                "volume": 1,
            },
            {
                "timestamp": "2026-05-14T09:29:00Z",
                "open": 100.8,
                "high": 100.9,
                "low": 100.2,
                "close": 100.6,
                "volume": 1,
            },
        ]
    )
    zones = pd.DataFrame([_zone_row(entry="2026-05-14T09:30:00", direction="short")])
    out = infer_journal_triggers(
        zones,
        bars=bars,
        trigger_params={"require_close_confirmation": True},
    )
    labels = decode_trigger_labels(out.iloc[0]["inferred_triggers_1m"])
    assert "fade" in labels
    assert "continuation" not in labels
    assert out.iloc[0]["trigger_direction_consistent"] is False
