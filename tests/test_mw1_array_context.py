"""MW1 §10.4: array context parity, slot lifetime, flag-off regression."""

from __future__ import annotations

import io
import json
import multiprocessing
import os
import threading
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.memory_parity.bits import replica_hex_list
from tests.fixtures.memory_parity.capture import isolate_store
from tests.fixtures.memory_parity.cells import CI_PREPARE_REPLICA, build_study_mapping
from tests.fixtures.memory_parity.compare import compare_trades
from tests.fixtures.memory_parity.generate_synthetic import (
    default_synthetic_path,
    write_synthetic_csv,
)
from tests.fixtures.memory_parity.hooks import replica_expectancies_hook
from thesistester.analytics.overfitting import vs_random_benchmark
from thesistester.data.derive import derive_complete_parent_ohlcv
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.intrabar import (
    PackedSubtimeframeGroups,
    clear_context_slot,
    compute_context_slot_key,
    context_slot_is_active,
    enter_context_slot,
    memory_path_is_array,
    prepare_subtimeframe_conservative_context,
    prepare_subtimeframe_context,
)
from thesistester.research_bundle import canonical_bundle_hash
from thesistester.study.expand import expand_study
from thesistester.study.execute import execute_study_cell

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "memory_parity" / "synthetic_golden"
TZ = "America/New_York"
MEMORY_PATH_ENV = "THESISTESTER_MEMORY_PATH"


@pytest.fixture(autouse=True)
def _clear_mw1_slot() -> Any:
    clear_context_slot()
    yield
    clear_context_slot()


def _complete_minute(minute: str, *, open_price: float, session: str = "RTH") -> pd.DataFrame:
    start = pd.Timestamp(minute).tz_localize(TZ)
    stamps = [start + pd.Timedelta(seconds=offset) for offset in (0, 15, 30, 45)]
    opens = [open_price, open_price + 0.25, open_price + 0.50, open_price + 0.75]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": np.array(opens, dtype="float64"),
            "high": np.array([value + 1.00 for value in opens], dtype="float64"),
            "low": np.array([value - 1.00 for value in opens], dtype="float64"),
            "close": np.array([value + 0.25 for value in opens], dtype="float64"),
            "volume": np.array([10.0, 11.0, 12.0, 13.0], dtype="float64"),
            "session": [session] * 4,
        }
    )


