"""Rendered-structure baseline for the Research Assistant page (RUX-series).

Structural regression net for ``docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md``.

The rest of the suite guards this page with source-string assertions
(`tests/test_assistant_workspace.py`, `tests/test_ui_copy_guards.py`), which
cannot see prominence: a surface can be present in source while being nested
three expanders deep. These tests render the page in-process with
``streamlit.testing.v1.AppTest`` against a temporary store and assert what the
page actually shows — which surfaces are top-level, which are collapsed, which
mode owns the chat input, and that the classic Discuss deep-link opens the run
thread.

Two assertions are the behavioral contract the RUX layout work must preserve
(RUX-0 §5.1): channel isolation of ``results_qa`` history, and the classic
``results_qa`` deep-link force-open (RUX-2: plus Discuss mode + run preselect).
"""

from __future__ import annotations

import multiprocessing
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from thesistester.assistant.llm import (
    ProductHelpSettings,
    ResultsQASettings,
    load_product_help_settings,
)
from thesistester.assistant.ux import (
    ASSISTANT_MODE_DISCUSS,
    ASSISTANT_MODE_DRAFT,
    ASSISTANT_MODE_HELP,
    ASSISTANT_MODE_SESSION_KEY,
    DISCUSS_NAV_HINT,
    DISCUSS_RUN_PICKER_KEY,
    HELP_NAV_HINT,
    chat_input_key,
    chat_input_placeholder,
)
from thesistester.assistant.workspace import (
    ASSISTANT_ADVANCED_EXPANDER_KEY,
    linked_run_expander_key,
)

PAGE_PATH = pathlib.Path(__file__).resolve().parents[1] / "pages" / "14_Research_Assistant.py"

DRAFT_USER_TEXT = "RUX draft probe question"
DRAFT_REPLY_TEXT = "RUX draft probe reply"
HELP_USER_TEXT = "RUX help probe question"
HELP_REPLY_TEXT = "RUX help probe reply"
RESULTS_USER_TEXT = "RUX results probe question"
RESULTS_REPLY_TEXT = "RUX results probe reply"
ORPHAN_RUN_ID = "run_ruxbaseline0000000000000000000"


@pytest.fixture(autouse=True)
def isolate_apptest_globals():
    """Undo the process-global state a rendered Streamlit script leaves behind.

    Streamlit's script runner installs the page as ``sys.modules["__main__"]`` and
    puts the page directory on ``sys.path``. Left in place, any later test that
    starts a ``spawn``-context process pool (``thesistester.cli.run_batch``) has
    its children re-import the Research Assistant page as their main module,
    which fails and breaks the pool. Restoring both keeps this module order-safe
    against the rest of the suite. Any future ``AppTest`` module must do the same
    (promote this to ``tests/conftest.py`` when a second one appears).
    """
    main_module = sys.modules.get("__main__")
    path_snapshot = list(sys.path)
    try:
        yield
    finally:
        if main_module is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = main_module
        sys.path[:] = path_snapshot


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Isolated assistant store with one thesis; returns (orchestrator, thesis)."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    from thesistester.assistant import AssistantOrchestrator

    orchestrator = AssistantOrchestrator.for_local_workspace()
    thesis = orchestrator.create_thesis(name="RUX baseline thesis")
    return orchestrator, thesis


def _seed_discussable_run(orchestrator: Any, thesis_id: str) -> Any:
    """Persist one completed run with dict provenance (Discuss UI eligibility)."""
    repository = orchestrator.repository
    draft = repository.create_spec_version(
        thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "levels": {},
            "setup": {
                "name": "RUX discuss seed",
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
        },
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis_id, draft.version)
    run = repository.start_run(
        thesis_id,
        spec_version=confirmed.version,
        request={"run_spec": confirmed.normalized_run_spec},
    )
    return repository.complete_run(
        thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={
            "bundle_path": "runs/fixture.research.zip",
            "canonical_bundle_hash": "a" * 64,
        },
    )


def _seed_messages(orchestrator: Any, thesis_id: str, messages: tuple[dict[str, Any], ...]) -> str:
    """Append messages to the thesis conversation; returns the conversation id."""
    conversation = orchestrator.ensure_conversation(thesis_id)
    revision = conversation.revision
    for message in messages:
        conversation = orchestrator.repository.append_conversation_message(
            thesis_id,
            conversation.conversation_id,
            expected_revision=revision,
            message=message,
        )
        revision = conversation.revision
    return conversation.conversation_id


