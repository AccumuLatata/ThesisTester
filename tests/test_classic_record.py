"""CAI-6 — register a completed classic bundle as a thesis run."""

from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from thesistester.api import run_experiment
from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantTools,
    LocalThesisRepository,
    OrchestrationStatus,
)
from thesistester.assistant.explainer import build_evidence_packet
from thesistester.classic_export import classic_state_to_run_spec
from thesistester.classic_record import (
    classic_export_session_state,
    classic_session_ready_for_record,
    classic_session_registration_gaps,
    materialize_classic_source_csv,
    record_classic_session_run,
    resolve_classic_record_source,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import DataIdentity
from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars


def _classic_completed_state(tmp_path: Path) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    spec = absolute_parity_run_spec(tmp_path)
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    # Classic pages expose source path separately from RunSpec dataset.path.
    state["dataset_source_path"] = str(tmp_path / "bars.csv")
    # Headless run_experiment does not populate Backtest widget keys; mirror the
    # classic page contract by stamping the executable backtest policy explicitly.
    state["backtest_config"] = deepcopy(spec["backtest"])
    state["dataset_id"] = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    ).dataset_id()
    return state


def _orchestrator(tmp_path: Path) -> tuple[AssistantOrchestrator, LocalThesisRepository]:
    repository = LocalThesisRepository(tmp_path / "assistant")
    tools = AssistantTools(data_roots=(tmp_path, Path.cwd()))
    return AssistantOrchestrator(tools=tools, repository=repository), repository


def test_register_external_bundle_preserves_hash_and_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="classic attach")

    bundle_bytes = build_research_bundle(state)
    original_hash = canonical_bundle_hash(bundle_bytes)
    original_packet = build_evidence_packet(
        state,
        provenance={
            "bundle_path": str(tmp_path / "classic.research.zip"),
            "canonical_bundle_hash": original_hash,
            "execution_origin": "classic",
        },
    ).to_dict()

    bundle_path = tmp_path / "classic.research.zip"
    bundle_path.write_bytes(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state,
        name=thesis.name,
        source_path=state["dataset_source_path"],
        store_root=tmp_path / "store",
    )

    result = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=bundle_path,
        run_spec=run_spec,
        expected_hash=original_hash,
    )
    assert result.status == OrchestrationStatus.COMPLETED.value
    assert result.payload["idempotent"] is False
    assert result.payload["execution_origin"] == "classic"
    assert result.payload["canonical_bundle_hash"] == original_hash

    run = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    assert run.status == "completed"
    assert run.provenance["execution_origin"] == "classic"
    assert run.provenance["canonical_bundle_hash"] == original_hash
    assert Path(run.provenance["bundle_path"]).read_bytes() == bundle_bytes

    explained = orchestrator.explain_run(
        thesis_id=thesis.thesis_id,
        conversation_id=None,
        run=run,
    )
    assert explained.status == OrchestrationStatus.COMPLETED.value
    packet = explained.payload["evidence"]
    assert packet["results"] == original_packet["results"]
    assert packet["provenance"]["canonical_bundle_hash"] == original_hash


def test_register_external_bundle_is_idempotent_by_hash(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="idempotent")
    bundle_bytes = build_research_bundle(state)
    digest = canonical_bundle_hash(bundle_bytes)
    path = tmp_path / "once.research.zip"
    path.write_bytes(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )

    first = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    second = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    assert second.payload["idempotent"] is True
    assert second.payload["run_id"] == first.payload["run_id"]
    assert second.payload["bundle_path"] == first.payload["bundle_path"]
    assert len(repository.list_runs(thesis.thesis_id)) == 1

    forced = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=digest,
        force_new=True,
    )
    assert forced.payload["idempotent"] is False
    assert forced.payload["run_id"] != first.payload["run_id"]
    assert len(repository.list_runs(thesis.thesis_id)) == 2


