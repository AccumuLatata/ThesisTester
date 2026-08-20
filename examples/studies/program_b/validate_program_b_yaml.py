#!/usr/bin/env python3
"""Expand-validate every Program B StudySpec against locked cell counts and product locks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping

import yaml

from thesistester.levels.catalog import STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.expand import expand_study
from thesistester.study.schema import StudySpecError, closed_level_token_set, load_study_spec

ROOT = Path(__file__).resolve().parent

LOCKED_INSTRUMENT = "MNQ"
LOCKED_TRIGGER = "touch"
LOCKED_TRIGGER_TF = "1min"
LOCKED_MODE = "anchor_rules"
LOCKED_FROM_PARTNERS = "required"
LOCKED_TIMEZONE = "America/New_York"
LOCKED_CLOSE = "16:00"
LOCKED_INGEST = "15s_primary_derive_1m"
LOCKED_FORMAT = "quantower_history_exporter"
FORBIDDEN_PARTNER = "dVWAP"


def _load_generate() -> Any:
    path = ROOT / "generate_program_b_yaml.py"
    spec = importlib.util.spec_from_file_location("program_b_generate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_inventory_matches_catalog(generate: Any | None = None) -> None:
    """Fail closed if the generator inventory leaves the default closed token set."""
    gen = generate if generate is not None else _load_generate()
    expected_anchors = STATIC_STUDY_LEVEL_NAMES | {"prev30mVWAP"}
    got = set(gen.ALL_ANCHORS)
    if got != expected_anchors:
        raise SystemExit(
            "Program B anchors drifted from catalog: "
            f"missing={sorted(expected_anchors - got)} extra={sorted(got - expected_anchors)}"
        )
    closed = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    confirms = [row[0] for family in gen.CONFIRMS.values() for row in family]
    unknown = [token for token in confirms if token not in closed]
    if unknown:
        raise SystemExit(f"Program B confirms not in closed set: {unknown}")
    if FORBIDDEN_PARTNER in confirms:
        raise SystemExit("Program B confirms must not include dVWAP")


def _check_backtest(bt: Mapping[str, Any], label: str) -> list[str]:
    if (
        float(bt.get("stop_loss_ticks", 0)) != 80
        or float(bt.get("take_profit_ticks", 0)) != 80
        or float(bt.get("commission_per_side", 0)) != 0.5
        or float(bt.get("slippage_ticks", 0)) != 1.0
        or bt.get("flat_by_session_close") is not True
        or str(bt.get("session_close_time")) != LOCKED_CLOSE
        or str(bt.get("session_timezone")) != LOCKED_TIMEZONE
        or str(bt.get("exposure_policy")) != "single_position"
        or str(bt.get("intrabar_model")) != "subtimeframe_conservative"
    ):
        return [f"{label}: backtest locks drifted"]
    return []


def validate_study_file(
    path: Path,
    row: Mapping[str, Any],
    *,
    generate: Any | None = None,
) -> list[str]:
    """Return lock/expand failures for one Program B YAML. Empty list means pass."""
    gen = generate if generate is not None else _load_generate()
    failures: list[str] = []
    try:
        spec = load_study_spec(path)
    except (OSError, StudySpecError, yaml.YAMLError) as exc:
        return [f"{path.name}: load failed: {exc}"]

    study = spec["study"]
    dataset = study.get("dataset") or {}
    factors = study.get("factors") or {}
    constants = study.get("constants") or {}
    mode_rules = (study.get("mode_rules") or {}).get("anchor_rules") or {}
    from_partners = (mode_rules.get("confluence_rules") or {}).get("from_partners")
    stem = path.stem
    min_valid = int(row["min_valid"])
    cores = list(factors.get("core_level") or [])
    partners = list(factors.get("partner_levels") or [])

    if dataset.get("instrument") != LOCKED_INSTRUMENT:
        failures.append(f"{path.name}: instrument {dataset.get('instrument')!r}")
    if dataset.get("format_profile") != LOCKED_FORMAT:
        failures.append(f"{path.name}: format_profile drifted")
    if dataset.get("source_timezone") != "UTC":
        failures.append(f"{path.name}: source_timezone drifted")
    if dataset.get("ingestion_mode") != LOCKED_INGEST:
        failures.append(f"{path.name}: ingestion_mode drifted")
    if list(factors.get("confluence_mode") or []) != [LOCKED_MODE]:
        failures.append(f"{path.name}: confluence_mode must be exclusive [{LOCKED_MODE}]")
    if list(factors.get("trigger") or []) != [LOCKED_TRIGGER]:
        failures.append(f"{path.name}: trigger drifted")
    if list(factors.get("trigger_timeframe") or []) != [LOCKED_TRIGGER_TF]:
        failures.append(f"{path.name}: trigger_timeframe drifted")
    if "otf" in factors:
        failures.append(f"{path.name}: factors.otf must be omitted")
    if from_partners != LOCKED_FROM_PARTNERS:
        failures.append(f"{path.name}: from_partners {from_partners!r}")

    raw_min = constants.get("min_valid_confluences")
    if isinstance(raw_min, bool) or raw_min is None or int(raw_min) != min_valid:
        failures.append(f"{path.name}: constants.min_valid_confluences {raw_min!r} != {min_valid}")

    if min_valid == 0:
        if partners != [[]]:
            failures.append(f"{path.name}: Wave 0 partner_levels must be [[]]")
        if set(cores) != set(gen.ALL_ANCHORS):
            failures.append(f"{path.name}: Wave 0 cores drifted from inventory")
    else:
        if any(len(partner_set) == 0 for partner_set in partners):
            failures.append(f"{path.name}: empty partner set illegal when min_valid>=1")
        partner_tokens = [token for partner_set in partners for token in partner_set]
        if FORBIDDEN_PARTNER in partner_tokens:
            failures.append(f"{path.name}: dVWAP must not appear in partner_levels")
        if any(len(partner_set) != 1 for partner_set in partners):
            failures.append(f"{path.name}: pair partner-sets must be one token")
        if stem.startswith("progB_w") and stem != "progB_w0_solo":
            wave_key, family = stem.removeprefix("progB_").rsplit("_", 1)
            if wave_key in gen.ANCHORS and family in gen.CONFIRMS:
                if cores != list(gen.ANCHORS[wave_key]):
                    failures.append(f"{path.name}: cores drifted from {wave_key}")
                expected_partners = [list(item) for item in gen.CONFIRMS[family]]
                if partners != expected_partners:
                    failures.append(f"{path.name}: partners drifted from {family}")
        if stem.startswith("progB_smoke"):
            if cores != ["ONH"] or partners != [["SMA_50_5min"]]:
                failures.append(f"{path.name}: smoke cell must be ONH x SMA_50_5min")

    failures.extend(_check_backtest(constants.get("backtest") or {}, path.name))
    for section in ("grid", "validation", "walk_forward"):
        if (constants.get(section) or {}).get("enabled") is not False:
            failures.append(f"{path.name}: constants.{section}.enabled must be false")
    if int(study.get("workers", 0)) != 1:
        failures.append(f"{path.name}: workers must be 1")
    report = study.get("report") or {}
    if int(report.get("min_trades", 0)) != 30:
        failures.append(f"{path.name}: report.min_trades must be 30")
    if report.get("primary_metric") != "expectancy_r":
        failures.append(f"{path.name}: primary_metric must be expectancy_r")

    try:
        expansion = expand_study(spec)
    except StudySpecError as exc:
        failures.append(f"{path.name}: expand failed: {exc}")
        return failures

    expected = int(row["cells"])
    if expansion.run_count != expected:
        failures.append(f"{path.name}: run_count={expansion.run_count} expected={expected}")
        return failures

    for run in expansion.experiment["runs"]:
        setup = run["setup"]
        if setup["confluence_mode"] != LOCKED_MODE:
            failures.append(f"{path.name}: mode {setup['confluence_mode']!r}")
            break
        if int(setup["min_valid_confluences"]) != min_valid:
            failures.append(
                f"{path.name}: setup min_valid={setup['min_valid_confluences']} expected={min_valid}"
            )
            break
        if (
            setup.get("trigger") != LOCKED_TRIGGER
            or setup.get("trigger_timeframe") != LOCKED_TRIGGER_TF
        ):
            failures.append(f"{path.name}: expanded trigger drifted")
            break
        if setup.get("instrument") != LOCKED_INSTRUMENT:
            failures.append(f"{path.name}: expanded instrument drifted")
            break
        rules = setup.get("confluence_rules") or []
        if min_valid == 0:
            if rules:
                failures.append(f"{path.name}: Wave 0 must expand to empty confluence_rules")
                break
        else:
            if not rules or any(rule.get("required") is not True for rule in rules):
                failures.append(f"{path.name}: pair rules must be required")
                break
            if any(rule.get("level") == FORBIDDEN_PARTNER for rule in rules):
                failures.append(f"{path.name}: expanded dVWAP partner")
                break
        bt_fail = _check_backtest(run["backtest"], path.name)
        if bt_fail:
            failures.extend(bt_fail)
            break
    return failures


def validate_manifest(
    root: Path | None = None,
) -> tuple[list[str], list[str], int, int]:
    """Validate every manifest row.

    Returns ``(ok_lines, failures, n_studies, n_cells)``. A file is listed in
    ``ok_lines`` only when it produced zero failures — callers must not print
    ``ok`` for a file that failed a lock check.
    """
    base = root or ROOT
    generate = _load_generate()
    assert_inventory_matches_catalog(generate)
    manifest = yaml.safe_load((base / "manifest.yaml").read_text(encoding="utf-8"))
    failures: list[str] = []
    ok_lines: list[str] = []
    for row in manifest["studies"]:
        path = base / str(row["file"])
        file_failures = validate_study_file(path, row, generate=generate)
        if file_failures:
            failures.extend(file_failures)
            continue
        ok_lines.append(f"ok {path.name} {int(row['cells'])}")
    return ok_lines, failures, int(manifest["total_studies"]), int(manifest["total_cells"])


def main() -> None:
    ok_lines, failures, n_studies, n_cells = validate_manifest()
    for line in ok_lines:
        print(line)
    if failures:
        raise SystemExit("FAILED\n" + "\n".join(failures))
    print(f"ok {n_studies} studies / {n_cells} cells")


if __name__ == "__main__":
    main()
