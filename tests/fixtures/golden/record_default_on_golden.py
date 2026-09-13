"""Record B-3 additive default-on golden families (QI-11-02).

Does not rewrite legacy, OTF, entry_window, or fade artifacts.

    python -m tests.fixtures.golden.record_default_on_golden --confirm-regenerate
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
from .pipeline_default_on import (
    BE_CONFIG,
    FLATTEN_ON_CONFIG,
    OPPOSITE_DIRECTION_LEGACY_CONFIG,
    THREE_C_SL_FIRST_CONFIG,
    TRAIL_CONFIG,
    run_be_pipeline,
    run_flatten_on_pipeline,
    run_opposite_direction_legacy_pipeline,
    run_three_c_sl_first_pipeline,
    run_trail_pipeline,
)

FIXTURE_DIR = Path(__file__).resolve().parent

_SKIP_COLUMNS = [
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
    if frame is None or frame.empty:
        return pd.DataFrame(columns=_SKIP_COLUMNS)
    columns = [column for column in _SKIP_COLUMNS if column in frame.columns]
    return canonicalize_trades(frame.loc[:, columns].copy())


def _write_family(
    *,
    family: str,
    data: pd.DataFrame,
    trades: pd.DataFrame,
    projection: dict,
    pipeline_config: dict,
    skipped: pd.DataFrame | None = None,
    extra_artifacts: dict | None = None,
) -> None:
    if len(trades) == 0:
        raise RuntimeError(f"{family} golden produced zero trades.")
    pandas_major = int(pd.__version__.split(".", maxsplit=1)[0])
    prefix = family
    dataset_path = FIXTURE_DIR / f"{prefix}_dataset.parquet"
    trades_path = FIXTURE_DIR / f"{prefix}_trades.csv"
    projection_path = FIXTURE_DIR / f"{prefix}_projection.json"
    manifest_path = FIXTURE_DIR / f"{prefix}_manifest.json"
    artifacts = {
        "dataset": dataset_path.name,
        "trades_csv": trades_path.name,
        "projection": projection_path.name,
        "accepted_trade_count": int(len(trades)),
        "trade_columns": list(trades.columns),
        "trade_dtype_families": dtype_families(trades),
    }
    _replace_parquet(dataset_path, data)
    _replace_text(
        trades_path,
        canonicalize_trades(trades).to_csv(index=False, float_format="%.17g"),
    )
    if skipped is not None:
        skipped_path = FIXTURE_DIR / f"{prefix}_skipped.csv"
        _replace_text(
            skipped_path,
            _skip_projection(skipped).to_csv(index=False, float_format="%.17g"),
        )
        artifacts["skipped_csv"] = skipped_path.name
    if extra_artifacts:
        artifacts.update(extra_artifacts)
    _replace_text(
        projection_path,
        json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    manifest = {
        "fixture_version": 1,
        "family": family,
        "thesistester_version": __version__,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline": {
            "entrypoint": "tests.fixtures.golden.pipeline_default_on",
            "backtest_config": pipeline_config,
        },
        "artifacts": artifacts,
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "pandas_major": pandas_major,
            "numpy": np.__version__,
            "pyarrow": version("pyarrow"),
        },
    }
    _replace_text(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def record() -> None:
    flatten = run_flatten_on_pipeline()
    if "SESSION_CLOSE" not in flatten["projection"]["exit_reasons"]:
        raise RuntimeError("flatten_on golden must include a SESSION_CLOSE exit.")
    if "empty_session_close_cap" not in flatten["projection"]["skip_reasons"]:
        raise RuntimeError("flatten_on golden must include an empty_session_close_cap skip.")
    _write_family(
        family="flatten_on",
        data=flatten["data"],
        trades=flatten["trades"],
        skipped=flatten["skipped_signals"],
        projection=flatten["projection"],
        pipeline_config=FLATTEN_ON_CONFIG,
    )

    three_c = run_three_c_sl_first_pipeline()
    if three_c["projection"]["exit_reasons"] != ["EOD"]:
        raise RuntimeError("three_c_sl_first filled path must exit EOD (not pre-retrace SL).")
    if three_c["projection"]["void_signal_ids"] != [2]:
        raise RuntimeError("three_c_sl_first must record the void candidate.")
    if 2 in three_c["projection"]["accepted_signal_ids"]:
        raise RuntimeError("void 3c must not fill.")
    _write_family(
        family="three_c_sl_first",
        data=three_c["data"],
        trades=three_c["trades"],
        projection=three_c["projection"],
        pipeline_config=THREE_C_SL_FIRST_CONFIG,
    )

    be = run_be_pipeline()
    trail = run_trail_pipeline()
    if be["projection"]["exit_reasons"] != ["BE"]:
        raise RuntimeError("be_trail BE scenario must exit BE.")
    if trail["projection"]["exit_reasons"] != ["TRAIL"]:
        raise RuntimeError("be_trail TRAIL scenario must exit TRAIL.")
    _write_family(
        family="be_trail_be",
        data=be["data"],
        trades=be["trades"],
        projection=be["projection"],
        pipeline_config=BE_CONFIG,
    )
    _write_family(
        family="be_trail_trail",
        data=trail["data"],
        trades=trail["trades"],
        projection=trail["projection"],
        pipeline_config=TRAIL_CONFIG,
    )

    opposite = run_opposite_direction_legacy_pipeline()
    if opposite["projection"]["policy"] != "legacy":
        raise RuntimeError("opposite_direction_legacy must record policy=legacy.")
    if opposite["projection"]["candidate_pairs"] < 1:
        raise RuntimeError("opposite_direction_legacy must record candidate pairs.")
    _write_family(
        family="opposite_direction_legacy",
        data=opposite["data"],
        trades=opposite["trades"],
        skipped=opposite["skipped_signals"],
        projection=opposite["projection"],
        pipeline_config=OPPOSITE_DIRECTION_LEGACY_CONFIG,
        extra_artifacts={"direction_collision_diagnostic": opposite["diagnostic"]},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-regenerate",
        action="store_true",
        help="Required acknowledgement of intentional additive-family recording.",
    )
    args = parser.parse_args()
    if not args.confirm_regenerate:
        parser.error(
            "refusing to write default-on golden artifacts without --confirm-regenerate; "
            "see tests/fixtures/golden/README.md"
        )
    record()
    print(f"Recorded default-on golden families in {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
