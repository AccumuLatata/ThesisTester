"""Run one study cell and write the §9.1 capture (flag-free, one process)."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd

from .bits import DA5_KEYS, SUMMARY_METRIC_KEYS
from .cells import (
    FULL_CELL,
    FULL_CELL_KNOWN_EXPECTANCY,
    FULL_CELL_KNOWN_TRADE_COUNT,
    CellSpec,
    build_study_mapping,
    rewrite_full_spec_dataset,
    write_study_yaml,
)
from .canonical import (
    CanonicalizeError,
    canonicalize_frame_datetimes,
    portable_canonical_bundle_hash,
)
from .compat import package_identity, resolve_hook
from .hooks import replica_expectancies_hook
from .io import cell_dir, write_capture

STORE_ENV = "THESISTESTER_STORE_DIR"


class CaptureAbort(RuntimeError):
    """A required check failed; the series must stop and report."""


def _read_zip_member_bytes(bundle: Path, name: str) -> bytes | None:
    if not bundle.is_file():
        return None
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            if name not in archive.namelist():
                return None
            return archive.read(name)
    except (OSError, zipfile.BadZipFile):
        return None


def read_bundle_trades(bundle: Path) -> pd.DataFrame:
    raw = _read_zip_member_bytes(bundle, "trades.parquet")
    if raw is None:
        raise CaptureAbort(f"bundle missing trades.parquet: {bundle}")
    return pd.read_parquet(io.BytesIO(raw))


def read_bundle_trade_summary(bundle: Path) -> dict[str, Any]:
    raw = _read_zip_member_bytes(bundle, "trade_summary.json")
    if raw is None:
        return {}
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        return {}
    nested = payload.get("trade_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    return dict(payload)


@contextmanager
def isolate_store(root: Path) -> Iterator[Path]:
    """Point ``THESISTESTER_STORE_DIR`` at a private store; restore on exit."""
    store = Path(root) / "store"
    store.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get(STORE_ENV)
    os.environ[STORE_ENV] = str(store.resolve())
    try:
        yield store
    finally:
        if previous is None:
            os.environ.pop(STORE_ENV, None)
        else:
            os.environ[STORE_ENV] = previous


def locate_full_spec() -> Path:
    """Find the smoke YAML next to this checkout or the imported package."""
    here = Path(__file__).resolve()
    rel = Path("examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml")
    candidates = [here.parents[3] / rel]
    tes_mod = resolve_hook("thesistester.research_bundle", "canonical_bundle_hash")
    tes_file = getattr(tes_mod.module, "__file__", None)
    if tes_file:
        tes_root = Path(tes_file).resolve().parents[1]
        candidates.append(tes_root / rel)
    for path in candidates:
        if path.is_file():
            return path
    raise CaptureAbort(
        "cannot find examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml "
        "beside this tooling tree or the imported thesistester package"
    )


def _index_row(results_index: Path, run_name: str) -> dict[str, Any]:
    if not results_index.is_file():
        raise CaptureAbort(f"missing results_index.csv: {results_index}")
    frame = pd.read_csv(results_index)
    if frame.empty or "run_name" not in frame.columns:
        raise CaptureAbort(f"{results_index} has no run_name rows")
    match = frame[frame["run_name"] == run_name]
    if match.empty:
        # One-cell studies still have exactly one row.
        if len(frame) == 1:
            return dict(frame.iloc[0])
        raise CaptureAbort(f"{results_index} has no row for {run_name!r}")
    return dict(match.iloc[0])


def _ledger_cell(ledger_path: Path, run_name: str) -> dict[str, Any]:
    if not ledger_path.is_file():
        raise CaptureAbort(f"missing study.ledger.json: {ledger_path}")
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    cells = payload.get("cells") or {}
    if run_name in cells:
        return dict(cells[run_name])
    if len(cells) == 1:
        return dict(next(iter(cells.values())))
    raise CaptureAbort(f"{ledger_path} has no cell {run_name!r}")


def _nullable_index_value(row: Mapping[str, Any], key: str) -> Any:
    if key not in row:
        return None
    value = row[key]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def capture_study_cell(
    spec: CellSpec,
    *,
    csv_path: Path,
    output_root: Path,
    run_label: str,
    full_spec_path: Path | None = None,
) -> Path:
    """Execute one cell via ``run_study`` (workers=1) and write the capture."""
    resolve_hook("thesistester.study.execute", "run_study")
    resolve_hook("thesistester.research_bundle", "canonical_bundle_hash")
    run_study = resolve_hook("thesistester.study.execute", "run_study").value
    canonical_bundle_hash = resolve_hook(
        "thesistester.research_bundle", "canonical_bundle_hash"
    ).value

    work = Path(tempfile.mkdtemp(prefix=f"mw0_{spec.cell_id}_"))
    try:
        return _capture_study_cell_in_work(
            spec,
            csv_path=csv_path,
            output_root=output_root,
            run_label=run_label,
            full_spec_path=full_spec_path,
            work=work,
            run_study=run_study,
            canonical_bundle_hash=canonical_bundle_hash,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _capture_study_cell_in_work(
    spec: CellSpec,
    *,
    csv_path: Path,
    output_root: Path,
    run_label: str,
    full_spec_path: Path | None,
    work: Path,
    run_study: Any,
    canonical_bundle_hash: Any,
) -> Path:
    study_out = work / "study"
    study_out.mkdir(parents=True, exist_ok=True)

    if spec.cell_id == FULL_CELL.cell_id:
        source = Path(full_spec_path) if full_spec_path is not None else locate_full_spec()
        yaml_path = rewrite_full_spec_dataset(source, work / "study.yaml", csv_path)
    else:
        mapping = build_study_mapping(
            spec,
            csv_path=csv_path,
            study_name=f"mw0_{spec.cell_id}",
            output_dir=study_out,
        )
        yaml_path = write_study_yaml(work / "study.yaml", mapping)

    with isolate_store(work), replica_expectancies_hook() as sink:
        result = run_study(
            yaml_path,
            output_dir=study_out,
            workers=1,
            confirm=False,
            force=True,
        )

    run_names = list(result.get("run_names") or [])
    if len(run_names) != 1:
        raise CaptureAbort(
            f"{spec.cell_id} expanded to {len(run_names)} cells {run_names!r}; expected 1"
        )
    run_name = str(run_names[0])
    ledger_cell = _ledger_cell(study_out / "study.ledger.json", run_name)
    status = str(ledger_cell.get("status") or "")
    if status != "ok":
        raise CaptureAbort(
            f"{spec.cell_id} finished status={status!r} error={ledger_cell.get('error')!r}. "
            "Stop and report; do not switch same_bar_opposite_direction or regenerate."
        )
    bundle_rel = ledger_cell.get("bundle_path")
    if not isinstance(bundle_rel, str) or not bundle_rel:
        raise CaptureAbort(f"{spec.cell_id} ok cell has no bundle_path")
    bundle_path = study_out / bundle_rel
    if not bundle_path.is_file():
        raise CaptureAbort(f"{spec.cell_id} bundle missing on disk: {bundle_path}")

    try:
        trades = canonicalize_frame_datetimes(read_bundle_trades(bundle_path))
    except CanonicalizeError as exc:
        raise CaptureAbort(
            f"{spec.cell_id} datetime canonicalize failed: {exc}. "
            "Stop and report; do not loosen unit or tz compare."
        ) from exc
    if spec.expect_zero_trades and len(trades) != 0:
        raise CaptureAbort(
            f"{spec.cell_id} was specified as the 0-trade cell but produced "
            f"{len(trades)} trades. The slice is wrong; do not record it."
        )
    if spec.same_bar_opposite_direction == "raise" and status != "ok":
        raise CaptureAbort(
            f"{spec.cell_id} uses same_bar_opposite_direction=raise and did not finish ok"
        )

    summary_bundle = read_bundle_trade_summary(bundle_path)
    index_row = _index_row(study_out / "results_index.csv", run_name)
    summary: dict[str, Any] = {}
    for key in SUMMARY_METRIC_KEYS:
        if key in summary_bundle:
            summary[key] = summary_bundle.get(key)
        else:
            summary[key] = _nullable_index_value(index_row, key)
    if summary.get("trade_count") is None:
        raise CaptureAbort(
            f"{spec.cell_id} missing trade_count in bundle and results_index. "
            "Stop and report; do not record a partial capture."
        )
    da5 = {key: _nullable_index_value(index_row, key) for key in DA5_KEYS}
    bundle_bytes = bundle_path.read_bytes()
    product_digest = canonical_bundle_hash(bundle_bytes)
    try:
        digest = portable_canonical_bundle_hash(bundle_bytes)
    except CanonicalizeError as exc:
        raise CaptureAbort(
            f"{spec.cell_id} portable bundle hash failed: {exc}. "
            "Stop and report; do not skip the hash gate."
        ) from exc
    replicas = sink.last
    if spec.expect_zero_trades and replicas:
        raise CaptureAbort(
            f"{spec.cell_id} is 0-trade but vs_random_benchmark produced "
            f"{len(replicas)} replica floats"
        )
    if (not spec.expect_zero_trades) and spec.n_replicas > 0 and len(trades) > 0:
        if len(replicas) != spec.n_replicas:
            raise CaptureAbort(
                f"{spec.cell_id} expected {spec.n_replicas} replica_expectancies, "
                f"got {len(replicas)}. The hook missed vs_random_benchmark "
                "(59a4652 bundles do not persist this list)."
            )

    if spec.cell_id == FULL_CELL.cell_id:
        count = int(summary.get("trade_count") or len(trades))
        expectancy = summary.get("expectancy_r")
        if count != FULL_CELL_KNOWN_TRADE_COUNT:
            raise CaptureAbort(
                f"full reference cell produced {count} trades; known result is "
                f"{FULL_CELL_KNOWN_TRADE_COUNT}. Stop and report."
            )
        if expectancy is not None:
            rounded = round(float(expectancy), 4)
            if rounded != FULL_CELL_KNOWN_EXPECTANCY:
                raise CaptureAbort(
                    f"full reference cell E={float(expectancy)!r} (rounded {rounded}); "
                    f"known result is E={FULL_CELL_KNOWN_EXPECTANCY}. Stop and report."
                )

    dest = cell_dir(output_root, spec.cell_id)
    identity = package_identity()
    write_capture(
        dest,
        cell_id=spec.cell_id,
        trades=trades,
        replica_expectancies=replicas,
        summary=summary,
        da5=da5,
        ledger=ledger_cell,
        canonical_hash=str(digest),
        meta={
            "run_label": run_label,
            "run_name": run_name,
            "csv_name": Path(csv_path).name,
            "n_replicas": spec.n_replicas,
            "same_bar_opposite_direction": spec.same_bar_opposite_direction,
            "expect_zero_trades": spec.expect_zero_trades,
            "replica_hook_calls": len(sink.calls),
            "thesistester_version": identity.get("thesistester_version"),
            "thesistester_file": identity.get("thesistester_file"),
            "thesistester_root": identity.get("thesistester_root"),
            "pythonpath_thesistester_root": identity.get("pythonpath_thesistester_root"),
            "farm_production_commit": identity.get("farm_production_commit"),
            "canonical_hash_kind": "portable_datetime_ns",
            "product_canonical_bundle_hash": str(product_digest),
        },
    )
    return dest
