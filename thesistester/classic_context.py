"""Classic-workspace thesis research context (CAI-5).

Streamlit-free session-state helpers for entering/leaving an explicit thesis
context on classic pages. Executable settings remain page-owned; thesis prose
stays on the Research Assistant conversation path. Linking or creating a thesis
must never record a run.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

# Additive Streamlit keys owned by classic research-mode chrome (CAI-5).
CLASSIC_SESSION_KEYS: tuple[str, ...] = (
    "classic_active_thesis_id",
    "classic_active_thesis_name",
    "classic_recording_policy",
    "classic_pending_navigation",
    "classic_bound_dataset_id",
    "classic_flash",
)

# Cleared when exiting research mode or when the bound dataset changes.
CLASSIC_THESIS_SCOPED_KEYS: tuple[str, ...] = (
    "classic_active_thesis_id",
    "classic_active_thesis_name",
    "classic_pending_navigation",
    "classic_bound_dataset_id",
    "classic_flash",
)

# CAI-0 default is manual; all_executions remains deferred to CAI-7.
RECORDING_POLICIES: tuple[str, ...] = ("manual", "all_executions")
DEFAULT_RECORDING_POLICY: str = "manual"

# Allowlisted page script paths for classic_pending_navigation → st.switch_page.
CLASSIC_PENDING_NAVIGATION_PAGES: frozenset[str] = frozenset(
    {
        "pages/1_Data.py",
        "pages/2_Levels.py",
        "pages/3_Setup_Builder.py",
        "pages/6_Signals.py",
        "pages/7_Backtest.py",
        "pages/8_Grid_Search.py",
        "pages/9_Time_Analysis.py",
        "pages/10_Validation.py",
        "pages/11_Report_Export.py",
        "pages/12_Research_Bundles.py",
        "pages/13_Portfolio.py",
        "pages/14_Research_Assistant.py",
    }
)

# Canonical classic producer keys that must retain value and type across
# thesis link/create/exit (session-state contract gate).
PROTECTED_CLASSIC_SESSION_KEYS: tuple[str, ...] = (
    "data",
    "dataset_id",
    "instrument",
    "base_interval",
    "source_timezone",
    "exchange_timezone",
    "format_profile",
    "levels",
    "session_levels",
    "levels_settings",
    "levels_data_fingerprint",
    "setup_config",
    "signals",
    "confluence_zones",
    "naked_flags",
    "last_signal_setup",
    "signal_settings",
    "trades",
    "equity_curve",
    "backtest_config",
    "backtest_summary",
)


def init_classic_session_state(session_state: MutableMapping[str, Any]) -> None:
    """Ensure every documented classic_* research-context key exists."""
    defaults: dict[str, Any] = {
        "classic_active_thesis_id": None,
        "classic_active_thesis_name": None,
        "classic_recording_policy": DEFAULT_RECORDING_POLICY,
        "classic_pending_navigation": None,
        "classic_bound_dataset_id": None,
        "classic_flash": None,
    }
    for key, value in defaults.items():
        session_state.setdefault(key, deepcopy(value) if isinstance(value, (dict, list)) else value)


def set_classic_flash(
    session_state: MutableMapping[str, Any],
    *,
    level: str,
    message: str,
) -> None:
    """Stage a one-shot UI notice that survives the next ``st.rerun()``."""
    if level not in {"success", "info", "warning", "error"}:
        raise ValueError("flash level must be success, info, warning, or error.")
    text = str(message).strip()
    if not text:
        raise ValueError("flash message must be a non-empty string.")
    init_classic_session_state(session_state)
    session_state["classic_flash"] = {"level": level, "message": text}


def consume_classic_flash(
    session_state: MutableMapping[str, Any],
) -> dict[str, str] | None:
    """Pop and return the staged flash payload, if any."""
    init_classic_session_state(session_state)
    flash = session_state.get("classic_flash")
    session_state["classic_flash"] = None
    if not isinstance(flash, Mapping):
        return None
    level = flash.get("level")
    message = flash.get("message")
    if level not in {"success", "info", "warning", "error"}:
        return None
    if not isinstance(message, str) or not message.strip():
        return None
    return {"level": str(level), "message": message.strip()}


def get_recording_policy(session_state: Mapping[str, Any]) -> str:
    """Return the classic recording policy (default ``manual``)."""
    policy = session_state.get("classic_recording_policy", DEFAULT_RECORDING_POLICY)
    if policy in RECORDING_POLICIES:
        return str(policy)
    return DEFAULT_RECORDING_POLICY


def set_recording_policy(session_state: MutableMapping[str, Any], policy: str) -> None:
    """Persist a recording policy (``manual`` or ``all_executions``, CAI-7)."""
    if policy not in RECORDING_POLICIES:
        raise ValueError(f"recording policy must be one of {RECORDING_POLICIES}, got {policy!r}.")
    init_classic_session_state(session_state)
    session_state["classic_recording_policy"] = policy


def is_research_mode(session_state: Mapping[str, Any]) -> bool:
    """True when a classic thesis context is active."""
    thesis_id = session_state.get("classic_active_thesis_id")
    return isinstance(thesis_id, str) and bool(thesis_id.strip())


def get_active_thesis_id(session_state: Mapping[str, Any]) -> str | None:
    """Return the active classic thesis id, or None."""
    thesis_id = session_state.get("classic_active_thesis_id")
    if isinstance(thesis_id, str) and thesis_id.strip():
        return thesis_id
    return None


def get_active_thesis_name(session_state: Mapping[str, Any]) -> str | None:
    """Return the cached active thesis display name, or None."""
    name = session_state.get("classic_active_thesis_name")
    if isinstance(name, str) and name.strip():
        return name
    return None


def set_pending_navigation(session_state: MutableMapping[str, Any], target: str) -> None:
    """Stage an optional page navigation target (page script path)."""
    text = str(target).strip()
    if not text:
        raise ValueError("pending navigation target must be a non-empty string.")
    init_classic_session_state(session_state)
    session_state["classic_pending_navigation"] = text


def consume_pending_navigation(session_state: MutableMapping[str, Any]) -> str | None:
    """Pop and return the staged navigation target, if any."""
    init_classic_session_state(session_state)
    target = session_state.get("classic_pending_navigation")
    session_state["classic_pending_navigation"] = None
    if isinstance(target, str) and target.strip():
        return target.strip()
    return None


def resolve_pending_navigation_target(target: str | None) -> str | None:
    """Return an allowlisted page path for ``st.switch_page``, or None."""
    if not isinstance(target, str):
        return None
    text = target.strip().replace("\\", "/")
    if text in CLASSIC_PENDING_NAVIGATION_PAGES:
        return text
    return None


def _clear_classic_relink_flags(session_state: MutableMapping[str, Any]) -> None:
    """Reset per-page relink UI toggles after exit or dataset switch."""
    for key in list(session_state.keys()):
        if isinstance(key, str) and key.startswith("_classic_relink_open_"):
            session_state[key] = False


def clear_classic_thesis_context(session_state: MutableMapping[str, Any]) -> None:
    """Drop thesis-scoped classic research context without touching page state."""
    init_classic_session_state(session_state)
    session_state["classic_active_thesis_id"] = None
    session_state["classic_active_thesis_name"] = None
    session_state["classic_pending_navigation"] = None
    session_state["classic_bound_dataset_id"] = None
    session_state["classic_flash"] = None
    _clear_classic_relink_flags(session_state)


def exit_research_mode(session_state: MutableMapping[str, Any]) -> None:
    """Leave classic research mode. Does not clear Assistant thesis selection."""
    clear_classic_thesis_context(session_state)


def sync_classic_context_for_dataset(
    session_state: MutableMapping[str, Any],
    dataset_id: str | None,
) -> bool:
    """Clear classic thesis context when the active dataset diverges.

    Linking before a dataset exists stores ``classic_bound_dataset_id=None``.
    When a dataset later appears, adopt that id rather than treating unset→set
    as a switch. Only a concrete bound that disagrees with the current id
    clears research mode.

    Returns True when context was cleared due to a dataset switch.
    """
    init_classic_session_state(session_state)
    if not is_research_mode(session_state):
        return False
    bound = session_state.get("classic_bound_dataset_id")
    current = dataset_id if isinstance(dataset_id, str) and dataset_id.strip() else None
    bound_norm = bound if isinstance(bound, str) and bound.strip() else None
    if bound_norm == current:
        return False
    if bound_norm is None and current is not None:
        session_state["classic_bound_dataset_id"] = current
        return False
    clear_classic_thesis_context(session_state)
    return True


def link_thesis(
    session_state: MutableMapping[str, Any],
    *,
    thesis_id: str,
    thesis_name: str,
    dataset_id: str | None,
) -> None:
    """Enter classic research mode for an existing thesis.

    Syncs ``assistant_selected_thesis_id`` so Research Assistant stays aligned.
    Does **not** record a run, create a specification, or mutate executable
    classic page keys.
    """
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("thesis_id must be a non-empty string.")
    name = str(thesis_name).strip()
    if not name:
        raise ValueError("thesis_name must be a non-empty string.")

    init_classic_session_state(session_state)
    bound = dataset_id if isinstance(dataset_id, str) and dataset_id.strip() else None
    session_state["classic_active_thesis_id"] = thesis_id.strip()
    session_state["classic_active_thesis_name"] = name
    session_state["classic_bound_dataset_id"] = bound

    # Keep Assistant page selection consistent; staging clears on thesis change.
    from thesistester.assistant.workspace import (
        init_assistant_session_state,
        select_thesis,
    )

    init_assistant_session_state(session_state)
    select_thesis(session_state, thesis_id.strip())


def snapshot_protected_classic_keys(
    session_state: Mapping[str, Any],
    keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Capture identity/type of protected classic keys for contract tests."""
    selected = tuple(keys) if keys is not None else PROTECTED_CLASSIC_SESSION_KEYS
    return {key: session_state[key] for key in selected if key in session_state}


