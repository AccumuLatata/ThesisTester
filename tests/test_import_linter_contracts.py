"""B-10 / QI-12-07: import-linter contract file and C10 page-scoped gate."""

from __future__ import annotations

import ast
import configparser
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTLINTER = ROOT / ".importlinter"
STUDIES_PAGE = ROOT / "pages" / "15_Studies.py"

REQUIRED_CONTRACT_IDS = (
    "c1-preview-no-execute",
    "c2-viewer-independence",
    "c3-observatory-independence",
    "c4-launch-no-viewer-execute",
    "c5-admit-followup-independence",
    "c7-journal-no-engine-core",
    "c8-library-streamlit-allowlist",
    "c9-sim-core-no-admission",
)

# QI-15 §5.4 payloads. Values are (source_modules, forbidden_modules).
QI15_CONTRACTS = {
    "c1-preview-no-execute": (
        ("thesistester.study.preview",),
        ("thesistester.study.execute",),
    ),
    "c2-viewer-independence": (
        ("thesistester.study.viewer",),
        (
            "thesistester.study.cli_study",
            "thesistester.cli",
            "thesistester.study.execute",
            "thesistester.study.rollup",
            "thesistester.study.observatory",
            "plotly",
            "streamlit",
        ),
    ),
    "c3-observatory-independence": (
        ("thesistester.study.observatory",),
        (
            "thesistester.study.cli_study",
            "thesistester.study.execute",
            "streamlit",
            "plotly",
        ),
    ),
    "c4-launch-no-viewer-execute": (
        ("thesistester.study.launch",),
        ("thesistester.study.viewer", "thesistester.study.execute"),
    ),
    "c5-admit-followup-independence": (
        ("thesistester.study.admit_followup",),
        (
            "thesistester.study.execute",
            "thesistester.study.launch",
            "thesistester.study.viewer",
            "thesistester.cli",
            "streamlit",
        ),
    ),
    "c7-journal-no-engine-core": (
        ("thesistester.journal",),
        (
            "thesistester.engine.backtest",
            "thesistester.levels.all",
            "thesistester.engine.sim_core",
        ),
    ),
    "c8-library-streamlit-allowlist": (
        ("thesistester",),
        ("streamlit",),
    ),
    "c9-sim-core-no-admission": (
        ("thesistester.engine.sim_core",),
        ("thesistester.entry_window_policy", "thesistester.analytics"),
    ),
}

C8_STREAMLIT_ALLOWLIST = (
    "thesistester.app_state -> streamlit",
    "thesistester.classic_context -> streamlit",
    "thesistester.classic_ledger -> streamlit",
    "thesistester.classic_nav -> streamlit",
    "thesistester.classic_proposal -> streamlit",
    "thesistester.classic_record -> streamlit",
    "thesistester.assistant.llm -> streamlit",
    "thesistester.assistant.voice.xai_realtime -> streamlit",
)

EXPAND_TO_CLI = "thesistester.study.expand -> thesistester.cli"

C10_BANNED_BUILDER_NAMES = (
    "FORMAT_PROFILE_LABELS",
    "normalize_builder_format_profile",
    "INGESTION_MODE_PRIMARY",
    "WIDGET_KEY_INGESTION_MODE",
)


def _load_importlinter() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    read = parser.read(IMPORTLINTER, encoding="utf-8")
    assert read == [str(IMPORTLINTER)]
    return parser


def _multiline(parser: configparser.ConfigParser, section: str, key: str) -> tuple[str, ...]:
    raw = parser.get(section, key, fallback="")
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def test_importlinter_declares_qi15_contracts():
    text = IMPORTLINTER.read_text(encoding="utf-8")
    parser = _load_importlinter()
    assert parser.get("importlinter", "root_package") == "thesistester"
    assert parser.get("importlinter", "include_external_packages").lower() == "true"
    assert "expand → cli → cli_study" in text or "expand -> cli -> cli_study" in text
    for contract_id in REQUIRED_CONTRACT_IDS:
        section = f"importlinter:contract:{contract_id}"
        assert parser.has_section(section), contract_id
        assert parser.get(section, "type") == "forbidden", contract_id
        sources, forbidden = QI15_CONTRACTS[contract_id]
        assert _multiline(parser, section, "source_modules") == sources, contract_id
        assert _multiline(parser, section, "forbidden_modules") == forbidden, contract_id
        # Blanket allow_indirect_imports hides new chains (C1/C4 hole).
        assert parser.get(section, "allow_indirect_imports", fallback="false").lower() != "true"
    # C6 is a call-ban; C10 is page-scoped (not a library source module).
    assert not any(s.startswith("importlinter:contract:c6-") for s in parser.sections())
    assert "C10" in text
    assert "pages/15_Studies.py" in text
    assert "FORMAT_PROFILE_LABELS" in text


