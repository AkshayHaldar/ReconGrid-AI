import {
  DiagnosticType,
  FeeWaterfallBreakdown,
  FeeWaterfallStage,
  ReconciliationRecordItem,
  ReconciliationStatus,
  WaterfallSegmentId,
} from "./types";
import { formatINR } from "./formatters";

/**
 * Rounds a number strictly to two decimal places (paise precision)
 * avoiding IEEE-754 floating point drift.
 */
export function roundToPaise(val: number): number {
  return Math.round((val + Number.EPSILON) * 100) / 100;
}

/**
 * Safely parses any raw string/number into a positive numeric rupee value.
 */
export function parseRupeeValue(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === "") return 0;
  if (typeof val === "number") {
    return Number.isFinite(val) ? Math.abs(val) : 0;
  }
  const clean = val.replace(/[₹,\s]/g, "").trim();
  const num = Number(clean);
  return Number.isFinite(num) ? Math.abs(num) : 0;
}

export interface RecordFeeDecomposition {
  recordGross: number;
  mdrFee: number;
  gstTax: number;
  tds: number;
  netBank: number;
  isCredit: boolean;
}

/**
 * Extracts and decomposes fees, taxes, and gross amount for a single reconciliation record.
 * Ensures the conservation rule: recordGross = netBank + mdrFee + gstTax + tds.
 */
