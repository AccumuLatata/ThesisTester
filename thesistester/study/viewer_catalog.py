"""SV1 Study catalog discovery (C-24 / QI-07-07).

One-level scan of ``results/studies/`` and ``out/`` under trusted roots.
Does not call ``report_study`` or ``promote``. Does not import Streamlit,
Plotly, ``execute``, ``observatory``, or ``cli_study``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from thesistester.persistence.local_store import get_store_root
from thesistester.study.ledger import load_ledger
from thesistester.study.report import RESULTS_INDEX
from thesistester.study.viewer_progress import _ledger_status_counts

CATALOG_SCAN_PREFIXES: tuple[str, ...] = ("results/studies", "out")
# Shared contract value. Studies page binds its own copy so a stale or
# mid-init viewer cannot ImportError the page. Discover / CLI stay uncapped.
CATALOG_DISPLAY_CAP = 50
STUDY_SPEC_FILENAME = "study.spec.yaml"


class StudyViewerError(ValueError):
    """Raised when a study directory cannot be loaded for the viewer."""


def default_study_viewer_roots() -> tuple[Path, ...]:
    """Trusted local roots: repo cwd + ThesisTester store (assistant parity)."""
    return (Path.cwd().resolve(), get_store_root().resolve())


def _patched_default_roots() -> tuple[Path, ...]:
    """Honor ``viewer.default_study_viewer_roots`` monkeypatches (SV1 tests)."""
    try:
        from thesistester.study import viewer as _viewer
    except ImportError:  # pragma: no cover — viewer façade still importing
        return default_study_viewer_roots()
    lookup = getattr(_viewer, "default_study_viewer_roots", None)
    if callable(lookup):
        return lookup()
    return default_study_viewer_roots()


def _patched_read_catalog_parent(study_dir: Path) -> str:
    """Honor ``viewer._read_catalog_parent`` monkeypatches."""
    try:
        from thesistester.study import viewer as _viewer
    except ImportError:  # pragma: no cover — viewer façade still importing
        return _read_catalog_parent(study_dir)
    lookup = getattr(_viewer, "_read_catalog_parent", None)
    if callable(lookup):
        return lookup(study_dir)
    return _read_catalog_parent(study_dir)


def resolve_study_dir(
    raw: str | Path,
    *,
    roots: Sequence[Path] | None = None,
) -> Path:
    """Resolve ``raw`` and refuse paths outside ``roots`` when provided."""
    if isinstance(raw, str) and not raw.strip():
        raise StudyViewerError("Study output directory path is required.")
    candidate = Path(raw).expanduser().resolve()
    allowed = tuple(Path(root).resolve() for root in (roots if roots is not None else ()))
    if allowed and not any(candidate.is_relative_to(root) for root in allowed):
        raise StudyViewerError(
            "Study path is outside the trusted local roots "
            f"(cwd and store). Resolved path: {candidate}"
        )
    if not candidate.is_dir():
        raise StudyViewerError(f"Study directory does not exist: {candidate}")
    return candidate


@dataclass(frozen=True)
class StudyCatalogEntry:
    """One local study dir discovered under trusted scan prefixes."""

    study_dir: Path
    study_name: str
    study_identity_hash: str | None
    run_count: int | None
    ok: int
    failed: int
    skipped: int
    running: int
    pending: int
    ledger_present: bool
    index_present: bool
    mtime: float
    parent: str = "—"


def is_study_dir(path: Path) -> bool:
    """Recognition rule: directory containing ``study.spec.yaml``."""
    return path.is_dir() and (path / STUDY_SPEC_FILENAME).is_file()


def _under_trusted(path: Path, trusted: Sequence[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in trusted)


def resolve_catalog_roots(raw_roots: Sequence[Path | str] | None = None) -> tuple[Path, ...]:
    """Resolve ``--root`` values; refuse paths outside default trusted roots."""
    roots, extras = split_catalog_scan_paths(raw_roots)
    return roots + extras


def split_catalog_scan_paths(
    raw_roots: Sequence[Path | str] | None = None,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Map CLI ``--root`` PATHs into prefix-scan roots vs extra dirs (§4.9).

    ``--root`` replaces the default roots (no implicit cwd+store union).
    Trusted-root PATHs go to ``roots`` (prefix scan). Prefix dirs, study
    dirs, and other in-root dirs go to ``extra_dirs``.
    """
    trusted = _patched_default_roots()
    if not raw_roots:
        return trusted, ()
    roots: list[Path] = []
    extras: list[Path] = []
    for raw in raw_roots:
        candidate = Path(raw).expanduser().resolve()
        if not _under_trusted(candidate, trusted):
            raise StudyViewerError(
                "Study path is outside the trusted local roots "
                f"(cwd and store). Resolved path: {candidate}"
            )
        if not candidate.is_dir():
            raise StudyViewerError(f"Study path does not exist or is not a directory: {candidate}")
        if any(candidate == root for root in trusted):
            roots.append(candidate)
        else:
            extras.append(candidate)
    return tuple(roots), tuple(extras)


