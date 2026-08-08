"""DI overview matching, path-catalog hints, and deterministic KPI builders.

Fail-closed numbers stay in ``llm_explainer``. This module selects frozen
overview slices, builds DI-2 first-pass path catalogs, and builds auditor-safe
replies when the LLM path fails (DI-1).
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import LLMProviderError
from thesistester.assistant.llm_explainer import (
    _path_exists,
    _path_get,
    assert_llm_explanation_grounded,
    merge_mandatory_packet_caveats,
)

OVERVIEW_INTENT_KPI = "kpi_summary"
OVERVIEW_INTENT_RUN = "run_overview"

REASON_PATH_MISS = "overview_path_miss"
REASON_DIGIT_MISS = "overview_digit_miss"
REASON_PROVIDER_EXHAUSTED = "overview_provider_exhausted"
REASON_REPAIR_FAILED = "overview_repair_failed"

# Frozen §4.2 allowlist (include only when path exists on turn context).
KPI_CLAIM_PATHS: tuple[str, ...] = (
    "results.trade_summary.trade_count",
    "results.trade_summary.expectancy_r",
    "results.trade_summary.win_rate",
    "results.trade_summary.profit_factor",
    "results.trade_summary.max_drawdown_r",
    "results.trade_summary.total_r",
    "results.best_grid_result.stop_loss_ticks",
    "results.best_grid_result.take_profit_ticks",
    "results.best_grid_result.trade_count",
)

_KPI_POSITIVE_CUES: tuple[str, ...] = (
    "kpi",
    "kpis",
    "key metrics",
    "key metric",
    "performance metrics",
    "run kpis",
)

_RUN_OVERVIEW_POSITIVE_CUES: tuple[str, ...] = (
    "run summary",
    "run overview",
    "run highlights",
    "run recap",
    "summarize this run",
    "summarise this run",
    "summary of this run",
    "a summary of this run",
    "highlights of this run",
)

_NEGATIVE_CUES: tuple[str, ...] = (
    "validation",
    "wfa",
    "walk-forward",
    "walk forward",
    "oos",
    "out of sample",
    "out-of-sample",
    "bootstrap",
    "monte carlo",
    "monte-carlo",
    "grid",
    "stop",
    "target",
    "sl",
    "tp",
    "stop loss",
    "take profit",
    "ranking",
    "time",
    "hour",
    "bucket",
    "clock",
    "session segment",
)


def _normalize_message(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _alias_matches(alias: str, normalized: str) -> bool:
    """Boundary-anchored alias match (single- and multi-word).

    Edges are alnum / underscore / hyphen so cues do not false-match inside
    compounds (``runtime`` / ``runaway`` / ``passkey metrics``) or hyphenated
    words (``non-stop`` must not hit negative cue ``stop``; ``off-grid`` must
    not hit ``grid``). Hyphenated cues such as ``walk-forward`` still match as
    whole aliases.
    """
    if not alias:
        return False
    return (
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])",
            normalized,
        )
        is not None
    )


def match_overview_intent(message: str) -> str | None:
    """Return ``kpi_summary`` / ``run_overview`` or ``None`` when vetoed/unmatched.

    Order: negative-cue veto first, then first positive overview match
    (``kpi_summary`` before ``run_overview``).
    """
    if not isinstance(message, str) or not message.strip():
        return None
    normalized = _normalize_message(message)
    if any(_alias_matches(cue, normalized) for cue in _NEGATIVE_CUES):
        return None
    if any(_alias_matches(cue, normalized) for cue in _KPI_POSITIVE_CUES):
        return OVERVIEW_INTENT_KPI
    if any(_alias_matches(cue, normalized) for cue in _RUN_OVERVIEW_POSITIVE_CUES):
        return OVERVIEW_INTENT_RUN
    return None


def classify_recovery_reason(exc: BaseException, *, repaired: bool) -> str:
    """Map a failed model/provider attempt to a DI recovery reason code."""
    if repaired:
        return REASON_REPAIR_FAILED
    # Prefer typed provider faults over string sniffing of unrelated auditor text.
    if isinstance(exc, LLMProviderError):
        return REASON_PROVIDER_EXHAUSTED
    text = str(exc)
    lowered = text.lower()
    if "uncited numerical" in lowered:
        return REASON_DIGIT_MISS
    if "missing from the evidence packet" in lowered or "claim path" in lowered:
        return REASON_PATH_MISS
    # Other LLMEvidenceError classes (schema/soften/etc.) are not provider exhaust.
    return REASON_PATH_MISS


def present_kpi_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen KPI claim paths that exist on the turn evidence context."""
    if not isinstance(evidence_context, Mapping):
        return ()
    return tuple(path for path in KPI_CLAIM_PATHS if _path_exists(evidence_context, path))


