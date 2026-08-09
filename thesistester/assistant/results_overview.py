"""DI/RI Discuss matching, path-catalog hints, and deterministic builders.

Fail-closed numbers stay in ``llm_explainer``. This module selects frozen
overview + specialist slices (RI-1: ``grid_ranking``; RI-2: ``time_ranking``;
RI-3: ``validation_wfa``), builds DI-2 first-pass path catalogs, and builds
auditor-safe replies when the LLM path fails.
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
INTENT_GRID_RANKING = "grid_ranking"
INTENT_TIME_RANKING = "time_ranking"
INTENT_VALIDATION_WFA = "validation_wfa"
INTENT_MIXED_ASK = "mixed_ask"

_LANDED_SPECIALIST_INTENTS = frozenset(
    {INTENT_GRID_RANKING, INTENT_TIME_RANKING, INTENT_VALIDATION_WFA}
)

REASON_PATH_MISS = "overview_path_miss"
REASON_DIGIT_MISS = "overview_digit_miss"
REASON_PROVIDER_EXHAUSTED = "overview_provider_exhausted"
REASON_REPAIR_FAILED = "overview_repair_failed"
REASON_MISSING_GRID = "grid_missing_evidence"
REASON_MISSING_TIME = "time_missing_evidence"
REASON_MISSING_VALIDATION = "validation_missing_evidence"
REASON_MIXED_ASK = "mixed_ask_narrow"
REASON_GRID_FALLBACK = "grid_deterministic_fallback"
REASON_TIME_FALLBACK = "time_deterministic_fallback"
REASON_VALIDATION_FALLBACK = "validation_deterministic_fallback"

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

# RI-1 landed specialist cues (sunsets matching DI negatives for grid topics).
# Bare short tokens ``sl``/``tp``/``stop``/``target`` require collocates (§4.1);
# alone they remain overview-refusing residual (DX veto ≠ unmatched).
_GRID_RANKING_POSITIVE_CUES: tuple[str, ...] = (
    "best sl",
    "best tp",
    "best sl/tp",
    "best stop",
    "best target",
    "stop loss",
    "take profit",
    "sl/tp",
    "grid ranking",
    "grid rank",
    "grid",
)

# Short tokens match ``grid_ranking`` only with best/pair/grid/ranking collocates.
_GRID_BARE_TOKEN_CUES: tuple[str, ...] = ("sl", "tp", "stop", "target")
_GRID_BARE_TOKEN_COLLOCATES: tuple[str, ...] = (
    "best",
    "pair",
    "grid",
    "ranking",
    "rank",
)

# ``ranking`` / ``ranking metric`` only count as grid when a grid collocate is present.
_GRID_RANKING_CONTEXT_CUES: tuple[str, ...] = ("ranking", "ranking metric")
_GRID_CONTEXT_COLLOCATES: tuple[str, ...] = (
    "grid",
    "sl",
    "tp",
    "stop",
    "target",
    "sl/tp",
    "stop loss",
    "take profit",
    "best sl",
    "best tp",
)

# RI-3 landed specialist cues (sunsets DI validation/WFA/OOS/bootstrap negatives).
# ``permutation`` requires validation-sense collocates; ``otf validation`` is RI-5.
_VALIDATION_WFA_POSITIVE_CUES: tuple[str, ...] = (
    "validation",
    "wfa",
    "walk-forward",
    "walk forward",
    "oos",
    "out of sample",
    "out-of-sample",
    "bootstrap",
)
_VALIDATION_PERMUTATION_COLLOCATES: tuple[str, ...] = (
    "bootstrap",
    "oos",
    "wfa",
    "walk-forward",
    "walk forward",
    "validation",
    "test",
)

# RI-2 landed specialist cues (sunsets DI time/hour/bucket/clock/session negatives).
_TIME_RANKING_POSITIVE_CUES: tuple[str, ...] = (
    "best time",
    "best entry",
    "entry time",
    "time bucket",
    "session segment",
    "hour bucket",
)
# Bare DI time negatives become owned after RI-2 sunset (boundary-safe vs runtime).
_TIME_BARE_TOKEN_CUES: tuple[str, ...] = ("time", "hour", "bucket", "clock")
# ``ranking`` / ``ranking metric`` count as time when a time collocate is present.
_TIME_RANKING_CONTEXT_CUES: tuple[str, ...] = ("ranking", "ranking metric")
_TIME_CONTEXT_COLLOCATES: tuple[str, ...] = (
    "time",
    "hour",
    "bucket",
    "clock",
    "session",
    "entry",
    "best time",
    "best entry",
    "time bucket",
    "hour bucket",
    "session segment",
)

# DI §4.1 negatives not yet owned by a landed specialist builder (RI residual veto).
# RI-2 sunsets time/hour/bucket/clock/session segment into ``time_ranking``.
# RI-3 sunsets validation/wfa/oos/bootstrap into ``validation_wfa``.
# ``otf validation`` stays residual until RI-5 (must not be owned by bare ``validation``).
_RESIDUAL_NEGATIVE_CUES: tuple[str, ...] = (
    "monte carlo",
    "monte-carlo",
    "otf validation",
    # Bare ranking without grid/time collocates stays residual (never overview).
    "ranking",
)

# Frozen RI §4.2 allowlist (include only when path exists on turn context).
GRID_CLAIM_PATHS: tuple[str, ...] = (
    "results.projections.grid_rankings.metric",
    "results.projections.grid_rankings.metric_source_path",
    "results.projections.grid_rankings.min_trades",
    "results.projections.grid_rankings.candidate_count",
    "results.projections.grid_rankings.eligible_count",
    "results.projections.grid_rankings.selection_scope",
    "results.projections.grid_rankings.oos_status",
    "results.projections.grid_rankings.best.stop_loss_ticks",
    "results.projections.grid_rankings.best.take_profit_ticks",
    "results.projections.grid_rankings.best.trade_count",
    "results.projections.grid_rankings.best.metric_value",
    "results.best_grid_result.stop_loss_ticks",
    "results.best_grid_result.take_profit_ticks",
    "results.best_grid_result.trade_count",
    "assumptions.costs_exposure.commission_per_side",
    "assumptions.costs_exposure.slippage_ticks",
    "assumptions.grid.ranking_metric",
)

_GRID_SL_PATHS: tuple[str, ...] = (
    "results.projections.grid_rankings.best.stop_loss_ticks",
    "results.best_grid_result.stop_loss_ticks",
)
_GRID_TP_PATHS: tuple[str, ...] = (
    "results.projections.grid_rankings.best.take_profit_ticks",
    "results.best_grid_result.take_profit_ticks",
)

# Frozen RI §4.3 allowlist (include only when path exists on turn context).
TIME_CLAIM_PATHS: tuple[str, ...] = (
    "results.projections.time_rankings.bucket_col",
    "results.projections.time_rankings.metric",
    "results.projections.time_rankings.min_trades",
    "results.projections.time_rankings.selection_scope",
    "results.projections.time_rankings.best.bucket",
    "results.projections.time_rankings.best.trade_count",
    "results.projections.time_rankings.best.metric_value",
    "results.projections.time_rankings.best.sample_warning",
)

# Frozen RI §4.4 allowlist (include only when path exists on turn context).
VALIDATION_CLAIM_PATHS: tuple[str, ...] = (
    "results.walk_forward_summary.fold_count",
    "results.walk_forward_summary.valid_fold_count",
    "results.walk_forward_summary.median_test_expectancy_r",
    "results.walk_forward_summary.stitched_oos_total_r",
    "results.walk_forward_summary.stitched_oos_status",
    "results.walk_forward_summary.status",
    "results.validation_summary.bootstrap.ci_lower",
    "results.validation_summary.bootstrap.ci_upper",
    "results.validation_summary.bootstrap.probability_positive",
    "results.validation_summary.grid_overfit.risk_level",
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


def _any_cue_matches(cues: Sequence[str], normalized: str) -> bool:
    return any(_alias_matches(cue, normalized) for cue in cues)


def _grid_ranking_matches(normalized: str) -> bool:
    if _any_cue_matches(_GRID_RANKING_POSITIVE_CUES, normalized):
        return True
    if _any_cue_matches(_GRID_RANKING_CONTEXT_CUES, normalized) and _any_cue_matches(
        _GRID_CONTEXT_COLLOCATES, normalized
    ):
        return True
    # Bare sl/tp/stop/target only with best/pair/grid/ranking collocates (§4.1).
    if _any_cue_matches(_GRID_BARE_TOKEN_CUES, normalized) and _any_cue_matches(
        _GRID_BARE_TOKEN_COLLOCATES, normalized
    ):
        return True
    return False


def _validation_wfa_matches(normalized: str) -> bool:
    # Non-``validation`` cues always land validation_wfa (even beside OTF talk).
    other_cues = tuple(cue for cue in _VALIDATION_WFA_POSITIVE_CUES if cue != "validation")
    if _any_cue_matches(other_cues, normalized):
        return True
    # ``permutation`` only in validation sense (§4.1).
    if _alias_matches("permutation", normalized) and _any_cue_matches(
        _VALIDATION_PERMUTATION_COLLOCATES, normalized
    ):
        return True
    # Bare ``validation`` — but not the RI-5 phrase ``otf validation``.
    if _alias_matches("validation", normalized) and not _alias_matches(
        "otf validation", normalized
    ):
        return True
    return False


def _time_ranking_matches(normalized: str) -> bool:
    if _any_cue_matches(_TIME_RANKING_POSITIVE_CUES, normalized):
        return True
    # Bare DI time negatives owned after RI-2 sunset (boundary vs runtime/stopwatch).
    if _any_cue_matches(_TIME_BARE_TOKEN_CUES, normalized):
        return True
    if _any_cue_matches(_TIME_RANKING_CONTEXT_CUES, normalized) and _any_cue_matches(
        _TIME_CONTEXT_COLLOCATES, normalized
    ):
        return True
    return False


def _hard_residual_negative_matches(normalized: str) -> bool:
    """Residual cues that block landed specialists (MC/ranking/otf validation)."""
    if _any_cue_matches(
        tuple(cue for cue in _RESIDUAL_NEGATIVE_CUES if cue != "ranking"),
        normalized,
    ):
        return True
    # Bare ranking without grid or time collocates remains residual (never overview).
    if _alias_matches("ranking", normalized) and not (
        _any_cue_matches(_GRID_CONTEXT_COLLOCATES, normalized)
        or _any_cue_matches(_TIME_CONTEXT_COLLOCATES, normalized)
    ):
        return True
    return False


def _soft_bare_grid_token_residual(normalized: str) -> bool:
    """Bare sl/tp/stop/target without collocates — overview-refuse only.

    Must not veto a lone landed ``validation_wfa`` match (e.g. ``tp and oos``).
    """
    if (
        _any_cue_matches(_GRID_BARE_TOKEN_CUES, normalized)
        and not _any_cue_matches(_GRID_BARE_TOKEN_COLLOCATES, normalized)
        and not _any_cue_matches(_GRID_RANKING_POSITIVE_CUES, normalized)
    ):
        return True
    return False


def _residual_negative_matches(normalized: str) -> bool:
    """True when a not-yet-owned DI negative cue is present.

    Bare ``ranking`` is residual only when grid-context ranking did not already
    classify the ask as ``grid_ranking`` (caller combines with grid match).
    Bare ``sl``/``tp``/``stop``/``target`` without collocates stay residual so
    overview/DX cannot topic-swap (collocated forms are owned by grid_ranking).
    """
    return _hard_residual_negative_matches(normalized) or _soft_bare_grid_token_residual(normalized)


def has_overview_negative_cue(message: str) -> bool:
    """Return True when overview matching must be refused (RI §4.1.1).

    ``overview_refused = landed specialist OR mixed_ask OR residual DI negative``.
    Duplex (DX) uses this to distinguish veto from unmatched — do not copy cue
    tables into ``voice/``.
    """
    if not isinstance(message, str) or not message.strip():
        return False
    intent = match_discuss_intent(message)
    if intent in _LANDED_SPECIALIST_INTENTS or intent == INTENT_MIXED_ASK:
        return True
    if intent is None:
        return _residual_negative_matches(_normalize_message(message))
    return False


def match_discuss_intent(message: str) -> str | None:
    """Return one Discuss intent id, ``mixed_ask``, or ``None`` (RI §4.1).

    Multi-eval (no first-match short-circuit): evaluate landed cue tables
    independently, then apply residual veto / mixed-ask rules.
    Landed intents in RI-2+: ``grid_ranking``, ``time_ranking``,
    ``validation_wfa``, ``kpi_summary``, ``run_overview``.
    """
    if not isinstance(message, str) or not message.strip():
        return None
    normalized = _normalize_message(message)
    grid = _grid_ranking_matches(normalized)
    time_ask = _time_ranking_matches(normalized)
    validation = _validation_wfa_matches(normalized)
    kpi = _any_cue_matches(_KPI_POSITIVE_CUES, normalized)
    run = _any_cue_matches(_RUN_OVERVIEW_POSITIVE_CUES, normalized)

    specialists: list[str] = []
    if grid:
        specialists.append(INTENT_GRID_RANKING)
    if time_ask:
        specialists.append(INTENT_TIME_RANKING)
    if validation:
        specialists.append(INTENT_VALIDATION_WFA)

    hard_residual = _hard_residual_negative_matches(normalized)
    soft_residual = _soft_bare_grid_token_residual(normalized)

    # §4.1 step 3: hard residual (MC/bare-ranking/otf) blocks specialists → None.
    if hard_residual:
        return None

    overview_count = (1 if kpi else 0) + (1 if run else 0)
    if soft_residual:
        # Soft bare-grid residual refuses overview/DX topic-swap, but must not
        # veto a lone landed specialist ("tp and oos" / "validation of my stop").
        if len(specialists) >= 2 or (len(specialists) == 1 and overview_count >= 1):
            return INTENT_MIXED_ASK
        if len(specialists) == 1:
            return specialists[0]
        return None

    if len(specialists) + overview_count >= 2:
        return INTENT_MIXED_ASK
    if len(specialists) == 1:
        return specialists[0]
    if kpi:
        return OVERVIEW_INTENT_KPI
    if run:
        return OVERVIEW_INTENT_RUN
    return None


def match_overview_intent(message: str) -> str | None:
    """Return ``kpi_summary`` / ``run_overview`` or ``None`` when vetoed/unmatched.

    Compatibility wrapper over ``match_discuss_intent`` for DI/DX callers.
    """
    intent = match_discuss_intent(message)
    if intent in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
        return intent
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


def present_grid_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen grid claim paths that exist on the turn evidence context."""
    if not isinstance(evidence_context, Mapping):
        return ()
    return tuple(path for path in GRID_CLAIM_PATHS if _path_exists(evidence_context, path))


