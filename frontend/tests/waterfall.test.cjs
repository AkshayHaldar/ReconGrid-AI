const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
let ts;
try {
  ts = require("typescript");
} catch {
  try {
    ts = require(path.resolve(__dirname, "../../../DevTrack/frontend/node_modules/typescript"));
  } catch (err) {
    throw new Error("Could not load typescript: " + err.message);
  }
}

// Compile and load src/lib/waterfall.ts and src/lib/formatters.ts
const formattersSource = readFileSync(
  path.join(__dirname, "../src/lib/formatters.ts"),
  "utf8"
);
const formattersCompiled = ts.transpileModule(formattersSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

const formattersModule = {};
vm.runInNewContext(formattersCompiled, { exports: formattersModule });

const waterfallSource = readFileSync(
  path.join(__dirname, "../src/lib/waterfall.ts"),
  "utf8"
);
const waterfallCompiled = ts.transpileModule(waterfallSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

const waterfallModule = {};
vm.runInNewContext(waterfallCompiled, {
  exports: waterfallModule,
  require: (mod) => {
    if (mod === "./formatters") return formattersModule;
    return {};
  },
});

const {
  roundToPaise,
  parseRupeeValue,
  extractRecordFeeDecomposition,
  computeFeeWaterfall,
} = waterfallModule;

test("roundToPaise accurately rounds without IEEE-754 precision noise", () => {
  assert.equal(roundToPaise(100.004), 100);
  assert.equal(roundToPaise(100.005), 100.01);
  assert.equal(roundToPaise(0.1 + 0.2), 0.3);
});

test("parseRupeeValue parses formatted and unformatted amounts safely", () => {
  assert.equal(parseRupeeValue("₹ 1,50,000.50"), 150000.5);
  assert.equal(parseRupeeValue("25000"), 25000);
  assert.equal(parseRupeeValue(""), 0);
  assert.equal(parseRupeeValue(null), 0);
  assert.equal(parseRupeeValue(-500), 500);
});

test("extractRecordFeeDecomposition handles standard fee deduction (2% MDR + 18% GST)", () => {
  const record = {
    id: "rec-fee-1",
    bank_amount: "48820.00",
    bank_direction: "CREDIT",
    rzp_gross_amount: "50000.00",
    rzp_amount: "48820.00",
    rzp_fees: "1000.00",
    rzp_tax: "180.00",
    diagnostic_type: "FEE_DEDUCTION",
    delta_amount: "1180.00",
    diagnostic_note: "Difference matches 2% Gateway Fee (₹ 1,000.00) + 18% GST (₹ 180.00)",
  };

  const decomp = extractRecordFeeDecomposition(record);
  assert.equal(decomp.recordGross, 50000);
  assert.equal(decomp.mdrFee, 1000);
  assert.equal(decomp.gstTax, 180);
  assert.equal(decomp.tds, 0);
  assert.equal(decomp.netBank, 48820);
  // Conservation: Gross - (Fees + GST + TDS) = Net
  assert.equal(
    decomp.recordGross - (decomp.mdrFee + decomp.gstTax + decomp.tds),
    decomp.netBank
  );
});

test("extractRecordFeeDecomposition handles Section 194-O TDS deduction (1% TDS + 2% MDR + 18% GST)", () => {
  const record = {
    id: "rec-tds-1",
    bank_amount: "96640.00",
    bank_direction: "CREDIT",
    rzp_gross_amount: "100000.00",
    rzp_amount: "97640.00",
    rzp_fees: "2000.00",
    rzp_tax: "360.00",
    diagnostic_type: "TDS_194O_DEDUCTION",
    delta_amount: "3360.00",
    diagnostic_note:
      "Difference of ₹ 3,360.00 matches 1% TDS u/s 194-O (₹ 1,000.00) + Gateway Fee (₹ 2,000.00) + 18% GST (₹ 360.00).",
  };

  const decomp = extractRecordFeeDecomposition(record);
  assert.equal(decomp.recordGross, 100000);
  assert.equal(decomp.mdrFee, 2000);
  assert.equal(decomp.gstTax, 360);
  assert.equal(decomp.tds, 1000);
  assert.equal(decomp.netBank, 96640);
  // Conservation: Gross - (Fees + GST + TDS) = Net
  assert.equal(
    decomp.recordGross - (decomp.mdrFee + decomp.gstTax + decomp.tds),
    decomp.netBank
  );
});

test("computeFeeWaterfall mathematically conserves Gross - (Fees + GST + TDS) = Net Bank Inflow", () => {
  const sampleRecords = [
    // 1. Exact match (no deductions)
    {
      id: "rec-1",
      bank_amount: "25000.00",
      bank_direction: "CREDIT",
      rzp_gross_amount: "25000.00",
      rzp_amount: "25000.00",
      diagnostic_type: "EXACT_MATCH",
      delta_amount: "0.00",
    },
    // 2. Fee deduction (2% fee = ₹1,000, 18% GST = ₹180)
    {
      id: "rec-2",
      bank_amount: "48820.00",
      bank_direction: "CREDIT",
      rzp_gross_amount: "50000.00",
      rzp_amount: "48820.00",
      rzp_fees: "1000.00",
      rzp_tax: "180.00",
      diagnostic_type: "FEE_DEDUCTION",
      delta_amount: "1180.00",
    },
    // 3. Section 194-O TDS deduction (2% fee = ₹2,000, 18% GST = ₹360, 1% TDS = ₹1,000)
    {
      id: "rec-3",
      bank_amount: "96640.00",
      bank_direction: "CREDIT",
      rzp_gross_amount: "100000.00",
      rzp_amount: "97640.00",
      rzp_fees: "2000.00",
      rzp_tax: "360.00",
      diagnostic_type: "TDS_194O_DEDUCTION",
      delta_amount: "3360.00",
      diagnostic_note: "1% TDS u/s 194-O (₹ 1,000.00)",
    },
  ];

  const result = computeFeeWaterfall(sampleRecords);

  // Expected Gross: 25000 + 50000 + 100000 = 175,000.00
  assert.equal(result.grossAmount, 175000);
  // Expected MDR Fees: 0 + 1000 + 2000 = 3,000.00
  assert.equal(result.mdrFeeAmount, 3000);
  assert.equal(result.mdrFeeCount, 2);
  // Expected GST: 0 + 180 + 360 = 540.00
  assert.equal(result.gstTaxAmount, 540);
  assert.equal(result.gstTaxCount, 2);
  // Expected TDS: 0 + 0 + 1000 = 1,000.00
  assert.equal(result.tdsAmount, 1000);
  assert.equal(result.tdsCount, 1);
  // Expected Net Bank Inflow: 25000 + 48820 + 96640 = 170,460.00
  assert.equal(result.netBankAmount, 170460);
  assert.equal(result.netBankCount, 3);
  // Total Deductions: 3000 + 540 + 1000 = 4,540.00
  assert.equal(result.totalDeductions, 4540);

  // Mathematical conservation: Gross - (Fees + GST + TDS) === Net Bank Inflow
  assert.equal(
    result.grossAmount - result.totalDeductions,
    result.netBankAmount
  );
  assert.equal(result.varianceAmount, 0);
  assert.equal(result.isInBalance, true);

  // Verify all 5 stages exist with proper attributes
  assert.equal(result.stages.length, 5);
  const stageIds = result.stages.map((s) => s.id);
  assert.equal(
    JSON.stringify(stageIds),
    JSON.stringify(["GROSS", "MDR_FEE", "GST_TAX", "TDS_194O", "NET_CREDIT"])
  );
});

test("handles empty records and recovers gracefully with zero variance", () => {
  const result = computeFeeWaterfall([]);
  assert.equal(result.grossAmount, 0);
  assert.equal(result.totalDeductions, 0);
  assert.equal(result.netBankAmount, 0);
  assert.equal(result.varianceAmount, 0);
  assert.equal(result.isInBalance, true);
});

test("falls back cleanly to status summary numbers when records are not yet fetched", () => {
  const mockStatus = {
    batch_id: "batch-mock",
    total_records: 10,
    matched_count: 8,
    suggested_count: 1,
    conflict_count: 1,
    exception_count: 0,
    match_rate_percentage: 80,
    total_ingested_amount: "₹ 5,00,000.00",
    total_reconciled_amount: "₹ 5,00,000.00",
    total_exception_amount: "₹ 0.00",
  };

  const result = computeFeeWaterfall([], mockStatus);
  assert.equal(result.grossAmount, 500000);
  assert.equal(result.netBankAmount, 500000);
  assert.equal(result.totalTransactions, 10);
  assert.equal(result.netBankCount, 8);
  assert.equal(result.isInBalance, true);
});

test("stage filters correctly route to diagnostic and status tab categories", () => {
  const sampleRecords = [
    {
      id: "rec-1",
      bank_amount: "96640.00",
      bank_direction: "CREDIT",
      rzp_gross_amount: "100000.00",
      rzp_fees: "2000.00",
      rzp_tax: "360.00",
      diagnostic_type: "TDS_194O_DEDUCTION",
      delta_amount: "3360.00",
      diagnostic_note: "1% TDS u/s 194-O (₹ 1,000.00)",
    },
  ];

  const result = computeFeeWaterfall(sampleRecords);
  const stagesById = Object.fromEntries(result.stages.map((s) => [s.id, s]));

  assert.equal(stagesById.GROSS.diagnosticFilter, "ALL");
  assert.equal(stagesById.GROSS.statusTabFilter, "ALL");

  assert.equal(stagesById.MDR_FEE.diagnosticFilter, "FEE_DEDUCTION");
  assert.equal(stagesById.MDR_FEE.statusTabFilter, null);

  assert.equal(stagesById.GST_TAX.diagnosticFilter, "FEE_DEDUCTION");
  assert.equal(stagesById.GST_TAX.statusTabFilter, null);

  assert.equal(stagesById.TDS_194O.diagnosticFilter, "TDS_194O_DEDUCTION");
  assert.equal(stagesById.TDS_194O.statusTabFilter, null);

  assert.equal(stagesById.NET_CREDIT.diagnosticFilter, "ALL");
  assert.equal(stagesById.NET_CREDIT.statusTabFilter, "MATCHED");
});

test("accurately computes fractional paise without drift across complex settlement batches", () => {
  const fractionalRecords = [
    {
      id: "rec-frac-1",
      bank_amount: "1234.56",
      bank_direction: "CREDIT",
      rzp_gross_amount: "1268.40",
      rzp_fees: "25.37",
      rzp_tax: "4.57",
      diagnostic_type: "TDS_194O_DEDUCTION",
      delta_amount: "33.84",
      diagnostic_note: "1% TDS u/s 194-O (₹ 3.90)",
    },
    {
      id: "rec-frac-2",
      bank_amount: "9876.54",
      bank_direction: "CREDIT",
      rzp_gross_amount: "10110.15",
      rzp_fees: "197.98",
      rzp_tax: "35.63",
      diagnostic_type: "FEE_DEDUCTION",
      delta_amount: "233.61",
    },
  ];

  const result = computeFeeWaterfall(fractionalRecords);
  assert.equal(
    result.grossAmount,
    roundToPaise(result.netBankAmount + result.totalDeductions)
  );
  assert.equal(result.isInBalance, true);
});
