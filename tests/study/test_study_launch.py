"""RS-D9 Studies CLI-launch — argv parity, confirm gates, mocked Popen."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
import yaml

from thesistester.study.launch import (
    LAUNCH_JSON_NAME,
    LAUNCH_LOG_NAME,
    LAUNCH_PID_NAME,
    LAUNCH_YAML_NAME,
    STUDIES_LAUNCH_APPROVAL_KEY,
    STUDIES_LAUNCH_OUTPUT_DIR_KEY,
    LaunchPlan,
    StudyLaunchError,
    approval_payload,
    build_launch_plan,
    build_study_run_argv,
    default_output_dir_from_yaml,
    launch_pid_is_alive,
    pid_is_alive,
    plan_with_confirm,
    planned_argv,
    reset_launch_session_for_preview,
    spawn_launch,
)
from thesistester.study.preview import example_study_spec_path, preview_study_yaml


def _example_yaml() -> str:
    return example_study_spec_path().read_text(encoding="utf-8")


def _write_bars(root: Path) -> Path:
    # Pin targets must match the teaching example's dataset.path / tick_paths.
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    bars = data_dir / "es_15s.csv"
    bars.write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
    ticks = data_dir / "es_ticks.csv"
    ticks.write_text("Aggressor flag;Price;Volume;Time left;\n", encoding="utf-8")
    return bars


class _FakeProc:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def wait(self, timeout: float | None = None) -> int:  # pragma: no cover - must not be called
        raise AssertionError("spawn_launch must not wait on the CLI child")


def _plan(
    tmp_path: Path,
    *,
    yaml_text: str | None = None,
    cached_yaml: str | None = None,
    expanded: bool = True,
    run_count: int | None = 40,
    output_name: str = "out/study1",
    force: bool = False,
    workers: int | None = None,
) -> LaunchPlan:
    text = yaml_text if yaml_text is not None else _example_yaml()
    cached = cached_yaml if cached_yaml is not None else text
    _write_bars(tmp_path)
    return build_launch_plan(
        text,
        cached_yaml=cached,
        expanded=expanded,
        run_count=run_count,
        output_dir_raw=str(tmp_path / output_name),
        force=force,
        workers=workers,
        roots=(tmp_path,),
    )


def test_argv_under_threshold_omits_confirm(tmp_path: Path):
    plan = _plan(tmp_path, run_count=40)
    assert plan.needs_confirm is False
    assert plan.argv[1:5] == ("-m", "thesistester", "study", "run")
    assert plan.argv[5].endswith(LAUNCH_YAML_NAME)
    assert "--output-dir" in plan.argv
    assert "--confirm" not in plan.argv
    assert "--force" not in plan.argv
    assert "--workers" not in plan.argv
    assert "--confirm" not in planned_argv(plan)


def test_argv_over_threshold_requires_second_step(tmp_path: Path):
    plan = _plan(tmp_path, run_count=200)
    assert plan.needs_confirm is True
    assert "--confirm" not in plan.argv
    assert "--confirm" in planned_argv(plan)
    with pytest.raises(StudyLaunchError, match="bound approval"):
        plan_with_confirm(plan, None)
    with pytest.raises(StudyLaunchError, match="bind confirm"):
        spawn_launch(plan, popen=lambda *a, **k: _FakeProc(1))
    confirmed = plan_with_confirm(plan, approval_payload(plan))
    assert "--confirm" in confirmed.argv
    assert confirmed.confirm is True


def test_force_and_workers_flags(tmp_path: Path):
    plain = _plan(tmp_path, force=False, workers=None)
    assert "--force" not in plain.argv
    assert "--workers" not in plain.argv
    forced = _plan(tmp_path, force=True, workers=4)
    assert "--force" in forced.argv
    assert forced.argv[forced.argv.index("--workers") + 1] == "4"
    with pytest.raises(StudyLaunchError, match="workers"):
        _plan(tmp_path, workers=0)


def test_stale_yaml_refuses(tmp_path: Path):
    text = _example_yaml()
    _write_bars(tmp_path)
    with pytest.raises(StudyLaunchError, match="changed since"):
        build_launch_plan(
            text + "\n",
            cached_yaml=text,
            expanded=True,
            run_count=40,
            output_dir_raw=str(tmp_path / "out"),
            roots=(tmp_path,),
        )


def test_bound_triple_mismatch_refuses(tmp_path: Path):
    plan = _plan(tmp_path, run_count=200)
    other = dict(approval_payload(plan))
    other["run_count"] = 199
    with pytest.raises(StudyLaunchError, match="bound approval"):
        plan_with_confirm(plan, other)
    other = dict(approval_payload(plan))
    other["output_dir"] = str(tmp_path / "other")
    with pytest.raises(StudyLaunchError, match="bound approval"):
        plan_with_confirm(plan, other)


def test_over_cap_refuses(tmp_path: Path):
    text = _example_yaml()
    _write_bars(tmp_path)
    with pytest.raises(StudyLaunchError, match="PREVIEW_EXPAND_CAP"):
        build_launch_plan(
            text,
            cached_yaml=text,
            expanded=False,
            run_count=None,
            output_dir_raw=str(tmp_path / "out"),
            roots=(tmp_path,),
        )


def test_path_sandbox_refuses_and_writes_nothing(tmp_path: Path):
    text = _example_yaml()
    _write_bars(tmp_path)
    outside = Path("/tmp") / "thesistester-launch-escape"
    with pytest.raises(StudyLaunchError, match="outside the trusted"):
        build_launch_plan(
            text,
            cached_yaml=text,
            expanded=True,
            run_count=40,
            output_dir_raw=str(outside),
            roots=(tmp_path,),
        )
    assert not (outside / LAUNCH_YAML_NAME).exists()
    with pytest.raises(StudyLaunchError, match="outside the trusted"):
        build_launch_plan(
            text,
            cached_yaml=text,
            expanded=True,
            run_count=40,
            output_dir_raw=str(tmp_path / ".." / "escape"),
            roots=(tmp_path,),
        )


def test_spawn_writes_launch_yaml_not_spec_and_pins_dataset(tmp_path: Path):
    bars = _write_bars(tmp_path)
    plan = _plan(tmp_path)
    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeProc(4242)

    result = spawn_launch(plan, popen=fake_popen)
    assert result.pid == 4242
    assert captured["argv"] == list(plan.argv)
    out_flag = plan.argv.index("--output-dir")
    assert Path(plan.argv[out_flag + 1]).is_absolute()
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs.get("start_new_session") is True or "creationflags" in kwargs
    assert kwargs.get("close_fds") is True
    assert kwargs.get("shell") is False
    env = kwargs.get("env")
    assert isinstance(env, dict)
    assert env.get("PYTHONUNBUFFERED") == "1"
    assert (plan.output_dir / LAUNCH_YAML_NAME).is_file()
    assert not (plan.output_dir / "study.spec.yaml").exists()
    payload = yaml.safe_load((plan.output_dir / LAUNCH_YAML_NAME).read_text(encoding="utf-8"))
    pinned_path = Path(payload["study"]["dataset"]["path"])
    assert pinned_path.is_absolute()
    assert pinned_path == bars.resolve()
    assert payload["study"]["output_dir"] == "results/studies/pdPOC_ma_confluence_battery"
    from thesistester.study.expand import study_identity_hash
    from thesistester.study.schema import normalize_study_spec, validate_study_spec

    round_trip = study_identity_hash(validate_study_spec(normalize_study_spec(payload)))
    assert round_trip == plan.study_identity_hash
    preview = preview_study_yaml(_example_yaml())
    assert plan.study_identity_hash != preview.study_identity_hash
    assert (plan.output_dir / LAUNCH_LOG_NAME).is_file()
    assert (plan.output_dir / LAUNCH_PID_NAME).read_text(encoding="utf-8").strip() == "4242"
    assert (plan.output_dir / LAUNCH_JSON_NAME).is_file()


def test_spawn_pins_relative_tick_paths_like_dataset_path(tmp_path: Path):
    bars = _write_bars(tmp_path)
    ticks = (tmp_path / "data" / "es_ticks.csv").resolve()
    plan = _plan(tmp_path)
    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return _FakeProc(77)

    spawn_launch(plan, popen=fake_popen)
    payload = yaml.safe_load((plan.output_dir / LAUNCH_YAML_NAME).read_text(encoding="utf-8"))
    pinned_path = Path(payload["study"]["dataset"]["path"])
    pinned_ticks = [Path(item) for item in payload["study"]["dataset"]["tick_paths"]]
    assert pinned_path.is_absolute()
    assert pinned_path == bars.resolve()
    assert pinned_ticks == [ticks]
    assert all(item.is_absolute() for item in pinned_ticks)


def test_spawn_refuses_missing_tick_file(tmp_path: Path):
    _write_bars(tmp_path)
    (tmp_path / "data" / "es_ticks.csv").unlink()
    with pytest.raises(StudyLaunchError, match="tick_paths"):
        _plan(tmp_path)


def test_second_spawn_refused_while_pid_alive(tmp_path: Path):
    plan = _plan(tmp_path)
    live_pid = os.getpid()
    calls = {"n": 0}

    def fake_popen(argv, **kwargs):
        calls["n"] += 1
        return _FakeProc(live_pid)

    spawn_launch(plan, popen=fake_popen)
    with pytest.raises(StudyLaunchError, match="already running"):
        spawn_launch(plan, popen=fake_popen)
    assert calls["n"] == 1


def test_inflight_parent_pid_claim_refuses_nested_spawn(tmp_path: Path):
    plan = _plan(tmp_path)
    nested = {"refused": False}

    def fake_popen(argv, **kwargs):
        pid_text = (plan.output_dir / LAUNCH_PID_NAME).read_text(encoding="utf-8").strip()
        assert pid_text == str(os.getpid())
        with pytest.raises(StudyLaunchError, match="already running"):
            spawn_launch(plan, popen=lambda *a, **k: _FakeProc(1))
        nested["refused"] = True
        return _FakeProc(4242)

    spawn_launch(plan, popen=fake_popen)
    assert nested["refused"] is True
    assert (plan.output_dir / LAUNCH_PID_NAME).read_text(encoding="utf-8").strip() == "4242"


def test_child_pid_persists_if_path_write_text_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    plan = _plan(tmp_path)
    original = Path.write_text

    def flaky(self, data, encoding="utf-8", **kwargs):
        if self.name == LAUNCH_PID_NAME and "4242" in str(data):
            raise OSError("simulated write_text failure")
        return original(self, data, encoding=encoding, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky)
    result = spawn_launch(plan, popen=lambda *a, **k: _FakeProc(4242))
    assert result.pid == 4242
    assert (plan.output_dir / LAUNCH_PID_NAME).read_text(encoding="utf-8").strip() == "4242"


def test_popen_failure_restores_prior_log_and_releases_claim(tmp_path: Path):
    plan = _plan(tmp_path)
    plan.output_dir.mkdir(parents=True, exist_ok=True)
    log = plan.output_dir / LAUNCH_LOG_NAME
    log.write_text("prior-run\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("spawn failed")

    with pytest.raises(OSError, match="spawn failed"):
        spawn_launch(plan, popen=boom)
    assert log.read_text(encoding="utf-8") == "prior-run\n"
    assert not (plan.output_dir / LAUNCH_PID_NAME).exists()


def test_build_study_run_argv_parity():
    argv = build_study_run_argv(
        launch_yaml="/tmp/out/study.launch.yaml",
        output_dir="/tmp/out",
        confirm=True,
        force=True,
        workers=3,
        executable="/usr/bin/python3",
    )
    assert argv == [
        "/usr/bin/python3",
        "-m",
        "thesistester",
        "study",
        "run",
        "/tmp/out/study.launch.yaml",
        "--output-dir",
        "/tmp/out",
        "--workers",
        "3",
        "--confirm",
        "--force",
    ]


def test_launch_module_import_allow_list():
    source = Path("thesistester/study/launch.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {
        "thesistester.study.execute",
        "thesistester.cli",
        "thesistester.study.promote",
        "thesistester.study.tools",
        "thesistester.study.viewer",
        "thesistester.assistant",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in banned
            assert not node.module.startswith("thesistester.study.execute")
            names = {alias.name for alias in node.names}
            assert "run_experiment" not in names
            assert "run_batch" not in names
            assert "promote_study" not in names
            assert "run_study" not in names
            assert "expand_study" not in names
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in banned
    assert "STUDY.run" not in source
    assert "def launch_pid_is_alive" in source
    assert "PYTHONUNBUFFERED" in source


def test_windows_detach_kwargs_omit_detached_process(monkeypatch):
    """DETACHED_PROCESS drops redirected stdout; CREATE_NO_WINDOW must stand alone."""
    import subprocess

    from thesistester.study import launch as launch_mod

    monkeypatch.setattr(launch_mod.os, "name", "nt")
    kwargs = launch_mod._popen_detach_kwargs()
    flags = int(kwargs["creationflags"])
    detached = int(getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
    no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    new_group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    assert flags & detached == 0
    assert flags & no_window == no_window
    assert flags & new_group == new_group
    assert kwargs.get("close_fds") is True
    assert "start_new_session" not in kwargs


def test_posix_detach_kwargs_use_new_session(monkeypatch):
    from thesistester.study import launch as launch_mod

    monkeypatch.setattr(launch_mod.os, "name", "posix")
    kwargs = launch_mod._popen_detach_kwargs()
    assert kwargs.get("start_new_session") is True
    assert kwargs.get("close_fds") is True
    assert "creationflags" not in kwargs


def test_preview_yaml_still_loads_example():
    preview = preview_study_yaml(_example_yaml())
    assert preview.run_count == 40
    assert preview.needs_confirm is False


def test_invalid_yaml_is_launch_error(tmp_path: Path):
    text = "schema_version: 1\nstudy:\n  name: x\n  factors:\n    core: [pdPOC]\n"
    _write_bars(tmp_path)
    with pytest.raises(StudyLaunchError):
        build_launch_plan(
            text,
            cached_yaml=text,
            expanded=True,
            run_count=1,
            output_dir_raw=str(tmp_path / "out"),
            roots=(tmp_path,),
        )


def test_reset_launch_session_reseeds_output_dir_when_yaml_changes():
    old_yaml = "schema_version: 1\nstudy:\n  name: a\n  output_dir: out/old\n"
    new_yaml = "schema_version: 1\nstudy:\n  name: b\n  output_dir: out/new\n"
    state = {
        STUDIES_LAUNCH_OUTPUT_DIR_KEY: "out/old",
        STUDIES_LAUNCH_APPROVAL_KEY: {"run_count": 40},
    }
    reset_launch_session_for_preview(state, prev_cached_yaml=old_yaml, new_yaml=new_yaml)
    assert STUDIES_LAUNCH_APPROVAL_KEY not in state
    assert state[STUDIES_LAUNCH_OUTPUT_DIR_KEY] == "out/new"
    assert default_output_dir_from_yaml(new_yaml) == "out/new"

    # Same YAML re-preview: keep operator-edited output_dir, still clear approval.
    state[STUDIES_LAUNCH_OUTPUT_DIR_KEY] = "out/custom"
    state[STUDIES_LAUNCH_APPROVAL_KEY] = {"run_count": 40}
    reset_launch_session_for_preview(state, prev_cached_yaml=new_yaml, new_yaml=new_yaml)
    assert STUDIES_LAUNCH_APPROVAL_KEY not in state
    assert state[STUDIES_LAUNCH_OUTPUT_DIR_KEY] == "out/custom"


def test_pid_is_alive_self_and_missing():
    assert launch_pid_is_alive(os.getpid()) is True
    assert pid_is_alive is launch_pid_is_alive
    assert pid_is_alive(0) is False
    assert pid_is_alive(-1) is False
    assert pid_is_alive(2**30) is False


def test_pid_is_alive_dispatches_windows_helper(monkeypatch: pytest.MonkeyPatch):
    import thesistester.study.launch as launch_mod

    seen: list[int] = []

    def fake_windows(pid: int) -> bool:
        seen.append(pid)
        return pid == 42

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(launch_mod, "_pid_is_alive_windows", fake_windows)
    assert launch_mod.pid_is_alive(42) is True
    assert launch_mod.pid_is_alive(7) is False
    assert seen == [42, 7]


def test_pid_is_alive_windows_openprocess(monkeypatch: pytest.MonkeyPatch):
    import thesistester.study.launch as launch_mod

    class _Kernel:
        def __init__(self) -> None:
            self.closed = False
            self._err = 0

        def OpenProcess(self, access, inherit, pid):  # noqa: N802
            if pid == 7:
                return 1234
            if pid == 8:
                self._err = 5  # ERROR_ACCESS_DENIED
                return 0
            self._err = 87
            return 0

        def CloseHandle(self, handle):  # noqa: N802
            self.closed = handle == 1234
            return 1

        def GetLastError(self):  # noqa: N802
            return self._err

    kernel = _Kernel()

    class _Ctypes:
        class windll:
            kernel32 = kernel

    monkeypatch.setitem(__import__("sys").modules, "ctypes", _Ctypes())
    assert launch_mod._pid_is_alive_windows(7) is True
    assert kernel.closed is True
    assert launch_mod._pid_is_alive_windows(8) is True
    assert launch_mod._pid_is_alive_windows(9) is False


def test_windows_pid_alive_does_not_call_os_kill(monkeypatch: pytest.MonkeyPatch):
    import thesistester.study.launch as launch_mod

    def boom(*_a, **_k):
        raise AssertionError("os.kill must not run on Windows")

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os, "kill", boom)
    monkeypatch.setattr(launch_mod, "_pid_is_alive_windows", lambda pid: pid == 42)
    assert launch_mod.launch_pid_is_alive(42) is True
    assert launch_mod.launch_pid_is_alive(7) is False


def test_missing_pinned_csv_refuses(tmp_path: Path):
    spec = yaml.safe_load(_example_yaml())
    missing = tmp_path / "data" / "missing.csv"
    spec["study"]["dataset"]["path"] = str(missing)
    text = yaml.safe_dump(spec, sort_keys=False)
    with pytest.raises(StudyLaunchError, match="not an existing file"):
        build_launch_plan(
            text,
            cached_yaml=text,
            expanded=True,
            run_count=40,
            output_dir_raw=str(tmp_path / "out"),
            roots=(tmp_path,),
        )


def test_pins_subtimeframe_path(tmp_path: Path):
    bars = _write_bars(tmp_path)
    stf = tmp_path / "data" / "es_15s_r12.csv"
    stf.write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
    spec = yaml.safe_load(_example_yaml())
    spec["study"]["dataset"]["subtimeframe_path"] = "data/es_15s_r12.csv"
    text = yaml.safe_dump(spec, sort_keys=False)
    plan = build_launch_plan(
        text,
        cached_yaml=text,
        expanded=True,
        run_count=40,
        output_dir_raw=str(tmp_path / "out/study1"),
        roots=(tmp_path,),
    )
    result = spawn_launch(plan, popen=lambda *a, **k: _FakeProc(11))
    payload = yaml.safe_load(result.launch_yaml_path.read_text(encoding="utf-8"))
    assert Path(payload["study"]["dataset"]["path"]) == bars.resolve()
    assert Path(payload["study"]["dataset"]["subtimeframe_path"]) == stf.resolve()


def test_confirm_rejects_preview_hash(tmp_path: Path):
    plan = _plan(tmp_path, run_count=200)
    preview = preview_study_yaml(_example_yaml())
    assert plan.study_identity_hash != preview.study_identity_hash
    stale = {
        "study_identity_hash": preview.study_identity_hash,
        "run_count": plan.run_count,
        "output_dir": str(plan.output_dir.resolve()),
    }
    with pytest.raises(StudyLaunchError, match="bound approval"):
        plan_with_confirm(plan, stale)
    confirmed = plan_with_confirm(plan, approval_payload(plan))
    assert confirmed.study_identity_hash == plan.study_identity_hash


def test_excl_lost_refuses_second_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan = _plan(tmp_path)

    def boom(*_a, **_k):
        raise FileExistsError("claimed")

    monkeypatch.setattr(os, "open", boom)
    with pytest.raises(StudyLaunchError, match="O_EXCL"):
        spawn_launch(plan, popen=lambda *a, **k: _FakeProc(99))
