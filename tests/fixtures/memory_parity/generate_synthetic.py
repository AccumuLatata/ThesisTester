"""Deterministic multi-day MNQ 15s Quantower fixture for the MW0 CI cells.

Covers UTC [2024-08-01, 2024-08-04) with CME hours only (halt 17:00–18:00 ET
and the weekend excluded). Dense 15-second bars in overnight + RTH windows so
``prepare_subtimeframe_conservative_context`` sees complete minutes. Three UTC
days stay well under 200 thirty-minute bars, so ``SMA_200_30min`` is NaN and
the cell-6 shape emits no trades.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

INSTRUMENT_BASE = 20000.0
HEADER = (
    "Time left;Time right;Open;High;Median;Low;Close;Typical;Volume;Quote asset volume;Weighted;"
)

# Thursday 2024-08-01 00:00 UTC through Sunday 2024-08-04 00:00 UTC.
WINDOW_START = pd.Timestamp("2024-08-01 00:00:00+00:00")
WINDOW_END = pd.Timestamp("2024-08-04 00:00:00+00:00")
EXCHANGE_TZ = "America/New_York"


def _cme_session_open(ts_utc: pd.Timestamp) -> bool:
    local = ts_utc.tz_convert(EXCHANGE_TZ)
    if local.weekday() >= 5:
        return False
    hour = local.hour
    minute = local.minute
    # 17:00–18:00 ET halt (inclusive start, exclusive end).
    if hour == 17:
        return False
    # Friday close at 17:00 ET is already excluded by the halt. Saturday/Sunday
    # rejected above. Sunday 18:00 open is outside this UTC window.
    if local.weekday() == 4 and (hour > 17 or (hour == 17 and minute >= 0)):
        return False
    return True


def _in_dense_window(ts_utc: pd.Timestamp) -> bool:
    """Keep overnight open + morning RTH so the fixture stays CI-sized."""
    local = ts_utc.tz_convert(EXCHANGE_TZ)
    minutes = local.hour * 60 + local.minute
    overnight = 18 * 60 <= minutes < 18 * 60 + 45  # 18:00–18:45 ET
    rth = 9 * 60 + 30 <= minutes < 11 * 60  # 09:30–11:00 ET
    return overnight or rth


def _ohlc_for(ts_utc: pd.Timestamp, bar_index: int) -> tuple[float, float, float, float, int]:
    local = ts_utc.tz_convert(EXCHANGE_TZ)
    session_bump = 5.0 * local.day
    base = INSTRUMENT_BASE + session_bump
    # Overnight spike establishes ONH well above later RTH prints.
    if local.hour == 18:
        wave = 80.0 + (bar_index % 4) * 0.25
    else:
        wave = (bar_index % 8) * 0.25
    open_ = base + wave
    high = open_ + 1.00
    low = open_ - 1.00
    close = open_ + 0.25
    volume = 100 + (bar_index % 17)
    return open_, high, low, close, volume


def generate_synthetic_rows() -> list[str]:
    rows: list[str] = []
    bar_index = 0
    cursor = WINDOW_START
    delta = pd.Timedelta(seconds=15)
    while cursor < WINDOW_END:
        if _cme_session_open(cursor) and _in_dense_window(cursor):
            open_, high, low, close, volume = _ohlc_for(cursor, bar_index)
            right = cursor + pd.Timedelta(milliseconds=14999)
            median = (high + low) / 2.0
            typical = (high + low + close) / 3.0
            weighted = (open_ + close) / 2.0
            left_s = cursor.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            right_s = right.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            rows.append(
                f"{left_s};{right_s};{open_:.4f};{high:.4f};{median:.4f};"
                f"{low:.4f};{close:.4f};{typical:.6f};{volume};0;{weighted:.4f};"
            )
            bar_index += 1
        cursor = cursor + delta
    return rows


def write_synthetic_csv(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_synthetic_rows()
    if len(rows) < 200:
        raise RuntimeError(f"synthetic fixture too small: {len(rows)} bars")
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def default_synthetic_path() -> Path:
    return Path(__file__).resolve().parent / "synthetic_mnq_15s.csv"


def main() -> int:
    path = write_synthetic_csv(default_synthetic_path())
    print(f"wrote {path} ({sum(1 for _ in path.open()) - 1} bars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
