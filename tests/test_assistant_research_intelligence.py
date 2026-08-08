"""RI Research Intelligence: grid + validation/WFA slices, residual veto, short-circuits."""

from __future__ import annotations

import pytest

from thesistester.assistant.explainer import EvidenceCaveat, EvidencePacket
from thesistester.assistant.llm import load_results_qa_settings
from thesistester.assistant.llm_explainer import LLMEvidenceError
from thesistester.assistant.results_overview import (
    INTENT_GRID_RANKING,
    INTENT_MIXED_ASK,
    INTENT_VALIDATION_WFA,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    REASON_MISSING_GRID,
    REASON_MISSING_VALIDATION,
    REASON_MIXED_ASK,
    REASON_PATH_MISS,
    build_deterministic_grid_ranking_reply,
    has_grid_ranking_evidence,
    has_overview_negative_cue,
    has_validation_wfa_evidence,
    match_discuss_intent,
    match_overview_intent,
    present_grid_allowlist,
    present_validation_allowlist,
)
from thesistester.assistant.results_projections import build_ephemeral_results_context
from thesistester.assistant.results_qa import propose_results_reply


def _packet(
    *,
    best_grid: bool = True,
    projections: bool = False,
    walk_forward: bool = False,
    validation: bool = False,
    missing_oos: bool = False,
) -> EvidencePacket:
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
    if walk_forward:
        results["walk_forward_summary"] = {
            "fold_count": 4,
            "valid_fold_count": 3,
            "median_test_expectancy_r": 0.12,
            "stitched_oos_total_r": 1.5,
            "stitched_oos_status": "ok",
            "status": "completed",
        }
    if validation:
        results["validation_summary"] = {
            "bootstrap": {
                "ci_lower": -0.1,
                "ci_upper": 0.4,
                "probability_positive": 0.72,
            },
            "grid_overfit": {"risk_level": "medium"},
        }
    caveats = ()
    if missing_oos:
        caveats = (
            EvidenceCaveat(
                code="missing_oos",
                message="Out-of-sample / walk-forward evidence is missing.",
            ),
        )
    return EvidencePacket(
        provenance={"run_id": "run_ri"},
        assumptions={
            "instrument": "NQ",
            "grid": {"ranking_metric": "expectancy_r"},
            "costs_exposure": {"commission_per_side": 0.0, "slippage_ticks": 1},
        },
        results=results,
        warnings=(),
        limitations=("Time analysis is not present in this evidence packet.",),
        caveats=caveats,
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
    # Multi-word grid positives must not be false-residualled by bare "stop"/"tp".
    assert match_discuss_intent("stop loss and take profit") == INTENT_GRID_RANKING
    assert match_discuss_intent("What is the stop loss?") == INTENT_GRID_RANKING
    assert match_discuss_intent("Give me the KPIs of this run") == OVERVIEW_INTENT_KPI
    assert match_discuss_intent("summarize this run") == OVERVIEW_INTENT_RUN
    assert match_discuss_intent("KPIs and best SL/TP") == INTENT_MIXED_ASK
    # Dual overview intents → mixed_ask (§4.1 |M|>=2).
    assert match_discuss_intent("Give me the KPIs and summarize this run") == INTENT_MIXED_ASK
    # RI-3: validation/WFA is a landed specialist (not residual).
    assert match_discuss_intent("Summarize the walk-forward results") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("validation diagnostics please") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("Give me KPIs and validation stats") == INTENT_MIXED_ASK
    assert match_discuss_intent("best SL and validation") == INTENT_MIXED_ASK
    # Residual cue not owned yet (time) still blocks even with landed specialists.
    assert match_discuss_intent("best SL and best time") is None
    assert match_discuss_intent("walk-forward by hour bucket") is None
    # Soft bare-grid residual must not veto lone validation_wfa.
    assert match_discuss_intent("tp and oos") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("oos for my tp") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("validation of my stop") == INTENT_VALIDATION_WFA
    # otf validation is RI-5 residual — not owned by bare RI-3 validation.
    assert match_discuss_intent("otf validation") is None
    assert has_overview_negative_cue("otf validation") is True
    # Other WFA cues still land even when OTF is mentioned in passing.
    assert (
        match_discuss_intent("walk-forward validation and otf notes") == INTENT_VALIDATION_WFA
    )
    # Bare permutation without validation-sense collocates does not match.
    assert match_discuss_intent("a permutation of the thesis") is None
    assert match_discuss_intent("bootstrap permutation test") == INTENT_VALIDATION_WFA
    # Bare short tokens without collocates are residual, not grid.
    assert match_discuss_intent("What's my stop?") is None
    assert match_discuss_intent("full stop") is None
    assert match_discuss_intent("show me the target") is None
    # Overview wrapper stays vetoed for specialist / residual topics.
    assert match_overview_intent("summary of best SL/TP") is None
    assert match_overview_intent("KPIs and best SL/TP") is None
    assert match_overview_intent("Give me KPIs and validation stats") is None
    assert match_overview_intent("Summarize the walk-forward results") is None
    assert match_overview_intent("summarize this run") == OVERVIEW_INTENT_RUN


def test_residual_veto_and_false_friends_for_overview_negative_export():
    assert has_overview_negative_cue("What is the best SL/TP?") is True
    assert has_overview_negative_cue("summarize the walk-forward results") is True
    assert has_overview_negative_cue("validation diagnostics please") is True
    assert has_overview_negative_cue("KPIs and best SL/TP") is True
    # Bare ranking (no grid collocate) stays residual — do not poison with "grid".
    assert match_discuss_intent("ranking alone") is None
    assert has_overview_negative_cue("ranking alone") is True
    assert match_discuss_intent("what is the ranking") is None
    assert has_overview_negative_cue("what is the ranking") is True
    # Bare stop/target still refuse overview (DX), but are not grid_ranking.
    assert has_overview_negative_cue("What's my stop?") is True
    assert has_overview_negative_cue("full stop") is True
    # mixed_ask (incl. dual overview) refuses overview envelopes for DX.
    assert has_overview_negative_cue("Give me the KPIs and summarize this run") is True
    # oos false friends must not fire validation ownership.
    assert match_discuss_intent("boost the sample") is None
    assert match_discuss_intent("loose ends only") is None
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
    assert not any("stop_loss_ticks" in c.path for c in reply.claims), (
        "flags-off must not emit deterministic grid claims"
    )


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


def test_r23_kpi_plus_validation_is_mixed_ask_not_kpi_slice():
    packet = _packet(best_grid=True, walk_forward=True)
    client = _FailClient(_uncited_digits_payload())
    assert match_discuss_intent("Give me KPIs and validation stats") == INTENT_MIXED_ASK
    assert has_overview_negative_cue("Give me KPIs and validation stats") is True
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Give me KPIs and validation stats",
        repair_retry_enabled=False,
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MIXED_ASK
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


def test_null_tp_leaf_is_missing_grid_not_sl_only_answer():
    """Narratable SL∧TP required — JSON-null TP must not yield SL-only best answer."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri1_null_tp"},
        assumptions={},
        results={
            "best_grid_result": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": None,
                "trade_count": 40,
            }
        },
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet)
    assert has_grid_ranking_evidence(context) is False
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
    assert "8" not in reply.summary


def test_projection_null_tp_falls_back_to_recorded_best_tp():
    """Per-leaf fallback: narratable recorded TP fills when projection TP is null."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri1_proj_null_tp"},
        assumptions={"grid": {"ranking_metric": "expectancy_r"}},
        results={
            "best_grid_result": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 40,
            },
            "projections": {
                "grid_rankings": {
                    "metric": "expectancy_r",
                    "selection_scope": "in_sample_grid",
                    "oos_status": "not_evaluated",
                    "best": {
                        "stop_loss_ticks": 8,
                        "take_profit_ticks": None,
                        "trade_count": 40,
                        "metric_value": 0.3,
                    },
                }
            },
        },
        warnings=(),
        limitations=(),
    )
    # Use packet results as turn context (skip ephemeral rebuild overwriting null).
    context = {
        "results": packet.results,
        "assumptions": packet.assumptions,
        "provenance": packet.provenance,
    }
    assert has_grid_ranking_evidence(context) is True
    reply = build_deterministic_grid_ranking_reply(packet, context)
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.grid_rankings.best.stop_loss_ticks" in paths
    assert "results.best_grid_result.take_profit_ticks" in paths
    assert any(claim.value == 16 for claim in reply.claims)
    assert "16" in reply.summary


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