def test_idempotent_reuse_requires_readable_stored_bundle(tmp_path: Path, monkeypatch):
    """Missing stored provenance must not return a hollow idempotent reuse."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="missing stored")
    bundle_bytes = build_research_bundle(state)
    digest = canonical_bundle_hash(bundle_bytes)
    first_path = tmp_path / "first.research.zip"
    first_path.write_bytes(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )

    first = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=first_path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    stored = Path(first.payload["bundle_path"])
    assert stored.is_file()
    stored.unlink()

    replacement = tmp_path / "replacement.research.zip"
    replacement.write_bytes(bundle_bytes)
    recovered = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=replacement,
        run_spec=run_spec,
        expected_hash=digest,
    )
    assert recovered.payload["idempotent"] is False
    assert recovered.payload["run_id"] != first.payload["run_id"]
    assert Path(recovered.payload["bundle_path"]).is_file()
    assert len(repository.list_runs(thesis.thesis_id)) == 2

    explained = orchestrator.explain_run(
        thesis_id=thesis.thesis_id,
        conversation_id=None,
        run=repository.get_run(thesis.thesis_id, recovered.payload["run_id"]),
    )
    assert explained.status == "completed"


def test_idempotent_reuse_reports_stored_execution_origin(tmp_path: Path, monkeypatch):
    """Reuse must not rewrite a non-classic run's origin as classic."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="origin reuse")
    bundle_bytes = build_research_bundle(state)
    digest = canonical_bundle_hash(bundle_bytes)
    path = tmp_path / "assistant_origin.research.zip"
    path.write_bytes(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )
    confirmed = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=run_spec,
        confirmation_note="assistant fixture",
    )
    run = repository.start_run(
        thesis.thesis_id,
        spec_version=confirmed.version,
        request={"action": "assistant_fixture"},
    )
    repository.complete_run(
        thesis.thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={
            "bundle_path": str(path),
            "canonical_bundle_hash": digest,
            "execution_origin": "assistant",
        },
    )

    reused = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    assert reused.payload["idempotent"] is True
    assert reused.payload["run_id"] == run.run_id
    assert reused.payload["execution_origin"] == "assistant"
    stored = repository.get_run(thesis.thesis_id, run.run_id)
    assert stored.provenance["execution_origin"] == "assistant"


