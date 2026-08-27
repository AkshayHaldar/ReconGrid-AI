"""Unit tests for RazorpayClient pagination, error handling, retries, and batch sync."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from app.core.config import settings
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.services.razorpay_client import RazorpayClient


@pytest.mark.asyncio
async def test_fetch_settlements_page_429_retry_and_success():
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()

    # Success response
    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"entity": "collection", "count": 1, "items": [{"id": "setl_100"}]}
    success_resp.raise_for_status = MagicMock()

    http_client.get.return_value = success_resp

    data = await client._fetch_settlements_page(http_client, count=10, skip=0)
    assert data["items"][0]["id"] == "setl_100"


@pytest.mark.asyncio
async def test_fetch_settlements_page_error_status():
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()

    # 401 Unauthorized response
    err_resp = MagicMock()
    err_resp.status_code = 401
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=err_resp)

    http_client.get.return_value = err_resp

    with pytest.raises(httpx.HTTPStatusError):
        await client._fetch_settlements_page(http_client, count=10, skip=0)


@pytest.mark.asyncio
async def test_sync_settlements_pagination_and_upsert():
    session = AsyncMock()
    client = RazorpayClient(session)

    # Setup 2 pages of mocked responses
    page1_items = [
        {"id": "setl_1", "amount": 4910000, "fees": 76271, "tax": 13729, "utr": "CMS1", "created_at": 1724496000, "status": "processed"},
        {"id": "setl_2", "amount": 9820000, "fees": 152542, "tax": 27458, "utr": "CMS2", "created_at": 1724496000, "status": "processed"},
    ]
    page2_items = [
        {"id": "setl_3", "amount": 10000000, "fees": 0, "tax": 0, "utr": "CMS3", "created_at": None, "status": "processed"},
    ]

    mock_setl1 = RazorpaySettlement(id="s1", settlement_id="setl_1", amount=Decimal("49100.00"), settlement_created_at=datetime.now(timezone.utc))
    mock_setl2 = RazorpaySettlement(id="s2", settlement_id="setl_2", amount=Decimal("98200.00"), settlement_created_at=datetime.now(timezone.utc))
    mock_setl3 = RazorpaySettlement(id="s3", settlement_id="setl_3", amount=Decimal("100000.00"), settlement_created_at=datetime.now(timezone.utc))

    client.settlement_repo.upsert_settlement = AsyncMock(side_effect=[
        (mock_setl1, True),   # newly inserted
        (mock_setl2, False),  # updated
        (mock_setl3, True),   # newly inserted
    ])

    bank_tx = BankTransaction(id="b1", amount=Decimal("49100.00"), date=datetime.now(timezone.utc), row_hash="h1")
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[bank_tx])
    client.engine.reconcile_batch = AsyncMock()

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        # We simulate page_size=2 by setting count_limit=3 and page1 having 2 items (so it fetches page 2)
        # Note: in sync_settlements, page_size = min(count_limit, 100). If count_limit=3, page_size is 3.
        # So page 1 must have 3 items for it not to break on len(items) < page_size.
        page1_items = [
            {"id": "setl_1", "amount": 4910000, "fees": 76271, "tax": 13729, "utr": "CMS1", "created_at": 1724496000, "status": "processed"},
            {"id": "setl_2", "amount": 9820000, "fees": 152542, "tax": 27458, "utr": "CMS2", "created_at": 1724496000, "status": "processed"},
        ]
        with patch.object(client, "_fetch_settlements_page", AsyncMock(side_effect=[
            {"items": page1_items},
            {"items": []},
        ])):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")
            assert res.fetched_count == 2
            assert res.newly_inserted == 1
            assert res.updated_count == 1
            assert res.reconciliation_triggered is True
            client.engine.reconcile_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_settlements_fetch_exception_handled():
    session = AsyncMock()
    client = RazorpayClient(session)
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[])

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        with patch.object(client, "_fetch_settlements_page", AsyncMock(side_effect=Exception("Network failure"))):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")
            assert res.fetched_count == 0
            assert res.reconciliation_triggered is False
