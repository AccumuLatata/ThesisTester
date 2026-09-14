"""B-13 / QI-10-05 classic AppTest smoke (MG-26).

QI-10 §3.6: feasible for smoke + seeded-state, not empty click-through.
Named session keys only — never iterate the session mapping. Per-page first
render must stay under 1 s (QI-10 §3.7 / §10 probes).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.serial

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_BUDGET_S = 1.0
HOME = "app.py"
DATA_PAGE = "pages/1_Data.py"
BACKTEST_PAGE = "pages/7_Backtest.py"


def _ensure_repo_root_on_path() -> None:
    """Backtest does not self-bootstrap; Data does (QI-10 §3.6 rule 5)."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _has_named_key(app: AppTest, key: str) -> bool:
    """Membership on a named key. Do not iterate the session mapping."""
    return key in app.session_state


def _run_page(relpath: str) -> tuple[AppTest, float]:
    _ensure_repo_root_on_path()
    started = time.perf_counter()
    app = AppTest.from_file(str(REPO_ROOT / relpath), default_timeout=30)
    app.run()
    return app, time.perf_counter() - started


def _tiny_levels() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-02 14:30", tz="America/New_York")],
        name="timestamp",
    )
    return pd.DataFrame(
        {
            "open": [5000.0],
            "high": [5001.0],
            "low": [4999.0],
            "close": [5000.25],
            "volume": [10],
        },
        index=index,
    )


def _tiny_signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [0],
            "direction": ["long"],
            "timestamp": [pd.Timestamp("2024-01-02 14:30", tz="America/New_York")],
        }
    )


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    return tmp_path


def test_home_smoke_empty_state(isolated_store) -> None:
    """QI-10 §3.1 / §10: title + empty info; no ``data`` key."""
    app, elapsed = _run_page(HOME)
    assert not app.exception, app.exception
    assert elapsed < RENDER_BUDGET_S, elapsed
    titles = [item.value for item in app.title]
    assert any("ThesisTester" in str(value) for value in titles)
    infos = [item.value for item in app.info]
    assert any("No data loaded yet" in str(text) for text in infos)
    assert _has_named_key(app, "data") is False


def test_data_smoke_sample_auto_load(isolated_store) -> None:
    """Empty session Sample auto-load (12 bars) — QI-10 §3.1 / §10."""
    app, elapsed = _run_page(DATA_PAGE)
    assert not app.exception, app.exception
    assert elapsed < RENDER_BUDGET_S, elapsed
    successes = [item.value for item in app.success]
    assert any("Loaded" in str(text) and "12" in str(text) for text in successes)
    assert _has_named_key(app, "data") is True
    assert _has_named_key(app, "dataset_id") is True
    assert _has_named_key(app, "instrument") is True
    assert _has_named_key(app, "display_timezone") is True
    assert _has_named_key(app, "exchange_timezone") is True
    data = app.session_state["data"]
    assert len(data) == 12


def test_backtest_smoke_warning_without_signals(isolated_store) -> None:
    """Empty Backtest: warning + ``st.stop`` before run widgets (QI-10 §3.1)."""
    app, elapsed = _run_page(BACKTEST_PAGE)
    assert not app.exception, app.exception
    assert elapsed < RENDER_BUDGET_S, elapsed
    titles = [item.value for item in app.title]
    assert any("Backtest" in str(value) for value in titles)
    warnings = [item.value for item in app.warning]
    assert any("No signals found" in str(text) for text in warnings)
    assert _has_named_key(app, "signals") is False
    assert _has_named_key(app, "classic_nav_prefill") is True
    assert app.session_state["classic_nav_prefill"] is None
    main_buttons = [item.label for item in app.button if item.label]
    assert "▶ Run backtest" not in main_buttons
    assert not any("Stop loss" in str(item.label) for item in app.number_input)


def test_backtest_seeded_signals_levels_instantiates_run_widgets(isolated_store) -> None:
    """Seed ``signals`` + ``levels`` before interaction (QI-10 §3.6 rule 4)."""
    _ensure_repo_root_on_path()
    started = time.perf_counter()
    app = AppTest.from_file(str(REPO_ROOT / BACKTEST_PAGE), default_timeout=30)
    app.session_state["levels"] = _tiny_levels()
    app.session_state["signals"] = _tiny_signals()
    app.session_state["instrument"] = "ES"
    app.run()
    elapsed = time.perf_counter() - started
    assert not app.exception, app.exception
    assert elapsed < RENDER_BUDGET_S, elapsed
    assert _has_named_key(app, "signals") is True
    assert _has_named_key(app, "levels") is True
    assert any(item.label == "Stop loss (ticks)" for item in app.number_input)
    assert any(item.label == "▶ Run backtest" for item in app.button)
    infos = [item.value for item in app.info]
    assert any("Run backtest" in str(text) for text in infos)
