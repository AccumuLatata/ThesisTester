from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm_explainer import explain_packet_with_llm


def test_llm_explanation_receives_only_evidence_packet():
    class Client:
        def complete_structured(self, **kwargs):
            assert "secret" not in kwargs["user"]
            return {
                "summary": "Observed sample has 10 trades.",
                "caveats": ["Small sample."],
                "claims": [
                    {
                        "text": "Observed sample has 10 trades.",
                        "path": "results.trade_summary.trade_count",
                    }
                ],
            }

    packet = EvidencePacket(
        provenance={"run_id": "run"},
        assumptions={},
        results={"trade_summary": {"trade_count": 10}},
        warnings=("Small sample.",),
    )
    explanation = explain_packet_with_llm(Client(), packet=packet)
    assert explanation.summary == "Observed sample has 10 trades."
    assert explanation.claims[0].value == 10
