"""Presentation helpers for Research Assistant UX modes (RUX-series).

Pure constants and functions — no I/O, no LLM, no orchestrator calls.
Navigation fragments are the single source of truth for page / product_help
call sites (see ``docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md`` §1.3).
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

# Mode ids (stable; used as segmented_control option values).
ASSISTANT_MODE_DISCUSS = "discuss"
ASSISTANT_MODE_HELP = "help"
ASSISTANT_MODE_DRAFT = "draft"

ASSISTANT_MODES: tuple[str, ...] = (
    ASSISTANT_MODE_DISCUSS,
    ASSISTANT_MODE_HELP,
    ASSISTANT_MODE_DRAFT,
)

ASSISTANT_MODE_LABELS: dict[str, str] = {
    ASSISTANT_MODE_DISCUSS: "Discuss runs",
    ASSISTANT_MODE_HELP: "Help",
    ASSISTANT_MODE_DRAFT: "Draft thesis",
}

ASSISTANT_MODE_SESSION_KEY = "assistant_ux_mode"
DISCUSS_RUN_PICKER_KEY = "assistant_discuss_run_picker"

# §1.3 navigation fragments — RUX-2 discuss-first locations (flipped from RUX-0).
DISCUSS_NAV_HINT = "the Discuss runs mode on Research Assistant"
DISCUSS_NAV_SHORT = "Discuss runs"
HELP_NAV_HINT = "the Help mode"
ADVANCED_PLAN_NAV_HINT = "Advanced → Plan review"
ADVANCED_COMPARE_NAV_HINT = "Advanced → Compare completed runs"
ADVANCED_PORTFOLIO_NAV_HINT = "Advanced → Portfolio analysis"

# Mirror classic_ledger.CLASSIC_LEDGER_ACTION without importing classic_ledger
# (avoids assistant ↔ classic import cycles from this pure helper module).
_CLASSIC_LEDGER_ACTION = "classic_execution_ledger"


def resolve_mode(
    session_state: Mapping[str, Any],
    *,
    default_mode: str,
    requested: str | None = None,
) -> str:
    """Return a legal mode id; unknown/absent values fall back safely.

    Priority: ``requested`` → ``session_state[ASSISTANT_MODE_SESSION_KEY]`` →
    ``default_mode`` → ``discuss``. Never raises.
    """
    candidates = (requested, session_state.get(ASSISTANT_MODE_SESSION_KEY), default_mode)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() in ASSISTANT_MODES:
            return candidate.strip()
    return ASSISTANT_MODE_DISCUSS


def recorded_completed_runs(runs: Sequence[Any]) -> tuple[Any, ...]:
    """Completed thesis-recorded runs (status + provenance dict), RQ-independent.

    Used for the Discuss run picker and secondary actions (Explain / Open /
    Restore). Q&A/voice additionally require ``results_qa`` enabled — see
    ``discussable_runs``. Preserves input order.
    """
    eligible: list[Any] = []
    for run in runs:
        if getattr(run, "status", None) != "completed":
            continue
        if not isinstance(getattr(run, "provenance", None), dict):
            continue
        eligible.append(run)
    return tuple(eligible)


def discussable_runs(
    runs: Sequence[Any],
    *,
    results_qa_enabled: bool,
) -> tuple[Any, ...]:
    """Filter runs with the frozen Discuss Q&A eligibility predicate.

    Predicate (RUX §1.1): ``status == "completed"`` and
    ``isinstance(provenance, dict)``, and results_qa enabled. Preserves input
    order — callers that want newest-first apply ``reversed`` themselves.
    """
    if not results_qa_enabled:
        return ()
    return recorded_completed_runs(runs)


def default_discuss_run_id(
    runs: Sequence[Any],
    *,
    focused_run_id: str | None,
) -> str | None:
    """Pick the focused run if eligible, else the newest eligible, else None.

    ``runs`` should already be the discussable subset in ``list_runs`` order
    (oldest first). Newest is therefore the last element.
    """
    eligible_ids: list[str] = []
    for run in runs:
        run_id = getattr(run, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            eligible_ids.append(run_id.strip())
    if not eligible_ids:
        return None
    if isinstance(focused_run_id, str) and focused_run_id.strip() in eligible_ids:
        return focused_run_id.strip()
    return eligible_ids[-1]


def _run_kind_token(run: Any) -> str:
    """Kind token matching ``classic_ledger.ledger_run_label`` (no import cycle).

    Keep branches byte-identical to ``ledger_run_label`` so Discuss picker titles
    and Linked-run expander titles stay aligned for the same run.
    """
    request = getattr(run, "request", None)
    if not isinstance(request, Mapping):
        request = {}
    provenance = getattr(run, "provenance", None)
    if not isinstance(provenance, Mapping):
        provenance = {}
    action = request.get("action")
    origin = provenance.get("execution_origin")
    if action == _CLASSIC_LEDGER_ACTION:
        page = request.get("origin_page") or "classic"
        return f"ledger:{page}"
    if action == "register_external_bundle":
        return "recorded:manual"
    if origin == "classic":
        return "classic"
    if origin == "assistant" or action is None:
        return "assistant"
    # Prefer action (not execution_origin) — matches ledger_run_label.
    return str(action)


def run_picker_label(run: Any) -> str:
    """Deterministic selectbox label matching Linked-run expander formatting."""
    run_id = str(getattr(run, "run_id", "") or "")
    suffix = run_id[-8:] if run_id else "????????"
    status = str(getattr(run, "status", "") or "")
    kind = _run_kind_token(run)
    return f"Run {suffix} · {status} · {kind}"


def apply_discuss_deep_link_preselect(
    session_state: MutableMapping[str, Any],
    *,
    run_id: str | None,
    channel: str | None,
) -> None:
    """On a fresh ``results_qa`` classic focus: preselect Discuss mode + run.

    Writes widget keys **before** the mode selector / run picker bind (RUX-2
    deep-link superset). Does not replace ``force_results_qa_expanders_open``.
    """
    if channel != "results_qa":
        return
    if not isinstance(run_id, str) or not run_id.strip():
        return
    session_state[ASSISTANT_MODE_SESSION_KEY] = ASSISTANT_MODE_DISCUSS
    session_state[DISCUSS_RUN_PICKER_KEY] = run_id.strip()


def chat_input_placeholder(mode: str) -> str:
    """Mode-specific placeholder for the single page-level ``st.chat_input``."""
    if mode == ASSISTANT_MODE_DISCUSS:
        return "Ask about this completed run"
    if mode == ASSISTANT_MODE_HELP:
        return "Ask how ThesisTester works"
    return "Describe or refine this thesis"


def chat_input_key(mode: str, run_id: str | None = None) -> str:
    """Stable widget key for the active-mode page-level ``st.chat_input``.

    Discuss keys include ``run_id`` when a run is selected so Streamlit does not
    reuse draft text across runs. Help/Draft keys are mode-only.
    """
    if mode == ASSISTANT_MODE_DISCUSS:
        if isinstance(run_id, str) and run_id.strip():
            return f"assistant-chat-input-discuss-{run_id.strip()}"
        return "assistant-chat-input-discuss"
    if mode == ASSISTANT_MODE_HELP:
        return "assistant-chat-input-help"
    return "assistant-chat-input-draft"


def reset_ux_mode_and_picker(
    session_state: MutableMapping[str, Any],
    *,
    default_mode: str,
) -> None:
    """Pop widget keys then restore defaults after a thesis switch.

    Streamlit binds ``assistant_ux_mode`` / ``assistant_discuss_run_picker`` as
    widget keys (RUX-2). Popping clears stale selectbox options; rewriting
    restores inventory defaults for the next render.
    """
    session_state.pop(ASSISTANT_MODE_SESSION_KEY, None)
    session_state.pop(DISCUSS_RUN_PICKER_KEY, None)
    resolved = (
        default_mode.strip()
        if isinstance(default_mode, str) and default_mode.strip() in ASSISTANT_MODES
        else ASSISTANT_MODE_DISCUSS
    )
    session_state[ASSISTANT_MODE_SESSION_KEY] = resolved
    session_state[DISCUSS_RUN_PICKER_KEY] = None
