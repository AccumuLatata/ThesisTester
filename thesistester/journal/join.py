"""Join journal trades to the 15s / derived-1m clock (TJ5).

Uses already-loaded ``data`` (1m parent) and ``subtimeframe_data`` (15s).
Optional Tick-Last prints walk with ``ts > entry_timestamp``. Does not call
``simulate_trades``, ``compute_all_levels``, or ``derive_complete_parent_ohlcv``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import math

import pandas as pd

from thesistester.journal.schema import (
    CME_MONTH_CODES,
    FLAG_EXCURSION_UNAVAILABLE,
    FLAG_MISSING_BAR,
    FLAG_PRICE_OUTSIDE_BAR,
    FLAG_ROLL_MISMATCH,
    JOIN_BAR_SECONDS,
    JOIN_OUTPUT_COLUMNS,
    JOIN_PARENT_MINUTES,
    JOIN_RESOLUTION_15S,
    JOIN_RESOLUTION_TICK,
    JOIN_RESOLUTIONS,
    JOURNAL_ETH_START,
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_TRADE_COLUMNS,
    STATUS_CLOSED,
    JournalIngestError,
)
from thesistester.levels.session_date import trading_session_date

_BAR_DELTA = pd.Timedelta(seconds=JOIN_BAR_SECONDS)
_PARENT_DELTA = pd.Timedelta(minutes=JOIN_PARENT_MINUTES)
_OHLC = ("open", "high", "low", "close")


def join_journal_bars(
    trades: pd.DataFrame,
    *,
    data: pd.DataFrame,
    subtimeframe_data: pd.DataFrame,
    ticks: pd.DataFrame | None = None,
    join_resolution: str = JOIN_RESOLUTION_15S,
    roll_metadata: Mapping[str, object] | None = None,
    series_contract: str | None = None,
) -> pd.DataFrame:
    """Attach 15s bar opens, 1m parent, ``bars_held``, and MAE/MFE.

    ``data``, ``subtimeframe_data``, ``ticks``, ``join_resolution``,
    ``roll_metadata``, and ``series_contract`` are keyword-only.
    Default ``join_resolution`` is ``15s``. Tick resolution requires a
    Last×Volume frame covering each trade's ``session_date``.
    """
    if join_resolution not in JOIN_RESOLUTIONS:
        raise JournalIngestError(
            f"join_resolution must be one of {sorted(JOIN_RESOLUTIONS)} (got {join_resolution!r})"
        )
    bars_15s = _normalize_ohlcv(subtimeframe_data, name="subtimeframe_data")
    parent_1m = _normalize_ohlcv(data, name="data")
    tick_frame = _normalize_ticks(ticks) if join_resolution == JOIN_RESOLUTION_TICK else None
    if trades.empty:
        out = trades.copy()
        for column in JOIN_OUTPUT_COLUMNS:
            out[column] = pd.Series(dtype="object")
        return out

    required = {"entry_timestamp", "entry_price", "direction", "session_date", "status"}
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))

    rows: list[dict[str, object]] = []
    for raw in trades.to_dict(orient="records"):
        rows.append(
            _join_trade(
                raw,
                bars_15s=bars_15s,
                parent_1m=parent_1m,
                ticks=tick_frame,
                join_resolution=join_resolution,
                roll_metadata=roll_metadata,
                series_contract=series_contract,
            )
        )
    frame = pd.DataFrame(rows)
    extra = [column for column in JOIN_OUTPUT_COLUMNS if column not in JOURNAL_TRADE_COLUMNS]
    ordered = [column for column in JOURNAL_TRADE_COLUMNS if column in frame.columns] + extra
    for leftover in frame.columns:
        if leftover not in ordered:
            ordered.append(leftover)
    return frame.loc[:, ordered]


def _normalize_ohlcv(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame):
        raise JournalIngestError(f"{name} must be a DataFrame")
    needed = {"timestamp", *_OHLC}
    missing = sorted(needed.difference(frame.columns))
    if missing:
        raise JournalIngestError(f"{name} missing columns: " + ", ".join(missing))
    if frame.empty:
        raise JournalIngestError(f"{name} has no bars")
    work = frame.loc[
        :, ["timestamp", *_OHLC] + (["contract"] if "contract" in frame.columns else [])
    ].copy()
    work["timestamp"] = work["timestamp"].map(_as_utc)
    for column in _OHLC:
        work[column] = pd.to_numeric(work[column], errors="coerce")
        if work[column].isna().any():
            raise JournalIngestError(f"{name} has non-finite {column}")
    work = work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if work["timestamp"].duplicated().any():
        raise JournalIngestError(f"{name} has duplicate bar opens")
    return work


def _normalize_ticks(ticks: pd.DataFrame | None) -> pd.DataFrame:
    if ticks is None or not isinstance(ticks, pd.DataFrame) or ticks.empty:
        raise JournalIngestError("join_resolution='tick' requires a non-empty ticks frame")
    if "timestamp" not in ticks.columns or "price" not in ticks.columns:
        raise JournalIngestError("ticks frame requires timestamp and price")
    work = ticks.loc[
        :,
        [
            column
            for column in ("timestamp", "price", "session_date", "_session_date")
            if column in ticks.columns
        ],
    ].copy()
    work["timestamp"] = work["timestamp"].map(_as_utc)
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    if work["price"].isna().any() or not work["price"].map(math.isfinite).all():
        raise JournalIngestError("ticks frame has non-finite price")
    if "session_date" in work.columns:
        sessions = work["session_date"]
    elif "_session_date" in work.columns:
        sessions = work["_session_date"]
    else:
        local = work["timestamp"].dt.tz_convert(JOURNAL_EXCHANGE_TZ)
        sessions = trading_session_date(local, JOURNAL_ETH_START)
    work["session_date"] = [_as_date(value) for value in sessions]
    return work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise JournalIngestError("timestamp is missing")
    if stamp.tzinfo is None:
        raise JournalIngestError(f"naive timestamp is not allowed ({stamp!r})")
    return stamp.tz_convert("UTC")


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return date.fromisoformat(str(value))


def _covering_bar(bars: pd.DataFrame, ts: pd.Timestamp, *, delta: pd.Timedelta) -> pd.Series | None:
    opens = bars["timestamp"]
    index = opens.searchsorted(ts, side="right") - 1
    if index < 0:
        return None
    row = bars.iloc[int(index)]
    open_ts = row["timestamp"]
    if open_ts <= ts < open_ts + delta:
        return row
    return None


def _completed_between(
    bars: pd.DataFrame,
    *,
    entry_bar_open: pd.Timestamp,
    exit_ts: pd.Timestamp,
) -> pd.DataFrame:
    opens = bars["timestamp"]
    close_at = opens + _BAR_DELTA
    mask = (opens > entry_bar_open) & (close_at <= exit_ts)
    return bars.loc[mask]


def _price_inside(bar: pd.Series, price: float) -> bool:
    return float(bar["low"]) <= price <= float(bar["high"])


def _month_token(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in CME_MONTH_CODES.values():
        return text
    if text in CME_MONTH_CODES:
        return CME_MONTH_CODES[text]
    compact = "".join(ch for ch in text if ch.isalnum())
    if len(compact) >= 5 and compact[-3] in CME_MONTH_CODES:
        return CME_MONTH_CODES[compact[-3]]
    for token in text.replace("_", " ").split():
        if token in CME_MONTH_CODES.values():
            return token
        if token in CME_MONTH_CODES:
            return CME_MONTH_CODES[token]
    return text if text.isalpha() else None


def _series_month(bar: pd.Series | None, *, series_contract: str | None) -> str | None:
    if bar is not None and "contract" in bar.index and bar["contract"] is not None:
        token = _month_token(bar["contract"])
        if token is not None:
            return token
    return _month_token(series_contract)


def _roll_ts(raw: object) -> pd.Timestamp | None:
    if raw is None:
        return None
    stamp = pd.Timestamp(raw)
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _gap_connects(gap: Mapping[str, object], *, trade_month: str, series_month: str) -> bool:
    previous = _month_token(gap.get("previous_contract"))
    nxt = _month_token(gap.get("next_contract"))
    if previous is None or nxt is None:
        return False
    pair = {previous, nxt}
    return trade_month in pair and series_month in pair


def _roll_metadata_covers(
    metadata: Mapping[str, object] | None,
    *,
    session_date: date,
    entry_ts: pd.Timestamp,
    trade_month: str,
    series_month: str,
) -> bool:
    """True when valid R7 metadata documents this session's contract change."""
    if not metadata or not bool(metadata.get("valid")):
        return False
    method = str(metadata.get("roll_method") or "")
    if method == "external_continuous":
        return True
    if method != "segmented_contracts":
        return False
    gaps = metadata.get("roll_gaps")
    if not isinstance(gaps, Sequence):
        return False
    for gap in gaps:
        if not isinstance(gap, Mapping):
            continue
        if not _gap_connects(gap, trade_month=trade_month, series_month=series_month):
            continue
        roll_ts = _roll_ts(gap.get("roll_timestamp"))
        if roll_ts is None:
            continue
        if roll_ts.date() == session_date or roll_ts <= entry_ts:
            return True
    return False


