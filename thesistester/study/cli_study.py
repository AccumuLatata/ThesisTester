"""CLI handlers for ``python -m thesistester study …`` (RS3–RS4)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from thesistester.study.execute import (
    cost_hint_lines,
    prepare_study_expansion,
    run_study,
)
from thesistester.study.report import StudyReportError, report_study
from thesistester.study.schema import StudySpecError


def add_study_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``study`` command group on the root CLI parser."""
    study_parser = subparsers.add_parser(
        "study",
        help="Research Study Runner (expand / run / report closed StudySpecs)",
    )
    study_sub = study_parser.add_subparsers(dest="study_command", required=True)

    expand_parser = study_sub.add_parser(
        "expand",
        help="Expand a StudySpec to experiment.yaml + factor map (no backtests)",
    )
    expand_parser.add_argument("study", type=Path, help="Path to StudySpec YAML")
    expand_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Study output directory (default: StudySpec output_dir)",
    )

    run_parser = study_sub.add_parser(
        "run",
        help="Expand and execute a StudySpec via the study-owned cell loop",
    )
    run_parser.add_argument("study", type=Path, help="Path to StudySpec YAML")
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Study output directory (default: StudySpec output_dir)",
    )
    run_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Independent worker processes (default: StudySpec workers or 1)",
    )
    run_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required when run_count >= confirm_above_runs",
    )
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore soft-resume skips and identity mismatch refuse",
    )

    report_parser = study_sub.add_parser(
        "report",
        help="Aggregate study results_index + factor map into overview CSV/MD",
    )
    report_parser.add_argument(
        "study_dir",
        type=Path,
        help="Completed study output directory (contains expansion + results_index)",
    )


def dispatch_study(args: argparse.Namespace) -> int:
    """Dispatch ``study expand|run|report``; return process exit code."""
    try:
        if args.study_command == "expand":
            return _cmd_expand(args)
        if args.study_command == "run":
            return _cmd_run(args)
        if args.study_command == "report":
            return _cmd_report(args)
    except StudySpecError as exc:
        print(f"StudySpec error: {exc}", file=sys.stderr)
        return 2
    except StudyReportError as exc:
        print(f"Study report error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Study error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"Unhandled study command: {args.study_command!r}")


def _cmd_expand(args: argparse.Namespace) -> int:
    spec, expansion, out, _base = prepare_study_expansion(
        args.study,
        output_dir=args.output_dir,
    )
    workers = int(spec["study"].get("workers", 1))
    print(f"Expanded {expansion.run_count} run(s) → {out}")
    for line in cost_hint_lines(expansion, workers=workers):
        print(line)
    print(f"Artifacts: {out / 'study.spec.yaml'}")
    print(f"           {out / 'study.expansion.json'}")
    print(f"           {out / 'experiment.yaml'}")
    print(f"Replay: python -m thesistester run {out / 'experiment.yaml'}")
    return os.EX_OK


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_study(
        args.study,
        output_dir=args.output_dir,
        workers=args.workers,
        confirm=bool(args.confirm),
        force=bool(args.force),
    )
    print(
        f"Study complete: executed {result['executed']} / {result['run_count']} "
        f"cell(s) with {result['workers']} worker(s)."
    )
    for line in result.get("cost_hints") or []:
        print(line)
    print(f"Ledger: {result['ledger_path']}")
    print(f"Results index: {result['results_index_path']}")
    ledger = result.get("ledger") or {}
    cells = ledger.get("cells") or {}
    # Scope exit-code aggregation to this expansion's run names only (orphans
    # from a prior identity must not poison a successful --force re-run).
    run_names = list(result.get("run_names") or cells.keys())
    ok = sum(1 for name in run_names if (cells.get(name) or {}).get("status") == "ok")
    failed = sum(1 for name in run_names if (cells.get(name) or {}).get("status") == "failed")
    print(f"Cell status: ok={ok} failed={failed}")
    return os.EX_OK if failed == 0 else 1


def _cmd_report(args: argparse.Namespace) -> int:
    result = report_study(args.study_dir)
    print(
        f"Study report: {result.study_name} — "
        f"ranked={len(result.ranked)} low_n={len(result.low_n)} "
        f"otf_delta={len(result.otf_delta)} "
        f"(primary={result.primary_metric}, min_trades={result.min_trades})"
    )
    if result.best_cell_suppressed:
        print("multiple_testing=error: best-cell crowning suppressed")
    print(f"Artifacts: {result.paths['study.overview.csv']}")
    print(f"           {result.paths['study.overview.md']}")
    print(f"           {result.paths['study.otf_delta.csv']}")
    return os.EX_OK
