"""QR G-4 / QI-12-06 / QI-07-09 — warn-first scanners, SHA pins, SHA-1 identity flag."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from thesistester.study.naming import factor_cell_fingerprint

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
NAMING = ROOT / "thesistester" / "study" / "naming.py"
GOLDEN_EXPERIMENT = ROOT / "tests" / "fixtures" / "study" / "golden" / "experiment.yaml"

G1_REQUIRED_NAMES = (
    "ruff (lint + format)",
    "pytest (py3.10)",
    "pytest (py3.11)",
    "pytest (py3.12)",
    "editable install (no dev extras)",
    "golden-master regeneration guard",
)

PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}

# RS2 golden run-name suffixes (10-hex SHA-1). Digest must not change.
GOLDEN_RUN_NAME_SUFFIXES = (
    "8b6a7a6332",
    "67804511db",
)


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_factor_cell_fingerprint_usedforsecurity_false_digest_unchanged() -> None:
    """QI-07-09: flag silences bandit B324; hex stays the identity digest."""
    factors = {
        "confluence_mode": "global_cluster",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "partner_levels": ["SMA_50_1min"],
        "otf": {"enabled": False},
    }
    payload = json.dumps(factors, sort_keys=True, separators=(",", ":"), default=str)
    legacy = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    flagged = hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    assert flagged == legacy
    assert factor_cell_fingerprint(factors) == legacy

    source = ast.parse(NAMING.read_text(encoding="utf-8"))
    flagged_call = False
    for node in ast.walk(source):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "sha1"
            and isinstance(func.value, ast.Name)
            and func.value.id == "hashlib"
        ):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        flag = keywords.get("usedforsecurity")
        assert flag is not None
        assert isinstance(flag, ast.Constant) and flag.value is False
        flagged_call = True
    assert flagged_call


def test_rs2_golden_run_name_suffixes_unchanged() -> None:
    text = GOLDEN_EXPERIMENT.read_text(encoding="utf-8")
    for suffix in GOLDEN_RUN_NAME_SUFFIXES:
        assert suffix in text, suffix


def test_build_system_setuptools_clears_named_cves() -> None:
    requires = _pyproject()["build-system"]["requires"]
    spec = next(item for item in requires if item.startswith("setuptools"))
    assert spec == "setuptools>=83,<85"


def test_dev_extra_declares_warn_first_scanners() -> None:
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert "bandit>=1.7,<2" in dev
    assert "pip-audit>=2.7,<3" in dev


def test_ci_actions_are_sha_pinned() -> None:
    text = CI.read_text(encoding="utf-8")
    assert not re.search(r"uses:\s+actions/[a-z0-9-]+@v\d+", text)
    for action, sha in PINNED_ACTIONS.items():
        assert f"uses: {action}@{sha}" in text
        assert re.fullmatch(r"[0-9a-f]{40}", sha)


def test_g4_jobs_are_warn_first_not_g1() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "name: bandit (warn-first)" in text
    assert "name: pip-audit (warn-first)" in text
    assert "bandit -r thesistester -ll" in text
    assert "pip-audit --progress-spinner off" in text
    assert "name: pytest (py${{ matrix.python-version }})" in text
    assert "name: ruff (lint + format)" in text
    assert "name: golden-master regeneration guard" in text
    assert "name: editable install (no dev extras)" in text
    assert "bandit (warn-first)" not in G1_REQUIRED_NAMES
    assert "pip-audit (warn-first)" not in G1_REQUIRED_NAMES


def test_bandit_high_is_zero() -> None:
    """G-4 exit: bandit High = 0 after usedforsecurity=False (QI-12-06)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            str(ROOT / "thesistester"),
            "-ll",
            "-f",
            "json",
            "-q",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout or "{}")
    results = payload.get("results") or []
    highs = [row for row in results if str(row.get("issue_severity", "")).upper() == "HIGH"]
    assert highs == [], highs
