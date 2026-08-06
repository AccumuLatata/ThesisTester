"""VA-4 deterministic VoiceIntentRouter tests."""

from __future__ import annotations

from thesistester.assistant.voice.intent import VoiceIntentRouter


def test_overview_and_default_unrecognized():
    router = VoiceIntentRouter()
    overview = router.route("Give me an overview of this run")
    assert overview.tool_name == "get_run_overview"
    assert overview.recognized is True
    assert overview.arguments == {}

    unknown = router.route("please invent alpha and buy the open")
    assert unknown.tool_name == "get_run_overview"
    assert unknown.recognized is False
    assert unknown.spoken_note is not None
    assert "text Discuss" in unknown.spoken_note or "realtime" in unknown.spoken_note


def test_caveats_and_metric_aliases():
    router = VoiceIntentRouter()
    caveats = router.route("What are the honesty caveats?")
    assert caveats.tool_name == "list_caveats"

    win = router.route("What was the win rate?")
    assert win.tool_name == "get_metric"
    assert win.arguments["path"] == "results.trade_summary.win_rate"

    expectancy = router.route("Tell me expectancy")
    assert expectancy.tool_name == "get_metric"
    assert expectancy.arguments["path"] == "results.trade_summary.expectancy_r"

    trades = router.route("How many trades / sample size?")
    assert trades.tool_name == "get_metric"
    assert trades.arguments["path"] == "results.trade_count"


def test_explicit_path_and_compare_with_run_id():
    router = VoiceIntentRouter()
    path = router.route("get results.trade_summary.profit_factor please")
    assert path.tool_name == "get_metric"
    assert path.arguments["path"] == "results.trade_summary.profit_factor"

    other = "run_" + ("ab" * 16)
    compare = router.route(f"Compare this with {other}")
    assert compare.tool_name == "compare_two_runs"
    assert compare.arguments["other_run_id"] == other

    compare_missing = router.route("compare versus the other candidate")
    # Without a run_… id, compare hint alone does not select compare_two_runs.
    assert compare_missing.tool_name == "get_run_overview"
    assert compare_missing.recognized is False


def test_empty_text_is_unrecognized_overview():
    router = VoiceIntentRouter()
    empty = router.route("   ")
    assert empty.tool_name == "get_run_overview"
    assert empty.recognized is False


def test_total_r_alias_does_not_match_total_risk():
    router = VoiceIntentRouter()
    total_r = router.route("what is total r on this run?")
    assert total_r.tool_name == "get_metric"
    assert total_r.arguments["path"] == "results.trade_summary.total_r"

    risk = router.route("what is total risk on this setup?")
    assert risk.tool_name == "get_run_overview"
    assert risk.recognized is False
