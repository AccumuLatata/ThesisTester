"""AMP Daily Statement PDF → ``AmpStatement`` (TJ2).

Two-stage: ``extract_amp_pdf_text`` (pdfplumber, this module only) then
``parse_amp_statement_text`` (pure). Does not pair fills, join bars, or call
``simulate_trades``.
"""

from __future__ import annotations

from datetime import date
import math
from pathlib import Path
import re

from thesistester.journal.schema import (
    AMP_KNOWN_FEE_NAMES,
    AMP_STANDARD_FEE_NAMES,
    AmpFill,
    AmpStatement,
    JournalIngestError,
)

_CONF_HEADER = "T R A D E S C O N F I R M A T I O N S"
_PS_HEADER = "P U R C H A S E & S A L E"
_SUMMARY_MARK = "Account Summary"
_DAILY_MARK = "DAILY STATEMENT"
# Collapsed (whitespace-stripped) headers. AMP letter-spaces section titles;
# Open Positions / Journal / delivery blocks sit between P&S and Account
# Summary and reuse the confirmation-row layout.
_HEADER_CONF = "TRADESCONFIRMATIONS"
_HEADER_PS = "PURCHASE&SALE"
_HEADER_SUMMARY = "ACCOUNTSUMMARY"
_HEADER_IGNORE = frozenset(
    {
        "OPENPOSITIONS",
        "JOURNALENTRIES",
        "DELIVERYANDCASHSETTLEMENT",
        "EXPIRATIONS",
        "EXERCISES",
    }
)

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_DATE_RE = re.compile(r"\b(\d{2})-([A-Z]{3})-(\d{2})\b")
_FILL_RE = re.compile(
    r"^(?P<date>\d{2}-[A-Z]{3}-\d{2})\s+"
    r"(?P<number>\d+)\s+"
    r"(?P<market>CME)"
    r"(?P<gap>.*?)"
    r"(?P<root>MNQ|MES)\s+Future\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<yy>\d{2})\s+"
    r"(?P<price>[\d,]+(?:\.\d+)?)\s+USD"
)
_AVG_RE = re.compile(r"AVERAGE\s+(LONG|SHORT)\s+([\d.]+)")
_PS_USD_RE = re.compile(r"P&S\s+USD\s+([\d,.]+)\s+(CR|DR)")
_MONEY_RE = re.compile(r"([\d,]+\.\d{2})\s+(CR|DR)")
_FEE_BLOCK_STOP = "OPEN TRADE EQUITY"
_FEE_BLOCK_START = "TOTAL COMMISSION & FEES"
_QTY_RE = re.compile(r"\d+")
# Date + FCM number: a trade row that must parse as MNQ/MES CME Future.
_TRADE_ROW_PREFIX = re.compile(r"^\d{2}-[A-Z]{3}-\d{2}\s+\d+\s+")
_CONF_TOTAL_RE = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\b")
_MONEY_TOLERANCE = 0.011  # 1 cent, plus float dust

_FEE_CANON = {
    "EXCHANGE": "Exchange",
    "NFA": "NFA",
    "CLEARING CLIENT": "Clearing Client",
    "RITHMIC TRF": "Rithmic TRF",
    "COMMISSION": "Commission",
    "LIQUIDATION FEE": "Liquidation Fee",
}

_SECTION_CONF = "conf"
_SECTION_PS = "ps"
_SECTION_SUMMARY = "summary"
_SECTION_NONE = "none"


