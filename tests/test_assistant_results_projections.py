"""RQ-2 deterministic grid/time ranking projection tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from thesistester.assistant import (
    AssistantOrchestrator,
    LocalThesisRepository,
    OrchestrationResult,
)
from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.results_projections import (
    CONFLUENCE_COMBO_TOP_N,
    EXIT_REASON_TOP_N,
    EXTREME_TRADES_N,
    build_ephemeral_results_context,
    project_confluence_combo,
    project_exit_reason_counts,
    project_extreme_trades,
    project_grid_rankings,
    project_streak_summary,
    project_time_rankings,
    resolve_grid_ranking_defaults,
)
from thesistester.assistant.results_qa import propose_results_reply
from thesistester.assistant.tools import AssistantToolError, AssistantTools


def _grid_rows():
    return [
        {
            "stop_loss_ticks": 12,
            "take_profit_ticks": 24,
            "trade_count": 40,
            "expectancy_r": 0.10,
            "total_r": 4.0,
            "profit_factor": 1.2,
            "win_rate": 0.45,
        },
        {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 50,
            "expectancy_r": 0.30,
            "total_r": 15.0,
            "profit_factor": 1.8,
            "win_rate": 0.55,
        },
        {
            "stop_loss_ticks": 6,
            "take_profit_ticks": 12,
            "trade_count": 5,
            "expectancy_r": 0.90,
            "total_r": 4.5,
            "profit_factor": 2.0,
            "win_rate": 0.80,
        },
        {
            "stop_loss_ticks": 10,
            "take_profit_ticks": 20,
            "trade_count": 45,
            "expectancy_r": 0.30,
            "total_r": 13.5,
            "profit_factor": 1.7,
            "win_rate": 0.52,
        },
    ]


def _packet(
    *,
    results: dict | None = None,
    assumptions: dict | None = None,
) -> EvidencePacket:
    base_results = {
        "trade_summary": {"trade_count": 50, "expectancy_r": 0.25},
        "best_grid_result": {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 50,
            "expectancy_r": 0.30,
        },
    }
    base_assumptions = {"grid": {"ranking_metric": "expectancy_r", "min_trades": 10}}
    if results:
        base_results.update(results)
    if assumptions:
        base_assumptions.update(assumptions)
    return EvidencePacket(
        provenance={"run_id": "run_proj"},
        assumptions=base_assumptions,
        results=base_results,
        warnings=(),
    )


def test_resolve_grid_ranking_defaults_prefers_best_row_then_assumptions():
    packet = EvidencePacket(
        provenance={},
        assumptions={"grid": {"ranking_metric": "total_r", "min_trades": 3}},
        results={
            "best_grid_result": {
                "ranking_metric": "profit_factor",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 10,
                "profit_factor": 1.5,
            }
        },
        warnings=(),
    )
    metric, path, min_trades = resolve_grid_ranking_defaults(packet)
    assert metric == "profit_factor"
    assert path == "results.best_grid_result.ranking_metric"
    assert min_trades == 3

    packet2 = _packet()
    metric2, path2, min_trades2 = resolve_grid_ranking_defaults(packet2)
    assert metric2 == "expectancy_r"
    assert path2 == "assumptions.grid.ranking_metric"
    assert min_trades2 == 10


def test_resolve_grid_ranking_defaults_sanitizes_unknown_metrics():
    # Invalid best metric falls through to allowlisted assumptions metric.
    packet = EvidencePacket(
        provenance={},
        assumptions={"grid": {"ranking_metric": "total_r", "min_trades": 2}},
        results={
            "best_grid_result": {
                "ranking_metric": "not_a_real_metric",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 10,
                "total_r": 4.0,
                "expectancy_r": 0.2,
            }
        },
        warnings=(),
    )
    metric, path, min_trades = resolve_grid_ranking_defaults(packet)
    assert metric == "total_r"
    assert path == "assumptions.grid.ranking_metric"
    assert min_trades == 2

    # Both invalid → expectancy_r default.
    packet2 = EvidencePacket(
        provenance={},
        assumptions={"grid": {"ranking_metric": "bogus", "min_trades": 1}},
        results={
            "best_grid_result": {
                "ranking_metric": "also_bogus",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 10,
                "expectancy_r": 0.2,
            }
        },
        warnings=(),
    )
    metric2, path2, _min2 = resolve_grid_ranking_defaults(packet2)
    assert metric2 == "expectancy_r"
    assert path2 == "assumptions.grid.ranking_metric"
    ranked = project_grid_rankings(packet2, metric="also_bogus", min_trades=1)
    assert ranked["metric"] == "expectancy_r"
    assert ranked["best"]["stop_loss_ticks"] == 8
    # Ephemeral context must not leave rejected metric names citable.
    context = build_ephemeral_results_context(packet2)
    assert context["assumptions"]["grid"]["ranking_metric"] == "expectancy_r"
    assert context["results"]["best_grid_result"]["ranking_metric"] == "expectancy_r"
    assert context["results"]["projections"]["grid_rankings"]["metric"] == "expectancy_r"


def test_project_grid_rankings_deterministic_and_respects_min_trades():
    ranked = project_grid_rankings(
        _grid_rows(),
        top_n=3,
        metric="expectancy_r",
        min_trades=10,
    )
    assert ranked["metric"] == "expectancy_r"
    assert ranked["min_trades"] == 10
    assert ranked["candidate_count"] == 4
    assert ranked["eligible_count"] == 3
    assert ranked["best"]["stop_loss_ticks"] == 8
    assert ranked["best"]["take_profit_ticks"] == 16
    assert ranked["best"]["metric_value"] == 0.3
    # Tie on expectancy: lower SL wins (8 before 10).
    assert [row["stop_loss_ticks"] for row in ranked["rows"]] == [8, 10, 12]
    assert ranked["by_rank"]["1"]["rank"] == 1


def test_project_grid_rankings_from_packet_uses_assumption_metric():
    packet = _packet()
    ranked = project_grid_rankings(packet, top_n=5)
    assert ranked["metric"] == "expectancy_r"
    assert ranked["metric_source_path"] == "assumptions.grid.ranking_metric"
    assert ranked["min_trades"] == 10
    assert ranked["best"]["stop_loss_ticks"] == 8
    assert ranked["oos_status"] == "missing"


def test_project_grid_rankings_empty_inputs():
    empty = project_grid_rankings([], top_n=5, metric="expectancy_r")
    assert empty["best"] is None
    assert empty["rows"] == []
    assert empty["candidate_count"] == 0

    packet = EvidencePacket(provenance={}, assumptions={}, results={}, warnings=())
    missing = project_grid_rankings(packet)
    assert missing["best"] is None
    assert missing["metric"] == "expectancy_r"


def test_project_time_rankings_filters_min_trades_and_ranks():
    summary = [
        {
            "entry_rth_segment": "rth_morning",
            "trade_count": 20,
            "avg_r": 0.20,
            "sample_warning": False,
        },
        {
            "entry_rth_segment": "rth_open_30m",
            "trade_count": 4,
            "avg_r": 0.90,
            "sample_warning": True,
        },
        {
            "entry_rth_segment": "rth_afternoon",
            "trade_count": 15,
            "avg_r": 0.10,
            "sample_warning": False,
        },
    ]
    ranked = project_time_rankings(
        summary,
        bucket_col="entry_rth_segment",
        metric="avg_r",
        min_trades=10,
    )
    assert ranked["best"]["bucket"] == "rth_morning"
    assert ranked["best"]["trade_count"] == 20
    assert ranked["eligible_count"] == 2
    assert ranked["candidate_count"] == 3
    assert [row["bucket"] for row in ranked["rows"]] == ["rth_morning", "rth_afternoon"]


def test_project_time_rankings_falls_back_to_clock_bucket_column():
    """Time Analysis hour/30m exports omit entry_rth_segment — still rank labels."""
    summary = [
        {
            "entry_30min_bucket": "08:30",
            "trade_count": 20,
            "avg_r": 0.40,
            "sample_warning": False,
        },
        {
            "entry_30min_bucket": "09:30",
            "trade_count": 12,
            "avg_r": 0.10,
            "sample_warning": False,
        },
    ]
    ranked = project_time_rankings(summary, min_trades=10)
    assert ranked["bucket_col"] == "entry_30min_bucket"
    assert ranked["best"]["bucket"] == "08:30"
    assert ranked["best"]["trade_count"] == 20
    assert [row["bucket"] for row in ranked["rows"]] == ["08:30", "09:30"]


def test_project_time_rankings_falls_back_when_preferred_labels_are_null():
    """Preferred key present-but-null must not block clock-bucket fallback."""
    summary = [
        {
            "entry_rth_segment": None,
            "entry_30min_bucket": "08:30",
            "trade_count": 20,
            "avg_r": 0.40,
            "sample_warning": False,
        },
        {
            "entry_rth_segment": None,
            "entry_30min_bucket": "09:30",
            "trade_count": 12,
            "avg_r": 0.10,
            "sample_warning": False,
        },
    ]
    ranked = project_time_rankings(summary, min_trades=10)
    assert ranked["bucket_col"] == "entry_30min_bucket"
    assert ranked["best"]["bucket"] == "08:30"


def test_build_ephemeral_context_merges_projections_without_mutating_packet():
    packet = _packet()
    original = packet.to_dict()
    context = build_ephemeral_results_context(
        packet,
        grid_rows=_grid_rows(),
        time_grouped_summary=[
            {
                "entry_rth_segment": "rth_morning",
                "trade_count": 12,
                "avg_r": 0.11,
                "sample_warning": False,
            }
        ],
    )
    assert "projections" not in original["results"]
    assert context["results"]["projections"]["grid_rankings"]["best"]["stop_loss_ticks"] == 8
    assert context["results"]["projections"]["time_rankings"]["best"]["bucket"] == "rth_morning"
    assert context["results"]["time_grouped_summary"][0]["entry_rth_segment"] == "rth_morning"


def test_build_ephemeral_context_empty_grid_rows_falls_back_to_best_grid():
    """Empty bundle grid_results must not blank out packet best_grid_result."""
    packet = _packet()
    context = build_ephemeral_results_context(packet, grid_rows=[])
    best = context["results"]["projections"]["grid_rankings"]["best"]
    assert best is not None
    assert best["stop_loss_ticks"] == 8
    assert best["take_profit_ticks"] == 16
    assert context["results"]["projections"]["grid_rankings"]["candidate_count"] == 1


def test_project_grid_rankings_treats_json_null_profit_factor_as_inf_for_all_wins():
    rows = [
        {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 10,
            "win_rate": 1.0,
            "profit_factor": None,  # JSON-coerced +inf
            "expectancy_r": 0.1,
        },
        {
            "stop_loss_ticks": 10,
            "take_profit_ticks": 20,
            "trade_count": 10,
            "win_rate": 0.6,
            "profit_factor": 2.0,
            "expectancy_r": 0.5,
        },
    ]
    ranked = project_grid_rankings(rows, metric="profit_factor", min_trades=1)
    assert ranked["best"]["stop_loss_ticks"] == 8
    assert ranked["best"]["metric_value"] is None  # JSON-safe
    assert ranked["rows"][1]["stop_loss_ticks"] == 10

    # Directional PF must use side win_rate, not aggregate.
    directional_rows = [
        {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "trade_count": 20,
            "win_rate": 0.5,
            "long_trade_count": 10,
            "long_win_rate": 1.0,
            "long_profit_factor": None,
            "short_trade_count": 10,
            "short_win_rate": 0.4,
            "short_profit_factor": 1.2,
        },
        {
            "stop_loss_ticks": 10,
            "take_profit_ticks": 20,
            "trade_count": 20,
            "win_rate": 0.9,
            "long_trade_count": 10,
            "long_win_rate": 0.7,
            "long_profit_factor": 3.0,
            "short_trade_count": 10,
            "short_win_rate": 0.9,
            "short_profit_factor": 2.5,
        },
    ]
    long_ranked = project_grid_rankings(directional_rows, metric="long_profit_factor", min_trades=1)
    assert long_ranked["best"]["stop_loss_ticks"] == 8


def test_build_ephemeral_pins_recorded_best_when_rerank_disagrees():
    packet = EvidencePacket(
        provenance={},
        assumptions={
            "grid": {
                "ranking_metric": "min_direction_expectancy_r",
                "min_trades": 1,
                "min_long_trades": 5,
                "min_short_trades": 5,
            }
        },
        results={
            "best_grid_result": {
                "ranking_metric": "min_direction_expectancy_r",
                "stop_loss_ticks": 6,
                "take_profit_ticks": 12,
                "trade_count": 20,
                "long_trade_count": 8,
                "short_trade_count": 7,
                "min_direction_expectancy_r": 0.15,
                "expectancy_r": 0.10,
            }
        },
        warnings=(),
    )
    # Aggregate expectancy would prefer SL=10, but recorded directional winner is 6/12.
    grid_rows = [
        {
            "stop_loss_ticks": 10,
            "take_profit_ticks": 20,
            "trade_count": 30,
            "long_trade_count": 2,
            "short_trade_count": 2,
            "expectancy_r": 0.50,
            "min_direction_expectancy_r": 0.01,
        },
        {
            "stop_loss_ticks": 6,
            "take_profit_ticks": 12,
            "trade_count": 20,
            "long_trade_count": 8,
            "short_trade_count": 7,
            "expectancy_r": 0.10,
            "min_direction_expectancy_r": 0.15,
        },
    ]
    context = build_ephemeral_results_context(packet, grid_rows=grid_rows)
    ranked = context["results"]["projections"]["grid_rankings"]
    assert ranked["metric"] == "min_direction_expectancy_r"
    assert ranked["min_long_trades"] == 5
    assert ranked["min_short_trades"] == 5
    assert ranked["best"]["stop_loss_ticks"] == 6
    assert ranked["best"]["take_profit_ticks"] == 12
    # Side filters exclude the high aggregate row (long/short counts < 5).
    assert ranked["eligible_count"] == 1


def test_propose_results_reply_grounds_projection_paths():
    packet = _packet()
    context = build_ephemeral_results_context(packet, grid_rows=_grid_rows())

    class Client:
        def complete_structured(self, **kwargs):
            return {
                "summary": (
                    "Best SL/TP by expectancy_r uses stop 8 and take profit 16 "
                    "from 4 grid candidates with min_trades 10; OOS status missing."
                ),
                "caveats": ["In-sample grid selection only."],
                "claims": [
                    {
                        "text": "Ranking metric is expectancy_r.",
                        "path": "results.projections.grid_rankings.metric",
                    },
                    {
                        "text": "Best stop is 8.",
                        "path": "results.projections.grid_rankings.best.stop_loss_ticks",
                    },
                    {
                        "text": "Best take profit is 16.",
                        "path": "results.projections.grid_rankings.best.take_profit_ticks",
                    },
                    {
                        "text": "Min trades filter is 10.",
                        "path": "results.projections.grid_rankings.min_trades",
                    },
                    {
                        "text": "Candidate count is 4.",
                        "path": "results.projections.grid_rankings.candidate_count",
                    },
                ],
                "followups": ["Ask about entry-time rankings next."],
            }

    reply = propose_results_reply(
        Client(),
        packet=packet,
        history=(),
        user_message="What is the best SL/TP?",
        turn_context=context,
    )
    assert reply.claims[1].value == 8
    assert reply.claims[2].value == 16


def _seed_completed_run(repository: LocalThesisRepository, *, name: str = "Proj"):
    thesis = repository.create_thesis(name=name)
    conversation = repository.create_conversation(thesis.thesis_id)
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "levels": {},
            "setup": {
                "name": name,
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
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    run = repository.start_run(
        thesis.thesis_id,
        spec_version=confirmed.version,
        request={"run_spec": confirmed.normalized_run_spec},
    )
    completed = repository.complete_run(
        thesis.thesis_id,
        run.run_id,
        expected_revision=run.revision,
        provenance={
            "bundle_path": "runs/proj.research.zip",
            "canonical_bundle_hash": "c" * 64,
        },
    )
    return thesis, conversation, completed


def test_handle_results_turn_enrichment_flag_off_skips_time_analyze(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis, conversation, run = _seed_completed_run(repository)
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    packet = _packet()
    monkeypatch.setattr(
        orchestrator,
        "explain_run",
        MagicMock(
            return_value=OrchestrationResult(
                status="completed",
                capability_id="BUNDLE.import",
                payload={"evidence": packet.to_dict()},
            )
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_bundle_tables_for_results",
        MagicMock(return_value=(None, None, None, None)),
    )
    enrich = MagicMock()
    monkeypatch.setattr(orchestrator, "_enrich_time_summary_for_results", enrich)
    dispatch = MagicMock(wraps=orchestrator.dispatch)
    execute = MagicMock(wraps=orchestrator.execute_confirmed_run)
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    monkeypatch.setattr(orchestrator, "execute_confirmed_run", execute)
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.load_results_qa_settings",
        lambda: type(
            "S",
            (),
            {
                "enabled": True,
                "max_history_messages": 12,
                "allow_time_enrichment": False,
                "repair_retry_enabled": True,
                "deterministic_overview_fallback": True,
            },
        )(),
    )

    class Client:
        def complete_structured(self, **kwargs):
            return {
                "summary": "No time rankings available.",
                "caveats": ["Time summary missing."],
                "claims": [],
                "followups": ["Enable time enrichment if needed."],
            }

    result = orchestrator.handle_results_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        message="Best entry window?",
        conversation_id=conversation.conversation_id,
    )
    assert result.status == "completed"
    enrich.assert_not_called()
    execute.assert_not_called()
    for call in dispatch.call_args_list:
        request = call.args[0] if call.args else None
        if request is not None:
            assert request.capability_id != "TIME.analyze"
            assert not str(request.capability_id).startswith("PIPELINE.")


def test_handle_results_turn_enrichment_on_calls_time_analyze_once(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis, conversation, run = _seed_completed_run(repository, name="Enrich")
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    packet = _packet()
    monkeypatch.setattr(
        orchestrator,
        "explain_run",
        MagicMock(
            return_value=OrchestrationResult(
                status="completed",
                capability_id="BUNDLE.import",
                payload={"evidence": packet.to_dict()},
            )
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_bundle_tables_for_results",
        MagicMock(return_value=(None, None, None, None)),
    )
    monkeypatch.setattr(
        orchestrator,
        "_enrich_time_summary_for_results",
        MagicMock(
            return_value=OrchestrationResult(
                status="completed",
                capability_id="TIME.analyze",
                payload={
                    "groups": [
                        {
                            "entry_rth_segment": "rth_morning",
                            "trade_count": 18,
                            "avg_r": 0.22,
                            "sample_warning": False,
                        }
                    ]
                },
            )
        ),
    )
    execute = MagicMock(wraps=orchestrator.execute_confirmed_run)
    monkeypatch.setattr(orchestrator, "execute_confirmed_run", execute)
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.load_results_qa_settings",
        lambda: type(
            "S",
            (),
            {
                "enabled": True,
                "max_history_messages": 12,
                "allow_time_enrichment": True,
                "repair_retry_enabled": True,
                "deterministic_overview_fallback": True,
            },
        )(),
    )
    captured = {}

    class Client:
        def complete_structured(self, **kwargs):
            captured["user"] = kwargs["user"]
            return {
                "summary": (
                    "Best entry window is rth_morning with 18 trades by avg_r and min_trades 10."
                ),
                "caveats": ["In-sample time buckets only."],
                "claims": [
                    {
                        "text": "Best bucket is rth_morning.",
                        "path": "results.projections.time_rankings.best.bucket",
                    },
                    {
                        "text": "Trade count is 18.",
                        "path": "results.projections.time_rankings.best.trade_count",
                    },
                    {
                        "text": "Min trades is 10.",
                        "path": "results.projections.time_rankings.min_trades",
                    },
                ],
                "followups": ["Ask about sample warnings."],
            }

    result = orchestrator.handle_results_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        message="What is the best entry time?",
        conversation_id=conversation.conversation_id,
    )
    assert result.status == "completed"
    assert orchestrator._enrich_time_summary_for_results.call_count == 1
    execute.assert_not_called()
    assert result.payload["time_enrichment"]["status"] == "completed"
    assert "rth_morning" in captured["user"]
    assert result.payload["results_reply"].claims[0].value == "rth_morning"


def test_handle_results_turn_surfaces_grid_table_load_failure(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis, conversation, run = _seed_completed_run(repository, name="LoadFail")
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    packet = _packet()
    monkeypatch.setattr(
        orchestrator,
        "explain_run",
        MagicMock(
            return_value=OrchestrationResult(
                status="completed",
                capability_id="BUNDLE.import",
                payload={"evidence": packet.to_dict()},
            )
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_bundle_tables_for_results",
        MagicMock(
            return_value=(
                None,
                None,
                None,
                "Bundle hash does not match recorded run provenance.",
            )
        ),
    )
    monkeypatch.setattr(
        "thesistester.assistant.orchestrator.load_results_qa_settings",
        lambda: type(
            "S",
            (),
            {
                "enabled": True,
                "max_history_messages": 12,
                "allow_time_enrichment": False,
                "repair_retry_enabled": True,
                "deterministic_overview_fallback": True,
            },
        )(),
    )

    class Client:
        def complete_structured(self, **kwargs):
            return {
                "summary": "Best stop is 8 from the recorded grid winner.",
                "caveats": ["Full grid table unavailable."],
                "claims": [
                    {
                        "text": "Best stop is 8.",
                        "path": "results.projections.grid_rankings.best.stop_loss_ticks",
                    }
                ],
                "followups": ["Ask about expectancy."],
            }

    result = orchestrator.handle_results_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        message="Best SL/TP?",
        conversation_id=conversation.conversation_id,
    )
    assert result.status == "completed"
    rankings = result.payload["results_turn_context"]["projections"]["grid_rankings"]
    assert rankings["bundle_tables_status"] == "unavailable"
    assert "could not be loaded" in rankings["bundle_tables_warning"]
    assert rankings["best"]["stop_loss_ticks"] == 8


def test_enrich_time_summary_fails_closed_on_hash_mismatch(tmp_path, monkeypatch):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis, conversation, run = _seed_completed_run(repository, name="Hash")
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )

    def boom(*args, **kwargs):
        raise AssistantToolError("Bundle hash does not match recorded run provenance.")

    monkeypatch.setattr(orchestrator.tools, "load_bundle_summary", boom)
    dispatch = MagicMock(wraps=orchestrator.dispatch)
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)

    result = orchestrator._enrich_time_summary_for_results(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        bundle_path="runs/proj.research.zip",
        expected_hash="c" * 64,
    )
    assert result.status == "failed"
    assert "does not match" in result.payload["error"]["message"]
    dispatch.assert_not_called()


def test_project_exit_reason_counts_caps_top_n_plus_other():
    rows = [{"exit_reason": f"R{i}", "r_multiple": 0.1} for i in range(EXIT_REASON_TOP_N + 3)]
    # Duplicate first reason so ordering is stable by count then label.
    rows.extend({"exit_reason": "R0", "r_multiple": 0.1} for _ in range(2))
    projection = project_exit_reason_counts(rows, top_n=EXIT_REASON_TOP_N)
    assert projection is not None
    assert projection["top_n"] == EXIT_REASON_TOP_N
    assert len(projection["reasons"]) == EXIT_REASON_TOP_N
    assert projection["other_unique_count"] == 3
    assert projection["other_count"] == 3
    assert projection["reasons"][0]["exit_reason"] == "R0"
    assert projection["reasons"][0]["count"] == 3


def test_project_extreme_trades_caps_best_and_worst():
    rows = [
        {"exit_reason": "TP", "r_multiple": float(i), "entry_timestamp": f"t{i}"}
        for i in range(EXTREME_TRADES_N + 2)
    ]
    projection = project_extreme_trades(rows, n=EXTREME_TRADES_N)
    assert projection is not None
    assert len(projection["best"]) == EXTREME_TRADES_N
    assert len(projection["worst"]) == EXTREME_TRADES_N
    assert projection["best"][0]["r_multiple"] == float(EXTREME_TRADES_N + 1)
    assert projection["worst"][0]["r_multiple"] == 0.0
    # Timestamps stay off the model-facing projection (digit-laundering risk).
    assert set(projection["best"][0]) <= {"r_multiple", "exit_reason"}
    assert "entry_timestamp" not in projection["best"][0]


def test_project_extreme_trades_hard_caps_oversized_n():
    rows = [{"exit_reason": "TP", "r_multiple": float(i)} for i in range(20)]
    projection = project_extreme_trades(rows, n=9)
    assert projection is not None
    assert len(projection["best"]) == EXTREME_TRADES_N
    assert len(projection["worst"]) == EXTREME_TRADES_N
    assert projection["n"] == EXTREME_TRADES_N


def test_project_streak_summary_prefers_trade_summary():
    packet = _packet(
        results={
            "trade_summary": {
                "trade_count": 10,
                "max_consecutive_wins": 4,
                "max_consecutive_losses": 2,
            }
        }
    )
    projection = project_streak_summary(packet, trade_rows=[{"r_multiple": 1.0}] * 10)
    assert projection == {
        "source": "trade_summary",
        "max_consecutive_wins": 4,
        "max_consecutive_losses": 2,
    }


def test_build_ephemeral_context_attaches_deep_trade_projections():
    packet = _packet()
    rows = [
        {"exit_reason": "TP", "r_multiple": 1.2},
        {"exit_reason": "SL", "r_multiple": -1.0},
        {"exit_reason": "TP", "r_multiple": 0.5},
    ]
    context = build_ephemeral_results_context(packet, trade_rows=rows)
    projections = context["results"]["projections"]
    assert "exit_reason_counts" in projections
    assert "extreme_trades" in projections
    assert "streak_summary" in projections
    assert projections["exit_reason_counts"]["total_trades"] == 3
    # Raw trade frames must not be attached to the ephemeral packet.
    assert "trades" not in context["results"]


def _combo_rows(n: int = 12) -> list[dict]:
    rows: list[dict] = []
    for index in range(n):
        rows.append(
            {
                "trade_id": index + 1,
                "entry_timestamp": f"2024-01-02T09:{30 + (index % 30):02d}:00",
                "r_multiple": 1.0 if index % 2 == 0 else -0.5,
                "level_names": "A|B" if index < 8 else "A",
            }
        )
    return rows


def test_project_confluence_combo_from_trades_bounded_and_omit_unavailable():
    packet = _packet()
    packet = EvidencePacket(
        provenance=packet.provenance,
        assumptions={
            **packet.assumptions,
            "setup_config": {
                "confluence_mode": "global_cluster",
                "selected_levels": ["A", "B"],
            },
        },
        results=packet.results,
        warnings=packet.warnings,
        limitations=packet.limitations,
    )
    projection = project_confluence_combo(_combo_rows(), packet_or_mapping=packet)
    assert projection is not None
    assert projection["available"] is True
    assert projection["top_n"] == CONFLUENCE_COMBO_TOP_N
    assert len(projection["top_exact_combo"]) <= CONFLUENCE_COMBO_TOP_N
    assert len(projection["top_level_count"]) <= CONFLUENCE_COMBO_TOP_N
    assert "top_pair" in projection
    assert projection["selection_scope"] == "observed_traded_combos"
    assert set(projection["warning_flags"]) >= {
        "membership_double_count",
        "pairwise_double_count",
        "trigger_3c_level_names",
    }
    assert isinstance(projection["warnings"], list)
    # Full by_* dumps must not ship in the projection leaf.
    assert "by_exact_combo" not in projection
    assert "tables" not in projection

    assert project_confluence_combo(None) is None
    assert project_confluence_combo([]) is None
    assert project_confluence_combo([{"r_multiple": 1.0}]) is None
    assert (
        project_confluence_combo(
            [{"r_multiple": 1.0, "level_names": ""}, {"r_multiple": -0.5, "level_names": "nan"}]
        )
        is None
    )


def test_build_ephemeral_context_attaches_confluence_combo_without_5c_siblings():
    packet = EvidencePacket(
        provenance={"run_id": "run_combo"},
        assumptions={
            "setup_config": {
                "confluence_mode": "global_cluster",
                "selected_levels": ["A", "B"],
            }
        },
        results={"trade_summary": {"trade_count": 12}},
        warnings=(),
        limitations=(),
    )
    context = build_ephemeral_results_context(packet, trade_rows=_combo_rows())
    projections = context["results"]["projections"]
    assert "confluence_combo" in projections
    assert projections["confluence_combo"]["available"] is True
    assert "confluence_combo_summary" not in context["results"]
    assert "trades" not in context["results"]


def test_project_confluence_combo_prefers_last_signal_setup_over_stale_setup_config():
    """Stale Setup Builder global_cluster must not beat signal-run anchor_rules."""
    rows = []
    for index in range(12):
        rows.append(
            {
                "trade_id": index + 1,
                "r_multiple": 1.0 if index % 2 == 0 else -0.5,
                "level_names": ["ANCHOR", "SUP"],
                "level_source_mode": "anchor_rules",
            }
        )
    packet = EvidencePacket(
        provenance={"run_id": "run_combo_identity"},
        assumptions={
            "setup_config": {
                "confluence_mode": "global_cluster",
                "selected_levels": ["A", "B"],
            },
            "last_signal_setup": {
                "confluence_mode": "anchor_rules",
                "anchor_level": "ANCHOR",
            },
        },
        results={"trade_summary": {"trade_count": 12}},
        warnings=(),
        limitations=(),
    )
    projection = project_confluence_combo(rows, packet_or_mapping=packet)
    assert projection is not None
    assert projection["confluence_mode"] == "anchor_rules"
    assert projection["anchor_level"] == "ANCHOR"


def test_project_confluence_combo_uses_signals_summary_setup_as_identity_fallback():
    rows = _combo_rows()
    packet = EvidencePacket(
        provenance={"run_id": "run_combo_signals_summary"},
        assumptions={
            # Deliberately omit confluence_mode on setup_config.
            "setup_config": {"selected_levels": ["A", "B"]},
        },
        results={
            "trade_summary": {"trade_count": 12},
            "signals_summary": {
                "available": True,
                "setup": {"confluence_mode": "global_cluster"},
            },
        },
        warnings=(),
        limitations=(),
    )
    projection = project_confluence_combo(rows, packet_or_mapping=packet)
    assert projection is not None
    assert projection["confluence_mode"] == "global_cluster"


def test_project_confluence_combo_uses_mounted_summary_when_signal_identity_absent():
    """Restored 5c summary on results must restore mode/anchor like report/bundle."""
    rows = []
    for index in range(12):
        rows.append(
            {
                "trade_id": index + 1,
                "r_multiple": 1.0 if index % 2 == 0 else -0.5,
                "level_names": ["ANCHOR", "SUP"],
            }
        )
    packet = EvidencePacket(
        provenance={"run_id": "run_combo_mounted_summary"},
        assumptions={"setup_config": {"selected_levels": ["A", "B"]}},
        results={
            "trade_summary": {"trade_count": 12},
            "confluence_combo_summary": {
                "available": True,
                "confluence_mode": "anchor_rules",
                "anchor_level": "ANCHOR",
            },
        },
        warnings=(),
        limitations=(),
    )
    projection = project_confluence_combo(rows, packet_or_mapping=packet)
    assert projection is not None
    assert projection["confluence_mode"] == "anchor_rules"
    assert projection["anchor_level"] == "ANCHOR"
