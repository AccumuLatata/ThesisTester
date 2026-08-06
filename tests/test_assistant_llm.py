import io
import json
from urllib import error

import pytest

from thesistester.assistant.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMSettings,
    OpenAIStructuredClient,
    UrllibOpenAITransport,
    _api_key_from_secrets_mapping,
    _openai_transport_failure_message,
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
    monkeypatch.setattr("thesistester.assistant.llm._read_streamlit_openai_api_key", lambda: None)
    with pytest.raises(LLMConfigurationError, match="rotated"):
        require_openai_api_key()


def test_require_openai_api_key_prefers_environment_over_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-rotated")
    monkeypatch.setattr(
        "thesistester.assistant.llm._read_streamlit_openai_api_key",
        lambda: "secrets-rotated",
    )
    assert require_openai_api_key() == "env-rotated"


def test_require_openai_api_key_falls_back_to_streamlit_secrets(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "thesistester.assistant.llm._read_streamlit_openai_api_key",
        lambda: "secrets-rotated",
    )
    assert require_openai_api_key() == "secrets-rotated"


def test_require_openai_api_key_env_placeholder_falls_through_to_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "REPLACE_WITH_ROTATED_OPENAI_API_KEY")
    monkeypatch.setattr(
        "thesistester.assistant.llm._read_streamlit_openai_api_key",
        lambda: "secrets-rotated",
    )
    assert require_openai_api_key() == "secrets-rotated"


def test_api_key_from_secrets_mapping_flat_and_nested_precedence():
    assert _api_key_from_secrets_mapping({"OPENAI_API_KEY": "flat-key"}) == "flat-key"
    assert _api_key_from_secrets_mapping({"openai": {"api_key": "nested-key"}}) == "nested-key"
    assert (
        _api_key_from_secrets_mapping(
            {"OPENAI_API_KEY": "flat-key", "openai": {"api_key": "nested-key"}}
        )
        == "flat-key"
    )
    assert (
        _api_key_from_secrets_mapping({"OPENAI_API_KEY": "REPLACE_WITH_ROTATED_OPENAI_API_KEY"})
        is None
    )
    assert _api_key_from_secrets_mapping({"openai": {"api_key": ""}}) is None
    assert _api_key_from_secrets_mapping(None) is None


def test_usable_openai_api_key_strips_wrapping_quotes_and_bom():
    from thesistester.assistant.llm import _usable_openai_api_key

    assert _usable_openai_api_key('  "sk-abc123"  ') == "sk-abc123"
    assert _usable_openai_api_key("'sk-abc123'") == "sk-abc123"
    assert _usable_openai_api_key("\ufeffsk-abc123") == "sk-abc123"
    assert _usable_openai_api_key('"REPLACE_WITH_ROTATED_OPENAI_API_KEY"') is None


def test_api_key_from_secrets_mapping_accepts_nested_openai_api_key_alias():
    assert (
        _api_key_from_secrets_mapping({"openai": {"OPENAI_API_KEY": "sk-nested-alias"}})
        == "sk-nested-alias"
    )
    assert (
        _api_key_from_secrets_mapping(
            {"openai": {"OPENAI_API_KEY": '"sk-quoted-nested"', "api_key": "sk-preferred"}}
        )
        == "sk-preferred"
    )


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


def test_openai_client_parses_responses_output_array():
    class Transport:
        def post_json(self, **kwargs):
            return {
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}
                ]
            }

    client = OpenAIStructuredClient(
        settings=LLMSettings("openai", "test", 1, 1), api_key="test", transport=Transport()
    )
    assert client.complete_structured(system="system", user="user", schema={"type": "object"}) == {
        "ok": True
    }


