"""QI-09-04 / B-8 — dispatch/payload tests for the nine zero-mention IDs.

QI-9 §5.1 capability matrix: these routed IDs had no test-file mention and no
dedicated behavioral coverage. ``get_handler`` had no unit test.
"""

from __future__ import annotations

from pathlib import Path

from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    LocalThesisRepository,
)
from thesistester.assistant.contracts import ResourceEnvelope
from thesistester.assistant.handlers import HANDLER_REGISTRY, get_handler, tool_limits_from_envelope
from thesistester.assistant.tools import AssistantTools, ToolLimits

# QI-9 §5.1 routed IDs with zero dedicated ID mentions at audit.
_ZERO_MENTION_IDS = (
    "HOME.workflow_guide",
    "DATA.inspect_dataset",
    "DATA.preview_resampled_timeframes",
    "DATA.manage_saved_datasets",
    "DATA.configure_roll_assumptions",
    "BACKTEST.manage_execution_defaults",
    "GRID.manage_execution_defaults",
    "VALIDATION.run_otf_matrix",
    "CLASSIC.propose_page_change",
)


def _orchestrator(tmp_path: Path) -> tuple[AssistantOrchestrator, AssistantTools]:
    tools = AssistantTools(data_roots=(tmp_path,))
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    # Keep monkeypatches on ``tools`` visible when the envelope allocates a
    # bounded AssistantTools (VALIDATION.run_otf_matrix uses _STANDARD_COMPUTE).
    orchestrator._tools_for_envelope = lambda limits: tools  # type: ignore[method-assign]
    return orchestrator, tools


def test_get_handler_returns_registry_callables_and_none_for_unknown():
    assert set(_ZERO_MENTION_IDS) <= set(HANDLER_REGISTRY)
    for capability_id, registered in HANDLER_REGISTRY.items():
        handler = get_handler(capability_id)
        assert handler is registered
        assert callable(handler)
    assert get_handler("DATA.load_ohlcv") is None
    assert get_handler("not.a_capability") is None


def test_zero_mention_ids_have_named_dispatch_payload_probes():
    """Fail closed if an inventory ID is mention-only (tuple / get_handler)."""
    source = Path(__file__).read_text(encoding="utf-8")
    for capability_id in _ZERO_MENTION_IDS:
        needle = f'capability_id="{capability_id}"'
        assert needle in source, f"{capability_id} has no named dispatch probe"


def test_zero_mention_ids_dispatch_is_not_unavailable(tmp_path):
    orchestrator, _tools = _orchestrator(tmp_path)
    for capability_id in _ZERO_MENTION_IDS:
        result = orchestrator.dispatch(AssistantRequest(capability_id=capability_id, payload={}))
        assert result.capability_id == capability_id
        assert result.status in {"completed", "failed", "approval_required"}


def test_tool_limits_from_envelope_projects_or_keeps_defaults():
    defaults = ToolLimits()
    empty = tool_limits_from_envelope(ResourceEnvelope())
    assert empty.max_grid_cells == defaults.max_grid_cells
    assert empty.max_simulations == defaults.max_simulations
    assert empty.max_walk_forward_matrix_cells == defaults.max_walk_forward_matrix_cells

    projected = tool_limits_from_envelope(
        ResourceEnvelope(max_grid_cells=4, max_simulations=8, max_walk_forward_folds=3),
        base=ToolLimits(max_grid_cells=99, max_simulations=99, max_walk_forward_matrix_cells=99),
    )
    assert projected.max_grid_cells == 4
    assert projected.max_simulations == 8
    assert projected.max_walk_forward_matrix_cells == 3


def test_home_workflow_guide_dispatch_returns_guide(tmp_path):
    orchestrator, _tools = _orchestrator(tmp_path)
    result = orchestrator.dispatch(
        AssistantRequest(capability_id="HOME.workflow_guide", payload={})
    )
    assert result.status == "completed"
    assert result.payload["guide"] == (
        "Draft explicit research assumptions, validate a RunSpec, confirm it, "
        "then execute through the assistant orchestrator."
    )


