"""TJ2 AMP Daily Statement parser — plan §3.2 / §5 TJ2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from thesistester.journal import JournalIngestError
from thesistester.journal.amp_statement import (
    extract_amp_pdf_text,
    load_amp_statement,
    parse_amp_statement_text,
)
from thesistester.journal.schema import AMP_STANDARD_FEE_NAMES

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "journal"
MNQ_JUN = FIXTURES / "amp_mnq_jun_3page.txt"
MNQ_SEP = FIXTURES / "amp_mnq_sep_2page.txt"
MES_SEP = FIXTURES / "amp_mes_sep_2page.txt"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mnq_jun_3page_confirmations_averages_and_ps():
    stmt = parse_amp_statement_text(_text(MNQ_JUN))
    assert stmt.session_date == date(2026, 5, 27)
    assert len(stmt.fills) == 4
    assert [fill.side for fill in stmt.fills] == ["buy", "sell", "buy", "sell"]
    assert {fill.instrument for fill in stmt.fills} == {"MNQ"}
    assert {fill.contract_month for fill in stmt.fills} == {"JUN"}
    assert {fill.contract_year for fill in stmt.fills} == {2026}
    assert stmt.average_long == 30132.875
    assert stmt.average_short == 30133.55
    assert stmt.ps_usd == 27.0
    assert len(stmt.ps_pairs) == 4
    assert [fill.fcm_number for fill in stmt.ps_pairs] != [fill.fcm_number for fill in stmt.fills]
    assert "../.." in _text(MNQ_JUN)


def test_per_side_schedule_from_standard_fees_only():
    stmt = parse_amp_statement_text(_text(MNQ_JUN))
    per_side = stmt.per_side_map()
    assert tuple(name for name, _ in stmt.per_side_schedule) == AMP_STANDARD_FEE_NAMES
    assert per_side["Exchange"] == pytest.approx(0.35)
    assert per_side["NFA"] == pytest.approx(0.02)
    assert per_side["Clearing Client"] == pytest.approx(0.13)
    assert per_side["Rithmic TRF"] == pytest.approx(0.10)
    assert per_side["Commission"] == pytest.approx(0.02)
    assert "Liquidation Fee" not in per_side
    assert stmt.day_fees_extra == 0.0


def test_mnq_sep_2page_keeps_liquidation_fee_extra():
    stmt = parse_amp_statement_text(_text(MNQ_SEP))
    assert stmt.session_date == date(2026, 6, 23)
    assert len(stmt.fills) == 2
    assert stmt.fills[0].contract_month == "SEP"
    assert stmt.fills[0].side == "sell"
    assert stmt.fills[1].side == "buy"
    assert stmt.fee_map()["Liquidation Fee"] == pytest.approx(2.50)
    assert stmt.day_fees_extra == pytest.approx(2.50)
    assert stmt.per_side_map()["Exchange"] == pytest.approx(0.35)
    assert stmt.ps_usd == pytest.approx(20.0)


def test_mes_sep_2page_instrument_and_ps_credit():
    stmt = parse_amp_statement_text(_text(MES_SEP))
    assert stmt.session_date == date(2026, 6, 29)
    assert {fill.instrument for fill in stmt.fills} == {"MES"}
    assert {fill.contract_month for fill in stmt.fills} == {"SEP"}
    assert stmt.average_long == 7458.75
    assert stmt.average_short == 7459.25
    assert stmt.ps_usd == pytest.approx(21.25)
    assert stmt.day_fees_extra == 0.0


def test_average_mismatch_fails_closed():
    text = _text(MNQ_JUN).replace("AVERAGE LONG 30132.87500", "AVERAGE LONG 30100.00000")
    with pytest.raises(JournalIngestError, match="AVERAGE LONG mismatch"):
        parse_amp_statement_text(text)


def test_unknown_fee_name_fails_closed():
    text = _text(MES_SEP).replace(
        "    COMMISSION                   0.04 DR",
        "    COMMISSION                   0.04 DR\n    WIDGET FEE                   1.00 DR",
    )
    with pytest.raises(JournalIngestError, match="unknown AMP fee name"):
        parse_amp_statement_text(text)


def test_qty_gt_1_is_one_confirmation_and_scales_fees_and_average():
    """Qty lives in the BUY xor SELL column; fee sides and averages are qty-weighted."""
    text = """\
                              DAILY STATEMENT
     REDACTED CLIENT                                 24-JUN-26
                           T R A D E S C O N F I R M A T I O N S
 24-JUN-26 19000001 CME 2        MNQ Future SEP 26         22600.00 USD
 24-JUN-26 19000002 CME        2 MNQ Future SEP 26         22610.00 USD
                                             AVERAGE LONG 22600.00000
                                             AVERAGE SHORT 22610.00000
                                P U R C H A S E & S A L E
 24-JUN-26 19000002 CME        2 MNQ Future SEP 26         22610.00 USD
 24-JUN-26 19000001 CME 2        MNQ Future SEP 26         22600.00 USD
 TOTAL                  2     2 EX- 18-SEP-26         P&S         USD     40.00 CR
                      Account Summary as of 06/24/26
   TOTAL COMMISSION & FEES       2.48 DR
    EXCHANGE                     1.40 DR
    NFA                          0.08 DR
    CLEARING CLIENT              0.52 DR
    RITHMIC TRF                  0.40 DR
    COMMISSION                   0.08 DR
   OPEN TRADE EQUITY             0.00 CR