def assert_protected_classic_keys_unchanged(
    before: Mapping[str, Any],
    session_state: Mapping[str, Any],
) -> None:
    """Fail when a protected classic key changed identity or type."""
    for key, prior in before.items():
        if key not in session_state:
            raise AssertionError(f"protected classic key {key!r} was removed.")
        current = session_state[key]
        if type(current) is not type(prior):
            raise AssertionError(
                f"protected classic key {key!r} changed type: "
                f"{type(prior).__name__} -> {type(current).__name__}."
            )
        if current is not prior and current != prior:
            raise AssertionError(f"protected classic key {key!r} changed value.")


def render_classic_thesis_chrome(
    *,
    page_key: str,
    allow_create_link: bool = False,
    dataset_id: str | None = None,
) -> None:
    """Compact thesis breadcrumb / create-link chrome for classic pages.

    Imports Streamlit lazily so pure helpers stay Streamlit-free for tests.
    """
    import streamlit as st

    from thesistester.assistant import AssistantOrchestrator

    if not isinstance(page_key, str) or not page_key.strip():
        raise ValueError("page_key must be a non-empty string.")
    page = page_key.strip()

    init_classic_session_state(st.session_state)
    sync_classic_context_for_dataset(st.session_state, dataset_id)

    flash = consume_classic_flash(st.session_state)
    if flash is not None:
        getattr(st, flash["level"])(flash["message"])

    pending = consume_pending_navigation(st.session_state)
    if pending is not None:
        resolved = resolve_pending_navigation_target(pending)
        if resolved is None:
            st.warning(f"Ignored invalid pending navigation target: `{pending}`")
        else:
            st.switch_page(resolved)

    if is_research_mode(st.session_state):
        thesis_id = get_active_thesis_id(st.session_state) or ""
        thesis_name = get_active_thesis_name(st.session_state) or thesis_id
        policy = get_recording_policy(st.session_state)
        short_id = thesis_id[-8:] if len(thesis_id) >= 8 else thesis_id
        st.caption(f"Research mode · **{thesis_name}** (`…{short_id}`) · recording: `{policy}`")
        col_exit, col_relink, col_policy = st.columns([1, 1, 2])
        with col_exit:
            if st.button(
                "Exit research mode",
                key=f"classic_exit_research_{page}",
                use_container_width=True,
            ):
                exit_research_mode(st.session_state)
                st.session_state[f"_classic_relink_open_{page}"] = False
                set_classic_flash(
                    st.session_state,
                    level="info",
                    message="Left classic research mode. Page settings are unchanged.",
                )
                st.rerun()
        with col_relink:
            if st.button(
                "Relink thesis",
                key=f"classic_relink_toggle_{page}",
                use_container_width=True,
            ):
                open_key = f"_classic_relink_open_{page}"
                st.session_state[open_key] = not bool(st.session_state.get(open_key))
                st.rerun()
        with col_policy:
            policy_labels = {
                "manual": "Manual — Record and discuss after a run",
                "all_executions": "All executions — ledger every Backtest attempt",
            }
            selected_policy = st.selectbox(
                "Recording policy",
                options=list(RECORDING_POLICIES),
                index=list(RECORDING_POLICIES).index(policy)
                if policy in RECORDING_POLICIES
                else 0,
                format_func=lambda value: policy_labels.get(value, value),
                key=f"classic_recording_policy_widget_{page}",
                help=(
                    "Manual keeps exploration untracked until you click "
                    "Record and discuss. All executions records completed, "
                    "failed, and cancelled Backtest attempts under this thesis."
                ),
            )
            if selected_policy != policy:
                set_recording_policy(st.session_state, selected_policy)
                st.rerun()
        if st.session_state.get(f"_classic_relink_open_{page}"):
            _render_link_thesis_form(
                st,
                orchestrator=AssistantOrchestrator.for_local_workspace(),
                page=page,
                dataset_id=dataset_id,
                form_key_suffix="relink",
            )
        return

    if not allow_create_link:
        return

    with st.expander("Thesis research context", expanded=False):
        st.caption(
            "Optional. Link a thesis to discuss classic runs later. "
            "Linking does not record a run or change setup settings."
        )
        create_tab, link_tab = st.tabs(["Create thesis", "Link existing"])
        orchestrator = AssistantOrchestrator.for_local_workspace()
        with create_tab:
            new_name = st.text_input(
                "Thesis name",
                key=f"classic_create_thesis_name_{page}",
            )
            if st.button(
                "Create and link thesis",
                key=f"classic_create_thesis_btn_{page}",
                use_container_width=True,
            ):
                try:
                    thesis = orchestrator.create_thesis(name=new_name)
                    link_thesis(
                        st.session_state,
                        thesis_id=thesis.thesis_id,
                        thesis_name=thesis.name,
                        dataset_id=dataset_id,
                    )
                    set_classic_flash(
                        st.session_state,
                        level="success",
                        message=(
                            f"Created and linked thesis “{thesis.name}”. No run was recorded."
                        ),
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with link_tab:
            _render_link_thesis_form(
                st,
                orchestrator=orchestrator,
                page=page,
                dataset_id=dataset_id,
                form_key_suffix="link",
            )


def _render_link_thesis_form(
    st: Any,
    *,
    orchestrator: Any,
    page: str,
    dataset_id: str | None,
    form_key_suffix: str,
) -> None:
    theses = orchestrator.list_theses(include_archived=False)
    if not theses:
        st.info("No active theses yet. Create one first.")
        return
    labels = {thesis.thesis_id: f"{thesis.name} ({thesis.thesis_id[-8:]})" for thesis in theses}
    thesis_ids = [thesis.thesis_id for thesis in theses]
    selected_id = st.selectbox(
        "Existing thesis",
        thesis_ids,
        format_func=labels.get,
        index=None,
        key=f"classic_link_thesis_select_{page}_{form_key_suffix}",
    )
    if st.button(
        "Link thesis",
        key=f"classic_link_thesis_btn_{page}_{form_key_suffix}",
        use_container_width=True,
        disabled=selected_id is None,
    ):
        if selected_id is None:
            st.error("Select a thesis to link.")
            return
        thesis = orchestrator.get_thesis(selected_id)
        link_thesis(
            st.session_state,
            thesis_id=thesis.thesis_id,
            thesis_name=thesis.name,
            dataset_id=dataset_id,
        )
        st.session_state[f"_classic_relink_open_{page}"] = False
        set_classic_flash(
            st.session_state,
            level="success",
            message=f"Linked thesis “{thesis.name}”. No run was recorded.",
        )
        st.rerun()
