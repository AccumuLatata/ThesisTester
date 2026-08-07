"""SW6 tests: setup persistence, report/bundles export, assistant Focus honesty."""

from __future__ import annotations

import pytest

from thesistester.analytics.entry_window import FOCUS_HONESTY_BANNER, focus_provenance
from thesistester.assistant.explainer import build_evidence_packet
from thesistester.entry_window_policy import normalize_entry_window
from thesistester.persistence.local_store import load_setup, save_setup
from thesistester.reporting import (
    build_entry_window_metadata,
    build_markdown_report,
    build_research_artifact,
)
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    load_research_bundle,
)
from thesistester.setup import (
    build_setup_config,
    get_effective_entry_window_config,
    validate_entry_window_config,
    validate_setup_config,
)

TZ = "America/New_York"


def _base_setup(**overrides):
    config = build_setup_config(
        name="SW6 setup",
        description="entry window persistence",
        instrument="ES",
        selected_levels=["ONH", "ONL"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        direction="both",
    )
    config.update(overrides)
    return config


def test_build_setup_config_defaults_entry_window_disabled():
    config = _base_setup()
    assert "entry_window" in config
    assert config["entry_window"]["enabled"] is False
    assert config["entry_window"]["timezone"] == TZ


def test_get_effective_entry_window_missing_key_disabled():
    effective = get_effective_entry_window_config({"instrument": "ES"})
    assert effective["enabled"] is False
    assert effective["timezone"] == TZ


def test_get_effective_entry_window_enabled_rth_segments():
    raw = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m"],
    }
    effective = get_effective_entry_window_config({"instrument": "ES", "entry_window": raw})
    assert effective["enabled"] is True
    assert effective["mode"] == "rth_segments"
    assert effective["rth_segments"] == ["rth_open_30m"]
    assert effective["timezone"] == TZ


def test_validate_entry_window_rejects_empty_segments():
    errors = validate_entry_window_config(
        {"enabled": True, "mode": "rth_segments", "rth_segments": []},
        exchange_tz=TZ,
    )
    assert errors
    setup_errors = validate_setup_config(
        _base_setup(
            entry_window={
                "enabled": True,
                "mode": "rth_segments",
                "rth_segments": [],
            }
        )
    )
    assert any("Entry window" in error for error in setup_errors)


def test_save_and_load_setup_normalizes_entry_window(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))
    enabled = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_morning"],
        },
        exchange_tz=TZ,
    )
    meta = save_setup(_base_setup(entry_window=enabled))
    loaded = load_setup(meta["setup_id"])
    loaded_window = loaded["setup_config"]["entry_window"]
    assert loaded_window["enabled"] is True
    assert loaded_window["rth_segments"] == ["rth_morning"]

    # Legacy setup without the key still loads; save fills disabled default.
    legacy = _base_setup()
    legacy.pop("entry_window", None)
    legacy_meta = save_setup(legacy)
    legacy_loaded = load_setup(legacy_meta["setup_id"])
    assert legacy_loaded["setup_config"]["entry_window"]["enabled"] is False


def test_save_setup_rejects_invalid_entry_window_on_load(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))
    meta = save_setup(_base_setup())
    setup_path = store / "setups" / meta["setup_id"] / "meta.json"
    import json

    payload = json.loads(setup_path.read_text())
    payload["setup_config"]["entry_window"] = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": [],
    }
    setup_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="entry_window"):
        load_setup(meta["setup_id"])


def test_build_entry_window_metadata_and_artifact_export_focus_honesty():
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
        exchange_tz=TZ,
    )
    provenance = focus_provenance(
        window,
        trade_count_before=40,
        trade_count_after=8,
        exchange_tz=TZ,
    )
    state = {
        "focus_entry_window": window,
        "focus_provenance": provenance,
        "entry_window": {"enabled": False, "timezone": TZ},
    }
    meta = build_entry_window_metadata(state)
    assert meta["available"] is True
    assert meta["focus"]["enabled"] is True
    assert meta["focus"]["is_not_admit"] is True
    assert meta["focus"]["honesty_banner"] == FOCUS_HONESTY_BANNER
    assert any("post-hoc" in note.lower() for note in meta["honesty_notes"])

    artifact = build_research_artifact(state)
    assert "entry_window" in artifact
    assert artifact["entry_window"]["focus"]["enabled"] is True
    markdown = build_markdown_report(artifact)
    assert "Entry Window (Focus / Admit)" in markdown
    assert "not proof of deployable edge" in markdown


def test_build_entry_window_metadata_disabled_placeholders_not_available():
    """Routine all-day runs leave disabled dicts — not export 'available' evidence."""
    meta = build_entry_window_metadata(
        {
            "entry_window": {"enabled": False, "timezone": TZ},
            "grid_entry_window": {"enabled": False, "timezone": TZ},
            "entry_window_armed": False,
        }
    )
    assert meta["available"] is False
    assert meta["admit"]["enabled"] is False
    assert meta["grid"]["enabled"] is False


def test_build_entry_window_metadata_focus_label_from_provenance_fallback():
    """SW7: when focus_entry_window is missing, provenance.entry_window fills label."""
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
        exchange_tz=TZ,
    )
    meta = build_entry_window_metadata(
        {
            "focus_provenance": focus_provenance(
                window,
                trade_count_before=20,
                trade_count_after=5,
                exchange_tz=TZ,
            )
        }
    )
    assert meta["available"] is True
    assert meta["focus"]["enabled"] is True
    assert meta["focus"]["entry_window"]["rth_segments"] == ["rth_open_30m"]
    assert meta["focus"]["label"] is not None
    assert "rth_open_30m" in meta["focus"]["label"]


