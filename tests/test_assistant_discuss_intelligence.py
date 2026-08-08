"""DI Discuss Intelligence: matcher, TLS wrap, overview fallback, path catalog."""

from __future__ import annotations

import json
import ssl
from urllib import error as urllib_error

import pytest

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm import (
    LLMProviderError,
    UrllibOpenAITransport,
    _is_tls_allowlist_error,
    load_results_qa_settings,
)
from thesistester.assistant.llm_explainer import LLMEvidenceError, _path_exists
from thesistester.assistant.results_overview import (
    KPI_CLAIM_PATHS,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    REASON_DIGIT_MISS,
    REASON_PATH_MISS,
    REASON_PROVIDER_EXHAUSTED,
    REASON_REPAIR_FAILED,
    build_prompt_path_catalog,
    collect_existing_paths,
    failure_class_from_exception,
    match_overview_intent,
    present_kpi_allowlist,
)
from thesistester.assistant.results_qa import propose_results_reply


def _packet(**trade_summary_extra) -> EvidencePacket:
    summary = {
        "trade_count": 42,
        "expectancy_r": 0.25,
        "win_rate": 0.52,
        "profit_factor": 1.4,
        "max_drawdown_r": -2.0,
        "total_r": 10.5,
    }
    summary.update(trade_summary_extra)
    return EvidencePacket(
        provenance={"run_id": "run_di1"},
        assumptions={"instrument": "NQ"},
        results={
            "trade_summary": summary,
            "best_grid_result": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "trade_count": 40,
            },
        },
        warnings=(),
        limitations=("Time analysis is not present in this evidence packet.",),
    )


class _FailClient:
    def __init__(self, payload_or_exc):
        self._items = list(payload_or_exc) if isinstance(payload_or_exc, list) else [payload_or_exc]
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        item = self._items[min(self.calls - 1, len(self._items) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


def _bad_path_payload(path: str = "results.instrument") -> dict:
    return {
        "summary": "Instrument is NQ.",
        "caveats": ["Path may be wrong."],
        "claims": [{"text": "Instrument is NQ.", "path": path}],
        "followups": ["Ask about KPIs next."],
    }


def _bare_percent_payload() -> dict:
    return {
        "summary": "Win rate is 52.",
        "caveats": ["Bare percent points."],
        "claims": [
            {
                "text": "Win rate is 52.",
                "path": "results.trade_summary.win_rate",
            }
        ],
        "followups": ["Ask again with a percent sign."],
    }


def test_match_overview_intent_positive_and_veto():
    assert match_overview_intent("Give me the KPIs of this run") == OVERVIEW_INTENT_KPI
    assert match_overview_intent("key metrics please") == OVERVIEW_INTENT_KPI
    assert match_overview_intent("summary of this run") == OVERVIEW_INTENT_RUN
    assert match_overview_intent("a summary of this run") == OVERVIEW_INTENT_RUN
    assert match_overview_intent("highlights of this run") == OVERVIEW_INTENT_RUN
    assert match_overview_intent("summarize this run") == OVERVIEW_INTENT_RUN
    # Bare tokens alone are insufficient.
    assert match_overview_intent("summary") is None
    assert match_overview_intent("overview") is None
    assert match_overview_intent("highlights") is None
    # Negative veto / mixed ask.
    assert match_overview_intent("summarize the walk-forward results") is None
    assert match_overview_intent("summary of best SL/TP") is None
    assert match_overview_intent("KPIs and best SL/TP") is None
    assert match_overview_intent("Give me KPIs and validation stats") is None
    # Word-boundary false friends must not veto.
    assert match_overview_intent("summary of this run for runtime review") == OVERVIEW_INTENT_RUN
    assert match_overview_intent("key metrics before stopwatch calibration") == OVERVIEW_INTENT_KPI
    # Multi-word cues must not substring-match false friends.
    assert match_overview_intent("highlights of this runtime") is None
    assert match_overview_intent("summarize this runaway") is None
    assert match_overview_intent("passkey metrics") is None
    # Hyphen compounds must not trip bare negative cues stop/grid.
    assert match_overview_intent("non-stop key metrics please") == OVERVIEW_INTENT_KPI
    assert match_overview_intent("off-grid key metrics") == OVERVIEW_INTENT_KPI


def test_tls_allowlist_wraps_ssl_error(monkeypatch):
    def boom(*args, **kwargs):
        raise ssl.SSLError("SSLV3_ALERT_BAD_RECORD_MAC")

    monkeypatch.setattr("thesistester.assistant.llm.request.urlopen", boom)
    with pytest.raises(LLMProviderError, match="TLS error") as caught:
        UrllibOpenAITransport().post_json(
            url="https://api.openai.com/v1/responses",
            api_key="sk-test",
            payload={"model": "x"},
        )
    assert caught.value.retryable is True
    assert failure_class_from_exception(caught.value) == "provider_tls"


def test_tls_allowlist_wraps_urlerror_ssl_reason(monkeypatch):
    def boom(*args, **kwargs):
        raise urllib_error.URLError(ssl.SSLError("bad record mac"))

    monkeypatch.setattr("thesistester.assistant.llm.request.urlopen", boom)
    with pytest.raises(LLMProviderError, match="TLS error") as caught:
        UrllibOpenAITransport().post_json(
            url="https://api.openai.com/v1/responses",
            api_key="sk-test",
            payload={"model": "x"},
        )
    assert caught.value.retryable is True
    assert "TLS error" in str(caught.value)
    assert failure_class_from_exception(caught.value) == "provider_tls"
    assert _is_tls_allowlist_error(urllib_error.URLError(ssl.SSLError("x")))
    assert not _is_tls_allowlist_error(OSError("disk full"))


def test_path_miss_on_kpi_ask_falls_back_to_trade_summary():
    client = _FailClient([_bad_path_payload("results.instrument"), _bad_path_payload()])
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="Give me the KPIs of this run",
    )
    assert reply.recovery_reason == REASON_REPAIR_FAILED
    paths = {claim.path for claim in reply.claims}
    assert "results.trade_summary.trade_count" in paths
    assert "results.trade_summary.win_rate" in paths
    assert all("instrument" not in claim.path for claim in reply.claims)
    assert "52%" in reply.summary or "52 %" in " ".join(c.text for c in reply.claims)


def test_validation_path_miss_on_run_summary_falls_back():
    client = _FailClient(_bad_path_payload("results.validation.trade_count"))
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="a summary of this run",
        repair_retry_enabled=False,
    )
    assert reply.recovery_reason == REASON_PATH_MISS
    assert any(c.path == "results.trade_summary.expectancy_r" for c in reply.claims)


