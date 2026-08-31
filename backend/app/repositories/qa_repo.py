"""QA repository for deterministic fact lookup and audit interaction logging."""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.models.qa_interaction_log import QaInteractionLog


class QaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_reconciliation_record(self, term: str) -> ReconciliationLog | None:
        """Deterministically retrieves the exact ReconciliationLog matching a UTR, Order, or Settlement ID."""
        clean_term = term.strip()
        if not clean_term:
            return None

        # Extract search candidates: identifiers with numbers or specific reference codes
        import re
        stop_words = {"WHY", "DID", "NOT", "SETTLE", "CORRECTLY", "HAVE", "FEE", "DEDUCTION", "WHAT", "HOW", "ABOUT", "THE", "THIS", "TRANSACTION", "RECORD", "SHOW", "WHERE", "ORDER", "TXN"}
        raw_tokens = re.findall(r"[A-Za-z0-9_\-#]{2,}", clean_term)
        
        # Prioritize tokens that contain digits or specific gateway prefixes
        specific_tokens = [
            t.lstrip("#") for t in raw_tokens
            if (any(c.isdigit() for c in t) or t.upper().startswith(("SETL", "CMS", "PAY", "RFND", "RTGS", "NEFT", "ICIC", "SBI", "HDFC")))
            and t.upper() not in stop_words
        ]

        search_terms = specific_tokens if specific_tokens else [clean_term]

        for st in search_terms:
            if not st:
                continue
            # Try settlement_id match
            stmt1 = (
                select(ReconciliationLog)
                .join(ReconciliationLog.rzp_settlement)
                .options(
                    selectinload(ReconciliationLog.bank_transaction),
                    selectinload(ReconciliationLog.rzp_settlement),
                )
                .where(
                    RazorpaySettlement.settlement_id.ilike(f"%{st}%"),
                    ReconciliationLog.superseded == False,  # noqa: E712
                )
            )
            res1 = await self.session.execute(stmt1)
            record = res1.scalars().first()
            if record:
                return record

            # Try UTR or Description match
            stmt2 = (
                select(ReconciliationLog)
                .join(ReconciliationLog.bank_transaction)
                .outerjoin(ReconciliationLog.rzp_settlement)
                .options(
                    selectinload(ReconciliationLog.bank_transaction),
                    selectinload(ReconciliationLog.rzp_settlement),
                )
                .where(
                    (BankTransaction.utr.ilike(f"%{st}%"))
                    | (BankTransaction.description.ilike(f"%{st}%"))
                    | (RazorpaySettlement.utr.ilike(f"%{st}%"))
                    | (ReconciliationLog.diagnostic_note.ilike(f"%{st}%")),
                    ReconciliationLog.superseded == False,  # noqa: E712
                )
            )
            res2 = await self.session.execute(stmt2)
            record2 = res2.scalars().first()
            if record2:
                return record2

    async def get_record_by_id(self, record_id: str) -> ReconciliationLog | None:
        """Retrieves a ReconciliationLog directly by its primary key ID."""
        if not record_id:
            return None
        stmt = (
            select(ReconciliationLog)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(ReconciliationLog.id == record_id)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def log_interaction(self, log_dict: dict) -> QaInteractionLog:
        """Appends an immutable record of every Q&A interaction to QaInteractionLog."""
        qa_log = QaInteractionLog(**log_dict)
        self.session.add(qa_log)
        await self.session.flush()
        return qa_log

    async def get_history(self, limit: int = 50) -> Sequence[QaInteractionLog]:
        stmt = select(QaInteractionLog).order_by(QaInteractionLog.asked_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