def _multi_day_frames(
    *, price: float = 100.0, sparse: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    minutes: list[pd.DataFrame] = []
    for day, base in (("2024-08-01", price), ("2024-08-02", price + 5.0)):
        for offset in range(8):
            stamp = f"{day} 14:{offset:02d}:00"
            minutes.append(_complete_minute(stamp, open_price=base + offset * 0.25))
    if sparse:
        minutes.append(_complete_minute("2024-08-01 14:08:00", open_price=price + 8.0).iloc[:2])
    source = pd.concat(minutes, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    derived = derive_complete_parent_ohlcv(source)
    return derived.parent_data, derived.source_data


def _assert_group_parity(flag_off: Any, flag_on: Any) -> None:
    assert flag_off.fallback_reasons == flag_on.fallback_reasons
    assert flag_off.parent_interval == flag_on.parent_interval
    assert flag_off.sub_interval == flag_on.sub_interval
    assert list(flag_off.groups) == list(flag_on.groups)
    assert len(flag_off.groups) == len(flag_on.groups)
    for index in flag_off.groups:
        left = flag_off.groups[index][["timestamp", "open", "high", "low", "close"]].reset_index(
            drop=True
        )
        right = flag_on.groups[index]
        assert list(right.columns) == ["timestamp", "open", "high", "low", "close"]
        assert "volume" not in right.columns
        assert "session" not in right.columns
        assert list(right.index) == list(range(len(right)))
        assert str(right["timestamp"].dtype) == str(left["timestamp"].dtype)
        for column in ("open", "high", "low", "close"):
            assert str(right[column].dtype) == "float64"
            assert np.array_equal(
                left[column].to_numpy(dtype="float64"),
                right[column].to_numpy(dtype="float64"),
            )
        pd.testing.assert_series_equal(left["timestamp"], right["timestamp"], check_names=False)


def _signal(bar_index: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [bar_index],
            "trigger": ["touch"],
            "direction": ["long"],
        }
    )


def _simulate(parent: pd.DataFrame, sub: pd.DataFrame) -> pd.DataFrame:
    trades = simulate_trades(
        parent,
        _signal(),
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=8,
        take_profit_ticks=12,
        commission_per_side=0.5,
        slippage_ticks=1.0,
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone=TZ,
        intrabar_model="subtimeframe_conservative",
        subtimeframe_data=sub,
        parent_interval="1min",
        sub_interval="15s",
    )
    assert isinstance(trades, pd.DataFrame)
    return trades


def test_flag_off_is_dict_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    parent, sub = _multi_day_frames()
    context = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    assert memory_path_is_array() is False
    assert isinstance(context.groups, dict)
    assert not isinstance(context.groups, PackedSubtimeframeGroups)


def test_group_parity_flag_on_vs_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames()
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    flag_off = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    flag_on = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    assert isinstance(flag_on.groups, PackedSubtimeframeGroups)
    _assert_group_parity(flag_off, flag_on)
    first = flag_on.groups[next(iter(flag_on.groups))]
    second = flag_on.groups[next(iter(flag_on.groups))]
    assert first is not second

    complete_parent, complete_sub = _multi_day_frames(sparse=False)
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    strict_off = prepare_subtimeframe_context(
        complete_parent,
        complete_sub,
        tick_size=0.25,
        parent_interval="1min",
        sub_interval="15s",
    )
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    strict_on = prepare_subtimeframe_context(
        complete_parent,
        complete_sub,
        tick_size=0.25,
        parent_interval="1min",
        sub_interval="15s",
    )
    _assert_group_parity(strict_off, strict_on)


def test_ohlc_mismatch_raises_same_type(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    parent = parent.copy()
    parent.loc[parent.index[0], "high"] = float(parent.loc[parent.index[0], "high"]) + 50.0
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    with pytest.raises(ValueError, match="does not reconcile") as flag_off:
        prepare_subtimeframe_conservative_context(
            parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
        )
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    with pytest.raises(ValueError, match="does not reconcile") as flag_on:
        prepare_subtimeframe_conservative_context(
            parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
        )
    assert type(flag_off.value) is type(flag_on.value)


def test_slot_key_changes_when_ohlc_bits_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    other_parent, other_sub = _multi_day_frames(price=140.0, sparse=False)
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    enter_context_slot()
    first = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    second = prepare_subtimeframe_conservative_context(
        other_parent, other_sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    key_a = compute_context_slot_key(
        parent,
        sub,
        parent_interval=first.parent_interval,
        sub_interval=first.sub_interval,
        tick_size=0.25,
        model="subtimeframe_conservative",
    )
    key_b = compute_context_slot_key(
        other_parent,
        other_sub,
        parent_interval=second.parent_interval,
        sub_interval=second.sub_interval,
        tick_size=0.25,
        model="subtimeframe_conservative",
    )
    assert key_a != key_b
    assert first is not second
    first_close = float(first.groups[0]["close"].iloc[-1])
    second_close = float(second.groups[0]["close"].iloc[-1])
    assert first_close != second_close


def test_unsorted_parent_raises_before_slot_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    enter_context_slot()
    prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    shuffled = parent.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="timestamps must be sorted"):
        prepare_subtimeframe_conservative_context(
            shuffled, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
        )


def test_load_time_prepare_reuses_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    levels_like = parent.copy()
    levels_like["SMA_50_5min"] = 100.0
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    enter_context_slot()
    discarded = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    reused = prepare_subtimeframe_conservative_context(
        levels_like,
        sub,
        tick_size=0.25,
        parent_interval=pd.Timedelta(minutes=1),
        sub_interval=pd.Timedelta(seconds=15),
    )
    assert discarded is reused
    assert context_slot_is_active() is True


def test_trade_parity_flag_on_vs_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    off_trades = _simulate(parent, sub)
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    on_trades = _simulate(parent, sub)
    diffs = compare_trades(off_trades, on_trades)
    assert diffs == [], diffs
    assert len(off_trades) >= 1


def test_replica_parity_flag_on_vs_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    reference = _simulate(parent, sub)
    kwargs = {
        "intrabar_model": "subtimeframe_conservative",
        "subtimeframe_data": sub,
        "parent_interval": "1min",
        "sub_interval": "15s",
        "commission_per_side": 0.5,
        "slippage_ticks": 1.0,
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": TZ,
    }
    off = vs_random_benchmark(
        parent,
        reference,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=8,
        take_profit_ticks=12,
        execution_kwargs=kwargs,
        n_replicas=50,
        random_state=42,
    )
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    enter_context_slot()
    on = vs_random_benchmark(
        parent,
        reference,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=8,
        take_profit_ticks=12,
        execution_kwargs=kwargs,
        n_replicas=50,
        random_state=42,
    )
    assert replica_hex_list(off["replica_expectancies"]) == replica_hex_list(
        on["replica_expectancies"]
    )
    assert len(off["replica_expectancies"]) == 50
    assert context_slot_is_active() is True


def _shift_quantower_prices(source: Path, dest: Path, delta: float) -> Path:
    lines = source.read_text(encoding="utf-8").splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(";")
        for index in (2, 3, 4, 5, 6, 7, 10):
            if index < len(parts) and parts[index]:
                parts[index] = f"{float(parts[index]) + delta:.4f}"
        out.append(";".join(parts))
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    return dest


def _cell_task(spec: Any, csv_path: Path, output_dir: Path) -> tuple[dict[str, Any], str]:
    mapping = build_study_mapping(
        spec,
        csv_path=csv_path,
        study_name=f"mw1_{spec.cell_id}_{output_dir.name}",
        output_dir=output_dir,
    )
    expansion = expand_study(mapping)
    run = dict(expansion.experiment["runs"][0])
    run["_da5_random_baseline"] = {
        "enabled": True,
        "n_replicas": spec.n_replicas,
        "random_state": 42,
    }
    return run, str(output_dir)


def _trades_from_bundle(bundle: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        return pd.read_parquet(io.BytesIO(archive.read("trades.parquet")))


def _run_execute_cell(
    *,
    csv_path: Path,
    work: Path,
    flag_on: bool,
) -> dict[str, Any]:
    if flag_on:
        os.environ[MEMORY_PATH_ENV] = "array"
    else:
        os.environ.pop(MEMORY_PATH_ENV, None)
    study_out = work / "study"
    study_out.mkdir(parents=True, exist_ok=True)
    task = _cell_task(CI_PREPARE_REPLICA, csv_path, study_out)
    with isolate_store(work), replica_expectancies_hook() as sink:
        payload = execute_study_cell(task)
    if payload["status"] != "ok" or payload["bundle"] is None:
        raise AssertionError(f"cell failed: {payload.get('error')!r}")
    trades = _trades_from_bundle(payload["bundle"])
    return {
        "status": payload["status"],
        "trades": trades,
        "replicas": sink.last,
        "hash": canonical_bundle_hash(payload["bundle"]),
        "index_row": payload["index_row"],
    }


def _spawn_execute_cell(payload: dict[str, Any]) -> dict[str, Any]:
    result = _run_execute_cell(
        csv_path=Path(payload["csv_path"]),
        work=Path(payload["work"]),
        flag_on=bool(payload["flag_on"]),
    )
    dest = Path(payload["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    result["trades"].to_parquet(dest / "trades.parquet", index=False)
    return {
        "hash": result["hash"],
        "replicas": result["replicas"],
        "dest": str(dest),
        "trade_count": int(len(result["trades"])),
    }


def test_two_cells_one_process_slot_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    csv_b = write_synthetic_csv(tmp_path / "b.csv")
    csv_a = _shift_quantower_prices(csv_b, tmp_path / "a.csv", delta=75.0)
    sequential = _run_execute_cell(csv_path=csv_a, work=tmp_path / "cell_a", flag_on=True)
    assert sequential["status"] == "ok"
    same_process_b = _run_execute_cell(csv_path=csv_b, work=tmp_path / "cell_b", flag_on=True)
    assert compare_trades(sequential["trades"], same_process_b["trades"]) != []
    assert sequential["hash"] != same_process_b["hash"]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=1) as pool:
        fresh = pool.apply(
            _spawn_execute_cell,
            [
                {
                    "csv_path": str(csv_b),
                    "work": str(tmp_path / "fresh_work"),
                    "dest": str(tmp_path / "fresh_dest"),
                    "flag_on": True,
                }
            ],
        )
    fresh_trades = pd.read_parquet(Path(fresh["dest"]) / "trades.parquet")
    diffs = compare_trades(same_process_b["trades"], fresh_trades)
    assert diffs == [], diffs
    assert replica_hex_list(same_process_b["replicas"]) == replica_hex_list(fresh["replicas"])
    assert same_process_b["hash"] == fresh["hash"]
    assert context_slot_is_active() is False


def test_flag_off_cell_b_matches_mw0_synthetic_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not GOLDEN.is_dir():
        pytest.fail("STOP AND REPORT: synthetic golden is missing")
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    csv_b = write_synthetic_csv(tmp_path / "b.csv")
    live = _run_execute_cell(csv_path=csv_b, work=tmp_path / "flag_off_b", flag_on=False)
    golden_cell = GOLDEN / "cells" / CI_PREPARE_REPLICA.cell_id
    golden_trades = pd.read_parquet(golden_cell / "trades.parquet")
    diffs = compare_trades(golden_trades, live["trades"])
    assert diffs == [], diffs
    golden_bits = list(
        json.loads((golden_cell / "replica_expectancies.json").read_text(encoding="utf-8")).get(
            "hex_bits"
        )
        or []
    )
    assert replica_hex_list(live["replicas"]) == golden_bits
    committed = default_synthetic_path()
    assert committed.is_file()


def test_flag_on_cell_matches_flag_off_product_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_b = write_synthetic_csv(tmp_path / "b.csv")
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    off = _run_execute_cell(csv_path=csv_b, work=tmp_path / "hash_off", flag_on=False)
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    on = _run_execute_cell(csv_path=csv_b, work=tmp_path / "hash_on", flag_on=True)
    diffs = compare_trades(off["trades"], on["trades"])
    assert diffs == [], diffs
    assert replica_hex_list(off["replicas"]) == replica_hex_list(on["replicas"])
    assert off["hash"] == on["hash"]
    assert str(off["trades"]["exit_subbar_timestamp"].dtype) == str(
        on["trades"]["exit_subbar_timestamp"].dtype
    )


def test_packed_groups_key_contract_matches_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    parent, sub = _multi_day_frames(sparse=False)
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    context = prepare_subtimeframe_conservative_context(
        parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
    )
    groups = context.groups
    assert isinstance(groups, PackedSubtimeframeGroups)
    first = next(iter(groups))
    assert groups.get(first) is not None
    assert groups.get("0") is None
    assert "0" not in groups
    assert groups.get(None) is None
    assert None not in groups
    with pytest.raises(KeyError):
        groups["0"]  # type: ignore[index]
    with pytest.raises(KeyError):
        groups[None]  # type: ignore[index]
    assert groups.get(np.int64(first)) is not None


def test_slot_is_thread_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    parent_a, sub_a = _multi_day_frames(price=100.0, sparse=False)
    parent_b, sub_b = _multi_day_frames(price=175.0, sparse=False)
    barrier = threading.Barrier(2)
    hits: dict[str, dict[str, Any]] = {}

    def worker(name: str, parent: pd.DataFrame, sub: pd.DataFrame) -> None:
        enter_context_slot()
        try:
            first = prepare_subtimeframe_conservative_context(
                parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
            )
            barrier.wait()
            second = prepare_subtimeframe_conservative_context(
                parent, sub, tick_size=0.25, parent_interval="1min", sub_interval="15s"
            )
            hits[name] = {
                "same": first is second,
                "close": float(first.groups[0]["close"].iloc[-1]),
            }
        finally:
            clear_context_slot()

    thread_a = threading.Thread(target=worker, args=("a", parent_a, sub_a))
    thread_b = threading.Thread(target=worker, args=("b", parent_b, sub_b))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()
    assert hits["a"]["same"] is True
    assert hits["b"]["same"] is True
    assert hits["a"]["close"] != hits["b"]["close"]
    assert context_slot_is_active() is False


def test_execute_study_cell_clears_slot_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")

    def boom(*_args: object, **_kwargs: object) -> None:
        assert context_slot_is_active() is True
        raise RuntimeError("cell exploded")

    monkeypatch.setattr("thesistester.study.execute.run_experiment", boom)
    payload = execute_study_cell(({"name": "boom"}, "."))
    assert payload["status"] == "failed"
    assert "RuntimeError" in str(payload.get("error"))
    assert context_slot_is_active() is False


def test_first_last_empty_and_missing_parent_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    source = pd.concat(
        [
            _complete_minute("2024-08-01 14:00:00", open_price=100.0),
            _complete_minute("2024-08-01 14:01:00", open_price=101.0),
            _complete_minute("2024-08-01 14:02:00", open_price=102.0).iloc[:1],
        ],
        ignore_index=True,
    )
    derived = derive_complete_parent_ohlcv(source)
    monkeypatch.delenv(MEMORY_PATH_ENV, raising=False)
    flag_off = prepare_subtimeframe_conservative_context(
        derived.parent_data,
        derived.source_data,
        tick_size=0.25,
        parent_interval="1min",
        sub_interval="15s",
    )
    monkeypatch.setenv(MEMORY_PATH_ENV, "array")
    flag_on = prepare_subtimeframe_conservative_context(
        derived.parent_data,
        derived.source_data,
        tick_size=0.25,
        parent_interval="1min",
        sub_interval="15s",
    )
    _assert_group_parity(flag_off, flag_on)
    last_parent = len(derived.parent_data) - 1
    assert last_parent not in flag_on.groups
    assert flag_on.groups.get(last_parent) is None
    empty_sub = derived.source_data.iloc[0:0].copy()
    empty_on = prepare_subtimeframe_conservative_context(
        derived.parent_data,
        empty_sub,
        tick_size=0.25,
        parent_interval="1min",
        sub_interval="15s",
    )
    assert len(empty_on.groups) == 0
    assert len(empty_on.fallback_reasons) == len(derived.parent_data)
