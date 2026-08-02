from copy import deepcopy
from pathlib import Path

import pytest

from thesistester.assistant import AssistantOrchestrator, LocalThesisRepository, SpecVersion


class _BundleTools:
    def __init__(self):
        self.run_specs = []
        self.data_roots = ()
        self.limits = None

    def run_experiment_to_bundle(self, spec, *, output_path):
        self.run_specs.append(spec)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"bundle")
        return {
            "bundle_path": str(output_path),
            "canonical_bundle_hash": "a" * 64,
            "dataset_fingerprint": {"rows": 10},
            "tool_version": "test",
            "summary": {"warnings": {"intrabar": "assumption"}},
            "effective_configuration": dict(spec),
            "resolved_paths": {"dataset.path": "bars.csv"},
            "resource_limits": {
                "max_grid_cells": 500,
                "max_simulations": 5000,
                "max_walk_forward_matrix_cells": 100,
            },
            "seeds": {},
        }


def _canonical_choices(name: str) -> dict:
    return {
        "dataset": {"path": "bars.csv", "instrument": "ES"},
        "levels": {},
        "setup": {
            "name": name,
            "description": "",
            "instrument": "ES",
            "selected_levels": ["dVWAP_RTH"],
            "tolerance_ticks": 0,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "direction": "both",
        },
        "backtest": {
            "commission_per_side": 0,
            "slippage_ticks": 0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
    }


def test_confirmed_spec_runs_and_persists_bundle_provenance(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Lifecycle")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_canonical_choices(thesis.name),
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
    assert "resource_limits" in restored.request
    assert restored.provenance["effective_configuration"]["dataset"]["path"] == "bars.csv"
    assert restored.provenance["resolved_paths"]["dataset.path"] == "bars.csv"
    assert restored.provenance["resource_limits"]["max_grid_cells"] == 500


def test_confirmed_spec_executes_after_thesis_rename(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Original title")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_canonical_choices(thesis.name),
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    repository.rename_thesis(
        thesis.thesis_id,
        name="Renamed title",
        expected_revision=thesis.revision,
    )
    tools = _BundleTools()
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "bundles" / "renamed.research.zip",
    )

    assert result.status == "completed"
    assert tools.run_specs == [
        {
            **confirmed.normalized_run_spec,
            "name": "Renamed title",
        }
    ]


def test_legacy_confirmed_spec_without_session_controls_executes(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Legacy session defaults")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_canonical_choices(thesis.name),
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    legacy_choices = deepcopy(confirmed.normalized_run_spec)
    for key in (
        "flat_by_session_close",
        "session_close_time",
        "session_timezone",
        "no_new_entries_after",
    ):
        legacy_choices["backtest"].pop(key)
    legacy_confirmed = SpecVersion.create(
        thesis_id=confirmed.thesis_id,
        version=confirmed.version,
        parent_version=confirmed.parent_version,
        status=confirmed.status,
        normalized_run_spec=legacy_choices,
        unresolved_assumptions=confirmed.unresolved_assumptions,
        compiler_version=confirmed.compiler_version,
        confirmed_at=confirmed.confirmed_at,
        confirmation_note=confirmed.confirmation_note,
        created_at=confirmed.created_at,
    )
    repository._write_json_atomic(
        repository._spec_path(thesis.thesis_id, confirmed.version),
        legacy_confirmed.to_dict(),
    )
    tools = _BundleTools()
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "bundles" / "legacy.research.zip",
    )

    assert result.status == "completed"
    assert tools.run_specs[0]["backtest"] == {
        **legacy_choices["backtest"],
        "flat_by_session_close": False,
        "session_close_time": None,
        "session_timezone": None,
        "no_new_entries_after": None,
    }


def test_unconfirmed_or_failed_run_has_safe_terminal_state(tmp_path):
    class FailingTools:
        data_roots = ()
        limits = None

        def run_experiment_to_bundle(self, spec, *, output_path):
            raise RuntimeError("fixture execution failure")

    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Failure")
    conversation = repository.create_conversation(thesis.thesis_id)
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_canonical_choices(thesis.name),
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
            conversation_id=conversation.conversation_id,
        )
    failed = repository.list_runs(thesis.thesis_id)[0]
    assert failed.status == "failed"
    assert failed.error["category"] == "execution"
    assert "RuntimeError" in failed.error["message"]
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert transcript[-1]["status"] == "failed"


def test_completed_run_survives_conversation_audit_failure(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Audit race")
    conversation = repository.create_conversation(thesis.thesis_id)
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec=_canonical_choices(thesis.name),
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    orchestrator = AssistantOrchestrator(tools=_BundleTools(), repository=repository)

    def boom(*args, **kwargs):
        raise RuntimeError("stale conversation revision")

    monkeypatch.setattr(repository, "append_conversation_message", boom)

    result = orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed.version,
        output_path=tmp_path / "bundles" / "audit.research.zip",
        conversation_id=conversation.conversation_id,
    )

    restored = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    assert result.status == "completed"
    assert restored.status == "completed"
    assert restored.provenance["canonical_bundle_hash"] == "a" * 64
