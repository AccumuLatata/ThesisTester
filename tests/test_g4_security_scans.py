"""QR G-4 / QI-12-06 / QI-07-09 — warn-first scanners, SHA pins, SHA-1 identity flag."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from thesistester.study.naming import factor_cell_fingerprint

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
NAMING = ROOT / "thesistester" / "study" / "naming.py"
GOLDEN_EXPERIMENT = ROOT / "tests" / "fixtures" / "study" / "golden" / "experiment.yaml"
CONSTRAINTS = ROOT / "constraints.txt"

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

USES_RE = re.compile(r"^\s+uses:\s+(\S+)", re.MULTILINE)
SPEC_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _dev_specs() -> list[str]:
    return list(_pyproject()["project"]["optional-dependencies"]["dev"])


def _dev_spec(prefix: str) -> str:
    return next(item for item in _dev_specs() if item.startswith(prefix))


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
    """Suffixes must be the run-name identity tail, not a file-level substring."""
    payload = yaml.safe_load(GOLDEN_EXPERIMENT.read_text(encoding="utf-8"))
    names = [str(run["name"]) for run in payload["runs"]]
    assert names, "golden experiment has no runs"
    suffixes = {name.rsplit("_", 1)[-1] for name in names}
    missing = [suffix for suffix in GOLDEN_RUN_NAME_SUFFIXES if suffix not in suffixes]
    assert missing == [], suffixes


def test_build_system_setuptools_clears_named_cves() -> None:
    requires = _pyproject()["build-system"]["requires"]
    spec = next(item for item in requires if item.startswith("setuptools"))
    assert spec == "setuptools>=83,<85"


def test_dev_extra_declares_warn_first_scanners() -> None:
    dev = _dev_specs()
    assert "bandit>=1.7,<2" in dev
    assert "pip-audit>=2.7,<3" in dev


def test_dev_extra_packages_are_locked_in_constraints() -> None:
    """G-2 lock must include every `dev` extra (B-10/B-11 class; G-4 scanners)."""
    lock = CONSTRAINTS.read_text(encoding="utf-8")
    missing = []
    for spec in _dev_specs():
        match = SPEC_NAME_RE.match(spec)
        assert match, spec
        name = match.group(1)
        if not re.search(rf"^{re.escape(name)}==", lock, re.MULTILINE):
            missing.append(name)
    assert missing == []


def test_ci_actions_are_sha_pinned() -> None:
    text = CI.read_text(encoding="utf-8")
    uses = USES_RE.findall(text)
    assert uses, "ci.yml has no uses: entries"
    for ref in uses:
        _action, sep, target = ref.partition("@")
        assert sep and re.fullmatch(r"[0-9a-f]{40}", target), ref
    for action, sha in PINNED_ACTIONS.items():
        assert f"uses: {action}@{sha}" in text
        assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert not re.search(r"uses:\s+\S+@v\d+", text)


def test_g4_jobs_are_warn_first_not_g1() -> None:
    text = CI.read_text(encoding="utf-8")
    jobs = yaml.safe_load(text)["jobs"]
    names = {job.get("name", key) for key, job in jobs.items()}
    assert "bandit (warn-first)" in names
    assert "pip-audit (warn-first)" in names
    assert "bandit (warn-first)" not in G1_REQUIRED_NAMES
    assert "pip-audit (warn-first)" not in G1_REQUIRED_NAMES
    assert f'"{_dev_spec("bandit")}"' in text
    assert f'"{_dev_spec("pip-audit")}"' in text
    assert "bandit -r thesistester -ll" in text
    assert "pip-audit --progress-spinner off" in text
    assert re.search(r"::warning title=bandit::[\s\S]*?exit 0", text)
    assert re.search(r"::warning title=pip-audit::[\s\S]*?exit 0", text)
    assert 'grep -qi "vulnerabilit"' in text
    assert "name: pytest (py${{ matrix.python-version }})" in text
    assert "name: ruff (lint + format)" in text
    assert "name: golden-master regeneration guard" in text
    assert "name: editable install (no dev extras)" in text


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
    stdout = (result.stdout or "").strip()
    assert stdout, f"bandit produced no JSON report (exit {result.returncode}): {result.stderr}"
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"bandit stdout is not JSON (exit {result.returncode}): {stdout[:200]!r}"
        ) from exc
    results = payload.get("results")
    assert isinstance(results, list), payload
    highs = [row for row in results if str(row.get("issue_severity", "")).upper() == "HIGH"]
    totals = (payload.get("metrics") or {}).get("_totals") or {}
    if "SEVERITY.HIGH" in totals:
        assert int(totals["SEVERITY.HIGH"]) == 0, totals
    assert highs == [], highs
