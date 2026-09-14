"""QI-11 §2.2 / §10 mutation sample recipe (B-4 / QI-11-04).

Copies ``thesistester/`` into a scratch package, swaps one comparison
operator at a time (12 sites per file), and runs the own-file suite from a
neutral cwd with ``--import-mode=importlib``.

    python -m tests.fixtures.mutation.mutate_sample
    python -m tests.fixtures.mutation.mutate_sample --write-baseline

Timeouts count as killed. Sites on ``raise`` lines are recorded and excluded
from the adjusted rate (QI-11 ValueError-string / equivalent mutants).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "thesistester"
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

SITE_LIMIT = 12
TIMEOUT_SECONDS = 180

_OP_SWAPS = {
    "==": "!=",
    "!=": "==",
    "<": ">",
    ">": "<",
    "<=": ">=",
    ">=": "<=",
}

TARGETS: dict[str, dict[str, Any]] = {
    "thesistester/engine/backtest.py": {
        "tests": [
            "tests/test_phase5_backtest.py",
            "tests/test_ah1_session_flatten.py",
            "tests/test_golden_master.py",
        ],
        "priority_needles": (
            "denominator > 0",
            "path_open_proximity",
            'entry_model == "next_bar_open"',
        ),
        # C-19 moved P7/P4/P6 comparison sites out of simulate_trades.
        # Keep helpers in the named surface so the 12-site sample still
        # covers path-proximity, next_bar_open BE, and P0 validation (B-4).
        "function_names": (
            "_intrabar_diagnostic",
            "_exit_management_diagnostic",
            "_direction_collision_diagnostic",
            "_validate_simulate_trades",
            "_admit_entry_candidates",
            "_exposure_skip_for_candidate",
            "_finalize_exit_walk",
            "walk_trade_exit",
            "simulate_trades",
        ),
        # walk_trade_exit lives on the R22 boundary (sim_core), not backtest.py.
        "source_modules": ("thesistester/engine/sim_core.py",),
    },
    "thesistester/analytics/walk_forward.py": {
        "tests": [
            "tests/test_walk_forward.py",
            "tests/test_otf_integration.py",
        ],
        "priority_needles": (
            'otf_history_policy == "fold_local"',
            'overlap_policy == "reject"',
            "train_expectancy > 1e-12",
            'fold_mode == "sessions"',
        ),
        # C-17 moved P0/P5 comparison sites out of run_walk_forward_sl_tp.
        # Keep helpers in the named surface so the 12-site sample still
        # covers fold/OTF policy and overlap-reject (B-4 / QI-11-04).
        "function_names": (
            "normalize_otf_history_policy",
            "_otf_source_for_fold",
            "_slice_signals",
            "_validate_walk_forward_run",
            "_train_fold_grid",
            "_stitch_walk_forward_oos",
            "_assemble_walk_forward_result",
            "run_walk_forward_sl_tp",
        ),
    },
}


@dataclass(frozen=True)
class ComparisonSite:
    index: int
    lineno: int
    column: int
    op: str
    replacement: str
    line: str
    on_raise_line: bool
    relpath: str = ""


def _function_line_ranges(source: str, names: tuple[str, ...]) -> list[tuple[int, int]]:
    tree = ast.parse(source)
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.lineno, end))
    return ranges


def _in_ranges(lineno: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= lineno <= end for start, end in ranges)


def _collect_sites(
    source: str,
    *,
    priority_needles: tuple[str, ...] = (),
    function_names: tuple[str, ...] = (),
    site_limit: int | None = SITE_LIMIT,
    relpath: str = "",
) -> list[ComparisonSite]:
    readline = BytesIO(source.encode("utf-8")).readline
    tokens = list(tokenize.tokenize(readline))
    lines = source.splitlines()
    found: list[ComparisonSite] = []
    for token in tokens:
        if token.type != tokenize.OP or token.string not in _OP_SWAPS:
            continue
        lineno, column = token.start
        line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        found.append(
            ComparisonSite(
                index=len(found),
                lineno=lineno,
                column=column,
                op=token.string,
                replacement=_OP_SWAPS[token.string],
                line=line.strip(),
                on_raise_line="raise " in line,
                relpath=relpath,
            )
        )
    if function_names:
        ranges = _function_line_ranges(source, function_names)
        found = [site for site in found if _in_ranges(site.lineno, ranges)]
    priority: list[ComparisonSite] = []
    rest: list[ComparisonSite] = []
    for site in found:
        if any(needle in site.line for needle in priority_needles):
            priority.append(site)
        else:
            rest.append(site)
    selected = priority + rest
    if site_limit is not None:
        selected = selected[:site_limit]
    return [
        ComparisonSite(
            index=index,
            lineno=site.lineno,
            column=site.column,
            op=site.op,
            replacement=site.replacement,
            line=site.line,
            on_raise_line=site.on_raise_line,
            relpath=site.relpath,
        )
        for index, site in enumerate(selected)
    ]


def _target_source_modules(relpath: str, spec: dict[str, Any]) -> tuple[str, ...]:
    modules: list[str] = []
    for path in (relpath, *tuple(spec.get("source_modules", ()))):
        if path not in modules:
            modules.append(path)
    return tuple(modules)


def collect_target_sites(relpath: str, spec: dict[str, Any]) -> list[ComparisonSite]:
    """Named-surface sites for one TARGETS entry (may span companion modules)."""
    needles = tuple(spec.get("priority_needles", ()))
    names = tuple(spec.get("function_names", ()))
    found: list[ComparisonSite] = []
    for path in _target_source_modules(relpath, spec):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        found.extend(
            _collect_sites(
                source,
                priority_needles=(),
                function_names=names,
                site_limit=None,
                relpath=path,
            )
        )
    return _collect_sites_from_found(found, priority_needles=needles)


def _collect_sites_from_found(
    found: list[ComparisonSite],
    *,
    priority_needles: tuple[str, ...],
) -> list[ComparisonSite]:
    priority: list[ComparisonSite] = []
    rest: list[ComparisonSite] = []
    for site in found:
        if any(needle in site.line for needle in priority_needles):
            priority.append(site)
        else:
            rest.append(site)
    selected = (priority + rest)[:SITE_LIMIT]
    return [
        ComparisonSite(
            index=index,
            lineno=site.lineno,
            column=site.column,
            op=site.op,
            replacement=site.replacement,
            line=site.line,
            on_raise_line=site.on_raise_line,
            relpath=site.relpath,
        )
        for index, site in enumerate(selected)
    ]


def _apply_site(source: str, site: ComparisonSite) -> str:
    lines = source.splitlines(keepends=True)
    line = lines[site.lineno - 1]
    prefix = line[: site.column]
    suffix = line[site.column + len(site.op) :]
    lines[site.lineno - 1] = f"{prefix}{site.replacement}{suffix}"
    return "".join(lines)


def _run_suite(
    *,
    mutant_pkg: Path,
    tests: list[str],
    cwd: Path,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{mutant_pkg}{os.pathsep}{REPO_ROOT}"
    env["THESISTESTER_STORE_DIR"] = str(cwd / "store")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--import-mode=importlib",
        "--rootdir",
        str(REPO_ROOT),
        *[str(REPO_ROOT / test) for test in tests],
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"killed": True, "reason": "timeout", "returncode": None}
    killed = completed.returncode != 0
    return {
        "killed": killed,
        "reason": "failed" if killed else "survived",
        "returncode": completed.returncode,
    }


def _evaluate_module(relpath: str, tests: list[str], scratch: Path) -> dict[str, Any]:
    spec = TARGETS[relpath]
    sites = collect_target_sites(relpath, spec)
    sources = {
        path: (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in _target_source_modules(relpath, spec)
    }
    pkg_root = scratch / "pkg"
    shutil.copytree(PACKAGE_DIR, pkg_root / "thesistester", dirs_exist_ok=True)
    cwd = scratch / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    killed = 0
    excluded = 0
    scored = 0
    for site in sites:
        site_path = site.relpath or relpath
        record = {
            "index": site.index,
            "lineno": site.lineno,
            "op": f"{site.op}->{site.replacement}",
            "line": site.line,
            "relpath": site_path,
        }
        if site.on_raise_line:
            excluded += 1
            records.append({**record, "excluded": True, "reason": "raise_line"})
            continue
        scored += 1
        mutant_file = pkg_root / site_path
        mutant_file.write_text(_apply_site(sources[site_path], site), encoding="utf-8")
        result = _run_suite(mutant_pkg=pkg_root, tests=tests, cwd=cwd)
        mutant_file.write_text(sources[site_path], encoding="utf-8")
        if result["killed"]:
            killed += 1
        records.append(
            {
                **record,
                "excluded": False,
                "killed": result["killed"],
                "reason": result["reason"],
            }
        )

    raw_total = scored + excluded
    raw_pct = (killed / raw_total * 100.0) if raw_total else 0.0
    adj_pct = (killed / scored * 100.0) if scored else 0.0
    return {
        "tests": tests,
        "sites_raw": raw_total,
        "sites_scored": scored,
        "sites_excluded": excluded,
        "killed": killed,
        "survived": scored - killed,
        "raw_pct": round(raw_pct, 1),
        "adjusted_pct": round(adj_pct, 1),
        "sites": records,
    }


def run_sample() -> dict[str, Any]:
    modules: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="qi11-mut-") as raw:
        scratch = Path(raw)
        for relpath, spec in TARGETS.items():
            modules[relpath] = _evaluate_module(
                relpath, spec["tests"], scratch / relpath.replace("/", "_")
            )
    report = {
        "recipe": "QI-11 §2.2 comparison-swap sample (B-4 / QI-11-04)",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "site_limit": SITE_LIMIT,
        "timeout_seconds": TIMEOUT_SECONDS,
        "modules": modules,
        "gate": {
            "minimum_pct": 70.0,
            "target_pct": 80.0,
            "backtest_adjusted_pct": modules["thesistester/engine/backtest.py"]["adjusted_pct"],
            "walk_forward_adjusted_pct": modules["thesistester/analytics/walk_forward.py"][
                "adjusted_pct"
            ],
        },
    }
    return report


def _meets_gate(report: dict[str, Any]) -> bool:
    gate = report["gate"]
    return (
        gate["backtest_adjusted_pct"] >= gate["minimum_pct"]
        and gate["walk_forward_adjusted_pct"] >= gate["minimum_pct"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite tests/fixtures/mutation/baseline.json with this run.",
    )
    args = parser.parse_args()
    report = run_sample()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text)
    if args.write_baseline:
        BASELINE_PATH.write_text(text, encoding="utf-8")
        print(f"Wrote {BASELINE_PATH}")
    if not _meets_gate(report):
        print(
            "QI-11-04 gate failed: backtest and walk_forward own-file "
            "adjusted kill rate must be ≥ 70 %.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
