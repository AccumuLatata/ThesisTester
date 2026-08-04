"""Controlled classic-page proposal draft + explicit apply (CAI-9).

The Assistant may stage a JSON-safe draft change for review. Classic pages own
mutation: settings change only when the user clicks Apply on the owning page.
Kept out of ``classic_context`` so link/create remain non-recording / non-mutating.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping

from thesistester.classic_context import (
    get_active_thesis_id,
    init_classic_session_state,
    resolve_pending_navigation_target,
    set_classic_flash,
    set_pending_navigation,
)

CLASSIC_PROPOSAL_SESSION_KEY = "classic_page_proposal"

# Allowlisted draft fields per classic page (JSON-safe scalars/lists only).
PROPOSAL_PAGE_FIELDS: dict[str, frozenset[str]] = {
    "pages/3_Setup_Builder.py": frozenset(
        {
            "selected_levels",
            "tolerance_ticks",
            "trigger",
            "direction",
            "confluence_mode",
            "min_confluences",
            "max_confluences",
            "naked_only",
        }
    ),
    "pages/7_Backtest.py": frozenset(
        {
            "stop_loss_ticks",
            "take_profit_ticks",
            "commission_per_side",
            "slippage_ticks",
        }
    ),
}

_SETUP_WIDGET_MAP: dict[str, str] = {
    "selected_levels": "_setup_builder_selected_levels",
    "tolerance_ticks": "_setup_builder_tolerance_ticks",
    "trigger": "_setup_builder_trigger",
    "direction": "_setup_builder_direction",
    "confluence_mode": "_setup_builder_confluence_mode",
    "min_confluences": "_setup_builder_min_confluences",
    "max_confluences": "_setup_builder_max_confluences",
    "naked_only": "_setup_builder_naked_only",
}

_BACKTEST_WIDGET_MAP: dict[str, str] = {
    "stop_loss_ticks": "backtest_sl_ticks",
    "take_profit_ticks": "backtest_tp_ticks",
    "commission_per_side": "backtest_commission_per_side",
    "slippage_ticks": "backtest_slippage_ticks",
}

# Must match Setup Builder CONFLUENCE_MODE_DISPLAY / selectbox labels.
_CONFLUENCE_MODE_DISPLAY = {
    "global_cluster": "Global cluster",
    "anchor_rules": "Anchor-based rules",
}
_ALLOWED_CONFLUENCE_MODES = frozenset(_CONFLUENCE_MODE_DISPLAY)


def validate_classic_proposal(
    *,
    target_page: str,
    draft_patch: Mapping[str, Any],
    note: str,
    evidence_paths: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Validate and normalize a classic proposal payload (no session mutation)."""
    resolved = resolve_pending_navigation_target(target_page)
    if resolved is None or resolved not in PROPOSAL_PAGE_FIELDS:
        raise ValueError(
            "target_page must be an allowlisted proposal page "
            f"({', '.join(sorted(PROPOSAL_PAGE_FIELDS))})."
        )
    if not isinstance(draft_patch, Mapping) or not draft_patch:
        raise ValueError("draft_patch must be a non-empty object.")
    text = str(note).strip()
    if not text:
        raise ValueError("note must be a non-empty string.")

    allowed = PROPOSAL_PAGE_FIELDS[resolved]
    unknown = sorted(str(key) for key in draft_patch if str(key) not in allowed)
    if unknown:
        raise ValueError(f"draft_patch contains disallowed fields for {resolved}: {unknown}")

    normalized: dict[str, Any] = {}
    for key, value in draft_patch.items():
        field = str(key)
        if field == "selected_levels":
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError("selected_levels must be a non-empty list of strings.")
            levels = [str(item).strip() for item in value if str(item).strip()]
            if not levels:
                raise ValueError("selected_levels must contain non-empty level names.")
            normalized[field] = levels
            continue
        if field in {
            "tolerance_ticks",
            "stop_loss_ticks",
            "take_profit_ticks",
            "commission_per_side",
            "slippage_ticks",
        }:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{field} must be a number.")
            number = float(value)
            # Match Backtest widget floors: SL/TP min_value=1; costs may be 0.
            if field in {"stop_loss_ticks", "take_profit_ticks"} and number < 1.0:
                raise ValueError(f"{field} must be >= 1.")
            if field in {"tolerance_ticks", "commission_per_side", "slippage_ticks"} and number < 0:
                raise ValueError(f"{field} must be >= 0.")
            normalized[field] = number
            continue
        if field in {"min_confluences", "max_confluences"}:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{field} must be an integer.")
            if value < 1:
                raise ValueError(f"{field} must be >= 1.")
            normalized[field] = int(value)
            continue
        if field == "naked_only":
            if not isinstance(value, bool):
                raise ValueError("naked_only must be a boolean.")
            normalized[field] = value
            continue
        if field in {"trigger", "direction", "confluence_mode"}:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string.")
            text_value = value.strip()
            if field == "confluence_mode" and text_value not in _ALLOWED_CONFLUENCE_MODES:
                raise ValueError(
                    "confluence_mode must be one of "
                    f"{sorted(_ALLOWED_CONFLUENCE_MODES)}, got {text_value!r}."
                )
            normalized[field] = text_value
            continue
        raise ValueError(f"Unsupported draft field: {field}")

    paths: list[str] = []
    if evidence_paths is not None:
        if not isinstance(evidence_paths, (list, tuple)):
            raise ValueError("evidence_paths must be a list of strings.")
        for path in evidence_paths:
            if not isinstance(path, str) or not path.strip():
                raise ValueError("evidence_paths entries must be non-empty strings.")
            paths.append(path.strip())

    return {
        "target_page": resolved,
        "draft_patch": normalized,
        "note": text,
        "evidence_paths": paths,
    }


