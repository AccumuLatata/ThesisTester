"""RI Research Intelligence: specialist Discuss slices (grid→deep_trade)."""

from __future__ import annotations

import json

import pytest

from thesistester.assistant.explainer import EvidenceCaveat, EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import load_results_qa_settings
from thesistester.assistant.llm_explainer import LLMEvidenceError, _ungrounded_number_tokens
from thesistester.assistant.results_overview import (
    ASSUMPTIONS_CLAIM_PATHS,
    DEEP_TRADE_CLAIM_PATHS,
    INTENT_ASSUMPTIONS_COSTS,
    INTENT_DEEP_TRADE,
    INTENT_GRID_RANKING,
    INTENT_MIXED_ASK,
    INTENT_ROBUSTNESS_TIER2,
    INTENT_SINGLE_METRIC,
    INTENT_TIME_RANKING,
    INTENT_VALIDATION_WFA,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    REASON_MISSING_ASSUMPTIONS,
    REASON_MISSING_DEEP_TRADE,
    REASON_MISSING_GRID,
    REASON_MISSING_METRIC,
    REASON_MISSING_ROBUSTNESS,
    REASON_MISSING_TIME,
    REASON_MISSING_VALIDATION,
    REASON_MIXED_ASK,
    REASON_PATH_MISS,
    ROBUSTNESS_CLAIM_PATHS,
    _SINGLE_METRIC_NOUN_PATHS,
    build_deterministic_assumptions_reply,
    build_deterministic_deep_trade_reply,
    build_deterministic_grid_ranking_reply,
    build_deterministic_robustness_reply,
    build_deterministic_single_metric_reply,
    build_deterministic_time_ranking_reply,
    build_deterministic_validation_wfa_reply,
    build_expert_overlay,
    build_meaning_overlay,
    build_mixed_ask_remediation_reply,
    has_assumptions_costs_evidence,
    has_deep_trade_evidence,
    has_grid_ranking_evidence,
    has_overview_negative_cue,
    has_robustness_tier2_evidence,
    has_single_metric_evidence,
    has_time_ranking_evidence,
    has_validation_wfa_evidence,
    match_discuss_intent,
    match_overview_intent,
    present_assumptions_allowlist,
    present_deep_trade_allowlist,
    present_grid_allowlist,
    present_robustness_allowlist,
    present_time_allowlist,
    present_validation_allowlist,
    resolve_single_metric_path,
)
from thesistester.assistant.results_projections import (
    EXIT_REASON_TOP_N,
    build_ephemeral_results_context,
)
from thesistester.assistant.results_qa import propose_results_reply


