"""Session tagging (RTH vs ETH) using the instrument's exchange calendar window."""
from __future__ import annotations

import pandas as pd

from ..config import INSTRUMENTS


def tag_session(df: pd.DataFrame, instrument: str = "ES") -> pd.DataFrame:
    """Add a 'session' column ('RTH'/'ETH') based on local exchange time."""
    inst = INSTRUMENTS[instrument]
    local = df["timestamp"].dt.tz_convert(inst.exchange_tz)
    rth_start = pd.to_datetime(inst.rth_start).time()
    rth_end = pd.to_datetime(inst.rth_end).time()

    t = local.dt.time
    is_rth = (t >= rth_start) & (t < rth_end)

    out = df.copy()
    out["session"] = is_rth.map({True: "RTH", False: "ETH"})
    return out
