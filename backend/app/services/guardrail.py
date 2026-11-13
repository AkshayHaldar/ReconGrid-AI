"""Strict Numeric Token Guardrail for Settlement Q&A Agent.

Enforces the non-negotiable rule: LLMs narrate facts, they NEVER compute or invent numbers.
Any generated answer containing a numeric token not present in the underlying record is rejected.

Scoped v1 Design Note:
The numeric guardrail operates on digit-based tokens (integers, floats, currency values, percentages).
Spelled-out words for numbers (e.g. 'nine hundred rupees', 'fifty thousand') are explicitly forbidden
at the LLM system prompt layer to ensure all financial figures remain machine-verifiable via exact regex tokens.
"""

import re
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal

# Regex to extract numeric tokens from natural language text (integers, floats, currency values)
NUMERIC_TOKEN_REGEX = re.compile(r"\b(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\b")


def extract_numeric_tokens(text: str) -> set[str]:
    """Extracts normalized numeric strings from text."""
    if not text:
        return set()
    matches = NUMERIC_TOKEN_REGEX.findall(text)
    normalized = set()
    for m in matches:
        clean = m.replace(",", "").strip()
        if clean:
            # Strip trailing zeros if decimal e.g. 900.00 -> 900
            try:
                dec = Decimal(clean)
                normalized.add(str(dec))
                normalized.add(f"{dec:.2f}")
                normalized.add(str(int(dec)))
            except Exception:
                normalized.add(clean)
    return normalized


def extract_record_numbers(log: ReconciliationLog) -> set[str]:
    """Extracts all valid numbers from the source ReconciliationLog and linked entities."""
    allowed: set[str] = set()

    def add_num(val: Any) -> None:
        if val is None:
            return
        if isinstance(val, (Decimal, int, float)):
            dec = to_decimal(val)
            allowed.add(str(dec))
            allowed.add(f"{dec:.2f}")
            allowed.add(f"{dec:.1f}")
            allowed.add(str(int(dec)))
        elif isinstance(val, str):
            allowed.update(extract_numeric_tokens(val))

    # Delta amount & confidence score
    add_num(getattr(log, "delta_amount", None))
    add_num(getattr(log, "confidence_score", None))

    # Bank transaction fields
    bank_tx = getattr(log, "bank_transaction", None)
    if bank_tx:
        add_num(getattr(bank_tx, "amount", None))
        add_num(getattr(bank_tx, "utr", None))
        add_num(getattr(bank_tx, "description", None))
        date_obj = getattr(bank_tx, "date", None)
        if date_obj:
            add_num(getattr(date_obj, "day", None))
            add_num(getattr(date_obj, "month", None))
            add_num(getattr(date_obj, "year", None))
            if hasattr(date_obj, "hour"):
                add_num(date_obj.hour)
                add_num(f"{date_obj.hour:02d}")
            if hasattr(date_obj, "minute"):
                add_num(date_obj.minute)
                add_num(f"{date_obj.minute:02d}")

    # Razorpay settlement fields
    rzp_setl = getattr(log, "rzp_settlement", None)
    if rzp_setl:
        add_num(getattr(rzp_setl, "amount", None))
        add_num(getattr(rzp_setl, "gross_amount", None))
        add_num(getattr(rzp_setl, "fees", None))
        add_num(getattr(rzp_setl, "tax", None))
        add_num(getattr(rzp_setl, "utr", None))
        add_num(getattr(rzp_setl, "settlement_id", None))
        setl_date = getattr(rzp_setl, "settlement_created_at", None)
        if setl_date:
            add_num(getattr(setl_date, "day", None))
            add_num(getattr(setl_date, "month", None))
            add_num(getattr(setl_date, "year", None))
            if hasattr(setl_date, "hour"):
                add_num(setl_date.hour)
                add_num(f"{setl_date.hour:02d}")
            if hasattr(setl_date, "minute"):
                add_num(setl_date.minute)
                add_num(f"{setl_date.minute:02d}")
        raw_payload = getattr(rzp_setl, "raw_payload", None)
        if raw_payload and isinstance(raw_payload, dict):
            for k, v in raw_payload.items():
                add_num(v)

    # Diagnostic note fields
    diag_note = getattr(log, "diagnostic_note", None)
    if diag_note:
        allowed.update(extract_numeric_tokens(diag_note))

    # Explicit statutory rate and fee percentage whitelist
    diag_type = getattr(log, "diagnostic_type", None)
    if diag_type in ("FEE_DEDUCTION", "TDS_194O_DEDUCTION", "BATCHED_SETTLEMENT", "EXACT_MATCH"):
        gst_pct = settings.GST_RATE * Decimal(100) if isinstance(settings.GST_RATE, Decimal) else Decimal(str(settings.GST_RATE)) * Decimal(100)
        mdr_pct = settings.DEFAULT_MDR_RATE * Decimal(100) if isinstance(settings.DEFAULT_MDR_RATE, Decimal) else Decimal(str(settings.DEFAULT_MDR_RATE)) * Decimal(100)
        tds_pct = settings.TDS_194O_RATE * Decimal(100) if isinstance(settings.TDS_194O_RATE, Decimal) else Decimal(str(settings.TDS_194O_RATE)) * Decimal(100)
        add_num(gst_pct)
        add_num(mdr_pct)
        add_num(tds_pct)

    return allowed


def validate_qa_narration(
    generated_text: str,
    source_log: ReconciliationLog,
) -> tuple[bool, list[str]]:
    """Validates that all numbers in the LLM narration exist in the source record.

    Returns (is_valid, list_of_invented_tokens).
    """
    text_numbers = extract_numeric_tokens(generated_text)
    allowed_numbers = extract_record_numbers(source_log)

    invented = [num for num in text_numbers if num not in allowed_numbers]
    is_valid = len(invented) == 0
    return is_valid, invented
