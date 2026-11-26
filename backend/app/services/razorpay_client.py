"""Razorpay REST Client with cursor pagination, tenacity backoff, and idempotency."""

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings
from app.core.logging import logger
from app.core.security import resolve_secret
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.razorpay import RazorpaySyncResponse
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import paise_to_rupees


class RazorpayFetchError(Exception):
    """Base exception for Razorpay fetch errors."""

    def __init__(
        self,
        message: str = "Razorpay API request failed.",
        *,
        status_code: int | None = None,
        code: str = "RAZORPAY_FETCH_ERROR",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class RazorpayFetchExhausted(RazorpayFetchError):
    """Raised when retryable Razorpay errors exhaust maximum retry attempts."""

    def __init__(
        self,
        message: str = "Razorpay API retries exhausted.",
        *,
        status_code: int | None = None,
        code: str = "RAZORPAY_FETCH_EXHAUSTED",
    ) -> None:
        super().__init__(message, status_code=status_code, code=code)


def _is_retryable_razorpay_error(exc: BaseException) -> bool:
    """Retry only transient network failures, 429 rate limits, and 5xx server responses."""
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or status_code >= 500
    return False


def _client_error_code(status_code: int) -> str:
    if status_code == 400:
        return "RAZORPAY_BAD_REQUEST"
    if status_code == 401:
        return "RAZORPAY_UNAUTHORIZED"
    if status_code == 403:
        return "RAZORPAY_FORBIDDEN"
    return "RAZORPAY_CLIENT_ERROR"


class RazorpayClient:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settlement_repo = SettlementRepository(session)
        self.bank_repo = BankRepository(session)
        self.recon_repo = ReconciliationRepository(session)
        self.engine = ReconciliationEngine(self.recon_repo)
        self.base_url = "https://api.razorpay.com/v1"

    async def _fetch_settlements_page(
        self,
        client: httpx.AsyncClient,
        count: int = 100,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Fetches a single page of settlements with retry backoff on transient errors only."""
        max_attempts = max(1, settings.RAZORPAY_FETCH_MAX_RETRIES)
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(initial=1, max=10, jitter=1),
                retry=retry_if_exception(_is_retryable_razorpay_error),
            ):
                with attempt:
                    resp = await client.get(
                        f"{self.base_url}/settlements",
                        params={"count": count, "skip": skip},
                        auth=(settings.RAZORPAY_KEY_ID, resolve_secret(settings.RAZORPAY_KEY_SECRET)),
                        timeout=10.0,
                    )
                    if resp.status_code == 429:
                        logger.warning(
                            "razorpay_rate_limited_retrying",
                            skip=skip,
                            attempt=attempt.retry_state.attempt_number,
                        )
                    resp.raise_for_status()
                    return resp.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if _is_retryable_razorpay_error(exc):
                logger.error(
                    "razorpay_fetch_retries_exhausted",
                    status_code=status_code,
                    attempts=max_attempts,
                    skip=skip,
                    error=str(exc),
                )
                error_code = "RAZORPAY_API_RATE_LIMIT" if status_code == 429 else "RAZORPAY_FETCH_EXHAUSTED"
                raise RazorpayFetchExhausted(
                    f"Razorpay API failed after {max_attempts} attempts (HTTP {status_code}).",
                    status_code=status_code,
                    code=error_code,
                ) from exc

            logger.error(
                "razorpay_fetch_client_error",
                status_code=status_code,
                skip=skip,
                error=str(exc),
            )
            raise RazorpayFetchError(
                f"Razorpay API rejected request with HTTP {status_code}. Check Razorpay API credentials and parameters.",
                status_code=status_code,
                code=_client_error_code(status_code),
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "razorpay_fetch_network_exhausted",
                attempts=max_attempts,
                skip=skip,
                error=str(exc),
            )
            raise RazorpayFetchExhausted(
                f"Razorpay API unreachable after {max_attempts} attempts: {exc}",
                status_code=502,
                code="RAZORPAY_NETWORK_ERROR",
            ) from exc

        raise RazorpayFetchError("Unexpected empty retry outcome from Razorpay client.")

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

        # If dummy keys or test mode without live credentials, skip external API call and reconcile DB records
        if settings.RAZORPAY_KEY_ID and not settings.RAZORPAY_KEY_ID.startswith("rzp_test_sample"):
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
                        dt = datetime.fromtimestamp(created_ts, UTC) if created_ts else datetime.now(UTC)

                        settlement_records.append(
                            {
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
                            }
                        )

                    if len(items) < page_size or total_fetched >= count_limit:
                        break
                    skip += len(items)

        # Save to database
        for s_data in settlement_records:
            setl, created = await self.settlement_repo.upsert_settlement(s_data)
            if created:
                newly_inserted += 1
            else:
                updated_count += 1

        # Fetch full list of settlements from DB instead of only using newly fetched data.
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
