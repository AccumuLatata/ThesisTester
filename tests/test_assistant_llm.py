import pytest

from thesistester.assistant.llm import (
    LLMConfigurationError,
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