def present_validation_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen validation/WFA claim paths with narratable scalars only.

    JSON-null / non-scalar leaves are omitted (same discipline as
    ``has_validation_wfa_evidence``) so path catalogs do not prefer dead leaves.
    """
    if not isinstance(evidence_context, Mapping):
        return ()
    out: list[str] = []
    for path in VALIDATION_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        if _format_scalar_for_claim(path, value) is None:
            continue
        out.append(path)
    return tuple(out)


def _narratable_grid_scalar(evidence_context: Mapping[str, Any], path: str) -> bool:
    """True when *path* exists and formats to a claimable scalar (nulls fail)."""
    if not _path_exists(evidence_context, path):
        return False
    value = _path_get(evidence_context, path)
    return _format_scalar_for_claim(path, value) is not None


def has_grid_ranking_evidence(evidence_context: Mapping[str, Any]) -> bool:
    """True when at least one narratable SL **and** one narratable TP exist.

    JSON-null / non-scalar leaves do not count — §4.2 requires a numeric best
    SL/TP pair (or missing-grid limitation), not an SL-only answer.
    """
    if not isinstance(evidence_context, Mapping):
        return False
    has_sl = any(_narratable_grid_scalar(evidence_context, path) for path in _GRID_SL_PATHS)
    has_tp = any(_narratable_grid_scalar(evidence_context, path) for path in _GRID_TP_PATHS)
    return has_sl and has_tp


def has_validation_wfa_evidence(evidence_context: Mapping[str, Any]) -> bool:
    """True when at least one narratable §4.4 WFA/validation leaf exists."""
    if not isinstance(evidence_context, Mapping):
        return False
    for path in VALIDATION_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        if _format_scalar_for_claim(path, value) is not None:
            return True
    return False


def _time_grouped_summary_from_context(
    evidence_context: Mapping[str, Any],
) -> Mapping[str, Any] | Sequence[Mapping[str, Any]] | None:
    results = evidence_context.get("results")
    if not isinstance(results, Mapping):
        return None
    summary = results.get("time_grouped_summary")
    if isinstance(summary, Mapping) and summary:
        return summary
    if isinstance(summary, Sequence) and not isinstance(summary, (str, bytes)) and summary:
        return summary
    return None


def _coerce_hour_bucket_label(value: Any) -> Any:
    """Normalize integer hour buckets to ``HH:00`` clock labels for grounding.

    String labels (``09:30``, ``rth_morning``) pass through. Hour-like ints/floats
    in ``0..23`` become zero-padded clock strings so RQ clock-span grounding and
    claim narration stay aligned.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or not value.is_integer()):
            return value
        hour = int(value)
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
        return value
    return value


