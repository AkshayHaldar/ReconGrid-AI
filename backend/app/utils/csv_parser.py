"""Streaming bank statement CSV parser with multi-bank dialect autodetection."""

import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncGenerator, Iterator, Literal, Tuple
from app.utils.money import to_decimal

# Regex for extracting Indian banking UTR / Transaction Reference numbers
UTR_REGEX = re.compile(
    r"(?:CMS|NEFT|RTGS|IMPS|UPI|TXN|REF|SETTLEMENT)?[\/\s\-_:]*([A-Z0-9]{8,24})",
    re.IGNORECASE,
)

# Standardized Bank Formats Header Signatures
BANK_COLUMN_MAPPINGS = {
    "HDFC": {
        "date": ["Date", "Txn Date", "Transaction Date", "Value Date"],
        "narration": ["Narration", "Description", "Transaction Description", "Particulars"],
        "ref": ["Chq/Ref No.", "Reference No", "Ref No.", "Cheque / Ref. No."],
        "withdrawal": ["Withdrawal Amt.", "Debit", "Debit Amount", "Dr Amount"],
        "deposit": ["Deposit Amt.", "Credit", "Credit Amount", "Cr Amount"],
    },
    "ICICI": {
        "date": ["Transaction Date", "Value Date", "Date"],
        "narration": ["Transaction Remarks", "Remarks", "Description"],
        "ref": ["Transaction Reference Number", "Cheque. No.", "Ref No"],
        "withdrawal": ["Withdrawal Amount (INR )", "Dr", "Debit Amount"],
        "deposit": ["Deposit Amount (INR )", "Cr", "Credit Amount"],
    },
    "SBI": {
        "date": ["Txn Date", "Value Date", "Date"],
        "narration": ["Description", "Narration"],
        "ref": ["Ref No./Cheque No.", "Txn Ref No", "Ref No"],
        "withdrawal": ["Debit", "Debit Amount"],
        "deposit": ["Credit", "Credit Amount"],
    },
    "AXIS": {
        "date": ["Tran Date", "Date", "Value Date"],
        "narration": ["PARTICULARS", "Particulars", "Description"],
        "ref": ["CHQNO", "Ref No", "Reference Number"],
        "withdrawal": ["DR", "Debit", "Withdrawal Amount"],
        "deposit": ["CR", "Credit", "Deposit Amount"],
    },
    "GENERIC": {
        "date": ["date", "txn_date", "transaction_date", "timestamp"],
        "narration": ["description", "narration", "remarks", "particulars", "desc"],
        "ref": ["utr", "ref", "reference", "utr_number", "rrn", "ref_no"],
        "amount": ["amount", "net_amount", "txn_amount"],
        "direction": ["type", "direction", "dr_cr", "cr_dr"],
        "withdrawal": ["debit", "withdrawal", "dr"],
        "deposit": ["credit", "deposit", "cr"],
    },
}


def extract_utr_from_text(text: str | None) -> str | None:
    """Extracts a UTR / reference alphanumeric code from raw description text."""
    if not text:
        return None
    match = UTR_REGEX.search(text)
    if match:
        candidate = match.group(1).strip()
        if len(candidate) >= 8:
            return candidate
    return None


def parse_flexible_date(date_str: str) -> datetime:
    """Parses various date formats commonly found in bank statements."""
    clean_date = date_str.strip()
    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(clean_date, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Fallback to current date if parsing fails completely
    return datetime.now(timezone.utc)


def compute_row_hash(
    date_val: datetime,
    amount: Decimal,
    direction: str,
    utr: str | None,
    description: str,
) -> str:
    """Generates a deterministic SHA-256 hash for row idempotency."""
    formatted_date = date_val.strftime("%Y-%m-%d")
    raw_key = f"{formatted_date}|{amount:.2f}|{direction}|{utr or ''}|{description.strip().upper()}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class BankCsvParser:
    """Stream-capable bank CSV parser."""

    @staticmethod
    def detect_headers(fieldnames: list[str]) -> dict[str, str]:
        """Maps bank-specific headers to canonical fields (date, description, ref, amount/cr/dr)."""
        clean_fields = {f.strip(): f for f in fieldnames if f}
        lower_map = {f.strip().lower(): f for f in fieldnames if f}

        mapping: dict[str, str] = {}

        # First check generic lowercased exact matches
        for canonical, options in BANK_COLUMN_MAPPINGS["GENERIC"].items():
            for opt in options:
                if opt in lower_map:
                    mapping[canonical] = lower_map[opt]
                    break

        # Check bank-specific mappings
        for bank_name, bank_map in BANK_COLUMN_MAPPINGS.items():
            if bank_name == "GENERIC":
                continue
            for canonical, options in bank_map.items():
                if canonical not in mapping:
                    for opt in options:
                        if opt in clean_fields:
                            mapping[canonical] = clean_fields[opt]
                            break
                        elif opt.lower() in lower_map:
                            mapping[canonical] = lower_map[opt.lower()]
                            break

        return mapping

    @classmethod
    def parse_csv_stream(
        cls,
        text_stream: Iterator[str],
    ) -> Iterator[dict[str, Any]]:
        """Parses CSV text stream row by row yielding canonical records."""
        reader = csv.DictReader(text_stream)
        if not reader.fieldnames:
            return

        header_map = cls.detect_headers(list(reader.fieldnames))

        for row_idx, row in enumerate(reader, start=1):
            if not any(row.values()):
                continue  # Skip blank lines

            try:
                # Extract Date
                date_col = header_map.get("date")
                raw_date = row.get(date_col, "") if date_col else ""
                parsed_date = parse_flexible_date(raw_date) if raw_date else datetime.now(timezone.utc)

                # Extract Description / Narration
                desc_col = header_map.get("narration")
                description = (row.get(desc_col, "") if desc_col else "").strip()

                # Extract UTR / Ref No
                ref_col = header_map.get("ref")
                utr = (row.get(ref_col, "") if ref_col else "").strip() or extract_utr_from_text(description)

                # Extract Amount & Direction (Credit vs Debit)
                amount = Decimal("0.00")
                direction: Literal["CREDIT", "DEBIT"] = "CREDIT"

                dep_col = header_map.get("deposit")
                wdr_col = header_map.get("withdrawal")
                amt_col = header_map.get("amount")
                dir_col = header_map.get("direction")

                if dep_col and row.get(dep_col) and to_decimal(row.get(dep_col)) > Decimal("0.00"):
                    amount = to_decimal(row.get(dep_col))
                    direction = "CREDIT"
                elif wdr_col and row.get(wdr_col) and to_decimal(row.get(wdr_col)) > Decimal("0.00"):
                    amount = to_decimal(row.get(wdr_col))
                    direction = "DEBIT"
                elif amt_col and row.get(amt_col):
                    raw_amt = to_decimal(row.get(amt_col))
                    if raw_amt < Decimal("0.00"):
                        amount = abs(raw_amt)
                        direction = "DEBIT"
                    else:
                        amount = raw_amt
                        if dir_col and str(row.get(dir_col)).upper().startswith("D"):
                            direction = "DEBIT"
                        else:
                            direction = "CREDIT"
                else:
                    # Skip rows with no amount
                    continue

                row_hash = compute_row_hash(parsed_date, amount, direction, utr, description)

                yield {
                    "row_index": row_idx,
                    "row_hash": row_hash,
                    "date": parsed_date,
                    "amount": amount,
                    "direction": direction,
                    "utr": utr if utr else None,
                    "description": description,
                    "raw_csv_row": row,
                }
            except Exception as ex:
                # Log or preserve row parse failure metadata
                continue
