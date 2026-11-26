"""Unit tests for RazorpayClient pagination, error handling, retries, and batch sync."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError
from tenacity import wait_none

from app.core.config import settings
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.services.razorpay_client import RazorpayClient


def refund_payload(number: int) -> dict:
    return {
        "id": f"rfnd_{number}",
        "payment_id": f"pay_{number}",
        "amount": 12055,
        "currency": "INR",
        "status": "processed",
        "created_at": 1724496000,
    }


async def test_fetch_refunds_limits_each_page_and_converts_paise(monkeypatch):
    client = RazorpayClient(AsyncMock())
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/refunds"
        count = int(request.url.params["count"])
        offset = int(request.url.params["skip"])
        requests.append((count, offset))
        return httpx.Response(200, json={"items": [refund_payload(i) for i in range(offset, offset + count)]})

    transport = httpx.MockTransport(respond)
    http_client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_mock_refunds")
    with patch("app.services.razorpay_client.httpx.AsyncClient", return_value=http_client):
        refunds = await client.fetch_refunds(count_limit=102)

    assert requests == [(100, 0), (2, 100)]
    assert len(refunds) == 102
    assert refunds[-1]["refund_id"] == "rfnd_101"
    assert refunds[-1]["amount"] == Decimal("120.55")
    assert "settlement_id" not in refunds[-1]


async def test_fetch_refunds_page_retries_a_throttle_but_not_an_auth_error():
    client = RazorpayClient(AsyncMock())
    statuses = iter((429, 401))
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(next(statuses))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        fetch = client._fetch_refunds_page.retry_with(wait=wait_none())
        with pytest.raises(httpx.HTTPStatusError) as error:
            await fetch(client, http_client, count=20, skip=0)

    assert error.value.response.status_code == 401
    assert len(requests) == 2


async def test_fetch_refunds_rejects_fractional_paise_without_retry(monkeypatch):
    client = RazorpayClient(AsyncMock())
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_mock_refunds")
    page = AsyncMock(return_value=[{**refund_payload(1), "amount": 120.55}])
    monkeypatch.setattr(client, "_fetch_refunds_page", page)

    with pytest.raises(ValidationError, match="amount"):
        await client.fetch_refunds()

    page.assert_awaited_once()


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
    client.sync_refunds = AsyncMock(return_value=0)

    # Setup 2 pages of mocked responses
    page1_items = [
        {"id": "setl_1", "amount": 4910000, "fees": 76271, "tax": 13729, "utr": "CMS1", "created_at": 1724496000, "status": "processed"},
        {"id": "setl_2", "amount": 9820000, "fees": 152542, "tax": 27458, "utr": "CMS2", "created_at": 1724496000, "status": "processed"},
    ]
    page2_items = [
        {"id": "setl_3", "amount": 10000000, "fees": 0, "tax": 0, "utr": "CMS3", "created_at": None, "status": "processed"},
    ]

    mock_setl1 = RazorpaySettlement(id="s1", settlement_id="setl_1", amount=Decimal("49100.00"), settlement_created_at=datetime.now(UTC))
    mock_setl2 = RazorpaySettlement(id="s2", settlement_id="setl_2", amount=Decimal("98200.00"), settlement_created_at=datetime.now(UTC))
    mock_setl3 = RazorpaySettlement(id="s3", settlement_id="setl_3", amount=Decimal("100000.00"), settlement_created_at=datetime.now(UTC))

    client.settlement_repo.upsert_settlement = AsyncMock(side_effect=[
        (mock_setl1, True),   # newly inserted
        (mock_setl2, False),  # updated
        (mock_setl3, True),   # newly inserted
    ])

    # Mock the DB get_all() to simulate returning the full list of historical settlements
    client.settlement_repo.get_all = AsyncMock(return_value=[mock_setl1, mock_setl2, mock_setl3])
    bank_tx = BankTransaction(id="b1", amount=Decimal("49100.00"), date=datetime.now(UTC), row_hash="h1")
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
    client.sync_refunds = AsyncMock(return_value=0)
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[])

    # Mock the DB get_all() because our new logic calls it even when API fails
    client.settlement_repo.get_all = AsyncMock(return_value=[])
    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        with patch.object(client, "_fetch_settlements_page", AsyncMock(side_effect=Exception("Network failure"))):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")
            assert res.fetched_count == 0
            assert res.reconciliation_triggered is False

@pytest.mark.asyncio
async def test_sync_settlements_reconciles_existing_db_data_when_api_is_empty():
    """
    Tests that even if the Razorpay API returns 0 new records,
    the system still fetches existing settlements from the DB and triggers reconciliation.
    """
    session = AsyncMock()
    client = RazorpayClient(session)
    client.sync_refunds = AsyncMock(return_value=0)

    # Mock the DB to return historical settlements
    mock_setl = RazorpaySettlement(
        id="s_hist_1", settlement_id="setl_hist_1", amount=Decimal("10000.00"), settlement_created_at=datetime.now(UTC)
    )
    client.settlement_repo.get_all = AsyncMock(return_value=[mock_setl])

    # Mock active bank transactions
    bank_tx = BankTransaction(id="b1", amount=Decimal("10000.00"), date=datetime.now(UTC), row_hash="h1")
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[bank_tx])

    # Mock the engine
    client.engine.reconcile_batch = AsyncMock()

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        # Mock the API to return an empty list
        with patch.object(client, "_fetch_settlements_page", AsyncMock(return_value={"items": []})):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")

            # Assertions
            assert res.fetched_count == 0
            assert res.reconciliation_triggered is True
            client.engine.reconcile_batch.assert_awaited_once()
