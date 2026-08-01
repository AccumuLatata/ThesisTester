from pathlib import Path
import sys
import os
import hashlib

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.data.loader import (
    DataValidationError,
    duplicate_timestamp_report,
    format_interval,
    infer_base_interval,
    load_ohlcv,
    validate_ohlcv,
)
from thesistester.data.rolls import (
    ROLL_METHODS,
    detect_contract_column,
    validate_roll_metadata,
)
from thesistester.data.resample import SUPPORTED_TIMEFRAMES, resample_ohlcv
from thesistester.data.sessions import tag_session
from thesistester.engine.intrabar import (
    inspect_subtimeframe_compatibility,
    prepare_subtimeframe_conservative_context,
)
from thesistester.app_state import (
    ACTIVE_SAVED_DATASET_KEY,
    BOOTSTRAP_MESSAGE_KEY,
    bootstrap_active_saved_dataset,
    restore_saved_dataset_provenance,
)
from thesistester.persistence import (
    clear_active_dataset_id,
    compute_dataset_id,
    delete_dataset,
    get_store_root,
    list_datasets,
    load_dataset,
    save_dataset,
    set_active_dataset_id,
)
from thesistester.timezone_display import (
    ensure_display_timezone,
    timezone_contract_caption,
)

FLASH_MESSAGE_KEY = "_data_local_store_message"
PENDING_INSTRUMENT_SELECTOR_KEY = "_pending_data_instrument_selector"
PENDING_SOURCE_TZ_SELECTOR_KEY = "_pending_data_source_timezone_selector"
RAW_CAPTURE_PROFILES = frozenset(
    {"ninjatrader", "databento_trades", "tick_capture", "second_capture"}
)
SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY = "_subtimeframe_upload_signature"
SUBTIMEFRAME_UPLOADER_NONCE_KEY = "_subtimeframe_uploader_nonce"
SUBTIMEFRAME_FALLBACK_BARS_KEY = "subtimeframe_fallback_parent_bars"
SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY = "_subtimeframe_compatibility_report"
SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY = "_subtimeframe_compatibility_signature"
SUBTIMEFRAME_DUPLICATE_REPORT_KEY = "_subtimeframe_duplicate_report"
SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY = "_subtimeframe_duplicate_signature"
SUBTIMEFRAME_FORMAT_PROFILES = ("canonical", "quantower_history_exporter")
FATAL_OHLCV_CODES = frozenset(
    {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
)


class SubtimeframeCompatibilityError(ValueError):
    """Lower CSV cannot be replayed; retain its read-only diagnostic report."""

    def __init__(self, message: str, report: pd.DataFrame) -> None:
        super().__init__(message)
        self.report = report


class SubtimeframeDuplicateTimestampError(ValueError):
    """Lower CSV contains duplicate bar-open timestamps."""

    def __init__(self, message: str, report: pd.DataFrame) -> None:
        super().__init__(message)
        self.report = report


def _default_source_timezone(format_profile: str, exchange_timezone: str) -> str:
    """Return the profile's default timezone for timezone-naive timestamps."""
    return "UTC" if format_profile == "ninjatrader" else exchange_timezone


def _reset_source_timezone_for_import() -> None:
    """Apply the selected source/profile default for timezone-naive timestamps."""
    source = st.session_state["data_source_selector"]
    profile = st.session_state.get("data_format_profile_selector", "canonical")
    exchange_timezone = INSTRUMENTS[st.session_state["data_instrument_selector"]].exchange_tz
    st.session_state["data_source_timezone_selector"] = (
        "America/New_York"
        if source == "Sample data"
        else _default_source_timezone(profile, exchange_timezone)
    )


@st.cache_data(show_spinner=False)
def cached_resample_and_tag(raw_df, instrument: str, timeframe: str):
    """Cache and return session-tagged resampled OHLCV data for preview."""
    out = resample_ohlcv(raw_df, timeframe)
    return tag_session(out, instrument)


def _default_dataset_name(df, instrument: str) -> str:
    if df is None or df.empty or "timestamp" not in df.columns:
        return f"{instrument} dataset"
    start = df["timestamp"].min()
    end = df["timestamp"].max()
    return f"{instrument} {start.date()} to {end.date()}"


def _saved_dataset_label(meta: dict) -> str:
    rows = f"{int(meta.get('rows', 0)):,} rows"
    date_range = "unknown range"
    if meta.get("timestamp_min") and meta.get("timestamp_max"):
        start = meta["timestamp_min"][:10]
        end = meta["timestamp_max"][:10]
        date_range = f"{start} → {end}"
    saved_at = meta.get("created_at", "")[:10] or "unknown date"
    return f"{meta.get('name', meta['dataset_id'])} · {meta.get('instrument', '—')} · {rows} · {date_range} · saved {saved_at}"


def _clear_dataset_dependent_state() -> None:
    for key in [
        "levels",
        "subtimeframe_data",
        "subtimeframe_interval",
        SUBTIMEFRAME_FALLBACK_BARS_KEY,
        SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY,
        SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY,
        SUBTIMEFRAME_DUPLICATE_REPORT_KEY,
        SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY,
        SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY,
        SUBTIMEFRAME_UPLOADER_NONCE_KEY,
        "raw_data",
        "raw_interval",
        "format_profile",
        "session_levels",
        "levels_settings",
        "levels_data_fingerprint",
        "confluence_zones",
        "naked_flags",
        "last_signal_setup",
        "signal_context",
        "signals",
        "trades",
        "trade_summary",
        "equity_curve",
        "backtest_intrabar_policy",
        "backtest_intrabar_diagnostic",
        "backtest_exit_management_policy",
        "backtest_exit_management_diagnostic",
        "grid_results",
        "best_grid_result",
        "grid_intrabar_policy",
        "grid_exit_management_policy",
        "time_bucketed_trades",
        "time_grouped_summary",
        "validation_summary",
        "walk_forward_results",
        "walk_forward_summary",
        "walk_forward_config",
        "walk_forward_otf_filter",
        "walk_forward_oos_trades",
        "walk_forward_stitched_equity",
        "walk_forward_warnings",
        "wfa_matrix",
        "wfa_matrix_config",
        "excursion_summary",
        "excursion_config",
        "excursion_grouped_summary",
        "excursion_calibration_grid",
        "excursion_quadrant_summary",
        "monte_carlo_summary",
        "monte_carlo_config",
        "noise_summary",
        "noise_config",
        "overfitting_summary",
        "overfitting_config",
        "sensitivity_summary",
        "sensitivity_config",
        "trade_review_trade_id",
        "trade_review_buffer_rows",
        "trade_review_export_zip",
        "trade_review_export_signature",
        "portfolio_setup_inputs",
        "portfolio_config",
        "portfolio_summary",
        "portfolio_trades",
        "portfolio_skipped_trades",
        "portfolio_equity_curve",
        "portfolio_correlation",
        "portfolio_drawdown_correlation",
        "portfolio_marginal_contribution",
        "roll_policy",
        "roll_validation",
        "roll_method_selector",
        "roll_contract_column_input",
        "roll_adjustment_method_selector",
        "roll_rule_selector",
    ]:
        st.session_state.pop(key, None)


def _clear_execution_dependent_state() -> None:
    """Clear outputs whose results depend on the selected intrabar data."""
    for key in [
        "trades",
        "trade_summary",
        "equity_curve",
        "backtest_intrabar_policy",
        "backtest_intrabar_diagnostic",
        "backtest_exit_management_policy",
        "backtest_exit_management_diagnostic",
        "grid_results",
        "best_grid_result",
        "grid_intrabar_policy",
        "grid_exit_management_policy",
        "time_bucketed_trades",
        "time_grouped_summary",
        "validation_summary",
        "walk_forward_results",
        "walk_forward_summary",
        "walk_forward_config",
        "walk_forward_otf_filter",
        "walk_forward_oos_trades",
        "walk_forward_stitched_equity",
        "walk_forward_warnings",
        "wfa_matrix",
        "wfa_matrix_config",
        "excursion_summary",
        "excursion_config",
        "excursion_grouped_summary",
        "excursion_calibration_grid",
        "excursion_quadrant_summary",
        "monte_carlo_summary",
        "monte_carlo_config",
        "noise_summary",
        "noise_config",
        "overfitting_summary",
        "overfitting_config",
        "sensitivity_summary",
        "sensitivity_config",
        "trade_review_trade_id",
        "trade_review_buffer_rows",
        "trade_review_export_zip",
        "trade_review_export_signature",
        "portfolio_setup_inputs",
        "portfolio_config",
        "portfolio_summary",
        "portfolio_trades",
        "portfolio_skipped_trades",
        "portfolio_equity_curve",
        "portfolio_correlation",
        "portfolio_drawdown_correlation",
        "portfolio_marginal_contribution",
    ]:
        st.session_state.pop(key, None)


def _load_subtimeframe_upload(
    uploaded_file,
    *,
    parent_df: pd.DataFrame,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
    format_profile: str,
) -> tuple[pd.DataFrame, str, list[dict[str, object]]]:
    """Load canonical lower bars for strict or conservative R12 replay."""
    raw_df = load_ohlcv(
        uploaded_file,
        source_tz=source_timezone,
        target_tz=exchange_timezone,
        format_profile=format_profile,
    )
    report = validate_ohlcv(raw_df)
    fatal_messages = [issue.message for issue in report.issues if issue.code in FATAL_OHLCV_CODES]
    if fatal_messages:
        if any(issue.code == "duplicate_timestamps" for issue in report.issues):
            raise SubtimeframeDuplicateTimestampError(
                "Lower-timeframe validation failed: " + "; ".join(fatal_messages),
                duplicate_timestamp_report(raw_df),
            )
        raise ValueError("Lower-timeframe validation failed: " + "; ".join(fatal_messages))

    subtimeframe_df = tag_session(raw_df, instrument)
    try:
        context = prepare_subtimeframe_conservative_context(
            parent_df,
            subtimeframe_df,
            tick_size=INSTRUMENTS[instrument].tick_size,
        )
    except ValueError as exc:
        compatibility = inspect_subtimeframe_compatibility(
            parent_df,
            subtimeframe_df,
            tick_size=INSTRUMENTS[instrument].tick_size,
        )
        raise SubtimeframeCompatibilityError(str(exc), compatibility.to_frame()) from exc
    return (
        subtimeframe_df,
        format_interval(context.sub_interval),
        context.fallback_diagnostics(parent_df),
    )


def _set_subtimeframe_state(
    subtimeframe_df: pd.DataFrame,
    *,
    interval: str,
    upload_signature: str,
    fallback_bars: list[dict[str, object]],
) -> None:
    """Store validated R12 data and invalidate dependent execution outputs."""
    st.session_state["subtimeframe_data"] = subtimeframe_df
    st.session_state["subtimeframe_interval"] = interval
    st.session_state[SUBTIMEFRAME_FALLBACK_BARS_KEY] = fallback_bars
    st.session_state[SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY] = upload_signature
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY, None)
    _clear_execution_dependent_state()


