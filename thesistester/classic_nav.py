"""Bidirectional classic ↔ Assistant navigation helpers (CAI-8).

Discuss / Open-exact / clarification navigation and identity badge resolution.
Does not record runs or mutate executable classic settings beyond hash-verified
bundle restore (Open exact). Streamlit UI imports are lazy.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, MutableMapping

from thesistester.assistant import AssistantOrchestrator, ResearchRun
from thesistester.classic_context import (
    get_active_thesis_id,
    is_research_mode,
    link_thesis,
    set_classic_flash,
    set_pending_navigation,
)
from thesistester.research_bundle import peek_research_identity
from thesistester.research_identity import (
    IDENTITY_RELATION_LABELS,
    DataIdentity,
    LevelsIdentity,
    classify_identity_relation,
    identities_from_payload,
    try_page_levels_identity,
)

# Clarification text → allowlisted classic page (nav + optional prefill note only).
# Order matters: Setup Builder before Levels so "setup levels" maps to Setup.
_CLARIFICATION_PAGE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"dataset|instrument|source\s*path|csv", re.I), "pages/1_Data.py"),
    (
        re.compile(r"setup|confluence|trigger|tolerance|naked|selected\s*levels", re.I),
        "pages/3_Setup_Builder.py",
    ),
    (
        re.compile(r"vwap|levels?|sma|ema|poc|opening\s*range|pivot", re.I),
        "pages/2_Levels.py",
    ),
    (
        re.compile(
            r"cost|commission|slippage|exposure|intrabar|session\s*close|stop.?loss|take.?profit",
            re.I,
        ),
        "pages/7_Backtest.py",
    ),
)


def set_classic_active_run(
    session_state: MutableMapping[str, Any],
    *,
    run_id: str,
    thesis_id: str | None = None,
) -> None:
    """Bind an active thesis run for classic breadcrumb (thesis-scoped)."""
    from thesistester.classic_context import init_classic_session_state

    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    init_classic_session_state(session_state)
    active_thesis = get_active_thesis_id(session_state)
    if thesis_id is not None and active_thesis and thesis_id != active_thesis:
        raise ValueError("Cannot bind a run from another thesis into classic context.")
    if thesis_id is not None and not active_thesis:
        raise ValueError("Classic research mode requires an active thesis before binding a run.")
    session_state["classic_active_run_id"] = run_id.strip()


def get_classic_active_run_id(session_state: Mapping[str, Any]) -> str | None:
    run_id = session_state.get("classic_active_run_id")
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()
    return None


def set_classic_focus_run(session_state: MutableMapping[str, Any], run_id: str) -> None:
    """Stage Assistant focus for a thesis run (consumed by Research Assistant)."""
    from thesistester.classic_context import init_classic_session_state

    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    init_classic_session_state(session_state)
    session_state["classic_focus_run_id"] = run_id.strip()


def consume_classic_focus_run(session_state: MutableMapping[str, Any]) -> str | None:
    from thesistester.classic_context import init_classic_session_state

    init_classic_session_state(session_state)
    run_id = session_state.get("classic_focus_run_id")
    session_state["classic_focus_run_id"] = None
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()
    return None


def set_classic_nav_prefill(
    session_state: MutableMapping[str, Any],
    *,
    target_page: str,
    note: str,
) -> None:
    """Stage one-shot clarification prefill (caption only — no page mutation)."""
    from thesistester.classic_context import (
        init_classic_session_state,
        resolve_pending_navigation_target,
    )

    resolved = resolve_pending_navigation_target(target_page)
    if resolved is None:
        raise ValueError(f"target_page is not an allowlisted classic page: {target_page!r}")
    text = str(note).strip()
    if not text:
        raise ValueError("prefill note must be a non-empty string.")
    init_classic_session_state(session_state)
    session_state["classic_nav_prefill"] = {"target_page": resolved, "note": text}


def consume_classic_nav_prefill(
    session_state: MutableMapping[str, Any],
    *,
    page_key: str | None = None,
) -> dict[str, str] | None:
    """Pop prefill when it targets the current page (or always when page_key is None)."""
    from thesistester.classic_context import init_classic_session_state

    init_classic_session_state(session_state)
    payload = session_state.get("classic_nav_prefill")
    if not isinstance(payload, Mapping):
        session_state["classic_nav_prefill"] = None
        return None
    target = payload.get("target_page")
    note = payload.get("note")
    if not isinstance(target, str) or not isinstance(note, str):
        session_state["classic_nav_prefill"] = None
        return None
    if page_key is not None:
        # page_key is logical (backtest); target_page is script path.
        pass
    session_state["classic_nav_prefill"] = None
    return {"target_page": target, "note": note.strip()}


def clarification_target_page(text: str) -> str | None:
    """Map one clarification string to an allowlisted classic page path."""
    if not isinstance(text, str) or not text.strip():
        return None
    for pattern, page in _CLARIFICATION_PAGE_RULES:
        if pattern.search(text):
            return page
    return None


def resolve_run_identities(
    run: ResearchRun | Mapping[str, Any],
) -> tuple[DataIdentity | None, LevelsIdentity | None]:
    """Resolve run data/levels identities from provenance or zip peek only."""
    if isinstance(run, ResearchRun):
        provenance = run.provenance if isinstance(run.provenance, Mapping) else {}
    else:
        provenance = run.get("provenance") if isinstance(run.get("provenance"), Mapping) else {}
    data, levels = identities_from_payload(provenance)
    if data is not None or levels is not None:
        return data, levels
    bundle_path = provenance.get("bundle_path") if isinstance(provenance, Mapping) else None
    if isinstance(bundle_path, str) and bundle_path.strip():
        peeked = peek_research_identity(bundle_path)
        return identities_from_payload(peeked)
    return None, None


def page_vs_run_identity_relation(
    session_state: Mapping[str, Any],
    run: ResearchRun | Mapping[str, Any],
) -> str:
    """Classify live classic page identity vs a thesis run (immutable identities)."""
    page_levels = try_page_levels_identity(session_state)
    run_data, run_levels = resolve_run_identities(run)
    return classify_identity_relation(page_levels, run_levels, run_data=run_data)


def identity_badge_label(relation: str) -> str:
    """Human label for a relation code."""
    return IDENTITY_RELATION_LABELS.get(relation, IDENTITY_RELATION_LABELS["identity_unavailable"])


def is_discussable_run(run: ResearchRun) -> bool:
    """True when a run can be explained/inspected (completed + hash-verified bundle)."""
    if run.status != "completed" or not isinstance(run.provenance, Mapping):
        return False
    path = run.provenance.get("bundle_path")
    digest = run.provenance.get("canonical_bundle_hash")
    return (
        isinstance(path, str)
        and bool(path.strip())
        and isinstance(digest, str)
        and bool(digest.strip())
    )


def latest_discussable_run(
    orchestrator: AssistantOrchestrator,
    *,
    thesis_id: str,
) -> ResearchRun | None:
    """Newest completed thesis run with a bundle path (metadata only)."""
    for run in reversed(orchestrator.list_runs(thesis_id)):
        if is_discussable_run(run):
            return run
    return None


def discuss_run(
    session_state: MutableMapping[str, Any],
    *,
    orchestrator: AssistantOrchestrator | None = None,
    run_id: str | None = None,
) -> str:
    """Focus a thesis run in Research Assistant without recording.

    Returns the focused run_id. Aligns ``assistant_selected_thesis_id`` with the
    classic active thesis so Discuss cannot land on a divergent Assistant picker.
    Only completed runs with hash-verified bundle provenance are discussable.
    """
    if not is_research_mode(session_state):
        raise ValueError("Discuss this run requires an active thesis (research mode).")
    thesis_id = get_active_thesis_id(session_state)
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("No active thesis is linked.")
    thesis_id = thesis_id.strip()
    orch = orchestrator or AssistantOrchestrator.for_local_workspace()
    explicit_run = isinstance(run_id, str) and bool(run_id.strip())
    target_run_id = run_id.strip() if explicit_run else get_classic_active_run_id(session_state)
    run: ResearchRun | None = None
    if isinstance(target_run_id, str) and target_run_id.strip():
        try:
            run = orch.get_run(thesis_id, target_run_id.strip())
        except Exception as exc:
            if explicit_run:
                raise ValueError(f"Focused run is not available on this thesis: {exc}") from exc
            # Stale classic_active_run_id breadcrumb — fall back like the Discuss UI.
            run = None
        if run is not None and not is_discussable_run(run):
            if explicit_run:
                raise ValueError(
                    "Focused run is not discussable "
                    "(requires a completed hash-verified research bundle)."
                )
            # Non-discussable active breadcrumb — fall back to latest discussable.
            run = None
    if run is None:
        run = latest_discussable_run(orch, thesis_id=thesis_id)
    if run is None:
        raise ValueError(
            "No thesis-recorded completed run to discuss. "
            "Use Record and discuss first, or complete an all_executions attempt."
        )
    if run.thesis_id != thesis_id:
        raise ValueError("Cannot discuss a run from another thesis.")
    if not is_discussable_run(run):
        raise ValueError(
            "Focused run is not discussable (requires a completed hash-verified research bundle)."
        )

    from thesistester.assistant.workspace import (
        init_assistant_session_state,
        select_thesis,
    )

    init_assistant_session_state(session_state)
    select_thesis(session_state, thesis_id)
    set_classic_active_run(session_state, run_id=run.run_id, thesis_id=thesis_id)
    set_classic_focus_run(session_state, run.run_id)
    set_classic_flash(
        session_state,
        level="info",
        message=f"Opening Research Assistant focused on run …{run.run_id[-8:]}.",
    )
    set_pending_navigation(session_state, "pages/14_Research_Assistant.py")
    return run.run_id


def open_exact_run_in_backtest(
    session_state: MutableMapping[str, Any],
    *,
    thesis_id: str,
    run_id: str,
    orchestrator: AssistantOrchestrator | None = None,
) -> dict[str, Any]:
    """Hash-restore a completed run and prepare Backtest navigation.

    Does not load the bundle until this explicit open/restore. Returns the
    handoff dict from ``restore_run_bundle_to_session``.
    """
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("thesis_id must be a non-empty string.")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    orch = orchestrator or AssistantOrchestrator.for_local_workspace()
    run = orch.get_run(thesis_id.strip(), run_id.strip())
    if run.thesis_id != thesis_id.strip():
        raise ValueError("Cannot open a run from another thesis.")
    if run.status != "completed":
        raise ValueError("Only completed runs can be opened in Backtest.")
    handoff = orch.restore_run_bundle_to_session(
        thesis_id=thesis_id.strip(),
        run_id=run_id.strip(),
        session_state=session_state,
    )
    thesis = orch.get_thesis(thesis_id.strip())
    dataset_id = session_state.get("dataset_id")
    link_thesis(
        session_state,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id=dataset_id if isinstance(dataset_id, str) else None,
    )
    # Same-thesis link preserves proposals; open-exact restores a different run's
    # widgets, so drop any staged draft that would overwrite the restored state.
    from thesistester.classic_proposal import clear_classic_proposal

    clear_classic_proposal(session_state)
    set_classic_active_run(session_state, run_id=run.run_id, thesis_id=thesis.thesis_id)
    # Prefer identities already restored into session; else peek without full reload.
    if not isinstance(session_state.get("data_identity"), Mapping) or not isinstance(
        session_state.get("levels_identity"), Mapping
    ):
        data_id, levels_id = resolve_run_identities(run)
        if data_id is not None and "data_identity" not in session_state:
            session_state["data_identity"] = data_id.to_dict()
        if levels_id is not None and "levels_identity" not in session_state:
            session_state["levels_identity"] = levels_id.to_dict()
    set_classic_flash(
        session_state,
        level="success",
        message=(
            f"Opened exact run …{run.run_id[-8:]} in Backtest "
            f"(restored {handoff.get('restored_count', 0)} keys)."
        ),
    )
    set_pending_navigation(session_state, "pages/7_Backtest.py")
    return handoff


def navigate_clarification_to_classic(
    session_state: MutableMapping[str, Any],
    *,
    clarification: str,
) -> str:
    """Stage caption prefill for a classic clarification page.

    Callers must ``st.switch_page`` to the returned target. Do **not** stage
    ``classic_pending_navigation`` here: Data/Levels do not run thesis chrome
    to consume it, so a leftover pending target would later hijack navigation
    on Backtest/Setup/Bundles.
    """
    target = clarification_target_page(clarification)
    if target is None:
        raise ValueError("No classic page mapping for this clarification.")
    set_classic_nav_prefill(
        session_state,
        target_page=target,
        note=clarification.strip(),
    )
    # Caption prefill only — do not stage classic_flash. Data/Levels lack thesis
    # chrome ``consume_classic_flash``, so a leftover flash would later surface
    # as a misleading notice on Backtest/Setup/Bundles.
    return target


def render_discuss_this_run(
    *,
    page_key: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Render **Discuss this run** (navigate-only) under an active thesis.

    Discuss needs a thesis-recorded completed run, not live session trades —
    so this chrome stays visible on empty Backtest / Bundles pages.
    """
    import streamlit as st

    from thesistester.classic_context import get_active_thesis_name

    if not isinstance(page_key, str) or not page_key.strip():
        raise ValueError("page_key must be a non-empty string.")
    page = page_key.strip()
    state = session_state if session_state is not None else st.session_state
    if not is_research_mode(state):
        return

    thesis_name = get_active_thesis_name(state) or get_active_thesis_id(state)
    active_run = get_classic_active_run_id(state)
    relation = "identity_unavailable"
    try:
        orch = AssistantOrchestrator.for_local_workspace()
        thesis_id = get_active_thesis_id(state)
        run = None
        if active_run and thesis_id:
            try:
                run = orch.get_run(thesis_id, active_run)
            except Exception:
                run = None
        if run is None and thesis_id:
            run = latest_discussable_run(orch, thesis_id=thesis_id)
        if run is not None:
            relation = page_vs_run_identity_relation(state, run)
            st.caption(
                f"Identity vs thesis run …{run.run_id[-8:]}: "
                f"**{identity_badge_label(relation)}** (`{relation}`)"
            )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Identity badge unavailable: {exc}")

    if st.button(
        "Discuss this run",
        key=f"classic_discuss_run_{page}",
        use_container_width=True,
        help=(
            f"Open Research Assistant for thesis “{thesis_name}” focused on the "
            "latest (or active) recorded run. Does not re-register."
        ),
    ):
        try:
            discuss_run(state)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def render_classic_nav_prefill_caption(
    *,
    target_page: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Show and consume a clarification prefill note on the target classic page."""
    import streamlit as st

    state = session_state if session_state is not None else st.session_state
    payload = state.get("classic_nav_prefill")
    if not isinstance(payload, Mapping):
        return
    if payload.get("target_page") != target_page:
        return
    consumed = consume_classic_nav_prefill(state)
    if consumed is None:
        return
    st.info(f"Assistant clarification: {consumed['note']}")