def test_bare_percent_on_run_summary_recovers_via_deterministic_fallback():
    client = _FailClient(_bare_percent_payload())
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="summary of this run",
        repair_retry_enabled=False,
    )
    assert reply.recovery_reason == REASON_DIGIT_MISS
    assert any("52%" in c.text for c in reply.claims)


def test_specialist_ask_path_miss_does_not_topic_swap_to_kpi():
    client = _FailClient(_bad_path_payload("results.validation.trade_count"))
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="Summarize the walk-forward results",
        repair_retry_enabled=False,
    )
    assert reply.claims == ()
    assert "could not ground" in reply.summary.lower()
    assert not any("trade_count" in c.path for c in reply.claims)


def test_mixed_ask_full_veto_no_partial_kpi_slice():
    client = _FailClient(_bad_path_payload())
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="KPIs and best SL/TP",
        repair_retry_enabled=False,
    )
    assert reply.claims == ()
    assert reply.recovery_reason == REASON_PATH_MISS


def test_flags_off_hard_fail_still_raises():
    client = _FailClient(_bad_path_payload())
    with pytest.raises(LLMEvidenceError, match="missing from the evidence packet"):
        propose_results_reply(
            client,
            packet=_packet(),
            history=(),
            user_message="Give me the KPIs of this run",
            repair_retry_enabled=False,
            deterministic_overview_fallback=False,
        )


def test_provider_exhaustion_on_overview_uses_deterministic_fallback():
    client = _FailClient(
        LLMProviderError("OpenAI structured request failed (TLS error).", retryable=True)
    )
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="key metrics",
        repair_retry_enabled=False,
    )
    assert reply.recovery_reason == REASON_PROVIDER_EXHAUSTED
    assert any(c.path.startswith("results.trade_summary.") for c in reply.claims)


def test_provider_error_skips_repair_second_model_call():
    """§5: LLMProviderError must not trigger a repair model call."""
    client = _FailClient(
        LLMProviderError("OpenAI structured request failed (TLS error).", retryable=True)
    )
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="key metrics",
        repair_retry_enabled=True,
        deterministic_overview_fallback=True,
    )
    assert client.calls == 1
    assert reply.recovery_reason == REASON_PROVIDER_EXHAUSTED
    assert any(c.path.startswith("results.trade_summary.") for c in reply.claims)


def test_missing_trade_summary_deterministic_limitation():
    packet = EvidencePacket(
        provenance={},
        assumptions={},
        results={},
        warnings=(),
        limitations=("Baseline trade_summary is missing from evidence.",),
    )
    client = _FailClient(_bad_path_payload())
    reply = propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Give me the KPIs of this run",
        repair_retry_enabled=False,
    )
    assert reply.claims == ()
    # §4.2: prefer digit-free packet limitation over generic empty-KPI copy.
    assert "baseline trade_summary is missing from evidence" in reply.summary.lower()
    assert all(not any(ch.isdigit() for ch in followup) for followup in reply.followups)