def _run_app(app: AppTest) -> AppTest:
    """Run the script, then undo the process-global state the run installed.

    Restoring here (not only at fixture teardown) keeps every helper leak-free by
    construction, so a spawn-context process pool started later in the same test
    still works.
    """
    main_module = sys.modules.get("__main__")
    path_snapshot = list(sys.path)
    try:
        app.run()
    finally:
        if main_module is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = main_module
        sys.path[:] = path_snapshot
    return app


def _render(thesis_id: str | None = None, **session_state: Any) -> AppTest:
    """Render the page, optionally with a selected thesis and staged session keys."""
    app = _run_app(AppTest.from_file(str(PAGE_PATH), default_timeout=90))
    if thesis_id is None and not session_state:
        return app
    if thesis_id is not None:
        app.session_state["assistant_selected_thesis_id"] = thesis_id
        app.session_state["assistant_thesis_picker"] = thesis_id
    for key, value in session_state.items():
        app.session_state[key] = value
    return _run_app(app)


def _element_kind(element: Any) -> str:
    return str(getattr(element, "type", None) or type(element).__name__)


def _top_level(app: AppTest) -> tuple[tuple[str, str], ...]:
    """Return ``(kind, label)`` for each direct child of the main page body."""
    entries: list[tuple[str, str]] = []
    for element in app.main.children.values():
        kind = _element_kind(element)
        label = getattr(element, "label", None)
        if label is None:
            label = getattr(element, "value", "")
        entries.append((kind, str(label)))
    return tuple(entries)


def _index_of(entries: tuple[tuple[str, str], ...], kind: str, label: str) -> int:
    for index, (entry_kind, entry_label) in enumerate(entries):
        if entry_kind == kind and entry_label == label:
            return index
    raise AssertionError(f"Top-level {kind} {label!r} not rendered. Rendered: {entries}")


def _expander(app: AppTest, label: str) -> Any:
    for element in app.get("expander"):
        if element.label == label:
            return element
    raise AssertionError(
        f"Expander {label!r} not rendered. Rendered: {[e.label for e in app.get('expander')]}"
    )


def _bubbles(container: Any) -> tuple[tuple[str, str], ...]:
    """Return ``(role, text)`` for chat bubbles rendered inside ``container``."""
    return tuple(
        (str(message.name), text.value)
        for message in container.chat_message
        for text in message.markdown
    )


def _top_level_bubbles(app: AppTest) -> tuple[tuple[str, str], ...]:
    """Chat bubbles rendered directly in the page body (active mode thread)."""
    return tuple(
        (str(element.name), text.value)
        for element in app.main.children.values()
        if _element_kind(element) == "chat_message"
        for text in element.markdown
    )


def _session_value(app: AppTest, key: str) -> Any:
    return app.session_state[key] if key in app.session_state else None


def test_no_thesis_selected_renders_only_the_thesis_gate(workspace):
    """Empty state stops before any assistant surface renders."""
    app = _render()

    assert not app.exception
    assert [info.value for info in app.info] == ["Create or select a thesis to begin."]
    assert app.chat_input.values == []
    assert app.get("expander") == []


def test_default_prominence_is_discuss_with_collapsed_secondary_surfaces(workspace):
    """RUX-2 prominence: Discuss is default; Advanced/Debug stay collapsed."""
    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    app = _render(thesis.thesis_id)

    assert not app.exception
    assert _session_value(app, ASSISTANT_MODE_SESSION_KEY) == ASSISTANT_MODE_DISCUSS
    assert _session_value(app, DISCUSS_RUN_PICKER_KEY) == completed.run_id

    entries = _top_level(app)
    advanced_index = _index_of(entries, "expander", "Advanced: draft, runs & compare")
    debug_index = _index_of(entries, "expander", "Debug: raw JSON & conversation audit")
    assert advanced_index < debug_index
    # Draft chat is mode-scoped — not a top-level hero on the default render.
    with pytest.raises(AssertionError):
        _index_of(entries, "subheader", "Assistant chat")
    # Help expander is gone; Help is a peer mode.
    assert all(label != "Help / how it works" for kind, label in entries if kind == "expander")

    for label in (
        "Manage thesis",
        "Advanced: draft, runs & compare",
        "Debug: raw JSON & conversation audit",
    ):
        assert _expander(app, label).proto.expanded is False, f"{label} must default collapsed"

    # Discuss mode owns the page-level chat_input (RUX-3).
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == chat_input_placeholder(ASSISTANT_MODE_DISCUSS)

    # Second-pipeline surfaces stay reachable under the collapsed Advanced expander.
    advanced = _expander(app, "Advanced: draft, runs & compare")
    advanced_subheaders = {item.value for item in advanced.subheader}
    assert {"Plan review", "Specifications", "Linked research runs"} <= advanced_subheaders


