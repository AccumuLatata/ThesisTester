"""B-11 / QI-12-05: path-scoped mypy config + per-file ratchet schema.

Does not invoke mypy. Type-error status stays CI-informational so required
pytest cells cannot become a merge gate.

``tomllib`` is 3.11+; CI ``pytest (py3.10)`` is a G-1 required cell and
must collect on 3.10 via the same ``tomli`` fallback as other schema tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from tests.fixtures.mypy.check_ratchet import (
    BASELINE_PATH,
    FLAGS,
    QI12_FIVE_TREE_STRICT,
    REPO_ROOT,
    SCOPE,
    compare_to_baseline,
    in_scope,
    mypy_produced_report,
    parse_mypy_output,
    scope_files,
)

_PYPROJECT = REPO_ROOT / "pyproject.toml"
_CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"

G1_REQUIRED_NAMES = (
    "ruff (lint + format)",
    "pytest (py3.10)",
    "pytest (py3.11)",
    "pytest (py3.12)",
    "editable install (no dev extras)",
    "golden-master regeneration guard",
)


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_tool_mypy_is_path_scoped_engine_analytics() -> None:
    data = _pyproject()
    mypy = data["tool"]["mypy"]
    assert mypy["files"] == list(SCOPE)
    assert mypy["ignore_missing_imports"] is True
    assert mypy["no_site_packages"] is True
    assert mypy["strict"] is True
    assert mypy["python_version"] == "3.10"
    scoped = " ".join(mypy["files"])
    assert "thesistester/api.py" not in scoped
    assert "thesistester/data" not in scoped
    assert "thesistester/levels" not in scoped
    assert "thesistester/engine" in scoped
    assert "thesistester/analytics" in scoped


def test_mypy_is_capped_dev_extra() -> None:
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    spec = next(req for req in dev if req.startswith("mypy"))
    assert spec == "mypy>=2.3,<3"


def test_committed_baseline_records_qi12_count() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["finding"] == "QI-12-05"
    assert baseline["pr"] == "B-11"
    assert baseline["scope"] == list(SCOPE)
    assert baseline["flags"] == list(FLAGS)
    assert baseline["qi12_five_tree_strict"] == QI12_FIVE_TREE_STRICT == 164
    assert "api.py later" in baseline["note"]
    assert int(baseline["total"]) == sum(int(v) for v in baseline["files"].values())
    assert int(baseline["total"]) >= 0
    assert "thesistester/api.py" not in baseline["scope"]
    assert all(in_scope(name) for name in baseline["files"])
    assert "--no-site-packages" in baseline["flags"]


def test_parse_mypy_output_counts_errors_not_notes() -> None:
    text = (
        "thesistester/engine/signals.py:10: error: Missing type [type-arg]\n"
        "thesistester/engine/signals.py:11:5: error: Bad arg [arg-type]\n"
        "thesistester/engine/signals.py:12: note: Reveal type is\n"
        "thesistester/analytics/walk_forward.py:3: error: Union [union-attr]\n"
        "Found 3 errors in 2 files (checked 4 source files)\n"
    )
    parsed = parse_mypy_output(text)
    assert parsed == {
        "thesistester/analytics/walk_forward.py": 1,
        "thesistester/engine/signals.py": 2,
    }
    pulled = parse_mypy_output(
        "thesistester/api.py:1: error: Missing [type-arg]\n"
        "thesistester/engine/signals.py:1: error: Missing [type-arg]\n"
    )
    assert scope_files(pulled) == {"thesistester/engine/signals.py": 1}
    assert not in_scope("thesistester/api.py")
    assert in_scope("thesistester/engine/signals.py")


def test_mypy_produced_report_distinguishes_crash() -> None:
    assert mypy_produced_report("Success: no issues found in 12 source files")
    assert mypy_produced_report("Found 7 errors in 3 files (checked 12 source files)")
    assert not mypy_produced_report("mypy: can't parse pyproject.toml")


def test_compare_to_baseline_flags_increase_not_decrease() -> None:
    baseline = {
        "total": 3,
        "files": {
            "thesistester/engine/signals.py": 2,
            "thesistester/analytics/walk_forward.py": 1,
        },
    }
    regressions, improvements = compare_to_baseline(
        {
            "thesistester/engine/signals.py": 3,
            "thesistester/analytics/walk_forward.py": 1,
        },
        baseline,
    )
    assert any("signals.py" in item for item in regressions)
    assert any("total 4 > baseline 3" in item for item in regressions)
    assert improvements == []

    regressions, improvements = compare_to_baseline(
        {"thesistester/engine/signals.py": 1},
        baseline,
    )
    assert regressions == []
    assert any("total 1 < baseline 3" in item for item in improvements)


def test_mypy_ratchet_schema_tests_keep_python310_tomli_fallback() -> None:
    """CI pytest (py3.10) is a G-1 required cell; tomllib is 3.11+."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert "import tomli as tomllib" in source
    assert "sys.version_info >= (3, 11)" in source


def test_ci_mypy_job_is_informational_not_g1() -> None:
    text = _CI.read_text(encoding="utf-8")
    assert "name: mypy (informational)" in text
    assert "python -m tests.fixtures.mypy.check_ratchet" in text
    assert "B-11 / QI-12-05" in text
    assert "Not a G-1 required check" in text
    assert "name: pytest (py${{ matrix.python-version }})" in text
    assert "name: ruff (lint + format)" in text
    assert "name: golden-master regeneration guard" in text
    assert "name: editable install (no dev extras)" in text
    assert "mypy (informational)" not in G1_REQUIRED_NAMES
