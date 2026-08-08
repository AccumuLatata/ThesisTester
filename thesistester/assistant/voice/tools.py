"""Read-only voice tool schemas and allowlisted executor (VA-3).

Exact v1 tools: get_run_overview, get_metric, list_caveats, compare_two_runs.
Never executes compute, search, mcp, or save_comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from thesistester.assistant.explainer import EvidencePacket, compare_evidence
from thesistester.assistant.repository import AssistantRepositoryError
from thesistester.assistant.results_overview import (
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
    build_deterministic_kpi_reply,
    build_expert_overlay,
    build_structured_remediation_reply,
    has_overview_negative_cue,
    match_overview_intent,
)
from thesistester.assistant.tools import AssistantToolError
from thesistester.assistant.voice.contracts import VoiceToolInvocation
from thesistester.assistant.voice.session import VoiceSessionError, VoiceSessionService
from thesistester.assistant.workspace import require_run_bundle_hash
from thesistester.reporting import to_jsonable

_ALLOWED_METRIC_ROOTS = frozenset({"results", "assumptions", "provenance"})
_VOICE_TOOL_NAMES = frozenset(
    {
        "get_run_overview",
        "get_metric",
        "list_caveats",
        "compare_two_runs",
    }
)
# Server-side xAI tool types that must never appear on ThesisTester voice sessions.
_FORBIDDEN_REALTIME_TOOL_TYPES = frozenset({"web_search", "x_search", "file_search", "mcp"})


def realtime_function_tool_schemas() -> tuple[dict[str, Any], ...]:
    """Return VA-3 function tool schemas safe for xAI ``session.update``."""
    return tuple(dict(schema) for schema in VOICE_TOOL_SCHEMAS)


def assert_realtime_tools_allowlisted(tools: list[Any] | tuple[Any, ...] | None) -> None:
    """Fail closed if a session tool list includes search/mcp or unknown functions."""
    if tools is None:
        return
    if not isinstance(tools, (list, tuple)):
        raise VoiceToolError("Realtime tools payload must be a list.")
    for index, tool in enumerate(tools):
        if not isinstance(tool, Mapping):
            raise VoiceToolError(f"Realtime tools[{index}] must be an object.")
        tool_type = str(tool.get("type") or "").strip()
        if tool_type in _FORBIDDEN_REALTIME_TOOL_TYPES:
            raise VoiceToolError(
                f"Forbidden realtime tool type {tool_type!r} is not allowed on voice sessions."
            )
        if tool_type != "function":
            raise VoiceToolError(
                f"Realtime tools may only include custom function tools; got type={tool_type!r}."
            )
        name = str(tool.get("name") or "").strip()
        if name not in _VOICE_TOOL_NAMES:
            raise VoiceToolError(f"Realtime function tool not in VA-3 allowlist: {name!r}.")


VOICE_TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "get_run_overview",
        "description": (
            "Return a DI-shaped grounded overview from the bound hash-verified "
            "evidence packet (summary, kpi_claims on results.trade_summary.*, "
            "digit-free expert_overlay, packet caveats). Prefer these fields; "
            "do not invent results.trade_count or results.instrument."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_metric",
        "description": (
            "Return one typed metric value from the bound evidence packet by "
            "dot-path under results, assumptions, or provenance. Prefer "
            "results.trade_summary.* paths (e.g. win_rate, trade_count)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Dot-path such as results.trade_summary.win_rate or "
                        "results.trade_summary.trade_count"
                    ),
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_caveats",
        "description": "List honesty caveats from the bound evidence packet.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "compare_two_runs",
        "description": (
            "Compare the bound run to another completed thesis run via pure "
            "compare_evidence. Does not persist a comparison record."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "other_run_id": {
                    "type": "string",
                    "description": "run_… id of the other completed run on this thesis",
                }
            },
            "required": ["other_run_id"],
            "additionalProperties": False,
        },
    },
)


class VoiceToolError(ValueError):
    """Raised when a voice tool name/args/path is rejected fail-closed."""


@dataclass(frozen=True)
class VoiceToolSession:
    """Bound handle for allowlisted voice tool execution."""

    service: VoiceSessionService
    thesis_id: str
    session_id: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_exists(root: Mapping[str, Any], path: str) -> bool:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _path_get(root: Mapping[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _safe_jsonable(value: Any) -> Any:
    try:
        return to_jsonable(value)
    except Exception:
        return str(value)


def _validate_metric_path(path: Any) -> str:
    if not isinstance(path, str) or not path.strip():
        raise VoiceToolError("get_metric requires a non-empty path string.")
    normalized = path.strip()
    if "/" in normalized or "\\" in normalized:
        raise VoiceToolError("get_metric path must not contain filesystem separators.")
    if ".." in normalized:
        raise VoiceToolError("get_metric rejects path traversal.")
    parts = normalized.split(".")
    if any(not part or part.strip() != part for part in parts):
        raise VoiceToolError("get_metric path segments must be non-empty.")
    if parts[0] not in _ALLOWED_METRIC_ROOTS:
        raise VoiceToolError("get_metric path must start with results, assumptions, or provenance.")
    return normalized


def _require_results_packet(session: VoiceToolSession) -> tuple[Any, EvidencePacket]:
    record = session.service.repository.get_voice_session(session.thesis_id, session.session_id)
    if record.channel != "results_qa":
        raise VoiceToolError("Voice tools that read evidence require a results_qa session.")
    if record.status != "active":
        raise VoiceToolError("Cannot execute voice tools on an ended session.")
    try:
        packet = session.service.require_bound_packet(session.thesis_id, session.session_id)
    except VoiceSessionError as exc:
        raise VoiceToolError(str(exc)) from exc
    return record, packet


def _latest_user_transcript_text(session: VoiceToolSession) -> str | None:
    """Current-turn user text for DX-1 overview intent selection.

    Uses the last non-empty ``role=="user"`` transcript turn **only when it is
    still the newest turn on the session** (no assistant turn after it). If an
    assistant turn already followed that user text, treat as no-text → neutral:
    otherwise a prior specialist/veto ask would false-veto a later
    ``get_run_overview`` call that was not tied to a fresh user utterance.
    """
    record = session.service.repository.get_voice_session(session.thesis_id, session.session_id)
    latest_user_text: str | None = None
    latest_user_index: int | None = None
    for index, turn in enumerate(record.transcript):
        if getattr(turn, "role", None) != "user":
            continue
        text = str(getattr(turn, "text", "") or "").strip()
        if text:
            latest_user_text = text
            latest_user_index = index
    if latest_user_text is None or latest_user_index is None:
        return None
    # Stale when any later turn exists (assistant reply, tool-side persist, etc.).
    if latest_user_index < len(record.transcript) - 1:
        return None
    return latest_user_text


def _claims_as_json(claims: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for claim in claims or ():
        if hasattr(claim, "to_dict"):
            payload = claim.to_dict()
            if isinstance(payload, Mapping):
                out.append(dict(payload))
            continue
        if isinstance(claim, Mapping):
            out.append(
                {
                    "text": claim.get("text"),
                    "path": claim.get("path"),
                    "value": _safe_jsonable(claim.get("value")),
                }
            )
    return out


def _packet_legacy_framing(packet: EvidencePacket) -> dict[str, Any]:
    return {
        "caveats": [caveat.to_dict() for caveat in packet.caveats],
        "limitations": list(packet.limitations),
        "next_experiments": list(packet.next_experiments),
    }


def _project_veto_overview_envelope(
    *,
    record: Any,
    packet: EvidencePacket,
) -> dict[str, Any]:
    """Negative-cue veto: remediation + legacy strip (no explainer narrative)."""
    reply = build_structured_remediation_reply(packet, failure_class="ungrounded")
    remediation = str(reply.summary or "").strip()
    return {
        **_packet_legacy_framing(packet),
        "overview": remediation,
        "claims": [],
        "overview_intent": None,
        "remediation": remediation,
        "run_id": record.run_id,
        "canonical_bundle_hash": record.expected_canonical_bundle_hash,
    }


def _project_di_overview_envelope(
    *,
    record: Any,
    packet: EvidencePacket,
    intent: str,
) -> dict[str, Any]:
    """Overview-match / neutral: DI builders → envelope (claims policy A)."""
    evidence_context = packet.to_dict()
    reply = build_deterministic_kpi_reply(
        packet,
        evidence_context,
        intent=intent,
    )
    overlay = build_expert_overlay(packet, reply.claims)
    claim_dicts = _claims_as_json(reply.claims)
    summary = str(reply.summary or "").strip()
    envelope: dict[str, Any] = {
        **_packet_legacy_framing(packet),
        "overview": summary,
        "claims": claim_dicts,
        "summary": summary,
        "kpi_claims": list(claim_dicts),
        "expert_overlay": list(overlay),
        "overview_intent": intent,
        "run_id": record.run_id,
        "canonical_bundle_hash": record.expected_canonical_bundle_hash,
    }
    if not claim_dicts:
        rem = build_structured_remediation_reply(packet, failure_class="ungrounded")
        envelope["remediation"] = str(rem.summary or "").strip()
    return envelope


def _tool_get_run_overview(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    if args:
        raise VoiceToolError("get_run_overview accepts no arguments.")
    record, packet = _require_results_packet(session)
    latest_user = _latest_user_transcript_text(session)
    # DX §4.1 decision order: veto → match → neutral (unmatched / no-text).
    if latest_user is not None and has_overview_negative_cue(latest_user):
        return _project_veto_overview_envelope(record=record, packet=packet)
    if latest_user is not None:
        matched = match_overview_intent(latest_user)
        if matched in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
            return _project_di_overview_envelope(
                record=record,
                packet=packet,
                intent=matched,
            )
    return _project_di_overview_envelope(
        record=record,
        packet=packet,
        intent=OVERVIEW_INTENT_RUN,
    )


def _tool_get_metric(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    path = _validate_metric_path(args.get("path"))
    unknown = sorted(set(args) - {"path"})
    if unknown:
        raise VoiceToolError(f"get_metric unknown arguments: {unknown}")
    _record, packet = _require_results_packet(session)
    root = packet.to_dict()
    if not _path_exists(root, path):
        raise VoiceToolError(f"Unknown metric path: {path}")
    value = _path_get(root, path)
    if isinstance(value, (dict, list)):
        raise VoiceToolError("get_metric path must resolve to a scalar leaf value.")
    if value is None or value == "":
        raise VoiceToolError(f"Metric path is empty: {path}")
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int) and not isinstance(value, bool):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    elif isinstance(value, str):
        value_type = "string"
    else:
        value_type = type(value).__name__
    return {
        "path": path,
        "value": _safe_jsonable(value),
        "value_type": value_type,
        "run_id": _record.run_id,
    }


def _tool_list_caveats(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    if args:
        raise VoiceToolError("list_caveats accepts no arguments.")
    _record, packet = _require_results_packet(session)
    return {
        "caveats": [caveat.to_dict() for caveat in packet.caveats],
        "warnings": list(packet.warnings),
        "run_id": _record.run_id,
    }


def _load_other_run_packet(
    session: VoiceToolSession, *, other_run_id: str
) -> tuple[str, str, EvidencePacket]:
    service = session.service
    if service.tools is None:
        raise VoiceToolError("AssistantTools is required for compare_two_runs.")
    try:
        other = service.repository.get_run(session.thesis_id, other_run_id)
    except AssistantRepositoryError as exc:
        raise VoiceToolError("Other research run does not exist.") from exc
    if other.status != "completed":
        raise VoiceToolError("compare_two_runs requires a completed other run.")
    if not isinstance(other.provenance, Mapping):
        raise VoiceToolError("Other run is missing provenance.")
    try:
        expected_hash = require_run_bundle_hash(other.provenance).lower()
    except ValueError as exc:
        raise VoiceToolError(str(exc)) from exc
    bundle_path = other.provenance.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise VoiceToolError("Other run is missing bundle_path provenance.")
    try:
        resolved = Path(bundle_path.strip()).expanduser().resolve()
    except OSError as exc:
        raise VoiceToolError("Other run bundle path is invalid.") from exc
    if not any(resolved.is_relative_to(root.resolve()) for root in service.tools.data_roots):
        raise VoiceToolError("Other run bundle path is outside assistant data roots.")
    if not resolved.is_file():
        raise VoiceToolError("Other run bundle file is missing.")
    try:
        payload = service.tools.build_bundle_evidence_packet(
            str(resolved),
            expected_hash=expected_hash,
            provenance=dict(other.provenance),
        )
    except (AssistantToolError, OSError, ValueError) as exc:
        raise VoiceToolError(str(exc)) from exc
    except Exception as exc:
        # Corrupt / non-zip bytes must fail closed (hash verify / load path).
        raise VoiceToolError("Other run bundle could not be hash-verified for comparison.") from exc
    return other.run_id, expected_hash, EvidencePacket.from_dict(payload)


def _tool_compare_two_runs(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(args) - {"other_run_id"})
    if unknown:
        raise VoiceToolError(f"compare_two_runs unknown arguments: {unknown}")
    other_run_id = args.get("other_run_id")
    if not isinstance(other_run_id, str) or not other_run_id.strip():
        raise VoiceToolError("compare_two_runs requires a non-empty other_run_id.")
    record, left_packet = _require_results_packet(session)
    if record.run_id is None:
        raise VoiceToolError("Bound results session is missing run_id.")
    if other_run_id.strip() == record.run_id:
        raise VoiceToolError("compare_two_runs other_run_id must differ from the bound run.")
    other_id, other_hash, right_packet = _load_other_run_packet(
        session, other_run_id=other_run_id.strip()
    )
    comparison = compare_evidence(left_packet, right_packet)
    # Pure compare only — never call repository.save_comparison.
    return {
        "left_run_id": record.run_id,
        "right_run_id": other_id,
        "left_canonical_bundle_hash": record.expected_canonical_bundle_hash,
        "right_canonical_bundle_hash": other_hash,
        "comparison": comparison,
        "persisted": False,
    }


_TOOL_IMPLS = {
    "get_run_overview": _tool_get_run_overview,
    "get_metric": _tool_get_metric,
    "list_caveats": _tool_list_caveats,
    "compare_two_runs": _tool_compare_two_runs,
}


def _flush_tool_audit_to_conversation(
    session: VoiceToolSession,
    invocation: VoiceToolInvocation,
) -> None:
    """Best-effort per-call conversation tool_transcript entry (VA-3 scope)."""
    try:
        record = session.service.repository.get_voice_session(session.thesis_id, session.session_id)
    except AssistantRepositoryError:
        return
    conversation_id = record.conversation_id
    if not conversation_id:
        return
    try:
        conversation = session.service.repository.get_conversation(
            session.thesis_id, conversation_id
        )
    except AssistantRepositoryError:
        return
    tool_entry = {
        "kind": "voice_tool",
        "voice_session_id": record.session_id,
        "tool_name": invocation.tool_name,
        "arguments": invocation.arguments,
        "ok": invocation.ok,
        "result": invocation.result,
        "error": invocation.error,
        "created_at": invocation.created_at,
        "channel": record.channel,
    }
    placeholder = {
        "role": "system",
        "content": f"voice_tool:{invocation.tool_name}",
        "channel": record.channel,
        "voice_session_id": record.session_id,
        "created_at": invocation.created_at,
    }
    if record.run_id is not None:
        placeholder["run_id"] = record.run_id
    try:
        session.service.repository.append_conversation_message(
            session.thesis_id,
            conversation_id,
            expected_revision=conversation.revision,
            message=placeholder,
            tool_entry=tool_entry,
        )
    except AssistantRepositoryError:
        return


def _audit_invocation(
    session: VoiceToolSession,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    ok: bool,
    result: dict[str, Any],
    error: str | None,
) -> VoiceToolInvocation:
    invocation = VoiceToolInvocation(
        tool_name=tool_name,
        arguments=arguments,
        ok=ok,
        result=result,
        created_at=_utcnow(),
        error=error,
    )
    try:
        session.service.append_tool_invocation(
            session.thesis_id,
            session.session_id,
            invocation,
            allow_ended=True,
        )
    except (VoiceSessionError, AssistantRepositoryError):
        # Still return the in-memory audit row to the caller even if persist fails.
        pass
    _flush_tool_audit_to_conversation(session, invocation)
    return invocation


def execute_voice_tool(
    name: str,
    args: Mapping[str, Any] | None,
    *,
    session: VoiceToolSession,
) -> dict[str, Any]:
    """Execute one allowlisted voice tool and record exactly one audit row.

    Unknown / denied names fail closed with no tool side effects beyond the
    single audit invocation row.
    """
    arguments = dict(args or {})
    tool_name = name.strip() if isinstance(name, str) else ""
    if tool_name not in _VOICE_TOOL_NAMES:
        invocation = _audit_invocation(
            session,
            tool_name=tool_name or str(name),
            arguments=arguments,
            ok=False,
            result={},
            error=f"Unknown or denied voice tool: {name!r}",
        )
        return {
            "ok": False,
            "tool_name": invocation.tool_name,
            "result": {},
            "error": invocation.error,
            "audit": invocation.to_dict(),
        }

    impl = _TOOL_IMPLS[tool_name]
    try:
        result = impl(session, arguments)
        invocation = _audit_invocation(
            session,
            tool_name=tool_name,
            arguments=arguments,
            ok=True,
            result=result if isinstance(result, dict) else {"value": result},
            error=None,
        )
        return {
            "ok": True,
            "tool_name": tool_name,
            "result": invocation.result,
            "error": None,
            "audit": invocation.to_dict(),
        }
    except Exception as exc:
        # Broad catch keeps the one-audit-row contract for unexpected failures
        # (e.g. compare_evidence ValueError) without leaking side effects.
        if not isinstance(
            exc,
            (VoiceToolError, VoiceSessionError, AssistantRepositoryError, AssistantToolError),
        ):
            error_text = f"Voice tool failed closed: {exc}"
        else:
            error_text = str(exc)
        invocation = _audit_invocation(
            session,
            tool_name=tool_name,
            arguments=arguments,
            ok=False,
            result={},
            error=error_text,
        )
        return {
            "ok": False,
            "tool_name": tool_name,
            "result": {},
            "error": invocation.error,
            "audit": invocation.to_dict(),
        }