def test_data_inspect_dataset_dispatch_and_payload(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    monkeypatch.setattr(
        tools, "describe_local_dataset", lambda dataset_id: {"dataset_id": dataset_id}
    )
    result = orchestrator.dispatch(
        AssistantRequest(capability_id="DATA.inspect_dataset", payload={"dataset_id": "ds_one"})
    )
    assert result.status == "completed"
    assert result.payload["dataset_id"] == "ds_one"

    missing = orchestrator.dispatch(
        AssistantRequest(capability_id="DATA.inspect_dataset", payload={"dataset_id": "  "})
    )
    assert missing.status == "failed"
    assert "dataset_id" in missing.payload["error"]["message"]


def test_data_manage_saved_datasets_list_describe_and_unknown(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    monkeypatch.setattr(tools, "list_local_datasets", lambda: [{"dataset_id": "ds_a"}])
    monkeypatch.setattr(
        tools, "describe_local_dataset", lambda dataset_id: {"dataset_id": dataset_id}
    )

    listed = orchestrator.dispatch(
        AssistantRequest(capability_id="DATA.manage_saved_datasets", payload={"action": "list"})
    )
    assert listed.status == "completed"
    assert listed.payload["datasets"] == [{"dataset_id": "ds_a"}]

    described = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.manage_saved_datasets",
            payload={"action": "describe", "dataset_id": "ds_a"},
        )
    )
    assert described.status == "completed"
    assert described.payload["dataset_id"] == "ds_a"

    gated = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.manage_saved_datasets",
            payload={"action": "delete"},
        )
    )
    assert gated.status == "approval_required"

    rejected = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.manage_saved_datasets",
            payload={"action": "delete"},
        ),
        confirmed=True,
    )
    assert rejected.status == "failed"
    assert "list and describe" in rejected.payload["error"]["message"]


def test_data_preview_resampled_timeframes_dispatch(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    calls: list[tuple[str, str, int]] = []

    def _preview(bundle_path, *, timeframe, max_rows):
        calls.append((bundle_path, timeframe, max_rows))
        return [{"close": 1.0}]

    monkeypatch.setattr(tools, "preview_bundle_resample", _preview)
    result = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.preview_resampled_timeframes",
            payload={"bundle_path": "/tmp/b.zip", "timeframe": "5min", "max_rows": 10},
        )
    )
    assert result.status == "completed"
    assert result.payload["rows"] == [{"close": 1.0}]
    assert calls == [("/tmp/b.zip", "5min", 10)]

    missing = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.preview_resampled_timeframes",
            payload={"bundle_path": "", "timeframe": "5min"},
        )
    )
    assert missing.status == "failed"
    assert "bundle_path" in missing.payload["error"]["message"]
    missing_tf = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.preview_resampled_timeframes",
            payload={"bundle_path": "/tmp/b.zip", "timeframe": "  "},
        )
    )
    assert missing_tf.status == "failed"
    assert "timeframe" in missing_tf.payload["error"]["message"]


def test_data_configure_roll_assumptions_dispatch(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    monkeypatch.setattr(
        tools,
        "validate_bundle_roll_assumptions",
        lambda bundle_path, **kwargs: {"ok": True, "path": bundle_path, **kwargs},
    )
    result = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.configure_roll_assumptions",
            payload={
                "bundle_path": "/tmp/roll.zip",
                "contract_column": "sym",
                "roll_method": "calendar",
            },
        )
    )
    assert result.status == "completed"
    assert result.payload["ok"] is True
    assert result.payload["contract_column"] == "sym"
    assert result.payload["roll_method"] == "calendar"
    missing = orchestrator.dispatch(
        AssistantRequest(
            capability_id="DATA.configure_roll_assumptions", payload={"bundle_path": ""}
        )
    )
    assert missing.status == "failed"
    assert "bundle_path" in missing.payload["error"]["message"]