def test_default_discuss_empty_state_names_record_and_discuss(workspace):
    """No eligible run → guidance; chat_input still present (RUX-3)."""
    _, thesis = workspace
    app = _render(thesis.thesis_id)

    assert not app.exception
    assert _session_value(app, ASSISTANT_MODE_SESSION_KEY) == ASSISTANT_MODE_DISCUSS
    infos = [item.value for item in app.info]
    assert any("Record and discuss this run" in text for text in infos)
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == chat_input_placeholder(ASSISTANT_MODE_DISCUSS)


def test_discuss_mode_reports_disabled_results_qa_not_missing_runs(workspace, monkeypatch):
    """When RQ is off, keep Explain/Open/Restore; do not claim missing runs."""
    import thesistester.assistant.llm as llm_mod

    monkeypatch.setattr(
        llm_mod,
        "load_results_qa_settings",
        lambda path="config/assistant.toml": ResultsQASettings(
            enabled=False,
            max_history_messages=12,
            allow_time_enrichment=False,
        ),
    )
    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    app = _render(thesis.thesis_id)

    assert not app.exception
    infos = [item.value for item in app.info]
    assert any("Results Q&A is disabled" in text for text in infos)
    assert all("Record and discuss this run" not in text for text in infos)
    assert len(app.chat_input) == 1
    # Pre-RUX-2 sibling gate: secondary actions stay available without RQ.
    assert any(item.label == "Explain run" for item in app.button)
    assert any(item.label == "Open exact run in Backtest" for item in app.button)
    assert any(item.label == "Restore bundle into research pages" for item in app.button)
    assert _session_value(app, DISCUSS_RUN_PICKER_KEY) == completed.run_id


def test_help_mode_shows_disabled_guidance_when_product_help_off(workspace, monkeypatch):
    """Help peer mode must not render a blank panel when the channel is off."""
    import thesistester.assistant.llm as llm_mod

    monkeypatch.setattr(
        llm_mod,
        "load_product_help_settings",
        lambda path="config/assistant.toml": ProductHelpSettings(
            enabled=False,
            max_history_messages=12,
            max_corpus_chars=24000,
        ),
    )
    _, thesis = workspace
    app = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_HELP})

    assert not app.exception
    assert any(item.value == "Help / how it works" for item in app.subheader)
    infos = [item.value for item in app.info]
    assert any("Product Help is disabled" in text for text in infos)
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == chat_input_placeholder(ASSISTANT_MODE_HELP)


def test_rendered_captions_contain_rux2_nav_fragments(workspace):
    """Draft-mode captions compose the flipped Discuss/Help nav constants."""
    _, thesis = workspace
    app = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_DRAFT})

    assert not app.exception
    captions = [item.value for item in app.caption]
    joined = "\n".join(captions)
    assert DISCUSS_NAV_HINT in joined
    assert HELP_NAV_HINT in joined


def test_page_renders_exactly_one_chat_input_in_every_mode(workspace):
    """RUX-3: exactly one page-level chat_input per rerun in all three modes."""
    from thesistester.assistant.ux import chat_input_placeholder as placeholder

    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)

    discuss = _render(thesis.thesis_id)
    assert not discuss.exception
    assert len(discuss.chat_input) == 1
    assert discuss.chat_input[0].placeholder == placeholder(ASSISTANT_MODE_DISCUSS)

    if load_product_help_settings().enabled:
        help_app = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_HELP})
        assert not help_app.exception
        assert len(help_app.chat_input) == 1
        assert help_app.chat_input[0].placeholder == placeholder(ASSISTANT_MODE_HELP)

    draft = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_DRAFT})
    assert not draft.exception
    assert len(draft.chat_input) == 1
    assert draft.chat_input[0].placeholder == placeholder(ASSISTANT_MODE_DRAFT)
    assert completed.run_id  # seeded for discuss routing tests below


