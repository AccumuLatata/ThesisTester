"""Direct tests for ``journal.rules`` (QI-11-01 / B-7).

QI-11 §2.3: existing coverage went through the package re-export only
(``test_journal_counterfactual.py``). This file imports the submodule path
and covers ``load_journal_rules`` plus parse/apply branches that had no
direct tests (overnight window, missing ``recon_status``, type guards).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.journal.rules import (
    JournalRule,
    apply_journal_rules,
    load_journal_rules,
    parse_journal_rule,
)
from thesistester.journal.schema import (
    JournalIngestError,
    RECON_RECONCILED,
    RULE_SPLIT_FORWARD,
    RULE_SPLIT_IN_SAMPLE,
)

UTC = "UTC"


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _trade(
    *,
    trade_id: str = "jt:t1:1",
    entry: str = "2026-05-14T14:00:03",
    exit_at: str | None = "2026-05-14T14:00:40",
    session: date = date(2026, 5, 14),
    net_ticks: float | None = 2.0,
    recon: str | None = RECON_RECONCILED,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": session,
        "entry_timestamp": _ts(entry),
        "exit_timestamp": None if exit_at is None else _ts(exit_at),
        "entry_price": 100.00,
        "exit_price": 100.50,
        "direction": "long",
        "qty": 1,
        "status": "closed",
        "net_ticks": net_ticks,
        "fee_ticks": 2.48,
        "commission_cost": 1.24,
        "day_fee_allocation": 0.0,
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def test_load_journal_rules_from_mapping_list_and_sequence():
    mapping = load_journal_rules({"name": "one", "declared_on": "2026-05-01"})
    assert len(mapping) == 1
    assert mapping[0].name == "one"

    wrapped = load_journal_rules({"rules": [{"name": "two", "declared_on": date(2026, 5, 2)}]})
    assert wrapped[0].declared_on == date(2026, 5, 2)

    sequential = load_journal_rules([{"name": "three", "declared_on": "2026-05-03"}])
    assert sequential[0].name == "three"


def test_load_journal_rules_from_yaml_and_json(tmp_path: Path):
    yaml_path = tmp_path / "rules.yaml"
    yaml_path.write_text(
        yaml.safe_dump([{"name": "yaml-rule", "declared_on": "2026-05-01"}]),
        encoding="utf-8",
    )
    loaded_yaml = load_journal_rules(yaml_path)
    assert loaded_yaml[0].name == "yaml-rule"

    json_path = tmp_path / "rules.json"
    json_path.write_text(
        json.dumps({"rules": [{"name": "json-rule", "declared_on": "2026-05-01"}]}),
        encoding="utf-8",
    )
    loaded_json = load_journal_rules(json_path)
    assert loaded_json[0].name == "json-rule"


def test_load_journal_rules_rejects_bad_path_and_type(tmp_path: Path):
    with pytest.raises(JournalIngestError, match="not found"):
        load_journal_rules(tmp_path / "missing.yaml")
    bad_suffix = tmp_path / "rules.txt"
    bad_suffix.write_text("[]", encoding="utf-8")
    with pytest.raises(JournalIngestError, match="yaml"):
        load_journal_rules(bad_suffix)
    with pytest.raises(JournalIngestError, match="path, mapping, or sequence"):
        load_journal_rules(1)  # type: ignore[arg-type]
    with pytest.raises(JournalIngestError, match="list or mapping"):
        load_journal_rules({"rules": "bad"})


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({"declared_on": "2026-05-01"}, "name is required"),
        ({"name": "x", "declared_on": "2026-05-01", "unknown": 1}, "unknown journal rule"),
        ({"name": "x", "declared_on": "2026-05-01", "max_trades_per_day": True}, "positive int"),
        ({"name": "x", "declared_on": "2026-05-01", "max_trades_per_day": 0}, "positive int"),
        (
            {"name": "x", "declared_on": "2026-05-01", "cooldown_seconds_after_loss": -1},
            "non-negative",
        ),
        ({"name": "x", "declared_on": "2026-05-01", "hard_stop_ticks": 0}, "positive number"),
        ({"name": "x", "declared_on": "2026-05-01", "trade_window_ny": "0930"}, "HH:MM-HH:MM"),
        ({"name": "x", "declared_on": "2026-05-01", "trade_window_ny": "9-10"}, "HH:MM"),
        ({"name": "x", "declared_on": "not-a-date"}, "invalid declared_on"),
        ({"name": "x"}, "declared_on is required"),
    ],
)
def test_parse_journal_rule_validation_matrix(raw, match):
    with pytest.raises((JournalIngestError, ValueError), match=match):
        parse_journal_rule(raw)


def test_parse_journal_rule_rejects_non_mapping():
    with pytest.raises(JournalIngestError, match="must be a mapping"):
        parse_journal_rule("not-a-rule")  # type: ignore[arg-type]


def test_parse_journal_rule_window_and_optional_fields():
    rule = parse_journal_rule(
        {
            "name": "windowed",
            "declared_on": datetime(2026, 5, 1, 12, 0),
            "trade_window_ny": "22:00-02:00",
            "max_trades_per_day": 3,
            "cooldown_seconds_after_loss": 30,
            "stop_after_k_consecutive_losses": 2,
            "daily_loss_stop_ticks": 10,
            "hard_stop_ticks": 8,
        }
    )
    assert rule.trade_window_ny == (time(22, 0), time(2, 0))
    assert rule.max_trades_per_day == 3
    assert rule.hard_stop_ticks == 8.0


def test_apply_journal_rules_overnight_window_keeps_late_session_only():
    """Overnight ``HH:MM-HH:MM`` is ``clock >= start or clock < end`` (end exclusive).

    Distinct ``net_ticks`` lock *which* trades are kept. A count-only assert
    would stay green if the wrap were inverted. Default ``exit_at`` is after
    each entry so the fixture is a valid closed trade.
    """
    rule = JournalRule(
        name="overnight",
        declared_on=date(2026, 5, 1),
        trade_window_ny=(time(22, 0), time(2, 0)),
    )
    start_inclusive = _trade(
        trade_id="jt:start:1",
        entry="2026-05-15T02:00:00",  # 22:00 EDT
        exit_at="2026-05-15T02:01:00",
        session=date(2026, 5, 14),
        net_ticks=7.0,
    )
    wrap_morning = _trade(
        trade_id="jt:morning:1",
        entry="2026-05-15T05:00:00",  # 01:00 EDT — wrap side
        exit_at="2026-05-15T05:01:00",
        session=date(2026, 5, 14),
        net_ticks=5.0,
    )
    midday = _trade(
        trade_id="jt:mid:1",
        entry="2026-05-14T16:00:00",  # 12:00 EDT
        exit_at="2026-05-14T16:01:00",
        session=date(2026, 5, 14),
        net_ticks=3.0,
    )
    end_exclusive = _trade(
        trade_id="jt:end:1",
        entry="2026-05-15T06:00:00",  # 02:00 EDT
        exit_at="2026-05-15T06:01:00",
        session=date(2026, 5, 14),
        net_ticks=11.0,
    )
    rows = apply_journal_rules(
        pd.DataFrame([start_inclusive, wrap_morning, midday, end_exclusive]),
        [rule],
    )
    forward = next(row for row in rows if row["split"] == RULE_SPLIT_FORWARD)
    assert forward["n_total"] == 4
    assert forward["n_kept"] == 2
    assert forward["trades_removed"] == 2
    # 7 + 5 kept; inverted wrap would keep 3+11 or drop the 01:00 side.
    assert forward["rule_net_ticks"] == pytest.approx(12.0)
    assert forward["baseline_net_ticks"] == pytest.approx(26.0)


def test_apply_journal_rules_guards_and_missing_recon_status():
    rule = parse_journal_rule({"name": "ok", "declared_on": "2026-05-01"})
    trades = pd.DataFrame([_trade()])
    with pytest.raises(JournalIngestError, match="sequence of JournalRule"):
        apply_journal_rules(trades, "not-rules")  # type: ignore[arg-type]
    with pytest.raises(JournalIngestError, match="must be a DataFrame"):
        apply_journal_rules(None, [rule])  # type: ignore[arg-type]
    with pytest.raises(JournalIngestError, match="JournalRule"):
        apply_journal_rules(trades, [{"name": "nope"}])  # type: ignore[list-item]

    missing_recon = pd.DataFrame([_trade(recon=None)])
    with pytest.raises(JournalIngestError, match="not reconciled"):
        apply_journal_rules(missing_recon, [rule])
    allowed = apply_journal_rules(missing_recon, [rule], allow_unreconciled=True)
    assert {row["split"] for row in allowed} == {RULE_SPLIT_IN_SAMPLE, RULE_SPLIT_FORWARD}


def test_apply_journal_rules_rejects_naive_and_duplicate_trade_id():
    rule = parse_journal_rule({"name": "ok", "declared_on": "2026-05-01"})
    naive = _trade()
    naive["entry_timestamp"] = pd.Timestamp("2026-05-14 14:00:03")
    with pytest.raises(JournalIngestError, match="naive timestamp"):
        apply_journal_rules(pd.DataFrame([naive]), [rule])

    first = _trade(trade_id="dup")
    second = _trade(trade_id="dup", entry="2026-05-14T14:01:00")
    with pytest.raises(JournalIngestError, match="duplicate trade_id"):
        apply_journal_rules(pd.DataFrame([first, second]), [rule])
