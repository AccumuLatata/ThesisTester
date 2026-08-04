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


def test_failure_claim_grounds_to_results_error_when_provenance_lacks_it():
    packet = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {"status": "failed"},
            "assumptions": {},
            "results": {"error": "bundle write failed"},
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    report = explain_evidence_report(packet)
    assert "Failure diagnosis: bundle write failed." in report["narrative"]
    error_claims = [claim for claim in report["claims"] if "error" in claim["path"]]
    assert error_claims == [
        {
            "text": "Failure diagnosis: bundle write failed.",
            "path": "results.error",
            "value": "bundle write failed",
        }
    ]
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


def test_grid_ranking_claim_grounds_to_assumptions_when_absent_from_best_row():
    """Real best_grid_result rows omit ranking_metric; claim the config path instead."""
    packet = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {
                "grid": {"enabled": True, "ranking_metric": "expectancy_r"},
                "costs_exposure": {
                    "commission_per_side": 1.25,
                    "slippage_ticks": 0.5,
                },
            },
            "results": {
                "trade_summary": {"trade_count": 40, "expectancy_r": 0.1},
                "best_grid_result": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "trade_count": 40,
                    "expectancy_r": 0.1,
                },
            },
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    report = explain_evidence_report(packet)
    assert "Best grid candidate by expectancy_r" in report["narrative"]
    metric_claims = [
        claim for claim in report["claims"] if claim["path"].endswith("ranking_metric")
    ]
    assert len(metric_claims) == 1
    assert metric_claims[0]["path"] == "assumptions.grid.ranking_metric"
    assert metric_claims[0]["value"] == "expectancy_r"
    cost_paths = {
        claim["path"]: claim["value"]
        for claim in report["claims"]
        if claim["path"].startswith("assumptions.costs_exposure.")
    }
    assert cost_paths["assumptions.costs_exposure.commission_per_side"] == 1.25
    assert cost_paths["assumptions.costs_exposure.slippage_ticks"] == 0.5
    assert_claims_grounded(packet, report)


def test_explanation_flags_grid_selection_and_walk_forward_scope():
    rich = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {
                "otf_filter": {"available": True},
                "grid": {"ranking_metric": "expectancy_r"},
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
                    "trade_count": 40,
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "expectancy_r": 0.1,
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


def test_build_evidence_packet_wires_top_level_otf_validation(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {}},
            "otf_filter": {"available": False},
            "results": {"trade_summary": {"trade_count": 40, "expectancy_r": 0.1}},
            "otf_validation": {
                "available": True,
                "summary": {"selected_label": "off", "oos_expectancy_r": 0.02},
                "config": {"train_fraction": 0.7},
            },
        },
    )
    packet = build_evidence_packet({}, provenance={})
    assert packet.results["otf_validation"]["available"] is True
    assert packet.results["otf_validation_summary"]["selected_label"] == "off"
    report = explain_evidence_report(packet)
    assert "OTF validation summary evidence is present." in report["narrative"]
    assert any(
        claim["path"] == "results.otf_validation_summary"
        and claim["value"]["selected_label"] == "off"
        for claim in report["claims"]
    )
    assert_claims_grounded(packet, report)


def test_build_evidence_packet_nests_dataset_fingerprint_under_dataset(monkeypatch):
    """Fingerprint must resolve at both nested and sibling assumption paths."""
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {}},
            "otf_filter": {},
            "results": {"trade_summary": {"trade_count": 12, "expectancy_r": 0.1}},
        },
    )
    fingerprint = {"rows": 10, "hash": "abc"}
    packet = build_evidence_packet(
        {},
        provenance={
            "dataset_fingerprint": fingerprint,
            "effective_configuration": {
                "dataset": {"path": "bars.csv", "instrument": "ES"},
            },
        },
    )
    assert packet.assumptions["dataset_fingerprint"] == fingerprint
    assert packet.assumptions["dataset"]["path"] == "bars.csv"
    assert packet.assumptions["dataset"]["dataset_fingerprint"] == fingerprint
    # Provenance remains authoritative; nested copy must not invent a second identity.
    assert packet.provenance["dataset_fingerprint"] == fingerprint


