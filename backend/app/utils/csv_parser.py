"""Streaming bank statement CSV parser with multi-bank dialect autodetection and preamble resilience."""

import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator, Literal, Optional, Tuple

from app.core.logging import logger
from app.utils.money import (
    UnscaledPaiseAmountError,
    parse_amount_and_direction,
    to_decimal,
    validate_raw_amount_format,
)

# Reserved non-UTR tokens commonly appearing in Indian banking narrations
NON_UTR_WORDS = {
    "RAZORPAY",
    "SETTLEMENT",
    "SETTLEMNT",
    "SOFTWARE",
    "BANGALORE",
    "BENGALURU",
    "MUMBAI",
    "DELHI",
    "CHENNAI",
    "HYDERABAD",
    "KOLKATA",
    "TRANSFER",
    "PAYMENT",
    "PAYOUT",
    "MERCHANT",
    "CHARGES",
    "STATEMENT",
    "TRANSACTION",
    "PARTICULARS",
    "DESCRIPTION",
    "INTERNET",
    "BANKING",
    "NETBANKING",
    "INTERNAL",
    "REVERSAL",
    "REFUND",
    "ADJUSTMENT",
    "PURCHASE",
    "OUTWARD",
    "INWARD",
    "SERVICE",
    "CLEARING",
    "CREDIT",
    "DEBIT",
    "BALANCE",
    "OPENING",
    "CLOSING",
}

# Regex for tokenizing narrations into candidate reference strings
TOKEN_SPLIT_REGEX = re.compile(r"[\/\s\-_:,;#]+", re.IGNORECASE)

# Standardized Bank Formats Header Signatures
BANK_COLUMN_MAPPINGS = {
    "HDFC": {
        "date": ["Date", "Txn Date", "Transaction Date", "Value Date"],
        "narration": ["Narration", "Description", "Transaction Description", "Particulars"],
        "ref": ["Chq/Ref No.", "Reference No", "Ref No.", "Ref No", "Cheque / Ref. No."],
        "withdrawal": ["Withdrawal Amt.", "Withdrawal Amt", "Debit", "Debit Amount", "Dr Amount"],
        "deposit": ["Deposit Amt.", "Deposit Amt", "Credit", "Credit Amount", "Cr Amount"],
    },
    "ICICI": {
        "date": ["Transaction Date", "Value Date", "Date"],
        "narration": ["Transaction Remarks", "Remarks", "Description", "Particulars"],
        "ref": ["Transaction Reference Number", "Cheque. No.", "Ref No", "Ref No."],
        "withdrawal": ["Withdrawal Amount (INR )", "Withdrawal Amount", "Dr", "Debit Amount", "Debit"],
        "deposit": ["Deposit Amount (INR )", "Deposit Amount", "Cr", "Credit Amount", "Credit"],
    },
    "SBI": {
        "date": ["Txn Date", "Value Date", "Date"],
        "narration": ["Description", "Narration", "Particulars"],
        "ref": ["Ref No./Cheque No.", "Txn Ref No", "Ref No", "Ref No."],
        "withdrawal": ["Debit", "Debit Amount", "Dr Amount"],
        "deposit": ["Credit", "Credit Amount", "Cr Amount"],
    },
    "AXIS": {
        "date": ["Tran Date", "Date", "Value Date", "Txn Date"],
        "narration": ["PARTICULARS", "Particulars", "Description", "Narration"],
        "ref": ["CHQNO", "Ref No", "Reference Number", "Ref No."],
        "withdrawal": ["DR", "Debit", "Withdrawal Amount", "DR Amount"],
        "deposit": ["CR", "Credit", "Deposit Amount", "CR Amount"],
    },
    "KOTAK": {
        "date": ["Transaction Date", "Date", "Value Date"],
        "narration": ["Description", "Narration", "Transaction Details"],
        "ref": ["Ref / Chq No", "Ref No", "Chq No"],
        "withdrawal": ["Debit (Dr)", "Debit", "Dr"],
        "deposit": ["Credit (Cr)", "Credit", "Cr"],
    },
    "GENERIC": {
        "date": ["date", "txn_date", "transaction_date", "tran_date", "timestamp", "booking_date", "value_date"],
        "narration": ["description", "narration", "remarks", "particulars", "desc", "details", "memo", "transaction_details"],
        "ref": ["utr", "ref", "reference", "utr_number", "rrn", "ref_no", "chq_no", "cheque_no", "ref_no.", "reference_number"],
        "amount": ["amount", "net_amount", "txn_amount", "transaction_amount", "total_amount"],
        "direction": ["type", "direction", "dr_cr", "cr_dr", "transaction_type", "dr/cr", "cr/dr"],
        "withdrawal": ["debit", "withdrawal", "dr", "debit_amount", "dr_amount", "outflow", "withdrawal_amount"],
        "deposit": ["credit", "deposit", "cr", "credit_amount", "cr_amount", "inflow", "deposit_amount"],
    },
}


