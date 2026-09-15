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
    SETUP_MUTATION_SIGNAL_KEYS,
    STICKY_APPLY_KEYS,
    THESIS_CLEAR_KEYS,
    WIDGET_KEYS,
    pop_setup_mutation_signal_keys,
    validate_apply_sticky,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs" / "ARCHITECTURE.md"
_SESSION_STATE_CONTRACT_HEADING = "## `st.session_state` contract (current)"
_RESEARCH_TABLE_HEADER = "| Key | Producing page(s) | Consuming page(s) | Schema (observed) |"
_VALIDATION_HELPER_PATHS = (
    "thesistester/validation_wfa_page_helpers.py",
    "thesistester/validation_batteries_page_helpers.py",
    "thesistester/validation_otf_page_helpers.py",
)
_QI1304_CONSUMER_NEEDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "data",
        (
            "Validation",
            "pages/10_Validation.py",
            "validation_*_page_helpers.py",
            "Portfolio",
            "pages/13_Portfolio.py",
            "parent bar-count",
        ),
    ),
    (
        "levels",
        ("Validation", "pages/10_Validation.py", "validation_*_page_helpers.py"),
    ),
    (
        "signals",
        ("Validation", "pages/10_Validation.py", "validation_*_page_helpers.py"),
    ),
    ("trades", ("Portfolio", "pages/13_Portfolio.py")),
)
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


_IDENTITY_STICKY_KEYS = (
    "data",
    "dataset_id",
    "instrument",
    "base_interval",
    "source_timezone",
    "exchange_timezone",
    "data_identity",
    "levels_identity",
)
_REGISTRY_SOURCE_NAMES = (
    "_DATASET_CLEAR_SOURCE",
    "_APPLY_CLEAR_SOURCE",
    "_THESIS_CLEAR_SOURCE",
    "_WIDGET_SOURCE",
    "_STICKY_APPLY_SOURCE",
)


