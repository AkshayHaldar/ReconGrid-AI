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
    # Settlements with no reported TDS and no reported gross: TDS cannot be derived, so none is flagged.
    tds_unverifiable: int = 0


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def build_tax_schedule(batch_id: str, logs: Iterable[ReconciliationLog], *, intra_state: bool = True) -> TaxSchedule:
    """Sum TDS and GST across the distinct settlements referenced by `logs`.

    Actual TDS is read from the settlement payload (`tds` or `tds_deducted`) when the
    gateway reports it, otherwise it is the residual of gross - net - fees - GST - refunds.
    A settlement is flagged when actual TDS differs from the statutory rate by more than
    Rs 1.00, including when nothing was deducted at all (a missed 194-O deduction). That check
    is skipped when neither TDS nor gross was reported, since TDS cannot be recovered then. With `intra_state` the GST is split into CGST and SGST,
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
        gross_reported = gross > ZERO
        if not gross_reported:
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

        # A real gross (or a gateway-reported TDS) makes zero TDS meaningful, so a missing 194-O
        # deduction is flagged. With an inferred gross the residual is always 0 and proves nothing.
        verifiable = reported is not None or gross_reported
        if not verifiable:
            schedule.tds_unverifiable += 1
        if verifiable and abs(actual - expected) > TDS_DEVIATION_TOLERANCE:
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


ATTESTATION_LINES = (
    "I have verified the above figures against Form 26AS and GSTR-2B / GSTR-3B.",
    "Chartered Accountant Name:",
    "Membership No.:",
    "UDIN:",
    "Signature:",
    "Date:",
)


def tax_schedule_csv_rows(schedule: TaxSchedule, sanitize=lambda v: v) -> list[list[str]]:
    """Rows for the CA-facing CSV: summary, TDS deviations and the attestation block."""
    rows: list[list[str]] = [
        ["Tax & Statutory Schedule", sanitize(schedule.batch_id)],
        [],
        ["Settlements", str(schedule.settlement_count)],
        ["Gross volume", f"{schedule.gross_volume:.2f}"],
        ["Expected TDS (194-O)", f"{schedule.expected_tds:.2f}"],
        ["Actual TDS", f"{schedule.actual_tds:.2f}"],
        ["Gateway MDR fees", f"{schedule.mdr_fees:.2f}"],
        ["GST on fees", f"{schedule.gst_on_fees:.2f}"],
        ["CGST", f"{schedule.cgst:.2f}"],
        ["SGST", f"{schedule.sgst:.2f}"],
        ["IGST", f"{schedule.igst:.2f}"],
        ["Settlements with TDS not verifiable", str(schedule.tds_unverifiable)],
        [],
        ["TDS deviations"],
        ["Settlement ID", "Gross", "Expected TDS", "Actual TDS", "Difference", "Note"],
    ]
    for d in schedule.tds_deviations:
        rows.append(
            [
                sanitize(d.settlement_id),
                f"{d.gross_amount:.2f}",
                f"{d.expected_tds:.2f}",
                f"{d.actual_tds:.2f}",
                f"{d.difference:.2f}",
                sanitize(d.note),
            ]
        )
    rows.append([])
    rows.append(["CA attestation"])
    rows.extend([line] for line in ATTESTATION_LINES)
    return rows