def test_c1_c4_ignore_only_expand_to_cli_hop():
    parser = _load_importlinter()
    for contract_id in ("c1-preview-no-execute", "c4-launch-no-viewer-execute"):
        section = f"importlinter:contract:{contract_id}"
        ignored = _multiline(parser, section, "ignore_imports")
        assert ignored == (EXPAND_TO_CLI,), contract_id
        assert parser.get(section, "unmatched_ignore_imports_alerting") == "error"


def test_c7_does_not_forbid_engine_signals():
    parser = _load_importlinter()
    forbidden = _multiline(
        parser, "importlinter:contract:c7-journal-no-engine-core", "forbidden_modules"
    )
    assert "thesistester.engine.signals" not in forbidden
    assert all("engine.signals" not in item for item in forbidden)


def test_c8_streamlit_allowlist_is_explicit():
    parser = _load_importlinter()
    section = "importlinter:contract:c8-library-streamlit-allowlist"
    ignored = _multiline(parser, section, "ignore_imports")
    assert ignored == C8_STREAMLIT_ALLOWLIST
    assert parser.get(section, "unmatched_ignore_imports_alerting") == "error"


def test_c9_sim_core_does_not_import_admission_or_analytics():
    """QI-4 §6.3 / C9 (B-19): sim_core ↛ entry_window_policy / analytics.*."""
    source = (ROOT / "thesistester" / "engine" / "sim_core.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = ("thesistester.entry_window_policy", "thesistester.analytics")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == item or alias.name.startswith(f"{item}.") for item in banned
                ), alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(
                node.module == item or node.module.startswith(f"{item}.") for item in banned
            ), node.module
    parser = _load_importlinter()
    section = "importlinter:contract:c9-sim-core-no-admission"
    sources, forbidden = QI15_CONTRACTS["c9-sim-core-no-admission"]
    assert _multiline(parser, section, "source_modules") == sources
    assert _multiline(parser, section, "forbidden_modules") == forbidden


def test_c9_sim_core_contract_is_kept():
    """C9 is kept today (unlike C7). Warn-first CI still reports the status."""
    result = subprocess.run(
        ["lint-imports", "--config", str(IMPORTLINTER), "--no-cache", "--no-logo"],
        check=False,
        capture_output=True,
        text=True,
    )
    out = f"{result.stdout}\n{result.stderr}"
    assert "C9 sim_core ↛ entry_window_policy / analytics (R22) KEPT" in out


def test_importlinter_config_is_loadable():
    """Config/module errors fail here. Kept/broken status stays CI-warn-first."""
    result = subprocess.run(
        ["lint-imports", "--config", str(IMPORTLINTER), "--no-cache", "--no-logo"],
        check=False,
        capture_output=True,
        text=True,
    )
    out = f"{result.stdout}\n{result.stderr}"
    assert "Contracts:" in out
    for label in ("C1", "C2", "C3", "C4", "C5", "C7", "C8", "C9"):
        assert label in out


def test_c10_studies_page_does_not_import_builder_labels():
    """QI-15 C10 / R17: page binds loader labels; stale builder must not brick it."""
    page = STUDIES_PAGE.read_text(encoding="utf-8")
    tree = ast.parse(page)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "thesistester.study.builder":
            imported = {alias.name for alias in node.names}
            assert "*" not in imported
            leaked = imported.intersection(C10_BANNED_BUILDER_NAMES)
            assert not leaked, leaked
        if isinstance(node, ast.ImportFrom) and node.module == "thesistester.study":
            assert all(alias.name != "builder" for alias in node.names)
    assert "from thesistester.data import loader as _data_loader" in page
    assert "Do not import FORMAT_PROFILE_LABELS" in page