def test_build_evidence_packet_omits_nested_fingerprint_when_provenance_missing(
    monkeypatch,
):
    """Null nested identity must not become a citable LLM claim path."""
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {}},
            "otf_filter": {},
            "results": {"trade_summary": {"trade_count": 12, "expectancy_r": 0.1}},
        },
    )
    packet = build_evidence_packet(
        {},
        provenance={
            "effective_configuration": {
                "dataset": {
                    "path": "bars.csv",
                    "instrument": "ES",
                    # Config-sourced identity must not become a claimable path.
                    "dataset_fingerprint": {"rows": 99, "hash": "from-config"},
                },
            },
        },
    )
    assert packet.assumptions["dataset_fingerprint"] is None
    assert "dataset_fingerprint" not in packet.assumptions["dataset"]
    assert packet.assumptions["dataset"]["path"] == "bars.csv"


def test_otf_template_does_not_claim_availability_on_empty_filter():
    packet = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {"otf_filter": {}},
            "results": {
                "otf_validation_summary": {"selected_label": "baseline"},
            },
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    report = explain_evidence_report(packet)
    assert "OTF validation summary evidence is present." in report["narrative"]
    assert "OTF filter evidence available=True" not in report["narrative"]
    assert all(claim["path"] != "assumptions.otf_filter" for claim in report["claims"])
    assert_claims_grounded(packet, report)


def test_otf_template_reads_history_policy_from_wfa_summary_without_assumptions():
    """Completed WFO packets may only expose otf_history_policy on the summary."""
    packet = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {},
            "results": {
                "walk_forward_summary": {
                    "fold_count": 2,
                    "valid_fold_count": 2,
                    "otf_history_policy": "causal_prefix",
                }
            },
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    report = explain_evidence_report(packet)
    assert "Walk-forward OTF history policy=causal_prefix" in report["narrative"]
    assert any(
        claim["path"] == "results.walk_forward_summary.otf_history_policy"
        and claim["value"] == "causal_prefix"
        for claim in report["claims"]
    )
    assert_claims_grounded(packet, report)


def test_intrabar_ambiguity_caveat_from_costs_model_without_diagnostic():
    """Non-sl_first models must caveat even when diagnostic evidence is absent."""
    packet = EvidencePacket.from_dict(
        {
            "schema_version": 1,
            "provenance": {},
            "assumptions": {
                "intrabar": {"intrabar_model": "path_open_proximity"},
                "costs_exposure": {"intrabar_model": "path_open_proximity"},
            },
            "results": {"trade_summary": {"trade_count": 40, "expectancy_r": 0.1}},
            "warnings": [],
            "caveats": [],
            "limitations": [],
            "claims": [],
            "next_experiments": [],
        }
    )
    # Rebuild caveats through the packet builder path using a monkeypatched artifact.
    from thesistester.assistant import explainer as explainer_mod

    caveats, _limitations = explainer_mod._derive_caveats(
        results=packet.results,
        assumptions=packet.assumptions,
        provenance=packet.provenance,
    )
    match = [item for item in caveats if item.code == "intrabar_ambiguity"]
    assert match
    assert match[0].path == "assumptions.intrabar.intrabar_model"


def test_mandatory_caveats_cover_costs_overlap_oos_and_robustness(monkeypatch):
    monkeypatch.setattr(
        "thesistester.assistant.explainer.build_research_artifact",
        lambda state: {
            "configuration": {"setup_config": {}, "instrument": "ES"},
            "intrabar": {"backtest_policy": {"intrabar_model": "path_open_proximity"}},
            "otf_filter": {"available": False},
            "results": {
                "trade_summary": {"trade_count": 5, "expectancy_r": 0.1},
                "best_grid_result": {"ranking_metric": "expectancy_r", "trade_count": 5},
                "validation_summary": {"available": False},
                "walk_forward_summary": {"fold_count": 2, "valid_fold_count": 0},
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
