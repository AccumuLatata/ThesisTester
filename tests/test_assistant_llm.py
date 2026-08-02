import pytest

from thesistester.assistant.llm import (
    LLMConfigurationError,
    LLMSettings,
    OpenAIStructuredClient,
    create_openai_client,
    load_llm_settings,
    require_openai_api_key,
)


def test_load_llm_settings_from_tracked_config(tmp_path):
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\nprovider = 'openai'\nmodel = 'gpt-5.6-luna'\nmax_tool_rounds = 8\nmax_history_messages = 12\n",
        encoding="utf-8",
    )
    settings = load_llm_settings(path)
    assert settings.model == "gpt-5.6-luna"


def test_key_must_be_environment_injected(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="rotated"):
        require_openai_api_key()


def test_openai_client_requires_strict_json_object_output():
    class Transport:
        def post_json(self, **kwargs):
            assert kwargs["payload"]["text"]["format"]["strict"] is True
            return {"output_text": '{"choice":"clarify"}'}

    client = OpenAIStructuredClient(
        settings=LLMSettings("openai", "test", 1, 1), api_key="test", transport=Transport()
    )
    assert client.complete_structured(system="system", user="user", schema={"type": "object"}) == {
        "choice": "clarify"
    }


def test_factory_requires_openai_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "rotated")
    with pytest.raises(LLMConfigurationError, match="not openai"):
        create_openai_client(LLMSettings("other", "test", 1, 1))
