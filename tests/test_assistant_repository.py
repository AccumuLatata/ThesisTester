from __future__ import annotations

import json

import pytest

from thesistester.assistant import (
    AssistantRepositoryError,
    InvalidStateTransitionError,
    LocalThesisRepository,
    RepositoryConflictError,
    RepositoryReadOnlyError,
)


@pytest.fixture
def repository(tmp_path):
    return LocalThesisRepository(tmp_path / "store" / "assistant")


def test_theses_are_versioned_clonable_and_archivable(repository):
    thesis = repository.create_thesis(name="dVWAP pullback", tags=("ES", "RTH"))
    clone = repository.clone_thesis(thesis.thesis_id)
    renamed = repository.rename_thesis(thesis.thesis_id, name="dVWAP reclaim", expected_revision=1)

    assert renamed.revision == 2
    assert clone.cloned_from_thesis_id == thesis.thesis_id
    assert [item.thesis_id for item in repository.list_theses()] == [
        renamed.thesis_id,
        clone.thesis_id,
    ]

    archived = repository.archive_thesis(renamed.thesis_id, expected_revision=2)
    assert archived.lifecycle == "archived"
    assert [item.thesis_id for item in repository.list_theses()] == [clone.thesis_id]
    assert repository.restore_thesis(archived.thesis_id, expected_revision=3).lifecycle == "active"

    with pytest.raises(RepositoryConflictError):
        repository.rename_thesis(thesis.thesis_id, name="stale", expected_revision=1)


def test_list_theses_reads_records_when_store_marker_is_absent(repository):
    thesis = repository.create_thesis(name="Markerless thesis")
    repository._marker_path.unlink()

    assert repository.get_thesis(thesis.thesis_id) == thesis
    assert repository.list_theses() == (thesis,)


def test_specs_are_immutable_and_runs_require_confirmation(repository):
    thesis = repository.create_thesis(name="dVWAP pullback")
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "levels": {},
            "setup": {
                "name": "dVWAP pullback",
                "instrument": "ES",
                "selected_levels": ["dVWAP_RTH"],
                "tolerance_ticks": 0,
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
        },
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    draft_path = repository._spec_path(thesis.thesis_id, draft.version).read_bytes()

    with pytest.raises(InvalidStateTransitionError):
        repository.start_run(
            thesis.thesis_id, spec_version=draft.version, request={"request_id": "x"}
        )

    confirmed = repository.confirm_spec_version(
        thesis.thesis_id, draft.version, confirmation_note="approved"
    )
    run = repository.start_run(
        thesis.thesis_id, spec_version=confirmed.version, request={"request_id": "x"}
    )
    completed = repository.complete_run(
        thesis.thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={"bundle_path": "runs/x.research.zip", "canonical_bundle_hash": "a" * 64},
        warnings=("small sample",),
    )

    assert confirmed.parent_version == draft.version
    assert repository._spec_path(thesis.thesis_id, draft.version).read_bytes() == draft_path
    assert completed.status == "completed"
    with pytest.raises(InvalidStateTransitionError):
        repository.fail_run(
            thesis.thesis_id, run.run_id, expected_revision=completed.revision, error={"x": 1}
        )


def test_confirmation_rejects_unresolved_or_invalid_content_and_is_idempotent(repository):
    thesis = repository.create_thesis(name="Canonical thesis")
    unresolved = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={},
        status="needs_clarification",
        unresolved_assumptions=("Select a dataset.",),
        compiler_version="runspec-2",
    )
    with pytest.raises(InvalidStateTransitionError, match="resolved"):
        repository.confirm_spec_version(thesis.thesis_id, unresolved.version)

    invalid = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "setup": {},
            "backtest": {},
        },
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    with pytest.raises(ValueError, match="Canonical RunSpec"):
        repository.confirm_spec_version(thesis.thesis_id, invalid.version)

    valid = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "levels": {},
            "setup": {
                "name": "Canonical thesis",
                "instrument": "ES",
                "selected_levels": ["dVWAP_RTH"],
                "tolerance_ticks": 0,
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
        },
        status="ready_for_confirmation",
        compiler_version="runspec-2",
    )
    first = repository.confirm_spec_version(thesis.thesis_id, valid.version)
    second = repository.confirm_spec_version(thesis.thesis_id, valid.version)

    assert first == second


def test_conversations_are_append_only_and_reject_stale_revisions(repository):
    thesis = repository.create_thesis(name="Conversation thesis")
    conversation = repository.create_conversation(thesis.thesis_id)
    updated = repository.append_conversation_message(
        thesis.thesis_id,
        conversation.conversation_id,
        expected_revision=1,
        message={"role": "user", "content": "Test this."},
        tool_entry={"capability_id": "PIPELINE.validate_run_spec"},
    )

    assert updated.messages == ({"role": "user", "content": "Test this."},)
    assert len(updated.tool_transcript) == 1
    with pytest.raises(RepositoryConflictError):
        repository.append_conversation_message(
            thesis.thesis_id,
            conversation.conversation_id,
            expected_revision=1,
            message={"role": "user"},
        )


def test_future_store_schema_blocks_mutation_and_corrupt_records_fail_closed(repository):
    root = repository.root
    root.mkdir(parents=True)
    (root / "schema_version.json").write_text(
        json.dumps({"schema_version": 2, "kind": "assistant_store"}), encoding="utf-8"
    )
    with pytest.raises(RepositoryReadOnlyError):
        repository.create_thesis(name="blocked")

    clean = LocalThesisRepository(root.parent / "clean")
    thesis = clean.create_thesis(name="Corrupt me")
    path = clean._thesis_dir(thesis.thesis_id) / "meta.json"
    path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(AssistantRepositoryError):
        clean.get_thesis(thesis.thesis_id)
