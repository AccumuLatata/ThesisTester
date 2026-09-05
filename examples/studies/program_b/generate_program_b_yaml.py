#!/usr/bin/env python3
"""Emit Program B StudySpec YAML from the locked inventory. Do not hand-edit the YAML.

Defaults reproduce the Run 1 packet in this directory (touch, implicit legacy
same-bar policy, random baseline omitted). Opt-in flags write a Run 2 packet
elsewhere — they never rewrite Run 1 files unless ``--output-dir`` points here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent
VALID_TRIGGERS = ("touch", "fade")
VALID_SAME_BAR = ("legacy", "skip_both", "raise")
VALID_PACKETS = ("15s", "tick", "both")

ANCHORS: dict[str, list[str]] = {
    "w1_ext": [
        "ONH",
        "ONL",
        "pONH",
        "pONL",
        "AsiaHigh",
        "AsiaLow",
        "LondonHigh",
        "LondonLow",
        "OR_High",
        "OR_Low",
        "pRTH_High",
        "pRTH_Low",
    ],
    "w2_open": [
        "dOpen",
        "RTH_Open",
        "pRTH_Open",
        "pdOpen",
        "wOpen",
        "pwOpen",
        "mOpen",
        "pmOpen",
    ],
    "w3_range": [
        "pdHigh",
        "pdLow",
        "pdEQ",
        "pwHigh",
        "pwLow",
        "pwEQ",
        "pmHigh",
        "pmLow",
        "pmEQ",
        "prevSettlement",
    ],
    "w4_profile": [
        "pdPOC",
        "pdVAH",
        "pdVAL",
        "pwPOC",
        "pwVAH",
        "pwVAL",
        "pmPOC",
        "pmVAH",
        "pmVAL",
    ],
    "w5_svwap": ["dVWAP", "dVWAP_RTH", "wVWAP", "mVWAP"],
    "w6_sp": [
        "dSinglePrint_30m_NearestAbove",
        "dSinglePrint_30m_NearestBelow",
        "pSinglePrint_30m_NearestAbove",
        "pSinglePrint_30m_NearestBelow",
    ],
    "w7_apoc": ["APOC", "pAPOC"],
    "w8_prev30m": ["prev30mVWAP"],
}

ALL_ANCHORS = [token for keys in ANCHORS.values() for token in keys]
VA_ANCHORS = list(ANCHORS["w4_profile"])
VA_ANCHOR_SET = set(VA_ANCHORS)
FIFTEEN_S_ANCHORS = [token for token in ALL_ANCHORS if token not in VA_ANCHOR_SET]
# Placeholder only. TV3 needs a non-empty list so the StudySpec loads.
# Launch still refuses until the operator pins a real Tick–Tick–Last export.
VA_TICK_PATHS = ["data/mnq_tick_last.csv"]

CONFIRMS: dict[str, list[list[str]]] = {
    "ma": [
        ["SMA_50_1min"],
        ["SMA_50_5min"],
        ["SMA_50_30min"],
        ["SMA_200_1min"],
        ["SMA_200_5min"],
        ["SMA_200_30min"],
        ["EMA_9_1min"],
        ["EMA_9_5min"],
        ["EMA_9_30min"],
        ["EMA_21_1min"],
        ["EMA_21_5min"],
        ["EMA_21_30min"],
    ],
    "rvwap": [["VWAP_rolling_30min"], ["VWAP_rolling_4h"]],
    "pivot": [
        ["Pivot_1m_High"],
        ["Pivot_1m_Low"],
        ["Pivot_5m_High"],
        ["Pivot_5m_Low"],
        ["Pivot_30m_High"],
        ["Pivot_30m_Low"],
        ["Pivot_4h_High"],
        ["Pivot_4h_Low"],
    ],
}

WAVE_TITLE = {
    "w1_ext": "session extremes",
    "w2_open": "session opens",
    "w3_range": "prior range / EQ / settlement",
    "w4_profile": "prior profile",
    "w5_svwap": "session VWAP as cores",
    "w6_sp": "single prints",
    "w7_apoc": "APOC",
    "w8_prev30m": "prev30mVWAP",
}

FAMILY_TITLE = {
    "ma": "MA confirms",
    "rvwap": "rolling VWAP confirms",
    "pivot": "pivot confirms",
}


def study_name(base: str, prefix: str) -> str:
    """Insert ``prefix`` after ``progB_`` so Run 2 dirs do not collide with Run 1."""
    token = prefix.strip().strip("_")
    if not token:
        return base
    if base.startswith("progB_"):
        return f"progB_{token}_{base.removeprefix('progB_')}"
    return f"{token}_{base}"


def _shared(
    *,
    name: str,
    description: str,
    min_valid: int,
    tick_paths: list[str] | None = None,
    trigger: str = "touch",
    same_bar_policy: str | None = None,
    random_baseline: int | None = None,
) -> dict:
    dataset: dict[str, object] = {
        "path": r"/Users/florianrichling/Dropbox/thesistester/data/MNQ AMP Futures (Rithmic), Time - Time - 15s, 8_1_2024 120000 AM-8_7_2026 120000 AM_72578ad9-eaad-41cc-a03e-cf056050cf77.csv",
        "instrument": "MNQ",
        "format_profile": "quantower_history_exporter",
        "source_timezone": "UTC",
        "ingestion_mode": "15s_primary_derive_1m",
    }
    if tick_paths:
        dataset["tick_paths"] = list(tick_paths)
    trigger_params: dict[str, object] = {}
    if trigger == "fade":
        trigger_params["require_close_confirmation"] = False
    backtest: dict[str, object] = {
        "stop_loss_ticks": 80,
        "take_profit_ticks": 80,
        "exposure_policy": "single_position",
        "commission_per_side": 0.5,
        "slippage_ticks": 1.0,
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "intrabar_model": "subtimeframe_conservative",
    }
    if same_bar_policy and same_bar_policy != "legacy":
        backtest["same_bar_opposite_direction"] = same_bar_policy
    report: dict[str, object] = {
        "primary_metric": "expectancy_r",
        "secondary_metrics": [
            "profit_factor",
            "max_drawdown_r",
            "trade_count",
            "total_r",
        ],
        "min_trades": 30,
        "multiple_testing": "warn",
        "group_by": ["core_level", "partner_levels"],
    }
    if random_baseline is not None and int(random_baseline) >= 1:
        report["random_baseline"] = {
            "enabled": True,
            "n_replicas": int(random_baseline),
            "random_state": 42,
        }
    return {
        "schema_version": 1,
        "study": {
            "name": name,
            "description": description,
            "workers": 1,
            "confirm_above_runs": 200,
            "output_dir": f"results/studies/{name}",
            "dataset": dataset,
            "levels": {
                "sma_lengths": [50, 200],
                "ema_lengths": [9, 21],
                "sma_timeframes": ["1min", "5min", "30min"],
                "ema_timeframes": ["1min", "5min", "30min"],
                "vwap_windows": ["30min", "4h"],
                "pivots_enabled": True,
                "pivot_timeframes": ["1min", "5min", "30min", "4h"],
                "prev30m_vwap_enabled": True,
                "session_vwap_enabled": True,
                "single_prints_enabled": True,
                "apoc_enabled": True,
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 10,
                "min_valid_confluences": min_valid,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": trigger_params,
                "entry_window": None,
                "backtest": backtest,
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": [],
                "partner_levels": [],
                "confluence_mode": ["anchor_rules"],
                "trigger": [trigger],
                "trigger_timeframe": ["1min"],
            },
            "mode_rules": {
                "anchor_rules": {
                    "selected_levels": [],
                    "anchor_level": "${core_level}",
                    "confluence_rules": {"from_partners": "required"},
                }
            },
            "report": report,
        },
    }


def _header(title: str, cells: int, extra: str, *, trigger: str = "touch") -> str:
    return (
        f"# Program B — {title}\n"
        f"# Cells: {cells}. Locks: MNQ {trigger}@1min, confluence 10 (pairs), "
        f"SL/TP 80/80, costs 0.5 + 1 tick/side, flatten 16:00 America/New_York.\n"
        f"# Bot: docs/PROGRAM_B_OPERATOR_RUNBOOK.md\n"
        f"# Replace dataset.path with the same 15s Quantower HE CSV used on Data.\n"
        f"{extra}"
        f"# Regenerated by generate_program_b_yaml.py — do not hand-edit tokens.\n"
    )


def _dump(path: Path, header: str, spec: dict) -> None:
    path.write_text(
        header + yaml.safe_dump(spec, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _write_manifest(
    path: Path,
    packet: str,
    rows: list[dict[str, object]],
    *,
    locks: str | None = None,
) -> None:
    payload: dict[str, object] = {"packet": packet}
    if locks:
        payload["locks"] = locks
    payload["total_studies"] = len(rows)
    payload["total_cells"] = sum(int(row["cells"]) for row in rows)
    payload["studies"] = rows
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _run2_readme(*, trigger: str, same_bar_policy: str, n_replicas: int) -> str:
    return (
        "# Program B Run 2 StudySpecs\n"
        "\n"
        "Bot runbook (normative): "
        "[`docs/PROGRAM_B_OPERATOR_RUNBOOK.md`](../../../docs/PROGRAM_B_OPERATOR_RUNBOOK.md) "
        "§1 Run 2 lock table.\n"
        "Generator: [`generate_program_b_yaml.py`](../program_b/generate_program_b_yaml.py).\n"
        "\n"
        f"**15s packet:** 23 studies / **944** cells (`manifest.yaml`). "
        f"Trigger `{trigger}` @ 1min, `same_bar_opposite_direction: {same_bar_policy}`, "
        f"`report.random_baseline.n_replicas: {n_replicas}`.\n"
        "Study names are `progB_r2_*` so `output_dir` does not collide with Run 1.\n"
        "Filenames stay `progB_*.yaml` so the validator Wave 0 / smoke stems still match.\n"
        "Do not hand-edit token lists. Do not treat Run 1 vs Run 2 as a paired ΔE.\n"
        "\n"
        "```bash\n"
        "python3 examples/studies/program_b/generate_program_b_yaml.py \\\n"
        "  --trigger fade --same-bar-policy raise --random-baseline 50 \\\n"
        "  --output-dir examples/studies/program_b_run2 --packet 15s\n"
        "PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \\\n"
        "  examples/studies/program_b_run2/manifest.yaml\n"
        "```\n"
        "\n"
        "Expect: `ok 23 studies / 944 cells`.\n"
    )


def generate_packet(
    output_dir: Path,
    *,
    trigger: str = "touch",
    same_bar_policy: str | None = None,
    random_baseline: int | None = None,
    packet: str = "both",
    study_prefix: str = "",
    write_readme: bool = False,
    locks: str | None = None,
) -> None:
    """Write Program B YAMLs. Default kwargs reproduce the Run 1 packet."""
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"trigger must be one of {VALID_TRIGGERS}; got {trigger!r}")
    if same_bar_policy is not None and same_bar_policy not in VALID_SAME_BAR:
        raise ValueError(
            f"same_bar_policy must be one of {VALID_SAME_BAR}; got {same_bar_policy!r}"
        )
    if packet not in VALID_PACKETS:
        raise ValueError(f"packet must be one of {VALID_PACKETS}; got {packet!r}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_15s = packet in {"15s", "both"}
    write_tick = packet in {"tick", "both"}
    shared_kw = {
        "trigger": trigger,
        "same_bar_policy": same_bar_policy,
        "random_baseline": random_baseline,
    }

    fifteen_s: list[dict[str, object]] = []
    tick_gated: list[dict[str, object]] = []

    if write_15s:
        smoke_name = study_name("progB_smoke_ONH_SMA50_5min", study_prefix)
        smoke = _shared(
            name=smoke_name,
            description="Program B 1-cell smoke: ONH x SMA_50_5min. Run this first.",
            min_valid=1,
            **shared_kw,
        )
        smoke["study"]["factors"]["core_level"] = ["ONH"]
        smoke["study"]["factors"]["partner_levels"] = [["SMA_50_5min"]]
        _dump(
            out / "progB_smoke_ONH_SMA50_5min.yaml",
            _header(
                "smoke",
                1,
                "# Run first. Do not start Wave 0 until this cell is ok.\n",
                trigger=trigger,
            ),
            smoke,
        )
        fifteen_s.append({"file": "progB_smoke_ONH_SMA50_5min.yaml", "cells": 1, "min_valid": 1})

        solo_name = study_name("progB_w0_solo", study_prefix)
        solo = _shared(
            name=solo_name,
            description=(
                "Program B Wave 0 (15s): 41 non-VA anchors alone (AO1 point zone, min_valid 0)."
            ),
            min_valid=0,
            **shared_kw,
        )
        solo["study"]["factors"]["core_level"] = list(FIFTEEN_S_ANCHORS)
        solo["study"]["factors"]["partner_levels"] = [[]]
        _dump(
            out / "progB_w0_solo.yaml",
            _header(
                "Wave 0 solo 15s (AO1)",
                len(FIFTEEN_S_ANCHORS),
                "# min_valid_confluences: 0. Point zone at the live anchor. Not ±10 ticks.\n"
                "# 15s-safe: no pd/pw/pm VA tokens. Tick-gated solos are progB_w0_va.yaml.\n",
                trigger=trigger,
            ),
            solo,
        )
        fifteen_s.append(
            {"file": "progB_w0_solo.yaml", "cells": len(FIFTEEN_S_ANCHORS), "min_valid": 0}
        )

    if write_tick:
        solo_va = _shared(
            name=study_name("progB_w0_va", study_prefix),
            description=(
                "Program B Wave 0 VA: 9 prior-profile anchors alone "
                "(AO1 point zone, min_valid 0). Tick-gated."
            ),
            min_valid=0,
            tick_paths=VA_TICK_PATHS,
            **shared_kw,
        )
        solo_va["study"]["factors"]["core_level"] = list(VA_ANCHORS)
        solo_va["study"]["factors"]["partner_levels"] = [[]]
        _dump(
            out / "progB_w0_va.yaml",
            _header(
                "Wave 0 solo VA (AO1, tick-gated)",
                len(VA_ANCHORS),
                "# min_valid_confluences: 0. Point zone at the live anchor. Not ±10 ticks.\n"
                "# Tick-gated: do not launch on 15s-only. TV3 refuses without dataset.tick_paths.\n"
                "# Placeholder tick_paths: data/mnq_tick_last.csv. Launch still refuses "
                "missing files.\n",
                trigger=trigger,
            ),
            solo_va,
        )
        tick_gated.append({"file": "progB_w0_va.yaml", "cells": len(VA_ANCHORS), "min_valid": 0})

    for wave_key, cores in ANCHORS.items():
        tick_wave = wave_key == "w4_profile"
        if tick_wave and not write_tick:
            continue
        if not tick_wave and not write_15s:
            continue
        extra = (
            "# min_valid_confluences: 1. One required partner. No dVWAP partner.\n"
            "# Tick-gated: prior-profile VA cores. Do not launch on 15s-only.\n"
            "# Placeholder tick_paths: data/mnq_tick_last.csv. Launch still refuses "
            "missing files.\n"
            if tick_wave
            else "# min_valid_confluences: 1. One required partner. No dVWAP partner.\n"
        )
        target = tick_gated if tick_wave else fifteen_s
        for family, partners in CONFIRMS.items():
            file_stem = f"progB_{wave_key}_{family}"
            name = study_name(file_stem, study_prefix)
            cells = len(cores) * len(partners)
            spec = _shared(
                name=name,
                description=(
                    f"Program B {wave_key} ({WAVE_TITLE[wave_key]}) x {FAMILY_TITLE[family]}."
                ),
                min_valid=1,
                tick_paths=VA_TICK_PATHS if tick_wave else None,
                **shared_kw,
            )
            spec["study"]["factors"]["core_level"] = list(cores)
            spec["study"]["factors"]["partner_levels"] = [list(row) for row in partners]
            _dump(
                out / f"{file_stem}.yaml",
                _header(f"{wave_key} / {family}", cells, extra, trigger=trigger),
                spec,
            )
            target.append({"file": f"{file_stem}.yaml", "cells": cells, "min_valid": 1})

    if write_15s:
        _write_manifest(out / "manifest.yaml", "15s", fifteen_s, locks=locks)
    if write_tick:
        _write_manifest(out / "manifest_va.yaml", "tick", tick_gated, locks=locks)
    if write_readme:
        policy = same_bar_policy or "legacy"
        n_rep = int(random_baseline) if random_baseline else 0
        (out / "README.md").write_text(
            _run2_readme(trigger=trigger, same_bar_policy=policy, n_replicas=n_rep),
            encoding="utf-8",
        )
    parts: list[str] = []
    if write_15s:
        parts.append(
            f"wrote 15s {len(fifteen_s)} studies / {sum(int(r['cells']) for r in fifteen_s)} cells"
        )
    if write_tick:
        parts.append(
            f"tick-gated {len(tick_gated)} studies / "
            f"{sum(int(r['cells']) for r in tick_gated)} cells"
        )
    print("; ".join(parts) + f" → {out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trigger",
        choices=VALID_TRIGGERS,
        default="touch",
        help="Study trigger token. Default touch (Run 1).",
    )
    parser.add_argument(
        "--same-bar-policy",
        choices=VALID_SAME_BAR,
        default=None,
        help="Opt-in same_bar_opposite_direction. Omitted / legacy = do not emit the key.",
    )
    parser.add_argument(
        "--random-baseline",
        type=int,
        default=None,
        metavar="N",
        help="Enable report.random_baseline with N replicas. Omitted = off (Run 1).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUT,
        help="Directory to write YAMLs. Default is this Run 1 directory.",
    )
    parser.add_argument(
        "--packet",
        choices=VALID_PACKETS,
        default="both",
        help="Which manifests to write. Default both (Run 1). Run 2 uses 15s.",
    )
    parser.add_argument(
        "--study-prefix",
        default=None,
        help="Inserted after progB_ in study.name / output_dir. Fade defaults to r2.",
    )
    args = parser.parse_args(argv)
    if args.random_baseline is not None and args.random_baseline < 1:
        parser.error("--random-baseline must be >= 1")
    prefix = args.study_prefix
    if prefix is None:
        prefix = "r2" if args.trigger == "fade" else ""
    write_readme = Path(args.output_dir).resolve() != OUT.resolve()
    locks = "run2" if args.trigger == "fade" else None
    generate_packet(
        Path(args.output_dir),
        trigger=args.trigger,
        same_bar_policy=args.same_bar_policy,
        random_baseline=args.random_baseline,
        packet=args.packet,
        study_prefix=prefix,
        write_readme=write_readme,
        locks=locks,
    )


if __name__ == "__main__":
    main()
