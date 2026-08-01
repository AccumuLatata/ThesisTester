from __future__ import annotations

import pytest

from thesistester.assistant.tools import AssistantToolError, AssistantTools, ToolLimits


def _spec(path):
    return {
        "name": "assistant-test",
        "dataset": {"path": str(path), "instrument": "ES"},
        "levels": {},
        "setup": {
            "name": "test",
            "description": "",
            "instrument": "ES",
            "selected_levels": ["dOpen"],
            "tolerance_ticks": 0,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "direction": "both",
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": {},
            "otf_filter": None,
        },
    }


def test_validate_experiment_rejects_paths_outside_allowed_root(tmp_path):
    tools = AssistantTools(data_roots=(tmp_path / "allowed",))

    with pytest.raises(AssistantToolError, match="outside"):
        tools.validate_experiment(_spec(tmp_path / "outside.csv"))


def test_validate_experiment_applies_grid_and_validation_limits(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    tools = AssistantTools(
        data_roots=(root,), limits=ToolLimits(max_grid_cells=4, max_simulations=10)
    )
    spec = _spec(root / "bars.csv")
    spec["grid"] = {"stop_loss_ticks_values": [1, 2, 3], "take_profit_ticks_values": [1, 2]}

    with pytest.raises(AssistantToolError, match="Grid exceeds"):
        tools.validate_experiment(spec)

    spec["grid"] = {"stop_loss_ticks_values": [1, 2], "take_profit_ticks_values": [1, 2]}
    spec["validation"] = {"n_bootstrap": 11}
    with pytest.raises(AssistantToolError, match="n_bootstrap"):
        tools.validate_experiment(spec)


def test_run_experiment_uses_public_facade_and_returns_compact_summary(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    tools = AssistantTools(data_roots=(root,))
    spec = _spec(root / "bars.csv")

    monkeypatch.setattr("thesistester.assistant.tools.validate_run_spec", lambda value: None)
    monkeypatch.setattr(
        "thesistester.assistant.tools._run_experiment",
        lambda value, base_directory: {"instrument": "ES", "trade_summary": {"trade_count": 2}},
    )
    monkeypatch.setattr(
        "thesistester.assistant.tools.build_research_artifact",
        lambda state: {
            "configuration": {"instrument": state["instrument"]},
            "results": {
                "walk_forward_warnings": [],
                "backtest_intrabar_diagnostic": None,
                "trade_summary": state["trade_summary"],
            },
        },
    )

    result = tools.run_experiment(spec)

    assert result["summary"]["instrument"] == "ES"
    assert result["summary"]["results"]["trade_summary"]["trade_count"] == 2
