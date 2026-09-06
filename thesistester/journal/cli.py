"""CLI handlers for ``python -m thesistester journal …`` (TJ4 / TJ6 / TJ7)."""

from __future__ import annotations

import argparse
from pathlib import Path

from thesistester.journal.counterfactual import counterfactual_files
from thesistester.journal.levels import attribute_files
from thesistester.journal.reconcile import reconcile_files
from thesistester.journal.schema import (
    DEFAULT_CF_K,
    DEFAULT_CF_SEED,
    DEFAULT_JOURNAL_RISK_TICKS,
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    JOIN_RESOLUTION_15S,
    JournalIngestError,
)


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
        help="Include manual FillRecord rows in pairing only (default: exclude). "
        "AMP recon stays imported-only",
    )
    reconcile_parser.add_argument(
        "--journal-risk-ticks",
        type=int,
        default=DEFAULT_JOURNAL_RISK_TICKS,
        help="Declared journal risk in ticks (default: 10)",
    )
    attribute_parser = journal_sub.add_parser(
        "attribute",
        help="Attribute journal entries to an already-built 1m levels frame",
    )
    attribute_parser.add_argument(
        "--trades",
        type=Path,
        required=True,
        help="Journal trades parquet/CSV (typically journal_trades.parquet)",
    )
    attribute_parser.add_argument(
        "--levels",
        type=Path,
        required=True,
        help="Already-built 1-minute levels frame (parquet/CSV). Not recomputed",
    )
    attribute_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for journal_attribution.parquet + attribution.json "
        "(must not be results/studies/)",
    )
    attribute_parser.add_argument(
        "--levels-settings",
        type=Path,
        default=None,
        help="Optional YAML/JSON levels settings for closed_level_token_set "
        "(default: DEFAULT_LEVELS_SETTINGS)",
    )
    attribute_parser.add_argument(
        "--level-tolerance-ticks",
        type=float,
        default=DEFAULT_LEVEL_TOLERANCE_TICKS,
        help="Nearby-token tolerance in ticks (default: 10)",
    )
    attribute_parser.add_argument(
        "--tag-tolerance-ticks",
        type=float,
        default=DEFAULT_TAG_TOLERANCE_TICKS,
        help="Tag-alignment tolerance in ticks (default: 10)",
    )
    attribute_parser.add_argument(
        "--allow-unreconciled",
        action="store_true",
        help="Allow days that are not reconciled (default: refuse)",
    )
    cf_parser = journal_sub.add_parser(
        "counterfactual",
        help="Replay journal entries under fixed brackets, a direction null, and declared rules",
    )
    cf_parser.add_argument(
        "--trades",
        type=Path,
        required=True,
        help="Journal trades parquet/CSV (typically journal_trades.parquet)",
    )
    cf_parser.add_argument(
        "--bars",
        type=Path,
        required=True,
        help="Already-loaded 15s OHLCV frame (parquet/CSV). Not derived here",
    )
    cf_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for journal_counterfactuals.parquet + counterfactual.json "
        "(must not be results/studies/)",
    )
    cf_parser.add_argument(
        "--ticks",
        type=Path,
        default=None,
        help="Optional Quantower Last prints (required when --resolution tick)",
    )
    cf_parser.add_argument(
        "--brackets",
        type=Path,
        default=None,
        help="Optional YAML/JSON brackets list (default: 10/10, 10/20, 20/20)",
    )
    cf_parser.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Optional YAML/JSON declared JournalRule list",
    )
    cf_parser.add_argument(
        "--resolution",
        default=JOIN_RESOLUTION_15S,
        help="15s or tick (default: 15s). Never mix resolutions in one mean",
    )
    cf_parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_CF_SEED,
        help="Direction-shuffle seed (default: 0). The only RNG in TJ7",
    )
    cf_parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_CF_K,
        help="Direction-shuffle draws (default: 1000)",
    )
    cf_parser.add_argument(
        "--allow-unreconciled",
        action="store_true",
        help="Allow days that are not reconciled (default: refuse)",
    )


def dispatch_journal(args: argparse.Namespace) -> int:
    """Dispatch ``journal reconcile`` / ``journal attribute``."""
    if args.journal_command == "reconcile":
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
    if args.journal_command == "attribute":
        try:
            paths = attribute_files(
                trades=args.trades,
                levels=args.levels,
                output_dir=args.output_dir,
                levels_settings=args.levels_settings,
                level_tolerance_ticks=float(args.level_tolerance_ticks),
                tag_tolerance_ticks=float(args.tag_tolerance_ticks),
                allow_unreconciled=bool(args.allow_unreconciled),
            )
        except JournalIngestError as exc:
            print(f"journal attribute failed: {exc}")
            return 2
        print(f"Wrote {paths['journal_attribution.parquet']}")
        print(f"      {paths['attribution.json']}")
        return 0
    if args.journal_command == "counterfactual":
        try:
            paths = counterfactual_files(
                trades=args.trades,
                bars=args.bars,
                output_dir=args.output_dir,
                ticks=args.ticks,
                brackets=args.brackets,
                rules=args.rules,
                resolution=str(args.resolution),
                seed=int(args.seed),
                k=int(args.k),
                allow_unreconciled=bool(args.allow_unreconciled),
            )
        except (JournalIngestError, ValueError) as exc:
            print(f"journal counterfactual failed: {exc}")
            return 2
        print(f"Wrote {paths['journal_counterfactuals.parquet']}")
        print(f"      {paths['counterfactual.json']}")
        return 0
    raise AssertionError(f"Unhandled journal command: {args.journal_command!r}")
