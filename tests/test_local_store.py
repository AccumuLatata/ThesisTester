import pandas as pd
import pytest

from thesistester.persistence.local_store import (
    compute_dataset_id,
    delete_dataset,
    delete_levels,
    find_matching_levels,
    list_datasets,
    list_saved_levels,
    load_dataset,
    load_levels,
    save_dataset,
    save_levels,
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
        "vwap_windows": ["15min", "1h"],
        "poc_windows": ["30min", "4h"],
        "value_area_pct": 0.7,
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

    delete_levels(dataset["dataset_id"], levels["settings_hash"])
    assert list_saved_levels(dataset["dataset_id"]) == []
    with pytest.raises(FileNotFoundError):
        load_levels(dataset["dataset_id"], levels["settings_hash"])

    delete_dataset(dataset["dataset_id"])
    assert list_datasets() == []
    with pytest.raises(FileNotFoundError):
        load_dataset(dataset["dataset_id"])
