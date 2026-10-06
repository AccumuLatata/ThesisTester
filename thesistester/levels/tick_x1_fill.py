"""TS4 X1 15s residual fill + parent-only farm impact report.

Fills only ``[2025-11-07 17:58:14.581, 2025-11-07 19:00:00.009)`` UTC from
15s residual typical-price Last×Volume (§6). Shared empty 16:49–17:58 is not
filled. ``tick_stitch_x1_burst_included`` is a required boolean (no silent
default). Q9 is still Accumu's call — this module reports all three variants
and does not pick one. The missing-key reject is TS5/TS6.

Not an execute hook. TS5 will call :func:`fill_x1_15s_residual` (via
``tick_stitch.apply_x1_residual_fill``) after clip and before the hourly
guard. Revert TS5 first, then this module.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, Mapping

import numpy as np
import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import TickChunk
from thesistester.levels.apoc_candidates import (
    VOLUME_CONSERVATION_ATOL,
    VOLUME_CONSERVATION_RTOL,
    compute_tick_last_volume_profile,
    select_a_period_rows,
)
from thesistester.levels.profile import _bucket_prices
from thesistester.levels.tick_vap import (
    PriorProfileTable,
    _family_rows,
    _normalize_table_frame,
    _session_histogram,
    build_prior_profile_table,
    map_shifted_prior_profile,
)

_NAS_TRADING_MARKER: Final[tuple[str, str]] = ("mnt", "nas-trading")

X1_TRADE_DATE: Final[date] = date(2025, 11, 7)
X1_WINDOW_START: Final[pd.Timestamp] = pd.Timestamp("2025-11-07 17:58:14.581", tz="UTC")
X1_WINDOW_END: Final[pd.Timestamp] = pd.Timestamp("2025-11-07 19:00:00.009", tz="UTC")
X1_BURST_START: Final[pd.Timestamp] = pd.Timestamp("2025-11-07 18:00:45", tz="UTC")
X1_BURST_END: Final[pd.Timestamp] = pd.Timestamp("2025-11-07 18:01:30", tz="UTC")
X1_FILL_OFFSET: Final[pd.Timedelta] = pd.Timedelta(milliseconds=7500)
_BAR_INTERVAL: Final[pd.Timedelta] = pd.Timedelta(seconds=15)
PD_LOOKAHEAD_DATE: Final[date] = date(2025, 11, 10)
STUDY_DAY_AGG: Final[int] = 4
STUDY_WEEK_AGG: Final[int] = 8
STUDY_MONTH_AGG: Final[int] = 10

VARIANT_TICKS_ONLY: Final[str] = "ticks_only"
VARIANT_FILL_WITHOUT_BURST: Final[str] = "fill_without_burst"
VARIANT_FILL_WITH_BURST: Final[str] = "fill_with_burst"
IMPACT_VARIANTS: Final[tuple[str, ...]] = (
    VARIANT_TICKS_ONLY,
    VARIANT_FILL_WITHOUT_BURST,
    VARIANT_FILL_WITH_BURST,
)


class X1FillError(ValueError):
    """Raised when the X1 residual fill input violates the locked contract."""


@dataclass(frozen=True)
class X1FillQuality:
    """Per-session quality record (§6.5). Not trade-frame columns."""

    x1_15s_residual_fill: bool
    x1_burst_included: bool
    shared_gap_1649_1758: bool
    x1_burst: bool
    n_synthetics: int
    residual_volume: float
    burst_synthetic_volume: float

    def as_data_quality(self) -> dict[str, bool]:
        return {
            "data_quality.x1_15s_residual_fill": self.x1_15s_residual_fill,
            "data_quality.x1_burst_included": self.x1_burst_included,
            "data_quality.shared_gap_1649_1758": self.shared_gap_1649_1758,
        }


def fill_x1_15s_residual(
    ticks: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    tick_stitch_x1_burst_included: bool,
    session_date: date,
    tick_size: float,
) -> tuple[pd.DataFrame, X1FillQuality]:
    """Append residual typical-price synthetics inside the locked X1 window.

    ``tick_stitch_x1_burst_included`` has no default. Burst bars
    ``[18:00:45, 18:01:30)`` UTC use the same residual rule when True and
    residual 0 when False. Synthetics are timestamped at ``bar_ts + 7.5s``.
    """
    burst_included = _require_explicit_burst_flag(tick_stitch_x1_burst_included)
    if session_date != X1_TRADE_DATE:
        return ticks.copy().reset_index(drop=True), _empty_quality(burst_included)
    if tick_size <= 0 or not np.isfinite(tick_size):
        raise X1FillError("tick_size must be a positive finite value.")
    bar_work = _validated_bars(bars)
    tick_work = _validated_ticks(ticks)
    fillable = _fillable_x1_bars(bar_work)
    if fillable.empty:
        return tick_work.copy(), _session_quality(
            burst_included,
            n_synthetics=0,
            residual_volume=0.0,
            burst_synthetic_volume=0.0,
            x1_burst=False,
        )

    tick_vol = _tick_volume_by_bar(tick_work)
    residual = _bar_residuals(fillable, tick_vol, burst_included=burst_included)
    expected_residual = float(residual.sum())
    synthetics = _residual_synthetics(fillable, residual, tick_size=tick_size)
    if synthetics.empty:
        filled = tick_work.copy()
        burst_volume = 0.0
        residual_volume = 0.0
    else:
        filled = (
            pd.concat([tick_work, synthetics], ignore_index=True)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        burst_mask = _is_burst_bar(synthetics["timestamp"] - X1_FILL_OFFSET)
        burst_volume = float(synthetics.loc[burst_mask.to_numpy(), "volume"].sum())
        residual_volume = float(synthetics["volume"].sum())
    if not np.isclose(
        residual_volume,
        expected_residual,
        rtol=VOLUME_CONSERVATION_RTOL,
        atol=VOLUME_CONSERVATION_ATOL,
    ):
        raise X1FillError("X1 residual fill failed volume conservation.")
    return filled, _session_quality(
        burst_included,
        n_synthetics=int(len(synthetics)),
        residual_volume=residual_volume,
        burst_synthetic_volume=burst_volume,
        x1_burst=burst_volume > 0,
    )


def reject_x1_synthetics(ticks: pd.DataFrame) -> pd.DataFrame:
    """Drop X1-window rows so APOC never sees residual synthetics (§6.4)."""
    if ticks.empty or "timestamp" not in ticks.columns:
        return ticks.copy().reset_index(drop=True)
    stamps = _utc_series(ticks["timestamp"])
    keep = (stamps < X1_WINDOW_START) | (stamps >= X1_WINDOW_END)
    out = ticks.loc[keep.to_numpy()].copy()
    out["timestamp"] = stamps.loc[keep].to_numpy()
    return out.reset_index(drop=True)


def session_apoc_poc(
    ticks: pd.DataFrame,
    *,
    session_date: date,
    tick_size: float,
    exchange_tz: str,
) -> float:
    """A-period Last×Volume POC after rejecting X1-window rows."""
    cleaned = reject_x1_synthetics(ticks)
    selected = select_a_period_rows(
        cleaned,
        session_date=session_date,
        exchange_tz=exchange_tz,
    )
    if selected.empty:
        return float("nan")
    result = compute_tick_last_volume_profile(selected, tick_size=tick_size)
    return float(result.poc)


def build_synthetic_impact_report(
    session_ticks: Mapping[date, pd.DataFrame],
    bars: pd.DataFrame,
    *,
    instrument: str = "MNQ",
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = STUDY_DAY_AGG,
    prior_week_aggregation_ticks: int = STUDY_WEEK_AGG,
    prior_month_aggregation_ticks: int = STUDY_MONTH_AGG,
) -> dict[str, Any]:
    """CI / desk impact triples for the three explicit burst variants.

    None of the variants is a product default. Does not assert a preferred VA.
    """
    if instrument not in INSTRUMENTS:
        raise X1FillError(f"Unsupported instrument: {instrument}")
    inst = INSTRUMENTS[instrument]
    variants: dict[str, dict[str, Any]] = {}
    apoc_values: list[float] = []
    for variant in IMPACT_VARIANTS:
        chunks: list[TickChunk] = []
        apoc = float("nan")
        for session_date, ticks in sorted(session_ticks.items()):
            work = ticks.copy().reset_index(drop=True)
            if session_date == X1_TRADE_DATE and variant != VARIANT_TICKS_ONLY:
                work, _quality = fill_x1_15s_residual(
                    work,
                    bars,
                    tick_stitch_x1_burst_included=variant == VARIANT_FILL_WITH_BURST,
                    session_date=session_date,
                    tick_size=inst.tick_size,
                )
            if session_date == X1_TRADE_DATE:
                apoc = session_apoc_poc(
                    work,
                    session_date=session_date,
                    tick_size=inst.tick_size,
                    exchange_tz=inst.exchange_tz,
                )
            chunks.append(_chunk_from_ticks(session_date, work))
        table = build_prior_profile_table(
            chunks,
            instrument=instrument,
            value_area_pct=value_area_pct,
            prior_day_aggregation_ticks=prior_day_aggregation_ticks,
            prior_week_aggregation_ticks=prior_week_aggregation_ticks,
            prior_month_aggregation_ticks=prior_month_aggregation_ticks,
        )
        row = _extract_required_triple(table)
        row["apoc_2025-11-07"] = apoc
        variants[variant] = row
        apoc_values.append(apoc)
    return _finish_impact_report(variants, apoc_values)


def run_farm_impact_report(
    plan: str | Path,
    root: str | Path,
    bars_path: str | Path,
    *,
    instrument: str = "MNQ",
    format_profile: str = "quantower_history_exporter",
    source_tz: str = "UTC",
    target_tz: str = "UTC",
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = STUDY_DAY_AGG,
    prior_week_aggregation_ticks: int = STUDY_WEEK_AGG,
    prior_month_aggregation_ticks: int = STUDY_MONTH_AGG,
) -> dict[str, Any]:
    """Parent-only NVMe stitch impact. Not a worker. Not CI. Do not run on farm here.

    Does not call ``guard_hourly_tick_holes``. Ticks-only and burst-off still
    emit (the TS3 option-A X1 18:00 guard remains an escalated plan-vs-code
    point; this report must not abort on it).
    """
    from thesistester.data.loader import load_ohlcv
    from thesistester.data.tick_stitch import (
        clip_ticks_to_15s_bars,
        iter_stitch_sessions,
        verify_tick_stitch_plan,
    )

    _refuse_nas_trading_paths(plan, root, bars_path)
    if instrument not in INSTRUMENTS:
        raise X1FillError(f"Unsupported instrument: {instrument}")
    inst = INSTRUMENTS[instrument]
    verify_tick_stitch_plan(plan, root)
    bars = load_ohlcv(
        bars_path,
        tz=target_tz,
        source_tz=source_tz,
        target_tz=target_tz,
        format_profile=format_profile,  # type: ignore[arg-type]
    )
    bars = bars.copy()
    bars["timestamp"] = _utc_series(bars["timestamp"])
    shared_hists: list[Any] = []
    x1_ticks: pd.DataFrame | None = None
    for chunk in iter_stitch_sessions(plan, root, instrument=instrument):
        clipped = clip_ticks_to_15s_bars(chunk.ticks, bars["timestamp"])
        if chunk.session_date == X1_TRADE_DATE:
            x1_ticks = clipped
            continue
        hist = _session_histogram(
            _chunk_from_ticks(chunk.session_date, clipped),
            tick_size=inst.tick_size,
        )
        if hist is not None:
            shared_hists.append(hist)

    variants: dict[str, dict[str, Any]] = {}
    apoc_values: list[float] = []
    for variant in IMPACT_VARIANTS:
        hists = list(shared_hists)
        work = pd.DataFrame(columns=["timestamp", "price", "volume"])
        if x1_ticks is not None:
            work = x1_ticks.copy()
            if variant != VARIANT_TICKS_ONLY:
                work, _quality = fill_x1_15s_residual(
                    work,
                    bars,
                    tick_stitch_x1_burst_included=variant == VARIANT_FILL_WITH_BURST,
                    session_date=X1_TRADE_DATE,
                    tick_size=inst.tick_size,
                )
            hist = _session_histogram(
                _chunk_from_ticks(X1_TRADE_DATE, work),
                tick_size=inst.tick_size,
            )
            if hist is not None:
                hists.append(hist)
        table = _table_from_histograms(
            hists,
            instrument=instrument,
            value_area_pct=value_area_pct,
            prior_day_aggregation_ticks=prior_day_aggregation_ticks,
            prior_week_aggregation_ticks=prior_week_aggregation_ticks,
            prior_month_aggregation_ticks=prior_month_aggregation_ticks,
        )
        row = _extract_required_triple(table)
        apoc = (
            session_apoc_poc(
                work,
                session_date=X1_TRADE_DATE,
                tick_size=inst.tick_size,
                exchange_tz=inst.exchange_tz,
            )
            if x1_ticks is not None
            else float("nan")
        )
        row["apoc_2025-11-07"] = apoc
        variants[variant] = row
        apoc_values.append(apoc)
    return _finish_impact_report(variants, apoc_values)


def main(argv: list[str] | None = None) -> int:
    """``python -m thesistester.levels.tick_x1_fill farm-impact PLAN ROOT BARS``."""
    parser = argparse.ArgumentParser(prog="python -m thesistester.levels.tick_x1_fill")
    sub = parser.add_subparsers(dest="command", required=True)
    impact = sub.add_parser(
        "farm-impact",
        help="Parent-only NVMe stitch impact (not CI; do not run on farm from TS4)",
    )
    impact.add_argument("plan", type=Path, help="Path to tick_stitch_plan.json")
    impact.add_argument("root", type=Path, help="Directory of local tick CSV copies")
    impact.add_argument("bars", type=Path, help="Run 2 15s OHLCV CSV")
    impact.add_argument("--instrument", default="MNQ")
    impact.add_argument("--format-profile", default="quantower_history_exporter")
    impact.add_argument("--source-tz", default="UTC")
    impact.add_argument("--target-tz", default="UTC")
    impact.add_argument("--prior-day-aggregation-ticks", type=int, default=STUDY_DAY_AGG)
    impact.add_argument("--prior-week-aggregation-ticks", type=int, default=STUDY_WEEK_AGG)
    impact.add_argument("--prior-month-aggregation-ticks", type=int, default=STUDY_MONTH_AGG)
    args = parser.parse_args(argv)
    if args.command != "farm-impact":
        raise AssertionError(f"Unhandled command: {args.command}")
    from thesistester.data.loader import DataValidationError

    try:
        report = run_farm_impact_report(
            args.plan,
            args.root,
            args.bars,
            instrument=args.instrument,
            format_profile=args.format_profile,
            source_tz=args.source_tz,
            target_tz=args.target_tz,
            prior_day_aggregation_ticks=args.prior_day_aggregation_ticks,
            prior_week_aggregation_ticks=args.prior_week_aggregation_ticks,
            prior_month_aggregation_ticks=args.prior_month_aggregation_ticks,
        )
    except (X1FillError, DataValidationError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return os.EX_DATAERR
    print(json.dumps(report, indent=2, sort_keys=True, default=_json_default))
    return os.EX_OK


def _require_explicit_burst_flag(value: object) -> bool:
    if type(value) is not bool:
        raise TypeError(
            "tick_stitch_x1_burst_included must be an explicit bool "
            "(no silent default; Q9 is Accumu's call)."
        )
    return value


def _empty_quality(burst_included: bool) -> X1FillQuality:
    return X1FillQuality(
        x1_15s_residual_fill=False,
        x1_burst_included=burst_included,
        shared_gap_1649_1758=False,
        x1_burst=False,
        n_synthetics=0,
        residual_volume=0.0,
        burst_synthetic_volume=0.0,
    )


def _session_quality(
    burst_included: bool,
    *,
    n_synthetics: int,
    residual_volume: float,
    burst_synthetic_volume: float,
    x1_burst: bool,
) -> X1FillQuality:
    return X1FillQuality(
        x1_15s_residual_fill=True,
        x1_burst_included=burst_included,
        shared_gap_1649_1758=True,
        x1_burst=x1_burst,
        n_synthetics=n_synthetics,
        residual_volume=residual_volume,
        burst_synthetic_volume=burst_synthetic_volume,
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = ("timestamp", "high", "low", "close", "volume")
    missing = [column for column in required if column not in bars.columns]
    if missing:
        raise X1FillError(f"X1 fill bars require columns: {missing}.")
    work = bars.loc[:, list(required)].copy()
    work["timestamp"] = _utc_series(work["timestamp"])
    for column in ("high", "low", "close", "volume"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["timestamp", "high", "low", "close", "volume"])
    if (work["volume"] < 0).any():
        raise X1FillError("X1 fill bar volume cannot be negative.")
    if (work["high"] < work["low"]).any():
        raise X1FillError("X1 fill bars contain high below low.")
    return work.reset_index(drop=True)


def _validated_ticks(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame(columns=["timestamp", "price", "volume"])
    required = ("timestamp", "price", "volume")
    missing = [column for column in required if column not in ticks.columns]
    if missing:
        raise X1FillError(f"X1 fill ticks require columns: {missing}.")
    work = ticks.loc[:, list(required)].copy()
    work["timestamp"] = _utc_series(work["timestamp"])
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce")
    work = work.dropna(subset=["timestamp", "price", "volume"])
    work = work.loc[work["volume"] > 0]
    return work.reset_index(drop=True)


def _fillable_x1_bars(bars: pd.DataFrame) -> pd.DataFrame:
    left = bars["timestamp"]
    placed = left + X1_FILL_OFFSET
    # Left edge in the window (excludes 17:58:00). Placement must also stay
    # inside the window so fill timestamps cannot land at 19:00:07.5.
    keep = (left >= X1_WINDOW_START) & (left < X1_WINDOW_END)
    keep = keep & (placed >= X1_WINDOW_START) & (placed < X1_WINDOW_END)
    return bars.loc[keep].copy().reset_index(drop=True)


def _tick_volume_by_bar(ticks: pd.DataFrame) -> pd.Series:
    if ticks.empty:
        return pd.Series(dtype="float64")
    floors = ticks["timestamp"].dt.floor("15s")
    return ticks.groupby(floors, sort=True)["volume"].sum()


def _is_burst_bar(left_edges: pd.DatetimeIndex | pd.Series) -> pd.Series:
    values = pd.DatetimeIndex(pd.Series(left_edges).to_numpy())
    right = values + _BAR_INTERVAL
    return pd.Series((values < X1_BURST_END) & (right > X1_BURST_START), dtype=bool)


def _bar_residuals(
    bars: pd.DataFrame,
    tick_vol: pd.Series,
    *,
    burst_included: bool,
) -> np.ndarray:
    left = pd.DatetimeIndex(bars["timestamp"])
    burst = _is_burst_bar(left).to_numpy()
    aligned = tick_vol.reindex(left, fill_value=0.0).to_numpy(dtype="float64")
    residual = np.maximum(0.0, bars["volume"].to_numpy(dtype="float64") - aligned)
    return np.where(burst & (not burst_included), 0.0, residual)


def _residual_synthetics(
    bars: pd.DataFrame,
    residual: np.ndarray,
    *,
    tick_size: float,
) -> pd.DataFrame:
    left = pd.DatetimeIndex(bars["timestamp"])
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    price = np.asarray(_bucket_prices(typical, tick_size), dtype="float64")
    keep = residual > 0
    if not keep.any():
        return pd.DataFrame(columns=["timestamp", "price", "volume"])
    return pd.DataFrame(
        {
            "timestamp": left.to_numpy()[keep] + X1_FILL_OFFSET,
            "price": price[keep],
            "volume": residual[keep],
        }
    ).reset_index(drop=True)


def _refuse_nas_trading_paths(*paths: str | Path) -> None:
    """Farm-impact is NVMe-only. Never open ``/mnt/nas-trading`` (not even in CI)."""
    for raw in paths:
        parts = Path(raw).expanduser().parts
        for index in range(len(parts) - 1):
            if (
                parts[index] == _NAS_TRADING_MARKER[0]
                and parts[index + 1] == _NAS_TRADING_MARKER[1]
            ):
                raise X1FillError(
                    "farm-impact refuses /mnt/nas-trading (NVMe stitch only; not a CI or SMB path)."
                )


def _utc_series(values: pd.Series) -> pd.Series:
    stamps = pd.to_datetime(values, utc=True)
    if getattr(stamps.dt, "tz", None) is None:
        stamps = stamps.dt.tz_localize("UTC")
    return stamps.dt.tz_convert("UTC")


def _chunk_from_ticks(session_date: date, ticks: pd.DataFrame) -> TickChunk:
    work = ticks.loc[:, ["timestamp", "price", "volume"]].copy() if not ticks.empty else ticks
    if work.empty:
        dummy = pd.Timestamp("2025-11-07 14:30:00", tz="UTC")
        first = last = dummy
        frame = pd.DataFrame(columns=["timestamp", "price", "volume"])
    else:
        work["timestamp"] = _utc_series(work["timestamp"])
        first = pd.Timestamp(work["timestamp"].min())
        last = pd.Timestamp(work["timestamp"].max())
        frame = work.reset_index(drop=True)
    return TickChunk(
        session_date=session_date,
        ticks=frame,
        source_paths=("x1_fill",),
        filename_window_mismatch=False,
        warnings=(),
        first_row_utc=first,
        last_row_utc=last,
        filename_window_start=None,
        filename_window_end=None,
    )


def _table_from_histograms(
    sessions: list[Any],
    *,
    instrument: str,
    value_area_pct: float,
    prior_day_aggregation_ticks: int,
    prior_week_aggregation_ticks: int,
    prior_month_aggregation_ticks: int,
) -> PriorProfileTable:
    inst = INSTRUMENTS[instrument]
    rows: list[dict[str, object]] = []
    rows.extend(
        _family_rows(
            sessions,
            family="pd",
            period_attr="day_key",
            aggregation_ticks=prior_day_aggregation_ticks,
            tick_size=inst.tick_size * prior_day_aggregation_ticks,
            value_area_pct=value_area_pct,
        )
    )
    rows.extend(
        _family_rows(
            sessions,
            family="pw",
            period_attr="week_key",
            aggregation_ticks=prior_week_aggregation_ticks,
            tick_size=inst.tick_size * prior_week_aggregation_ticks,
            value_area_pct=value_area_pct,
        )
    )
    rows.extend(
        _family_rows(
            sessions,
            family="pm",
            period_attr="month_key",
            aggregation_ticks=prior_month_aggregation_ticks,
            tick_size=inst.tick_size * prior_month_aggregation_ticks,
            value_area_pct=value_area_pct,
        )
    )
    return PriorProfileTable(frame=_normalize_table_frame(pd.DataFrame(rows)))


def _triple_payload(vah: object, val: object, poc: object) -> dict[str, float]:
    return {
        "VAH": _maybe_float(vah),
        "VAL": _maybe_float(val),
        "POC": _maybe_float(poc),
    }


def _extract_required_triple(table: PriorProfileTable) -> dict[str, Any]:
    """11-07 VA, 11-10 pd*, W-SUN pw*, Nov pm*, December prior-month VA (Q6)."""
    pd_rows = table.family_rows("pd")
    pw_rows = table.family_rows("pw")
    pm_rows = table.family_rows("pm")
    week_key = pd.Timestamp(X1_TRADE_DATE).to_period("W-SUN")
    nov_key = pd.Timestamp(X1_TRADE_DATE).to_period("M")
    session_va = _lookup_family_row(pd_rows, X1_TRADE_DATE)
    week_va = _lookup_family_row(pw_rows, week_key)
    nov_pm = _lookup_family_row(pm_rows, nov_key)
    lookahead = pd.Series([X1_TRADE_DATE, PD_LOOKAHEAD_DATE], name="period")
    pd_shifted = map_shifted_prior_profile(lookahead, table, family="pd")
    pd_1110 = pd_shifted.iloc[-1]
    month_keys = pd.Series(
        [pd.Period("2025-11", freq="M"), pd.Period("2025-12", freq="M")],
        name="period",
    )
    pm_shifted = map_shifted_prior_profile(month_keys, table, family="pm")
    dec_prior = pm_shifted.iloc[-1]
    return {
        "session_2025-11-07": _triple_payload(
            session_va.get("VAH"), session_va.get("VAL"), session_va.get("POC")
        ),
        "pd_2025-11-10": _triple_payload(pd_1110["pdVAH"], pd_1110["pdVAL"], pd_1110["pdPOC"]),
        "pw_w_sun_containing_2025-11-07": {
            "period_key": str(week_key),
            **_triple_payload(week_va.get("VAH"), week_va.get("VAL"), week_va.get("POC")),
        },
        "pm_2025-11": _triple_payload(nov_pm.get("VAH"), nov_pm.get("VAL"), nov_pm.get("POC")),
        "pm_prior_month_2025-12": _triple_payload(
            dec_prior["pmVAH"], dec_prior["pmVAL"], dec_prior["pmPOC"]
        ),
    }


def _lookup_family_row(frame: pd.DataFrame, key: object) -> Mapping[str, object]:
    if frame.empty:
        return {"VAH": float("nan"), "VAL": float("nan"), "POC": float("nan")}
    matched = frame.loc[frame["period_key"].map(lambda item: item == key)]
    if matched.empty:
        matched = frame.loc[frame["period_key"].map(lambda item: str(item) == str(key))]
    if matched.empty:
        return {"VAH": float("nan"), "VAL": float("nan"), "POC": float("nan")}
    row = matched.iloc[0]
    return {"VAH": row["VAH"], "VAL": row["VAL"], "POC": row["POC"]}


def _finish_impact_report(
    variants: Mapping[str, Mapping[str, Any]],
    apoc_values: list[float],
) -> dict[str, Any]:
    apoc_identical = True
    if apoc_values:
        first = apoc_values[0]
        for value in apoc_values[1:]:
            both_nan = not np.isfinite(first) and not np.isfinite(value)
            if both_nan:
                continue
            if not np.isfinite(first) or not np.isfinite(value) or value != first:
                apoc_identical = False
                break
    return {
        "variants": dict(variants),
        "apoc_identical": bool(apoc_identical),
        "deltas": {
            "fill_without_burst_vs_ticks_only": _variant_delta(
                variants[VARIANT_FILL_WITHOUT_BURST],
                variants[VARIANT_TICKS_ONLY],
            ),
            "fill_with_burst_vs_ticks_only": _variant_delta(
                variants[VARIANT_FILL_WITH_BURST],
                variants[VARIANT_TICKS_ONLY],
            ),
            "fill_with_burst_vs_fill_without_burst": _variant_delta(
                variants[VARIANT_FILL_WITH_BURST],
                variants[VARIANT_FILL_WITHOUT_BURST],
            ),
        },
        "q9": (
            "open — Accumu sets dataset.tick_stitch_x1_burst_included from this "
            "report; no product default in TS4"
        ),
    }


def _variant_delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "session_2025-11-07",
        "pd_2025-11-10",
        "pw_w_sun_containing_2025-11-07",
        "pm_2025-11",
        "pm_prior_month_2025-12",
    ):
        left_row = left[key]
        right_row = right[key]
        out[key] = {
            field: _maybe_float(left_row[field]) - _maybe_float(right_row[field])
            for field in ("VAH", "VAL", "POC")
        }
    return out


def _maybe_float(value: object) -> float:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return float("nan")
    return float(value)


def _json_default(value: object) -> object:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
