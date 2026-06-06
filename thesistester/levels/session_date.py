"""Trading-session date helpers for session-based level grouping."""
from __future__ import annotations

from datetime import time

import pandas as pd


def _parse_session_start(eth_start: str | None) -> time | None:
    if eth_start is None:
        return None
    value = str(eth_start).strip()
    if value == "":
        return None
    return pd.to_datetime(value).time()


def trading_session_date(local_ts: pd.Series, eth_start: str | None) -> pd.Series:
    """Return trading-session date for exchange-local timestamps."""
    session_start = _parse_session_start(eth_start)
    base_date = pd.Series(local_ts.dt.date, index=local_ts.index)
    if session_start is None:
        return base_date

    session_date_ts = pd.to_datetime(base_date)
    after_start = local_ts.dt.time >= session_start
    session_date_ts = session_date_ts + pd.to_timedelta(after_start.astype("int64"), unit="day")
    return pd.Series(session_date_ts.dt.date, index=local_ts.index)
