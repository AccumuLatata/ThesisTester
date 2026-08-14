"""CAI-2 — durable internal execution-artifact store."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import compute_levels
from thesistester.data.derive import (
    DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
)
from thesistester.persistence.execution_artifacts import (
    DATA_ARTIFACT_SCHEMA_VERSION,
    MANIFEST_FILENAME,
    ArtifactMiss,
    DataArtifact,
    LevelsArtifact,
    data_artifact_key,
    get_execution_artifacts_root,
    invalidate_data_artifact,
    invalidate_levels_artifact,
    levels_artifact_key,
    read_verified_data_artifact,
    read_verified_levels_artifact,
    resolve_contained_artifact_path,
    source_binding_key,
    write_data_artifact,
    write_levels_artifact,
)
from thesistester.persistence.local_store import (
    LEVEL_ENGINE_VERSION,
    find_matching_levels,
    list_saved_levels,
    save_levels,
)
from thesistester.research_identity import (
    LEVELS_ARTIFACT_SCHEMA_VERSION,
    DataIdentity,
    LevelsIdentity,
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-06-01 09:30:00", periods=12, freq="1min", tz="America/New_York"
            ),
            "open": [100.0 + i * 0.0 for i in range(12)],
            "high": [100.5] * 12,
            "low": [99.5] * 12,
            "close": [100.25 if i % 2 == 0 else 99.75 for i in range(12)],
            "volume": list(range(12)),
        }
    )


def _data_identity(data: pd.DataFrame, *, format_profile: str = "canonical") -> DataIdentity:
    return DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile=format_profile,
    )


def _levels_bundle(
    data: pd.DataFrame, identity: DataIdentity
) -> tuple[LevelsIdentity, dict, pd.DataFrame, pd.DataFrame]:
    result = compute_levels(data, instrument=identity.instrument, config={"poc_windows": []})
    levels_identity = LevelsIdentity.from_normalized(identity, result["levels_settings"])
    return levels_identity, result["levels_settings"], result["levels"], result["session_levels"]


def test_cold_miss_then_valid_hit(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    identity = _data_identity(data)

    miss = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"

    written = write_data_artifact(
        identity,
        data,
        ingestion_meta={"source_path": "bars.csv"},
        store_root=store,
    )
    assert isinstance(written, DataArtifact)
    assert written.artifact_key == data_artifact_key(identity)
    assert written.manifest["artifact_schema_version"] == DATA_ARTIFACT_SCHEMA_VERSION
    assert "created_at" in written.manifest
    assert "accessed_at" in written.manifest

    hit = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(hit, DataArtifact)
    pd.testing.assert_frame_equal(hit.data, data, check_dtype=False)
    assert hit.identity.dataset_id() == identity.dataset_id()


def test_format_profile_changes_data_artifact_key(tmp_path: Path):
    data = _bars()
    canonical = _data_identity(data, format_profile="canonical")
    ninja = _data_identity(data, format_profile="ninjatrader")
    assert canonical.dataset_id() == ninja.dataset_id()
    assert data_artifact_key(canonical) != data_artifact_key(ninja)

    write_data_artifact(canonical, data, store_root=tmp_path / "store")
    miss = read_verified_data_artifact(ninja, store_root=tmp_path / "store")
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"


def test_levels_artifact_roundtrip(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    data_identity = _data_identity(data)
    levels_identity, settings, levels, session_levels = _levels_bundle(data, data_identity)

    miss = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"

    written = write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )
    assert isinstance(written, LevelsArtifact)
    assert written.artifact_key == levels_artifact_key(levels_identity)

    hit = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(hit, LevelsArtifact)
    pd.testing.assert_frame_equal(hit.levels, levels, check_dtype=False)
    pd.testing.assert_frame_equal(hit.session_levels, session_levels, check_dtype=False)
    assert hit.levels_settings == settings


def test_corrupt_manifest_and_missing_parquet_are_misses(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    identity = _data_identity(data)
    written = write_data_artifact(identity, data, store_root=store)

    (written.path / MANIFEST_FILENAME).write_text("{not-json", encoding="utf-8")
    corrupt = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(corrupt, ArtifactMiss)
    assert corrupt.reason == "corrupt_manifest"

    # Repair by rewrite, then delete parquet.
    write_data_artifact(identity, data, store_root=store)
    hit = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(hit, DataArtifact)
    (hit.path / "data.parquet").unlink()
    incomplete = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(incomplete, ArtifactMiss)
    assert incomplete.reason == "incomplete"


def test_schema_drift_and_engine_version_drift_are_misses(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    data_identity = _data_identity(data)
    levels_identity, settings, levels, session_levels = _levels_bundle(data, data_identity)
    artifact = write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )

    manifest = json.loads((artifact.path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    manifest["artifact_schema_version"] = LEVELS_ARTIFACT_SCHEMA_VERSION + 99
    (artifact.path / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    schema_miss = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(schema_miss, ArtifactMiss)
    assert schema_miss.reason == "schema_drift"

    # Restore schema, break engine version.
    write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )
    repaired = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(repaired, LevelsArtifact)
    manifest = json.loads((repaired.path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    manifest["level_engine_version"] = LEVEL_ENGINE_VERSION + 7
    (repaired.path / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    engine_miss = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(engine_miss, ArtifactMiss)
    assert engine_miss.reason == "engine_incompatible"


def test_non_numeric_manifest_version_fields_are_misses_not_raises(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    data_identity = _data_identity(data)
    levels_identity, settings, levels, session_levels = _levels_bundle(data, data_identity)

    data_artifact = write_data_artifact(data_identity, data, store_root=store)
    data_manifest = json.loads((data_artifact.path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    data_manifest["artifact_schema_version"] = "not-an-int"
    (data_artifact.path / MANIFEST_FILENAME).write_text(
        json.dumps(data_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    data_miss = read_verified_data_artifact(data_identity, store_root=store)
    assert isinstance(data_miss, ArtifactMiss)
    assert data_miss.reason == "corrupt_manifest"

    levels_artifact = write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )
    levels_manifest = json.loads(
        (levels_artifact.path / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    levels_manifest["level_engine_version"] = None
    (levels_artifact.path / MANIFEST_FILENAME).write_text(
        json.dumps(levels_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    levels_miss = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(levels_miss, ArtifactMiss)
    assert levels_miss.reason == "corrupt_manifest"


def test_write_reuses_completed_artifact(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    identity = _data_identity(data)
    first = write_data_artifact(identity, data, store_root=store)
    second = write_data_artifact(identity, data, store_root=store)
    assert first.path == second.path
    assert first.manifest["created_at"] == second.manifest["created_at"]


def test_concurrent_publish_reuses_or_publishes_equivalent(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    identity = _data_identity(data)
    barrier = threading.Barrier(4)
    results: list[DataArtifact | BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=5)
        try:
            artifact = write_data_artifact(identity, data, store_root=store)
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            with lock:
                results.append(exc)
            return
        with lock:
            results.append(artifact)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker) for _ in range(4)]
        for future in futures:
            future.result(timeout=30)

    assert len(results) == 4
    assert all(isinstance(item, DataArtifact) for item in results)
    keys = {item.artifact_key for item in results}  # type: ignore[union-attr]
    paths = {item.path for item in results}  # type: ignore[union-attr]
    assert keys == {data_artifact_key(identity)}
    assert len(paths) == 1
    hit = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(hit, DataArtifact)


def test_path_containment_rejects_escape(tmp_path: Path):
    store = tmp_path / "store"
    escaped = resolve_contained_artifact_path(("..", "outside"), store_root=store)
    assert isinstance(escaped, ArtifactMiss)
    assert escaped.reason == "path_escape"

    from thesistester.persistence.execution_artifacts import _fs_path

    root = get_execution_artifacts_root(store)
    ok = resolve_contained_artifact_path(("data", "abc"), store_root=store)
    assert isinstance(ok, Path)
    assert ok == _fs_path((root / "data" / "abc").resolve())


def test_contain_path_reapplies_fs_path_after_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Windows resolve() can strip \\\\?\\; containment must re-prefix for I/O."""
    from thesistester.persistence import execution_artifacts as ea

    store = tmp_path / "store"
    root = get_execution_artifacts_root(store)
    child = root / "data" / "abc"
    child.mkdir(parents=True)

    calls: list[Path] = []
    real_fs_path = ea._fs_path

    def _track(path: Path) -> Path:
        calls.append(path)
        return real_fs_path(path)

    monkeypatch.setattr(ea, "_fs_path", _track)
    contained = ea._contain_path(child, root=root)
    assert contained is not None
    assert len(calls) >= 2  # root + path after resolve
    assert contained == real_fs_path(child.resolve())


