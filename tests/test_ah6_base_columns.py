"""AH6 probes: reject BASE_COLUMNS in validate_setup_config (H3).

P1 fails when ``close`` is headless-legal and ``api.build_setup`` /
``generate_signals`` can emit ``close|ONH`` zones. P2 locks hit-column
rejection. P3 locks a valid ONH-only setup. See
``docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md`` §6.6.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.api import build_setup, generate_signals
from thesistester.setup import build_setup_config, validate_setup_config

_HIT_M1 = "prev30mVWAP_hit_m1"
_HIT_ERROR_PREFIX = (
    "Selected levels include diagnostic (non-level) columns that cannot be used for confluence:"
)


def _cluster(**overrides) -> dict:
    otf_filter = overrides.pop("otf_filter", None)
    config = build_setup_config(
        name="AH6 probe",
        description="test",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=1,
        max_confluences=2,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        direction="both",
        trigger_params={},
        otf_filter=otf_filter,
    )
    config.update(overrides)
    return config


def _levels_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=3, freq="1min"),
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.5, 100.5, 100.5],
            "volume": [1000, 1000, 1000],
            "ONH": [100.5, 100.5, 100.5],
        }
    )


def test_ah6_p1_close_onh_fails_closed():
    """AH6-P1: ``selected_levels=['close','ONH']`` is rejected; no close|ONH zones."""
    config = _cluster(selected_levels=["close", "ONH"])
    errors = validate_setup_config(config)
    assert errors
    assert any("close" in message for message in errors)
    joined = " ".join(errors)
    assert "close" in joined
    assert "cannot be used for confluence" in joined

    with pytest.raises(ValueError, match="close") as built:
        build_setup(config)
    assert "close|ONH" not in str(built.value)

    with pytest.raises(ValueError, match="close") as generated:
        generate_signals(_levels_frame(), config)
    assert "close|ONH" not in str(generated.value)


def test_ah6_p2_hit_columns_still_rejected():
    """AH6-P2: diagnostic hit columns stay rejected with the same error style."""
    errors = validate_setup_config(_cluster(selected_levels=["prev30mVWAP", _HIT_M1]))
    assert any("diagnostic" in message.lower() for message in errors)
    assert any(_HIT_ERROR_PREFIX in message and _HIT_M1 in message for message in errors)
    assert not any("OHLCV/base" in message for message in errors)


def test_ah6_p3_onh_only_setup_unchanged():
    """AH6-P3: valid ONH-only setup still returns an empty error list."""
    config = _cluster(selected_levels=["ONH"])
    assert validate_setup_config(config) == []
    setup = build_setup(config)
    assert setup["selected_levels"] == ["ONH"]
    result = generate_signals(_levels_frame(), setup)
    zones = result["confluence_zones"]
    if not zones.empty and "level_names" in zones.columns:
        assert not any("close" in str(name) for name in zones["level_names"])