def _packet(
    *,
    best_grid: bool = True,
    projections: bool = False,
    walk_forward: bool = False,
    validation: bool = False,
    time_summary: bool = False,
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
    if time_summary:
        results["time_grouped_summary"] = [
            {
                "entry_30min_bucket": "09:30",
                "trade_count": 24,
                "avg_r": 0.45,
                "sample_warning": False,
            },
            {
                "entry_30min_bucket": "14:00",
                "trade_count": 18,
                "avg_r": 0.20,
                "sample_warning": False,
            },
        ]
    caveats = ()
    if missing_oos:
        caveats = (
            EvidenceCaveat(
                code="missing_oos",
                message="Out-of-sample / walk-forward evidence is missing.",
            ),
        )
    limitations = ()
    if not time_summary:
        limitations = ("Time analysis is not present in this evidence packet.",)
    return EvidencePacket(
        provenance={"run_id": "run_ri"},
        assumptions={
            "instrument": "NQ",
            "grid": {"ranking_metric": "expectancy_r"},
            "costs_exposure": {"commission_per_side": 0.0, "slippage_ticks": 1},
        },
        results=results,
        warnings=(),
        limitations=limitations,
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
    # RI-2: time is a landed specialist; multi-specialist asks are mixed_ask.
    assert match_discuss_intent("What is the best time?") == INTENT_TIME_RANKING
    assert match_discuss_intent("best entry please") == INTENT_TIME_RANKING
    assert match_discuss_intent("hour bucket ranking") == INTENT_TIME_RANKING
    assert match_discuss_intent("session segment please") == INTENT_TIME_RANKING
    assert match_discuss_intent("best SL and best time") == INTENT_MIXED_ASK
    assert match_discuss_intent("walk-forward by hour bucket") == INTENT_MIXED_ASK
    assert match_discuss_intent("KPIs and best entry time") == INTENT_MIXED_ASK
    # Soft bare-grid residual must not veto lone validation_wfa or time_ranking.
    assert match_discuss_intent("tp and oos") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("oos for my tp") == INTENT_VALIDATION_WFA
    assert match_discuss_intent("validation of my stop") == INTENT_VALIDATION_WFA
    # Bare tp (no grid collocate) must not veto lone time_ranking.
    assert match_discuss_intent("tp and hour bucket") == INTENT_TIME_RANKING
    # "best" collocates bare tp → grid + time → mixed_ask.
    assert match_discuss_intent("tp and best time") == INTENT_MIXED_ASK
    # Soft residual still refuses overview topic-swap (not kpi_summary).
    assert match_discuss_intent("Give me KPIs and what's my stop?") is None
    assert has_overview_negative_cue("Give me KPIs and what's my stop?") is True
    assert match_overview_intent("Give me KPIs and what's my stop?") is None
    # RI-5: otf validation / Monte Carlo are landed robustness_tier2 (not RI-3).
    assert match_discuss_intent("otf validation") == INTENT_ROBUSTNESS_TIER2
    assert has_overview_negative_cue("otf validation") is True
    assert match_discuss_intent("otf-validation") == INTENT_ROBUSTNESS_TIER2
    assert has_overview_negative_cue("otf-validation") is True
    assert match_discuss_intent("monte carlo summary please") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("overfitting diagnostics") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("overfit diagnostics") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("sensitivity battery") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("noise test results") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("portfolio summary please") == INTENT_ROBUSTNESS_TIER2
    # Other WFA cues still land even when OTF is mentioned in passing (no otf cue).
    assert match_discuss_intent("walk-forward validation and otf notes") == INTENT_VALIDATION_WFA
    # WFA + otf validation phrase → mixed_ask (both specialists).
    assert match_discuss_intent("walk-forward and otf validation") == INTENT_MIXED_ASK
    # Bare ``validation`` must survive beside OTF (not collapse to robustness-only).
    assert match_discuss_intent("validation and otf validation") == INTENT_MIXED_ASK
    assert match_discuss_intent("validation and otf-validation") == INTENT_MIXED_ASK
    # Near-miss bare monte/carlo must not launder into single_metric.
    assert match_discuss_intent("what is the monte expectancy?") is None
    assert has_overview_negative_cue("what is the monte expectancy?") is True
    assert match_discuss_intent("carlo summary") is None
    assert has_overview_negative_cue("carlo summary") is True
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
    assert match_overview_intent("What is the best time?") is None
    assert match_overview_intent("summarize this run") == OVERVIEW_INTENT_RUN
    # RI-4: single_metric lands with value collocates; bare nouns do not.
    assert match_discuss_intent("What is the win rate?") == INTENT_SINGLE_METRIC
    assert match_discuss_intent("win rate") is None
    assert match_overview_intent("What is the win rate?") is None
    assert has_overview_negative_cue("What is the win rate?") is True
    # RI-6: assumptions/costs specialist.
    assert match_discuss_intent("What costs were assumed?") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("commission and slippage please") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("exposure policy on this run") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("intrabar model used") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("what assumptions were used?") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("what cost was assumed?") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("what assumption was used?") == INTENT_ASSUMPTIONS_COSTS
    # Configured SL/TP language is assumptions, not best-grid ranks.
    assert match_discuss_intent("what stop loss was configured?") == INTENT_ASSUMPTIONS_COSTS
    assert match_discuss_intent("what take profit was assumed?") == INTENT_ASSUMPTIONS_COSTS
    # Help-shaped how-to / docs asks stay unmatched (not run-assumption answers).
    assert match_discuss_intent("how do I set commission?") is None
    assert match_discuss_intent("how to configure slippage") is None
    assert match_discuss_intent("explain assumptions in the docs") is None
    # Value-metric + costs with ``and`` composes; sole metric×grid still grid-only.
    assert match_discuss_intent("what is the win rate and costs") == INTENT_MIXED_ASK
    assert match_discuss_intent("ranking and costs") == INTENT_ASSUMPTIONS_COSTS
    assert has_overview_negative_cue("What costs were assumed?") is True
    assert match_overview_intent("What costs were assumed?") is None
    assert match_discuss_intent("KPIs and costs") == INTENT_MIXED_ASK
    # RI-9: deep-trade specialist (capped projections only).
    assert match_discuss_intent("What were the exit reasons?") == INTENT_DEEP_TRADE
    assert match_discuss_intent("exit reason histogram please") == INTENT_DEEP_TRADE
    assert match_discuss_intent("how many trades exited?") == INTENT_DEEP_TRADE
    assert match_discuss_intent("how many trades?") == INTENT_SINGLE_METRIC
    assert match_discuss_intent("best trades") == INTENT_DEEP_TRADE
    assert match_discuss_intent("worst trades") == INTENT_DEEP_TRADE
    assert match_discuss_intent("winning streak") == INTENT_DEEP_TRADE
    assert match_discuss_intent("losing streak") == INTENT_DEEP_TRADE
    assert match_discuss_intent("what is the win rate and exit reasons") == INTENT_MIXED_ASK
    assert match_discuss_intent("what is the win rate and exit reasons ranking") == (
        INTENT_MIXED_ASK
    )
    assert match_discuss_intent("why did trades exit") == INTENT_DEEP_TRADE
    assert match_discuss_intent("how did trades exit") == INTENT_DEEP_TRADE
    assert match_discuss_intent("what was the worst trade") == INTENT_DEEP_TRADE
    assert match_discuss_intent("show the best trade") == INTENT_DEEP_TRADE
    assert match_discuss_intent("extreme trades on this run") == INTENT_DEEP_TRADE
    assert match_discuss_intent("what was the win streak") == INTENT_DEEP_TRADE
    assert match_discuss_intent("loss streak please") == INTENT_DEEP_TRADE
    assert match_discuss_intent("consecutive wins") == INTENT_DEEP_TRADE
    assert match_discuss_intent("consecutive losses") == INTENT_DEEP_TRADE
    assert has_overview_negative_cue("What were the exit reasons?") is True
    assert match_overview_intent("What were the exit reasons?") is None
    assert match_discuss_intent("KPIs and exit reasons") == INTENT_MIXED_ASK


def test_residual_veto_and_false_friends_for_overview_negative_export():
    assert has_overview_negative_cue("What is the best SL/TP?") is True
    assert has_overview_negative_cue("summarize the walk-forward results") is True
    assert has_overview_negative_cue("validation diagnostics please") is True
    assert has_overview_negative_cue("What is the best time?") is True
    assert has_overview_negative_cue("KPIs and best SL/TP") is True
    # Bare ranking (no grid/time collocate) stays residual — do not poison with "grid".
    assert match_discuss_intent("ranking alone") is None
    assert has_overview_negative_cue("ranking alone") is True
    assert match_discuss_intent("what is the ranking") is None
    assert has_overview_negative_cue("what is the ranking") is True
    # Time-sense ranking collocates land time_ranking (no longer residual).
    assert match_discuss_intent("time ranking") == INTENT_TIME_RANKING
    # Bare stop/target still refuse overview (DX), but are not grid_ranking.
    assert has_overview_negative_cue("What's my stop?") is True
    assert has_overview_negative_cue("full stop") is True
    # mixed_ask (incl. dual overview) refuses overview envelopes for DX.
    assert has_overview_negative_cue("Give me the KPIs and summarize this run") is True
    # oos false friends must not fire validation ownership.
    assert match_discuss_intent("boost the sample") is None
    assert match_discuss_intent("loose ends only") is None
    # R18: time/grid false friends must not fire specialist ownership.
    assert match_discuss_intent("runtime of this batch") is None
    assert match_discuss_intent("stopwatch only") is None
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


def test_r4_uncited_llm_digits_fall_back_to_deterministic_time():
    packet = _packet(best_grid=True, time_summary=True)
    context = build_ephemeral_results_context(packet)
    assert has_time_ranking_evidence(context) is True
    client = _FailClient(
        {
            "summary": "Best entry is 99:99 with secret clock 77.",
            "caveats": ["Invented clocks."],
            "claims": [
                {
                    "text": "Best bucket is 99:99.",
                    "path": "results.trade_summary.trade_count",
                }
            ],
            "followups": ["Deploy this now."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best time?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.time_rankings.best.bucket" in paths
    assert any(claim.value == "09:30" for claim in reply.claims)
    assert "99:99" not in reply.summary
    assert "77" not in reply.summary
    assert client.calls == 1


def test_r5_missing_time_short_circuits_without_llm():
    packet = _packet(best_grid=True, time_summary=False)
    assert has_time_ranking_evidence(packet.to_dict()) is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best entry time?",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_TIME
    assert "time" in reply.summary.lower()
    assert "99" not in reply.summary


def test_time_allowlist_and_deterministic_builder_from_summary():
    packet = _packet(time_summary=True)
    # No ephemeral projections yet — builder/evidence must project from summary.
    assert "projections" not in packet.to_dict()["results"]
    assert has_time_ranking_evidence(packet.to_dict()) is True
    paths = present_time_allowlist(packet.to_dict())
    assert "results.projections.time_rankings.best.bucket" in paths
    reply = build_deterministic_time_ranking_reply(packet, packet.to_dict())
    claim_paths = {claim.path for claim in reply.claims}
    assert "results.projections.time_rankings.best.bucket" in claim_paths
    assert "results.projections.time_rankings.selection_scope" in claim_paths
    assert any(claim.value == "09:30" for claim in reply.claims)
    assert "99" not in reply.summary


def test_time_summary_only_syncs_evidence_packet_with_catalog_paths():
    """Catalog preferred paths must exist on evidence_packet for path audit."""
    packet = _packet(time_summary=True)
    assert "projections" not in packet.to_dict()["results"]

    class _CatalogClient:
        def __init__(self):
            self.calls = 0
            self.last_user: dict | None = None

        def complete_structured(self, **kwargs):
            self.calls += 1
            self.last_user = json.loads(kwargs["user"])
            return {
                "summary": "Best entry bucket is 09:30 under avg_r.",
                "caveats": ["In-sample time buckets only."],
                "claims": [
                    {
                        "text": "Best bucket is 09:30.",
                        "path": "results.projections.time_rankings.best.bucket",
                    },
                    {
                        "text": "Trade count is 24.",
                        "path": "results.projections.time_rankings.best.trade_count",
                    },
                ],
                "followups": ["Ask about KPIs next."],
            }

    client = _CatalogClient()
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best time?",
        repair_retry_enabled=False,
        deterministic_specialist_fallback=False,
    )
    assert client.calls == 1
    assert client.last_user is not None
    evidence = client.last_user["evidence_packet"]
    catalog = client.last_user["path_catalog"]
    bucket_path = "results.projections.time_rankings.best.bucket"
    assert evidence["results"]["projections"]["time_rankings"]["best"]["bucket"] == "09:30"
    assert bucket_path in catalog["existing_paths"]
    assert bucket_path in catalog["preferred_claim_paths"]
    assert reply.claims[0].value == "09:30"
    assert "09:30" in reply.summary


def test_incomplete_time_projection_reprojects_from_summary():
    packet = _packet(time_summary=True)
    context = packet.to_dict()
    context["results"] = dict(context["results"])
    context["results"]["projections"] = {
        "time_rankings": {
            "bucket_col": "entry_30min_bucket",
            "metric": "avg_r",
            "min_trades": 10,
            "selection_scope": "in_sample_time_buckets",
            "best": {"bucket": None, "trade_count": None, "metric_value": None},
        }
    }
    assert has_time_ranking_evidence(context) is True
    reply = build_deterministic_time_ranking_reply(packet, context)
    assert any(claim.value == "09:30" for claim in reply.claims)
    assert "results.projections.time_rankings.best.bucket" in {c.path for c in reply.claims}


def test_numeric_hour_bucket_claim_label_and_grounding():
    from thesistester.assistant.results_overview import _format_scalar_for_claim

    assert (
        _format_scalar_for_claim("results.projections.time_rankings.best.bucket", 9)
        == "Best time bucket is 09:00."
    )
    packet = EvidencePacket(
        provenance={"run_id": "run_ri2_hour"},
        assumptions={},
        results={
            "projections": {
                "time_rankings": {
                    "bucket_col": "entry_hour_bucket",
                    "metric": "avg_r",
                    "min_trades": 10,
                    "selection_scope": "in_sample_time_buckets",
                    "best": {
                        "bucket": 9,
                        "trade_count": 20,
                        "metric_value": 0.4,
                        "sample_warning": False,
                    },
                }
            }
        },
        warnings=(),
        limitations=(),
    )
    reply = build_deterministic_time_ranking_reply(packet, packet.to_dict())
    assert "Best time bucket is 09:00" in reply.summary
    assert any(claim.value == "09:00" for claim in reply.claims)


def test_r13_mixed_ask_over_cap_narrow_remediation_without_llm():
    """R13 (post RI-8): >3 matched intents still narrow-remediate."""
    from thesistester.assistant.results_overview import (
        MIXED_COMPOSE_CAP,
        list_matched_discuss_intents,
    )

    packet = _packet(best_grid=True, walk_forward=True, time_summary=True)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(_uncited_digits_payload())
    message = "KPIs and best SL and best time and walk-forward"
    assert match_discuss_intent(message) == INTENT_MIXED_ASK
    assert len(list_matched_discuss_intents(message)) > MIXED_COMPOSE_CAP
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message=message,
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MIXED_ASK
    assert "mix" in reply.summary.lower() or "one topic" in reply.summary.lower()


def test_r14_mixed_kpis_and_best_sl_composes_both_allowlists():
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

    packet = _packet(best_grid=True)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="KPIs and best SL/TP",
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MIXED_COMPOSE
    paths = {claim.path for claim in reply.claims}
    assert any(path.startswith("results.trade_summary.") for path in paths)
    assert (
        "results.projections.grid_rankings.best.stop_loss_ticks" in paths
        or "results.best_grid_result.stop_loss_ticks" in paths
    )
    assert (
        "results.projections.grid_rankings.best.take_profit_ticks" in paths
        or "results.best_grid_result.take_profit_ticks" in paths
    )
    # Compose must not stack per-slice "ask for KPIs" / WFA-presence next-steps
    # after both topics were answered.
    assert not any("ask for the key metrics" in c.lower() for c in reply.caveats)
    assert len(paths) == len(reply.claims), "compose must dedupe claim paths"


def test_ri8_missing_grid_slice_does_not_kpi_only_compose():
    """Partial topic-swap: KPIs + best SL without grid evidence → remediation."""
    packet = _packet(best_grid=False)
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


def test_ri8_metric_plus_kpi_dedupes_overlapping_paths():
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

    packet = _packet()
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="what is the win rate and key metrics",
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MIXED_COMPOSE
    win_rate_claims = [c for c in reply.claims if c.path == "results.trade_summary.win_rate"]
    assert len(win_rate_claims) == 1
    assert reply.summary.lower().count("win rate") == 1


def test_ri8_raw_cap_before_dual_overview_collapse():
    """Four raw intents must remediate even if dual overview would collapse."""
    from thesistester.assistant.results_overview import list_matched_discuss_intents

    packet = _packet(best_grid=True, time_summary=True)
    context = build_ephemeral_results_context(packet)
    message = "KPIs and summarize this run and best SL and best time"
    matched = list_matched_discuss_intents(message)
    assert len(matched) > 3
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message=message,
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MIXED_ASK


def test_ri8_multi_metric_over_leaf_cap_remediates():
    packet = _packet()
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="what is the win rate and expectancy and profit factor and drawdown",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MIXED_ASK


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


def test_r23_kpi_plus_validation_composes_not_kpi_only():
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

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
    assert reply.recovery_reason == REASON_MIXED_COMPOSE
    paths = {claim.path for claim in reply.claims}
    assert any(path.startswith("results.trade_summary.") for path in paths)
    assert any("walk_forward_summary" in path for path in paths)
    # Still not a KPI-only overview envelope.
    assert match_overview_intent("Give me KPIs and validation stats") is None


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
    """OTF ask must not remap to WFA missing-validation / WFA leaves (RI-5 owns OTF)."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_otf"},
        assumptions={},
        results={
            "otf_validation": {"available": True},
            "otf_validation_summary": {
                "status": "present",
                "selected_oos_expectancy_r": 0.11,
                "train_fraction": 0.7,
                "oos_fraction": 0.3,
            },
            "walk_forward_summary": {
                "fold_count": 4,
                "median_test_expectancy_r": 0.2,
                "status": "ok",
            },
        },
        warnings=(),
        limitations=(),
    )
    assert match_discuss_intent("otf validation") == INTENT_ROBUSTNESS_TIER2
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="otf validation",
        repair_retry_enabled=False,
    )
    assert reply.recovery_reason != REASON_MISSING_VALIDATION
    paths = {claim.path for claim in reply.claims}
    assert not any("walk_forward_summary" in path for path in paths)
    assert "results.otf_validation.available" in paths or (
        "results.otf_validation_summary.selected_oos_expectancy_r" in paths
    )


def test_r10_monte_carlo_ask_grounds_frozen_scalars():
    """R10: Monte Carlo ask with summary present → §4.6 grounded status/scalars."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_mc"},
        assumptions={},
        results={
            "trade_summary": {"trade_count": 42, "expectancy_r": 0.25, "win_rate": 0.52},
            "monte_carlo_summary": {"available": True, "trade_count": 40},
        },
        warnings=(),
        limitations=(),
    )
    assert match_discuss_intent("Summarize the Monte Carlo results") == INTENT_ROBUSTNESS_TIER2
    assert has_robustness_tier2_evidence(packet.to_dict()) is True
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Summarize the Monte Carlo results",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.monte_carlo_summary.available" in paths
    assert "results.monte_carlo_summary.trade_count" in paths
    assert not any("trade_summary" in path for path in paths)
    assert "99" not in reply.summary
    # Undeclared nested dumps must not appear.
    assert not any("methods" in path for path in paths)


def test_r10_missing_all_robustness_batteries_limits_without_llm():
    packet = _packet(best_grid=True)
    assert has_robustness_tier2_evidence(packet.to_dict()) is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What does the Monte Carlo battery say?",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_ROBUSTNESS
    assert "99" not in reply.summary


def test_robustness_allowlist_omits_null_and_undeclared_paths():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_null"},
        assumptions={},
        results={
            "monte_carlo_summary": {
                "available": True,
                "trade_count": None,
                "methods": {"reshuffle": {"observed": {"final_r": 1.2}}},
            },
            "overfitting_summary": {"available": False, "pbo": {"pbo": 0.4}},
        },
        warnings=(),
        limitations=(),
    )
    paths = present_robustness_allowlist(packet.to_dict())
    assert "results.monte_carlo_summary.available" in paths
    assert "results.overfitting_summary.available" in paths
    assert "results.overfitting_summary.pbo.pbo" in paths
    assert "results.monte_carlo_summary.trade_count" not in paths
    assert not any(path not in ROBUSTNESS_CLAIM_PATHS for path in paths)
    assert not any("methods" in path for path in paths)
    reply = build_deterministic_robustness_reply(packet, packet.to_dict())
    claim_paths = {claim.path for claim in reply.claims}
    assert "results.monte_carlo_summary.available" in claim_paths
    assert not any("methods" in path for path in claim_paths)


def test_r11_costs_assumed_grounds_assumptions_allowlist_only():
    """R11: “What costs were assumed?” → §4.6 assumption claims; no expectancy."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_costs"},
        assumptions={
            "instrument": "NQ",
            "costs_exposure": {
                "commission_per_side": 1.25,
                "slippage_ticks": 0.5,
                "exposure_policy": "one_trade",
                "intrabar_model": "sl_first",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
            },
            "entry_window": {"focus": {"enabled": True}},
            "dataset": {"dataset_fingerprint": "fp-abc"},
        },
        results={
            "trade_summary": {
                "trade_count": 42,
                "expectancy_r": 0.25,
                "win_rate": 0.52,
            }
        },
        warnings=(),
        limitations=(),
    )
    assert match_discuss_intent("What costs were assumed?") == INTENT_ASSUMPTIONS_COSTS
    assert has_assumptions_costs_evidence(packet.to_dict()) is True
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What costs were assumed?",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "assumptions.costs_exposure.commission_per_side" in paths
    assert "assumptions.costs_exposure.slippage_ticks" in paths
    assert "assumptions.instrument" in paths
    assert not any("trade_summary" in path for path in paths)
    assert "expectancy" not in reply.summary.lower()
    assert "99" not in reply.summary
    # Configured SL/TP must not narrate as "Best" grid ranks.
    assert "Best stop-loss" not in reply.summary
    assert "Configured stop-loss ticks is 8" in reply.summary


def test_r11_missing_assumptions_limits_without_llm():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_empty"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10, "expectancy_r": 0.1}},
        warnings=(),
        limitations=(),
    )
    assert has_assumptions_costs_evidence(packet.to_dict()) is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What costs were assumed?",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_ASSUMPTIONS
    assert "99" not in reply.summary


def test_assumptions_allowlist_rejects_kpi_and_undeclared_paths():
    packet = _packet()
    paths = present_assumptions_allowlist(packet.to_dict())
    assert "assumptions.costs_exposure.commission_per_side" in paths
    assert "assumptions.instrument" in paths
    assert not any(path not in ASSUMPTIONS_CLAIM_PATHS for path in paths)
    assert not any("trade_summary" in path for path in paths)
    reply = build_deterministic_assumptions_reply(packet, packet.to_dict())
    claim_paths = {claim.path for claim in reply.claims}
    assert "assumptions.costs_exposure.slippage_ticks" in claim_paths
    assert not any("trade_summary" in path for path in claim_paths)


def test_r8_win_rate_single_metric_with_percent_narration():
    packet = _packet()
    client = _FailClient(
        {
            "summary": "Win rate is 99 percent secretly.",
            "caveats": ["Invented."],
            "claims": [
                {
                    "text": "Win rate is 99%.",
                    "path": "results.trade_summary.trade_count",
                }
            ],
            "followups": ["Deploy."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the win rate?",
        repair_retry_enabled=False,
    )
    assert len(reply.claims) == 1
    assert reply.claims[0].path == "results.trade_summary.win_rate"
    assert reply.claims[0].value == 0.52
    assert "%" in reply.summary
    assert "99" not in reply.summary
    assert client.calls == 1


def test_r9_missing_metric_leaf_short_circuits_without_llm():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri4_null"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10, "win_rate": None}},
        warnings=(),
        limitations=(),
    )
    assert has_single_metric_evidence(packet.to_dict(), "results.trade_summary.win_rate") is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the win rate?",
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_METRIC
    assert "99" not in reply.summary


def test_r24_oos_expectancy_does_not_cite_in_sample_leaf():
    packet = _packet(walk_forward=True)
    assert match_discuss_intent("what is the OOS expectancy?") == INTENT_VALIDATION_WFA
    # Uncited digits force recovery; deterministic WFA must not launder IS expectancy.
    client = _FailClient(
        {
            "summary": "OOS expectancy is 9.9 from trade summary.",
            "caveats": ["Soft."],
            "claims": [
                {
                    "text": "Expectancy is 0.25.",
                    "path": "results.trade_summary.expectancy_r",
                }
            ],
            "followups": ["Deploy."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="what is the OOS expectancy?",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.trade_summary.expectancy_r" not in paths
    assert any("walk_forward_summary" in path for path in paths)
    assert "9.9" not in reply.summary
    # Lone single_metric path is never chosen for this ask.
    assert resolve_single_metric_path("what is the OOS expectancy?") == (
        "results.trade_summary.expectancy_r"
    )
    assert match_discuss_intent("what is the OOS expectancy?") != INTENT_SINGLE_METRIC


def test_single_metric_hard_refuse_grid_time_validation_and_residual():
    # Specialist/residual collocates hard-refuse single_metric (§4.5 / R24).
    assert match_discuss_intent("what is the win rate on the grid?") == INTENT_GRID_RANKING
    assert match_discuss_intent("what is expectancy by hour bucket?") == INTENT_TIME_RANKING
    assert match_discuss_intent("what is the OOS expectancy?") == INTENT_VALIDATION_WFA
    # RI-5: Monte Carlo collocates land robustness_tier2 (not IS single_metric).
    assert match_discuss_intent("what is monte carlo expectancy?") == INTENT_ROBUSTNESS_TIER2
    assert match_discuss_intent("what is expectancy for my stop?") is None
    assert has_overview_negative_cue("what is expectancy for my stop?") is True
    assert has_overview_negative_cue("what is monte carlo expectancy?") is True


def test_metric_over_time_idiom_is_single_metric_not_time_slice():
    """``over time`` must not hijack §4.5 metric asks onto time_ranking."""
    assert match_discuss_intent("what is the win rate over time?") == INTENT_SINGLE_METRIC
    assert resolve_single_metric_path("what is the win rate over time?") == (
        "results.trade_summary.win_rate"
    )
    assert match_discuss_intent("how many trades over time") == INTENT_SINGLE_METRIC
    packet = _packet(time_summary=True)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="what is the win rate over time?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.trade_summary.win_rate" in paths
    assert not any("time_rankings" in path for path in paths)
    assert "99" not in reply.summary


def test_bare_time_token_plus_metric_is_mixed_ask():
    # Bare hour/clock with a metric value-ask → mixed_ask (not time slice alone).
    assert match_discuss_intent("show win rate by hour") == INTENT_MIXED_ASK
    assert match_discuss_intent("what is the win rate by bucket") == INTENT_MIXED_ASK
    # Soft bare-grid residual must not promote bare time into lone time_ranking.
    assert match_discuss_intent("show win rate by hour for my stop") == INTENT_MIXED_ASK
    assert match_discuss_intent("how many trades by hour for tp") == INTENT_MIXED_ASK
    # Strong time cues still own the turn alone (§4.5 hard-refuse).
    assert match_discuss_intent("what is expectancy by hour bucket?") == INTENT_TIME_RANKING
    # Lone bare time remains time_ranking (RI-2).
    assert match_discuss_intent("What is the time?") == INTENT_TIME_RANKING


def test_how_many_is_not_a_general_metric_collocate():
    assert match_discuss_intent("how many sharpe") is None
    assert match_discuss_intent("how many expectancy") is None
    assert match_discuss_intent("how many win rate") is None
    assert match_discuss_intent("how many trades") == INTENT_SINGLE_METRIC
    assert resolve_single_metric_path("how many trades") == "results.trade_summary.trade_count"


def test_curly_apostrophe_whats_matches_single_metric():
    assert match_discuss_intent("what\u2019s the win rate?") == INTENT_SINGLE_METRIC
    assert resolve_single_metric_path("what\u2019s the win rate?") == (
        "results.trade_summary.win_rate"
    )


def test_single_metric_noun_table_resolves_each_frozen_path():
    cases = (
        ("What is the win rate?", "results.trade_summary.win_rate"),
        ("What is expectancy?", "results.trade_summary.expectancy_r"),
        ("What's the expectancy_r?", "results.trade_summary.expectancy_r"),
        ("Show me the profit factor", "results.trade_summary.profit_factor"),
        ("Give me the max drawdown", "results.trade_summary.max_drawdown_r"),
        ("What is the drawdown?", "results.trade_summary.max_drawdown_r"),
        ("What is total r?", "results.trade_summary.total_r"),
        ("What is the trade count?", "results.trade_summary.trade_count"),
        ("What is the number of trades?", "results.trade_summary.trade_count"),
        ("What is sample size?", "results.trade_summary.trade_count"),
        ("How many trades?", "results.trade_summary.trade_count"),
        ("What is avg r?", "results.trade_summary.avg_r"),
        ("What is average r?", "results.trade_summary.avg_r"),
        ("What is median r?", "results.trade_summary.median_r"),
        ("What is the sharpe?", "results.trade_summary.sharpe_like_r"),
        ("What is the sortino?", "results.trade_summary.sortino_like_r"),
        ("What is the ulcer?", "results.trade_summary.ulcer_index_r"),
        ("What is the recovery factor?", "results.trade_summary.recovery_factor"),
    )
    covered_paths = {path for _nouns, path in _SINGLE_METRIC_NOUN_PATHS}
    for message, path in cases:
        assert match_discuss_intent(message) == INTENT_SINGLE_METRIC, message
        assert resolve_single_metric_path(message) == path, message
        covered_paths.discard(path)
    assert not covered_paths, f"untested §4.5 paths: {covered_paths}"


def test_unknown_metric_noun_stays_unmatched():
    assert match_discuss_intent("What is the frobenius?") is None
    assert resolve_single_metric_path("What is the frobenius?") is None


def test_deterministic_single_metric_builder_one_claim():
    packet = _packet()
    reply = build_deterministic_single_metric_reply(
        packet,
        packet.to_dict(),
        path="results.trade_summary.expectancy_r",
    )
    assert len(reply.claims) == 1
    assert reply.claims[0].path == "results.trade_summary.expectancy_r"
    assert reply.claims[0].value == 0.25


def test_r12_overlay_lines_on_grid_and_kpi_are_digit_free():
    packet = _packet(best_grid=True)
    context = build_ephemeral_results_context(packet)
    grid_reply = build_deterministic_grid_ranking_reply(packet, context)
    assert any("research diagnostics" in c for c in grid_reply.caveats)
    assert any("in-sample grid ranking" in c for c in grid_reply.caveats)
    for caveat in grid_reply.caveats:
        assert _ungrounded_number_tokens(caveat, allowed=set()) == []

    metric_reply = build_deterministic_single_metric_reply(
        packet,
        packet.to_dict(),
        path="results.trade_summary.win_rate",
    )
    assert any("Win rate is the share" in c for c in metric_reply.caveats)
    assert any("research diagnostics" in c for c in metric_reply.caveats)
    for caveat in metric_reply.caveats:
        assert _ungrounded_number_tokens(caveat, allowed=set()) == []

    # KPI/overview path still digit-free under RI-7 alias.
    claims = (
        EvidenceClaim(
            text="Expectancy R is 0.25.",
            path="results.trade_summary.expectancy_r",
            value=0.25,
        ),
    )
    assert build_meaning_overlay is build_expert_overlay
    overlay = build_meaning_overlay(packet, claims, discuss_intent=OVERVIEW_INTENT_KPI)
    assert any("Expectancy R is mean net R" in line for line in overlay)
    for line in overlay:
        assert _ungrounded_number_tokens(line, allowed=set()) == []


def test_ri7_validation_overlay_skips_wfa_presence_coaching():
    packet = _packet(walk_forward=True)
    reply = build_deterministic_validation_wfa_reply(packet, packet.to_dict())
    assert any(
        "Median OOS test expectancy" in c or "walk-forward" in c.lower() for c in reply.caveats
    )
    assert not any("ask whether walk-forward" in c.lower() for c in reply.caveats)
    for caveat in reply.caveats:
        assert _ungrounded_number_tokens(caveat, allowed=set()) == []


def test_ri7_oos_anti_soften_retained_on_grid_overlay():
    packet = _packet(best_grid=True, missing_oos=True)
    context = build_ephemeral_results_context(packet)
    reply = build_deterministic_grid_ranking_reply(packet, context)
    assert any("missing" in c.lower() or "out-of-sample" in c.lower() for c in reply.caveats)
    assert any("do not invent confirmation" in c.lower() for c in reply.caveats)
    assert not any("ask whether walk-forward" in c.lower() for c in reply.caveats)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)
    for caveat in reply.caveats:
        assert _ungrounded_number_tokens(caveat, allowed=set()) == []


def test_ri7_cited_oos_status_missing_suppresses_wfa_presence_coaching():
    """Typical grid projection cites oos_status=missing without a missing_oos caveat."""
    packet = _packet(best_grid=True, missing_oos=False)
    context = build_ephemeral_results_context(packet)
    assert context["results"]["projections"]["grid_rankings"]["oos_status"] == "missing"
    reply = build_deterministic_grid_ranking_reply(packet, context)
    assert any(c.path.endswith("oos_status") for c in reply.claims)
    assert any("Grid OOS status is an honesty signal" in c for c in reply.caveats)
    assert any("do not invent confirmation" in c.lower() for c in reply.caveats)
    assert not any("ask whether walk-forward" in c.lower() for c in reply.caveats)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)


def test_ri7_bare_packet_grid_hydrates_oos_status_for_overlay():
    """Deterministic grid on bare packet must still suppress WFA-presence asks."""
    packet = _packet(best_grid=True, missing_oos=False)
    bare = packet.to_dict()
    assert "projections" not in bare["results"]
    reply = build_deterministic_grid_ranking_reply(packet, bare)
    assert any(c.path.endswith("oos_status") for c in reply.claims)
    assert any("do not invent confirmation" in c.lower() for c in reply.caveats)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)


def test_ri7_llm_grid_without_oos_claim_still_suppresses_presence_coaching():
    """LLM drafts that omit oos_status still use turn-evidence status for RI-7."""
    packet = _packet(best_grid=True, missing_oos=False)
    context = build_ephemeral_results_context(packet)
    client = _FailClient(
        {
            "summary": "Best stop is 8 and take profit is 16.",
            "caveats": ["In-sample grid only."],
            "claims": [
                {
                    "text": "Best stop-loss ticks is 8.",
                    "path": "results.projections.grid_rankings.best.stop_loss_ticks",
                },
                {
                    "text": "Best take-profit ticks is 16.",
                    "path": "results.projections.grid_rankings.best.take_profit_ticks",
                },
            ],
            "followups": [
                "Ask whether walk-forward or validation diagnostics are present on this packet.",
                "Ask about expectancy next.",
            ],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What is the best SL/TP?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    assert client.calls == 1
    assert not any(c.path.endswith("oos_status") for c in reply.claims)
    assert any("do not invent confirmation" in c.lower() for c in reply.caveats)
    assert not any("ask whether walk-forward" in c.lower() for c in reply.caveats)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)
    assert "Ask about expectancy next." in reply.followups


def test_ri7_mixed_ask_followups_respect_missing_oos():
    packet = _packet(best_grid=True, missing_oos=True)
    reply = build_mixed_ask_remediation_reply(packet)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)
    assert any("evidence paths remain available" in f.lower() for f in reply.followups)


def test_ri7_mixed_ask_followups_respect_turn_oos_status():
    packet = _packet(best_grid=True, missing_oos=False)
    context = build_ephemeral_results_context(packet)
    assert context["results"]["projections"]["grid_rankings"]["oos_status"] == "missing"
    reply = build_mixed_ask_remediation_reply(packet, evidence_context=context)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)
    assert any("evidence paths remain available" in f.lower() for f in reply.followups)
    # Over-cap mixed remediation still hydrates and suppresses WFA presence coaching.
    client = _FailClient(_uncited_digits_payload())
    e2e = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="KPIs, best SL/TP, win rate by hour, and validation status",
        turn_context=context,
    )
    assert client.calls == 0
    assert e2e.recovery_reason == REASON_MIXED_ASK
    assert not any("whether walk-forward" in f.lower() for f in e2e.followups)


def test_ri8_compose_followups_respect_turn_oos_status():
    """RI-8: composed KPI+SL/TP answers also suppress WFA presence coaching without oos_status."""
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

    packet = _packet(best_grid=True, missing_oos=False)
    context = build_ephemeral_results_context(packet)
    assert context["results"]["projections"]["grid_rankings"]["oos_status"] == "missing"
    client = _FailClient(_uncited_digits_payload())
    e2e = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="KPIs and best SL/TP",
        turn_context=context,
    )
    assert client.calls == 0
    assert e2e.recovery_reason == REASON_MIXED_COMPOSE
    assert not any("whether walk-forward" in f.lower() for f in e2e.followups)


def test_ri7_single_metric_llm_multi_claim_falls_back_to_one_leaf():
    packet = _packet()
    client = _FailClient(
        {
            "summary": "Trade count is 42 and win rate is 52%.",
            "caveats": ["In-sample only."],
            "claims": [
                {
                    "text": "Trade count is 42.",
                    "path": "results.trade_summary.trade_count",
                },
                {
                    "text": "Win rate is 52%.",
                    "path": "results.trade_summary.win_rate",
                },
            ],
            "followups": ["Ask for KPIs."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="How many trades?",
        repair_retry_enabled=False,
    )
    assert client.calls == 1
    assert len(reply.claims) == 1
    assert reply.claims[0].path == "results.trade_summary.trade_count"
    assert "52" not in reply.summary


def test_ri7_time_overlay_includes_meaning_line():
    packet = _packet(time_summary=True)
    context = build_ephemeral_results_context(packet)
    reply = build_deterministic_time_ranking_reply(packet, context)
    assert any(
        "in-sample session ranking" in c or "time bucket" in c.lower() for c in reply.caveats
    )
    assert any("research diagnostics" in c for c in reply.caveats)
    for caveat in reply.caveats:
        assert _ungrounded_number_tokens(caveat, allowed=set()) == []


def test_ri5_non_bool_available_is_not_narrated():
    from thesistester.assistant.results_overview import _format_scalar_for_claim

    assert _format_scalar_for_claim("results.monte_carlo_summary.available", 1) is None
    assert _format_scalar_for_claim("results.monte_carlo_summary.available", "true") is None
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_avail"},
        assumptions={},
        results={"monte_carlo_summary": {"available": 1, "trade_count": 12}},
        warnings=(),
        limitations=(),
    )
    # Int available must not count as evidence; trade_count still can.
    paths = present_robustness_allowlist(packet.to_dict())
    assert "results.monte_carlo_summary.available" not in paths
    assert "results.monte_carlo_summary.trade_count" in paths
    reply = build_deterministic_robustness_reply(packet, packet.to_dict())
    assert "available is 1" not in reply.summary.lower()
    assert not any(c.path.endswith(".available") for c in reply.claims)


def test_ri5_missing_robustness_followups_respect_oos_absent():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_miss_oos"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10}},
        warnings=(),
        limitations=("Walk-forward / OOS evidence is missing on this packet.",),
        caveats=(
            EvidenceCaveat(
                code="missing_oos",
                message="Out-of-sample evidence is missing.",
                path="results.walk_forward_summary",
            ),
        ),
    )
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What does the Monte Carlo battery say?",
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MISSING_ROBUSTNESS
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)


def test_ri5_llm_nested_dump_hard_rejects_to_deterministic():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_methods"},
        assumptions={},
        results={
            "monte_carlo_summary": {
                "available": True,
                "trade_count": 40,
                "methods": {"reshuffle": {"observed": {"final_r": 1.2}}},
            }
        },
        warnings=(),
        limitations=(),
    )
    client = _FailClient(
        {
            "summary": "Methods final_r is 1.2 under Monte Carlo.",
            "caveats": ["Soft."],
            "claims": [
                {
                    "text": "Final R is 1.2.",
                    "path": "results.monte_carlo_summary.methods.reshuffle.observed.final_r",
                }
            ],
            "followups": ["Deploy."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Summarize the Monte Carlo results",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.monte_carlo_summary.available" in paths
    assert "results.monte_carlo_summary.trade_count" in paths
    assert not any("methods" in path for path in paths)
    assert "1.2" not in reply.summary


def test_ri5_robustness_catalog_existing_paths_is_allowlist_only():
    from thesistester.assistant.results_overview import build_prompt_path_catalog

    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_catalog"},
        assumptions={},
        results={
            "trade_summary": {"trade_count": 42, "expectancy_r": 0.25},
            "monte_carlo_summary": {
                "available": True,
                "trade_count": 40,
                "methods": {"reshuffle": {"observed": {"final_r": 1.2}}},
            },
        },
        warnings=(),
        limitations=(),
    )
    catalog = build_prompt_path_catalog(packet.to_dict(), discuss_intent=INTENT_ROBUSTNESS_TIER2)
    existing = set(catalog["existing_paths"])
    assert existing
    assert existing <= set(ROBUSTNESS_CLAIM_PATHS)
    assert not any("methods" in path for path in existing)
    assert not any("trade_summary" in path for path in existing)


def test_ri5_robustness_overlay_oos_absent_skips_wfa_coaching():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri5_overlay_oos"},
        assumptions={},
        results={"monte_carlo_summary": {"available": True, "trade_count": 12}},
        warnings=(),
        limitations=("Walk-forward / OOS evidence is missing on this packet.",),
        caveats=(
            EvidenceCaveat(
                code="missing_oos",
                message="Out-of-sample evidence is missing.",
                path="results.walk_forward_summary",
            ),
        ),
    )
    reply = build_deterministic_robustness_reply(packet, packet.to_dict())
    assert not any("walk-forward summary" in c.lower() for c in reply.caveats)
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)
    assert any("in-sample baseline" in c.lower() for c in reply.caveats)


def test_ri8_compose_keeps_non_kpi_metric_with_overview():
    """Overview + sharpe must not drop the non-KPI metric leaf (compose bug)."""
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

    packet = EvidencePacket(
        provenance={"run_id": "run_ri8_sharpe"},
        assumptions={},
        results={
            "trade_summary": {
                "trade_count": 42,
                "expectancy_r": 0.25,
                "win_rate": 0.52,
                "profit_factor": 1.4,
                "max_drawdown_r": -2.0,
                "total_r": 10.5,
                "sharpe_like_r": 1.1,
            }
        },
        warnings=(),
        limitations=(),
    )
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="key metrics and what is the sharpe?",
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MIXED_COMPOSE
    paths = {claim.path for claim in reply.claims}
    assert "results.trade_summary.sharpe_like_r" in paths
    assert any(path.startswith("results.trade_summary.") for path in paths)


def test_ri6_compose_grid_and_commission_does_not_narrow():
    """Shared cost leaves must not make grid×assumptions fall through to narrow."""
    from thesistester.assistant.results_overview import REASON_MIXED_COMPOSE

    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_compose_overlap"},
        assumptions={
            "costs_exposure": {"commission_per_side": 2.5, "slippage_ticks": 1},
            "grid": {"ranking_metric": "expectancy_r"},
        },
        results={
            "trade_summary": {"trade_count": 10, "win_rate": 0.5},
            "best_grid_result": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 10,
                "ranking_metric": "expectancy_r",
            },
        },
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet)
    assert match_discuss_intent("best stop and commission") == INTENT_MIXED_ASK
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="best stop and commission",
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MIXED_COMPOSE
    paths = {claim.path for claim in reply.claims}
    assert (
        "results.projections.grid_rankings.best.stop_loss_ticks" in paths
        or "results.best_grid_result.stop_loss_ticks" in paths
    )
    assert "assumptions.costs_exposure.commission_per_side" in paths
    # Cost leaves narrated once (assumptions owns them in the mix).
    assert reply.summary.lower().count("commission per side") == 1


def test_ri6_missing_assumptions_followups_respect_oos_absent():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_miss_oos"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10}},
        warnings=(),
        limitations=("Walk-forward / OOS evidence is missing on this packet.",),
        caveats=(
            EvidenceCaveat(
                code="missing_oos",
                message="Out-of-sample evidence is missing.",
                path="results.walk_forward_summary",
            ),
        ),
    )
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What costs were assumed?",
    )
    assert client.calls == 0
    assert reply.recovery_reason == REASON_MISSING_ASSUMPTIONS
    assert not any("whether walk-forward" in f.lower() for f in reply.followups)


def test_ri6_configured_sl_grounds_assumption_leaf_not_best_grid():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_configured_sl"},
        assumptions={
            "costs_exposure": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "commission_per_side": 1.0,
            }
        },
        results={
            "best_grid_result": {
                "stop_loss_ticks": 12,
                "take_profit_ticks": 24,
                "trade_count": 10,
                "ranking_metric": "expectancy_r",
            }
        },
        warnings=(),
        limitations=(),
    )
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="what stop loss was configured?",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "assumptions.costs_exposure.stop_loss_ticks" in paths
    assert "results.best_grid_result.stop_loss_ticks" not in paths
    assert "Configured stop-loss ticks is 8" in reply.summary
    assert "Best stop-loss" not in reply.summary


def test_ri6_instrument_dict_and_intrabar_nest_are_narratable():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_instr_intrabar"},
        assumptions={
            "instrument": {"symbol": "NQ", "name": "Nasdaq"},
            "intrabar": {"intrabar_model": "ohlc_pessimistic"},
        },
        results={},
        warnings=(),
        limitations=(),
    )
    assert has_assumptions_costs_evidence(packet.to_dict()) is True
    paths = present_assumptions_allowlist(packet.to_dict())
    assert "assumptions.instrument" in paths
    assert "assumptions.intrabar.intrabar_model" in paths
    reply = build_deterministic_assumptions_reply(packet, packet.to_dict())
    claim_paths = {claim.path for claim in reply.claims}
    assert "assumptions.instrument" in claim_paths
    assert "assumptions.intrabar.intrabar_model" in claim_paths
    assert "Instrument is NQ" in reply.summary
    assert "Intrabar model is ohlc_pessimistic" in reply.summary


def test_ri6_llm_kpi_substitution_hard_rejects_to_deterministic():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri6_kpi_reject"},
        assumptions={
            "instrument": "NQ",
            "costs_exposure": {"commission_per_side": 1.25, "slippage_ticks": 0.5},
        },
        results={"trade_summary": {"trade_count": 42, "expectancy_r": 0.25}},
        warnings=(),
        limitations=(),
    )
    client = _FailClient(
        {
            "summary": "Expectancy is 0.25 under these costs.",
            "caveats": ["Soft."],
            "claims": [
                {
                    "text": "Expectancy R is 0.25.",
                    "path": "results.trade_summary.expectancy_r",
                }
            ],
            "followups": ["Deploy."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What costs were assumed?",
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "assumptions.costs_exposure.commission_per_side" in paths
    assert not any("trade_summary" in path for path in paths)
    assert "0.25" not in reply.summary


def _trade_rows_for_deep_trade() -> list[dict]:
    """Small trade table covering exit histogram, extremes, and streaks.

    Reason labels stay digit-free so auditor grounding cannot launder label
    digits; timestamps may exist on rows but are not claimable (§6).
    """
    rows: list[dict] = []
    # 8 TP, 5 SL, 2 TIME, 1 EOD — TP/SL dominate; extremes from R values.
    for _ in range(8):
        rows.append({"exit_reason": "TP", "r_multiple": 1.0})
    for _ in range(5):
        rows.append({"exit_reason": "SL", "r_multiple": -1.0})
    rows.append({"exit_reason": "TIME", "r_multiple": -0.2})
    rows.append({"exit_reason": "TIME", "r_multiple": 0.1})
    rows.append(
        {
            "exit_reason": "EOD",
            "r_multiple": 3.5,
            "entry_timestamp": "2024-01-02T14:00:00Z",
            "exit_timestamp": "2024-01-02T15:00:00Z",
        }
    )
    # Extra unique reasons to exercise top-N + other (beyond EXIT_REASON_TOP_N).
    # Letter-only labels (AA, AB, …) avoid digit tokens in claim text.
    for index in range(EXIT_REASON_TOP_N):
        label = chr(ord("A") + (index // 26)) + chr(ord("A") + (index % 26))
        rows.append({"exit_reason": label, "r_multiple": 0.05})
    return rows


def test_r21_exit_reason_ask_with_tables_grounds_capped_histogram():
    """R21: exit-reason ask with trade tables → capped §6 projection claims."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_trades"},
        assumptions={"instrument": "NQ"},
        results={"trade_summary": {"trade_count": 20, "expectancy_r": 0.1}},
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet, trade_rows=_trade_rows_for_deep_trade())
    assert match_discuss_intent("What were the exit reasons?") == INTENT_DEEP_TRADE
    assert has_deep_trade_evidence(context) is True
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What were the exit reasons?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.exit_reason_counts.total_trades" in paths
    assert "results.projections.exit_reason_counts.reasons.0.exit_reason" in paths
    assert "results.projections.exit_reason_counts.reasons.0.count" in paths
    assert "results.projections.exit_reason_counts.other_count" in paths
    assert not any("trade_summary" in path for path in paths)
    assert not any(path not in DEEP_TRADE_CLAIM_PATHS for path in paths)
    # Cap: indexed reasons only through EXIT_REASON_TOP_N - 1.
    assert (
        f"results.projections.exit_reason_counts.reasons.{EXIT_REASON_TOP_N}.exit_reason"
        not in paths
    )
    assert "99" not in reply.summary
    assert "results.projections.extreme_trades.best.0.r_multiple" in paths
    # Exit-reason asks are topic-scoped to table projections (not streaks alone).
    assert "results.projections.streak_summary.max_consecutive_wins" not in paths


