"""QR D-1 / QI-10-03: research-key registry completeness and session-key contract."""

from __future__ import annotations

import ast
import pathlib
import re
import sys

import pandas as pd

from tests.test_data_page_helpers import (
    _QI1001_A7_APPLY_ONLY_KEYS,
    _QI1001_DATASET_CLEAR_LEFTOVERS,
    _import_data_page_module,
    _qi1001_leftover_session,
)
from thesistester.assistant.workspace import (
    THESIS_SCOPED_STAGING_KEYS,
    clear_thesis_scoped_state,
    init_assistant_session_state,
)
from thesistester.research_bundle import (
    _MANAGED_RESEARCH_KEYS,
    apply_research_bundle_to_session,
    build_research_bundle,
    load_research_bundle,
)
from thesistester.research_keys import (
    APPLY_CLEAR_KEYS,
    DATASET_CLEAR_KEYS,
    RESEARCH_KEY_BY_NAME,
    RESEARCH_KEY_REGISTRY,
    STICKY_APPLY_KEYS,
    THESIS_CLEAR_KEYS,
    WIDGET_KEYS,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs" / "ARCHITECTURE.md"
_SESSION_ATTRS = frozenset({"get", "pop", "setdefault"})
_CHROME_PREFIXES = (
    "assistant_",
    "studies_",
    "journal_",
    "observatory_",
    "classic_",
    "assistant-",
    "ra-",
    "voice-",
)


def test_research_key_registry_completeness():
    """Every managed key is dataset-clear or explicitly sticky (QI-10-03)."""
    assert RESEARCH_KEY_REGISTRY
    for spec in RESEARCH_KEY_REGISTRY:
        if spec.apply_clear:
            assert spec.dataset_clear or spec.sticky, spec.key
        if spec.sticky:
            assert spec.apply_clear and not spec.dataset_clear, spec.key
        if spec.thesis_clear:
            assert spec.key.startswith("assistant_"), spec.key

    assert frozenset(APPLY_CLEAR_KEYS) == frozenset(_MANAGED_RESEARCH_KEYS)
    assert len(APPLY_CLEAR_KEYS) == 105
    assert set(THESIS_CLEAR_KEYS) == set(THESIS_SCOPED_STAGING_KEYS)
    assert set(STICKY_APPLY_KEYS) == set(APPLY_CLEAR_KEYS) - set(DATASET_CLEAR_KEYS)

    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.dataset_clear
        assert key in DATASET_CLEAR_KEYS
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.apply_clear and spec.sticky and not spec.dataset_clear
        assert key not in DATASET_CLEAR_KEYS


def test_apply_clear_source_literals_bind_a7_residuals():
    """Comment needles in research_keys.py must not bind A-7 apply-clear keys."""
    tree = ast.parse((REPO_ROOT / "thesistester" / "research_keys.py").read_text(encoding="utf-8"))
    literals: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "_APPLY_CLEAR_SOURCE":
            continue
        assert isinstance(node.value, ast.Tuple)
        literals = {
            elt.value
            for elt in node.value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        break
    assert literals, "missing _APPLY_CLEAR_SOURCE literals"
    missing = [key for key in _QI1001_A7_APPLY_ONLY_KEYS if key not in literals]
    assert missing == [], missing


def _is_session_state(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "session_state") or (
        isinstance(node, ast.Name) and node.id == "session_state"
    )


class _SessionKeyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.keys: set[str] = set()

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (
            _is_session_state(node.value)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            self.keys.add(node.slice.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _SESSION_ATTRS
            and _is_session_state(func.value)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self.keys.add(node.args[0].value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if (
            node.comparators
            and isinstance(node.ops[0], ast.In)
            and _is_session_state(node.comparators[0])
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
        ):
            self.keys.add(node.left.value)
        self.generic_visit(node)


def _measured_session_keys(path: pathlib.Path) -> set[str]:
    visitor = _SessionKeyVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return visitor.keys


def _architecture_research_table() -> tuple[set[str], dict[str, str]]:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    marker = "| Key | Producing page(s) | Consuming page(s) | Schema (observed) |"
    start = text.index(marker)
    chunk = text[start:]
    heading = re.search(r"\n## ", chunk)
    if heading:
        chunk = chunk[: heading.start()]
    keys: set[str] = set()
    consumers: dict[str, str] = {}
    for line in chunk.splitlines():
        if not line.startswith("| `"):
            continue
        cols = [col.strip() for col in line.strip("|").split("|")]
        if len(cols) < 3:
            continue
        found = re.findall(r"`([^`]+)`", cols[0])
        for key in found:
            keys.add(key)
            consumers[key] = cols[2]
    return keys, consumers


def _is_chrome_key(key: str) -> bool:
    return key.startswith(_CHROME_PREFIXES)


def _is_widgetish(key: str) -> bool:
    if key in WIDGET_KEYS:
        return True
    if key.endswith(("_selector", "_input")):
        return True
    managed = set(APPLY_CLEAR_KEYS) | set(DATASET_CLEAR_KEYS)
    if key.startswith("backtest_") and key not in managed:
        return True
    if key.startswith("grid_") and key not in managed:
        return True
    return key in {"stop_loss_ticks", "take_profit_ticks"}


def test_architecture_session_key_table_covers_measured_research_keys():
    """F-5 / QI-10-03: table ⊇ measured research keys and named consumers."""
    table_keys, consumers = _architecture_research_table()
    assert table_keys

    paths = [
        REPO_ROOT / "app.py",
        REPO_ROOT / "thesistester" / "classic_nav.py",
        REPO_ROOT / "thesistester" / "timezone_display.py",
        *sorted((REPO_ROOT / "pages").glob("*.py")),
    ]
    measured: set[str] = set()
    by_file: dict[str, set[str]] = {}
    for path in paths:
        keys = _measured_session_keys(path)
        by_file[str(path.relative_to(REPO_ROOT))] = keys
        measured |= keys

    research = {
        key
        for key in measured
        if not key.startswith("_") and not _is_chrome_key(key) and not _is_widgetish(key)
    }
    missing = sorted(research - table_keys)
    assert missing == [], f"ARCHITECTURE session-key table missing measured keys {missing}"

    for key, label, path in (
        ("data", "Validation", "pages/10_Validation.py"),
        ("levels", "Validation", "pages/10_Validation.py"),
        ("signals", "Validation", "pages/10_Validation.py"),
        ("trades", "Portfolio", "pages/13_Portfolio.py"),
    ):
        assert key in by_file[path], f"{path} must read {key}"
        assert label in consumers[key], f"{key} consumers must name {label}"

    arch = ARCHITECTURE.read_text(encoding="utf-8")
    assert "CAI-5" in arch
    assert "classic_*" in arch or "`classic_" in arch
    assert not (set(WIDGET_KEYS) & research)


def test_qi10_stale_state_matrix_d1_rows(monkeypatch):
    """QI-10 §3.2 D-1-owned rows: dataset switch, exec-clear, apply, thesis."""
    kept = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    leftovers = _qi1001_leftover_session(data=kept, dataset_id="keep-id")
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        leftovers[key] = {"leftover": True}
    leftovers["levels"] = pd.DataFrame({"timestamp": [1]})
    leftovers["signals"] = pd.DataFrame({"signal_id": [1]})
    leftovers["trades"] = pd.DataFrame({"trade_id": [99]})

    session = dict(leftovers)
    data_page = _import_data_page_module(session)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])
    data_page._clear_dataset_dependent_state()
    assert session["data"] is kept
    assert session["dataset_id"] == "keep-id"
    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        assert key not in session, f"dataset-switch leftover {key}"
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        assert key in session, f"A-7 residual {key} must stay apply-clear only"

    session = dict(leftovers)
    data_page = _import_data_page_module(session)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])
    data_page._clear_execution_dependent_state()
    assert "trades" not in session
    assert "validation_summary" not in session
    assert session["levels"] is leftovers["levels"]
    assert session["signals"] is leftovers["signals"]
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        assert key in session

    session = dict(leftovers)
    session["display_timezone"] = "UTC"
    bundle_state = {
        "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
        "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
        "trade_summary": {"trade_count": 1},
        "exchange_timezone": "Europe/Berlin",
    }
    apply_research_bundle_to_session(
        load_research_bundle(build_research_bundle(bundle_state)), session
    )
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        assert key not in session, f"apply leftover {key}"
    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        if key == "display_timezone":
            continue
        if key in APPLY_CLEAR_KEYS:
            assert key not in session, f"apply leftover {key}"
    # Trades-only zip still resets leftover UTC (A-8). Dataset-bearing
    # restore-to-exchange_timezone is covered in test_research_bundle.
    assert session.get("display_timezone") != "UTC"

    session = {}
    init_assistant_session_state(session)
    session["data"] = kept
    session["levels"] = leftovers["levels"]
    session["trades"] = leftovers["trades"]
    session["assistant_draft_prompt"] = "stale draft"
    session["assistant_bundle_handoff"] = {"path": "stale"}
    session["assistant_flash"] = {"level": "info", "message": "stale"}
    clear_thesis_scoped_state(session)
    assert session["assistant_draft_prompt"] == ""
    assert session["assistant_bundle_handoff"] is None
    assert session["assistant_flash"] is None
    assert session["data"] is kept
    assert session["levels"] is leftovers["levels"]
    assert session["trades"] is leftovers["trades"]
    assert set(THESIS_SCOPED_STAGING_KEYS) == set(THESIS_CLEAR_KEYS)
