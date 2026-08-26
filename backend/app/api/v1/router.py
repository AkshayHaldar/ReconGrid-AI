"""API v1 router aggregator."""

from fastapi import APIRouter
from app.api.v1.bank import router as bank_router
from app.api.v1.demo import router as demo_router
from app.api.v1.qa import router as qa_router
from app.api.v1.razorpay import router as razorpay_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(bank_router)
api_router.include_router(razorpay_router)
api_router.include_router(reconciliation_router)
api_router.include_router(qa_router)
api_router.include_router(webhooks_router)
api_router.include_router(demo_router)
