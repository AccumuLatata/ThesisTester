"""SB1 StudyDraft compiler — emit / hydrate, no execute import."""

from __future__ import annotations

import ast
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from thesistester.api import validate_run_spec
from thesistester.data.derive import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.data.loader import FORMAT_PROFILE_LABELS as LOADER_FORMAT_PROFILE_LABELS
from thesistester.data.loader import FORMAT_PROFILES
from thesistester.study.builder import (
    DEFAULT_FORMAT_PROFILE,
    DEFAULT_NEW_DRAFT_DATASET_PATH,
    DEFAULT_NEW_DRAFT_FORMAT_PROFILE,
    FORMAT_PROFILE_LABELS,
    INGESTION_MODE_PRIMARY,
    bind_format_profile_labels,
    OTF_PRESETS,
    STUDIES_BUILDER_DRAFT_KEY,
    STUDIES_BUILDER_PENDING_SYNC_KEY,
    StudyDraft,
    TF_MODE_EXPLICIT,
    TF_MODE_NO_MA,
    TF_MODE_PRODUCT_DEFAULT,
    WIDGET_KEY_INGESTION_MODE,
    apply_grid_tick_widgets,
    apply_levels_tf_mode,
    builder_token_catalog,
    clamp_widget_selection,
    coerce_partner_levels,
    coerce_whole_number,
    collect_stage_include,
    constrain_group_by,
    declared_factor_domains,
    default_study_draft,
    delete_stage_cells,
    draft_from_mapping,
    draft_to_mapping,
    draft_warnings,
    emit_study_spec,
    emit_study_yaml,
    hydrate_study_draft,
    hydrate_study_yaml,
    infer_tf_mode,
    normalize_builder_format_profile,
    otf_for_selected_presets,
    otf_from_preset_ids,
    otf_preset_ids,
    parse_csv_ints,
    preferred_group_by,
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


def test_default_draft_emits_15s_primary_contract():
    spec = emit_study_spec(default_study_draft())
    dataset = spec["study"]["dataset"]
    assert dataset["path"] == DEFAULT_NEW_DRAFT_DATASET_PATH
    assert dataset["format_profile"] == DEFAULT_NEW_DRAFT_FORMAT_PROFILE
    assert dataset["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert "subtimeframe_path" not in dataset
    assert spec["study"]["constants"]["backtest"]["intrabar_model"] == ("subtimeframe_conservative")
    expansion = expand_study(spec)
    assert expansion.run_count == 2
    for run in expansion.experiment["runs"]:
        validate_run_spec(run)


def test_study_draft_field_defaults_stay_legacy_safe():
    draft = StudyDraft()
    assert draft.dataset_path == "data/es_1m.csv"
    assert draft.format_profile == DEFAULT_FORMAT_PROFILE
    assert draft.ingestion_mode == INGESTION_MODE_PRIMARY
    assert draft.backtest["intrabar_model"] == "sl_first"
    spec = emit_study_spec(draft)
    assert "ingestion_mode" not in spec["study"]["dataset"]
    assert spec["study"]["dataset"]["format_profile"] == DEFAULT_FORMAT_PROFILE
    assert spec["study"]["dataset"]["path"] == "data/es_1m.csv"
    assert spec["study"]["constants"]["backtest"]["intrabar_model"] == "sl_first"


def test_builder_format_profile_labels_follow_loader_when_present():
    """Builder still exposes the live loader catalog when present."""
    from thesistester.study import builder as builder_mod

    assert builder_mod.FORMAT_PROFILE_LABELS is LOADER_FORMAT_PROFILE_LABELS
    assert list(builder_mod.FORMAT_PROFILE_LABELS) == list(LOADER_FORMAT_PROFILE_LABELS)
    assert "quantower_history_exporter" in builder_mod.FORMAT_PROFILE_LABELS


def test_bind_format_profile_labels_falls_back_when_loader_catalog_missing():
    class _StaleLoader:
        pass

    labels = bind_format_profile_labels(_StaleLoader())
    assert labels == bind_format_profile_labels(object())
    assert set(labels) == set(FORMAT_PROFILES)
    assert labels["quantower_history_exporter"] == "Quantower History Exporter (semicolon)"
    assert labels is not LOADER_FORMAT_PROFILE_LABELS


def test_normalize_builder_format_profile_allow_list():
    assert set(FORMAT_PROFILE_LABELS) == set(FORMAT_PROFILES)
    assert normalize_builder_format_profile(None) == DEFAULT_FORMAT_PROFILE
    assert normalize_builder_format_profile("") == DEFAULT_FORMAT_PROFILE
    assert normalize_builder_format_profile("  ") == DEFAULT_FORMAT_PROFILE
    assert normalize_builder_format_profile("not_a_profile") == "not_a_profile"
    assert (
        normalize_builder_format_profile("quantower_history_exporter")
        == "quantower_history_exporter"
    )


def test_emit_blank_format_profile_writes_canonical():
    for raw in (None, "", "  "):
        draft = StudyDraft()
        draft.format_profile = raw  # type: ignore[assignment]
        spec = emit_study_spec(draft)
        assert spec["study"]["dataset"]["format_profile"] == DEFAULT_FORMAT_PROFILE
        assert "ingestion_mode" not in spec["study"]["dataset"]


def test_emit_unknown_format_profile_fails_closed():
    draft = default_study_draft()
    draft.format_profile = "not_a_profile"
    with pytest.raises(StudySpecError, match="format_profile"):
        emit_study_spec(draft)
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["dataset"]["format_profile"] = "not_a_profile"
    hydrated = hydrate_study_draft(spec)
    assert hydrated.format_profile == "not_a_profile"
    with pytest.raises(StudySpecError, match="format_profile"):
        emit_study_spec(hydrated)


def test_emit_and_hydrate_quantower_format_profile():
    draft = default_study_draft()
    draft.format_profile = "quantower_history_exporter"
    spec = emit_study_spec(draft)
    assert spec["study"]["dataset"]["format_profile"] == "quantower_history_exporter"
    again = hydrate_study_draft(spec)
    assert again.format_profile == "quantower_history_exporter"
    mapping = draft_from_mapping({"format_profile": None})
    assert mapping.format_profile == DEFAULT_FORMAT_PROFILE


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


def test_identity_hash_roundtrip_golden_emits_canonical_format_profile():
    loaded = load_study_spec(GOLDEN_STUDY)
    assert "format_profile" not in loaded["study"]["dataset"]
    draft = hydrate_study_draft(loaded)
    assert draft.format_profile == DEFAULT_FORMAT_PROFILE
    first = emit_study_spec(draft)
    assert first["study"]["dataset"]["format_profile"] == DEFAULT_FORMAT_PROFILE
    second = emit_study_spec(hydrate_study_draft(first))
    assert study_identity_hash(first) == study_identity_hash(second)
    assert study_identity_hash(loaded) != study_identity_hash(first)


def test_identity_hash_roundtrip_pdpoc_example_emits_15s_primary_contract():
    loaded = load_study_spec(PDPOC_EXAMPLE)
    dataset = loaded["study"]["dataset"]
    assert dataset["path"] == "data/es_15s.csv"
    assert dataset["format_profile"] == "quantower_history_exporter"
    assert dataset["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert loaded["study"]["constants"]["backtest"]["intrabar_model"] == (
        "subtimeframe_conservative"
    )
    first = emit_study_spec(hydrate_study_draft(loaded))
    assert first["study"]["dataset"]["format_profile"] == "quantower_history_exporter"
    assert first["study"]["dataset"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert first["study"]["constants"]["backtest"]["intrabar_model"] == (
        "subtimeframe_conservative"
    )
    second = emit_study_spec(hydrate_study_draft(first))
    assert study_identity_hash(first) == study_identity_hash(second)


def test_identity_hash_roundtrip_dopen_example():
    original, roundtrip = _roundtrip_hash(DOPEN_EXAMPLE)
    assert original == roundtrip


def test_explicit_null_group_by_roundtrip():
    """``group_by: null`` must not become the normalize-invented default list."""
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["report"]["group_by"] = None
    spec["study"]["dataset"]["format_profile"] = DEFAULT_FORMAT_PROFILE
    spec = validate_study_spec(normalize_study_spec(spec))
    assert spec["study"]["report"]["group_by"] is None
    roundtrip = emit_study_spec(hydrate_study_draft(spec))
    assert roundtrip["study"]["report"]["group_by"] is None
    assert study_identity_hash(spec) == study_identity_hash(roundtrip)


def test_explicit_null_description_roundtrip():
    """Schema-valid ``description: null`` must survive hydrate → emit."""
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["description"] = None
    spec["study"]["dataset"]["format_profile"] = DEFAULT_FORMAT_PROFILE
    spec = validate_study_spec(normalize_study_spec(spec))
    assert spec["study"]["description"] is None
    roundtrip = emit_study_spec(hydrate_study_draft(spec))
    assert roundtrip["study"]["description"] is None
    assert study_identity_hash(spec) == study_identity_hash(roundtrip)


def test_pdpoc_hydrate_stage_and_preview():
    loaded = load_study_spec(PDPOC_EXAMPLE)
    draft = hydrate_study_draft(loaded)
    assert draft.ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert draft.format_profile == "quantower_history_exporter"
    assert draft.backtest["intrabar_model"] == "subtimeframe_conservative"
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
    banner = DOPEN_EXAMPLE.read_text(encoding="utf-8")
    assert "LEGACY 1m PRIMARY" in banner
    assert "ingestion_mode: 15s_primary_derive_1m" in banner
    loaded = load_study_spec(DOPEN_EXAMPLE)
    draft = hydrate_study_draft(loaded)
    assert draft.ingestion_mode == INGESTION_MODE_PRIMARY
    assert "ingestion_mode" not in loaded["study"]["dataset"]
    assert draft.format_profile == "quantower_history_exporter"
    assert draft.backtest["intrabar_model"] == "sl_first"
    assert draft.otf is None
    assert draft.trigger == ["3c"]
    assert draft.grid["enabled"] is True
    assert draft.grid["stop_loss_ticks_values"] == [20, 40, 60, 80]
    assert draft.grid["take_profit_ticks_values"] == [80, 160, 400, 800, 1000]
    assert draft.emit_entry_window is True
    spec = emit_study_spec(draft)
    assert spec["study"]["dataset"]["format_profile"] == "quantower_history_exporter"
    assert "ingestion_mode" not in spec["study"]["dataset"]
    assert spec["study"]["constants"]["backtest"]["intrabar_model"] == "sl_first"
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
            assert not node.module.startswith("pages")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in banned
                assert not alias.name.startswith("pages")
    assert "run_study" not in source
    assert "STUDY.run" not in source
    assert "pages.1_Data" not in source


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
    assert coerce_partner_levels(["SMA_50_1min", "EMA_21_1min"]) == [["SMA_50_1min", "EMA_21_1min"]]
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
    # Apply writes the Preview textarea key; Build body must run first.
    assert page.index("with build_tab:") < page.index("with preview_tab:")
    assert "Load YAML from Preview tab" in page
    assert "CSV format profile" in page
    assert "Format profile (optional)" not in page
    assert "FORMAT_PROFILE_LABELS.get(key, str(key))" in page
    assert "normalize_builder_format_profile(base.format_profile)" in page
    builder_import = page.split("from thesistester.study.builder import (")[1].split(")")[0]
    assert "FORMAT_PROFILE_LABELS" not in builder_import
    assert "normalize_builder_format_profile" not in builder_import
    assert "INGESTION_MODE_PRIMARY" not in builder_import
    assert "WIDGET_KEY_INGESTION_MODE" not in builder_import
    assert 'INGESTION_MODE_PRIMARY = "primary"' in page
    assert 'WIDGET_KEY_INGESTION_MODE = "_study_builder_ingestion_mode"' in page
    assert "def _draft_ingestion_mode" in page
    assert "def _apply_builder_ingestion_mode" in page
    assert 'getattr(draft, "ingestion_mode", None)' in page
    assert 'hasattr(draft, "ingestion_mode")' in page
    assert 'extra.get("ingestion_mode")' in page
    assert "from thesistester.study import builder" not in page
    assert "from thesistester.data import loader as _data_loader" in page
    assert "def _bind_format_profile_labels" in page
    assert "isinstance(labels, dict) and labels" in page
    assert "def normalize_builder_format_profile" in page
    assert "Download StudySpec YAML" in page
    assert "Delete selected rows" in page
    assert (
        "spawn_launch"
        not in page.split("def _render_build() -> None:")[1].split("with inspect_tab:")[0]
    )
    assert 'key="_study_builder_copy_spec"' in page
    assert "WIDGET_KEY_INGESTION_MODE" in page
    assert "Recommended: 15-second primary — derive one-minute canonical" in page
    assert "Legacy: one-minute primary (advanced)" in page


def test_ingestion_mode_widget_key_is_studies_scoped():
    import thesistester.study.builder as builder

    assert WIDGET_KEY_INGESTION_MODE == "_study_builder_ingestion_mode"
    assert "WIDGET_KEY_INGESTION_MODE" in builder.__all__


def test_pages_studies_ingest_radio_source_contract():
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    dataset = page.split('st.markdown("### Dataset")')[1].split('st.markdown("### Levels')[0]
    assert "WIDGET_KEY_INGESTION_MODE" in dataset
    assert dataset.index("WIDGET_KEY_INGESTION_MODE") < dataset.index("CSV format profile")
    assert "Recommended: 15-second primary — derive one-minute canonical" in page
    assert "Legacy: one-minute primary (advanced)" in page
    assert "subtimeframe_path" in dataset
    assert "WIDGET_KEY_SUBTIMEFRAME" not in page
    assert 'key="subtimeframe_path"' not in page
    tree = ast.parse(page)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("pages")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "pages.1_Data"
            assert not module.startswith("pages.")
    sync_body = page.split("def _sync_builder_widgets")[1].split("\ndef ")[0]
    assert "WIDGET_KEY_INGESTION_MODE" in sync_body
    assert "_draft_ingestion_mode(draft)" in sync_body
    read_body = page.split("def _draft_from_builder_widgets")[1].split("\ndef ")[0]
    assert "WIDGET_KEY_INGESTION_MODE" in read_body
    assert "_apply_builder_ingestion_mode(" in read_body
    assert "WIDGET_KEY_FORMAT_PROFILE" in read_body
    assert "WIDGET_KEY_INTRABAR_MODEL" in read_body
    ingest_assign = [
        line
        for line in read_body.splitlines()
        if "_apply_builder_ingestion_mode" in line or "WIDGET_KEY_INGESTION_MODE" in line
    ]
    assert ingest_assign
    assert all("WIDGET_KEY_FORMAT_PROFILE" not in line for line in ingest_assign)
    assert all("WIDGET_KEY_INTRABAR_MODEL" not in line for line in ingest_assign)
    radios = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "radio":
            continue
        key_kw = next((keyword for keyword in node.keywords if keyword.arg == "key"), None)
        if key_kw is None:
            continue
        value = key_kw.value
        if isinstance(value, ast.Name) and value.id == "WIDGET_KEY_INGESTION_MODE":
            radios.append(node)
    assert len(radios) == 1
    assert not any(keyword.arg == "on_change" for keyword in radios[0].keywords)
    build = page.split("def _render_build() -> None:")[1].split("with inspect_tab:")[0]
    assert "run_study" not in build
    assert "spawn_launch" not in build
    assert "_draft_ingestion_mode(base)" in build


def test_page_ingest_helpers_survive_pre_sia1_draft():
    """Page helpers must not AttributeError when StudyDraft lacks ingestion_mode."""
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    start = page.index("def _resolved_builder_ingestion_mode")
    end = page.index("\nst.title(")
    namespace = {
        "Any": object,
        "INGESTION_MODE_PRIMARY": INGESTION_MODE_PRIMARY,
    }
    exec(page[start:end], namespace)  # noqa: S102 — slice is the page-local helpers
    read = namespace["_draft_ingestion_mode"]
    apply = namespace["_apply_builder_ingestion_mode"]
    resolve = namespace["_resolved_builder_ingestion_mode"]

    class _StaleDraft:
        def __init__(self) -> None:
            self.dataset_extra = {"ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M}

    stale = _StaleDraft()
    assert read(stale) == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    apply(stale, INGESTION_MODE_PRIMARY)
    assert stale.dataset_extra["ingestion_mode"] == INGESTION_MODE_PRIMARY
    assert not hasattr(stale, "ingestion_mode")

    class _EmptyStale:
        def __init__(self) -> None:
            self.dataset_extra = {}

    empty = _EmptyStale()
    assert resolve(read(empty)) == INGESTION_MODE_PRIMARY

    current = StudyDraft()
    current.ingestion_mode = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert read(current) == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    current.ingestion_mode = "  "
    current.dataset_extra = {"ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M}
    assert read(current) == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    apply(current, INGESTION_MODE_PRIMARY)
    assert current.ingestion_mode == INGESTION_MODE_PRIMARY
    assert current.dataset_extra["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M


def test_pages_studies_unkeyed_buttons_have_unique_labels():
    """Streamlit runs every tab body; duplicate unkeyed labels raise DuplicateElementId."""
    tree = ast.parse(Path("pages/15_Studies.py").read_text(encoding="utf-8"))
    unkeyed: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "button":
            continue
        if any(keyword.arg == "key" for keyword in node.keywords):
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            label = node.args[0].value
            if isinstance(label, str):
                unkeyed.append(label)
    duplicates = sorted({label for label in unkeyed if unkeyed.count(label) > 1})
    assert duplicates == []


def test_emit_rejects_enabled_grid_without_tick_lists():
    draft = default_study_draft()
    draft.grid = {"enabled": True, "stop_loss_ticks_values": [], "take_profit_ticks_values": []}
    with pytest.raises(StudySpecError, match="stop_loss_ticks_values"):
        emit_study_spec(draft)
    draft.grid = {"enabled": True, "stop_loss_ticks_values": [20], "take_profit_ticks_values": []}
    with pytest.raises(StudySpecError, match="take_profit_ticks_values"):
        emit_study_spec(draft)
    draft.grid = {
        "enabled": True,
        "stop_loss_ticks_values": [20, 40],
        "take_profit_ticks_values": [80],
    }
    spec = emit_study_spec(draft)
    assert spec["study"]["constants"]["grid"]["stop_loss_ticks_values"] == [20, 40]


def test_apply_grid_tick_widgets_empty_overwrites_stale():
    grid = apply_grid_tick_widgets(
        {
            "enabled": True,
            "stop_loss_ticks_values": [20, 40],
            "take_profit_ticks_values": [80],
            "max_grid_cells": 12,
        },
        enabled=True,
        sl_text="  ",
        tp_text="",
    )
    assert grid["enabled"] is True
    assert grid["stop_loss_ticks_values"] == []
    assert grid["take_profit_ticks_values"] == []
    assert grid["max_grid_cells"] == 12
    disabled = apply_grid_tick_widgets(
        {
            "enabled": True,
            "stop_loss_ticks_values": [20, 40],
            "take_profit_ticks_values": [80],
        },
        enabled=False,
        sl_text="",
        tp_text="99",
    )
    assert disabled["enabled"] is False
    assert disabled["stop_loss_ticks_values"] == [20, 40]
    assert disabled["take_profit_ticks_values"] == [80]


def test_emit_empty_sma_lengths_does_not_invent_default_tokens():
    draft = default_study_draft()
    draft.levels["sma_lengths"] = []
    draft.partner_levels = [["pdHigh"]]
    spec = emit_study_spec(draft)
    assert spec["study"]["levels"]["sma_lengths"] == []
    catalog = builder_token_catalog(spec["study"]["levels"])
    assert "SMA_50_1min" not in catalog
    assert "SMA_200_1min" not in catalog


def test_empty_ma_lengths_do_not_merge_product_default_lengths():
    catalog = builder_token_catalog(
        {
            "sma_lengths": [],
            "ema_lengths": [],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
        }
    )
    assert not any(token.startswith("SMA_") for token in catalog)
    assert not any(token.startswith("EMA_") for token in catalog)
    omitted = builder_token_catalog({"sma_timeframes": ["1min"]})
    assert "SMA_50_1min" in omitted
    assert "SMA_200_1min" in omitted


def test_otf_for_selected_presets_keeps_original_dicts():
    original = [{"enabled": False, "keep": True}]
    kept = otf_for_selected_presets(["off"], original)
    assert kept == original
    assert kept is not original
    rebuilt = otf_for_selected_presets(["off", "5m"], original)
    assert rebuilt is not None
    assert [entry.get("enabled") for entry in rebuilt] == [False, True]
    assert "keep" not in rebuilt[0]


def test_coerce_whole_number_preserves_int_yaml():
    assert coerce_whole_number(0.0) == 0
    assert isinstance(coerce_whole_number(0.0), int)
    assert coerce_whole_number(0.5) == 0.5


def test_pdpoc_full_cartesian_is_800_and_needs_confirm():
    draft = hydrate_study_draft(load_study_spec(PDPOC_EXAMPLE))
    draft.stage_mode = None
    preview = preview_study_spec(emit_study_spec(draft))
    assert preview.cartesian_product == 800
    assert preview.effective_run_count_estimate == 800
    assert preview.run_count == 800
    assert preview.needs_confirm is True


def test_collect_stage_include_stays_inside_domains():
    domains = {
        "trigger": ["touch", "reject"],
        "trigger_timeframe": ["base", "1min"],
        "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
    }
    include = collect_stage_include(
        domains,
        {
            "trigger": ["touch", "not_a_trigger"],
            "trigger_timeframe": ["base"],
            "partner_levels": ["EMA_21_5min"],
            "core_level": ["pdPOC"],
        },
    )
    assert include == {
        "trigger": ["touch"],
        "trigger_timeframe": ["base"],
        "partner_levels": [["EMA_21_5min"]],
    }
    draft = hydrate_study_draft(load_study_spec(PDPOC_EXAMPLE))
    draft.stage_mode = "filter"
    draft.stage_include = include
    # pdPOC domains include these values; emit + preview is 40 vs 800 when
    # trigger/timeframe are the only includes (partner include would narrow).
    draft.stage_include = {"trigger": ["touch"], "trigger_timeframe": ["base"]}
    preview = preview_study_spec(emit_study_spec(draft))
    assert preview.run_count == 40
    assert preview.cartesian_product == 800


def test_preview_yaml_hydrate_emit_identity_hash():
    first = emit_study_spec(hydrate_study_draft(load_study_spec(PDPOC_EXAMPLE)))
    yaml_text = emit_study_yaml(hydrate_study_draft(first))
    again = emit_study_spec(hydrate_study_yaml(yaml_text))
    assert first["study"]["dataset"]["format_profile"] == "quantower_history_exporter"
    assert first["study"]["dataset"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert study_identity_hash(first) == study_identity_hash(again)


def test_dopen_hydrate_preview_is_eight_cells():
    draft = hydrate_study_draft(load_study_spec(DOPEN_EXAMPLE))
    assert draft.format_profile == "quantower_history_exporter"
    assert draft.grid["stop_loss_ticks_values"] == [20, 40, 60, 80]
    assert draft.grid["take_profit_ticks_values"] == [80, 160, 400, 800, 1000]
    preview = preview_study_spec(emit_study_spec(draft))
    assert preview.run_count == 8
    assert preview.needs_confirm is False


def test_delete_stage_cells_and_empty_emit_fails():
    draft = hydrate_study_draft(load_study_spec(PDPOC_EXAMPLE))
    spec = emit_study_spec(draft)
    factors = spec["study"]["factors"]

    def _copy_value(value):
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    cell_a = {axis: _copy_value(factors[axis][0]) for axis in factors}
    cell_b = {
        axis: _copy_value(factors[axis][1] if len(factors[axis]) > 1 else factors[axis][0])
        for axis in factors
    }
    draft.stage_mode = "explicit_cells"
    draft.stage_cells = [cell_a, cell_b]
    remaining = delete_stage_cells(draft.stage_cells, {0})
    assert len(remaining) == 1
    draft.stage_cells = remaining
    assert len(emit_study_spec(draft)["study"]["stage"]["cells"]) == 1
    draft.stage_cells = []
    with pytest.raises(StudySpecError, match="non-empty stage.cells"):
        emit_study_spec(draft)


def test_clamp_widget_selection_drops_stale_values():
    assert clamp_widget_selection(["touch", "reject", "gone"], ["touch", "break"]) == ["touch"]
    assert clamp_widget_selection(["otf", "trigger"], ["trigger", "partner_levels"]) == ["trigger"]
    assert clamp_widget_selection([0, 2, 5], [0, 1, 2]) == [0, 2]
    assert clamp_widget_selection("not-a-list", ["touch"]) == []


def test_group_by_cannot_include_undeclared_axes():
    keys = set(declared_factor_domains(default_study_draft()))
    assert "otf" not in keys
    assert constrain_group_by(["otf", "trigger", "not_a_factor"], keys) == ["trigger"]
    preferred = preferred_group_by(keys)
    assert "otf" not in preferred
    assert "trigger" in preferred


def test_hydrate_omitted_ingestion_mode_is_primary_and_reemit_omits_key():
    loaded = load_study_spec(GOLDEN_STUDY)
    assert "ingestion_mode" not in loaded["study"]["dataset"]
    draft = hydrate_study_draft(loaded)
    assert draft.ingestion_mode == INGESTION_MODE_PRIMARY
    assert "intrabar_model" not in draft.backtest
    spec = emit_study_spec(draft)
    assert "ingestion_mode" not in spec["study"]["dataset"]
    assert "intrabar_model" not in spec["study"]["constants"]["backtest"]


def test_draft_from_mapping_pre_sia_session_is_primary():
    payload = asdict(StudyDraft())
    payload.pop("ingestion_mode")
    restored = draft_from_mapping(payload)
    assert restored.ingestion_mode == INGESTION_MODE_PRIMARY
    assert restored.dataset_path == "data/es_1m.csv"
    assert restored.format_profile == DEFAULT_FORMAT_PROFILE
    assert restored.backtest["intrabar_model"] == "sl_first"
    assert draft_from_mapping(None).ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M


def test_hydrate_and_mapping_promote_ingestion_mode_from_extra():
    spec = load_study_spec(GOLDEN_STUDY)
    spec["study"]["dataset"]["format_profile"] = "quantower_history_exporter"
    spec["study"]["dataset"]["ingestion_mode"] = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    spec["study"]["constants"]["backtest"]["intrabar_model"] = "subtimeframe_conservative"
    draft = hydrate_study_draft(spec)
    assert draft.ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert "ingestion_mode" not in draft.dataset_extra
    emitted = emit_study_spec(draft)
    assert emitted["study"]["dataset"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M

    payload = asdict(StudyDraft())
    payload.pop("ingestion_mode")
    payload["dataset_extra"] = {
        "ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        "data_artifact_key": "abc",
    }
    restored = draft_from_mapping(payload)
    assert restored.ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert "ingestion_mode" not in restored.dataset_extra
    assert restored.dataset_extra["data_artifact_key"] == "abc"

    blank = asdict(StudyDraft())
    blank["ingestion_mode"] = "  "
    blank["dataset_extra"] = {"ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M}
    promoted = draft_from_mapping(blank)
    assert promoted.ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert "ingestion_mode" not in promoted.dataset_extra


def test_emit_15s_primary_rejects_subtimeframe_path_and_canonical_profile():
    draft = default_study_draft()
    draft.subtimeframe_path = "data/es_15s_lower.csv"
    with pytest.raises(StudySpecError, match="subtimeframe_path cannot be combined"):
        emit_study_spec(draft)
    draft = default_study_draft()
    draft.format_profile = DEFAULT_FORMAT_PROFILE
    with pytest.raises(StudySpecError, match="format_profile must be one of"):
        emit_study_spec(draft)
    draft = StudyDraft()
    draft.ingestion_mode = "ticks"
    with pytest.raises(StudySpecError, match="ingestion_mode must be one of"):
        emit_study_spec(draft)


def test_draft_warnings_sia_ingest_rows():
    sl_first = default_study_draft()
    sl_first.backtest["intrabar_model"] = "sl_first"
    assert draft_warnings(sl_first) == (
        "15s-primary attaches 15s for R12, but backtest.intrabar_model is sl_first "
        "(or omitted → sl_first). Data-page recommended model is subtimeframe_conservative.",
    )
    omitted = default_study_draft()
    omitted.backtest.pop("intrabar_model")
    assert draft_warnings(omitted)[0].startswith("15s-primary attaches 15s for R12")

    primary_quantower = StudyDraft()
    primary_quantower.format_profile = "quantower_history_exporter"
    assert draft_warnings(primary_quantower) == (
        "Quantower profile with primary ingestion treats the CSV as the decision "
        "timeframe. A 15-second History Exporter file needs "
        "ingestion_mode=15s_primary_derive_1m to match the Data-page recommended path.",
    )

    grid_mismatch = default_study_draft()
    grid_mismatch.grid = {
        "enabled": True,
        "stop_loss_ticks_values": [8],
        "take_profit_ticks_values": [16],
    }
    warnings = draft_warnings(grid_mismatch)
    assert (
        "grid.intrabar_model is sl_first (or omitted → sl_first) while backtest uses "
        "observed replay. Grid cells will not use the 15s R12 path."
    ) in warnings
    assert default_study_draft().ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert draft_warnings(default_study_draft()) == ()
