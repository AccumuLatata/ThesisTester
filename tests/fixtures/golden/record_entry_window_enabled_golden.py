"""Record the enabled entry_window golden artifacts (SW2).

Additive golden family — does not rewrite legacy or OTF golden files.

    python -m tests.fixtures.golden.record_entry_window_enabled_golden --confirm-regenerate
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
from .generate_entry_window_enabled import ENTRY_WINDOW, INSTRUMENT, TIMEZONE
from .pipeline_entry_window_enabled import BACKTEST_CONFIG, run_entry_window_enabled_pipeline

FIXTURE_DIR = Path(__file__).resolve().parent
DATASET_PATH = FIXTURE_DIR / "entry_window_enabled_dataset.parquet"
TRADES_CSV_PATH = FIXTURE_DIR / "entry_window_enabled_trades.csv"
SKIPPED_CSV_PATH = FIXTURE_DIR / "entry_window_enabled_skipped.csv"
PROJECTION_PATH = FIXTURE_DIR / "entry_window_enabled_projection.json"
MANIFEST_PATH = FIXTURE_DIR / "entry_window_enabled_manifest.json"

_SKIP_PROJECTION_COLUMNS = [
    "signal_id",
    "bar_index",
    "entry_bar_index",
    "trigger",
    "direction",
    "skip_reason",
]


def _replace_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _replace_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def _skip_projection(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in _SKIP_PROJECTION_COLUMNS if column in frame.columns]
    return canonicalize_trades(frame.loc[:, columns].copy())


def record() -> None:
    """Regenerate enabled entry_window golden artifacts from current behavior."""
    result = run_entry_window_enabled_pipeline(enabled=True)
    data = result["data"]
    trades = result["trades"]
    skipped = result["skipped_signals"]
    projection = result["projection"]
    pandas_major = int(pd.__version__.split(".", maxsplit=1)[0])

    if len(trades) == 0:
        raise RuntimeError("Enabled entry_window golden produced zero accepted trades.")
    window_skips = skipped[skipped["skip_reason"] == "outside_entry_window"]
    if len(window_skips) == 0:
        raise RuntimeError("Enabled entry_window golden produced zero window skips.")

    manifest = {
        "fixture_version": 1,
        "family": "entry_window_enabled",
        "thesistester_version": __version__,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "module": "tests.fixtures.golden.generate_entry_window_enabled",
            "algorithm": "rth_open_30m_boundary_v1",
            "instrument": INSTRUMENT,
            "timezone": TIMEZONE,
            "entry_window": ENTRY_WINDOW,
        },
        "pipeline": {
            "entrypoint": (
                "tests.fixtures.golden.pipeline_entry_window_enabled."
                "run_entry_window_enabled_pipeline"
            ),
            "backtest_config": BACKTEST_CONFIG,
        },
        "artifacts": {
            "dataset": DATASET_PATH.name,
            "trades_csv": TRADES_CSV_PATH.name,
            "skipped_csv": SKIPPED_CSV_PATH.name,
            "projection": PROJECTION_PATH.name,
            "accepted_trade_count": projection["accepted_trade_count"],
            "outside_entry_window_skip_count": projection["outside_entry_window_skip_count"],
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
        TRADES_CSV_PATH,
        canonicalize_trades(trades).to_csv(index=False, float_format="%.17g"),
    )
    _replace_text(
        SKIPPED_CSV_PATH,
        _skip_projection(window_skips).to_csv(index=False, float_format="%.17g"),
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
            "Refusing to rewrite enabled entry_window golden artifacts without "
            "--confirm-regenerate (see tests/fixtures/golden/README.md)."
        )
    record()
    print(f"Recorded enabled entry_window golden artifacts in {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