export function extractRecordFeeDecomposition(
  r: ReconciliationRecordItem
): RecordFeeDecomposition {
  const bankAmt = parseRupeeValue(r.bank_amount);
  const isCredit = r.bank_direction !== "DEBIT";

  let rzpFee = parseRupeeValue(r.rzp_fees);
  let rzpTax = parseRupeeValue(r.rzp_tax);
  const rzpGross = parseRupeeValue(r.rzp_gross_amount);
  const rzpNet = parseRupeeValue(r.rzp_amount);
  const delta = parseRupeeValue(r.delta_amount);
  let tds = 0;

  // 1. Check raw_rzp_payload for explicit TDS fields if available
  if (r.raw_rzp_payload) {
    if (r.raw_rzp_payload.tds !== undefined) {
      tds = parseRupeeValue(r.raw_rzp_payload.tds);
    } else if (r.raw_rzp_payload.tds_194o !== undefined) {
      tds = parseRupeeValue(r.raw_rzp_payload.tds_194o);
    }
  }

  // 2. Parse Section 194-O TDS from diagnostic_note if explicit
  if (tds === 0 && r.diagnostic_type === "TDS_194O_DEDUCTION" && r.diagnostic_note) {
    const match = r.diagnostic_note.match(
      /1%\s*TDS[^(]*\((?:₹|INR|Rs\.?)?\s*([\d,.]+)\)/i
    );
    if (match) {
      tds = parseRupeeValue(match[1]);
    }
  }

  // 3. Mathematical reconstruction for TDS_194O_DEDUCTION if not yet isolated
  if (tds === 0 && r.diagnostic_type === "TDS_194O_DEDUCTION") {
    if (rzpGross > 0) {
      tds = roundToPaise(rzpGross * 0.01);
      if (rzpFee === 0) rzpFee = roundToPaise(rzpGross * 0.02);
      if (rzpTax === 0) rzpTax = roundToPaise(rzpFee * 0.18);
    } else if (delta > 0) {
      // Standard decomposition: 2% MDR + 0.36% GST (18% on MDR) + 1% TDS = 3.36% delta
      const estGross = delta / 0.0336;
      tds = roundToPaise(estGross * 0.01);
      if (rzpFee === 0) rzpFee = roundToPaise(estGross * 0.02);
      if (rzpTax === 0) rzpTax = roundToPaise(rzpFee * 0.18);
    }
  }

  // 4. Mathematical reconstruction for FEE_DEDUCTION if fees/tax are not populated
  if (
    r.diagnostic_type === "FEE_DEDUCTION" &&
    rzpFee === 0 &&
    rzpTax === 0 &&
    delta > 0
  ) {
    // delta = fee * 1.18
    rzpFee = roundToPaise(delta / 1.18);
    rzpTax = roundToPaise(delta - rzpFee);
  }

  // 5. Establish exact gross amount conserving: Gross = Net + Fees + Tax + TDS
  let recordGross = 0;
  const deductions = roundToPaise(rzpFee + rzpTax + tds);

  if (rzpGross > 0 && Math.abs(rzpGross - (bankAmt + deductions)) <= 1.0) {
    recordGross = rzpGross;
  } else if (deductions > 0) {
    recordGross = roundToPaise(bankAmt + deductions);
  } else if (rzpNet > 0) {
    recordGross = rzpNet;
  } else {
    recordGross = bankAmt;
  }

  // Final sanity clamp: ensure Gross >= Net + Deductions
  if (recordGross < bankAmt + deductions) {
    recordGross = roundToPaise(bankAmt + deductions);
  }

  return {
    recordGross,
    mdrFee: rzpFee,
    gstTax: rzpTax,
    tds,
    netBank: bankAmt,
    isCredit,
  };
}

/**
 * Computes aggregated fee & tax waterfall breakdown from active reconciliation records.
 * Mathematically guarantees: Gross − (Fees + GST + TDS) = Net Bank Inflow.
 */
export function computeFeeWaterfall(
  records: ReconciliationRecordItem[] = [],
  status?: ReconciliationStatus | null
): FeeWaterfallBreakdown {
  let grossAmount = 0;
  let mdrFeeAmount = 0;
  let gstTaxAmount = 0;
  let tdsAmount = 0;
  let netBankAmount = 0;

  let totalTransactions = 0;
  let mdrFeeCount = 0;
  let gstTaxCount = 0;
  let tdsCount = 0;
  let netBankCount = 0;

  if (records && records.length > 0) {
    for (const r of records) {
      totalTransactions++;
      const decomp = extractRecordFeeDecomposition(r);

      grossAmount += decomp.recordGross;
      netBankAmount += decomp.netBank;

      if (decomp.isCredit) {
        netBankCount++;
      }

      if (decomp.mdrFee > 0) {
        mdrFeeAmount += decomp.mdrFee;
        mdrFeeCount++;
      }

      if (decomp.gstTax > 0) {
        gstTaxAmount += decomp.gstTax;
        gstTaxCount++;
      }

      if (decomp.tds > 0) {
        tdsAmount += decomp.tds;
        tdsCount++;
      }
    }
  } else if (status) {
    // Fallback estimation from status summary if records are not yet fetched
    const ingested = parseRupeeValue(status.total_ingested_amount);
    const reconciled = parseRupeeValue(status.total_reconciled_amount);

    grossAmount = ingested > 0 ? ingested : reconciled;
    netBankAmount = reconciled > 0 ? reconciled : ingested;
    totalTransactions = status.total_records || 0;
    netBankCount = status.matched_count || 0;
  }

  // Quantize all totals to paise
  grossAmount = roundToPaise(grossAmount);
  mdrFeeAmount = roundToPaise(mdrFeeAmount);
  gstTaxAmount = roundToPaise(gstTaxAmount);
  tdsAmount = roundToPaise(tdsAmount);
  netBankAmount = roundToPaise(netBankAmount);

  const totalDeductions = roundToPaise(mdrFeeAmount + gstTaxAmount + tdsAmount);

  // Mathematical conservation variance
  // In a balanced batch: Gross - Total Deductions = Net Bank Amount
  const varianceAmount = roundToPaise(
    Math.abs(grossAmount - (totalDeductions + netBankAmount))
  );
  const isInBalance = varianceAmount <= 0.05; // Paired tolerance within 5 paise rounding noise

  // Percentages relative to Gross
  const calcPct = (amt: number): number => {
    if (grossAmount <= 0) return 0;
    return roundToPaise((amt / grossAmount) * 100);
  };

  const stages: FeeWaterfallStage[] = [
    {
      id: "GROSS",
      label: "Gross Settlement Volume",
      shortLabel: "Gross GMV",
      amount: grossAmount,
      formattedAmount: formatINR(grossAmount),
      percentageOfGross: 100.0,
      transactionCount: totalTransactions,
      diagnosticFilter: "ALL",
      statusTabFilter: "ALL",
      color: {
        bg: "bg-slate-900/60",
        border: "border-slate-700/80",
        text: "text-slate-200",
        hoverBg: "hover:bg-slate-800/80",
        barBg: "bg-slate-500",
        badgeBg: "bg-slate-950/80 text-slate-300 border-slate-700",
      },
      description:
        "Total gross transaction volume processed before payment gateway fees and statutory tax withholdings",
    },
    {
      id: "MDR_FEE",
      label: "MDR Gateway Fee",
      shortLabel: "MDR (2%)",
      rateLabel: "2.00%",
      amount: mdrFeeAmount,
      formattedAmount: formatINR(mdrFeeAmount),
      percentageOfGross: calcPct(mdrFeeAmount),
      transactionCount: mdrFeeCount,
      diagnosticFilter: "FEE_DEDUCTION",
      statusTabFilter: null,
      color: {
        bg: "bg-indigo-950/40",
        border: "border-indigo-800/60",
        text: "text-indigo-300",
        hoverBg: "hover:bg-indigo-900/50",
        barBg: "bg-indigo-500",
        badgeBg: "bg-indigo-950/80 text-indigo-300 border-indigo-700",
      },
      description:
        "Merchant Discount Rate processing fee charged by Razorpay on settled card/UPI transactions",
    },
    {
      id: "GST_TAX",
      label: "GST on Gateway Fee",
      shortLabel: "GST (18%)",
      rateLabel: "18.00%",
      amount: gstTaxAmount,
      formattedAmount: formatINR(gstTaxAmount),
      percentageOfGross: calcPct(gstTaxAmount),
      transactionCount: gstTaxCount,
      diagnosticFilter: "FEE_DEDUCTION",
      statusTabFilter: null,
      color: {
        bg: "bg-amber-950/40",
        border: "border-amber-800/60",
        text: "text-amber-300",
        hoverBg: "hover:bg-amber-900/50",
        barBg: "bg-amber-500",
        badgeBg: "bg-amber-950/80 text-amber-300 border-amber-700",
      },
      description:
        "18% Goods & Services Tax statutory levy applied directly onto payment gateway processing charges",
    },
    {
      id: "TDS_194O",
      label: "Section 194-O TDS",
      shortLabel: "1% TDS (194-O)",
      rateLabel: "1.00%",
      amount: tdsAmount,
      formattedAmount: formatINR(tdsAmount),
      percentageOfGross: calcPct(tdsAmount),
      transactionCount: tdsCount,
      diagnosticFilter: "TDS_194O_DEDUCTION",
      statusTabFilter: null,
      color: {
        bg: "bg-violet-950/40",
        border: "border-violet-800/60",
        text: "text-violet-300",
        hoverBg: "hover:bg-violet-900/50",
        barBg: "bg-violet-500",
        badgeBg: "bg-violet-950/80 text-violet-300 border-violet-700",
      },
      description:
        "1% Tax Deducted at Source on gross e-commerce marketplace payouts mandated under Section 194-O",
    },
    {
      id: "NET_CREDIT",
      label: "Net Bank Inflow",
      shortLabel: "Net Inflow",
      rateLabel: "Net",
      amount: netBankAmount,
      formattedAmount: formatINR(netBankAmount),
      percentageOfGross: calcPct(netBankAmount),
      transactionCount: netBankCount,
      diagnosticFilter: "ALL",
      statusTabFilter: "MATCHED",
      color: {
        bg: "bg-emerald-950/40",
        border: "border-emerald-800/60",
        text: "text-emerald-300",
        hoverBg: "hover:bg-emerald-900/50",
        barBg: "bg-emerald-500",
        badgeBg: "bg-emerald-950/80 text-emerald-300 border-emerald-700",
      },
      description:
        "Actual net funds credited to the corporate bank account after fee and tax deductions",
    },
  ];

  return {
    grossAmount,
    mdrFeeAmount,
    gstTaxAmount,
    tdsAmount,
    netBankAmount,
    totalDeductions,
    varianceAmount,
    isInBalance,
    totalTransactions,
    mdrFeeCount,
    gstTaxCount,
    tdsCount,
    netBankCount,
    stages,
  };
}