def extract_amp_pdf_text(path: str | Path) -> str:
    """Extract layout-preserving text from an AMP Daily Statement PDF.

    ``pdfplumber`` is imported here only (plan §5 TJ2).
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - CI pins the dep
        raise JournalIngestError("pdfplumber is required to read AMP statement PDFs") from exc

    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise JournalIngestError(f"AMP statement PDF not found: {pdf_path}")
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            raise JournalIngestError("AMP statement PDF has no pages")
        for page in pdf.pages:
            pages.append(page.extract_text(layout=True) or "")
    return "\n".join(pages)


def parse_amp_statement_text(text: str) -> AmpStatement:
    """Parse layout text from ``extract_amp_pdf_text`` into ``AmpStatement``."""
    if not text or not text.strip():
        raise JournalIngestError("empty AMP statement text")
    if _DAILY_MARK not in text:
        raise JournalIngestError("not an AMP Daily Statement (missing DAILY STATEMENT)")
    if _CONF_HEADER not in text:
        raise JournalIngestError("AMP statement missing Trades Confirmations section")

    session_date = _header_session_date(text)
    conf_lines, ps_lines, summary_lines, conf_totals = _split_sections(text)

    fills = tuple(_parse_fill_line(line, session_date) for line in conf_lines)
    if not fills:
        raise JournalIngestError("AMP confirmations contain no fills")
    _assert_one_session(fills, session_date)
    _assert_confirmation_totals(fills, conf_totals)

    # P&S legs may predate the statement (prior-day open / liquidation).
    ps_pairs = tuple(
        _parse_fill_line(line, session_date, require_session_date=False) for line in ps_lines
    )
    ps_usd = _parse_ps_usd(text)
    avg_source = text.split(_PS_HEADER, 1)[0] if _PS_HEADER in text else text
    printed_long, printed_short = _parse_printed_averages(avg_source)
    _assert_averages(fills, printed_long, printed_short)
    average_long, average_short = printed_long[0], printed_short[0]

    fee_lines = _parse_fee_lines(summary_lines or text)
    n_sides = sum(fill.qty for fill in fills)
    if n_sides <= 0:
        raise JournalIngestError("AMP confirmation qty sums to zero")
    per_side = tuple((name, fee_lines[name] / n_sides) for name in AMP_STANDARD_FEE_NAMES)
    extra = fee_lines.get("Liquidation Fee", 0.0)
    return AmpStatement(
        session_date=session_date,
        fills=fills,
        ps_pairs=ps_pairs,
        ps_usd=ps_usd,
        average_long=average_long,
        average_short=average_short,
        fee_lines=tuple(fee_lines.items()),
        per_side_schedule=per_side,
        day_fees_extra=extra,
        currency="USD",
    )


def load_amp_statement(path: str | Path) -> AmpStatement:
    """Extract then parse one AMP Daily Statement PDF."""
    return parse_amp_statement_text(extract_amp_pdf_text(path))


def _collapse_header(line: str) -> str:
    return re.sub(r"[^A-Z0-9&]+", "", line.upper())


def _split_sections(
    text: str,
) -> tuple[list[str], list[str], list[str], list[tuple[int, int]]]:
    section = _SECTION_NONE
    conf: list[str] = []
    ps: list[str] = []
    summary: list[str] = []
    conf_totals: list[tuple[int, int]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("../.."):
            continue
        collapsed = _collapse_header(stripped)
        if _HEADER_CONF in collapsed or _CONF_HEADER in stripped:
            section = _SECTION_CONF
            continue
        if _HEADER_PS in collapsed or _PS_HEADER in stripped:
            section = _SECTION_PS
            continue
        if _HEADER_SUMMARY in collapsed or _SUMMARY_MARK in stripped:
            section = _SECTION_SUMMARY
            continue
        if any(name in collapsed for name in _HEADER_IGNORE):
            # Open Positions / journal / delivery rows can match ``_FILL_RE``.
            section = _SECTION_NONE
            continue
        if section == _SECTION_CONF:
            if _FILL_RE.match(stripped):
                conf.append(stripped)
            elif _TRADE_ROW_PREFIX.match(stripped):
                raise JournalIngestError(f"unparseable AMP confirmation row: {stripped!r}")
            else:
                total_match = _CONF_TOTAL_RE.match(stripped)
                if total_match:
                    conf_totals.append((int(total_match.group(1)), int(total_match.group(2))))
        elif section == _SECTION_PS:
            if _FILL_RE.match(stripped):
                ps.append(stripped)
            elif _TRADE_ROW_PREFIX.match(stripped):
                raise JournalIngestError(f"unparseable AMP P&S row: {stripped!r}")
        elif section == _SECTION_SUMMARY:
            summary.append(line)
    return conf, ps, summary, conf_totals


def _parse_fill_line(
    line: str,
    session_date: date,
    *,
    require_session_date: bool = True,
) -> AmpFill:
    match = _FILL_RE.match(line.strip())
    if match is None:
        raise JournalIngestError(f"unparseable AMP fill line: {line!r}")
    fill_date = _parse_amp_date(match.group("date"))
    if require_session_date and fill_date != session_date:
        raise JournalIngestError(
            f"fill date {fill_date} disagrees with statement date {session_date}"
        )
    month = match.group("month")
    if month not in _MONTHS:
        raise JournalIngestError(f"unknown AMP contract month {month!r}")
    qty, side = _side_from_gap(match.group("gap"))
    price = float(match.group("price").replace(",", ""))
    if not math.isfinite(price) or price <= 0:
        raise JournalIngestError(f"AMP fill price must be finite and > 0 (got {price})")
    return AmpFill(
        fcm_number=match.group("number"),
        session_date=fill_date,
        market=match.group("market"),
        instrument=match.group("root"),
        contract_month=month,
        contract_year=2000 + int(match.group("yy")),
        side=side,
        qty=qty,
        price=price,
    )


def _side_from_gap(gap: str) -> tuple[int, str]:
    """BUY vs SELL from the qty token's position between CME and the root."""
    qty_match = _QTY_RE.search(gap)
    if qty_match is None:
        raise JournalIngestError(f"AMP fill missing BUY/SELL qty in gap {gap!r}")
    extras = _QTY_RE.findall(gap)
    if len(extras) != 1:
        raise JournalIngestError(f"AMP fill gap is not a single BUY xor SELL qty: {gap!r}")
    qty = int(qty_match.group(0))
    if qty <= 0:
        raise JournalIngestError(f"AMP fill qty must be a positive int (got {qty})")
    left = qty_match.start()
    right = len(gap) - qty_match.end()
    if left == right:
        raise JournalIngestError(f"AMP fill BUY/SELL columns are ambiguous: {gap!r}")
    side = "buy" if left < right else "sell"
    return qty, side