def catalog_load_path(raw: str | Path, *, roots: Sequence[Path] | None = None) -> str:
    """Resolve a catalog pick to the Inspect path string.

    Prefer a cwd-relative path when the study sits under the process cwd;
    otherwise return the resolved absolute path.
    """
    resolved = resolve_study_dir(raw, roots=roots)
    cwd = Path.cwd().resolve()
    try:
        return str(resolved.relative_to(cwd))
    except ValueError:
        return str(resolved)


def catalog_cache_stamp(
    roots: Sequence[Path],
    extra_dirs: Sequence[str | Path] = (),
) -> str:
    """Identity for the Inspect catalog cache (Refresh catalog rescans)."""
    root_part = "|".join(str(Path(root).resolve()) for root in roots)
    extra_part = "|".join(str(item).strip() for item in extra_dirs if str(item).strip())
    return f"{root_part}::{extra_part}"


def _safe_mtime(path: Path) -> float | None:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return None


def _catalog_mtime(study_dir: Path) -> float:
    times: list[float] = []
    for path in (
        study_dir,
        study_dir / "study.ledger.json",
        study_dir / RESULTS_INDEX,
        study_dir / "study.expansion.json",
        study_dir / STUDY_SPEC_FILENAME,
    ):
        if path != study_dir and not path.is_file():
            continue
        stamp = _safe_mtime(path)
        if stamp is not None:
            times.append(stamp)
    return max(times) if times else 0.0


def _iter_study_children(base: Path) -> tuple[Path, ...]:
    try:
        if not base.is_dir():
            return ()
        children = list(base.iterdir())
    except OSError:
        return ()
    hits: list[Path] = []
    for child in children:
        try:
            if is_study_dir(child):
                hits.append(child.resolve())
        except OSError:
            continue
    return tuple(hits)


def _fallback_catalog_entry(study_dir: Path) -> StudyCatalogEntry:
    """Name + path only when identity / ledger reads fail."""
    return StudyCatalogEntry(
        study_dir=study_dir,
        study_name=study_dir.name,
        study_identity_hash=None,
        run_count=None,
        ok=0,
        failed=0,
        skipped=0,
        running=0,
        pending=0,
        ledger_present=False,
        index_present=(study_dir / RESULTS_INDEX).is_file(),
        mtime=_catalog_mtime(study_dir),
        parent="—",
    )


def _catalog_entry_from_dir(study_dir: Path) -> StudyCatalogEntry:
    """Best-effort catalog row. Never calls ``report_study``. Never raises."""
    try:
        identity_hash, run_count, spec_name = _read_identity(study_dir)
        ledger_present = False
        counts: dict[str, int] = {}
        try:
            ledger = load_ledger(study_dir)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
            ledger = None
        if ledger is not None:
            ledger_present = True
            counts = _ledger_status_counts(ledger)
        # Parent label is best-effort and must not discard identity / ledger.
        try:
            parent = _patched_read_catalog_parent(study_dir)
        except Exception:  # noqa: BLE001 — corrupt lineage → "—", keep the row
            parent = "—"
        return StudyCatalogEntry(
            study_dir=study_dir,
            study_name=spec_name or study_dir.name,
            study_identity_hash=identity_hash,
            run_count=run_count,
            ok=int(counts.get("ok") or 0),
            failed=int(counts.get("failed") or 0),
            skipped=int(counts.get("skipped") or 0),
            running=int(counts.get("running") or 0),
            pending=int(counts.get("pending") or 0),
            ledger_present=ledger_present,
            index_present=(study_dir / RESULTS_INDEX).is_file(),
            mtime=_catalog_mtime(study_dir),
            parent=parent,
        )
    except Exception:  # noqa: BLE001 — one corrupt dir must not fail the catalog
        return _fallback_catalog_entry(study_dir)


