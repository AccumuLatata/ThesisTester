"""Record the legacy golden artifacts.

Run only in a dedicated GOLDEN_REGEN pull request:

    python -m tests.fixtures.golden.record_golden --confirm-regenerate
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
from .generate import BARS_PER_SESSION, INSTRUMENT, SESSION_DATES, TIMEZONE, generate_dataset
from .pipeline import BACKTEST_CONFIG, BASE_INTERVAL, run_legacy_pipeline

FIXTURE_DIR = Path(__file__).resolve().parent
DATASET_PATH = FIXTURE_DIR / "dataset_nq_1m_small.parquet"
TRADES_PATH = FIXTURE_DIR / "trades_legacy.parquet"
TRADES_CSV_PATH = FIXTURE_DIR / "trades_legacy.csv"
MANIFEST_PATH = FIXTURE_DIR / "fixture_manifest.json"
BUNDLE_HASH_PATH = FIXTURE_DIR / "legacy_bundle_hash.txt"


def _replace_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _replace_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def record() -> None:
    """Regenerate all golden artifacts from current legacy behavior."""
    data = generate_dataset()
    result = run_legacy_pipeline(data)
    trades = result["trades"]
    pandas_major = int(pd.__version__.split(".", maxsplit=1)[0])
    manifest = {
        "fixture_version": 1,
        "thesistester_version": __version__,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "module": "tests.fixtures.golden.generate",
            "algorithm": "fixed_three_session_rth_both_hit_fixture_v1",
            "instrument": INSTRUMENT,
            "session_dates": list(SESSION_DATES),
            "bars_per_session": BARS_PER_SESSION,
            "base_interval": BASE_INTERVAL,
            "timezone": TIMEZONE,
        },
        "pipeline": {
            "entrypoint": "thesistester.engine.backtest.simulate_trades",
            "signal_generator": "tests.fixtures.golden.generate.generate_signals",
            "backtest_config": BACKTEST_CONFIG,
        },
        "artifacts": {
            "dataset": DATASET_PATH.name,
            "trades_parquet": TRADES_PATH.name,
            "trades_csv": TRADES_CSV_PATH.name,
            "bundle_hash": BUNDLE_HASH_PATH.name,
            "dataset_id": result["dataset_id"],
            "trade_count": int(len(trades)),
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
    _replace_parquet(TRADES_PATH, trades)
    _replace_text(
        TRADES_CSV_PATH,
        canonicalize_trades(trades).to_csv(index=False, float_format="%.17g"),
    )
    _replace_text(
        MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _replace_text(
        BUNDLE_HASH_PATH,
        f"pandas_major={pandas_major}\nsha256={result['bundle_hash']}\n",
    )
    print(f"Recorded {len(data)} bars and {len(trades)} trades.")
    print(f"Canonical bundle hash: {result['bundle_hash']}")
    print(f"Pandas major: {pandas_major}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record legacy golden-master artifacts")
    parser.add_argument(
        "--confirm-regenerate",
        action="store_true",
        help="Required acknowledgement of the GOLDEN_REGEN policy.",
    )
    args = parser.parse_args()
    if not args.confirm_regenerate:
        parser.error(
            "refusing to write golden artifacts without --confirm-regenerate; "
            "see tests/fixtures/golden/README.md §4"
        )
    record()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
