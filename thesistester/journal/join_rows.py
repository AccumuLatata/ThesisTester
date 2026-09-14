"""TJ5 row-to-frame helpers (C-25 / QI-08-04).

Object-None join cells stay object dtype. MAE/MFE walk math stays on
``join.py`` (``_join_trade``).
"""

from __future__ import annotations

import pandas as pd

from thesistester.journal.schema import JOIN_OUTPUT_COLUMNS, JOURNAL_TRADE_COLUMNS


def _as_object_cell(value: object) -> object:
    """Coerce pandas/numpy NA to Python ``None`` for object-dtype cells.

    TJ5 keeps nullable join/cost cells as object-None, not float64 NaN.
    ``DataFrame.to_dict(orient="records")`` plus pandas 2.3 ``concat`` of
    mixed None/float columns can feed ``nan`` into the row dicts. Rebuild
    must emit ``None`` (same as TJ4 ``reconcile``), never leave NA-in-object.
    Do not call ``pd.isna`` on tuples/lists (``tags``, ``join_flags``).
    """
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _rows_to_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    extra = [column for column in JOIN_OUTPUT_COLUMNS if column not in JOURNAL_TRADE_COLUMNS]
    present = list(rows[0].keys())
    ordered = [column for column in JOURNAL_TRADE_COLUMNS if column in present] + extra
    for leftover in present:
        if leftover not in ordered:
            ordered.append(leftover)
    frame = pd.DataFrame(index=range(len(rows)))
    for column in ordered:
        values = [row.get(column) for row in rows]
        if column in {"entry_timestamp", "exit_timestamp"}:
            frame[column] = pd.Series(
                [value if value is not None and not pd.isna(value) else pd.NaT for value in values],
                dtype="datetime64[ns, UTC]",
            )
        else:
            frame[column] = pd.Series(
                [_as_object_cell(value) for value in values],
                dtype="object",
            )
    return frame.loc[:, ordered]