def test_r6_uncited_llm_falls_back_to_deterministic_wfa():
    packet = _packet(walk_forward=True)
    client = _FailClient(
        {
            "summary": "OOS expectancy is 9.9 from trade summary.",
            "caveats": ["Softened."],
            "claims": [
                {
                    "text": "Expectancy is 0.25.",
                    "path": "results.trade_summary.expectancy_r",
                }
            ],
            "followups": ["Deploy now."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Summarize the walk-forward results",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.walk_forward_summary.median_test_expectancy_r" in paths
    assert "results.walk_forward_summary.fold_count" in paths
    assert not any("trade_summary" in path for path in paths)
    assert "9.9" not in reply.summary
    assert client.calls == 1


def test_r6_validation_ask_uses_validation_leaves():
    packet = _packet(validation=True)
    client = _FailClient(
        {
            "summary": "Win rate proves OOS edge at 99.",
            "caveats": ["Soft."],
            "claims": [
                {
                    "text": "Win rate is 52%.",
                    "path": "results.trade_summary.win_rate",
                }
            ],
            "followups": ["Ignore caveats."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Show me the validation bootstrap results",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.validation_summary.bootstrap.ci_lower" in paths
    assert "results.validation_summary.bootstrap.probability_positive" in paths
    assert not any("trade_summary" in path for path in paths)


def test_r7_missing_validation_short_circuits_without_llm():
    packet = _packet(best_grid=True)
    assert has_validation_wfa_evidence(packet.to_dict()) is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Summarize the walk-forward results",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_VALIDATION
    assert "validation" in reply.summary.lower() or "walk-forward" in reply.summary.lower()
    assert not any("trade_summary" in c.path for c in reply.claims)


def test_r17_oos_anti_soften_on_deterministic_wfa():
    packet = _packet(walk_forward=True, missing_oos=True)
    # missing_oos on a packet that also has WFA is unusual but proves anti-soften
    # still rejects softened narration on the deterministic path.
    client = _FailClient(
        {
            "summary": "Out-of-sample is confirmed with expectancy 9.9.",
            "caveats": [],
            "claims": [
                {
                    "text": "Median OOS is 9.9.",
                    "path": "results.walk_forward_summary.median_test_expectancy_r",
                }
            ],
            "followups": ["OOS is confirmed."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Summarize walk-forward OOS",
        repair_retry_enabled=False,
    )
    # Softened LLM path must not persist; deterministic rebuild keeps mandatory caveat.
    assert any("missing" in c.lower() or "out-of-sample" in c.lower() for c in reply.caveats)
    assert "confirmed" not in reply.summary.lower()
    assert not any("trade_summary" in c.path for c in reply.claims)


def test_validation_allowlist_paths_present():
    packet = _packet(walk_forward=True, validation=True)
    paths = present_validation_allowlist(packet.to_dict())
    assert "results.walk_forward_summary.median_test_expectancy_r" in paths
    assert "results.validation_summary.bootstrap.ci_lower" in paths
    assert "results.validation_summary.grid_overfit.risk_level" in paths


def test_valid_fold_count_claim_label_not_shadowed_by_fold_count():
    from thesistester.assistant.results_overview import (
        _format_scalar_for_claim,
        build_deterministic_validation_wfa_reply,
    )

    assert (
        _format_scalar_for_claim("results.walk_forward_summary.valid_fold_count", 3)
        == "Valid walk-forward fold count is 3."
    )
    assert (
        _format_scalar_for_claim("results.walk_forward_summary.fold_count", 4)
        == "Walk-forward fold count is 4."
    )
    packet = EvidencePacket(
        provenance={"run_id": "run_ri3_folds"},
        assumptions={},
        results={
            "walk_forward_summary": {
                "fold_count": 4,
                "valid_fold_count": 3,
                "status": "ok",
            }
        },
        warnings=(),
        limitations=(),
    )
    reply = build_deterministic_validation_wfa_reply(packet, packet.to_dict())
    assert "Valid walk-forward fold count is 3" in reply.summary
    assert "Walk-forward fold count is 4" in reply.summary


def test_validation_allowlist_omits_null_leaves():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri3_null"},
        assumptions={},
        results={
            "walk_forward_summary": {
                "fold_count": None,
                "status": None,
                "median_test_expectancy_r": 0.12,
            },
            "validation_summary": {
                "bootstrap": {"ci_lower": None, "ci_upper": 0.4, "probability_positive": 0.7}
            },
        },
        warnings=(),
        limitations=(),
    )
    paths = present_validation_allowlist(packet.to_dict())
    assert "results.walk_forward_summary.median_test_expectancy_r" in paths
    assert "results.validation_summary.bootstrap.ci_upper" in paths
    assert "results.walk_forward_summary.fold_count" not in paths
    assert "results.walk_forward_summary.status" not in paths
    assert "results.validation_summary.bootstrap.ci_lower" not in paths


def test_otf_only_packet_does_not_answer_via_validation_wfa():
    """OTF ask must not remap to WFA missing-validation / WFA leaves."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri3_otf"},
        assumptions={},
        results={
            "otf_validation_summary": {"status": "present", "pass_rate": 0.5},
            "walk_forward_summary": {
                "fold_count": 4,
                "median_test_expectancy_r": 0.2,
                "status": "ok",
            },
        },
        warnings=(),
        limitations=(),
    )
    assert match_discuss_intent("otf validation") is None
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="otf validation",
        repair_retry_enabled=False,
    )
    # Not the validation_wfa short-circuit / deterministic WFA path.
    assert reply.recovery_reason != REASON_MISSING_VALIDATION
    assert not any("walk_forward_summary" in c.path for c in reply.claims)