def test_r21_exit_reason_ask_without_tables_limits_before_llm():
    """R21: exit-reason ask without trade projections → limitation; zero LLM."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_empty"},
        assumptions={"instrument": "NQ"},
        results={"trade_summary": {"trade_count": 10, "expectancy_r": 0.1}},
        warnings=(),
        limitations=(),
    )
    # No trade_rows and no streak leaves → no deep-trade projections.
    context = build_ephemeral_results_context(packet)
    assert has_deep_trade_evidence(context, user_message="What were the exit reasons?") is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What were the exit reasons?",
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_DEEP_TRADE
    assert "99" not in reply.summary


def test_ri9_exit_ask_does_not_use_streak_only_trade_summary():
    """Streak scalars alone must not answer exit-reason asks (§6 tables gate)."""
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_streak_only"},
        assumptions={},
        results={
            "trade_summary": {
                "trade_count": 10,
                "max_consecutive_wins": 3,
                "max_consecutive_losses": 2,
            }
        },
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet)
    assert has_deep_trade_evidence(context, user_message="win streak") is True
    assert has_deep_trade_evidence(context, user_message="exit reasons please") is False
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="exit reasons please",
        turn_context=context,
    )
    assert client.calls == 0
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_MISSING_DEEP_TRADE


def test_ri9_digit_bearing_exit_labels_do_not_crash_builder():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_digit_labels"},
        assumptions={},
        results={"trade_summary": {"trade_count": 3}},
        warnings=(),
        limitations=(),
    )
    rows = [
        {"exit_reason": "SL-12", "r_multiple": 1.0},
        {"exit_reason": "SL-12", "r_multiple": -1.0},
        {"exit_reason": "TP", "r_multiple": 2.0},
    ]
    context = build_ephemeral_results_context(packet, trade_rows=rows)
    client = _FailClient(_uncited_digits_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What were the exit reasons?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.exit_reason_counts.total_trades" in paths
    # Digit-bearing labels are skipped; digit-free TP may still narrate.
    assert not any(
        claim.path.endswith(".exit_reason") and claim.value == "SL-12" for claim in reply.claims
    )
    assert "12" not in reply.summary
    assert "99" not in reply.summary


def test_deep_trade_allowlist_rejects_kpi_and_undeclared_paths():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_allow"},
        assumptions={},
        results={"trade_summary": {"trade_count": 12, "expectancy_r": 0.2}},
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet, trade_rows=_trade_rows_for_deep_trade())
    paths = present_deep_trade_allowlist(context)
    assert "results.projections.exit_reason_counts.reasons.0.exit_reason" in paths
    assert not any(path not in DEEP_TRADE_CLAIM_PATHS for path in paths)
    assert not any("trade_summary" in path for path in paths)
    reply = build_deterministic_deep_trade_reply(packet, context)
    claim_paths = {claim.path for claim in reply.claims}
    assert "results.projections.exit_reason_counts.total_trades" in claim_paths
    assert not any("trade_summary" in path for path in claim_paths)


def test_ri9_deep_trade_rejects_kpi_substitution_via_fallback():
    packet = EvidencePacket(
        provenance={"run_id": "run_ri9_kpi"},
        assumptions={},
        results={"trade_summary": {"trade_count": 12, "expectancy_r": 0.25}},
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet, trade_rows=_trade_rows_for_deep_trade())
    assert has_deep_trade_evidence(context) is True
    client = _FailClient(
        {
            "summary": "Expectancy is 0.25 from exits.",
            "caveats": ["Soft."],
            "claims": [
                {
                    "text": "Expectancy R is 0.25.",
                    "path": "results.trade_summary.expectancy_r",
                }
            ],
            "followups": ["Deploy."],
        }
    )
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="What were the exit reasons?",
        turn_context=context,
        repair_retry_enabled=False,
    )
    paths = {claim.path for claim in reply.claims}
    assert "results.projections.exit_reason_counts.total_trades" in paths
    assert not any("trade_summary" in path for path in paths)
    assert "0.25" not in reply.summary