def _header_session_date(text: str) -> date:
    after = text.split(_DAILY_MARK, 1)[1]
    header = after.split(_CONF_HEADER, 1)[0] if _CONF_HEADER in after else after
    for line in header.splitlines():
        match = _DATE_RE.search(line)
        if match:
            return _parse_amp_date(match.group(0))
    raise JournalIngestError("AMP statement header has no session date")


def _parse_amp_date(raw: str) -> date:
    match = _DATE_RE.fullmatch(raw.strip())
    if match is None:
        raise JournalIngestError(f"unparseable AMP date {raw!r}")
    day = int(match.group(1))
    month = _MONTHS.get(match.group(2))
    if month is None:
        raise JournalIngestError(f"unknown AMP month in date {raw!r}")
    year = 2000 + int(match.group(3))
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise JournalIngestError(f"invalid AMP date {raw!r}") from exc


def _assert_confirmation_totals(
    fills: tuple[AmpFill, ...],
    conf_totals: list[tuple[int, int]],
) -> None:
    if not conf_totals:
        raise JournalIngestError("AMP confirmations missing TOTAL buy/sell counts")
    buy_qty = sum(fill.qty for fill in fills if fill.side == "buy")
    sell_qty = sum(fill.qty for fill in fills if fill.side == "sell")
    printed_buy, printed_sell = conf_totals[-1]
    if (printed_buy, printed_sell) != (buy_qty, sell_qty):
        raise JournalIngestError(
            f"confirmation TOTAL buy/sell {printed_buy}/{printed_sell} != {buy_qty}/{sell_qty}"
        )


def _assert_one_session(fills: tuple[AmpFill, ...], session_date: date) -> None:
    bad = {fill.session_date for fill in fills if fill.session_date != session_date}
    if bad:
        raise JournalIngestError(f"confirmation dates {sorted(bad)} != {session_date}")


def _parse_printed_averages(text: str) -> tuple[tuple[float, int], tuple[float, int]]:
    found: dict[str, tuple[float, int]] = {}
    for match in _AVG_RE.finditer(text):
        raw = match.group(2)
        places = len(raw.split(".", 1)[1]) if "." in raw else 0
        value = (float(raw), places)
        key = match.group(1)
        prior = found.get(key)
        if prior is not None and abs(prior[0] - value[0]) > 10 ** (-max(prior[1], places, 2)):
            raise JournalIngestError(f"conflicting AVERAGE {key} values: {prior[0]} vs {value[0]}")
        found[key] = value
    if "LONG" not in found or "SHORT" not in found:
        raise JournalIngestError("AMP statement missing AVERAGE LONG / AVERAGE SHORT")
    return found["LONG"], found["SHORT"]


