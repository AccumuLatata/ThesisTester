#!/usr/bin/env python3
"""Expand-validate every Program B StudySpec against the locked cell counts."""

from __future__ import annotations

from pathlib import Path

import yaml

from thesistester.study.expand import expand_study
from thesistester.study.schema import load_study_spec

ROOT = Path(__file__).resolve().parent


def main() -> None:
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    failures: list[str] = []
    for row in manifest["studies"]:
        path = ROOT / str(row["file"])
        spec = load_study_spec(path)
        expansion = expand_study(spec)
        expected = int(row["cells"])
        if expansion.run_count != expected:
            failures.append(f"{path.name}: run_count={expansion.run_count} expected={expected}")
            continue
        min_valid = int(row["min_valid"])
        for run in expansion.experiment["runs"]:
            setup = run["setup"]
            if setup["confluence_mode"] != "anchor_rules":
                failures.append(f"{path.name}: mode {setup['confluence_mode']!r}")
                break
            if int(setup["min_valid_confluences"]) != min_valid:
                failures.append(
                    f"{path.name}: setup min_valid={setup['min_valid_confluences']} expected={min_valid}"
                )
                break
            bt = run["backtest"]
            if (
                float(bt["stop_loss_ticks"]) != 80
                or float(bt["take_profit_ticks"]) != 80
                or float(bt["commission_per_side"]) != 0.5
                or float(bt["slippage_ticks"]) != 1.0
                or bt.get("flat_by_session_close") is not True
                or str(bt.get("session_close_time")) != "16:00"
            ):
                failures.append(f"{path.name}: backtest locks drifted")
                break
        print(f"ok {path.name} {expansion.run_count}")
    if failures:
        raise SystemExit("FAILED\n" + "\n".join(failures))
    print(f"ok {manifest['total_studies']} studies / {manifest['total_cells']} cells")


if __name__ == "__main__":
    main()
