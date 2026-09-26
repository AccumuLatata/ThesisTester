"""MW0 synthetic-fixture recorder. Compare-only unless ``--regenerate``.

Does not touch ``tests/fixtures/golden/``. Real-CSV MW0 goldens are not
recorded by this script; those wait for the farm §9 pre-step.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .capture import CaptureAbort, capture_study_cell
from .cells import CI_CELL6_SHAPE, CI_PREPARE_REPLICA
from .compare import compare_captures, format_report
from .compat import ensure_thesistester_import_path, package_identity, resolve_all_hooks
from .generate_synthetic import default_synthetic_path, write_synthetic_csv

FIXTURE_ROOT = Path(__file__).resolve().parent
GOLDEN_ROOT = FIXTURE_ROOT / "synthetic_golden"
CI_CELLS = (CI_PREPARE_REPLICA, CI_CELL6_SHAPE)


def record_synthetic(dest: Path, *, run_label: str) -> Path:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    committed = default_synthetic_path()
    if dest.resolve() == GOLDEN_ROOT.resolve():
        # Golden regen uses the committed fixture. Do not copy the CSV
        # into synthetic_golden/ (that path is not the CI input).
        generated = write_synthetic_csv(dest / "_regen_synthetic_mnq_15s.csv")
        if committed.is_file() and committed.read_bytes() != generated.read_bytes():
            generated.unlink(missing_ok=True)
            raise CaptureAbort(
                "committed synthetic_mnq_15s.csv differs from the generator; "
                "stop and report — do not record from a drifted fixture"
            )
        if not committed.is_file():
            shutil.move(str(generated), committed)
        else:
            generated.unlink(missing_ok=True)
        csv_path = committed
    else:
        # Compare/live runs write under dest. Never overwrite the committed fixture.
        csv_path = write_synthetic_csv(dest / "synthetic_mnq_15s.csv")
        if committed.is_file() and committed.read_bytes() != csv_path.read_bytes():
            raise CaptureAbort(
                "committed synthetic_mnq_15s.csv differs from the generator; "
                "stop and report — do not record from a drifted fixture"
            )
    for spec in CI_CELLS:
        capture_study_cell(
            spec,
            csv_path=csv_path,
            output_root=dest,
            run_label=run_label,
        )
    identity = package_identity()
    manifest = {
        "suite": "mw0_synthetic",
        "run_label": run_label,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "csv": str(csv_path.relative_to(FIXTURE_ROOT))
        if csv_path.is_relative_to(FIXTURE_ROOT)
        else str(csv_path),
        "cells": [spec.cell_id for spec in CI_CELLS],
        "captured": [f"cells/{spec.cell_id}" for spec in CI_CELLS],
        "thesistester_version": identity.get("thesistester_version"),
        "farm_production_commit": identity.get("farm_production_commit"),
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dest


def compare_against_golden(candidate: Path) -> int:
    if not GOLDEN_ROOT.is_dir():
        print(
            "STOP AND REPORT: synthetic golden is missing; "
            "re-run with --regenerate at the MW0 base commit.",
            file=sys.stderr,
        )
        return 2
    report = compare_captures(GOLDEN_ROOT, candidate, pre_step=False)
    print(format_report(report))
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Write the committed synthetic golden. Default is compare-only.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Candidate capture dir for compare-only (default: a temp run under /tmp)",
    )
    args = parser.parse_args(argv)
    ensure_thesistester_import_path()
    resolve_all_hooks()
    try:
        if args.regenerate:
            record_synthetic(GOLDEN_ROOT, run_label="mw0-synthetic-golden")
            print(f"regenerated {GOLDEN_ROOT}")
            return 0
        dest = args.output_dir
        if dest is None:
            dest = Path("/tmp/mw0_synthetic_compare")
        record_synthetic(dest, run_label="mw0-synthetic-compare")
        return compare_against_golden(dest)
    except CaptureAbort as exc:
        print(f"STOP AND REPORT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
