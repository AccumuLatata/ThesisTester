"""Data-page tick-last attach helpers (QR D-5 / QI-01-01).

Streamlit-free: renderers take ``st``. Trusted-root / persist math unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from thesistester.data.quantower_ticks import TickIngestError, iter_tick_files
from thesistester.data.loader import DataValidationError
from thesistester.persistence import get_store_root

from thesistester.data_page_constants import (
    TICK_PATHS_KEY,
    TICK_PATHS_TEXT_KEY,
    TICK_ROW_COUNT_KEY,
    TICK_SESSION_COUNT_KEY,
    TICK_UPLOAD_SIGNATURE_KEY,
    TICK_UPLOADER_NONCE_KEY,
    TICK_WARNINGS_KEY,
)


def _normalize_tick_path_list(raw) -> list[str]:
    """Coerce widget / leftover extra tick paths to a de-duplicated string list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        tokens: list[str] = []
        for line in raw.replace(",", "\n").splitlines():
            token = line.strip()
            if token:
                tokens.append(token)
        return list(dict.fromkeys(tokens))
    if isinstance(raw, (list, tuple)):
        tokens = []
        for item in raw:
            token = str(item).strip()
            if token:
                tokens.append(token)
        return list(dict.fromkeys(tokens))
    token = str(raw).strip()
    return [token] if token else []


def _tick_upload_dir() -> Path:
    dest = get_store_root() / "tick_uploads"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _sha256_file(path: Path) -> str:
    """Hash file bytes in 1 MiB blocks. Do not load the whole file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _tick_trusted_roots() -> tuple[Path, ...]:
    """Same trusted roots as Studies launch (cwd + local store)."""
    return (Path.cwd().resolve(), get_store_root().resolve())


def _is_within_tick_trusted_roots(path: Path) -> bool:
    """True when ``path`` sits under cwd or the local store after resolve."""
    resolved = path.expanduser().resolve()
    return any(resolved.is_relative_to(root) for root in _tick_trusted_roots())


def _classify_typed_tick_path(raw: str) -> tuple[str, Path | None]:
    """Classify a typed tick path as ``ok``, ``missing``, or ``outside``.

    Search order matches launch: cwd file first, then store-relative. Files
    that exist but sit outside cwd/store are ``outside`` so attach cannot
    cite a path Studies launch will refuse.
    """
    token = str(raw).strip()
    if not token:
        return "missing", None
    path = Path(token).expanduser()
    if path.is_file():
        resolved = path.resolve()
        if _is_within_tick_trusted_roots(resolved):
            return "ok", resolved
        return "outside", None
    if path.is_absolute():
        return "missing", None
    store_candidate = (get_store_root() / path).resolve()
    if store_candidate.is_file():
        if _is_within_tick_trusted_roots(store_candidate):
            return "ok", store_candidate
        return "outside", None
    return "missing", None


def _resolve_existing_tick_path(raw: str) -> Path | None:
    """Resolve a typed tick path against cwd first, then the local store root.

    Launch pin searches viewer roots the same way; Data-page attach must not
    refuse a store-relative path that Studies would later find. Absolute or
    ``..`` paths outside cwd/store are rejected so attach cannot cite a file
    launch will refuse.
    """
    status, found = _classify_typed_tick_path(raw)
    return found if status == "ok" else None


def _dedupe_attached_tick_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Drop duplicate resolved paths and exact-duplicate file content.

    Upload + typed path of the same bytes would otherwise fail TV1
    ``_reject_duplicate_files``. Keep the first path; warn on content dupes.
    """
    unique: list[str] = []
    seen_resolved: set[Path] = set()
    seen_hash: dict[str, str] = {}
    warnings: list[str] = []
    for raw in paths:
        full = Path(raw).expanduser().resolve()
        if full in seen_resolved:
            continue
        digest = _sha256_file(full)
        prior = seen_hash.get(digest)
        if prior is not None:
            warnings.append(f"Ignored exact-duplicate tick file {full} (same bytes as {prior}).")
            continue
        seen_resolved.add(full)
        seen_hash[digest] = str(full)
        unique.append(str(full))
    return unique, warnings


