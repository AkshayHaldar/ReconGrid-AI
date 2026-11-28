"""Razorpay Settlements and Manual Sync API Routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.common import ApiResponse
from app.schemas.razorpay import (
    RazorpaySettlementResponse,
    RazorpaySyncRequest,
    RazorpaySyncResponse,
)
from app.services.razorpay_client import (
    RazorpayClient,
    RazorpayFetchError,
    RazorpayFetchExhausted,
)

router = APIRouter(prefix="/razorpay", tags=["Razorpay"])


@router.post("/sync", response_model=ApiResponse[RazorpaySyncResponse])
async def sync_razorpay_settlements(
    payload: RazorpaySyncRequest = RazorpaySyncRequest(),
    batch_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    """Triggers an automated paginated fetch of Razorpay settlements with exponential backoff."""
    client = RazorpayClient(db)
    try:
        result = await client.sync_settlements(count_limit=payload.count, batch_id=batch_id)
    except RazorpayFetchExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": {"upstream_status": exc.status_code},
            },
        ) from exc
    except RazorpayFetchError as exc:
        http_status = exc.status_code if exc.status_code in (400, 401, 403, 404) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=http_status,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": {"upstream_status": exc.status_code},
            },
        ) from exc
    return ApiResponse.ok(result)


@router.get("/settlements", response_model=ApiResponse[list[RazorpaySettlementResponse]])
async def list_settlements(
    db: AsyncSession = Depends(get_db),
):
    """Lists all stored Razorpay settlements."""
    repo = SettlementRepository(db)
    items = await repo.get_all()
    res = [RazorpaySettlementResponse.model_validate(s) for s in items]
    return ApiResponse.ok(res)
