"""Demo seeding & sample statement generator API Routes."""

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.common import ApiResponse
from sqlalchemy import delete
from app.models.bank_transaction import BankTransaction
from app.models.reconciliation_log import ReconciliationLog
from app.models.razorpay_settlement import RazorpaySettlement
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, to_decimal

router = APIRouter(prefix="/demo", tags=["Demo & Fixtures"])


@router.post("/reset", response_model=ApiResponse[dict])
async def reset_demo_dataset(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Clears all bank transactions and reconciliation logs for clean testing."""
    await db.execute(delete(ReconciliationLog).where(ReconciliationLog.batch_id == batch_id))
    await db.execute(delete(BankTransaction).where(BankTransaction.batch_id == batch_id))
    await db.execute(delete(RazorpaySettlement).where(RazorpaySettlement.is_test_mode == True))
    await db.commit()
    return ApiResponse.ok({"status": "reset", "batch_id": batch_id})


@router.post("/seed", response_model=ApiResponse[dict])
async def seed_demo_dataset(
    count: int = 60,
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Seeds a realistic 50+ record synthetic dataset covering all reconciliation tiers & edge cases."""
    bank_repo = BankRepository(db)
    setl_repo = SettlementRepository(db)
    recon_repo = ReconciliationRepository(db)
    engine = ReconciliationEngine(recon_repo)

    now = datetime.now(timezone.utc)

    # 1. Generate Razorpay settlements using standard 2% MDR + 18% GST fee formula
    s1_fee, s1_tax, s1_net = calculate_standard_fees(Decimal("100000.00"))
    s2_fee, s2_tax, s2_net = calculate_standard_fees(Decimal("45800.00"))
    s3_fee, s3_tax, s3_net = calculate_standard_fees(Decimal("127500.00"))
    s4_fee, s4_tax, s4_net = calculate_standard_fees(Decimal("34800.00"))
    s5_fee, s5_tax, s5_net = calculate_standard_fees(Decimal("50000.00"))
    s6_fee, s6_tax, s6_net = calculate_standard_fees(Decimal("75000.00"))
    s7_fee, s7_tax, s7_net = calculate_standard_fees(Decimal("85000.00"))
    s12_fee, s12_tax, s12_net = calculate_standard_fees(Decimal("100000.00"))

    settlements_data = [
        # Tier 1 Exact Matches (High volume clean settlements)
        {
            "settlement_id": "setl_Kjs9283jkd901",
            "amount": s1_net,
            "gross_amount": Decimal("100000.00"),
            "fees": s1_fee,
            "tax": s1_tax,
            "utr": "CMS002938491801",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=1),
            "raw_payload": {"description": "Daily settlement batch 901"},
            "is_test_mode": True,
        },
        {
            "settlement_id": "setl_Kjs9283jkd902",
            "amount": s2_net,
            "gross_amount": Decimal("45800.00"),
            "fees": s2_fee,
            "tax": s2_tax,
            "utr": "CMS002938491802",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=1),
            "raw_payload": {"description": "Daily settlement batch 902"},
            "is_test_mode": True,
        },
        {
            "settlement_id": "setl_Kjs9283jkd903",
            "amount": s3_net,
            "gross_amount": Decimal("127500.00"),
            "fees": s3_fee,
            "tax": s3_tax,
            "utr": "CMS002938491803",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=2),
            "raw_payload": {"description": "Daily settlement batch 903"},
            "is_test_mode": True,
        },
        {
            "settlement_id": "setl_Kjs9283jkd904",
            "amount": s4_net,
            "gross_amount": Decimal("34800.00"),
            "fees": s4_fee,
            "tax": s4_tax,
            "utr": "CMS002938491804",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=2),
            "raw_payload": {"description": "Daily settlement batch 904"},
            "is_test_mode": True,
        },
        # Tier 3 Fee Deduction (Bank received net, gross was in UTR record)
        {
            "settlement_id": "setl_Kjs9283jkd905",
            "amount": Decimal("50000.00"),
            "gross_amount": Decimal("50000.00"),
            "fees": s5_fee,
            "tax": s5_tax,
            "utr": "CMS002938491805",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=3),
            "raw_payload": {"description": "Order #4521 settlement batch 905"},
            "is_test_mode": True,
        },
        # Tier 3 Refund Adjusted (Refund clawback deducted)
        {
            "settlement_id": "setl_Kjs9283jkd906",
            "amount": s6_net,
            "gross_amount": Decimal("75000.00"),
            "fees": s6_fee,
            "tax": s6_tax,
            "utr": "CMS002938491806",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=3),
            "raw_payload": {
                "description": "Settlement with refund clawbacks",
                "refund_total": "5000.00",
            },
            "is_test_mode": True,
        },
        # Tier 3 FX Adjusted
        {
            "settlement_id": "setl_Kjs9283jkd907",
            "amount": s7_net,
            "gross_amount": Decimal("85000.00"),
            "fees": s7_fee,
            "tax": s7_tax,
            "utr": "CMS002938491807",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=4),
            "raw_payload": {
                "description": "International Stripe/USD payout cross settlement",
                "fx_fee": "1150.00",
            },
            "is_test_mode": True,
        },
        # Tier 3 Reversal / Debit
        {
            "settlement_id": "setl_Kjs9283jkd908",
            "amount": Decimal("15000.00"),
            "gross_amount": Decimal("15000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS002938491808",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=4),
            "raw_payload": {"description": "Chargeback debit reversal adjustment"},
            "is_test_mode": True,
        },
        # Tier 2 Fuzzy Match Target
        {
            "settlement_id": "setl_Kjs9283jkd909",
            "amount": Decimal("12450.00"),
            "gross_amount": Decimal("12450.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "RTGS983921092812",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=5),
            "raw_payload": {"description": "RTGS RAZORPAY SOFTWARE PRIVATE LIMITED BANGALORE"},
            "is_test_mode": True,
        },
        # Tier 0 Fallback Target (No UTR)
        {
            "settlement_id": "setl_Kjs9283jkd910",
            "amount": Decimal("78900.00"),
            "gross_amount": Decimal("78900.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "SETLNOUTR910",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=1),
            "raw_payload": {"description": "Batch transfer with non-standard UTR"},
            "is_test_mode": True,
        },
        # Conflict Target (Matches 2 bank rows)
        {
            "settlement_id": "setl_Kjs9283jkd911",
            "amount": Decimal("50000.00"),
            "gross_amount": Decimal("50000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS002938491811",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=2),
            "raw_payload": {"description": "Multi-candidate payout batch 911"},
            "is_test_mode": True,
        },
        # Section 194-O E-Commerce 1% TDS Target
        {
            "settlement_id": "setl_Kjs9283jkd912",
            "amount": s12_net,
            "gross_amount": Decimal("100000.00"),
            "fees": s12_fee,
            "tax": s12_tax,
            "utr": "CMS002938491812",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=3),
            "raw_payload": {"description": "E-commerce marketplace sales with Section 194-O TDS"},
            "is_test_mode": True,
        },
        # Batched Settlement Sub-payout 1
        {
            "settlement_id": "setl_Kjs9283jkd913",
            "amount": Decimal("60000.00"),
            "gross_amount": Decimal("60000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS002938491813",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=2),
            "raw_payload": {"description": "Batched morning payout cycle"},
            "is_test_mode": True,
        },
        # Batched Settlement Sub-payout 2
        {
            "settlement_id": "setl_Kjs9283jkd914",
            "amount": Decimal("40000.00"),
            "gross_amount": Decimal("40000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS002938491814",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=2),
            "raw_payload": {"description": "Batched evening payout cycle"},
            "is_test_mode": True,
        },
    ]

    # Additional standard settlements to scale up to count using standard 2% MDR + 18% GST formula
    for i in range(15, count + 1):
        amt = Decimal(f"{(i * 3750) % 85000 + 10000}.00")
        fees, tax, net_amt = calculate_standard_fees(amt)
        settlements_data.append({
            "settlement_id": f"setl_Kjs9283jkd{i:03d}",
            "amount": net_amt,
            "gross_amount": amt,
            "fees": fees,
            "tax": tax,
            "utr": f"CMS0029384918{i:02d}",
            "status": "processed",
            "settlement_created_at": now - timedelta(days=(i % 15) + 1),
            "raw_payload": {"description": f"Standard automated settlement batch {i}"},
            "is_test_mode": True,
        })

    saved_settlements = []
    for s in settlements_data:
        setl, _ = await setl_repo.upsert_settlement(s)
        saved_settlements.append(setl)

    # 2. Generate Bank statement transactions matching standard calculations
    bank_txs_data = [
        # Exact Matches
        {
            "date": now - timedelta(days=1),
            "amount": s1_net,
            "direction": "CREDIT",
            "utr": "CMS002938491801",
            "description": "CMS/002938491801/HDFC/RAZORPAY SOFTWARE PVT",
            "row_hash": "hash_demo_001",
        },
        {
            "date": now - timedelta(days=1),
            "amount": s2_net,
            "direction": "CREDIT",
            "utr": "CMS002938491802",
            "description": "CMS/002938491802/HDFC/RAZORPAY PAYOUT",
            "row_hash": "hash_demo_002",
        },
        {
            "date": now - timedelta(days=2),
            "amount": s3_net,
            "direction": "CREDIT",
            "utr": "CMS002938491803",
            "description": "NEFT/CMS002938491803/RAZORPAY SETTLEMENT",
            "row_hash": "hash_demo_003",
        },
        {
            "date": now - timedelta(days=2),
            "amount": s4_net,
            "direction": "CREDIT",
            "utr": "CMS002938491804",
            "description": "RTGS/CMS002938491804/RAZORPAY",
            "row_hash": "hash_demo_004",
        },
        # Fee deduction (Bank shows net against gross)
        {
            "date": now - timedelta(days=3),
            "amount": s5_net,
            "direction": "CREDIT",
            "utr": "CMS002938491805",
            "description": "CMS/002938491805/RAZORPAY ORDER 4521 NET",
            "row_hash": "hash_demo_005",
        },
        # Refund adjustment (Bank shows 68,230.00 = 73,230.00 - 5,000.00)
        {
            "date": now - timedelta(days=3),
            "amount": s6_net - Decimal("5000.00"),
            "direction": "CREDIT",
            "utr": "CMS002938491806",
            "description": "CMS/002938491806/RAZORPAY REFUND ADJ BATCH",
            "row_hash": "hash_demo_006",
        },
        # FX adjusted (Bank shows 81,844.00 = 82,994.00 - 1,150.00)
        {
            "date": now - timedelta(days=4),
            "amount": s7_net - Decimal("1150.00"),
            "direction": "CREDIT",
            "utr": "CMS002938491807",
            "description": "CMS/002938491807/RAZORPAY CROSS CURRENCY",
            "row_hash": "hash_demo_007",
        },
        # Reversal Debit (Bank shows debit of 15,000.00)
        {
            "date": now - timedelta(days=4),
            "amount": Decimal("15000.00"),
            "direction": "DEBIT",
            "utr": "CMS002938491808",
            "description": "DR/CMS002938491808/RAZORPAY CHARGEBACK REVERSAL",
            "row_hash": "hash_demo_008",
        },
        # Tier 2 Fuzzy match (Malformed UTR in bank description)
        {
            "date": now - timedelta(days=5),
            "amount": Decimal("12450.00"),
            "direction": "CREDIT",
            "utr": None,
            "description": "RTGS RAZORPAY SOFTWARE PRIVATE LIMITED BANGLORE 94",
            "row_hash": "hash_demo_009",
        },
        # Tier 0 Fallback (Missing UTR completely, exact amount 78,900.00)
        {
            "date": now - timedelta(days=1),
            "amount": Decimal("78900.00"),
            "direction": "CREDIT",
            "utr": None,
            "description": "DIRECT CR BATCH CLEARING MISC",
            "row_hash": "hash_demo_010",
        },
        # Conflict Row 1
        {
            "date": now - timedelta(days=2),
            "amount": Decimal("50000.00"),
            "direction": "CREDIT",
            "utr": "CMS002938491811",
            "description": "CMS/002938491811/HDFC/BRANCH A",
            "row_hash": "hash_demo_011_a",
        },
        # Conflict Row 2 (Duplicate claim on settlement 911)
        {
            "date": now - timedelta(days=2),
            "amount": Decimal("50000.00"),
            "direction": "CREDIT",
            "utr": "CMS002938491811",
            "description": "CMS/002938491811/HDFC/BRANCH B",
            "row_hash": "hash_demo_011_b",
        },
        # Section 194-O E-Commerce 1% TDS Bank Credit (100000 - 2000 fee - 360 tax - 1000 TDS = 96640.00)
        {
            "date": now - timedelta(days=3),
            "amount": s12_net - Decimal("1000.00"),
            "direction": "CREDIT",
            "utr": "CMS002938491812",
            "description": "CMS/002938491812/HDFC/ECOM SALES NET 194O",
            "row_hash": "hash_demo_012",
        },
        # Batched Single Bank Credit matching setl_913 + setl_914 (60k + 40k = 100k)
        {
            "date": now - timedelta(days=2),
            "amount": Decimal("100000.00"),
            "direction": "CREDIT",
            "utr": None,
            "description": "DIRECT CR BATCHED CLEARING 913 914",
            "row_hash": "hash_demo_013_batched",
        },
        # Unresolved Exceptions (No matching Razorpay records)
        {
            "date": now - timedelta(days=6),
            "amount": Decimal("18450.00"),
            "direction": "CREDIT",
            "utr": "ICIC009283921099",
            "description": "NEFT/ICIC009283921099/UNKNOWN MERCHANT TRANSFER",
            "row_hash": "hash_demo_exc_1",
        },
        {
            "date": now - timedelta(days=7),
            "amount": Decimal("6200.00"),
            "direction": "CREDIT",
            "utr": "SBI002938491899",
            "description": "RTGS/SBI002938491899/DIRECT CLIENT INWARD",
            "row_hash": "hash_demo_exc_2",
        },
    ]

    # Additional standard bank transactions matching the extra settlements
    for i in range(15, count + 1):
        target_s = saved_settlements[i - 1]
        bank_txs_data.append({
            "date": target_s.settlement_created_at,
            "amount": to_decimal(target_s.amount),
            "direction": "CREDIT",
            "utr": target_s.utr,
            "description": f"CMS/{target_s.utr}/HDFC/RAZORPAY PAYOUT {i}",
            "row_hash": f"hash_demo_{i:03d}",
        })

    saved_bank_txs = []
    for b in bank_txs_data:
        b["batch_id"] = batch_id
        b["raw_csv_row"] = {
            "sample": True,
            "date": b["date"].isoformat() if isinstance(b["date"], (datetime, date)) else str(b["date"]),
            "amount": str(b["amount"]),
            "direction": b["direction"],
            "description": b["description"],
            "utr": b.get("utr"),
        }
        tx, _ = await bank_repo.upsert_transaction(b)
        saved_bank_txs.append(tx)

    # 3. Run reconciliation engine
    reconciled_logs = await engine.reconcile_batch(
        bank_transactions=saved_bank_txs,
        settlements=saved_settlements,
        batch_id=batch_id,
    )

    summary = await recon_repo.get_summary_metrics(batch_id)

    return ApiResponse.ok({
        "status": "seeded",
        "total_settlements": len(saved_settlements),
        "total_bank_transactions": len(saved_bank_txs),
        "reconciled_logs": len(reconciled_logs),
        "summary": summary,
    })