def _clear_subtimeframe_state() -> None:
    """Remove R12 data and reset its uploader while retaining primary data."""
    st.session_state.pop("subtimeframe_data", None)
    st.session_state.pop("subtimeframe_interval", None)
    st.session_state.pop(SUBTIMEFRAME_FALLBACK_BARS_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY, None)
    st.session_state[SUBTIMEFRAME_UPLOADER_NONCE_KEY] = (
        int(st.session_state.get(SUBTIMEFRAME_UPLOADER_NONCE_KEY, 0)) + 1
    )
    _clear_execution_dependent_state()


def _clear_loaded_subtimeframe_after_failed_upload() -> None:
    """Fail closed when a replacement lower upload cannot be parsed safely."""
    for key in (
        "subtimeframe_data",
        "subtimeframe_interval",
        SUBTIMEFRAME_FALLBACK_BARS_KEY,
        SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY,
    ):
        st.session_state.pop(key, None)
    _clear_execution_dependent_state()


def _upload_signature(uploaded_file, *, format_profile: str) -> str:
    """Return a stable signature for file content and its explicit parser profile."""
    content_hash = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
    return f"{format_profile}:{content_hash}"


def _render_subtimeframe_upload(
    parent_df: pd.DataFrame,
    *,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
) -> None:
    """Render the optional interactive R12 lower-timeframe import."""
    with st.expander("Lower-timeframe R12 replay (optional)", expanded=False):
        st.caption(
            "Upload lower OHLCV bars for observed lower-timeframe replay. "
            "They must cover and reconcile exactly to every main-chart bar."
        )
        subtimeframe_format_profile = st.selectbox(
            "Lower CSV format profile",
            options=SUBTIMEFRAME_FORMAT_PROFILES,
            format_func=profile_options.get,
            key="subtimeframe_format_profile",
            help="Explicit selection only; the lower file never inherits the main CSV profile.",
        )
        uploader_nonce = int(st.session_state.get(SUBTIMEFRAME_UPLOADER_NONCE_KEY, 0))
        uploaded_file = st.file_uploader(
            "Lower-timeframe CSV (canonical OHLCV)",
            type=["csv", "txt"],
            key=f"subtimeframe_csv_upload_{uploader_nonce}",
        )
        upload_signature = (
            _upload_signature(uploaded_file, format_profile=subtimeframe_format_profile)
            if uploaded_file is not None
            else None
        )
        duplicate_report = st.session_state.get(SUBTIMEFRAME_DUPLICATE_REPORT_KEY)
        if isinstance(duplicate_report, pd.DataFrame) and upload_signature == st.session_state.get(
            SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY
        ):
            exact_count = int(duplicate_report["exact_duplicate_group"].sum())
            group_count = int(duplicate_report["timestamp"].nunique())
            st.warning(
                f"Lower duplicate report: {group_count:,} duplicate timestamp groups. "
                f"{exact_count:,} duplicate rows belong to exact-duplicate groups; "
                "conflicting groups remain fail-closed."
            )
            st.dataframe(duplicate_report, width="stretch")
            st.download_button(
                "Download lower duplicate report CSV",
                data=duplicate_report.to_csv(index=False).encode("utf-8"),
                file_name="r12_lower_duplicate_report.csv",
                mime="text/csv",
            )
        compatibility_report = st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY)
        if isinstance(
            compatibility_report, pd.DataFrame
        ) and upload_signature == st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY):
            st.warning(
                f"R12 compatibility report: {len(compatibility_report):,} parent bars "
                "cannot be replayed from this lower CSV."
            )
            st.dataframe(compatibility_report, width="stretch")
            st.download_button(
                "Download R12 compatibility report CSV",
                data=compatibility_report.to_csv(index=False).encode("utf-8"),
                file_name="r12_compatibility_report.csv",
                mime="text/csv",
            )
        if (
            uploaded_file is not None
            and upload_signature != st.session_state.get(SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY)
            and upload_signature != st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY)
            and upload_signature != st.session_state.get(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY)
        ):
            try:
                subtimeframe_df, interval, fallback_bars = _load_subtimeframe_upload(
                    uploaded_file,
                    parent_df=parent_df,
                    instrument=instrument,
                    source_timezone=source_timezone,
                    exchange_timezone=exchange_timezone,
                    format_profile=subtimeframe_format_profile,
                )
                _set_subtimeframe_state(
                    subtimeframe_df,
                    interval=interval,
                    upload_signature=upload_signature,
                    fallback_bars=fallback_bars,
                )
                if fallback_bars:
                    st.warning(
                        f"{len(fallback_bars):,} parent bars lack replayable lower data. "
                        "Strict observed replay will reject this file; "
                        "select the explicit conservative model to use SL-first "
                        "fallback only on those bars."
                    )
                else:
                    st.success(
                        f"R12 data ready: {len(subtimeframe_df):,} {interval} bars "
                        f"reconcile to the main chart."
                    )
            except SubtimeframeDuplicateTimestampError as exc:
                _clear_loaded_subtimeframe_after_failed_upload()
                st.session_state[SUBTIMEFRAME_DUPLICATE_REPORT_KEY] = exc.report
                st.session_state[SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY] = upload_signature
                st.error(str(exc))
                st.rerun()
            except SubtimeframeCompatibilityError as exc:
                _clear_loaded_subtimeframe_after_failed_upload()
                st.session_state[SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY] = exc.report
                st.session_state[SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY] = upload_signature
                st.error(str(exc))
                st.rerun()
            except (DataValidationError, ValueError) as exc:
                _clear_loaded_subtimeframe_after_failed_upload()
                st.error(str(exc))

        subtimeframe_df = st.session_state.get("subtimeframe_data")
        if isinstance(subtimeframe_df, pd.DataFrame):
            interval = st.session_state.get("subtimeframe_interval", "unknown interval")
            st.info(f"R12 data loaded: {len(subtimeframe_df):,} bars at {interval}.")
            fallback_bars = st.session_state.get(SUBTIMEFRAME_FALLBACK_BARS_KEY, [])
            if fallback_bars:
                st.caption(
                    f"Conservative R12 fallback is required for {len(fallback_bars):,} "
                    "parent bars; the strict model remains unavailable."
                )
            if st.button("Remove lower-timeframe data"):
                _clear_subtimeframe_state()
                st.rerun()


