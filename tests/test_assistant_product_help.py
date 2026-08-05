"""RQ-3 product/help channel tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thesistester.assistant import (
    AssistantOrchestrator,
    LocalThesisRepository,
)
from thesistester.assistant.help_corpus import (
    HelpCorpusError,
    select_help_corpus_chunks,
)
from thesistester.assistant.product_help import (
    PRODUCT_HELP_CHANNEL,
    HelpEvidenceError,
    assert_help_reply_grounded,
    filter_product_help_history,
    format_help_reply_content,
    is_run_performance_question,
    propose_help_reply,
    remediation_help_reply,
)
from thesistester.assistant.tools import AssistantTools

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_is_run_performance_question_detects_personal_run_metrics():
    assert is_run_performance_question("What was my best SL?")
    assert is_run_performance_question("How did this run perform?")
    assert is_run_performance_question("What is my expectancy on this run?")
    assert not is_run_performance_question("How does grid ranking work?")
    assert not is_run_performance_question("What is expectancy_r?")
    assert not is_run_performance_question("How do I confirm a RunSpec?")


def test_remediation_help_reply_has_no_numbers_or_choices():
    reply = remediation_help_reply()
    assert reply.remediation is True
    assert "Discuss results" in reply.summary
    assert reply.citations == ()
    content = format_help_reply_content(reply)
    assert "choices" not in content
    # Prefer number-free remediation text.
    from thesistester.assistant.llm_explainer import _NUMBER_RE

    assert _NUMBER_RE.search(reply.summary) is None


def test_filter_product_help_history_by_channel():
    messages = [
        {"role": "user", "content": "draft"},
        {"role": "user", "content": "help-1", "channel": PRODUCT_HELP_CHANNEL},
        {
            "role": "assistant",
            "content": "ans-1",
            "channel": PRODUCT_HELP_CHANNEL,
        },
        {
            "role": "user",
            "content": "results",
            "channel": "results_qa",
            "run_id": "run_x",
        },
        {"role": "user", "content": "help-2", "channel": PRODUCT_HELP_CHANNEL},
    ]
    trimmed = filter_product_help_history(messages, max_history_messages=2)
    assert [item["content"] for item in trimmed] == ["ans-1", "help-2"]


def test_assert_help_reply_grounded_requires_verbatim_digits():
    chunks = [
        {
            "doc_id": "metrics",
            "section": "__preface__",
            "text": "Expectancy uses trade_count thresholds such as 30 trades.",
        }
    ]
    digest = '[{"capability_id": "GRID.run", "status": "executable"}]'
    assert_help_reply_grounded(
        summary="Screening mentions 30 trades.",
        caveats=["See metrics glossary."],
        followups=["Ask about ranking metrics."],
        corpus_chunks=chunks,
        registry_digest=digest,
    )
    with pytest.raises(HelpEvidenceError, match="Uncited numerical token"):
        assert_help_reply_grounded(
            summary="There were 99 mystery trades.",
            caveats=[],
            followups=[],
            corpus_chunks=chunks,
            registry_digest=digest,
        )


def test_propose_help_reply_rejects_uncited_citation_and_digits():
    chunks = [
        {
            "doc_id": "metrics",
            "section": "__preface__",
            "text": "Grid ranking uses expectancy_r.",
        }
    ]

    class BadCitationClient:
        def complete_structured(self, **kwargs):
            return {
                "summary": "Grid ranking uses expectancy_r.",
                "caveats": ["Docs only."],
                "citations": [{"doc_id": "agent_guide", "section": "secret"}],
                "followups": ["Ask about OTF."],
            }

    with pytest.raises(HelpEvidenceError, match="not attached"):
        propose_help_reply(
            BadCitationClient(),
            corpus_chunks=chunks,
            registry_digest=[],
            history=(),
            user_message="How does grid ranking work?",
        )

    class BadNumberClient:
        def complete_structured(self, **kwargs):
            return {
                "summary": "Always use 77 as the magic threshold.",
                "caveats": ["Docs only."],
                "citations": [{"doc_id": "metrics", "section": "__preface__"}],
                "followups": ["Ask about OTF."],
            }

    with pytest.raises(HelpEvidenceError, match="Uncited numerical token"):
        propose_help_reply(
            BadNumberClient(),
            corpus_chunks=chunks,
            registry_digest=[],
            history=(),
            user_message="How does grid ranking work?",
        )


def test_propose_help_reply_accepts_allowlisted_citations():
    chunks = [
        {
            "doc_id": "metrics",
            "section": "__preface__",
            "text": "Grid ranking uses expectancy_r.",
        }
    ]

    class Client:
        def complete_structured(self, **kwargs):
            return {
                "summary": "Grid ranking uses expectancy_r from the metrics glossary.",
                "caveats": ["Documentation only; not your run results."],
                "citations": [{"doc_id": "metrics", "section": "__preface__"}],
                "followups": ["Ask about confirmation gates next."],
            }

    reply = propose_help_reply(
        Client(),
        corpus_chunks=chunks,
        registry_digest=[{"capability_id": "PIPELINE.run_experiment", "status": "executable"}],
        history=(),
        user_message="How does grid ranking work?",
    )
    assert reply.citations[0].doc_id == "metrics"
    assert reply.remediation is False


def test_propose_help_reply_remediates_performance_without_llm():
    class Client:
        def complete_structured(self, **kwargs):  # pragma: no cover
            raise AssertionError("LLM must not run for performance remediation")

    reply = propose_help_reply(
        Client(),
        corpus_chunks=(),
        registry_digest=[],
        history=(),
        user_message="What was my best SL?",
    )
    assert reply.remediation is True
    assert "Discuss results" in reply.summary


def test_select_help_corpus_never_loads_agent_guide():
    from thesistester.assistant.help_corpus import load_corpus_chunks, resolve_corpus_path

    chunks = select_help_corpus_chunks(
        "How does the Research Assistant confirmation gate work?",
        repo_root=REPO_ROOT,
        max_chars=12000,
    )
    assert chunks
    assert all(chunk.doc_id != "agent_guide" for chunk in chunks)
    with pytest.raises(HelpCorpusError, match="excluded"):
        resolve_corpus_path("docs/AGENT_GUIDE.md", repo_root=REPO_ROOT)
    with pytest.raises(HelpCorpusError, match="not allowlisted"):
        load_corpus_chunks("architecture", repo_root=REPO_ROOT, sections=["nope"])


def test_handle_help_turn_persists_without_choices_and_skips_bundles(tmp_path, monkeypatch):
    from thesistester.assistant.help_corpus import CorpusChunk

    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Help")
    conversation = repository.create_conversation(thesis.thesis_id)
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    execute = MagicMock(wraps=orchestrator.execute_confirmed_run)
    dispatch = MagicMock(wraps=orchestrator.dispatch)
    monkeypatch.setattr(orchestrator, "execute_confirmed_run", execute)
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.select_help_corpus_chunks",
        lambda *args, **kwargs: (
            CorpusChunk(
                doc_id="metrics",
                section="__preface__",
                text="Grid ranking uses expectancy_r.",
            ),
        ),
    )
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.build_registry_digest",
        lambda: [{"capability_id": "PIPELINE.run_experiment", "status": "executable"}],
    )
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.registry_digest_json",
        lambda rows=None: '[{"capability_id":"PIPELINE.run_experiment","status":"executable"}]',
    )

    class Client:
        def complete_structured(self, **kwargs):
            return {
                "summary": "Grid ranking uses expectancy_r.",
                "caveats": ["Docs only."],
                "citations": [{"doc_id": "metrics", "section": "__preface__"}],
                "followups": ["Ask about confirmation."],
            }

    result = orchestrator.handle_help_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        message="How does grid ranking work?",
        conversation_id=conversation.conversation_id,
        repo_root=REPO_ROOT,
    )
    assert result.status == "completed"
    assert result.capability_id == PRODUCT_HELP_CHANNEL
    execute.assert_not_called()
    dispatch.assert_not_called()
    messages = repository.get_conversation(thesis.thesis_id, conversation.conversation_id).messages
    assert messages[-1]["channel"] == PRODUCT_HELP_CHANNEL
    assert "choices" not in messages[-1]
    assert messages[-1]["citations"][0]["doc_id"] == "metrics"


def test_handle_help_turn_remediates_best_sl_without_dispatch(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Remediate")
    conversation = repository.create_conversation(thesis.thesis_id)
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    execute = MagicMock(wraps=orchestrator.execute_confirmed_run)
    dispatch = MagicMock(wraps=orchestrator.dispatch)
    select = MagicMock()
    monkeypatch.setattr(orchestrator, "execute_confirmed_run", execute)
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    monkeypatch.setattr("thesistester.assistant.orchestrator.select_help_corpus_chunks", select)

    class Client:
        def complete_structured(self, **kwargs):  # pragma: no cover
            raise AssertionError("no LLM")

    result = orchestrator.handle_help_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        message="What was my best SL?",
        conversation_id=conversation.conversation_id,
        repo_root=REPO_ROOT,
    )
    assert result.status == "completed"
    assert result.payload["remediation"] is True
    select.assert_not_called()
    execute.assert_not_called()
    dispatch.assert_not_called()
    assistant = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).messages[-1]
    assert assistant["channel"] == PRODUCT_HELP_CHANNEL
    assert "choices" not in assistant
    assert "Discuss results" in assistant["content"]


def test_handle_chat_turn_excludes_help_channel(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Isolation")
    conversation = repository.create_conversation(thesis.thesis_id)
    conversation = repository.append_conversation_message(
        thesis.thesis_id,
        conversation.conversation_id,
        expected_revision=conversation.revision,
        message={"role": "user", "content": "draft-seed"},
    )
    conversation = repository.append_conversation_message(
        thesis.thesis_id,
        conversation.conversation_id,
        expected_revision=conversation.revision,
        message={
            "role": "user",
            "content": "help-leak",
            "channel": PRODUCT_HELP_CHANNEL,
        },
    )
    captured: dict[str, str] = {}

    class Client:
        def complete_structured(self, **kwargs):
            captured["user"] = kwargs["user"]
            return {
                "choices": [{"key": "dataset", "value": "bars.csv"}],
                "clarifications": ["Need more controls."],
            }

    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    orchestrator.handle_chat_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        user_message="refine thesis",
        max_history_messages=12,
    )
    assert "draft-seed" in captured["user"]
    assert "help-leak" not in captured["user"]
