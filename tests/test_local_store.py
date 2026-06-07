import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

import thesistester.persistence.local_store as local_store
from thesistester.persistence.local_store import (
    SETUP_SCHEMA_VERSION,
    compute_setup_id,
    compute_levels_settings_hash,
    compute_signal_settings_hash,
    compute_dataset_id,
    delete_dataset,
    delete_levels,
    delete_setup,
    delete_signal_run,
    find_matching_levels,
    find_matching_signal_run,
    get_active_dataset_id,
    get_active_levels_hash,
    get_store_root,
    list_datasets,
    list_saved_setups,
    list_saved_levels,
    list_saved_signal_runs,
    load_dataset,
    load_levels,
    load_setup,
    load_signal_run,
    save_dataset,
    save_levels,
    save_setup,
    save_signal_run,
    set_active_dataset_id,
    set_active_levels_hash,
)


TZ = "America/New_York"


def _base_dataset() -> pd.DataFrame:
    timestamps = pd.date_range("2026-06-02 09:30:00", periods=3, freq="1min", tz=TZ)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.5, 100.5, 101.5],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 20.0, 30.0],
            "session": ["RTH", "RTH", "RTH"],
        }
    )


def _levels_frame() -> pd.DataFrame:
    df = _base_dataset().copy()
    df["RTH_Open"] = [100.0, 100.0, 100.0]
    df["OR_High"] = [None, None, 103.0]
    return df


def _session_levels_frame() -> pd.DataFrame:
    df = _base_dataset().copy()
    df["RTH_Open"] = [100.0, 100.0, 100.0]
    return df


def _levels_settings(**overrides) -> dict:
    settings = {
        "instrument": "ES",
        "opening_range_minutes": 30,
        "sma_lengths": [20, 50, 200],
        "ema_lengths": [20, 50, 200],
        "sma_timeframes": ["1min"],
        "ema_timeframes": ["1min"],
        "vwap_windows": ["15min", "1h"],
        "poc_windows": ["30min", "4h"],
        "value_area_pct": 0.7,
        "prior_day_profile_aggregation_ticks": 1,
        "prior_week_profile_aggregation_ticks": 1,
        "prior_month_profile_aggregation_ticks": 1,
    }
    settings.update(overrides)
    return settings


def _levels_fingerprint() -> dict:
    df = _base_dataset()
    return {
        "instrument": "ES",
        "rows": len(df),
        "timestamp_min": str(df["timestamp"].min()),
        "timestamp_max": str(df["timestamp"].max()),
        "columns": tuple(df.columns),
        "base_interval": "1min",
        "source_timezone": TZ,
        "exchange_timezone": TZ,
    }


def _signal_settings(**overrides) -> dict:
    settings = {
        "confluence_mode": "global_cluster",
        "selected_levels": ["OR_High", "OR_Low", "RTH_Open"],
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "direction": "both",
        "trigger_params": {},
        "use_saved_setup": False,
        "setup_snapshot": None,
    }
    settings.update(overrides)
    return settings


def _signals_frame() -> pd.DataFrame:
    df = _base_dataset()[["timestamp", "close"]].copy()
    df["signal_id"] = [1, 2, 3]
    df["bar_index"] = [0, 1, 2]
    df["trigger"] = ["touch", "touch", "touch"]
    df["direction"] = ["long", "short", "long"]
    df["zone_low"] = [100.0, 101.0, 102.0]
    df["zone_high"] = [100.5, 101.5, 102.5]
    df["zone_mid"] = [100.25, 101.25, 102.25]
    df["level_count"] = [2, 2, 3]
    df["level_names"] = ["OR_High,OR_Low", "OR_High,RTH_Open", "OR_High,OR_Low,RTH_Open"]
    df["entry_reference_price"] = df["close"]
    df["entry_model"] = "next_open"
    df["status"] = ["candidate", "candidate", "void"]
    return df


def _confluence_zones_frame() -> pd.DataFrame:
    df = _base_dataset()[["timestamp"]].copy()
    df["bar_index"] = [0, 1, 2]
    df["zone_low"] = [100.0, 101.0, 102.0]
    df["zone_high"] = [100.5, 101.5, 102.5]
    df["zone_mid"] = [100.25, 101.25, 102.25]
    df["level_count"] = [2, 2, 3]
    df["level_names"] = ["OR_High,OR_Low", "OR_High,RTH_Open", "OR_High,OR_Low,RTH_Open"]
    return df