def _set_active_dataset_state(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    resampled_data: dict | None,
    saved_dataset_id: str | None,
):
    dataset_id = saved_dataset_id or compute_dataset_id(
        df,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    previous_dataset_id = st.session_state.get("dataset_id")
    if previous_dataset_id is not None and previous_dataset_id != dataset_id:
        _clear_dataset_dependent_state()
        active_setup = st.session_state.get("setup_config")
        setup_dataset_id = (
            active_setup.get("dataset_id") if isinstance(active_setup, dict) else None
        )
        if (
            isinstance(setup_dataset_id, str)
            and setup_dataset_id
            and setup_dataset_id != dataset_id
        ):
            st.session_state.pop("setup_config", None)
            st.session_state.pop("_setup_builder_editor_config", None)
    st.session_state["data"] = df
    st.session_state["resampled_data"] = resampled_data or {}
    st.session_state["instrument"] = instrument
    st.session_state["base_interval"] = base_interval
    st.session_state["source_timezone"] = source_timezone
    st.session_state["exchange_timezone"] = exchange_timezone
    ensure_display_timezone(
        st.session_state,
        exchange_timezone=exchange_timezone,
    )
    st.session_state["dataset_id"] = dataset_id
    if saved_dataset_id is None:
        clear_active_dataset_id()
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
    else:
        set_active_dataset_id(saved_dataset_id)
        st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_dataset_id


def _render_dataset_summary(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    report=None,
    resampled_data: dict | None = None,
    saved_dataset_loaded: bool = False,
):
    st.success(f"Loaded {len(df):,} bars.")
    st.caption(f"{df['timestamp'].min()} → {df['timestamp'].max()}")
    st.caption(timezone_contract_caption(st.session_state))

    summary_cols = st.columns(4)
    summary_cols[0].metric("Rows", f"{len(df):,}")
    summary_cols[1].metric("Inferred base interval", base_interval or "unknown")
    summary_cols[2].metric("RTH bars", int((df["session"] == "RTH").sum()))
    summary_cols[3].metric("ETH bars", int((df["session"] == "ETH").sum()))

    if report is not None:
        detail_cols = st.columns(2)
        detail_cols[0].metric("Validation issues", len(report.issues))
        detail_cols[1].metric("Instrument", instrument)
        if report.is_clean:
            st.info("Validation passed ✓")
        else:
            st.warning("Validation issues detected:")
            for issue in report.messages():
                st.write(f"- {issue}")
    elif saved_dataset_loaded:
        st.info("Loaded canonical dataset from local store.")
    else:
        st.info("Using dataset from current session.")

    for timeframe, out in (resampled_data or {}).items():
        with st.expander(f"{timeframe} preview ({len(out):,} rows)"):
            st.dataframe(out.head(50), width="stretch")

    st.subheader("Base timeframe preview")
    st.dataframe(df.head(50), width="stretch")


def _render_roll_assumptions(df, *, instrument: str) -> None:
    st.subheader("Futures roll assumptions")
    existing_policy = st.session_state.get("roll_policy")
    if not isinstance(existing_policy, dict):
        existing_policy = {}

    detected_contract_column = detect_contract_column(df)
    roll_method_options = [
        "single_contract",
        "external_continuous",
        "segmented_contracts",
    ]
    default_roll_method = existing_policy.get("roll_method", "single_contract")
    if default_roll_method not in ROLL_METHODS:
        default_roll_method = "single_contract"
    roll_method = st.selectbox(
        "Roll method",
        options=roll_method_options,
        index=roll_method_options.index(default_roll_method),
        key="roll_method_selector",
    )

    contract_column = (
        st.text_input(
            "Contract column",
            value=(
                existing_policy.get("contract_column") or detected_contract_column or "contract"
            ),
            key="roll_contract_column_input",
        ).strip()
        or "contract"
    )

    adjustment_options = [
        "unknown",
        "back_adjusted",
        "ratio_adjusted",
        "panama",
        "none",
    ]
    roll_rule_options = [
        "unknown",
        "volume",
        "open_interest",
        "calendar",
        "first_notice",
        "last_trade",
    ]

    default_adjustment = existing_policy.get("adjustment_method", "unknown")
    if default_adjustment not in adjustment_options:
        default_adjustment = "unknown"
    default_roll_rule = existing_policy.get("roll_rule", "unknown")
    if default_roll_rule not in roll_rule_options:
        default_roll_rule = "unknown"

    if roll_method == "external_continuous":
        adjustment_method = st.selectbox(
            "Adjustment method",
            options=adjustment_options,
            index=adjustment_options.index(default_adjustment),
            key="roll_adjustment_method_selector",
        )
        roll_rule = st.selectbox(
            "Roll rule",
            options=roll_rule_options,
            index=roll_rule_options.index(default_roll_rule),
            key="roll_rule_selector",
        )
    else:
        adjustment_method = "unknown"
        roll_rule = "unknown"

    st.session_state["roll_policy"] = {
        "roll_method": roll_method,
        "contract_column": contract_column,
        "adjustment_method": adjustment_method,
        "roll_rule": roll_rule,
    }

    tick_size = INSTRUMENTS[instrument].tick_size if instrument in INSTRUMENTS else None
    if st.button("Validate roll metadata"):
        st.session_state["roll_validation"] = validate_roll_metadata(
            df,
            roll_method=roll_method,
            contract_column=contract_column,
            adjustment_method=adjustment_method,
            roll_rule=roll_rule,
            tick_size=tick_size,
        )

    validation = st.session_state.get("roll_validation")
    if not isinstance(validation, dict):
        return

    st.metric("Roll metadata valid", "✅" if validation.get("valid") else "❌")
    st.write(f"Contract count: {validation.get('contract_count', '—')}")
    warnings = validation.get("warnings")
    if isinstance(warnings, list) and warnings:
        st.warning("Warnings:")
        for warning in warnings:
            st.write(f"- {warning}")
    roll_gaps = validation.get("roll_gaps")
    if isinstance(roll_gaps, list) and roll_gaps:
        st.dataframe(pd.DataFrame(roll_gaps), width="stretch")


st.title("\U0001f4e5 Data")

bootstrap_active_saved_dataset()

flash_message = st.session_state.pop(FLASH_MESSAGE_KEY, None)
if flash_message:
    st.success(flash_message)
bootstrap_message = st.session_state.pop(BOOTSTRAP_MESSAGE_KEY, None)
if bootstrap_message:
    st.success(bootstrap_message)
raw_capture_warning = st.session_state.pop("raw_capture_warning", None)
if raw_capture_warning:
    st.warning(raw_capture_warning)

st.subheader("Local saved datasets")
st.caption(f"Local store: `{get_store_root()}`")
if not os.environ.get("THESISTESTER_STORE_DIR"):
    st.warning(
        "THESISTESTER_STORE_DIR is not set. Saved datasets are stored in a local repo folder "
        "and may not persist across environments."
    )
saved_datasets = list_datasets()
saved_dataset_options = {item["dataset_id"]: item for item in saved_datasets}

if saved_datasets:
    selected_saved_dataset_id = st.selectbox(
        "Saved datasets",
        options=list(saved_dataset_options),
        format_func=lambda dataset_id: _saved_dataset_label(saved_dataset_options[dataset_id]),
    )
    selected_saved_dataset = saved_dataset_options[selected_saved_dataset_id]

    action_cols = st.columns(3)
    if action_cols[0].button("Load saved dataset", width="stretch"):
        loaded_df, loaded_meta = load_dataset(selected_saved_dataset_id)
        _set_active_dataset_state(
            loaded_df,
            instrument=loaded_meta["instrument"],
            base_interval=loaded_meta.get("base_interval"),
            source_timezone=loaded_meta.get("source_timezone"),
            exchange_timezone=loaded_meta.get("exchange_timezone"),
            resampled_data={},
            saved_dataset_id=loaded_meta["dataset_id"],
        )
        restore_saved_dataset_provenance(
            loaded_meta["dataset_id"],
            loaded_meta,
        )
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Loaded saved dataset '{loaded_meta['name']}' ({loaded_meta['dataset_id'][:12]}...)."
        )
        st.session_state[PENDING_INSTRUMENT_SELECTOR_KEY] = loaded_meta["instrument"]
        if loaded_meta.get("source_timezone") is not None:
            st.session_state[PENDING_SOURCE_TZ_SELECTOR_KEY] = loaded_meta["source_timezone"]
        st.rerun()

    if action_cols[1].button("Delete saved dataset", width="stretch"):
        delete_dataset(selected_saved_dataset_id)
        if st.session_state.get(ACTIVE_SAVED_DATASET_KEY) == selected_saved_dataset_id:
            st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Deleted saved dataset '{selected_saved_dataset.get('name', selected_saved_dataset_id)}'."
        )
        st.rerun()

    if action_cols[2].button("Refresh saved datasets", width="stretch"):
        st.rerun()