"""
    stmt = parse_amp_statement_text(text)
    assert len(stmt.fills) == 2
    assert [fill.qty for fill in stmt.fills] == [2, 2]
    assert [fill.side for fill in stmt.fills] == ["buy", "sell"]
    assert stmt.ps_usd == 40.0
    assert stmt.per_side_map()["Exchange"] == pytest.approx(0.35)
    assert stmt.day_fees_extra == 0.0


def test_fixtures_are_redacted():
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (MNQ_JUN, MNQ_SEP, MES_SEP))
    for token in ("Florian", "Richling", "Ahornergasse", "212106", "Wien"):
        assert token not in blob


def test_pdfplumber_import_is_confined_to_amp_module():
    journal_root = Path(__file__).resolve().parents[1] / "thesistester" / "journal"
    for path in journal_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if path.name == "amp_statement.py":
            assert "import pdfplumber" in source
            continue
        assert "pdfplumber" not in source
        assert "from thesistester.engine" not in source


def test_extract_amp_pdf_text_then_parse_synthetic_pdf(tmp_path):
    pdf_path = tmp_path / "amp_synthetic.pdf"
    # Wide BUY/SELL gaps so pdfplumber layout reconstructs the columns.
    pdf_lines = [
        "DAILY STATEMENT",
        "REDACTED                                         29-JUN-26",
        "T R A D E S C O N F I R M A T I O N S",
        "29-JUN-26 18100001 CME 1                MES Future SEP 26          7458.75 USD",
        "29-JUN-26 18100002 CME                1 MES Future SEP 26          7459.25 USD",
        "AVERAGE LONG 7458.75000",
        "AVERAGE SHORT 7459.25000",
        "P U R C H A S E & S A L E",
        "29-JUN-26 18100002 CME                1 MES Future SEP 26          7459.25 USD",
        "29-JUN-26 18100001 CME 1                MES Future SEP 26          7458.75 USD",
        "TOTAL 1 1 P&S         USD     21.25 CR",
        "Account Summary as of 06/29/26",
        "TOTAL COMMISSION & FEES       1.24 DR",
        "    EXCHANGE                     0.70 DR",
        "    NFA                          0.04 DR",
        "    CLEARING CLIENT              0.26 DR",
        "    RITHMIC TRF                  0.20 DR",
        "    COMMISSION                   0.04 DR",
        "OPEN TRADE EQUITY             0.00 CR",
    ]
    _write_synthetic_amp_pdf(pdf_path, pdf_lines)
    extracted = extract_amp_pdf_text(pdf_path)
    assert "DAILY STATEMENT" in extracted
    assert "MES Future SEP 26" in extracted
    loaded = load_amp_statement(pdf_path)
    assert loaded.session_date == date(2026, 6, 29)
    assert [fill.side for fill in loaded.fills] == ["buy", "sell"]
    assert loaded.ps_usd == pytest.approx(21.25)
    assert loaded.per_side_map()["Exchange"] == pytest.approx(0.35)


def _write_synthetic_amp_pdf(path: Path, lines: list[str]) -> None:
    """Minimal one-page PDF. Courier + per-glyph x so layout extract keeps gaps."""
    commands = ["BT", "/F1 7 Tf"]
    y = 800
    for line in lines:
        x = 24.0
        for char in line:
            if char == " ":
                x += 6.0
                continue
            safe = {"\\": "\\\\", "(": "\\(", ")": "\\)"}.get(char, char)
            commands.append(f"1 0 0 1 {x:.2f} {y} Tm ({safe}) Tj")
            x += 4.2
        y -= 9
        if y < 40:
            break
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(out)
