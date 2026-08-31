"""Multi-page Bank Statement PDF parser with password decryption, table extraction, and OCR support."""

import base64
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator, List, Optional

import httpx
import pdfplumber
import pypdf

from app.core.config import settings
from app.core.logging import logger
from app.utils.csv_parser import compute_row_hash, extract_utr_from_text, parse_flexible_date
from app.utils.money import to_decimal

# Known Indian Bank Password Formats / Patterns Guide
BANK_PASSWORD_FORMATS = [
    {
        "bank": "HDFC Bank",
        "pattern": "Customer ID (or DOB in DDMMYYYY format, or first 4 letters of name in lowercase + DDMM)",
        "example": "12345678 or 15081995 or aksh1508",
    },
    {
        "bank": "ICICI Bank",
        "pattern": "First 4 letters of name in LOWERCASE + DDMM of Birth",
        "example": "aksh1508 (for Akshay, DOB 15-Aug)",
    },
    {
        "bank": "State Bank of India (SBI)",
        "pattern": "Last 5 digits of registered Mobile No + DDMM of DOB (or 11-digit Account Number)",
        "example": "987651508 or 0000012345678",
    },
    {
        "bank": "Axis Bank",
        "pattern": "First 4 letters of Name (CAPITAL) + Last 4 digits of Customer ID (or Mobile)",
        "example": "AKSH1234",
    },
    {
        "bank": "Kotak Mahindra Bank",
        "pattern": "CRN Number (Customer Relationship Number) or DOB (DDMMYYYY)",
        "example": "98765432 or 15081995",
    },
    {
        "bank": "Punjab National Bank (PNB)",
        "pattern": "Account Number or Customer ID",
        "example": "1234000100123456",
    },
    {
        "bank": "Bank of Baroda (BOB)",
        "pattern": "Registered Mobile Number or First 4 letters of Name + DDMM",
        "example": "9876543210 or AKSH1508",
    },
    {
        "bank": "Canara Bank",
        "pattern": "Customer ID or 13-digit Account Number",
        "example": "123456789",
    },
]


class PdfPasswordRequiredError(Exception):
    """Raised when a PDF is encrypted and requires a password to open."""
    pass


class PdfInvalidPasswordError(Exception):
    """Raised when the provided password fails to decrypt the PDF."""
    pass


