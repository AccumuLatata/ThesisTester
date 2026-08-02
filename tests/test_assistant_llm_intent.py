import pytest

from thesistester.assistant.llm_intent import LLMIntentError, parse_llm_intent, propose_thesis_draft


def test_intent_parser_rejects_unknown_model_fields():
    with pytest.raises(LLMIntentError, match="only"):
        parse_llm_intent({"choices": {}, "clarifications": [], "tool": "run"})


def test_provider_draft_remains_non_executing():
    class Client:
        def complete_structured(self, **kwargs):
            return {
                "choices": {
                    "trend_rule": "SMA slope",
                    "trigger": "touch",
                    "session_window": "10:00-11:00 ET",
                    "success_criteria": "30 trades",
                },
                "clarifications": ["Confirm dataset and costs."],
            }

    draft = propose_thesis_draft(Client(), prompt="Test an uptrend pullback.")
    assert "Confirm dataset and costs." in draft.unresolved_assumptions
