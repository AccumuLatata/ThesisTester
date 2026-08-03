"""CAI-3 — cached headless pipeline parity and safe miss fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import compute_levels, load_dataset, run_experiment
from thesistester.persistence.execution_artifacts import (
    MANIFEST_FILENAME,
    get_execution_artifacts_root,
    invalidate_data_artifact,
    levels_artifact_key,
    read_verified_levels_artifact,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import DataIdentity, LevelsIdentity
from tests.fixtures.assistant_parity import parity_run_spec, write_parity_bars


def _run(
    tmp_path: Path,
    *,
    cache_policy: str,
    store_root: Path,
    levels_overlay: dict | None = None,
) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    spec = parity_run_spec(dataset_path="bars.csv")
    if levels_overlay:
        spec = {**spec, "levels": {**spec["levels"], **levels_overlay}}
    return run_experiment(
        spec,
        base_directory=tmp_path,
        cache_policy=cache_policy,
        store_root=store_root,
    )


def test_default_cache_policy_is_bypassed(tmp_path: Path):
    store = tmp_path / "store"
    state = _run(tmp_path, cache_policy="off", store_root=store)
    assert state["cache_provenance"]["outcome"] == "bypassed"
    assert state["cache_provenance"]["policy"] == "off"
    assert not (store / "execution_artifacts").exists()


def test_cold_and_warm_read_write_match_bundle_and_frames(tmp_path: Path):
    store = tmp_path / "store"
    cold = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert cold["cache_provenance"]["outcome"] == "cold"
    assert cold["cache_provenance"]["data"]["status"] == "written"
    assert cold["cache_provenance"]["levels"]["status"] == "written"

    warm = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert warm["cache_provenance"]["outcome"] == "levels_hit"
    assert warm["cache_provenance"]["data"]["status"] == "hit"
    assert warm["cache_provenance"]["levels"]["status"] == "hit"

    assert canonical_bundle_hash(build_research_bundle(cold)) == canonical_bundle_hash(
        build_research_bundle(warm)
    )
    pd.testing.assert_frame_equal(cold["data"], warm["data"], check_dtype=False)
    pd.testing.assert_frame_equal(cold["levels"], warm["levels"], check_dtype=False)
    pd.testing.assert_frame_equal(
        cold["session_levels"], warm["session_levels"], check_dtype=False
    )
    pd.testing.assert_frame_equal(cold["signals"], warm["signals"], check_dtype=False)
    pd.testing.assert_frame_equal(cold["trades"], warm["trades"], check_dtype=False)
    assert cold["trade_summary"] == warm["trade_summary"]
    assert cold.get("validation_summary") == warm.get("validation_summary")


def test_warm_path_skips_csv_when_source_deleted_after_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Warm data hits must not require re-parsing the source CSV."""
    store = tmp_path / "store"
    cold = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert cold["cache_provenance"]["outcome"] == "cold"

    calls = {"n": 0}
    real_load = load_dataset

    def counting_load(*args, **kwargs):
        calls["n"] += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr("thesistester.api.load_dataset", counting_load)
    warm = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert warm["cache_provenance"]["outcome"] == "levels_hit"
    assert calls["n"] == 0


def test_corrupt_levels_artifact_falls_back_to_cold(tmp_path: Path):
    store = tmp_path / "store"
    cold = _run(tmp_path, cache_policy="read_write", store_root=store)
    levels_identity = LevelsIdentity.from_dict(cold["levels_identity"])
    assert levels_identity is not None
    artifact = read_verified_levels_artifact(levels_identity, store_root=store)
    assert not isinstance(artifact, type(None))
    from thesistester.persistence.execution_artifacts import LevelsArtifact

    assert isinstance(artifact, LevelsArtifact)
    (artifact.path / MANIFEST_FILENAME).write_text("{bad", encoding="utf-8")

    recovered = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert recovered["cache_provenance"]["data"]["status"] == "hit"
    assert recovered["cache_provenance"]["levels"]["status"] == "written"
    assert recovered["cache_provenance"]["outcome"] == "data_hit"
    assert canonical_bundle_hash(build_research_bundle(cold)) == canonical_bundle_hash(
        build_research_bundle(recovered)
    )


