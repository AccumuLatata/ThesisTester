from pathlib import Path

import pytest

from thesistester.assistant import AssistantOrchestrator, LocalThesisRepository


class _BundleTools:
    def run_experiment_to_bundle(self, spec, *, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"bundle")
        return {
            "bundle_path": str(output_path),
            "canonical_bundle_hash": "a" * 64,
            "dataset_fingerprint": {"rows": 10},
            "tool_version": "test",
            "summary": {"warnings": {"intrabar": "assumption"}},
        }


def test_confirmed_spec_runs_and_persists_bundle_provenance(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Lifecycle")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={"dataset": {}, "setup": {}, "backtest": {}},
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    orchestrator = AssistantOrchestrator(tools=_BundleTools(), repository=repository)

    result = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "bundles" / "run.research.zip",
    )

    restored = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    assert restored.status == "completed"
    assert restored.provenance["canonical_bundle_hash"] == "a" * 64
    assert restored.warnings == ("intrabar: assumption",)
    assert Path(restored.provenance["bundle_path"]).read_bytes() == b"bundle"


def test_unconfirmed_or_failed_run_has_safe_terminal_state(tmp_path):
    class FailingTools:
        def run_experiment_to_bundle(self, spec, *, output_path):
            raise RuntimeError("fixture execution failure")

    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Failure")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={"dataset": {}, "setup": {}, "backtest": {}},
        status="ready_for_confirmation",
    )
    orchestrator = AssistantOrchestrator(tools=FailingTools(), repository=repository)

    with pytest.raises(ValueError, match="confirmed"):
        orchestrator.execute_confirmed_run(
            thesis_id=thesis.thesis_id,
            spec_version=draft.version,
            output_path=tmp_path / "run.zip",
        )

    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    with pytest.raises(RuntimeError, match="fixture"):
        orchestrator.execute_confirmed_run(
            thesis_id=thesis.thesis_id,
            spec_version=confirmed.version,
            output_path=tmp_path / "run.zip",
        )
    failed = repository.list_runs(thesis.thesis_id)[0]
    assert failed.status == "failed"
    assert failed.error["type"] == "RuntimeError"