def _normalize_time_rankings_buckets(projected: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with hour-like ``bucket`` leaves coerced to clocks."""
    out = dict(projected)
    best = out.get("best")
    if isinstance(best, Mapping):
        best_copy = dict(best)
        if "bucket" in best_copy:
            best_copy["bucket"] = _coerce_hour_bucket_label(best_copy["bucket"])
        out["best"] = best_copy
    rows = out.get("rows")
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        normalized_rows: list[Any] = []
        for row in rows:
            if isinstance(row, Mapping):
                row_copy = dict(row)
                if "bucket" in row_copy:
                    row_copy["bucket"] = _coerce_hour_bucket_label(row_copy["bucket"])
                normalized_rows.append(row_copy)
            else:
                normalized_rows.append(row)
        out["rows"] = normalized_rows
    by_rank = out.get("by_rank")
    if isinstance(by_rank, Mapping):
        normalized_rank: dict[str, Any] = {}
        for key, row in by_rank.items():
            if isinstance(row, Mapping):
                row_copy = dict(row)
                if "bucket" in row_copy:
                    row_copy["bucket"] = _coerce_hour_bucket_label(row_copy["bucket"])
                normalized_rank[str(key)] = row_copy
            else:
                normalized_rank[str(key)] = row
        out["by_rank"] = normalized_rank
    return out


def _time_bucket_display_label(value: Any) -> str | None:
    """Return a narratable time-bucket label, or None when empty/non-narratable."""
    coerced = _coerce_hour_bucket_label(value)
    if isinstance(coerced, bool) or coerced is None:
        return None
    if isinstance(coerced, str):
        text = coerced.strip()
        return text or None
    if isinstance(coerced, (int, float)):
        if isinstance(coerced, float) and coerced != coerced:
            return None
        if isinstance(coerced, float) and coerced.is_integer():
            return str(int(coerced))
        return format(coerced, ".12g") if isinstance(coerced, float) else str(coerced)
    return None


def _ensure_time_rankings_context(
    evidence_context: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return a context that includes ``results.projections.time_rankings`` when possible.

    Prefers an existing projection with a narratable ``best.bucket``. When the
    projection is absent or incomplete (null/empty best), projects from
    ``results.time_grouped_summary`` via the RQ helper (no TIME.analyze).
    Integer hour buckets are normalized to ``HH:00`` labels for RQ grounding.
    """
    if not isinstance(evidence_context, Mapping):
        return {}

    def _with_projection(projected: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(evidence_context)
        results = dict(merged.get("results") or {})
        projections = dict(results.get("projections") or {})
        projections["time_rankings"] = _normalize_time_rankings_buckets(projected)
        results["projections"] = projections
        merged["results"] = results
        return merged

    def _best_bucket_narratable(ctx: Mapping[str, Any]) -> bool:
        path = "results.projections.time_rankings.best.bucket"
        if not _path_exists(ctx, path):
            return False
        return _format_scalar_for_claim(path, _path_get(ctx, path)) is not None

    existing: Mapping[str, Any] | None = None
    if _path_exists(evidence_context, "results.projections.time_rankings"):
        raw = _path_get(evidence_context, "results.projections.time_rankings")
        if isinstance(raw, Mapping):
            existing = raw

    normalized_existing: dict[str, Any] | None = None
    if existing is not None:
        normalized_existing = _with_projection(existing)
        if _best_bucket_narratable(normalized_existing):
            return normalized_existing

    summary = _time_grouped_summary_from_context(evidence_context)
    if summary is None:
        return normalized_existing if normalized_existing is not None else evidence_context
    try:
        from thesistester.assistant.results_projections import project_time_rankings

        projected = project_time_rankings(summary)
    except Exception:
        return normalized_existing if normalized_existing is not None else evidence_context
    if not isinstance(projected, Mapping) or not projected:
        return normalized_existing if normalized_existing is not None else evidence_context
    # Empty best → still attach projection meta so allowlist/catalog stay honest.
    return _with_projection(projected)


def present_time_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen time-ranking claim paths with narratable scalars only."""
    if not isinstance(evidence_context, Mapping):
        return ()
    working = _ensure_time_rankings_context(evidence_context)
    out: list[str] = []
    for path in TIME_CLAIM_PATHS:
        if not _path_exists(working, path):
            continue
        value = _path_get(working, path)
        if _format_scalar_for_claim(path, value) is None:
            continue
        out.append(path)
    return tuple(out)


def has_time_ranking_evidence(evidence_context: Mapping[str, Any]) -> bool:
    """True when a narratable best time bucket exists (§4.3).

    Meta-only projections without ``best.bucket`` do not count — that is a
    missing-time limitation, not a clock invention opportunity.
    """
    if not isinstance(evidence_context, Mapping):
        return False
    working = _ensure_time_rankings_context(evidence_context)
    path = "results.projections.time_rankings.best.bucket"
    if not _path_exists(working, path):
        return False
    return _format_scalar_for_claim(path, _path_get(working, path)) is not None


def build_prompt_path_catalog(
    evidence_context: Mapping[str, Any],
    *,
    overview_intent: str | None = None,
    discuss_intent: str | None = None,
) -> dict[str, Any]:
    """Build the DI-2 / RI first-pass path catalog for the Results Q&A user payload.

    Always includes ``existing_paths`` from the turn context. Overview asks get
    ``kpi_allowlist``; specialist asks get their frozen ``preferred_claim_paths``.
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
    intent = discuss_intent if discuss_intent is not None else overview_intent
    if intent in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
        kpi_paths = list(present_kpi_allowlist(evidence_context))
        catalog["overview_intent"] = intent
        catalog["kpi_allowlist"] = kpi_paths
        catalog["overview_instruction"] = (
            "This is an overview/KPI ask. Prefer citing a subset of "
            "kpi_allowlist paths that exist. Do not substitute validation, "
            "instrument, or other specialist paths for the KPI overview."
        )
        # Optional must-cite hint: cite these or a subset (never invent outside).
        catalog["preferred_claim_paths"] = kpi_paths
    elif intent == INTENT_GRID_RANKING:
        grid_paths = list(present_grid_allowlist(evidence_context))
        catalog["discuss_intent"] = INTENT_GRID_RANKING
        catalog["grid_allowlist"] = grid_paths
        catalog["specialist_instruction"] = (
            "This is a best SL/TP / grid-ranking ask. Prefer citing a subset of "
            "grid_allowlist / preferred_claim_paths. Cite the ranking metric, "
            "selection_scope, and oos_status when present. Do not invent ranks "
            "or choose a different metric. Do not answer with trade_summary KPIs."
        )
        catalog["preferred_claim_paths"] = grid_paths
    elif intent == INTENT_VALIDATION_WFA:
        validation_paths = list(present_validation_allowlist(evidence_context))
        catalog["discuss_intent"] = INTENT_VALIDATION_WFA
        catalog["validation_allowlist"] = validation_paths
        catalog["specialist_instruction"] = (
            "This is a validation / walk-forward / OOS ask. Prefer citing a "
            "subset of validation_allowlist / preferred_claim_paths. Do not "
            "substitute results.trade_summary.* KPIs as OOS proof. Do not "
            "soften missing_oos / failed_oos caveats."
        )
        catalog["preferred_claim_paths"] = validation_paths
    elif intent == INTENT_TIME_RANKING:
        # Ensure projected paths are listed when only time_grouped_summary exists.
        working = _ensure_time_rankings_context(evidence_context)
        time_paths = list(present_time_allowlist(working))
        catalog["discuss_intent"] = INTENT_TIME_RANKING
        catalog["time_allowlist"] = time_paths
        catalog["specialist_instruction"] = (
            "This is a best-entry-time / session-bucket ask. Prefer citing a "
            "subset of time_allowlist / preferred_claim_paths. Cite bucket, "
            "metric, selection_scope, and sample_warning when present. Do not "
            "invent clocks or buckets. Do not answer with trade_summary KPIs."
        )
        catalog["preferred_claim_paths"] = time_paths
        # Prefer the working context's existing_paths when we projected locally.
        if working is not evidence_context:
            catalog["existing_paths"] = list(collect_existing_paths(working))
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


# DI-3: strictly digit-free overlay glosses keyed by full claim paths
# (leaf-only keys would mis-gloss results.best_grid_result.trade_count).
_OVERLAY_GLOSS_BY_PATH: tuple[tuple[str, str], ...] = (
    (
        "results.trade_summary.expectancy_r",
        "Expectancy R is mean net R on the recorded sample, not a forecast.",
    ),
    (
        "results.trade_summary.win_rate",
        "Win rate is the share of winning trades in the recorded sample, not a forward-looking edge.",
    ),
    (
        "results.trade_summary.trade_count",
        "Trade count is the recorded sample size for this run, not proof of deployable edge.",
    ),
    (
        "results.trade_summary.profit_factor",
        "Profit factor summarizes historical wins versus losses on the recorded sample only.",
    ),
    (
        "results.trade_summary.max_drawdown_r",
        "Max drawdown R describes historical equity drawdown on the recorded sample, not future risk bounds.",
    ),
    (
        "results.trade_summary.total_r",
        "Total R is the sum of realized R multiples on the recorded sample, not a prediction.",
    ),
    (
        "results.best_grid_result.trade_count",
        "Best-grid trade count is the in-sample cell sample size when present, not proof of deployable edge.",
    ),
    (
        "results.best_grid_result.stop_loss_ticks",
        "Best-grid stop ticks reflect in-sample grid selection when present, not out-of-sample confirmation.",
    ),
    (
        "results.best_grid_result.take_profit_ticks",
        "Best-grid take-profit ticks reflect in-sample grid selection when present, not out-of-sample confirmation.",
    ),
)

_OVERLAY_ALWAYS = "These figures are research diagnostics, not trading advice."

_OVERLAY_NEXT_STEP = (
    "If you care about robustness, ask whether walk-forward or validation "
    "diagnostics are present on this packet."
)

_OVERVIEW_FOLLOWUP_BANK: tuple[str, ...] = (
    "Ask whether walk-forward or validation diagnostics are present on this packet.",
    "Ask about best stop and take profit ranking if a grid was recorded.",
)

# When OOS/WFA is already known missing, do not coach the user to re-ask presence.
_OVERVIEW_FOLLOWUP_BANK_OOS_ABSENT: tuple[str, ...] = (
    "Ask about best stop and take profit ranking if a grid was recorded.",
    "Ask which evidence paths remain available on this packet.",
)

_MISSING_KPI_OVERLAY = "Baseline trade summary KPIs were not available to interpret for this ask."


def _packet_caveat_codes(packet: EvidencePacket) -> set[str]:
    return {str(getattr(item, "code", "") or "") for item in getattr(packet, "caveats", ()) or ()}


def _is_diagnostic_honesty_line(text: str) -> bool:
    """True for diagnostic-only honesty lines (packet or overlay-authored)."""
    lowered = text.lower()
    return "diagnostic" in lowered and ("trading advice" in lowered or "proof of edge" in lowered)


def _packet_signals_oos_absent(packet: EvidencePacket) -> bool:
    """True when packet already states WFA/OOS evidence is missing or failed."""
    codes = _packet_caveat_codes(packet)
    if "missing_oos" in codes or "failed_oos" in codes:
        return True
    for line in getattr(packet, "limitations", ()) or ():
        if not isinstance(line, str):
            continue
        lowered = line.lower()
        # Phrase markers + boundary-anchored ``oos`` (avoid ``boost`` / ``loose``).
        mentions_oos = (
            any(
                marker in lowered
                for marker in (
                    "walk-forward",
                    "walk forward",
                    "out-of-sample",
                    "out of sample",
                )
            )
            or re.search(r"(?<![a-z0-9])oos(?![a-z0-9])", lowered) is not None
        )
        absent = any(
            marker in lowered
            for marker in (
                "not present",
                "missing",
                "absent",
                "unavailable",
                "not available",
                "failed",
            )
        )
        if mentions_oos and absent:
            return True
    return False


def overview_followup_bank(packet: EvidencePacket | None = None) -> tuple[str, ...]:
    """Digit-free follow-up bank for overview / KPI replies (DI-3).

    Packet-aware: when OOS/WFA is already known absent, do not suggest asking
    whether those diagnostics are present (§6.2 no optimistic fill).
    """
    if packet is not None and _packet_signals_oos_absent(packet):
        return _OVERVIEW_FOLLOWUP_BANK_OOS_ABSENT
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
    lines: list[str] = []
    cited_paths = {
        claim.path.strip()
        for claim in claims
        if isinstance(getattr(claim, "path", None), str) and claim.path.strip()
    }
    for path, gloss in _OVERLAY_GLOSS_BY_PATH:
        if path in cited_paths:
            lines.append(gloss)
        if len(lines) >= 3:
            break
    if not cited_paths:
        lines.append(_MISSING_KPI_OVERLAY)
    else:
        # Only when figures were cited — never "these figures" on empty KPI path.
        # Skip when packet already carries diagnostic_only (near-duplicate).
        if "diagnostic_only" not in _packet_caveat_codes(packet):
            if _OVERLAY_ALWAYS not in lines:
                lines.append(_OVERLAY_ALWAYS)
    # Do not coach "ask whether WFA is present" when the packet already says no.
    if not _packet_signals_oos_absent(packet) and _OVERLAY_NEXT_STEP not in lines:
        lines.append(_OVERLAY_NEXT_STEP)

    audited: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if _ungrounded_number_tokens(text, allowed=set()):
            raise ValueError(f"Expert overlay line is not digit-free: {text!r}")
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
    existing_diagnostic = any(
        _is_diagnostic_honesty_line(item) for item in merged_caveats if isinstance(item, str)
    )
    for line in overlay:
        if line in seen:
            continue
        # Near-dedupe diagnostic honesty vs mandatory diagnostic_only message.
        if existing_diagnostic and _is_diagnostic_honesty_line(line):
            continue
        merged_caveats.append(line)
        seen.add(line)
    followups = overview_followup_bank(packet)
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
    # RI-2: sample_warning is an explicit allowlisted boolean honesty claim.
    if path.endswith("sample_warning") and isinstance(value, bool):
        return (
            "Sample warning is true (thin bucket sample)." if value else "Sample warning is false."
        )
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
        if path.endswith("stop_loss_ticks"):
            return f"Best stop-loss ticks is {display}."
        if path.endswith("take_profit_ticks"):
            return f"Best take-profit ticks is {display}."
        if path.endswith("metric_value"):
            return f"Ranked metric value is {display}."
        if path.endswith("min_trades"):
            return f"Minimum trades floor is {display}."
        if path.endswith("median_test_expectancy_r"):
            return f"Median OOS test expectancy R is {display}."
        if path.endswith("stitched_oos_total_r"):
            return f"Stitched OOS total R is {display}."
        # ``valid_fold_count`` also endswith ``fold_count`` — check the longer suffix first.
        if path.endswith("valid_fold_count"):
            return f"Valid walk-forward fold count is {display}."
        if path.endswith("fold_count"):
            return f"Walk-forward fold count is {display}."
        if path.endswith("ci_lower"):
            return f"Bootstrap CI lower is {display}."
        if path.endswith("ci_upper"):
            return f"Bootstrap CI upper is {display}."
        if path.endswith("probability_positive"):
            return f"Bootstrap probability mean R is positive is {display}."
        if path.endswith("trade_count"):
            return f"Trade count is {display}."
        # Integer hour buckets must not fall through to generic "bucket is N."
        if path.endswith("best.bucket"):
            label = _time_bucket_display_label(value)
            if label:
                return f"Best time bucket is {label}."
            return None
        return f"{leaf} is {display}."
    if isinstance(value, str) and value.strip():
        text = value.strip()
        # Grid / validation / time honesty labels are narratable strings.
        if path.endswith("selection_scope"):
            return f"Selection scope is {text}."
        if path.endswith("oos_status") or path.endswith("stitched_oos_status"):
            return f"OOS status is {text}."
        if path.endswith("metric") or path.endswith("ranking_metric"):
            return f"Ranking metric is {text}."
        if path.endswith("metric_source_path"):
            return f"Ranking metric source path is {text}."
        if path.endswith("risk_level"):
            return f"Grid overfit risk level is {text}."
        if path.endswith("walk_forward_summary.status"):
            return f"Walk-forward status is {text}."
        if path.endswith("bucket_col"):
            return f"Time bucket column is {text}."
        if path.endswith("best.bucket"):
            return f"Best time bucket is {text}."
        # KPI allowlist is numeric; skip other non-numeric strings.
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


def build_missing_grid_limitation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MISSING_GRID,
):
    """Digit-free missing-grid limitation (RI-1 short-circuit; no invented ticks)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer best stop-loss / take-profit ranking because grid ranking "
        "evidence is not present on this run."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether a grid search was recorded for this run.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No best-grid SL/TP figures were invented for this ask.",
            "Grid rankings are in-sample selection diagnostics, not out-of-sample proof.",
        ),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_mixed_ask_remediation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MIXED_ASK,
):
    """Narrow-ask remediation for mixed intents until RI-8 composition lands."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "That ask mixes more than one results topic. Ask about one topic at a time "
        "(for example key metrics, best stop and take profit, best entry time, "
        "or walk-forward)."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask about best stop and take profit ranking if a grid was recorded.",
        "Ask about the best entry time or session bucket if time analysis was recorded.",
        "Ask whether walk-forward or validation diagnostics are present on this packet.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        ("No partial KPI or specialist slice was shown for a mixed ask.",),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_missing_validation_limitation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MISSING_VALIDATION,
):
    """Digit-free missing-validation/WFA limitation (RI-3 short-circuit)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer validation or walk-forward questions because those "
        "diagnostics are not present on this run."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether a validation or walk-forward battery was recorded for this run.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No out-of-sample or validation figures were invented for this ask.",
            "In-sample trade summary KPIs are not a substitute for WFA or OOS evidence.",
        ),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_missing_time_limitation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MISSING_TIME,
):
    """Digit-free missing-time limitation (RI-2 short-circuit; no invented clocks)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer best entry time or session-bucket ranking because time "
        "ranking evidence is not present on this run."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether a time or session analysis was recorded for this run.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No entry-time or session-bucket figures were invented for this ask.",
            "Time rankings are in-sample bucket diagnostics, not out-of-sample proof.",
        ),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_deterministic_time_ranking_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
):
    """Build an auditor-safe best-entry-time reply from the frozen §4.3 allowlist."""
    from thesistester.assistant.results_qa import ResultsQAReply

    working = _ensure_time_rankings_context(evidence_context)
    if not has_time_ranking_evidence(working):
        return build_missing_time_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_TIME,
        )

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    for path in TIME_CLAIM_PATHS:
        if not _path_exists(working, path):
            continue
        value = _path_get(working, path)
        text = _format_scalar_for_claim(path, value)
        if text is None:
            continue
        claims.append(EvidenceClaim(text=text, path=path, value=value))
        summary_parts.append(text.rstrip("."))

    claim_paths = {claim.path for claim in claims}
    if not claims or "results.projections.time_rankings.best.bucket" not in claim_paths:
        return build_missing_time_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_TIME,
        )

    summary = "Best entry time / session bucket: " + "; ".join(summary_parts) + "."
    caveat_seed = (
        "Time rankings reflect in-sample bucket selection on the recorded sample, not a forecast.",
        "Do not treat the selected bucket as out-of-sample confirmation unless OOS/WFA evidence says so.",
    )
    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask about best stop and take profit ranking if a grid was recorded.",
        "Ask for the key metrics or a summary of this run.",
    )
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


