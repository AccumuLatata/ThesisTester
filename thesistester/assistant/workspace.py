"""Presentation helpers for the Research Assistant Streamlit workspace.

These helpers own thesis-scoped session-state contracts and structured draft
merges. They never execute research, touch the filesystem, or call tools.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm import is_draft_channel_message
from thesistester.assistant.thesis_compiler import (
    normalize_setup_level_selection,
    normalize_walk_forward_controls,
)
from thesistester.config import TIMEZONE_OPTIONS as _CONFIG_TIMEZONE_OPTIONS
from thesistester.levels.prev30m_vwap import prev30m_price_column_names
from thesistester.setup import SUGGESTED_DEFAULT_LEVELS

# Additive Streamlit staging keys owned by the Research Assistant page.
ASSISTANT_SESSION_KEYS: tuple[str, ...] = (
    "assistant_selected_thesis_id",
    "assistant_draft_prompt",
    "assistant_draft_choices",
    "assistant_conversation_ids",
    "assistant_hydrated_conversation_id",
    "assistant_validated_run_spec",
    "assistant_run_explanations",
    "assistant_llm_run_explanations",
    "assistant_llm_attempts",
    "assistant_run_reports",
    "assistant_run_artifacts",
    "assistant_run_comparisons",
    "assistant_portfolio_analyses",
    "assistant_results_qa_drafts",
    "assistant_product_help_draft",
    "assistant_focused_run_id",
    "assistant_results_qa_deep_link",
    "assistant_results_qa_force_expand",
    "assistant_bundle_handoff",
    "assistant_flash",
    # VA-4 push-to-talk staging (ephemeral; not a second evidence store).
    "assistant_voice_results_sessions",
    "assistant_voice_help_session_id",
    "assistant_voice_last_turn",
    "assistant_voice_playback",
    # Voice UI controls (session widgets; persisted via override file).
    "assistant_voice_ui_enabled",
    "assistant_voice_ui_mode",
)

# Cleared whenever the active thesis changes so drafts/validation/handoff
# staging cannot leak across theses.
THESIS_SCOPED_STAGING_KEYS: tuple[str, ...] = (
    "assistant_draft_prompt",
    "assistant_draft_choices",
    "assistant_hydrated_conversation_id",
    "assistant_validated_run_spec",
    "assistant_results_qa_drafts",
    "assistant_product_help_draft",
    "assistant_focused_run_id",
    "assistant_results_qa_deep_link",
    "assistant_results_qa_force_expand",
    "assistant_bundle_handoff",
    "assistant_flash",
    "assistant_voice_results_sessions",
    "assistant_voice_help_session_id",
    "assistant_voice_last_turn",
    "assistant_voice_playback",
)

# Streamlit expander widget keys (1.55+) controlled when forcing RQ-4 open.
ASSISTANT_ADVANCED_EXPANDER_KEY: str = "ra-advanced-expander"


def linked_run_expander_key(run_id: str) -> str:
    """Session-state key for a Linked research-run expander."""
    return f"ra-run-expander-{run_id}"


# Human labels for persisted SpecVersion.status values shown in the UI.
SPEC_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "needs_clarification": "Needs clarification",
    "ready_for_confirmation": "Ready to confirm",
    "confirmed": "Confirmed — can run",
}

RESEARCH_WORKFLOW_STEPS: tuple[str, ...] = (
    "Apply structured controls — stages draft choices in this session only; does not create a specification version.",
    "Draft research plan (optional) — persists a specification version from the current draft.",
    "Validate executable RunSpec, then Confirm validated RunSpec under Plan review.",
    "Open a Confirmed specification and click Run confirmed research.",
)

SETUP_TRIGGER_OPTIONS: tuple[str, ...] = ("touch", "reject", "break", "reclaim", "3c")
EXPOSURE_POLICIES: tuple[str, ...] = (
    "allow_all",
    "single_position",
    "single_direction",
    "single_setup",
)
INTRABAR_MODELS: tuple[str, ...] = (
    "sl_first",
    "path_open_proximity",
    "subtimeframe",
    "subtimeframe_conservative",
)
RANKING_METRICS: tuple[str, ...] = ("expectancy_r", "total_r", "profit_factor", "win_rate")
INSTRUMENTS: tuple[str, ...] = ("ES", "NQ", "MES", "MNQ")
TIMEZONE_OPTIONS: tuple[str, ...] = tuple(_CONFIG_TIMEZONE_OPTIONS)
SMA_TIMEFRAMES: tuple[str, ...] = ("1min", "5min", "15min", "30min", "1h", "4h")
INDICATOR_LENGTH_OPTIONS: tuple[int, ...] = (9, 20, 21, 50, 100, 200)
OPENING_RANGE_MINUTES_OPTIONS: tuple[int, ...] = (5, 15, 30)
VWAP_WINDOW_OPTIONS: tuple[str, ...] = ("15min", "30min", "1h", "4h")
POC_WINDOW_OPTIONS: tuple[str, ...] = ("30min", "1h", "4h")
CONFLUENCE_MODES: tuple[str, ...] = ("global_cluster", "anchor_rules")
NAKED_REQUIREMENTS: tuple[str, ...] = ("any", "all")
DIRECTIONS: tuple[str, ...] = ("both", "long", "short")
TRIGGER_TIMEFRAMES: tuple[str, ...] = ("base", "1min", "5min", "15min", "30min")
WINDOW_MODES: tuple[str, ...] = ("rolling", "anchored")
OVERLAP_POLICIES: tuple[str, ...] = ("reject", "first", "last")
FOLD_MODES: tuple[str, ...] = ("sessions", "bars")
WFA_MATRIX_METRICS: tuple[str, ...] = (
    "median_test_expectancy_r",
    "median_retention_ratio_expectancy",
    "stitched_oos_total_r",
    "oos_profitable_fold_rate",
)
# Static session/profile/opt-in level names used when no Levels dataframe is loaded.
SESSION_LEVEL_CATALOG: tuple[str, ...] = (
    "ONH",
    "ONL",
    "pONH",
    "pONL",
    "AsiaHigh",
    "AsiaLow",
    "LondonHigh",
    "LondonLow",
    "OR_High",
    "OR_Low",
    "RTH_Open",
    "pRTH_Open",
    "pRTH_High",
    "pRTH_Low",
    "prevSettlement",
    "dOpen",
    "wOpen",
    "mOpen",
    "pdOpen",
    "pwOpen",
    "pmOpen",
    "pdHigh",
    "pdLow",
    "pwHigh",
    "pwLow",
    "pmHigh",
    "pmLow",
    "pdEQ",
    "pwEQ",
    "pmEQ",
    "pdPOC",
    "dVWAP_RTH",
    "dVWAP",
    "prev30mVWAP",
    "APOC",
    "pAPOC",
    "dSinglePrint_30m_NearestAbove",
    "dSinglePrint_30m_NearestBelow",
    "pSinglePrint_30m_NearestAbove",
    "pSinglePrint_30m_NearestBelow",
    "Pivot_1min_High",
    "Pivot_1min_Low",
    "Pivot_5min_High",
    "Pivot_5min_Low",
    "Pivot_30min_High",
    "Pivot_30min_Low",
    "Pivot_4h_High",
    "Pivot_4h_Low",
)


def thesis_has_running_run(runs: Iterable[Any]) -> bool:
    """True when any thesis research run is mid-compute (blocks VA-4 mic)."""
    return any(getattr(run, "status", None) == "running" for run in runs)


def read_audio_input_bytes(audio_value: Any) -> bytes | None:
    """Normalize Streamlit ``st.audio_input`` / UploadedFile-like values to bytes."""
    if audio_value is None:
        return None
    if isinstance(audio_value, (bytes, bytearray)):
        return bytes(audio_value) if audio_value else None
    read = getattr(audio_value, "read", None)
    if callable(read):
        try:
            data = read()
        except Exception:
            data = None
        if isinstance(data, (bytes, bytearray)) and data:
            return bytes(data)
    getvalue = getattr(audio_value, "getvalue", None)
    if callable(getvalue):
        try:
            data = getvalue()
        except Exception:
            data = None
        if isinstance(data, (bytes, bytearray)) and data:
            return bytes(data)
    return None


def init_assistant_session_state(session_state: MutableMapping[str, Any]) -> None:
    """Ensure every documented assistant_* staging key exists."""
    defaults: dict[str, Any] = {
        "assistant_selected_thesis_id": None,
        "assistant_draft_prompt": "",
        "assistant_draft_choices": {},
        "assistant_conversation_ids": {},
        "assistant_hydrated_conversation_id": None,
        "assistant_validated_run_spec": None,
        "assistant_run_explanations": {},
        "assistant_llm_run_explanations": {},
        "assistant_llm_attempts": {},
        "assistant_run_reports": {},
        "assistant_run_artifacts": {},
        "assistant_run_comparisons": {},
        "assistant_portfolio_analyses": {},
        "assistant_results_qa_drafts": {},
        "assistant_product_help_draft": "",
        "assistant_focused_run_id": None,
        "assistant_results_qa_deep_link": False,
        "assistant_results_qa_force_expand": False,
        "assistant_bundle_handoff": None,
        "assistant_flash": None,
        "assistant_voice_results_sessions": {},
        "assistant_voice_help_session_id": None,
        "assistant_voice_last_turn": None,
        "assistant_voice_playback": None,
        # Seeded from load_voice_settings() on first Voice controls render.
        "assistant_voice_ui_enabled": False,
        "assistant_voice_ui_mode": "push_to_talk",
    }
    for key, value in defaults.items():
        session_state.setdefault(key, deepcopy(value) if isinstance(value, (dict, list)) else value)


def set_assistant_flash(
    session_state: MutableMapping[str, Any],
    *,
    level: str,
    message: str,
) -> None:
    """Stage a one-shot UI notice that survives the next ``st.rerun()``."""
    if level not in {"success", "info", "warning", "error"}:
        raise ValueError("flash level must be success, info, warning, or error.")
    text = str(message).strip()
    if not text:
        raise ValueError("flash message must be a non-empty string.")
    session_state["assistant_flash"] = {"level": level, "message": text}


def consume_assistant_flash(
    session_state: MutableMapping[str, Any],
) -> dict[str, str] | None:
    """Pop and return the staged flash payload, if any."""
    flash = session_state.get("assistant_flash")
    session_state["assistant_flash"] = None
    if not isinstance(flash, Mapping):
        return None
    level = flash.get("level")
    message = flash.get("message")
    if level not in {"success", "info", "warning", "error"}:
        return None
    if not isinstance(message, str) or not message.strip():
        return None
    return {"level": str(level), "message": message.strip()}


def format_assistant_draft_reply(clarifications: Sequence[str] | None = None) -> str:
    """Build the user-visible assistant chat body for a thesis-draft turn.

    Chat persists structured ``clarifications`` separately for Plan review /
    audit consumers; this helper folds them into readable ``content`` so the
    Streamlit chat bubble is never an opaque status line alone.
    """
    items = [
        str(item).strip()
        for item in (clarifications or ())
        if isinstance(item, str) and str(item).strip()
    ]
    if items:
        bullets = "\n".join(f"- {item}" for item in items)
        return (
            "I need a few clarifications before this thesis draft can run:\n"
            f"{bullets}\n\n"
            "Answer here, or fill Structured execution controls below, then "
            "Draft research plan."
        )
    return (
        "Drafted non-executing research choices. Review Structured execution "
        "controls, then Draft research plan when ready."
    )


def _clarification_visible_in_content(item: str, content: str) -> bool:
    """True when ``item`` is already rendered as a clarification in ``content``.

    Uses bullet/line presence rather than raw substring checks so a short
    clarification like ``research choices`` is not treated as satisfied by the
    opaque legacy status line ``Drafted non-executing research choices.``.
    """
    if not item or not content:
        return False
    if f"- {item}" in content:
        return True
    if content == item:
        return True
    return f"\n{item}\n" in f"\n{content}\n"


def format_chat_message_body(message: Mapping[str, Any]) -> str:
    """Return the text shown inside one Assistant chat bubble.

    Prefer persisted ``content`` when it already surfaces every structured
    clarification. When older turns stored clarifications only on the structured
    field (pre-UX fix), or when ``content`` is an opaque status line that only
    accidentally overlaps a short clarification substring, fold missing items
    into the body so Assistant chat never drops structured questions.
    """
    if not isinstance(message, Mapping):
        return ""
    content = str(message.get("content") or "").strip()
    clarifications = message.get("clarifications")
    items: list[str] = []
    if isinstance(clarifications, Sequence) and not isinstance(clarifications, (str, bytes)):
        items = [
            str(item).strip()
            for item in clarifications
            if isinstance(item, str) and str(item).strip()
        ]
    if not items:
        return content
    # New turns persist clarifications inside content via
    # format_assistant_draft_reply — trust that body when complete.
    if content and all(_clarification_visible_in_content(item, content) for item in items):
        return content
    missing = [item for item in items if not _clarification_visible_in_content(item, content)]
    if content and missing:
        bullets = "\n".join(f"- {item}" for item in missing)
        return f"{content}\n\nClarifications still needed:\n{bullets}"
    return format_assistant_draft_reply(items)


def chat_message_display_role(message: Mapping[str, Any]) -> str | None:
    """Map a persisted conversation message to a Streamlit chat role.

    Tool/audit lines are omitted from the friendly chat (they remain in
    Conversation audit). Non-draft channel messages (``results_qa``,
    ``product_help``, …) are also omitted so thesis chat stays draft-only.
    Returns ``None`` when the message should not render as a chat bubble.
    """
    if not isinstance(message, Mapping):
        return None
    if not is_draft_channel_message(message):
        return None
    role = str(message.get("role") or "").strip().lower()
    if role in {"user", "human"}:
        return "user"
    if role in {"assistant", "ai"}:
        return "assistant"
    return None


def format_spec_status(status: str | None) -> str:
    """Return a user-facing label for a persisted specification status."""
    key = str(status or "").strip()
    return SPEC_STATUS_LABELS.get(key, key or "unknown")


def spec_status_next_step(status: str | None) -> str:
    """Return the concrete next action for a listed specification version."""
    key = str(status or "").strip()
    if key == "needs_clarification":
        return (
            "Resolve clarifications in structured controls or chat, then Draft research plan again."
        )
    if key == "ready_for_confirmation":
        return (
            "This version is not waiting on a hidden button. "
            "Under Plan review: Validate executable RunSpec, then click Confirm validated RunSpec."
        )
    if key == "confirmed":
        return (
            "Click Run confirmed research below to start compute for this immutable specification."
        )
    if key == "draft":
        return "Draft or validate from Plan review to advance this specification."
    return "Use Plan review to validate and confirm before running."


def clear_failed_llm_run_explanation(session_state: MutableMapping[str, Any], run_id: str) -> None:
    """Drop cached LLM paraphrase after a failed regen for ``run_id``.

    Fail-closed: a grounding/provider/config error must not leave a prior
    summary/claims visible for the same run.
    """
    if not isinstance(run_id, str) or not run_id:
        return
    explanations = session_state.get("assistant_llm_run_explanations")
    if isinstance(explanations, dict):
        explanations.pop(run_id, None)
    attempts = session_state.get("assistant_llm_attempts")
    if isinstance(attempts, dict):
        attempts.pop(run_id, None)


def select_thesis(session_state: MutableMapping[str, Any], thesis_id: str) -> bool:
    """Switch the active thesis and clear scoped staging state.

    Returns True when the selection changed.
    """
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("thesis_id must be a non-empty string.")
    if session_state.get("assistant_selected_thesis_id") == thesis_id:
        return False
    session_state["assistant_selected_thesis_id"] = thesis_id
    clear_thesis_scoped_state(session_state)
    return True


def clear_thesis_scoped_state(session_state: MutableMapping[str, Any]) -> None:
    """Drop draft/validation/hydration/handoff staging that must not cross theses."""
    session_state["assistant_draft_prompt"] = ""
    session_state["assistant_draft_choices"] = {}
    session_state["assistant_hydrated_conversation_id"] = None
    session_state["assistant_validated_run_spec"] = None
    session_state["assistant_results_qa_drafts"] = {}
    session_state["assistant_product_help_draft"] = ""
    session_state["assistant_focused_run_id"] = None
    session_state["assistant_results_qa_deep_link"] = False
    session_state["assistant_results_qa_force_expand"] = False
    session_state["assistant_bundle_handoff"] = None
    session_state["assistant_flash"] = None
    session_state["assistant_voice_results_sessions"] = {}
    session_state["assistant_voice_help_session_id"] = None
    session_state["assistant_voice_last_turn"] = None
    session_state["assistant_voice_playback"] = None
    # Ephemeral Streamlit widget keys + deferred-clear flags for Discuss/Help
    # text inputs. If left behind, ``if key not in session_state`` hydration
    # would revive cleared drafts, or a stale clear flag would wipe the next
    # conversation's input.
    session_state.pop("assistant_clear_product_help_input", None)
    for key in list(session_state.keys()):
        if isinstance(key, str) and (
            key.startswith("results-qa-input-")
            or key.startswith("product-help-input")
            or key.startswith("assistant_clear_results-qa-input-")
            or key.startswith("ra-run-expander-")
            or key.startswith("voice-results-audio-")
            or key.startswith("voice-help-audio")
            or key == ASSISTANT_ADVANCED_EXPANDER_KEY
        ):
            del session_state[key]


def apply_consumed_classic_focus(
    session_state: MutableMapping[str, Any],
    *,
    run_id: str | None,
    channel: str | None,
) -> tuple[bool, str | None]:
    """Stage Assistant UI for a consumed classic focus pair (RQ-4).

    ``results_qa`` deep-links persist ``assistant_results_qa_deep_link`` +
    ``assistant_focused_run_id`` across Streamlit reruns (one-shot classic keys
    are already cleared by ``consume_classic_focus``). Returns
    ``(expand_results_qa, expand_run_id)`` for Advanced / Linked-run expanders.
    Legacy ``channel is None`` only records the focused run id for that render's
    banner path — it does not keep Advanced forced open.

    On a fresh ``results_qa`` consume, also sets
    ``assistant_results_qa_force_expand`` so keyed Streamlit expanders reopen
    even when the user previously collapsed Advanced.
    """
    init_assistant_session_state(session_state)
    cleaned = run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
    if cleaned is not None:
        session_state["assistant_focused_run_id"] = cleaned
    if channel == "results_qa" and cleaned is not None:
        session_state["assistant_results_qa_deep_link"] = True
        session_state["assistant_results_qa_force_expand"] = True
    if not session_state.get("assistant_results_qa_deep_link"):
        return False, None
    focused = session_state.get("assistant_focused_run_id")
    if isinstance(focused, str) and focused.strip():
        return True, focused.strip()
    return False, None


def force_results_qa_expanders_open(
    session_state: MutableMapping[str, Any],
    *,
    run_id: str | None,
) -> None:
    """One-shot: set keyed expander widget state open (Streamlit >= 1.55)."""
    if not session_state.pop("assistant_results_qa_force_expand", False):
        return
    session_state[ASSISTANT_ADVANCED_EXPANDER_KEY] = True
    if isinstance(run_id, str) and run_id.strip():
        session_state[linked_run_expander_key(run_id.strip())] = True


def active_bundle_handoff(
    session_state: Mapping[str, Any], *, thesis_id: str | None
) -> dict[str, Any] | None:
    """Return the staged handoff only when it belongs to the active thesis."""
    handoff = session_state.get("assistant_bundle_handoff")
    if not isinstance(handoff, dict) or not handoff.get("run_id"):
        return None
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        return None
    if handoff.get("thesis_id") != thesis_id:
        return None
    return handoff


def latest_unresolved_assumptions(specs: Iterable[Any]) -> tuple[str, ...]:
    """Return clarifications only when the newest specification still needs them.

    Older ``needs_clarification`` versions are ignored once a later ready or
    confirmed specification exists, so plan review never shows stale warnings.
    """
    ordered = list(specs)
    if not ordered:
        return ()
    try:
        ordered.sort(key=lambda spec: int(getattr(spec, "version", 0) or 0))
    except (TypeError, ValueError):
        pass
    latest = ordered[-1]
    if getattr(latest, "status", None) != "needs_clarification":
        return ()
    assumptions = getattr(latest, "unresolved_assumptions", ()) or ()
    return tuple(str(item) for item in assumptions)


def safe_int(value: Any, default: int) -> int:
    """Coerce widget defaults to int without raising on malformed draft values."""
    if isinstance(value, bool) or value is None:
        return int(default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and float(value).is_integer():
            return int(value)
        return int(default)
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return int(default)
    if math.isfinite(parsed) and parsed.is_integer():
        return int(parsed)
    return int(default)


def safe_float(value: Any, default: float) -> float:
    """Coerce widget defaults to float without raising on malformed draft values."""
    if isinstance(value, bool) or value is None:
        return float(default)
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else float(default)
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def invalidate_validation(session_state: MutableMapping[str, Any]) -> None:
    """Clear a staged validated RunSpec after draft edits."""
    session_state["assistant_validated_run_spec"] = None


def parse_positive_number_list(raw: str) -> list[float]:
    """Parse one or more positive comma-separated numbers."""
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    if not values or any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Provide one or more positive comma-separated values.")
    return values


def parse_positive_int_list(raw: str) -> list[int]:
    """Parse one or more positive comma-separated integers."""
    numbers = parse_positive_number_list(raw)
    values: list[int] = []
    for value in numbers:
        if not float(value).is_integer():
            raise ValueError("Provide one or more positive comma-separated integers.")
        values.append(int(value))
    return values


def parse_json_choices(raw: str) -> dict[str, Any]:
    """Parse Advanced JSON audit edits into a choices object."""
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Choices must be a JSON object.")
    return parsed


def require_run_bundle_hash(provenance: Mapping[str, Any]) -> str:
    """Return the completed-run canonical hash or fail closed."""
    expected_hash = provenance.get("canonical_bundle_hash")
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        raise ValueError("Completed run is missing canonical bundle hash provenance.")
    return expected_hash.strip()


def evidence_packet_from_payload(payload: Mapping[str, Any]) -> EvidencePacket:
    """Rebuild an EvidencePacket from a completed BUNDLE.import evidence payload."""
    evidence = payload.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("Evidence payload is missing.")
    return EvidencePacket.from_dict(evidence)


def merge_execution_controls(
    choices: Mapping[str, Any],
    *,
    dataset_path: str,
    instrument: str,
    source_timezone: str,
    subtimeframe_path: str,
    stop_loss_ticks: int,
    take_profit_ticks: int,
    commission_per_side: float,
    slippage_ticks: float,
    exposure_policy: str,
    intrabar_model: str,
    flat_by_session_close: bool,
    session_close_time: str,
    session_timezone: str,
    no_new_entries_after: str,
    max_holding_bars: int | None,
    allow_same_bar_exit: bool,
    cooldown_bars_after_exit: int,
) -> dict[str, Any]:
    """Merge structured execution controls into staged research choices."""
    current = deepcopy(dict(choices))
    dataset = dict(current.get("dataset") or {})
    backtest = dict(current.get("backtest") or {})
    setup = current.get("setup")
    dataset.update(
        {
            "path": dataset_path,
            "instrument": instrument,
            "source_timezone": source_timezone,
        }
    )
    if subtimeframe_path.strip():
        dataset["subtimeframe_path"] = subtimeframe_path.strip()
    else:
        dataset.pop("subtimeframe_path", None)
    backtest.update(
        {
            "stop_loss_ticks": int(stop_loss_ticks),
            "take_profit_ticks": int(take_profit_ticks),
            "commission_per_side": float(commission_per_side),
            "slippage_ticks": float(slippage_ticks),
            "exposure_policy": exposure_policy,
            "intrabar_model": intrabar_model,
            "flat_by_session_close": bool(flat_by_session_close),
            "session_close_time": session_close_time or None,
            "session_timezone": session_timezone or None,
            "no_new_entries_after": no_new_entries_after or None,
            "max_holding_bars": max_holding_bars,
            "allow_same_bar_exit": bool(allow_same_bar_exit),
            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
        }
    )
    current["dataset"] = dataset
    current["backtest"] = backtest
    if isinstance(setup, Mapping):
        current["setup"] = {**deepcopy(dict(setup)), "instrument": instrument}
    return current


def merge_validation_controls(
    choices: Mapping[str, Any],
    *,
    n_bootstrap: int,
    n_permutations: int,
    random_state: int,
    monte_carlo_enabled: bool,
    monte_carlo_simulations: int,
    excursion_enabled: bool,
    overfitting_enabled: bool,
    noise_enabled: bool,
    sensitivity_enabled: bool,
    min_trades_soft: int,
    min_trades_hard: int,
) -> dict[str, Any]:
    """Merge structured validation controls into staged research choices."""
    current = deepcopy(dict(choices))
    validation = dict(current.get("validation") or {})
    validation.update(
        {
            "n_bootstrap": int(n_bootstrap),
            "n_permutations": int(n_permutations),
            "random_state": int(random_state),
            "min_trades_soft": int(min_trades_soft),
            "min_trades_hard": int(min_trades_hard),
            "monte_carlo": {
                **dict(validation.get("monte_carlo") or {}),
                "enabled": bool(monte_carlo_enabled),
                "n_simulations": int(monte_carlo_simulations),
                "random_state": int(random_state),
            },
            "excursion": {
                **dict(validation.get("excursion") or {}),
                "enabled": bool(excursion_enabled),
            },
            "overfitting": {
                **dict(validation.get("overfitting") or {}),
                "enabled": bool(overfitting_enabled),
                "random_state": int(random_state),
            },
            "noise": {
                **dict(validation.get("noise") or {}),
                "enabled": bool(noise_enabled),
                "random_state": int(random_state),
            },
            "sensitivity": {
                **dict(validation.get("sensitivity") or {}),
                "enabled": bool(sensitivity_enabled),
                "random_state": int(random_state),
            },
        }
    )
    current["validation"] = validation
    return current


def merge_grid_controls(
    choices: Mapping[str, Any],
    *,
    enabled: bool,
    stop_values_raw: str,
    target_values_raw: str,
    ranking_metric: str,
    min_trades: int,
    max_grid_cells: int,
) -> dict[str, Any]:
    """Merge structured grid controls into staged research choices."""
    current = deepcopy(dict(choices))
    if not enabled:
        current["grid"] = {"enabled": False}
        return current
    grid = dict(current.get("grid") or {})
    grid.update(
        {
            "enabled": True,
            "stop_loss_ticks_values": parse_positive_number_list(stop_values_raw),
            "take_profit_ticks_values": parse_positive_number_list(target_values_raw),
            "ranking_metric": ranking_metric,
            "min_trades": int(min_trades),
            "max_grid_cells": int(max_grid_cells),
        }
    )
    current["grid"] = grid
    return current


def merge_walk_forward_controls(
    choices: Mapping[str, Any],
    *,
    enabled: bool,
    fold_mode: str,
    window_mode: str,
    overlap_policy: str,
    train_size: int,
    test_size: int,
    step_size: int,
    ranking_metric: str,
    min_train_trades: int,
    stop_values_raw: str,
    target_values_raw: str,
    matrix_enabled: bool,
    matrix_train_raw: str,
    matrix_test_raw: str,
    matrix_metric: str,
    max_matrix_cells: int,
    otf_history_policy: str = "fold_local",
) -> dict[str, Any]:
    """Merge structured walk-forward controls into staged research choices."""
    current = deepcopy(dict(choices))
    walk_forward = normalize_walk_forward_controls(
        enabled=enabled,
        fold_mode=fold_mode,
        window_mode=window_mode,
        overlap_policy=overlap_policy,
        otf_history_policy=otf_history_policy,
        train_sessions=train_size if fold_mode == "sessions" else 20,
        test_sessions=test_size if fold_mode == "sessions" else 5,
        step_sessions=step_size if fold_mode == "sessions" else 5,
        train_bars=train_size if fold_mode == "bars" else 500,
        test_bars=test_size if fold_mode == "bars" else 100,
        step_bars=step_size if fold_mode == "bars" else 100,
        ranking_metric=ranking_metric,
        min_train_trades=min_train_trades,
        stop_loss_ticks_values=parse_positive_number_list(stop_values_raw)
        if enabled and stop_values_raw.strip()
        else None,
        take_profit_ticks_values=parse_positive_number_list(target_values_raw)
        if enabled and target_values_raw.strip()
        else None,
    )
    # WFA matrix is session-scoped only (parity with pages/10_Validation.py).
    if enabled and matrix_enabled and fold_mode == "sessions":
        walk_forward["matrix"] = {
            "enabled": True,
            "train_session_values": parse_positive_int_list(matrix_train_raw),
            "test_session_values": parse_positive_int_list(matrix_test_raw),
            "matrix_metric": matrix_metric,
            "max_matrix_cells": int(max_matrix_cells),
        }
    elif enabled:
        walk_forward["matrix"] = {"enabled": False}
    current["walk_forward"] = walk_forward
    return current


def _normalize_int_selection(values: Any, *, allow_empty: bool) -> list[int]:
    if isinstance(values, str):
        text = values.strip()
        if not text:
            if allow_empty:
                return []
            raise ValueError("Provide one or more positive comma-separated integers.")
        return parse_positive_int_list(text)
    if isinstance(values, Iterable) and not isinstance(values, (bytes, bytearray)):
        parsed = [safe_int(item, 0) for item in values]
        cleaned = [value for value in parsed if value > 0]
        if not cleaned and not allow_empty:
            raise ValueError("Provide one or more positive integers.")
        return cleaned
    raise ValueError("Integer selections must be a list or comma-separated string.")


def coerce_window_label(value: Any) -> str | None:
    """Normalize a VWAP/POC window to a Levels catalog label.

    Legacy drafts may still store bare minute integers (from the old
    ``parse_positive_int_list`` merge). Those become ``\"30min\"`` / ``\"1h\"``
    so confluence names match computed columns (``VWAP_rolling_30min``).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
        if minutes <= 0:
            return None
        if minutes % 60 == 0:
            return f"{minutes // 60}h"
        return f"{minutes}min"
    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return None
    if text.isdigit():
        return coerce_window_label(int(text))
    return text


