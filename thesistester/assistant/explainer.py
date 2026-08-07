"""Grounded, deterministic research-result explanation helpers.

Every narrative claim is built from an evidence path and exact packet value.
Missing evidence becomes an explicit limitation; "best"/"better" language always
states metric, candidate set, sample, costs, and OOS status.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from thesistester.reporting import build_research_artifact, to_jsonable

EVIDENCE_PACKET_SCHEMA_VERSION = 1
COMPARISON_EVIDENCE_SCHEMA_VERSION = 1
LOW_SAMPLE_THRESHOLD = 30

_CAVEAT_CODES = {
    "diagnostic_only": "Research results are diagnostics, not proof of edge or trading advice.",
    "low_sample": "Trade count is below the 30-trade screening threshold.",
    "sample_unavailable": "Trade count is unavailable; sample-size screening cannot be assessed.",
    "zero_costs": "Execution uses zero commission and zero slippage assumptions.",
    "overlapping_exposure": "allow_all exposure can count overlapping signals independently.",
    "intrabar_ambiguity": "Intrabar ordering remains model-dependent.",
    "grid_selection": "Grid selection is in-sample unless confirmed by OOS/WFA evidence.",
    "missing_oos": "Out-of-sample / walk-forward evidence is missing.",
    "failed_oos": "Walk-forward / OOS diagnostics report failed or empty folds.",
    "failed_robustness": "One or more robustness diagnostics failed or are unavailable.",
    "multiple_testing": "Multiple candidate trials increase selection bias risk.",
    "focus_post_hoc": (
        "Focus results are a post-hoc trade subset — not a constrained re-simulation "
        "and not proof of deployable edge. Promote and re-simulate (Admit) before "
        "treating a window as constrained evidence."
    ),
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _path_get(root: Mapping[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


@dataclass(frozen=True)
class EvidenceClaim:
    """One narrative fragment grounded to an exact packet path and value."""

    text: str
    path: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "path": self.path, "value": to_jsonable(self.value)}


@dataclass(frozen=True)
class EvidenceCaveat:
    """Structured mandatory caveat with a stable code."""

    code: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.path is not None:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class EvidencePacket:
    """Immutable JSON-safe evidence allowed to support an assistant explanation."""

    provenance: Mapping[str, Any]
    assumptions: Mapping[str, Any]
    results: Mapping[str, Any]
    warnings: tuple[str, ...]
    schema_version: int = EVIDENCE_PACKET_SCHEMA_VERSION
    caveats: tuple[EvidenceCaveat, ...] = ()
    limitations: tuple[str, ...] = ()
    claims: tuple[EvidenceClaim, ...] = ()
    next_experiments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "assumptions", _freeze(self.assumptions))
        object.__setattr__(self, "results", _freeze(self.results))
        object.__setattr__(
            self,
            "caveats",
            tuple(
                item
                if isinstance(item, EvidenceCaveat)
                else EvidenceCaveat(**item)
                if isinstance(item, Mapping)
                else item
                for item in self.caveats
            ),
        )
        object.__setattr__(
            self,
            "claims",
            tuple(
                item
                if isinstance(item, EvidenceClaim)
                else EvidenceClaim(**item)
                if isinstance(item, Mapping)
                else item
                for item in self.claims
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provenance": _thaw(self.provenance),
            "assumptions": _thaw(self.assumptions),
            "results": _thaw(self.results),
            "warnings": list(self.warnings),
            "caveats": [caveat.to_dict() for caveat in self.caveats],
            "limitations": list(self.limitations),
            "claims": [claim.to_dict() for claim in self.claims],
            "next_experiments": list(self.next_experiments),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidencePacket:
        """Rebuild a packet; missing schema fields hydrate to v1 defaults."""
        if not isinstance(payload, Mapping):
            raise ValueError("Evidence packet payload must be an object.")
        caveats = tuple(
            EvidenceCaveat(
                code=str(item.get("code", "diagnostic_only")),
                message=str(item.get("message", "")),
                path=item.get("path") if isinstance(item.get("path"), str) else None,
            )
            for item in payload.get("caveats") or ()
            if isinstance(item, Mapping)
        )
        claims = tuple(
            EvidenceClaim(
                text=str(item.get("text", "")),
                path=str(item.get("path", "")),
                value=item.get("value"),
            )
            for item in payload.get("claims") or ()
            if isinstance(item, Mapping)
        )
        warnings = tuple(str(item) for item in payload.get("warnings") or ())
        if not caveats and warnings:
            caveats = tuple(
                EvidenceCaveat(code="legacy_warning", message=warning) for warning in warnings
            )
        return cls(
            schema_version=int(payload.get("schema_version") or EVIDENCE_PACKET_SCHEMA_VERSION),
            provenance=dict(payload.get("provenance") or {}),
            assumptions=dict(payload.get("assumptions") or {}),
            results=dict(payload.get("results") or {}),
            warnings=warnings,
            caveats=caveats,
            limitations=tuple(str(item) for item in payload.get("limitations") or ()),
            claims=claims,
            next_experiments=tuple(str(item) for item in payload.get("next_experiments") or ()),
        )


def _effective_configuration(
    provenance: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    config = provenance.get("effective_configuration")
    if isinstance(config, Mapping):
        return dict(config)
    return {
        key: state.get(key)
        for key in ("dataset", "levels", "setup", "backtest", "grid", "validation", "walk_forward")
        if isinstance(state.get(key), Mapping)
    }


def _cost_exposure_assumptions(
    config: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    backtest = _as_mapping(config.get("backtest")) or {}
    grid = _as_mapping(config.get("grid")) or {}
    state_costs = _as_mapping(state.get("backtest_execution_costs")) or {}
    grid_costs = _as_mapping(state.get("grid_execution_costs")) or {}
    commission = backtest.get("commission_per_side", state_costs.get("commission_per_side"))
    slippage = backtest.get("slippage_ticks", state_costs.get("slippage_ticks"))
    exposure = backtest.get("exposure_policy")
    if exposure is None:
        exposure_map = _as_mapping(state.get("exposure_policy")) or {}
        exposure = exposure_map.get("exposure_policy")
    grid_commission = grid.get("commission_per_side", grid_costs.get("commission_per_side"))
    grid_slippage = grid.get("slippage_ticks", grid_costs.get("slippage_ticks"))
    grid_exposure = grid.get("exposure_policy")
    if grid_exposure is None:
        grid_exposure_map = _as_mapping(state.get("grid_exposure_policy")) or {}
        grid_exposure = grid_exposure_map.get("exposure_policy")
    return {
        "commission_per_side": commission,
        "slippage_ticks": slippage,
        "exposure_policy": exposure,
        "grid_commission_per_side": grid_commission,
        "grid_slippage_ticks": grid_slippage,
        "grid_exposure_policy": grid_exposure,
        "stop_loss_ticks": backtest.get("stop_loss_ticks"),
        "take_profit_ticks": backtest.get("take_profit_ticks"),
        "intrabar_model": backtest.get("intrabar_model"),
    }


def _append_caveat(
    caveats: list[EvidenceCaveat],
    code: str,
    *,
    path: str | None = None,
    message: str | None = None,
) -> None:
    text = message or _CAVEAT_CODES.get(code, code)
    if any(item.code == code and item.message == text for item in caveats):
        return
    caveats.append(EvidenceCaveat(code=code, message=text, path=path))


def _derive_caveats(
    *,
    results: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> tuple[list[EvidenceCaveat], list[str]]:
    caveats: list[EvidenceCaveat] = []
    limitations: list[str] = []
    _append_caveat(caveats, "diagnostic_only")

    summary = _as_mapping(results.get("trade_summary")) or {}
    trade_count = _numeric(summary.get("trade_count"))
    if trade_count is None:
        _append_caveat(caveats, "sample_unavailable", path="results.trade_summary.trade_count")
        limitations.append("Baseline trade_count is missing from evidence.")
    elif trade_count < LOW_SAMPLE_THRESHOLD:
        _append_caveat(caveats, "low_sample", path="results.trade_summary.trade_count")

    costs = _as_mapping(assumptions.get("costs_exposure")) or {}
    if costs.get("commission_per_side") == 0 and costs.get("slippage_ticks") == 0:
        _append_caveat(caveats, "zero_costs", path="assumptions.costs_exposure")
    elif costs.get("commission_per_side") is None and costs.get("slippage_ticks") is None:
        limitations.append("Cost assumptions are not present in evidence.")

    if (
        costs.get("exposure_policy") == "allow_all"
        or costs.get("grid_exposure_policy") == "allow_all"
    ):
        _append_caveat(
            caveats, "overlapping_exposure", path="assumptions.costs_exposure.exposure_policy"
        )

    # Real backtest_intrabar_policy / costs_exposure store `intrabar_model`.
    # Accept legacy `model` for older packet fixtures.
    intrabar_policy = _as_mapping(assumptions.get("intrabar")) or {}
    intrabar_model = (
        intrabar_policy.get("intrabar_model")
        if intrabar_policy.get("intrabar_model") is not None
        else intrabar_policy.get("model")
        if intrabar_policy.get("model") is not None
        else costs.get("intrabar_model")
    )
    has_intrabar_diagnostic = results.get("backtest_intrabar_diagnostic") is not None
    if has_intrabar_diagnostic or intrabar_model not in (None, "sl_first"):
        if has_intrabar_diagnostic:
            caveat_path = "results.backtest_intrabar_diagnostic"
        elif intrabar_policy.get("intrabar_model") not in (None, "sl_first"):
            caveat_path = "assumptions.intrabar.intrabar_model"
        elif intrabar_policy.get("model") not in (None, "sl_first"):
            caveat_path = "assumptions.intrabar.model"
        else:
            caveat_path = "assumptions.costs_exposure.intrabar_model"
        _append_caveat(caveats, "intrabar_ambiguity", path=caveat_path)

    grid_result = _as_mapping(results.get("best_grid_result"))
    grid_cfg = _as_mapping(assumptions.get("grid")) or {}
    if (
        grid_result is not None
        or grid_cfg.get("enabled", False)
        or (isinstance(grid_cfg.get("stop_loss_ticks_values"), list))
    ):
        _append_caveat(caveats, "grid_selection", path="results.best_grid_result")

    wfa = _as_mapping(results.get("walk_forward_summary"))
    if wfa is None:
        if grid_result is not None:
            _append_caveat(caveats, "missing_oos", path="results.walk_forward_summary")
            limitations.append("OOS/WFA summary is missing while a grid candidate is present.")
    else:
        valid_folds = _numeric(wfa.get("valid_fold_count"))
        fold_count = _numeric(wfa.get("fold_count"))
        if (valid_folds is not None and valid_folds <= 0) or (
            fold_count is not None and fold_count > 0 and valid_folds == 0
        ):
            _append_caveat(
                caveats, "failed_oos", path="results.walk_forward_summary.valid_fold_count"
            )
        warnings = results.get("walk_forward_warnings") or []
        if isinstance(warnings, (list, tuple)) and warnings:
            _append_caveat(
                caveats,
                "failed_oos",
                path="results.walk_forward_warnings",
                message="Walk-forward warnings indicate OOS fragility.",
            )

    robustness_keys = (
        "validation_summary",
        "monte_carlo_summary",
        "noise_summary",
        "sensitivity_summary",
        "overfitting_summary",
    )
    failed_robustness = False
    for key in robustness_keys:
        value = results.get(key)
        if value is None:
            continue
        if value == {} or value is False:
            failed_robustness = True
            continue
        mapping = _as_mapping(value)
        if mapping is not None and mapping.get("available") is False:
            failed_robustness = True
        if mapping is not None and str(mapping.get("status", "")).lower() in {
            "failed",
            "error",
            "unavailable",
        }:
            failed_robustness = True
    if failed_robustness:
        _append_caveat(caveats, "failed_robustness", path="results.validation_summary")

    trial_count = _numeric((_as_mapping(provenance.get("summary")) or {}).get("trial_count"))
    if trial_count is None:
        trial_count = _numeric(provenance.get("trial_count"))
    if grid_result is not None or (trial_count is not None and trial_count > 1):
        _append_caveat(caveats, "multiple_testing", path="results.best_grid_result")

    entry_window = _as_mapping(assumptions.get("entry_window")) or {}
    focus = _as_mapping(entry_window.get("focus")) or {}
    focus_enabled = focus.get("enabled") is True
    focus_prov = _as_mapping(focus.get("provenance")) or {}
    if focus_enabled or focus_prov:
        _append_caveat(
            caveats,
            "focus_post_hoc",
            path="assumptions.entry_window.focus",
        )

    return caveats, limitations


def _next_experiments(
    *,
    caveats: list[EvidenceCaveat],
    results: Mapping[str, Any],
    limitations: list[str],
) -> list[str]:
    codes = {item.code for item in caveats}
    guidance: list[str] = []
    if "low_sample" in codes or "sample_unavailable" in codes:
        guidance.append(
            "Gather a larger historical sample before ranking candidates (evidence: trade_count)."
        )
    if "zero_costs" in codes:
        guidance.append(
            "Re-run with explicit non-zero commission and slippage to test cost sensitivity."
        )
    if "overlapping_exposure" in codes:
        guidance.append(
            "Compare against single_position or single_direction exposure to remove overlap inflation."
        )
    if "grid_selection" in codes and "missing_oos" in codes:
        guidance.append(
            "Run walk-forward / OOS validation on the selected SL/TP candidate before promotion."
        )
    if "failed_oos" in codes or "failed_robustness" in codes:
        guidance.append(
            "Treat the current candidate as rejected until OOS/robustness diagnostics pass."
        )
    if results.get("time_grouped_summary") is None and "time analysis" not in " ".join(limitations):
        if _as_mapping(results.get("trade_summary")) is not None:
            guidance.append(
                "Add session/time analysis to test whether expectancy concentrates in one session."
            )
    if not guidance and limitations:
        guidance.append(
            "Fill missing evidence fields listed in limitations before drawing ranking conclusions."
        )
    return guidance


def _otf_validation_from_artifact(
    artifact: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Project top-level artifact/session OTF validation into packet results."""
    otf_validation = artifact.get("otf_validation")
    if isinstance(otf_validation, Mapping):
        return dict(to_jsonable(otf_validation))
    summary = state.get("otf_validation_summary")
    config = state.get("otf_validation_config")
    matrix = state.get("otf_validation_matrix")
    has_matrix = False
    if matrix is not None:
        try:
            has_matrix = len(matrix) > 0
        except TypeError:
            has_matrix = bool(matrix)
    if summary is None and config is None and not has_matrix:
        return None
    return {
        "available": True,
        "summary": to_jsonable(summary) if summary is not None else None,
        "config": to_jsonable(config) if config is not None else None,
    }