def test_backtest_manage_execution_defaults_get_save_clear(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    store = {"backtest": {"stop_loss_ticks": 8}}
    monkeypatch.setattr(
        tools, "get_execution_defaults", lambda: {"backtest": store["backtest"], "grid": {}}
    )
    monkeypatch.setattr(
        tools,
        "save_backtest_execution_defaults",
        lambda defaults: store.update({"backtest": defaults}),
    )
    monkeypatch.setattr(
        tools, "clear_backtest_execution_defaults", lambda: store.update({"backtest": {}})
    )

    got = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BACKTEST.manage_execution_defaults",
            payload={"action": "get"},
        )
    )
    assert got.status == "completed"
    assert got.payload["defaults"]["stop_loss_ticks"] == 8

    gated = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BACKTEST.manage_execution_defaults",
            payload={"action": "save", "defaults": {"stop_loss_ticks": 12}},
        )
    )
    assert gated.status == "approval_required"
    assert store["backtest"]["stop_loss_ticks"] == 8

    saved = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BACKTEST.manage_execution_defaults",
            payload={"action": "save", "defaults": {"stop_loss_ticks": 12}},
        ),
        confirmed=True,
    )
    assert saved.status == "completed"
    assert saved.payload["saved"] is True
    assert store["backtest"]["stop_loss_ticks"] == 12

    cleared = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BACKTEST.manage_execution_defaults",
            payload={"action": "clear"},
        ),
        confirmed=True,
    )
    assert cleared.status == "completed"
    assert cleared.payload["cleared"] is True

    bad = orchestrator.dispatch(
        AssistantRequest(
            capability_id="BACKTEST.manage_execution_defaults",
            payload={"action": "save", "defaults": "nope"},
        ),
        confirmed=True,
    )
    assert bad.status == "failed"
    assert "object" in bad.payload["error"]["message"]


def test_grid_manage_execution_defaults_get_save_clear(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    store = {"grid": {"metric": "expectancy"}}
    monkeypatch.setattr(
        tools, "get_execution_defaults", lambda: {"backtest": {}, "grid": store["grid"]}
    )
    monkeypatch.setattr(
        tools, "save_grid_execution_defaults", lambda defaults: store.update({"grid": defaults})
    )
    monkeypatch.setattr(tools, "clear_grid_execution_defaults", lambda: store.update({"grid": {}}))

    got = orchestrator.dispatch(
        AssistantRequest(capability_id="GRID.manage_execution_defaults", payload={"action": "get"})
    )
    assert got.status == "completed"
    assert got.payload["defaults"]["metric"] == "expectancy"

    gated = orchestrator.dispatch(
        AssistantRequest(
            capability_id="GRID.manage_execution_defaults",
            payload={"defaults": {"metric": "pf"}},
        )
    )
    assert gated.status == "approval_required"
    assert store["grid"]["metric"] == "expectancy"

    saved = orchestrator.dispatch(
        AssistantRequest(
            capability_id="GRID.manage_execution_defaults",
            payload={"defaults": {"metric": "pf"}},
        ),
        confirmed=True,
    )
    assert saved.status == "completed"
    assert saved.payload["saved"] is True
    assert store["grid"]["metric"] == "pf"

    cleared = orchestrator.dispatch(
        AssistantRequest(
            capability_id="GRID.manage_execution_defaults", payload={"action": "clear"}
        ),
        confirmed=True,
    )
    assert cleared.status == "completed"
    assert cleared.payload["cleared"] is True

    bad = orchestrator.dispatch(
        AssistantRequest(
            capability_id="GRID.manage_execution_defaults",
            payload={"defaults": "nope"},
        ),
        confirmed=True,
    )
    assert bad.status == "failed"
    assert "object" in bad.payload["error"]["message"]


def test_validation_run_otf_matrix_dispatch(tmp_path, monkeypatch):
    orchestrator, tools = _orchestrator(tmp_path)
    monkeypatch.setattr(
        tools,
        "run_bundle_otf_validation",
        lambda bundle_path, **kwargs: {"bundle_path": bundle_path, **kwargs},
    )
    result = orchestrator.dispatch(
        AssistantRequest(
            capability_id="VALIDATION.run_otf_matrix",
            payload={
                "bundle_path": "/tmp/otf.zip",
                "instrument": "ES",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "train_fraction": 0.6,
            },
        ),
        confirmed=True,
    )
    assert result.status == "completed"
    assert result.payload["matrix"]["instrument"] == "ES"
    assert result.payload["matrix"]["stop_loss_ticks"] == 8
    assert result.payload["matrix"]["take_profit_ticks"] == 16
    assert result.payload["matrix"]["train_fraction"] == 0.6

    gated = orchestrator.dispatch(
        AssistantRequest(
            capability_id="VALIDATION.run_otf_matrix",
            payload={
                "bundle_path": "/tmp/otf.zip",
                "instrument": "ES",
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
            },
        )
    )
    assert gated.status == "approval_required"

    missing = orchestrator.dispatch(
        AssistantRequest(
            capability_id="VALIDATION.run_otf_matrix",
            payload={"bundle_path": "/tmp/otf.zip", "instrument": "  "},
        ),
        confirmed=True,
    )
    assert missing.status == "failed"
    assert "instrument" in missing.payload["error"]["message"]
    missing_path = orchestrator.dispatch(
        AssistantRequest(
            capability_id="VALIDATION.run_otf_matrix",
            payload={"bundle_path": "", "instrument": "ES"},
        ),
        confirmed=True,
    )
    assert missing_path.status == "failed"
    assert "bundle_path" in missing_path.payload["error"]["message"]


def test_classic_propose_page_change_validates_without_staging(tmp_path):
    orchestrator, _tools = _orchestrator(tmp_path)
    result = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CLASSIC.propose_page_change",
            payload={
                "target_page": "pages/7_Backtest.py",
                "draft_patch": {"stop_loss_ticks": 8, "take_profit_ticks": 12},
                "note": "B-8 payload test",
            },
        )
    )
    assert result.status == "completed"
    assert result.payload["staged"] is False
    assert result.payload["applied"] is False
    assert result.payload["proposal"]["target_page"] == "pages/7_Backtest.py"
    assert result.payload["proposal"]["note"] == "B-8 payload test"
    assert result.payload["proposal"]["draft_patch"]["stop_loss_ticks"] == 8.0
    assert result.payload["proposal"]["draft_patch"]["take_profit_ticks"] == 12.0

    rejected = orchestrator.dispatch(
        AssistantRequest(
            capability_id="CLASSIC.propose_page_change",
            payload={"target_page": "pages/7_Backtest.py", "draft_patch": {}, "note": "x"},
        )
    )
    assert rejected.status == "failed"
    assert "non-empty object" in rejected.payload["error"]["message"]


