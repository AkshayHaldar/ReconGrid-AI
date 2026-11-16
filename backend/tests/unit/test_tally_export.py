"""Tally Prime XML export: voucher shape and the Dr == Cr invariant."""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.tally_export import (
    CLEARING_LEDGER,
    CUSTOMER_REFUNDS_LEDGER,
    GATEWAY_CHARGES_LEDGER,
    INPUT_GST_LEDGER,
    TDS_RECEIVABLE_LEDGER,
    build_tally_xml,
)


def make_log(*, bank=Decimal("49100.00"), gross=Decimal("50000.00"), fee=Decimal("762.71"),
             tax=Decimal("137.29"), status="MATCHED", setl="setl_abc123", with_rzp=True):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    bank_tx = BankTransaction(id="b-" + setl, amount=bank, date=now, direction="CREDIT",
                              utr="ICIC009283", description="CMS", row_hash="h" + setl)
    rzp = RazorpaySettlement(id="r-" + setl, settlement_id=setl, amount=bank, gross_amount=gross,
                             fees=fee, tax=tax, utr="ICIC009283", settlement_created_at=now)
    return ReconciliationLog(
        id="l-" + setl, bank_tx_id=bank_tx.id, rzp_settlement_id=rzp.id, match_status=status,
        match_tier="TIER_3", delta_amount=Decimal("0.00"), diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="n", bank_transaction=bank_tx, rzp_settlement=rzp if with_rzp else None,
        matched_at=now,
    )


def amounts(voucher):
    return [(e.findtext("LEDGERNAME"), Decimal(e.findtext("AMOUNT")), e.findtext("ISDEEMEDPOSITIVE"))
            for e in voucher.findall("ALLLEDGERENTRIES.LIST")]


def test_matched_settlement_becomes_balanced_journal_voucher():
    export = build_tally_xml([make_log()])
    root = ET.fromstring(export.xml)
    voucher = root.find(".//VOUCHER")
    assert voucher.get("VCHTYPE") == "Journal" and voucher.get("ACTION") == "Create"
    assert voucher.findtext("DATE") == "20260814"
    entries = amounts(voucher)
    assert [e[0] for e in entries] == ["Bank Account", GATEWAY_CHARGES_LEDGER, INPUT_GST_LEDGER, CLEARING_LEDGER]
    # Tally: debits negative + ISDEEMEDPOSITIVE Yes, credits positive; the lot sums to zero.
    assert sum(a for _, a, _ in entries) == Decimal("0.00")
    assert entries[-1] == (CLEARING_LEDGER, Decimal("50000.00"), "No")
    assert export.voucher_count == 1 and export.skipped == []


def test_envelope_structure_and_udf_namespace():
    root = ET.fromstring(build_tally_xml([make_log()]).xml)
    assert root.tag == "ENVELOPE"
    assert root.findtext("HEADER/TALLYREQUEST") == "Import Data"
    assert root.findtext("BODY/IMPORTDATA/REQUESTDESC/REPORTNAME") == "Vouchers"
    assert 'xmlns:UDF="TallyUDF"' in build_tally_xml([make_log()]).xml


def test_every_voucher_balances_across_a_batch():
    logs = [make_log(setl=f"setl_{i}", gross=Decimal(g), bank=Decimal(g) - Decimal("118.00"),
                     fee=Decimal("100.00"), tax=Decimal("18.00"))
            for i, g in enumerate(["1000.00", "2500.50", "99999.99"])]
    root = ET.fromstring(build_tally_xml(logs).xml)
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 3
    assert all(sum(a for _, a, _ in amounts(v)) == Decimal("0.00") for v in vouchers)


def test_unbalanced_record_is_skipped_and_reported_not_written():
    bad = make_log(setl="setl_bad", bank=Decimal("49000.00"))  # short by 100.00
    export = build_tally_xml([bad, make_log(setl="setl_ok")])
    assert export.voucher_count == 1
    assert export.skipped == ["setl_bad"]
    assert "setl_bad" not in export.xml


def test_zero_fee_and_tax_lines_are_omitted():
    export = build_tally_xml([make_log(bank=Decimal("50000.00"), fee=Decimal("0.00"), tax=Decimal("0.00"))])
    names = [e[0] for e in amounts(ET.fromstring(export.xml).find(".//VOUCHER"))]
    assert names == ["Bank Account", CLEARING_LEDGER]


def test_only_matched_records_with_both_sides_are_exported():
    logs = [make_log(setl="s1", status="SUGGESTED"), make_log(setl="s2", with_rzp=False)]
    export = build_tally_xml(logs)
    assert export.voucher_count == 0 and ET.fromstring(export.xml).find(".//VOUCHER") is None


def test_special_characters_are_escaped():
    log = make_log(setl="setl_a&b<c>")
    assert ET.fromstring(build_tally_xml([log]).xml).findtext(".//VOUCHERNUMBER") == "setl_a&b<c>"


def test_tds_deduction_adds_receivable_debit():
    log = make_log(bank=Decimal("48600.00"))
    log.diagnostic_type = "TDS_194O_DEDUCTION"
    entries = amounts(ET.fromstring(build_tally_xml([log]).xml).find(".//VOUCHER"))
    assert (TDS_RECEIVABLE_LEDGER, Decimal("-500.00"), "Yes") in entries
    assert sum(amount for _, amount, _ in entries) == Decimal("0.00")


def test_refund_adjustment_adds_suspense_debit_only_when_netted():
    log = make_log(bank=Decimal("47100.00"))
    log.rzp_settlement.raw_payload = {"refund_total": "2000.00"}
    log.diagnostic_type = "REFUND_ADJUSTED"
    entries = amounts(ET.fromstring(build_tally_xml([log]).xml).find(".//VOUCHER"))
    assert (CUSTOMER_REFUNDS_LEDGER, Decimal("-2000.00"), "Yes") in entries
    assert sum(amount for _, amount, _ in entries) == Decimal("0.00")

    log.diagnostic_type = "FEE_DEDUCTION"
    assert build_tally_xml([log]).skipped == [log.rzp_settlement.settlement_id]


def test_compound_tds_and_refund_settlement_balances():
    log = make_log(bank=Decimal("46600.00"))
    log.diagnostic_type = "REFUND_ADJUSTED"
    log.diagnostic_note = "Refund clawback + 1% TDS + gateway fee"
    log.rzp_settlement.raw_payload = {"refund_total": "2000.00"}
    export = build_tally_xml([log])
    entries = amounts(ET.fromstring(export.xml).find(".//VOUCHER"))
    assert [name for name, _, _ in entries] == [
        "Bank Account", GATEWAY_CHARGES_LEDGER, INPUT_GST_LEDGER,
        TDS_RECEIVABLE_LEDGER, CUSTOMER_REFUNDS_LEDGER, CLEARING_LEDGER,
    ]
    assert sum(amount for _, amount, _ in entries) == Decimal("0.00")
    assert export.voucher_count == 1 and export.skipped == []