def build_evidence_packet(
    state: Mapping[str, Any], *, provenance: Mapping[str, Any]
) -> EvidencePacket:
    """Build bounded explanation evidence from an existing research result only."""
    artifact = build_research_artifact(state)
    results = to_jsonable(artifact["results"])
    if not isinstance(results, dict):
        results = {}
    else:
        results = dict(results)
    # Research artifacts store OTF validation as a top-level section, not under
    # results; project it so explanation templates can ground OTF claims.
    otf_validation = _otf_validation_from_artifact(artifact, state)
    if otf_validation is not None:
        results["otf_validation"] = otf_validation
        if results.get("otf_validation_summary") is None:
            results["otf_validation_summary"] = otf_validation.get("summary")
    # CAI-9 page-shaped summaries (bounded; never raw frames).
    from thesistester.assistant.page_summaries import (
        summarize_backtest_state,
        summarize_grid_state,
        summarize_levels_state,
        summarize_signals_state,
        summarize_validation_state,
    )

    provenance_data = to_jsonable(dict(provenance))
    config = _effective_configuration(provenance_data, state)
    costs_exposure = _cost_exposure_assumptions(config, state)
    levels_summary = summarize_levels_state(state)
    signals_summary = summarize_signals_state(state)
    # Pass provenance-derived costs so page-summary caveats match assumptions.
    backtest_summary = summarize_backtest_state(state, cost_assumptions=costs_exposure)
    grid_summary = summarize_grid_state(state)
    validation_page_summary = summarize_validation_state(state)
    if levels_summary.get("available"):
        results["levels_summary"] = levels_summary
    if signals_summary.get("available"):
        results["signals_summary"] = signals_summary
    if backtest_summary.get("available"):
        results["backtest_page_summary"] = backtest_summary
    if grid_summary.get("available"):
        results["grid_summary"] = grid_summary
    if validation_page_summary.get("available"):
        results["validation_page_summary"] = validation_page_summary
    # Nest fingerprint under assumptions.dataset so LLM claim paths like
    # assumptions.dataset.dataset_fingerprint resolve. Keep the top-level
    # assumptions.dataset_fingerprint sibling for compare_evidence and older
    # packet consumers. Nest only when provenance has a fingerprint so a null
    # key cannot make a missing identity look citable; strip any config-sourced
    # dataset_fingerprint so only provenance identity is claimable.
    dataset_assumptions = to_jsonable(config.get("dataset") or {})
    if not isinstance(dataset_assumptions, dict):
        dataset_assumptions = {}
    else:
        dataset_assumptions = dict(dataset_assumptions)
    dataset_assumptions.pop("dataset_fingerprint", None)
    dataset_fingerprint = to_jsonable(provenance_data.get("dataset_fingerprint"))
    if dataset_fingerprint is not None:
        dataset_assumptions["dataset_fingerprint"] = dataset_fingerprint
    assumptions = {
        "setup_config": artifact["configuration"]["setup_config"],
        "instrument": artifact["configuration"]["instrument"],
        "intrabar": artifact["intrabar"]["backtest_policy"],
        "otf_filter": artifact["otf_filter"],
        "entry_window": artifact.get("entry_window"),
        "dataset": dataset_assumptions,
        "backtest": to_jsonable(config.get("backtest") or {}),
        "grid": to_jsonable(config.get("grid") or {}),
        "validation": to_jsonable(config.get("validation") or {}),
        "walk_forward": to_jsonable(config.get("walk_forward") or {}),
        "costs_exposure": to_jsonable(costs_exposure),
        "dataset_fingerprint": dataset_fingerprint,
        "seeds": to_jsonable(provenance_data.get("seeds") or {}),
        "levels_settings": to_jsonable(levels_summary.get("configuration") or {}),
        "levels_identity": to_jsonable(levels_summary.get("identity")),
    }
    caveats, limitations = _derive_caveats(
        results=results,
        assumptions=assumptions,
        provenance=provenance_data,
    )
    if results.get("trade_summary") is None:
        limitations.append("Baseline trade_summary is missing from evidence.")
    for key, label in (
        ("validation_summary", "Validation diagnostics"),
        ("monte_carlo_summary", "Monte Carlo diagnostics"),
        ("noise_summary", "Noise diagnostics"),
        ("sensitivity_summary", "Sensitivity diagnostics"),
        ("overfitting_summary", "Overfitting diagnostics"),
        ("walk_forward_summary", "Walk-forward / OOS diagnostics"),
        ("portfolio_summary", "Portfolio diagnostics"),
        ("time_grouped_summary", "Time/session analysis"),
    ):
        if results.get(key) is None:
            limitations.append(f"{label} are not present in this evidence packet.")
    otf = _as_mapping(assumptions.get("otf_filter")) or {}
    has_otf_validation = (
        results.get("otf_validation_summary") is not None
        or (_as_mapping(results.get("otf_validation")) or {}).get("available") is True
    )
    if otf.get("available") is False and not has_otf_validation:
        limitations.append("OTF filter evidence is not available for this run.")
    elif not otf and not has_otf_validation:
        limitations.append("OTF filter evidence is not available for this run.")

    next_experiments = _next_experiments(caveats=caveats, results=results, limitations=limitations)
    warnings = tuple(caveat.message for caveat in caveats)
    return EvidencePacket(
        schema_version=EVIDENCE_PACKET_SCHEMA_VERSION,
        provenance=provenance_data,
        assumptions=assumptions,
        results=results,
        warnings=warnings,
        caveats=tuple(caveats),
        limitations=tuple(dict.fromkeys(limitations)),
        next_experiments=tuple(dict.fromkeys(next_experiments)),
    )


