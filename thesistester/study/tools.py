"""RS6 default-off assistant adapters for Study Runner APIs.

Registered always via ``FEATURE_PARITY_REGISTRY``; every entrypoint refuses when
``[assistant.study_tools] enabled`` is false/missing. Never calls ``run_batch``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib

import yaml

from thesistester.assistant.tools import AssistantToolError
from thesistester.study.execute import cost_hint_lines, prepare_study_expansion, run_study
from thesistester.study.expand import expand_study_to_directory, study_identity_hash
from thesistester.study.ledger import load_ledger
from thesistester.study.promote import promote_study
from thesistester.study.report import report_study
from thesistester.study.schema import (
    StudySpecError,
    load_study_spec,
    normalize_study_spec,
    validate_study_spec,
)

DEFAULT_ASSISTANT_TOML = Path("config/assistant.toml")
APPROVAL_PAYLOAD_KEY = "approval"


@dataclass(frozen=True)
class StudyToolsSettings:
    """Non-secret ``[assistant.study_tools]`` settings (RS6)."""

    enabled: bool = False


class StudyToolsDisabledError(AssistantToolError):
    """Raised when STUDY.* tools are invoked while the feature flag is off."""


def _coerce_enabled_flag(value: Any, *, default: bool = False) -> bool:
    """Parse enable flags fail-closed (mirror ``assistant.voice.settings``)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        return default
    if value is None:
        return default
    return default


def load_study_tools_settings(
    path: str | Path | None = None,
) -> StudyToolsSettings:
    """Load ``[assistant.study_tools]``; missing section → disabled."""
    # Resolve default at call time so tests can patch DEFAULT_ASSISTANT_TOML.
    config_path = Path(path) if path is not None else Path(DEFAULT_ASSISTANT_TOML)
    if not config_path.is_file():
        return StudyToolsSettings(enabled=False)
    try:
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, ValueError, TypeError):
        return StudyToolsSettings(enabled=False)
    if not isinstance(payload, dict):
        return StudyToolsSettings(enabled=False)
    assistant = payload.get("assistant")
    if not isinstance(assistant, dict):
        return StudyToolsSettings(enabled=False)
    section = assistant.get("study_tools")
    if not isinstance(section, dict):
        return StudyToolsSettings(enabled=False)
    return StudyToolsSettings(enabled=_coerce_enabled_flag(section.get("enabled"), default=False))