def _assert_averages(
    fills: tuple[AmpFill, ...],
    printed_long: tuple[float, int],
    printed_short: tuple[float, int],
) -> None:
    computed_long = _qty_weighted_average(fills, "buy")
    computed_short = _qty_weighted_average(fills, "sell")
    long_val, long_places = printed_long
    short_val, short_places = printed_short
    if not _avg_matches(computed_long, long_val, long_places):
        raise JournalIngestError(
            f"AVERAGE LONG mismatch: computed {computed_long} vs printed {long_val}"
        )
    if not _avg_matches(computed_short, short_val, short_places):
        raise JournalIngestError(
            f"AVERAGE SHORT mismatch: computed {computed_short} vs printed {short_val}"
        )


def _qty_weighted_average(fills: tuple[AmpFill, ...], side: str) -> float:
    legs = [fill for fill in fills if fill.side == side]
    if not legs:
        raise JournalIngestError(f"no {side} confirmation fills to average")
    total_qty = sum(fill.qty for fill in legs)
    return sum(fill.price * fill.qty for fill in legs) / total_qty


def _avg_matches(computed: float, printed: float, places: int) -> bool:
    # Printed AMP averages truncate/round at a fixed dp (observed 5). Allow 1 ULP.
    places = max(places, 2)
    return abs(computed - printed) <= 10 ** (-places)


def _parse_ps_usd(text: str) -> float:
    signed: set[float] = set()
    for match in _PS_USD_RE.finditer(text):
        amount = float(match.group(1).replace(",", ""))
        sign = 1.0 if match.group(2) == "CR" else -1.0
        signed.add(sign * amount)
    if not signed:
        raise JournalIngestError("AMP statement missing P&S USD total")
    if len(signed) > 1:
        raise JournalIngestError(f"conflicting P&S USD totals: {sorted(signed)}")
    return next(iter(signed))


def _parse_fee_lines(lines: list[str] | str) -> dict[str, float]:
    blob = lines if isinstance(lines, list) else lines.splitlines()
    parsed: dict[str, float] = {}
    printed_totals: list[float] = []
    collecting = False
    for line in blob:
        if _FEE_BLOCK_START in line:
            collecting = True
            printed_totals.append(_last_money(line))
            continue
        if collecting and _FEE_BLOCK_STOP in line:
            collecting = False
            continue
        if not collecting:
            continue
        name_raw, tail = _split_fee_line(line)
        raw_key = re.sub(r"\s+", " ", name_raw.strip().upper())
        canon = _FEE_CANON.get(raw_key)
        if canon is None or canon not in AMP_KNOWN_FEE_NAMES:
            raise JournalIngestError(f"unknown AMP fee name {name_raw!r}")
        amount = _last_money(tail)
        if canon in parsed and abs(parsed[canon] - amount) > 0.001:
            raise JournalIngestError(f"AMP fee {canon} listed twice with different amounts")
        parsed[canon] = amount
    missing = [name for name in AMP_STANDARD_FEE_NAMES if name not in parsed]
    if missing:
        raise JournalIngestError("AMP statement missing standard fee lines: " + ", ".join(missing))
    if not printed_totals:
        raise JournalIngestError("AMP statement missing TOTAL COMMISSION & FEES")
    if any(abs(total - printed_totals[0]) > _MONEY_TOLERANCE for total in printed_totals):
        raise JournalIngestError(f"conflicting TOTAL COMMISSION & FEES: {printed_totals}")
    summed = sum(parsed.values())
    if abs(summed - printed_totals[0]) > _MONEY_TOLERANCE:
        raise JournalIngestError(
            f"fee lines sum {summed:.2f} != printed TOTAL COMMISSION & FEES {printed_totals[0]:.2f}"
        )
    return parsed


def _split_fee_line(line: str) -> tuple[str, str]:
    matches = list(_MONEY_RE.finditer(line))
    if not matches:
        raise JournalIngestError(f"AMP fee line has no amount: {line!r}")
    name = line[: matches[0].start()].strip()
    if not name:
        raise JournalIngestError(f"AMP fee line missing name: {line!r}")
    return name, line[matches[0].start() :]


def _last_money(tail: str) -> float:
    matches = list(_MONEY_RE.finditer(tail))
    if not matches:
        raise JournalIngestError(f"AMP fee line has no amount: {tail!r}")
    amount = float(matches[-1].group(1).replace(",", ""))
    sign = 1.0 if matches[-1].group(2) == "DR" else -1.0
    return sign * amount
