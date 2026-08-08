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
    _ungrounded_number_tokens,
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

# Walk these ``results.*`` keys before fat arrays (e.g. time_grouped_summary).
_RESULTS_PRIORITY_KEYS: tuple[str, ...] = (
    "trade_summary",
    "best_grid_result",
    "projections",
    "validation_summary",
    "walk_forward_summary",
    "walk_forward_warnings",
    "otf_validation_summary",
)

# Honesty / framing paths reserved before provenance and fat tables.
_TOP_LEVEL_PRIORITY_KEYS: tuple[str, ...] = (
    "limitations",
    "caveats",
    "warnings",
    "assumptions",
)

# Large row tables: keep the root + a shallow sample so they cannot exhaust
# the catalog budget ahead of projections / honesty paths.
_FAT_RESULTS_KEYS: frozenset[str] = frozenset({"time_grouped_summary"})
_FAT_ARRAY_ROW_CAP = 8

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

    Priority order so DI-2 / repair catalogs stay useful under fat packets:

    1. frozen KPI allowlist leaves
    2. specialist ``results.*`` keys (trade_summary, projections, validation/WFA)
    3. top-level honesty paths (limitations / caveats / warnings / assumptions)
       — before remaining fat ``results.*``
    4. remaining ``results.*`` (shallow sample for fat row tables)
    5. remaining top-level maps (provenance, …)
    """
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> bool:
        if path in seen or len(paths) >= max_paths:
            return len(paths) < max_paths
        seen.add(path)
        paths.append(path)
        return len(paths) < max_paths

    def walk(node: Any, prefix: str, *, sequence_cap: int | None = None) -> None:
        if len(paths) >= max_paths:
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not isinstance(key, str) or not key:
                    continue
                path = f"{prefix}.{key}" if prefix else key
                if not add(path):
                    return
                child_cap = _FAT_ARRAY_ROW_CAP if key in _FAT_RESULTS_KEYS else sequence_cap
                walk(value, path, sequence_cap=child_cap)
            return
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            items = list(node)
            if sequence_cap is not None:
                items = items[:sequence_cap]
            for index, value in enumerate(items):
                path = f"{prefix}.{index}" if prefix else str(index)
                if not add(path):
                    return
                walk(value, path, sequence_cap=None)

    def walk_mapping_keys(
        mapping: Mapping[str, Any],
        *,
        prefix: str,
        keys: Sequence[str],
        skip: set[str] | None = None,
    ) -> None:
        skipped = skip or set()
        for key in keys:
            if key in skipped or key not in mapping:
                continue
            value = mapping[key]
            path = f"{prefix}.{key}" if prefix else key
            if not add(path):
                return
            child_cap = _FAT_ARRAY_ROW_CAP if key in _FAT_RESULTS_KEYS else None
            walk(value, path, sequence_cap=child_cap)

    if isinstance(root, Mapping):
        for path in KPI_CLAIM_PATHS:
            if _path_exists(root, path):
                add(path)
        results = root.get("results")
        if isinstance(results, Mapping):
            if not add("results"):
                return tuple(paths)
            # Specialist results first (before honesty + fat tables).
            walk_mapping_keys(results, prefix="results", keys=_RESULTS_PRIORITY_KEYS)
        # Honesty / framing before fat remaining results.* and provenance.
        walk_mapping_keys(root, prefix="", keys=_TOP_LEVEL_PRIORITY_KEYS, skip={"results"})
        if isinstance(results, Mapping):
            for key, value in results.items():
                if not isinstance(key, str) or not key:
                    continue
                if key in _RESULTS_PRIORITY_KEYS:
                    continue
                path = f"results.{key}"
                if not add(path):
                    return tuple(paths)
                child_cap = _FAT_ARRAY_ROW_CAP if key in _FAT_RESULTS_KEYS else None
                walk(value, path, sequence_cap=child_cap)
        for key, value in root.items():
            if key == "results" or key in _TOP_LEVEL_PRIORITY_KEYS:
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


# DI-3: strictly digit-free overlay glosses keyed by cited claim leaf names.
_OVERLAY_GLOSS_BY_LEAF: tuple[tuple[str, str], ...] = (
    (
        "expectancy_r",
        "Expectancy R is mean net R on the recorded sample, not a forecast.",
    ),
    (
        "win_rate",
        "Win rate is the share of winning trades in the recorded sample, not a forward-looking edge.",
    ),
    (
        "trade_count",
        "Trade count is the recorded sample size for this run, not proof of deployable edge.",
    ),
    (
        "profit_factor",
        "Profit factor summarizes historical wins versus losses on the recorded sample only.",
    ),
    (
        "max_drawdown_r",
        "Max drawdown R describes historical equity drawdown on the recorded sample, not future risk bounds.",
    ),
    (
        "total_r",
        "Total R is the sum of realized R multiples on the recorded sample, not a prediction.",
    ),
    (
        "stop_loss_ticks",
        "Best-grid stop ticks reflect in-sample grid selection when present, not out-of-sample confirmation.",
    ),
    (
        "take_profit_ticks",
        "Best-grid take-profit ticks reflect in-sample grid selection when present, not out-of-sample confirmation.",
    ),
)

_OVERLAY_ALWAYS: tuple[str, ...] = (
    "These figures are research diagnostics, not trading advice.",
)

_OVERLAY_NEXT_STEP = (
    "If you care about robustness, ask whether walk-forward or validation "
    "diagnostics are present on this packet."
)

_OVERVIEW_FOLLOWUP_BANK: tuple[str, ...] = (
    "Ask whether walk-forward or validation diagnostics are present on this packet.",
    "Ask about best stop and take profit ranking if a grid was recorded.",
)

_MISSING_KPI_OVERLAY = (
    "Baseline trade summary KPIs were not available to interpret for this ask."
)


def overview_followup_bank() -> tuple[str, ...]:
    """Digit-free follow-up bank for overview / KPI replies (DI-3)."""
    return _OVERVIEW_FOLLOWUP_BANK


def build_expert_overlay(
    packet: EvidencePacket,
    claims: Sequence[EvidenceClaim],
) -> tuple[str, ...]:
    """Return overlay-authored caveat lines that are strictly digit-free.

    Mandatory packet caveats stay on ``merge_mandatory_packet_caveats`` and are
    **not** returned here. Every line must pass
    ``_ungrounded_number_tokens(line, allowed=set()) == []``.
    """
    del packet  # reserved for future packet-shaped honesty without new digits
    lines: list[str] = []
    cited_leaves = {
        claim.path.rsplit(".", 1)[-1]
        for claim in claims
        if isinstance(getattr(claim, "path", None), str) and claim.path.strip()
    }
    for leaf, gloss in _OVERLAY_GLOSS_BY_LEAF:
        if leaf in cited_leaves:
            lines.append(gloss)
        if len(lines) >= 3:
            break
    if not cited_leaves:
        lines.append(_MISSING_KPI_OVERLAY)
    for always in _OVERLAY_ALWAYS:
        if always not in lines:
            lines.append(always)
    if _OVERLAY_NEXT_STEP not in lines:
        lines.append(_OVERLAY_NEXT_STEP)

    audited: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if _ungrounded_number_tokens(text, allowed=set()):
            raise ValueError(
                f"Expert overlay line is not digit-free: {text!r}"
            )
        audited.append(text)
    return tuple(audited)


def apply_expert_overlay(
    packet: EvidencePacket,
    *,
    summary: str,
    caveats: Sequence[str],
    claims: Sequence[EvidenceClaim],
    recovery_reason: str | None = None,
):
    """Append DI-3 overlay lines and overview followups; re-run the auditor."""
    from thesistester.assistant.results_qa import ResultsQAReply

    overlay = build_expert_overlay(packet, claims)
    # Keep mandatory/LLM caveats first; append only new overlay-authored lines.
    merged_caveats = list(caveats)
    seen = {item.strip() for item in merged_caveats if isinstance(item, str)}
    for line in overlay:
        if line not in seen:
            merged_caveats.append(line)
            seen.add(line)
    followups = overview_followup_bank()
    caveat_tuple = tuple(merged_caveats)
    claim_tuple = tuple(claims)
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveat_tuple,
        claims=claim_tuple,
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveat_tuple,
        claims=claim_tuple,
        followups=followups,
        recovery_reason=recovery_reason,
    )


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
        caveat_seed = (
            "No trade_summary KPI scalars were available for a deterministic overview.",
            *limitation_honesty[1:2],
        )
    else:
        label = "Key metrics" if intent == OVERVIEW_INTENT_KPI else "Run summary"
        summary = f"{label}: " + "; ".join(summary_parts) + "."
        # §4.1 run_overview: one-line honesty from digit-free limitations when present.
        caveat_seed = (
            "These figures describe the recorded historical sample, not a forecast.",
            *limitation_honesty[:1],
        )

    grounded = tuple(claims)
    # Wire order (DI-3): claims/summary → mandatory caveats → overlay → auditor.
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
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
