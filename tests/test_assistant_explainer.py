from thesistester.assistant.explainer import build_evidence_packet, explain_evidence


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
