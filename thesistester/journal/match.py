"""Named-cell match (TJ8). One hash-verified bundle or RunSpec, never a corpus.

C-25 (QI-08-04) keeps ``load_named_cell`` / hash verify here and moves
``_classify`` row assembly to ``match_classify.py``. Match class tokens
are unchanged. Does not call ``simulate_trades``. Does not import or
mutate ``STUDY_INDEX_KEYS`` / ``R18_INDEX_METRIC_KEYS``. Does not re-rank
``results_index``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import io
import json
import math
import zipfile

import pandas as pd
import yaml

from thesistester.journal.ledger import build_forward_ledger, load_live_declarations
from thesistester.journal.match_classify import (
    _as_optional_str,
    _classify,
    _match_frame,
    _optional_float,
)
from thesistester.journal.schema import (
    DEFAULT_MATCH_TICKS,
    DEFAULT_MATCH_WINDOW_SECONDS,
    JOURNAL_ETH_START,
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_POINT_VALUE,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    MATCH_HONESTY,
    RECON_RECONCILED,
    JournalIngestError,
)
from thesistester.levels.session_date import trading_session_date
from thesistester.research_bundle import canonical_bundle_hash

_CORPUS_NAMES = frozenset(
    {
        "results_index.csv",
        "study.overview.csv",
        "observatory.parquet",
        "corpus.parquet",
    }
)


@dataclass(frozen=True)
class NamedCell:
    """One hash-verified completed cell."""

    run_name: str
    bundle_path: Path
    bundle_hash: str
    instrument: str
    stop_loss_ticks: float
    bar_seconds: float
    expectancy_r: float | None
    expectancy_ticks: float | None
    trades: pd.DataFrame
    signals: pd.DataFrame
    live_since: date | None = None


def match_journal_to_cell(
    trades: pd.DataFrame,
    *,
    systematic_trades: pd.DataFrame,
    cell_id: str,
    instrument: str,
    stop_loss_ticks: float,
    bar_seconds: float = 60.0,
    systematic_signals: pd.DataFrame | None = None,
    match_window_seconds: float = DEFAULT_MATCH_WINDOW_SECONDS,
    match_ticks: float = DEFAULT_MATCH_TICKS,
    allow_unreconciled: bool = False,
    tick_size: float = JOURNAL_TICK_SIZE,
) -> pd.DataFrame:
    """Classify journal trades against one named cell.

    Keyword-only after ``trades``. Default window 60 s, default ``match_ticks``
    8. ``executed_cell`` requires hold/risk compatibility with the cell lock.
    """
    if not isinstance(allow_unreconciled, bool):
        raise JournalIngestError("allow_unreconciled must be a bool")
    window = _as_positive_number(match_window_seconds, "match_window_seconds")
    ticks = _as_positive_number(match_ticks, "match_ticks")
    sl = _as_positive_number(stop_loss_ticks, "stop_loss_ticks")
    clock = _as_positive_number(bar_seconds, "bar_seconds")
    tick = _as_positive_tick(tick_size)
    if not str(cell_id).strip():
        raise JournalIngestError("cell_id is required")
    instrument = _as_instrument(instrument)
    journal = _coerce_journal(trades)
    _assert_reconciled(journal, allow_unreconciled=allow_unreconciled)
    systematic = _coerce_systematic(systematic_trades, instrument=str(instrument), tick=tick)
    signals = (
        _coerce_signals(systematic_signals, instrument=str(instrument), tick=tick)
        if systematic_signals is not None
        else pd.DataFrame()
    )
    rows = _classify(
        journal,
        systematic,
        signals,
        cell_id=str(cell_id),
        instrument=str(instrument),
        stop_loss_ticks=sl,
        bar_seconds=clock,
        window=window,
        match_ticks=ticks,
        tick=tick,
    )
    return _match_frame(rows)


def load_named_cell(
    *,
    bundle: str | Path | None = None,
    runspec: str | Path | None = None,
    expected_hash: str | None = None,
    live_since: date | str | None = None,
) -> NamedCell:
    """Load one hash-verified bundle. Corpus paths fail closed."""
    spec: dict[str, object] = {}
    if runspec is not None:
        spec = _load_runspec(Path(runspec))
    spec_bundle = spec.get("bundle_path")
    bundle_path = Path(str(bundle if bundle is not None else spec_bundle or ""))
    if not str(bundle_path):
        raise JournalIngestError("journal match requires a named bundle zip or RunSpec path")
    if (
        bundle is not None
        and spec_bundle not in (None, "")
        and Path(str(spec_bundle)).expanduser().resolve() != bundle_path.expanduser().resolve()
    ):
        raise JournalIngestError("RunSpec bundle_path does not match the named --bundle")
    _refuse_corpus(bundle_path)
    if not bundle_path.is_file():
        raise JournalIngestError(f"named cell bundle not found: {bundle_path}")
    payload = bundle_path.read_bytes()
    digest = canonical_bundle_hash(payload)
    want = expected_hash if expected_hash is not None else spec.get("bundle_hash")
    if want not in (None, "") and str(want) != digest:
        raise JournalIngestError(
            f"bundle hash mismatch (got {digest[:12]}…, expected {str(want)[:12]}…)"
        )
    trades, signals, summary, meta = _read_bundle_members(bundle_path)
    spec_instrument = str(spec.get("instrument") or "").strip()
    meta_instrument = str(meta.get("instrument") or "").strip()
    if spec_instrument and meta_instrument and spec_instrument != meta_instrument:
        raise JournalIngestError(
            f"RunSpec instrument {spec_instrument!r} does not match bundle {meta_instrument!r}"
        )
    instrument = spec_instrument or meta_instrument
    if not instrument:
        raise JournalIngestError("named cell is missing instrument")
    instrument = _as_instrument(instrument)
    sl = _optional_float(spec.get("stop_loss_ticks"))
    if sl is None:
        sl = _optional_float(summary.get("stop_loss_ticks"))
    if sl is None and not trades.empty and "stop_loss_ticks" in trades.columns:
        sl = _optional_float(trades["stop_loss_ticks"].iloc[0])
    if sl is None:
        raise JournalIngestError("named cell is missing stop_loss_ticks")
    expectancy_r = _optional_float(summary.get("expectancy_r"))
    if expectancy_r is None and not trades.empty and "r_multiple" in trades.columns:
        values = [_optional_float(value) for value in trades["r_multiple"]]
        finite = [value for value in values if value is not None]
        expectancy_r = (sum(finite) / len(finite)) if finite else None
    expectancy_ticks = (expectancy_r * sl) if expectancy_r is not None else None
    since = live_since if live_since is not None else spec.get("live_since")
    run_name = _run_name_from_bundle(bundle_path, spec)
    return NamedCell(
        run_name=run_name,
        bundle_path=bundle_path.resolve(),
        bundle_hash=digest,
        instrument=instrument,
        stop_loss_ticks=float(sl),
        bar_seconds=_bar_seconds(meta.get("base_interval") or spec.get("base_interval") or "1min"),
        expectancy_r=expectancy_r,
        expectancy_ticks=expectancy_ticks,
        trades=trades,
        signals=signals,
        live_since=_as_optional_date(since),
    )


def write_match_artifacts(
    output_dir: str | Path,
    frame: pd.DataFrame,
    *,
    cell: NamedCell,
    ledger: list[dict[str, object]],
    match_window_seconds: float,
    match_ticks: float,
) -> dict[str, Path]:
    """Write ``journal_matches.parquet`` + ``match.json``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / "journal_matches.parquet"
    json_path = out / "match.json"
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "honesty": MATCH_HONESTY,
        "cell": {
            "run_name": cell.run_name,
            "bundle_path": str(cell.bundle_path),
            "bundle_hash": cell.bundle_hash,
            "instrument": cell.instrument,
            "stop_loss_ticks": cell.stop_loss_ticks,
            "bar_seconds": cell.bar_seconds,
            "expectancy_r": cell.expectancy_r,
            "expectancy_ticks": cell.expectancy_ticks,
            "live_since": cell.live_since.isoformat() if cell.live_since else None,
        },
        "match_window_seconds": float(match_window_seconds),
        "match_ticks": float(match_ticks),
        "ledger": ledger,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    frame.to_parquet(parquet_path, index=False)
    return {"journal_matches.parquet": parquet_path, "match.json": json_path}


