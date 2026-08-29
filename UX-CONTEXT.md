# 🎨 UX Context & Design Specifications — ReconGrid AI

---

## 1. Who Is This Built For?

### 👤 Ramesh — Senior Chartered Accountant & Finance Lead
- **Age:** 35
- **Role:** Leads Finance Operations at an omnichannel D2C brand processing 3,000+ orders/day
- **What frustrates him:**
  - *"I despise bloated dashboards with giant empty cards taking up half my screen. I need dense, actionable data."*
  - *"Every month I waste days doing VLOOKUPs between bank exports and Razorpay sheets to find missing paise."*
  - *"I dread amount mismatches where I have to manually figure out if it's a fee, a refund, or a reversal."*
- **What he actually wants:**
  - Compact tables where all the key columns fit on one screen
  - Instant, one-click explanations for discrepancies
  - Fast CSV exports for audit and GST filing

---

## 2. Core UX Principles

1. **High Information Density:** Compact padding, monospaced numbers, key columns visible without horizontal scrolling.
2. **Actionable Discrepancy Tags:** Every mismatch explains *why* (fee, refund, FX, reversal) — never just a vague "mismatch."
3. **Zero-Click Auto-Reconciliation:** Exact matches need no human intervention. Near-matches go to a quick-review queue.
4. **Never Hide Failures:** Every record ends in a visible state (`MATCHED`, `SUGGESTED`, `CONFLICT`, `EXCEPTION`). Nothing silently disappears.

---

## 3. Dashboard Layout (Happy Path)

```
+---------------------------------------------------------------------------------------------------------------+
|  [ReconGrid AI]       [Date: 01 Aug - 25 Aug 2026]       [Bank: HDFC v]       [ + Upload Statement CSV ]     |
+---------------------------------------------------------------------------------------------------------------+
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|  | TOTAL INGESTED      |  | AUTO-RECONCILED     |  | SUGGESTED MATCHES   |  | EXCEPTIONS                    | |
|  | ₹ 1,42,85,900.00    |  | 94.2% (1,240 txns)  |  | 38 txns (Review)    |  | ₹ 18,450.00 (12 txns)         | |
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|                                                                                                               |
|  [ Filter: All (1,290) ] [ Matched ] [ Suggested ] [ Conflicts ] [ Exceptions ]                [ Export CSV ] |
|  +---------------------------------------------------------------------------------------------------------+  |
|  | DATE     | BANK UTR / DESC        | BANK AMT     | RZP SETTLEMENT ID  | RZP AMT     | STATUS             |  |
|  |----------|------------------------|--------------|--------------------|-------------|--------------------| |
|  | 08-24    | CMS/002938491823/HDFC  | ₹ 98,200.00  | setl_Kjs9283jkd921 | ₹ 98,200.00 | [✔ MATCHED]        |  |
|  | 08-24    | CMS/002938491824/HDFC  | ₹ 49,100.00  | setl_Kjs9283jkd922 | ₹ 50,000.00 | [! FEE DEDUCTED]   |  |
|  | 08-23    | RTGS/983921092812/HDF  | ₹ 12,450.00  | setl_Kjs9283jkd928 | ₹ 12,450.00 | [? 94% SUGGESTED]  |  |
|  |          |                        |              |                    |             | [Approve] [Deny]   |  |
|  +---------------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 4. UI States & Edge Cases

### 4.1 Empty State (First Load)
- Shown when no data has been uploaded yet
- Clean, low-emphasis visual + a prominent **"Upload your first bank statement"** button
- No misleading `₹ 0.00` cards — summary cards are replaced by a helpful getting-started message

### 4.2 Loading / In-Progress State
- Shows clear progress (e.g., *"Processing row 240 of 1,200..."*)
- Table renders rows progressively — users see matched rows appear as they're processed

### 4.3 Upload Error State
- If a CSV is corrupted or wrong type → an inline error banner names the **exact problem** (e.g., *"Row 42: amount column is missing or not a number"*), never a generic *"Upload failed"*

### 4.4 Conflict State
- When two bank rows fuzzy-match the same Razorpay settlement, both get a **[⚠ CONFLICT]** badge
- The Approve button is disabled; clicking opens a side drawer forcing the user to pick which bank row is the real match

### 4.5 Negative Amount / Debit Rows
- Chargebacks, TDS deductions, and settlement reversals are shown with a distinct **DEBIT** indicator and red-tinted styling so they're never confused with standard payout credits

---

## 5. Status Badges & Diagnostic Tags

| Badge | Look | Meaning & Tooltip |
|---|---|---|
| **`MATCHED`** | Green `[✔]` | Exact match — no action required |
| **`FEE DEDUCTION`** | Amber `[!]` | *"Difference of ₹900 matches Gateway Fee (₹762.71) + 18% GST (₹137.29)"* |
| **`REFUND ADJUSTED`** | Purple `[↩]` | *"Settlement reduced by ₹5,000 for refund batch #rfnd_8392"* |
| **`FX ADJUSTED`** | Teal `[$]` | *"Difference matches estimated FX adjustment component"* |
| **`SUGGESTED`** | Blue `[?]` | Near match with confidence score (e.g., 94%) — inline Approve/Deny buttons |
| **`CONFLICT`** | Orange `[⚠]` | Multiple bank rows matched one settlement — needs manual pick |
| **`EXCEPTION`** | Red `[✖]` | Could not match — opens side drawer with raw data for audit |

> **Accessibility:** Every badge combines a color with an icon and a text label — never color alone.

---

## 6. Settlement Q&A Panel (The AI Assistant)

### Where It Lives
A collapsible side panel on the right side of the screen, opened via an **"Ask ReconGrid"** button in the header. It never takes over the full screen so Ramesh can keep looking at the ledger.

```
+---------------------------------------------+
|  Ask ReconGrid                          [✕] |
+---------------------------------------------+
|  > Why didn't order #4521 settle correctly?  |
|                                               |
|  ReconGrid: Order #4521's settlement was     |
|  short by ₹900.00. This matches the Gateway  |
|  Fee (₹762.71) + 18% GST (₹137.29).          |
|  No action needed — this is classified as a  |
|  FEE DEDUCTION.                              |
|                                               |
|  [🔗 View source record →]                   |
+---------------------------------------------+
|  [ Type a question...               ] [Send] |
+---------------------------------------------+
```

### Key Behaviors
- **Traceable:** Every answer includes a **"View source record"** link that highlights the exact row in the ledger.
- **Honest:** If no record matches the question, it says: *"No record found for that reference. Check the order ID, UTR, or settlement ID."*
- **Guardrailed:** If the AI tries to make up a number, the system catches it, rejects the answer, and shows a verified template instead.