def _resolve_proposal_thesis_id(
    session_state: Mapping[str, Any],
    *,
    thesis_id: str | None = None,
) -> str:
    """Resolve and validate the thesis scope for a staged proposal."""
    active = get_active_thesis_id(session_state)
    explicit = thesis_id.strip() if isinstance(thesis_id, str) and thesis_id.strip() else None
    if explicit and active and explicit != active:
        raise ValueError(
            "Cannot stage a proposal for a different thesis than the classic active thesis."
        )
    scoped = explicit or active
    if not isinstance(scoped, str) or not scoped.strip():
        raise ValueError("Classic proposals require an active thesis.")
    return scoped.strip()


def stage_classic_proposal(
    session_state: MutableMapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    navigate: bool = True,
    thesis_id: str | None = None,
) -> dict[str, Any]:
    """Stage a validated proposal for classic review (does not apply settings)."""
    validated = validate_classic_proposal(
        target_page=str(proposal.get("target_page", "")),
        draft_patch=proposal.get("draft_patch")
        if isinstance(proposal.get("draft_patch"), Mapping)
        else {},
        note=str(proposal.get("note", "")),
        evidence_paths=proposal.get("evidence_paths")
        if isinstance(proposal.get("evidence_paths"), (list, tuple))
        else None,
    )
    init_classic_session_state(session_state)
    scoped_thesis = _resolve_proposal_thesis_id(
        session_state,
        thesis_id=thesis_id
        if thesis_id is not None
        else (str(proposal["thesis_id"]) if isinstance(proposal.get("thesis_id"), str) else None),
    )
    staged = {**validated, "thesis_id": scoped_thesis}
    session_state[CLASSIC_PROPOSAL_SESSION_KEY] = deepcopy(staged)
    # Keep thesis-scoped clear contract: also mirror into classic_* clear set via helper.
    set_classic_flash(
        session_state,
        level="info",
        message=(
            f"Assistant proposal staged for {staged['target_page'].split('/')[-1]} — "
            "review and Apply on the owning page."
        ),
    )
    if navigate:
        set_pending_navigation(session_state, staged["target_page"])
    return staged


def get_classic_proposal(session_state: Mapping[str, Any]) -> dict[str, Any] | None:
    payload = session_state.get(CLASSIC_PROPOSAL_SESSION_KEY)
    if not isinstance(payload, Mapping):
        return None
    thesis_id = payload.get("thesis_id")
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        # Unscoped / legacy staged proposals fail closed.
        return None
    thesis_id = thesis_id.strip()
    active = get_active_thesis_id(session_state)
    if active is not None and active != thesis_id:
        return None
    try:
        validated = validate_classic_proposal(
            target_page=str(payload.get("target_page", "")),
            draft_patch=payload.get("draft_patch")
            if isinstance(payload.get("draft_patch"), Mapping)
            else {},
            note=str(payload.get("note", "")),
            evidence_paths=payload.get("evidence_paths")
            if isinstance(payload.get("evidence_paths"), (list, tuple))
            else None,
        )
    except ValueError:
        return None
    return {**validated, "thesis_id": thesis_id}


