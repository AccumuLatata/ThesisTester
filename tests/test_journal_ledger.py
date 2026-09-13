"""Direct tests for ``journal.ledger`` (QI-11-01 / B-7).

QI-11 §2.3: ``build_forward_ledger`` was reached via the package re-export
in ``test_journal_match.py``; ``load_live_declarations`` had no unit tests.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.journal.ledger import build_forward_ledger, load_live_declarations
from thesistester.journal.schema import (
    JournalIngestError,
    MATCH_DISCRETIONARY_ONLY,
    MATCH_EXECUTED_CELL,
    MATCH_NEAR_LEVEL,
    MATCH_PRODUCT_MISMATCH,
    MATCH_SIDE_JOURNAL,
    MATCH_SIDE_SYSTEMATIC,
    MATCH_SYSTEMATIC_UNFILLED,
)


def test_load_live_declarations_none_is_empty():
    assert load_live_declarations(None) == {}


def test_load_live_declarations_yaml_json_and_shapes(tmp_path: Path):
    yaml_path = tmp_path / "live.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "cells": [
                    {"run_name": "cell-a", "live_since": "2026-05-01"},
                    {"cell_id": "cell-b", "live_since": date(2026, 5, 2)},
                ]
            }
        ),
        encoding="utf-8",
    )
    loaded = load_live_declarations(yaml_path)
    assert loaded == {"cell-a": date(2026, 5, 1), "cell-b": date(2026, 5, 2)}

    single = tmp_path / "single.json"
    single.write_text(
        json.dumps({"run_name": "solo", "live_since": "2026-06-01"}),
        encoding="utf-8",
    )
    assert load_live_declarations(single) == {"solo": date(2026, 6, 1)}

    listed = tmp_path / "list.yaml"
    listed.write_text(
        yaml.safe_dump([{"run_name": "listed", "live_since": datetime(2026, 7, 1)}]),
        encoding="utf-8",
    )
    assert load_live_declarations(listed)["listed"] == date(2026, 7, 1)


def test_load_live_declarations_rejects_bad_payloads(tmp_path: Path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(JournalIngestError, match="not found"):
        load_live_declarations(missing)

    txt = tmp_path / "live.txt"
    txt.write_text("[]", encoding="utf-8")
    with pytest.raises(JournalIngestError, match="yaml"):
        load_live_declarations(txt)

    bad_map = tmp_path / "bad.yaml"
    bad_map.write_text(yaml.safe_dump({"foo": 1}), encoding="utf-8")
    with pytest.raises(JournalIngestError, match="list of cells"):
        load_live_declarations(bad_map)

    no_name = tmp_path / "noname.yaml"
    no_name.write_text(yaml.safe_dump([{"live_since": "2026-05-01"}]), encoding="utf-8")
    with pytest.raises(JournalIngestError, match="run_name is required"):
        load_live_declarations(no_name)

    no_since = tmp_path / "nosince.yaml"
    no_since.write_text(yaml.safe_dump([{"run_name": "x"}]), encoding="utf-8")
    with pytest.raises(JournalIngestError, match="missing live_since"):
        load_live_declarations(no_since)

    not_map = tmp_path / "notmap.yaml"
    not_map.write_text(yaml.safe_dump(["just-a-string"]), encoding="utf-8")
    with pytest.raises(JournalIngestError, match="must be a mapping"):
        load_live_declarations(not_map)


def test_build_forward_ledger_empty_and_live_since_filter():
    assert build_forward_ledger(None, live_since=None, cell_expectancy_ticks=1.0) == []
    assert build_forward_ledger(pd.DataFrame(), live_since=None, cell_expectancy_ticks=1.0) == []

    matches = pd.DataFrame(
        [
            {
                "session_date": date(2026, 5, 1),
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 2.0,
            }
        ]
    )
    assert (
        build_forward_ledger(matches, live_since=date(2026, 5, 2), cell_expectancy_ticks=1.0) == []
    )


def test_build_forward_ledger_counts_adherence_and_skips_null_live_net():
    matches = pd.DataFrame(
        [
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 4.0,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 8.0,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": None,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_SYSTEMATIC_UNFILLED,
                "side": MATCH_SIDE_SYSTEMATIC,
                "net_ticks": None,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_NEAR_LEVEL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 1.0,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_DISCRETIONARY_ONLY,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 1.0,
            },
            {
                "session_date": "2026-05-14",
                "match_class": MATCH_PRODUCT_MISMATCH,
                "side": MATCH_SIDE_SYSTEMATIC,
                "net_ticks": None,
            },
            {
                "session_date": "2026-05-14",
                "match_class": "unknown_class",
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 9.0,
            },
            {
                "session_date": date(2026, 5, 15),
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 6.0,
            },
        ]
    )
    rows = build_forward_ledger(matches, live_since=None, cell_expectancy_ticks=3.5)
    assert len(rows) == 2
    first, second = rows
    assert first["session_date"] == "2026-05-14"
    assert first["executed_cell"] == 3
    assert first["systematic_unfilled"] == 1
    assert first["near_level"] == 1
    assert first["discretionary_only"] == 1
    assert first["product_mismatch"] == 1
    assert first["systematic_signals"] == 5
    assert first["adherence"] == pytest.approx(3 / 4)
    # Two live nets (4 and 8); null live net skipped. Sum ≠ mean.
    assert first["live_net_ticks"] == 12.0
    assert first["live_expectancy_ticks"] == pytest.approx(6.0)
    assert first["cell_expectancy_ticks"] == 3.5
    assert first["cumulative_n"] == 3
    assert first["cumulative_live_expectancy_ticks"] == pytest.approx(6.0)

    assert second["session_date"] == "2026-05-15"
    assert second["executed_cell"] == 1
    assert second["adherence"] == 1.0
    assert second["live_net_ticks"] == 6.0
    assert second["live_expectancy_ticks"] == 6.0
    assert second["cumulative_n"] == 4
    assert second["cumulative_live_expectancy_ticks"] == pytest.approx(6.0)
    assert second["systematic_signals"] == 1


def test_build_forward_ledger_rejects_invalid_session_date():
    matches = pd.DataFrame(
        [
            {
                "session_date": "not-a-date",
                "match_class": MATCH_EXECUTED_CELL,
                "side": MATCH_SIDE_JOURNAL,
                "net_ticks": 1.0,
            }
        ]
    )
    with pytest.raises(JournalIngestError, match="invalid session_date"):
        build_forward_ledger(matches, live_since=None, cell_expectancy_ticks=1.0)
