"""CLI Seed script to generate 50+ synthetic transactions for Track 04 judging demonstration."""

import argparse
import asyncio
from decimal import Decimal
import httpx


async def main(count: int, base_url: str):
    print(f"[*] Seeding {count} synthetic transactions on {base_url}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{base_url}/api/v1/demo/seed?count={count}")
            if resp.status_code == 200:
                data = resp.json()["data"]
                summary = data["summary"]
                print("[+] Seeding complete!")
                print(f"    - Bank Transactions : {data['total_bank_transactions']}")
                print(f"    - Settlements       : {data['total_settlements']}")
                print(f"    - Reconciled Logs   : {data['reconciled_logs']}")
                print(f"    - Match Rate %      : {summary['match_rate_percentage']}%")
                print(f"    - Total Ingested    : ₹ {summary['total_ingested_amount']}")
                print(f"    - Total Reconciled  : ₹ {summary['total_reconciled_amount']}")
                print(f"    - Exceptions        : {summary['exception_count']} (₹ {summary['total_exception_amount']})")
                print(f"    - Suggested Matches : {summary['suggested_count']}")
                print(f"    - Conflicts         : {summary['conflict_count']}")
            else:
                print(f"[-] Seeding failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[-] Error connecting to backend: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic transactions for ReconGrid AI")
    parser.add_argument("--count", type=int, default=60, help="Number of records to seed (default: 60)")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="Backend API base URL")
    args = parser.parse_args()

    asyncio.run(main(args.count, args.url))