class BankPdfParser:
    """Parser for multi-page digital and scanned bank statement PDFs."""

    # Common bank column regex patterns
    DATE_HEADER = re.compile(r"(date|txn\s*date|trans\s*date|value\s*date)", re.IGNORECASE)
    NARRATION_HEADER = re.compile(r"(narration|description|particulars|remarks|details|transaction\s*details)", re.IGNORECASE)
    REF_HEADER = re.compile(r"(chq|ref|cheque|reference|utr|rrn|txn\s*id)", re.IGNORECASE)
    DEBIT_HEADER = re.compile(r"(debit|dr|withdrawal|dr\s*amount|withdrawal\s*amt)", re.IGNORECASE)
    CREDIT_HEADER = re.compile(r"(credit|cr|deposit|cr\s*amount|deposit\s*amt)", re.IGNORECASE)
    AMOUNT_HEADER = re.compile(r"(amount|txn\s*amount|net\s*amount)", re.IGNORECASE)
    BALANCE_HEADER = re.compile(r"(balance|bal|closing\s*balance)", re.IGNORECASE)

    DATE_LINE_REGEX = re.compile(
        r"^(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})"
    )

    @classmethod
    def decrypt_pdf_bytes(cls, pdf_bytes: bytes, password: Optional[str] = None) -> bytes:
        """Attempts to decrypt PDF bytes using PyPDF and returns decrypted PDF bytes."""
        input_stream = io.BytesIO(pdf_bytes)
        try:
            reader = pypdf.PdfReader(input_stream)
        except Exception as e:
            raise ValueError(f"Failed to read PDF file: {str(e)}")

        if not reader.is_encrypted:
            return pdf_bytes

        # PDF is encrypted. Try empty password first if none provided
        pwd = password.strip() if password else ""
        
        # Check if empty string can decrypt
        if not pwd:
            try:
                res = reader.decrypt("")
                if res > 0:
                    out_stream = io.BytesIO()
                    writer = pypdf.PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    writer.write(out_stream)
                    return out_stream.getvalue()
            except Exception:
                pass
            raise PdfPasswordRequiredError(
                "This bank statement PDF is password-protected. Please enter your PDF password."
            )

        # Attempt decryption with user password
        try:
            res = reader.decrypt(pwd)
            if res == 0:
                raise PdfInvalidPasswordError(
                    "Incorrect PDF password. Please check your bank's password format and try again."
                )
        except PdfInvalidPasswordError:
            raise
        except Exception as ex:
            raise PdfInvalidPasswordError(f"Password decryption failed: {str(ex)}")

        # Create unencrypted PDF bytes in memory
        out_stream = io.BytesIO()
        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.write(out_stream)
        return out_stream.getvalue()

    @classmethod
    def parse_pdf(
        cls,
        pdf_bytes: bytes,
        password: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        """Parses multi-page PDF bank statement, handling decryption and tables/text."""
        decrypted_bytes = cls.decrypt_pdf_bytes(pdf_bytes, password=password)

        parsed_rows: List[dict[str, Any]] = []

        try:
            with pdfplumber.open(io.BytesIO(decrypted_bytes)) as pdf:
                # 1. Try table extraction across all pages
                for page_idx, page in enumerate(pdf.pages, start=1):
                    page_rows = cls._extract_tables_from_page(page, page_idx)
                    parsed_rows.extend(page_rows)

                # 2. If table extraction yielded nothing, try text line extraction
                if not parsed_rows:
                    logger.info("pdf_table_empty_fallback_to_text_regex", pages=len(pdf.pages))
                    for page_idx, page in enumerate(pdf.pages, start=1):
                        text = page.extract_text() or ""
                        if text:
                            page_rows = cls._extract_from_text_lines(text, page_idx)
                            parsed_rows.extend(page_rows)

                # 3. If still no rows and OCR is possible (scanned PDF)
                if not parsed_rows and (settings.OCR_API_KEY or settings.GEMINI_API_KEY or settings.LLM_API_KEY):
                    logger.info("pdf_text_empty_attempting_ocr", pages=len(pdf.pages))
                    ocr_rows = cls._extract_via_ocr(pdf)
                    parsed_rows.extend(ocr_rows)

        except (PdfPasswordRequiredError, PdfInvalidPasswordError):
            raise
        except Exception as e:
            logger.error("pdf_parse_error", error=str(e))
            raise ValueError(f"Failed to extract bank transactions from PDF: {str(e)}")

        return parsed_rows

    @classmethod
    def _extract_tables_from_page(cls, page: pdfplumber.page.Page, page_idx: int) -> List[dict[str, Any]]:
        """Extracts and normalizes transactions from tables on a PDF page."""
        results: List[dict[str, Any]] = []
        tables = page.extract_tables()
        if not tables:
            return results

        for table in tables:
            if not table or len(table) < 2:
                continue

            # Find header index and header map
            header_idx = -1
            header_map: dict[str, int] = {}

            for idx, row in enumerate(table):
                if not row:
                    continue
                clean_row = [str(cell or "").strip() for cell in row]
                mapping = cls._map_table_headers(clean_row)
                if "date" in mapping and ("withdrawal" in mapping or "deposit" in mapping or "amount" in mapping):
                    header_idx = idx
                    header_map = mapping
                    break

            if header_idx == -1:
                continue

            # Parse data rows below the header
            for row_offset, row in enumerate(table[header_idx + 1 :]):
                if not row:
                    continue
                clean_cells = [str(c or "").strip().replace("\n", " ") for c in row]
                if not any(clean_cells):
                    continue

                date_idx = header_map.get("date")
                raw_date = clean_cells[date_idx] if (date_idx is not None and date_idx < len(clean_cells)) else ""
                if not raw_date or not cls.DATE_LINE_REGEX.match(raw_date):
                    continue

                parsed_date = parse_flexible_date(raw_date)

                desc_idx = header_map.get("narration")
                description = clean_cells[desc_idx] if (desc_idx is not None and desc_idx < len(clean_cells)) else ""

                ref_idx = header_map.get("ref")
                raw_ref = clean_cells[ref_idx] if (ref_idx is not None and ref_idx < len(clean_cells)) else ""
                utr = raw_ref or extract_utr_from_text(description)

                wdr_idx = header_map.get("withdrawal")
                dep_idx = header_map.get("deposit")
                amt_idx = header_map.get("amount")

                amount = Decimal("0.00")
                direction = "CREDIT"

                raw_dep = clean_cells[dep_idx] if (dep_idx is not None and dep_idx < len(clean_cells)) else ""
                raw_wdr = clean_cells[wdr_idx] if (wdr_idx is not None and wdr_idx < len(clean_cells)) else ""
                raw_amt = clean_cells[amt_idx] if (amt_idx is not None and amt_idx < len(clean_cells)) else ""

                if raw_dep and to_decimal(raw_dep) > Decimal("0.00"):
                    amount = to_decimal(raw_dep)
                    direction = "CREDIT"
                elif raw_wdr and to_decimal(raw_wdr) > Decimal("0.00"):
                    amount = to_decimal(raw_wdr)
                    direction = "DEBIT"
                elif raw_amt:
                    parsed_amt = to_decimal(raw_amt)
                    amount = abs(parsed_amt)
                    direction = "DEBIT" if parsed_amt < Decimal("0.00") else "CREDIT"
                else:
                    continue

                row_hash = compute_row_hash(parsed_date, amount, direction, utr, description)

                results.append({
                    "row_index": len(results) + 1,
                    "row_hash": row_hash,
                    "date": parsed_date,
                    "amount": amount,
                    "direction": direction,
                    "utr": utr if utr else None,
                    "description": description,
                    "raw_csv_row": {
                        "date": raw_date,
                        "description": description,
                        "ref": raw_ref,
                        "withdrawal": raw_wdr,
                        "deposit": raw_dep,
                        "page": page_idx,
                    },
                })

        return results

    @classmethod
    def _map_table_headers(cls, headers: List[str]) -> dict[str, int]:
        """Maps column indices to canonical fields based on regex matching."""
        mapping: dict[str, int] = {}
        for idx, text in enumerate(headers):
            if not text:
                continue
            if cls.DATE_HEADER.search(text) and "date" not in mapping:
                mapping["date"] = idx
            elif cls.NARRATION_HEADER.search(text) and "narration" not in mapping:
                mapping["narration"] = idx
            elif cls.REF_HEADER.search(text) and "ref" not in mapping:
                mapping["ref"] = idx
            elif cls.DEBIT_HEADER.search(text) and "withdrawal" not in mapping:
                mapping["withdrawal"] = idx
            elif cls.CREDIT_HEADER.search(text) and "deposit" not in mapping:
                mapping["deposit"] = idx
            elif cls.AMOUNT_HEADER.search(text) and "amount" not in mapping:
                mapping["amount"] = idx
        return mapping

    @classmethod
    def _extract_from_text_lines(cls, text: str, page_idx: int) -> List[dict[str, Any]]:
        """Fallback line-based parser using regex for non-standard or borderless PDF layouts."""
        results: List[dict[str, Any]] = []
        lines = text.splitlines()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            match = cls.DATE_LINE_REGEX.match(line_str)
            if not match:
                continue

            raw_date = match.group(1)
            parsed_date = parse_flexible_date(raw_date)

            # Find numerical tokens at the end of the line (amounts / balance)
            tokens = line_str[len(raw_date) :].strip().split()
            if len(tokens) < 2:
                continue

            # Extract amounts from right side of tokens
            amount_val = Decimal("0.00")
            direction = "CREDIT"
            narration_tokens = []

            # Check for Cr / Dr indicator
            if tokens[-1].upper() in ("CR", "CR.", "CREDIT"):
                direction = "CREDIT"
                amount_candidate = tokens[-2] if len(tokens) >= 2 else ""
                amount_val = to_decimal(amount_candidate)
                narration_tokens = tokens[:-2]
            elif tokens[-1].upper() in ("DR", "DR.", "DEBIT"):
                direction = "DEBIT"
                amount_candidate = tokens[-2] if len(tokens) >= 2 else ""
                amount_val = to_decimal(amount_candidate)
                narration_tokens = tokens[:-2]
            else:
                # Look for numbers
                num_indices = []
                for i, tok in enumerate(tokens):
                    clean_tok = tok.replace(",", "").replace("₹", "")
                    try:
                        float(clean_tok)
                        num_indices.append(i)
                    except ValueError:
                        pass

                if not num_indices:
                    continue

                first_num_idx = num_indices[0]
                amount_val = to_decimal(tokens[first_num_idx])
                narration_tokens = tokens[:first_num_idx]

            if amount_val <= Decimal("0.00"):
                continue

            description = " ".join(narration_tokens).strip()
            utr = extract_utr_from_text(description)
            row_hash = compute_row_hash(parsed_date, amount_val, direction, utr, description)

            results.append({
                "row_index": len(results) + 1,
                "row_hash": row_hash,
                "date": parsed_date,
                "amount": amount_val,
                "direction": direction,
                "utr": utr if utr else None,
                "description": description,
                "raw_csv_row": {
                    "raw_line": line_str,
                    "page": page_idx,
                },
            })

        return results

    @classmethod
    def _extract_via_ocr(cls, pdf: pdfplumber.PDF) -> List[dict[str, Any]]:
        """Extracts transactions from scanned PDF pages via LLM Vision / OCR."""
        results: List[dict[str, Any]] = []
        api_key = settings.GEMINI_API_KEY or settings.OCR_API_KEY or settings.LLM_API_KEY
        if not api_key:
            return results

        # Process each page as an image
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                img = page.to_image(resolution=200).original
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format="PNG")
                b64_data = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

                # If Gemini API key is available
                if settings.GEMINI_API_KEY or (settings.LLM_PROVIDER == "gemini" and api_key):
                    gemini_key = settings.GEMINI_API_KEY or api_key
                    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                    prompt = (
                        "Extract all bank statement transaction rows from this page image in structured format.\n"
                        "Output ONLY valid JSON array with objects containing:\n"
                        "date (YYYY-MM-DD), description (string), utr (string or null), amount (number), direction ('CREDIT' or 'DEBIT')."
                    )
                    payload = {
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt},
                                    {
                                        "inline_data": {
                                            "mime_type": "image/png",
                                            "data": b64_data,
                                        }
                                    },
                                ]
                            }
                        ]
                    }
                    headers = {
                        "x-goog-api-key": gemini_key,
                        "Content-Type": "application/json",
                    }
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.post(url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                            # Parse JSON array from output
                            clean_json = re.search(r"\[\s*\{.*\}\s*\]", text_out, re.DOTALL)
                            if clean_json:
                                import json
                                tx_list = json.loads(clean_json.group(0))
                                for row in tx_list:
                                    dt = parse_flexible_date(str(row.get("date", "")))
                                    amt = to_decimal(row.get("amount", "0"))
                                    direct = str(row.get("direction", "CREDIT")).upper()
                                    desc = str(row.get("description", ""))
                                    utr = row.get("utr") or extract_utr_from_text(desc)
                                    h = compute_row_hash(dt, amt, direct, utr, desc)
                                    results.append({
                                        "row_index": len(results) + 1,
                                        "row_hash": h,
                                        "date": dt,
                                        "amount": amt,
                                        "direction": direct,
                                        "utr": utr,
                                        "description": desc,
                                        "raw_csv_row": row,
                                    })
            except Exception as ocr_err:
                logger.warning("ocr_page_failed", page=page_idx, error=str(ocr_err))
                continue

        return results
