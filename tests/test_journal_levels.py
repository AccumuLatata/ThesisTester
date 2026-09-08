"""TJ6 level attribution + tag map — plan §3.0 / §3.6 / §5 TJ6."""

from __future__ import annotations

import importlib.util
import inspect
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.journal import (
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    attribute_journal_trades,
    load_tag_map,
    mapped_engine_tokens,
    resolve_tag,
    write_attribution_artifacts,
)
from thesistester.journal import levels as levels_mod
from thesistester.journal.schema import (
    JOURNAL_TICK_SIZE,
    LEVEL_CONTEXT_AT_LEVEL,
    LEVEL_CONTEXT_BETWEEN,
    LEVEL_CONTEXT_NO_FRAME,
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    TAG_ALIGN_ALL,
    TAG_ALIGN_NONE,
    TAG_ALIGN_PARTIAL,
    TAG_ALIGN_UNVERIFIABLE,
    TAG_CLASS_CONFIRM,
    TAG_CLASS_CONTEXT,
    TAG_CLASS_LEVEL,
    TAG_CLASS_UNMAPPED,
    JournalIngestError,
)
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import closed_level_token_set

UTC = "UTC"

# Byte-stable exact rows (TJ6 export + locked MA short forms). Additive
# Program B / closed-set keys may follow; these must not be remapped,
# renamed, or dropped.
_FROZEN_EXACT_ROWS: dict[str, dict[str, object]] = {
    "pdH": {"token": "pdHigh", "class": "level"},
    "pdLow": {"token": "pdLow", "class": "level"},
    "pdEQ": {"token": "pdEQ", "class": "level"},
    "pdH_RTH": {"token": "pRTH_High", "class": "level"},
    "pdVAL": {"token": "pdVAL", "class": "level"},
    "pwVAH": {"token": "pwVAH", "class": "level"},
    "dVWAP": {"token": "dVWAP", "class": "level"},
    "mVWAP": {"token": "mVWAP", "class": "level"},
    "4hVWAP": {"token": "VWAP_rolling_4h", "class": "level"},
    "p30VWAP": {"token": "prev30mVWAP", "class": "level"},
    "APOC": {"token": "APOC", "class": "level"},
    "pSettlement": {"token": "prevSettlement", "class": "level"},
    "dOpen": {"token": "dOpen", "class": "level"},
    "p30POC": {"token": None, "class": "unmapped"},
    "5m21EMA": {"token": "EMA_21_5min", "class": "confirm"},
    "5m50SMA": {"token": "SMA_50_5min", "class": "confirm"},
    "1m9EMA": {"token": "EMA_9_1min", "class": "confirm"},
    "1m50SMA": {"token": "SMA_50_1min", "class": "confirm"},
}

_FROZEN_CONTEXT = [
    "ITR",
    "ITR-C",
    "CTR",
    "CTR-R",
    "3c",
    "touch",
    "DeltaNode",
    "GEX2",
    "5mCOT",
    "5mSFP",
]

# Program B desk short forms. ``4hVWAP`` → ``VWAP_rolling_4h`` is the other
# short form (not a Program B core). Do not add those tokens as exact keys.
_SHORT_FORM_TO_TOKEN: dict[str, str] = {
    "pdH": "pdHigh",
    "pdH_RTH": "pRTH_High",
    "pSettlement": "prevSettlement",
    "p30VWAP": "prev30mVWAP",
}
_SHORT_FORM_ENGINE_ALIASES = frozenset(_SHORT_FORM_TO_TOKEN.values()) | {"VWAP_rolling_4h"}

