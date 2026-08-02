from thesistester.assistant.explainer import (
    EVIDENCE_PACKET_SCHEMA_VERSION,
    EvidencePacket,
    assert_claims_grounded,
    build_evidence_packet,
    compare_evidence,
    explain_evidence,
    explain_evidence_report,
)


def test_evidence_packet_and_explanation_are_grounded(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {"name": "test"}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {"model": "sl_first"}},
            "otf_filter": {},
            "results": {
                "trade_summary": {"trade_count": 12, "expectancy_r": 0.25},
                "backtest_intrabar_diagnostic": {"ambiguous": 1},
            },
        },
    )
    packet = build_evidence_packet({}, provenance={"bundle_hash": "abc"})
    explanation = explain_evidence(packet)
    report = explain_evidence_report(packet)

    assert packet.schema_version == EVIDENCE_PACKET_SCHEMA_VERSION
    assert packet.provenance["bundle_hash"] == "abc"
    assert "12 trades" in explanation
    assert "0.25" in explanation
    assert "below the 30-trade" in explanation
    assert "forecast" in explanation
    assert any(caveat.code == "low_sample" for caveat in packet.caveats)
    assert any(caveat.code == "intrabar_ambiguity" for caveat in packet.caveats)
    assert_claims_grounded(packet, report)


def test_missing_or_null_trade_count_is_safe_and_warns(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {}},
            "otf_filter": {},
            "results": {
                "trade_summary": {"trade_count": None},
                "backtest_intrabar_diagnostic": None,
            },
        },
    )
    packet = build_evidence_packet({}, provenance={})

    assert "unavailable" in " ".join(packet.warnings)
    assert "unknown trades" in explain_evidence(packet)
    assert any("trade_count is missing" in item for item in packet.limitations)


def test_evidence_packet_defensively_freezes_nested_payloads():
    source = {"nested": {"value": 1}}
    packet = EvidencePacket(provenance=source, assumptions={}, results={}, warnings=())
    source["nested"]["value"] = 2

    assert packet.provenance["nested"]["value"] == 1


def test_comparison_reports_metrics_assumptions_and_conclusions():
    left = EvidencePacket(
        provenance={"run_id": "left", "dataset_fingerprint": {"rows": 10}},
        assumptions={
            "instrument": "ES",
            "dataset_fingerprint": {"rows": 10},
            "costs_exposure": {"commission_per_side": 0, "slippage_ticks": 0},
            "backtest": {"stop_loss_ticks": 8},
        },
        results={"trade_summary": {"trade_count": 10, "expectancy_r": 0.1}},
        warnings=("Low sample.",),
        next_experiments=(
            "Gather a larger historical sample before ranking candidates (evidence: trade_count).",
        ),
    )
    right = EvidencePacket(
        provenance={"run_id": "right", "dataset_fingerprint": {"rows": 10}},
        assumptions={
            "instrument": "ES",
            "dataset_fingerprint": {"rows": 10},
            "costs_exposure": {"commission_per_side": 1.5, "slippage_ticks": 0.25},
            "backtest": {"stop_loss_ticks": 12},
        },
        results={"trade_summary": {"trade_count": 20, "expectancy_r": 0.2}},
        warnings=("Low sample.", "Costs excluded."),
    )

    comparison = compare_evidence(left, right)

    assert comparison["schema_version"] == 1
    assert comparison["metrics"]["expectancy_r"] == {"left": 0.1, "right": 0.2}
    assert comparison["warnings"] == ["Low sample.", "Costs excluded."]
    assert comparison["assumptions_diff"]["backtest"]["stop_loss_ticks"] == {
        "left": 8,
        "right": 12,
    }
    assert comparison["data_comparability"]["comparable"] is True
    assert any("Better expectancy_r is right" in item for item in comparison["conclusions"])
    assert any("metric=expectancy_r" in item for item in comparison["conclusions"])
    assert comparison["next_experiments"]


def test_explanation_flags_grid_selection_and_walk_forward_scope():
    rich = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {
                "otf_filter": {"available": True},
                "costs_exposure": {
                    "commission_per_side": 0,
                    "slippage_ticks": 0,
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                },
            },
            "results": {
                "trade_summary": {"trade_count": 40, "expectancy_r": 0.1},
                "best_grid_result": {
                    "ranking_metric": "expectancy_r",
                    "trade_count": 40,
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                },
                "validation_summary": {"status": "present"},
                "walk_forward_summary": {
                    "fold_count": 3,
                    "valid_fold_count": 3,
                    "median_test_expectancy_r": 0.05,
                },
                "monte_carlo_summary": {"status": "present"},
                "noise_summary": {"status": "present"},
                "sensitivity_summary": {"status": "present"},
                "overfitting_summary": {"status": "present"},
                "time_grouped_summary": [{"bucket": "A"}],
                "portfolio_summary": {"trade_count": 40},
            },
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    explanation = explain_evidence(rich)
    assert "expectancy_r" in explanation
    assert "Walk-forward" in explanation
    assert "Monte Carlo" in explanation
    assert "Time/session" in explanation
    assert "OTF filter" in explanation
    assert "Portfolio evidence" in explanation
    assert "Best grid candidate" in explanation
    assert "OOS/WFA status=present" in explanation
    assert_claims_grounded(rich)


def test_mandatory_caveats_cover_costs_overlap_oos_and_robustness(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {"model": "path_open_proximity"}},
            "otf_filter": {"available": False},
            "results": {
                "trade_summary": {"trade_count": 5, "expectancy_r": 0.1},
                "best_grid_result": {"ranking_metric": "expectancy_r", "trade_count": 5},
                "validation_summary": {"available": False},
                "walk_forward_summary": {"fold_count": 2, "valid_fold_count": 0},
                "backtest_intrabar_diagnostic": {"ambiguous": True},
            },
        },
    )
    packet = build_evidence_packet(
        {},
        provenance={
            "effective_configuration": {
                "backtest": {
                    "commission_per_side": 0,
                    "slippage_ticks": 0,
                    "exposure_policy": "allow_all",
                    "intrabar_model": "path_open_proximity",
                },
                "grid": {"enabled": True},
            },
            "trial_count": 12,
        },
    )
    codes = {caveat.code for caveat in packet.caveats}
    assert {
        "low_sample",
        "zero_costs",
        "overlapping_exposure",
        "intrabar_ambiguity",
        "grid_selection",
        "failed_oos",
        "failed_robustness",
        "multiple_testing",
    } <= codes
    assert packet.next_experiments
    assert any("Limitation:" in line for line in explain_evidence(packet).splitlines())


def test_evidence_packet_round_trip_preserves_versioned_fields():
    original = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {"bundle_hash": "abc"},
            "assumptions": {"instrument": "ES"},
            "results": {"trade_summary": {"trade_count": 3}},
            "warnings": ["Trade count is below the 30-trade screening threshold."],
            "caveats": [
                {
                    "code": "low_sample",
                    "message": "Trade count is below the 30-trade screening threshold.",
                    "path": "results.trade_summary.trade_count",
                }
            ],
            "limitations": ["Monte Carlo diagnostics are not present in this evidence packet."],
            "claims": [],
            "next_experiments": [
                "Gather a larger historical sample before ranking candidates (evidence: trade_count)."
            ],
        }
    )
    restored = EvidencePacket.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()
