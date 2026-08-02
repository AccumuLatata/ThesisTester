"""Provider-neutral, structured LLM boundary for the research assistant."""

from __future__ import annotations

import os
import json
from urllib import error, request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib


class LLMConfigurationError(ValueError):
    """Raised when the optional assistant provider is not safely configured."""


class LLMProviderError(RuntimeError):
    """Raised when a provider request fails or returns invalid structured output."""


class StructuredLLMClient(Protocol):
    """Minimal injectable client contract; provider SDKs stay outside engine code."""

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class OpenAITransport(Protocol):
    """Injectable HTTPS transport for deterministic provider tests."""

    def post_json(self, *, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class UrllibOpenAITransport:
    """Minimal standard-library transport; no provider SDK reaches engine code."""

    def post_json(self, *, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        outbound = request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=30) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMProviderError("OpenAI structured request failed.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI response must be an object.")
        return decoded


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    max_tool_rounds: int
    max_history_messages: int


@dataclass
class OpenAIStructuredClient:
    """OpenAI Responses client restricted to JSON-schema output."""

    settings: LLMSettings
    api_key: str
    transport: OpenAITransport
    endpoint: str = "https://api.openai.com/v1/responses"

    def complete_structured(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": [{"type": "input_text", "text": user}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "assistant_response",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = self.transport.post_json(
            url=self.endpoint, api_key=self.api_key, payload=payload
        )
        text = response.get("output_text")
        if not isinstance(text, str):
            raise LLMProviderError("OpenAI response did not contain output_text.")
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("OpenAI response is not valid JSON.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI structured output must be an object.")
        return decoded


def create_openai_client(
    settings: LLMSettings, *, transport: OpenAITransport | None = None
) -> OpenAIStructuredClient:
    """Create an OpenAI client only for the configured provider."""
    if settings.provider != "openai":
        raise LLMConfigurationError("Configured provider is not openai.")
    return OpenAIStructuredClient(
        settings=settings,
        api_key=require_openai_api_key(),
        transport=transport or UrllibOpenAITransport(),
    )


def load_llm_settings(path: str | Path = "config/assistant.toml") -> LLMSettings:
    """Load non-secret assistant settings from tracked TOML."""
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        raise LLMConfigurationError("Missing [assistant] configuration.")
    return LLMSettings(
        provider=str(assistant.get("provider", "")),
        model=str(assistant.get("model", "")),
        max_tool_rounds=int(assistant.get("max_tool_rounds", 0)),
        max_history_messages=int(assistant.get("max_history_messages", 0)),
    )


def require_openai_api_key() -> str:
    """Return only an environment-injected key; never read tracked configuration."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key or key == "REPLACE_WITH_ROTATED_OPENAI_API_KEY":
        raise LLMConfigurationError("Set OPENAI_API_KEY to a rotated credential.")
    return key