def test_build_entry_window_metadata_invalid_window_fail_closed():
    meta = build_entry_window_metadata(
        {
            "entry_window": {
                "enabled": True,
                "mode": "rth_segments",
                "rth_segments": [],
                "timezone": TZ,
            }
        }
    )
    assert meta["available"] is False
    assert meta["admit"]["entry_window"] is None
    assert meta["admit"]["enabled"] is None


def test_build_entry_window_metadata_invalid_focus_provenance_fail_closed():
    """Raw provenance.enabled must not mark Focus available without a valid window."""
    meta = build_entry_window_metadata(
        {
            "focus_provenance": {
                "mode": "focus",
                "entry_window": {
                    "enabled": True,
                    "mode": "rth_segments",
                    "rth_segments": [],
                    "timezone": TZ,
                },
                "trade_count_before": 10,
                "trade_count_after": 0,
            }
        }
    )
    assert meta["available"] is False
    assert meta["focus"]["enabled"] is False
    assert meta["focus"]["entry_window"] is None
    assert meta["focus"]["label"] is None


def test_incomplete_setup_entry_window_draft_fails_closed_on_save():
    """Setup Builder may attach a raw invalid draft; validate must block Save."""
    draft = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": [],
        "timezone": TZ,
    }
    # Editor scaffolding builds with disabled placeholder (no normalize crash).
    scaffold = _base_setup(entry_window={"enabled": False})
    scaffold["entry_window"] = draft
    errors = validate_setup_config(scaffold)
    assert any("Entry window" in error or "rth_segments" in error for error in errors)
    assert validate_entry_window_config(draft, exchange_tz=TZ)


def test_research_bundle_roundtrips_entry_window_provenance():
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "clock_range",
            "start_time": "09:30",
            "end_time": "10:00",
            "timezone": TZ,
        },
        exchange_tz=TZ,
    )
    provenance = focus_provenance(
        window,
        trade_count_before=20,
        trade_count_after=12,
        exchange_tz=TZ,
    )
    import pandas as pd

    trades = pd.DataFrame(
        {
            "trade_id": [1],
            "entry_timestamp": [pd.Timestamp("2026-06-02 09:45", tz=TZ)],
            "exit_timestamp": [pd.Timestamp("2026-06-02 09:50", tz=TZ)],
            "r_multiple": [1.0],
        }
    )
    equity = pd.DataFrame(
        {
            "trade_id": [1],
            "exit_timestamp": [pd.Timestamp("2026-06-02 09:50", tz=TZ)],
            "cum_r": [1.0],
        }
    )
    source = {
        "trades": trades,
        "equity_curve": equity,
        "trade_summary": {"trade_count": 1},
        "entry_window": window,
        "entry_window_armed": False,
        "focus_entry_window": window,
        "focus_provenance": provenance,
        "focused_trade_summary": {"trade_count": 12},
        "grid_entry_window": window,
        "grid_results": pd.DataFrame({"stop_loss_ticks": [8.0], "expectancy_r": [0.1]}),
        "best_grid_result": {"stop_loss_ticks": 8.0},
    }
    # Stale Admit widgets from a prior session must not survive import.
    prior_session = {
        "backtest_entry_window_enabled": False,
        "backtest_entry_window_mode": "rth_segments",
        "backtest_entry_window_rth_segments": ["rth_lunch"],
    }
    bundle_bytes = build_research_bundle(source)
    loaded = load_research_bundle(bundle_bytes)
    restored: dict = dict(prior_session)
    apply_research_bundle_to_session(loaded, restored)
    assert restored["entry_window"]["enabled"] is True
    assert restored["focus_provenance"]["trade_count_after"] == 12
    assert restored["focus_entry_window"]["mode"] == "clock_range"
    assert restored["grid_entry_window"]["enabled"] is True
    # Backtest Run builds Admit from widgets — must match imported entry_window.
    assert restored["backtest_entry_window_enabled"] is True
    assert restored["backtest_entry_window_mode"] == "clock_range"
    assert restored["backtest_entry_window_start_time"] == "09:30"
    assert restored["backtest_entry_window_end_time"] == "10:00"
    assert restored["backtest_entry_window_timezone"] == TZ


def test_assistant_focus_post_hoc_caveat_from_evidence_packet():
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
        exchange_tz=TZ,
    )
    state = {
        "focus_entry_window": window,
        "focus_provenance": focus_provenance(
            window,
            trade_count_before=30,
            trade_count_after=15,
            exchange_tz=TZ,
        ),
        "trade_summary": {"trade_count": 30},
    }
    packet = build_evidence_packet(state, provenance={"bundle_hash": "sw6"})
    assert any(caveat.code == "focus_post_hoc" for caveat in packet.caveats)
    assert packet.assumptions["entry_window"]["focus"]["enabled"] is True
    assert packet.assumptions["entry_window"]["focus"]["is_not_admit"] is True


def test_assistant_no_focus_caveat_when_focus_absent():
    packet = build_evidence_packet(
        {"trade_summary": {"trade_count": 40}},
        provenance={},
    )
    assert all(caveat.code != "focus_post_hoc" for caveat in packet.caveats)
