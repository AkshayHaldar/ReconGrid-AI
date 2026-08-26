# ReconGrid AI — Project Overview

## 1. Executive Summary
**ReconGrid AI** is a settlement reconciliation and discrepancy-diagnostic engine for B2B SaaS and high-volume D2C finance teams using Razorpay. It ingests bank statement CSVs, pulls live Razorpay settlement and refund data, runs a deterministic multi-tier matching pipeline, and produces three verifiable outputs on every run:

1. An **automated match rate %** (matched + suggested-and-approved ÷ total records).
2. A **total ₹ reconciled** figure with full audit trail back to source rows.
3. An **honest, unedited exception list** — everything the engine could not resolve, with a reason.

This is a verification and audit tool first. LLM/AI components (if any) are used only where deterministic code demonstrably cannot resolve a case — never for arithmetic, matching, or money decisions.

---

## 2. The Problem
For SMEs, scale-ups, and Chartered Accountants, settlement reconciliation is a recurring high-friction, error-prone workflow:

* **Manual Excel Gridlock** — finance managers spend 15–30 hours/month cross-referencing bank UTRs against Razorpay payout reports across hundreds or thousands of rows.
* **Non-trivial discrepancy math** — settlement amounts rarely match gross transaction amounts due to platform fees, 18% GST, chargebacks, and mid-cycle refund clawbacks.
* **High human error, delayed closes** — manual matching produces reconciliation gaps, unlocated funds, and audit risk.
* **Disparate data silos** — bank statements (varying formats) are disconnected from gateway API logs, with no automated source of truth.

---

## 3. The Solution
A four-stage deterministic pipeline, with narrow, explicitly-bounded AI assistance:

1. **Intelligent Ingestion** — parse bank statement CSVs (HDFC, ICICI, SBI, Axis, Kotak, etc.) into canonical records (date, amount, UTR/reference, description), with a documented fallback path for statements that lack a clean UTR field entirely.
2. **Automated Razorpay Pipeline** — pull settlements and refunds via the REST API with cursor pagination, exponential backoff, and a hard retry ceiling; ingest real-time `settlement.processed` webhooks idempotently.
3. **Multi-Tier Matching Engine**:
   * **Tier 0 (Fallback Match)** — date-window + exact-amount match, used when UTR is missing or non-standard.
   * **Tier 1 (Exact Match)** — UTR + exact net settlement amount.
   * **Tier 2 (Fuzzy Match)** — string similarity (≥90% confidence) on descriptor text for malformed/truncated UTRs.
   * **Tier 3 (Diagnostics)** — deterministic delta analysis: fees + GST, refund clawbacks, FX adjustment, settlement reversal.
4. **Audit & Exception Reporting** — every match, suggestion, and diagnostic decision is written to an append-only log with the inputs that produced it. Every run ends in one of three states per record: `MATCHED`, `SUGGESTED (pending human approval)`, or `EXCEPTION (reason code + raw data attached)` — never a silent drop.
5. **Settlement Q&A Agent** — a natural-language layer on top of the audit trail. A finance user can ask *"why didn't order #4521 settle correctly?"* and get a plain-language answer sourced strictly from the already-computed `ReconciliationLog` entry — the LLM narrates an existing fact, it never calculates one. Any generated answer containing a number not present in the underlying record is rejected in favor of a template fallback.

---

## 4. Explicit Stopping Conditions
The engine **must** stop attempting automated resolution and escalate to a human when:
* A delta cannot be explained by fees + GST, refund batching, or FX adjustment within a configured tolerance (default ±₹1.00).
* A fuzzy match confidence falls below the approval threshold (default 90%) — it is surfaced for review, never auto-applied.
* The same settlement ID is a candidate match for more than one bank row (conflict — locked until a human resolves it).
* A webhook payload fails signature verification — rejected outright, logged, never processed.
* Razorpay API failures exceed the configured retry ceiling (default 5 attempts) — job halts and raises an operator alert rather than looping indefinitely.

---

## 5. Success Metrics (What We Will Show Judges)
* **Match rate %** on a 50+ record synthetic test batch (Track 04 requirement).
* **Total ₹ reconciled** vs. total ₹ ingested.
* **Unedited exception list** — every unresolved row, verbatim, with reason code.
* **Audit trail sample** — one record traced end-to-end: raw CSV row → matched settlement → diagnostic decision → log entry.

---

## 6. Target Audience
* **SME Founders & Finance Ops** — need payout/fee visibility without dedicated reconciliation headcount.
* **Chartered Accountants & Accounting Firms** — multi-client month-end closes, GST input-tax-credit verification.
* **D2C & E-Commerce Brands** — high-volume daily payouts, chargebacks, instant refunds.

---

## 7. Razorpay Ecosystem Alignment
* **Settlements API (`/v1/settlements`)** — full settlement history via cursor/offset pagination (gross, net, fees, tax, UTR).
* **Refunds API (`/v1/refunds`)** — cross-referenced against settlement deduction cycles.
* **Webhooks (`settlement.processed`)** — real-time ingestion, idempotent by event ID, signature-verified before any processing.
* **Cryptographic Security** — HMAC SHA-256 verification (`X-Razorpay-Signature`) on every webhook, constant-time comparison, raw-body verification before JSON parsing.

---

## 8. Explicit Out-of-Scope (v1)
To keep scope honest for a 14-day build:
* Multi-bank-account netting/consolidation across accounts.
* Non-INR settlement currencies beyond basic FX-delta detection.
* Real-time GST filing/e-invoicing integration (diagnostics only — no filing).
* Multi-gateway support (Razorpay only in v1).

---

## 9. Known Real-World Edge Cases This Design Accounts For
1. **Split/batched settlements** — one bank credit may correspond to multiple Razorpay settlement IDs batched by the bank, or a large settlement may be split across two credit dates. Matching logic groups candidate settlements by date-window + summed amount before declaring `UNRESOLVED`.
2. **Settlement reversals** — Razorpay can debit a merchant's account days after a settlement (chargeback, hold reversal). Bank statement shows a debit, not a credit. Ingestion classifies transaction direction explicitly (`CREDIT`/`DEBIT`) rather than assuming all rows are credits.
3. **Cross-currency settlements** — an FX component sits on top of fees + GST. Tier 3 diagnostics include an FX-adjustment check before falling back to `UNRESOLVED`.