def test_time_analyze_and_pipeline_run_experiment_payloads(tmp_path, monkeypatch):
    """Adjacent routed handlers so ``handlers.py`` clears the B-8 ≥ 70% gate."""
    orchestrator, tools = _orchestrator(tmp_path)
    monkeypatch.setattr(
        tools,
        "summarize_bundle_time_analysis",
        lambda bundle_path, **kwargs: [{"n": 12, "path": bundle_path, **kwargs}],
    )
    timed = orchestrator.dispatch(
        AssistantRequest(
            capability_id="TIME.analyze",
            payload={"bundle_path": "/tmp/t.zip", "group_col": "entry_hour", "min_trades": 5},
        )
    )
    assert timed.status == "completed"
    assert timed.payload["groups"][0]["n"] == 12
    assert timed.payload["groups"][0]["group_col"] == "entry_hour"
    assert timed.payload["groups"][0]["min_trades"] == 5
    missing_time = orchestrator.dispatch(
        AssistantRequest(capability_id="TIME.analyze", payload={"bundle_path": ""})
    )
    assert missing_time.status == "failed"
    assert "bundle_path" in missing_time.payload["error"]["message"]

    monkeypatch.setattr(tools, "run_experiment", lambda spec: {"ok": True, "spec": spec})
    monkeypatch.setattr(
        tools,
        "run_experiment_to_bundle",
        lambda spec, output_path: {"ok": True, "path": output_path},
    )
    gated_pipeline = orchestrator.dispatch(
        AssistantRequest(
            capability_id="PIPELINE.run_experiment", payload={"run_spec": {"dataset": {}}}
        )
    )
    assert gated_pipeline.status == "approval_required"

    ran = orchestrator.dispatch(
        AssistantRequest(
            capability_id="PIPELINE.run_experiment", payload={"run_spec": {"dataset": {}}}
        ),
        confirmed=True,
    )
    assert ran.status == "completed"
    assert ran.payload["ok"] is True

    bundled = orchestrator.dispatch(
        AssistantRequest(
            capability_id="PIPELINE.run_experiment",
            payload={"run_spec": {"dataset": {}}, "output_path": "/tmp/out.zip"},
        ),
        confirmed=True,
    )
    assert bundled.status == "completed"
    assert bundled.payload["path"] == "/tmp/out.zip"

    bad_spec = orchestrator.dispatch(
        AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"run_spec": "nope"})
    )
    assert bad_spec.status == "failed"
    assert "run_spec" in bad_spec.payload["error"]["message"]
