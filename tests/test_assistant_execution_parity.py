"""Real execution parity and provenance fail-closed gates (C2-3).

Proves API, CLI composition, assistant tools, and the confirmed-run lifecycle
emit the same canonical research-bundle hash for one fixed fixture, then
verifies restoration and hash-mismatch rejection without touching golden masters.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from tests.fixtures.assistant_parity import (
    PARITY_RUN_NAME,
    absolute_parity_run_spec,
    clone_spec,
    parity_cli_experiment,
    parity_run_spec,
    write_parity_bars,
)
from thesistester.api import run_experiment
from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    LocalThesisRepository,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools
from thesistester.cli import run_batch
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash


def _parity_choices(root: Path) -> dict:
    """Return confirmable structured choices rooted at ``root``."""
    spec = absolute_parity_run_spec(root)
    return {key: value for key, value in spec.items() if key != "name"}


def _confirm_parity_run(repository: LocalThesisRepository, thesis_id: str, root: Path):
    draft = repository.create_spec_version(
        thesis_id,
        normalized_run_spec=_parity_choices(root),
        status="ready_for_confirmation",
    )
    return repository.confirm_spec_version(thesis_id, draft.version)


def _write_replacement_bundle(path: Path) -> bytes:
    """Write a different portable zip so the canonical digest diverges."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "kind": "research_bundle",
                    "bundle_schema_version": 1,
                    "created_at": "replacement",
                    "app_version": "parity-test",
                    "included": {},
                    "session_keys": [],
                },
                sort_keys=True,
            ),
        )
    raw = buffer.getvalue()
    path.write_bytes(raw)
    return raw


def test_api_cli_and_assistant_canonical_hashes_match(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    relative_spec = parity_run_spec(dataset_path="bars.csv")

    api_state = run_experiment(clone_spec(relative_spec), base_directory=tmp_path)
    api_hash = canonical_bundle_hash(build_research_bundle(api_state))

    cli_index = run_batch(
        parity_cli_experiment(),
        base_directory=tmp_path,
        output_directory=tmp_path / "cli_batch",
        workers=1,
    )
    cli_hash = str(cli_index.iloc[0]["bundle_hash"])
    cli_bundle = tmp_path / "cli_batch" / f"{PARITY_RUN_NAME}.research.zip"
    assert cli_bundle.is_file()
    assert canonical_bundle_hash(cli_bundle.read_bytes()) == cli_hash

    experiment_path = tmp_path / "experiment.yaml"
    experiment_path.write_text(
        yaml.safe_dump(parity_cli_experiment(), sort_keys=False),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesistester",
            "run",
            str(experiment_path),
            "--workers",
            "1",
            "--output-dir",
            str(tmp_path / "cli_module"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Completed 1 run" in completed.stdout
    module_bundle = tmp_path / "cli_module" / f"{PARITY_RUN_NAME}.research.zip"
    module_hash = canonical_bundle_hash(module_bundle.read_bytes())

    tools = AssistantTools(data_roots=(tmp_path,))
    tool_result = tools.run_experiment_to_bundle(
        absolute_parity_run_spec(tmp_path),
        output_path=tmp_path / "assistant_tools.research.zip",
    )

    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)
    lifecycle = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "assistant_lifecycle.research.zip",
    )

    hashes = {
        api_hash,
        cli_hash,
        module_hash,
        tool_result["canonical_bundle_hash"],
        lifecycle.payload["canonical_bundle_hash"],
    }
    assert len(hashes) == 1
    assert lifecycle.status == "completed"
    restored = repository.get_run(thesis.thesis_id, lifecycle.payload["run_id"])
    assert restored.status == "completed"
    assert restored.provenance["canonical_bundle_hash"] == api_hash


def test_restored_bundle_reproduces_provenance_and_summary(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    tools = AssistantTools(data_roots=(tmp_path,))
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    completed = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "runs" / "parity.research.zip",
    )
    run = repository.get_run(thesis.thesis_id, completed.payload["run_id"])
    digest = run.provenance["canonical_bundle_hash"]
    bundle_path = run.provenance["bundle_path"]

    # Immutable historical reload: a fresh repository/tools surface must load
    # the same provenance hash and compact summary from on-disk bytes.
    reloaded_repo = LocalThesisRepository(tmp_path / "assistant")
    historical = reloaded_repo.get_run(thesis.thesis_id, run.run_id)
    assert historical.status == "completed"
    assert historical.provenance["canonical_bundle_hash"] == digest
    assert historical.provenance["summary"] == run.provenance["summary"]
    assert Path(historical.provenance["bundle_path"]).read_bytes() == Path(bundle_path).read_bytes()

    restored = tools.load_bundle_summary(bundle_path, expected_hash=digest)
    assert restored["canonical_bundle_hash"] == digest
    assert restored["summary"]["instrument"] == "ES"
    assert restored["summary"]["results"]["trade_count"] == run.provenance["summary"]["results"][
        "trade_count"
    ]

    evidence = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BUNDLE.import",
            payload={
                "action": "evidence",
                "bundle_path": bundle_path,
                "expected_hash": digest,
            },
        )
    )
    assert evidence.status == "completed"
    assert evidence.payload["evidence"]["provenance"]["canonical_bundle_hash"] == digest


