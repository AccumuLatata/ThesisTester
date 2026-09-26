"""Bit-identical compare of two MW0 capture directories.

Full mode gates trades (every column, dtypes/unit/tz), replica bits, summary
metrics, DA5 (non-null where the reference is non-null), ledger equality
fields, and ``canonical_bundle_hash``. Ledger wall-clock timestamps are stored
but never compared.

``--pre-step`` gates only the §9 equality subset (trades + replica bits +
trade_count + expectancy_r). DA5 and canonical hash are reported but do not
fail the pre-step.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .bits import (
    DA5_KEYS,
    LEDGER_EQUALITY_KEYS,
    PRESTEP_GATES,
    SUMMARY_METRIC_KEYS,
    decode_optional_float,
)
from .io import describe_series_dtype, list_cell_ids, load_capture


@dataclass
class Diff:
    cell_id: str
    field: str
    gate: bool
    message: str


@dataclass
class CompareReport:
    diffs: list[Diff] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(
        self,
        cell_id: str,
        field: str,
        message: str,
        *,
        gate: bool,
    ) -> None:
        self.diffs.append(Diff(cell_id=cell_id, field=field, gate=gate, message=message))

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def gate_failures(self) -> list[Diff]:
        return [item for item in self.diffs if item.gate]

    @property
    def ok(self) -> bool:
        return not self.gate_failures


def _is_null_encoded(payload: Any) -> bool:
    if payload is None:
        return True
    if isinstance(payload, dict):
        return bool(payload.get("is_null")) or payload.get("hex") is None
    return False


def _encoded_hex(payload: Any) -> str | None:
    if isinstance(payload, dict):
        hex_bits = payload.get("hex")
        return None if hex_bits is None else str(hex_bits)
    if payload is None:
        return None
    return None


def compare_optional_encoded(
    left: Any,
    right: Any,
    *,
    allow_both_null: bool = True,
) -> str | None:
    left_null = _is_null_encoded(left)
    right_null = _is_null_encoded(right)
    if left_null and right_null:
        return None if allow_both_null else "both null"
    if left_null != right_null:
        return f"null mismatch left_null={left_null} right_null={right_null}"
    left_hex = _encoded_hex(left)
    right_hex = _encoded_hex(right)
    if left_hex != right_hex:
        left_f = decode_optional_float(left)
        right_f = decode_optional_float(right)
        return f"bit mismatch left_hex={left_hex} right_hex={right_hex} left={left_f!r} right={right_f!r}"
    return None


def _float_bits_equal(left: Any, right: Any) -> bool:
    left_arr = np.float64(left)
    right_arr = np.float64(right)
    left_nan = bool(np.isnan(left_arr))
    right_nan = bool(np.isnan(right_arr))
    if left_nan or right_nan:
        return left_nan and right_nan
    return int(left_arr.view(np.uint64)) == int(right_arr.view(np.uint64))


def compare_series_values(column: str, left: pd.Series, right: pd.Series) -> list[str]:
    diffs: list[str] = []
    if len(left) != len(right):
        return [f"{column}: length {len(left)} != {len(right)}"]
    if pd.api.types.is_float_dtype(left.dtype) or pd.api.types.is_float_dtype(right.dtype):
        for index, (lv, rv) in enumerate(zip(left.tolist(), right.tolist(), strict=True)):
            left_na = lv is None or pd.isna(lv)
            right_na = rv is None or pd.isna(rv)
            if left_na and right_na:
                if isinstance(lv, (float, np.floating)) and isinstance(rv, (float, np.floating)):
                    if not _float_bits_equal(lv, rv):
                        diffs.append(f"{column}[{index}]: NaN bit pattern {lv!r} != {rv!r}")
                continue
            if left_na != right_na or not _float_bits_equal(lv, rv):
                diffs.append(f"{column}[{index}]: bits {lv!r} != {rv!r}")
            if len(diffs) >= 8:
                diffs.append(f"{column}: further float mismatches omitted")
                break
        return diffs
    if isinstance(left.dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_dtype(left.dtype):
        for index, (lv, rv) in enumerate(zip(left.tolist(), right.tolist(), strict=True)):
            if pd.isna(lv) and pd.isna(rv):
                continue
            if pd.isna(lv) or pd.isna(rv) or lv != rv:
                diffs.append(
                    f"{column}[{index}]: {lv!r} != {rv!r} "
                    f"(left_tz={getattr(lv, 'tzinfo', None)!r} "
                    f"right_tz={getattr(rv, 'tzinfo', None)!r})"
                )
                if len(diffs) >= 8:
                    diffs.append(f"{column}: further timestamp mismatches omitted")
                    break
        return diffs
    unequal = left.ne(right) & ~(left.isna() & right.isna())
    if bool(unequal.any()):
        bad = [int(i) for i in list(unequal[unequal].index[:8])]
        diffs.append(f"{column}: value mismatch at rows {bad}")
    return diffs


def compare_trades(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    diffs: list[str] = []
    if list(left.columns) != list(right.columns):
        diffs.append(f"columns {list(left.columns)} != {list(right.columns)}")
    if len(left) != len(right):
        diffs.append(f"row_count {len(left)} != {len(right)}")
    shared = [column for column in left.columns if column in right.columns]
    for column in shared:
        left_desc = describe_series_dtype(left[column])
        right_desc = describe_series_dtype(right[column])
        if left_desc != right_desc:
            diffs.append(f"{column} dtype {left_desc} != {right_desc}")
        diffs.extend(compare_series_values(column, left[column], right[column]))
    return diffs


def compare_replica(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    diffs: list[str] = []
    left_bits = list(left.get("hex_bits") or [])
    right_bits = list(right.get("hex_bits") or [])
    if len(left_bits) != len(right_bits):
        diffs.append(f"replica count {len(left_bits)} != {len(right_bits)}")
    for index, (lv, rv) in enumerate(zip(left_bits, right_bits)):
        if lv != rv:
            diffs.append(f"replica[{index}] hex {lv} != {rv}")
            if len(diffs) >= 8:
                diffs.append("replica: further bit mismatches omitted")
                break
    leftover = abs(len(left_bits) - len(right_bits))
    if leftover and len(left_bits) != len(right_bits):
        diffs.append(f"replica tail length differs by {leftover}")
    return diffs


def _gate_for(field: str, *, pre_step: bool) -> bool:
    if not pre_step:
        return True
    return field in PRESTEP_GATES


def compare_captures(
    left_root: Path,
    right_root: Path,
    *,
    pre_step: bool = False,
    cell_ids: Iterable[str] | None = None,
) -> CompareReport:
    report = CompareReport()
    left_ids = list_cell_ids(left_root)
    right_ids = list_cell_ids(right_root)
    wanted = list(cell_ids) if cell_ids is not None else sorted(set(left_ids) | set(right_ids))
    if not wanted:
        report.add("-", "cells", "no cell directories in either capture", gate=True)
        return report
    if pre_step:
        report.note(
            "pre-step gates (§9): trades (every column, dtypes/unit/tz), "
            "replica_expectancies bits, trade_count, expectancy_r. "
            "DA5 and canonical_bundle_hash are reported only."
        )
    else:
        report.note(
            "full MW equality: trades, replica bits, summary, DA5 "
            "(non-null where reference non-null), ledger status/error/bundle_path, "
            "canonical_bundle_hash. Ledger started_at/finished_at excluded."
        )

    for cell_id in wanted:
        left_dir = Path(left_root) / "cells" / cell_id
        right_dir = Path(right_root) / "cells" / cell_id
        if not left_dir.is_dir() or not right_dir.is_dir():
            report.add(
                cell_id,
                "cells",
                f"missing directory left={left_dir.is_dir()} right={right_dir.is_dir()}",
                gate=True,
            )
            continue
        left = load_capture(left_dir)
        right = load_capture(right_dir)

        trade_diffs = compare_trades(left["trades"], right["trades"])
        for message in trade_diffs:
            report.add(cell_id, "trades", message, gate=_gate_for("trades", pre_step=pre_step))

        replica_diffs = compare_replica(left["replica"], right["replica"])
        for message in replica_diffs:
            report.add(
                cell_id,
                "replica_expectancies",
                message,
                gate=_gate_for("replica_expectancies", pre_step=pre_step),
            )

        for key in SUMMARY_METRIC_KEYS:
            left_val = left["summary"].get(key)
            right_val = right["summary"].get(key)
            if key == "trade_count":
                if left_val != right_val:
                    report.add(
                        cell_id,
                        "trade_count",
                        f"{left_val!r} != {right_val!r}",
                        gate=_gate_for("trade_count", pre_step=pre_step),
                    )
                continue
            mismatch = compare_optional_encoded(left_val, right_val)
            if mismatch:
                report.add(
                    cell_id,
                    key,
                    mismatch,
                    gate=_gate_for(key, pre_step=pre_step),
                )

        for key in DA5_KEYS:
            left_val = left["da5"].get(key)
            right_val = right["da5"].get(key)
            if _is_null_encoded(left_val) and _is_null_encoded(right_val):
                continue
            if _is_null_encoded(left_val) and not _is_null_encoded(right_val):
                # Reference (left) is null: right may be non-null; still a full-mode miss.
                report.add(
                    cell_id,
                    key,
                    f"reference null, other={right_val!r}",
                    gate=not pre_step,
                )
                continue
            if not _is_null_encoded(left_val) and _is_null_encoded(right_val):
                report.add(
                    cell_id,
                    key,
                    "DA5 null where reference is non-null",
                    gate=not pre_step,
                )
                continue
            mismatch = compare_optional_encoded(left_val, right_val)
            if mismatch:
                report.add(cell_id, key, mismatch, gate=not pre_step)

        left_hash = left["canonical_bundle_hash"]
        right_hash = right["canonical_bundle_hash"]
        if left_hash != right_hash:
            report.add(
                cell_id,
                "canonical_bundle_hash",
                f"{left_hash} != {right_hash}",
                gate=not pre_step,
            )

        if not pre_step:
            for key in LEDGER_EQUALITY_KEYS:
                if left["ledger"].get(key) != right["ledger"].get(key):
                    report.add(
                        cell_id,
                        f"ledger.{key}",
                        f"{left['ledger'].get(key)!r} != {right['ledger'].get(key)!r}",
                        gate=True,
                    )
    return report


def format_report(report: CompareReport) -> str:
    lines = list(report.notes)
    if report.ok and not report.diffs:
        lines.append("OK: captures are bit-identical on every gated field.")
        return "\n".join(lines)
    if report.ok and report.diffs:
        lines.append("OK: gated fields match. Informational differences:")
    else:
        lines.append("FAIL: gated bit differences:")
    for diff in report.diffs:
        tag = "GATE" if diff.gate else "INFO"
        lines.append(f"  [{tag}] {diff.cell_id} {diff.field}: {diff.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path, help="Reference capture directory")
    parser.add_argument("right", type=Path, help="Candidate capture directory")
    parser.add_argument(
        "--pre-step",
        action="store_true",
        help="Gate only §9 pre-step subset (trades + replica bits + trade_count + E)",
    )
    parser.add_argument(
        "--cells",
        default="",
        help="Optional comma-separated cell ids (default: union of both dirs)",
    )
    args = parser.parse_args(argv)
    cell_ids = [part.strip() for part in args.cells.split(",") if part.strip()] or None
    report = compare_captures(args.left, args.right, pre_step=args.pre_step, cell_ids=cell_ids)
    text = format_report(report)
    print(text)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
