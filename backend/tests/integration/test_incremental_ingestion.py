"""Database-backed regression tests for incremental bank statement reconciliation."""

import asyncio
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.reconciliation_log import ReconciliationLog
from app.services.ingestion import IngestionService
from app.services.reconciliation import verify_batch_audit_chain


def _statement(date: datetime, *rows: tuple[str, str, str]) -> UploadFile:
    header = "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
    content = "".join(f"{date:%d/%m/%Y},{utr},{description},{amount},0.00\n" for utr, description, amount in rows)
    return UploadFile(
        filename="statement.csv",
        file=io.BytesIO((header + content).encode()),
        headers={"content-type": "text/csv"},
    )


async def _only_settlement(service: IngestionService, date: datetime, utr: str) -> str:
    settlement, _ = await service.settlement_repo.upsert_settlement(
        {
            "settlement_id": "setl_upload_recon",
            "settlement_created_at": date,
            "amount": Decimal("97640"),
            "gross_amount": Decimal("97640"),
            "fees": Decimal("0"),
            "tax": Decimal("0"),
            "utr": utr,
            "status": "processed",
        }
    )
    return settlement.id


async def _batch_logs(session: AsyncSession, batch_id: str) -> list[ReconciliationLog]:
    stmt = select(ReconciliationLog).where(ReconciliationLog.batch_id == batch_id)
    return list((await session.execute(stmt)).scalars())


async def test_incremental_upload_deduplicates_and_supersedes_contested_claim(db_session: AsyncSession):
    service = IngestionService(db_session)
    today = datetime.now(UTC)
    utr = "CMS002938491801"
    batch = "incremental-conflict"
    settlement_id = await _only_settlement(service, today, utr)
    first = (utr, "Razorpay first transfer", "97640.00")
    second = (utr, "Razorpay later transfer", "97640.00")

    uploaded = await service.ingest_csv(_statement(today, first, first), batch)
    assert (uploaded.inserted_count, uploaded.duplicate_count, uploaded.reconciled_immediately) == (1, 1, 1)
    (initial,) = await _batch_logs(db_session, batch)
    assert initial.match_status == "MATCHED"

    await service.ingest_csv(_statement(today, second), batch)
    history = await _batch_logs(db_session, batch)
    active = [log for log in history if not log.superseded]
    assert initial.superseded and initial.match_status == "MATCHED"
    assert len(history) == 3
    assert len({log.bank_tx_id for log in active}) == 2
    assert all(log.match_status == "CONFLICT" and log.rzp_settlement_id == settlement_id for log in active)

    retry = await service.ingest_csv(_statement(today, first, second), batch)
    assert retry.reconciled_immediately == 0
    assert len(await _batch_logs(db_session, batch)) == 3
    assert (await verify_batch_audit_chain(service.recon_repo, batch)).status == "VERIFIED"


async def test_incremental_upload_revisits_pending_rows_only_when_their_decision_changes(db_session: AsyncSession):
    service = IngestionService(db_session)
    today = datetime.now(UTC)
    utr = "CMS002938491802"
    batch = "incremental-pending"
    pending_row = (utr, "Pending transfer", "97640.00")
    await service.ingest_csv(_statement(today, pending_row), batch)
    (pending,) = await _batch_logs(db_session, batch)
    assert pending.match_status == "PENDING_SETTLEMENT_DATA"

    retry = await service.ingest_csv(_statement(today, pending_row), batch)
    assert retry.reconciled_immediately == 0
    assert not pending.superseded

    await _only_settlement(service, today, utr)
    other_row = ("CMS002938491899", "Unrelated transfer", "500000.00")
    response = await service.ingest_csv(_statement(today, other_row), batch)
    assert response.reconciled_immediately == 2
    active = [log for log in await _batch_logs(db_session, batch) if not log.superseded]
    assert pending.superseded
    assert next(log for log in active if log.bank_tx_id == pending.bank_tx_id).match_status == "MATCHED"


@pytest.mark.parametrize("decision", ["APPROVED", "DENIED"])
async def test_incremental_upload_preserves_human_decisions(db_session: AsyncSession, decision: str):
    service = IngestionService(db_session)
    today = datetime.now(UTC)
    utr = "CMS002938491803"
    batch = "incremental-human-decision"
    await _only_settlement(service, today, utr)
    first = ("", "First transfer", "97640.00")
    await service.ingest_csv(_statement(today, first), batch)
    (original,) = await _batch_logs(db_session, batch)
    assert original.match_status == "SUGGESTED"
    original.human_action = decision
    original.match_status = "MATCHED" if decision == "APPROVED" else "EXCEPTION"
    await db_session.flush()

    retry = await service.ingest_csv(_statement(today, first), batch)
    assert retry.reconciled_immediately == 0
    assert not original.superseded

    estimated = ("", "Different transfer", "97640.00")
    await service.ingest_csv(_statement(today, estimated), batch)
    active = [log for log in await _batch_logs(db_session, batch) if not log.superseded]
    new = next(log for log in active if log.bank_tx_id != original.bank_tx_id)
    assert new.match_status == ("PENDING_SETTLEMENT_DATA" if decision == "APPROVED" else "SUGGESTED")
    assert not original.superseded and original.human_action == decision
    assert original.rzp_settlement_id is not None


async def test_incremental_upload_does_not_reconcile_identical_rows_in_a_second_batch(db_session: AsyncSession):
    service = IngestionService(db_session)
    today = datetime.now(UTC)
    utr = "CMS002938491804"
    first = (utr, "Original batch transfer", "97640.00")
    await _only_settlement(service, today, utr)
    await service.ingest_csv(_statement(today, first), "original-batch")
    (original,) = await _batch_logs(db_session, "original-batch")
    duplicate = await service.ingest_csv(_statement(today, first), "second-batch")
    assert (duplicate.inserted_count, duplicate.duplicate_count, duplicate.reconciled_immediately) == (0, 1, 0)
    assert not await _batch_logs(db_session, "second-batch")

    distinct = (utr, "Second batch transfer", "97640.00")
    await service.ingest_csv(_statement(today, distinct), "second-batch")
    (other,) = await _batch_logs(db_session, "second-batch")
    assert other.match_status == "MATCHED"
    assert original.match_status == "MATCHED" and not original.superseded


async def test_parallel_postgres_uploads_share_the_same_claim_snapshot(db_session: AsyncSession):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL transaction lock coverage")

    today = datetime.now(UTC)
    utr = "CMS002938491805"
    batch = "parallel-uploads"
    await _only_settlement(IngestionService(db_session), today, utr)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def upload(description: str):
        async with sessions.begin() as session:
            return await IngestionService(session).ingest_csv(_statement(today, (utr, description, "97640.00")), batch)

    first, second = await asyncio.gather(upload("First concurrent transfer"), upload("Second concurrent transfer"))
    assert first.inserted_count == second.inserted_count == 1
    history = await _batch_logs(db_session, batch)
    assert len(history) == 3
    assert sorted(log.match_status for log in history if not log.superseded) == ["CONFLICT", "CONFLICT"]
    assert (await verify_batch_audit_chain(IngestionService(db_session).recon_repo, batch)).status == "VERIFIED"
