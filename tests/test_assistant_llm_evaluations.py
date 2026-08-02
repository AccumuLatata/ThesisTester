"""Adversarial C2-6 evaluation fixtures for the LLM boundary."""

import pytest

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm_explainer import LLMEvidenceError, explain_packet_with_llm
from thesistester.assistant.llm_intent import LLMIntentError, parse_llm_intent


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [], "clarifications": [], "tool_request": "PIPELINE.run_experiment"},
        {
            "choices": [{"key": "trend_rule", "value": "x"}, {"key": "trend_rule", "value": "y"}],
            "clarifications": [],
        },
        {"choices": [{"key": "trend_rule", "value": " "}], "clarifications": []},
    ],
)
def test_adversarial_intent_payloads_fail_closed(payload):
    with pytest.raises(LLMIntentError):
        parse_llm_intent(payload)


def test_explanation_rejects_unexpected_provider_fields():
    class Client:
        def complete_structured(self, **kwargs):
            return {"summary": "result", "caveats": [], "tool": "run"}

    packet = EvidencePacket(provenance={}, assumptions={}, results={}, warnings=())
    with pytest.raises(LLMEvidenceError):
        explain_packet_with_llm(Client(), packet=packet)