def clear_classic_proposal(session_state: MutableMapping[str, Any]) -> None:
    init_classic_session_state(session_state)
    session_state[CLASSIC_PROPOSAL_SESSION_KEY] = None


def apply_classic_proposal(
    session_state: MutableMapping[str, Any],
    *,
    target_page: str,
) -> dict[str, Any]:
    """Apply a staged proposal onto classic widget keys (user-explicit only)."""
    proposal = get_classic_proposal(session_state)
    if proposal is None:
        raise ValueError("No classic page proposal is staged.")
    active_thesis = require_active_thesis_for_proposal(session_state)
    if proposal.get("thesis_id") != active_thesis:
        raise ValueError(
            "Staged proposal belongs to another thesis; re-link the proposing thesis to Apply."
        )
    if proposal["target_page"] != target_page:
        raise ValueError(f"Staged proposal targets {proposal['target_page']}, not {target_page}.")
    patch = proposal["draft_patch"]
    applied: dict[str, Any] = {}
    if target_page == "pages/3_Setup_Builder.py":
        for field, widget_key in _SETUP_WIDGET_MAP.items():
            if field not in patch:
                continue
            value = patch[field]
            if field == "confluence_mode":
                session_state[widget_key] = _CONFLUENCE_MODE_DISPLAY.get(value, value)
            else:
                session_state[widget_key] = deepcopy(value)
            applied[field] = value
        # Keep producer key in sync when present.
        setup = session_state.get("setup_config")
        if isinstance(setup, MutableMapping):
            for field, value in applied.items():
                setup[field] = deepcopy(value)
    elif target_page == "pages/7_Backtest.py":
        for field, widget_key in _BACKTEST_WIDGET_MAP.items():
            if field not in patch:
                continue
            session_state[widget_key] = patch[field]
            applied[field] = patch[field]
        # Keep producer key in sync when present — classic_state_to_run_spec /
        # CAI-7 ledger prefer backtest_config over widget keys when set.
        backtest_config = session_state.get("backtest_config")
        if isinstance(backtest_config, MutableMapping):
            for field, value in applied.items():
                backtest_config[field] = deepcopy(value)
        costs = session_state.get("backtest_execution_costs")
        if isinstance(costs, MutableMapping):
            for field in ("commission_per_side", "slippage_ticks"):
                if field in applied:
                    costs[field] = deepcopy(applied[field])
    else:
        raise ValueError(f"Apply is not implemented for {target_page}.")

    clear_classic_proposal(session_state)
    set_classic_flash(
        session_state,
        level="success",
        message=f"Applied Assistant proposal ({len(applied)} field(s)). Re-run the page action to execute.",
    )
    return {"applied": applied, "target_page": target_page}


def render_classic_proposal_card(
    *,
    target_page: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Render review/Apply/Dismiss UI when a proposal targets this page."""
    import streamlit as st

    state = session_state if session_state is not None else st.session_state
    proposal = get_classic_proposal(state)
    if proposal is None or proposal["target_page"] != target_page:
        return

    st.info(f"Assistant proposal: {proposal['note']}")
    st.json(proposal["draft_patch"])
    if proposal["evidence_paths"]:
        st.caption("Evidence paths: " + ", ".join(proposal["evidence_paths"]))
    apply_col, dismiss_col = st.columns(2)
    with apply_col:
        if st.button(
            "Apply Assistant proposal",
            key=f"classic_apply_proposal_{target_page}",
            type="primary",
            use_container_width=True,
        ):
            try:
                apply_classic_proposal(state, target_page=target_page)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with dismiss_col:
        if st.button(
            "Dismiss proposal",
            key=f"classic_dismiss_proposal_{target_page}",
            use_container_width=True,
        ):
            clear_classic_proposal(state)
            st.rerun()


def require_active_thesis_for_proposal(session_state: Mapping[str, Any]) -> str:
    thesis_id = get_active_thesis_id(session_state)
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("Classic proposals require an active thesis.")
    return thesis_id
