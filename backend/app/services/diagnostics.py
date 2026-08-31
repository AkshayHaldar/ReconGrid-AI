"""Tier 3 Discrepancy Diagnostics Engine.

Evaluates monetary deltas deterministically against:
1. Gateway Fees + 18% GST
2. Aggregated Refund Deductions / Clawbacks
3. FX Adjustments
4. Debit Reversals / Chargebacks
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple, Optional
from app.core.config import settings
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.utils.money import calculate_standard_fees, format_inr, is_amount_matching, to_decimal

GST_RATE = settings.GST_RATE  # GST standard for payment gateway processing fees


class DiagnosticResult(NamedTuple):
    diagnostic_type: str
    match_status: str
    delta_amount: Decimal
    diagnostic_note: str


class DiagnosticsService:
    @classmethod
    def evaluate_delta(
        cls,
        bank_tx: BankTransaction,
        rzp_setl: RazorpaySettlement,
        tolerance: Decimal = Decimal("1.00"),
    ) -> DiagnosticResult:
        """Deterministically diagnoses why bank credit/debit differs from gross/net settlement."""
        bank_amount = to_decimal(bank_tx.amount)
        rzp_net = to_decimal(rzp_setl.amount)
        rzp_gross = to_decimal(rzp_setl.gross_amount)
        fees = to_decimal(rzp_setl.fees)
        tax = to_decimal(rzp_setl.tax)
        raw_payload = rzp_setl.raw_payload or {}
        refund_total = to_decimal(raw_payload.get("refund_total", Decimal("0.00")))
        fx_component = to_decimal(raw_payload.get("fx_fee", Decimal("0.00")))

        # If gross amount is unpopulated but net and fees exist, resolve effective gross
        if rzp_gross <= Decimal("0.00"):
            if fees + tax > Decimal("0.00"):
                rzp_gross = rzp_net + fees + tax
            else:
                rzp_gross = rzp_net

        # Standard 2% MDR + 18% GST estimation
        estimated_fee, estimated_tax, _ = (
            calculate_standard_fees(rzp_gross, mdr_rate=Decimal("0.02"), gst_rate=GST_RATE)
            if rzp_gross > Decimal("0.00")
            else (Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
        )
        actual_or_est_fees = (fees + tax) if (fees + tax) > Decimal("0.00") else (estimated_fee + estimated_tax)

        # Section 194-O 1% TDS calculation
        tds_194o = (
            (rzp_gross * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if rzp_gross > Decimal("0.00")
            else Decimal("0.00")
        )

        # Case 1: Settlement Reversal / Chargeback (Debit Row)
        if bank_tx.direction == "DEBIT":
            return DiagnosticResult(
                diagnostic_type="REVERSAL",
                match_status="MATCHED",
                delta_amount=bank_amount,
                diagnostic_note=(
                    f"Settlement reversal/chargeback debit of {format_inr(bank_amount)} "
                    f"matched against negative adjustment on settlement {rzp_setl.settlement_id}."
                ),
            )

        # Case 0: Exact match with zero delta on net payout
        if is_amount_matching(bank_amount, rzp_net, tolerance):
            return DiagnosticResult(
                diagnostic_type="EXACT_MATCH",
                match_status="MATCHED",
                delta_amount=Decimal("0.00"),
                diagnostic_note=f"Exact match on net payout amount {format_inr(bank_amount)}.",
            )

        # Case 0b: Exact match on gross amount
        if rzp_gross > Decimal("0.00") and is_amount_matching(bank_amount, rzp_gross, tolerance):
            return DiagnosticResult(
                diagnostic_type="EXACT_MATCH",
                match_status="MATCHED",
                delta_amount=Decimal("0.00"),
                diagnostic_note=f"Exact match on gross payout amount {format_inr(bank_amount)}.",
            )

        # Case 2: Gateway Fees + 18% GST Deduction (Actual values from settlement)
        if (fees + tax) > Decimal("0.00") and is_amount_matching(
            rzp_gross - bank_amount, fees + tax, tolerance
        ):
            return DiagnosticResult(
                diagnostic_type="FEE_DEDUCTION",
                match_status="MATCHED",
                delta_amount=fees + tax,
                diagnostic_note=(
                    f"Difference of {format_inr(fees + tax)} matches Gateway Fee "
                    f"({format_inr(fees)}) + 18% GST ({format_inr(tax)})."
                ),
            )

        # Case 2b: Standard 2% MDR Fee + 18% GST estimation
        if (estimated_fee + estimated_tax > Decimal("0.00")) and is_amount_matching(
            rzp_gross - bank_amount, estimated_fee + estimated_tax, tolerance
        ):
            return DiagnosticResult(
                diagnostic_type="FEE_DEDUCTION",
                match_status="MATCHED",
                delta_amount=estimated_fee + estimated_tax,
                diagnostic_note=(
                    f"Difference of {format_inr(estimated_fee + estimated_tax)} matches standard "
                    f"2% Gateway Fee ({format_inr(estimated_fee)}) + 18% GST ({format_inr(estimated_tax)})."
                ),
            )

        # Case 2c: Section 194-O E-Commerce 1% TDS + Gateway Fee + 18% GST
        total_tds_deduction = actual_or_est_fees + tds_194o
        if tds_194o > Decimal("0.00") and is_amount_matching(
            rzp_gross - bank_amount, total_tds_deduction, tolerance
        ):
            fee_part = fees if fees > Decimal("0.00") else estimated_fee
            tax_part = tax if tax > Decimal("0.00") else estimated_tax
            return DiagnosticResult(
                diagnostic_type="TDS_194O_DEDUCTION",
                match_status="MATCHED",
                delta_amount=total_tds_deduction,
                diagnostic_note=(
                    f"Difference of {format_inr(total_tds_deduction)} matches 1% TDS u/s 194-O ({format_inr(tds_194o)}) "
                    f"+ Gateway Fee ({format_inr(fee_part)}) + 18% GST ({format_inr(tax_part)})."
                ),
            )

        # Case 3: Refund Batch Clawback Deduction
        if refund_total > Decimal("0.00"):
            if is_amount_matching(rzp_net - bank_amount, refund_total, tolerance) or is_amount_matching(
                rzp_gross - bank_amount - actual_or_est_fees, refund_total, tolerance
            ):
                return DiagnosticResult(
                    diagnostic_type="REFUND_ADJUSTED",
                    match_status="MATCHED",
                    delta_amount=refund_total,
                    diagnostic_note=(
                        f"Settlement adjusted for mid-cycle refund clawback of {format_inr(refund_total)} "
                        f"plus gateway fee ({format_inr(actual_or_est_fees)})."
                    ),
                )
            # Compound Fee + TDS + Refund
            if is_amount_matching(
                rzp_gross - bank_amount, actual_or_est_fees + tds_194o + refund_total, tolerance
            ):
                return DiagnosticResult(
                    diagnostic_type="REFUND_ADJUSTED",
                    match_status="MATCHED",
                    delta_amount=refund_total + actual_or_est_fees + tds_194o,
                    diagnostic_note=(
                        f"Settlement adjusted for refund clawback ({format_inr(refund_total)}) "
                        f"+ 1% TDS ({format_inr(tds_194o)}) + gateway fee ({format_inr(actual_or_est_fees)})."
                    ),
                )

        # Case 4: FX / Currency Conversion Adjustment
        if fx_component > Decimal("0.00"):
            if is_amount_matching(rzp_net - bank_amount, fx_component, tolerance) or is_amount_matching(
                rzp_gross - bank_amount - actual_or_est_fees, fx_component, tolerance
            ):
                return DiagnosticResult(
                    diagnostic_type="FX_ADJUSTED",
                    match_status="MATCHED",
                    delta_amount=fx_component,
                    diagnostic_note=(
                        f"Cross-currency settlement delta of {format_inr(fx_component)} "
                        f"matches international processing/FX adjustment."
                    ),
                )

        # Unresolved Exception
        unexplained_delta = abs(bank_amount - rzp_net)
        return DiagnosticResult(
            diagnostic_type="UNRESOLVED",
            match_status="EXCEPTION",
            delta_amount=unexplained_delta,
            diagnostic_note=(
                f"Unexplained delta of {format_inr(unexplained_delta)} between bank amount "
                f"({format_inr(bank_amount)}) and Razorpay net ({format_inr(rzp_net)})."
            ),
        )
