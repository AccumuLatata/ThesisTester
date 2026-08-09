"""DI/RI Discuss matching, path-catalog hints, and deterministic builders.

Fail-closed numbers stay in ``llm_explainer``. This module selects frozen
overview + specialist slices (RI-1: ``grid_ranking``; RI-2: ``time_ranking``;
RI-3: ``validation_wfa``; RI-4: ``single_metric``; RI-5: ``robustness_tier2``;
RI-6: ``assumptions_costs``), builds DI-2 first-pass path catalogs, builds
auditor-safe replies when the LLM path fails, and attaches DI-3/RI-7 digit-free
meaning overlays after mandatory caveats.
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
INTENT_ROBUSTNESS_TIER2 = "robustness_tier2"
INTENT_ASSUMPTIONS_COSTS = "assumptions_costs"
INTENT_SINGLE_METRIC = "single_metric"
INTENT_MIXED_ASK = "mixed_ask"

_LANDED_SPECIALIST_INTENTS = frozenset(
    {
        INTENT_GRID_RANKING,
        INTENT_TIME_RANKING,
        INTENT_VALIDATION_WFA,
        INTENT_ROBUSTNESS_TIER2,
        INTENT_ASSUMPTIONS_COSTS,
    }
)
# Intents that refuse overview/DX KPI envelopes (specialists + single-metric).
_OVERVIEW_REFUSING_INTENTS = frozenset(
    {*_LANDED_SPECIALIST_INTENTS, INTENT_SINGLE_METRIC, INTENT_MIXED_ASK}
)

REASON_PATH_MISS = "overview_path_miss"
REASON_DIGIT_MISS = "overview_digit_miss"
REASON_PROVIDER_EXHAUSTED = "overview_provider_exhausted"
REASON_REPAIR_FAILED = "overview_repair_failed"
REASON_MISSING_GRID = "grid_missing_evidence"
REASON_MISSING_TIME = "time_missing_evidence"
REASON_MISSING_VALIDATION = "validation_missing_evidence"
REASON_MISSING_ROBUSTNESS = "robustness_missing_evidence"
REASON_MISSING_ASSUMPTIONS = "assumptions_missing_evidence"
REASON_MISSING_METRIC = "metric_missing_leaf"
REASON_MIXED_ASK = "mixed_ask_narrow"
REASON_MIXED_COMPOSE = "mixed_ask_compose"
REASON_GRID_FALLBACK = "grid_deterministic_fallback"
REASON_TIME_FALLBACK = "time_deterministic_fallback"
REASON_VALIDATION_FALLBACK = "validation_deterministic_fallback"
REASON_ROBUSTNESS_FALLBACK = "robustness_deterministic_fallback"
REASON_ASSUMPTIONS_FALLBACK = "assumptions_deterministic_fallback"
REASON_METRIC_FALLBACK = "metric_deterministic_fallback"

# §4.1 composition / summary order (sole-intent tie-break + RI-8 compose order).
_COMPOSE_PRIORITY: tuple[str, ...] = (
    INTENT_GRID_RANKING,
    INTENT_TIME_RANKING,
    INTENT_VALIDATION_WFA,
    INTENT_ROBUSTNESS_TIER2,
    INTENT_ASSUMPTIONS_COSTS,
    INTENT_SINGLE_METRIC,
    OVERVIEW_INTENT_KPI,
    OVERVIEW_INTENT_RUN,
)
MIXED_COMPOSE_CAP = 3

# Frozen RI §4.5 noun → path map (longer phrases first within each row).
_SINGLE_METRIC_NOUN_PATHS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("win rate",), "results.trade_summary.win_rate"),
    (("expectancy_r", "expectancy"), "results.trade_summary.expectancy_r"),
    (("profit factor",), "results.trade_summary.profit_factor"),
    (("max drawdown", "drawdown"), "results.trade_summary.max_drawdown_r"),
    (("total r",), "results.trade_summary.total_r"),
    (
        ("number of trades", "trade count", "sample size"),
        "results.trade_summary.trade_count",
    ),
    (("average r", "avg r"), "results.trade_summary.avg_r"),
    (("median r",), "results.trade_summary.median_r"),
    (("sharpe",), "results.trade_summary.sharpe_like_r"),
    (("sortino",), "results.trade_summary.sortino_like_r"),
    (("ulcer",), "results.trade_summary.ulcer_index_r"),
    (("recovery factor",), "results.trade_summary.recovery_factor"),
)

# Value / define collocates required for single_metric (§4.5).
# ``how many`` alone is not a general collocate — only the explicit form
# ``how many trades`` below (avoids ``how many sharpe`` false matches).
_SINGLE_METRIC_VALUE_COLLOCATES: tuple[str, ...] = (
    "what is",
    "what's",
    "whats",
    "show",
    "give me",
)

# Explicit metric question forms that do not need a separate value collocate.
_SINGLE_METRIC_EXPLICIT_FORMS: tuple[tuple[str, str], ...] = (
    ("how many trades", "results.trade_summary.trade_count"),
)

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
    "otf_validation",
    "monte_carlo_summary",
    "overfitting_summary",
    "sensitivity_summary",
    "noise_summary",
    "portfolio_summary",
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
# English temporal idioms must not fire bare ``time`` (RI-4 metric asks).
_TIME_BARE_IDIOM_PHRASES: tuple[str, ...] = (
    "over time",
    "through time",
    "across time",
)
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
# RI-5 sunsets monte carlo / otf validation into ``robustness_tier2``.
_RESIDUAL_NEGATIVE_CUES: tuple[str, ...] = (
    # Bare ranking without grid/time collocates stays residual (never overview).
    "ranking",
)

# RI-5 landed specialist cues (sunsets DI MC / OTF residual negatives).
_ROBUSTNESS_TIER2_POSITIVE_CUES: tuple[str, ...] = (
    "monte carlo",
    "monte-carlo",
    "overfitting",
    "overfit",
    "sensitivity",
    "noise test",
    "noise summary",
    "portfolio summary",
    "otf validation",
    "otf-validation",
)

# Near-miss tokens that must not launder into single_metric / overview when the
# full robustness cue is absent (``monte carlo`` / ``overfitting`` still own).
_ROBUSTNESS_NEAR_MISS_TOKENS: tuple[str, ...] = ("monte", "carlo")

# Phrases that must not count as bare RI-3 ``validation``.
_OTF_VALIDATION_PHRASES: tuple[str, ...] = ("otf validation", "otf-validation")

# RI-6 landed specialist cues (run-assumption / costs sense; Help how-to is out of channel).
_ASSUMPTIONS_COSTS_POSITIVE_CUES: tuple[str, ...] = (
    "commission",
    "slippage",
    "exposure policy",
    "intrabar model",
    "costs",
    "assumptions",
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

# Frozen RI §4.6 robustness_tier2 allowlist (presence-first; no deep nested dumps).
ROBUSTNESS_CLAIM_PATHS: tuple[str, ...] = (
    "results.monte_carlo_summary.available",
    "results.monte_carlo_summary.trade_count",
    "results.overfitting_summary.available",
    "results.overfitting_summary.pbo.pbo",
    "results.overfitting_summary.deflated_sharpe.dsr",
    "results.sensitivity_summary.available",
    "results.sensitivity_summary.fragile_parameter_count",
    "results.noise_summary.available",
    "results.noise_summary.replicas.n_completed",
    "results.portfolio_summary.available",
    "results.portfolio_summary.admission.admitted_trade_count",
    "results.portfolio_summary.portfolio_metrics.total_r",
    "results.otf_validation.available",
    "results.otf_validation_summary.status",
    "results.otf_validation_summary.selected_oos_expectancy_r",
    "results.otf_validation_summary.train_fraction",
    "results.otf_validation_summary.oos_fraction",
)

# Frozen RI §4.6 assumptions_costs allowlist (no performance KPIs).
ASSUMPTIONS_CLAIM_PATHS: tuple[str, ...] = (
    "assumptions.costs_exposure.commission_per_side",
    "assumptions.costs_exposure.slippage_ticks",
    "assumptions.costs_exposure.exposure_policy",
    "assumptions.costs_exposure.intrabar_model",
    "assumptions.costs_exposure.stop_loss_ticks",
    "assumptions.costs_exposure.take_profit_ticks",
    "assumptions.entry_window.focus.enabled",
    "assumptions.instrument",
    "assumptions.dataset.dataset_fingerprint",
)


def _normalize_message(text: str) -> str:
    # Map common curly/smart apostrophes so ``what's`` cues still match.
    lowered = (
        text.strip().lower().replace("\u2019", "'").replace("\u2018", "'").replace("\u00b4", "'")
    )
    return " ".join(lowered.split())


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


def _mask_otf_validation_phrases(normalized: str) -> str:
    """Blank OTF phrases so remaining bare ``validation`` can still match WFA."""
    masked = normalized
    for phrase in _OTF_VALIDATION_PHRASES:
        masked = masked.replace(phrase, " ")
    return " ".join(masked.split())


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
    # Bare ``validation`` after masking RI-5 ``otf validation`` / ``otf-validation``
    # so "validation and otf validation" can be mixed_ask (WFA + robustness).
    if _alias_matches("validation", _mask_otf_validation_phrases(normalized)):
        return True
    return False


def _robustness_tier2_matches(normalized: str) -> bool:
    return _any_cue_matches(_ROBUSTNESS_TIER2_POSITIVE_CUES, normalized)


def _assumptions_costs_matches(normalized: str) -> bool:
    return _any_cue_matches(_ASSUMPTIONS_COSTS_POSITIVE_CUES, normalized)


def _robustness_near_miss_matches(normalized: str) -> bool:
    """True for bare ``monte`` / ``carlo`` without a full robustness cue."""
    if _robustness_tier2_matches(normalized):
        return False
    return _any_cue_matches(_ROBUSTNESS_NEAR_MISS_TOKENS, normalized)


def _mask_time_bare_idioms(normalized: str) -> str:
    """Blank temporal idioms so bare ``time`` does not false-fire inside them."""
    masked = normalized
    for phrase in _TIME_BARE_IDIOM_PHRASES:
        masked = masked.replace(phrase, " ")
    return " ".join(masked.split())


def _bare_time_token_matches(normalized: str) -> bool:
    """True when a bare time token hits outside excluded temporal idioms."""
    return _any_cue_matches(_TIME_BARE_TOKEN_CUES, _mask_time_bare_idioms(normalized))


def _strong_time_ranking_matches(normalized: str) -> bool:
    """Multi-word / collocated time asks (not bare token alone)."""
    if _any_cue_matches(_TIME_RANKING_POSITIVE_CUES, normalized):
        return True
    if _any_cue_matches(_TIME_RANKING_CONTEXT_CUES, normalized) and _any_cue_matches(
        _TIME_CONTEXT_COLLOCATES, normalized
    ):
        return True
    return False


def _time_ranking_matches(normalized: str) -> bool:
    if _strong_time_ranking_matches(normalized):
        return True
    # Bare DI time negatives owned after RI-2 sunset (boundary vs runtime/stopwatch).
    # Idioms like ``over time`` are masked so RI-4 metric asks are not hijacked.
    if _bare_time_token_matches(normalized):
        return True
    return False


def _hard_residual_negative_matches(normalized: str) -> bool:
    """Residual cues that block landed specialists (bare ranking / MC near-miss)."""
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
    # Bare ``monte`` / ``carlo`` without full robustness cue — never IS metric.
    if _robustness_near_miss_matches(normalized):
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


def _matched_single_metric_paths(normalized: str) -> list[str]:
    """Return distinct §4.5 paths for value-collocate nouns or explicit forms."""
    paths: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        if path in seen:
            return
        seen.add(path)
        paths.append(path)

    for form, path in _SINGLE_METRIC_EXPLICIT_FORMS:
        if _alias_matches(form, normalized):
            _add(path)
    if _any_cue_matches(_SINGLE_METRIC_VALUE_COLLOCATES, normalized):
        for nouns, path in _SINGLE_METRIC_NOUN_PATHS:
            if _any_cue_matches(nouns, normalized):
                _add(path)
    return paths


def resolve_single_metric_path(message: str) -> str | None:
    """Return the single §4.5 claim path for a lone metric ask, or None.

    Does not apply hard-refuse / residual rules — callers that need the Discuss
    intent should use ``match_discuss_intent`` first.
    """
    if not isinstance(message, str) or not message.strip():
        return None
    paths = _matched_single_metric_paths(_normalize_message(message))
    if len(paths) != 1:
        return None
    return paths[0]


def has_overview_negative_cue(message: str) -> bool:
    """Return True when overview matching must be refused (RI §4.1.1).

    ``overview_refused = landed specialist OR single_metric OR mixed_ask OR
    residual DI negative``. Duplex (DX) uses this to distinguish veto from
    unmatched — do not copy cue tables into ``voice/``.
    """
    if not isinstance(message, str) or not message.strip():
        return False
    intent = match_discuss_intent(message)
    if intent in _OVERVIEW_REFUSING_INTENTS:
        return True
    if intent is None:
        return _residual_negative_matches(_normalize_message(message))
    return False


def _evaluate_discuss_match(message: str) -> dict[str, Any] | None:
    """Evaluate landed cue tables; return match state or None for empty input."""
    if not isinstance(message, str) or not message.strip():
        return None
    normalized = _normalize_message(message)
    grid = _grid_ranking_matches(normalized)
    time_strong = _strong_time_ranking_matches(normalized)
    time_bare_only = _bare_time_token_matches(normalized) and not time_strong
    validation = _validation_wfa_matches(normalized)
    robustness = _robustness_tier2_matches(normalized)
    assumptions = _assumptions_costs_matches(normalized)
    metric_paths = _matched_single_metric_paths(normalized)
    kpi = _any_cue_matches(_KPI_POSITIVE_CUES, normalized)
    run = _any_cue_matches(_RUN_OVERVIEW_POSITIVE_CUES, normalized)

    specialists: list[str] = []
    if grid:
        specialists.append(INTENT_GRID_RANKING)
    if time_strong:
        specialists.append(INTENT_TIME_RANKING)
    if validation:
        specialists.append(INTENT_VALIDATION_WFA)
    if robustness:
        specialists.append(INTENT_ROBUSTNESS_TIER2)
    if assumptions:
        specialists.append(INTENT_ASSUMPTIONS_COSTS)

    hard_residual = _hard_residual_negative_matches(normalized)
    soft_residual = _soft_bare_grid_token_residual(normalized)
    overview_count = (1 if kpi else 0) + (1 if run else 0)

    # Bare time × metric is a composable mixed set (RI-8); never time-alone.
    bare_time_metric_mixed = bool(
        time_bare_only and metric_paths and not specialists and overview_count == 0
    )

    if time_bare_only and not bare_time_metric_mixed:
        specialists.append(INTENT_TIME_RANKING)

    # §4.5 hard-refuse: specialist or residual collocates → never emit single_metric.
    # Exception: bare-time×metric keeps metric paths for composition.
    metric_allowed = (not specialists and not soft_residual) or bare_time_metric_mixed
    if bare_time_metric_mixed:
        specialists.append(INTENT_TIME_RANKING)

    single_metric = metric_allowed and len(metric_paths) == 1
    multi_metric = metric_allowed and len(metric_paths) >= 2

    intents: list[str] = list(specialists)
    if single_metric or multi_metric:
        intents.append(INTENT_SINGLE_METRIC)
    if kpi:
        intents.append(OVERVIEW_INTENT_KPI)
    if run:
        intents.append(OVERVIEW_INTENT_RUN)

    # Stable §4.1 priority order; unique.
    ordered = tuple(intent for intent in _COMPOSE_PRIORITY if intent in intents)
    return {
        "normalized": normalized,
        "hard_residual": hard_residual,
        "soft_residual": soft_residual,
        "specialists": tuple(specialists),
        "metric_paths": tuple(metric_paths),
        "single_metric": single_metric,
        "multi_metric": multi_metric,
        "kpi": kpi,
        "run": run,
        "overview_count": overview_count,
        "bare_time_metric_mixed": bare_time_metric_mixed,
        "intents": ordered,
    }


def list_matched_discuss_intents(message: str) -> tuple[str, ...]:
    """Return priority-ordered matched landed intents for RI-8 composition.

    Empty when unmatched, hard-residual blocked, or soft residual with no
    landed specialist owner. Does not return the ``mixed_ask`` sentinel.
    """
    state = _evaluate_discuss_match(message)
    if state is None or state["hard_residual"]:
        return ()
    if state["soft_residual"] and not state["specialists"] and not state["bare_time_metric_mixed"]:
        return ()
    # state["intents"] already includes metric when bare-time×metric mixed
    # (soft residual must not drop the metric half of that pair).
    return state["intents"]


def list_matched_metric_paths(message: str) -> tuple[str, ...]:
    """Return §4.5 paths matched for composition (empty when metric hard-refused)."""
    state = _evaluate_discuss_match(message)
    if state is None or state["hard_residual"]:
        return ()
    if not (state["single_metric"] or state["multi_metric"] or state["bare_time_metric_mixed"]):
        return ()
    return state["metric_paths"]


def match_discuss_intent(message: str) -> str | None:
    """Return one Discuss intent id, ``mixed_ask``, or ``None`` (RI §4.1).

    Multi-eval (no first-match short-circuit): evaluate landed cue tables
    independently, then apply residual veto / mixed-ask rules.
    Landed intents in RI-6+: ``grid_ranking``, ``time_ranking``,
    ``validation_wfa``, ``robustness_tier2``, ``assumptions_costs``,
    ``single_metric``, ``kpi_summary``, ``run_overview``.
    """
    state = _evaluate_discuss_match(message)
    if state is None:
        return None

    # §4.1 step 3: hard residual (bare ranking) blocks specialists → None.
    # Also hard-refuses single_metric (§4.5) so IS leaves cannot launder residual asks.
    if state["hard_residual"]:
        return None

    specialists = list(state["specialists"])
    overview_count = state["overview_count"]
    soft_residual = state["soft_residual"]
    single_metric = state["single_metric"]
    multi_metric = state["multi_metric"]

    # Bare time × metric → mixed_ask (RI-8 composes time + metric).
    if state["bare_time_metric_mixed"]:
        return INTENT_MIXED_ASK

    if soft_residual:
        # Soft bare-grid residual refuses overview/DX topic-swap, but must not
        # veto a lone landed specialist ("tp and oos" / "validation of my stop").
        if len(specialists) >= 2 or (len(specialists) == 1 and overview_count >= 1):
            return INTENT_MIXED_ASK
        if len(specialists) == 1:
            return specialists[0]
        return None

    metric_count = (1 if single_metric else 0) + (1 if multi_metric else 0)
    if len(specialists) + overview_count + metric_count >= 2:
        return INTENT_MIXED_ASK
    if len(specialists) == 1:
        return specialists[0]
    if multi_metric:
        return INTENT_MIXED_ASK
    if single_metric:
        return INTENT_SINGLE_METRIC
    if state["kpi"]:
        return OVERVIEW_INTENT_KPI
    if state["run"]:
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


def present_robustness_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen §4.6 robustness claim paths with narratable scalars only."""
    if not isinstance(evidence_context, Mapping):
        return ()
    out: list[str] = []
    for path in ROBUSTNESS_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        if _format_scalar_for_claim(path, value) is None:
            continue
        out.append(path)
    return tuple(out)


