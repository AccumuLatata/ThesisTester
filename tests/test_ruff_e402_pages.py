"""B-14 / QI-10-08: E402 ignore is Data-only; only Data bootstraps sys.path.

QI-10 §2.2: blanket ``pages/*.py`` hid real import-order lint on pages that
do not insert ``REPO_ROOT``. Restoring that glob, or adding a second
bootstrap, is a regression.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
DATA_PAGE = PAGES / "1_Data.py"
E402_IGNORE_KEY = "pages/1_Data.py"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _page_files() -> list[Path]:
    return sorted(PAGES.glob("*.py"))


def _is_import(node: ast.AST) -> bool:
    return isinstance(node, (ast.Import, ast.ImportFrom))


def _is_future_import(node: ast.AST) -> bool:
    return isinstance(node, ast.ImportFrom) and node.module == "__future__"


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(getattr(node, "value", None), ast.Constant)
        and isinstance(node.value.value, str)
    )


def _late_import_lines(tree: ast.Module) -> list[int]:
    """Module-level import line numbers after a non-import statement (E402)."""
    seen_code = False
    seen_docstring = False
    late: list[int] = []
    for node in tree.body:
        if _is_future_import(node):
            continue
        if not seen_docstring and _is_docstring(node):
            seen_docstring = True
            continue
        if _is_import(node):
            if seen_code:
                late.append(node.lineno)
            continue
        seen_code = True
    return late


def _module_level_sys_path_lines(tree: ast.Module) -> list[int]:
    """Lines of module-level ``sys.path`` reads/writes (not inside defs)."""
    hits: list[int] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Attribute)
                and child.attr == "path"
                and isinstance(child.value, ast.Name)
                and child.value.id == "sys"
            ):
                hits.append(node.lineno)
                break
    return hits


def test_e402_per_file_ignore_is_data_page_only() -> None:
    ignores = _pyproject()["tool"]["ruff"]["lint"]["per-file-ignores"]
    e402_keys = [key for key, codes in ignores.items() if "E402" in codes]
    assert e402_keys == [E402_IGNORE_KEY]
    assert "pages/*.py" not in ignores
    assert ignores[E402_IGNORE_KEY] == ["E402"]


def test_only_data_page_bootstraps_sys_path_before_imports() -> None:
    pages = _page_files()
    assert DATA_PAGE in pages
    assert len(pages) >= 15

    bootstrapped: list[str] = []
    late_by_page: dict[str, list[int]] = {}
    for path in pages:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        path_lines = _module_level_sys_path_lines(tree)
        late = _late_import_lines(tree)
        if path_lines:
            bootstrapped.append(rel)
        if late:
            late_by_page[rel] = late

    assert bootstrapped == [E402_IGNORE_KEY]
    assert set(late_by_page) == {E402_IGNORE_KEY}
    # QI-10 §2.2 / PR probe: the remaining ignore covers Data's post-bootstrap
    # thesistester imports, not a blanket pages glob. C-2 adds one statement
    # (`from thesistester.data import loader as _data_loader`) for the R17
    # type-checked getattr bind.
    assert len(late_by_page[E402_IGNORE_KEY]) == 15

    data_src = DATA_PAGE.read_text(encoding="utf-8")
    assert "REPO_ROOT = Path(__file__).resolve().parents[1]" in data_src
    assert "sys.path.insert(0, str(REPO_ROOT))" in data_src
