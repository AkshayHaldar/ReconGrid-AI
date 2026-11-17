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
