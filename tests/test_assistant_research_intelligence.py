"""RI-1 Research Intelligence: grid ranking matcher, short-circuit, deterministic slice."""

from __future__ import annotations

import pytest

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm import load_results_qa_settings
from thesistester.assistant.llm_explainer import LLMEvidenceError
from thesistester.assistant.results_overview import (
    INTENT_GRID_RANKING,
    INTENT_MIXED_ASK,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    REASON_MISSING_GRID,
    REASON_MIXED_ASK,
    REASON_PATH_MISS,
    has_overview_negative_cue,
    match_discuss_intent,
    match_overview_intent,
    present_grid_allowlist,
)
from thesistester.assistant.results_projections import build_ephemeral_results_context
from thesistester.assistant.results_qa import propose_results_reply


def _packet(*, best_grid: bool = True, projections: bool = False) -> EvidencePacket:
    results: dict = {
        "trade_summary": {
            "trade_count": 42,
            "expectancy_r": 0.25,
            "win_rate": 0.52,
            "profit_factor": 1.4,
            "max_drawdown_r": -2.0,
            "total_r": 10.5,
        }
    }
    if best_grid:
        results["best_grid_result"] = {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 40,
            "expectancy_r": 0.3,
            "ranking_metric": "expectancy_r",
        }
    return EvidencePacket(
        provenance={"run_id": "run_ri1"},
        assumptions={
            "instrument": "NQ",
            "grid": {"ranking_metric": "expectancy_r"},
            "costs_exposure": {"commission_per_side": 0.0, "slippage_ticks": 1},
        },
        results=results,
        warnings=(),
        limitations=("Time analysis is not present in this evidence packet.",),
    )


