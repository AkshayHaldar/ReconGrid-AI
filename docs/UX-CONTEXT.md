# ReconGrid AI — UX Context & Design Specifications

## 1. User Persona

### **Ramesh | Senior Chartered Accountant & Finance Lead**
* **Demographics**: 35 years old, leading Finance Operations at an omnichannel D2C consumer electronics brand processing 3,000+ online orders daily.
* **Core Frustrations**:
  * "I despise bloated SaaS dashboards with giant cards that take up half my screen. I need dense, actionable data."
  * "Every month, I waste days doing VLOOKUPs between bank exports and Razorpay Excel sheets to find missing paise and unexplained fee deductions."
  * "I dread finding an amount mismatch and having to manually calculate whether it was a 2% gateway fee or an unrecorded customer return."
* **Core Desires**:
  * Compact, high-density financial tables with clear status badges.
  * Instant, one-click discrepancy explanations (GST, fee splits, refund deductions).
  * Fast export capabilities directly into CSV/Excel for auditing and GST filing.

---

## 2. Core UX Principles

1. **Information Density Over Decorative Fluff**:
   * Prioritize tabular real-estate, compact padding, mono-spaced monetary digits, and clear column alignments.
   * Finance professionals want all relevant variables (UTR, Bank Amount, Gateway Amount, Delta, Status) visible at a glance without endless scrolling.
2. **Actionable Feedback on Discrepancies**:
   * Never leave the user guessing *why* an amount didn't match. Every mismatch must immediately display a contextual heuristic tag (e.g., "Fee Deduction", "Refund Clawback", "Unlocated UTR").
3. **"Zero-Click" Vision for Auto-Reconciliation**:
   * Exact UTR and exact amount matches are auto-reconciled with zero manual effort required.
   * Near matches (>90% fuzzy confidence) are elevated into a dedicated review queue requiring only a single keypress or click to approve.

---

## 3. Text-Based Wireframe

```
+---------------------------------------------------------------------------------------------------------------+
|  [ReconGrid AI Logo]   [Date Range: 01 Aug - 25 Aug 2026 v]   [Select Bank: HDFC v]   [ Upload CSV Button ]  |
+---------------------------------------------------------------------------------------------------------------+
|                                                                                                               |
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|  | TOTAL INGESTED      |  | AUTO-RECONCILED     |  | SUGGESTED MATCHES   |  | UNRESOLVED DISCREPANCIES      | |
|  | ₹ 1,42,85,900.00    |  | 94.2% (1,240 txns)  |  | 38 txns (Review)    |  | ₹ 18,450.00 (12 txns)         | |
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|                                                                                                               |
|  [ Filter: All (1,290) ]  [ Matched (1,240) ]  [ Suggested (38) ]  [ Discrepancies (12) ]      [ Export CSV ] |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  | DATE       | BANK UTR / DESC       | BANK AMT    | RZP SETTLEMENT ID     | RZP AMT     | STATUS         |  |
|  |------------|-----------------------|-------------|-----------------------|-------------|----------------|  |
|  | 2026-08-24 | CMS/002938491823/HDFC | ₹ 98,200.00 | setl_Kjs9283jkd921    | ₹ 98,200.00 | [✔ MATCHED]    |  |
|  | 2026-08-24 | CMS/002938491824/HDFC | ₹ 49,100.00 | setl_Kjs9283jkd922    | ₹ 50,000.00 | [! FEE TAG]    |  |
|  |            |                       |             | (Fee: ₹762.71+GST)    |             | (Explained)    |  |
|  | 2026-08-23 | RTGS/983921092812/HDF | ₹ 12,450.00 | setl_Kjs9283jkd928    | ₹ 12,450.00 | [? SUGGESTED]  |  |
|  |            | (94% UTR similarity)  |             |                       |             | [Approve][Deny]|  |
|  +---------------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 4. Discrepancy Diagnostics UI

Whenever a bank record deviates from the payment gateway settlement record, the UI renders actionable diagnostic tags:

* **Green Check Badge (`MATCHED`)**: Exact match on UTR and settlement amount. Zero manual action required.
* **Amber Warning Tag (`FEE DEDUCTION`)**:
  * *Visual*: Yellow/amber badge with an info icon `[!]`.
  * *Tooltip / Expanded Drawer*: *"Difference of ₹ 900.00 perfectly matches Razorpay Gateway Fee (₹ 762.71) + 18% GST (₹ 137.29)."*
* **Purple Tag (`REFUND ADJUSTED`)**:
  * *Visual*: Purple indicator badge `[↩]`.
  * *Tooltip*: *"Settlement reduced by ₹ 2,500.00 due to Customer Refund Batch #rfnd_9381029."*
* **Blue Tag (`SUGGESTED MATCH`)**:
  * *Visual*: Blue high-contrast pill displaying fuzzy match confidence (e.g., `94% Confidence`).
  * *Controls*: Inline **Approve Match** and **Dismiss** micro-buttons.
* **Red Alert Badge (`UNRESOLVED`)**:
  * *Visual*: Crimson badge `[✖]`.
  * *Action*: Provides a **Flag for Manual Audit** drawer with direct links to view raw CSV metadata and Razorpay settlement logs.
