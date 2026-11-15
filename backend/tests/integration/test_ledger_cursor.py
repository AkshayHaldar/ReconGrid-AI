from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository


async def seed(session, count=7, batch="default", start=1):
    logs = []
    for i in range(start, start + count):
        bank = BankTransaction(
            id=str(UUID(int=i)),
            batch_id=batch,
            row_hash=f"{batch}-{i}",
            date=datetime(2026, 1, 1),
            amount=Decimal(i),
            utr=None if i % 3 == 0 else f"UTR{i:04}",
            description=f"Synthetic row {i}",
        )
        log = ReconciliationLog(
            id=str(UUID(int=10000 + i)),
            bank_transaction=bank,
            batch_id=batch,
            match_status="SUGGESTED" if i % 2 else "MATCHED",
            match_tier="TIER_1",
            diagnostic_type="EXACT_MATCH" if i % 2 else "UNRESOLVED",
            diagnostic_note="Synthetic",
        )
        session.add(log)
        logs.append(log)
    await session.commit()
    return logs


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("sort", ["date", "bank_amount", "rzp_amount", "delta_amount", "bank_utr"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_all_sort_orders_walk_ties_nulls_without_duplicates(db_session, client, sort, direction):
    rows = await seed(db_session)
    await seed(db_session, 1, batch="other", start=100)
    params = {"limit": 2, "sort": sort, "direction": direction}
    seen = []
    while True:
        response = await client.get("/api/v1/reconciliation/default/records", params=params)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total_count"] == (None if "cursor" in params else 7)
        assert len(data["records"]) <= 2
        seen.extend(r["id"] for r in data["records"])
        if not data["has_more"]:
            assert data["next_cursor"] is None
            break
        params["cursor"] = data["next_cursor"]
    assert len(seen) == len(set(seen)) == len(rows)
    repo = ReconciliationRepository(db_session)
    expected, _, _, _ = await repo.get_log_window("default", sort=sort, direction=direction, limit=20)
    assert seen == [r.id for r in expected]


async def test_insert_and_delete_before_boundary_do_not_shift_remaining_rows(db_session, client):
    rows = await seed(db_session)
    first = (await client.get("/api/v1/reconciliation/default/records", params={"limit": 2})).json()["data"]
    await seed(db_session, 1, start=100)
    await db_session.delete(rows[-1])
    await db_session.commit()
    rest = (
        await client.get("/api/v1/reconciliation/default/records", params={"limit": 20, "cursor": first["next_cursor"]})
    ).json()["data"]
    assert [r["id"] for r in rest["records"]] == [r.id for r in reversed(rows[:-2])]


@pytest.mark.parametrize(
    "change",
    [
        {"status": "MATCHED"},
        {"q": "other"},
        {"diagnostic": "UNRESOLVED"},
        {"sort": "bank_amount"},
        {"direction": "asc"},
    ],
)
async def test_cursor_is_bound_to_filters_and_sort(db_session, client, change):
    await seed(db_session)
    first = (await client.get("/api/v1/reconciliation/default/records", params={"limit": 2})).json()["data"]
    response = await client.get(
        "/api/v1/reconciliation/default/records", params={"limit": 2, "cursor": first["next_cursor"], **change}
    )
    assert response.status_code == 400
    assert "cursor" in response.text


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-json"},
        {"cursor": "x" * 2049},
        {"limit": 0},
        {"limit": 201},
        {"sort": "sql"},
        {"direction": "sideways"},
    ],
)
async def test_invalid_pagination_is_rejected(client, params):
    response = await client.get("/api/v1/reconciliation/default/records", params=params)
    assert response.status_code in (400, 422)


async def test_diagnostic_filter_applies_before_pagination_and_legacy_still_works(db_session, client):
    await seed(db_session)
    data = (
        await client.get("/api/v1/reconciliation/default/records", params={"limit": 2, "diagnostic": "EXACT_MATCH"})
    ).json()["data"]
    assert data["total_count"] == 4
    assert all(r["diagnostic_type"] == "EXACT_MATCH" for r in data["records"])
    legacy = (await client.get("/api/v1/reconciliation/default/records", params={"page": 2, "page_size": 2})).json()[
        "data"
    ]
    assert legacy["total_count"] == 7
    assert legacy["page"] == 2 and len(legacy["records"]) == 2


async def test_citation_anchor_starts_at_record_and_respects_batch(db_session, client):
    rows = await seed(db_session)
    response = await client.get("/api/v1/reconciliation/default/records", params={"limit": 2, "anchor_id": rows[2].id})
    assert response.json()["data"]["records"][0]["id"] == rows[2].id
    assert (
        await client.get("/api/v1/reconciliation/other/records", params={"limit": 2, "anchor_id": rows[2].id})
    ).status_code == 404


async def test_continuation_query_uses_seek_limit_without_offset_or_count(db_session):
    await seed(db_session, 250)
    repo = ReconciliationRepository(db_session)
    _, _, cursor, _ = await repo.get_log_window("default", limit=100)
    statements = []
    engine = db_session.bind.sync_engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(str(context.compiled.statement) if context.compiled else statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        rows, total, _, _ = await repo.get_log_window("default", limit=100, cursor=cursor)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(rows) == 100 and total is None
    assert all("OFFSET" not in sql.upper() and "COUNT(" not in sql.upper() for sql in statements)
    assert any("LIMIT" in sql and "reconciliation_logs.id <" in sql for sql in statements)


async def test_repository_rejects_invalid_seek_arguments_and_cursor_anchor_combination(db_session):
    repo = ReconciliationRepository(db_session)
    for params in (
        {"limit": 0},
        {"sort": "unknown"},
        {"direction": "unknown"},
        {"cursor": "opaque", "anchor_id": str(UUID(int=1))},
    ):
        with pytest.raises(ValueError):
            await repo.get_log_window("default", **params)


async def test_settlement_candidates_are_complete_and_query_scoped(db_session):
    from app.models.razorpay_settlement import RazorpaySettlement

    rows = await seed(db_session)
    settlement = RazorpaySettlement(settlement_id="synthetic", amount=Decimal("1.00"))
    db_session.add(settlement)
    await db_session.flush()
    for row in rows[:3]:
        row.rzp_settlement_id = settlement.id
        row.match_status = "CONFLICT"
    await db_session.commit()
    repo = ReconciliationRepository(db_session)
    found, count, cursor, more = await repo.get_log_window(
        "default", status_filter="CONFLICT", settlement_id=settlement.id, limit=2
    )
    assert count == 3 and more
    remainder, _, _, _ = await repo.get_log_window(
        "default", status_filter="CONFLICT", settlement_id=settlement.id, limit=2, cursor=cursor
    )
    assert {row.id for row in found + remainder} == {row.id for row in rows[:3]}
    with pytest.raises(ValueError):
        await repo.get_log_window("other", status_filter="CONFLICT", settlement_id=settlement.id, cursor=cursor)
    anchored, _, _, _ = await repo.get_log_window("default", anchor_id=rows[2].id, limit=2)
    assert anchored[0].id == rows[2].id
    with pytest.raises(LookupError):
        await repo.get_log_window("other", anchor_id=rows[2].id, limit=2)
