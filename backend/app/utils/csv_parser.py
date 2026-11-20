"""Streaming bank statement CSV parser with multi-bank dialect autodetection and preamble resilience."""

import csv
import hashlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from app.core.logging import logger
from app.utils.money import (
    UnscaledPaiseAmountError,
    parse_amount_and_direction,
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
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue

    # Try matching first date substring if line has extraneous text e.g. "01-08-2026 14:30:00.000"
    date_match = re.search(r"(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{2,4})", clean_date)
    if date_match:
        sub_date = date_match.group(1)
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"]:
            try:
                dt = datetime.strptime(sub_date, fmt)
                return dt.replace(tzinfo=UTC)
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
        clean_fields = {f.lstrip("﻿").strip(): f for f in fieldnames if f and f.lstrip("﻿").strip()}
        lower_map = {f.lstrip("﻿").strip().lower(): f for f in fieldnames if f and f.lstrip("﻿").strip()}

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
    def _find_header_and_data_lines(
        cls,
        lines: list[str],
        custom_mappings: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Scans lines to detect and skip preamble metadata, returning (header_row, data_lines)."""
        best_header_idx = -1
        best_header_fields: list[str] = []
        best_score = 0

        for idx, line in enumerate(lines[:30]):  # check up to first 30 lines for table header
            clean = line.lstrip("﻿").strip()
            if not clean:
                continue
            try:
                reader = csv.reader([clean])
                fields = next(reader, [])
                if not fields or len(fields) < 2:
                    continue
                mapping = cls.detect_headers(fields)
                score = len(mapping)
                has_essential = (
                    "date" in mapping
                    and ("deposit" in mapping or "withdrawal" in mapping or "amount" in mapping or "narration" in mapping)
                )

                if custom_mappings:
                    clean_fields_set = {f.lstrip("﻿").strip().lower() for f in fields if f}
                    custom_matches = 0
                    for col_val in custom_mappings.values():
                        if col_val is None or col_val == "" or col_val == "__none__":
                            continue
                        col_str = str(col_val).strip()
                        if (isinstance(col_val, int) or col_str.isdigit()) and int(col_str) < len(fields):
                            custom_matches += 1
                        elif col_str.lower() in clean_fields_set:
                            custom_matches += 1

                    if custom_matches > 0:
                        score += custom_matches * 5
                        if custom_matches >= 2 or score >= 2:
                            has_essential = True

                if has_essential and score > best_score:
                    best_score = score
                    best_header_idx = idx
                    best_header_fields = fields
            except Exception:
                continue

        if best_header_idx >= 0:
            data_lines = lines[best_header_idx:]
            if data_lines:
                data_lines = [data_lines[0].lstrip("﻿")] + data_lines[1:]
            return best_header_fields, data_lines
        return [], lines

    @classmethod
    def parse_csv_stream(
        cls,
        text_stream: Iterator[str],
        custom_mappings: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Parses CSV text stream row by row yielding canonical records with robust error handling."""
        raw_lines = [l.lstrip("﻿") if idx == 0 else l for idx, l in enumerate(text_stream)]
        if not raw_lines:
            return

        header_fields, table_lines = cls._find_header_and_data_lines(raw_lines, custom_mappings=custom_mappings)
        if not table_lines:
            return

        if table_lines:
            table_lines = [table_lines[0].lstrip("﻿")] + table_lines[1:]

        reader = csv.reader(table_lines)
        raw_header_row = next(reader, None)
        if not raw_header_row:
            return

        clean_header_row = [h.lstrip("﻿").strip() for h in raw_header_row]
        num_cols = len(clean_header_row)

        target_indices: dict[str, int] = {}
        alias_map = {
            "description": "narration",
            "desc": "narration",
            "particulars": "narration",
            "remarks": "narration",
            "details": "narration",
            "memo": "narration",
            "narrative": "narration",
            "utr": "ref",
            "reference": "ref",
            "chq_no": "ref",
            "ref_no": "ref",
            "cheque_no": "ref",
            "credit": "deposit",
            "debit": "withdrawal",
            "deposit_amount": "deposit",
            "withdrawal_amount": "withdrawal",
            "cr": "deposit",
            "dr": "withdrawal",
        }

        if custom_mappings:
            for raw_k, raw_v in custom_mappings.items():
                if raw_k is None or raw_v is None or raw_v == "" or raw_v == "__none__":
                    continue
                k = str(raw_k).strip().lower()
                canon_k = alias_map.get(k, k)

                col_idx: int | None = None
                val_str = str(raw_v).strip()

                if isinstance(raw_v, int):
                    col_idx = raw_v
                elif val_str.isdigit():
                    col_idx = int(val_str)
                elif val_str.startswith("col_") and val_str[4:].isdigit():
                    col_idx = int(val_str[4:])
                elif val_str.startswith("__col_") and val_str[6:].rstrip("_").isdigit():
                    col_idx = int(val_str[6:].rstrip("_"))
                else:
                    # Match Col index pattern e.g. "Amount (Col 3)"
                    col_match = re.search(r"\(Col\s+(\d+)\)", val_str, re.IGNORECASE)
                    if col_match:
                        col_idx = int(col_match.group(1)) - 1
                    else:
                        dup_match = re.search(r"^(.+)_(\d+)$", val_str)
                        if dup_match:
                            base_name = dup_match.group(1).lower()
                            occ_target = int(dup_match.group(2))
                            occ = 0
                            for idx, h in enumerate(clean_header_row):
                                if h.lower() == base_name:
                                    occ += 1
                                    if occ == occ_target:
                                        col_idx = idx
                                        break

                    if col_idx is None:
                        for idx, h in enumerate(clean_header_row):
                            if h == val_str:
                                col_idx = idx
                                break
                    if col_idx is None:
                        for idx, h in enumerate(clean_header_row):
                            if h.lower() == val_str.lower():
                                col_idx = idx
                                break

                if col_idx is not None and 0 <= col_idx < num_cols:
                    target_indices[canon_k] = col_idx

            # If user mapped both amount and withdrawal, amount acts as the deposit column
            if "amount" in target_indices and "withdrawal" in target_indices:
                if "deposit" not in target_indices:
                    target_indices["deposit"] = target_indices.pop("amount")
        else:
            detected_map = cls.detect_headers(clean_header_row)
            for canon_k, raw_h in detected_map.items():
                for idx, h in enumerate(clean_header_row):
                    if h == raw_h:
                        target_indices[canon_k] = idx
                        break

        for row_idx, row_values in enumerate(reader, start=1):
            if not any(v and str(v).strip() for v in row_values if v is not None):
                continue

            try:
                def get_cell(col_idx: int | None) -> str:
                    if col_idx is not None and 0 <= col_idx < len(row_values):
                        return str(row_values[col_idx]).strip()
                    return ""

                raw_date = get_cell(target_indices.get("date"))
                parsed_date = parse_flexible_date(raw_date) if raw_date else datetime.now(UTC)

                description = get_cell(target_indices.get("narration"))
                raw_ref = get_cell(target_indices.get("ref"))
                utr = raw_ref or extract_utr_from_text(description)

                raw_dep = get_cell(target_indices.get("deposit"))
                raw_wdr = get_cell(target_indices.get("withdrawal"))
                raw_amt = get_cell(target_indices.get("amount"))
                raw_dir = get_cell(target_indices.get("direction"))

                amount = Decimal("0.00")
                direction: Literal["CREDIT", "DEBIT"] = "CREDIT"

                # 1. Check Deposit column
                if raw_dep:
                    val, dep_dir = parse_amount_and_direction(raw_dep)
                    if val > Decimal("0.00"):
                        dep_name = clean_header_row[target_indices["deposit"]] if "deposit" in target_indices else "Deposit"
                        validate_raw_amount_format(raw_dep, col_name=dep_name, row_idx=row_idx)
                        amount = val
                        direction = dep_dir if dep_dir == "DEBIT" else "CREDIT"

                # 2. Check Withdrawal column (for debit rows)
                if amount == Decimal("0.00") and raw_wdr:
                    val, wdr_dir = parse_amount_and_direction(raw_wdr)
                    if val > Decimal("0.00"):
                        wdr_name = clean_header_row[target_indices["withdrawal"]] if "withdrawal" in target_indices else "Withdrawal"
                        validate_raw_amount_format(raw_wdr, col_name=wdr_name, row_idx=row_idx)
                        amount = val
                        direction = "DEBIT"

                # 3. Check Generic Amount column if deposit/withdrawal not found
                if amount == Decimal("0.00") and raw_amt:
                    val, detected_dir = parse_amount_and_direction(raw_amt)
                    if val > Decimal("0.00"):
                        amt_name = clean_header_row[target_indices["amount"]] if "amount" in target_indices else "Amount"
                        validate_raw_amount_format(raw_amt, col_name=amt_name, row_idx=row_idx)
                        amount = val
                        if raw_dir:
                            direction = "DEBIT" if raw_dir.upper().startswith("D") else "CREDIT"
                        else:
                            direction = detected_dir

                if amount == Decimal("0.00"):
                    continue

                row_hash = compute_row_hash(parsed_date, amount, direction, utr, description)

                seen_keys: dict[str, int] = {}
                raw_csv_row: dict[str, Any] = {}
                for idx, val in enumerate(row_values):
                    h_name = clean_header_row[idx] if idx < len(clean_header_row) and clean_header_row[idx] else f"Column_{idx + 1}"
                    if h_name in seen_keys:
                        seen_keys[h_name] += 1
                        key = f"{h_name}_{seen_keys[h_name]}"
                    else:
                        seen_keys[h_name] = 1
                        key = h_name
                    raw_csv_row[key] = val

                yield {
                    "row_index": row_idx,
                    "row_hash": row_hash,
                    "date": parsed_date,
                    "amount": amount,
                    "direction": direction,
                    "utr": utr if utr else None,
                    "description": description,
                    "raw_csv_row": raw_csv_row,
                }
            except UnscaledPaiseAmountError as ex:
                logger.warning("csv_row_unscaled_paise_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": str(ex),
                    "raw_csv_row": raw_csv_row if "raw_csv_row" in locals() else {},
                }
                continue
            except ValueError as ex:
                logger.warning("csv_row_value_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": f"Row {row_idx}: {ex!s}",
                    "raw_csv_row": raw_csv_row if "raw_csv_row" in locals() else {},
                }
                continue
            except Exception as ex:
                logger.error("csv_row_unexpected_error", row_index=row_idx, error=str(ex))
                yield {
                    "row_index": row_idx,
                    "validation_error": f"Row {row_idx}: Unexpected error parsing row: {ex!s}",
                    "raw_csv_row": raw_csv_row if "raw_csv_row" in locals() else {},
                }
                continue