def _naked_flags_frame() -> pd.DataFrame:
    df = _base_dataset()[["timestamp"]].copy()
    df["OR_High"] = [True, False, True]
    df["OR_Low"] = [False, False, True]
    df["RTH_Open"] = [True, True, True]
    return df


@pytest.fixture(autouse=True)
def _store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))


def test_dataset_roundtrip():
    df = _base_dataset()

    saved_meta = save_dataset(
        df,
        name="ES sample",
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )

    loaded_df, loaded_meta = load_dataset(saved_meta["dataset_id"])

    pd.testing.assert_frame_equal(loaded_df, df.reset_index(drop=True))
    assert loaded_df["timestamp"].dt.tz is not None
    assert str(loaded_df["timestamp"].dt.tz) == TZ
    assert loaded_meta["name"] == "ES sample"
    assert loaded_meta["instrument"] == "ES"
    assert loaded_meta["rows"] == len(df)
    assert loaded_meta["timestamp_min"] == df["timestamp"].min().isoformat()
    assert loaded_meta["timestamp_max"] == df["timestamp"].max().isoformat()
    assert loaded_meta["base_interval"] == "1min"
    assert loaded_meta["source_timezone"] == TZ
    assert loaded_meta["exchange_timezone"] == TZ


def test_dataset_id_content_sensitivity():
    df_one = _base_dataset()
    df_two = _base_dataset()
    df_two.loc[1, "close"] = 999.0

    dataset_id_one = compute_dataset_id(
        df_one,
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )
    dataset_id_two = compute_dataset_id(
        df_two,
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )

    assert dataset_id_one != dataset_id_two


def test_levels_roundtrip():
    dataset_id = "dataset-123"
    levels = _levels_frame()
    session_levels = _session_levels_frame()
    settings = _levels_settings()
    fingerprint = _levels_fingerprint()

    saved_meta = save_levels(
        dataset_id=dataset_id,
        levels=levels,
        session_levels=session_levels,
        levels_settings=settings,
        levels_data_fingerprint=fingerprint,
    )

    loaded_levels, loaded_session_levels, loaded_meta = load_levels(
        dataset_id,
        saved_meta["settings_hash"],
    )

    pd.testing.assert_frame_equal(loaded_levels, levels.reset_index(drop=True))
    pd.testing.assert_frame_equal(loaded_session_levels, session_levels.reset_index(drop=True))
    assert loaded_meta["levels_settings"] == settings
    assert loaded_meta["levels_data_fingerprint"] == {
        **fingerprint,
        "columns": list(fingerprint["columns"]),
    }


def test_matching_levels_lookup():
    dataset_id = "dataset-123"
    settings = _levels_settings()
    save_levels(
        dataset_id=dataset_id,
        levels=_levels_frame(),
        session_levels=_session_levels_frame(),
        levels_settings=settings,
        levels_data_fingerprint=_levels_fingerprint(),
    )

    matched = find_matching_levels(dataset_id=dataset_id, levels_settings=settings)
    missing = find_matching_levels(
        dataset_id=dataset_id,
        levels_settings=_levels_settings(opening_range_minutes=5),
    )

    assert matched is not None
    assert matched["dataset_id"] == dataset_id
    assert missing is None


