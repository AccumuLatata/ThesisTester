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
    LaunchPlan,
    StudyLaunchError,
    approval_payload,
    build_launch_plan,
    build_study_run_argv,
    plan_with_confirm,
    planned_argv,
    spawn_launch,
)
from thesistester.study.preview import example_study_spec_path, preview_study_yaml


def _example_yaml() -> str:
    return example_study_spec_path().read_text(encoding="utf-8")


def _write_bars(root: Path) -> Path:
    bars = root / "data" / "es_1m.csv"
    bars.parent.mkdir(parents=True, exist_ok=True)
    bars.write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
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
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs.get("start_new_session") is True or "creationflags" in kwargs
    assert (plan.output_dir / LAUNCH_YAML_NAME).is_file()
    assert not (plan.output_dir / "study.spec.yaml").exists()
    payload = yaml.safe_load((plan.output_dir / LAUNCH_YAML_NAME).read_text(encoding="utf-8"))
    pinned_path = Path(payload["study"]["dataset"]["path"])
    assert pinned_path.is_absolute()
    assert pinned_path == bars.resolve()
    assert payload["study"]["output_dir"] == str(plan.output_dir)
    assert (plan.output_dir / LAUNCH_LOG_NAME).is_file()
    assert (plan.output_dir / LAUNCH_PID_NAME).read_text(encoding="utf-8").strip() == "4242"
    assert (plan.output_dir / LAUNCH_JSON_NAME).is_file()


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
