"""Unit and API tests for RazorpayClient pagination, error handling, retries, and batch sync."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from tenacity import wait_none

from app.core.config import settings
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.services.razorpay_client import (
    RazorpayClient,
    RazorpayFetchError,
    RazorpayFetchExhausted,
)


def _mock_status_response(status_code: int, message: str = "error") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    req = httpx.Request("GET", "https://api.razorpay.com/v1/settlements")
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(message, request=req, response=resp)
    return resp


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

    rate_limited_resp = _mock_status_response(429, "429 Too Many Requests")
    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"entity": "collection", "count": 1, "items": [{"id": "setl_100"}]}
    success_resp.raise_for_status = MagicMock()

    http_client.get.side_effect = [rate_limited_resp, success_resp]

    with patch("asyncio.sleep", new=AsyncMock()):
        data = await client._fetch_settlements_page(http_client, count=10, skip=0)
    assert data["items"][0]["id"] == "setl_100"
    assert http_client.get.await_count == 2


@pytest.mark.asyncio
async def test_fetch_settlements_page_5xx_retries_and_succeeds():
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()

    err_503 = _mock_status_response(503, "503 Service Unavailable")
    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"entity": "collection", "count": 1, "items": [{"id": "setl_200"}]}
    success_resp.raise_for_status = MagicMock()

    http_client.get.side_effect = [err_503, err_503, success_resp]

    with patch("asyncio.sleep", new=AsyncMock()):
        data = await client._fetch_settlements_page(http_client, count=10, skip=0)
    assert data["items"][0]["id"] == "setl_200"
    assert http_client.get.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_fetch_settlements_page_non_retryable_4xx_fails_immediately(status_code: int):
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()
    http_client.get.return_value = _mock_status_response(status_code, f"{status_code} Client Error")

    with pytest.raises(RazorpayFetchError) as exc_info:
        await client._fetch_settlements_page(http_client, count=10, skip=0)

    assert not isinstance(exc_info.value, RazorpayFetchExhausted)
    assert exc_info.value.status_code == status_code
    assert http_client.get.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 502, 503])
async def test_fetch_settlements_page_exhausts_retries_on_retryable_http_errors(status_code: int):
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()
    http_client.get.return_value = _mock_status_response(status_code, f"{status_code} Retryable Error")

    with (
        patch.object(settings, "RAZORPAY_FETCH_MAX_RETRIES", 3),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(RazorpayFetchExhausted) as exc_info:
            await client._fetch_settlements_page(http_client, count=10, skip=0)

    assert exc_info.value.status_code == status_code
    assert http_client.get.await_count == 3


@pytest.mark.asyncio
async def test_fetch_settlements_page_exhausts_retries_on_request_error():
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()
    req = httpx.Request("GET", "https://api.razorpay.com/v1/settlements")
    http_client.get.side_effect = httpx.ConnectTimeout("timed out", request=req)

    with (
        patch.object(settings, "RAZORPAY_FETCH_MAX_RETRIES", 3),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(RazorpayFetchExhausted) as exc_info:
            await client._fetch_settlements_page(http_client, count=10, skip=0)

    assert exc_info.value.code == "RAZORPAY_NETWORK_ERROR"
    assert http_client.get.await_count == 3


@pytest.mark.asyncio
async def test_sync_settlements_pagination_and_upsert():
    session = AsyncMock()
    client = RazorpayClient(session)
    client.sync_refunds = AsyncMock(return_value=0)

    page1_items = [
        {
            "id": "setl_1",
            "amount": 4910000,
            "fees": 76271,
            "tax": 13729,
            "utr": "CMS1",
            "created_at": 1724496000,
            "status": "processed",
        },
        {
            "id": "setl_2",
            "amount": 9820000,
            "fees": 152542,
            "tax": 27458,
            "utr": "CMS2",
            "created_at": 1724496000,
            "status": "processed",
        },
    ]

    mock_setl1 = RazorpaySettlement(
        id="s1", settlement_id="setl_1", amount=Decimal("49100.00"), settlement_created_at=datetime.now(UTC)
    )
    mock_setl2 = RazorpaySettlement(
        id="s2", settlement_id="setl_2", amount=Decimal("98200.00"), settlement_created_at=datetime.now(UTC)
    )

    client.settlement_repo.upsert_settlement = AsyncMock(
        side_effect=[
            (mock_setl1, True),
            (mock_setl2, False),
        ]
    )
    client.settlement_repo.get_all = AsyncMock(return_value=[mock_setl1, mock_setl2])
    bank_tx = BankTransaction(id="b1", amount=Decimal("49100.00"), date=datetime.now(UTC), row_hash="h1")
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[bank_tx])
    client.engine.reconcile_batch = AsyncMock()

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        with patch.object(
            client,
            "_fetch_settlements_page",
            AsyncMock(side_effect=[{"items": page1_items}, {"items": []}]),
        ):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")
            assert res.fetched_count == 2
            assert res.newly_inserted == 1
            assert res.updated_count == 1
            assert res.reconciliation_triggered is True
            client.engine.reconcile_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_settlements_propagates_fetch_errors_without_swallowing():
    session = AsyncMock()
    client = RazorpayClient(session)
    client.sync_refunds = AsyncMock(return_value=0)
    client.settlement_repo.upsert_settlement = AsyncMock()
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[])
    client.settlement_repo.get_all = AsyncMock(return_value=[])
    client.engine.reconcile_batch = AsyncMock()

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        with patch.object(
            client,
            "_fetch_settlements_page",
            AsyncMock(side_effect=RazorpayFetchError("Invalid API key", status_code=401, code="RAZORPAY_UNAUTHORIZED")),
        ):
            with pytest.raises(RazorpayFetchError) as exc_info:
                await client.sync_settlements(count_limit=10, batch_id="batch_test")

    assert exc_info.value.status_code == 401
    client.settlement_repo.upsert_settlement.assert_not_awaited()
    client.engine.reconcile_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_settlements_reconciles_existing_db_data_when_api_is_empty():
    """When Razorpay returns 0 new records, existing DB settlements still reconcile."""
    session = AsyncMock()
    client = RazorpayClient(session)
    client.sync_refunds = AsyncMock(return_value=0)

    mock_setl = RazorpaySettlement(
        id="s_hist_1", settlement_id="setl_hist_1", amount=Decimal("10000.00"), settlement_created_at=datetime.now(UTC)
    )
    client.settlement_repo.get_all = AsyncMock(return_value=[mock_setl])
    bank_tx = BankTransaction(id="b1", amount=Decimal("10000.00"), date=datetime.now(UTC), row_hash="h1")
    client.bank_repo.get_all_by_batch = AsyncMock(return_value=[bank_tx])
    client.engine.reconcile_batch = AsyncMock()

    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_testkey"):
        with patch.object(client, "_fetch_settlements_page", AsyncMock(return_value={"items": []})):
            res = await client.sync_settlements(count_limit=10, batch_id="batch_test")

            assert res.fetched_count == 0
            assert res.reconciliation_triggered is True
            client.engine.reconcile_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_razorpay_sync_endpoint_returns_structured_401_without_retrying(db_session):
    async_get = AsyncMock(return_value=_mock_status_response(401, "401 Unauthorized"))

    with (
        patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_invalid"),
        patch.object(settings, "RAZORPAY_KEY_SECRET", "bad_secret"),
        patch("httpx.AsyncClient.get", new=async_get),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/razorpay/sync?batch_id=b_err", json={"count": 10})

    assert async_get.await_count == 1
    assert response.status_code == 401
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "RAZORPAY_UNAUTHORIZED"
    assert "401" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_razorpay_sync_endpoint_returns_structured_502_when_retries_exhausted(db_session):
    async_get = AsyncMock(return_value=_mock_status_response(503, "503 Service Unavailable"))

    with (
        patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_livekey"),
        patch.object(settings, "RAZORPAY_KEY_SECRET", "good_secret"),
        patch.object(settings, "RAZORPAY_FETCH_MAX_RETRIES", 2),
        patch("asyncio.sleep", new=AsyncMock()),
        patch("httpx.AsyncClient.get", new=async_get),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/razorpay/sync?batch_id=b_err", json={"count": 10})

    assert async_get.await_count == 2
    assert response.status_code == 502
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "RAZORPAY_FETCH_EXHAUSTED"
    assert "2 attempts" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_fetch_settlements_page_rejects_invalid_json_without_retrying():
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.side_effect = ValueError("Expecting value")
    http_client.get.return_value = bad_resp

    with pytest.raises(RazorpayFetchError) as exc_info:
        await client._fetch_settlements_page(http_client, count=10, skip=0)

    assert not isinstance(exc_info.value, RazorpayFetchExhausted)
    assert exc_info.value.code == "RAZORPAY_INVALID_RESPONSE"
    assert exc_info.value.status_code == 502
    assert http_client.get.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_payload",
    [
        {"entity": "collection", "count": 0},
        {"items": None},
        {"items": "not-a-list"},
        {"items": ["invalid-item"]},
        ["not-a-dict"],
    ],
)
async def test_fetch_settlements_page_rejects_missing_or_malformed_items(bad_payload):
    client = RazorpayClient(AsyncMock())
    http_client = AsyncMock()
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = bad_payload
    http_client.get.return_value = bad_resp

    with pytest.raises(RazorpayFetchError) as exc_info:
        await client._fetch_settlements_page(http_client, count=10, skip=0)

    assert not isinstance(exc_info.value, RazorpayFetchExhausted)
    assert exc_info.value.code == "RAZORPAY_INVALID_RESPONSE"
    assert exc_info.value.status_code == 502
    assert http_client.get.await_count == 1


@pytest.mark.asyncio
async def test_razorpay_sync_endpoint_returns_structured_502_on_malformed_200_payload(db_session):
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"entity": "collection"}
    async_get = AsyncMock(return_value=bad_resp)

    with (
        patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_livekey"),
        patch.object(settings, "RAZORPAY_KEY_SECRET", "good_secret"),
        patch("httpx.AsyncClient.get", new=async_get),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/razorpay/sync?batch_id=b_err", json={"count": 10})

    assert async_get.await_count == 1
    assert response.status_code == 502
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "RAZORPAY_INVALID_RESPONSE"