def extract_utr_from_text(text: str | None) -> str | None:
    """Extracts a valid Indian banking UTR / reference alphanumeric code from raw description text."""
    if not text:
        return None

    clean_text = text.strip()
    if not clean_text:
        return None

    tokens = TOKEN_SPLIT_REGEX.split(clean_text)
    for tok in tokens:
        candidate = tok.strip().upper()
        if 8 <= len(candidate) <= 24 and candidate not in NON_UTR_WORDS:
            # Must contain at least one digit or match standard banking prefixes
            if any(c.isdigit() for c in candidate) or candidate.startswith("CMS") or candidate.startswith("UTR"):
                return candidate

    return None


def parse_flexible_date(date_str: str) -> datetime:
    """Parses various date formats commonly found in Indian bank statements."""
    clean_date = date_str.strip()
    # Strip any trailing timezone words like 'IST', 'UTC', 'GMT'
    clean_date = re.sub(r"\s+(?:IST|UTC|GMT|EDT|EST)$", "", clean_date, flags=re.IGNORECASE).strip()

    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %B %Y",
        "%d-%B-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(clean_date, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Try matching first date substring if line has extraneous text e.g. "01-08-2026 14:30:00.000"
    date_match = re.search(r"(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{2,4})", clean_date)
    if date_match:
        sub_date = date_match.group(1)
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"]:
            try:
                dt = datetime.strptime(sub_date, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    raise ValueError(f"Unable to parse date string: '{date_str}'")


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
    """Stream-capable bank CSV parser with preamble detection and multi-bank dialect mapping."""

    @staticmethod
    def detect_headers(fieldnames: list[str]) -> dict[str, str]:
        """Maps bank-specific headers to canonical fields (date, description, ref, amount/cr/dr)."""
        clean_fields = {f.strip(): f for f in fieldnames if f and f.strip()}
        lower_map = {f.strip().lower(): f for f in fieldnames if f and f.strip()}

        mapping: dict[str, str] = {}

        # 1. Exact lowercased matches on generic mappings
        for canonical, options in BANK_COLUMN_MAPPINGS["GENERIC"].items():
            for opt in options:
                if opt in lower_map:
                    mapping[canonical] = lower_map[opt]
                    break

        # 2. Check bank-specific exact mappings
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

        # 3. Word-boundary regex matching for composite headers (e.g. "Withdrawal Amount (INR )", "Debit (Dr)")
        for canonical, options in BANK_COLUMN_MAPPINGS["GENERIC"].items():
            if canonical not in mapping:
                for opt in options:
                    for header_lower, raw_header in lower_map.items():
                        # Use word boundary to avoid matching "dr" inside "description"
                        pattern = rf"\b{re.escape(opt)}\b"
                        if re.search(pattern, header_lower):
                            mapping[canonical] = raw_header
                            break
                    if canonical in mapping:
                        break

        return mapping

    @classmethod
    def _find_header_and_data_lines(cls, lines: list[str]) -> Tuple[list[str], list[str]]:
        """Scans lines to detect and skip preamble metadata, returning (header_row, data_lines)."""
        best_header_idx = -1
        best_header_fields: list[str] = []
        best_score = 0

        for idx, line in enumerate(lines[:30]):  # check up to first 30 lines for table header
            clean = line.strip()
            if not clean:
                continue
            try:
                reader = csv.reader([clean])
                fields = next(reader, [])
                if not fields or len(fields) < 2:
                    continue
                mapping = cls.detect_headers(fields)
                # Score based on how many canonical columns were identified
                score = len(mapping)
                # Header must contain at least a date or narration or amount/deposit/withdrawal
                has_essential = (
                    "date" in mapping
                    and ("deposit" in mapping or "withdrawal" in mapping or "amount" in mapping or "narration" in mapping)
                )
                if has_essential and score > best_score:
                    best_score = score
                    best_header_idx = idx
                    best_header_fields = fields
            except Exception:
                continue

        if best_header_idx >= 0:
            return best_header_fields, lines[best_header_idx:]
        return [], lines

    @classmethod
    def parse_csv_stream(
        cls,
        text_stream: Iterator[str],
    ) -> Iterator[dict[str, Any]]:
        """Parses CSV text stream row by row yielding canonical records with robust error handling."""
        raw_lines = [l for l in text_stream]
        if not raw_lines:
            return

        header_fields, table_lines = cls._find_header_and_data_lines(raw_lines)
        if not table_lines:
            return

        reader = csv.DictReader(table_lines)
        if not reader.fieldnames:
            return

        header_map = cls.detect_headers(list(reader.fieldnames))

        for row_idx, row in enumerate(reader, start=1):
            if not any(v and str(v).strip() for v in row.values() if v is not None):
                continue  # Skip blank and whitespace-only lines

            try:
                # Extract Date
                date_col = header_map.get("date")
                raw_date = str(row.get(date_col, "")).strip() if date_col else ""
                parsed_date = parse_flexible_date(raw_date) if raw_date else datetime.now(timezone.utc)

                # Extract Description / Narration
                desc_col = header_map.get("narration")
                description = (str(row.get(desc_col, "")).strip()) if desc_col else ""

                # Extract UTR / Ref No
                ref_col = header_map.get("ref")
                raw_ref = (str(row.get(ref_col, "")).strip()) if ref_col else ""
                utr = raw_ref or extract_utr_from_text(description)

                # Extract Amount & Direction (Credit vs Debit)
                amount = Decimal("0.00")
                direction: Literal["CREDIT", "DEBIT"] = "CREDIT"

                dep_col = header_map.get("deposit")
                wdr_col = header_map.get("withdrawal")
                amt_col = header_map.get("amount")
                dir_col = header_map.get("direction")

                # Check Deposit column first
                if dep_col and row.get(dep_col) and str(row.get(dep_col)).strip():
                    raw_dep = str(row.get(dep_col)).strip()
                    val, dep_dir = parse_amount_and_direction(raw_dep)
                    if val > Decimal("0.00"):
                        validate_raw_amount_format(raw_dep, col_name=dep_col, row_idx=row_idx)
                        amount = val
                        direction = dep_dir if dep_dir == "DEBIT" else "CREDIT"

                # Check Withdrawal column if amount is still 0
                if amount == Decimal("0.00") and wdr_col and row.get(wdr_col) and str(row.get(wdr_col)).strip():
                    raw_wdr = str(row.get(wdr_col)).strip()
                    val, wdr_dir = parse_amount_and_direction(raw_wdr)
                    if val > Decimal("0.00"):
                        validate_raw_amount_format(raw_wdr, col_name=wdr_col, row_idx=row_idx)
                        amount = val
                        direction = "DEBIT"

                # Check Generic Amount column if deposit/withdrawal not found
                if amount == Decimal("0.00") and amt_col and row.get(amt_col) and str(row.get(amt_col)).strip():
                    raw_amt_str = str(row.get(amt_col)).strip()
                    val, detected_dir = parse_amount_and_direction(raw_amt_str)
                    if val > Decimal("0.00"):
                        validate_raw_amount_format(raw_amt_str, col_name=amt_col, row_idx=row_idx)
                        amount = val
                        if dir_col and row.get(dir_col):
                            dir_str = str(row.get(dir_col)).strip().upper()
                            direction = "DEBIT" if dir_str.startswith("D") else "CREDIT"
                        else:
                            direction = detected_dir

                if amount == Decimal("0.00"):
                    # Skip rows with zero or missing amount
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
            except UnscaledPaiseAmountError as ex:
                logger.warning("csv_row_unscaled_paise_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": str(ex),
                    "raw_csv_row": row,
                }
                continue
            except ValueError as ex:
                logger.warning("csv_row_value_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": f"Row {row_idx}: {str(ex)}",
                    "raw_csv_row": row,
                }
                continue
            except Exception as ex:
                logger.error("csv_row_unexpected_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": f"Row {row_idx}: Unexpected error parsing row: {str(ex)}",
                    "raw_csv_row": row,
                }
                continue
