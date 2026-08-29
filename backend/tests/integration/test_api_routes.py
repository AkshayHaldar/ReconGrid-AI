"""Integration tests for all REST API endpoints: bank, razorpay, reconciliation, qa, and demo."""

import io
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app


@pytest.mark.asyncio
async def test_bank_upload_and_transactions_flow(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload sample CSV
        csv_content = (
            "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
            "24/08/2026,CMS002938491805,CMS/CMS002938491805/RAZORPAY ORDER 4521,49100.00,0.00\n"
        )
        files = {"file": ("statement.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        resp = await client.post("/api/v1/bank/upload", data={"batch_id": "api_test_batch"}, files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["inserted_count"] == 1

        # 2. Get bank transactions
        tx_resp = await client.get("/api/v1/bank/transactions?batch_id=api_test_batch")
        assert tx_resp.status_code == 200
        tx_data = tx_resp.json()
        assert tx_data["success"] is True
        assert len(tx_data["data"]) == 1
        assert tx_data["data"][0]["amount"] == "49100.00"


@pytest.mark.asyncio
async def test_razorpay_sync_and_list_endpoints(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sync settlements
        sync_resp = await client.post(
            "/api/v1/razorpay/sync?batch_id=api_test_batch",
            json={"count": 10, "skip": 0, "force_resync": False},
        )
        assert sync_resp.status_code == 200
        data = sync_resp.json()
        assert data["success"] is True

        # 2. List settlements
        list_resp = await client.get("/api/v1/razorpay/settlements")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["success"] is True


@pytest.mark.asyncio
async def test_reconciliation_status_records_and_actions(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed test batch
        await client.post("/api/v1/demo/seed?count=15")

        # 1. Get batch status
        status_resp = await client.get("/api/v1/reconciliation/default/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["success"] is True
        assert status_data["data"]["total_records"] > 0

        # 2. Get records with search & filter
        records_resp = await client.get("/api/v1/reconciliation/default/records?status=ALL&q=4521&page=1&page_size=10")
        assert records_resp.status_code == 200
        records_data = records_resp.json()
        assert records_data["success"] is True
        records = records_data["data"]["records"]
        assert len(records) > 0
        rec_id = records[0]["id"]

        # 3. Approve action
        appr_resp = await client.post(
            f"/api/v1/reconciliation/records/{rec_id}/approve",
            json={"note": "Approved by auditor"},
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["data"]["match_status"] == "MATCHED"

        # 4. Deny action
        deny_resp = await client.post(
            f"/api/v1/reconciliation/records/{rec_id}/deny",
            json={"note": "Rejected discrepancy"},
        )
        assert deny_resp.status_code == 200
        assert deny_resp.json()["data"]["match_status"] == "EXCEPTION"

        # 5. Resolve conflict action
        resolve_resp = await client.post(
            f"/api/v1/reconciliation/records/{rec_id}/resolve-conflict",
            json={"chosen_settlement_id": "setl_chosen_123", "note": "Resolved manual match"},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["data"]["match_status"] == "MATCHED"

        # 6. Action on nonexistent record (404s)
        assert (await client.post("/api/v1/reconciliation/records/nonexistent/approve", json={"note": "Test"})).status_code == 404
        assert (await client.post("/api/v1/reconciliation/records/nonexistent/deny", json={"note": "Test"})).status_code == 404
        assert (await client.post("/api/v1/reconciliation/records/nonexistent/resolve-conflict", json={"chosen_settlement_id": "s1"})).status_code == 404

        # 7. Export CSV
        export_resp = await client.get("/api/v1/reconciliation/default/export")
        assert export_resp.status_code == 200
        assert "text/csv" in export_resp.headers.get("content-type", "")
        assert "Date,Direction,Bank Description" in export_resp.text


@pytest.mark.asyncio
async def test_conflict_locking_and_competing_resolution_flow(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Seed demo settlements first so settlements exist in DB
        await client.post("/api/v1/demo/seed?count=15")

        # 2. Upload CSV with 2 duplicate UTR entries claiming same settlement
        csv_content = (
            "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
            "24/08/2026,CMS002938491811,CMS/002938491811/BRANCH A,50000.00,0.00\n"
            "24/08/2026,CMS002938491811,CMS/002938491811/BRANCH B,50000.00,0.00\n"
        )
        files = {"file": ("statement.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        await client.post("/api/v1/bank/upload", data={"batch_id": "conflict_test_batch"}, files=files)

        # 3. Get records - verify both are in CONFLICT
        resp = await client.get("/api/v1/reconciliation/conflict_test_batch/records?status=CONFLICT")
        assert resp.status_code == 200
        conflicts = resp.json()["data"]["records"]
        assert len(conflicts) == 2
        rec_a, rec_b = conflicts[0], conflicts[1]
        assert rec_a["match_status"] == "CONFLICT"
        assert rec_b["match_status"] == "CONFLICT"
        target_setl_id = rec_a["rzp_settlement_id"] or "setl_Kjs9283jkd911"

        # 4. Resolve conflict on rec_a allocating the settlement
        res_resp = await client.post(
            f"/api/v1/reconciliation/records/{rec_a['id']}/resolve-conflict",
            json={"chosen_settlement_id": target_setl_id, "note": "Verified with branch A"},
        )
        assert res_resp.status_code == 200
        resolved_a = res_resp.json()["data"]
        assert resolved_a["match_status"] == "MATCHED"
        assert resolved_a["human_action"] == "RESOLVED"

        # 5. Check rec_b: it must be automatically transitioned to EXCEPTION (unlinked)
        resp_all = await client.get("/api/v1/reconciliation/conflict_test_batch/records?status=ALL")
        all_recs = resp_all.json()["data"]["records"]
        updated_b = next(r for r in all_recs if r["id"] == rec_b["id"])
        assert updated_b["match_status"] == "EXCEPTION"
        assert updated_b["human_action"] == "AUTO_DISPLACED"
        assert updated_b["rzp_settlement_db_id"] is None

        # 6. Test dismissing a conflict as EXCEPTION
        dismiss_csv = (
            "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
            "24/08/2026,CMS002938491899,CMS/002938491899/DISMISS TEST,10000.00,0.00\n"
        )
        files2 = {"file": ("statement.csv", io.BytesIO(dismiss_csv.encode("utf-8")), "text/csv")}
        await client.post("/api/v1/bank/upload", data={"batch_id": "dismiss_batch"}, files=files2)
        recs_resp = await client.get("/api/v1/reconciliation/dismiss_batch/records?status=ALL")
        dismiss_target = recs_resp.json()["data"]["records"][0]

        dis_resp = await client.post(
            f"/api/v1/reconciliation/records/{dismiss_target['id']}/resolve-conflict",
            json={"chosen_settlement_id": "DISMISS", "note": "Unlink completely"},
        )
        assert dis_resp.status_code == 200
        assert dis_resp.json()["data"]["match_status"] == "EXCEPTION"
        assert dis_resp.json()["data"]["human_action"] == "DISMISSED"
        assert dis_resp.json()["data"]["rzp_settlement_db_id"] is None


@pytest.mark.asyncio
async def test_qa_and_demo_endpoints(db_session: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed batch first
        await client.post("/api/v1/demo/seed?count=15")

        # 1. Ask question
        ask_resp = await client.post(
            "/api/v1/qa/ask",
            json={"query": "Why was order #4521 short?"},
        )
        assert ask_resp.status_code == 200
        assert ask_resp.json()["success"] is True

        # 2. Get QA history
        hist_resp = await client.get("/api/v1/qa/history")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert hist_data["success"] is True
        assert len(hist_data["data"]) >= 1

        # 3. Sample statements (HDFC, ICICI, SBI)
        sample_hdfc = await client.get("/api/v1/demo/sample-statement?bank=HDFC")
        assert sample_hdfc.status_code == 200
        assert "text/csv" in sample_hdfc.headers.get("content-type", "")

        sample_icici = await client.get("/api/v1/demo/sample-statement?bank=ICICI")
        assert sample_icici.status_code == 200

        sample_sbi = await client.get("/api/v1/demo/sample-statement?bank=SBI")
        assert sample_sbi.status_code == 200