def _source_tuple_literals(name: str) -> tuple[str, ...]:
    """String Constants on a module-level annotated source tuple (comments fail-closed)."""
    tree = ast.parse((REPO_ROOT / "thesistester" / "research_keys.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != name:
            continue
        if not isinstance(node.value, ast.Tuple):
            raise AssertionError(f"{name} must be a tuple of string literals")
        return tuple(
            elt.value
            for elt in node.value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        )
    raise AssertionError(f"missing {name} literals")


def test_research_key_registry_completeness():
    """Every managed key is dataset-clear or explicitly sticky (QI-10-03)."""
    assert RESEARCH_KEY_REGISTRY
    sticky_literals = set(_source_tuple_literals("_STICKY_APPLY_SOURCE"))
    for spec in RESEARCH_KEY_REGISTRY:
        if spec.apply_clear:
            assert spec.dataset_clear or spec.sticky, spec.key
            if spec.sticky:
                assert spec.key in sticky_literals, spec.key
        if spec.sticky:
            assert spec.apply_clear and not spec.dataset_clear, spec.key
            assert spec.key in sticky_literals, spec.key
        if spec.thesis_clear:
            assert spec.key.startswith("assistant_"), spec.key

    assert frozenset(APPLY_CLEAR_KEYS) == frozenset(_MANAGED_RESEARCH_KEYS)
    assert len(APPLY_CLEAR_KEYS) == 105
    assert set(THESIS_CLEAR_KEYS) == set(THESIS_SCOPED_STAGING_KEYS)
    assert set(STICKY_APPLY_KEYS) == set(APPLY_CLEAR_KEYS) - set(DATASET_CLEAR_KEYS)
    assert set(STICKY_APPLY_KEYS) == sticky_literals

    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.dataset_clear
        assert key in DATASET_CLEAR_KEYS
        assert key not in sticky_literals
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.apply_clear and spec.sticky and not spec.dataset_clear
        assert key not in DATASET_CLEAR_KEYS
        assert key in sticky_literals
    for key in _IDENTITY_STICKY_KEYS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.apply_clear and spec.sticky and not spec.dataset_clear, key
        assert key in sticky_literals


def test_registry_source_tuples_are_unique_literals():
    """Source tuples cannot silently collapse duplicates."""
    for name in _REGISTRY_SOURCE_NAMES:
        literals = _source_tuple_literals(name)
        assert literals, f"missing {name} literals"
        dups = [key for key in literals if literals.count(key) > 1]
        assert dups == [], f"{name} has duplicate literals {dups}"


def test_setup_mutation_signal_keys_are_known_or_page_local():
    """D-2 pop cluster is registry keys plus page-6 identity fields."""
    page_local = {
        "signal_artifact_identity_status",
        "signal_artifact_identity_error",
    }
    assert SETUP_MUTATION_SIGNAL_KEYS[0] == "signals"
    extras = [key for key in SETUP_MUTATION_SIGNAL_KEYS if key not in RESEARCH_KEY_BY_NAME]
    assert set(extras) == page_local
    session = {"signals": object(), "trades": object(), "setup_config": {"name": "keep"}}
    for key in SETUP_MUTATION_SIGNAL_KEYS:
        session[key] = object()
    pop_setup_mutation_signal_keys(session)
    assert "signals" not in session
    assert session["setup_config"]["name"] == "keep"
    assert "trades" in session


def test_apply_clear_source_literals_bind_a7_residuals():
    """Comment needles in research_keys.py must not bind A-7 apply-clear keys."""
    apply_literals = set(_source_tuple_literals("_APPLY_CLEAR_SOURCE"))
    sticky_literals = set(_source_tuple_literals("_STICKY_APPLY_SOURCE"))
    missing_apply = [key for key in _QI1001_A7_APPLY_ONLY_KEYS if key not in apply_literals]
    missing_sticky = [key for key in _QI1001_A7_APPLY_ONLY_KEYS if key not in sticky_literals]
    assert missing_apply == [], missing_apply
    assert missing_sticky == [], missing_sticky


def test_unlabeled_apply_clear_key_fails_closed():
    """Derived sticky (apply minus dataset) must not satisfy the completeness gate."""
    apply_set = set(APPLY_CLEAR_KEYS) | {"unlabeled_apply_key"}
    dataset_set = set(DATASET_CLEAR_KEYS)
    sticky_set = set(STICKY_APPLY_KEYS)
    try:
        validate_apply_sticky(apply_set, dataset_set, sticky_set)
    except ValueError as exc:
        assert "explicitly sticky" in str(exc)
        assert "unlabeled_apply_key" in str(exc)
    else:
        raise AssertionError("unlabeled apply-clear key must not pass as implied sticky")

    try:
        validate_apply_sticky(set(APPLY_CLEAR_KEYS), dataset_set, sticky_set | {"levels"})
    except ValueError as exc:
        assert "dataset-clear" in str(exc)
    else:
        raise AssertionError("sticky ∩ dataset-clear must fail closed")


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


def _architecture_text(text: str | None = None) -> str:
    return ARCHITECTURE.read_text(encoding="utf-8") if text is None else text


def _architecture_research_table(
    text: str | None = None,
) -> tuple[set[str], dict[str, str]]:
    source = _architecture_text(text)
    start = source.index(_RESEARCH_TABLE_HEADER)
    chunk = source[start:]
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


def _session_key_table_preamble(text: str | None = None) -> str:
    """Contract prose immediately before the research table (not the CAI-5 H2)."""
    source = _architecture_text(text)
    contract = source.index(_SESSION_STATE_CONTRACT_HEADING)
    table = source.index(_RESEARCH_TABLE_HEADER, contract)
    return source[contract:table]


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
    """D-1 / QI-10-03: table ⊇ measured research keys. F-5 names consumers."""
    table_keys, consumers = _architecture_research_table()
    assert table_keys

    paths = [
        REPO_ROOT / "app.py",
        REPO_ROOT / "thesistester" / "classic_nav.py",
        REPO_ROOT / "thesistester" / "timezone_display.py",
        *sorted((REPO_ROOT / "pages").glob("*.py")),
        REPO_ROOT / "thesistester" / "validation_wfa_page_helpers.py",
        REPO_ROOT / "thesistester" / "validation_batteries_page_helpers.py",
        REPO_ROOT / "thesistester" / "validation_otf_page_helpers.py",
        REPO_ROOT / "thesistester" / "validation_display_page_helpers.py",
        REPO_ROOT / "thesistester" / "validation_sidebar_page_helpers.py",
        REPO_ROOT / "thesistester" / "data_workspace_page_helpers.py",
        REPO_ROOT / "thesistester" / "data_tick_page_helpers.py",
        REPO_ROOT / "thesistester" / "data_subtimeframe_page_helpers.py",
        REPO_ROOT / "thesistester" / "data_display_page_helpers.py",
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

    public_dataset_clear = {
        key for key in DATASET_CLEAR_KEYS if not key.startswith("_") and key not in WIDGET_KEYS
    }
    missing_dataset = sorted(public_dataset_clear - table_keys)
    assert missing_dataset == [], (
        f"ARCHITECTURE session-key table missing dataset-clear keys {missing_dataset}"
    )

    _assert_qi1304_named_consumers(by_file, consumers)
    _assert_qi1304_cai5_pointer()
    _assert_qi1304_chrome_out_of_table(table_keys)
    _assert_qi1304_widgets_out_of_research(research)


def test_qi1304_session_key_table_names_validation_and_portfolio_consumers():
    """F-5 / QI-13-04 (+ QI-10-02): Validation + Portfolio consumers; CAI-5 chrome."""
    table_keys, consumers = _architecture_research_table()
    paths = {
        "pages/13_Portfolio.py": REPO_ROOT / "pages" / "13_Portfolio.py",
        **{rel: REPO_ROOT / rel for rel in _VALIDATION_HELPER_PATHS},
    }
    by_file = {rel: _measured_session_keys(path) for rel, path in paths.items()}
    _assert_qi1304_named_consumers(by_file, consumers)
    _assert_qi1304_cai5_pointer()
    _assert_qi1304_chrome_out_of_table(table_keys)


def _assert_qi1304_named_consumers(
    by_file: dict[str, set[str]],
    consumers: dict[str, str],
) -> None:
    for key in ("data", "levels", "signals"):
        helpers = [path for path in _VALIDATION_HELPER_PATHS if key in by_file.get(path, set())]
        assert helpers, f"a Validation helper must read {key}"
    assert "trades" in by_file["pages/13_Portfolio.py"], "Portfolio must read trades"
    assert "data" in by_file["pages/13_Portfolio.py"], "Portfolio must read data"

    for key, needles in _QI1304_CONSUMER_NEEDLES:
        cell = consumers[key]
        missing = [needle for needle in needles if needle not in cell]
        assert missing == [], f"{key} consumers missing {missing}: {cell}"


def _assert_qi1304_cai5_pointer(text: str | None = None) -> None:
    """Bind classic_* / CAI-5 / QI-13-04 to the table preamble, not the CAI-5 H2."""
    source = _architecture_text(text)
    preamble = _session_key_table_preamble(source)
    for needle in (
        "`classic_*`",
        "## Classic thesis research context (CAI-5)",
        "QI-13-04",
    ):
        assert needle in preamble, f"session-key table preamble missing {needle!r}"
    heading_at = source.index("## Classic thesis research context (CAI-5)")
    contract_at = source.index(_SESSION_STATE_CONTRACT_HEADING)
    assert heading_at < contract_at, "CAI-5 heading must stay above the research table"


def _assert_qi1304_chrome_out_of_table(table_keys: set[str]) -> None:
    leaked = sorted(key for key in table_keys if key.startswith("classic_"))
    assert leaked == [], f"classic_* chrome leaked into the research table: {leaked}"


def _assert_qi1304_widgets_out_of_research(research: set[str]) -> None:
    """WIDGET_KEYS stay out of table ⊇ research via registry membership, not heuristics."""
    nonce_widgets = tuple(key for key in WIDGET_KEYS if key.startswith("_"))
    assert nonce_widgets, "WIDGET_KEYS must include nonce/textarea keys"
    unflagged = [key for key in nonce_widgets if not _is_widgetish(key)]
    assert unflagged == [], (
        f"_is_widgetish must treat registry nonce widgets as widgets: {unflagged}"
    )
    leaked = sorted(set(WIDGET_KEYS) & research)
    assert leaked == [], f"widget keys leaked into the research contract: {leaked}"


def test_qi1304_wrapped_cai5_heading_cite_does_not_bind_pointer():
    """A line-wrapped heading cite in the preamble must not satisfy the pointer."""
    fake = (
        "## Classic thesis research context (CAI-5)\n\n"
        f"{_SESSION_STATE_CONTRACT_HEADING}\n\n"
        "Classic chrome (`classic_*`) lives in the **CAI-5** table above (`## Classic\n"
        "thesis research context (CAI-5)`), not this research table — F-5 / QI-13-04.\n\n"
        f"{_RESEARCH_TABLE_HEADER}\n"
        "|---|---|---|---|\n"
        "| `data` | Data | Levels |\n"
    )
    try:
        _assert_qi1304_cai5_pointer(fake)
    except AssertionError:
        return
    raise AssertionError("wrapped CAI-5 heading cite must not bind the pointer")


def test_qi1304_file_level_cai5_heading_does_not_bind_pointer():
    """Whole-file CAI-5 heading / later QI-13-04 must not satisfy the F-5 pointer."""
    fake = (
        "## Classic thesis research context (CAI-5)\n\n"
        "| Key | Role |\n| `classic_active_run_id` | chrome |\n\n"
        f"{_SESSION_STATE_CONTRACT_HEADING}\n\n"
        "Uploader nonce ≠ leftover research keys.\n\n"
        f"{_RESEARCH_TABLE_HEADER}\n"
        "|---|---|---|---|\n"
        "| `data` | Data | Levels |\n"
        "\n## Local persistence topology\n\n"
        "Later mention: F-5 / QI-13-04 `classic_*` CAI-5.\n"
    )
    try:
        _assert_qi1304_cai5_pointer(fake)
    except AssertionError:
        return
    raise AssertionError("CAI-5 heading / later-section needles must not bind the pointer")


def test_qi1304_later_validation_mention_does_not_name_consumers():
    """A later Validation/Portfolio sentence must not populate consumer cells."""
    fake = (
        f"{_RESEARCH_TABLE_HEADER}\n"
        "|---|---|---|---|\n"
        "| `data` | Data | Levels (`pages/2_Levels.py`) |\n"
        "| `levels` | Levels | Setup (`pages/3_Setup_Builder.py`) |\n"
        "| `signals` | Signals | Backtest (`pages/7_Backtest.py`) |\n"
        "| `trades` | Backtest | Time (`pages/9_Time_Analysis.py`) |\n"
        "\n## Local persistence topology\n\n"
        "Validation (`pages/10_Validation.py` via `validation_*_page_helpers.py`) "
        "and Portfolio (`pages/13_Portfolio.py`, parent bar-count) consume data.\n"
    )
    _table_keys, consumers = _architecture_research_table(fake)
    try:
        _assert_qi1304_named_consumers(
            {
                "pages/13_Portfolio.py": {"trades", "data"},
                **{path: {"data", "levels", "signals"} for path in _VALIDATION_HELPER_PATHS},
            },
            consumers,
        )
    except AssertionError:
        return
    raise AssertionError("later-section Validation/Portfolio needles must not name consumers")


def test_qi1304_nonce_widgets_require_registry_membership():
    """Nonce widgets are WIDGET_KEYS-only; suffix/prefix heuristics must not hide a drop."""
    nonce = "_primary_csv_uploader_nonce"
    assert nonce in WIDGET_KEYS
    assert _is_widgetish(nonce)
    assert not nonce.endswith(("_selector", "_input"))
    assert not nonce.startswith(("backtest_", "grid_"))


def test_qi1304_widget_keys_in_research_set_fail_closed():
    """A nonce widget inside the measured-research set must fail closed."""
    try:
        _assert_qi1304_widgets_out_of_research({"data", "_primary_csv_uploader_nonce"})
    except AssertionError:
        return
    raise AssertionError("nonce widget in research must fail closed")


def test_qi1304_classic_key_in_research_table_fail_closed():
    """classic_* rows in the research table must fail closed."""
    try:
        _assert_qi1304_chrome_out_of_table({"data", "classic_active_run_id"})
    except AssertionError:
        return
    raise AssertionError("classic_* table key must fail closed")


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