def test_delete_behavior():
    dataset = save_dataset(
        _base_dataset(),
        name="Delete me",
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )
    levels = save_levels(
        dataset_id=dataset["dataset_id"],
        levels=_levels_frame(),
        session_levels=_session_levels_frame(),
        levels_settings=_levels_settings(),
        levels_data_fingerprint=_levels_fingerprint(),
    )

    assert list_datasets()
    assert list_saved_levels(dataset["dataset_id"])
    signal_run = save_signal_run(
        dataset_id=dataset["dataset_id"],
        levels_settings_hash=levels["settings_hash"],
        signal_settings=_signal_settings(),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    delete_levels(dataset["dataset_id"], levels["settings_hash"])
    assert list_saved_levels(dataset["dataset_id"]) == []
    with pytest.raises(FileNotFoundError):
        load_levels(dataset["dataset_id"], levels["settings_hash"])

    delete_dataset(dataset["dataset_id"])
    assert list_datasets() == []
    with pytest.raises(FileNotFoundError):
        load_dataset(dataset["dataset_id"])
    with pytest.raises(FileNotFoundError):
        load_signal_run(dataset["dataset_id"], levels["settings_hash"], signal_run["signal_settings_hash"])


def test_delete_dataset_clears_active_pointers():
    dataset = save_dataset(
        _base_dataset(),
        name="Pointer cleanup",
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )
    set_active_dataset_id(dataset["dataset_id"])
    set_active_levels_hash(dataset["dataset_id"], "hash-123")

    delete_dataset(dataset["dataset_id"])

    assert get_active_dataset_id() is None
    assert get_active_levels_hash(dataset["dataset_id"]) is None


def test_env_override_stable(tmp_path, monkeypatch):
    """THESISTESTER_STORE_DIR override is respected and datasets are found."""
    custom_store = tmp_path / "custom_store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(custom_store))

    save_dataset(
        _base_dataset(),
        name="env-override",
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )
    datasets = list_datasets()

    assert len(datasets) == 1
    assert datasets[0]["name"] == "env-override"
    assert str(get_store_root()).startswith(str(custom_store))


def test_list_rescans_from_disk(tmp_path, monkeypatch):
    """list_datasets() finds saved datasets even when manifest is stale or empty."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))

    save_dataset(
        _base_dataset(),
        name="rescan-test",
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )

    # Overwrite manifest with an empty datasets list to simulate stale state.
    from thesistester.persistence.local_store import _dataset_manifest_path

    manifest_path = _dataset_manifest_path()
    manifest_path.write_text('{"datasets": []}', encoding="utf-8")

    datasets = list_datasets()

    assert len(datasets) == 1
    assert datasets[0]["name"] == "rescan-test"


def test_list_rescans_when_manifest_missing(tmp_path, monkeypatch):
    """list_datasets() scans dataset folders when manifest.json does not exist."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))

    save_dataset(
        _base_dataset(),
        name="no-manifest",
        instrument="NQ",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )

    from thesistester.persistence.local_store import _dataset_manifest_path

    _dataset_manifest_path().unlink()

    datasets = list_datasets()

    assert len(datasets) == 1
    assert datasets[0]["name"] == "no-manifest"


def test_compute_signal_settings_hash_is_deterministic():
    settings_one = _signal_settings()
    settings_two = {
        "direction": "both",
        "trigger": "touch",
        "selected_levels": ["OR_High", "OR_Low", "RTH_Open"],
        "confluence_mode": "global_cluster",
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger_params": {},
        "use_saved_setup": False,
        "setup_snapshot": None,
    }

    assert compute_signal_settings_hash(settings_one) == compute_signal_settings_hash(settings_two)


def test_compute_levels_settings_hash_changes_when_indicator_timeframes_change():
    base = _levels_settings(sma_timeframes=["1min"], ema_timeframes=["1min"])
    changed = _levels_settings(sma_timeframes=["1min", "5min"], ema_timeframes=["1min"])

    assert compute_levels_settings_hash(base) != compute_levels_settings_hash(changed)


def test_compute_levels_settings_hash_handles_none_indicator_timeframes():
    with_none = _levels_settings(sma_timeframes=None, ema_timeframes=None)
    with_default = _levels_settings(sma_timeframes=["1min"], ema_timeframes=["1min"])

    assert compute_levels_settings_hash(with_none) != compute_levels_settings_hash(with_default)


def test_compute_levels_settings_hash_changes_when_prior_profile_aggregation_ticks_change():
    base = _levels_settings()
    changed = _levels_settings(prior_day_profile_aggregation_ticks=4)

    assert compute_levels_settings_hash(base) != compute_levels_settings_hash(changed)


def test_compute_signal_settings_hash_ignores_selected_levels_order():
    settings_one = _signal_settings(selected_levels=["OR_High", "OR_Low", "RTH_Open"])
    settings_two = _signal_settings(selected_levels=["RTH_Open", "OR_High", "OR_Low"])

    assert compute_signal_settings_hash(settings_one) == compute_signal_settings_hash(settings_two)


def test_compute_signal_settings_hash_ignores_confluence_rules_order():
    rules_one = [
        {"level": "OR_High", "tolerance_ticks": 1.0, "required": True},
        {"level": "RTH_Open", "tolerance_ticks": 2.0, "required": False},
    ]
    rules_two = [rules_one[1], rules_one[0]]
    settings_one = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_Low",
        confluence_rules=rules_one,
    )
    settings_two = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_Low",
        confluence_rules=rules_two,
    )

    assert compute_signal_settings_hash(settings_one) == compute_signal_settings_hash(settings_two)