def discover_study_dirs(
    roots: Sequence[Path] | None = None,
    *,
    extra_dirs: Sequence[str | Path] = (),
) -> tuple[StudyCatalogEntry, ...]:
    """List study dirs one level under ``results/studies/`` and ``out/``.

    Does not call ``report_study``, ``promote``, ``run_study``, or ``rollup_study``.
    Corrupt ledger / expansion / spec on one dir does not fail the catalog.
    ``roots is None`` uses default trusted roots. An empty ``roots`` tuple
    skips the prefix scan (CLI ``--root`` extras-only).
    """
    if roots is None:
        allowed = _patched_default_roots()
    else:
        allowed = tuple(Path(root).resolve() for root in roots)
    sandbox = allowed if allowed else _patched_default_roots()
    found: dict[Path, StudyCatalogEntry] = {}
    for root in allowed:
        for prefix in CATALOG_SCAN_PREFIXES:
            for resolved in _iter_study_children(root / prefix):
                if not any(resolved.is_relative_to(item) for item in sandbox):
                    continue
                found[resolved] = _catalog_entry_from_dir(resolved)
    for raw in extra_dirs:
        if raw is None or not str(raw).strip():
            continue
        try:
            extra = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if not extra.is_dir() or not _under_trusted(extra, sandbox):
            continue
        if is_study_dir(extra):
            found[extra] = _catalog_entry_from_dir(extra)
            continue
        for resolved in _iter_study_children(extra):
            if _under_trusted(resolved, sandbox):
                found[resolved] = _catalog_entry_from_dir(resolved)
    entries = list(found.values())
    entries.sort(key=lambda item: (-item.mtime, item.study_name.lower(), str(item.study_dir)))
    return tuple(entries)


def format_study_catalog_table(entries: Sequence[StudyCatalogEntry]) -> str:
    """Stable text table for ``study list`` (no JSON schema)."""
    if not entries:
        return "No study directories found under results/studies/ or out/."
    headers = ("study_name", "parent", "ok/failed/skipped/running/pending", "run_count", "path")
    rows: list[tuple[str, str, str, str, str]] = []
    for entry in entries:
        counts = f"{entry.ok}/{entry.failed}/{entry.skipped}/{entry.running}/{entry.pending}"
        run_count = "—" if entry.run_count is None else str(entry.run_count)
        parent = str(getattr(entry, "parent", None) or "—")
        rows.append((entry.study_name, parent, counts, run_count, str(entry.study_dir)))
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)


def _catalog_parent_label(raw: object, *, cwd: Path | None = None) -> str:
    """Basename or cwd-relative path from ``study.lineage.parent_output_dir``."""
    if not isinstance(raw, str) or not raw.strip():
        return "—"
    try:
        path = Path(raw.strip())
        name = path.name.strip()
        if name:
            return name
        base = Path(cwd) if cwd is not None else Path.cwd()
        resolved = path.expanduser()
        if not resolved.is_absolute():
            resolved = (base / resolved).resolve()
        else:
            resolved = resolved.resolve()
        rel = resolved.relative_to(base.resolve())
        text = rel.as_posix()
        return text if text and text != "." else (resolved.name or "—")
    except (OSError, TypeError, ValueError):
        return "—"


def _read_catalog_parent(study_dir: Path) -> str:
    """Best-effort lineage parent label. Corrupt / missing → ``—``."""
    spec_path = study_dir / STUDY_SPEC_FILENAME
    if not spec_path.is_file():
        return "—"
    try:
        import yaml
    except ImportError:
        return "—"
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        return "—"
    if not isinstance(spec, Mapping):
        return "—"
    study = spec.get("study")
    if not isinstance(study, Mapping):
        return "—"
    lineage = study.get("lineage")
    if not isinstance(lineage, Mapping):
        return "—"
    try:
        return _catalog_parent_label(lineage.get("parent_output_dir"))
    except Exception:  # noqa: BLE001 — catalog parent is best-effort only
        return "—"


def _read_identity(study_dir: Path) -> tuple[str | None, int | None, str | None]:
    """Return (study_identity_hash, run_count, study_name) best-effort."""
    identity_hash: str | None = None
    run_count: int | None = None
    study_name: str | None = None
    expansion_path = study_dir / "study.expansion.json"
    if expansion_path.is_file():
        try:
            payload = json.loads(expansion_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, Mapping):
            raw_hash = payload.get("study_identity_hash")
            if isinstance(raw_hash, str) and raw_hash.strip():
                identity_hash = raw_hash.strip()
            raw_count = payload.get("run_count")
            if isinstance(raw_count, int) and not isinstance(raw_count, bool):
                run_count = raw_count
            factor_map = payload.get("factor_map")
            if run_count is None and isinstance(factor_map, Mapping):
                run_count = len(factor_map)
    spec_path = study_dir / "study.spec.yaml"
    if spec_path.is_file():
        spec = None
        try:
            import yaml
        except ImportError:
            spec = None
        else:
            try:
                spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
                spec = None
        if isinstance(spec, Mapping):
            study = spec.get("study")
            if isinstance(study, Mapping):
                name = study.get("name")
                if isinstance(name, str) and name.strip():
                    study_name = name.strip()
    return identity_hash, run_count, study_name