def _claim(claims: list[EvidenceClaim], text: str, path: str, value: Any) -> None:
    claims.append(EvidenceClaim(text=text, path=path, value=value))


def _template_baseline(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    summary = _as_mapping(packet.results.get("trade_summary")) or {}
    trades = summary.get("trade_count")
    expectancy = summary.get("expectancy_r")
    if _numeric(trades) is None and trades is not None and not isinstance(trades, (int, float)):
        trades_display = trades
    elif _numeric(trades) is None:
        trades_display = "unknown"
    else:
        trades_display = trades
    expectancy_display = expectancy if expectancy is not None else "unavailable"
    text = f"Historical sample: {trades_display} trades; expectancy R: {expectancy_display}."
    lines.append(text)
    _claim(claims, text, "results.trade_summary.trade_count", trades)
    _claim(claims, text, "results.trade_summary.expectancy_r", expectancy)
    lines.append("This describes the recorded sample, not a forecast.")


def _template_failure(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    provenance_error = packet.provenance.get("error")
    results_error = packet.results.get("error")
    error = provenance_error if provenance_error not in (None, "") else results_error
    error_path = (
        "provenance.error"
        if provenance_error not in (None, "")
        else "results.error"
        if results_error not in (None, "")
        else None
    )
    if not error and packet.provenance.get("status") not in {"failed", "cancelled"}:
        summary = _as_mapping(packet.results.get("trade_summary")) or {}
        if _numeric(summary.get("trade_count")) == 0:
            text = "Failure diagnosis: the recorded sample contains 0 trades."
            lines.append(text)
            _claim(claims, text, "results.trade_summary.trade_count", 0)
        return
    if error and error_path is not None:
        text = f"Failure diagnosis: {error}."
        lines.append(text)
        _claim(claims, text, error_path, error)


def _resolve_grid_ranking_metric(packet: EvidencePacket) -> tuple[Any, str]:
    """Resolve ranking metric from a path that actually exists on the packet.

    Real ``best_grid_result`` rows are metric-column snapshots and do not store
    ``ranking_metric``; the configured metric lives on ``assumptions.grid``.
    """
    grid_result = _as_mapping(packet.results.get("best_grid_result")) or {}
    metric = grid_result.get("ranking_metric")
    if isinstance(metric, str) and metric.strip():
        return metric, "results.best_grid_result.ranking_metric"
    grid_cfg = _as_mapping(packet.assumptions.get("grid")) or {}
    metric = grid_cfg.get("ranking_metric")
    if isinstance(metric, str) and metric.strip():
        return metric, "assumptions.grid.ranking_metric"
    return None, "assumptions.grid.ranking_metric"


def _template_sl_tp(packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]) -> None:
    grid_result = _as_mapping(packet.results.get("best_grid_result"))
    costs = _as_mapping(packet.assumptions.get("costs_exposure")) or {}
    if grid_result is None:
        stop = costs.get("stop_loss_ticks")
        target = costs.get("take_profit_ticks")
        if stop is None and target is None:
            return
        text = (
            f"Configured SL/TP: stop_loss_ticks={stop}, take_profit_ticks={target}; "
            "no grid-selected candidate is present."
        )
        lines.append(text)
        _claim(claims, text, "assumptions.costs_exposure.stop_loss_ticks", stop)
        _claim(claims, text, "assumptions.costs_exposure.take_profit_ticks", target)
        return
    metric, metric_path = _resolve_grid_ranking_metric(packet)
    metric_display = metric if metric is not None else "unavailable ranking metric"
    trade_count = grid_result.get("trade_count")
    trade_display = trade_count if trade_count is not None else "unavailable trade count"
    stop = grid_result.get("stop_loss_ticks")
    target = grid_result.get("take_profit_ticks")
    commission = costs.get("commission_per_side")
    slippage = costs.get("slippage_ticks")
    wfa = _as_mapping(packet.results.get("walk_forward_summary"))
    oos_status = "present" if wfa is not None else "missing"
    text = (
        f"Best grid candidate by {metric_display} uses SL={stop}, TP={target} with "
        f"{trade_display} trades in the selection sample; costs "
        f"commission_per_side={commission}, slippage_ticks={slippage}; "
        f"OOS/WFA status={oos_status}."
    )
    lines.append(text)
    _claim(claims, text, metric_path, metric)
    _claim(claims, text, "results.best_grid_result.trade_count", trade_count)
    _claim(claims, text, "results.best_grid_result.stop_loss_ticks", stop)
    _claim(claims, text, "results.best_grid_result.take_profit_ticks", target)
    _claim(claims, text, "assumptions.costs_exposure.commission_per_side", commission)
    _claim(claims, text, "assumptions.costs_exposure.slippage_ticks", slippage)
    lines.append(
        "Grid candidate uses the stated ranking metric and sample; confirm it with OOS/WFA evidence."
    )


def _template_validation(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    validation = packet.results.get("validation_summary")
    if validation is None:
        return
    text = "Validation diagnostics are available and should be reviewed alongside the baseline."
    lines.append(text)
    _claim(claims, text, "results.validation_summary", validation)


def _template_robustness(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    for key, label in (
        ("monte_carlo_summary", "Monte Carlo"),
        ("noise_summary", "Noise"),
        ("sensitivity_summary", "Sensitivity"),
        ("overfitting_summary", "Overfitting"),
    ):
        value = packet.results.get(key)
        if value is None:
            continue
        mapping = _as_mapping(value) or {}
        status = mapping.get("status", "present")
        text = f"{label} diagnostic evidence is {status}."
        lines.append(text)
        _claim(claims, text, f"results.{key}", value)


def _template_wfa(packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]) -> None:
    wfa = _as_mapping(packet.results.get("walk_forward_summary"))
    if wfa is None:
        return
    folds = wfa.get("fold_count")
    valid = wfa.get("valid_fold_count")
    median = wfa.get("median_test_expectancy_r")
    text = (
        f"Walk-forward/OOS: fold_count={folds}, valid_fold_count={valid}, "
        f"median_test_expectancy_r={median}."
    )
    lines.append(text)
    _claim(claims, text, "results.walk_forward_summary.fold_count", folds)
    _claim(claims, text, "results.walk_forward_summary.valid_fold_count", valid)
    _claim(claims, text, "results.walk_forward_summary.median_test_expectancy_r", median)
    lines.append(
        "Walk-forward output is available; do not treat in-sample selection as OOS performance."
    )


def _template_time(packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]) -> None:
    grouped = packet.results.get("time_grouped_summary")
    if grouped is None:
        return
    text = "Time/session analysis evidence is present for descriptive segmentation only."
    lines.append(text)
    _claim(claims, text, "results.time_grouped_summary", grouped)


def _template_otf(packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]) -> None:
    otf = _as_mapping(packet.assumptions.get("otf_filter")) or {}
    walk_forward = _as_mapping(packet.assumptions.get("walk_forward")) or {}
    wfa_summary = _as_mapping(packet.results.get("walk_forward_summary")) or {}
    otf_validation = _as_mapping(packet.results.get("otf_validation")) or {}
    otf_summary = packet.results.get("otf_validation_summary")
    if otf_summary is None and otf_validation:
        otf_summary = otf_validation.get("summary")
    # Keep going when only walk_forward_summary carries otf_history_policy —
    # assumptions.walk_forward may be absent on completed WFO evidence packets.
    if (
        not otf
        and otf_summary is None
        and not otf_validation
        and not walk_forward
        and "otf_history_policy" not in wfa_summary
    ):
        return
    # Availability must be claimed at the path that actually stores it.
    if "available" in otf:
        available = otf.get("available")
        text = f"OTF filter evidence available={available}."
        lines.append(text)
        _claim(claims, text, "assumptions.otf_filter.available", available)
    history_policy = walk_forward.get("otf_history_policy")
    if history_policy is None:
        history_policy = wfa_summary.get("otf_history_policy")
    if history_policy is not None:
        text = (
            f"Walk-forward OTF history policy={history_policy} "
            "(fold_local is conservative cold-start; causal_prefix may use "
            "prior bars before each fold start; never future bars)."
        )
        lines.append(text)
        if "otf_history_policy" in walk_forward:
            _claim(
                claims,
                text,
                "assumptions.walk_forward.otf_history_policy",
                history_policy,
            )
        else:
            _claim(
                claims,
                text,
                "results.walk_forward_summary.otf_history_policy",
                history_policy,
            )
    if otf_summary is not None:
        text = "OTF validation summary evidence is present."
        lines.append(text)
        _claim(claims, text, "results.otf_validation_summary", otf_summary)
    elif "available" in otf_validation:
        available = otf_validation.get("available")
        text = f"OTF validation evidence available={available}."
        lines.append(text)
        _claim(claims, text, "results.otf_validation.available", available)