def test_invalidate_removes_artifact(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    identity = _data_identity(data)
    write_data_artifact(identity, data, store_root=store)
    assert invalidate_data_artifact(identity, store_root=store) is True
    miss = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"
    assert invalidate_data_artifact(identity, store_root=store) is False


def test_execution_artifacts_do_not_affect_ux_saved_levels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = tmp_path / "store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))
    data = _bars()
    data_identity = _data_identity(data)
    levels_identity, settings, levels, session_levels = _levels_bundle(data, data_identity)

    write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )
    assert list_saved_levels(data_identity.dataset_id()) == []
    assert (
        find_matching_levels(
            dataset_id=data_identity.dataset_id(),
            levels_settings=settings,
        )
        is None
    )

    saved = save_levels(
        dataset_id=data_identity.dataset_id(),
        levels=levels,
        session_levels=session_levels,
        levels_settings=settings,
        levels_data_fingerprint={"instrument": "ES", "rows": len(data)},
    )
    matched = find_matching_levels(
        dataset_id=data_identity.dataset_id(),
        levels_settings=settings,
    )
    assert matched is not None
    assert matched["settings_hash"] == saved["settings_hash"]
    assert (store / "levels").exists()
    assert (store / "execution_artifacts").exists()
    assert saved["path"].startswith(str(store / "levels"))