# Widget-maximal extras (inventory §2.2) unioned with product defaults.
# closed_level_token_set merges DEFAULT_LEVELS_SETTINGS; these overrides
# add MA lengths + rolling windows the widget can emit.
_WIDGET_MA_LENGTHS = (9, 20, 21, 50, 100, 200)
_WIDGET_MA_TIMEFRAMES = ("1min", "5min", "30min")
_MA_TF_SHORT = {"1min": "1m", "5min": "5m", "30min": "30m"}
_WIDGET_MAXIMAL_LEVELS: dict[str, object] = {
    "sma_lengths": list(_WIDGET_MA_LENGTHS),
    "ema_lengths": list(_WIDGET_MA_LENGTHS),
    "sma_timeframes": list(_WIDGET_MA_TIMEFRAMES),
    "ema_timeframes": list(_WIDGET_MA_TIMEFRAMES),
    "vwap_windows": ["15min", "30min", "1h", "4h"],
    "poc_windows": ["30min", "1h", "4h"],
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TAG_MAP_YAML = _REPO_ROOT / "thesistester" / "journal" / "tag_map.yaml"
_PROGRAM_B_GENERATE = (
    _REPO_ROOT / "examples" / "studies" / "program_b" / "generate_program_b_yaml.py"
)


def _ma_desk_key(kind: str, length: int, timeframe: str) -> str:
    return f"{_MA_TF_SHORT[timeframe]}{length}{kind}"


def _ma_engine_token(kind: str, length: int, timeframe: str) -> str:
    return f"{kind}_{length}_{timeframe}"


def _ma_short_form_to_token() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for kind in ("SMA", "EMA"):
        for length in _WIDGET_MA_LENGTHS:
            for timeframe in _WIDGET_MA_TIMEFRAMES:
                token = _ma_engine_token(kind, length, timeframe)
                mapping[_ma_desk_key(kind, length, timeframe)] = token
    return mapping


def _coverage_token_set() -> frozenset[str]:
    """Product default closed set ∪ widget-maximal extras."""
    return frozenset(
        closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
        | closed_level_token_set(_WIDGET_MAXIMAL_LEVELS)
    )


def _program_b_all_anchors() -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "program_b_generate_for_tags", _PROGRAM_B_GENERATE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.ALL_ANCHORS)


