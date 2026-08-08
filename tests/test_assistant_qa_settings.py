"""RQ-0 results_qa / product_help settings loader tests."""

from __future__ import annotations

from pathlib import Path

from thesistester.assistant.llm import (
    is_draft_channel_message,
    load_llm_settings,
    load_product_help_settings,
    load_results_qa_settings,
)

TRACKED = Path("config/assistant.toml")


def test_load_llm_settings_still_succeeds_with_new_sections():
    settings = load_llm_settings(TRACKED)
    assert settings.provider == "openai"
    assert settings.max_history_messages == 12


def test_tracked_config_enables_results_and_help_channels():
    results = load_results_qa_settings(TRACKED)
    help_settings = load_product_help_settings(TRACKED)
    assert results.enabled is True
    assert results.max_history_messages == 12
    assert results.allow_time_enrichment is False
    assert results.repair_retry_enabled is True
    assert results.deterministic_overview_fallback is True
    assert help_settings.enabled is True
    assert help_settings.max_history_messages == 12
    assert help_settings.max_corpus_chars == 24000


def test_missing_channel_sections_are_disabled(tmp_path):
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "max_tool_rounds = 8\n"
        "max_history_messages = 7\n"
        "max_retries = 2\n",
        encoding="utf-8",
    )
    results = load_results_qa_settings(path)
    help_settings = load_product_help_settings(path)
    assert results.enabled is False
    assert results.allow_time_enrichment is False
    assert results.repair_retry_enabled is True
    assert results.deterministic_overview_fallback is True
    assert results.max_history_messages == 7
    assert help_settings.enabled is False
    assert help_settings.max_history_messages == 7
    assert help_settings.max_corpus_chars == 24000


def test_channel_history_override_when_section_present(tmp_path):
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "max_tool_rounds = 8\n"
        "max_history_messages = 20\n"
        "\n"
        "[assistant.results_qa]\n"
        "enabled = true\n"
        "max_history_messages = 3\n"
        "allow_time_enrichment = true\n"
        "\n"
        "[assistant.product_help]\n"
        "enabled = false\n"
        "max_history_messages = 4\n"
        "max_corpus_chars = 1000\n",
        encoding="utf-8",
    )
    results = load_results_qa_settings(path)
    help_settings = load_product_help_settings(path)
    assert results.enabled is True
    assert results.max_history_messages == 3
    assert results.allow_time_enrichment is True
    assert help_settings.enabled is False
    assert help_settings.max_history_messages == 4
    assert help_settings.max_corpus_chars == 1000


def test_is_draft_channel_message_helper():
    assert is_draft_channel_message({"role": "user", "content": "hi"}) is True
    assert is_draft_channel_message({"role": "user", "channel": None}) is True
    # Empty/whitespace channel is still "set" → non-draft (exclude from draft history).
    assert is_draft_channel_message({"role": "user", "channel": ""}) is False
    assert is_draft_channel_message({"role": "user", "channel": "  "}) is False
    assert is_draft_channel_message({"role": "user", "channel": "results_qa"}) is False
    assert is_draft_channel_message({"role": "user", "channel": "product_help"}) is False
    assert is_draft_channel_message("not-a-dict") is True


def test_enabled_flags_fail_closed_on_string_false(tmp_path):
    """``bool(\"false\")`` is True — channel flags must not treat that as enabled."""
    path = tmp_path / "assistant.toml"
    path.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "max_tool_rounds = 8\n"
        "max_history_messages = 12\n"
        "\n"
        "[assistant.results_qa]\n"
        "enabled = 'false'\n"
        "allow_time_enrichment = 'false'\n"
        "\n"
        "[assistant.product_help]\n"
        "enabled = 'false'\n"
        "max_corpus_chars = 1000\n",
        encoding="utf-8",
    )
    results = load_results_qa_settings(path)
    help_settings = load_product_help_settings(path)
    assert results.enabled is False
    assert results.allow_time_enrichment is False
    assert help_settings.enabled is False