def _template_portfolio(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    portfolio = packet.results.get("portfolio_summary")
    if portfolio is None:
        return
    mapping = _as_mapping(portfolio) or {}
    trade_count = mapping.get("trade_count")
    text = f"Portfolio evidence trade_count={trade_count}."
    lines.append(text)
    _claim(claims, text, "results.portfolio_summary.trade_count", trade_count)


def _template_levels(packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]) -> None:
    summary = _as_mapping(packet.results.get("levels_summary")) or {}
    if summary.get("available") is not True:
        return
    column_count = summary.get("level_column_count")
    text = f"Levels evidence: {column_count} level columns in the recorded run."
    lines.append(text)
    _claim(claims, text, "results.levels_summary.level_column_count", column_count)
    identity = _as_mapping(summary.get("identity")) or _as_mapping(
        packet.assumptions.get("levels_identity")
    )
    if identity and identity.get("levels_settings_hash"):
        digest = identity.get("levels_settings_hash")
        id_text = f"Levels settings hash: {digest}."
        lines.append(id_text)
        _claim(claims, id_text, "results.levels_summary.identity.levels_settings_hash", digest)


def _template_signals(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    summary = _as_mapping(packet.results.get("signals_summary")) or {}
    if summary.get("available") is not True:
        return
    signal_count = summary.get("signal_count")
    zone_count = summary.get("zone_count")
    text = f"Signals evidence: {signal_count} signals across {zone_count} confluence zones."
    lines.append(text)
    _claim(claims, text, "results.signals_summary.signal_count", signal_count)
    _claim(claims, text, "results.signals_summary.zone_count", zone_count)
    trigger_dist = _as_mapping(summary.get("trigger_distribution")) or {}
    if trigger_dist:
        # Prefer a single grounded trigger key when present.
        for key, count in trigger_dist.items():
            if key.startswith("_"):
                continue
            trig_text = f"Trigger `{key}` count: {count}."
            lines.append(trig_text)
            _claim(
                claims,
                trig_text,
                f"results.signals_summary.trigger_distribution.{key}",
                count,
            )
            break


def _template_backtest_page(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    summary = _as_mapping(packet.results.get("backtest_page_summary")) or {}
    if summary.get("available") is not True:
        return
    kpis = _as_mapping(summary.get("kpis")) or {}
    trade_count = kpis.get("trade_count")
    expectancy = kpis.get("expectancy_r")
    text = f"Backtest page summary: trade_count={trade_count}, expectancy_r={expectancy}."
    lines.append(text)
    _claim(claims, text, "results.backtest_page_summary.kpis.trade_count", trade_count)
    _claim(claims, text, "results.backtest_page_summary.kpis.expectancy_r", expectancy)
    costs = _as_mapping(summary.get("costs")) or {}
    if "commission_per_side" in costs:
        cost_text = f"Commission per side: {costs.get('commission_per_side')}."
        lines.append(cost_text)
        _claim(
            claims,
            cost_text,
            "results.backtest_page_summary.costs.commission_per_side",
            costs.get("commission_per_side"),
        )


def _template_grid_page(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    summary = _as_mapping(packet.results.get("grid_summary")) or {}
    if summary.get("available") is not True:
        return
    best = _as_mapping(summary.get("best_cell")) or {}
    if not best:
        return
    stop = best.get("stop_loss_ticks")
    target = best.get("take_profit_ticks")
    text = f"Grid selection evidence: SL={stop}, TP={target}."
    lines.append(text)
    _claim(claims, text, "results.grid_summary.best_cell.stop_loss_ticks", stop)
    _claim(claims, text, "results.grid_summary.best_cell.take_profit_ticks", target)


def _template_validation_page(
    packet: EvidencePacket, claims: list[EvidenceClaim], lines: list[str]
) -> None:
    summary = _as_mapping(packet.results.get("validation_page_summary")) or {}
    if summary.get("available") is not True:
        return
    oos = _as_mapping(summary.get("oos_evidence")) or {}
    present = oos.get("present")
    text = f"OOS evidence present: {present}."
    lines.append(text)
    _claim(claims, text, "results.validation_page_summary.oos_evidence.present", present)


def explain_evidence_report(packet: EvidencePacket) -> dict[str, Any]:
    """Render a structured explanation with claims, caveats, and next experiments."""
    claims: list[EvidenceClaim] = []
    lines: list[str] = []
    _template_baseline(packet, claims, lines)
    _template_levels(packet, claims, lines)
    _template_signals(packet, claims, lines)
    _template_backtest_page(packet, claims, lines)
    _template_failure(packet, claims, lines)
    _template_sl_tp(packet, claims, lines)
    _template_grid_page(packet, claims, lines)
    _template_validation(packet, claims, lines)
    _template_validation_page(packet, claims, lines)
    _template_robustness(packet, claims, lines)
    _template_wfa(packet, claims, lines)
    _template_time(packet, claims, lines)
    _template_otf(packet, claims, lines)
    _template_portfolio(packet, claims, lines)
    for limitation in packet.limitations:
        lines.append(f"Limitation: {limitation}")
    for caveat in packet.caveats:
        lines.append(f"Caveat: {caveat.message}")
    next_experiments = list(packet.next_experiments)
    if not next_experiments:
        next_experiments = _next_experiments(
            caveats=list(packet.caveats),
            results=_thaw(packet.results),
            limitations=list(packet.limitations),
        )
    for item in next_experiments:
        lines.append(f"Next experiment: {item}")
    grounded = []
    packet_dict = {
        "provenance": _thaw(packet.provenance),
        "assumptions": _thaw(packet.assumptions),
        "results": _thaw(packet.results),
    }
    for claim in claims:
        if claim.path and _path_get(packet_dict, claim.path) is None and claim.value is not None:
            # Exact value may live only on the claim when parent path differs; still
            # require the claimed value to match the path when the path resolves.
            pass
        grounded.append(claim.to_dict())
    return {
        "schema_version": EVIDENCE_PACKET_SCHEMA_VERSION,
        "narrative": "\n".join(lines),
        "claims": grounded,
        "caveats": [caveat.to_dict() for caveat in packet.caveats],
        "limitations": list(packet.limitations),
        "next_experiments": next_experiments,
    }


def explain_evidence(packet: EvidencePacket) -> str:
    """Render a concise explanation containing only packet-backed claims."""
    return explain_evidence_report(packet)["narrative"]


def assert_claims_grounded(packet: EvidencePacket, report: Mapping[str, Any] | None = None) -> None:
    """Fail closed when a reported numeric claim is absent from the packet."""
    payload = report or explain_evidence_report(packet)
    packet_dict = packet.to_dict()
    for claim in payload.get("claims") or ():
        if not isinstance(claim, Mapping):
            continue
        path = claim.get("path")
        value = claim.get("value")
        if not isinstance(path, str) or not path:
            raise ValueError("Explanation claim is missing an evidence path.")
        resolved = _path_get(packet_dict, path)
        if value is not None and resolved != value and resolved is None:
            # Allow claims that cite a missing path only when value is also missing.
            raise ValueError(f"Claim path {path!r} is missing from the evidence packet.")
        if value is not None and resolved is not None and resolved != value:
            raise ValueError(f"Claim path {path!r} value mismatch: {resolved!r} != {value!r}")


def _mapping_diff(
    left: Mapping[str, Any] | None, right: Mapping[str, Any] | None
) -> dict[str, Any]:
    left_map = _thaw(left or {})
    right_map = _thaw(right or {})
    keys = sorted(set(left_map) | set(right_map))
    changed = {}
    for key in keys:
        if left_map.get(key) != right_map.get(key):
            changed[key] = {"left": left_map.get(key), "right": right_map.get(key)}
    return changed


def compare_evidence(left: EvidencePacket, right: EvidencePacket) -> dict[str, Any]:
    """Return a versioned evidence-only comparison of two explicitly selected runs."""

    def metrics(packet: EvidencePacket) -> dict[str, Any]:
        summary = packet.results.get("trade_summary")
        return _thaw(summary) if isinstance(summary, Mapping) else {}

    left_metrics = metrics(left)
    right_metrics = metrics(right)
    keys = ("trade_count", "expectancy_r", "total_r", "max_drawdown_r", "win_rate")
    left_costs = _thaw(_as_mapping(left.assumptions.get("costs_exposure")) or {})
    right_costs = _thaw(_as_mapping(right.assumptions.get("costs_exposure")) or {})
    left_fp = _thaw(
        left.assumptions.get("dataset_fingerprint") or left.provenance.get("dataset_fingerprint")
    )
    right_fp = _thaw(
        right.assumptions.get("dataset_fingerprint") or right.provenance.get("dataset_fingerprint")
    )
    assumptions_diff = {
        "setup_config": _mapping_diff(
            _as_mapping(left.assumptions.get("setup_config")),
            _as_mapping(right.assumptions.get("setup_config")),
        ),
        "backtest": _mapping_diff(
            _as_mapping(left.assumptions.get("backtest")),
            _as_mapping(right.assumptions.get("backtest")),
        ),
        "grid": _mapping_diff(
            _as_mapping(left.assumptions.get("grid")),
            _as_mapping(right.assumptions.get("grid")),
        ),
        "validation": _mapping_diff(
            _as_mapping(left.assumptions.get("validation")),
            _as_mapping(right.assumptions.get("validation")),
        ),
        "walk_forward": _mapping_diff(
            _as_mapping(left.assumptions.get("walk_forward")),
            _as_mapping(right.assumptions.get("walk_forward")),
        ),
        "costs_exposure": _mapping_diff(left_costs, right_costs),
    }
    data_comparability = {
        "same_dataset_fingerprint": left_fp == right_fp and left_fp is not None,
        "left_dataset_fingerprint": left_fp,
        "right_dataset_fingerprint": right_fp,
        "left_instrument": left.assumptions.get("instrument"),
        "right_instrument": right.assumptions.get("instrument"),
        "comparable": (
            left_fp == right_fp
            and left_fp is not None
            and left.assumptions.get("instrument") == right.assumptions.get("instrument")
        ),
    }
    conclusions: list[str] = []
    if not data_comparability["comparable"]:
        conclusions.append(
            "Runs are not directly comparable on dataset fingerprint and instrument; "
            "treat metric deltas as descriptive only."
        )
    else:
        conclusions.append(
            "Runs share dataset fingerprint and instrument; executable-spec differences "
            "are listed under assumptions_diff."
        )
    left_exp = _numeric(left_metrics.get("expectancy_r"))
    right_exp = _numeric(right_metrics.get("expectancy_r"))
    if left_exp is not None and right_exp is not None:
        better = "left" if left_exp > right_exp else "right" if right_exp > left_exp else "neither"
        conclusions.append(
            f"Better expectancy_r is {better} using metric=expectancy_r, "
            f"candidate set=two selected runs, "
            f"samples=({left_metrics.get('trade_count')}, {right_metrics.get('trade_count')}), "
            f"costs=({left_costs.get('commission_per_side')}/{left_costs.get('slippage_ticks')}, "
            f"{right_costs.get('commission_per_side')}/{right_costs.get('slippage_ticks')}), "
            f"OOS status=("
            f"{'present' if left.results.get('walk_forward_summary') is not None else 'missing'}, "
            f"{'present' if right.results.get('walk_forward_summary') is not None else 'missing'})."
        )
    warnings = list(dict.fromkeys((*left.warnings, *right.warnings)))
    next_experiments = list(dict.fromkeys((*left.next_experiments, *right.next_experiments)))
    if not data_comparability["comparable"]:
        next_experiments.insert(
            0,
            "Re-run both specs on the same dataset fingerprint before ranking expectancy.",
        )
    return to_jsonable(
        {
            "schema_version": COMPARISON_EVIDENCE_SCHEMA_VERSION,
            "left_provenance": _thaw(left.provenance),
            "right_provenance": _thaw(right.provenance),
            "metrics": {
                key: {"left": left_metrics.get(key), "right": right_metrics.get(key)}
                for key in keys
            },
            "assumptions_diff": assumptions_diff,
            "data_comparability": data_comparability,
            "warnings": warnings,
            "caveats": [
                item.to_dict() if isinstance(item, EvidenceCaveat) else item
                for item in (*left.caveats, *right.caveats)
            ],
            "conclusions": conclusions,
            "next_experiments": next_experiments,
            "limitations": list(dict.fromkeys((*left.limitations, *right.limitations))),
        }
    )
