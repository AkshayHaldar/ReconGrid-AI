"""Statutory tax schedule: Section 194-O TDS and GST input tax credit on gateway fees.

Aggregates per-settlement figures for a batch so a CA can tie them to Form 26AS
(TDS) and GSTR-2B / GSTR-3B (input tax credit). All math is Decimal.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import settings
from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal

PAISE = Decimal("0.01")
TDS_DEVIATION_TOLERANCE = Decimal("1.00")
ZERO = Decimal("0.00")


@dataclass
class TdsDeviation:
    settlement_id: str
    gross_amount: Decimal
    expected_tds: Decimal
    actual_tds: Decimal
    difference: Decimal
    note: str


@dataclass
class TaxSchedule:
    batch_id: str
    settlement_count: int = 0
    gross_volume: Decimal = ZERO
    expected_tds: Decimal = ZERO
    actual_tds: Decimal = ZERO
    mdr_fees: Decimal = ZERO
    gst_on_fees: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    tds_deviations: list[TdsDeviation] = field(default_factory=list)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def build_tax_schedule(batch_id: str, logs: Iterable[ReconciliationLog], *, intra_state: bool = True) -> TaxSchedule:
    """Sum TDS and GST across the distinct settlements referenced by `logs`.

    Actual TDS is read from the settlement payload (`tds` or `tds_deducted`) when the
    gateway reports it, otherwise it is the residual of gross - net - fees - GST - refunds.
    A settlement is flagged when actual TDS is present and differs from the statutory
    rate by more than Rs 1.00. With `intra_state` the GST is split into CGST and SGST,
    otherwise it is reported as IGST.
    """
    schedule = TaxSchedule(batch_id=batch_id)
    seen: set[str] = set()

    for log in logs:
        setl = log.rzp_settlement
        if setl is None or setl.id in seen:
            continue
        seen.add(setl.id)

        net = to_decimal(setl.amount)
        fees = to_decimal(setl.fees)
        tax = to_decimal(setl.tax)
        gross = to_decimal(setl.gross_amount)
        payload = setl.raw_payload or {}
        refunds = to_decimal(payload.get("refund_total", ZERO))
        if gross <= ZERO:
            gross = net + fees + tax

        expected = _quantize(gross * settings.TDS_194O_RATE) if gross > ZERO else ZERO
        reported = payload.get("tds", payload.get("tds_deducted"))
        if reported is not None:
            actual = to_decimal(reported)
        else:
            actual = max(gross - net - fees - tax - refunds, ZERO)

        schedule.settlement_count += 1
        schedule.gross_volume += gross
        schedule.expected_tds += expected
        schedule.actual_tds += actual
        schedule.mdr_fees += fees
        schedule.gst_on_fees += tax

        if (reported is not None or actual > ZERO) and abs(actual - expected) > TDS_DEVIATION_TOLERANCE:
            schedule.tds_deviations.append(
                TdsDeviation(
                    settlement_id=setl.settlement_id,
                    gross_amount=gross,
                    expected_tds=expected,
                    actual_tds=actual,
                    difference=actual - expected,
                    note=f"TDS deducted differs from {settings.TDS_194O_RATE * 100:.2f}% of gross by more than Rs 1.00.",
                )
            )

    if intra_state:
        schedule.cgst = _quantize(schedule.gst_on_fees / 2)
        schedule.sgst = schedule.gst_on_fees - schedule.cgst
    else:
        schedule.igst = schedule.gst_on_fees
    return schedule