def _normalize_window_selection(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_items: list[Any] = [item for item in values.split(",") if item.strip()]
    elif isinstance(values, Iterable) and not isinstance(values, (bytes, bytearray)):
        raw_items = list(values)
    else:
        raise ValueError("Window selections must be a list or comma-separated string.")
    labels: list[str] = []
    for item in raw_items:
        label = coerce_window_label(item)
        if label and label not in labels:
            labels.append(label)
    return labels


def merge_level_controls(
    choices: Mapping[str, Any],
    *,
    session_vwap_enabled: bool,
    opening_range_minutes: int,
    sma_lengths_raw: Any,
    sma_timeframes: list[str],
    ema_lengths_raw: Any,
    ema_timeframes: list[str],
    vwap_windows_raw: Any,
    poc_windows_raw: Any,
) -> dict[str, Any]:
    """Merge structured level controls into staged research choices."""
    current = deepcopy(dict(choices))
    levels = dict(current.get("levels") or {})
    levels.update(
        {
            "session_vwap_enabled": bool(session_vwap_enabled),
            "opening_range_minutes": int(opening_range_minutes),
            "sma_lengths": _normalize_int_selection(sma_lengths_raw, allow_empty=False),
            "sma_timeframes": list(sma_timeframes) or ["30min"],
            "ema_lengths": _normalize_int_selection(ema_lengths_raw, allow_empty=True),
            "ema_timeframes": list(ema_timeframes),
            "vwap_windows": _normalize_window_selection(vwap_windows_raw),
            "poc_windows": _normalize_window_selection(poc_windows_raw),
        }
    )
    current["levels"] = levels
    return current


def merge_setup_controls(
    choices: Mapping[str, Any],
    *,
    setup_name: str,
    description: str,
    selected_levels_raw: Any,
    trigger: str,
    direction: str,
    tolerance_ticks: float,
    min_confluences: int,
    max_confluences: int,
    naked_only: bool,
    naked_requirement: str,
    trigger_timeframe: str,
    confluence_mode: str,
    anchor_level: str,
    min_valid_confluences: int,
) -> dict[str, Any]:
    """Merge structured setup/confluence controls into staged research choices."""
    current = deepcopy(dict(choices))
    setup = dict(current.get("setup") or {})
    levels, clamped_min, clamped_max = normalize_setup_level_selection(
        selected_levels_raw,
        previous_min=min_confluences,
        previous_max=max_confluences,
    )
    instrument = str(
        (current.get("dataset") or {}).get("instrument") or setup.get("instrument") or "ES"
    )
    current["setup"] = {
        **setup,
        "name": setup_name,
        "description": description,
        "instrument": instrument,
        "selected_levels": levels,
        "tolerance_ticks": float(tolerance_ticks),
        "min_confluences": clamped_min,
        "max_confluences": clamped_max,
        "naked_only": bool(naked_only),
        "naked_requirement": naked_requirement,
        "trigger": trigger,
        "trigger_timeframe": trigger_timeframe,
        "direction": direction,
        "confluence_mode": confluence_mode,
        "anchor_level": str(anchor_level or "").strip() or None,
        "confluence_rules": list(setup.get("confluence_rules") or []),
        "min_valid_confluences": int(min_valid_confluences),
        "trigger_params": dict(setup.get("trigger_params") or {}),
        "otf_filter": setup.get("otf_filter"),
    }
    return current


def build_plan_review(
    *,
    thesis_name: str,
    choices: Mapping[str, Any],
    validated_spec: Mapping[str, Any] | None,
    unresolved_assumptions: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a presentation-only plan-review card payload."""
    setup = choices.get("setup") if isinstance(choices.get("setup"), Mapping) else {}
    backtest = choices.get("backtest") if isinstance(choices.get("backtest"), Mapping) else {}
    dataset = choices.get("dataset") if isinstance(choices.get("dataset"), Mapping) else {}
    ready = validated_spec is not None and not unresolved_assumptions
    if unresolved_assumptions:
        next_action = "Resolve clarifications before confirming the validated RunSpec."
    elif validated_spec is None:
        next_action = "Click Validate executable RunSpec. Confirm appears here only after a successful validate."
    elif ready:
        next_action = (
            "Click Confirm validated RunSpec, then open the new Confirmed specification and run it."
        )
    else:
        next_action = "Validate again after editing draft choices."
    return {
        "thesis_name": thesis_name,
        "ready_for_confirmation": ready,
        "next_action": next_action,
        "dataset_path": dataset.get("path"),
        "instrument": dataset.get("instrument") or setup.get("instrument"),
        "selected_levels": list(setup.get("selected_levels") or []),
        "trigger": setup.get("trigger"),
        "direction": setup.get("direction"),
        "tolerance_ticks": setup.get("tolerance_ticks"),
        "exposure_policy": backtest.get("exposure_policy"),
        "intrabar_model": backtest.get("intrabar_model"),
        "has_grid": isinstance(choices.get("grid"), Mapping)
        and bool((choices.get("grid") or {}).get("enabled", True)),
        "has_validation": isinstance(choices.get("validation"), Mapping),
        "has_walk_forward": isinstance(choices.get("walk_forward"), Mapping)
        and bool((choices.get("walk_forward") or {}).get("enabled", False)),
        "unresolved_assumptions": list(unresolved_assumptions),
        "validated_spec": dict(validated_spec) if isinstance(validated_spec, Mapping) else None,
    }


def build_provenance_card(run: Mapping[str, Any]) -> dict[str, Any]:
    """Build a presentation-only provenance card for one research run."""
    provenance = run.get("provenance") if isinstance(run.get("provenance"), Mapping) else {}
    request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "spec_version": run.get("spec_version"),
        "request_action": request.get("action"),
        "origin_page": request.get("origin_page") or provenance.get("origin_page"),
        "classic_config_hash": request.get("classic_config_hash")
        or provenance.get("classic_config_hash"),
        "recording_policy": request.get("recording_policy") or provenance.get("recording_policy"),
        "execution_origin": provenance.get("execution_origin") or request.get("execution_origin"),
        "data_identity": provenance.get("data_identity"),
        "levels_identity": provenance.get("levels_identity"),
        "bundle_path": provenance.get("bundle_path"),
        "canonical_bundle_hash": provenance.get("canonical_bundle_hash"),
        "dataset_fingerprint": provenance.get("dataset_fingerprint"),
        "tool_version": provenance.get("tool_version"),
        "warnings": list(run.get("warnings") or provenance.get("warnings") or ()),
        "error": run.get("error"),
        "summary": provenance.get("summary"),
        "seeds": provenance.get("seeds"),
        "resource_limits": provenance.get("resource_limits"),
        "resolved_paths": provenance.get("resolved_paths"),
        "cache_provenance": provenance.get("cache_provenance"),
        "cache_outcome": (provenance.get("cache_provenance") or {}).get("outcome")
        if isinstance(provenance.get("cache_provenance"), Mapping)
        else provenance.get("cache_outcome"),
    }


def option_index(
    options: Sequence[Any],
    value: Any,
    default: int = 0,
) -> int:
    """Return a safe selectbox index for a current value."""
    options_list = list(options)
    if not options_list:
        return default
    if value in options_list:
        return options_list.index(value)
    text = str(value) if value is not None else ""
    text_options = [str(item) for item in options_list]
    if text in text_options:
        return text_options.index(text)
    return default


def options_with_current(catalog: Sequence[Any], current: Any) -> list[Any]:
    """Return catalog options, appending ``current`` when it is outside the catalog.

    Prevents fixed selectboxes from silently remapping unknown draft values to
    the catalog default via ``option_index``.
    """
    return options_with_currents(catalog, (current,) if current is not None else ())


def options_with_currents(
    catalog: Sequence[Any],
    current_values: Iterable[Any] | None,
) -> list[Any]:
    """Return catalog options, appending any draft values outside the catalog.

    Used by multiselects so Apply cannot drop previously staged windows/lengths
    that are not in the fixed default catalog.
    """
    options = list(catalog)
    text_options = {str(item) for item in options}
    for current in current_values or ():
        if current is None or current in options:
            continue
        text = str(current).strip() if isinstance(current, str) else current
        if text == "" or text is None:
            continue
        if str(text) in text_options:
            continue
        appended = text if isinstance(current, str) else current
        options.append(appended)
        text_options.add(str(appended))
    return options


def coerce_multiselect_defaults(
    selected: Iterable[Any] | None,
    options: Sequence[Any],
) -> list[Any]:
    """Keep only selected values that exist in ``options`` (Streamlit-safe defaults)."""
    option_set = set(options)
    values: list[Any] = []
    for item in selected or ():
        if item in option_set and item not in values:
            values.append(item)
    return values


def _levels_setting_sequence(
    settings: Mapping[str, Any],
    key: str,
    *,
    default: Sequence[Any],
) -> list[Any]:
    """Return a levels-settings sequence.

    Missing / ``None`` uses ``default``. An explicit empty list/tuple is preserved
    so cleared windows/lengths do not expand back into the full catalog.
    """
    if key not in settings:
        return list(default)
    raw = settings.get(key)
    if raw is None:
        return list(default)
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return list(default)


def build_confluence_level_options(
    *,
    selected_levels: Iterable[Any] | None = None,
    levels_settings: Mapping[str, Any] | None = None,
    available_columns: Iterable[str] | None = None,
) -> list[str]:
    """Build a searchable confluence catalog for Assistant multiselects.

    Prefers live Levels-page columns when available, then static session/profile
    names, then indicator names implied by the staged levels settings, and
    always retains any already-selected draft levels. Explicit empty
    ``vwap_windows`` / ``poc_windows`` / indicator-length lists stay empty —
    they do not fall back to the full default catalogs.
    """
    options: list[str] = []

    def _add(items: Iterable[Any] | None) -> None:
        for item in items or ():
            text = str(item).strip()
            if text and text not in options:
                options.append(text)

    _add(SUGGESTED_DEFAULT_LEVELS)
    _add(SESSION_LEVEL_CATALOG)
    settings = levels_settings if isinstance(levels_settings, Mapping) else {}
    sma_lengths = [
        value
        for value in _levels_setting_sequence(
            settings, "sma_lengths", default=INDICATOR_LENGTH_OPTIONS
        )
        if safe_int(value, 0) > 0
    ]
    ema_lengths = [
        value
        for value in _levels_setting_sequence(
            settings, "ema_lengths", default=INDICATOR_LENGTH_OPTIONS
        )
        if safe_int(value, 0) > 0
    ]
    sma_timeframes = [
        str(value).strip()
        for value in _levels_setting_sequence(settings, "sma_timeframes", default=("30min",))
        if str(value).strip()
    ]
    ema_timeframes = [
        str(value).strip()
        for value in _levels_setting_sequence(settings, "ema_timeframes", default=())
        if str(value).strip()
    ]
    for length in sma_lengths:
        for timeframe in sma_timeframes:
            _add((f"SMA_{int(length)}_{timeframe}",))
    for length in ema_lengths:
        for timeframe in ema_timeframes:
            _add((f"EMA_{int(length)}_{timeframe}",))
    for window in _levels_setting_sequence(settings, "vwap_windows", default=VWAP_WINDOW_OPTIONS):
        label = coerce_window_label(window)
        if label:
            _add((f"VWAP_rolling_{label}",))
    for window in _levels_setting_sequence(settings, "poc_windows", default=POC_WINDOW_OPTIONS):
        label = coerce_window_label(window)
        if label:
            _add((f"POC_rolling_{label}",))
    if bool(settings.get("prev30m_vwap_enabled", False)):
        validity = safe_int(settings.get("prev30m_vwap_validity_periods"), 1)
        _add(prev30m_price_column_names(max(validity, 1)))
    _add(available_columns)
    _add(selected_levels)
    return options