def _persist_tick_uploads(files, dest_dir: Path) -> list[str]:
    """Write Streamlit uploads to disk so Studies Build can cite durable paths.

    Dest names are ``{sha256[:12]}_{basename}`` so two uploads that share a
    basename do not overwrite each other.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for uploaded in files or []:
        payload = uploaded.getvalue()
        name = Path(str(getattr(uploaded, "name", "ticks.csv") or "ticks.csv")).name
        if not name or name in {".", ".."}:
            name = "ticks.csv"
        digest = hashlib.sha256(payload).hexdigest()[:12]
        dest = dest_dir / f"{digest}_{name}"
        dest.write_bytes(payload)
        paths.append(str(dest.resolve()))
    return list(dict.fromkeys(paths))


def _validate_attached_tick_paths(
    paths: list[str],
    *,
    instrument: str,
    source_tz: str = "UTC",
) -> tuple[int, int, list[str]]:
    """Parse attached Tick–Tick–Last files via the TV1 session iterator.

    Does not call ``load_ohlcv`` and does not concatenate sessions into one
    frame. Returns ``(session_count, row_count, warnings)``.
    """
    sessions = 0
    rows = 0
    warnings: list[str] = []
    for chunk in iter_tick_files(paths, instrument=instrument, source_tz=source_tz):
        sessions += 1
        rows += len(chunk.ticks)
        if chunk.filename_window_mismatch:
            warnings.append(
                "Filename window does not cover row timestamps: " + ", ".join(chunk.source_paths)
            )
        warnings.extend(chunk.warnings)
    return sessions, rows, list(dict.fromkeys(warnings))


def _install_tick_paths(
    session_state,
    paths: list[str],
    *,
    row_count: int | None = None,
    session_count: int | None = None,
    signature: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    """Record validated tick paths. Does not mutate primary ``data``."""
    session_state[TICK_PATHS_KEY] = list(paths)
    if row_count is not None:
        session_state[TICK_ROW_COUNT_KEY] = int(row_count)
    if session_count is not None:
        session_state[TICK_SESSION_COUNT_KEY] = int(session_count)
    if signature is not None:
        session_state[TICK_UPLOAD_SIGNATURE_KEY] = signature
    if warnings is not None:
        session_state[TICK_WARNINGS_KEY] = list(warnings)
    else:
        session_state.pop(TICK_WARNINGS_KEY, None)


def _clear_tick_session_state(st, session_state=None) -> None:
    """Drop installed tick attach keys. Does not mutate widget-bound text."""
    state = st.session_state if session_state is None else session_state
    for key in (
        TICK_PATHS_KEY,
        TICK_UPLOAD_SIGNATURE_KEY,
        TICK_ROW_COUNT_KEY,
        TICK_SESSION_COUNT_KEY,
        TICK_WARNINGS_KEY,
    ):
        state.pop(key, None)


def _handle_tick_attach_submit(st, *, instrument: str, uploaded_files) -> None:
    """Resolve typed + uploaded tick paths and install when valid."""
    typed = _normalize_tick_path_list(st.session_state.get(TICK_PATHS_TEXT_KEY))
    persisted: list[str] = []
    if uploaded_files:
        persisted = _persist_tick_uploads(uploaded_files, _tick_upload_dir())
    resolved: list[str] = list(persisted)
    missing: list[str] = []
    outside: list[str] = []
    for token in typed:
        status, found = _classify_typed_tick_path(token)
        if status == "ok" and found is not None:
            resolved.append(str(found))
        elif status == "outside":
            outside.append(token)
        else:
            missing.append(token)
    if missing:
        st.error("Tick file is not an existing file: " + ", ".join(missing))
    if outside:
        st.error(
            "Tick file is outside the trusted local roots (cwd and store): " + ", ".join(outside)
        )
    if missing or outside:
        return
    combined, dedupe_warnings = _dedupe_attached_tick_paths(resolved)
    if not combined:
        st.error("Choose at least one Tick–Tick–Last file or path.")
        return
    try:
        sessions, rows, warnings = _validate_attached_tick_paths(
            combined,
            instrument=instrument,
        )
    except (TickIngestError, DataValidationError, OSError, ValueError) as exc:
        st.error(str(exc))
        return
    _install_tick_paths(
        st.session_state,
        combined,
        row_count=rows,
        session_count=sessions,
        signature="|".join(combined),
        warnings=[*dedupe_warnings, *warnings],
    )
    st.rerun()


def _render_tick_attached_status(st) -> None:
    """Show installed tick-last files and the clear control."""
    installed = st.session_state.get(TICK_PATHS_KEY)
    if not (isinstance(installed, list) and installed):
        return
    sessions = st.session_state.get(TICK_SESSION_COUNT_KEY)
    rows = st.session_state.get(TICK_ROW_COUNT_KEY)
    detail = ""
    if isinstance(sessions, int) and isinstance(rows, int):
        detail = f" ({sessions:,} session(s), {rows:,} prints)"
    st.info(
        f"Tick-last attached: {len(installed)} file(s){detail}. "
        "Paste these paths into Studies Build when factors name VA "
        "tokens. Data-page attach does not feed classic Calculate "
        "levels. Paths must sit under cwd or the local store. "
        "15s remains the bar clock."
    )
    for path in installed:
        st.write(f"- `{path}`")
    stored_warnings = st.session_state.get(TICK_WARNINGS_KEY)
    if isinstance(stored_warnings, list):
        for warning in stored_warnings:
            st.warning(warning)
    if st.button("Clear tick attach"):
        _clear_tick_session_state(st)
        st.session_state[TICK_UPLOADER_NONCE_KEY] = (
            int(st.session_state.get(TICK_UPLOADER_NONCE_KEY, 0)) + 1
        )
        st.rerun()


def render_tick_attach(st, *, instrument: str) -> None:
    """Optional Quantower Tick–Tick–Last attach beside the 15s bar clock."""
    with st.expander("Quantower tick-last (optional; VA / APOC / rolling POC)", expanded=False):
        st.caption(
            "Attach one or many Quantower Tick–Tick–Last CSVs for prior VA, "
            "APOC, and rolling POC. This does not replace the 15-second "
            "(or one-minute) OHLCV file and is not an ingestion mode. "
            "Named VA / APOC / rolling POC refuse without ticks "
            "(`requires ticks`). Production math is tick Last×Volume only "
            "(never typical). Unsound prints still emit `NaN`. Studies keep "
            "walking 1m."
        )
        uploader_nonce = int(st.session_state.get(TICK_UPLOADER_NONCE_KEY, 0))
        uploaded_files = st.file_uploader(
            "Tick–Tick–Last CSV (one or many)",
            type=["csv", "txt"],
            accept_multiple_files=True,
            key=f"tick_csv_upload_{uploader_nonce}",
        )
        st.text_area(
            "Tick file paths (one per line, optional)",
            key=TICK_PATHS_TEXT_KEY,
            placeholder="data/es_ticks.csv",
            help=(
                "Local Quantower Tick–Tick–Last paths already on disk. "
                "Must sit under cwd or the local store — Launch and Studies "
                "Build pin these the same way as dataset.path."
            ),
        )
        if st.button("Attach tick files"):
            _handle_tick_attach_submit(st, instrument=instrument, uploaded_files=uploaded_files)
        _render_tick_attached_status(st)
