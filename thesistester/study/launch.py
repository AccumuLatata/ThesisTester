"""RS-D9 Studies CLI-launch helper (argv + detached ``study run`` spawn).

Builds the same argv a human would type and starts it with ``subprocess.Popen``.
Does **not** import ``thesistester.study.execute``, call the in-process runner,
or acquire ``.study.lock`` (the child CLI owns the lock).
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from thesistester.study.expand import study_identity_hash
from thesistester.study.schema import StudySpecError, normalize_study_spec, validate_study_spec
from thesistester.study.viewer import default_study_viewer_roots

LAUNCH_YAML_NAME = "study.launch.yaml"
LAUNCH_LOG_NAME = "study.launch.log"
LAUNCH_PID_NAME = "study.launch.pid"
LAUNCH_JSON_NAME = "study.launch.json"

STUDIES_LAUNCH_OUTPUT_DIR_KEY = "studies_launch_output_dir"
STUDIES_LAUNCH_APPROVAL_KEY = "studies_launch_approval"

_DATASET_PATH_KEYS = ("path", "subtimeframe_path")


class StudyLaunchError(ValueError):
    """Raised when a Studies CLI launch cannot be prepared or spawned."""


@dataclass(frozen=True)
class LaunchPlan:
    """Validated spawn plan. ``confirm`` is False until the bound-approval step."""

    argv: tuple[str, ...]
    output_dir: Path
    launch_yaml_path: Path
    pinned_spec: dict[str, Any]
    study_identity_hash: str
    run_count: int
    confirm_above_runs: int
    needs_confirm: bool
    confirm: bool
    force: bool
    workers: int | None


@dataclass(frozen=True)
class LaunchResult:
    """Metadata for a detached CLI child (does not wait on the process)."""

    pid: int
    argv: tuple[str, ...]
    output_dir: Path
    launch_yaml_path: Path
    log_path: Path
    pid_path: Path
    json_path: Path
    study_identity_hash: str
    run_count: int
    confirm: bool
    force: bool


@dataclass(frozen=True)
class LaunchPidStatus:
    """Last launch pid recorded under an output dir."""

    pid: int
    alive: bool


def default_output_dir_from_yaml(text: str) -> str:
    """Return ``study.output_dir`` from YAML text, or empty string."""
    if not str(text).strip():
        return ""
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        return ""
    if not isinstance(payload, Mapping):
        return ""
    study = payload.get("study")
    if not isinstance(study, Mapping):
        return ""
    raw = study.get("output_dir")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def approval_payload(plan: LaunchPlan) -> dict[str, Any]:
    """RS6-shaped bound triple for the two-step confirm UI."""
    return {
        "study_identity_hash": plan.study_identity_hash,
        "run_count": int(plan.run_count),
        "output_dir": str(plan.output_dir.resolve()),
    }


def format_argv(argv: Sequence[str]) -> str:
    """Single-line display of planned argv (honesty)."""
    return " ".join(str(part) for part in argv)


def resolve_launch_output_dir(
    raw: str | Path,
    *,
    roots: Sequence[Path] | None = None,
) -> Path:
    """Resolve a launch output dir that may not exist yet; refuse extra-root paths."""
    if isinstance(raw, str) and not raw.strip():
        raise StudyLaunchError("Launch output directory path is required.")
    path = Path(raw).expanduser()
    candidate = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    return _ensure_within_roots(candidate, roots, label="output_dir")


def build_study_run_argv(
    *,
    launch_yaml: str | Path,
    output_dir: str | Path,
    confirm: bool = False,
    force: bool = False,
    workers: int | None = None,
    executable: str | None = None,
) -> list[str]:
    """Argv parity with ``python -m thesistester study run …``."""
    if workers is not None:
        workers_n = int(workers)
        if workers_n < 1:
            raise StudyLaunchError("workers override must be an integer >= 1")
    argv = [
        executable or sys.executable,
        "-m",
        "thesistester",
        "study",
        "run",
        str(_absolute_argv_path(launch_yaml)),
        "--output-dir",
        str(_absolute_argv_path(output_dir)),
    ]
    if workers is not None:
        argv.extend(["--workers", str(int(workers))])
    if confirm:
        argv.append("--confirm")
    if force:
        argv.append("--force")
    return argv


def launch_pid_is_alive(pid: int) -> bool:
    """True when ``pid`` still exists on this host (stdlib only).

    POSIX uses ``os.kill(pid, 0)``. Windows does not treat signal ``0`` as an
    existence probe (``os.kill`` maps to ``TerminateProcess``), so use
    ``OpenProcess`` via ``ctypes`` instead — never ``os.kill`` on NT.
    """
    pid_n = int(pid)
    if pid_n <= 0:
        return False
    if os.name == "nt":
        return _pid_is_alive_windows(pid_n)
    try:
        os.kill(pid_n, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


pid_is_alive = launch_pid_is_alive


def _pid_is_alive_windows(pid: int) -> bool:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    process_query_limited_information = 0x1000
    error_access_denied = 5
    handle = kernel32.OpenProcess(process_query_limited_information, 0, int(pid))
    if handle:
        kernel32.CloseHandle(handle)
        return True
    # Access denied still means the PID exists on this host.
    return int(kernel32.GetLastError()) == error_access_denied


def reset_launch_session_for_preview(
    session_state: Any,
    *,
    prev_cached_yaml: str | None,
    new_yaml: str,
) -> None:
    """Clear armed confirm; reseed CLI output_dir when preview YAML changed.

    Streamlit keeps widget keys across Validate / Preview. Without this, a second
    preview of a different StudySpec can spawn into the previous study's
    ``output_dir`` (and reuse a stale bound-confirm triple's directory).
    """
    session_state.pop(STUDIES_LAUNCH_APPROVAL_KEY, None)
    if prev_cached_yaml != new_yaml:
        # Assign (do not rely on pop alone): widget-backed keys persist across
        # reruns; overwrite with the new YAML default before the text_input runs.
        session_state[STUDIES_LAUNCH_OUTPUT_DIR_KEY] = default_output_dir_from_yaml(new_yaml)


def read_launch_pid_status(output_dir: str | Path) -> LaunchPidStatus | None:
    """Read ``study.launch.pid`` when present."""
    path = Path(output_dir) / LAUNCH_PID_NAME
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return LaunchPidStatus(pid=pid, alive=launch_pid_is_alive(pid))


def build_launch_plan(
    yaml_text: str,
    *,
    cached_yaml: str | None,
    expanded: bool,
    run_count: int | None,
    output_dir_raw: str,
    force: bool = False,
    workers: int | None = None,
    roots: Sequence[Path] | None = None,
) -> LaunchPlan:
    """Validate spawn gates except bound-approval and live-pid.

    ``confirm`` on the returned plan is always False. Over-threshold launches
    must call :func:`plan_with_confirm` before :func:`spawn_launch`.
    """
    if cached_yaml is None or yaml_text != cached_yaml:
        raise StudyLaunchError(
            "StudySpec YAML changed since the last successful preview. "
            "Click Validate / Preview again before launching."
        )
    if not expanded or run_count is None:
        raise StudyLaunchError(
            "In-memory expand did not complete (over PREVIEW_EXPAND_CAP). "
            "Shrink the study or run `python -m thesistester study expand` on the CLI."
        )
    run_count_n = int(run_count)
    if run_count_n < 1:
        raise StudyLaunchError("run_count must be >= 1 to launch.")
    if workers is not None:
        workers_n = int(workers)
        if workers_n < 1:
            raise StudyLaunchError("workers override must be an integer >= 1")
        workers = workers_n

    allowed_roots = _roots_or_default(roots)
    pinned = _pinned_normalized_spec(yaml_text, roots=allowed_roots)
    output_dir = resolve_launch_output_dir(output_dir_raw, roots=allowed_roots)
    # Do not rewrite study.output_dir in the launch YAML — the child uses
    # absolute --output-dir. Rewriting would change the identity hash.
    identity = study_identity_hash(pinned)
    study = dict(pinned.get("study") or {})
    confirm_above = int(study.get("confirm_above_runs", 200))
    needs_confirm = run_count_n >= confirm_above
    launch_yaml_path = output_dir / LAUNCH_YAML_NAME
    argv = tuple(
        build_study_run_argv(
            launch_yaml=launch_yaml_path,
            output_dir=output_dir,
            confirm=False,
            force=bool(force),
            workers=workers,
        )
    )
    return LaunchPlan(
        argv=argv,
        output_dir=output_dir,
        launch_yaml_path=launch_yaml_path,
        pinned_spec=pinned,
        study_identity_hash=identity,
        run_count=run_count_n,
        confirm_above_runs=confirm_above,
        needs_confirm=needs_confirm,
        confirm=False,
        force=bool(force),
        workers=workers,
    )


def planned_argv(plan: LaunchPlan) -> tuple[str, ...]:
    """Argv that would run after a successful confirm step (honesty display)."""
    return tuple(
        build_study_run_argv(
            launch_yaml=plan.launch_yaml_path,
            output_dir=plan.output_dir,
            confirm=plan.needs_confirm,
            force=plan.force,
            workers=plan.workers,
        )
    )


def approval_matches(approval: Mapping[str, Any] | None, plan: LaunchPlan) -> bool:
    """True when ``approval`` echoes the current pinned triple."""
    if not isinstance(approval, Mapping):
        return False
    got_hash = approval.get("study_identity_hash")
    got_out = approval.get("output_dir")
    try:
        got_count = int(approval["run_count"]) if approval.get("run_count") is not None else None
    except (TypeError, ValueError):
        got_count = None
    if not isinstance(got_hash, str) or not isinstance(got_out, str) or got_count is None:
        return False
    try:
        got_out_resolved = str(Path(got_out).expanduser().resolve())
    except OSError:
        return False
    return (
        got_hash == plan.study_identity_hash
        and got_count == plan.run_count
        and got_out_resolved == str(plan.output_dir.resolve())
    )


def plan_with_confirm(plan: LaunchPlan, approval: Mapping[str, Any] | None) -> LaunchPlan:
    """Attach ``--confirm`` only when the bound triple matches this plan."""
    if not plan.needs_confirm:
        raise StudyLaunchError(
            "This expansion is under confirm_above_runs; use Run via CLI (do not pass --confirm)."
        )
    if not approval_matches(approval, plan):
        raise StudyLaunchError(
            "Confirm and run requires a bound approval matching "
            "(study_identity_hash, run_count, output_dir). "
            "Click Bind confirm first, and do not change YAML or output_dir."
        )
    argv = tuple(
        build_study_run_argv(
            launch_yaml=plan.launch_yaml_path,
            output_dir=plan.output_dir,
            confirm=True,
            force=plan.force,
            workers=plan.workers,
        )
    )
    return replace(plan, confirm=True, argv=argv)


def spawn_launch(
    plan: LaunchPlan,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
) -> LaunchResult:
    """Write launch YAML and start a detached CLI child. Does not wait."""
    if plan.needs_confirm and not plan.confirm:
        raise StudyLaunchError(
            "Expansion is at or above confirm_above_runs; bind confirm, then Confirm and run."
        )
    if (not plan.needs_confirm) and plan.confirm:
        raise StudyLaunchError("Refusing to pass --confirm under confirm_above_runs.")

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = plan.output_dir / LAUNCH_LOG_NAME
    pid_path = plan.output_dir / LAUNCH_PID_NAME
    json_path = plan.output_dir / LAUNCH_JSON_NAME
    _claim_launch_pid_file(pid_path, output_dir=plan.output_dir)
    previous_log = log_path.read_bytes() if log_path.is_file() else None
    try:
        _write_launch_yaml(plan.launch_yaml_path, plan.pinned_spec)
        log_handle = open(log_path, "w", encoding="utf-8")
        try:
            proc = popen(
                list(plan.argv),
                cwd=str(Path.cwd()),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=_child_env(),
                shell=False,
                **_popen_detach_kwargs(),
            )
        except Exception:
            log_handle.close()
            _restore_launch_log(log_path, previous_log)
            raise
        log_handle.close()
    except Exception:
        _release_launch_pid_claim(pid_path)
        raise

    pid = int(getattr(proc, "pid"))
    try:
        _record_child_pid(pid_path, pid)
    except OSError as exc:
        raise StudyLaunchError(
            f"Started CLI pid {pid} but could not persist {pid_path}: {exc}. "
            "Stop that process before launching again on this output_dir."
        ) from exc
    record = {
        "pid": pid,
        "argv": list(plan.argv),
        "study_identity_hash": plan.study_identity_hash,
        "run_count": plan.run_count,
        "output_dir": str(plan.output_dir),
        "confirm": plan.confirm,
        "force": plan.force,
        "workers": plan.workers,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "log": str(log_path),
        "launch_yaml": str(plan.launch_yaml_path),
    }
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return LaunchResult(
        pid=pid,
        argv=plan.argv,
        output_dir=plan.output_dir,
        launch_yaml_path=plan.launch_yaml_path,
        log_path=log_path,
        pid_path=pid_path,
        json_path=json_path,
        study_identity_hash=plan.study_identity_hash,
        run_count=plan.run_count,
        confirm=plan.confirm,
        force=plan.force,
    )


def _roots_or_default(roots: Sequence[Path] | None) -> tuple[Path, ...]:
    if roots is None:
        return tuple(Path(root).resolve() for root in default_study_viewer_roots())
    return tuple(Path(root).resolve() for root in roots)


def _ensure_within_roots(path: Path, roots: Sequence[Path] | None, *, label: str) -> Path:
    candidate = path.expanduser().resolve()
    if roots is None:
        return candidate
    allowed = tuple(Path(root).resolve() for root in roots)
    if allowed and not any(candidate.is_relative_to(root) for root in allowed):
        raise StudyLaunchError(
            f"{label} is outside the trusted local roots (cwd and store). "
            f"Resolved path: {candidate}"
        )
    return candidate


def _load_mapping_yaml(text: str) -> dict[str, Any]:
    if not str(text).strip():
        raise StudyLaunchError("StudySpec YAML is empty")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StudyLaunchError(f"Invalid StudySpec YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise StudyLaunchError("StudySpec YAML must contain a mapping")
    return dict(payload)


def _pinned_normalized_spec(
    yaml_text: str,
    *,
    roots: Sequence[Path],
) -> dict[str, Any]:
    payload = _load_mapping_yaml(yaml_text)
    try:
        normalized = validate_study_spec(normalize_study_spec(payload))
    except StudySpecError as exc:
        raise StudyLaunchError(str(exc)) from exc
    pinned = copy.deepcopy(normalized)
    _pin_dataset_paths(pinned, roots=roots)
    return pinned


def _absolute_argv_path(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def _claim_launch_pid_file(pid_path: Path, *, output_dir: Path) -> None:
    """Exclusive-create ``study.launch.pid`` before ``Popen`` (TOCTOU-safe).

    The in-flight placeholder is this process's pid (alive), not ``0``. A second
    tab that treated ``0`` as dead could unlink the claim and double-spawn.
    """
    existing = read_launch_pid_status(output_dir)
    if existing is not None and existing.alive:
        raise StudyLaunchError(
            f"A CLI study launch is already running (pid {existing.pid}) on "
            f"{output_dir}; wait for it to finish or use a different output_dir."
        )
    if pid_path.is_file():
        try:
            pid_path.unlink()
        except OSError as exc:
            raise StudyLaunchError(
                f"Could not clear stale launch pid file {pid_path}: {exc}"
            ) from exc
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(pid_path), flags)
    except FileExistsError as exc:
        raise StudyLaunchError(
            f"A CLI study launch claim already exists on {output_dir} "
            "(O_EXCL lost); wait or use a different output_dir."
        ) from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
    finally:
        os.close(fd)


def _release_launch_pid_claim(pid_path: Path) -> None:
    try:
        pid_path.unlink()
    except OSError:
        return


def _record_child_pid(pid_path: Path, pid: int) -> None:
    """Replace the in-flight parent-pid placeholder with the child pid."""
    text = f"{int(pid)}\n"
    try:
        pid_path.write_text(text, encoding="utf-8")
        return
    except OSError:
        fd = os.open(str(pid_path), os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(fd, text.encode("ascii"))
        finally:
            os.close(fd)


def _restore_launch_log(log_path: Path, previous: bytes | None) -> None:
    """Undo truncation when ``Popen`` fails (plan: do not wipe a prior log)."""
    try:
        if previous is None:
            log_path.unlink()
        else:
            log_path.write_bytes(previous)
    except OSError:
        return


def _pin_dataset_paths(spec: dict[str, Any], *, roots: Sequence[Path]) -> None:
    """Pin relative dataset paths (search-roots-then-cwd); sandbox the result.

    Mirrors promote's search-roots-then-cwd rule without importing promote.
    """
    study = spec.get("study")
    if not isinstance(study, dict):
        return
    dataset = study.get("dataset")
    if not isinstance(dataset, dict):
        return
    cwd = Path.cwd().resolve()
    resolved_roots = [Path(root).resolve() for root in roots]
    for key in _DATASET_PATH_KEYS:
        raw = dataset.get(key)
        if raw is None:
            continue
        if not isinstance(raw, (str, Path)):
            raise StudyLaunchError(f"study.dataset.{key} must be a path string")
        path = Path(raw)
        if path.is_absolute():
            pinned = path.resolve()
        else:
            found: Path | None = None
            search_roots = list(resolved_roots)
            if cwd not in search_roots:
                search_roots.append(cwd)
            for root in search_roots:
                candidate = (root / path).resolve()
                if candidate.is_file():
                    found = candidate
                    break
            pinned = found if found is not None else (cwd / path).resolve()
        pinned = _ensure_within_roots(pinned, resolved_roots, label=f"dataset.{key}")
        if not pinned.is_file():
            raise StudyLaunchError(
                f"Pinned dataset.{key} is not an existing file: {pinned}. "
                "Preview may succeed without the CSV; launch requires it."
            )
        dataset[key] = str(pinned)
    study["dataset"] = dataset
    spec["study"] = study


def _write_launch_yaml(path: Path, spec: Mapping[str, Any]) -> None:
    if path.name != LAUNCH_YAML_NAME:
        raise StudyLaunchError(f"Launch YAML must be named {LAUNCH_YAML_NAME}")
    text = yaml.safe_dump(
        dict(spec),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    path.write_text(text, encoding="utf-8")


def _child_env() -> dict[str, str]:
    """Copy the parent env; force unbuffered child stdout into ``study.launch.log``."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _popen_detach_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP: child outlives the Streamlit request / Ctrl+C.
        # CREATE_NO_WINDOW: no extra console flash.
        # Do **not** set DETACHED_PROCESS (0x8). That flag does not inherit
        # redirected stdout/stderr, so study.launch.log stays empty, and
        # CREATE_NO_WINDOW is ignored when combined with it (Win32).
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        return {"creationflags": flags, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}