def test_hash_mismatch_rejects_explanation_comparison_export_and_portfolio(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    tools = AssistantTools(data_roots=(tmp_path,))
    left = tools.run_experiment_to_bundle(
        absolute_parity_run_spec(tmp_path, name="parity_left"),
        output_path=tmp_path / "left.research.zip",
    )
    right = tools.run_experiment_to_bundle(
        absolute_parity_run_spec(tmp_path, name="parity_right"),
        output_path=tmp_path / "right.research.zip",
    )
    left_hash = left["canonical_bundle_hash"]
    right_hash = right["canonical_bundle_hash"]
    assert left_hash == right_hash

    replaced = tmp_path / "replaced.research.zip"
    _write_replacement_bundle(replaced)
    assert canonical_bundle_hash(replaced.read_bytes()) != left_hash

    orchestrator = AssistantOrchestrator(tools=tools, repository=LocalThesisRepository(tmp_path / "assistant"))

    explanation = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BUNDLE.import",
            payload={
                "action": "evidence",
                "bundle_path": str(replaced),
                "expected_hash": left_hash,
            },
        )
    )
    assert explanation.status == "failed"
    assert "does not match" in explanation.payload["error"]["message"]

    with pytest.raises(AssistantToolError, match="does not match"):
        tools.compare_bundle_summaries(
            [tmp_path / "left.research.zip", replaced],
            expected_hashes=[left_hash, left_hash],
        )

    export = orchestrator.dispatch(
        AssistantRequest(
            capability_id="EXPORT.build_research_artifact",
            payload={
                "bundle_path": str(replaced),
                "expected_hash": left_hash,
            },
        ),
        confirmed=True,
    )
    assert export.status == "failed"
    assert "does not match" in export.payload["error"]["message"]

    portfolio = orchestrator.dispatch(
        AssistantRequest(
            capability_id="PORTFOLIO.analyze",
            payload={
                "bundle_paths": [str(tmp_path / "left.research.zip"), str(replaced)],
                "expected_hashes": [left_hash, right_hash],
                "instrument": "ES",
            },
        ),
        confirmed=True,
    )
    assert portfolio.status == "failed"
    assert "does not match" in portfolio.payload["error"]["message"]


@pytest.mark.parametrize(
    ("failure", "expected_status", "error_category"),
    [
        (RuntimeError("forced execution failure"), "failed", "execution"),
        (KeyboardInterrupt(), "failed", "execution"),
    ],
)
def test_failed_and_interrupted_runs_retain_request_without_success_summary(
    tmp_path, failure, expected_status, error_category
):
    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)

    class _FailingTools(AssistantTools):
        def run_experiment_to_bundle(self, spec, *, output_path):
            raise failure

    result = AssistantOrchestrator(
        tools=_FailingTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "fail.research.zip",
    )

    assert result.status == expected_status
    run = repository.list_runs(thesis.thesis_id)[0]
    assert run.status == expected_status
    assert run.request["run_spec"]["name"] == PARITY_RUN_NAME
    assert run.provenance is None
    assert run.error["category"] == error_category
    assert "summary" not in (run.error or {})