def present_assumptions_allowlist(evidence_context: Mapping[str, Any]) -> tuple[str, ...]:
    """Return frozen §4.6 assumptions/costs claim paths with narratable scalars only."""
    if not isinstance(evidence_context, Mapping):
        return ()
    out: list[str] = []
    for path in ASSUMPTIONS_CLAIM_PATHS:
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


def _ensure_grid_rankings_context(
    evidence_context: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Attach ephemeral ``results.projections.grid_rankings`` when absent.

    Ensures ``oos_status`` is available for RI-7 OOS-absent coaching even when
    callers pass a bare packet dict without an orchestrator turn context.
    """
    if not isinstance(evidence_context, Mapping):
        return {}
    if _path_exists(evidence_context, "results.projections.grid_rankings"):
        return evidence_context
    try:
        from thesistester.assistant.results_projections import build_ephemeral_results_context

        hydrated = build_ephemeral_results_context(evidence_context)
    except Exception:
        return evidence_context
    grid = ((hydrated.get("results") or {}).get("projections") or {}).get("grid_rankings")
    if not isinstance(grid, Mapping) or not grid:
        return evidence_context
    merged = dict(evidence_context)
    results = dict(merged.get("results") or {})
    projections = dict(results.get("projections") or {})
    projections["grid_rankings"] = dict(grid)
    results["projections"] = projections
    merged["results"] = results
    return merged


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


def has_robustness_tier2_evidence(evidence_context: Mapping[str, Any]) -> bool:
    """True when at least one narratable §4.6 tier-2 robustness leaf exists."""
    if not isinstance(evidence_context, Mapping):
        return False
    for path in ROBUSTNESS_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        if _format_scalar_for_claim(path, value) is not None:
            return True
    return False


def has_assumptions_costs_evidence(evidence_context: Mapping[str, Any]) -> bool:
    """True when at least one narratable §4.6 assumptions/costs leaf exists."""
    if not isinstance(evidence_context, Mapping):
        return False
    for path in ASSUMPTIONS_CLAIM_PATHS:
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


def has_single_metric_evidence(
    evidence_context: Mapping[str, Any],
    path: str,
) -> bool:
    """True when the §4.5 leaf exists and formats to a narratable scalar."""
    if not isinstance(evidence_context, Mapping) or not isinstance(path, str) or not path:
        return False
    if not _path_exists(evidence_context, path):
        return False
    return _format_scalar_for_claim(path, _path_get(evidence_context, path)) is not None


def build_prompt_path_catalog(
    evidence_context: Mapping[str, Any],
    *,
    overview_intent: str | None = None,
    discuss_intent: str | None = None,
    single_metric_path: str | None = None,
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
    elif intent == INTENT_ROBUSTNESS_TIER2:
        robustness_paths = list(present_robustness_allowlist(evidence_context))
        catalog["discuss_intent"] = INTENT_ROBUSTNESS_TIER2
        catalog["robustness_allowlist"] = robustness_paths
        catalog["specialist_instruction"] = (
            "This is a tier-2 robustness ask (Monte Carlo / overfitting / "
            "sensitivity / noise / portfolio / OTF). Cite only paths from "
            "robustness_allowlist / preferred_claim_paths / existing_paths "
            "(presence and frozen scalars only). Do not dump undeclared nested "
            "battery paths (methods.*, parameter arrays). Do not substitute "
            "results.trade_summary.* KPIs."
        )
        catalog["preferred_claim_paths"] = robustness_paths
        # §4.6: undeclared nested dumps must not appear in existing_paths.
        catalog["existing_paths"] = list(robustness_paths)
    elif intent == INTENT_ASSUMPTIONS_COSTS:
        assumptions_paths = list(present_assumptions_allowlist(evidence_context))
        catalog["discuss_intent"] = INTENT_ASSUMPTIONS_COSTS
        catalog["assumptions_allowlist"] = assumptions_paths
        catalog["specialist_instruction"] = (
            "This is a costs / assumptions ask. Cite only paths from "
            "assumptions_allowlist / preferred_claim_paths / existing_paths. "
            "Do not narrate results.trade_summary.* performance KPIs. Configured "
            "stop/take-profit ticks are assumption leaves, not grid best ranks."
        )
        catalog["preferred_claim_paths"] = assumptions_paths
        # §4.6: do not expose performance KPI paths on assumptions asks.
        catalog["existing_paths"] = list(assumptions_paths)
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
    elif intent == INTENT_SINGLE_METRIC:
        metric_paths: list[str] = []
        if (
            isinstance(single_metric_path, str)
            and single_metric_path.strip()
            and has_single_metric_evidence(evidence_context, single_metric_path)
        ):
            metric_paths = [single_metric_path]
        catalog["discuss_intent"] = INTENT_SINGLE_METRIC
        catalog["metric_allowlist"] = metric_paths
        catalog["specialist_instruction"] = (
            "This is a single-metric ask. Cite exactly one preferred_claim_paths "
            "leaf when present. Do not expand into a full KPI overview. Do not "
            "substitute OOS/WFA/validation leaves for in-sample trade_summary "
            "metrics (and never the reverse)."
        )
        catalog["preferred_claim_paths"] = metric_paths
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


# DI-3 / RI-7: strictly digit-free overlay glosses keyed by full claim paths
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
        "results.trade_summary.avg_r",
        "Average R is the mean trade R on the recorded sample, not a forecast.",
    ),
    (
        "results.trade_summary.median_r",
        "Median R is the middle trade R on the recorded sample, not a forecast.",
    ),
    (
        "results.trade_summary.sharpe_like_r",
        "Sharpe-like R is a per-trade dispersion diagnostic on the recorded sample, not annualized Sharpe.",
    ),
    (
        "results.trade_summary.sortino_like_r",
        "Sortino-like R is a downside dispersion diagnostic on the recorded sample, not annualized Sortino.",
    ),
    (
        "results.trade_summary.ulcer_index_r",
        "Ulcer index R summarizes drawdown magnitude on the recorded equity path, not future pain bounds.",
    ),
    (
        "results.trade_summary.recovery_factor",
        "Recovery factor relates total R to drawdown on the recorded sample, not a deploy score.",
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
    (
        "results.projections.grid_rankings.best.stop_loss_ticks",
        "Projected best stop ticks come from in-sample grid ranking, not out-of-sample confirmation.",
    ),
    (
        "results.projections.grid_rankings.best.take_profit_ticks",
        "Projected best take-profit ticks come from in-sample grid ranking, not out-of-sample confirmation.",
    ),
    (
        "results.projections.grid_rankings.best.trade_count",
        "Projected best-cell trade count is an in-sample sample-size signal, not proof of edge.",
    ),
    (
        "results.projections.grid_rankings.selection_scope",
        "Grid selection scope states which sample the ranking used; it is not a live-trading warrant.",
    ),
    (
        "results.projections.grid_rankings.oos_status",
        "Grid OOS status is an honesty signal about out-of-sample support, not a deploy recommendation.",
    ),
    (
        "results.projections.grid_rankings.metric",
        "The grid ranking metric is the frozen selection key for this projection, not a shoppable alternative.",
    ),
    (
        "results.projections.time_rankings.best.bucket",
        "Best time bucket is an in-sample session ranking on the recorded sample, not a clock forecast.",
    ),
    (
        "results.projections.time_rankings.best.trade_count",
        "Best-bucket trade count is an in-sample sample-size signal; treat thin buckets cautiously.",
    ),
    (
        "results.projections.time_rankings.best.sample_warning",
        "Sample warning flags thin time buckets; it is honesty framing, not a trading signal.",
    ),
    (
        "results.projections.time_rankings.selection_scope",
        "Time selection scope states which sample the bucket ranking used; it is not live-session advice.",
    ),
    (
        "results.walk_forward_summary.median_test_expectancy_r",
        "Median OOS test expectancy summarizes walk-forward folds; it is not in-sample expectancy.",
    ),
    (
        "results.walk_forward_summary.fold_count",
        "Walk-forward fold count describes the recorded validation design, not future fold outcomes.",
    ),
    (
        "results.walk_forward_summary.valid_fold_count",
        "Valid fold count is how many walk-forward folds produced usable tests on this packet.",
    ),
    (
        "results.walk_forward_summary.stitched_oos_total_r",
        "Stitched OOS total R aggregates recorded out-of-sample folds; it is not a live equity promise.",
    ),
    (
        "results.validation_summary.bootstrap.probability_positive",
        "Bootstrap probability positive is a resampling diagnostic on the recorded sample, not a guarantee.",
    ),
    (
        "results.validation_summary.grid_overfit.risk_level",
        "Grid overfit risk level is a research diagnostic about selection pressure, not a pass/fail trade gate.",
    ),
    (
        "results.monte_carlo_summary.available",
        "Monte Carlo availability is a battery presence flag, not a deployability proof.",
    ),
    (
        "results.monte_carlo_summary.trade_count",
        "Monte Carlo trade count is the sample size of the reshuffled sequence, not future trade volume.",
    ),
    (
        "results.overfitting_summary.available",
        "Overfitting-summary availability marks whether PBO/DSR diagnostics were recorded.",
    ),
    (
        "results.overfitting_summary.pbo.pbo",
        "PBO is an overfitting diagnostic on the recorded grid, not a live edge score.",
    ),
    (
        "results.sensitivity_summary.fragile_parameter_count",
        "Fragile parameter count summarizes sensitivity diagnostics, not a trading signal.",
    ),
    (
        "results.otf_validation.available",
        "OTF validation availability is presence framing, not walk-forward fold proof.",
    ),
    (
        "results.otf_validation_summary.selected_oos_expectancy_r",
        "Selected OTF OOS expectancy is a one-shot train/test diagnostic, not stitched WFA OOS.",
    ),
    (
        "assumptions.costs_exposure.commission_per_side",
        "Commission per side is an execution-cost assumption for this run, not a live brokerage quote.",
    ),
    (
        "assumptions.costs_exposure.slippage_ticks",
        "Slippage ticks are an assumed fill penalty used in research, not guaranteed live slippage.",
    ),
    (
        "assumptions.costs_exposure.exposure_policy",
        "Exposure policy frames how overlapping positions were modeled, not a portfolio mandate.",
    ),
    (
        "assumptions.costs_exposure.intrabar_model",
        "Intrabar model is an ordering assumption for same-bar exits, not a market microstructure claim.",
    ),
    (
        "assumptions.instrument",
        "Instrument identity labels the researched contract/symbol, not a trade recommendation.",
    ),
)

_OVERLAY_ALWAYS = "These figures are research diagnostics, not trading advice."

_OVERLAY_NEXT_STEP = (
    "If you care about robustness, ask whether walk-forward or validation "
    "diagnostics are present on this packet."
)

_OVERLAY_NEXT_STEP_VALIDATION = (
    "Ask for the key metrics or a summary of this run if you want the in-sample baseline."
)

_OVERLAY_NEXT_STEP_TIME = (
    "Ask about best stop and take profit ranking if a grid was recorded, or ask for key metrics."
)

_OVERLAY_NEXT_STEP_ROBUSTNESS = (
    "Ask for the key metrics or a walk-forward summary if you want the baseline or OOS folds."
)

_OVERLAY_NEXT_STEP_ROBUSTNESS_OOS_ABSENT = (
    "Ask for the key metrics or a summary of this run if you want the in-sample baseline."
)

_OVERLAY_NEXT_STEP_ASSUMPTIONS = (
    "Ask for the key metrics or a summary of this run if you want the recorded performance figures."
)

_OVERLAY_OOS_ABSENT = (
    "Out-of-sample or walk-forward evidence is missing or failed on this packet; "
    "do not invent confirmation."
)

_OVERLAY_SAMPLE_SIZE_QUALITATIVE = (
    "Sample size is cited in the claims; treat thin samples cautiously."
)

_OVERLAY_GLOSS_CAP = 3

# Prefer honesty / scope glosses when the cited-path budget is tight (common
# grid replies cite SL/TP/count before ``oos_status`` in claim-builder order).
_OVERLAY_HONESTY_PATH_SUFFIXES: tuple[str, ...] = (
    "oos_status",
    "stitched_oos_status",
    "selection_scope",
    "sample_warning",
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

# Cited / projected honesty statuses that mean OOS/WFA support is absent.
_OOS_ABSENT_STATUS_VALUES: frozenset[str] = frozenset(
    {
        "missing",
        "failed",
        "absent",
        "not_present",
        "unavailable",
        "not_available",
    }
)

_WFA_PRESENCE_ASK_SNIPPET = "whether walk-forward or validation diagnostics are present"


def _packet_caveat_codes(packet: EvidencePacket) -> set[str]:
    return {str(getattr(item, "code", "") or "") for item in getattr(packet, "caveats", ()) or ()}


def _is_diagnostic_honesty_line(text: str) -> bool:
    """True for diagnostic-only honesty lines (packet or overlay-authored)."""
    lowered = text.lower()
    return "diagnostic" in lowered and ("trading advice" in lowered or "proof of edge" in lowered)


def _normalize_oos_status_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    return text or None


def _claims_signal_oos_absent(claims: Sequence[EvidenceClaim]) -> bool:
    """True when cited ``oos_status`` / ``stitched_oos_status`` is an absent value."""
    for claim in claims:
        path = getattr(claim, "path", None)
        if not isinstance(path, str) or not path.endswith("oos_status"):
            continue
        token = _normalize_oos_status_token(getattr(claim, "value", None))
        if token in _OOS_ABSENT_STATUS_VALUES:
            return True
    return False


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


def _context_signals_oos_absent(evidence_context: Mapping[str, Any] | None) -> bool:
    """True when turn evidence already stores an absent OOS honesty status.

    Covers successful LLM drafts that omit citing ``oos_status`` even though the
    ephemeral projection / walk-forward summary already records missing/failed.
    """
    if not isinstance(evidence_context, Mapping):
        return False
    for path in (
        "results.projections.grid_rankings.oos_status",
        "results.walk_forward_summary.stitched_oos_status",
    ):
        if not _path_exists(evidence_context, path):
            continue
        token = _normalize_oos_status_token(_path_get(evidence_context, path))
        if token in _OOS_ABSENT_STATUS_VALUES:
            return True
    return False


def _oos_evidence_absent(
    packet: EvidencePacket,
    claims: Sequence[EvidenceClaim] | None = None,
    evidence_context: Mapping[str, Any] | None = None,
) -> bool:
    """Packet caveats/limitations, cited status, or turn-evidence status (§5)."""
    if _packet_signals_oos_absent(packet):
        return True
    if claims is not None and _claims_signal_oos_absent(claims):
        return True
    if _context_signals_oos_absent(evidence_context):
        return True
    return False


def _followups_without_wfa_presence_ask(followups: Sequence[str]) -> tuple[str, ...]:
    """Drop WFA/OOS presence-coaching followups when evidence is already absent."""
    out: list[str] = []
    for item in followups:
        if not isinstance(item, str):
            continue
        lowered = item.lower()
        if _WFA_PRESENCE_ASK_SNIPPET in lowered:
            continue
        if "ask whether walk-forward" in lowered or "ask whether walk forward" in lowered:
            continue
        out.append(item)
    return tuple(out)


def overview_followup_bank(packet: EvidencePacket | None = None) -> tuple[str, ...]:
    """Digit-free follow-up bank for overview / KPI replies (DI-3).

    Packet-aware: when OOS/WFA is already known absent, do not suggest asking
    whether those diagnostics are present (§6.2 no optimistic fill).
    """
    if packet is not None and _packet_signals_oos_absent(packet):
        return _OVERVIEW_FOLLOWUP_BANK_OOS_ABSENT
    return _OVERVIEW_FOLLOWUP_BANK


def _overlay_next_step_line(discuss_intent: str | None, *, oos_absent: bool) -> str | None:
    """Return intent-aware next-step coaching, or None when suppressed."""
    if discuss_intent == INTENT_MIXED_ASK:
        # Compose followups already prefer unanswered topics — no next-step line.
        return None
    if discuss_intent == INTENT_VALIDATION_WFA:
        return _OVERLAY_NEXT_STEP_VALIDATION
    if discuss_intent == INTENT_ROBUSTNESS_TIER2:
        if oos_absent:
            return _OVERLAY_NEXT_STEP_ROBUSTNESS_OOS_ABSENT
        return _OVERLAY_NEXT_STEP_ROBUSTNESS
    if discuss_intent == INTENT_ASSUMPTIONS_COSTS:
        return _OVERLAY_NEXT_STEP_ASSUMPTIONS
    if discuss_intent == INTENT_TIME_RANKING:
        return _OVERLAY_NEXT_STEP_TIME
    # Overview / grid / single_metric: WFA-presence coaching unless already absent.
    if oos_absent:
        return None
    return _OVERLAY_NEXT_STEP


def build_expert_overlay(
    packet: EvidencePacket,
    claims: Sequence[EvidenceClaim],
    *,
    discuss_intent: str | None = None,
    evidence_context: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Return overlay-authored caveat lines that are strictly digit-free.

    DI-3 overview + RI-7 specialist / single-metric meaning overlay. Mandatory
    packet caveats stay on ``merge_mandatory_packet_caveats`` and are **not**
    returned here. Every line must pass
    ``_ungrounded_number_tokens(line, allowed=set()) == []``.
    """
    lines: list[str] = []
    cited_paths = {
        claim.path.strip()
        for claim in claims
        if isinstance(getattr(claim, "path", None), str) and claim.path.strip()
    }
    codes = _packet_caveat_codes(packet)
    oos_absent = _oos_evidence_absent(packet, claims, evidence_context)

    honesty_glosses: list[str] = []
    other_glosses: list[str] = []
    for path, gloss in _OVERLAY_GLOSS_BY_PATH:
        if path not in cited_paths:
            continue
        if any(path.endswith(suffix) for suffix in _OVERLAY_HONESTY_PATH_SUFFIXES):
            honesty_glosses.append(gloss)
        else:
            other_glosses.append(gloss)
    for gloss in honesty_glosses + other_glosses:
        lines.append(gloss)
        if len(lines) >= _OVERLAY_GLOSS_CAP:
            break

    # Qualitative sample-size caution when a trade_count leaf was cited (no digits).
    if any(path.endswith("trade_count") for path in cited_paths):
        if _OVERLAY_SAMPLE_SIZE_QUALITATIVE not in lines:
            lines.append(_OVERLAY_SAMPLE_SIZE_QUALITATIVE)

    if oos_absent and _OVERLAY_OOS_ABSENT not in lines:
        lines.append(_OVERLAY_OOS_ABSENT)

    if not cited_paths:
        # Missing-KPI honesty is overview-shaped; specialists use limitation builders.
        if discuss_intent in {None, OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
            lines.append(_MISSING_KPI_OVERLAY)
    else:
        # Only when figures were cited — never "these figures" on empty KPI path.
        # Skip when packet already carries diagnostic_only (near-duplicate).
        if "diagnostic_only" not in codes:
            if _OVERLAY_ALWAYS not in lines:
                lines.append(_OVERLAY_ALWAYS)

    next_step = _overlay_next_step_line(discuss_intent, oos_absent=oos_absent)
    if next_step is not None and next_step not in lines:
        lines.append(next_step)

    audited: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if _ungrounded_number_tokens(text, allowed=set()):
            raise ValueError(f"Expert overlay line is not digit-free: {text!r}")
        audited.append(text)
    return tuple(audited)


# Contract alias (RI-7); same pure digit-free builder as DI-3.
build_meaning_overlay = build_expert_overlay


def apply_expert_overlay(
    packet: EvidencePacket,
    *,
    summary: str,
    caveats: Sequence[str],
    claims: Sequence[EvidenceClaim],
    recovery_reason: str | None = None,
    followups: Sequence[str] | None = None,
    discuss_intent: str | None = None,
    evidence_context: Mapping[str, Any] | None = None,
):
    """Append DI-3/RI-7 overlay lines; re-run the auditor.

    When ``followups`` is omitted, uses the overview followup bank (DI-3).
    Specialist / single-metric builders pass their own digit-free followups;
    WFA-presence asks are stripped when OOS/WFA is already known absent
    (packet caveats/limitations, cited ``oos_status``, or turn-evidence status).
    """
    from thesistester.assistant.results_qa import ResultsQAReply

    overlay = build_expert_overlay(
        packet,
        claims,
        discuss_intent=discuss_intent,
        evidence_context=evidence_context,
    )
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
    oos_absent = _oos_evidence_absent(packet, claims, evidence_context)
    if followups is not None:
        final_followups = tuple(followups)
        if oos_absent:
            filtered = _followups_without_wfa_presence_ask(followups)
            final_followups = filtered or _OVERVIEW_FOLLOWUP_BANK_OOS_ABSENT
    else:
        final_followups = (
            _OVERVIEW_FOLLOWUP_BANK_OOS_ABSENT if oos_absent else _OVERVIEW_FOLLOWUP_BANK
        )
    caveat_tuple = tuple(merged_caveats)
    claim_tuple = tuple(claims)
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveat_tuple,
        claims=claim_tuple,
        followups=final_followups,
    )
    return ResultsQAReply(
        summary=summary,
        caveats=caveat_tuple,
        claims=claim_tuple,
        followups=final_followups,
        recovery_reason=recovery_reason,
    )


def _robustness_available_label(path: str) -> str:
    """Human label for §4.6 ``*.available`` presence claims."""
    if "monte_carlo_summary" in path:
        return "Monte Carlo summary available"
    if "overfitting_summary" in path:
        return "Overfitting summary available"
    if "sensitivity_summary" in path:
        return "Sensitivity summary available"
    if "noise_summary" in path:
        return "Noise summary available"
    if "portfolio_summary" in path:
        return "Portfolio summary available"
    if "otf_validation" in path:
        return "OTF validation available"
    return "Available"


def _format_scalar_for_claim(path: str, value: Any) -> str | None:
    """Return claim text for an allowlisted scalar, or None when not narratable."""
    # RI-2: sample_warning is an explicit allowlisted boolean honesty claim.
    if path.endswith("sample_warning") and isinstance(value, bool):
        return (
            "Sample warning is true (thin bucket sample)." if value else "Sample warning is false."
        )
    # RI-5: battery ``.available`` presence flags are allowlisted booleans only
    # (reject int 0/1 / strings that would otherwise narrate as ``available is 1.``).
    if path.endswith("available"):
        if not isinstance(value, bool):
            return None
        label = _robustness_available_label(path)
        return f"{label} is {'true' if value else 'false'}."
    # RI-6: focus enabled is an allowlisted boolean assumption flag.
    if path.endswith("entry_window.focus.enabled") and isinstance(value, bool):
        return (
            "Entry-window focus enabled is true."
            if value
            else "Entry-window focus enabled is false."
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
        # Configured assumption SL/TP (not grid best ranks).
        if path.startswith("assumptions.costs_exposure.") and path.endswith("stop_loss_ticks"):
            return f"Configured stop-loss ticks is {display}."
        if path.startswith("assumptions.costs_exposure.") and path.endswith("take_profit_ticks"):
            return f"Configured take-profit ticks is {display}."
        if path.endswith("stop_loss_ticks"):
            return f"Best stop-loss ticks is {display}."
        if path.endswith("take_profit_ticks"):
            return f"Best take-profit ticks is {display}."
        if path.endswith("commission_per_side"):
            return f"Commission per side is {display}."
        if path.endswith("slippage_ticks"):
            return f"Slippage ticks is {display}."
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
        if path.endswith("selected_oos_expectancy_r"):
            return f"Selected OTF OOS expectancy R is {display}."
        if path.endswith("monte_carlo_summary.trade_count"):
            return f"Monte Carlo trade count is {display}."
        if path.endswith("pbo.pbo"):
            return f"PBO is {display}."
        if path.endswith("deflated_sharpe.dsr"):
            return f"Deflated Sharpe ratio is {display}."
        if path.endswith("fragile_parameter_count"):
            return f"Fragile parameter count is {display}."
        if path.endswith("replicas.n_completed"):
            return f"Noise replica completed count is {display}."
        if path.endswith("admission.admitted_trade_count"):
            return f"Portfolio admitted trade count is {display}."
        if path.endswith("portfolio_metrics.total_r"):
            return f"Portfolio total R is {display}."
        if path.endswith("train_fraction"):
            return f"OTF train fraction is {display}."
        if path.endswith("oos_fraction"):
            return f"OTF OOS fraction is {display}."
        if path.endswith("trade_count"):
            return f"Trade count is {display}."
        if path.endswith("expectancy_r"):
            return f"Expectancy R is {display}."
        if path.endswith("profit_factor"):
            return f"Profit factor is {display}."
        if path.endswith("max_drawdown_r"):
            return f"Max drawdown R is {display}."
        if path.endswith("total_r"):
            return f"Total R is {display}."
        if path.endswith("avg_r"):
            return f"Average R is {display}."
        if path.endswith("median_r"):
            return f"Median R is {display}."
        if path.endswith("sharpe_like_r"):
            return f"Sharpe-like R is {display}."
        if path.endswith("sortino_like_r"):
            return f"Sortino-like R is {display}."
        if path.endswith("ulcer_index_r"):
            return f"Ulcer index R is {display}."
        if path.endswith("recovery_factor"):
            return f"Recovery factor is {display}."
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
        if path.endswith("otf_validation_summary.status"):
            return f"OTF validation status is {text}."
        if path.endswith("exposure_policy"):
            return f"Exposure policy is {text}."
        if path.endswith("intrabar_model"):
            return f"Intrabar model is {text}."
        if path == "assumptions.instrument" or path.endswith("assumptions.instrument"):
            return f"Instrument is {text}."
        if path.endswith("dataset.dataset_fingerprint"):
            return f"Dataset fingerprint is {text}."
        if path.endswith("bucket_col"):
            return f"Time bucket column is {text}."
        if path.endswith("best.bucket"):
            return f"Best time bucket is {text}."
        # KPI allowlist is numeric; skip other non-numeric strings.
        return None
    return None


def _reply_without_overlay(
    *,
    summary: str,
    caveats: Sequence[str],
    claims: Sequence[EvidenceClaim],
    followups: Sequence[str] = (),
    recovery_reason: str | None = None,
):
    """Return a ResultsQAReply without overlay/auditor (RI-8 compose ingredient)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    return ResultsQAReply(
        summary=summary,
        caveats=tuple(caveats),
        claims=tuple(claims),
        followups=tuple(followups),
        recovery_reason=recovery_reason,
    )


def build_deterministic_kpi_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    intent: str,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
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
    # Wire order (DI-3 / RI-7): claims/summary → mandatory caveats → overlay → auditor.
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        discuss_intent=intent,
        evidence_context=evidence_context,
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
    evidence_context: Mapping[str, Any] | None = None,
):
    """Narrow-ask remediation when mixed intents exceed the compose cap or lack evidence."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "That ask mixes more than one results topic. Ask about one topic at a time "
        "(for example one metric, key metrics, best stop and take profit, best "
        "entry time, or walk-forward)."
    )
    followups_list = [
        "Ask for one metric (for example win rate or expectancy).",
        "Ask for the key metrics or a summary of this run.",
        "Ask about best stop and take profit ranking if a grid was recorded.",
        "Ask about the best entry time or session bucket if time analysis was recorded.",
    ]
    if _oos_evidence_absent(packet, evidence_context=evidence_context):
        followups_list.append("Ask which evidence paths remain available on this packet.")
    else:
        followups_list.append(
            "Ask whether walk-forward or validation diagnostics are present on this packet."
        )
    followups = tuple(followups_list)
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


def _collapse_compose_intents(intents: Sequence[str]) -> tuple[str, ...]:
    """Collapse dual overview intents to one kpi_summary slice (same allowlist)."""
    ordered = tuple(intent for intent in _COMPOSE_PRIORITY if intent in set(intents))
    if OVERVIEW_INTENT_KPI in ordered and OVERVIEW_INTENT_RUN in ordered:
        return tuple(intent for intent in ordered if intent != OVERVIEW_INTENT_RUN)
    return ordered


def _compose_followups_for_intents(
    matched: Sequence[str],
    *,
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Digit-free followups preferring topics not already answered in *matched*."""
    matched_set = set(matched)
    suggestions: list[str] = []
    if INTENT_SINGLE_METRIC not in matched_set and OVERVIEW_INTENT_KPI not in matched_set:
        suggestions.append("Ask for one metric (for example win rate or expectancy).")
    if OVERVIEW_INTENT_KPI not in matched_set and OVERVIEW_INTENT_RUN not in matched_set:
        suggestions.append("Ask for the key metrics or a summary of this run.")
    if INTENT_GRID_RANKING not in matched_set:
        suggestions.append("Ask about best stop and take profit ranking if a grid was recorded.")
    if INTENT_TIME_RANKING not in matched_set:
        suggestions.append(
            "Ask about the best entry time or session bucket if time analysis was recorded."
        )
    if INTENT_VALIDATION_WFA not in matched_set:
        if _oos_evidence_absent(packet, evidence_context=evidence_context):
            suggestions.append("Ask which evidence paths remain available on this packet.")
        else:
            suggestions.append(
                "Ask whether walk-forward or validation diagnostics are present on this packet."
            )
    if INTENT_ROBUSTNESS_TIER2 not in matched_set:
        suggestions.append(
            "Ask about Monte Carlo or other robustness batteries if they were recorded."
        )
    if INTENT_ASSUMPTIONS_COSTS not in matched_set:
        suggestions.append("Ask what costs or exposure assumptions were used on this run.")
    if not suggestions:
        suggestions.append("Ask which evidence paths remain available on this packet.")
    return tuple(suggestions[:3])


def compose_deterministic_replies(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    user_message: str,
    intents: Sequence[str] | None = None,
    recovery_reason: str | None = None,
):
    """Compose grounded replies for a mixed ask (§4.7 / RI-8).

    Builds claims per matched intent allowlist (priority order), concatenates
    summaries, merges/dedupes caveats, applies the meaning overlay once, and
    runs the auditor once. Cap is on **raw** matched intents (≤3); dual overview
    collapses to one KPI slice after the cap check. Every matched intent must
    produce claims (no partial topic-swap). Metric×KPI overlap drops the
    redundant single-metric slice. Multi-metric alone with more than three
    matched leaves → narrow remediation.
    """
    raw_matched = tuple(
        intents if intents is not None else list_matched_discuss_intents(user_message)
    )
    # Cap before dual-overview collapse so four cues cannot sneak through.
    if len(raw_matched) > MIXED_COMPOSE_CAP:
        return build_mixed_ask_remediation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MIXED_ASK,
            evidence_context=evidence_context,
        )
    matched = _collapse_compose_intents(raw_matched)
    metric_paths = list_matched_metric_paths(user_message)
    multi_metric_alone = (
        len(matched) == 1 and matched[0] == INTENT_SINGLE_METRIC and len(metric_paths) >= 2
    )
    if multi_metric_alone and len(metric_paths) > MIXED_COMPOSE_CAP:
        return build_mixed_ask_remediation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MIXED_ASK,
            evidence_context=evidence_context,
        )
    # Dual overview collapses to one slice; still a valid composed answer.
    dual_overview_collapsed = (
        len(matched) == 1
        and matched[0] in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}
        and OVERVIEW_INTENT_KPI in raw_matched
        and OVERVIEW_INTENT_RUN in raw_matched
    )
    if len(matched) < 2 and not multi_metric_alone and not dual_overview_collapsed:
        return build_mixed_ask_remediation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MIXED_ASK,
            evidence_context=evidence_context,
        )

    working = dict(evidence_context) if isinstance(evidence_context, Mapping) else {}
    if INTENT_GRID_RANKING in matched:
        working = dict(_ensure_grid_rankings_context(working))
    if INTENT_TIME_RANKING in matched:
        working = dict(_ensure_time_rankings_context(working))

    # KPI allowlist covers overlapping §4.5 leaves — still build metric paths
    # outside the KPI table (e.g. sharpe_like_r) when overview also matched.
    overview_in_matched = any(
        intent in matched for intent in (OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN)
    )
    kpi_path_set = set(KPI_CLAIM_PATHS)

    summary_parts: list[str] = []
    claims: list[EvidenceClaim] = []
    caveat_lines: list[str] = []
    seen_caveats: set[str] = set()
    seen_claim_paths: set[str] = set()
    answered: list[str] = []

    def _absorb(reply) -> bool:
        if reply is None or not getattr(reply, "claims", ()):
            return False
        new_claims = [claim for claim in reply.claims if claim.path not in seen_claim_paths]
        if not new_claims:
            return False
        text = str(getattr(reply, "summary", "") or "").strip()
        if text:
            summary_parts.append(text)
        for claim in new_claims:
            seen_claim_paths.add(claim.path)
            claims.append(claim)
        for line in getattr(reply, "caveats", ()) or ():
            if not isinstance(line, str):
                continue
            key = line.strip()
            if not key or key in seen_caveats:
                continue
            seen_caveats.add(key)
            caveat_lines.append(key)
        return True

    def _mark(intent_id: str) -> None:
        if intent_id not in answered:
            answered.append(intent_id)

    for intent in matched:
        if intent == INTENT_GRID_RANKING:
            if not has_grid_ranking_evidence(working):
                continue
            if _absorb(
                build_deterministic_grid_ranking_reply(packet, working, apply_overlay=False)
            ):
                _mark(intent)
        elif intent == INTENT_TIME_RANKING:
            if not has_time_ranking_evidence(working):
                continue
            if _absorb(
                build_deterministic_time_ranking_reply(packet, working, apply_overlay=False)
            ):
                _mark(intent)
        elif intent == INTENT_VALIDATION_WFA:
            if not has_validation_wfa_evidence(working):
                continue
            if _absorb(
                build_deterministic_validation_wfa_reply(packet, working, apply_overlay=False)
            ):
                _mark(intent)
        elif intent == INTENT_ROBUSTNESS_TIER2:
            if not has_robustness_tier2_evidence(working):
                continue
            if _absorb(build_deterministic_robustness_reply(packet, working, apply_overlay=False)):
                _mark(intent)
        elif intent == INTENT_ASSUMPTIONS_COSTS:
            if not has_assumptions_costs_evidence(working):
                continue
            if _absorb(build_deterministic_assumptions_reply(packet, working, apply_overlay=False)):
                _mark(intent)
        elif intent == INTENT_SINGLE_METRIC:
            paths = tuple(metric_paths or ())
            if overview_in_matched:
                paths = tuple(path for path in paths if path not in kpi_path_set)
                if not paths:
                    # Fully covered by KPI allowlist; count as answered.
                    _mark(intent)
                    continue
            if not paths:
                continue
            for path in paths:
                if not has_single_metric_evidence(working, path):
                    continue
                if _absorb(
                    build_deterministic_single_metric_reply(
                        packet, working, path=path, apply_overlay=False
                    )
                ):
                    _mark(intent)
        elif intent in {OVERVIEW_INTENT_KPI, OVERVIEW_INTENT_RUN}:
            if _absorb(
                build_deterministic_kpi_reply(
                    packet,
                    working,
                    intent=intent,
                    apply_overlay=False,
                )
            ):
                _mark(intent)

    # No partial topic-swap: every matched intent must contribute claims
    # (single_metric may be marked answered when fully covered by KPI).
    required = list(matched)
    if not claims or any(intent not in answered for intent in required):
        return build_mixed_ask_remediation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MIXED_ASK,
            evidence_context=working,
        )

    summary = " ".join(summary_parts)
    followups = _compose_followups_for_intents(
        answered,
        packet=packet,
        evidence_context=working,
    )
    # §4.7: one overlay + one auditor pass on the composed reply.
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=tuple(caveat_lines),
        claims=tuple(claims),
        followups=followups,
        recovery_reason=recovery_reason or REASON_MIXED_COMPOSE,
        discuss_intent=INTENT_MIXED_ASK,
        evidence_context=working,
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


def build_missing_assumptions_limitation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MISSING_ASSUMPTIONS,
):
    """Digit-free missing assumptions/costs limitation (RI-6 short-circuit)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer costs or run-assumption questions because those "
        "assumption leaves are not present on this run."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether walk-forward or validation diagnostics are present on this packet.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No cost or assumption figures were invented for this ask.",
            "In-sample trade summary KPIs are not a substitute for cost assumptions.",
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


def build_missing_robustness_limitation_reply(
    packet: EvidencePacket,
    *,
    recovery_reason: str | None = REASON_MISSING_ROBUSTNESS,
    evidence_context: Mapping[str, Any] | None = None,
):
    """Digit-free missing tier-2 robustness limitation (RI-5 short-circuit)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer Monte Carlo, overfitting, sensitivity, noise, portfolio, "
        "or OTF robustness questions because those batteries are not present on "
        "this run."
    )
    followups_list = [
        "Ask for the key metrics or a summary of this run.",
    ]
    if _oos_evidence_absent(packet, evidence_context=evidence_context):
        followups_list.append("Ask which evidence paths remain available on this packet.")
    else:
        followups_list.append(
            "Ask whether walk-forward or validation diagnostics are present on this packet."
        )
    followups = tuple(followups_list)
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No secondary robustness figures were invented for this ask.",
            "In-sample trade summary KPIs are not a substitute for robustness batteries.",
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


def build_missing_metric_limitation_reply(
    packet: EvidencePacket,
    *,
    path: str | None = None,
    recovery_reason: str | None = REASON_MISSING_METRIC,
):
    """Digit-free missing-leaf limitation (RI-4 short-circuit; no invented metrics)."""
    from thesistester.assistant.results_qa import ResultsQAReply

    summary = (
        "I cannot answer that metric question because the requested trade-summary "
        "leaf is not present on this run."
    )
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask about a different metric that was recorded on this packet.",
    )
    caveats = merge_mandatory_packet_caveats(
        packet,
        (
            "No metric figures were invented for this ask.",
            "In-sample trade summary leaves are not a substitute for OOS or WFA evidence.",
        ),
    )
    assert_llm_explanation_grounded(
        packet,
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
    )
    # path retained for callers/logging; not narrated (digit-/path-free limitation).
    _ = path
    return ResultsQAReply(
        summary=summary,
        caveats=caveats,
        claims=(),
        followups=followups,
        recovery_reason=recovery_reason,
    )


def build_deterministic_single_metric_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    path: str,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe one-claim reply for a frozen §4.5 metric path."""
    if not has_single_metric_evidence(evidence_context, path):
        return build_missing_metric_limitation_reply(
            packet,
            path=path,
            recovery_reason=recovery_reason or REASON_MISSING_METRIC,
        )

    value = _path_get(evidence_context, path)
    text = _format_scalar_for_claim(path, value)
    if text is None:
        return build_missing_metric_limitation_reply(
            packet,
            path=path,
            recovery_reason=recovery_reason or REASON_MISSING_METRIC,
        )

    claim = EvidenceClaim(text=text, path=path, value=value)
    summary = text
    caveat_seed = (
        "This figure describes the recorded historical sample, not a forecast.",
        "Do not treat an in-sample metric as out-of-sample confirmation.",
    )
    grounded = (claim,)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether walk-forward or validation diagnostics are present on this packet.",
    )
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_SINGLE_METRIC,
        evidence_context=evidence_context,
    )