def ensure_study_tools_enabled(
    settings: StudyToolsSettings | None = None,
) -> StudyToolsSettings:
    """Refuse STUDY.* dispatch when the default-off flag is false."""
    resolved = settings or load_study_tools_settings()
    if not resolved.enabled:
        raise StudyToolsDisabledError(
            "Study assistant tools are disabled. Set "
            "[assistant.study_tools] enabled=true in config/assistant.toml "
            "to opt in, or use the CLI: python -m thesistester study …"
        )
    return resolved


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _optional_bool(value: Any, *, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a boolean.")


def _optional_positive_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be an integer >= 1.")
    return value


def _ensure_within_roots(
    path: str | Path,
    roots: Sequence[Path] | None,
) -> Path:
    """Resolve ``path``; when roots are provided, refuse paths outside them."""
    candidate = Path(path).expanduser().resolve()
    if roots is None:
        return candidate
    resolved_roots = tuple(Path(root).resolve() for root in roots)
    if not resolved_roots:
        raise AssistantToolError("At least one allowed local data root is required.")
    if not any(candidate.is_relative_to(root) for root in resolved_roots):
        raise AssistantToolError("Path is outside the configured local data roots.")
    return candidate


def _resolve_against(base_dir: Path, raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _default_base_directory(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None,
) -> Path:
    """Base for resolving relative StudySpec dataset/output paths (dict inputs)."""
    raw = payload.get("base_directory")
    if isinstance(raw, str) and raw.strip():
        return _ensure_within_roots(raw, data_roots)
    cwd = Path.cwd().resolve()
    if data_roots:
        resolved_roots = tuple(Path(root).resolve() for root in data_roots)
        if any(cwd.is_relative_to(root) for root in resolved_roots):
            return cwd
        return resolved_roots[0]
    return cwd


def _absolutize_study_relative_paths(
    spec: Mapping[str, Any],
    *,
    base_dir: Path,
) -> dict[str, Any]:
    """Pin relative dataset/output paths so temp StudySpec materialization is safe.

    ``run_study`` resolves relative ``dataset.path`` against the StudySpec parent.
    Dict inputs are written under a TemporaryDirectory; without absolutizing,
    bars/output would resolve against that ephemeral temp tree.
    """
    out = dict(spec)
    study = dict(out.get("study") or {})
    dataset = dict(study.get("dataset") or {})
    for key in ("path", "subtimeframe_path"):
        raw = dataset.get(key)
        if not isinstance(raw, (str, Path)):
            continue
        dataset[key] = str(_resolve_against(base_dir, raw))
    study["dataset"] = dataset
    output_dir = study.get("output_dir")
    if isinstance(output_dir, (str, Path)):
        study["output_dir"] = str(_resolve_against(base_dir, output_dir))
    out["study"] = study
    return out


def _ensure_study_spec_paths_within_roots(
    spec: Mapping[str, Any],
    roots: Sequence[Path] | None,
    *,
    relative_base: Path,
) -> None:
    """Refuse Spec-embedded dataset/output paths outside ``data_roots``.

    Mirrors ``AssistantTools._normalize_dataset_paths`` for the study surface:
    absolute paths and ``..`` traversal must not bypass the sandbox.
    """
    if roots is None:
        return
    study = spec.get("study")
    if not isinstance(study, Mapping):
        return
    dataset = study.get("dataset")
    if isinstance(dataset, Mapping):
        for key in ("path", "subtimeframe_path"):
            raw = dataset.get(key)
            if raw is None or not isinstance(raw, (str, Path)):
                continue
            _ensure_within_roots(_resolve_against(relative_base, raw), roots)
    output_dir = study.get("output_dir")
    if isinstance(output_dir, (str, Path)) and str(output_dir).strip():
        _ensure_within_roots(_resolve_against(relative_base, output_dir), roots)


def _resolve_output_dir(
    payload: Mapping[str, Any],
    *,
    required: bool = True,
    data_roots: Sequence[Path] | None = None,
) -> Path | None:
    raw = payload.get("output_dir")
    if raw is None:
        if required:
            raise ValueError("output_dir is required.")
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("output_dir must be a non-empty string.")
    return _ensure_within_roots(raw, data_roots)


def _normalized_spec_from_payload(
    payload: Mapping[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a validated StudySpec from ``study_path`` or ``study_spec``."""
    study_path = payload.get("study_path")
    study_spec = payload.get("study_spec")
    if study_path is not None and study_spec is not None:
        raise ValueError("Provide only one of study_path or study_spec.")
    if isinstance(study_path, str) and study_path.strip():
        return load_study_spec(Path(study_path).expanduser().resolve())
    if isinstance(study_spec, Mapping):
        normalized = normalize_study_spec(dict(study_spec))
        validate_study_spec(normalized)
        if base_dir is not None:
            normalized = _absolutize_study_relative_paths(normalized, base_dir=base_dir)
            # Re-validate after path rewrites (still a StudySpec mapping).
            validate_study_spec(normalized)
        return normalized
    raise ValueError("study_path or study_spec is required.")


def _materialize_study_path(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    """Return a filesystem StudySpec path; materialize dict inputs to a temp YAML."""
    study_path = payload.get("study_path")
    if isinstance(study_path, str) and study_path.strip():
        path = _ensure_within_roots(study_path, data_roots)
        spec = load_study_spec(path)
        _ensure_study_spec_paths_within_roots(
            spec,
            data_roots,
            relative_base=path.parent,
        )
        return path, None
    base_dir = _default_base_directory(payload, data_roots=data_roots)
    normalized = _normalized_spec_from_payload(payload, base_dir=base_dir)
    _ensure_study_spec_paths_within_roots(
        normalized,
        data_roots,
        relative_base=base_dir,
    )
    tmp = tempfile.TemporaryDirectory(prefix="study_tools_")
    path = Path(tmp.name) / "study.yaml"
    path.write_text(
        yaml.safe_dump(normalized, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path, tmp


def study_run_approval_preview(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """In-memory expand preview for confirm gating (no artifact writes).

    ``output_dir`` is required so dict-materialized Specs cannot fall back to a
    relative ``study.output_dir`` resolved against the ephemeral temp parent.
    """
    study_path, tmp = _materialize_study_path(payload, data_roots=data_roots)
    try:
        output_dir = _resolve_output_dir(payload, required=True, data_roots=data_roots)
        assert output_dir is not None
        _spec, expansion, out, _base = prepare_study_expansion(
            study_path,
            output_dir=output_dir,
            write_artifacts=False,
        )
        out = _ensure_within_roots(out, data_roots)
        confirm_above = int(_spec["study"].get("confirm_above_runs", 200))
        return {
            "study_identity_hash": expansion.study_identity_hash,
            "run_count": expansion.run_count,
            "output_dir": str(out.resolve()),
            "confirm_above_runs": confirm_above,
            "needs_confirm": expansion.run_count >= confirm_above,
            "cost_hints": cost_hint_lines(expansion, workers=int(_spec["study"].get("workers", 1))),
        }
    finally:
        if tmp is not None:
            tmp.cleanup()


def study_run_needs_confirm(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> bool:
    """True when STUDY.run must take the orchestrator APPROVAL_REQUIRED path."""
    if not load_study_tools_settings().enabled:
        return False
    try:
        preview = study_run_approval_preview(payload, data_roots=data_roots)
    except (OSError, ValueError, TypeError, StudySpecError, KeyError, AssistantToolError):
        # Fail closed: require confirm when the preview cannot be computed.
        return True
    return bool(preview["needs_confirm"])


def _validate_approval(
    payload: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> None:
    """Enforce bound approval triple; ``confirmed=True`` alone is insufficient."""
    approval = payload.get(APPROVAL_PAYLOAD_KEY)
    if not isinstance(approval, Mapping):
        raise AssistantToolError(
            "STUDY.run over confirm_above_runs requires payload.approval bound to "
            f"(study_identity_hash, run_count, output_dir); got {type(approval).__name__}."
        )
    expected_hash = str(expected["study_identity_hash"])
    expected_count = int(expected["run_count"])
    expected_out = str(Path(str(expected["output_dir"])).resolve())
    got_hash = approval.get("study_identity_hash")
    got_count = approval.get("run_count")
    got_out = approval.get("output_dir")
    try:
        got_count_int = int(got_count) if got_count is not None else None
    except (TypeError, ValueError):
        got_count_int = None
    got_out_resolved = None
    if isinstance(got_out, str) and got_out.strip():
        got_out_resolved = str(Path(got_out).expanduser().resolve())
    if (
        got_hash != expected_hash
        or got_count_int != expected_count
        or got_out_resolved != expected_out
    ):
        raise AssistantToolError(
            "STUDY.run approval does not match the current expansion target "
            f"(expected hash={expected_hash}, run_count={expected_count}, "
            f"output_dir={expected_out})."
        )


def expand_study_capability(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    ensure_study_tools_enabled()
    output_dir = _resolve_output_dir(payload, required=True, data_roots=data_roots)
    assert output_dir is not None
    base_dir = _default_base_directory(payload, data_roots=data_roots)
    study_path = payload.get("study_path")
    source_spec_parent: Path | None = None
    if isinstance(study_path, str) and study_path.strip():
        path = _ensure_within_roots(study_path, data_roots)
        source_spec_parent = path.parent
        normalized = _normalized_spec_from_payload(payload)
        _ensure_study_spec_paths_within_roots(
            normalized,
            data_roots,
            relative_base=path.parent,
        )
    else:
        normalized = _normalized_spec_from_payload(payload, base_dir=base_dir)
        _ensure_study_spec_paths_within_roots(
            normalized,
            data_roots,
            relative_base=base_dir,
        )
    expansion = expand_study_to_directory(
        normalized,
        output_dir,
        source_spec_parent=source_spec_parent,
    )
    workers = int(normalized["study"].get("workers", 1))
    return {
        "run_count": expansion.run_count,
        "study_identity_hash": expansion.study_identity_hash,
        "output_dir": str(output_dir.resolve()),
        "cost_hints": cost_hint_lines(expansion, workers=workers),
        "artifacts": {
            "study_spec": str((output_dir / "study.spec.yaml").resolve()),
            "expansion": str((output_dir / "study.expansion.json").resolve()),
            "experiment": str((output_dir / "experiment.yaml").resolve()),
        },
        "honesty": {
            "descriptive_only": True,
            "multiple_testing": True,
        },
    }


def run_study_capability(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    ensure_study_tools_enabled()
    preview = study_run_approval_preview(payload, data_roots=data_roots)
    if preview["needs_confirm"]:
        _validate_approval(payload, expected=preview)
    force = _optional_bool(payload.get("force"), field="force", default=False)
    workers = _optional_positive_int(payload.get("workers"), field="workers")
    study_path, tmp = _materialize_study_path(payload, data_roots=data_roots)
    try:
        result = run_study(
            study_path,
            output_dir=preview["output_dir"],
            workers=workers,
            confirm=True if preview["needs_confirm"] else False,
            force=force,
        )
    except StudySpecError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if tmp is not None:
            tmp.cleanup()

    ledger = result.get("ledger") or load_ledger(Path(result["output_dir"])) or {}
    cells = ledger.get("cells") or {}
    status_counts: dict[str, int] = {}
    for cell in cells.values():
        status = str((cell or {}).get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "run_count": result["run_count"],
        "executed": result["executed"],
        "workers": result["workers"],
        "study_identity_hash": result["study_identity_hash"],
        "output_dir": result["output_dir"],
        "ledger_path": result["ledger_path"],
        "results_index_path": result["results_index_path"],
        "cost_hints": result.get("cost_hints") or [],
        "ledger_summary": status_counts,
        "honesty": {
            "descriptive_only": True,
            "soft_resume": not force,
            "confirm_bound": bool(preview["needs_confirm"]),
        },
    }


def report_study_capability(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    ensure_study_tools_enabled()
    study_dir = payload.get("study_dir")
    if not isinstance(study_dir, str) or not study_dir.strip():
        raise ValueError("study_dir is required.")
    root = _ensure_within_roots(study_dir, data_roots)
    try:
        result = report_study(root)
    except Exception as exc:  # StudyReportError is ValueError subclass
        raise ValueError(str(exc)) from exc
    return {
        "study_name": result.study_name,
        "primary_metric": result.primary_metric,
        "min_trades": result.min_trades,
        "multiple_testing": result.multiple_testing,
        "best_cell_suppressed": result.best_cell_suppressed,
        "ranked_count": int(len(result.ranked)),
        "low_n_count": int(len(result.low_n)),
        "unresolved_count": int(len(result.unresolved)),
        "paths": {key: str(path.resolve()) for key, path in result.paths.items()},
        "honesty": {
            "descriptive_only": True,
            "multiple_testing": result.multiple_testing,
            "best_cell_suppressed": result.best_cell_suppressed,
        },
    }


def promote_study_capability(
    payload: Mapping[str, Any],
    *,
    data_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    ensure_study_tools_enabled()
    study_dir = payload.get("study_dir")
    output = payload.get("output")
    if not isinstance(study_dir, str) or not study_dir.strip():
        raise ValueError("study_dir is required.")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("output is required.")
    top_n = payload.get("top_n", 10)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be an integer >= 1.")
    metric = payload.get("metric")
    if metric is not None and (not isinstance(metric, str) or not metric.strip()):
        raise ValueError("metric must be a non-empty string when provided.")
    force = _optional_bool(payload.get("force"), field="force", default=False)
    try:
        result = promote_study(
            _ensure_within_roots(study_dir, data_roots),
            output=_ensure_within_roots(output, data_roots),
            top_n=top_n,
            metric=metric,
            force=force,
        )
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return {
        "study_name": result.study_name,
        "output_path": str(result.output_path.resolve()),
        "cell_count": result.cell_count,
        "selected_run_names": list(result.selected_run_names),
        "primary_metric": result.primary_metric,
        "top_n": result.top_n,
        "source_study_dir": str(result.source_study_dir.resolve()),
        "honesty": {
            "draft_only": True,
            "does_not_execute": True,
        },
    }


# Keep identity helper import used for re-exports / tests.
__all__ = [
    "APPROVAL_PAYLOAD_KEY",
    "StudyToolsDisabledError",
    "StudyToolsSettings",
    "ensure_study_tools_enabled",
    "expand_study_capability",
    "load_study_tools_settings",
    "promote_study_capability",
    "report_study_capability",
    "run_study_capability",
    "study_identity_hash",
    "study_run_approval_preview",
    "study_run_needs_confirm",
]
