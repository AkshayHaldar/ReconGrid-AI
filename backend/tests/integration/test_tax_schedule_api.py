"""GET /reconciliation/{batch}/tax-schedule returns the batch tax totals."""

from datetime import UTC, datetime
from decimal import Decimal

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


async def test_tax_schedule_endpoint(db_session):
    bank = BankTransaction(
        batch_id="tax-b",
        row_hash="tax-row",
        date=datetime(2026, 1, 1, tzinfo=UTC),
        amount=Decimal("96640.00"),
        direction="CREDIT",
        description="CMS",
        utr="UTR1",
    )
    settlement = RazorpaySettlement(
        settlement_id="setl_tax",
        amount=Decimal("96640.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("2000.00"),
        tax=Decimal("360.00"),
    )
    db_session.add(
        ReconciliationLog(
            batch_id="tax-b",
            bank_transaction=bank,
            rzp_settlement=settlement,
            match_status="MATCHED",
            match_tier="TIER_3",
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reconciliation/tax-b/tax-schedule")
    assert response.status_code == 200
    data = response.json()["data"]
    assert Decimal(data["gross_volume"]) == Decimal("100000.00")
    assert Decimal(data["actual_tds"]) == Decimal("1000.00")
    assert Decimal(data["cgst"]) == Decimal("180.00")
    assert Decimal(data["sgst"]) == Decimal("180.00")
    assert data["tds_deviations"] == []


async def test_tax_schedule_covers_batches_beyond_ten_thousand_rows_cap(db_session, monkeypatch):
    """Totals must come from every page, not a single capped fetch."""
    from app.api.v1 import reconciliation as module
    from app.repositories.reconciliation_repo import ReconciliationRepository

    for i in range(5):
        db_session.add(
            ReconciliationLog(
                batch_id="tax-many",
                bank_transaction=BankTransaction(
                    batch_id="tax-many",
                    row_hash=f"row-{i}",
                    date=datetime(2026, 1, 1 + i, tzinfo=UTC),
                    amount=Decimal("96640.00"),
                    direction="CREDIT",
                    description="CMS",
                    utr=f"UTRM{i}",
                ),
                rzp_settlement=RazorpaySettlement(
                    settlement_id=f"setl_many_{i}",
                    amount=Decimal("96640.00"),
                    gross_amount=Decimal("100000.00"),
                    fees=Decimal("2000.00"),
                    tax=Decimal("360.00"),
                ),
                match_status="MATCHED",
                match_tier="TIER_3",
            )
        )
    await db_session.commit()

    logs = await module._all_active_logs(ReconciliationRepository(db_session), "tax-many", page_size=2)
    assert len(logs) == 5


async def test_tax_schedule_export_has_attestation_block(db_session):
    bank = BankTransaction(
        batch_id="tax-x",
        row_hash="tax-x-row",
        date=datetime(2026, 1, 1, tzinfo=UTC),
        amount=Decimal("97640.00"),
        direction="CREDIT",
        description="CMS",
        utr="UTRX",
    )
    settlement = RazorpaySettlement(
        settlement_id="setl_x",
        amount=Decimal("97640.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("2000.00"),
        tax=Decimal("360.00"),
    )
    db_session.add(
        ReconciliationLog(
            batch_id="tax-x",
            bank_transaction=bank,
            rzp_settlement=settlement,
            match_status="MATCHED",
            match_tier="TIER_3",
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reconciliation/tax-x/tax-schedule/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "setl_x" in body  # zero-TDS deviation row
    assert "UDIN:" in body
    assert "Signature:" in body
