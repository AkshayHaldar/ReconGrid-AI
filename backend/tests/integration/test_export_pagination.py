"""Regression coverage ensuring CSV, Excel, and Tally XML exports paginate past 10,000 rows."""

import csv
import io
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import Engine, event
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import reconciliation as reconciliation_api
from app.core.database import get_db
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository


def _make_db_log(batch_id: str, index: int, status: str = "MATCHED") -> ReconciliationLog:
    tx_date = datetime(2026, 2, 1, tzinfo=UTC) + timedelta(minutes=index)
    amount = Decimal("100.00")
    bank = BankTransaction(
        batch_id=batch_id,
        row_hash=f"{batch_id}-row-{index}",
        date=tx_date,
        amount=amount,
        direction="CREDIT",
        description=f"NEFT/UTR{index:05d}",
        utr=f"UTR{index:05d}",
    )
    rzp = RazorpaySettlement(
        settlement_id=f"setl_{batch_id}_{index:05d}",
        amount=amount,
        gross_amount=Decimal("102.36"),
        fees=Decimal("2.00"),
        tax=Decimal("0.36"),
    )
    return ReconciliationLog(
        batch_id=batch_id,
        bank_transaction=bank,
        rzp_settlement=rzp,
        match_status=status,
        match_tier="TIER_1",
        delta_amount=Decimal("0.00") if status == "MATCHED" else Decimal("5.00"),
        diagnostic_type="EXACT_MATCH" if status == "MATCHED" else "AMOUNT_MISMATCH",
        diagnostic_note=f"row-{index}",
    )


async def test_exports_paginate_all_pages_from_database(db_session, monkeypatch):
    """CSV, XLSX, and Tally XML must traverse all pages instead of stopping at page 1."""
    batch_id = "paginated-db-batch"
    for i in range(5):
        status = "EXCEPTION" if i == 4 else "MATCHED"
        db_session.add(_make_db_log(batch_id, i, status=status))
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export")
        xlsx_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export-xlsx")
        xml_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert len(csv_rows) == 5
    assert {row["Bank UTR"] for row in csv_rows} == {f"UTR{i:05d}" for i in range(5)}

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    summary = wb["Executive Summary"]
    ledger = wb["Reconciled Ledger"]
    exceptions = wb["Exceptions & Discrepancies"]
    assert summary["B9"].value == 4
    assert summary["B10"].value == 1
    assert ledger.max_row == 7  # header + 4 rows + blank + Total row
    assert exceptions.max_row == 4  # header + 1 row + blank + Total row

    assert xml_resp.status_code == 200
    root = ET.fromstring(xml_resp.text)
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 4


