# 🎯 Project Overview — ReconGrid AI

## 1. What Is ReconGrid AI?

**ReconGrid AI** is a settlement reconciliation and discrepancy-diagnostic engine built for finance teams using Razorpay — especially B2B SaaS companies and high-volume D2C brands.

Every time you run it, it gives you three clear, verifiable things:

1. **Automated Match Rate %** — how much was resolved automatically (`(matched + approved suggested) ÷ total records`)
2. **Total ₹ Reconciled** — the exact amount reconciled, with an audit trail back to every source row
3. **An Honest Exception List** — every single row that couldn't be resolved, verbatim, with a reason code

This is a **verification and audit tool first**. AI is used only for plain-English explanations of already-computed facts — never for math, matching, or financial decisions.

---

## 2. Why This Problem Matters

Talk to any SME founder, finance lead, or Chartered Accountant handling Razorpay, and they'll tell you the same things:

* **Excel Gridlock:** They spend 15–30 hours every month manually comparing bank UTRs against Razorpay payout reports across hundreds or thousands of rows.
* **The Math Is Never Simple:** Settlement amounts rarely match gross transaction amounts. Platform fees, 18% GST, mid-cycle refunds, chargebacks, and gateway reserves all create deltas that have to be figured out one by one.
* **Human Error & Delayed Closes:** Doing this manually leads to missed discrepancies, unlocated funds, and delayed month-end closes.
* **Data Silos:** Bank statement formats vary wildly (HDFC, ICICI, SBI, Axis all format differently), and they don't talk to payment gateway logs.

---

## 3. How ReconGrid AI Solves It

A four-stage deterministic pipeline with bounded AI assistance:

```
[ Bank CSV ] ──► [ 1. Ingest & Normalize ] ──┐
                                             ├──► [ 3. Multi-Tier Matcher ] ──► [ 4. Audit & Exceptions ]
[ Razorpay ] ──► [ 2. Sync Settlements ]  ──┘                                      │
                                                                                   ▼
                                                                           [ 5. Q&A Agent ]
```

1. **Ingest & Normalize:** Parses bank CSVs into standard records (`date`, `amount`, `utr`, `direction`), with a fallback for statements lacking a clean UTR.
2. **Sync Settlements:** Pulls settlements and refunds via Razorpay's REST API (paginated, with backoff) and listens for real-time webhooks (HMAC-verified, idempotent).
3. **Multi-Tier Matching Engine:**
   - **Tier 1 (Exact):** UTR match + exact amount match → `MATCHED`
   - **Tier 0 (Fallback):** Date window (±2 days) + exact amount → `SUGGESTED` (human approves)
   - **Tier 2 (Fuzzy):** Descriptor string similarity (≥90%) → `SUGGESTED` (human reviews)
   - **Tier 3 (Diagnostics):** Explains deltas: fees + GST, refunds, FX adjustments → diagnostic logged or `EXCEPTION`
4. **Audit & Exception Reporting:** Every decision is written to an append-only log. Every record ends in a clear state (`MATCHED`, `SUGGESTED`, `CONFLICT`, or `EXCEPTION`).
5. **Settlement Q&A Agent:** Finance users can ask questions in plain English (*"Why didn't order #4521 settle correctly?"*). The system retrieves the exact audit record, has the LLM explain it in plain language, and runs a guardrail to make sure the LLM didn't invent any numbers.

---

## 4. When the System Stops & Asks a Human

The engine **never guesses**. It stops and asks for human review whenever:

- A discrepancy can't be explained by fees + GST, refund batching, or FX within the ±₹1.00 tolerance
- A fuzzy match confidence is below 90%
- One settlement matches more than one bank row (conflict — locked until resolved)
- A webhook fails signature verification (rejected immediately, logged)
- Razorpay API retries exceed 5 attempts (halts and alerts rather than looping forever)

---

## 5. What We'll Show the Judges

| Output | What It Proves |
|---|---|
| **Match rate %** on 50+ record synthetic batch | Meets the Track 04 hackathon requirement |
| **Total ₹ reconciled vs. ingested** | Shows the financial scale handled |
| **Unedited exception list** | Proves the tool is honest and doesn't sweep errors under the rug |
| **End-to-end audit trail** | Shows one record traced: raw CSV row → matched settlement → diagnostic → log entry |
| **Q&A Agent demo** | Shows the plain-English explanation layer working with guardrails |

---

## 6. Who This Is For

- **SME Founders & Finance Ops:** Need payout and fee visibility without hiring a dedicated reconciliation team
- **Chartered Accountants & Accounting Firms:** Manage multi-client month-end closes and need GST input-tax-credit verification
- **D2C & E-Commerce Brands:** High daily transaction volumes, frequent chargebacks, instant refunds

---

## 7. Out of Scope for v1 (Keeping It Honest)

To keep the scope realistic for a 14-day buildathon:
- ❌ Multi-bank-account netting/consolidation across different accounts
- ❌ Non-INR settlement currencies beyond basic FX-delta detection
- ❌ Direct GST filing/e-invoicing (we do diagnostics, not filing)
- ❌ Multi-gateway support (Razorpay only for v1)

---

## 8. Real-World Edge Cases Handled

1. **Split / Batched Settlements:** A bank credit might bundle multiple Razorpay settlements, or a large settlement might be split across two days. The engine groups candidate settlements by date-window + summed amount before declaring an exception.
2. **Settlement Reversals:** Razorpay sometimes debits an account days after settlement (chargeback, hold reversal). The bank statement shows a debit, not a credit. Ingestion explicitly tracks `CREDIT` vs `DEBIT` rather than assuming everything is a credit.
3. **Cross-Currency Settlements:** Foreign transactions have an FX component on top of fees + GST. Tier 3 includes an FX-adjustment check before falling back to unresolved.