def _exact_keys_from_yaml_text(text: str) -> list[str]:
    """Indent-2 exact keys from the raw file (PyYAML last-wins on duplicates)."""
    keys: list[str] = []
    in_exact = False
    for line in text.splitlines():
        if line.startswith("exact:"):
            in_exact = True
            continue
        if in_exact and line and not line[0].isspace() and not line.startswith("#"):
            break
        if not in_exact:
            continue
        stripped = line.split("#", 1)[0].rstrip()
        if (
            len(stripped) >= 3
            and stripped.startswith("  ")
            and not stripped.startswith("    ")
            and stripped.endswith(":")
        ):
            key = stripped[2:-1]
            if key:
                keys.append(key)
    return keys


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _trade(
    *,
    entry: str,
    price: float,
    tags: tuple[str, ...] = (),
    recon: str | None = RECON_RECONCILED,
    trade_id: str = "jt:t1:1",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": date(2026, 5, 14),
        "entry_timestamp": _ts(entry),
        "entry_price": price,
        "tags": tags,
        "direction": "long",
        "qty": 1,
        "status": "closed",
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def _trades(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _levels(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["timestamp"] = [_ts(str(value)) for value in frame["timestamp"]]
    return frame


def _frame_14() -> pd.DataFrame:
    """Hand-built 1m frame: 13:59 / 14:00 / 14:01."""
    return _levels(
        [
            {
                "timestamp": "2026-05-14T13:59:00",
                "pdHigh": 99.00,
                "pdLow": 80.00,
                "pdVAL": 98.00,
                "pwVAH": 97.00,
                "pRTH_High": 96.00,
                "dVWAP": 90.00,
                "APOC": 91.00,
            },
            {
                "timestamp": "2026-05-14T14:00:00",
                "pdHigh": 100.00,
                "pdLow": 90.00,
                "pdVAL": 99.50,
                "pwVAH": 103.00,
                "pRTH_High": 100.25,
                "dVWAP": 100.00,
                "APOC": 100.50,
            },
            {
                "timestamp": "2026-05-14T14:01:00",
                "pdHigh": 101.00,
                "pdLow": 90.00,
                "pdVAL": 110.00,
                "pwVAH": 104.00,
                "pRTH_High": 108.00,
                "dVWAP": 200.00,
                "APOC": 201.00,
            },
        ]
    )


def test_attribute_kwargs_are_keyword_only() -> None:
    params = inspect.signature(attribute_journal_trades).parameters
    for name in (
        "levels",
        "levels_settings",
        "level_tolerance_ticks",
        "tag_tolerance_ticks",
        "allow_unreconciled",
        "tick_size",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["level_tolerance_ticks"].default == DEFAULT_LEVEL_TOLERANCE_TICKS
    assert params["tag_tolerance_ticks"].default == DEFAULT_TAG_TOLERANCE_TICKS
    assert params["allow_unreconciled"].default is False


def test_journal_levels_does_not_import_engine() -> None:
    import thesistester.journal.levels as loaded
    import thesistester.journal.tags as tags_loaded

    assert "thesistester.engine" not in getattr(loaded, "__dict__", {})
    assert "compute_all_levels" not in loaded.__dict__
    assert "simulate_trades" not in loaded.__dict__
    assert "compute_all_levels" not in tags_loaded.__dict__
    assert "thesistester.levels.all" not in loaded.__dict__


def test_mapped_tokens_are_in_coverage_set() -> None:
    closed = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    coverage = _coverage_token_set()
    tokens = mapped_engine_tokens()
    assert tokens
    assert closed <= coverage
    assert sorted(closed - tokens) == []
    assert sorted(coverage - tokens) == []
    assert sorted(tokens - coverage) == []
    for token in (
        "EMA_9_1min",
        "SMA_50_5min",
        "EMA_21_5min",
        "SMA_50_1min",
        "VWAP_rolling_4h",
        "prev30mVWAP",
        "mVWAP",
        "APOC",
    ):
        assert token in closed
        assert token in tokens


def test_tag_map_is_data_not_code() -> None:
    payload = load_tag_map()
    assert isinstance(payload.get("exact"), dict)
    assert resolve_tag("pdH").token == "pdHigh"
    assert resolve_tag("pdH").tag_class == TAG_CLASS_LEVEL
    assert resolve_tag("pdH_RTH").token == "pRTH_High"
    assert resolve_tag("pdH_RTH").qualifier is None
    stripped = resolve_tag("pdVAL_retest")
    assert stripped.token == "pdVAL"
    assert stripped.qualifier == "_retest"
    assert resolve_tag("p30POC").tag_class == TAG_CLASS_UNMAPPED
    assert resolve_tag("p30POC").token is None
    assert resolve_tag("ITR").tag_class == TAG_CLASS_CONTEXT
    assert resolve_tag("ITR").token is None
    exact = payload.get("exact")
    assert isinstance(exact, dict)
    assert "touch" not in exact
    assert "3c" not in exact
    tokens = mapped_engine_tokens()
    assert "touch" not in tokens
    assert "3c" not in tokens
    for raw in ("touch", "3c"):
        mapped = resolve_tag(raw)
        assert mapped.tag_class == TAG_CLASS_CONTEXT
        assert mapped.token is None
        assert mapped.qualifier is None
    context = payload.get("context")
    assert isinstance(context, list)
    assert all(isinstance(item, str) for item in context)
    assert context == _FROZEN_CONTEXT
    stripped_touch = resolve_tag("touch_retest")
    assert stripped_touch.tag_class == TAG_CLASS_CONTEXT
    assert stripped_touch.token is None
    assert stripped_touch.qualifier == "_retest"
    stripped_3c = resolve_tag("3c_SFP")
    assert stripped_3c.tag_class == TAG_CLASS_CONTEXT
    assert stripped_3c.token is None
    assert stripped_3c.qualifier == "_SFP"
    assert resolve_tag("Touch").tag_class == TAG_CLASS_UNMAPPED
    assert resolve_tag("3C").tag_class == TAG_CLASS_UNMAPPED
    assert resolve_tag("5m21EMA").tag_class == TAG_CLASS_CONFIRM
    assert resolve_tag("5m21EMA").token == "EMA_21_5min"
    assert resolve_tag("1m50SMA").tag_class == TAG_CLASS_CONFIRM
    assert resolve_tag("1m50SMA").token == "SMA_50_1min"
    unknown = resolve_tag("notADeskTag")
    assert unknown.tag_class == TAG_CLASS_UNMAPPED
    assert unknown.raw == "notADeskTag"
    for key, expected in _FROZEN_EXACT_ROWS.items():
        assert key in exact
        row = exact[key]
        assert isinstance(row, dict)
        assert row.get("token") == expected["token"]
        assert row.get("class") == expected["class"]
    assert list(payload.get("qualifiers") or []) == ["_retest", "_SFP", "_RTH"]


def test_tag_map_covers_program_b_anchors_exactly_once() -> None:
    """Every Program B ANCHOR is reachable exactly once via one exact row."""
    payload = load_tag_map()
    exact = payload.get("exact")
    assert isinstance(exact, dict)
    raw_keys = _exact_keys_from_yaml_text(_TAG_MAP_YAML.read_text(encoding="utf-8"))
    assert len(raw_keys) == len(set(raw_keys))
    assert set(raw_keys) == set(exact)

    anchors = _program_b_all_anchors()
    assert len(anchors) == len(set(anchors)) == 50
    assert "p30POC" not in anchors
    assert not any(name.startswith("POC_rolling") for name in anchors)

    token_to_keys: dict[str, list[str]] = {}
    for key, row in exact.items():
        assert isinstance(row, dict)
        token = row.get("token")
        if row.get("class") == TAG_CLASS_UNMAPPED or not token:
            continue
        token_to_keys.setdefault(str(token), []).append(str(key))

    for token in anchors:
        keys = token_to_keys.get(token, [])
        assert len(keys) == 1, f"{token} mapped by {keys}"
        key = keys[0]
        row = exact[key]
        assert isinstance(row, dict)
        assert row.get("class") == TAG_CLASS_LEVEL
        mapped = resolve_tag(key)
        assert mapped.token == token
        assert mapped.tag_class == TAG_CLASS_LEVEL
        assert mapped.qualifier is None
        if token in _SHORT_FORM_TO_TOKEN.values():
            assert key in _SHORT_FORM_TO_TOKEN
            assert _SHORT_FORM_TO_TOKEN[key] == token
            assert token not in exact
            assert resolve_tag(token).tag_class == TAG_CLASS_UNMAPPED
        else:
            assert key == token

    colliding = sorted(_SHORT_FORM_ENGINE_ALIASES & set(exact))
    assert colliding == []

    parked = resolve_tag("p30POC")
    assert exact["p30POC"] == {"token": None, "class": "unmapped"}
    assert parked.tag_class == TAG_CLASS_UNMAPPED
    assert parked.token is None
    # Rolling POC identity keys are confirms; they must not alias p30POC.
    for poc_key in ("POC_rolling_30min", "POC_rolling_1h", "POC_rolling_4h"):
        poc = resolve_tag(poc_key)
        assert poc.token == poc_key
        assert poc.tag_class == TAG_CLASS_CONFIRM
        assert exact[poc_key] == {"token": poc_key, "class": "confirm"}
    assert not any(
        str(row.get("token") or "").startswith("POC_rolling")
        for key, row in exact.items()
        if isinstance(row, dict) and key == "p30POC"
    )

    rth_vwap = resolve_tag("dVWAP_RTH")
    assert rth_vwap.token == "dVWAP_RTH"
    assert rth_vwap.tag_class == TAG_CLASS_LEVEL
    assert rth_vwap.qualifier is None
    without_rth = {key: row for key, row in exact.items() if key != "dVWAP_RTH"}
    stripped = resolve_tag("dVWAP_RTH", tag_map={**payload, "exact": without_rth})
    assert stripped.token == "dVWAP"
    assert stripped.tag_class == TAG_CLASS_LEVEL
    assert stripped.qualifier == "_RTH"


def test_tag_map_covers_closed_and_widget_tokens_exactly_once() -> None:
    """Every product/widget-closed token is reachable via exactly one exact row."""
    payload = load_tag_map()
    exact = payload.get("exact")
    assert isinstance(exact, dict)
    raw_keys = _exact_keys_from_yaml_text(_TAG_MAP_YAML.read_text(encoding="utf-8"))
    assert len(raw_keys) == len(set(raw_keys))
    assert set(raw_keys) == set(exact)

    coverage = _coverage_token_set()
    default_closed = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    assert default_closed <= coverage
    assert "SMA_50_15min" not in coverage
    assert "Pivot_1min_High" not in coverage
    assert "wVWAP_RTH" not in coverage
    assert "mVWAP_RTH" not in coverage
    assert "RTH_High" not in coverage
    assert "RTH_Low" not in coverage

    token_to_keys: dict[str, list[str]] = {}
    for key, row in exact.items():
        assert isinstance(row, dict)
        token = row.get("token")
        if row.get("class") == TAG_CLASS_UNMAPPED or not token:
            continue
        token_to_keys.setdefault(str(token), []).append(str(key))

    assert set(token_to_keys) == set(coverage)
    ma_short = _ma_short_form_to_token()
    short_forms = {**_SHORT_FORM_TO_TOKEN, "4hVWAP": "VWAP_rolling_4h", **ma_short}

    for token in sorted(coverage):
        keys = token_to_keys.get(token, [])
        assert len(keys) == 1, f"{token} mapped by {keys}"
        key = keys[0]
        row = exact[key]
        assert isinstance(row, dict)
        mapped = resolve_tag(key)
        assert mapped.token == token
        assert mapped.qualifier is None
        if token.startswith(("SMA_", "EMA_")):
            assert row.get("class") == TAG_CLASS_CONFIRM
            assert mapped.tag_class == TAG_CLASS_CONFIRM
            assert key == next(desk for desk, engine in ma_short.items() if engine == token)
            assert token not in exact
            assert resolve_tag(token).tag_class == TAG_CLASS_UNMAPPED
        elif token in _SHORT_FORM_TO_TOKEN.values() or token == "VWAP_rolling_4h":
            assert row.get("class") == TAG_CLASS_LEVEL
            assert mapped.tag_class == TAG_CLASS_LEVEL
            assert token not in exact
            assert resolve_tag(token).tag_class == TAG_CLASS_UNMAPPED
        elif token.startswith(("Pivot_", "VWAP_rolling_", "POC_rolling_")):
            assert key == token
            assert row.get("class") == TAG_CLASS_CONFIRM
            assert mapped.tag_class == TAG_CLASS_CONFIRM
        else:
            assert key == token
            assert row.get("class") == TAG_CLASS_LEVEL
            assert mapped.tag_class == TAG_CLASS_LEVEL

    colliding = sorted(set(short_forms.values()) & set(exact))
    assert colliding == []
    assert resolve_tag("1m50SMA").token == "SMA_50_1min"
    assert resolve_tag("30m200SMA").token == "SMA_200_30min"
    assert resolve_tag("5m9EMA").token == "EMA_9_5min"
    assert resolve_tag("Pivot_1m_High").token == "Pivot_1m_High"
    assert resolve_tag("VWAP_rolling_30min").token == "VWAP_rolling_30min"
    assert resolve_tag("POC_rolling_30min").token == "POC_rolling_30min"


def test_at_level_between_levels_and_no_frame() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(entry="2026-05-14T14:00:24", price=100.00, trade_id="jt:at:1"),
        _trade(entry="2026-05-14T14:00:24", price=110.00, trade_id="jt:between:1"),
        _trade(entry="2026-05-14T15:00:24", price=100.00, trade_id="jt:none:1"),
    )
    out = attribute_journal_trades(trades, levels=frame)
    at_row = out.loc[out["trade_id"] == "jt:at:1"].iloc[0]
    between = out.loc[out["trade_id"] == "jt:between:1"].iloc[0]
    missing = out.loc[out["trade_id"] == "jt:none:1"].iloc[0]
    assert at_row["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    assert "pdHigh" in list(at_row["levels_within_tolerance"])
    assert at_row["nearest_level_token"] == "pdHigh"
    assert at_row["nearest_level_distance_ticks"] == pytest.approx(0.0)
    assert between["level_context"] == LEVEL_CONTEXT_BETWEEN
    assert list(between["levels_within_tolerance"]) == []
    assert between["nearest_level_token"] == "pwVAH"
    assert between["nearest_level_distance_ticks"] == pytest.approx(28.0)
    assert missing["level_context"] == LEVEL_CONTEXT_NO_FRAME
    assert list(missing["levels_within_tolerance"]) == []
    assert missing["nearest_level_token"] is None


def test_developing_token_uses_previous_completed_minute() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:01:10", price=100.00))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    nearby = list(row["levels_within_tolerance"])
    assert "dVWAP" in nearby
    assert "APOC" in nearby
    assert row["nearest_level_token"] == "dVWAP"
    assert row["nearest_level_distance_ticks"] == pytest.approx(0.0)
    # Current-minute developing values are 200 / 201 — using them would miss.
    assert 200.0 not in {abs(float(row["nearest_level_distance_ticks"]))}


def test_exact_minute_entry_uses_bar_closed_strictly_before() -> None:
    """Fill at 14:01:00 must not read the 14:00 close (equals entry)."""
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:01:00", price=90.00, tags=("dVWAP",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    # Expected previous open is 13:59 (dVWAP=90), not 14:00 (dVWAP=100).
    assert row["nearest_level_token"] == "dVWAP"
    assert row["nearest_level_distance_ticks"] == pytest.approx(0.0)
    assert row["tag_verifications"][0]["tag_level_missing"] is False


def test_frozen_token_uses_containing_minute() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:01:10", price=101.00))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert row["nearest_level_token"] == "pdHigh"
    assert row["nearest_level_distance_ticks"] == pytest.approx(0.0)


def test_gapped_previous_minute_omits_developing_token() -> None:
    """A stale earlier row is not 'the previous completed minute' (session/gap)."""
    frame = _levels(
        [
            {
                "timestamp": "2026-05-14T13:59:00",
                "pdHigh": 99.00,
                "dVWAP": 90.00,
                "APOC": 91.00,
            },
            {
                "timestamp": "2026-05-14T14:01:00",
                "pdHigh": 101.00,
                "dVWAP": 200.00,
                "APOC": 201.00,
            },
        ]
    )
    trades = _trades(_trade(entry="2026-05-14T14:01:10", price=101.00, tags=("dVWAP", "APOC")))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    nearby = list(row["levels_within_tolerance"])
    assert "dVWAP" not in nearby
    assert "APOC" not in nearby
    assert row["nearest_level_token"] == "pdHigh"
    assert all(verify["tag_level_missing"] is True for verify in row["tag_verifications"])


def test_missing_previous_developing_bar_omits_token() -> None:
    frame = _levels(
        [
            {
                "timestamp": "2026-05-14T14:00:00",
                "pdHigh": 100.00,
                "dVWAP": 100.00,
            }
        ]
    )
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("dVWAP",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert "dVWAP" not in list(row["levels_within_tolerance"])
    assert row["nearest_level_token"] == "pdHigh"
    verify = row["tag_verifications"][0]
    assert verify["token"] == "dVWAP"
    assert verify["tag_level_missing"] is True
    assert row["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE


def test_unmapped_tags_are_counted_never_dropped() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "p30POC", "ITR", "touch", "3c", "mystery"),
        )
    )
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert list(row["unmapped_tags"]) == ["p30POC", "mystery"]
    assert "ITR" not in list(row["unmapped_tags"])
    assert "touch" not in list(row["unmapped_tags"])
    assert "3c" not in list(row["unmapped_tags"])
    assert row["tag_alignment"] == TAG_ALIGN_ALL
    assert resolve_tag("pdH").raw == "pdH"


def test_alignment_classes_and_intent_mismatch() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "pdH_RTH"),
            trade_id="jt:all:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "pdLow"),
            trade_id="jt:partial:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdLow",),
            trade_id="jt:none:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdVAL",),
            trade_id="jt:missing:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("ITR", "5m21EMA"),
            trade_id="jt:unver:1",
        ),
    )
    slim = frame.drop(columns=["pdVAL"])
    out = attribute_journal_trades(trades, levels=slim)
    all_row = out.loc[out["trade_id"] == "jt:all:1"].iloc[0]
    assert all_row["tag_alignment"] == TAG_ALIGN_ALL
    assert all_row["intent_mismatch"] is False
    partial = out.loc[out["trade_id"] == "jt:partial:1"].iloc[0]
    assert partial["tag_alignment"] == TAG_ALIGN_PARTIAL
    assert partial["intent_mismatch"] is False
    none_row = out.loc[out["trade_id"] == "jt:none:1"].iloc[0]
    assert none_row["tag_alignment"] == TAG_ALIGN_NONE
    assert none_row["intent_mismatch"] is True
    missing = out.loc[out["trade_id"] == "jt:missing:1"].iloc[0]
    assert missing["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert missing["tag_verifications"][0]["tag_level_missing"] is True
    assert missing["intent_mismatch"] is True
    unver = out.loc[out["trade_id"] == "jt:unver:1"].iloc[0]
    assert unver["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert unver["intent_mismatch"] is False


def test_tagged_a_but_at_b_when_named_level_is_far() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("pdVAL",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    # pdVAL at 99.50 is 2 ticks — aligned at default 10, so tighten tag tolerance.
    tight = attribute_journal_trades(
        trades, levels=frame, tag_tolerance_ticks=1.0, level_tolerance_ticks=10.0
    )
    row = tight.iloc[0]
    assert row["tag_alignment"] == TAG_ALIGN_NONE
    assert row["intent_mismatch"] is True
    assert "pdHigh" in list(row["levels_within_tolerance"])


def test_confirm_and_context_tags_do_not_drive_alignment() -> None:
    frame = _frame_14()
    trades = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("ITR-C", "5m50SMA"),
            trade_id="jt:confirm-ctx:1",
        ),
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("touch", "3c"),
            trade_id="jt:entry-style:1",
        ),
    )
    out = attribute_journal_trades(trades, levels=frame)
    row = out.loc[out["trade_id"] == "jt:confirm-ctx:1"].iloc[0]
    assert row["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert row["tag_verifications"] == []
    assert list(row["unmapped_tags"]) == []
    entry = out.loc[out["trade_id"] == "jt:entry-style:1"].iloc[0]
    assert entry["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert entry["tag_verifications"] == []
    assert list(entry["unmapped_tags"]) == []
    assert entry["intent_mismatch"] is False
    assert entry["level_context"] == LEVEL_CONTEXT_AT_LEVEL


def test_refuses_unreconciled_days_by_default() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, recon=RECON_AMP_MISSING))
    with pytest.raises(JournalIngestError, match="not reconciled"):
        attribute_journal_trades(trades, levels=frame)
    out = attribute_journal_trades(trades, levels=frame, allow_unreconciled=True)
    assert out.iloc[0]["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    missing_col = trades.drop(columns=["recon_status"])
    with pytest.raises(JournalIngestError, match="not reconciled"):
        attribute_journal_trades(missing_col, levels=frame)


def test_positional_levels_argument_is_rejected() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    with pytest.raises(TypeError):
        attribute_journal_trades(trades, frame)  # type: ignore[misc]


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    trades_path = tmp_path / "journal_trades.parquet"
    levels_path = tmp_path / "levels.parquet"
    raw = _trades(
        _trade(
            entry="2026-05-14T14:00:24",
            price=100.00,
            tags=("pdH", "p30POC", "mystery"),
        )
    )
    raw["tags"] = raw["tags"].map(list)
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    _frame_14().to_parquet(levels_path, index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "attribute",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--output-dir",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads((out / "attribution.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["unmapped_tag_counts"] == {"mystery": 1, "p30POC": 1}
    assert payload["unmapped_tag_total"] == 2
    frame = pd.read_parquet(out / "journal_attribution.parquet")
    assert frame.iloc[0]["level_context"] == LEVEL_CONTEXT_AT_LEVEL
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "attribute",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "attribution.json").exists()


def test_write_helpers_are_keyword_only_on_files() -> None:
    params = inspect.signature(levels_mod.attribute_files).parameters
    for name in (
        "trades",
        "levels",
        "output_dir",
        "levels_settings",
        "level_tolerance_ticks",
        "tag_tolerance_ticks",
        "allow_unreconciled",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_tick_size_matches_journal_lock() -> None:
    assert JOURNAL_TICK_SIZE == 0.25
    frame = _levels([{"timestamp": "2026-05-14T14:00:00", "pdHigh": 100.25}])
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    out = attribute_journal_trades(trades, levels=frame)
    assert out.iloc[0]["nearest_level_distance_ticks"] == pytest.approx(-1.0)


def test_write_attribution_round_trip(tmp_path: Path) -> None:
    trades = attribute_journal_trades(
        _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("pdH",))),
        levels=_frame_14(),
    )
    paths = write_attribution_artifacts(tmp_path / "out", trades)
    assert paths["journal_attribution.parquet"].is_file()
    loaded = pd.read_parquet(paths["journal_attribution.parquet"])
    assert loaded.iloc[0]["nearest_level_token"] == "pdHigh"


