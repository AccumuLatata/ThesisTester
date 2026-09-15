"""Data-page lower-timeframe upload helpers (QR D-5 / QI-01-01).

Streamlit-free: renderers take ``st``. H10 primary admission is not here.
"""

from __future__ import annotations

import hashlib
import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import (
    DataValidationError,
    duplicate_timestamp_report,
    format_interval,
    load_ohlcv,
    resolve_ohlc_identical_duplicates,
    validate_ohlcv,
)
from thesistester.data.sessions import tag_session
from thesistester.engine.intrabar import (
    inspect_subtimeframe_compatibility,
    prepare_subtimeframe_conservative_context,
)
from thesistester.data_page_constants import (
    FATAL_OHLCV_CODES,
    LEGACY_SUBTIMEFRAME_EXPANDER_TITLE,
    SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY,
    SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY,
    SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY,
    SUBTIMEFRAME_DUPLICATE_REPORT_KEY,
    SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY,
    SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY,
    SUBTIMEFRAME_DUPLICATE_SOURCE_KEY,
    SUBTIMEFRAME_FALLBACK_BARS_KEY,
    SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY,
    SUBTIMEFRAME_UPLOADER_NONCE_KEY,
    SubtimeframeCompatibilityError,
    SubtimeframeDuplicateTimestampError,
)


def _clear_execution_dependent_state(st) -> None:
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
                raw_df,
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
    st,
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
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SOURCE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY, None)
    _clear_execution_dependent_state(st)


def _clear_subtimeframe_state(st) -> None:
    """Remove R12 data and reset its uploader while retaining primary data."""
    st.session_state.pop("subtimeframe_data", None)
    st.session_state.pop("subtimeframe_interval", None)
    st.session_state.pop(SUBTIMEFRAME_FALLBACK_BARS_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SOURCE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY, None)
    st.session_state[SUBTIMEFRAME_UPLOADER_NONCE_KEY] = (
        int(st.session_state.get(SUBTIMEFRAME_UPLOADER_NONCE_KEY, 0)) + 1
    )
    _clear_execution_dependent_state(st)


def _clear_loaded_subtimeframe_after_failed_upload(st) -> None:
    """Fail closed when a replacement lower upload cannot be parsed safely."""
    for key in (
        "subtimeframe_data",
        "subtimeframe_interval",
        SUBTIMEFRAME_FALLBACK_BARS_KEY,
        SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY,
        SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY,
    ):
        st.session_state.pop(key, None)
    _clear_execution_dependent_state(st)


def _upload_signature(uploaded_file, *, format_profile: str) -> str:
    """Return a stable signature for file content and its explicit parser profile."""
    content_hash = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
    return f"{format_profile}:{content_hash}"


def _render_subtimeframe_duplicate_report(
    st,
    *,
    parent_df,
    instrument: str,
    upload_signature,
) -> None:
    """Show / resolve the OHLC-identical lower duplicate report."""
    duplicate_report = st.session_state.get(SUBTIMEFRAME_DUPLICATE_REPORT_KEY)
    if not (
        isinstance(duplicate_report, pd.DataFrame)
        and upload_signature == st.session_state.get(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY)
    ):
        return
    if "subtimeframe_data" in st.session_state:
        _clear_loaded_subtimeframe_after_failed_upload(st)
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
    if not bool(duplicate_report["ohlc_identical_group"].all()):
        return
    st.info(
        "All duplicate groups share identical OHLC. Lower-timeframe replay does not use "
        "lower-bar volume for event ordering; one lowest-volume row per "
        "timestamp can be retained with a recorded audit trail."
    )
    if not st.button("Use OHLC-identical duplicates for lower-timeframe replay only"):
        return
    source = st.session_state.get(SUBTIMEFRAME_DUPLICATE_SOURCE_KEY)
    if not isinstance(source, pd.DataFrame):
        st.error("Duplicate source data is unavailable; re-upload the lower CSV.")
        return
    try:
        resolved, audit = resolve_ohlc_identical_duplicates(source)
        subtimeframe_df = tag_session(resolved, instrument)
        context = prepare_subtimeframe_conservative_context(
            parent_df,
            subtimeframe_df,
            tick_size=INSTRUMENTS[instrument].tick_size,
        )
        _set_subtimeframe_state(
            st,
            subtimeframe_df,
            interval=format_interval(context.sub_interval),
            upload_signature=upload_signature,
            fallback_bars=context.fallback_diagnostics(parent_df),
        )
        st.session_state[SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY] = {
            "policy": "ohlc_identical_keep_lowest_volume",
            "groups_resolved": len(audit),
            "groups": audit,
        }
        st.success(
            f"Resolved {len(audit):,} OHLC-identical duplicate groups "
            "for lower-timeframe replay only."
        )
        st.rerun()
    except (DataValidationError, ValueError) as exc:
        primary_report = validate_ohlcv(parent_df)
        if "parent data contains duplicate timestamps" in str(exc) and any(
            issue.code == "duplicate_timestamps" for issue in primary_report.issues
        ):
            st.session_state[SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY] = subtimeframe_df
            st.session_state[SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY] = {
                "policy": "ohlc_identical_keep_lowest_volume",
                "groups_resolved": len(audit),
                "groups": audit,
            }
            st.warning(
                "Resolved lower data is retained for primary-volume "
                "diagnostics only. Lower-timeframe replay remains unavailable until "
                "primary duplicate timestamps are resolved."
            )
            st.rerun()
        else:
            st.error(str(exc))