else:
    st.caption(f"No saved datasets found in `{get_store_root()}`.")
    if st.button("Refresh saved datasets"):
        st.rerun()

st.divider()

available_instruments = list(INSTRUMENTS.keys())
if PENDING_INSTRUMENT_SELECTOR_KEY in st.session_state:
    st.session_state["data_instrument_selector"] = st.session_state.pop(
        PENDING_INSTRUMENT_SELECTOR_KEY
    )
if "data_instrument_selector" not in st.session_state:
    st.session_state["data_instrument_selector"] = st.session_state.get(
        "instrument",
        available_instruments[0],
    )
inst = st.selectbox("Instrument", available_instruments, key="data_instrument_selector")
meta = INSTRUMENTS[inst]
st.caption(
    f"{meta.name} \u00b7 tick size {meta.tick_size} \u00b7 point value ${meta.point_value:,.0f} "
    f"\u00b7 session tz {meta.exchange_tz} ({meta.rth_start}\u2013{meta.rth_end} RTH)"
)

source = st.radio(
    "Source",
    ["Sample data", "Upload CSV"],
    horizontal=True,
    key="data_source_selector",
    on_change=_reset_source_timezone_for_import,
)
profile_options = {
    "canonical": "Canonical / Quantower OHLCV",
    "quantower_history_exporter": "Quantower History Exporter (semicolon)",
    "ninjatrader": "NinjaTrader export",
    "sierra_intraday": "Sierra Intraday CSV",
    "databento_trades": "Databento trades CSV",
    "tick_capture": "Generic tick capture CSV",
    "second_capture": "Generic second capture CSV",
}
format_profile = (
    st.selectbox(
        "CSV format profile",
        options=list(profile_options),
        format_func=profile_options.get,
        help="Explicit selection only; ThesisTester never auto-detects vendor formats.",
        key="data_format_profile_selector",
        on_change=_reset_source_timezone_for_import,
    )
    if source == "Upload CSV"
    else "canonical"
)
default_source_tz = (
    "America/New_York"
    if source == "Sample data"
    else _default_source_timezone(format_profile, meta.exchange_tz)
)
if PENDING_SOURCE_TZ_SELECTOR_KEY in st.session_state:
    st.session_state["data_source_timezone_selector"] = st.session_state.pop(
        PENDING_SOURCE_TZ_SELECTOR_KEY
    )
