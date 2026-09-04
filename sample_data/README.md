# 📁 ReconGrid AI — Sample Statements & Evaluation Datasets

This folder provides ready-to-use sample bank statements and settlement test files to evaluate **ReconGrid AI** across Indian banking formats (SBI, HDFC, ICICI, Axis) and Razorpay settlement data.

---

## 📄 Available Test Statements

| File | Bank / Source | Records | What It Tests |
|:---|:---|:---:|:---|
| [`sbi_sample_statement.csv`](./sbi_sample_statement.csv) | State Bank of India | 100 rows | Preamble header skips, UTR extraction, Indian number formatting (Lakhs/Crores), direct debits, and credit inflows. |
| [`hdfc_sample_statement.csv`](./hdfc_sample_statement.csv) | HDFC Bank NetBanking | 50 rows | Standard 2% MDR fee + 18% GST deductions, Section 194-O 1% TDS, and customer refund clawbacks. |
| [`icici_sample_statement.csv`](./icici_sample_statement.csv) | ICICI Corporate | 35 rows | Batched multi-cycle payouts, fuzzy descriptor matches ($\ge 90\%$), and competing conflict claims. |

---

## 🚀 How to Test in the UI

1. Open the ReconGrid AI Dashboard at **`http://localhost:3000`** (or `3001`).
2. Click **"Upload Statement"** in the top navigation bar.
3. Select your bank (e.g. **SBI**, **HDFC**, or **ICICI**).
4. Drag and drop any `.csv` file from this folder.
5. Click **"Upload & Run Reconciliation"**.
6. Watch the 4 summary metric cards, distribution composition bar, and ledger populate instantly.

---

## 🔐 Password-Protected PDF Testing

If you upload a password-protected bank PDF:
- **SBI**: Last 5 digits of Mobile No + DDMM of DOB (or 11-digit Account Number)
- **HDFC**: Customer ID (or DDMMYYYY / First 4 letters in lowercase + DDMM)
- **ICICI**: First 4 letters of name in lowercase + DDMM of DOB
- **Axis**: First 4 letters of Name (CAPITAL) + Last 4 digits of Customer ID