def test_transport_failure_message_includes_http_status_and_redacts_key():
    body = json.dumps(
        {
            "error": {
                "message": "Incorrect API key provided: sk-abc123def456. Check your key.",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        }
    ).encode("utf-8")
    exc = error.HTTPError(
        url="https://api.openai.com/v1/responses",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(body),
    )
    message = _openai_transport_failure_message(exc)
    assert "OpenAI structured request failed" in message
    assert "HTTP 401" in message
    assert "invalid_api_key" in message
    assert "sk-***" in message
    assert "sk-abc123def456" not in message
    assert message.endswith(").")
    assert ".)." not in message


def test_transport_failure_message_redacts_configured_non_sk_key():
    secret = "my-secret-key-value"
    body = json.dumps(
        {
            "error": {
                "message": f"Incorrect API key provided: {secret}.",
                "code": "invalid_api_key",
            }
        }
    ).encode("utf-8")
    exc = error.HTTPError(
        url="https://api.openai.com/v1/responses",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(body),
    )
    message = _openai_transport_failure_message(exc, api_key=secret)
    assert secret not in message
    assert "***" in message
    assert "HTTP 401" in message


def test_transport_failure_message_for_timeout_bad_json_and_urlerror():
    assert _openai_transport_failure_message(TimeoutError()) == (
        "OpenAI structured request failed (timed out)."
    )
    assert _openai_transport_failure_message(json.JSONDecodeError("Expecting value", "", 0)) == (
        "OpenAI structured request failed (invalid JSON response)."
    )
    assert _openai_transport_failure_message(error.URLError("Name or service not known")) == (
        "OpenAI structured request failed (Name or service not known)."
    )


def test_transport_failure_message_uses_string_error_field():
    body = json.dumps({"error": "sk-abc123XYZ is invalid"}).encode("utf-8")
    exc = error.HTTPError(
        url="https://api.openai.com/v1/responses",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(body),
    )
    message = _openai_transport_failure_message(exc)
    assert "sk-***" in message
    assert "sk-abc123XYZ" not in message
    assert '{"error"' not in message


def test_urllib_transport_surfaces_http_error_detail(monkeypatch):
    body = json.dumps(
        {
            "error": {
                "message": "Incorrect API key provided: sk-live-secret-value.",
                "code": "invalid_api_key",
            }
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=30):  # noqa: ARG001
        raise error.HTTPError(
            url=req.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr("thesistester.assistant.llm.request.urlopen", fake_urlopen)
    with pytest.raises(LLMProviderError, match="HTTP 401") as caught:
        UrllibOpenAITransport().post_json(
            url="https://api.openai.com/v1/responses",
            api_key="sk-test-key",
            payload={"model": "gpt-5.6-luna"},
        )
    assert "invalid_api_key" in str(caught.value)
    assert "sk-live-secret-value" not in str(caught.value)
    assert caught.value.retryable is False


def test_urllib_transport_redacts_configured_api_key_echo(monkeypatch):
    secret = "plain-configured-secret"
    body = json.dumps(
        {"error": {"message": f"Incorrect API key provided: {secret}.", "code": "invalid_api_key"}}
    ).encode("utf-8")

    def fake_urlopen(req, timeout=30):  # noqa: ARG001
        raise error.HTTPError(
            url=req.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr("thesistester.assistant.llm.request.urlopen", fake_urlopen)
    with pytest.raises(LLMProviderError) as caught:
        UrllibOpenAITransport().post_json(
            url="https://api.openai.com/v1/responses",
            api_key=secret,
            payload={"model": "gpt-5.6-luna"},
        )
    assert secret not in str(caught.value)
    assert caught.value.retryable is False


def test_structured_client_does_not_retry_non_retryable_http(monkeypatch):
    settings = LLMSettings(
        provider="openai",
        model="gpt-test",
        max_tool_rounds=1,
        max_history_messages=4,
        max_retries=2,
    )
    calls = {"n": 0}

    class OnceTransport:
        def post_json(self, *, url, api_key, payload):  # noqa: ARG002
            calls["n"] += 1
            raise LLMProviderError(
                "OpenAI structured request failed (HTTP 401: x).", retryable=False
            )

    client = OpenAIStructuredClient(
        settings=settings, api_key="sk-test-key", transport=OnceTransport()
    )
    with pytest.raises(LLMProviderError, match="HTTP 401"):
        client.complete_structured(system="s", user="u", schema={"type": "object"})
    assert calls["n"] == 1
    assert client.last_attempt_count == 1