if "data_source_timezone_selector" not in st.session_state:
    st.session_state["data_source_timezone_selector"] = default_source_tz
source_tz = st.selectbox(
    "Source timestamp timezone",
    TIMEZONE_OPTIONS,
    index=TIMEZONE_OPTIONS.index(st.session_state["data_source_timezone_selector"]),
    key="data_source_timezone_selector",
    help=(
        "Use this for timezone-naive CSV timestamps. Timezone-aware timestamps are "
        "converted from their embedded timezone automatically."
    ),
)

file = None
if source == "Upload CSV":
    file = st.file_uploader("CSV file for the selected explicit profile", type=["csv", "txt"])
else:
    sample = REPO_ROOT / "sample_data" / "ES_sample_1m.csv"
    file = sample if sample.exists() else None
    if file is None:
        st.error("Sample data not found.")

use_source_dataset = file is not None and (
    source == "Upload CSV" or ACTIVE_SAVED_DATASET_KEY not in st.session_state
)

if use_source_dataset:
    try:
        raw_df, captured_raw = load_ohlcv(
            file,
            source_tz=source_tz,
            target_tz=meta.exchange_tz,
            format_profile=format_profile,
            return_raw=True,
        )
        report = validate_ohlcv(raw_df)
        base_interval = format_interval(report.inferred_interval)
        df = tag_session(raw_df, inst)

        selected_timeframes = st.multiselect(
            "Preview resampled timeframes",
            options=list(SUPPORTED_TIMEFRAMES),
            default=["5min", "15min"],
        )

        resampled_data = {}
        for timeframe in selected_timeframes:
            out = cached_resample_and_tag(raw_df, inst, timeframe)
            resampled_data[timeframe] = out
        _set_active_dataset_state(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=meta.exchange_tz,
            resampled_data=resampled_data,
            saved_dataset_id=None,
        )
        st.session_state["format_profile"] = format_profile
        if format_profile in RAW_CAPTURE_PROFILES:
            st.session_state["raw_data"] = captured_raw
            st.session_state["raw_interval"] = format_interval(
                infer_base_interval(captured_raw["timestamp"])
            )
            st.caption(
                f"Captured {len(captured_raw):,} raw rows; the engine uses the resampled 1-minute bars."
            )
        else:
            st.session_state.pop("raw_data", None)
            st.session_state.pop("raw_interval", None)
        _render_dataset_summary(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=meta.exchange_tz,
            report=report,
            resampled_data=resampled_data,
        )
    except DataValidationError as exc:
        st.error(str(exc))
