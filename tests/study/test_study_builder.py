"""SB1 StudyDraft compiler — emit / hydrate, no execute import."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from thesistester.study.builder import (
    OTF_PRESETS,
    STUDIES_BUILDER_DRAFT_KEY,
    STUDIES_BUILDER_PENDING_SYNC_KEY,
    StudyDraft,
    TF_MODE_EXPLICIT,
    TF_MODE_NO_MA,
    TF_MODE_PRODUCT_DEFAULT,
    apply_levels_tf_mode,
    builder_token_catalog,
    coerce_partner_levels,
    default_study_draft,
    draft_from_mapping,
    draft_to_mapping,
    draft_warnings,
    emit_study_spec,
    emit_study_yaml,
    hydrate_study_draft,
    hydrate_study_yaml,
    infer_tf_mode,
    otf_from_preset_ids,
    otf_preset_ids,
    parse_csv_ints,
)
from thesistester.study.launch import (
    STUDIES_LAUNCH_APPROVAL_KEY,
    reset_launch_session_for_preview,
)
from thesistester.study.preview import (
    STUDIES_PREVIEW_CACHED_KEY,
    STUDIES_PREVIEW_CACHED_YAML_KEY,
    STUDIES_PREVIEW_YAML_KEY,
)
from thesistester.study.expand import expand_study, study_identity_hash
from thesistester.study.preview import preview_study_spec
from thesistester.study.schema import (
    StudySpecError,
    load_study_spec,
    normalize_study_spec,
    validate_study_spec,
)

GOLDEN_STUDY = Path("tests/fixtures/study/golden_study.yaml")
PDPOC_EXAMPLE = Path("examples/studies/pdPOC_ma_confluence_battery.yaml")
DOPEN_EXAMPLE = Path("examples/studies/dopen_ma_3c_mnq.yaml")


def _roundtrip_hash(path: Path) -> tuple[str, str]:
    loaded = load_study_spec(path)
    roundtrip = emit_study_spec(hydrate_study_draft(loaded))
    return study_identity_hash(loaded), study_identity_hash(roundtrip)


def test_default_draft_expands_to_two_cells():
    spec = emit_study_spec(default_study_draft())
    expansion = expand_study(spec)
    assert expansion.run_count == 2
    factors = spec["study"]["factors"]
    assert list(factors)[:5] == [
        "core_level",
        "partner_levels",
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
    ]
    assert "otf" not in factors
    assert "direction" not in factors
    assert spec["study"]["constants"]["direction"] == "both"


def test_identity_hash_roundtrip_golden():
    original, roundtrip = _roundtrip_hash(GOLDEN_STUDY)
    assert original == roundtrip


def test_identity_hash_roundtrip_pdpoc_example():
    original, roundtrip = _roundtrip_hash(PDPOC_EXAMPLE)
    assert original == roundtrip


def test_identity_hash_roundtrip_dopen_example():
    original, roundtrip = _roundtrip_hash(DOPEN_EXAMPLE)
    assert original == roundtrip


def test_explicit_null_group_by_roundtrip():
    """``group_by: null`` must not become the normalize-invented default list."""
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["report"]["group_by"] = None
    spec = validate_study_spec(normalize_study_spec(spec))
    assert spec["study"]["report"]["group_by"] is None
    roundtrip = emit_study_spec(hydrate_study_draft(spec))
    assert roundtrip["study"]["report"]["group_by"] is None
    assert study_identity_hash(spec) == study_identity_hash(roundtrip)


def test_explicit_null_description_roundtrip():
    """Schema-valid ``description: null`` must survive hydrate → emit."""
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["description"] = None
    spec = validate_study_spec(normalize_study_spec(spec))
    assert spec["study"]["description"] is None
    roundtrip = emit_study_spec(hydrate_study_draft(spec))
    assert roundtrip["study"]["description"] is None
    assert study_identity_hash(spec) == study_identity_hash(roundtrip)


def test_pdpoc_hydrate_stage_and_preview():
    loaded = load_study_spec(PDPOC_EXAMPLE)
    draft = hydrate_study_draft(loaded)
    assert draft.stage_mode == "filter"
    assert draft.stage_include["trigger"] == ["touch"]
    assert draft.stage_include["trigger_timeframe"] == ["base"]
    assert otf_preset_ids(draft.otf) == ("off", "5m", "15m", "30m", "combo")
    preview = preview_study_spec(emit_study_spec(draft))
    assert preview.run_count == 40
    assert preview.cartesian_product == 800
    assert preview.effective_run_count_estimate == 40
    assert preview.needs_confirm is False


def test_dopen_hydrate_fields():
    loaded = load_study_spec(DOPEN_EXAMPLE)
    draft = hydrate_study_draft(loaded)
    assert draft.format_profile == "quantower_history_exporter"
    assert draft.otf is None
    assert draft.trigger == ["3c"]
    assert draft.grid["enabled"] is True
    assert draft.grid["stop_loss_ticks_values"] == [20, 40, 60, 80]
    assert draft.grid["take_profit_ticks_values"] == [80, 160, 400, 800, 1000]
    assert draft.emit_entry_window is True
    spec = emit_study_spec(draft)
    assert spec["study"]["dataset"]["format_profile"] == "quantower_history_exporter"
    assert spec["study"]["constants"]["grid"]["stop_loss_ticks_values"] == [20, 40, 60, 80]
    assert "otf" not in spec["study"]["factors"]


def test_emit_mode_rules_listed_modes_only():
    draft = default_study_draft()
    draft.confluence_mode = ["global_cluster"]
    spec = emit_study_spec(draft)
    assert set(spec["study"]["mode_rules"]) == {"global_cluster"}
    draft.confluence_mode = ["anchor_rules"]
    spec = emit_study_spec(draft)
    assert set(spec["study"]["mode_rules"]) == {"anchor_rules"}
    assert spec["study"]["mode_rules"]["anchor_rules"]["confluence_rules"]["from_partners"] == (
        "required"
    )


def test_emit_batteries_always_have_enabled():
    draft = default_study_draft()
    draft.grid = {}
    draft.validation = {}
    draft.walk_forward = {}
    spec = emit_study_spec(draft)
    for key in ("grid", "validation", "walk_forward"):
        assert spec["study"]["constants"][key]["enabled"] is False
    dumped = yaml.safe_dump(spec["study"]["constants"])
    assert "grid: {}" not in dumped.replace("\n", " ")


def test_emit_rejects_unknown_token():
    draft = default_study_draft()
    draft.core_level = ["NOT_A_REAL_LEVEL"]
    with pytest.raises(StudySpecError, match="Unknown core_level token"):
        emit_study_spec(draft)


def test_emit_rejects_30min_trigger_timeframe():
    draft = default_study_draft()
    draft.trigger_timeframe = ["30min"]
    with pytest.raises(StudySpecError, match="30min is not a valid trigger timeframe"):
        emit_study_spec(draft)


def test_emit_rejects_empty_partner_set():
    draft = default_study_draft()
    draft.partner_levels = [[]]
    with pytest.raises(StudySpecError, match="partner_levels"):
        emit_study_spec(draft)


def test_emit_never_writes_null_timeframe_keys():
    draft = default_study_draft()
    draft.levels = {
        "sma_lengths": [50],
        "ema_lengths": [21],
        "sma_timeframes": None,
        "ema_timeframes": None,
    }
    spec = emit_study_spec(draft)
    levels = spec["study"]["levels"]
    assert "sma_timeframes" not in levels
    assert "ema_timeframes" not in levels
    dumped = emit_study_yaml(draft)
    assert "sma_timeframes: null" not in dumped
    assert "ema_timeframes: null" not in dumped


def test_direction_as_factor_vs_constant():
    constant = emit_study_spec(default_study_draft())
    assert constant["study"]["constants"]["direction"] == "both"
    assert "direction" not in constant["study"]["factors"]

    draft = default_study_draft()
    draft.direction_as_factor = True
    draft.direction_values = ["long", "short"]
    factored = emit_study_spec(draft)
    assert "direction" not in factored["study"]["constants"]
    assert factored["study"]["factors"]["direction"] == ["long", "short"]


def test_otf_preset_alias_duplicate_fails():
    draft = default_study_draft()
    draft.otf = [
        dict(OTF_PRESETS["5m"]),
        {
            "enabled": True,
            "timeframes": ["5min"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
        },
    ]
    with pytest.raises(StudySpecError, match="duplicates a prior OTF"):
        emit_study_spec(draft)


def test_builder_token_catalog_is_sorted_and_closed():
    catalog = builder_token_catalog(default_study_draft().levels)
    assert catalog == tuple(sorted(catalog))
    assert "pdPOC" in catalog
    assert "SMA_50_1min" in catalog
    assert "EMA_21_1min" in catalog
    assert "NOT_A_REAL_LEVEL" not in catalog


def test_draft_warnings_core_partner_overlap():
    draft = default_study_draft()
    draft.core_level = ["pdPOC"]
    draft.partner_levels = [["pdPOC", "SMA_50_1min"]]
    warnings = draft_warnings(draft)
    assert warnings
    assert "pdPOC" in warnings[0]
    # Emit still validates; expand (not emit) rejects core-in-partners.
    spec = emit_study_spec(draft)
    assert spec["study"]["factors"]["partner_levels"][0] == ["pdPOC", "SMA_50_1min"]


def test_hydrate_yaml_rejects_empty_and_non_mapping():
    with pytest.raises(StudySpecError, match="empty"):
        hydrate_study_yaml("  \n")
    with pytest.raises(StudySpecError, match="Invalid StudySpec YAML"):
        hydrate_study_yaml("study: [unterminated")
    with pytest.raises(StudySpecError, match="must contain a mapping"):
        hydrate_study_yaml("- just a list\n")


def test_emit_yaml_roundtrip_parses():
    text = emit_study_yaml(default_study_draft())
    payload = yaml.safe_load(text)
    assert isinstance(payload, dict)
    assert payload["schema_version"] == 1
    again = hydrate_study_yaml(text)
    assert again.name == "untitled_study"


def test_package_init_does_not_import_builder():
    source = Path("thesistester/study/__init__.py").read_text(encoding="utf-8")
    assert "builder" not in source


def test_builder_module_import_allow_list():
    source = Path("thesistester/study/builder.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {
        "thesistester.study.execute",
        "thesistester.study.launch",
        "thesistester.study.promote",
        "thesistester.study.tools",
        "thesistester.study.viewer",
        "thesistester.study.preview",
        "thesistester.cli",
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
            assert "preview_study_spec" not in names
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in banned
    assert "run_study" not in source
    assert "STUDY.run" not in source


def test_study_draft_type_is_dataclass():
    draft = default_study_draft()
    assert isinstance(draft, StudyDraft)
    assert draft.name == "untitled_study"


def test_draft_mapping_roundtrip_preserves_partner_sets():
    draft = default_study_draft()
    draft.partner_levels = [["SMA_50_1min"], ["EMA_21_1min"]]
    restored = draft_from_mapping(draft_to_mapping(draft))
    assert restored.partner_levels == [["SMA_50_1min"], ["EMA_21_1min"]]
    assert all(isinstance(item, list) for item in restored.partner_levels)


def test_coerce_partner_levels_never_returns_flat_list():
    assert coerce_partner_levels(["SMA_50_1min", "EMA_21_1min"]) == [
        ["SMA_50_1min", "EMA_21_1min"]
    ]
    assert coerce_partner_levels([["SMA_50_1min"], ["EMA_21_1min"]]) == [
        ["SMA_50_1min"],
        ["EMA_21_1min"],
    ]
    assert coerce_partner_levels(None) == []


def test_ema_21_5min_only_after_levels_imply_it():
    default_catalog = builder_token_catalog(default_study_draft().levels)
    assert "EMA_21_5min" not in default_catalog
    implied = apply_levels_tf_mode(
        {"ema_lengths": [21], "sma_lengths": [50]},
        "ema_timeframes",
        TF_MODE_EXPLICIT,
        ["5min"],
    )
    implied = apply_levels_tf_mode(implied, "sma_timeframes", TF_MODE_NO_MA, [])
    catalog = builder_token_catalog(implied)
    assert "EMA_21_5min" in catalog
    omitted = apply_levels_tf_mode(implied, "ema_timeframes", TF_MODE_PRODUCT_DEFAULT, [])
    assert "ema_timeframes" not in omitted


def test_infer_tf_mode_maps_omit_empty_explicit():
    assert infer_tf_mode({}, "sma_timeframes") == TF_MODE_PRODUCT_DEFAULT
    assert infer_tf_mode({"sma_timeframes": []}, "sma_timeframes") == TF_MODE_NO_MA
    assert infer_tf_mode({"sma_timeframes": ["1min"]}, "sma_timeframes") == TF_MODE_EXPLICIT


def test_otf_from_preset_ids_empty_omits_axis():
    assert otf_from_preset_ids([]) is None
    values = otf_from_preset_ids(["combo", "off"])
    assert values is not None
    assert [entry["enabled"] for entry in values] == [False, True]


def test_parse_csv_ints():
    assert parse_csv_ints("20, 40, 60") == [20, 40, 60]


def test_apply_to_preview_sequence_clears_cache_and_approval():
    yaml_text = emit_study_yaml(default_study_draft())
    state = {
        STUDIES_PREVIEW_CACHED_KEY: object(),
        STUDIES_PREVIEW_CACHED_YAML_KEY: "old yaml",
        STUDIES_LAUNCH_APPROVAL_KEY: {"run_count": 1},
    }
    prev_cached_yaml = state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
    state[STUDIES_PREVIEW_YAML_KEY] = yaml_text
    state.pop(STUDIES_PREVIEW_CACHED_KEY, None)
    state.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
    reset_launch_session_for_preview(
        state,
        prev_cached_yaml=prev_cached_yaml if isinstance(prev_cached_yaml, str) else None,
        new_yaml=yaml_text,
    )
    assert state[STUDIES_PREVIEW_YAML_KEY] == yaml_text
    assert STUDIES_PREVIEW_CACHED_KEY not in state
    assert STUDIES_PREVIEW_CACHED_YAML_KEY not in state
    assert STUDIES_LAUNCH_APPROVAL_KEY not in state


def test_pages_studies_build_tab_source_contract():
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "Build StudySpec" in page
    assert "Inspect output dir" in page
    assert "Preview StudySpec" in page
    assert "Apply to Preview" in page
    assert "Start from example" in page
    assert "preview_study_spec" in page
    assert "example_study_spec_path" in page
    assert "reset_launch_session_for_preview" in page
    assert STUDIES_BUILDER_DRAFT_KEY in page or "STUDIES_BUILDER_DRAFT_KEY" in page
    assert STUDIES_BUILDER_PENDING_SYNC_KEY in page or "STUDIES_BUILDER_PENDING_SYNC_KEY" in page
    assert "run_study" not in page
    assert "expand_study" not in page
    assert "Honesty" in page
