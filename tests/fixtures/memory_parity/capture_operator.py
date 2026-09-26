"""§9.3 operator script: slice the farm CSV and capture MW0 cells.

Flag-free, one process. Works against current main and, via PYTHONPATH, the
farm production commit ``59a4652`` (bundles there do not persist
``replica_expectancies``; this script hooks ``vs_random_benchmark`` at import
time). ``python -m`` from this checkout would otherwise shadow a
``59a4652`` worktree with cwd; the operator lifts that worktree to
``sys.path[0]`` and aborts if the imported package is not that tree.

Invocations are documented in ``tests/fixtures/memory_parity/README.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .cells import FULL_CELL, parse_cell_selector
from .compat import (
    FARM_PRODUCTION_COMMIT,
    ensure_thesistester_import_path,
    package_identity,
    resolve_all_hooks,
)
from .capture import CaptureAbort, capture_study_cell
from .slice_csv import (
    CELL6_SLICE_NAME,
    CELL6_WINDOW_END_UTC,
    CELL6_WINDOW_START_UTC,
    SHORT_SLICE_NAME,
    SHORT_WINDOW_END_UTC,
    SHORT_WINDOW_START_UTC,
    slice_quantower_csv_utc,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True, help="Farm Quantower 15s MNQ CSV")
    parser.add_argument("--output-dir", type=Path, required=True, help="Capture root directory")
    parser.add_argument(
        "--cells",
        required=True,
        help="short | full | all | comma list of 1-6 / cell ids",
    )
    parser.add_argument("--run-label", required=True, help="Operator label written into meta")
    parser.add_argument(
        "--full-spec",
        type=Path,
        default=None,
        help="Override path to progB_smoke_ONH_SMA50_5min.yaml",
    )
    return parser.parse_args(argv)


def _csv_for_cell(spec, *, csv: Path, slices: dict[str, Path]) -> Path:
    if spec.csv_role == "full":
        return csv
    if spec.csv_role == "cell6":
        return slices["cell6"]
    if spec.csv_role == "short":
        return slices["short"]
    return csv


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ensure_thesistester_import_path()
    resolve_all_hooks()
    cells = parse_cell_selector(args.cells)
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    csv = Path(args.csv).resolve()
    if not csv.is_file():
        raise SystemExit(f"--csv is not a file: {csv}")

    slice_dir = output / "slices"
    slices: dict[str, Path] = {}
    slice_stats: dict[str, object] = {}
    captured: list[str] = []
    try:
        if any(spec.csv_role == "short" for spec in cells):
            dest = slice_dir / SHORT_SLICE_NAME
            slice_stats["short"] = slice_quantower_csv_utc(
                csv,
                dest,
                start_utc=SHORT_WINDOW_START_UTC,
                end_utc=SHORT_WINDOW_END_UTC,
            )
            slices["short"] = dest
        if any(spec.csv_role == "cell6" for spec in cells):
            source = slices.get("short", csv)
            dest = slice_dir / CELL6_SLICE_NAME
            slice_stats["cell6"] = slice_quantower_csv_utc(
                source,
                dest,
                start_utc=CELL6_WINDOW_START_UTC,
                end_utc=CELL6_WINDOW_END_UTC,
            )
            slices["cell6"] = dest

        for spec in cells:
            cell_csv = _csv_for_cell(spec, csv=csv, slices=slices)
            print(f"capturing {spec.cell_id} from {cell_csv}", flush=True)
            dest = capture_study_cell(
                spec,
                csv_path=cell_csv,
                output_root=output,
                run_label=args.run_label,
                full_spec_path=args.full_spec,
            )
            captured.append(str(dest))
            print(f"wrote {dest}", flush=True)
    except (CaptureAbort, ValueError) as exc:
        print(f"STOP AND REPORT: {exc}", file=sys.stderr)
        return 2

    manifest = {
        "run_label": args.run_label,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "csv": str(csv),
        "cells": [spec.cell_id for spec in cells],
        "slices": {key: str(path) for key, path in slices.items()},
        "slice_stats": slice_stats,
        "captured": captured,
        "farm_production_commit": FARM_PRODUCTION_COMMIT,
        "full_cell_id": FULL_CELL.cell_id,
        **package_identity(),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
