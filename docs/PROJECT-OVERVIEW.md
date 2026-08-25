# ReconGrid AI — Project Overview

## 1. Executive Summary
**ReconGrid AI** is an Autonomous Settlement Reconciliation & Discrepancy Diagnostic Engine engineered specifically for modern B2B SaaS and high-volume D2C finance teams. Built for the Razorpay Buildathon, ReconGrid AI closes the gap between internal banking records and payment gateway settlements by autonomously ingesting bank statement CSVs, fetching live Razorpay settlement and refund data, running multi-tier matching algorithms (exact UTR + fuzzy logic), and diagnosing discrepancies down to fee structures, GST deductions, and refund adjustments.

---

## 2. The Problem
For SMEs, scale-ups, and Chartered Accountants, financial settlement reconciliation remains one of the most tedious, high-friction, and error-prone monthly workflows:
* **Manual Excel Gridlock**: Finance managers spend 15–30 hours each month manually cross-referencing bank UTR numbers against Razorpay payout reports across hundreds or thousands of transactions.
* **Complex Discrepancy Math**: Settlement amounts in bank statements rarely match gross transaction amounts due to dynamic platform fees, 18% GST deductions, chargebacks, and mid-cycle refund clawbacks.
* **High Human Error & Delayed Closes**: Manual copy-pasting leads to reconciliation gaps, unlocated funds, audit compliance risks, and delayed month-end book closings.
* **Disparate Data Silos**: Bank statements in varying CSV formats are completely disconnected from payment gateway API logs, leaving finance operators without an automated source of truth.

---

## 3. The Solution
ReconGrid AI eliminates manual reconciliation spreadsheets through an intelligent 4-pillar pipeline:
1. **Intelligent Ingestion**: Upload standard bank statement CSVs (HDFC, ICICI, SBI, Axis, Kotak, etc.) and automatically parse, normalize, and extract core parameters (Date, Amount, UTR/Reference, Description).
2. **Automated Razorpay Pipeline**: Fetch settlements and refund records across target date ranges with automated pagination and real-time webhook event listening.
3. **Multi-Tier Matching Engine**:
   * **Tier 1 (Exact Match)**: Deterministic matching on Bank UTR == Razorpay Settlement UTR and exact net settlement amount.
   * **Tier 2 (Fuzzy Heuristics)**: String similarity and Levenshtein distance matching (>90% confidence threshold) for truncated or malformed bank descriptor UTRs.
   * **Tier 3 (Automated Diagnostics)**: Discrepancy diagnostics that calculate Gateway Fees + GST deductions and correlate mid-cycle refund batching to pinpoint exactly why an amount deviates.
4. **Actionable Finance Dashboard**: High-density UI presenting clear auto-reconciled ledgers, suggested fuzzy matches awaiting single-click review, and flagged discrepancies with explanatory tooltips.

---

## 4. Target Audience
* **SME Founders & Finance Operations**: Fast-growing businesses needing visibility into cash flows, net settlement payouts, and gateway charges without hiring dedicated reconciliation staff.
* **Chartered Accountants (CAs) & Accounting Firms**: Financial auditors and tax consultants handling multi-client month-end closings and statutory GST input-tax-credit (ITC) verifications.
* **D2C & E-Commerce Brands**: High-velocity online merchants handling hundreds of daily payouts, chargebacks, and instant customer refunds.

---

## 5. Razorpay Ecosystem Alignment
ReconGrid AI deeply integrates with core Razorpay developer primitives to ensure high accuracy and real-time ledger synchronization:
* **Settlements API (`/v1/settlements`)**: Complete settlement history retrieval with cursor/offset pagination to ingest gross settlements, net payouts, fees, tax, and unique UTR references.
* **Refunds API (`/v1/refunds`)**: Automated cross-referencing of refund IDs and clawbacks against settlement deduction cycles.
* **Webhook Architecture (`settlement.processed`)**: Real-time webhook ingestion to immediately trigger reconciliation whenever Razorpay dispatches a payout.
* **Cryptographic Security**: Strict HMAC SHA256 signature verification over incoming Razorpay webhook payloads (`X-Razorpay-Signature`) protecting against replay and spoofing attacks.
