"""TJ7 own-entry counterfactuals — plan §3.0 / §3.7 / §5 TJ7."""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.journal import (
    apply_journal_rules,
    direction_shuffle_null,
    parse_journal_rule,
    replay_journal_brackets,
)
from thesistester.journal import counterfactual as cf_mod
from thesistester.journal.schema import (
    CF_EXIT_SESSION_END,
    CF_EXIT_SL,
    CF_EXIT_TIME_STOP,
    CF_EXIT_TP,
    CF_EXIT_UNRESOLVED,
    DEFAULT_CF_BRACKETS,
    DEFAULT_CF_K,
    DEFAULT_CF_SEED,
    JOIN_RESOLUTION_15S,
    JOIN_RESOLUTION_TICK,
    RECON_AMP_MISSING,
    RECON_RECONCILED,
    RULE_SPLIT_FORWARD,
    RULE_SPLIT_IN_SAMPLE,
    JournalIngestError,
)

UTC = "UTC"


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz=UTC)


def _trade(
    *,
    trade_id: str = "jt:t1:1",
    entry: str = "2026-05-14T14:00:03",
    exit_at: str | None = "2026-05-14T14:00:40",
    price: float = 100.00,
    exit_price: float = 100.50,
    direction: str = "long",
    qty: int = 1,
    session: date = date(2026, 5, 14),
    recon: str | None = RECON_RECONCILED,
    net_ticks: float | None = 2.0,
    fee_ticks: float | None = 2.48,
    commission_cost: float | None = 1.24,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": "MNQ",
        "session_date": session,
        "entry_timestamp": _ts(entry),
        "exit_timestamp": None if exit_at is None else _ts(exit_at),
        "entry_price": price,
        "exit_price": exit_price,
        "direction": direction,
        "qty": qty,
        "status": "closed",
        "net_ticks": net_ticks,
        "fee_ticks": fee_ticks,
        "commission_cost": commission_cost,
        "day_fee_allocation": 0.0,
    }
    if recon is not None:
        payload["recon_status"] = recon
    return payload


def _bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": _ts(stamp),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            }
            for stamp, open_, high, low, close in rows
        ]
    )


def _path_15s() -> pd.DataFrame:
    """Entry bar 14:00:00 would hit both; first post-entry bar hits both."""
    return _bars(
        [
            ("2026-05-14T14:00:00", 100.00, 110.00, 90.00, 100.00),
            ("2026-05-14T14:00:15", 100.00, 103.00, 97.00, 101.00),
            ("2026-05-14T14:00:30", 101.00, 101.25, 100.75, 101.00),
        ]
    )


