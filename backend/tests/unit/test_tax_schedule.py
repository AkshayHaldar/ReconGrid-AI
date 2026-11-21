"""Tax schedule: TDS 194-O totals, GST split and deviation flags."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.tax_schedule import build_tax_schedule


def make_log(setl_id, gross, fee, tax, net, payload=None):
    bank = BankTransaction(
        id="b-" + setl_id,
        amount=net,
        date=datetime(2026, 8, 14, tzinfo=UTC),
        direction="CREDIT",
        utr="UTR" + setl_id,
        description="CMS",
    )
    setl = RazorpaySettlement(
        id="s-" + setl_id,
        settlement_id=setl_id,
        amount=net,
        gross_amount=gross,
        fees=fee,
        tax=tax,
        raw_payload=payload,
    )
    return ReconciliationLog(id="l-" + setl_id, bank_transaction=bank, rzp_settlement=setl)


def test_totals_and_cgst_sgst_split():
    # 100000 gross, 2000 fee, 360 GST, 1000 TDS -> 96640 net
    logs = [make_log("setl_1", Decimal("100000.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("96640.00"))]
    schedule = build_tax_schedule("b1", logs)
    assert schedule.gross_volume == Decimal("100000.00")
    assert schedule.expected_tds == Decimal("1000.00")
    assert schedule.actual_tds == Decimal("1000.00")
    assert schedule.mdr_fees == Decimal("2000.00")
    assert schedule.gst_on_fees == Decimal("360.00")
    assert (schedule.cgst, schedule.sgst, schedule.igst) == (Decimal("180.00"), Decimal("180.00"), Decimal("0.00"))
    assert schedule.tds_deviations == []


def test_igst_when_inter_state():
    logs = [make_log("setl_1", Decimal("100000.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("96640.00"))]
    schedule = build_tax_schedule("b1", logs, intra_state=False)
    assert schedule.igst == Decimal("360.00")
    assert schedule.cgst == schedule.sgst == Decimal("0.00")


def test_odd_paise_gst_split_sums_exactly():
    logs = [make_log("setl_1", Decimal("5000.00"), Decimal("100.00"), Decimal("18.01"), Decimal("4831.99"))]
    schedule = build_tax_schedule("b1", logs)
    assert schedule.cgst + schedule.sgst == Decimal("18.01")


def test_reported_tds_off_by_more_than_a_rupee_is_flagged():
    logs = [
        make_log(
            "setl_bad",
            Decimal("100000.00"),
            Decimal("2000.00"),
            Decimal("360.00"),
            Decimal("96640.00"),
            payload={"tds": "1500.00"},
        ),
        make_log(
            "setl_ok",
            Decimal("100000.00"),
            Decimal("2000.00"),
            Decimal("360.00"),
            Decimal("96640.00"),
            payload={"tds": "1000.50"},
        ),
    ]
    schedule = build_tax_schedule("b1", logs)
    assert [d.settlement_id for d in schedule.tds_deviations] == ["setl_bad"]
    assert schedule.tds_deviations[0].difference == Decimal("500.00")


def test_same_settlement_counted_once():
    log = make_log("setl_1", Decimal("100000.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("96640.00"))
    schedule = build_tax_schedule("b1", [log, log])
    assert schedule.settlement_count == 1
    assert schedule.gross_volume == Decimal("100000.00")


def test_logs_without_settlement_are_ignored():
    schedule = build_tax_schedule("b1", [ReconciliationLog(id="l-x")])
    assert schedule.settlement_count == 0
    assert schedule.gross_volume == Decimal("0.00")


def test_zero_actual_tds_is_flagged_as_missed_deduction():
    # Gross is known and the net credited leaves no room for any TDS: expected Rs 1000, actual Rs 0.
    logs = [make_log("setl_miss", Decimal("100000.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("97640.00"))]
    schedule = build_tax_schedule("b1", logs)
    assert schedule.actual_tds == Decimal("0.00")
    assert [d.settlement_id for d in schedule.tds_deviations] == ["setl_miss"]
    assert schedule.tds_deviations[0].difference == Decimal("-1000.00")


def test_gateway_reported_zero_tds_is_flagged():
    logs = [
        make_log(
            "setl_zero",
            Decimal("100000.00"),
            Decimal("2000.00"),
            Decimal("360.00"),
            Decimal("96640.00"),
            payload={"tds": "0"},
        )
    ]
    schedule = build_tax_schedule("b1", logs)
    assert [d.settlement_id for d in schedule.tds_deviations] == ["setl_zero"]


def test_inferred_gross_without_reported_tds_is_not_flagged():
    # gross_amount missing: gross is rebuilt from net + fees + tax so TDS can't be recovered.
    logs = [make_log("setl_nogross", Decimal("0.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("96640.00"))]
    schedule = build_tax_schedule("b1", logs)
    assert schedule.tds_deviations == []
    assert schedule.tds_unverifiable == 1


def test_csv_rows_include_deviations_and_attestation():
    from app.services.tax_schedule import tax_schedule_csv_rows

    logs = [make_log("setl_miss", Decimal("100000.00"), Decimal("2000.00"), Decimal("360.00"), Decimal("97640.00"))]
    rows = tax_schedule_csv_rows(build_tax_schedule("b1", logs))
    flat = [cell for row in rows for cell in row]
    assert "setl_miss" in flat
    assert "UDIN:" in flat
    assert "Signature:" in flat