def build_prompt_path_catalog(
    evidence_context: Mapping[str, Any],
    *,
    overview_intent: str | None = None,
) -> dict[str, Any]:
    """Build the DI-2 first-pass path catalog for the Results Q&A user payload.

    Always includes ``existing_paths`` from the turn context. When an overview
    intent is matched, also includes ``kpi_allowlist`` (present paths only) and
    an overview instruction — never a must-cite set for non-overview asks.
    """
    existing = list(collect_existing_paths(evidence_context))
    catalog: dict[str, Any] = {
        "existing_paths": existing,
        "instruction": (
            "Cite claim.path values only from existing_paths. "
            "Do not invent nested keys (e.g. results.instrument, "
            "results.validation.trade_count). "
            "Narrate fractional rates with % or percent/pct/Prozent."
        ),
    }
    if overview_intent in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
        kpi_paths = list(present_kpi_allowlist(evidence_context))
        catalog["overview_intent"] = overview_intent
        catalog["kpi_allowlist"] = kpi_paths
        catalog["overview_instruction"] = (
            "This is an overview/KPI ask. Prefer citing a subset of "
            "kpi_allowlist paths that exist. Do not substitute validation, "
            "instrument, or other specialist paths for the KPI overview."
        )
        # Optional must-cite hint: cite these or a subset (never invent outside).
        catalog["preferred_claim_paths"] = kpi_paths
    return catalog


def collect_existing_paths(
    root: Mapping[str, Any],
    *,
    max_paths: int = 240,
) -> tuple[str, ...]:
    """Collect dotted paths present on the turn evidence context (bounded).

    Prefers KPI allowlist paths and the ``results.*`` subtree so repair catalogs
    are not starved by large ``provenance`` / ``assumptions`` maps.
    """
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> bool:
        if path in seen or len(paths) >= max_paths:
            return len(paths) < max_paths
        seen.add(path)
        paths.append(path)
        return len(paths) < max_paths

    def walk(node: Any, prefix: str) -> None:
        if len(paths) >= max_paths:
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not isinstance(key, str) or not key:
                    continue
                path = f"{prefix}.{key}" if prefix else key
                if not add(path):
                    return
                walk(value, path)
            return
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for index, value in enumerate(node):
                path = f"{prefix}.{index}" if prefix else str(index)
                if not add(path):
                    return
                walk(value, path)

    if isinstance(root, Mapping):
        for path in KPI_CLAIM_PATHS:
            if _path_exists(root, path):
                add(path)
        results = root.get("results")
        if isinstance(results, Mapping):
            walk(results, "results")
        for key, value in root.items():
            if key == "results":
                continue
            if not isinstance(key, str) or not key:
                continue
            path = key
            if not add(path):
                break
            walk(value, path)
    else:
        walk(root, "")
    return tuple(paths)


def _digit_free_lines(lines: Sequence[Any]) -> tuple[str, ...]:
    """Return stripped lines that introduce no digit tokens (auditor-safe)."""
    out: list[str] = []
    for line in lines:
        if not isinstance(line, str):
            continue
        text = line.strip()
        if text and not any(ch.isdigit() for ch in text):
            out.append(text)
    return tuple(out)