class _FailClient:
    def __init__(self, payload_or_exc):
        self._items = list(payload_or_exc) if isinstance(payload_or_exc, list) else [payload_or_exc]
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        item = self._items[min(self.calls - 1, len(self._items) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


def _uncited_digits_payload() -> dict:
    return {
        "summary": "Best SL is 99 and TP is 88 under a secret metric.",
        "caveats": ["Invented ranks."],
        "claims": [
            {
                "text": "Best stop is 99.",
                "path": "results.trade_summary.trade_count",
            }
        ],
        "followups": ["Deploy this now."],
    }


def test_match_discuss_intent_grid_overview_mixed_and_residual():
    assert match_discuss_intent("What is the best SL/TP?") == INTENT_GRID_RANKING
    assert match_discuss_intent("summary of best SL/TP") == INTENT_GRID_RANKING
    assert match_discuss_intent("grid ranking please") == INTENT_GRID_RANKING
    assert match_discuss_intent("Give me the KPIs of this run") == OVERVIEW_INTENT_KPI
    assert match_discuss_intent("summarize this run") == OVERVIEW_INTENT_RUN
    assert match_discuss_intent("KPIs and best SL/TP") == INTENT_MIXED_ASK
    assert match_discuss_intent("Summarize the walk-forward results") is None
    assert match_discuss_intent("Give me KPIs and validation stats") is None
    # Overview wrapper stays vetoed for specialist / residual topics.
    assert match_overview_intent("summary of best SL/TP") is None
    assert match_overview_intent("KPIs and best SL/TP") is None
    assert match_overview_intent("Give me KPIs and validation stats") is None
    assert match_overview_intent("summarize this run") == OVERVIEW_INTENT_RUN


def test_residual_veto_and_false_friends_for_overview_negative_export():
    assert has_overview_negative_cue("What is the best SL/TP?") is True
    assert has_overview_negative_cue("summarize the walk-forward results") is True
    assert has_overview_negative_cue("validation diagnostics please") is True
    assert has_overview_negative_cue("KPIs and best SL/TP") is True
    assert has_overview_negative_cue("ranking alone without grid") is True
    assert has_overview_negative_cue("runtime of this batch") is False
    assert has_overview_negative_cue("stopwatch only") is False
    assert has_overview_negative_cue("non-stop session") is False
    assert has_overview_negative_cue("off-grid idea") is False
    assert has_overview_negative_cue("tell me about this") is False


def test_r1_uncited_llm_digits_fall_back_to_deterministic_grid():
    packet = _packet(best_grid=True)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best SL/TP?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.grid_rankings.best.stop_loss_ticks" in paths
    assert "results.projections.grid_rankings.best.take_profit_ticks" in paths
    assert any(claim.value == 8 for claim in reply.claims)
    assert any(claim.value == 16 for claim in reply.claims)
    assert "99" not in reply.summary
    assert client.calls == 1


def test_r2_missing_grid_short_circuits_without_llm():
    packet = _packet(best_grid=False)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best SL/TP?",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_GRID
    assert "grid" in reply.summary.lower()
    assert "99" not in reply.summary


def test_r13_mixed_ask_narrow_remediation_without_llm():
    packet = _packet(best_grid=True)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="KPIs and best SL/TP",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MIXED_ASK
    assert "mix" in reply.summary.lower() or "one topic" in reply.summary.lower()
    assert not any("trade_summary" in c.path for c in reply.claims)


def test_r16_specialist_flag_off_restores_remediation_on_grounding_miss():
    packet = _packet(best_grid=True)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best SL/TP?",
        turn_context=context,
        repair_retry_enabled=False,
        deterministic_specialist_fallback=False,
    )
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_PATH_MISS or "could not ground" in reply.summary.lower()
    assert not any(
        "stop_loss_ticks" in c.path for c in reply.claims
    ), "flags-off must not emit deterministic grid claims"


def test_r19_pure_overview_unchanged():
    packet = _packet(best_grid=True)
    client = _FailClient(
        {
            "summary": "Win rate is 52%.",
            "caveats": ["Sample only."],
            "claims": [
                {
                    "text": "Win rate is 52%.",
                    "path": "results.trade_summary.win_rate",
                }
            ],
            "followups": ["Ask about validation next."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="summarize this run",
    )
    assert any(c.path == "results.trade_summary.win_rate" for c in reply.claims)


def test_r23_residual_validation_still_refuses_overview_slice():
    packet = _packet(best_grid=True)
    client = _FailClient(
        {
            "summary": "Trade count is 42.",
            "caveats": ["Wrong topic."],
            "claims": [
                {
                    "text": "Trade count is 42.",
                    "path": "results.trade_summary.trade_count",
                }
            ],
            "followups": ["Ask again."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Give me KPIs and validation stats",
        repair_retry_enabled=False,
    )
    # Residual veto → LLM may succeed, but overview deterministic fallback must not
    # rewrite a failed specialist/residual ask into KPI slice when LLM fails.
    assert match_discuss_intent("Give me KPIs and validation stats") is None
    assert has_overview_negative_cue("Give me KPIs and validation stats") is True
    # Force LLM failure path:
    client = _FailClient(
        LLMEvidenceError("Results Q&A claim path 'results.validation.trade_count' is missing from the evidence packet.")
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Give me KPIs and validation stats",
        repair_retry_enabled=False,
    )
    assert reply.claims == ()
    assert not any("trade_summary" in c.path for c in reply.claims)


def test_grid_allowlist_from_projections_context():
    packet = _packet(best_grid=True)
    context = build_ephemeral_results_context(packet)
    paths = present_grid_allowlist(context)
    assert "results.projections.grid_rankings.best.stop_loss_ticks" in paths
    assert "results.projections.grid_rankings.selection_scope" in paths
    assert "results.projections.grid_rankings.oos_status" in paths


def test_settings_default_specialist_fallback_true():
    settings = load_results_qa_settings("config/assistant.toml")
    assert settings.deterministic_specialist_fallback is True


def test_di_flags_off_still_hard_fails_overview():
    packet = _packet(best_grid=True)
    client = _FailClient(
        LLMEvidenceError(
            "Results Q&A claim path 'results.instrument' is missing from the evidence packet."
        )
    )
    with pytest.raises(LLMEvidenceError, match="missing from the evidence packet"):
        propose_results_reply(
            client,
            packet=packet,
            history=(),
            user_message="Give me the KPIs of this run",
            repair_retry_enabled=False,
            deterministic_overview_fallback=False,
            deterministic_specialist_fallback=False,
        )
