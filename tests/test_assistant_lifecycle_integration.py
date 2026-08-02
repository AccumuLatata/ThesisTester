from pathlib import Path

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
