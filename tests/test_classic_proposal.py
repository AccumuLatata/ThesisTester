"""Direct tests for classic proposal helpers (QI-11-01 / B-7).

CAI-9 already stages/applies through ``test_cai9_page_capabilities.py``.
This file covers the public helper matrix that had no dedicated file:
``validate_classic_proposal`` field floors, ``clear_classic_proposal``,
``require_active_thesis_for_proposal``, and ``stage_classic_proposal(..., navigate=False)``.
"""

from __future__ import annotations

import pytest

from thesistester.classic_context import (
    consume_pending_navigation,
    init_classic_session_state,
    link_thesis,
)
from thesistester.classic_proposal import (
    CLASSIC_PROPOSAL_SESSION_KEY,
    apply_classic_proposal,
    clear_classic_proposal,
    get_classic_proposal,
    render_classic_proposal_card,
    require_active_thesis_for_proposal,
    stage_classic_proposal,
    validate_classic_proposal,
)


def _linked_session() -> dict:
    session: dict = {}
    init_classic_session_state(session)
    link_thesis(
        session,
        thesis_id="th" + ("a" * 32),
        thesis_name="Proposal thesis",
        dataset_id="ds_test",
    )
    return session


def test_validate_classic_proposal_setup_and_backtest_fields():
    setup = validate_classic_proposal(
        target_page="pages/3_Setup_Builder.py",
        draft_patch={
            "selected_levels": [" ONH ", "ONL"],
            "tolerance_ticks": 2,
            "min_confluences": 2,
            "max_confluences": 3,
            "naked_only": False,
            "confluence_mode": "global_cluster",
            "trigger": "close",
            "direction": "long",
        },
        note="  tighten setup  ",
        evidence_paths=(" /tmp/a.md ",),
    )
    assert setup["draft_patch"]["selected_levels"] == ["ONH", "ONL"]
    assert setup["note"] == "tighten setup"
    assert setup["evidence_paths"] == ["/tmp/a.md"]

    backtest = validate_classic_proposal(
        target_page="pages/7_Backtest.py",
        draft_patch={
            "stop_loss_ticks": 8,
            "take_profit_ticks": 12,
            "commission_per_side": 0,
            "slippage_ticks": 0.25,
        },
        note="costs",
    )
    assert backtest["draft_patch"]["stop_loss_ticks"] == 8.0
    assert backtest["draft_patch"]["commission_per_side"] == 0.0


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {
                "target_page": "pages/1_Data.py",
                "draft_patch": {"stop_loss_ticks": 8},
                "note": "x",
            },
            "allowlisted proposal page",
        ),
        (
            {"target_page": "pages/7_Backtest.py", "draft_patch": {}, "note": "x"},
            "non-empty object",
        ),
        (
            {
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"stop_loss_ticks": 8},
                "note": "  ",
            },
            "non-empty string",
        ),
        (
            {
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"stop_loss_ticks": 0},
                "note": "x",
            },
            "must be >= 1",
        ),
        (
            {
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"slippage_ticks": -1},
                "note": "x",
            },
            "must be >= 0",
        ),
        (
            {
                "target_page": "pages/3_Setup_Builder.py",
                "draft_patch": {"selected_levels": ["  "]},
                "note": "x",
            },
            "non-empty level names",
        ),
        (
            {
                "target_page": "pages/3_Setup_Builder.py",
                "draft_patch": {"min_confluences": True},
                "note": "x",
            },
            "must be an integer",
        ),
        (
            {
                "target_page": "pages/3_Setup_Builder.py",
                "draft_patch": {"naked_only": "yes"},
                "note": "x",
            },
            "must be a boolean",
        ),
        (
            {
                "target_page": "pages/3_Setup_Builder.py",
                "draft_patch": {"confluence_mode": "not-a-mode"},
                "note": "x",
            },
            "confluence_mode must be one of",
        ),
        (
            {
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"stop_loss_ticks": 8, "unknown": 1},
                "note": "x",
            },
            "disallowed fields",
        ),
        (
            {
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"stop_loss_ticks": 8},
                "note": "x",
                "evidence_paths": "nope",
            },
            "list of strings",
        ),
    ],
)
def test_validate_classic_proposal_rejects_invalid_fields(kwargs, match):
    with pytest.raises(ValueError, match=match):
        validate_classic_proposal(**kwargs)


def test_stage_without_navigate_clear_and_require_active_thesis():
    session = _linked_session()
    staged = stage_classic_proposal(
        session,
        {
            "target_page": "pages/7_Backtest.py",
            "draft_patch": {"stop_loss_ticks": 8, "take_profit_ticks": 12},
            "note": "stage only",
        },
        navigate=False,
    )
    assert staged["thesis_id"].startswith("th")
    assert consume_pending_navigation(session) is None
    assert get_classic_proposal(session)["note"] == "stage only"

    clear_classic_proposal(session)
    assert session[CLASSIC_PROPOSAL_SESSION_KEY] is None
    assert get_classic_proposal(session) is None
    with pytest.raises(ValueError, match="No classic page proposal"):
        apply_classic_proposal(session, target_page="pages/7_Backtest.py")

    empty: dict = {}
    init_classic_session_state(empty)
    with pytest.raises(ValueError, match="active thesis"):
        require_active_thesis_for_proposal(empty)
    assert require_active_thesis_for_proposal(session) == session["classic_active_thesis_id"]


def test_render_classic_proposal_card_stub(monkeypatch: pytest.MonkeyPatch):
    from tests.test_classic_context import install_classic_streamlit_stub

    session = _linked_session()
    stub = install_classic_streamlit_stub(monkeypatch, session)
    render_classic_proposal_card(target_page="pages/7_Backtest.py", session_state=session)
    assert not any(name == "info" for name, _args, _kwargs in stub._calls)

    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 8, "take_profit_ticks": 12},
            note="raise SL",
            evidence_paths=["docs/note.md"],
        ),
        navigate=False,
    )
    stub = install_classic_streamlit_stub(monkeypatch, session)
    render_classic_proposal_card(target_page="pages/7_Backtest.py", session_state=session)
    assert any("raise SL" in str(args) for name, args, _kwargs in stub._calls if name == "info")
    assert any(name == "json" for name, _args, _kwargs in stub._calls)
    assert any(name == "caption" for name, _args, _kwargs in stub._calls)
    assert any(
        name == "button" and args == ("Apply Assistant proposal",)
        for name, args, _kwargs in stub._calls
    )
    assert any(
        name == "button" and args == ("Dismiss proposal",) for name, args, _kwargs in stub._calls
    )

    stub = install_classic_streamlit_stub(
        monkeypatch,
        session,
        button_clicks={"classic_apply_proposal_pages/7_Backtest.py": True},
    )
    render_classic_proposal_card(target_page="pages/7_Backtest.py", session_state=session)
    assert session.get("backtest_sl_ticks") == 8.0
    assert session.get("backtest_tp_ticks") == 12.0
    assert get_classic_proposal(session) is None
    assert any(name == "rerun" for name, _args, _kwargs in stub._calls)

    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 8, "take_profit_ticks": 12},
            note="raise SL",
            evidence_paths=["docs/note.md"],
        ),
        navigate=False,
    )
    stub = install_classic_streamlit_stub(
        monkeypatch,
        session,
        button_clicks={"classic_dismiss_proposal_pages/7_Backtest.py": True},
    )
    render_classic_proposal_card(target_page="pages/7_Backtest.py", session_state=session)
    assert get_classic_proposal(session) is None
    assert any(name == "rerun" for name, _args, _kwargs in stub._calls)
