# ReconGrid AI — UX Context & Design Specifications

## 1. User Persona

### **Ramesh | Senior Chartered Accountant & Finance Lead**
* **Demographics**: 35, leads Finance Operations at an omnichannel D2C electronics brand processing 3,000+ orders/day.
* **Core Frustrations**:
  * "I despise bloated SaaS dashboards with giant cards eating half my screen. I need dense, actionable data."
  * "Every month I waste days doing VLOOKUPs between bank exports and Razorpay sheets to find missing paise."
  * "I dread an amount mismatch and having to manually work out if it's a fee or an unrecorded refund."
* **Core Desires**:
  * Compact, high-density tables with clear status badges.
  * Instant, one-click discrepancy explanations.
  * Fast CSV/Excel export for audit and GST filing.

---

## 2. Core UX Principles
1. **Information Density Over Decorative Fluff** — compact padding, mono-spaced monetary digits, all key columns visible without scrolling.
2. **Actionable Feedback on Discrepancies** — every mismatch shows a contextual tag explaining *why* (fee, refund, FX, reversal), never just "mismatch."
3. **"Zero-Click" Auto-Reconciliation** — exact matches require no action; near-matches go to a single-click review queue.
4. **Never Hide a Failure** — every record ends in a visible state (matched/suggested/conflict/exception); nothing silently disappears from the ledger.

---

## 3. Text-Based Wireframe (Happy Path)

