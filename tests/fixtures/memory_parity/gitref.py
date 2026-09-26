"""Fail-closed git object resolution for MW0 CI gates.

Shallow GitHub Actions checkouts often lack ``origin/main`` and historical
commit ``59a4652``. These helpers fetch the missing objects. If a required
ref cannot be resolved, they raise ``GitRefError`` (stop and report). They
do not skip.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .compat import FARM_PRODUCTION_COMMIT, FARM_PRODUCTION_COMMIT_FULL

REPO = Path(__file__).resolve().parents[3]
_BASE_FETCH_BRANCH = "main"


class GitRefError(RuntimeError):
    """A required git object could not be resolved. Stop and report."""


def _git_ok(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd or REPO, check=False, capture_output=True, text=True)


def _is_shallow(*, cwd: Path | None = None) -> bool:
    probe = _git_ok(["git", "rev-parse", "--is-shallow-repository"], cwd=cwd)
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def ref_exists(ref: str, *, cwd: Path | None = None) -> bool:
    return (
        _git_ok(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=cwd,
        ).returncode
        == 0
    )


def git_output(*args: str, cwd: Path | None = None) -> str:
    proc = _git_ok(["git", *args], cwd=cwd)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or "no output"
        raise GitRefError(
            f"STOP AND REPORT: git {' '.join(args)} failed "
            f"(exit {proc.returncode}): {detail}"
        )
    return proc.stdout


def resolve_main_ref(*, cwd: Path | None = None) -> str:
    """Return origin/main (or the PR base). Never a stale local ``main``.

    Local ``main`` is ignored on purpose: a snapshot that is hours behind
    ``origin/main`` would make the untouched-package gate false-fail.
    """
    explicit = (
        os.environ.get("MW0_REGRESSION_BASE") or os.environ.get("GITHUB_BASE_SHA") or ""
    ).strip()
    candidates = [item for item in (explicit, "origin/main") if item]
    for ref in candidates:
        if ref_exists(ref, cwd=cwd):
            return ref

    branch = (os.environ.get("GITHUB_BASE_REF") or _BASE_FETCH_BRANCH).strip() or _BASE_FETCH_BRANCH
    remote_ref = f"origin/{branch}"
    fetched = _git_ok(
        [
            "git",
            "fetch",
            "--depth=1",
            "--no-tags",
            "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
        ],
        cwd=cwd,
    )
    if fetched.returncode == 0:
        if ref_exists(remote_ref, cwd=cwd):
            return remote_ref
        if ref_exists("FETCH_HEAD", cwd=cwd):
            return "FETCH_HEAD"
    detail = (fetched.stderr or fetched.stdout).strip() or "no output"
    raise GitRefError(
        "STOP AND REPORT: MW0 cannot resolve origin/main (or the PR base) "
        f"for the untouched-package / golden-tree gate "
        f"(tried {candidates + [remote_ref]}; "
        f"git fetch origin {branch} exited {fetched.returncode}: {detail})"
    )


def resolve_farm_production_commit(*, cwd: Path | None = None) -> str:
    """Return the farm production commit, fetching it if the clone is shallow."""
    if ref_exists(FARM_PRODUCTION_COMMIT_FULL, cwd=cwd):
        return FARM_PRODUCTION_COMMIT_FULL
    if ref_exists(FARM_PRODUCTION_COMMIT, cwd=cwd):
        return FARM_PRODUCTION_COMMIT

    attempts: list[list[str]] = [
        [
            "git",
            "fetch",
            "--depth=1",
            "--no-tags",
            "origin",
            FARM_PRODUCTION_COMMIT_FULL,
        ],
        ["git", "fetch", "--deepen=400", "--no-tags", "origin"],
    ]
    if _is_shallow(cwd=cwd):
        attempts.append(["git", "fetch", "--unshallow", "--no-tags", "origin"])

    last_detail = "farm production commit not in the local object store"
    for cmd in attempts:
        fetched = _git_ok(cmd, cwd=cwd)
        if ref_exists(FARM_PRODUCTION_COMMIT_FULL, cwd=cwd):
            return FARM_PRODUCTION_COMMIT_FULL
        if ref_exists(FARM_PRODUCTION_COMMIT, cwd=cwd):
            return FARM_PRODUCTION_COMMIT
        last_detail = (fetched.stderr or fetched.stdout).strip() or last_detail

    raise GitRefError(
        "STOP AND REPORT: MW0 cannot resolve farm production commit "
        f"{FARM_PRODUCTION_COMMIT_FULL} ({FARM_PRODUCTION_COMMIT}) for the "
        f"hook-point audit: {last_detail}"
    )


def diff_vs_main(*paths: str, cwd: Path | None = None) -> str:
    base = resolve_main_ref(cwd=cwd)
    return git_output("diff", base, "--", *paths, cwd=cwd)


def show_at_farm(rel_path: str, *, cwd: Path | None = None) -> str:
    commit = resolve_farm_production_commit(cwd=cwd)
    return git_output("show", f"{commit}:{rel_path}", cwd=cwd)
