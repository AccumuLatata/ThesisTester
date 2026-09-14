"""B-10 / QI-12-07: import-linter contract file and C10 page-scoped gate.

B-19 / C9: sim_core AST gate resolves parent-package and relative imports
so those forms cannot false-green. C12 lives in ``tests/test_validation.py``.
"""

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

# QI-15 §5.4 payloads, C-24-extended. Values are (source_modules, forbidden_modules).
# C-24 moved join/desk/lens/catalog/progress off the façades; C2–C5 must name
# those siblings or a banned import in a helper would false-green the contract.
_C24_VIEWER_MODULES = (
    "thesistester.study.viewer",
    "thesistester.study.viewer_catalog",
    "thesistester.study.viewer_progress",
)
_C24_OBSERVATORY_MODULES = (
    "thesistester.study.observatory",
    "thesistester.study.observatory_support",
    "thesistester.study.observatory_join",
    "thesistester.study.observatory_desks",
    "thesistester.study.observatory_lens",
    "thesistester.study.observatory_query",
)
QI15_CONTRACTS = {
    "c1-preview-no-execute": (
        ("thesistester.study.preview",),
        ("thesistester.study.execute",),
    ),
    "c2-viewer-independence": (
        _C24_VIEWER_MODULES,
        (
            "thesistester.study.cli_study",
            "thesistester.cli",
            "thesistester.study.execute",
            "thesistester.study.rollup",
            *_C24_OBSERVATORY_MODULES,
            "plotly",
            "streamlit",
        ),
    ),
    "c3-observatory-independence": (
        _C24_OBSERVATORY_MODULES,
        (
            "thesistester.study.cli_study",
            "thesistester.study.execute",
            "streamlit",
            "plotly",
        ),
    ),
    "c4-launch-no-viewer-execute": (
        ("thesistester.study.launch",),
        (*_C24_VIEWER_MODULES, "thesistester.study.execute"),
    ),
    "c5-admit-followup-independence": (
        ("thesistester.study.admit_followup",),
        (
            "thesistester.study.execute",
            "thesistester.study.launch",
            *_C24_VIEWER_MODULES,
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

C9_SOURCE_MODULE = "thesistester.engine.sim_core"
C9_BANNED_PREFIXES = ("thesistester.entry_window_policy", "thesistester.analytics")
C9_CONTRACT_NAME = "C9 sim_core ↛ entry_window_policy / analytics (R22)"


def _load_importlinter() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    read = parser.read(IMPORTLINTER, encoding="utf-8")
    assert read == [str(IMPORTLINTER)]
    return parser


def _multiline(parser: configparser.ConfigParser, section: str, key: str) -> tuple[str, ...]:
    raw = parser.get(section, key, fallback="")
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def _resolve_from_module(module: str | None, level: int, source_module: str) -> str:
    """Resolve a relative ImportFrom module against ``source_module``."""
    if level <= 0:
        return module or ""
    parts = source_module.split(".")
    if level > len(parts):
        return module or ""
    base = parts[: len(parts) - level]
    if module:
        base.append(module)
    return ".".join(base)


def _imported_module_names(tree: ast.AST, source_module: str) -> tuple[str, ...]:
    """Absolute module names referenced by ``import`` / ``from … import``.

    Includes parent-package forms (``from thesistester import analytics``)
    and relatives (``from .. import entry_window_policy``). A walker that
    only checks ``node.module`` / ``alias.name`` against fully-qualified
    prefixes false-greens those (B-2 fail-closed class).
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from_module(node.module, node.level, source_module)
            if resolved:
                names.append(resolved)
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.append(f"{resolved}.{alias.name}" if resolved else alias.name)
    return tuple(names)


def _hits_ban(imported: str, banned: str) -> bool:
    """True when ``imported`` is ``banned`` or a submodule (``banned.*``)."""
    return imported == banned or imported.startswith(f"{banned}.")


def _hits_observatory_family(imported: str) -> bool:
    """C-24 siblings are ``observatory_join``, not ``observatory.join``."""
    return (
        imported == "thesistester.study.observatory"
        or imported.startswith("thesistester.study.observatory_")
        or imported.startswith("thesistester.study.observatory.")
    )


def _violates_c9(imported: str) -> bool:
    return any(_hits_ban(imported, banned) for banned in C9_BANNED_PREFIXES)


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


def test_c24_import_ban_catches_parent_and_submodule_forms():
    """C-24 AST bans must not false-green ``from pkg import execute`` / ``plotly.express``."""
    snippets = (
        ("from thesistester.study import execute", "thesistester.study.execute"),
        ("from thesistester.study.execute import run_study", "thesistester.study.execute"),
        ("import thesistester.study.execute", "thesistester.study.execute"),
        ("from plotly.express import px", "plotly"),
        ("import plotly.graph_objects", "plotly"),
        ("from thesistester.study import observatory_join", "observatory_family"),
        (
            "from thesistester.study.observatory_join import load_observatory_frame",
            "observatory_family",
        ),
    )
    for src, banned in snippets:
        imported = _imported_module_names(ast.parse(src), "thesistester.study.viewer")
        if banned == "observatory_family":
            assert any(_hits_observatory_family(name) for name in imported), src
        else:
            assert any(_hits_ban(name, banned) for name in imported), src


def test_c9_ast_gate_catches_parent_and_relative_imports():
    """C9 AST must not false-green parent-package or relative hops."""
    snippets = (
        "from thesistester import analytics",
        "from thesistester import entry_window_policy",
        "from .. import entry_window_policy",
        "from ..analytics import validation",
        "from ..entry_window_policy import normalize_entry_window",
        "import thesistester.analytics.validation",
        "from thesistester.analytics.validation import validation_summary",
    )
    for src in snippets:
        imported = _imported_module_names(ast.parse(src), C9_SOURCE_MODULE)
        assert any(_violates_c9(name) for name in imported), src


def test_c9_sim_core_does_not_import_admission_or_analytics():
    """QI-4 §6.3 / C9 (B-19): sim_core ↛ entry_window_policy / analytics.*."""
    source = (ROOT / "thesistester" / "engine" / "sim_core.py").read_text(encoding="utf-8")
    imported = _imported_module_names(ast.parse(source), C9_SOURCE_MODULE)
    leaked = [name for name in imported if _violates_c9(name)]
    assert leaked == []
    parser = _load_importlinter()
    section = "importlinter:contract:c9-sim-core-no-admission"
    sources, forbidden = QI15_CONTRACTS["c9-sim-core-no-admission"]
    assert _multiline(parser, section, "source_modules") == sources
    assert _multiline(parser, section, "forbidden_modules") == forbidden


def _contract_kept_or_broken(out: str, label: str) -> str | None:
    """Read KEPT/BROKEN even when lint-imports wraps a long contract name."""
    section = out.split("Broken contracts")[0]
    idx = section.find(label)
    if idx < 0:
        return None
    tail = section[idx:]
    kept = tail.find("KEPT")
    broken = tail.find("BROKEN")
    if kept < 0 and broken < 0:
        return None
    if broken >= 0 and (kept < 0 or broken < kept):
        return "BROKEN"
    return "KEPT"


def test_c2_c3_c24_siblings_stay_kept():
    """C-24: C2/C3 name the split helpers; contracts stay KEPT."""
    result = subprocess.run(
        ["lint-imports", "--config", str(IMPORTLINTER), "--no-cache", "--no-logo"],
        check=False,
        capture_output=True,
        text=True,
    )
    out = f"{result.stdout}\n{result.stderr}"
    assert "Contracts:" in out
    for label in (
        "C2 viewer family",
        "C3 observatory family",
        "C4 launch.py ↛ viewer family",
        "C5 admit_followup.py ↛ execute / launch / viewer family",
    ):
        assert _contract_kept_or_broken(out, label) == "KEPT", out


def test_c9_sim_core_contract_is_kept():
    """C9 is kept today (unlike C7). Warn-first CI still reports the status."""
    result = subprocess.run(
        ["lint-imports", "--config", str(IMPORTLINTER), "--no-cache", "--no-logo"],
        check=False,
        capture_output=True,
        text=True,
    )
    out = f"{result.stdout}\n{result.stderr}"
    assert "Contracts:" in out
    # CI awk '/BROKEN$/' — status is the last token on the contract line.
    c9_lines = [line for line in out.splitlines() if C9_CONTRACT_NAME in line]
    assert c9_lines, out
    assert any(line.endswith("KEPT") for line in c9_lines), c9_lines
    assert not any(line.endswith("BROKEN") for line in c9_lines), c9_lines


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
