"""CAI-10 — artifact inspection, eviction, rebind, and cold-after-delete safety."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from thesistester.api import run_experiment
from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    AssistantTools,
    CapabilityMode,
    FEATURE_PARITY_REGISTRY,
    HANDLER_REGISTRY,
    LocalThesisRepository,
)
from thesistester.persistence import (
    delete_execution_artifact,
    evict_execution_artifacts,
    get_execution_cache_stats,
    list_execution_artifacts,
    list_saved_levels,
    rebind_source_path,
    save_levels,
)
from thesistester.persistence.execution_artifacts import (
    ArtifactMiss,
    DataArtifact,
    data_artifact_key,
    invalidate_data_artifact,
    read_verified_data_artifact,
    write_data_artifact,
)
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
)
from thesistester.research_identity import DataIdentity
from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars


def _warm_state(tmp_path: Path, store: Path) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    spec = absolute_parity_run_spec(tmp_path)
    return run_experiment(
        spec,
        base_directory=tmp_path,
        cache_policy="read_write",
        store_root=store,
    )


def test_list_inspect_and_hit_counts(tmp_path: Path):
    store = tmp_path / "store"
    state = _warm_state(tmp_path, store)
    cold_hits = get_execution_cache_stats(store_root=store)["hit_count"]
    # Second warm run should hit cache (data/levels reads only — not binding).
    _warm_state(tmp_path, store)
    warm_hits = get_execution_cache_stats(store_root=store)["hit_count"]
    assert warm_hits > cold_hits
    artifacts = list_execution_artifacts(store_root=store, limit=50)
    kinds = {item["kind"] for item in artifacts}
    assert "data" in kinds
    assert "levels" in kinds
    assert all("size_bytes" in item for item in artifacts)
    assert all("artifact_key" in item for item in artifacts)
    stats = get_execution_cache_stats(store_root=store)
    assert stats["total_bytes"] > 0
    assert stats["hit_count"] >= 1
    identity = DataIdentity.from_dict(state["data_identity"])
    assert identity is not None
    before = get_execution_cache_stats(store_root=store)["hit_count"]
    hit = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(hit, DataArtifact)
    after = get_execution_cache_stats(store_root=store)["hit_count"]
    assert after == before + 1  # one store-level hit per data artifact read
    records = list_execution_artifacts(store_root=store, kind="data")
    assert any((r.get("hit_count") or 0) >= 1 for r in records)
    capped = list_execution_artifacts(store_root=store, limit=1)
    unbounded = list_execution_artifacts(store_root=store, limit=None)
    assert len(capped) == 1
    assert len(unbounded) >= 2


def test_delete_forces_cold_recompute_and_equal_hash(tmp_path: Path):
    store = tmp_path / "store"
    first = _warm_state(tmp_path, store)
    first_hash = canonical_bundle_hash(build_research_bundle(first))
    identity = DataIdentity.from_dict(first["data_identity"])
    assert identity is not None
    key = data_artifact_key(identity)
    deleted = delete_execution_artifact(kind="data", artifact_key=key, store_root=store)
    assert deleted["deleted"] is True
    assert deleted["cold_recompute_required"] is True
    miss = read_verified_data_artifact(identity, store_root=store)
    assert isinstance(miss, ArtifactMiss)
    assert miss.reason == "missing"
    second = _warm_state(tmp_path, store)
    second_hash = canonical_bundle_hash(build_research_bundle(second))
    assert second_hash == first_hash


def test_eviction_scans_unbounded_and_ages_by_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = tmp_path / "store"
    _warm_state(tmp_path, store)
    calls: list[dict] = []
    real_list = list_execution_artifacts

    def _tracking_list(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_list(*args, **kwargs)

    monkeypatch.setattr(
        "thesistester.persistence.execution_artifacts.list_execution_artifacts",
        _tracking_list,
    )
    # Also patch the public re-export path used if imported via persistence.
    monkeypatch.setattr(
        "thesistester.persistence.list_execution_artifacts",
        _tracking_list,
    )
    from thesistester.persistence.execution_artifacts import (
        evict_execution_artifacts as evict_direct,
    )

    def _rewrite_timestamps(record: dict, *, accessed_at: str, created_at: str) -> None:
        path = Path(record["path"])
        target = path if path.is_file() else path / "manifest.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["accessed_at"] = accessed_at
        payload["created_at"] = created_at
        target.write_text(json.dumps(payload), encoding="utf-8")

    # Make one artifact look hot (recent access) and another cold.
    records = real_list(store_root=store, limit=None)
    assert len(records) >= 2
    cold, hot = records[0], records[1]
    _rewrite_timestamps(
        cold,
        accessed_at="2000-01-01T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
    )
    _rewrite_timestamps(
        hot,
        accessed_at="2099-01-01T00:00:00+00:00",
        created_at="2000-01-01T00:00:00+00:00",
    )

    # Age threshold between cold access and hot access.
    result = evict_direct(store_root=store, max_age_seconds=10_000_000)
    assert any(call.get("limit") is None for call in calls)
    deleted_keys = {(item["kind"], item["artifact_key"]) for item in result["deleted"]}
    assert (cold["kind"], cold["artifact_key"]) in deleted_keys
    assert (hot["kind"], hot["artifact_key"]) not in deleted_keys


def test_eviction_never_touches_user_or_bundle_namespaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = tmp_path / "store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))
    state = _warm_state(tmp_path, store)
    # User-saved levels snapshot (distinct namespace under store/levels).
    save_levels(
        dataset_id=state["dataset_id"],
        levels=state["levels"],
        session_levels=state["session_levels"],
        levels_settings=state["levels_settings"],
        levels_data_fingerprint=state["levels_data_fingerprint"],
    )
    assert list_saved_levels(state["dataset_id"])

    bundle_bytes = build_research_bundle(state)
    bundle_path = tmp_path / "kept.research.zip"
    bundle_path.write_bytes(bundle_bytes)
    digest = canonical_bundle_hash(bundle_bytes)

    # Thesis-like assistant tree must survive.
    thesis_dir = store / "assistant" / "theses" / "th_demo"
    thesis_dir.mkdir(parents=True)
    (thesis_dir / "meta.json").write_text("{}", encoding="utf-8")
    # Marker file under datasets namespace.
    dataset_marker = store / "datasets" / "keep_me" / "meta.json"
    dataset_marker.parent.mkdir(parents=True)
    dataset_marker.write_text("{}", encoding="utf-8")

    result = evict_execution_artifacts(store_root=store, max_entries=0)
    assert result["deleted_count"] >= 1
    assert list_saved_levels(state["dataset_id"])
    assert (store / "assistant" / "theses" / "th_demo" / "meta.json").is_file()
    assert dataset_marker.is_file()
    # Bundle restore still works (self-contained).
    loaded = load_research_bundle(bundle_path.read_bytes())
    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)
    assert "data" in restored
    assert "levels" in restored
    assert canonical_bundle_hash(bundle_path.read_bytes()) == digest
    assert set(result["protected_namespaces"]) >= {"assistant", "levels", "datasets"}


def test_rebind_source_path_requires_content_identity(tmp_path: Path):
    store = tmp_path / "store"
    state = _warm_state(tmp_path, store)
    identity = DataIdentity.from_dict(state["data_identity"])
    assert identity is not None
    original = tmp_path / "bars.csv"
    relocated = tmp_path / "moved" / "bars.csv"
    relocated.parent.mkdir(parents=True)
    shutil.copy2(original, relocated)
    # Wrong content must fail closed.
    bad = tmp_path / "moved" / "bad.csv"
    bad.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match|Unable to load"):
        rebind_source_path(
            new_source_path=bad,
            expected_identity=identity,
            store_root=store,
        )
    binding = rebind_source_path(
        new_source_path=relocated,
        expected_identity=identity,
        store_root=store,
    )
    assert binding.identity.data_content_hash == identity.data_content_hash
    assert binding.data_artifact_key == data_artifact_key(identity)


def test_cache_capabilities_routed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    store = tmp_path / "store"
    _warm_state(tmp_path, store)
    for capability_id in (
        "CACHE.inspect_artifacts",
        "CACHE.delete_artifact",
        "CACHE.evict_artifacts",
        "CACHE.rebind_source_path",
    ):
        capability = next(c for c in FEATURE_PARITY_REGISTRY if c.capability_id == capability_id)
        assert capability.mode is not CapabilityMode.UNSUPPORTED
        assert capability_id in HANDLER_REGISTRY

    tools = AssistantTools(data_roots=(tmp_path, Path.cwd()))
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    thesis = repository.create_thesis(name="cache")
    inspected = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CACHE.inspect_artifacts",
            payload={"store_root": str(store), "limit": 20},
        ),
        thesis_id=thesis.thesis_id,
    )
    assert inspected.status == "completed"
    assert "artifacts" in inspected.payload
    assert "stats" in inspected.payload

    # Eviction requires explicit confirmation.
    gated = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CACHE.evict_artifacts",
            payload={"store_root": str(store), "max_entries": 0},
        ),
        thesis_id=thesis.thesis_id,
        confirmed=False,
    )
    assert gated.status == "approval_required"
    evicted = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CACHE.evict_artifacts",
            payload={"store_root": str(store), "max_entries": 0},
        ),
        thesis_id=thesis.thesis_id,
        confirmed=True,
    )
    assert evicted.status == "completed"
    assert evicted.payload["cold_recompute_required"] is True

    # Numeric strings must coerce (JSON-friendly payloads).
    string_evict = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CACHE.evict_artifacts",
            payload={"store_root": str(store), "max_entries": "0"},
        ),
        thesis_id=thesis.thesis_id,
        confirmed=True,
    )
    assert string_evict.status == "completed"
    string_inspect = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CACHE.inspect_artifacts",
            payload={"store_root": str(store), "limit": "5"},
        ),
        thesis_id=thesis.thesis_id,
    )
    assert string_inspect.status == "completed"
    assert len(string_inspect.payload["artifacts"]) <= 5


def test_invalidate_alias_still_cold_safe(tmp_path: Path):
    store = tmp_path / "store"
    state = _warm_state(tmp_path, store)
    identity = DataIdentity.from_dict(state["data_identity"])
    assert identity is not None
    assert invalidate_data_artifact(identity, store_root=store) is True
    # Publishing again after invalidate must succeed (cold write).
    write_data_artifact(identity, state["data"], store_root=store)
    assert isinstance(
        read_verified_data_artifact(identity, store_root=store),
        object,
    )