def test_fat_provenance_repair_catalog_keeps_kpi_paths():
    """Repair path catalog must not starve KPI leaves behind fat provenance."""
    fat_provenance = {f"blob_{i}": {"nested": i} for i in range(400)}
    context = {
        "provenance": fat_provenance,
        "assumptions": {"instrument": "NQ"},
        "results": {
            "trade_summary": {
                "trade_count": 42,
                "expectancy_r": 0.25,
                "win_rate": 0.52,
            }
        },
        "warnings": [],
        "limitations": [],
    }
    paths = collect_existing_paths(context, max_paths=240)
    for required in (
        "results.trade_summary.trade_count",
        "results.trade_summary.expectancy_r",
        "results.trade_summary.win_rate",
    ):
        assert required in paths
    assert any(p in paths for p in KPI_CLAIM_PATHS)


def test_repair_retry_succeeds_without_fallback():
    good = {
        "summary": "Sample has 42 trades.",
        "caveats": ["Historical sample only."],
        "claims": [
            {
                "text": "Sample has 42 trades.",
                "path": "results.trade_summary.trade_count",
            }
        ],
        "followups": ["Ask about expectancy next."],
    }
    client = _FailClient([_bad_path_payload(), good])
    reply = propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="How many trades?",
    )
    assert client.calls == 2
    assert reply.recovery_reason is None
    assert reply.claims[0].value == 42


def test_tracked_config_loads_di1_recovery_defaults():
    settings = load_results_qa_settings("config/assistant.toml")
    assert settings.repair_retry_enabled is True
    assert settings.deterministic_overview_fallback is True


class _CaptureClient:
    """Capture complete_structured kwargs; return a grounded overview reply."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "summary": "Sample has 42 trades. Win rate is 52 percent.",
            "caveats": ["Historical sample only."],
            "claims": [
                {
                    "text": "Sample has 42 trades.",
                    "path": "results.trade_summary.trade_count",
                },
                {
                    "text": "Win rate is 52 percent.",
                    "path": "results.trade_summary.win_rate",
                },
            ],
            "followups": ["Ask about expectancy next."],
        }


def _user_payload_from_call(call: dict) -> dict:
    return json.loads(call["user"])


def test_di2_overview_ask_includes_path_catalog_and_kpi_allowlist():
    client = _CaptureClient()
    packet = _packet()
    propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="Give me the KPIs of this run",
    )
    assert len(client.calls) == 1
    payload = _user_payload_from_call(client.calls[0])
    assert "path_catalog" in payload
    catalog = payload["path_catalog"]
    existing = catalog["existing_paths"]
    assert isinstance(existing, list) and existing
    evidence = packet.to_dict()
    assert all(_path_exists(evidence, path) for path in existing)
    assert "results.instrument" not in existing
    assert "results.validation.trade_count" not in existing
    assert catalog["overview_intent"] == OVERVIEW_INTENT_KPI
    assert "kpi_allowlist" in catalog
    assert "preferred_claim_paths" in catalog
    assert set(catalog["kpi_allowlist"]) == set(present_kpi_allowlist(evidence))
    assert "results.trade_summary.trade_count" in catalog["kpi_allowlist"]
    assert "path_catalog" in client.calls[0]["system"]


def test_di2_non_overview_ask_gets_shared_catalog_without_kpi_must_cite():
    client = _CaptureClient()
    packet = _packet()
    propose_results_reply(
        client,
        packet=packet,
        history=(),
        user_message="How many trades?",
    )
    payload = _user_payload_from_call(client.calls[0])
    catalog = payload["path_catalog"]
    assert "existing_paths" in catalog
    assert "kpi_allowlist" not in catalog
    assert "preferred_claim_paths" not in catalog
    assert "overview_intent" not in catalog
    evidence = packet.to_dict()
    assert all(_path_exists(evidence, path) for path in catalog["existing_paths"])


def test_di2_vetoed_specialist_ask_has_catalog_without_kpi_allowlist():
    class Client:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def complete_structured(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "summary": "Walk-forward evidence is not answered from the KPI slice.",
                "caveats": ["Ask using validation paths when present."],
                "claims": [],
                "followups": ["Ask about key metrics of this run."],
            }

    client = Client()
    propose_results_reply(
        client,
        packet=_packet(),
        history=(),
        user_message="Summarize the walk-forward results",
    )
    payload = _user_payload_from_call(client.calls[0])
    catalog = payload["path_catalog"]
    assert "existing_paths" in catalog
    assert "kpi_allowlist" not in catalog


def test_di2_build_prompt_path_catalog_helper_overview_vs_none():
    evidence = _packet().to_dict()
    overview = build_prompt_path_catalog(evidence, overview_intent=OVERVIEW_INTENT_RUN)
    plain = build_prompt_path_catalog(evidence, overview_intent=None)
    assert overview["overview_intent"] == OVERVIEW_INTENT_RUN
    assert overview["kpi_allowlist"]
    assert "kpi_allowlist" not in plain
    assert set(overview["existing_paths"]) >= set(overview["kpi_allowlist"])