def _tick_sessions(ticks: pd.DataFrame) -> set[date]:
    return {_as_date(value) for value in ticks["session_date"]}


def _mae_mfe_from_bars(
    bars: pd.DataFrame, *, entry_price: float, direction: str
) -> tuple[float, float]:
    mae = 0.0
    mfe = 0.0
    for row in bars.itertuples(index=False):
        high = float(row.high)
        low = float(row.low)
        if direction == "long":
            mae = max(mae, entry_price - low)
            mfe = max(mfe, high - entry_price)
        else:
            mae = max(mae, high - entry_price)
            mfe = max(mfe, entry_price - low)
    return mae, mfe


def _mae_mfe_from_ticks(
    ticks: pd.DataFrame,
    *,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    entry_price: float,
    direction: str,
) -> tuple[float, float] | None:
    mask = (ticks["timestamp"] > entry_ts) & (ticks["timestamp"] < exit_ts)
    path = ticks.loc[mask]
    if path.empty:
        return None
    mae = 0.0
    mfe = 0.0
    for price in path["price"].astype(float):
        if direction == "long":
            mae = max(mae, entry_price - price)
            mfe = max(mfe, price - entry_price)
        else:
            mae = max(mae, price - entry_price)
            mfe = max(mfe, entry_price - price)
    return mae, mfe