def _render_subtimeframe_compatibility_report(st, *, upload_signature) -> None:
    compatibility_report = st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY)
    if not (
        isinstance(compatibility_report, pd.DataFrame)
        and upload_signature == st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY)
    ):
        return
    st.warning(
        f"Lower-timeframe compatibility report: {len(compatibility_report):,} parent bars "
        "cannot be replayed from this lower CSV."
    )
    st.dataframe(compatibility_report, width="stretch")
    st.download_button(
        "Download lower-timeframe compatibility report CSV",
        data=compatibility_report.to_csv(index=False).encode("utf-8"),
        file_name="r12_compatibility_report.csv",
        mime="text/csv",
    )


def _apply_new_subtimeframe_upload(
    st,
    uploaded_file,
    *,
    parent_df,
    instrument: str,
    source_timezone,
    exchange_timezone,
    format_profile,
    upload_signature,
) -> None:
    if uploaded_file is None:
        return
    if upload_signature in (
        st.session_state.get(SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY),
        st.session_state.get(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY),
        st.session_state.get(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY),
    ):
        return
    try:
        subtimeframe_df, interval, fallback_bars = _load_subtimeframe_upload(
            uploaded_file,
            parent_df=parent_df,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
        )
        _set_subtimeframe_state(
            st,
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
                f"Lower-timeframe data ready: {len(subtimeframe_df):,} {interval} bars "
                f"reconcile to the main chart."
            )
    except SubtimeframeDuplicateTimestampError as exc:
        _clear_loaded_subtimeframe_after_failed_upload(st)
        st.session_state[SUBTIMEFRAME_DUPLICATE_REPORT_KEY] = exc.report
        st.session_state[SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY] = upload_signature
        st.session_state[SUBTIMEFRAME_DUPLICATE_SOURCE_KEY] = exc.source
        st.error(str(exc))
        st.rerun()
    except SubtimeframeCompatibilityError as exc:
        _clear_loaded_subtimeframe_after_failed_upload(st)
        st.session_state[SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY] = exc.report
        st.session_state[SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY] = upload_signature
        st.error(str(exc))
        st.rerun()
    except (DataValidationError, ValueError) as exc:
        _clear_loaded_subtimeframe_after_failed_upload(st)
        st.error(str(exc))


def _render_subtimeframe_loaded_state(st) -> None:
    subtimeframe_df = st.session_state.get("subtimeframe_data")
    if not isinstance(subtimeframe_df, pd.DataFrame):
        return
    interval = st.session_state.get("subtimeframe_interval", "unknown interval")
    st.info(f"Lower-timeframe data loaded: {len(subtimeframe_df):,} bars at {interval}.")
    fallback_bars = st.session_state.get(SUBTIMEFRAME_FALLBACK_BARS_KEY, [])
    if fallback_bars:
        st.caption(
            f"Conservative lower-timeframe fallback is required for {len(fallback_bars):,} "
            "parent bars; the strict model remains unavailable."
        )
    if st.button("Remove lower-timeframe data"):
        _clear_subtimeframe_state(st)
        st.rerun()


def render_subtimeframe_upload(
    st,
    parent_df: pd.DataFrame,
    *,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
    profile_options: dict,
    format_profiles,
) -> None:
    """Render the optional interactive R12 lower-timeframe import."""
    with st.expander(LEGACY_SUBTIMEFRAME_EXPANDER_TITLE, expanded=False):
        st.caption(
            "Legacy path: upload separately exported lower OHLCV bars for R12 "
            "replay. They must cover and reconcile exactly to every main-chart "
            "bar. For Quantower 15-second exports, prefer Recommended "
            "15-second primary ingestion instead."
        )
        subtimeframe_format_profile = st.selectbox(
            "Lower CSV format profile",
            options=format_profiles,
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
        _render_subtimeframe_duplicate_report(
            st,
            parent_df=parent_df,
            instrument=instrument,
            upload_signature=upload_signature,
        )
        _render_subtimeframe_compatibility_report(st, upload_signature=upload_signature)
        _apply_new_subtimeframe_upload(
            st,
            uploaded_file,
            parent_df=parent_df,
            instrument=instrument,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=subtimeframe_format_profile,
            upload_signature=upload_signature,
        )
        _render_subtimeframe_loaded_state(st)
