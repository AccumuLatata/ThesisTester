"""Classic research-mode execution ledger (CAI-7).

When recording policy is ``all_executions`` under an active thesis, every Backtest
attempt is persisted as a ResearchRun before classic execution and terminalized
as completed, failed, or cancelled. Manual policy and non-research sessions are
no-ops. Recording stays out of ``classic_context`` so link/create remain
non-recording.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from thesistester.assistant import AssistantOrchestrator, ResearchRun
from thesistester.classic_context import (
    get_active_thesis_id,
    get_recording_policy,
    is_research_mode,
)
from thesistester.classic_export import (
    classic_state_export_gaps,
    classic_state_to_run_spec,
    format_classic_export_gaps,
)
from thesistester.classic_record import (
    classic_session_ready_for_record,
    resolve_classic_record_source_path,
)
from thesistester.persistence.local_store import get_store_root
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import compute_run_spec_hash, normalize_execution_origin
from thesistester.reporting import to_jsonable

CLASSIC_LEDGER_ACTION = "classic_execution_ledger"
RECORDING_POLICY_ALL_EXECUTIONS = "all_executions"


@dataclass(frozen=True)
class ClassicLedgerHandle:
    """In-flight classic ledger attempt (maps to a repository ResearchRun)."""

    thesis_id: str
    run_id: str
    revision: int
    spec_version: int
    config_hash: str
    origin_page: str


def should_record_all_executions(session_state: Mapping[str, Any]) -> bool:
    """True when research mode is active and policy is ``all_executions``."""
    return (
        is_research_mode(session_state)
        and get_recording_policy(session_state) == RECORDING_POLICY_ALL_EXECUTIONS
    )


def is_classic_ledger_run(run: ResearchRun | Mapping[str, Any]) -> bool:
    """True when a ResearchRun was created by the CAI-7 classic ledger."""
    request = run.request if isinstance(run, ResearchRun) else run.get("request")
    if not isinstance(request, Mapping):
        return False
    return request.get("action") == CLASSIC_LEDGER_ACTION


def ledger_run_label(run: ResearchRun) -> str:
    """Short UI label distinguishing ledger / manual-record / assistant runs."""
    request = run.request if isinstance(run.request, Mapping) else {}
    action = request.get("action")
    origin = None
    if isinstance(run.provenance, Mapping):
        origin = run.provenance.get("execution_origin")
    if action == CLASSIC_LEDGER_ACTION:
        page = request.get("origin_page") or "classic"
        return f"ledger:{page}"
    if action == "register_external_bundle":
        return "recorded:manual"
    if origin == "classic":
        return "classic"
    if origin == "assistant" or action is None:
        return "assistant"
    return str(action)


def begin_classic_execution_ledger(
    orchestrator: AssistantOrchestrator,
    *,
    thesis_id: str,
    session_state: Mapping[str, Any],
    origin_page: str,
    store_root: str | Path | None = None,
) -> ClassicLedgerHandle:
    """Persist a running ledger request before classic execution.

    Exports and confirms a CAI-4 RunSpec for lineage, then ``start_run``. Does
    not simulate trades or write a research bundle.
    """
    page = str(origin_page).strip()
    if not page:
        raise ValueError("origin_page must be a non-empty string.")
    thesis = orchestrator.get_thesis(thesis_id)
    root = Path(store_root) if store_root is not None else get_store_root()
    staging = root / "assistant" / "theses" / thesis_id / "classic_ledger" / "staging"
    resolved_source = resolve_classic_record_source_path(
        session_state,
        materialize_dir=staging,
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
        raise ValueError(
            "all_executions ledger requires an exportable classic RunSpec before "
            f"execution: {rendered}"
        )
    run_spec = classic_state_to_run_spec(
        session_state,
        name=thesis.name,
        source_path=resolved_source,
        store_root=root,
    )
    config_hash = compute_run_spec_hash(to_jsonable(dict(run_spec)))
    confirmed = orchestrator.confirm_validated_spec(
        thesis_id=thesis_id,
        validated_spec=dict(run_spec),
        confirmation_note=(f"Classic all_executions ledger request from {page} (CAI-7)"),
    )
    run = orchestrator.repository.start_run(
        thesis_id,
        spec_version=confirmed.version,
        request={
            "action": CLASSIC_LEDGER_ACTION,
            "origin_page": page,
            "classic_config_hash": config_hash,
            "execution_origin": "classic",
            "recording_policy": RECORDING_POLICY_ALL_EXECUTIONS,
            "run_spec": dict(run_spec),
        },
    )
    return ClassicLedgerHandle(
        thesis_id=thesis_id,
        run_id=run.run_id,
        revision=run.revision,
        spec_version=confirmed.version,
        config_hash=config_hash,
        origin_page=page,
    )


def fail_classic_execution_ledger(
    orchestrator: AssistantOrchestrator,
    handle: ClassicLedgerHandle,
    *,
    message: str,
    phase: str,
    extra: Mapping[str, Any] | None = None,
) -> ResearchRun:
    """Terminalize a ledger attempt as failed. Never marks the run completed."""
    text = str(message).strip() or "Classic execution failed."
    phase_text = str(phase).strip() or "unknown"
    error: dict[str, Any] = {
        "phase": phase_text,
        "message": text,
        "origin_page": handle.origin_page,
        "classic_config_hash": handle.config_hash,
    }
    if extra:
        error.update({str(key): value for key, value in extra.items()})
    return orchestrator.repository.fail_run(
        handle.thesis_id,
        handle.run_id,
        expected_revision=handle.revision,
        error=error,
    )


def complete_classic_execution_ledger(
    orchestrator: AssistantOrchestrator,
    handle: ClassicLedgerHandle,
    *,
    session_state: Mapping[str, Any],
    store_root: str | Path | None = None,
    warnings: Sequence[str] = (),
) -> ResearchRun:
    """Terminalize a successful classic execution.

    Writes a research bundle when session sections are complete. A bundle-write
    failure fails the run (not completed) while preserving the original request.
    """
    root = Path(store_root) if store_root is not None else get_store_root()
    warning_tuple = tuple(str(item).strip() for item in warnings if str(item).strip())

    if not classic_session_ready_for_record(session_state):
        return fail_classic_execution_ledger(
            orchestrator,
            handle,
            message=(
                "Classic execution finished but the session is missing required "
                "bundle sections for evidence attachment."
            ),
            phase="bundle_incomplete",
            extra={"simulation_succeeded": True},
        )

    output_path = orchestrator.default_bundle_output_path(handle.thesis_id, store_root=root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        bundle_bytes = build_research_bundle(session_state)
        output_path.write_bytes(bundle_bytes)
        digest = canonical_bundle_hash(bundle_bytes)
    except (OSError, ValueError, TypeError) as exc:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return fail_classic_execution_ledger(
            orchestrator,
            handle,
            message=f"Bundle write failed after classic execution: {exc}",
            phase="bundle_write",
            extra={"simulation_succeeded": True},
        )

    fingerprint = to_jsonable(session_state.get("levels_data_fingerprint"))
    request_run_spec = None
    current = orchestrator.repository.get_run(handle.thesis_id, handle.run_id)
    if isinstance(current.request, Mapping):
        request_run_spec = current.request.get("run_spec")

    from thesistester.research_identity import (
        try_page_data_identity,
        try_page_levels_identity,
    )

    page_data = try_page_data_identity(session_state)
    page_levels = try_page_levels_identity(session_state)
    data_identity = to_jsonable(session_state.get("data_identity"))
    levels_identity = to_jsonable(session_state.get("levels_identity"))
    if data_identity is None and page_data is not None:
        data_identity = page_data.to_dict()
    if levels_identity is None and page_levels is not None:
        levels_identity = page_levels.to_dict()

    provenance = {
        "bundle_path": str(output_path),
        "canonical_bundle_hash": digest,
        "dataset_fingerprint": fingerprint,
        "summary": {
            "trade_summary": to_jsonable(session_state.get("trade_summary")),
        },
        "warnings": list(warning_tuple),
        "effective_configuration": to_jsonable(request_run_spec)
        if isinstance(request_run_spec, Mapping)
        else None,
        "classic_config_hash": handle.config_hash,
        "origin_page": handle.origin_page,
        "execution_origin": normalize_execution_origin("classic"),
        "registration_source": "classic_execution_ledger",
        "recording_policy": RECORDING_POLICY_ALL_EXECUTIONS,
        "data_identity": data_identity,
        "levels_identity": levels_identity,
    }
    try:
        return orchestrator.repository.complete_run(
            handle.thesis_id,
            handle.run_id,
            expected_revision=handle.revision,
            provenance=provenance,
            warnings=warning_tuple,
        )
    except Exception as exc:
        # Keep the request record; do not leave a silent orphan zip or a
        # permanently ``running`` ResearchRun after complete_run fails.
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return fail_classic_execution_ledger(
            orchestrator,
            handle,
            message=f"complete_run failed after classic execution: {exc}",
            phase="complete_run",
            extra={"simulation_succeeded": True},
        )


def list_classic_ledger_runs(
    orchestrator: AssistantOrchestrator,
    *,
    thesis_id: str,
) -> tuple[ResearchRun, ...]:
    """Return thesis runs, newest first, for ledger display."""
    runs = orchestrator.list_runs(thesis_id)
    return tuple(reversed(runs))


def render_classic_execution_ledger(
    *,
    page_key: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Compact thesis run ledger for classic pages (Backtest)."""
    import streamlit as st

    if not isinstance(page_key, str) or not page_key.strip():
        raise ValueError("page_key must be a non-empty string.")
    state = session_state if session_state is not None else st.session_state
    if not is_research_mode(state):
        return
    thesis_id = get_active_thesis_id(state)
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        return

    policy = get_recording_policy(state)
    st.subheader("Thesis run ledger")
    st.caption(
        f"Recording policy: `{policy}`. "
        "Ledger attempts are thesis-recorded; exploratory runs without research "
        "mode are never listed here."
    )
    try:
        orchestrator = AssistantOrchestrator.for_local_workspace()
        runs = list_classic_ledger_runs(orchestrator, thesis_id=thesis_id)
    except Exception as exc:  # noqa: BLE001 - page chrome must not crash
        st.warning(f"Unable to load thesis run ledger: {exc}")
        return
    if not runs:
        st.info("No thesis-recorded runs yet for this thesis.")
        return

    rows: list[dict[str, Any]] = []
    for run in runs:
        request = run.request if isinstance(run.request, Mapping) else {}
        provenance = run.provenance if isinstance(run.provenance, Mapping) else {}
        error = run.error if isinstance(run.error, Mapping) else {}
        bundle_hash = provenance.get("canonical_bundle_hash")
        config_hash = request.get("classic_config_hash") or provenance.get("classic_config_hash")
        rows.append(
            {
                "Run": run.run_id[-8:],
                "Status": run.status,
                "Kind": ledger_run_label(run),
                "Origin": request.get("origin_page") or provenance.get("origin_page") or "—",
                "Config": (str(config_hash)[:12] + "…") if config_hash else "—",
                "Bundle": (str(bundle_hash)[:12] + "…") if bundle_hash else "—",
                "Error": error.get("message") or error.get("reason") or "",
                "Updated": run.updated_at,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
