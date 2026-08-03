from __future__ import annotations

from pathlib import Path

import pandas as pd
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


def test_validate_experiment_rejects_subtimeframe_outside_allowed_root(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    tools = AssistantTools(data_roots=(root,))
    spec = _spec(root / "bars.csv")
    spec["dataset"]["subtimeframe_path"] = str(tmp_path / "outside.csv")

    with pytest.raises(AssistantToolError, match="outside"):
        tools.validate_experiment(spec)


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

    spec["grid"] = {
        "stop_loss_ticks_values": [1],
        "take_profit_ticks_values": [1],
        "breakeven_after_r_values": [None, 1],
        "trailing_after_r_values": [None, 1],
        "trailing_distance_ticks_values": [None, 4],
    }
    with pytest.raises(AssistantToolError, match="Grid exceeds"):
        tools.validate_experiment(spec)

    spec["grid"] = {
        "stop_loss_ticks_values": [1],
        "take_profit_ticks_values": [1],
        "max_grid_cells": 5,
    }
    with pytest.raises(AssistantToolError, match="Grid exceeds"):
        tools.validate_experiment(spec)

    spec["grid"] = {
        "stop_loss_ticks_values": [1, 2],
        "take_profit_ticks_values": [1, 2],
        "max_grid_cells": 3,
    }
    with pytest.raises(AssistantToolError, match="Grid exceeds"):
        tools.validate_experiment(spec)

    spec["grid"] = {"stop_loss_ticks_values": [1, 2], "take_profit_ticks_values": [1, 2]}
    spec["validation"] = {"n_bootstrap": 11}
    with pytest.raises(AssistantToolError, match="n_bootstrap"):
        tools.validate_experiment(spec)

    spec["validation"] = {}
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
        lambda value, base_directory, **kwargs: {
            "instrument": "ES",
            "trade_summary": {"trade_count": 2},
            "execution_origin": kwargs.get("execution_origin", "assistant"),
        },
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
    assert result["execution_origin"] == "assistant"


def test_bundle_execution_records_canonical_provenance(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    tools = AssistantTools(data_roots=(root,))
    spec = _spec(root / "bars.csv")
    monkeypatch.setattr("thesistester.assistant.tools.validate_run_spec", lambda value: None)
    monkeypatch.setattr(
        "thesistester.assistant.tools._run_experiment",
        lambda value, base_directory, **kwargs: {
            "execution_origin": kwargs.get("execution_origin", "assistant"),
            "cache_provenance": {
                "policy": kwargs.get("cache_policy", "read_write"),
                "outcome": "cold",
            },
        },
    )
    monkeypatch.setattr(
        "thesistester.assistant.tools.build_research_bundle", lambda state: b"bundle"
    )
    monkeypatch.setattr("thesistester.assistant.tools.canonical_bundle_hash", lambda bundle: "hash")
    monkeypatch.setattr(
        "thesistester.assistant.tools._state_summary",
        lambda state: {"instrument": "ES", "results": {}},
    )

    result = tools.run_experiment_to_bundle(spec, output_path=root / "run.research.zip")

    assert (root / "run.research.zip").read_bytes() == b"bundle"
    assert result["canonical_bundle_hash"] == "hash"
    assert result["execution_origin"] == "assistant"
    assert result["cache_provenance"]["outcome"] == "cold"


def test_analyze_bundle_portfolio_verifies_expected_hashes(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    left = root / "left.research.zip"
    right = root / "right.research.zip"
    left.write_bytes(b"left")
    right.write_bytes(b"right")
    tools = AssistantTools(data_roots=(root,))
    calls = []

    def fake_read(bundle_path, roots, *, expected_hash=None, require_hash=False):
        calls.append((Path(bundle_path).name, expected_hash, require_hash))
        trades = pd.DataFrame({"r_multiple": [1.0, -0.5]})
        return Path(bundle_path), b"raw", {"trades": trades}

    monkeypatch.setattr("thesistester.assistant.tools._read_verified_bundle", fake_read)
    monkeypatch.setattr(
        "thesistester.assistant.tools.run_portfolio_analysis",
        lambda setup_trades, instrument, config=None: {"count": len(setup_trades)},
    )

    with pytest.raises(AssistantToolError, match="expected_hashes"):
        tools.analyze_bundle_portfolio(
            [left, right],
            instrument="ES",
            expected_hashes=["only-one"],
        )

    result = tools.analyze_bundle_portfolio(
        [left, right],
        instrument="ES",
        expected_hashes=["hash-left", "hash-right"],
    )

    assert result == {"count": 2}
    assert calls == [
        ("left.research.zip", "hash-left", True),
        ("right.research.zip", "hash-right", True),
    ]


def test_read_verified_bundle_fails_closed_without_expected_hash(tmp_path, monkeypatch):
    from thesistester.assistant.tools import _read_verified_bundle

    root = tmp_path / "allowed"
    root.mkdir()
    bundle = root / "run.research.zip"
    bundle.write_bytes(b"bundle")
    monkeypatch.setattr("thesistester.assistant.tools.canonical_bundle_hash", lambda raw: "digest")
    monkeypatch.setattr(
        "thesistester.assistant.tools.load_research_bundle",
        lambda raw: {"session_values": {"trades": pd.DataFrame()}},
    )

    with pytest.raises(AssistantToolError, match="non-empty expected hash"):
        _read_verified_bundle(bundle, (root,), expected_hash=None, require_hash=True)
    with pytest.raises(AssistantToolError, match="non-empty expected hash"):
        _read_verified_bundle(bundle, (root,), expected_hash="   ", require_hash=True)
    with pytest.raises(AssistantToolError, match="does not match"):
        _read_verified_bundle(bundle, (root,), expected_hash="other", require_hash=True)

    path, raw, session_values = _read_verified_bundle(
        bundle, (root,), expected_hash="digest", require_hash=True
    )
    assert path == bundle
    assert raw == b"bundle"
    assert "trades" in session_values