def test_invalidate_levels_artifact(tmp_path: Path):
    store = tmp_path / "store"
    data = _bars()
    data_identity = _data_identity(data)
    levels_identity, settings, levels, session_levels = _levels_bundle(data, data_identity)
    write_levels_artifact(
        levels_identity,
        levels,
        session_levels,
        levels_settings=settings,
        store_root=store,
    )
    assert invalidate_levels_artifact(levels_identity, store_root=store) is True
    miss = read_verified_levels_artifact(levels_identity, store_root=store)
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"


def test_source_binding_key_separates_ingestion_mode_and_derivation_policy():
    common = {
        "source_content_hash_value": "deadbeef",
        "instrument": "ES",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "format_profile": "quantower_history_exporter",
    }
    primary = source_binding_key(**common, ingestion_mode="primary", derivation_policy=None)
    derive = source_binding_key(
        **common,
        ingestion_mode=INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        derivation_policy=DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1,
    )
    other_policy = source_binding_key(
        **common,
        ingestion_mode=INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        derivation_policy="different_policy",
    )
    assert primary != derive
    assert derive != other_policy
    assert primary == source_binding_key(**common)


def test_fsync_file_swallows_ebadf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from thesistester.persistence import execution_artifacts as ea

    path = tmp_path / "artifact.json"
    path.write_text("{}", encoding="utf-8")

    def _boom(_fd: int) -> None:
        raise OSError(9, "Bad file descriptor")

    monkeypatch.setattr(ea.os, "fsync", _boom)
    ea._fsync_file(path)


def test_fsync_file_opens_rdwr_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from thesistester.persistence import execution_artifacts as ea

    path = tmp_path / "artifact.json"
    path.write_text("{}", encoding="utf-8")
    seen: dict[str, int] = {}
    real_open = ea.os.open

    def _spy(name, flags, *args, **kwargs):
        seen["flags"] = int(flags)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(ea.os, "name", "nt")
    monkeypatch.setattr(ea.os, "open", _spy)
    ea._fsync_file(path)
    assert seen["flags"] & ea.os.O_RDWR