def build_deterministic_time_ranking_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe best-entry-time reply from the frozen §4.3 allowlist."""
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
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_TIME_RANKING,
        evidence_context=working,
    )


def build_deterministic_validation_wfa_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe validation/WFA reply from the frozen §4.4 allowlist."""
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
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_VALIDATION_WFA,
        evidence_context=evidence_context,
    )


def build_deterministic_robustness_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe tier-2 robustness reply from the frozen §4.6 allowlist."""
    if not has_robustness_tier2_evidence(evidence_context):
        return build_missing_robustness_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_ROBUSTNESS,
            evidence_context=evidence_context,
        )

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    for path in ROBUSTNESS_CLAIM_PATHS:
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
        return build_missing_robustness_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_ROBUSTNESS,
            evidence_context=evidence_context,
        )

    summary = "Robustness batteries: " + "; ".join(summary_parts) + "."
    caveat_seed = (
        "These Monte Carlo / overfitting / sensitivity / noise / portfolio / OTF "
        "figures are research diagnostics, not proof of deployable edge.",
        "Do not treat in-sample trade summary KPIs as robustness confirmation.",
    )
    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask whether walk-forward or validation diagnostics are present on this packet.",
    )
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_ROBUSTNESS_TIER2,
        evidence_context=evidence_context,
    )


def build_deterministic_assumptions_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe assumptions/costs reply from the frozen §4.6 allowlist."""
    if not has_assumptions_costs_evidence(evidence_context):
        return build_missing_assumptions_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_ASSUMPTIONS,
        )

    claims: list[EvidenceClaim] = []
    summary_parts: list[str] = []
    for path in ASSUMPTIONS_CLAIM_PATHS:
        if not _path_exists(evidence_context, path):
            continue
        value = _path_get(evidence_context, path)
        text = _format_scalar_for_claim(path, value)
        if text is None:
            continue
        # Hard rule: never emit trade_summary / performance KPI paths.
        if "trade_summary" in path:
            continue
        claims.append(EvidenceClaim(text=text, path=path, value=value))
        summary_parts.append(text.rstrip("."))

    if not claims:
        return build_missing_assumptions_limitation_reply(
            packet,
            recovery_reason=recovery_reason or REASON_MISSING_ASSUMPTIONS,
        )

    summary = "Run assumptions: " + "; ".join(summary_parts) + "."
    caveat_seed = (
        "These cost and assumption figures describe the recorded research setup, "
        "not live brokerage conditions or deployable edge.",
        "Do not treat in-sample trade summary KPIs as cost or assumption evidence.",
    )
    grounded = tuple(claims)
    caveats = merge_mandatory_packet_caveats(packet, caveat_seed)
    followups = (
        "Ask for the key metrics or a summary of this run.",
        "Ask about best stop and take profit ranking if a grid was recorded.",
    )
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_ASSUMPTIONS_COSTS,
        evidence_context=evidence_context,
    )


def build_deterministic_grid_ranking_reply(
    packet: EvidencePacket,
    evidence_context: Mapping[str, Any],
    *,
    recovery_reason: str | None = None,
    apply_overlay: bool = True,
):
    """Build an auditor-safe best SL/TP reply from the frozen grid allowlist."""
    working = _ensure_grid_rankings_context(evidence_context)
    if not has_grid_ranking_evidence(working):
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
        if not _path_exists(working, path):
            continue
        # Skip recorded best leaf only when the matching projection leaf was cited.
        if path.startswith("results.best_grid_result."):
            leaf = path.rsplit(".", 1)[-1]
            projection_path = f"results.projections.grid_rankings.best.{leaf}"
            if projection_path in claimed_paths:
                continue
        value = _path_get(working, path)
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
    if not apply_overlay:
        return _reply_without_overlay(
            summary=summary,
            caveats=caveats,
            claims=grounded,
            followups=followups,
            recovery_reason=recovery_reason,
        )
    return apply_expert_overlay(
        packet,
        summary=summary,
        caveats=caveats,
        claims=grounded,
        recovery_reason=recovery_reason,
        followups=followups,
        discuss_intent=INTENT_GRID_RANKING,
        evidence_context=working,
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
