#!/usr/bin/env python3
"""Informational quality-metrics harness for the QI series (QI-0).

Reproduces the counters in ``docs/QUALITY_INVESTIGATION_PLAN.md`` §A.1
(``radon`` cyclomatic complexity / maintainability index, ``vulture``
dead-code candidates, ``rg`` smell/coupling counters, LOC) and emits a
single JSON document.

This script is **informational and non-blocking**. It is not a CI job
(QR owns gates). It does not interpret metrics as findings.

Usage (repo root)::

    python scripts/quality_metrics.py
    python scripts/quality_metrics.py --output /tmp/qi-metrics.json

Requires: ``radon``, ``vulture``, and ``rg`` (ripgrep) on ``PATH``.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Exclusive module → slice ownership. Every ``.py`` under ``thesistester/``,
# ``pages/``, ``scripts/``, and ``examples/`` maps to exactly one slice.
# ``app.py`` (repo root) is included because plan §A.2 assigns it to QI-10.
# ``scripts/quality_metrics.py`` is the §1.2 QI-0 harness exception.
#
# Package ``__init__.py`` files that re-export more than one slice are
# assigned to the slice that owns the majority of the re-exported
# implementation; the minority is a Handoff, not dual ownership.
_OWNERSHIP_PREFIXES: tuple[tuple[str, str], ...] = (
    ("thesistester/data/", "QI-1"),
    ("thesistester/persistence/local_store.py", "QI-1"),
    ("thesistester/persistence/__init__.py", "QI-1"),
    ("thesistester/config.py", "QI-1"),
    ("pages/1_Data.py", "QI-1"),
    ("thesistester/levels/", "QI-2"),
    ("thesistester/visualization/levels_chart.py", "QI-2"),
    ("pages/2_Levels.py", "QI-2"),
    ("thesistester/setup.py", "QI-3"),
    ("thesistester/engine/signals.py", "QI-3"),
    ("thesistester/engine/signals_3c.py", "QI-3"),
    ("thesistester/engine/confluence.py", "QI-3"),
    ("thesistester/engine/anchor_confluence.py", "QI-3"),
    ("thesistester/engine/naked.py", "QI-3"),
    ("thesistester/engine/candidate_level.py", "QI-3"),
    ("thesistester/engine/otf.py", "QI-3"),
    ("thesistester/engine/otf_filter.py", "QI-3"),
    ("thesistester/engine/otf_integration.py", "QI-3"),
    ("thesistester/engine/__init__.py", "QI-3"),
    ("thesistester/visualization/signals_chart.py", "QI-3"),
    ("thesistester/visualization/chart_window.py", "QI-3"),
    ("pages/3_Setup_Builder.py", "QI-3"),
    ("pages/6_Signals.py", "QI-3"),
    ("thesistester/engine/backtest.py", "QI-4"),
    ("thesistester/engine/sim_core.py", "QI-4"),
    ("thesistester/engine/intrabar.py", "QI-4"),
    ("thesistester/engine/exit_management.py", "QI-4"),
    ("thesistester/entry_window_policy.py", "QI-4"),
    ("thesistester/execution_defaults.py", "QI-4"),
    ("thesistester/analytics/metrics.py", "QI-4"),
    ("thesistester/analytics/entry_window.py", "QI-4"),
    ("thesistester/visualization/backtest_chart.py", "QI-4"),
    ("thesistester/visualization/trade_review_chart.py", "QI-4"),
    ("thesistester/visualization/trade_review_export.py", "QI-4"),
    ("thesistester/visualization/__init__.py", "QI-4"),
    ("pages/7_Backtest.py", "QI-4"),
    ("thesistester/analytics/", "QI-5"),
    ("pages/8_Grid_Search.py", "QI-5"),
    ("pages/9_Time_Analysis.py", "QI-5"),
    ("pages/10_Validation.py", "QI-5"),
    ("pages/13_Portfolio.py", "QI-5"),
    ("thesistester/api.py", "QI-6"),
    ("thesistester/cli.py", "QI-6"),
    ("thesistester/__main__.py", "QI-6"),
    ("thesistester/__init__.py", "QI-6"),
    ("thesistester/research_identity.py", "QI-6"),
    ("thesistester/research_bundle.py", "QI-6"),
    ("thesistester/reporting.py", "QI-6"),
    ("thesistester/classic_context.py", "QI-6"),
    ("thesistester/classic_export.py", "QI-6"),
    ("thesistester/classic_ledger.py", "QI-6"),
    ("thesistester/classic_proposal.py", "QI-6"),
    ("thesistester/classic_record.py", "QI-6"),
    ("thesistester/app_state.py", "QI-6"),
    ("thesistester/persistence/execution_artifacts.py", "QI-6"),
    ("pages/11_Report_Export.py", "QI-6"),
    ("pages/12_Research_Bundles.py", "QI-6"),
    ("thesistester/study/", "QI-7"),
    ("pages/15_Studies.py", "QI-7"),
    ("pages/16_Study_Observatory.py", "QI-7"),
    ("examples/studies/", "QI-7"),
    ("thesistester/journal/", "QI-8"),
    ("pages/17_Journal.py", "QI-8"),
    ("examples/journal/", "QI-8"),
    ("thesistester/assistant/", "QI-9"),
    ("pages/14_Research_Assistant.py", "QI-9"),
    ("thesistester/classic_nav.py", "QI-10"),
    ("thesistester/timezone_display.py", "QI-10"),
    ("app.py", "QI-10"),
    ("scripts/quality_metrics.py", "QI-0"),
    ("scripts/", "QI-12"),
)


def _run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"required tool {args[0]!r} is not on PATH "
            "(need git, rg, radon, and vulture for a full run)"
        ) from exc


def _physical_loc(paths: list[Path]) -> int:
    """Physical line count (``splitlines``), matching ``wc -l`` on newline-terminated files."""
    return sum(
        len(path.read_text(encoding="utf-8", errors="replace").splitlines()) for path in paths
    )


def _list_py(root: Path, rel: str) -> list[Path]:
    base = root / rel
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _git_meta(root: Path) -> dict[str, str]:
    sha = _run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    short = _run(["git", "rev-parse", "--short", "HEAD"], cwd=root).stdout.strip()
    date = _run(
        ["git", "log", "-1", "--format=%ad", "--date=short"],
        cwd=root,
    ).stdout.strip()
    commits = _run(["git", "rev-list", "--count", "HEAD"], cwd=root).stdout.strip()
    return {
        "commit": sha,
        "commit_short": short,
        "commit_date": date,
        "commit_count": commits,
    }


def _size(root: Path) -> dict[str, Any]:
    lib = _list_py(root, "thesistester")
    pages = _list_py(root, "pages")
    tests = _list_py(root, "tests")
    docs = sorted((root / "docs").rglob("*.md")) if (root / "docs").exists() else []
    docs_top = sorted((root / "docs").glob("*.md")) if (root / "docs").exists() else []
    test_fn = 0
    rg = _run(
        ["rg", "-c", "def test_", "tests"],
        cwd=root,
        check=False,
    )
    if rg.returncode == 0:
        for line in rg.stdout.splitlines():
            if ":" in line:
                test_fn += int(line.rsplit(":", 1)[1])
    largest = sorted(
        ((p.relative_to(root).as_posix(), _physical_loc([p])) for p in lib + pages),
        key=lambda item: item[1],
        reverse=True,
    )[:12]
    return {
        "library_modules": len(lib),
        "library_loc": _physical_loc(lib),
        "pages_modules": len(pages),
        "pages_loc": _physical_loc(pages),
        "app_py_loc": _physical_loc([root / "app.py"]) if (root / "app.py").exists() else 0,
        "test_files": len(tests),
        "test_loc": _physical_loc(tests),
        "test_def_test_": test_fn,
        "docs_md_all": len(docs),
        "docs_md_top_level": len(docs_top),
        "docs_loc_top_level": _physical_loc(docs_top),
        "docs_loc_all": _physical_loc(docs),
        "largest_modules": [{"path": path, "loc": loc} for path, loc in largest],
    }


def _radon_cc(root: Path) -> dict[str, Any]:
    raw = _run(
        ["radon", "cc", "thesistester", "pages", "-s", "-j"],
        cwd=root,
    ).stdout
    data = json.loads(raw)
    grades: Counter[str] = Counter()
    complexities: list[int] = []
    f_grade: list[dict[str, Any]] = []
    d_plus: list[dict[str, Any]] = []
    for path, blocks in data.items():
        for block in blocks:
            if not isinstance(block, dict):
                continue
            rank = block.get("rank")
            complexity = block.get("complexity")
            name = block.get("name")
            if rank is None or complexity is None:
                continue
            grades[str(rank)] += 1
            complexities.append(int(complexity))
            rec = {
                "path": path,
                "name": name,
                "complexity": int(complexity),
                "rank": rank,
            }
            if rank in {"D", "E", "F"}:
                d_plus.append(rec)
            if rank == "F":
                f_grade.append(rec)
    f_grade.sort(key=lambda r: r["complexity"], reverse=True)
    d_plus.sort(key=lambda r: r["complexity"], reverse=True)
    total = sum(grades.values())
    average = round(sum(complexities) / total, 2) if total else None
    return {
        "blocks": total,
        "histogram": {k: grades[k] for k in ("A", "B", "C", "D", "E", "F") if k in grades},
        "average": average,
        "f_grade": f_grade,
        "d_plus": d_plus,
    }


_MI_LINE = re.compile(r"^(?P<path>.+?)\s+-\s+(?P<rank>[A-F])\s+\((?P<mi>[0-9.]+)\)$")


def _radon_mi(root: Path) -> dict[str, Any]:
    raw = _run(
        ["radon", "mi", "thesistester", "pages", "-s"],
        cwd=root,
    ).stdout
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _MI_LINE.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "path": match.group("path"),
                "rank": match.group("rank"),
                "mi": float(match.group("mi")),
            }
        )
    zero = [r for r in rows if r["mi"] == 0.0]
    under_20 = [r for r in rows if r["mi"] < 20.0]
    under_20.sort(key=lambda r: r["mi"])
    return {
        "modules": len(rows),
        "mi_zero": zero,
        "mi_under_20": under_20,
    }


def _vulture(root: Path, min_confidence: int) -> list[dict[str, Any]]:
    proc = _run(
        [
            "vulture",
            "thesistester",
            "pages",
            f"--min-confidence={min_confidence}",
        ],
        cwd=root,
        check=False,
    )
    # vulture exits 3 when it finds candidates; still parse stdout.
    rows: list[dict[str, Any]] = []
    line_re = re.compile(
        r"^(?P<path>.+?):(?P<line>\d+):\s+unused (?P<kind>\w+) '(?P<name>[^']+)' "
        r"\((?P<confidence>\d+)% confidence\)$"
    )
    for line in proc.stdout.splitlines():
        match = line_re.match(line.strip())
        if match:
            rows.append(
                {
                    "path": match.group("path"),
                    "line": int(match.group("line")),
                    "kind": match.group("kind"),
                    "name": match.group("name"),
                    "confidence": int(match.group("confidence")),
                }
            )
        elif line.strip():
            rows.append({"raw": line.strip()})
    return rows


def _rg_count(root: Path, pattern: str, *paths: str, flags: list[str] | None = None) -> int:
    cmd = ["rg", "-n", *(flags or []), pattern, *paths]
    proc = _run(cmd, cwd=root, check=False)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"rg failed ({proc.returncode}): {proc.stderr}")
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def _rg_count_per_file_sum(root: Path, pattern: str, *paths: str) -> int:
    proc = _run(["rg", "-c", pattern, *paths], cwd=root, check=False)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"rg -c failed ({proc.returncode}): {proc.stderr}")
    total = 0
    for line in proc.stdout.splitlines():
        if ":" in line:
            total += int(line.rsplit(":", 1)[1])
    return total


def _rg_files(root: Path, pattern: str, *paths: str) -> list[str]:
    proc = _run(["rg", "-l", pattern, *paths], cwd=root, check=False)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"rg -l failed ({proc.returncode}): {proc.stderr}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _smells(root: Path) -> dict[str, Any]:
    except_n = _rg_count(root, r"except Exception|except:", "thesistester", "pages")
    todo = _rg_count(
        root,
        r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b",
        "thesistester",
        "pages",
    )
    todo_i = _rg_count(
        root,
        r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b",
        "thesistester",
        "pages",
        flags=["-i"],
    )
    noqa = _rg_count_per_file_sum(root, r"type: ignore|noqa", "thesistester", "pages")
    session_state = _rg_count_per_file_sum(root, r"st\.session_state", "pages")
    session_state_by_page: dict[str, int] = {}
    proc = _run(["rg", "-c", r"st\.session_state", "pages"], cwd=root, check=False)
    for line in proc.stdout.splitlines():
        if ":" in line:
            path, count = line.rsplit(":", 1)
            session_state_by_page[path] = int(count)
    streamlit_lib = _rg_files(
        root,
        r"^import streamlit|^from streamlit",
        "thesistester",
    )
    private_imports = _rg_count(
        root,
        r"from thesistester\.[\w.]+ import .*\b_[a-z]",
        "pages",
        "thesistester",
    )
    return {
        "broad_except": except_n,
        "todo_markers": todo,
        "todo_case_insensitive_hits": todo_i,
        "noqa_or_type_ignore": noqa,
        "session_state_lines": session_state,
        "session_state_by_page": dict(sorted(session_state_by_page.items())),
        "library_streamlit_imports": streamlit_lib,
        "cross_module_private_imports": private_imports,
    }


def _annotations(root: Path) -> dict[str, Any]:
    """AST return-annotation counts plus the same-line ``def … ->`` proxy.

    Plan §4.2 quoted 1,588 vs 6 — that pair is a different (unreproduced)
    heuristic. This function records (1) a same-line ``def … ->`` count
    (1,597 on ``e82c2a9``; 1,598 after #478) and (2) a full AST walk so
    later slices do not treat the plan pair, the same-line leftover, and
    the AST unannotated list as interchangeable.
    """
    same_line_ann = 0
    same_line_no = 0
    ast_ann = 0
    ast_un: list[str] = []
    def_line = re.compile(r"^\s*(async )?def\s+")
    for path in _list_py(root, "thesistester"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if def_line.match(line):
                if "->" in line:
                    same_line_ann += 1
                else:
                    same_line_no += 1
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is not None:
                    ast_ann += 1
                else:
                    ast_un.append(f"{path.relative_to(root).as_posix()}:{node.name}")
    return {
        "same_line_return_annotated": same_line_ann,
        "same_line_def_without_arrow": same_line_no,
        "ast_return_annotated": ast_ann,
        "ast_unannotated": len(ast_un),
        "ast_unannotated_symbols": ast_un,
    }


def _page_shape(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _list_py(root, "pages"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        fns = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "loc": _physical_loc([path]),
                "top_level_functions": len(fns),
                "top_level_classes": len(classes),
                "function_names": fns,
            }
        )
    return rows


def _assign_owner(rel: str) -> str | None:
    # Longest prefix wins so ``scripts/quality_metrics.py`` beats ``scripts/``.
    best: tuple[int, str] | None = None
    for prefix, slice_id in _OWNERSHIP_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), slice_id)
    return None if best is None else best[1]


def _ownership(root: Path) -> dict[str, Any]:
    targets: list[Path] = []
    for rel in ("thesistester", "pages", "scripts", "examples"):
        targets.extend(_list_py(root, rel))
    app = root / "app.py"
    if app.exists():
        targets.append(app)
    assigned: dict[str, str] = {}
    unassigned: list[str] = []
    for path in targets:
        rel = path.relative_to(root).as_posix()
        owner = _assign_owner(rel)
        if owner is None:
            unassigned.append(rel)
        else:
            assigned[rel] = owner
    by_slice: dict[str, list[str]] = {}
    for rel, owner in assigned.items():
        by_slice.setdefault(owner, []).append(rel)
    for files in by_slice.values():
        files.sort()
    return {
        "files": assigned,
        "by_slice": dict(sorted(by_slice.items())),
        "unassigned": unassigned,
        "counts": {k: len(v) for k, v in sorted(by_slice.items())},
        "exclusive": not unassigned and len(assigned) == len(targets),
    }


def collect(root: Path) -> dict[str, Any]:
    vulture_60 = _vulture(root, 60)
    vulture_80 = _vulture(root, 80)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "cwd": str(root),
        "git": _git_meta(root),
        "size": _size(root),
        "radon_cc": _radon_cc(root),
        "radon_mi": _radon_mi(root),
        "vulture": {
            "min_confidence_60": len(vulture_60),
            "min_confidence_80": len(vulture_80),
            "candidates_60": vulture_60,
            "candidates_80": vulture_80,
        },
        "smells": _smells(root),
        "annotations": _annotations(root),
        "pages": _page_shape(root),
        "ownership": _ownership(root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON here. Default: stdout.",
    )
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    os.chdir(root)
    payload = collect(root)
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    if payload["ownership"]["unassigned"]:
        print(
            "WARNING: unassigned files: " + ", ".join(payload["ownership"]["unassigned"]),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