def test_changed_levels_settings_cold_recomputes_levels(tmp_path: Path):
    store = tmp_path / "store"
    first = _run(tmp_path, cache_policy="read_write", store_root=store)
    second = _run(
        tmp_path,
        cache_policy="read_write",
        store_root=store,
        levels_overlay={"sma_lengths": [3]},
    )
    assert second["cache_provenance"]["data"]["status"] == "hit"
    assert second["cache_provenance"]["levels"]["status"] == "written"
    assert second["cache_provenance"]["outcome"] == "data_hit"
    assert first["levels_identity"]["levels_settings_hash"] != second["levels_identity"][
        "levels_settings_hash"
    ]


def test_stale_source_content_misses_data_cache(tmp_path: Path):
    store = tmp_path / "store"
    first = _run(tmp_path, cache_policy="read_write", store_root=store)
    # Mutate source bytes after the initial fixture write. Binding keys include
    # the raw file digest, so this must miss even if the path is unchanged.
    path = tmp_path / "bars.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "volume"] = int(frame.loc[0, "volume"]) + 1000
    frame.to_csv(path, index=False)
    second = run_experiment(
        parity_run_spec(dataset_path="bars.csv"),
        base_directory=tmp_path,
        cache_policy="read_write",
        store_root=store,
    )
    assert second["cache_provenance"]["data"]["status"] == "written"
    assert second["cache_provenance"]["outcome"] == "cold"
    assert first["data_identity"]["data_content_hash"] != second["data_identity"][
        "data_content_hash"
    ]


def test_off_and_read_write_bundle_hashes_match(tmp_path: Path):
    store = tmp_path / "store"
    bypassed = _run(tmp_path, cache_policy="off", store_root=store)
    cached = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert bypassed["cache_provenance"]["outcome"] == "bypassed"
    assert cached["cache_provenance"]["outcome"] == "cold"
    assert canonical_bundle_hash(build_research_bundle(bypassed)) == canonical_bundle_hash(
        build_research_bundle(cached)
    )


def test_compute_levels_cache_hit(tmp_path: Path):
    store = tmp_path / "store"
    write_parity_bars(tmp_path / "bars.csv")
    data = load_dataset(tmp_path / "bars.csv", instrument="ES", source_timezone="America/New_York")
    identity = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
    )
    config = {"sma_lengths": [2], "ema_lengths": [2], "poc_windows": []}
    cold = compute_levels(
        data,
        instrument="ES",
        config=config,
        cache_policy="read_write",
        data_identity=identity,
        store_root=store,
    )
    assert cold.get("cache_status") == "written"
    warm = compute_levels(
        data,
        instrument="ES",
        config=config,
        cache_policy="read",
        data_identity=identity,
        store_root=store,
    )
    assert warm.get("cache_status") == "hit"
    pd.testing.assert_frame_equal(cold["levels"], warm["levels"], check_dtype=False)


def test_invalidate_data_forces_cold_rebind(tmp_path: Path):
    store = tmp_path / "store"
    first = _run(tmp_path, cache_policy="read_write", store_root=store)
    identity = DataIdentity.from_dict(first["data_identity"])
    assert identity is not None
    assert invalidate_data_artifact(identity, store_root=store) is True
    second = _run(tmp_path, cache_policy="read_write", store_root=store)
    assert second["cache_provenance"]["data"]["status"] == "written"
    assert canonical_bundle_hash(build_research_bundle(first)) == canonical_bundle_hash(
        build_research_bundle(second)
    )


def test_cache_provenance_not_in_bundle_members(tmp_path: Path):
    store = tmp_path / "store"
    state = _run(tmp_path, cache_policy="read_write", store_root=store)
    bundle = build_research_bundle(state)
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        names = set(zf.namelist())
        assert "research_identity.json" in names
        identity_meta = json.loads(zf.read("research_identity.json").decode("utf-8"))
    assert "cache_provenance" not in identity_meta
    assert "cache_provenance" not in names
    # Artifact root exists for read_write but is outside the research bundle.
    assert get_execution_artifacts_root(store).exists()
    assert levels_artifact_key(LevelsIdentity.from_dict(state["levels_identity"]))  # type: ignore[arg-type]
