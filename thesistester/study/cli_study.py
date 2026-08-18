"""CLI handlers for ``python -m thesistester study …`` (RS3–RS5, RS-D4, SV1–SV2)."""

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
from thesistester.study.promote import StudyPromoteError, promote_study
from thesistester.study.report import StudyReportError, report_study
from thesistester.study.rollup import StudyRollupError, rollup_study
from thesistester.study.schema import StudySpecError
from thesistester.study.viewer import (
    StudyViewerError,
    discover_study_dirs,
    failed_cell_error_lines,
    format_study_catalog_table,
    split_catalog_scan_paths,
)


def add_study_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``study`` command group on the root CLI parser."""
    study_parser = subparsers.add_parser(
        "study",
        help="Research Study Runner (expand / run / report / promote / rollup / list)",
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

    promote_parser = study_sub.add_parser(
        "promote",
        help="Draft survivor StudySpec (explicit_cells); does not execute",
    )
    promote_parser.add_argument(
        "study_dir",
        type=Path,
        help="Completed study output directory (overview / expansion / spec)",
    )
    promote_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the draft StudySpec YAML",
    )
    promote_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of ranked survivor cells to include (default: 10)",
    )
    promote_parser.add_argument(
        "--metric",
        type=str,
        default=None,
        help="Ranking metric override (default: study.report.primary_metric)",
    )
    promote_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing draft StudySpec at --output",
    )
    promote_parser.add_argument(
        "--admit-tod",
        nargs="?",
        const="auto",
        choices=("auto",),
        default=None,
        help=(
            "Draft a one-cell Admit follow-up (default NY entry_rth_segment). "
            "Requires --top-n 1 or --admit-run-name. Optional --tod-group / "
            "--allow-thin. Absence keeps RS5 promote. Never executes."
        ),
    )
    promote_parser.add_argument(
        "--admit-run-name",
        type=str,
        default=None,
        help="Ranked run_name to constrain for --admit-tod (default: first ranked row)",
    )
    promote_parser.add_argument(
        "--tod-group",
        choices=(
            "entry_rth_segment",
            "entry_hour_bucket",
            "entry_30min_bucket",
        ),
        default=None,
        help=(
            "ToD grouping for --admit-tod (default: entry_rth_segment). "
            "Requires --admit-tod. Hour/30min stay CLI-only."
        ),
    )
    promote_parser.add_argument(
        "--allow-thin",
        action="store_true",
        help=(
            "Permit a thin Admit bucket (N < report.min_trades / sample_warning). "
            "Requires --admit-tod. Sets lineage.admit.thin true."
        ),
    )

    rollup_parser = study_sub.add_parser(
        "rollup",
        help="Compose per-cell WFA/validation/overfitting diagnostics (no new inference)",
    )
    rollup_parser.add_argument(
        "study_dir",
        type=Path,
        help="Completed study output directory (results_index + optional cell bundles)",
    )

    list_parser = study_sub.add_parser(
        "list",
        help="List local study directories under results/studies/ and out/ (no writes)",
    )
    list_parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        type=Path,
        default=None,
        help=(
            "Scan path (repeatable): a trusted root (prefix scan of "
            "results/studies and out), a locked prefix dir, a study dir, or "
            "another directory under cwd/store (one-level children). Extra-root "
            "refused. Default: cwd and the ThesisTester store."
        ),
    )


def dispatch_study(args: argparse.Namespace) -> int:
    """Dispatch ``study expand|run|report|promote|rollup|list``; return process exit code."""
    try:
        if args.study_command == "expand":
            return _cmd_expand(args)
        if args.study_command == "run":
            return _cmd_run(args)
        if args.study_command == "report":
            return _cmd_report(args)
        if args.study_command == "promote":
            return _cmd_promote(args)
        if args.study_command == "rollup":
            return _cmd_rollup(args)
        if args.study_command == "list":
            return _cmd_list(args)
    except StudySpecError as exc:
        print(f"StudySpec error: {exc}", file=sys.stderr)
        return 2
    except StudyReportError as exc:
        print(f"Study report error: {exc}", file=sys.stderr)
        return 2
    except StudyPromoteError as exc:
        print(f"Study promote error: {exc}", file=sys.stderr)
        return 2
    except StudyRollupError as exc:
        print(f"Study rollup error: {exc}", file=sys.stderr)
        return 2
    except StudyViewerError as exc:
        print(f"Study list error: {exc}", file=sys.stderr)
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
    for line in failed_cell_error_lines(cells, run_names):
        print(line)
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


def _cmd_promote(args: argparse.Namespace) -> int:
    result = promote_study(
        args.study_dir,
        output=args.output,
        top_n=int(args.top_n),
        metric=args.metric,
        force=bool(args.force),
        admit_tod=getattr(args, "admit_tod", None),
        admit_run_name=getattr(args, "admit_run_name", None),
        tod_group=getattr(args, "tod_group", None),
        allow_thin=bool(getattr(args, "allow_thin", False)),
    )
    print(
        f"Draft StudySpec written: {result.output_path} "
        f"({result.cell_count} survivor cell(s) by {result.primary_metric})"
    )
    if getattr(args, "admit_tod", None):
        print(
            f"Admit follow-up child: {result.study_name} "
            "(constrained re-sim; Focus ≠ Admit; no auto-execution)."
        )
    print("This is a DRAFT — edit and confirm before `study run` (no auto-execution).")
    print(f"Expand preview: python -m thesistester study expand {result.output_path}")
    return os.EX_OK


def _cmd_rollup(args: argparse.Namespace) -> int:
    result = rollup_study(args.study_dir)
    print(
        f"Study rollup: {result.study_name} — cells={result.cell_count} "
        f"wfa_present={result.wfa_present_count} "
        f"validation_present={result.validation_present_count} "
        f"overfitting_present={result.overfitting_present_count}"
    )
    print("Compose-only: no cross-cell PBO/DSR; missing batteries → not_run.")
    print(f"Artifacts: {result.paths['study.rollup.csv']}")
    print(f"           {result.paths['study.rollup.md']}")
    return os.EX_OK


def _cmd_list(args: argparse.Namespace) -> int:
    roots, extras = split_catalog_scan_paths(args.roots)
    entries = discover_study_dirs(roots, extra_dirs=extras)
    print(format_study_catalog_table(entries))
    return os.EX_OK
