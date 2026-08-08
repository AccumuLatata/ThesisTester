"""Multi-turn grounded results Q&A over a hash-verified EvidencePacket (RQ / DI)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import LLMProviderError, StructuredLLMClient
from thesistester.assistant.llm_explainer import (
    LLMEvidenceError,
    _path_exists,
    _path_get,
    assert_llm_explanation_grounded,
    merge_mandatory_packet_caveats,
)
from thesistester.assistant.results_overview import (
    apply_expert_overlay,
    build_deterministic_kpi_reply,
    build_prompt_path_catalog,
    build_structured_remediation_reply,
    classify_recovery_reason,
    failure_class_from_exception,
    match_overview_intent,
)

RESULTS_QA_CHANNEL = "results_qa"

_RESULTS_QA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "caveats", "claims", "followups"],
    "properties": {
        "summary": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "path"],
                "properties": {
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        },
        "followups": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = (
    "Answer only from the supplied evidence_packet JSON using structured claims. "
    "Each claim.text that includes a number must cite claim.path to an existing "
    "packet field. claim.path is relative to the evidence_packet object root "
    "(e.g. results.trade_summary.trade_count, results.projections.*, "
    "limitations, caveats) — never prefix paths with evidence_packet. or packet. "
    "Array rows may use integer indices (e.g. results.time_grouped_summary.0.avg_r). "
    "When path_catalog is present, cite only paths listed in "
    "path_catalog.existing_paths; on overview asks prefer a subset of "
    "path_catalog.kpi_allowlist / preferred_claim_paths. "
    "Do not invent nested keys. Do not add calculations, forecasts, trade advice, "
    "tools, or facts absent from the packet. "
    "Distinguish in-sample observed results from robustness/OOS evidence. "
    "When answering best SL/TP or best entry-time questions, cite "
    "results.projections.* (or results.best_grid_result when projections are "
    "absent) and state the ranking metric, candidate set / eligible count, "
    "min_trades filter, and in-sample vs OOS status from the evidence. "
    "Do not invent rankings or choose a ranking metric. "
    "Focus (post-hoc subset) is not Admit (constrained re-sim). Never claim "
    "deployable edge from Focus alone; when assumptions.entry_window.focus is "
    "enabled, keep the focus_post_hoc caveat and prefer Admit evidence. "
    "Narrate fractional rates with a % sign or the words percent/pct/Prozent "
    "(e.g. 60% or 60 Prozent for win_rate 0.6); bare 60 is not grounded from 0.6. "
    "Decimal commas are accepted for fractional claim values (e.g. 0,25 for 0.25). "
    "When evidence for the question is missing, say so in caveats and propose "
    "followups. Prefer number-free followups. Preserve uncertainty and caveats."
)

# Models often echo the user-payload wrapper key; strip before path resolution.
_CLAIM_PATH_WRAPPER_PREFIXES = ("evidence_packet.", "packet.")


def normalize_results_claim_path(path: str) -> str:
    """Strip accidental evidence-wrapper prefixes from a results claim path.

    Models sometimes stack wrappers (``evidence_packet.packet.*``); strip every
    leading ``evidence_packet.`` / ``packet.`` segment before resolution.
    """
    text = path.strip()
    while True:
        lowered = text.lower()
        stripped = False
        for prefix in _CLAIM_PATH_WRAPPER_PREFIXES:
            if lowered.startswith(prefix):
                text = text[len(prefix) :].lstrip(".")
                stripped = True
                break
        if not stripped:
            return text


@dataclass(frozen=True)
class ResultsQAReply:
    """Grounded multi-turn results reply; claims carry server-resolved values."""

    summary: str
    caveats: tuple[str, ...]
    claims: tuple[EvidenceClaim, ...] = ()
    followups: tuple[str, ...] = ()
    recovery_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "summary": self.summary,
            "caveats": list(self.caveats),
            "claims": [claim.to_dict() for claim in self.claims],
            "followups": list(self.followups),
        }
        if self.recovery_reason is not None:
            payload["recovery_reason"] = self.recovery_reason
        return payload


def format_results_qa_reply_content(reply: ResultsQAReply) -> str:
    """Build persisted assistant ``content`` for a results Q&A turn.

    Includes path-cited claims so Discuss results threads remain auditable in
    plain ``content`` (not only in structured message fields).
    """
    lines = [reply.summary.strip()]
    if reply.claims:
        lines.append("")
        lines.append("Claims:")
        for claim in reply.claims:
            lines.append(f"- `{claim.path}` = {claim.value} — {claim.text}")
    if reply.caveats:
        lines.append("")
        lines.append("Caveats:")
        lines.extend(f"- {item}" for item in reply.caveats)
    if reply.followups:
        lines.append("")
        lines.append("Follow-ups:")
        lines.extend(f"- {item}" for item in reply.followups)
    return "\n".join(lines).strip()


def filter_results_qa_history(
    messages: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    max_history_messages: int,
) -> tuple[dict[str, Any], ...]:
    """Return the last N results_qa messages for ``run_id`` (excluding tools)."""
    if not isinstance(max_history_messages, int) or max_history_messages < 0:
        raise ValueError("max_history_messages must be a non-negative integer.")
    selected: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        if message.get("channel") != RESULTS_QA_CHANNEL:
            continue
        if message.get("run_id") != run_id:
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "human", "assistant", "ai"}:
            continue
        selected.append(dict(message))
    if max_history_messages == 0:
        return ()
    return tuple(selected[-max_history_messages:])


def _decode_results_payload(
    payload: Mapping[str, Any],
    *,
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
) -> ResultsQAReply:
    if set(payload) != {"summary", "caveats", "claims", "followups"}:
        raise LLMEvidenceError(
            "Results Q&A reply must contain only summary, caveats, claims, and followups."
        )
    summary = payload["summary"]
    caveats = payload["caveats"]
    claims_raw = payload["claims"]
    followups_raw = payload["followups"]
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(caveats, list)
        or not isinstance(claims_raw, list)
        or not isinstance(followups_raw, list)
    ):
        raise LLMEvidenceError("Results Q&A reply has invalid field types.")
    if any(not isinstance(caveat, str) or not caveat.strip() for caveat in caveats):
        raise LLMEvidenceError("Results Q&A caveats must be non-empty strings.")
    if any(not isinstance(followup, str) or not followup.strip() for followup in followups_raw):
        raise LLMEvidenceError("Results Q&A followups must be non-empty strings.")
    claims: list[EvidenceClaim] = []
    for item in claims_raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"text", "path"}
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
            or not isinstance(item.get("path"), str)
            or not item["path"].strip()
        ):
            raise LLMEvidenceError("Results Q&A claims must be non-empty text/path objects.")
        path = normalize_results_claim_path(item["path"])
        if not path or not _path_exists(evidence_context, path):
            raise LLMEvidenceError(
                f"Results Q&A claim path {path!r} is missing from the evidence packet."
            )
        claims.append(
            EvidenceClaim(
                text=item["text"].strip(),
                path=path,
                value=_path_get(evidence_context, path),
            )
        )
    grounded = tuple(claims)
    summary_text = summary.strip()
    caveat_texts = merge_mandatory_packet_caveats(
        packet, tuple(caveat.strip() for caveat in caveats)
    )
    followup_texts = tuple(followup.strip() for followup in followups_raw)
    assert_llm_explanation_grounded(
        packet,
        summary=summary_text,
        caveats=caveat_texts,
        claims=grounded,
        followups=followup_texts,
    )
    return ResultsQAReply(
        summary=summary_text,
        caveats=caveat_texts,
        claims=grounded,
        followups=followup_texts,
    )


def _complete_results_structured(
    client: StructuredLLMClient,
    *,
    evidence_context: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    user_message: str,
    overview_intent: str | None = None,
    repair: Mapping[str, Any] | None = None,
    include_path_catalog: bool = True,
) -> dict[str, Any]:
    history_lines = [
        {
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in history
        if isinstance(message, Mapping)
    ]
    user_payload: dict[str, Any] = {
        "evidence_packet": dict(evidence_context),
        "history": history_lines,
        "user_message": user_message.strip(),
    }
    # DI-2: first-pass (and repair) path catalog — existing paths only.
    if include_path_catalog:
        user_payload["path_catalog"] = build_prompt_path_catalog(
            evidence_context,
            overview_intent=overview_intent,
        )
    if repair is not None:
        user_payload["repair"] = dict(repair)
    return client.complete_structured(
        system=_SYSTEM_PROMPT,
        user=json.dumps(user_payload, sort_keys=True),
        schema=_RESULTS_QA_SCHEMA,
    )


def _recover_results_reply(
    *,
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    overview_intent: str | None,
    exc: BaseException,
    repaired: bool,
    deterministic_overview_fallback: bool,
) -> ResultsQAReply:
    """Apply DI-1 overview fallback or §5.3 structured remediation."""
    reason = classify_recovery_reason(exc, repaired=repaired)
    if overview_intent is not None and deterministic_overview_fallback:
        return build_deterministic_kpi_reply(
            packet,
            evidence_context,
            intent=overview_intent,
            recovery_reason=reason,
        )
    return build_structured_remediation_reply(
        packet,
        failure_class=failure_class_from_exception(exc),
        recovery_reason=reason,
    )


def propose_results_reply(
    client: StructuredLLMClient,
    *,
    packet: EvidencePacket,
    history: Sequence[Mapping[str, Any]],
    user_message: str,
    turn_context: Mapping[str, Any] | None = None,
    repair_retry_enabled: bool = True,
    deterministic_overview_fallback: bool = True,
) -> ResultsQAReply:
    """Request a grounded results reply from the ephemeral turn evidence context.

    ``turn_context`` may include ``results.projections.*`` (RQ-2). Path
    resolution and numeric grounding audit that same object. When omitted, the
    immutable packet dict is used (RQ-1 behavior).

    DI-1: on grounding/provider faults, optionally one repair attempt, then
    deterministic overview fallback (matched intents only) or §5.3 structured
    remediation. Both flags false restores pre-DI hard-fail raises (TLS wrap
    still applies in the transport).

    DI-2: first-pass user payload includes ``path_catalog`` (existing paths;
    plus ``kpi_allowlist`` when an overview intent matches).

    DI-3: successful overview replies (and deterministic overview fallback)
    append a strictly digit-free expert overlay after mandatory caveats.
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise LLMEvidenceError("Results Q&A user message must be a non-empty string.")
    if turn_context is None:
        evidence_context: dict[str, Any] = packet.to_dict()
    else:
        if not isinstance(turn_context, Mapping):
            raise LLMEvidenceError("Results Q&A turn_context must be a mapping.")
        evidence_context = dict(turn_context)

    overview_intent = match_overview_intent(user_message)

    def _maybe_overlay(reply: ResultsQAReply) -> ResultsQAReply:
        if overview_intent is None:
            return reply
        return apply_expert_overlay(
            packet,
            summary=reply.summary,
            caveats=reply.caveats,
            claims=reply.claims,
            recovery_reason=reply.recovery_reason,
        )

    try:
        payload = _complete_results_structured(
            client,
            evidence_context=evidence_context,
            history=history,
            user_message=user_message,
            overview_intent=overview_intent,
        )
        return _maybe_overlay(
            _decode_results_payload(payload, packet=packet, evidence_context=evidence_context)
        )
    except (LLMEvidenceError, LLMProviderError) as first_exc:
        if not repair_retry_enabled and not deterministic_overview_fallback:
            raise
        # §5: repair is for grounding/auditor faults only. Provider/TLS faults
        # already exhausted transport retries — go straight to overview fallback
        # or §5.3 remediation (never a second model call on dead transport).
        if repair_retry_enabled and isinstance(first_exc, LLMEvidenceError):
            # Path allowlist lives solely on path_catalog (DI-2); repair carries
            # only the prior error + instruction so lists cannot diverge.
            repair_payload = {
                "prior_error": str(first_exc),
                "instruction": (
                    "Repair the reply using only path_catalog.existing_paths. "
                    "Narrate fractional rates with % or percent/pct/Prozent. "
                    "Do not invent paths or numbers."
                ),
            }
            try:
                repaired = _complete_results_structured(
                    client,
                    evidence_context=evidence_context,
                    history=history,
                    user_message=user_message,
                    overview_intent=overview_intent,
                    repair=repair_payload,
                )
                return _maybe_overlay(
                    _decode_results_payload(
                        repaired, packet=packet, evidence_context=evidence_context
                    )
                )
            except (LLMEvidenceError, LLMProviderError) as repair_exc:
                return _recover_results_reply(
                    packet=packet,
                    evidence_context=evidence_context,
                    overview_intent=overview_intent,
                    exc=repair_exc,
                    repaired=True,
                    deterministic_overview_fallback=deterministic_overview_fallback,
                )
        return _recover_results_reply(
            packet=packet,
            evidence_context=evidence_context,
            overview_intent=overview_intent,
            exc=first_exc,
            repaired=False,
            deterministic_overview_fallback=deterministic_overview_fallback,
        )
