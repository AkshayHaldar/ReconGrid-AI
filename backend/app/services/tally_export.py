"""Tally Prime XML export: one balanced Journal voucher per matched gateway settlement.

Each voucher debits the bank (what actually landed), the gateway charge and the GST on that
charge, and credits the Razorpay clearing account with the gross settlement. Amounts are Decimal
end to end; a voucher whose debits do not equal its credit is left out and reported, never
written out unbalanced.
"""

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal

from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal

BANK_LEDGER = "Bank Account"
GATEWAY_CHARGES_LEDGER = "Payment Gateway Charges"
INPUT_GST_LEDGER = "Input GST (18%)"
TDS_RECEIVABLE_LEDGER = "TDS u/s 194-O Receivable"
CLEARING_LEDGER = "Razorpay Clearing Account"

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class TallyExport:
    xml: str
    voucher_count: int
    skipped: list[str] = field(default_factory=list)


def _tally_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _ledger_entry(parent: ET.Element, ledger: str, amount: Decimal, *, debit: bool) -> None:
    """Tally writes debit amounts as negative with ISDEEMEDPOSITIVE=Yes, credits as positive."""
    entry = ET.SubElement(parent, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(entry, "LEDGERNAME").text = ledger
    ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
    ET.SubElement(entry, "AMOUNT").text = _tally_amount(-amount if debit else amount)


def build_voucher_lines(log: ReconciliationLog, bank_ledger: str = BANK_LEDGER):
    """Return (debits, credit) as ledger/amount pairs, or None when the record is not postable."""
    bank, rzp = log.bank_transaction, log.rzp_settlement
    if log.match_status != "MATCHED" or bank is None or rzp is None:
        return None

    # Check for batched many-to-many settlement matches
    matches = getattr(log, "settlement_matches", None)
    if matches and len(matches) > 1:
        valid_setls = [m.rzp_settlement for m in matches if getattr(m, "rzp_settlement", None)]
        if valid_setls:
            gross = sum((to_decimal(s.gross_amount) or to_decimal(s.amount) for s in valid_setls), ZERO)
            fees_amt = sum((to_decimal(s.fees) for s in valid_setls), ZERO)
            tax_amt = sum((to_decimal(s.tax) for s in valid_setls), ZERO)
        else:
            gross = to_decimal(rzp.gross_amount) or to_decimal(rzp.amount)
            fees_amt = to_decimal(rzp.fees)
            tax_amt = to_decimal(rzp.tax)
    else:
        gross = to_decimal(rzp.gross_amount) or to_decimal(rzp.amount)
        fees_amt = to_decimal(rzp.fees)
        tax_amt = to_decimal(rzp.tax)

    bank_amt = to_decimal(bank.amount)

    debits = [
        (bank_ledger, bank_amt),
        (GATEWAY_CHARGES_LEDGER, fees_amt),
        (INPUT_GST_LEDGER, tax_amt),
    ]

    # Handle Section 194-O E-Commerce TDS deduction to preserve double-entry balance
    if log.diagnostic_type == "TDS_194O_DEDUCTION":
        tds_amount = gross - (bank_amt + fees_amt + tax_amt)
        if tds_amount > ZERO:
            debits.append((TDS_RECEIVABLE_LEDGER, tds_amount))
    elif gross > (bank_amt + fees_amt + tax_amt):
        remaining = gross - (bank_amt + fees_amt + tax_amt)
        if log.delta_amount and abs(to_decimal(log.delta_amount) - remaining) <= Decimal("1.00"):
            debits.append((TDS_RECEIVABLE_LEDGER, remaining))

    return [(name, amt) for name, amt in debits if amt != ZERO], (CLEARING_LEDGER, gross)


def is_balanced(debits, credit) -> bool:
    return sum((amt for _, amt in debits), ZERO) - credit[1] == ZERO


def build_tally_xml(logs: list[ReconciliationLog], bank_ledger: str = BANK_LEDGER) -> TallyExport:
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    request_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(request_desc, "REPORTNAME").text = "Vouchers"
    request_data = ET.SubElement(import_data, "REQUESTDATA")

    count = 0
    skipped: list[str] = []
    for log in logs:
        lines = build_voucher_lines(log, bank_ledger)
        if lines is None:
            continue
        debits, credit = lines
        setl_id = log.rzp_settlement.settlement_id
        if not is_balanced(debits, credit):
            skipped.append(setl_id)
            continue

        message = ET.SubElement(request_data, "TALLYMESSAGE")
        message.set("xmlns:UDF", "TallyUDF")
        voucher = ET.SubElement(message, "VOUCHER", {"VCHTYPE": "Journal", "ACTION": "Create"})
        ET.SubElement(voucher, "DATE").text = log.bank_transaction.date.strftime("%Y%m%d")
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = "Journal"
        ET.SubElement(voucher, "VOUCHERNUMBER").text = setl_id
        ET.SubElement(voucher, "NARRATION").text = (
            f"Razorpay settlement {setl_id} UTR {log.bank_transaction.utr or 'N/A'}"
        )
        for ledger, amount in debits:
            _ledger_entry(voucher, ledger, amount, debit=True)
        _ledger_entry(voucher, credit[0], credit[1], debit=False)
        count += 1

    ET.indent(envelope)
    buf = io.StringIO()
    ET.ElementTree(envelope).write(buf, encoding="unicode", xml_declaration=False)
    return TallyExport(xml=buf.getvalue(), voucher_count=count, skipped=skipped)