def test_compute_signal_settings_hash_changes_when_settings_change():
    base = _signal_settings()
    changed = _signal_settings(trigger="reject")

    assert compute_signal_settings_hash(base) != compute_signal_settings_hash(changed)


def test_compute_signal_settings_hash_treats_missing_trigger_timeframe_as_base():
    missing = _signal_settings()
    explicit_base = _signal_settings(trigger_timeframe="base")
    missing.pop("trigger_timeframe", None)

    assert compute_signal_settings_hash(missing) == compute_signal_settings_hash(explicit_base)


def test_compute_signal_settings_hash_changes_between_base_and_5min():
    base = _signal_settings(trigger_timeframe="base")
    five_min = _signal_settings(trigger_timeframe="5min")

    assert compute_signal_settings_hash(base) != compute_signal_settings_hash(five_min)


def test_compute_signal_settings_hash_changes_when_rule_value_changes():
    base = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_High",
        confluence_rules=[{"level": "OR_Low", "tolerance_ticks": 1.0, "required": True}],
    )
    changed = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_High",
        confluence_rules=[{"level": "OR_Low", "tolerance_ticks": 2.0, "required": True}],
    )

    assert compute_signal_settings_hash(base) != compute_signal_settings_hash(changed)


def test_compute_signal_settings_hash_handles_malformed_rule_tolerance():
    malformed = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_High",
        confluence_rules=[{"level": "OR_Low", "tolerance_ticks": "not-a-number", "required": True}],
    )
    normalized = _signal_settings(
        confluence_mode="anchor_rules",
        anchor_level="OR_High",
        confluence_rules=[{"level": "OR_Low", "tolerance_ticks": 0.0, "required": True}],
    )

    assert compute_signal_settings_hash(malformed) == compute_signal_settings_hash(normalized)


def test_signal_run_roundtrip():
    saved_meta = save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={"setup_name": None, "confluence_mode": "global_cluster", "setup_caption": None},
        last_signal_setup={},
    )

    signals, zones, naked_flags, loaded_meta = load_signal_run(
        "dataset-123",
        "levels-hash-1",
        saved_meta["signal_settings_hash"],
    )

    pd.testing.assert_frame_equal(signals, _signals_frame().reset_index(drop=True))
    pd.testing.assert_frame_equal(zones, _confluence_zones_frame().reset_index(drop=True))
    pd.testing.assert_frame_equal(naked_flags, _naked_flags_frame().reset_index(drop=True))
    assert loaded_meta["dataset_id"] == "dataset-123"
    assert loaded_meta["levels_settings_hash"] == "levels-hash-1"
    assert loaded_meta["signal_settings"] == _signal_settings()


def test_save_signal_run_recovers_if_run_dir_is_deleted_before_first_write(monkeypatch):
    signal_settings = _signal_settings()
    signal_hash = compute_signal_settings_hash(signal_settings)
    run_dir = get_store_root() / "signals" / "dataset-123" / "levels-hash-1" / signal_hash
    assert not run_dir.exists()
    signals_path = run_dir / "signals.parquet"
    original_ensure_parent = local_store._ensure_parent
    first_write = {"done": False}
    run_dir_deleted = {"done": False}

    def _drop_run_dir_before_first_parquet_write(path):
        if not first_write["done"] and path == signals_path:
            first_write["done"] = True
            if run_dir.exists():
                shutil.rmtree(run_dir)
                run_dir_deleted["done"] = True
        return original_ensure_parent(path)

    monkeypatch.setattr(local_store, "_ensure_parent", _drop_run_dir_before_first_parquet_write)

    save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=signal_settings,
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    assert first_write["done"] is True
    assert run_dir_deleted["done"] is True
    assert (run_dir / "signals.parquet").exists()
    assert (run_dir / "confluence_zones.parquet").exists()
    assert (run_dir / "naked_flags.parquet").exists()
    assert (run_dir / "meta.json").exists()