def test_discuss_chat_input_routes_to_handle_results_turn(workspace, monkeypatch):
    """Submitting Discuss chat_input calls handle_results_turn with selected run_id."""
    from thesistester.assistant import AssistantOrchestrator, OrchestrationResult
    from thesistester.assistant.contracts import OrchestrationStatus
    import thesistester.assistant.llm as llm_mod

    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    calls: list[dict[str, Any]] = []

    def _fake_results(self, client, **kwargs):
        calls.append(kwargs)
        assert "choices" not in kwargs
        return OrchestrationResult(
            status=OrchestrationStatus.COMPLETED.value,
            capability_id="RESULTS.qa",
            payload={"reply": {"summary": "ok", "claims": (), "caveats": (), "followups": ()}},
        )

    monkeypatch.setattr(AssistantOrchestrator, "handle_results_turn", _fake_results)
    monkeypatch.setattr(llm_mod, "create_openai_client", lambda settings: object())

    app = _render(thesis.thesis_id)
    assert not app.exception
    assert len(app.chat_input) == 1
    _run_app(app.chat_input[0].set_value("What was expectancy?"))

    assert not app.exception, app.exception
    assert len(calls) == 1
    assert calls[0]["run_id"] == completed.run_id
    assert calls[0]["message"] == "What was expectancy?"
    assert calls[0]["thesis_id"] == thesis.thesis_id
    assert "choices" not in calls[0]


def test_help_chat_input_routes_to_handle_help_turn_without_choices(workspace, monkeypatch):
    """Submitting Help chat_input calls handle_help_turn; no choices on the path."""
    from thesistester.assistant import AssistantOrchestrator, OrchestrationResult
    from thesistester.assistant.contracts import OrchestrationStatus
    import thesistester.assistant.llm as llm_mod

    if not load_product_help_settings().enabled:
        pytest.skip("product_help disabled in tracked config")

    _, thesis = workspace
    calls: list[dict[str, Any]] = []

    def _fake_help(self, client, **kwargs):
        calls.append(kwargs)
        assert "choices" not in kwargs
        return OrchestrationResult(
            status=OrchestrationStatus.COMPLETED.value,
            capability_id="HELP.qa",
            payload={
                "reply": {"summary": "ok", "citations": (), "caveats": (), "followups": ()},
                "remediation": False,
            },
        )

    monkeypatch.setattr(AssistantOrchestrator, "handle_help_turn", _fake_help)
    monkeypatch.setattr(llm_mod, "create_openai_client", lambda settings: object())

    app = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_HELP})
    assert not app.exception
    assert len(app.chat_input) == 1
    _run_app(app.chat_input[0].set_value("How does Setup Builder work?"))

    assert not app.exception, app.exception
    assert len(calls) == 1
    assert calls[0]["message"] == "How does Setup Builder work?"
    assert calls[0]["thesis_id"] == thesis.thesis_id
    assert "run_id" not in calls[0]
    assert "choices" not in calls[0]


def test_results_qa_history_never_renders_in_the_draft_or_help_threads(workspace):
    """Channel isolation, asserted on rendered bubbles rather than source strings."""
    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    run_id = completed.run_id
    _seed_messages(
        orchestrator,
        thesis.thesis_id,
        (
            {"role": "user", "content": DRAFT_USER_TEXT},
            {"role": "assistant", "content": DRAFT_REPLY_TEXT, "choices": {}},
            {"role": "user", "content": HELP_USER_TEXT, "channel": "product_help"},
            {"role": "assistant", "content": HELP_REPLY_TEXT, "channel": "product_help"},
            {
                "role": "user",
                "content": RESULTS_USER_TEXT,
                "channel": "results_qa",
                "run_id": run_id,
            },
            {
                "role": "assistant",
                "content": RESULTS_REPLY_TEXT,
                "channel": "results_qa",
                "run_id": run_id,
            },
        ),
    )

    draft = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_DRAFT})
    assert not draft.exception
    draft_texts = [text for _, text in _top_level_bubbles(draft)]
    assert draft_texts == [DRAFT_USER_TEXT, DRAFT_REPLY_TEXT]
    assert HELP_USER_TEXT not in draft_texts
    assert HELP_REPLY_TEXT not in draft_texts
    assert RESULTS_USER_TEXT not in draft_texts
    assert RESULTS_REPLY_TEXT not in draft_texts

    if load_product_help_settings().enabled:
        help_app = _render(thesis.thesis_id, **{ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_HELP})
        assert not help_app.exception
        help_texts = [text for _, text in _top_level_bubbles(help_app)]
        assert help_texts == [HELP_USER_TEXT, HELP_REPLY_TEXT]
        assert RESULTS_USER_TEXT not in help_texts
        assert DRAFT_USER_TEXT not in help_texts

    discuss = _render(
        thesis.thesis_id,
        **{
            ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_DISCUSS,
            DISCUSS_RUN_PICKER_KEY: run_id,
        },
    )
    assert not discuss.exception
    discuss_texts = [text for _, text in _top_level_bubbles(discuss)]
    assert discuss_texts == [RESULTS_USER_TEXT, RESULTS_REPLY_TEXT]
    assert DRAFT_USER_TEXT not in discuss_texts
    assert HELP_USER_TEXT not in discuss_texts


