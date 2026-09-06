"""Named-cell match (TJ8). One hash-verified bundle or RunSpec, never a corpus.

Does not call ``simulate_trades``. Does not import or mutate
``STUDY_INDEX_KEYS`` / ``R18_INDEX_METRIC_KEYS``. Does not re-rank
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
from thesistester.journal.schema import (
    DEFAULT_JOURNAL_RISK_TICKS,
    DEFAULT_MATCH_TICKS,
    DEFAULT_MATCH_WINDOW_SECONDS,
    JOURNAL_ETH_START,
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    MATCH_DISCRETIONARY_ONLY,
    MATCH_EXECUTED_CELL,
    MATCH_HONESTY,
    MATCH_NEAR_LEVEL,
    MATCH_OUTPUT_COLUMNS,
    MATCH_PRODUCT_MISMATCH,
    MATCH_RISK_TOLERANCE_RATIO,
    MATCH_SIDE_JOURNAL,
    MATCH_SIDE_SYSTEMATIC,
    MATCH_SYSTEMATIC_UNFILLED,
    MISMATCH_HOLD,
    MISMATCH_RISK,
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
    window = _as_positive_number(match_window_seconds, "match_window_seconds")
    ticks = _as_positive_number(match_ticks, "match_ticks")
    sl = _as_positive_number(stop_loss_ticks, "stop_loss_ticks")
    clock = _as_positive_number(bar_seconds, "bar_seconds")
    tick = _as_positive_tick(tick_size)
    if not str(cell_id).strip():
        raise JournalIngestError("cell_id is required")
    if not str(instrument).strip():
        raise JournalIngestError("instrument is required")
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
    bundle_path = Path(str(bundle if bundle is not None else spec.get("bundle_path") or ""))
    if not str(bundle_path):
        raise JournalIngestError("journal match requires a named bundle zip or RunSpec path")
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
    instrument = str(spec.get("instrument") or meta.get("instrument") or "").strip()
    if not instrument:
        raise JournalIngestError("named cell is missing instrument")
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


def _classify(
    journal: pd.DataFrame,
    systematic: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    cell_id: str,
    instrument: str,
    stop_loss_ticks: float,
    bar_seconds: float,
    window: float,
    match_ticks: float,
    tick: float,
) -> list[dict[str, object]]:
    journal_rows = journal.to_dict(orient="records")
    sys_rows = systematic.to_dict(orient="records")
    candidates: list[tuple[float, float, int, int]] = []
    for j_idx, journal_row in enumerate(journal_rows):
        if str(journal_row["instrument"]) != instrument:
            continue
        for s_idx, sys_row in enumerate(sys_rows):
            if str(sys_row["direction"]) != str(journal_row["direction"]):
                continue
            delta_s = abs(
                (journal_row["entry_timestamp"] - sys_row["entry_timestamp"]).total_seconds()
            )
            if delta_s > window:
                continue
            delta_t = _price_distance_ticks(float(journal_row["entry_price"]), sys_row, tick)
            if delta_t > match_ticks:
                continue
            candidates.append((delta_s, delta_t, j_idx, s_idx))
    candidates.sort()
    used_j: set[int] = set()
    used_s: set[int] = set()
    pairs: list[tuple[int, int, float, float]] = []
    for delta_s, delta_t, j_idx, s_idx in candidates:
        if j_idx in used_j or s_idx in used_s:
            continue
        used_j.add(j_idx)
        used_s.add(s_idx)
        pairs.append((j_idx, s_idx, delta_s, delta_t))

    executed_signal_ids: set[str] = set()
    executed_sys_ids: set[str] = set()
    rows: list[dict[str, object]] = []
    for j_idx, s_idx, delta_s, delta_t in pairs:
        journal_row = journal_rows[j_idx]
        sys_row = sys_rows[s_idx]
        failing = _product_failing(
            journal_row,
            sys_row,
            stop_loss_ticks=stop_loss_ticks,
            bar_seconds=bar_seconds,
        )
        sid = _as_optional_str(sys_row.get("signal_id"))
        if sid is not None:
            executed_signal_ids.add(sid)
        executed_sys_ids.add(str(sys_row["trade_id"]))
        if failing:
            klass = MATCH_PRODUCT_MISMATCH
            dimension = ",".join(failing)
        else:
            klass = MATCH_EXECUTED_CELL
            dimension = None
        rows.append(
            _journal_match_row(
                journal_row,
                cell_id=cell_id,
                match_class=klass,
                dimension=dimension,
                counterpart_id=str(sys_row["trade_id"]),
                delta_s=delta_s,
                delta_t=delta_t,
                sl=stop_loss_ticks,
                bars_held=sys_row.get("bars_held"),
            )
        )

    for j_idx, journal_row in enumerate(journal_rows):
        if j_idx in used_j:
            continue
        if str(journal_row["instrument"]) == instrument and _near_any_level(
            float(journal_row["entry_price"]),
            str(journal_row["direction"]),
            sys_rows,
            signals.to_dict(orient="records") if not signals.empty else [],
            match_ticks=match_ticks,
            tick=tick,
        ):
            klass = MATCH_NEAR_LEVEL
        else:
            klass = MATCH_DISCRETIONARY_ONLY
        rows.append(
            _journal_match_row(
                journal_row,
                cell_id=cell_id,
                match_class=klass,
                dimension=None,
                counterpart_id=None,
                delta_s=None,
                delta_t=None,
                sl=stop_loss_ticks,
                bars_held=None,
            )
        )

    if not signals.empty:
        for raw in signals.to_dict(orient="records"):
            sid = _as_optional_str(raw.get("signal_id"))
            if sid is not None and sid in executed_signal_ids:
                continue
            rows.append(_systematic_unfilled_row(raw, cell_id=cell_id, sl=stop_loss_ticks))
    else:
        for raw in sys_rows:
            if str(raw["trade_id"]) in executed_sys_ids:
                continue
            rows.append(_systematic_unfilled_row(raw, cell_id=cell_id, sl=stop_loss_ticks))
    return rows


def _product_failing(
    journal_row: Mapping[str, object],
    sys_row: Mapping[str, object],
    *,
    stop_loss_ticks: float,
    bar_seconds: float,
) -> list[str]:
    failing: list[str] = []
    hold = _optional_float(journal_row.get("hold_seconds"))
    bars = _optional_float(sys_row.get("bars_held"))
    if hold is None or bars is None or bars <= 0:
        failing.append(MISMATCH_HOLD)
    else:
        lo = max(0.0, (bars - 1.0) * bar_seconds)
        hi = bars * bar_seconds
        if not (lo <= hold <= hi):
            failing.append(MISMATCH_HOLD)
    risk = _optional_float(journal_row.get("journal_risk_ticks"))
    if risk is None:
        risk = float(DEFAULT_JOURNAL_RISK_TICKS)
    sl = _optional_float(sys_row.get("stop_loss_ticks")) or stop_loss_ticks
    lo_r = sl * (1.0 - MATCH_RISK_TOLERANCE_RATIO)
    hi_r = sl * (1.0 + MATCH_RISK_TOLERANCE_RATIO)
    if not (lo_r <= risk <= hi_r):
        failing.append(MISMATCH_RISK)
    return failing


def _price_distance_ticks(price: float, sys_row: Mapping[str, object], tick: float) -> float:
    distances: list[float] = []
    for key in ("theoretical_entry_price", "entry_price", "zone_mid"):
        value = _optional_float(sys_row.get(key))
        if value is not None:
            distances.append(abs(price - value) / tick)
    low = _optional_float(sys_row.get("zone_low"))
    high = _optional_float(sys_row.get("zone_high"))
    if low is not None and high is not None:
        if low <= price <= high:
            distances.append(0.0)
        else:
            distances.append(min(abs(price - low), abs(price - high)) / tick)
    return min(distances) if distances else math.inf


def _near_any_level(
    price: float,
    direction: str,
    systematic: list[dict[str, object]],
    signals: list[dict[str, object]],
    *,
    match_ticks: float,
    tick: float,
) -> bool:
    for raw in systematic + signals:
        if str(raw.get("direction") or "") != direction:
            continue
        if _price_distance_ticks(price, raw, tick) <= match_ticks:
            return True
    return False


def _journal_match_row(
    raw: Mapping[str, object],
    *,
    cell_id: str,
    match_class: str,
    dimension: str | None,
    counterpart_id: str | None,
    delta_s: float | None,
    delta_t: float | None,
    sl: float,
    bars_held: object,
) -> dict[str, object]:
    return {
        "side": MATCH_SIDE_JOURNAL,
        "trade_id": str(raw["trade_id"]),
        "signal_id": None,
        "session_date": raw["session_date"],
        "match_class": match_class,
        "product_mismatch_dimension": dimension,
        "cell_id": cell_id,
        "counterpart_id": counterpart_id,
        "delta_entry_seconds": delta_s,
        "delta_entry_ticks": delta_t,
        "instrument": str(raw["instrument"]),
        "direction": str(raw["direction"]),
        "net_ticks": _optional_float(raw.get("net_ticks")),
        "hold_seconds": _optional_float(raw.get("hold_seconds")),
        "journal_risk_ticks": _optional_float(raw.get("journal_risk_ticks"))
        or float(DEFAULT_JOURNAL_RISK_TICKS),
        "cell_stop_loss_ticks": sl,
        "cell_bars_held": _optional_float(bars_held),
    }


def _systematic_unfilled_row(
    raw: Mapping[str, object], *, cell_id: str, sl: float
) -> dict[str, object]:
    trade_id = raw.get("trade_id") or raw.get("signal_id") or "systematic"
    return {
        "side": MATCH_SIDE_SYSTEMATIC,
        "trade_id": str(trade_id),
        "signal_id": _as_optional_str(raw.get("signal_id")),
        "session_date": raw["session_date"],
        "match_class": MATCH_SYSTEMATIC_UNFILLED,
        "product_mismatch_dimension": None,
        "cell_id": cell_id,
        "counterpart_id": None,
        "delta_entry_seconds": None,
        "delta_entry_ticks": None,
        "instrument": str(raw.get("instrument") or ""),
        "direction": str(raw.get("direction") or ""),
        "net_ticks": None,
        "hold_seconds": None,
        "journal_risk_ticks": None,
        "cell_stop_loss_ticks": sl,
        "cell_bars_held": _optional_float(raw.get("bars_held")),
    }


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
    work["entry_timestamp"] = [_as_utc(value) for value in work["entry_timestamp"]]
    work["entry_price"] = pd.to_numeric(work["entry_price"], errors="coerce")
    if work["entry_price"].isna().any() or not (work["entry_price"] > 0).all():
        raise JournalIngestError("trades frame has non-finite entry_price")
    work["direction"] = work["direction"].map(str)
    bad_dir = sorted({str(item) for item in work["direction"] if item not in {"long", "short"}})
    if bad_dir:
        raise JournalIngestError(f"direction must be long/short (got {bad_dir})")
    work["instrument"] = work["instrument"].map(str)
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
    work["direction"] = work["direction"].map(str)
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
    work = signals.copy()
    stamp_col = "timestamp" if "timestamp" in work.columns else "entry_timestamp"
    work["entry_timestamp"] = [_as_utc(value) for value in work[stamp_col]]
    work["direction"] = work["direction"].map(str) if "direction" in work.columns else "long"
    work["instrument"] = instrument
    if "signal_id" not in work.columns:
        work["signal_id"] = [f"sig:{index}" for index in range(len(work))]
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


def _match_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(MATCH_OUTPUT_COLUMNS))
    frame = pd.DataFrame(rows)
    keep = [column for column in MATCH_OUTPUT_COLUMNS if column in frame.columns]
    out = frame.loc[:, keep]
    for column in (
        "product_mismatch_dimension",
        "counterpart_id",
        "delta_entry_seconds",
        "delta_entry_ticks",
        "net_ticks",
        "hold_seconds",
        "journal_risk_ticks",
        "cell_bars_held",
        "signal_id",
    ):
        if column in out.columns:
            out[column] = pd.Series([row.get(column) for row in rows], dtype="object")
    return out


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
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return date.fromisoformat(str(value)[:10])


def _as_optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    return _as_date(value)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_positive_tick(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise JournalIngestError(f"tick_size must be a positive number (got {value!r})")
    return float(value)


def _as_positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    return float(value)