def _format_scalar_for_claim(path: str, value: Any) -> str | None:
    """Return claim text for an allowlisted scalar, or None when not narratable."""
    if value is None or isinstance(value, bool):
        return None
    if path.endswith("win_rate"):
        if not isinstance(value, (int, float)):
            return None
        percent = float(value) * 100.0
        if percent.is_integer():
            percent_text = str(int(percent))
        else:
            percent_text = format(percent, ".12g")
        return f"Win rate is {percent_text}%."
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            display: Any = int(value)
        else:
            display = value
        leaf = path.rsplit(".", 1)[-1]
        return f"{leaf} is {display}."
    if isinstance(value, str) and value.strip():
        # KPI allowlist is numeric; skip non-numeric strings.
        return None
    return None


def build_deterministic_kpi_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    intent: str,
    recovery_reason: str | None = None,
):
    """Build an auditor-safe KPI/overview reply from the frozen path allowlist."""
    # Local import avoids a circular import at module load (results_qa → overview).
    from thesistester.assistant.results_qa import ResultsQAReply

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    for path in KPI_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        text = _format_scalar_for_claim(path, value)
        if text is None:
            continue
        claims.append(EvidenceClaim(text=text, path=path, value=value))
        summary_parts.append(text.rstrip("."))

    limitation_honesty = _digit_free_lines(packet.limitations)
    if not claims:
        # §4.2: when trade_summary is absent, prefer digit-free packet limitations.
        summary = (
            limitation_honesty[0]
            if limitation_honesty
            else "Baseline trade summary KPIs are not present in this evidence packet."
        )
        followups = (
            "Ask whether validation diagnostics exist on this run.",
            "Ask about best grid result if a grid was recorded.",
        )
        caveat_seed = (
            "No trade_summary KPI scalars were available for a deterministic overview.",
            *limitation_honesty[1:2],
        )
    else:
        label = "Key metrics" if intent == OVERVIEW_INTENT_KPI else "Run summary"
        summary = f"{label}: " + "; ".join(summary_parts) + "."
        followups = (
            "Ask about validation or walk-forward diagnostics if present.",
            "Ask about best stop and take profit ranking next.",
        )
        # §4.1 run_overview: one-line honesty from digit-free limitations when present.
        caveat_seed = (
            "These figures describe the recorded historical sample, not a forecast.",
            *limitation_honesty[:1],
        )

    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=grounded,
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_structured_remediation_reply(
    packet: EvidencePacket,
    *,
    failure_class: str,
    recovery_reason: str | None = None,
):
    """§5.3 digit-free structured remediation (RQ-shaped; no traceback)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    class_text = {
        "missing_path": (
            "I could not ground that answer because a cited evidence path was missing."
        ),
        "uncited_number": (
            "I could not ground that answer because a numerical claim was not cited "
            "to packet evidence."
        ),
        "provider_tls": (
            "I could not reach the model provider securely, so I could not complete "
            "a grounded narration for that ask."
        ),
        "provider": (
            "I could not complete a grounded narration because the model provider failed."
        ),
        "ungrounded": (
            "I could not produce a grounded answer for that ask from the evidence packet."
        ),
    }.get(
        failure_class,
        "I could not produce a grounded answer for that ask from the evidence packet.",
    )

    summary = class_text
    # Prefer empty claims for remediation (§5.3). Limitation bodies often contain
    # digits and must not be pasted into summary/followups without citation.
    claims: tuple[EvidenceClaim, ...] = ()

    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask a specialist question about validation or ranking if that was your topic.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        ("No ungrounded draft was shown; ask again with a narrower evidence question.",),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=claims,
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=claims,
        followups=followups,
        recovery_reason=recovery_reason,
    )


def failure_class_from_exception(exc: BaseException) -> str:
    """Map exception / typed provider fault to a §5.3 remediation failure class."""
    if isinstance(exc, LLMProviderError):
        text = str(exc).lower()
        if "tls" in text or "ssl" in text:
            return "provider_tls"
        return "provider"
    text = str(exc).lower()
    if "uncited numerical" in text:
        return "uncited_number"
    if "missing from the evidence packet" in text or "claim path" in text:
        return "missing_path"
    if "tls" in text or "ssl" in text:
        return "provider_tls"
    if "openai" in text or "provider" in text or "timed out" in text:
        return "provider"
    return "ungrounded"