def test_idempotent_reuse_skips_stale_match_for_readable_twin(tmp_path: Path, monkeypatch):
    """A stale oldest match must not block reuse of a later readable twin."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="stale then readable")
    bundle_bytes = build_research_bundle(state)
    digest = canonical_bundle_hash(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )

    first_path = tmp_path / "stale.research.zip"
    first_path.write_bytes(bundle_bytes)
    first = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=first_path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    Path(first.payload["bundle_path"]).unlink()

    second_path = tmp_path / "readable.research.zip"
    second_path.write_bytes(bundle_bytes)
    second = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=second_path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    assert second.payload["idempotent"] is False
    assert second.payload["run_id"] != first.payload["run_id"]

    third_path = tmp_path / "again.research.zip"
    third_path.write_bytes(bundle_bytes)
    third = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=third_path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    assert third.payload["idempotent"] is True
    assert third.payload["run_id"] == second.payload["run_id"]
    assert third.payload["bundle_path"] == second.payload["bundle_path"]
    assert len(repository.list_runs(thesis.thesis_id)) == 2


def test_record_classic_session_run_honors_store_root(tmp_path: Path, monkeypatch):
    """Bundle writes must use the same store_root as export/staging."""
    env_store = tmp_path / "env_store"
    explicit_store = tmp_path / "explicit_store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(env_store))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="store root")

    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=explicit_store,
    )
    bundle_path = Path(result.payload["bundle_path"]).resolve()
    assert explicit_store.resolve() in bundle_path.parents
    assert env_store.resolve() not in bundle_path.parents
    assert bundle_path.is_file()


def test_record_classic_session_run_cleans_orphan_zip_on_idempotent_reuse(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="orphan cleanup")
    store = tmp_path / "store"

    first = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=store,
    )
    first_path = Path(first.payload["bundle_path"])
    assert first_path.is_file()
    before = {path.resolve() for path in first_path.parent.glob("*.research.zip")}

    again = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=store,
    )
    assert again.payload["idempotent"] is True
    assert again.payload["run_id"] == first.payload["run_id"]
    after = {path.resolve() for path in first_path.parent.glob("*.research.zip")}
    assert after == before
    assert first_path.resolve() in after
    assert len(repository.list_runs(thesis.thesis_id)) == 1


def test_record_preflight_requires_complete_bundle_sections(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    assert classic_session_registration_gaps(state) == []
    assert classic_session_ready_for_record(state)

    incomplete = deepcopy(state)
    del incomplete["signals"]
    assert "signals" in classic_session_registration_gaps(incomplete)
    assert not classic_session_ready_for_record(incomplete)

    orchestrator, _repository = _orchestrator(tmp_path)
    thesis = _repository.create_thesis(name="preflight")
    with pytest.raises(ValueError, match="Missing: signals"):
        record_classic_session_run(
            orchestrator,
            thesis_id=thesis.thesis_id,
            session_state=incomplete,
            store_root=tmp_path / "store",
        )


def test_record_failed_register_removes_orphan_zip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="failed register")
    store = tmp_path / "store"
    bundles = store / "assistant" / "theses" / thesis.thesis_id / "bundles"

    def _boom(*_args, **_kwargs):
        raise RuntimeError("registration exploded")

    monkeypatch.setattr(orchestrator, "register_external_bundle_run", _boom)
    with pytest.raises(RuntimeError, match="registration exploded"):
        record_classic_session_run(
            orchestrator,
            thesis_id=thesis.thesis_id,
            session_state=state,
            store_root=store,
        )
    assert not bundles.exists() or list(bundles.glob("*.research.zip")) == []


def test_record_cancelled_register_keeps_attached_bundle(tmp_path: Path, monkeypatch):
    """Cancel races may attach provenance; do not delete that zip."""
    from thesistester.assistant import OrchestrationResult

    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="cancelled keep")
    store = tmp_path / "store"
    bundles = store / "assistant" / "theses" / thesis.thesis_id / "bundles"
    captured: dict[str, Path] = {}

    def _cancel(**kwargs):
        captured["path"] = Path(kwargs["bundle_path"]).resolve()
        return OrchestrationResult(
            status="cancelled",
            capability_id="BUNDLE.register_external_run",
            payload={
                "run_id": "run_cancelled",
                "error": {"message": "Cancelled during execution."},
            },
        )

    monkeypatch.setattr(orchestrator, "register_external_bundle_run", _cancel)
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=store,
    )
    assert result.status == "cancelled"
    assert captured["path"].is_file()
    assert captured["path"].parent == bundles.resolve()


def test_idempotent_reuse_rejects_run_spec_drift(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="spec drift")
    bundle_bytes = build_research_bundle(state)
    digest = canonical_bundle_hash(bundle_bytes)
    path = tmp_path / "drift.research.zip"
    path.write_bytes(bundle_bytes)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )

    first = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=digest,
    )
    drifted = deepcopy(run_spec)
    drifted["backtest"] = {
        **dict(drifted["backtest"]),
        "stop_loss_ticks": int(drifted["backtest"]["stop_loss_ticks"]) + 1,
    }
    second = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=drifted,
        expected_hash=digest,
    )
    assert second.payload["idempotent"] is False
    assert second.payload["run_id"] != first.payload["run_id"]
    assert len(repository.list_runs(thesis.thesis_id)) == 2


def test_register_fails_closed_on_tamper_missing_and_out_of_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="fail closed")
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )
    good = tmp_path / "good.research.zip"
    raw = build_research_bundle(state)
    good.write_bytes(raw)
    digest = canonical_bundle_hash(raw)

    with pytest.raises(Exception, match="hash|Bundle"):
        orchestrator.register_external_bundle_run(
            thesis_id=thesis.thesis_id,
            bundle_path=good,
            run_spec=run_spec,
            expected_hash="0" * 64,
        )

    missing = tmp_path / "missing.research.zip"
    with pytest.raises(Exception, match="does not exist|outside"):
        orchestrator.register_external_bundle_run(
            thesis_id=thesis.thesis_id,
            bundle_path=missing,
            run_spec=run_spec,
            expected_hash=digest,
        )

    outside = Path("/tmp") / f"thesistester-cai6-{tmp_path.name}.zip"
    outside.write_bytes(raw)
    try:
        with pytest.raises(Exception, match="outside"):
            orchestrator.register_external_bundle_run(
                thesis_id=thesis.thesis_id,
                bundle_path=outside,
                run_spec=run_spec,
                expected_hash=digest,
            )
    finally:
        outside.unlink(missing_ok=True)

    # Corrupt zip fails closed.
    corrupt = tmp_path / "corrupt.research.zip"
    corrupt.write_bytes(b"not-a-zip")
    with pytest.raises(Exception, match="corrupt|invalid|zip"):
        orchestrator.register_external_bundle_run(
            thesis_id=thesis.thesis_id,
            bundle_path=corrupt,
            run_spec=run_spec,
        )

    # Bundle missing required backtest section fails closed.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "kind": "thesistester_research_bundle",
                    "bundle_schema_version": 1,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "included": {
                        "dataset": False,
                        "levels": False,
                        "signals": False,
                        "backtest": False,
                    },
                    "session_keys": [],
                }
            ),
        )
    incomplete = tmp_path / "incomplete.research.zip"
    incomplete.write_bytes(buffer.getvalue())
    with pytest.raises(Exception, match="requires bundle sections|Missing"):
        orchestrator.register_external_bundle_run(
            thesis_id=thesis.thesis_id,
            bundle_path=incomplete,
            run_spec=run_spec,
        )


def test_register_does_not_recompute_or_bypass_future_confirmation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="no recompute")
    calls: list[str] = []

    original = AssistantTools.run_experiment_to_bundle

    def _spy(self, spec, *, output_path):
        calls.append("run")
        return original(self, spec, output_path=output_path)

    monkeypatch.setattr(AssistantTools, "run_experiment_to_bundle", _spy)

    path = tmp_path / "norecompute.research.zip"
    raw = build_research_bundle(state)
    path.write_bytes(raw)
    run_spec = classic_state_to_run_spec(
        state, name=thesis.name, source_path=state["dataset_source_path"]
    )
    result = orchestrator.register_external_bundle_run(
        thesis_id=thesis.thesis_id,
        bundle_path=path,
        run_spec=run_spec,
        expected_hash=canonical_bundle_hash(raw),
    )
    assert calls == []
    assert result.payload["execution_origin"] == "classic"

    # Future recomputation still requires the explicit execute_confirmed_run path.
    confirmed_versions = [
        spec.version
        for spec in repository.list_spec_versions(thesis.thesis_id)
        if spec.status == "confirmed"
    ]
    assert confirmed_versions
    # execute_confirmed_run remains confirmation-gated at the capability level and
    # will invoke tools — registration must not have already executed it.
    assert not any(
        isinstance(run.request, dict) and run.request.get("action") != "register_external_bundle"
        for run in repository.list_runs(thesis.thesis_id)
    )


def test_record_classic_session_run_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    assert classic_session_ready_for_record(state)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="session record")

    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    assert result.status == OrchestrationStatus.COMPLETED.value
    run = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    assert run.provenance["execution_origin"] == "classic"
    assert Path(run.provenance["bundle_path"]).is_file()

    # Materialized source path works when classic pages omit dataset_source_path.
    state_no_path = deepcopy(state)
    state_no_path.pop("dataset_source_path", None)
    state_no_path.pop("source_csv_path", None)
    materialized = materialize_classic_source_csv(
        state_no_path, output_dir=tmp_path / "materialized"
    )
    assert materialized.is_file()
    again = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state_no_path,
        store_root=tmp_path / "store",
        force_new=True,
    )
    assert again.status == OrchestrationStatus.COMPLETED.value


def test_materialized_vendor_session_exports_canonical_format_profile(tmp_path: Path):
    """Streamlit vendor uploads leave no durable path; lineage CSV is always canonical.

    Reproduces the Quantower Record-and-discuss failure where a materialized
    comma-separated classic_source.csv was verified with sep=';'.
    """
    state = _classic_completed_state(tmp_path)
    state["format_profile"] = "quantower_history_exporter"
    state.pop("dataset_source_path", None)
    state.pop("source_csv_path", None)

    source = resolve_classic_record_source(state, materialize_dir=tmp_path / "staging")
    assert source.materialized is True
    assert source.format_profile == "canonical"
    assert Path(source.path).read_text(encoding="utf-8").splitlines()[0] == (
        "timestamp,open,high,low,close,volume"
    )

    export_state = classic_export_session_state(state, source)
    assert export_state["format_profile"] == "canonical"
    assert state["format_profile"] == "quantower_history_exporter"

    run_spec = classic_state_to_run_spec(
        export_state,
        name="vendor materialize",
        source_path=source.path,
        store_root=tmp_path / "store",
    )
    assert run_spec["dataset"]["format_profile"] == "canonical"
    assert run_spec["dataset"]["path"] == source.path


def test_export_overlay_normalizes_whitespace_format_profile(tmp_path: Path):
    """Raw session profile must be rewritten when it only matches after strip."""
    state = _classic_completed_state(tmp_path)
    state["format_profile"] = "  canonical  "
    state.pop("dataset_source_path", None)
    source = resolve_classic_record_source(state, materialize_dir=tmp_path / "staging")
    assert source.format_profile == "canonical"
    export_state = classic_export_session_state(state, source)
    assert export_state["format_profile"] == "canonical"
    assert state["format_profile"] == "  canonical  "


def test_record_quantower_session_without_source_path(tmp_path: Path, monkeypatch):
    """Record and discuss must succeed for Quantower sessions with no source path.

    Dual provenance is intentional after materialization:
    - RunSpec ``dataset.format_profile`` is canonical (lineage CSV parser)
    - Bundle / provenance ``data_identity.format_profile`` keep the ingest profile
      so CAI-8 page badges stay ``exact_match``
    """
    from zipfile import ZipFile
    import json

    from thesistester.api import load_dataset
    from thesistester.research_identity import (
        classify_identity_relation,
        identities_from_payload,
        try_page_data_identity,
        try_page_levels_identity,
    )

    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _classic_completed_state(tmp_path)
    vendor_identity = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
    )
    state["format_profile"] = "quantower_history_exporter"
    state["data_identity"] = vendor_identity.to_dict()
    state["dataset_id"] = vendor_identity.dataset_id()
    page_levels = try_page_levels_identity(state)
    if page_levels is not None:
        state["levels_identity"] = page_levels.to_dict()
    state.pop("dataset_source_path", None)
    state.pop("source_csv_path", None)

    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="quantower record")
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    assert result.status == OrchestrationStatus.COMPLETED.value
    run = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    request = run.request if isinstance(run.request, dict) else {}
    run_spec = request.get("run_spec") or {}
    dataset = run_spec.get("dataset") if isinstance(run_spec, dict) else {}
    assert dataset.get("format_profile") == "canonical"
    lineage_path = Path(str(dataset.get("path", "")))
    assert lineage_path.name == "classic_source.csv"
    load_dataset(
        lineage_path,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    )

    # Ingest profile preserved for badges / bundle meta.
    assert (run.provenance.get("data_identity") or {}).get(
        "format_profile"
    ) == "quantower_history_exporter"
    with ZipFile(run.provenance["bundle_path"]) as zf:
        meta = json.loads(zf.read("dataset_meta.json"))
    assert meta.get("format_profile") == "quantower_history_exporter"
    run_data, run_levels = identities_from_payload(run.provenance)
    assert (
        classify_identity_relation(
            try_page_levels_identity(state),
            run_levels,
            page_data=try_page_data_identity(state),
            run_data=run_data,
        )
        == "exact_match"
    )


def test_pages_wire_record_and_discuss():
    root = Path(__file__).resolve().parents[1]
    backtest = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    bundles = (root / "pages" / "12_Research_Bundles.py").read_text(encoding="utf-8")
    assert "render_record_and_discuss" in backtest
    assert "render_record_and_discuss" in bundles
    context = (root / "thesistester" / "classic_context.py").read_text(encoding="utf-8")
    assert "register_external_bundle_run" not in context
    assert "record_classic_session_run" not in context


def test_registry_routes_register_external_run():
    from thesistester.assistant import FEATURE_PARITY_REGISTRY, HANDLER_REGISTRY
    from thesistester.assistant.contracts import CapabilityMode, ConfirmationLevel
    from thesistester.assistant.registry_audit import audit_capability_registry

    capability = next(
        item
        for item in FEATURE_PARITY_REGISTRY
        if item.capability_id == "BUNDLE.register_external_run"
    )
    assert capability.mode is CapabilityMode.IMPORT_EXPORT
    assert capability.confirmation is ConfirmationLevel.EXPLICIT_CONFIRMATION
    assert "BUNDLE.register_external_run" in HANDLER_REGISTRY
    assert all(row.status != "invalid" for row in audit_capability_registry())


def test_dispatch_requires_confirmation_for_register(tmp_path: Path):
    orchestrator, _repository = _orchestrator(tmp_path)
    from thesistester.assistant import AssistantRequest

    result = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BUNDLE.register_external_run",
            payload={"bundle_path": str(tmp_path / "x.zip")},
        ),
        confirmed=False,
    )
    assert result.status == OrchestrationStatus.APPROVAL_REQUIRED.value
