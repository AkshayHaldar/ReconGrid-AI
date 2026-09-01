"""Settlement Q&A Agent API Routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.repositories.qa_repo import QaRepository
from app.schemas.common import ApiResponse
from app.schemas.qa import QaAskRequest, QaAskResponse, QaHistoryItem
from app.services.settlement_qa import SettlementQaAgent

router = APIRouter(prefix="/qa", tags=["Settlement Q&A Agent"])


@router.post("/ask", response_model=ApiResponse[QaAskResponse])
async def ask_settlement_question(
    req: QaAskRequest,
    db: AsyncSession = Depends(get_db),
):
    """Answers natural-language settlement questions backed strictly by computed audit facts."""
    qa_repo = QaRepository(db)
    agent = SettlementQaAgent(qa_repo)
    result = await agent.answer_query(
        query=req.query,
        context_record_id=req.context_record_id,
        history=req.history,
    )
    return ApiResponse.ok(result)


@router.get("/history", response_model=ApiResponse[list[QaHistoryItem]])
async def get_qa_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Returns the append-only audit log of past Q&A agent queries and answers."""
    qa_repo = QaRepository(db)
    history = await qa_repo.get_history(limit=limit)
    items = [QaHistoryItem.model_validate(h) for h in history]
    return ApiResponse.ok(items)
