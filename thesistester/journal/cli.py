"""CLI handlers for ``python -m thesistester journal …`` (TJ4)."""

from __future__ import annotations

import argparse
from pathlib import Path

from thesistester.journal.reconcile import reconcile_files
from thesistester.journal.schema import DEFAULT_JOURNAL_RISK_TICKS, JournalIngestError


def add_journal_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the additive ``journal`` command group. Does not alter ``run`` / ``study``."""
    journal_parser = subparsers.add_parser(
        "journal",
        help="Post-trade journal ingest (TradesViz + AMP). Does not run studies.",
    )
    journal_sub = journal_parser.add_subparsers(dest="journal_command", required=True)
    reconcile_parser = journal_sub.add_parser(
        "reconcile",
        help="Pair executions, reconcile AMP statements, write journal/v1 artifacts",
    )
    reconcile_parser.add_argument(
        "--executions",
        type=Path,
        required=True,
        help="TradesViz executions CSV (profile tradesviz_executions)",
    )
    reconcile_parser.add_argument(
        "--statements",
        type=Path,
        nargs="+",
        required=True,
        help="AMP Daily Statement PDF or redacted text extract (repeatable)",
    )
    reconcile_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for reconcile.json + journal_trades.parquet "
        "(must not be results/studies/)",
    )
    reconcile_parser.add_argument(
        "--include-manual",
        action="store_true",
        help="Include manual FillRecord rows in pairing (default: exclude)",
    )
    reconcile_parser.add_argument(
        "--journal-risk-ticks",
        type=int,
        default=DEFAULT_JOURNAL_RISK_TICKS,
        help="Declared journal risk in ticks (default: 10)",
    )


def dispatch_journal(args: argparse.Namespace) -> int:
    """Dispatch ``journal reconcile``."""
    if args.journal_command != "reconcile":
        raise AssertionError(f"Unhandled journal command: {args.journal_command!r}")
    try:
        paths = reconcile_files(
            executions=args.executions,
            statements=args.statements,
            output_dir=args.output_dir,
            include_manual=bool(args.include_manual),
            journal_risk_ticks=int(args.journal_risk_ticks),
        )
    except JournalIngestError as exc:
        print(f"journal reconcile failed: {exc}")
        return 2
    print(f"Wrote {paths['reconcile.json']}")
    print(f"      {paths['journal_trades.parquet']}")
    return 0
