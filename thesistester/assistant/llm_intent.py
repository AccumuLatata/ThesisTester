"""Structured, non-executing LLM intent adapter for thesis drafting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.thesis_compiler import ThesisDraft, compile_thesis

_INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["choices", "clarifications"],
    "properties": {
        "choices": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "value"],
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            },
        },
        "clarifications": {"type": "array", "items": {"type": "string"}},
    },
}


class LLMIntentError(ValueError):
    """Raised when a provider response violates the assistant intent contract."""


@dataclass(frozen=True)
class LLMIntent:
    choices: dict[str, Any]
    clarifications: tuple[str, ...]


def parse_llm_intent(payload: Mapping[str, Any]) -> LLMIntent:
    """Fail closed on malformed model output before it reaches compiler state."""
    if set(payload) != {"choices", "clarifications"}:
        raise LLMIntentError("LLM intent must contain only choices and clarifications.")
    choices = payload["choices"]
    clarifications = payload["clarifications"]
    if not isinstance(choices, list) or not isinstance(clarifications, list):
        raise LLMIntentError("LLM intent fields have invalid types.")
    if any(
        not isinstance(item, dict)
        or set(item) != {"key", "value"}
        or not isinstance(item["key"], str)
        or not item["key"].strip()
        or not isinstance(item["value"], str)
        for item in choices
    ):
        raise LLMIntentError("LLM choices must be key/value string objects.")
    if any(not isinstance(item, str) or not item.strip() for item in clarifications):
        raise LLMIntentError("LLM clarifications must be non-empty strings.")
    return LLMIntent(
        choices={item["key"]: item["value"] for item in choices},
        clarifications=tuple(clarifications),
    )


def propose_thesis_draft(client: StructuredLLMClient, *, prompt: str) -> ThesisDraft:
    """Ask a provider for choices, then deterministically compile a non-executable draft."""
    payload = client.complete_structured(
        system=(
            "Extract only explicit research choices. Do not request tools, run experiments, "
            "or claim performance. Return clarification questions for unresolved definitions."
        ),
        user=prompt,
        schema=_INTENT_SCHEMA,
    )
    intent = parse_llm_intent(payload)
    draft = compile_thesis(prompt, choices=intent.choices)
    combined = tuple(dict.fromkeys((*draft.unresolved_assumptions, *intent.clarifications)))
    return ThesisDraft(
        prompt=draft.prompt,
        normalized_run_spec=draft.normalized_run_spec,
        unresolved_assumptions=combined,
    )
