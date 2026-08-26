"""Integration tests for Settlement Q&A Agent."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository


@pytest.mark.asyncio
async def test_qa_agent_deterministic_retrieval_and_not_found(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed test record via demo seed
        await client.post("/api/v1/demo/seed?count=15")

        # 1. Ask question about known order 4521 / UTR
        resp = await client.post(
            "/api/v1/qa/ask",
            json={"query": "Why did order #4521 have a fee deduction?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        ans = data["data"]["answer"]
        assert "Gateway" in ans or "FEE" in ans or "4521" in ans or "short" in ans
        assert data["data"]["source_record_id"] is not None

        # 2. Ask question about nonexistent record
        resp_nf = await client.post(
            "/api/v1/qa/ask",
            json={"query": "Why did order #9999999999 not settle?"},
        )
        assert resp_nf.status_code == 200
        data_nf = resp_nf.json()
        assert "No record found" in data_nf["data"]["answer"]
        assert data_nf["data"]["source_record_id"] is None