def match_files(
    *,
    trades: str | Path,
    output_dir: str | Path,
    bundle: str | Path | None = None,
    runspec: str | Path | None = None,
    expected_hash: str | None = None,
    live_since: date | str | None = None,
    live_declarations: str | Path | None = None,
    match_window_seconds: float = DEFAULT_MATCH_WINDOW_SECONDS,
    match_ticks: float = DEFAULT_MATCH_TICKS,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Load a named cell, match, write journal/v1 outputs. Registry is read-only."""
    if bundle is None and runspec is None:
        raise JournalIngestError("journal match requires --bundle or --runspec")
    declarations = load_live_declarations(live_declarations)
    cell = load_named_cell(
        bundle=bundle,
        runspec=runspec,
        expected_hash=expected_hash,
        live_since=live_since,
    )
    declared = declarations.get(cell.run_name)
    if cell.live_since is None and declared is not None:
        cell = NamedCell(
            run_name=cell.run_name,
            bundle_path=cell.bundle_path,
            bundle_hash=cell.bundle_hash,
            instrument=cell.instrument,
            stop_loss_ticks=cell.stop_loss_ticks,
            bar_seconds=cell.bar_seconds,
            expectancy_r=cell.expectancy_r,
            expectancy_ticks=cell.expectancy_ticks,
            trades=cell.trades,
            signals=cell.signals,
            live_since=declared,
        )
    trade_frame = _load_table(trades, name="trades")
    matched = match_journal_to_cell(
        trade_frame,
        systematic_trades=cell.trades,
        cell_id=cell.run_name,
        instrument=cell.instrument,
        stop_loss_ticks=cell.stop_loss_ticks,
        bar_seconds=cell.bar_seconds,
        systematic_signals=cell.signals if not cell.signals.empty else None,
        match_window_seconds=match_window_seconds,
        match_ticks=match_ticks,
        allow_unreconciled=allow_unreconciled,
    )
    ledger = build_forward_ledger(
        matched,
        live_since=cell.live_since,
        cell_expectancy_ticks=cell.expectancy_ticks,
    )
    return write_match_artifacts(
        output_dir,
        matched,
        cell=cell,
        ledger=ledger,
        match_window_seconds=match_window_seconds,
        match_ticks=match_ticks,
    )


def _coerce_journal(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    needed = {
        "trade_id",
        "entry_timestamp",
        "entry_price",
        "direction",
        "instrument",
        "session_date",
    }
    missing = sorted(needed.difference(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["trade_id"] = work["trade_id"].map(str)
    if work["trade_id"].duplicated().any():
        raise JournalIngestError("trades frame has duplicate trade_id")
    work["entry_timestamp"] = [_as_utc(value) for value in work["entry_timestamp"]]
    work["entry_price"] = pd.to_numeric(work["entry_price"], errors="coerce")
    if (
        work["entry_price"].isna().any()
        or not work["entry_price"].map(math.isfinite).all()
        or not (work["entry_price"] > 0).all()
    ):
        raise JournalIngestError("trades frame has non-finite or non-positive entry_price")
    work["direction"] = work["direction"].map(_as_direction)
    work["instrument"] = work["instrument"].map(_as_instrument)
    work["session_date"] = work["session_date"].map(_as_date)
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_optional_str)
    return work


def _coerce_systematic(trades: pd.DataFrame, *, instrument: str, tick: float) -> pd.DataFrame:
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("systematic_trades must be a DataFrame")
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "trade_id",
                "signal_id",
                "direction",
                "entry_timestamp",
                "entry_price",
                "theoretical_entry_price",
                "zone_low",
                "zone_high",
                "zone_mid",
                "stop_loss_ticks",
                "bars_held",
                "session_date",
                "instrument",
            ]
        )
    needed = {"entry_timestamp", "direction"}
    missing = sorted(needed.difference(trades.columns))
    if missing:
        raise JournalIngestError("systematic trades missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["entry_timestamp"] = [_as_utc(value) for value in work["entry_timestamp"]]
    work["direction"] = work["direction"].map(_as_direction)
    price_keys = {"theoretical_entry_price", "entry_price", "zone_mid"}
    has_zone = "zone_low" in work.columns and "zone_high" in work.columns
    if not price_keys.intersection(work.columns) and not has_zone:
        raise JournalIngestError("systematic trades missing price or zone columns")
    if "trade_id" not in work.columns:
        work["trade_id"] = [f"sys:{index}" for index in range(len(work))]
    else:
        work["trade_id"] = work["trade_id"].map(str)
    work["instrument"] = instrument
    if "session_date" in trades.columns:
        work["session_date"] = [_as_date(value) for value in trades["session_date"]]
    else:
        work["session_date"] = [_session_of(stamp, None) for stamp in work["entry_timestamp"]]
    _ = tick
    return work.reset_index(drop=True)


def _coerce_signals(signals: pd.DataFrame, *, instrument: str, tick: float) -> pd.DataFrame:
    if signals is None or not isinstance(signals, pd.DataFrame) or signals.empty:
        return pd.DataFrame()
    if "timestamp" not in signals.columns and "entry_timestamp" not in signals.columns:
        raise JournalIngestError("systematic signals require timestamp")
    if "direction" not in signals.columns:
        raise JournalIngestError("systematic signals require direction")
    work = signals.copy()
    stamp_col = "timestamp" if "timestamp" in work.columns else "entry_timestamp"
    work["entry_timestamp"] = [_as_utc(value) for value in work[stamp_col]]
    work["direction"] = work["direction"].map(_as_direction)
    work["instrument"] = instrument
    if "signal_id" not in work.columns:
        work["signal_id"] = [f"sig:{index}" for index in range(len(work))]
    if "session_date" in signals.columns:
        work["session_date"] = [_as_date(value) for value in signals["session_date"]]
    else:
        work["session_date"] = [_session_of(stamp, None) for stamp in work["entry_timestamp"]]
    _ = tick
    return work.reset_index(drop=True)


def _session_of(stamp: pd.Timestamp, existing: object) -> date:
    if existing is not None and not isinstance(existing, pd.Series):
        try:
            return _as_date(existing)
        except (TypeError, ValueError, JournalIngestError):
            pass
    local = pd.Series([stamp.tz_convert(JOURNAL_EXCHANGE_TZ)])
    return trading_session_date(local, JOURNAL_ETH_START).iloc[0]


def _read_bundle_members(
    path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object], dict[str, object]]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            if "trades.parquet" not in names:
                raise JournalIngestError("named cell bundle is missing trades.parquet")
            trades = pd.read_parquet(io.BytesIO(archive.read("trades.parquet")))
            signals = (
                pd.read_parquet(io.BytesIO(archive.read("signals.parquet")))
                if "signals.parquet" in names
                else pd.DataFrame()
            )
            summary = (
                json.loads(archive.read("trade_summary.json").decode("utf-8"))
                if "trade_summary.json" in names
                else {}
            )
            meta = (
                json.loads(archive.read("dataset_meta.json").decode("utf-8"))
                if "dataset_meta.json" in names
                else {}
            )
    except zipfile.BadZipFile as exc:
        raise JournalIngestError(f"named cell bundle is not a zip: {path}") from exc
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(meta, dict):
        meta = {}
    return trades, signals, dict(summary), dict(meta)


def _load_runspec(path: Path) -> dict[str, object]:
    _refuse_corpus(path)
    if not path.is_file():
        raise JournalIngestError(f"RunSpec path not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    elif suffix == ".json":
        payload = json.loads(text)
    else:
        raise JournalIngestError("RunSpec path must be .yaml, .yml, or .json")
    if isinstance(payload, Mapping) and "runs" in payload:
        runs = payload.get("runs")
        if not isinstance(runs, list) or len(runs) != 1:
            raise JournalIngestError(
                "journal match requires a named RunSpec (exactly one run); "
                "corpus-wide matching is out"
            )
        payload = runs[0]
    if not isinstance(payload, Mapping):
        raise JournalIngestError("RunSpec path must contain a mapping")
    return dict(payload)


def _run_name_from_bundle(path: Path, spec: Mapping[str, object]) -> str:
    named = str(spec.get("run_name") or "").strip()
    if named:
        return named
    stem = path.stem
    if stem.endswith(".research"):
        return stem[: -len(".research")]
    return stem


def _refuse_corpus(path: Path) -> None:
    if path.is_dir():
        raise JournalIngestError("journal match requires a named bundle zip or RunSpec path")
    if path.name.lower() in _CORPUS_NAMES:
        raise JournalIngestError("journal match requires a named cell; corpus-wide matching is out")


def _bar_seconds(interval: object) -> float:
    text = str(interval).strip().lower()
    mapping = {
        "1min": 60.0,
        "1m": 60.0,
        "1 minute": 60.0,
        "15s": 15.0,
        "15sec": 15.0,
        "5min": 300.0,
        "5m": 300.0,
    }
    if text in mapping:
        return mapping[text]
    raise JournalIngestError(f"unsupported cell bar clock {interval!r}")


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal match refuses days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal match refuses days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal match must not write into results/studies/")
    return resolved


def _load_table(path: str | Path, *, name: str) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"{name} file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(source)
    if suffix == ".csv":
        return pd.read_csv(source)
    raise JournalIngestError(f"{name} must be .parquet or .csv")


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise JournalIngestError("timestamp is missing")
    if stamp.tzinfo is None:
        raise JournalIngestError(f"naive timestamp is not allowed ({stamp!r})")
    return stamp.tz_convert("UTC")


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise JournalIngestError("session_date is missing")
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"invalid session_date {value!r}") from exc
    if pd.isna(stamp):
        raise JournalIngestError("session_date is missing")
    return stamp.date()


def _as_optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    return _as_date(value)


def _as_direction(value: object) -> str:
    text = str(value)
    if text not in {"long", "short"}:
        raise JournalIngestError(f"invalid direction {text!r}")
    return text


def _as_instrument(value: object) -> str:
    text = str(value).strip()
    if text not in JOURNAL_POINT_VALUE:
        raise JournalIngestError(f"unknown instrument {text!r}")
    return text


def _as_positive_tick(value: object) -> float:
    return _as_positive_number(value, "tick_size")


def _as_positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    return number