async def test_exports_do_not_truncate_over_ten_thousand_rows(monkeypatch):
    """All 10,005 records must appear in CSV, XLSX, and Tally XML outputs."""
    total_rows = 10_005
    tx_date = datetime(2026, 3, 1, tzinfo=UTC)
    synthetic_logs = [
        SimpleNamespace(
            id=f"log-{i:05d}",
            batch_id="large-batch",
            match_status="MATCHED",
            match_tier="TIER_1",
            confidence_score=1.0,
            diagnostic_type="EXACT_MATCH",
            diagnostic_note=f"row-{i}",
            human_action="AUTO",
            delta_amount=Decimal("0.00"),
            bank_transaction=SimpleNamespace(
                date=tx_date,
                direction="CREDIT",
                description=f"Merchant payout {i}",
                utr=f"UTR{i:05d}",
                amount=Decimal("100.00"),
            ),
            rzp_settlement=SimpleNamespace(
                settlement_id=f"setl_{i:05d}",
                created_at=tx_date,
                amount=Decimal("100.00"),
                gross_amount=Decimal("102.36"),
                fees=Decimal("2.00"),
                tax=Decimal("0.36"),
            ),
        )
        for i in range(total_rows)
    ]

    class PaginatedStubRepo:
        async def get_active_logs_cursor(
            self,
            *,
            batch_id: str,
            page_size: int = 1000,
            cursor: tuple[datetime, str] | None = None,
        ):
            assert batch_id == "large-batch"
            start = 0 if cursor is None else int(cursor[1].removeprefix("log-")) + 1
            chunk = synthetic_logs[start : start + page_size]
            if not chunk or start + page_size >= len(synthetic_logs):
                return chunk, None
            return chunk, (tx_date, chunk[-1].id)

    monkeypatch.setattr(reconciliation_api, "ReconciliationRepository", lambda db: PaginatedStubRepo())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get("/api/v1/reconciliation/large-batch/export")
        xlsx_resp = await client.get("/api/v1/reconciliation/large-batch/export-xlsx")
        xml_resp = await client.get("/api/v1/reconciliation/large-batch/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert len(csv_rows) == total_rows
    assert csv_rows[-1]["Bank UTR"] == "UTR10004"

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    assert wb["Executive Summary"]["B9"].value == total_rows
    assert wb["Reconciled Ledger"][f"B{total_rows + 1}"].value == "UTR10004"

    assert xml_resp.status_code == 200
    vouchers = ET.fromstring(xml_resp.text).findall(".//VOUCHER")
    assert len(vouchers) == total_rows


async def test_exports_handle_empty_batch_cleanly(db_session):
    """Empty batches return valid CSV header, XLSX workbook, and Tally XML envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get("/api/v1/reconciliation/empty-batch/export")
        xlsx_resp = await client.get("/api/v1/reconciliation/empty-batch/export-xlsx")
        xml_resp = await client.get("/api/v1/reconciliation/empty-batch/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert csv_rows == []
    assert csv_resp.text.startswith("Date,Direction,Bank Description")

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    assert wb["Executive Summary"]["B9"].value == 0

    assert xml_resp.status_code == 200
    vouchers = ET.fromstring(xml_resp.text).findall(".//VOUCHER")
    assert vouchers == []


async def test_csv_export_uses_keyset_without_offset_or_count_and_handles_ties(db_session, monkeypatch):
    """Keyset export executes zero OFFSET/COUNT queries and handles tied timestamps deterministically."""
    batch_id = "keyset-ties-batch"
    shared_ts = datetime(2026, 2, 10, 12, 0, tzinfo=UTC)
    for i in range(6):
        log = _make_db_log(batch_id, i, status="MATCHED")
        if i in (1, 2, 3, 4):
            log.bank_transaction.date = shared_ts
        db_session.add(log)
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)

    async def forbid_offset_pagination(*args, **kwargs):
        raise AssertionError("OFFSET get_active_logs must not be called by export")

    monkeypatch.setattr(ReconciliationRepository, "get_active_logs", forbid_offset_pagination)

    executed_sql: list[str] = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        sql = str(context.compiled.statement) if context.compiled else statement
        executed_sql.append(sql.upper())

    event.listen(Engine, "before_cursor_execute", capture_sql)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export")
    finally:
        event.remove(Engine, "before_cursor_execute", capture_sql)

    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text, newline="")))
    assert len(rows) == 6
    assert {row["Bank UTR"] for row in rows} == {f"UTR{i:05d}" for i in range(6)}

    select_sql = [s for s in executed_sql if s.lstrip().startswith("SELECT")]
    ledger_page_queries = [s for s in select_sql if "FROM RECONCILIATION_LOGS" in s]
    assert len(ledger_page_queries) == 3  # 6 rows at page_size=2 requires 3 keyset page queries
    assert not any("OFFSET" in s for s in select_sql)
    assert not any("COUNT(" in s for s in select_sql)
    assert any("RECONCILIATION_LOGS.ID <" in s for s in ledger_page_queries)


async def test_csv_keyset_pagination_avoids_drift_when_rows_change_mid_export(db_session, monkeypatch):
    """Inserting or superseding earlier-page rows mid-export must not duplicate or skip remaining rows."""
    batch_id = "drift-safe-batch"
    for i in range(5):
        db_session.add(_make_db_log(batch_id, i, status="MATCHED"))
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)
    orig_fetch = reconciliation_api._fetch_csv_export_page
    call_count = 0

    async def mutating_fetch(request, target_batch, cursor):
        nonlocal call_count
        payload, next_cursor = await orig_fetch(request, target_batch, cursor)
        call_count += 1
        if call_count == 1:
            # Supersede already-exported newest row and add an even newer row between page 1 and page 2.
            newer = _make_db_log(batch_id, 99, status="MATCHED")
            newer.bank_transaction.date = datetime(2026, 2, 2, tzinfo=UTC)
            db_session.add(newer)
            await db_session.commit()
        return payload, next_cursor

    monkeypatch.setattr(reconciliation_api, "_fetch_csv_export_page", mutating_fetch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export")

    assert resp.status_code == 200
    utrs = [row["Bank UTR"] for row in csv.DictReader(io.StringIO(resp.text, newline=""))]
    # Exact original 5 rows (UTR00004..UTR00000) exported without duplicates or skips.
    assert utrs == [f"UTR{i:05d}" for i in range(4, -1, -1)]
    assert call_count == 3


async def test_csv_export_prefetches_page_one_and_surfaces_initial_db_error(monkeypatch):
    """Initial DB failure must happen before StreamingResponse and must not return 200 headers-only CSV."""
    fetch_calls = 0

    class FailingFirstPageRepo:
        async def get_active_logs_cursor(self, **kwargs):
            nonlocal fetch_calls
            fetch_calls += 1
            raise SQLAlchemyError("simulated initial DB failure")

    monkeypatch.setattr(reconciliation_api, "ReconciliationRepository", lambda db: FailingFirstPageRepo())

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/reconciliation/broken-batch/export")

    assert fetch_calls == 1
    assert resp.status_code == 500
    assert "Date,Direction,Bank Description" not in resp.text


async def test_csv_export_initial_page_is_fetched_once_and_sessions_scoped_per_page(db_session, monkeypatch):
    """Page 1 is fetched once and each page uses an isolated session closed before streaming next page."""
    batch_id = "session-scope-batch"
    for i in range(5):
        db_session.add(_make_db_log(batch_id, i, status="MATCHED"))
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)

    orig_override = app.dependency_overrides[get_db]
    lifecycle_events: list[str] = []
    open_sessions = 0
    seen_page_cursors: list[tuple[datetime, str] | None] = []

    async def tracking_get_db():
        nonlocal open_sessions
        gen = orig_override()
        session = await anext(gen)
        open_sessions += 1
        lifecycle_events.append(f"open:{open_sessions}")
        try:
            yield session
        except GeneratorExit:
            raise
        except BaseException as exc:
            await gen.athrow(exc)
        else:
            try:
                await anext(gen)
            except StopAsyncIteration:
                pass
        finally:
            await gen.aclose()
            open_sessions -= 1
            lifecycle_events.append(f"close:{open_sessions}")

    orig_cursor_method = ReconciliationRepository.get_active_logs_cursor

    async def recording_cursor(self, *, batch_id: str = "default", page_size: int = 1000, cursor=None):
        # Every query must run inside an active session and open count must be exactly 1.
        assert open_sessions == 1
        seen_page_cursors.append(cursor)
        return await orig_cursor_method(self, batch_id=batch_id, page_size=page_size, cursor=cursor)

    monkeypatch.setitem(app.dependency_overrides, get_db, tracking_get_db)
    monkeypatch.setattr(ReconciliationRepository, "get_active_logs_cursor", recording_cursor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export")

    assert resp.status_code == 200
    assert open_sessions == 0
    assert len(seen_page_cursors) == 3
    assert seen_page_cursors[0] is None
    assert lifecycle_events == ["open:1", "close:0", "open:1", "close:0", "open:1", "close:0"]


async def test_csv_export_session_cleanup_on_stream_cancellation_and_exception(db_session, monkeypatch):
    """Mid-stream errors and client cancellation must release per-page sessions without leaks."""
    batch_id = "cancel-batch"
    for i in range(4):
        db_session.add(_make_db_log(batch_id, i, status="MATCHED"))
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)

    orig_override = app.dependency_overrides[get_db]
    active_sessions = 0
    rollbacks = 0
    closes = 0

    async def tracking_get_db():
        nonlocal active_sessions, rollbacks, closes
        gen = orig_override()
        session = await anext(gen)
        active_sessions += 1
        try:
            yield session
        except GeneratorExit:
            raise
        except BaseException as exc:
            rollbacks += 1
            await gen.athrow(exc)
        else:
            try:
                await anext(gen)
            except StopAsyncIteration:
                pass
        finally:
            await gen.aclose()
            active_sessions -= 1
            closes += 1

    monkeypatch.setitem(app.dependency_overrides, get_db, tracking_get_db)

    # 1) Cancellation after reading headers + page 1: session 1 already closed cleanly, no session left open.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("GET", f"/api/v1/reconciliation/{batch_id}/export") as stream_resp:
            assert stream_resp.status_code == 200
            aiter = stream_resp.aiter_bytes()
            first_chunk = await anext(aiter)
            assert b"Date,Direction,Bank Description" in first_chunk
            await aiter.aclose()

    assert active_sessions == 0
    assert closes >= 1

    # 2) Exception on page 2 triggers rollback and closes session 2 cleanly.
    orig_cursor_method = ReconciliationRepository.get_active_logs_cursor
    page_calls = 0

    async def fail_on_second_page(self, *, batch_id: str = "default", page_size: int = 1000, cursor=None):
        nonlocal page_calls
        page_calls += 1
        if page_calls == 2:
            raise SQLAlchemyError("mid-stream connection drop")
        return await orig_cursor_method(self, batch_id=batch_id, page_size=page_size, cursor=cursor)

    monkeypatch.setattr(ReconciliationRepository, "get_active_logs_cursor", fail_on_second_page)

    with pytest.raises(SQLAlchemyError, match="mid-stream connection drop"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get(f"/api/v1/reconciliation/{batch_id}/export")

    assert active_sessions == 0
    assert rollbacks == 1


async def test_csv_export_uses_async_session_factory_without_get_db_dependency(monkeypatch):
    """Production export path (no Depends override) must scope async_session_factory per page cleanly."""
    tx_date = datetime(2026, 3, 1, tzinfo=UTC)
    page1_log = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        batch_id="factory-batch",
        match_status="MATCHED",
        match_tier="TIER_1",
        confidence_score=1.0,
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="p1",
        human_action="AUTO",
        delta_amount=Decimal("0.00"),
        bank_transaction=SimpleNamespace(
            date=tx_date,
            direction="CREDIT",
            description="Page 1",
            utr="UTRP1",
            amount=Decimal("100.00"),
        ),
        rzp_settlement=None,
    )
    page2_log = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        batch_id="factory-batch",
        match_status="MATCHED",
        match_tier="TIER_1",
        confidence_score=1.0,
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="p2",
        human_action="AUTO",
        delta_amount=Decimal("0.00"),
        bank_transaction=SimpleNamespace(
            date=tx_date,
            direction="CREDIT",
            description="Page 2",
            utr="UTRP2",
            amount=Decimal("200.00"),
        ),
        rzp_settlement=None,
    )

    entered_sessions: list[bool] = []

    class DummyFactorySession:
        def __init__(self):
            self.active = False

        async def __aenter__(self):
            self.active = True
            entered_sessions.append(True)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.active = False

    class FactoryRepo:
        def __init__(self, session):
            assert session.active is True
            self.session = session

        async def get_active_logs_cursor(self, *, batch_id: str, page_size: int = 1000, cursor=None):
            assert self.session.active is True
            if cursor is None:
                return [page1_log], (tx_date, page1_log.id)
            return [page2_log], None

    monkeypatch.delitem(app.dependency_overrides, get_db, raising=False)
    monkeypatch.setattr(reconciliation_api, "async_session_factory", DummyFactorySession)
    monkeypatch.setattr(reconciliation_api, "ReconciliationRepository", FactoryRepo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/reconciliation/factory-batch/export")

    assert resp.status_code == 200
    assert len(entered_sessions) == 2
    utrs = [row["Bank UTR"] for row in csv.DictReader(io.StringIO(resp.text, newline=""))]
    assert utrs == ["UTRP1", "UTRP2"]


async def test_csv_export_sanitizes_content_disposition_filename_and_preserves_batch_data(db_session):
    """Unsafe batch IDs must be sanitized in Content-Disposition while preserving the queried batch rows."""
    raw_batch_id = '..batch";evil\r\nX-Inject:1'
    db_session.add(_make_db_log(raw_batch_id, 0, status="MATCHED"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/reconciliation/{quote(raw_batch_id, safe='')}/export")

    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert disposition == "attachment; filename=recongrid_audit__batch__evil__X-Inject_1.csv"
    assert "\r" not in disposition and "\n" not in disposition and '"' not in disposition
    assert "x-inject" not in {k.lower() for k in resp.headers}

    rows = list(csv.DictReader(io.StringIO(resp.text, newline="")))
    assert len(rows) == 1
    assert rows[0]["Bank UTR"] == "UTR00000"