def _join_trade(
    raw: Mapping[str, object],
    *,
    bars_15s: pd.DataFrame,
    parent_1m: pd.DataFrame,
    ticks: pd.DataFrame | None,
    join_resolution: str,
    roll_metadata: Mapping[str, object] | None,
    series_contract: str | None,
) -> dict[str, object]:
    row = dict(raw)
    flags: list[str] = []
    entry_ts = _as_utc(raw["entry_timestamp"])
    entry_price = float(raw["entry_price"])
    if not math.isfinite(entry_price):
        raise JournalIngestError(f"non-finite entry_price {raw['entry_price']!r}")
    direction = str(raw["direction"])
    if direction not in {"long", "short"}:
        raise JournalIngestError(f"invalid direction {direction!r}")
    session = _as_date(raw["session_date"])
    status = str(raw["status"])

    if join_resolution == JOIN_RESOLUTION_TICK:
        assert ticks is not None
        if session not in _tick_sessions(ticks):
            raise JournalIngestError(
                f"join_resolution='tick' but no Last prints for session {session}"
            )

    entry_bar = _covering_bar(bars_15s, entry_ts, delta=_BAR_DELTA)
    parent = _covering_bar(parent_1m, entry_ts, delta=_PARENT_DELTA)
    exit_ts = None
    exit_bar = None
    raw_exit = raw.get("exit_timestamp")
    if raw_exit is not None and not pd.isna(raw_exit):
        exit_ts = _as_utc(raw_exit)
        exit_bar = _covering_bar(bars_15s, exit_ts, delta=_BAR_DELTA)

    if entry_bar is None or (status == STATUS_CLOSED and exit_bar is None):
        flags.append(FLAG_MISSING_BAR)

    if entry_bar is not None and not _price_inside(entry_bar, entry_price):
        flags.append(FLAG_PRICE_OUTSIDE_BAR)
    exit_price = raw.get("exit_price")
    if (
        exit_bar is not None
        and exit_price is not None
        and not (isinstance(exit_price, float) and pd.isna(exit_price))
        and not _price_inside(exit_bar, float(exit_price))
    ):
        flags.append(FLAG_PRICE_OUTSIDE_BAR)

    trade_month = _month_token(raw.get("contract_month"))
    series_month = _series_month(entry_bar, series_contract=series_contract)
    if (
        trade_month is not None
        and series_month is not None
        and trade_month != series_month
        and not _roll_metadata_covers(
            roll_metadata,
            session_date=session,
            entry_ts=entry_ts,
            trade_month=trade_month,
            series_month=series_month,
        )
    ):
        flags.append(FLAG_ROLL_MISMATCH)

    bars_held = None
    mae = None
    mfe = None
    if (
        status == STATUS_CLOSED
        and entry_bar is not None
        and exit_ts is not None
        and exit_bar is not None
    ):
        held = _completed_between(
            bars_15s,
            entry_bar_open=entry_bar["timestamp"],
            exit_ts=exit_ts,
        )
        bars_held = int(len(held))
        if bars_held == 0:
            flags.append(FLAG_EXCURSION_UNAVAILABLE)
        elif join_resolution == JOIN_RESOLUTION_15S:
            mae, mfe = _mae_mfe_from_bars(held, entry_price=entry_price, direction=direction)
        else:
            assert ticks is not None
            walked = _mae_mfe_from_ticks(
                ticks,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                entry_price=entry_price,
                direction=direction,
            )
            if walked is None:
                flags.append(FLAG_EXCURSION_UNAVAILABLE)
            else:
                mae, mfe = walked

    row["bars_held"] = bars_held
    row["mae_points"] = mae
    row["mfe_points"] = mfe
    row["resolution"] = join_resolution
    row["entry_bar_open"] = None if entry_bar is None else entry_bar["timestamp"]
    row["exit_bar_open"] = None if exit_bar is None else exit_bar["timestamp"]
    row["parent_1m_ts"] = None if parent is None else parent["timestamp"]
    row["join_flags"] = tuple(flags)
    return row
