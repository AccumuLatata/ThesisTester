"""RS6 STUDY.* assistant capabilities — default-off, confirm, CLI parity."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from thesistester.assistant import (
    FEATURE_PARITY_REGISTRY,
    HANDLER_REGISTRY,
    AssistantOrchestrator,
    AssistantRequest,
    AssistantTools,
    CapabilityMode,
    ConfirmationLevel,
    OrchestrationStatus,
)
from thesistester.assistant.registry_audit import capability_audit_summary
from thesistester.assistant.repository import LocalThesisRepository
from thesistester.study.execute import run_study
from thesistester.study.schema import STUDY_SCHEMA_VERSION
from thesistester.assistant.tools import AssistantToolError
from thesistester.study.tools import (
    APPROVAL_PAYLOAD_KEY,
    StudyToolsDisabledError,
    ensure_study_tools_enabled,
    expand_study_capability,
    load_study_tools_settings,
    study_run_approval_preview,
    study_run_needs_confirm,
)


def _mini_study_yaml(
    path: Path,
    *,
    confirm_above_runs: int = 200,
    name: str = "pdPOC_rs6",
) -> Path:
    spec = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": name,
            "confirm_above_runs": confirm_above_runs,
            "workers": 1,
            "dataset": {
                "path": "bars.csv",
                "instrument": "ES",
                "source_timezone": "America/New_York",
            },
            "levels": {
                "sma_lengths": [50],
                "ema_lengths": [21],
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["5min"],
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "min_valid_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": {},
                "backtest": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "exposure_policy": "single_position",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": ["pdPOC"],
                "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
                "confluence_mode": ["global_cluster", "anchor_rules"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
                "anchor_rules": {
                    "selected_levels": [],
                    "anchor_level": "${core_level}",
                    "confluence_rules": {"from_partners": "required"},
                },
            },
        },
    }
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


def _enable_study_tools(monkeypatch, tmp_path: Path) -> Path:
    cfg = tmp_path / "assistant.toml"
    cfg.write_text(
        "[assistant.study_tools]\nenabled = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "thesistester.study.tools.DEFAULT_ASSISTANT_TOML",
        cfg,
    )
    return cfg


def _fake_executor_factory():
    from thesistester.study.execute import R18_INDEX_METRIC_KEYS, build_index_row_from_state
    import io
    import json
    import zipfile

    def _bundle(name: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"run_name": name}))
            archive.writestr(
                "trade_summary.json",
                json.dumps(
                    {
                        "trade_summary": {
                            "trade_count": 3,
                            "expectancy_r": 0.25,
                            "total_r": 0.75,
                            "max_drawdown_r": -0.5,
                            "profit_factor": 1.5,
                            "win_rate": 0.6,
                        }
                    }
                ),
            )
        return buffer.getvalue()

    def _executor(task):
        run_spec, _base = task
        name = str(run_spec["name"])
        state = {
            "dataset_id": "ds-test",
            "instrument": "ES",
            "execution_origin": "study",
            "cache_provenance": {"outcome": "miss"},
            "trade_summary": {
                "trade_count": 3,
                "expectancy_r": 0.25,
                "total_r": 0.75,
                "max_drawdown_r": -0.5,
                "profit_factor": 1.5,
                "win_rate": 0.6,
            },
            "best_grid_result": {},
            "validation_summary": {},
            "walk_forward_summary": {},
        }
        bundle = _bundle(name)
        row = build_index_row_from_state(name=name, state=state, bundle=bundle)
        assert set(row) == set(R18_INDEX_METRIC_KEYS)
        return {
            "status": "ok",
            "name": name,
            "bundle": bundle,
            "index_row": row,
            "error": None,
        }

    return _executor


def _orchestrator(tmp_path: Path) -> AssistantOrchestrator:
    return AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path.resolve(),)),
        repository=LocalThesisRepository(root=tmp_path / "repo"),
    )


def test_study_tools_default_disabled():
    settings = load_study_tools_settings()
    assert settings.enabled is False
    with pytest.raises(StudyToolsDisabledError, match="disabled"):
        ensure_study_tools_enabled()


def test_study_tools_missing_section_disabled(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "assistant.toml"
    cfg.write_text('[assistant]\nprovider = "openai"\n', encoding="utf-8")
    monkeypatch.setattr("thesistester.study.tools.DEFAULT_ASSISTANT_TOML", cfg)
    assert load_study_tools_settings().enabled is False


def test_study_tools_non_boolean_fails_closed(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "assistant.toml"
    cfg.write_text('[assistant.study_tools]\nenabled = "maybe"\n', encoding="utf-8")
    monkeypatch.setattr("thesistester.study.tools.DEFAULT_ASSISTANT_TOML", cfg)
    assert load_study_tools_settings().enabled is False


def test_study_capabilities_registered_executable_modes():
    by_id = {cap.capability_id: cap for cap in FEATURE_PARITY_REGISTRY}
    for capability_id, confirmation in (
        ("STUDY.expand", ConfirmationLevel.NONE),
        ("STUDY.run", ConfirmationLevel.EXPLICIT_CONFIRMATION),
        ("STUDY.report", ConfirmationLevel.NONE),
        ("STUDY.promote", ConfirmationLevel.NONE),
    ):
        cap = by_id[capability_id]
        assert cap.mode is CapabilityMode.EXECUTABLE
        assert cap.confirmation is confirmation
        assert capability_id in HANDLER_REGISTRY
    summary = capability_audit_summary()
    assert summary["invalid"] == 0
    assert summary["routed"] + summary["unsupported"] == summary["total"]


def test_disabled_handlers_refuse_via_orchestrator(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml")
    orch = _orchestrator(tmp_path)
    for capability_id, payload in (
        (
            "STUDY.expand",
            {"study_path": str(study), "output_dir": str(tmp_path / "out")},
        ),
        (
            "STUDY.run",
            {"study_path": str(study), "output_dir": str(tmp_path / "out")},
        ),
        ("STUDY.report", {"study_dir": str(tmp_path / "out")}),
        (
            "STUDY.promote",
            {
                "study_dir": str(tmp_path / "out"),
                "output": str(tmp_path / "draft.yaml"),
            },
        ),
    ):
        result = orch.dispatch(AssistantRequest(capability_id=capability_id, payload=payload))
        assert result.status == OrchestrationStatus.FAILED.value
        assert "disabled" in result.payload["error"]["message"].lower()


def test_expand_and_run_below_threshold_without_approval(tmp_path: Path, monkeypatch):
    _enable_study_tools(monkeypatch, tmp_path)
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    monkeypatch.setattr(
        "thesistester.study.execute.execute_study_cell",
        _fake_executor_factory(),
    )
    # Patch the executor used inside run_study via cell_executor path — tools
    # call run_study without cell_executor, so patch module symbol.
    monkeypatch.setattr(
        "thesistester.study.execute.execute_study_cell",
        _fake_executor_factory(),
    )
    # Also patch where run_study looks up default executor — it uses execute_study_cell
    # from the same module when cell_executor is None.

    orch = _orchestrator(tmp_path)
    expand = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.expand",
            payload={"study_path": str(study), "output_dir": str(out)},
        )
    )
    assert expand.status == OrchestrationStatus.COMPLETED.value
    assert expand.payload["run_count"] == 4
    assert (out / "experiment.yaml").is_file()

    assert study_run_needs_confirm({"study_path": str(study), "output_dir": str(out)}) is False

    run = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.run",
            payload={"study_path": str(study), "output_dir": str(out)},
        )
    )
    assert run.status == OrchestrationStatus.COMPLETED.value
    assert run.payload["executed"] == 4
    assert run.payload["ledger_summary"].get("ok") == 4


def test_run_over_threshold_requires_bound_approval(tmp_path: Path, monkeypatch):
    _enable_study_tools(monkeypatch, tmp_path)
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=2)
    out = tmp_path / "out"
    monkeypatch.setattr(
        "thesistester.study.execute.execute_study_cell",
        _fake_executor_factory(),
    )
    orch = _orchestrator(tmp_path)
    payload = {"study_path": str(study), "output_dir": str(out)}

    gated = orch.dispatch(AssistantRequest(capability_id="STUDY.run", payload=payload))
    assert gated.status == OrchestrationStatus.APPROVAL_REQUIRED.value
    approval = gated.payload[APPROVAL_PAYLOAD_KEY]
    assert approval["run_count"] == 4
    assert "study_identity_hash" in approval

    # Forged read-only action must not skip the STUDY.run confirm gate.
    spoofed = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.run",
            payload={**payload, "action": "list", APPROVAL_PAYLOAD_KEY: approval},
        )
    )
    assert spoofed.status == OrchestrationStatus.APPROVAL_REQUIRED.value

    # confirmed=True alone must not bypass the bound approval.
    bare = orch.dispatch(
        AssistantRequest(capability_id="STUDY.run", payload=payload),
        confirmed=True,
    )
    assert bare.status == OrchestrationStatus.FAILED.value
    assert "approval" in bare.payload["error"]["message"].lower()

    ok = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.run",
            payload={**payload, APPROVAL_PAYLOAD_KEY: approval},
        ),
        confirmed=True,
    )
    assert ok.status == OrchestrationStatus.COMPLETED.value
    assert ok.payload["executed"] == 4


def test_structured_dict_spec_validates_before_expand(tmp_path: Path, monkeypatch):
    _enable_study_tools(monkeypatch, tmp_path)
    study = _mini_study_yaml(tmp_path / "study.yaml")
    raw = yaml.safe_load(study.read_text(encoding="utf-8"))
    out = tmp_path / "out"
    result = expand_study_capability({"study_spec": raw, "output_dir": str(out)})
    assert result["run_count"] == 4
    assert (out / "study.spec.yaml").is_file()

    with pytest.raises(Exception, match=r"Unknown study keys|not_a_key"):
        expand_study_capability(
            {
                "study_spec": {**raw, "study": {**raw["study"], "not_a_key": 1}},
                "output_dir": str(tmp_path / "bad"),
            }
        )


def test_promote_overwrite_requires_force(tmp_path: Path, monkeypatch):
    _enable_study_tools(monkeypatch, tmp_path)
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    # Fake cells have trade_count=3; lower min_trades so ranked survivors exist.
    payload = yaml.safe_load(study.read_text(encoding="utf-8"))
    payload["study"]["report"] = {"primary_metric": "expectancy_r", "min_trades": 1}
    study.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(
        "thesistester.study.execute.execute_study_cell",
        _fake_executor_factory(),
    )
    run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    from thesistester.study.report import report_study

    report_study(out)
    draft = tmp_path / "draft.yaml"
    orch = _orchestrator(tmp_path)
    first = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.promote",
            payload={
                "study_dir": str(out),
                "output": str(draft),
                "top_n": 2,
            },
        )
    )
    assert first.status == OrchestrationStatus.COMPLETED.value
    assert draft.is_file()
    second = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.promote",
            payload={
                "study_dir": str(out),
                "output": str(draft),
                "top_n": 2,
            },
        )
    )
    assert second.status == OrchestrationStatus.FAILED.value
    forced = orch.dispatch(
        AssistantRequest(
            capability_id="STUDY.promote",
            payload={
                "study_dir": str(out),
                "output": str(draft),
                "top_n": 2,
                "force": True,
            },
        )
    )
    assert forced.status == OrchestrationStatus.COMPLETED.value


def test_run_study_capability_does_not_call_run_batch():
    import thesistester.study.tools as tools_mod
    import inspect

    source = inspect.getsource(tools_mod)
    assert "run_batch(" not in source
    assert "from thesistester.cli import" not in source
    assert "import thesistester.cli" not in source


def test_dict_study_spec_relative_dataset_path_uses_base_not_temp(tmp_path: Path, monkeypatch):
    """Dict materialization must not resolve bars against the TemporaryDirectory."""
    _enable_study_tools(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bars.csv").write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
    study = _mini_study_yaml(tmp_path / "study.yaml")
    raw = yaml.safe_load(study.read_text(encoding="utf-8"))
    # Keep relative dataset.path; expand should still succeed under tmp_path roots.
    assert raw["study"]["dataset"]["path"] == "bars.csv"
    out = tmp_path / "out"
    result = expand_study_capability(
        {"study_spec": raw, "output_dir": str(out)},
        data_roots=(tmp_path.resolve(),),
    )
    assert result["run_count"] == 4
    written = yaml.safe_load((out / "study.spec.yaml").read_text(encoding="utf-8"))
    dataset_path = Path(written["study"]["dataset"]["path"])
    assert dataset_path.is_absolute()
    assert dataset_path == (tmp_path / "bars.csv").resolve()
    assert "study_tools_" not in str(dataset_path)


def test_study_paths_outside_data_roots_are_refused(tmp_path: Path, monkeypatch):
    _enable_study_tools(monkeypatch, tmp_path)
    root = tmp_path / "sandbox"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    study = _mini_study_yaml(outside / "study.yaml")
    out = root / "out"

    with pytest.raises(AssistantToolError, match="outside the configured local data roots"):
        expand_study_capability(
            {"study_path": str(study), "output_dir": str(out)},
            data_roots=(root.resolve(),),
        )

    # Spec-embedded absolute dataset path must not bypass the sandbox.
    raw = yaml.safe_load(study.read_text(encoding="utf-8"))
    raw["study"]["dataset"]["path"] = str(outside / "secret_bars.csv")
    with pytest.raises(AssistantToolError, match="outside the configured local data roots"):
        expand_study_capability(
            {
                "study_spec": raw,
                "output_dir": str(out),
                "base_directory": str(root),
            },
            data_roots=(root.resolve(),),
        )

    with pytest.raises(AssistantToolError, match="outside the configured local data roots"):
        study_run_approval_preview(
            {
                "study_path": str(_mini_study_yaml(root / "ok.yaml")),
                "output_dir": str(outside / "escaped"),
            },
            data_roots=(root.resolve(),),
        )
