"""MW0 cell constants (§9.2) and StudySpec builders.

Policies are per cell. Cells 1/3/4/6 use ``raise``; 2 and 5 use ``legacy``.
Do not switch a policy to obtain trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .slice_csv import (
    CELL6_WINDOW_END_UTC,
    CELL6_WINDOW_START_UTC,
    SHORT_WINDOW_END_UTC,
    SHORT_WINDOW_START_UTC,
)

FULL_SPEC_RELATIVE = Path("examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml")
FULL_CELL_KNOWN_TRADE_COUNT = 59
FULL_CELL_KNOWN_EXPECTANCY = 0.0805

PROGRAM_B_LEVELS: dict[str, Any] = {
    "sma_lengths": [50, 200],
    "ema_lengths": [9, 21],
    "sma_timeframes": ["1min", "5min", "30min"],
    "ema_timeframes": ["1min", "5min", "30min"],
    "vwap_windows": ["30min", "4h"],
    "poc_windows": [],
    "pivots_enabled": True,
    "pivot_timeframes": ["1min", "5min", "30min", "4h"],
    "prev30m_vwap_enabled": True,
    "session_vwap_enabled": True,
    "single_prints_enabled": True,
    "apoc_enabled": False,
    "prior_day_profile_aggregation_ticks": 4,
    "prior_week_profile_aggregation_ticks": 8,
    "prior_month_profile_aggregation_ticks": 10,
}

SMOKE_CONSTANTS: dict[str, Any] = {
    "direction": "both",
    "tolerance_ticks": 10,
    "min_valid_confluences": 1,
    "naked_only": False,
    "naked_requirement": "any",
    "trigger_params": {"require_close_confirmation": False},
    "entry_window": None,
    "grid": {"enabled": False},
    "validation": {"enabled": False},
    "walk_forward": {"enabled": False},
}

RANDOM_BASELINE: dict[str, Any] = {
    "enabled": True,
    "n_replicas": 50,
    "random_state": 42,
}


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    number: int | None
    title: str
    trigger: str
    trigger_timeframe: str
    core_level: str
    partner_level: str
    stop_loss_ticks: int
    take_profit_ticks: int
    same_bar_opposite_direction: str
    csv_role: str
    n_replicas: int
    expect_zero_trades: bool
    notes: str
    confluence_mode: str = "anchor_rules"
    tolerance_ticks: int = 10
    min_confluences: int = 1
    max_confluences: int = 2


SHORT_CELLS: tuple[CellSpec, ...] = (
    CellSpec(
        cell_id="cell_01_fade_onh_sma50_5min",
        number=1,
        title="fade @ 1min, ONH × SMA_50_5min, 80/80, raise",
        trigger="fade",
        trigger_timeframe="1min",
        core_level="ONH",
        partner_level="SMA_50_5min",
        stop_loss_ticks=80,
        take_profit_ticks=80,
        same_bar_opposite_direction="raise",
        csv_role="short",
        n_replicas=50,
        expect_zero_trades=False,
        notes="Reference configuration, short UTC window.",
    ),
    CellSpec(
        cell_id="cell_02_touch_pdhigh_ema9_1min",
        number=2,
        title="touch, pdHigh × EMA_9_1min, 40/80, legacy",
        trigger="touch",
        trigger_timeframe="base",
        core_level="pdHigh",
        partner_level="EMA_9_1min",
        stop_loss_ticks=40,
        take_profit_ticks=80,
        same_bar_opposite_direction="legacy",
        csv_role="short",
        n_replicas=50,
        expect_zero_trades=False,
        notes="Other entry + bracket. direction stays both.",
    ),
    CellSpec(
        cell_id="cell_03_break_orhigh_rvwap30",
        number=3,
        title="break, OR_High × VWAP_rolling_30min, 20/60, raise",
        trigger="break",
        trigger_timeframe="base",
        core_level="OR_High",
        partner_level="VWAP_rolling_30min",
        stop_loss_ticks=20,
        take_profit_ticks=60,
        same_bar_opposite_direction="raise",
        csv_role="short",
        n_replicas=50,
        expect_zero_trades=False,
        notes="Other anchor family.",
    ),
    CellSpec(
        cell_id="cell_04_continuation_london_pivot5m",
        number=4,
        title="continuation, LondonHigh × Pivot_5m_High, 80/40, raise",
        trigger="continuation",
        trigger_timeframe="base",
        core_level="LondonHigh",
        partner_level="Pivot_5m_High",
        stop_loss_ticks=80,
        take_profit_ticks=40,
        same_bar_opposite_direction="raise",
        csv_role="short",
        n_replicas=50,
        expect_zero_trades=False,
        notes="Approach-side twin of fade, asymmetric bracket.",
    ),
    CellSpec(
        cell_id="cell_05_3c_onl_ema21_1min",
        number=5,
        title="3c, ONL × EMA_21_1min, 60/60, legacy",
        trigger="3c",
        trigger_timeframe="base",
        core_level="ONL",
        partner_level="EMA_21_1min",
        stop_loss_ticks=60,
        take_profit_ticks=60,
        same_bar_opposite_direction="legacy",
        csv_role="short",
        n_replicas=50,
        expect_zero_trades=False,
        notes="Different signal machinery.",
    ),
    CellSpec(
        cell_id="cell_06_fade_onh_sma200_30min_zero",
        number=6,
        title="fade, ONH × SMA_200_30min, UTC [2024-08-01, 2024-08-04), 0 trades",
        trigger="fade",
        trigger_timeframe="1min",
        core_level="ONH",
        partner_level="SMA_200_30min",
        stop_loss_ticks=80,
        take_profit_ticks=80,
        same_bar_opposite_direction="raise",
        csv_role="cell6",
        n_replicas=50,
        expect_zero_trades=True,
        notes="Three UTC days: SMA_200_30min stays NaN; random fields stay null.",
    ),
)

FULL_CELL = CellSpec(
    cell_id="full_reference",
    number=None,
    title="full Program B smoke ONH × SMA_50_5min on the farm CSV",
    trigger="fade",
    trigger_timeframe="1min",
    core_level="ONH",
    partner_level="SMA_50_5min",
    stop_loss_ticks=80,
    take_profit_ticks=80,
    same_bar_opposite_direction="raise",
    csv_role="full",
    n_replicas=50,
    expect_zero_trades=False,
    notes="Known 59 trades, E=0.0805. Spec is the smoke YAML.",
)

CI_PREPARE_REPLICA = CellSpec(
    cell_id="ci_prepare_replica",
    number=None,
    title="synthetic: prepare + one replica loop",
    trigger="touch",
    trigger_timeframe="base",
    core_level="dOpen",
    partner_level="RTH_Open",
    stop_loss_ticks=80,
    take_profit_ticks=80,
    same_bar_opposite_direction="legacy",
    csv_role="synthetic",
    n_replicas=1,
    expect_zero_trades=False,
    notes="CI only. Exercises prepare and vs_random_benchmark once. Policy legacy so a same-bar opposite pair still fills.",
    confluence_mode="global_cluster",
    tolerance_ticks=10000,
    min_confluences=1,
    max_confluences=2,
)

CI_CELL6_SHAPE = CellSpec(
    cell_id="ci_cell6_shape",
    number=None,
    title="synthetic: cell-6 shape (0 trades, SMA_200_30min NaN)",
    trigger="fade",
    trigger_timeframe="1min",
    core_level="ONH",
    partner_level="SMA_200_30min",
    stop_loss_ticks=80,
    take_profit_ticks=80,
    same_bar_opposite_direction="raise",
    csv_role="synthetic",
    n_replicas=50,
    expect_zero_trades=True,
    notes="CI only. Same pair/policy/shape as §9.2 cell 6.",
)

CELLS_BY_ID: dict[str, CellSpec] = {
    spec.cell_id: spec for spec in (*SHORT_CELLS, FULL_CELL, CI_PREPARE_REPLICA, CI_CELL6_SHAPE)
}


def parse_cell_selector(raw: str) -> list[CellSpec]:
    """Parse ``short``, ``full``, ``all``, numeric 1-6, or cell ids."""
    tokens = [part.strip() for part in raw.split(",") if part.strip()]
    if not tokens:
        raise ValueError(" --cells is empty")
    selected: list[CellSpec] = []
    seen: set[str] = set()

    def _add(spec: CellSpec) -> None:
        if spec.cell_id not in seen:
            selected.append(spec)
            seen.add(spec.cell_id)

    for token in tokens:
        lowered = token.lower()
        if lowered in {"short", "shorts", "six"}:
            for spec in SHORT_CELLS:
                _add(spec)
            continue
        if lowered in {"full", "reference"}:
            _add(FULL_CELL)
            continue
        if lowered == "all":
            for spec in SHORT_CELLS:
                _add(spec)
            _add(FULL_CELL)
            continue
        if lowered in {"ci", "synthetic"}:
            _add(CI_PREPARE_REPLICA)
            _add(CI_CELL6_SHAPE)
            continue
        if token.isdigit():
            number = int(token)
            match = next((spec for spec in SHORT_CELLS if spec.number == number), None)
            if match is None:
                raise ValueError(f"unknown short-cell number {number!r}; expected 1-6")
            _add(match)
            continue
        if token in CELLS_BY_ID:
            _add(CELLS_BY_ID[token])
            continue
        raise ValueError(
            f"unknown --cells token {token!r}; use short, full, all, 1-6, or a cell id"
        )
    return selected


def program_b_backtest(spec: CellSpec) -> dict[str, Any]:
    return {
        "stop_loss_ticks": spec.stop_loss_ticks,
        "take_profit_ticks": spec.take_profit_ticks,
        "exposure_policy": "single_position",
        "commission_per_side": 0.5,
        "slippage_ticks": 1.0,
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "intrabar_model": "subtimeframe_conservative",
        "same_bar_opposite_direction": spec.same_bar_opposite_direction,
    }


def build_study_mapping(
    spec: CellSpec,
    *,
    csv_path: Path,
    study_name: str,
    output_dir: Path,
    n_replicas: int | None = None,
    levels: Mapping[str, Any] | None = None,
    extra_constants: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    constants = {
        **SMOKE_CONSTANTS,
        "tolerance_ticks": spec.tolerance_ticks,
        "min_confluences": spec.min_confluences,
        "max_confluences": spec.max_confluences,
        **dict(extra_constants or {}),
        "backtest": program_b_backtest(spec),
    }
    replicas = int(n_replicas if n_replicas is not None else spec.n_replicas)
    if spec.confluence_mode == "global_cluster":
        mode_rules: dict[str, Any] = {
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            }
        }
    else:
        mode_rules = {
            "anchor_rules": {
                "selected_levels": [],
                "anchor_level": "${core_level}",
                "confluence_rules": {"from_partners": "required"},
            }
        }
    return {
        "schema_version": 1,
        "study": {
            "name": study_name,
            "description": spec.title,
            "workers": 1,
            "confirm_above_runs": 200,
            "output_dir": str(output_dir),
            "dataset": {
                "path": str(Path(csv_path).resolve()),
                "instrument": "MNQ",
                "format_profile": "quantower_history_exporter",
                "source_timezone": "UTC",
                "ingestion_mode": "15s_primary_derive_1m",
            },
            "levels": dict(levels or PROGRAM_B_LEVELS),
            "constants": constants,
            "factors": {
                "core_level": [spec.core_level],
                "partner_levels": [[spec.partner_level]],
                "confluence_mode": [spec.confluence_mode],
                "trigger": [spec.trigger],
                "trigger_timeframe": [spec.trigger_timeframe],
            },
            "mode_rules": mode_rules,
            "report": {
                "primary_metric": "expectancy_r",
                "secondary_metrics": [
                    "profit_factor",
                    "max_drawdown_r",
                    "trade_count",
                    "total_r",
                ],
                "min_trades": 1 if spec is CI_PREPARE_REPLICA else 30,
                "multiple_testing": "warn",
                "group_by": ["core_level", "partner_levels"],
                "random_baseline": {
                    "enabled": True,
                    "n_replicas": replicas,
                    "random_state": 42,
                },
            },
        },
    }


def write_study_yaml(path: Path, mapping: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(mapping), sort_keys=False), encoding="utf-8")
    return path


def rewrite_full_spec_dataset(source_yaml: Path, dest_yaml: Path, csv_path: Path) -> Path:
    """Load the smoke spec and point dataset.path at *csv_path*."""
    payload = yaml.safe_load(Path(source_yaml).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "study" not in payload:
        raise ValueError(f"not a StudySpec: {source_yaml}")
    study = dict(payload["study"])
    dataset = dict(study.get("dataset") or {})
    dataset["path"] = str(Path(csv_path).resolve())
    study["dataset"] = dataset
    payload["study"] = study
    return write_study_yaml(dest_yaml, payload)


def window_label(spec: CellSpec) -> str:
    if spec.csv_role == "cell6":
        return f"[{CELL6_WINDOW_START_UTC.isoformat()}, {CELL6_WINDOW_END_UTC.isoformat()})"
    if spec.csv_role == "short":
        return f"[{SHORT_WINDOW_START_UTC.isoformat()}, {SHORT_WINDOW_END_UTC.isoformat()})"
    if spec.csv_role == "full":
        return "full farm CSV"
    return "synthetic multi-day 15s fixture"
