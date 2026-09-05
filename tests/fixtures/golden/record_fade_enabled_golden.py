"""Record the enabled fade golden artifacts (DA4).

Additive golden family — does not rewrite legacy, OTF, or entry_window files.

    python -m tests.fixtures.golden.record_fade_enabled_golden --confirm-regenerate
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
from .generate_fade_enabled import INSTRUMENT, TIMEZONE
from .pipeline_fade_enabled import BACKTEST_CONFIG, run_fade_enabled_pipeline

FIXTURE_DIR = Path(__file__).resolve().parent
DATASET_PATH = FIXTURE_DIR / "fade_enabled_dataset.parquet"
SIGNALS_CSV_PATH = FIXTURE_DIR / "fade_enabled_signals.csv"
TRADES_CSV_PATH = FIXTURE_DIR / "fade_enabled_trades.csv"
PROJECTION_PATH = FIXTURE_DIR / "fade_enabled_projection.json"
MANIFEST_PATH = FIXTURE_DIR / "fade_enabled_manifest.json"

_SIGNAL_PROJECTION_COLUMNS = [
    "signal_id",
    "bar_index",
    "trigger",
    "direction",
    "approach_side",
    "entry_model",
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
    result = run_fade_enabled_pipeline()
    data = result["data"]
    signals = result["signals"]
    trades = result["trades"]
    projection = result["projection"]
    pandas_major = int(pd.__version__.split(".", maxsplit=1)[0])

    if len(signals) == 0:
        raise RuntimeError("Enabled fade golden produced zero fade candidates.")
    if projection["collision_pairs"] != 0:
        raise RuntimeError("Enabled fade golden expected zero collision pairs on one zone.")
    if set(projection["candidate_directions"]) != {"long", "short"}:
        raise RuntimeError("Enabled fade golden expected both long and short candidates.")

    manifest = {
        "fixture_version": 1,
        "family": "fade_enabled",
        "thesistester_version": __version__,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "module": "tests.fixtures.golden.generate_fade_enabled",
            "algorithm": "one_zone_approach_touch_v1",
            "instrument": INSTRUMENT,
            "timezone": TIMEZONE,
            "trigger": "fade",
        },
        "pipeline": {
            "entrypoint": "tests.fixtures.golden.pipeline_fade_enabled.run_fade_enabled_pipeline",
            "backtest_config": BACKTEST_CONFIG,
        },
        "artifacts": {
            "dataset": DATASET_PATH.name,
            "signals_csv": SIGNALS_CSV_PATH.name,
            "trades_csv": TRADES_CSV_PATH.name,
            "projection": PROJECTION_PATH.name,
            "candidate_signal_count": projection["candidate_signal_count"],
            "accepted_trade_count": projection["accepted_trade_count"],
            "collision_pairs": projection["collision_pairs"],
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
        SIGNALS_CSV_PATH,
        _signal_projection(signals).to_csv(index=False, float_format="%.17g"),
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
            "Refusing to rewrite enabled fade golden artifacts without "
            "--confirm-regenerate (see tests/fixtures/golden/README.md)."
        )
    record()
    print(f"Recorded enabled fade golden artifacts in {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
