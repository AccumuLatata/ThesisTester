"""Record the enabled-OTF golden artifacts.

Additive golden family — does not rewrite legacy golden files.

    python -m tests.fixtures.golden.record_otf_enabled_golden --confirm-regenerate
"""

from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from thesistester import __version__

from .canonical import canonicalize_trades, dtype_families
from .generate_otf_enabled import (
    ETH_START,
    INSTRUMENT,
    MINIMUM_CONSECUTIVE_BARS,
    OTF_TIMEFRAMES,
    TIMEZONE,
)
from .pipeline_otf_enabled import BACKTEST_CONFIG, run_otf_enabled_pipeline

FIXTURE_DIR = Path(__file__).resolve().parent
DATASET_PATH = FIXTURE_DIR / "otf_enabled_dataset.parquet"
ACCEPTED_CSV_PATH = FIXTURE_DIR / "otf_enabled_accepted_signals.csv"
REJECTED_CSV_PATH = FIXTURE_DIR / "otf_enabled_rejected_signals.csv"
TRADES_CSV_PATH = FIXTURE_DIR / "otf_enabled_trades.csv"
PROJECTION_PATH = FIXTURE_DIR / "otf_enabled_projection.json"
MANIFEST_PATH = FIXTURE_DIR / "otf_enabled_manifest.json"

_SIGNAL_PROJECTION_COLUMNS = [
    "signal_id",
    "timestamp",
    "direction",
    "notes",
    "otf_filter_enabled",
    "otf_filter_passed",
    "otf_filter_reason",
    "otf_5m_state",
    "otf_5m_sequence_length",
]


def _replace_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _replace_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def _signal_projection(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in _SIGNAL_PROJECTION_COLUMNS if column in frame.columns]
    return canonicalize_trades(frame.loc[:, columns].copy())


def record() -> None:
    """Regenerate enabled-OTF golden artifacts from current behavior."""
    result = run_otf_enabled_pipeline()
    data = result["data"]
    accepted = result["accepted_signals"]
    rejected = result["rejected_signals"]
    trades = result["trades"]
    projection = result["projection"]
    pandas_major = int(pd.__version__.split(".", maxsplit=1)[0])

    if len(accepted) == 0:
        raise RuntimeError("Enabled OTF golden fixture produced zero accepted signals.")
    if len(rejected) == 0:
        raise RuntimeError("Enabled OTF golden fixture produced zero rejected signals.")
    if len(trades) == 0:
        raise RuntimeError("Enabled OTF golden fixture produced zero trades.")

    manifest = {
        "fixture_version": 1,
        "family": "otf_enabled",
        "thesistester_version": __version__,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "module": "tests.fixtures.golden.generate_otf_enabled",
            "algorithm": "overnight_eth_otf_up_down_unknown_v1",
            "instrument": INSTRUMENT,
            "timezone": TIMEZONE,
            "eth_start": ETH_START,
            "otf_timeframes": list(OTF_TIMEFRAMES),
            "minimum_consecutive_bars": MINIMUM_CONSECUTIVE_BARS,
        },
        "pipeline": {
            "entrypoint": "tests.fixtures.golden.pipeline_otf_enabled.run_otf_enabled_pipeline",
            "backtest_config": BACKTEST_CONFIG,
        },
        "artifacts": {
            "dataset": DATASET_PATH.name,
            "accepted_signals_csv": ACCEPTED_CSV_PATH.name,
            "rejected_signals_csv": REJECTED_CSV_PATH.name,
            "trades_csv": TRADES_CSV_PATH.name,
            "projection": PROJECTION_PATH.name,
            "candidate_signal_count": projection["candidate_signal_count"],
            "accepted_signal_count": projection["otf_accepted_signal_count"],
            "rejected_signal_count": projection["otf_rejected_signal_count"],
            "trade_count": projection["trade_count"],
            "trade_columns": list(trades.columns),
            "trade_dtype_families": dtype_families(trades),
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "pandas_major": pandas_major,
            "numpy": np.__version__,
            "pyarrow": version("pyarrow"),
        },
    }

    _replace_parquet(DATASET_PATH, data)
    _replace_text(
        ACCEPTED_CSV_PATH,
        _signal_projection(accepted).to_csv(index=False, float_format="%.17g"),
    )
    _replace_text(
        REJECTED_CSV_PATH,
        _signal_projection(rejected).to_csv(index=False, float_format="%.17g"),
    )
    _replace_text(
        TRADES_CSV_PATH,
        canonicalize_trades(trades).to_csv(index=False, float_format="%.17g"),
    )
    _replace_text(
        PROJECTION_PATH,
        json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _replace_text(
        MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-regenerate",
        action="store_true",
        help="Required flag acknowledging intentional golden regeneration.",
    )
    args = parser.parse_args()
    if not args.confirm_regenerate:
        raise SystemExit(
            "Refusing to rewrite enabled-OTF golden artifacts without "
            "--confirm-regenerate (see tests/fixtures/golden/README.md)."
        )
    record()
    print(f"Recorded enabled-OTF golden artifacts in {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
