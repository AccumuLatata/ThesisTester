"""Classic → thesis run attachment helpers (CAI-6).

Builds/verifies a research bundle from classic page state, exports a CAI-4
RunSpec, and registers an immutable classic-origin thesis run. Streamlit UI is
lazy-imported so unit tests stay Streamlit-free. Recording must never live in
``classic_context`` (link/create must remain non-recording).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping

import pandas as pd

from thesistester.assistant import AssistantOrchestrator, OrchestrationResult
from thesistester.classic_context import (
    get_active_thesis_id,
    get_active_thesis_name,
    is_research_mode,
    set_classic_flash,
    set_pending_navigation,
)
from thesistester.classic_export import (
    classic_state_export_gaps,
    classic_state_to_run_spec,
    format_classic_export_gaps,
)
from thesistester.persistence.local_store import get_store_root
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def classic_session_ready_for_record(session_state: Mapping[str, Any]) -> bool:
    """True when classic session has a completed backtest suitable for recording."""
    return isinstance(session_state.get("trades"), pd.DataFrame) and isinstance(
        session_state.get("equity_curve"), pd.DataFrame
    )


def materialize_classic_source_csv(
    session_state: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> Path:
    """Write a canonical OHLCV CSV from in-memory classic data for RunSpec lineage.

    Used only when the session lacks ``dataset_source_path`` / ``source_csv_path``.
    Does not recompute levels or trades.
    """
    data = session_state.get("data")
    if not isinstance(data, pd.DataFrame):
        raise ValueError("Classic session is missing a data DataFrame.")
    missing = [column for column in _OHLCV_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError("Classic data is missing required OHLCV columns: " + ", ".join(missing))
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "classic_source.csv"
    data.loc[:, list(_OHLCV_COLUMNS)].to_csv(path, index=False)
    return path.resolve()


def resolve_classic_record_source_path(
    session_state: Mapping[str, Any],
    *,
    materialize_dir: str | Path,
    source_path: str | Path | None = None,
) -> str:
    """Return an existing source path or materialize one under ``materialize_dir``."""
    if source_path is not None and str(source_path).strip():
        return str(Path(source_path).expanduser().resolve())
    for key in ("dataset_source_path", "source_csv_path"):
        value = session_state.get(key)
        if isinstance(value, (str, Path)) and str(value).strip():
            return str(Path(value).expanduser().resolve())
    return str(materialize_classic_source_csv(session_state, output_dir=materialize_dir))


def record_classic_session_run(
    orchestrator: AssistantOrchestrator,
    *,
    thesis_id: str,
    session_state: Mapping[str, Any],
    source_path: str | Path | None = None,
    store_root: str | Path | None = None,
    conversation_id: str | None = None,
    force_new: bool = False,
) -> OrchestrationResult:
    """Export RunSpec, write bundle, and register a classic-origin thesis run.

    Does not recompute the experiment. Raises ``ValueError`` when classic export
    gaps remain after source-path resolution.
    """
    if not classic_session_ready_for_record(session_state):
        raise ValueError(
            "Record and discuss requires a completed classic backtest (trades and equity_curve)."
        )
    thesis = orchestrator.get_thesis(thesis_id)
    root = Path(store_root) if store_root is not None else get_store_root()
    staging = root / "assistant" / "theses" / thesis_id / "classic_registration" / "staging"
    resolved_source = resolve_classic_record_source_path(
        session_state,
        materialize_dir=staging,
        source_path=source_path,
    )
    gaps = classic_state_export_gaps(
        session_state,
        source_path=resolved_source,
        store_root=root,
    )
    if gaps:
        rendered = "; ".join(
            f"{item['code']}: {item['message']}" for item in format_classic_export_gaps(gaps)
        )
        raise ValueError(f"Classic state is not exportable: {rendered}")

    run_spec = classic_state_to_run_spec(
        session_state,
        name=thesis.name,
        source_path=resolved_source,
        store_root=root,
    )
    bundle_bytes = build_research_bundle(session_state)
    digest = canonical_bundle_hash(bundle_bytes)
    output_path = orchestrator.default_bundle_output_path(thesis_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bundle_bytes)

    result = orchestrator.register_external_bundle_run(
        thesis_id=thesis_id,
        bundle_path=output_path,
        run_spec=run_spec,
        expected_hash=digest,
        conversation_id=conversation_id,
        force_new=force_new,
    )
    # Idempotent reuse keeps the existing provenance path; drop the orphan zip.
    if bool(result.payload.get("idempotent")):
        stored = result.payload.get("bundle_path")
        try:
            if (
                isinstance(stored, str)
                and stored.strip()
                and output_path.resolve() != Path(stored).resolve()
            ):
                output_path.unlink(missing_ok=True)
        except OSError:
            pass
    return result


def render_record_and_discuss(
    *,
    page_key: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Render the **Record and discuss this run** control on classic pages."""
    import streamlit as st

    if not isinstance(page_key, str) or not page_key.strip():
        raise ValueError("page_key must be a non-empty string.")
    page = page_key.strip()
    state = session_state if session_state is not None else st.session_state

    if not classic_session_ready_for_record(state):
        return

    st.subheader("Thesis recording")
    if not is_research_mode(state):
        st.info(
            "Link or create a thesis (Setup Builder → Thesis research context) "
            "to record this completed run for Assistant discussion."
        )
        return

    thesis_id = get_active_thesis_id(state)
    thesis_name = get_active_thesis_name(state) or thesis_id
    st.caption(
        f"Active thesis: **{thesis_name}**. "
        "Recording attaches the current research bundle without recomputing."
    )
    force_new = st.checkbox(
        "Create a new run record even if this bundle was already registered",
        value=False,
        key=f"classic_record_force_new_{page}",
    )
    if st.button(
        "Record and discuss this run",
        key=f"classic_record_and_discuss_{page}",
        type="primary",
        use_container_width=True,
    ):
        if not isinstance(thesis_id, str) or not thesis_id.strip():
            st.error("No active thesis is linked.")
            return
        try:
            orchestrator = AssistantOrchestrator.for_local_workspace()
            result = record_classic_session_run(
                orchestrator,
                thesis_id=thesis_id,
                session_state=state,
                force_new=bool(force_new),
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface registration failures in UI
            st.error(f"Recording failed: {exc}")
            return

        if result.status != "completed":
            error = result.payload.get("error") if isinstance(result.payload, dict) else None
            message = None
            if isinstance(error, Mapping):
                message = error.get("message")
            st.error(message or f"Recording ended with status {result.status}.")
            return

        run_id = result.payload.get("run_id")
        digest = result.payload.get("canonical_bundle_hash")
        idempotent = bool(result.payload.get("idempotent"))
        short_run = str(run_id)[-8:] if isinstance(run_id, str) else "?"
        short_hash = str(digest)[:12] if isinstance(digest, str) else "?"
        verb = "Reused existing" if idempotent else "Recorded"
        set_classic_flash(
            state,
            level="success",
            message=(
                f"{verb} classic run …{short_run} (bundle {short_hash}…). "
                "Opening Research Assistant."
            ),
        )
        set_pending_navigation(state, "pages/14_Research_Assistant.py")
        st.rerun()