@router.get("/sample-statement")
async def download_sample_csv(
    bank: str = "HDFC",
):
    """Generates a downloadable sample bank statement CSV for live testing (HDFC / ICICI / SBI)."""
    output = io.StringIO()
    writer = csv.writer(output)
    now = datetime.now(timezone.utc)

    if bank.upper() == "ICICI":
        writer.writerow(["Transaction Date", "Transaction Reference Number", "Transaction Remarks", "Deposit Amount (INR )", "Withdrawal Amount (INR )"])
        writer.writerow([(now - timedelta(days=1)).strftime("%d/%m/%Y"), "CMS002938491801", "CMS/002938491801/RAZORPAY", "97640.00", "0.00"])
        writer.writerow([(now - timedelta(days=2)).strftime("%d/%m/%Y"), "CMS002938491805", "CMS/002938491805/RAZORPAY ORDER 4521", "48820.00", "0.00"])
        writer.writerow([(now - timedelta(days=3)).strftime("%d/%m/%Y"), "CMS002938491806", "CMS/002938491806/REFUND BATCH", "68230.00", "0.00"])
        writer.writerow([(now - timedelta(days=4)).strftime("%d/%m/%Y"), "CMS002938491808", "CMS/002938491808/CHARGEBACK", "0.00", "15000.00"])
        writer.writerow([(now - timedelta(days=5)).strftime("%d/%m/%Y"), "", "RTGS RAZORPAY SOFTWARE PRIVATE LIMITED", "12450.00", "0.00"])
    elif bank.upper() == "SBI":
        writer.writerow(["Txn Date", "Ref No./Cheque No.", "Description", "Credit", "Debit"])
        writer.writerow([(now - timedelta(days=1)).strftime("%d-%m-%Y"), "CMS002938491801", "RAZORPAY PAYOUT 901", "97640.00", ""])
        writer.writerow([(now - timedelta(days=2)).strftime("%d-%m-%Y"), "CMS002938491805", "RAZORPAY ORDER 4521", "48820.00", ""])
        writer.writerow([(now - timedelta(days=3)).strftime("%d-%m-%Y"), "CMS002938491806", "RAZORPAY SETTLEMENT", "68230.00", ""])
        writer.writerow([(now - timedelta(days=4)).strftime("%d-%m-%Y"), "", "DIRECT TRANSFER NO UTR", "78900.00", ""])
    else:  # HDFC format
        writer.writerow(["Date", "Chq/Ref No.", "Narration", "Deposit Amt.", "Withdrawal Amt."])
        writer.writerow([(now - timedelta(days=1)).strftime("%d/%m/%Y"), "CMS002938491801", "CMS/002938491801/HDFC/RAZORPAY", "97640.00", "0.00"])
        writer.writerow([(now - timedelta(days=1)).strftime("%d/%m/%Y"), "CMS002938491802", "CMS/002938491802/HDFC/RAZORPAY", "44719.12", "0.00"])
        writer.writerow([(now - timedelta(days=2)).strftime("%d/%m/%Y"), "CMS002938491805", "CMS/002938491805/RAZORPAY ORDER 4521", "48820.00", "0.00"])
        writer.writerow([(now - timedelta(days=3)).strftime("%d/%m/%Y"), "CMS002938491806", "CMS/002938491806/RAZORPAY REFUND", "68230.00", "0.00"])
        writer.writerow([(now - timedelta(days=4)).strftime("%d/%m/%Y"), "CMS002938491808", "CMS/002938491808/REVERSAL", "0.00", "15000.00"])
        writer.writerow([(now - timedelta(days=5)).strftime("%d/%m/%Y"), "", "RTGS RAZORPAY SOFTWARE BANGLORE", "12450.00", "0.00"])
        writer.writerow([(now - timedelta(days=6)).strftime("%d/%m/%Y"), "ICIC009283921099", "UNKNOWN DIRECT CREDIT", "18450.00", "0.00"])

    csv_text = output.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=sample_{bank.lower()}_statement.csv"},
    )