def test_cost_columns_stay_object_none_after_attribution() -> None:
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    trades["commission_cost"] = pd.Series([None], dtype="object")
    trades["day_fee_allocation"] = pd.Series([None], dtype="object")
    trades["fee_ticks"] = pd.Series([None], dtype="object")
    out = attribute_journal_trades(trades, levels=_frame_14())
    assert out.iloc[0]["commission_cost"] is None
    assert out.iloc[0]["day_fee_allocation"] is None
    assert out.iloc[0]["fee_ticks"] is None
    assert out["commission_cost"].dtype == object


def test_non_finite_tolerance_and_non_positive_price_fail_closed() -> None:
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    with pytest.raises(JournalIngestError, match="level_tolerance_ticks"):
        attribute_journal_trades(trades, levels=frame, level_tolerance_ticks=float("nan"))
    with pytest.raises(JournalIngestError, match="tag_tolerance_ticks"):
        attribute_journal_trades(trades, levels=frame, tag_tolerance_ticks=float("inf"))
    zero = _trades(_trade(entry="2026-05-14T14:00:24", price=0.0))
    with pytest.raises(JournalIngestError, match="non-positive"):
        attribute_journal_trades(zero, levels=frame)
    negative = _trades(_trade(entry="2026-05-14T14:00:24", price=-1.0))
    with pytest.raises(JournalIngestError, match="non-positive"):
        attribute_journal_trades(negative, levels=frame)