def build_deterministic_validation_wfa_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
):
    """Build an auditor-safe validation/WFA reply from the frozen §4.4 allowlist."""
    from thesistester.assistant.results_qa import ResultsQAReply

    if not has_validation_wfa_evidence(evidence_context):
        return build_missing_validation_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_VALIDATION,
        )

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    for path in VALIDATION_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        text = _format_scalar_for_claim(path, value)
        if text is None:
            continue
        # Hard rule: never emit trade_summary paths from this builder.
        if "trade_summary" in path:
            continue
        claims.append(EvidenceClaim(text=text, path=path, value=value))
        summary_parts.append(text.rstrip("."))

    if not claims:
        return build_missing_validation_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_VALIDATION,
        )

    summary = "Validation / walk-forward: " + "; ".join(summary_parts) + "."
    caveat_seed = (
        "These validation and walk-forward figures are research diagnostics, not proof of deployable edge.",
        "Do not treat in-sample trade summary KPIs as out-of-sample confirmation.",
    )
    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask about best stop and take profit ranking if a grid was recorded.",
    )
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


def build_deterministic_grid_ranking_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
):
    """Build an auditor-safe best SL/TP reply from the frozen grid allowlist."""
    from thesistester.assistant.results_qa import ResultsQAReply

    if not has_grid_ranking_evidence(evidence_context):
        return build_missing_grid_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_GRID,
        )

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    claimed_paths: set[str] = set()
    # Prefer projection best SL/TP paths when narratable; else recorded best.
    preferred_order = list(GRID_CLAIM_PATHS)
    for path in preferred_order:
        if not _path_exists(evidence_context, path):
            continue
        # Skip recorded best leaf only when the matching projection leaf was cited.
        if path.startswith("results.best_grid_result."):
            leaf = path.rsplit(".", 1)[-1]
            projection_path = f"results.projections.grid_rankings.best.{leaf}"
            if projection_path in claimed_paths:
                continue
        value = _path_get(evidence_context, path)
        text = _format_scalar_for_claim(path, value)
        if text is None:
            continue
        claims.append(EvidenceClaim(text=text, path=path, value=value))
        claimed_paths.add(path)
        summary_parts.append(text.rstrip("."))

    claim_paths = {claim.path for claim in claims}
    has_sl_claim = bool(claim_paths.intersection(_GRID_SL_PATHS))
    has_tp_claim = bool(claim_paths.intersection(_GRID_TP_PATHS))
    if not claims or not (has_sl_claim and has_tp_claim):
        return build_missing_grid_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_GRID,
        )

    summary = "Best SL/TP grid ranking: " + "; ".join(summary_parts) + "."
    caveat_seed = (
        "Grid rankings reflect in-sample selection on the recorded grid, not a forecast.",
        "Do not treat the selected cell as out-of-sample confirmation unless OOS/WFA evidence says so.",
    )
    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask whether walk-forward or validation diagnostics are present on this packet.",
        "Ask for the key metrics or a summary of this run.",
    )
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