def test_cancelled_run_keeps_terminal_cancel_state(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    conversation = repository.create_conversation(thesis.thesis_id)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)
    tools = AssistantTools(data_roots=(tmp_path,))
    original = tools.run_experiment_to_bundle

    def cancel_then_run(spec, *, output_path):
        running = repository.list_runs(thesis.thesis_id)[0]
        repository.cancel_run(
            thesis.thesis_id,
            running.run_id,
            expected_revision=running.revision,
            reason="Interrupted by operator cancel.",
        )
        return original(spec, output_path=output_path)

    tools.run_experiment_to_bundle = cancel_then_run
    result = AssistantOrchestrator(tools=tools, repository=repository).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "cancelled.research.zip",
        conversation_id=conversation.conversation_id,
    )

    assert result.status == "cancelled"
    run = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    assert run.status == "cancelled"
    assert run.error["reason"] == "Interrupted by operator cancel."
    assert run.provenance is not None
    assert Path(run.provenance["bundle_path"]).is_file()
    assert run.provenance["canonical_bundle_hash"] == canonical_bundle_hash(
        Path(run.provenance["bundle_path"]).read_bytes()
    )


def test_run_cannot_complete_without_readable_bundle_and_verified_hash(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)

    class _MissingBundleTools(AssistantTools):
        def run_experiment_to_bundle(self, spec, *, output_path):
            return {
                "bundle_path": str(output_path),
                "canonical_bundle_hash": "a" * 64,
                "dataset_fingerprint": {"rows": 1},
                "tool_version": "test",
                "summary": {"warnings": {}},
            }

    missing = AssistantOrchestrator(
        tools=_MissingBundleTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "missing.research.zip",
    )
    assert missing.status == "failed"
    missing_run = repository.list_runs(thesis.thesis_id)[0]
    assert missing_run.status == "failed"
    assert missing_run.provenance is None
    assert "not written" in missing_run.error["message"]

    thesis_b = repository.create_thesis(name="parity_hash_mismatch")
    confirmed_b = _confirm_parity_run(repository, thesis_b.thesis_id, tmp_path)

    class _MismatchedHashTools(AssistantTools):
        def run_experiment_to_bundle(self, spec, *, output_path):
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = _write_replacement_bundle(path)
            return {
                "bundle_path": str(path),
                "canonical_bundle_hash": "b" * 64,
                "dataset_fingerprint": {"rows": 1},
                "tool_version": "test",
                "summary": {"warnings": {}},
                "effective_configuration": dict(spec),
                "resolved_paths": {},
                "resource_limits": {},
                "seeds": {},
                "_actual": canonical_bundle_hash(raw),
            }

    mismatched = AssistantOrchestrator(
        tools=_MismatchedHashTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis_b.thesis_id,
        spec_version=confirmed_b.version,
        output_path=tmp_path / "mismatch.research.zip",
    )
    assert mismatched.status == "failed"
    mismatched_run = repository.list_runs(thesis_b.thesis_id)[0]
    assert mismatched_run.status == "failed"
    assert mismatched_run.provenance is None
    assert "does not match" in mismatched_run.error["message"]


def test_completed_parity_run_is_listed_immutably_after_reload(tmp_path):
    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name=PARITY_RUN_NAME)
    confirmed = _confirm_parity_run(repository, thesis.thesis_id, tmp_path)
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    completed = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "history.research.zip",
    )
    first = repository.get_run(thesis.thesis_id, completed.payload["run_id"])

    reloaded = LocalThesisRepository(tmp_path / "assistant")
    listed = reloaded.list_runs(thesis.thesis_id)
    assert len(listed) == 1
    assert listed[0].run_id == first.run_id
    assert listed[0].status == "completed"
    assert listed[0].provenance == first.provenance
    assert listed[0].warnings == first.warnings