def test_save_signal_run_repeat_save_succeeds():
    signal_settings = _signal_settings()
    signal_hash = compute_signal_settings_hash(signal_settings)
    run_dir = get_store_root() / "signals" / "dataset-123" / "levels-hash-1" / signal_hash

    save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=signal_settings,
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )
    save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=signal_settings,
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    assert (run_dir / "signals.parquet").exists()
    assert (run_dir / "confluence_zones.parquet").exists()
    assert (run_dir / "naked_flags.parquet").exists()
    assert (run_dir / "meta.json").exists()


def test_list_saved_signal_runs_filters_by_dataset_and_levels_hash():
    save_signal_run(
        dataset_id="dataset-a",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(trigger="touch"),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )
    save_signal_run(
        dataset_id="dataset-a",
        levels_settings_hash="levels-hash-2",
        signal_settings=_signal_settings(trigger="reject"),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )
    save_signal_run(
        dataset_id="dataset-b",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(trigger="break"),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    filtered = list_saved_signal_runs(dataset_id="dataset-a", levels_settings_hash="levels-hash-1")

    assert len(filtered) == 1
    assert filtered[0]["dataset_id"] == "dataset-a"
    assert filtered[0]["levels_settings_hash"] == "levels-hash-1"


def test_find_matching_signal_run_finds_exact_settings():
    settings = _signal_settings()
    save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=settings,
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    matched = find_matching_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=settings,
    )
    missing = find_matching_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(direction="long"),
    )

    assert matched is not None
    assert matched["dataset_id"] == "dataset-123"
    assert missing is None


def test_delete_signal_run_removes_only_selected_run():
    saved_touch = save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(trigger="touch"),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )
    saved_reject = save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(trigger="reject"),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )

    delete_signal_run("dataset-123", "levels-hash-1", saved_touch["signal_settings_hash"])

    with pytest.raises(FileNotFoundError):
        load_signal_run("dataset-123", "levels-hash-1", saved_touch["signal_settings_hash"])
    remaining = load_signal_run("dataset-123", "levels-hash-1", saved_reject["signal_settings_hash"])
    assert len(remaining[0]) == len(_signals_frame())


def test_list_saved_signal_runs_ignores_missing_or_corrupt_entries():
    saved = save_signal_run(
        dataset_id="dataset-123",
        levels_settings_hash="levels-hash-1",
        signal_settings=_signal_settings(),
        signals=_signals_frame(),
        confluence_zones=_confluence_zones_frame(),
        naked_flags=_naked_flags_frame(),
        signal_context={},
        last_signal_setup={},
    )
    run_root = Path(saved["path"])
    (run_root / "signals.parquet").unlink()

    corrupt_root = run_root.parent / "corrupt-run"
    corrupt_root.mkdir(parents=True, exist_ok=True)
    (corrupt_root / "meta.json").write_text("{not json", encoding="utf-8")

    assert list_saved_signal_runs(dataset_id="dataset-123", levels_settings_hash="levels-hash-1") == []


def test_default_store_root_stable(monkeypatch):
    """get_store_root() without env override is absolute and repo-root-relative."""
    monkeypatch.delenv("THESISTESTER_STORE_DIR", raising=False)

    root = get_store_root()

    assert root.is_absolute()
    assert root.name == ".thesistester_store"
    # Must not be inside the thesistester/persistence package directory.
    from thesistester.persistence import local_store

    persistence_dir = Path(local_store.__file__).resolve().parent
    assert not str(root).startswith(str(persistence_dir))


def _setup_config(**overrides) -> dict:
    config = {
        "name": "OR touch",
        "description": "test setup",
        "instrument": "ES",
        "selected_levels": ["OR_High", "OR_Low"],
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "confluence_mode": "global_cluster",
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "trigger_params": {},
    }
    config.update(overrides)
    return config


def test_save_and_load_setup_roundtrip():
    saved = save_setup(
        _setup_config(),
        dataset_id="dataset-a",
        instrument="ES",
    )
    loaded = load_setup(saved["setup_id"])

    assert loaded["schema_version"] == SETUP_SCHEMA_VERSION
    assert loaded["kind"] == "setup"
    assert loaded["dataset_id"] == "dataset-a"
    assert loaded["instrument"] == "ES"
    assert loaded["setup_config"]["name"] == "OR touch"
    assert loaded["setup_id"] == saved["setup_id"]


