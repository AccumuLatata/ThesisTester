"""QI-12 §2.3 / B-11 per-file mypy ratchet (QI-12-05).

Path-scoped ``--strict --ignore-missing-imports`` on ``engine/`` +
``analytics/`` only. Not repo-wide. ``api.py`` later.

CI job ``mypy (informational)`` runs this. Type errors and ratchet
increases are warn-first (exit 0). Config/runtime crash fails.
Pytest does **not** invoke mypy — that would make type errors a
required-cell merge gate.

    python -m tests.fixtures.mypy.check_ratchet
    python -m tests.fixtures.mypy.check_ratchet --write-baseline
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
SCOPE = ("thesistester/engine", "thesistester/analytics")
FLAGS = ("--strict", "--ignore-missing-imports", "--no-site-packages")
# QI-12 §2.3 five-tree probe (engine+analytics+api+data+levels) was 164.
QI12_FIVE_TREE_STRICT = 164


def in_scope(path: str) -> bool:
    """True for engine/ + analytics/ paths. api.py and other trees are later."""
    return path.startswith("thesistester/engine/") or path.startswith("thesistester/analytics/")


def scope_files(files: dict[str, int]) -> dict[str, int]:
    return {name: count for name, count in files.items() if in_scope(name)}


_ERROR_LINE = re.compile(r"^(?P<path>.+?):\d+(?::\d+)?: error:")
_REPORT_OK = re.compile(r"^Success: no issues found", re.MULTILINE)
_REPORT_ERRORS = re.compile(r"^Found \d+ error", re.MULTILINE)


def parse_mypy_output(text: str, *, root: Path = REPO_ROOT) -> dict[str, int]:
    """Count ``error:`` lines per repo-relative path. Notes are ignored."""
    counts: Counter[str] = Counter()
    root_resolved = root.resolve()
    for raw in text.splitlines():
        match = _ERROR_LINE.match(raw)
        if match is None:
            continue
        path = Path(match.group("path").replace("\\", "/"))
        if path.is_absolute():
            try:
                rel = path.resolve().relative_to(root_resolved).as_posix()
            except ValueError:
                rel = path.as_posix()
        else:
            rel = path.as_posix()
        counts[rel] += 1
    return dict(sorted(counts.items()))


def mypy_produced_report(text: str) -> bool:
    """True when mypy finished a type-check (errors or clean)."""
    return bool(_REPORT_OK.search(text) or _REPORT_ERRORS.search(text))


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_baseline(files: dict[str, int]) -> dict[str, Any]:
    return {
        "finding": "QI-12-05",
        "pr": "B-11",
        "scope": list(SCOPE),
        "flags": list(FLAGS),
        "note": (
            "QI-12 §2.3 five-tree probe (engine+analytics+api+data+levels) "
            f"was {QI12_FIVE_TREE_STRICT} strict. This baseline ratchets "
            "engine+analytics paths only; api.py later. Import-pulled errors "
            "outside the two trees are logged, not ratcheted. "
            "--no-site-packages avoids numpy stub syntax abort under "
            "python_version 3.10."
        ),
        "qi12_five_tree_strict": QI12_FIVE_TREE_STRICT,
        "total": sum(files.values()),
        "files": files,
    }


def compare_to_baseline(
    current: dict[str, int], baseline: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements). Empty regressions means no increase."""
    base_files = {str(k): int(v) for k, v in baseline["files"].items()}
    base_total = int(baseline["total"])
    cur_total = sum(current.values())
    regressions: list[str] = []
    improvements: list[str] = []
    if cur_total > base_total:
        regressions.append(f"total {cur_total} > baseline {base_total}")
    elif cur_total < base_total:
        improvements.append(f"total {cur_total} < baseline {base_total}")
    names = sorted(set(base_files) | set(current))
    for name in names:
        before = base_files.get(name, 0)
        after = current.get(name, 0)
        if after > before:
            regressions.append(f"{name}: {after} > {before}")
        elif after < before:
            improvements.append(f"{name}: {after} < {before}")
    return regressions, improvements


def run_mypy(*, root: Path = REPO_ROOT) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        *FLAGS,
        "--no-incremental",
        "--hide-error-context",
        "--no-color-output",
        *SCOPE,
    ]
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    return result.returncode, f"{result.stdout}\n{result.stderr}"


def _gh(kind: str, title: str, message: str) -> None:
    safe = message.replace("\n", " ").replace("%", "%25")
    print(f"::{kind} title={title}::{safe}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="overwrite tests/fixtures/mypy/baseline.json from this run",
    )
    args = parser.parse_args(argv)

    try:
        code, output = run_mypy()
    except OSError as exc:
        _gh("error", "mypy", f"mypy failed to start (config/runtime, not informational): {exc}")
        return 1

    print(output, end="" if output.endswith("\n") else "\n")

    if not mypy_produced_report(output):
        _gh(
            "error",
            "mypy",
            "mypy failed before producing a type-check report "
            f"(config/runtime error, not informational; exit {code}).",
        )
        return 1

    files = scope_files(parse_mypy_output(output))
    total = sum(files.values())

    if args.write_baseline:
        payload = build_baseline(files)
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {BASELINE_PATH.relative_to(REPO_ROOT)} total={total}")
        return 0

    baseline = load_baseline()
    regressions, improvements = compare_to_baseline(files, baseline)
    base_total = int(baseline["total"])

    if regressions:
        _gh(
            "warning",
            "mypy",
            "Ratchet regression (QI-12-05 / B-11 informational, not blocking): "
            + "; ".join(regressions)
            + ". Do not raise the baseline. Blocking flip is a later PR.",
        )
        return 0

    if improvements:
        _gh(
            "notice",
            "mypy",
            f"Count dropped below baseline {base_total} → {total}. "
            "Update tests/fixtures/mypy/baseline.json so the ratchet stays tight.",
        )
        return 0

    _gh(
        "notice",
        "mypy",
        f"engine+analytics --strict count {total} matches baseline "
        f"(QI-12 §2.3 five-tree probe was {QI12_FIVE_TREE_STRICT}; "
        "api.py later). Informational; not a G-1 required check.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