def test_rendering_the_page_leaves_spawned_worker_processes_usable(workspace):
    """Guard the suite-order hazard this harness would otherwise introduce.

    ``thesistester.cli.run_batch`` starts a ``spawn``-context pool whose children
    re-import the parent's main module. Rendering must not leave the page
    installed as ``sys.modules["__main__"]``, or those children die with
    ``BrokenProcessPool`` in this or any later test.
    """
    _, thesis = workspace
    app = _render(thesis.thesis_id)

    assert not app.exception
    assert getattr(sys.modules.get("__main__"), "__file__", None) != str(PAGE_PATH)
    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn")
    ) as executor:
        assert executor.submit(abs, -7).result(timeout=180) == 7


def test_classic_results_qa_deep_link_preselects_discuss_and_force_opens(workspace):
    """CAI-8/RQ-4 + RUX-2: Discuss this run lands on the run's Discuss thread."""
    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    run_id = completed.run_id
    app = _render(
        thesis.thesis_id,
        classic_focus_run_id=run_id,
        classic_focus_channel="results_qa",
    )

    assert not app.exception
    # One-shot classic focus keys are consumed atomically.
    assert _session_value(app, "classic_focus_run_id") is None
    assert _session_value(app, "classic_focus_channel") is None
    # Sticky deep-link plus keyed force-open for Advanced and the focused run.
    assert _session_value(app, "assistant_results_qa_deep_link") is True
    assert _session_value(app, "assistant_focused_run_id") == run_id
    assert _session_value(app, ASSISTANT_ADVANCED_EXPANDER_KEY) is True
    assert _session_value(app, linked_run_expander_key(run_id)) is True
    assert _expander(app, "Advanced: draft, runs & compare").proto.expanded is True
    # RUX-2 superset: Discuss mode + preselected run.
    assert _session_value(app, ASSISTANT_MODE_SESSION_KEY) == ASSISTANT_MODE_DISCUSS
    assert _session_value(app, DISCUSS_RUN_PICKER_KEY) == run_id
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == chat_input_placeholder(ASSISTANT_MODE_DISCUSS)
    assert chat_input_key(ASSISTANT_MODE_DISCUSS, run_id=run_id) in app.session_state


def test_classic_results_qa_orphan_deep_link_still_force_opens_expanders(workspace):
    """Orphan run_id still proves expander force-open session keys (RUX-0 baseline)."""
    _, thesis = workspace
    app = _render(
        thesis.thesis_id,
        classic_focus_run_id=ORPHAN_RUN_ID,
        classic_focus_channel="results_qa",
    )

    assert not app.exception
    assert _session_value(app, "classic_focus_run_id") is None
    assert _session_value(app, "classic_focus_channel") is None
    assert _session_value(app, "assistant_results_qa_deep_link") is True
    assert _session_value(app, "assistant_focused_run_id") == ORPHAN_RUN_ID
    assert _session_value(app, ASSISTANT_ADVANCED_EXPANDER_KEY) is True
    assert _session_value(app, linked_run_expander_key(ORPHAN_RUN_ID)) is True
    assert _expander(app, "Advanced: draft, runs & compare").proto.expanded is True
    assert _session_value(app, ASSISTANT_MODE_SESSION_KEY) == ASSISTANT_MODE_DISCUSS


def test_orphan_deep_link_with_other_runs_warns_instead_of_silent_swap(workspace):
    """Ineligible focus + other recorded runs → warning, not silent wrong thread."""
    orchestrator, thesis = workspace
    completed = _seed_discussable_run(orchestrator, thesis.thesis_id)
    app = _render(
        thesis.thesis_id,
        classic_focus_run_id=ORPHAN_RUN_ID,
        classic_focus_channel="results_qa",
    )

    assert not app.exception
    warnings = [item.value for item in app.warning]
    assert any("not available for Discuss" in text for text in warnings)
    assert _session_value(app, ASSISTANT_MODE_SESSION_KEY) == ASSISTANT_MODE_DISCUSS
    assert _session_value(app, DISCUSS_RUN_PICKER_KEY) == completed.run_id
    assert _session_value(app, "assistant_focused_run_id") == ORPHAN_RUN_ID
