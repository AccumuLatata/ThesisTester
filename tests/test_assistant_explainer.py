from thesistester.assistant.explainer import (
    EvidencePacket,
    build_evidence_packet,
    compare_evidence,
    explain_evidence,
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

    assert packet.provenance["bundle_hash"] == "abc"
    assert "12 trades" in explanation
    assert "0.25" in explanation
    assert "below the 30-trade" in explanation
    assert "forecast" in explanation


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


def test_evidence_packet_defensively_freezes_nested_payloads():
    source = {"nested": {"value": 1}}
    packet = EvidencePacket(provenance=source, assumptions={}, results={}, warnings=())
    source["nested"]["value"] = 2

    assert packet.provenance["nested"]["value"] == 1


def test_comparison_reports_only_selected_packet_metrics():
    left = EvidencePacket(
        provenance={"run_id": "left"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10, "expectancy_r": 0.1}},
        warnings=("Low sample.",),
    )
    right = EvidencePacket(
        provenance={"run_id": "right"},
        assumptions={},
        results={"trade_summary": {"trade_count": 20, "expectancy_r": 0.2}},
        warnings=("Low sample.", "Costs excluded."),
    )

    comparison = compare_evidence(left, right)

    assert comparison["metrics"]["expectancy_r"] == {"left": 0.1, "right": 0.2}
    assert comparison["warnings"] == ["Low sample.", "Costs excluded."]