```
+---------------------------------------------------------------------------------------------------------------+
|  [ReconGrid AI Logo]   [Date Range: 01 Aug - 25 Aug 2026 v]   [Select Bank: HDFC v]   [ Upload CSV Button ]  |
+---------------------------------------------------------------------------------------------------------------+
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|  | TOTAL INGESTED      |  | AUTO-RECONCILED     |  | SUGGESTED MATCHES   |  | EXCEPTIONS                    | |
|  | Rs 1,42,85,900.00   |  | 94.2% (1,240 txns)  |  | 38 txns (Review)    |  | Rs 18,450.00 (12 txns)        | |
|  +---------------------+  +---------------------+  +---------------------+  +-------------------------------+ |
|  [ Filter: All (1,290) ] [ Matched ] [ Suggested ] [ Conflicts ] [ Exceptions ]                [ Export CSV ] |
|  +---------------------------------------------------------------------------------------------------------+  |
|  | DATE     | BANK UTR/DESC          | BANK AMT     | RZP SETTLEMENT ID  | RZP AMT     | STATUS             |  |
|  |----------|------------------------|--------------|--------------------|-------------|--------------------| |
|  | 08-24    | CMS/002938491823/HDFC  | Rs 98,200.00 | setl_Kjs9283jkd921 | Rs 98,200.00| [OK MATCHED]       |  |
|  | 08-24    | CMS/002938491824/HDFC | Rs 49,100.00 | setl_Kjs9283jkd922 | Rs 50,000.00| [! FEE] (explained) |  |
|  | 08-23    | RTGS/983921092812/HDF | Rs 12,450.00 | setl_Kjs9283jkd928 | Rs 12,450.00| [? 94% SUGGESTED]  |  |
|  |          |                        |              |                    |             | [Approve][Deny]    |  |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 4. Required Non-Happy-Path States (previously missing)

### 4.1 Empty State (no data uploaded yet)
* Shown on first load / no CSV uploaded for the selected range.
* Large, low-emphasis illustration + single primary action: **"Upload your first bank statement"**.
* No zero-filled summary cards (`Rs 0.00` everywhere reads as broken, not empty) — cards are replaced with a single explanatory line instead.

### 4.2 Loading / Sync-in-Progress State
* CSV parsing and Razorpay sync each show independent progress indicators (row count processed / total, or a spinner with elapsed time if total is unknown).
* Table renders progressively as rows are classified — Ramesh should see matched rows appear before the whole batch finishes, not stare at a blank screen.

### 4.3 Upload Error State
* Wrong file type, oversized file, or malformed CSV → inline error banner naming the *specific* problem ("Row 42: amount column not numeric") — never a generic "upload failed."

### 4.4 Conflict State (new)
* When two bank rows fuzzy-match the same settlement ID: both rows get a **[⚠ CONFLICT]** badge (distinct from `SUGGESTED`), locked from independent approval, with a merged review drawer forcing the user to pick one before either can be approved.

### 4.5 Negative Amount / Debit Row (new)
* Chargebacks, TDS deductions, and settlement reversals render as **debit rows**: amount shown in parentheses with a red-tinted (not purely color-coded — also an inline "DEBIT" text label for accessibility) treatment, distinct from the standard credit row styling.

---

## 5. Discrepancy Diagnostics UI
* **`MATCHED`** — green badge `[OK]`, zero manual action.
* **`FEE DEDUCTION`** — amber badge `[!]`; tooltip: *"Difference of Rs 900.00 matches Gateway Fee (Rs 762.71) + 18% GST (Rs 137.29)."*
* **`REFUND ADJUSTED`** — purple badge `[↩]`; tooltip references the refund batch ID.
* **`FX ADJUSTED`** — teal badge `[$]`; tooltip shows estimated FX component.
* **`SUGGESTED MATCH`** — blue badge with confidence %, inline Approve/Dismiss.
* **`CONFLICT`** — orange badge `[⚠]`, disabled Approve until resolved via the merge drawer.
* **`EXCEPTION`** — red badge `[X]`; opens a "Flag for Manual Audit" drawer with raw CSV row + raw Razorpay payload side by side.

> All badges pair color with a text/icon label — never color alone — for colorblind accessibility.

---

## 6. Accessibility Notes
* Status is always conveyed by icon + text label, not color alone.
* Table supports full keyboard navigation; Approve/Deny on `SUGGESTED` rows reachable and actionable via keyboard.
* Minimum contrast ratio 4.5:1 on all badge text against its background.

---

## 7. Settlement Q&A Panel (New — Differentiator Feature)

### 7.1 Placement
A collapsible side panel (desktop) or bottom sheet (narrow viewports), accessible from a persistent "Ask ReconGrid" button in the header — never a full-page takeover, since Ramesh's core desire is staying on the dense ledger view.

### 7.2 Interaction Pattern
```
+---------------------------------------------+
|  Ask ReconGrid                          [x] |
+---------------------------------------------+
|  > Why didn't order #4521 settle correctly?  |
|                                               |
|  ReconGrid: Order #4521's settlement was     |
|  short by Rs 900.00. This matches the        |
|  Gateway Fee (Rs 762.71) + 18% GST           |
|  (Rs 137.29). No action needed — this is     |
|  already reflected as a FEE DEDUCTION.       |
|                                               |
|  [View source record ->]                     |
+---------------------------------------------+
|  [ Type a question... ]              [Send]  |
+---------------------------------------------+
```

### 7.3 Required States
* **Answer found** — narration text + a **"View source record"** link that jumps directly to the underlying `ReconciliationLog` row in the main ledger. This link is not optional: every Q&A answer must be traceable to a specific row the user can independently verify.
* **No record found** — a plain, non-apologetic message: *"No record found matching that reference. Check the order ID, UTR, or settlement ID and try again."* Never a hedged guess.
* **Guardrail fallback** — if the LLM's narration was rejected (invented a number not in the source record), the UI silently shows the template fallback — the user should never see an error about this; it should just look like a slightly plainer, still-correct answer. Internally, this event is still logged (`ARCHITECTURE.md §2.5`) for your own audit/debugging, just not surfaced as a failure to the end user.
* **Loading** — a short "Looking that up..." state, distinct from the main table's loading state.

### 7.4 Why This Matters for the UX Narrative
This panel is the visible surface of the project's core AI-judgment rule: it always cites a specific, already-computed record rather than reasoning freely. The "View source record" link exists specifically so a skeptical CA (or a judge) can verify the AI didn't make anything up — this is a trust-building UI element, not a nice-to-have.

