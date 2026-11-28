"""Razorpay REST Client with cursor pagination, tenacity backoff, and idempotency."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.locks import lock_batch
from app.core.logging import logger
from app.core.security import resolve_secret
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.razorpay import RazorpayRefundPayload, RazorpaySyncResponse
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import paise_to_rupees


class RazorpayFetchError(Exception):
    """Base exception for Razorpay fetch errors."""


class RazorpayFetchExhausted(Exception):
    """Raised when maximum retries are exceeded."""


def _is_transient_refund_fetch_error(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status == 429 or 500 <= status < 600
    return isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


def _razorpay_month(timestamp: datetime) -> date:
    if timestamp.tzinfo is None:  # SQLite returns stored UTC times without an offset.
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(ZoneInfo("Asia/Kolkata")).date().replace(day=1)


class RazorpayClient:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settlement_repo = SettlementRepository(session)
        self.bank_repo = BankRepository(session)
        self.recon_repo = ReconciliationRepository(session)
        self.engine = ReconciliationEngine(self.recon_repo)
        self.base_url = "https://api.razorpay.com/v1"

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _fetch_settlements_page(
        self,
        client: httpx.AsyncClient,
        count: int = 100,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Fetches a single page of settlements with retry backoff."""
        resp = await client.get(
            f"{self.base_url}/settlements",
            params={"count": count, "skip": skip},
            auth=(settings.RAZORPAY_KEY_ID, resolve_secret(settings.RAZORPAY_KEY_SECRET)),
            timeout=10.0,
        )
        if resp.status_code == 429:
            logger.warning("razorpay_rate_limited_retrying", skip=skip)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_transient_refund_fetch_error),
    )
    async def _fetch_refunds_page(
        self, client: httpx.AsyncClient, count: int, skip: int, *, settlement_month: date | None = None,
    ) -> list[dict[str, Any]]:
        endpoint = "refunds"
        params = {"count": count, "skip": skip}
        if settlement_month is not None:
            endpoint = "settlements/recon/combined"
            params.update(year=settlement_month.year, month=settlement_month.month)
        response = await client.get(
            f"{self.base_url}/{endpoint}",
            params=params,
            auth=(settings.RAZORPAY_KEY_ID, resolve_secret(settings.RAZORPAY_KEY_SECRET)),
            timeout=10.0,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise RazorpayFetchError("Invalid JSON response from Razorpay") from error
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) > count or any(not isinstance(item, dict) for item in items):
            raise RazorpayFetchError("Invalid refunds response from Razorpay")
        return items

    async def fetch_refunds(self, count_limit: int = 100) -> list[dict[str, Any]]:
        """Read and validate a bounded window of INR refund records before writing any rows."""
        if not settings.RAZORPAY_KEY_ID or settings.RAZORPAY_KEY_ID.startswith("rzp_test_sample"):
            return []

        records = []
        offset = 0
        async with httpx.AsyncClient() as client:
            while offset < count_limit:
                page_size = min(100, count_limit - offset)
                items = await self._fetch_refunds_page(client, count=page_size, skip=offset)
                for item in items:
                    refund = RazorpayRefundPayload.model_validate(item)
                    if refund.currency == "INR":
                        records.append(refund.to_record(item))
                if len(items) < page_size:
                    break
                offset += len(items)
        return records

    async def sync_refunds(
        self, count_limit: int = 100, *, settlements: Sequence[RazorpaySettlement] | None = None,
    ) -> int:
        if not settings.RAZORPAY_KEY_ID or settings.RAZORPAY_KEY_ID.startswith("rzp_test_sample"):
            return 0
        refunds = await self.fetch_refunds(count_limit)
        for refund in refunds:
            await self.settlement_repo.upsert_refund(refund)

        oldest_unlinked = await self.settlement_repo.oldest_unlinked_processed_refund()
        if oldest_unlinked is not None:
            all_settlements = settlements if settlements is not None else await self.settlement_repo.get_all()
            await self._link_reported_refunds(all_settlements, _razorpay_month(oldest_unlinked))
        return len(refunds)

    async def _link_reported_refunds(self, settlements: Sequence[RazorpaySettlement], start_month: date) -> None:
        # Only the settlement report attests which payout absorbed a refund.
        known_payouts = {
            item.settlement_id: _razorpay_month(item.settlement_created_at)
            for item in settlements if item.is_test_mode == settings.IS_TEST_MODE
        }
        months = {month for month in known_payouts.values() if month >= start_month}
        if not months:
            return
        links: dict[str, set[str]] = {}
        async with httpx.AsyncClient() as client:
            for month in sorted(months):
                offset = 0
                while True:
                    page = await self._fetch_refunds_page(client, 1000, offset, settlement_month=month)
                    for row in page:
                        refund_id = row.get("entity_id")
                        settlement_id = row.get("settlement_id")
                        if (
                            row.get("type") == "refund" and row.get("settled") is True
                            and row.get("currency") == "INR" and isinstance(refund_id, str)
                            and isinstance(settlement_id, str)
                        ):
                            links.setdefault(refund_id, set()).add(settlement_id)
                    if len(page) < 1000:
                        break
                    offset += len(page)

        for refund_id, settlement_ids in links.items():
            if len(settlement_ids) == 1:
                settlement_id = next(iter(settlement_ids))
                if settlement_id in known_payouts:
                    await self.settlement_repo.link_refund(refund_id, settlement_id)

    async def sync_settlements(
        self,
        count_limit: int = 100,
        batch_id: str = "default",
    ) -> RazorpaySyncResponse:
        """Pulls settlements from Razorpay API or test mode fixtures, upserts, and triggers reconciliation."""
        newly_inserted = 0
        updated_count = 0
        total_fetched = 0
        settlement_records: list[dict] = []

        # If dummy keys or test mode without live credentials, handle gracefully or fetch from API
        if settings.RAZORPAY_KEY_ID and not settings.RAZORPAY_KEY_ID.startswith("rzp_test_sample"):
            try:
                async with httpx.AsyncClient() as client:
                    skip = 0
                    page_size = min(count_limit, 100)
                    while True:
                        data = await self._fetch_settlements_page(client, count=page_size, skip=skip)
                        items = data.get("items", [])
                        if not items:
                            break

                        for item in items:
                            total_fetched += 1
                            amount_inr = paise_to_rupees(item.get("amount", 0))
                            fees_inr = paise_to_rupees(item.get("fees", 0))
                            tax_inr = paise_to_rupees(item.get("tax", 0))
                            gross_inr = amount_inr + fees_inr + tax_inr

                            created_ts = item.get("created_at")
                            dt = (
                                datetime.fromtimestamp(created_ts, UTC)
                                if created_ts
                                else datetime.now(UTC)
                            )

                            settlement_records.append({
                                "settlement_id": item.get("id"),
                                "amount": amount_inr,
                                "gross_amount": gross_inr,
                                "fees": fees_inr,
                                "tax": tax_inr,
                                "utr": item.get("utr"),
                                "status": item.get("status", "processed"),
                                "settlement_created_at": dt,
                                "raw_payload": item,
                                "is_test_mode": settings.IS_TEST_MODE,
                            })

                        if len(items) < page_size or total_fetched >= count_limit:
                            break
                        skip += len(items)
            except Exception as ex:
                logger.error("razorpay_fetch_failed_using_cached_or_test", error=str(ex))

        # The settlement fetch is done; serialize the upserts with other writers of the batch.
        await lock_batch(self.session, batch_id)

        # Save to database
        for s_data in settlement_records:
            setl, created = await self.settlement_repo.upsert_settlement(s_data)
            if created:
                newly_inserted += 1
            else:
                updated_count += 1

        # sync_refunds calls Razorpay with retries, so commit first and do not hold the lock while it waits.
        await self.session.commit()
        all_settlements = await self.settlement_repo.get_all()
        try:
            await self.sync_refunds(count_limit, settlements=all_settlements)
        except (httpx.HTTPError, RazorpayFetchError, ValidationError) as error:
            logger.warning("razorpay_refund_sync_failed", error_type=type(error).__name__)

        # Take the lock again and re-read, so the reconcile sees whatever other writers committed meanwhile.
        await self.session.commit()
        await lock_batch(self.session, batch_id)
        all_settlements = await self.settlement_repo.get_all()

        # Trigger reconciliation on active bank batch
        bank_txs = await self.bank_repo.get_all_by_batch(batch_id)
        reconciliation_triggered = False
        if bank_txs and all_settlements:
            await self.engine.reconcile_batch(
                bank_transactions=bank_txs,
                settlements=all_settlements,
                batch_id=batch_id,
            )
            reconciliation_triggered = True

        return RazorpaySyncResponse(
            fetched_count=total_fetched,
            newly_inserted=newly_inserted,
            updated_count=updated_count,
            reconciliation_triggered=reconciliation_triggered,
        )
