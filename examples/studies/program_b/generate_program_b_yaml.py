#!/usr/bin/env python3
"""Emit Program B StudySpec YAML from the locked inventory. Do not hand-edit the YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent

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


def _shared(*, name: str, description: str, min_valid: int) -> dict:
    return {
        "schema_version": 1,
        "study": {
            "name": name,
            "description": description,
            "workers": 1,
            "confirm_above_runs": 200,
            "output_dir": f"results/studies/{name}",
            "dataset": {
                "path": "data/mnq_15s.csv",
                "instrument": "MNQ",
                "format_profile": "quantower_history_exporter",
                "source_timezone": "UTC",
                "ingestion_mode": "15s_primary_derive_1m",
            },
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
                "trigger_params": {},
                "entry_window": None,
                "backtest": {
                    "stop_loss_ticks": 80,
                    "take_profit_ticks": 80,
                    "exposure_policy": "single_position",
                    "commission_per_side": 0.5,
                    "slippage_ticks": 1.0,
                    "flat_by_session_close": True,
                    "session_close_time": "16:00",
                    "session_timezone": "America/New_York",
                    "intrabar_model": "subtimeframe_conservative",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": [],
                "partner_levels": [],
                "confluence_mode": ["anchor_rules"],
                "trigger": ["touch"],
                "trigger_timeframe": ["1min"],
            },
            "mode_rules": {
                "anchor_rules": {
                    "selected_levels": [],
                    "anchor_level": "${core_level}",
                    "confluence_rules": {"from_partners": "required"},
                }
            },
            "report": {
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
            },
        },
    }


def _header(title: str, cells: int, extra: str) -> str:
    return (
        f"# Program B — {title}\n"
        f"# Cells: {cells}. Locks: MNQ touch@1min, confluence 10 (pairs), "
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


def main() -> None:
    manifest: list[dict[str, object]] = []

    smoke = _shared(
        name="progB_smoke_ONH_SMA50_5min",
        description="Program B 1-cell smoke: ONH x SMA_50_5min. Run this first.",
        min_valid=1,
    )
    smoke["study"]["factors"]["core_level"] = ["ONH"]
    smoke["study"]["factors"]["partner_levels"] = [["SMA_50_5min"]]
    _dump(
        OUT / "progB_smoke_ONH_SMA50_5min.yaml",
        _header("smoke", 1, "# Run first. Do not start Wave 0 until this cell is ok.\n"),
        smoke,
    )
    manifest.append({"file": "progB_smoke_ONH_SMA50_5min.yaml", "cells": 1, "min_valid": 1})

    solo = _shared(
        name="progB_w0_solo",
        description="Program B Wave 0: 50 anchors alone (AO1 point zone, min_valid 0).",
        min_valid=0,
    )
    solo["study"]["factors"]["core_level"] = list(ALL_ANCHORS)
    solo["study"]["factors"]["partner_levels"] = [[]]
    _dump(
        OUT / "progB_w0_solo.yaml",
        _header(
            "Wave 0 solo (AO1)",
            50,
            "# min_valid_confluences: 0. Point zone at the live anchor. Not ±10 ticks.\n",
        ),
        solo,
    )
    manifest.append({"file": "progB_w0_solo.yaml", "cells": 50, "min_valid": 0})

    for wave_key, cores in ANCHORS.items():
        for family, partners in CONFIRMS.items():
            name = f"progB_{wave_key}_{family}"
            cells = len(cores) * len(partners)
            spec = _shared(
                name=name,
                description=(
                    f"Program B {wave_key} ({WAVE_TITLE[wave_key]}) x "
                    f"{FAMILY_TITLE[family]}."
                ),
                min_valid=1,
            )
            spec["study"]["factors"]["core_level"] = list(cores)
            spec["study"]["factors"]["partner_levels"] = [list(row) for row in partners]
            _dump(
                OUT / f"{name}.yaml",
                _header(
                    f"{wave_key} / {family}",
                    cells,
                    "# min_valid_confluences: 1. One required partner. No dVWAP partner.\n",
                ),
                spec,
            )
            manifest.append({"file": f"{name}.yaml", "cells": cells, "min_valid": 1})

    (OUT / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "total_studies": len(manifest),
                "total_cells": sum(int(row["cells"]) for row in manifest),
                "studies": manifest,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(manifest)} studies, {sum(int(r['cells']) for r in manifest)} cells")


if __name__ == "__main__":
    main()
