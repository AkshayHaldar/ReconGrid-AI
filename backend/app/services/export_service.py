"""Styled multi-sheet Excel export of a reconciliation batch."""

import io
from collections.abc import Sequence
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.core.config import settings
from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CURRENCY_FORMAT = '"₹" #,##0.00'
HEADER_FILL = PatternFill("solid", start_color="1E293B", end_color="1E293B")
HEADER_FONT = Font(bold=True, color="FFFFFF")

LEDGER_HEADERS = [
    "Date",
    "Bank UTR",
    "Settlement ID",
    "Bank Amount",
    "Gross",
    "Fee",
    "Tax",
    "Net",
    "Match Tier",
    "Diagnostic",
    "Human Action",
]
EXCEPTION_HEADERS = [
    "Date",
    "Bank UTR",
    "Settlement ID",
    "Bank Amount",
    "Razorpay Net",
    "Delta",
    "Status",
    "Diagnostic Type",
    "Diagnostic Note",
]
# 1-based columns that hold currency values
LEDGER_MONEY_COLUMNS = (4, 5, 6, 7, 8)
EXCEPTION_MONEY_COLUMNS = (4, 5, 6)


def _text(ws: Worksheet, row: int, col: int, value: str | None) -> Cell:
    """Stores text literally: never a formula, never scientific notation."""
    cell = ws.cell(row=row, column=col)
    cell.value = value or ""
    cell.data_type = "s"
    cell.number_format = "@"
    return cell


def _money(ws: Worksheet, row: int, col: int, value: Decimal | None) -> Cell:
    cell = ws.cell(row=row, column=col, value=float(value) if value is not None else None)
    cell.number_format = CURRENCY_FORMAT
    return cell


def _write_header(ws: Worksheet, headers: Sequence[str]) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def _autofit(ws: Worksheet) -> None:
    for column in ws.columns:
        longest = max((len(str(c.value)) for c in column if c.value is not None and c.data_type != "f"), default=8)
        ws.column_dimensions[get_column_letter(column[0].column)].width = min(max(longest + 2, 10), 70)


def _add_sum_row(ws: Worksheet, money_columns: Sequence[int], last_data_row: int) -> None:
    total_row = last_data_row + 2
    label = ws.cell(row=total_row, column=1, value="Total")
    label.font = Font(bold=True)
    for col in money_columns:
        letter = get_column_letter(col)
        cell = ws.cell(row=total_row, column=col, value=f"=SUM({letter}2:{letter}{max(last_data_row, 2)})")
        cell.number_format = CURRENCY_FORMAT
        cell.font = Font(bold=True)


def _date(log: ReconciliationLog) -> str:
    bank = log.bank_transaction
    return bank.date.strftime("%Y-%m-%d") if bank and bank.date else ""


def build_reconciliation_workbook(batch_id: str, logs: Sequence[ReconciliationLog]) -> bytes:
    """Returns .xlsx bytes with Executive Summary, Reconciled Ledger and Exceptions tabs."""
    matched = [log for log in logs if log.match_status == "MATCHED"]
    problems = [log for log in logs if log.match_status in ("EXCEPTION", "CONFLICT")]

    wb = Workbook()
    summary = wb.active
    summary.title = "Executive Summary"
    ledger = wb.create_sheet("Reconciled Ledger")
    exceptions = wb.create_sheet("Exceptions & Discrepancies")

    # Reconciled ledger
    _write_header(ledger, LEDGER_HEADERS)
    for row, log in enumerate(matched, start=2):
        bank, rzp = log.bank_transaction, log.rzp_settlement
        _text(ledger, row, 1, _date(log))
        _text(ledger, row, 2, bank.utr if bank else "")
        _text(ledger, row, 3, rzp.settlement_id if rzp else "")
        _money(ledger, row, 4, to_decimal(bank.amount) if bank else None)
        _money(ledger, row, 5, to_decimal(rzp.gross_amount) if rzp else None)
        _money(ledger, row, 6, to_decimal(rzp.fees) if rzp else None)
        _money(ledger, row, 7, to_decimal(rzp.tax) if rzp else None)
        _money(ledger, row, 8, to_decimal(rzp.amount) if rzp else None)
        _text(ledger, row, 9, log.match_tier)
        _text(ledger, row, 10, log.diagnostic_type)
        _text(ledger, row, 11, log.human_action or "AUTO")
    _add_sum_row(ledger, LEDGER_MONEY_COLUMNS, len(matched) + 1)
    _autofit(ledger)

    # Exceptions
    _write_header(exceptions, EXCEPTION_HEADERS)
    for row, log in enumerate(problems, start=2):
        bank, rzp = log.bank_transaction, log.rzp_settlement
        _text(exceptions, row, 1, _date(log))
        _text(exceptions, row, 2, bank.utr if bank else "")
        _text(exceptions, row, 3, rzp.settlement_id if rzp else "")
        _money(exceptions, row, 4, to_decimal(bank.amount) if bank else None)
        _money(exceptions, row, 5, to_decimal(rzp.amount) if rzp else None)
        _money(exceptions, row, 6, to_decimal(log.delta_amount))
        _text(exceptions, row, 7, log.match_status)
        _text(exceptions, row, 8, log.diagnostic_type)
        _text(exceptions, row, 9, log.diagnostic_note)
    _add_sum_row(exceptions, EXCEPTION_MONEY_COLUMNS, len(problems) + 1)
    _autofit(exceptions)

    # Executive summary: formulas point at the detail sheets so the totals stay in sync
    tds = sum(
        (
            to_decimal(log.rzp_settlement.gross_amount) * settings.TDS_194O_RATE
            for log in matched
            if log.diagnostic_type == "TDS_194O_DEDUCTION" and log.rzp_settlement
        ),
        Decimal("0.00"),
    )
    total_ingested = sum(
        (to_decimal(log.bank_transaction.amount) for log in logs if log.bank_transaction), Decimal("0.00")
    )
    _write_header(summary, ["Metric", "Value"])
    last_l = max(len(matched) + 1, 2)
    last_e = max(len(problems) + 1, 2)
    rows: list[tuple[str, object]] = [
        ("Batch", batch_id),
        ("Total Ingested (bank rows)", total_ingested),
        ("Net Reconciled", f"=SUM('Reconciled Ledger'!D2:D{last_l})"),
        ("MDR Fees", f"=SUM('Reconciled Ledger'!F2:F{last_l})"),
        ("GST on Fees", f"=SUM('Reconciled Ledger'!G2:G{last_l})"),
        ("TDS (Section 194-O)", tds.quantize(Decimal("0.01"))),
        ("Unresolved Variance", f"=SUM('Exceptions & Discrepancies'!F2:F{last_e})"),
        ("Matched Rows", len(matched)),
        ("Exception / Conflict Rows", len(problems)),
    ]
    for row, (label, value) in enumerate(rows, start=2):
        summary.cell(row=row, column=1, value=label).font = Font(bold=True)
        if label == "Batch":
            _text(summary, row, 2, str(value))
        elif isinstance(value, Decimal):
            _money(summary, row, 2, value)
        elif isinstance(value, str):
            summary.cell(row=row, column=2, value=value).number_format = CURRENCY_FORMAT
        else:
            summary.cell(row=row, column=2, value=value)
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 22

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