def test_save_setup_preserves_created_at_when_updating():
    saved = save_setup(_setup_config(name="First"), setup_id="setup-123", dataset_id="dataset-a")
    original_created_at = saved["created_at"]

    updated = save_setup(_setup_config(name="Updated"), setup_id="setup-123", dataset_id="dataset-a")

    assert updated["setup_id"] == "setup-123"
    assert updated["created_at"] == original_created_at
    assert updated["updated_at"] >= original_created_at
    assert updated["name"] == "Updated"


def test_list_saved_setups_returns_newest_first():
    first = save_setup(_setup_config(name="first"), setup_id="setup-first", dataset_id="dataset-a")
    second = save_setup(_setup_config(name="second"), setup_id="setup-second", dataset_id="dataset-a")

    first_meta_path = Path(first["path"]) / "meta.json"
    second_meta_path = Path(second["path"]) / "meta.json"
    first_meta = json.loads(first_meta_path.read_text(encoding="utf-8"))
    second_meta = json.loads(second_meta_path.read_text(encoding="utf-8"))
    first_meta["updated_at"] = "2026-06-01T00:00:00+00:00"
    second_meta["updated_at"] = "2026-06-02T00:00:00+00:00"
    first_meta_path.write_text(json.dumps(first_meta), encoding="utf-8")
    second_meta_path.write_text(json.dumps(second_meta), encoding="utf-8")

    listed = list_saved_setups()

    assert [item["setup_id"] for item in listed] == ["setup-second", "setup-first"]


def test_list_saved_setups_ignores_corrupt_metadata():
    corrupt_dir = get_store_root() / "setups" / "corrupt-setup"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "meta.json").write_text("{not json", encoding="utf-8")

    assert list_saved_setups() == []


def test_list_saved_setups_ignores_unsupported_schema():
    saved = save_setup(_setup_config(), setup_id="setup-123", dataset_id="dataset-a")
    meta_path = Path(saved["path"]) / "meta.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    listed = list_saved_setups()
    assert listed == []
    with pytest.raises(ValueError):
        load_setup("setup-123")


def test_list_saved_setups_can_filter_dataset():
    save_setup(_setup_config(name="a"), setup_id="setup-a", dataset_id="dataset-a")
    save_setup(_setup_config(name="b"), setup_id="setup-b", dataset_id="dataset-b")
    save_setup(_setup_config(name="global"), setup_id="setup-g", dataset_id=None)

    filtered = list_saved_setups(dataset_id="dataset-a")

    assert [item["setup_id"] for item in filtered] == ["setup-a"]


def test_delete_setup_removes_saved_setup():
    saved = save_setup(_setup_config(), setup_id="setup-123", dataset_id="dataset-a")

    delete_setup(saved["setup_id"])

    assert list_saved_setups() == []
    with pytest.raises(FileNotFoundError):
        load_setup(saved["setup_id"])


def test_compute_setup_id_returns_unique_values():
    assert compute_setup_id() != compute_setup_id()


@pytest.mark.parametrize("invalid_setup_id", ["../escape", "abc/def", r"abc\def", "", "   "])
def test_setup_operations_reject_invalid_setup_ids(invalid_setup_id):
    with pytest.raises(ValueError):
        save_setup(_setup_config(), setup_id=invalid_setup_id, dataset_id="dataset-a")

    with pytest.raises(ValueError):
        load_setup(invalid_setup_id)

    with pytest.raises(ValueError):
        delete_setup(invalid_setup_id)


@pytest.mark.parametrize("valid_setup_id", ["setup-123", "setup_123"])
def test_setup_operations_accept_valid_explicit_setup_ids(valid_setup_id):
    saved = save_setup(_setup_config(), setup_id=valid_setup_id, dataset_id="dataset-a")

    loaded = load_setup(valid_setup_id)

    assert saved["setup_id"] == valid_setup_id
    assert loaded["setup_id"] == valid_setup_id


def test_save_setup_accepts_generated_safe_setup_id():
    saved = save_setup(_setup_config(), dataset_id="dataset-a")

    assert saved["setup_id"]
    assert "/" not in saved["setup_id"]
    assert "\\" not in saved["setup_id"]
    assert load_setup(saved["setup_id"])["setup_id"] == saved["setup_id"]