def test_confirm_qualifier_strip_does_not_drive_alignment() -> None:
    stripped = resolve_tag("5m21EMA_retest")
    assert stripped.token == "EMA_21_5min"
    assert stripped.tag_class == TAG_CLASS_CONFIRM
    assert stripped.qualifier == "_retest"
    frame = _frame_14()
    trades = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00, tags=("5m21EMA_retest",)))
    out = attribute_journal_trades(trades, levels=frame)
    row = out.iloc[0]
    assert row["tag_alignment"] == TAG_ALIGN_UNVERIFIABLE
    assert row["tag_verifications"] == []
    assert list(row["unmapped_tags"]) == []


def test_corrupt_levels_settings_fail_closed(tmp_path: Path) -> None:
    trades_path = tmp_path / "journal_trades.parquet"
    levels_path = tmp_path / "levels.parquet"
    raw = _trades(_trade(entry="2026-05-14T14:00:24", price=100.00))
    raw["tags"] = raw["tags"].map(list)
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    _frame_14().to_parquet(levels_path, index=False)
    bad = tmp_path / "settings.yaml"
    bad.write_text("not: [valid\n", encoding="utf-8")
    code = cli_main(
        [
            "journal",
            "attribute",
            "--trades",
            str(trades_path),
            "--levels",
            str(levels_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--levels-settings",
            str(bad),
        ]
    )
    assert code == 2
