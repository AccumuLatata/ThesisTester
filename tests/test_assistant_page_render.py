"""Rendered-structure baseline for the Research Assistant page (RUX-0).

Structural regression net for ``docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md``.

The rest of the suite guards this page with source-string assertions
(`tests/test_assistant_workspace.py`, `tests/test_ui_copy_guards.py`), which
cannot see prominence: a surface can be present in source while being nested
three expanders deep. These tests render the page in-process with
``streamlit.testing.v1.AppTest`` against a temporary store and assert what the
page actually shows — which surfaces are top-level, which are collapsed, which
chat channel owns the chat input, and that the classic Discuss deep-link opens
the run thread.

Two assertions are the behavioral contract the RUX layout work must preserve
(RUX-0 §5.1): channel isolation of ``results_qa`` history, and the classic
``results_qa`` deep-link force-open. The prominence assertions describe today's
draft-first layout and are rewritten — never deleted — by the RUX-2 layout PR.
"""

from __future__ import annotations

import multiprocessing
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from thesistester.assistant.llm import load_product_help_settings
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
    """Chat bubbles rendered directly in the page body (the draft thread today)."""
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


def test_default_prominence_is_draft_chat_with_collapsed_secondary_surfaces(workspace):
    """Baseline prominence: draft chat is the hero; Help/Advanced/Debug are collapsed.

    RUX-2 inverts this ordering; the assertion is rewritten there, not removed.
    """
    _, thesis = workspace
    app = _render(thesis.thesis_id)

    assert not app.exception
    entries = _top_level(app)

    draft_index = _index_of(entries, "subheader", "Assistant chat")
    advanced_index = _index_of(entries, "expander", "Advanced: draft, runs & compare")
    debug_index = _index_of(entries, "expander", "Debug: raw JSON & conversation audit")
    assert draft_index < advanced_index < debug_index

    if load_product_help_settings().enabled:
        help_index = _index_of(entries, "expander", "Help / how it works")
        assert draft_index < help_index < advanced_index
        assert _expander(app, "Help / how it works").proto.expanded is False

    for label in (
        "Manage thesis",
        "Advanced: draft, runs & compare",
        "Debug: raw JSON & conversation audit",
    ):
        assert _expander(app, label).proto.expanded is False, f"{label} must default collapsed"

    # Second-pipeline surfaces stay reachable under the collapsed Advanced expander.
    advanced = _expander(app, "Advanced: draft, runs & compare")
    advanced_subheaders = {item.value for item in advanced.subheader}
    assert {"Plan review", "Specifications", "Linked research runs"} <= advanced_subheaders


def test_rendered_captions_still_contain_rux0_nav_fragments(workspace):
    """RUX-1 nav-constant substitution must be value-preserving on the page."""
    from thesistester.assistant.ux import DISCUSS_NAV_HINT, HELP_NAV_HINT

    _, thesis = workspace
    app = _render(thesis.thesis_id)

    assert not app.exception
    captions = [item.value for item in app.caption]
    joined = "\n".join(captions)
    assert DISCUSS_NAV_HINT in joined
    assert HELP_NAV_HINT in joined


def test_page_renders_exactly_one_chat_input_owned_by_the_draft_channel(workspace):
    """One page-level chat input; today it belongs to thesis drafting."""
    _, thesis = workspace
    app = _render(thesis.thesis_id)

    assert not app.exception
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == "Describe or refine this thesis"

    # Discuss and Help use keyed text inputs with send buttons (RQ v1 widgets).
    if load_product_help_settings().enabled:
        help_labels = [item.label for item in _expander(app, "Help / how it works").text_input]
        assert "Ask how ThesisTester works" in help_labels


def test_results_qa_history_never_renders_in_the_draft_or_help_threads(workspace):
    """Channel isolation, asserted on rendered bubbles rather than source strings."""
    orchestrator, thesis = workspace
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
                "run_id": ORPHAN_RUN_ID,
            },
            {
                "role": "assistant",
                "content": RESULTS_REPLY_TEXT,
                "channel": "results_qa",
                "run_id": ORPHAN_RUN_ID,
            },
        ),
    )
    app = _render(thesis.thesis_id)

    assert not app.exception
    draft_texts = [text for _, text in _top_level_bubbles(app)]
    assert draft_texts == [DRAFT_USER_TEXT, DRAFT_REPLY_TEXT]
    # Help and results history must not leak into the draft thread.
    assert HELP_USER_TEXT not in draft_texts
    assert HELP_REPLY_TEXT not in draft_texts
    assert RESULTS_USER_TEXT not in draft_texts
    assert RESULTS_REPLY_TEXT not in draft_texts

    if load_product_help_settings().enabled:
        help_texts = [text for _, text in _bubbles(_expander(app, "Help / how it works"))]
        assert help_texts == [HELP_USER_TEXT, HELP_REPLY_TEXT]
        assert RESULTS_USER_TEXT not in help_texts
        assert DRAFT_USER_TEXT not in help_texts

    # The results thread renders only under its own completed run (none recorded here).
    assert RESULTS_USER_TEXT not in [text for _, text in _bubbles(app.main)]


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


def test_classic_results_qa_deep_link_force_opens_advanced_and_run_expanders(workspace):
    """CAI-8/RQ-4 contract: Discuss this run must land on the run's thread."""
    _, thesis = workspace
    app = _render(
        thesis.thesis_id,
        classic_focus_run_id=ORPHAN_RUN_ID,
        classic_focus_channel="results_qa",
    )

    assert not app.exception
    # One-shot classic focus keys are consumed atomically.
    assert _session_value(app, "classic_focus_run_id") is None
    assert _session_value(app, "classic_focus_channel") is None
    # Sticky deep-link plus keyed force-open for Advanced and the focused run.
    assert _session_value(app, "assistant_results_qa_deep_link") is True
    assert _session_value(app, "assistant_focused_run_id") == ORPHAN_RUN_ID
    assert _session_value(app, ASSISTANT_ADVANCED_EXPANDER_KEY) is True
    assert _session_value(app, linked_run_expander_key(ORPHAN_RUN_ID)) is True
    assert _expander(app, "Advanced: draft, runs & compare").proto.expanded is True