elif "data" in st.session_state:
    _render_dataset_summary(
        st.session_state["data"],
        instrument=st.session_state.get("instrument", inst),
        base_interval=st.session_state.get("base_interval"),
        source_timezone=st.session_state.get("source_timezone"),
        exchange_timezone=st.session_state.get("exchange_timezone"),
        resampled_data=st.session_state.get("resampled_data"),
        saved_dataset_loaded=ACTIVE_SAVED_DATASET_KEY in st.session_state,
    )

current_df = st.session_state.get("data")
if current_df is not None:
    st.divider()
    _render_subtimeframe_upload(
        current_df,
        instrument=st.session_state.get("instrument", inst),
        source_timezone=st.session_state.get("source_timezone"),
        exchange_timezone=st.session_state.get("exchange_timezone", meta.exchange_tz),
    )
    st.divider()
    _render_roll_assumptions(
        current_df,
        instrument=st.session_state.get("instrument", inst),
    )
    st.divider()
    current_instrument = st.session_state.get("instrument", inst)
    default_name = _default_dataset_name(current_df, current_instrument)
    dataset_name = st.text_input("Local dataset name", value=default_name)
    if st.button("Save dataset locally"):
        saved_meta = save_dataset(
            current_df,
            name=dataset_name.strip() or default_name,
            instrument=current_instrument,
            base_interval=st.session_state.get("base_interval"),
            source_timezone=st.session_state.get("source_timezone"),
            exchange_timezone=st.session_state.get("exchange_timezone"),
            raw_data=st.session_state.get("raw_data"),
            format_profile=st.session_state.get("format_profile", "canonical"),
            raw_interval=st.session_state.get("raw_interval"),
        )
        st.session_state["dataset_id"] = saved_meta["dataset_id"]
        set_active_dataset_id(saved_meta["dataset_id"])
        st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_meta["dataset_id"]
        st.session_state[FLASH_MESSAGE_KEY] = (
            f"Saved dataset '{saved_meta['name']}' locally ({saved_meta['dataset_id'][:12]}...)."
        )
        st.rerun()