def test_replay_kwargs_are_keyword_only() -> None:
    params = inspect.signature(replay_journal_brackets).parameters
    for name in ("bars", "ticks", "brackets", "resolution", "allow_unreconciled", "tick_size"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["brackets"].default == DEFAULT_CF_BRACKETS
    assert params["resolution"].default == JOIN_RESOLUTION_15S
    null_params = inspect.signature(direction_shuffle_null).parameters
    for name in ("seed", "k", "allow_unreconciled", "tick_size"):
        assert null_params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert null_params["seed"].default == DEFAULT_CF_SEED
    assert null_params["k"].default == DEFAULT_CF_K


def test_journal_cf_does_not_import_engine() -> None:
    assert "compute_all_levels" not in cf_mod.__dict__
    assert "simulate_trades" not in cf_mod.__dict__
    source = Path(cf_mod.__file__).read_text(encoding="utf-8")
    assert "from thesistester.engine" not in source
    assert "import thesistester.engine" not in source


def test_same_post_entry_bar_both_hit_is_sl() -> None:
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(trades, bars=_path_15s(), brackets=((10, 10, None),))
    row = out.iloc[0]
    assert row["cf_exit_reason"] == CF_EXIT_SL
    assert row["cf_exit_price"] == pytest.approx(97.50)
    # 100 → 97.50 = −2.50 points × qty 1 / 0.25 = −10 ticks; fees 2.48
    assert row["cf_gross_ticks"] == pytest.approx(-10.0)
    assert row["cf_net_ticks"] == pytest.approx(-12.48)


def test_entry_bar_hl_is_not_used_at_15s() -> None:
    bars = _bars(
        [
            ("2026-05-14T14:00:00", 100.00, 110.00, 90.00, 100.00),
            ("2026-05-14T14:00:15", 100.00, 100.50, 99.75, 100.25),
            ("2026-05-14T14:00:30", 100.25, 100.50, 100.00, 100.25),
        ]
    )
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(trades, bars=bars, brackets=((10, 10, None),))
    assert out.iloc[0]["cf_exit_reason"] == CF_EXIT_UNRESOLVED
    assert out.iloc[0]["cf_exit_price"] is None


def test_tick_path_resolves_by_last_order_after_fill() -> None:
    ticks = pd.DataFrame(
        [
            {"timestamp": _ts("2026-05-14T14:00:03"), "price": 90.00},  # at fill — excluded
            {"timestamp": _ts("2026-05-14T14:00:04"), "price": 100.25},
            {"timestamp": _ts("2026-05-14T14:00:05"), "price": 102.50},  # TP
            {"timestamp": _ts("2026-05-14T14:00:06"), "price": 97.50},
        ]
    )
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(
        trades,
        bars=_path_15s(),
        ticks=ticks,
        brackets=((10, 10, None),),
        resolution=JOIN_RESOLUTION_TICK,
    )
    row = out.iloc[0]
    assert row["cf_exit_reason"] == CF_EXIT_TP
    assert row["cf_exit_price"] == pytest.approx(102.50)
    assert row["resolution"] == JOIN_RESOLUTION_TICK


def test_session_end_and_unresolved() -> None:
    quiet = _bars(
        [
            ("2026-05-14T14:00:00", 100.00, 100.25, 99.75, 100.00),
            ("2026-05-14T14:00:15", 100.00, 100.25, 99.75, 100.10),
            ("2026-05-14T21:59:45", 100.10, 100.20, 100.00, 100.15),
            ("2026-05-14T22:00:00", 100.15, 100.20, 100.10, 100.15),
        ]
    )
    trades = pd.DataFrame([_trade()])
    ended = replay_journal_brackets(trades, bars=quiet, brackets=((10, 10, None),))
    assert ended.iloc[0]["cf_exit_reason"] == CF_EXIT_SESSION_END
    assert ended.iloc[0]["cf_exit_price"] == pytest.approx(100.15)

    truncated = _bars(
        [
            ("2026-05-14T14:00:00", 100.00, 100.25, 99.75, 100.00),
            ("2026-05-14T14:00:15", 100.00, 100.25, 99.75, 100.10),
        ]
    )
    missing = replay_journal_brackets(trades, bars=truncated, brackets=((10, 10, None),))
    assert missing.iloc[0]["cf_exit_reason"] == CF_EXIT_UNRESOLVED


def test_later_day_bars_do_not_fake_session_end() -> None:
    bars = _bars(
        [
            ("2026-05-14T14:00:00", 100.00, 100.25, 99.75, 100.00),
            ("2026-05-14T14:00:15", 100.00, 100.25, 99.75, 100.10),
            ("2026-05-15T13:30:00", 100.10, 100.20, 100.00, 100.15),
        ]
    )
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(trades, bars=bars, brackets=((10, 10, None),))
    assert out.iloc[0]["cf_exit_reason"] == CF_EXIT_UNRESOLVED
    assert out.iloc[0]["cf_exit_price"] is None


def test_later_day_ticks_do_not_fake_session_end() -> None:
    ticks = pd.DataFrame(
        [
            {"timestamp": _ts("2026-05-14T14:00:04"), "price": 100.10},
            {"timestamp": _ts("2026-05-14T14:00:10"), "price": 100.15},
            {"timestamp": _ts("2026-05-15T13:30:00"), "price": 100.20},
        ]
    )
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(
        trades,
        bars=_path_15s(),
        ticks=ticks,
        brackets=((10, 10, None),),
        resolution=JOIN_RESOLUTION_TICK,
    )
    assert out.iloc[0]["cf_exit_reason"] == CF_EXIT_UNRESOLVED
    assert out.iloc[0]["cf_exit_price"] is None


def test_exit_rule_delta_pairs_same_entries_only() -> None:
    trades = pd.DataFrame(
        [
            _trade(trade_id="jt:closed:1", net_ticks=4.0),
            _trade(
                trade_id="jt:open:1",
                entry="2026-05-14T15:00:03",
                exit_at=None,
                exit_price=None,
                net_ticks=None,
            ),
            _trade(
                trade_id="jt:unresolved:1",
                entry="2026-05-14T15:01:03",
                net_ticks=10.0,
                exit_price=101.00,
            ),
        ]
    )
    frame = replay_journal_brackets(trades, bars=_path_15s(), brackets=((10, 10, None),))
    reasons = dict(zip(frame["trade_id"], frame["cf_exit_reason"], strict=True))
    assert reasons["jt:closed:1"] == CF_EXIT_SL
    assert reasons["jt:open:1"] == CF_EXIT_UNRESOLVED
    assert reasons["jt:unresolved:1"] == CF_EXIT_UNRESOLVED
    summary = cf_mod.summarize_bracket_replay(frame, trades)
    bucket = summary["brackets"]["bracket:10/10"]
    assert bucket["paired"] == 1
    assert bucket["n_resolved"] == 1
    assert bucket["exit_rule_delta"] == pytest.approx(-12.48 - 4.0)
    assert bucket["mean_cf_net_ticks"] == pytest.approx(-12.48)


def test_time_stop_before_next_15s_open() -> None:
    trades = pd.DataFrame([_trade()])
    out = replay_journal_brackets(trades, bars=_path_15s(), brackets=((10, 10, 5),))
    assert out.iloc[0]["cf_exit_reason"] == CF_EXIT_TIME_STOP


def test_fees_are_qty_scaled() -> None:
    trades = pd.DataFrame([_trade(qty=2, fee_ticks=4.96, commission_cost=2.48, net_ticks=4.0)])
    out = replay_journal_brackets(trades, bars=_path_15s(), brackets=((10, 10, None),))
    # −10 ticks/contract × 2 = −20 gross; fees 4.96
    assert out.iloc[0]["cf_gross_ticks"] == pytest.approx(-20.0)
    assert out.iloc[0]["cf_net_ticks"] == pytest.approx(-24.96)


def test_direction_shuffle_seed_and_count_preservation() -> None:
    trades = pd.DataFrame(
        [
            _trade(trade_id="jt:a:1", direction="long", exit_price=101.00, net_ticks=4.0),
            _trade(
                trade_id="jt:b:1",
                entry="2026-05-14T14:01:03",
                direction="long",
                exit_price=99.00,
                net_ticks=-4.0,
            ),
            _trade(
                trade_id="jt:c:1",
                entry="2026-05-14T14:02:03",
                direction="short",
                exit_price=99.00,
                net_ticks=4.0,
            ),
            _trade(
                trade_id="jt:d:1",
                session=date(2026, 5, 15),
                entry="2026-05-15T14:00:03",
                direction="short",
                exit_price=101.00,
                net_ticks=-4.0,
            ),
        ]
    )
    first = direction_shuffle_null(trades, seed=7, k=50)
    second = direction_shuffle_null(trades, seed=7, k=50)
    assert first["direction_null_pct"] == second["direction_null_pct"]
    assert first["realized_gross_ticks"] == second["realized_gross_ticks"]
    other = direction_shuffle_null(trades, seed=8, k=50)
    assert other["seed"] == 8
    # Preserve 2 long / 1 short on 14-May and 1 short on 15-May: permutation of labels.
    records = trades.to_dict(orient="records")
    groups = cf_mod._group_indices(records)
    rng = __import__("numpy").random.RandomState(7)
    assigned = cf_mod._shuffle_directions(records, groups, rng)
    may14 = [
        assigned[i] for i, row in enumerate(records) if row["session_date"] == date(2026, 5, 14)
    ]
    assert may14.count("long") == 2
    assert may14.count("short") == 1


def test_positional_args_rejected() -> None:
    trades = pd.DataFrame([_trade()])
    with pytest.raises(TypeError):
        replay_journal_brackets(trades, _path_15s())  # type: ignore[misc]
    with pytest.raises(TypeError):
        direction_shuffle_null(trades, 0)  # type: ignore[misc]


def test_refuses_unreconciled_days() -> None:
    trades = pd.DataFrame([_trade(recon=RECON_AMP_MISSING)])
    with pytest.raises(JournalIngestError, match="not reconciled"):
        replay_journal_brackets(trades, bars=_path_15s(), brackets=((10, 10, None),))
    out = replay_journal_brackets(
        trades, bars=_path_15s(), brackets=((10, 10, None),), allow_unreconciled=True
    )
    assert out.iloc[0]["cf_exit_reason"] == CF_EXIT_SL


def test_declared_on_required() -> None:
    with pytest.raises(ValueError, match="declared_on"):
        parse_journal_rule({"name": "no_lunch", "trade_window_ny": "09:30-11:00"})


def test_each_rule_filter_and_split_not_blended() -> None:
    trades = pd.DataFrame(
        [
            _trade(
                trade_id="jt:in:1",
                session=date(2026, 5, 13),
                entry="2026-05-13T14:30:03",  # 10:30 NY
                exit_at="2026-05-13T14:30:10",
                net_ticks=-5.0,
                exit_price=98.75,
            ),
            _trade(
                trade_id="jt:in:2",
                session=date(2026, 5, 13),
                entry="2026-05-13T14:30:20",
                exit_at="2026-05-13T14:30:40",
                net_ticks=-5.0,
            ),
            _trade(
                trade_id="jt:fwd:1",
                session=date(2026, 5, 15),
                entry="2026-05-15T15:30:03",  # 11:30 NY
                net_ticks=8.0,
            ),
            _trade(
                trade_id="jt:fwd:2",
                session=date(2026, 5, 15),
                entry="2026-05-15T16:00:03",  # 12:00 NY
                net_ticks=3.0,
            ),
        ]
    )
    window = parse_journal_rule(
        {"name": "window", "declared_on": "2026-05-14", "trade_window_ny": "09:30-11:00"}
    )
    cap = parse_journal_rule({"name": "cap", "declared_on": "2026-05-14", "max_trades_per_day": 1})
    cooldown = parse_journal_rule(
        {
            "name": "cooldown",
            "declared_on": "2026-05-14",
            "cooldown_seconds_after_loss": 60,
        }
    )
    streak = parse_journal_rule(
        {
            "name": "streak",
            "declared_on": "2026-05-14",
            "stop_after_k_consecutive_losses": 1,
        }
    )
    daily = parse_journal_rule(
        {
            "name": "daily",
            "declared_on": "2026-05-14",
            "daily_loss_stop_ticks": 1,
        }
    )
    hard = parse_journal_rule({"name": "hard", "declared_on": "2026-05-14", "hard_stop_ticks": 10})
    rows = apply_journal_rules(trades, (window, cap, cooldown, streak, daily, hard))
    by_name = {(row["name"], row["split"]): row for row in rows}
    # window 09:30-11:00 NY: 10:30 kept, 11:30/12:00 dropped
    assert by_name[("window", RULE_SPLIT_IN_SAMPLE)]["n_kept"] == 2
    assert by_name[("window", RULE_SPLIT_FORWARD)]["n_kept"] == 0
    assert by_name[("window", RULE_SPLIT_FORWARD)]["trades_removed"] == 2
    assert by_name[("cap", RULE_SPLIT_IN_SAMPLE)]["n_kept"] == 1
    assert by_name[("cap", RULE_SPLIT_IN_SAMPLE)]["trades_removed"] == 1
    assert by_name[("cooldown", RULE_SPLIT_IN_SAMPLE)]["trades_removed"] == 1
    assert by_name[("streak", RULE_SPLIT_IN_SAMPLE)]["trades_removed"] == 1
    assert by_name[("daily", RULE_SPLIT_IN_SAMPLE)]["trades_removed"] == 1
    # Splits never blended into one number.
    assert (
        by_name[("window", RULE_SPLIT_IN_SAMPLE)]["rule_delta_ticks"]
        != by_name[("window", RULE_SPLIT_FORWARD)]["rule_delta_ticks"]
        or by_name[("window", RULE_SPLIT_FORWARD)]["n_total"] == 2
    )
    hard_rows = [row for row in rows if row["name"] == "hard"]
    assert {row["split"] for row in hard_rows} == {RULE_SPLIT_IN_SAMPLE, RULE_SPLIT_FORWARD}


def test_hard_stop_uses_sl_path() -> None:
    trades = pd.DataFrame([_trade(net_ticks=20.0, exit_price=105.00)])
    hit = cf_mod.sl_hit_for_trade(
        trades.iloc[0].to_dict(),
        bars=_path_15s(),
        ticks=None,
        sl_ticks=10,
        resolution=JOIN_RESOLUTION_15S,
    )
    assert hit is not None
    rows = apply_journal_rules(
        trades,
        (parse_journal_rule({"name": "hard", "declared_on": "2026-05-20", "hard_stop_ticks": 10}),),
        hard_stop_exits={("jt:t1:1", 10.0): hit},
    )
    in_sample = next(row for row in rows if row["split"] == RULE_SPLIT_IN_SAMPLE)
    assert in_sample["rule_net_ticks"] == pytest.approx(-12.48)
    assert in_sample["rule_delta_ticks"] == pytest.approx(-12.48 - 20.0)


def test_hard_stop_cooldown_uses_sl_fill_time() -> None:
    first = _trade(
        trade_id="jt:loser:1",
        entry="2026-05-14T14:00:03",
        exit_at="2026-05-14T14:05:00",
        net_ticks=20.0,
        exit_price=105.00,
    )
    later = _trade(
        trade_id="jt:next:1",
        entry="2026-05-14T14:00:40",
        exit_at="2026-05-14T14:01:10",
        net_ticks=5.0,
        exit_price=101.25,
    )
    trades = pd.DataFrame([first, later])
    hit = cf_mod.sl_hit_for_trade(
        first,
        bars=_path_15s(),
        ticks=None,
        sl_ticks=10,
        resolution=JOIN_RESOLUTION_15S,
    )
    assert hit is not None
    rows = apply_journal_rules(
        trades,
        (
            parse_journal_rule(
                {
                    "name": "hard_cooldown",
                    "declared_on": "2026-05-20",
                    "hard_stop_ticks": 10,
                    "cooldown_seconds_after_loss": 30,
                }
            ),
        ),
        hard_stop_exits={("jt:loser:1", 10.0): hit},
    )
    in_sample = next(row for row in rows if row["split"] == RULE_SPLIT_IN_SAMPLE)
    assert in_sample["n_kept"] == 1
    assert in_sample["trades_removed"] == 1
    assert in_sample["rule_net_ticks"] == pytest.approx(-12.48)


def test_cli_writes_artifacts_and_refuses_studies_dir(tmp_path: Path) -> None:
    trades_path = tmp_path / "journal_trades.parquet"
    bars_path = tmp_path / "bars.parquet"
    rules_path = tmp_path / "rules.yaml"
    raw = pd.DataFrame([_trade()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(trades_path, index=False)
    _path_15s().to_parquet(bars_path, index=False)
    rules_path.write_text(
        yaml.safe_dump(
            {"rules": [{"name": "cap", "declared_on": "2026-05-20", "max_trades_per_day": 10}]}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "journal_out"
    code = cli_main(
        [
            "journal",
            "counterfactual",
            "--trades",
            str(trades_path),
            "--bars",
            str(bars_path),
            "--rules",
            str(rules_path),
            "--output-dir",
            str(out),
            "--k",
            "20",
            "--seed",
            "3",
        ]
    )
    assert code == 0
    payload = json.loads((out / "counterfactual.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["seed"] == 3
    assert payload["k"] == 20
    assert "no slippage" in payload["honesty"]
    assert payload["null"]["seed"] == 3
    frame = pd.read_parquet(out / "journal_counterfactuals.parquet")
    assert set(frame["cf_id"]) == {"bracket:10/10", "bracket:10/20", "bracket:20/20"}
    assert frame.iloc[0]["cf_exit_reason"] == CF_EXIT_SL
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "counterfactual",
            "--trades",
            str(trades_path),
            "--bars",
            str(bars_path),
            "--output-dir",
            str(forbidden),
            "--k",
            "5",
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "counterfactual.json").exists()
