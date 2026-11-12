"""Tally Prime XML export: voucher shape and the Dr == Cr invariant."""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.tally_export import (
    CLEARING_LEDGER,
    GATEWAY_CHARGES_LEDGER,
    INPUT_GST_LEDGER,
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
