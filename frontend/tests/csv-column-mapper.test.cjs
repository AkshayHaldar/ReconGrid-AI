const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/lib/csv-mapper.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function getExports() {
  const exports = {};
  vm.runInNewContext(compiled, { exports });
  return exports;
}

function toHost(val) {
  return JSON.parse(JSON.stringify(val));
}

test("parseCsvLines correctly handles quotes, embedded commas and escaped quotes", () => {
  const { parseCsvLines } = getExports();
  const csv = [
    'Header1,"Header 2, with comma",Header3',
    'Value1,"Value 2 with ""quotes""",Value3',
    'Simple1,Simple2,Simple3',
  ].join("\n");

  const rows = parseCsvLines(csv);
  assert.equal(rows.length, 3);
  assert.deepEqual(toHost(rows[0]), ["Header1", "Header 2, with comma", "Header3"]);
  assert.deepEqual(toHost(rows[1]), ["Value1", 'Value 2 with "quotes"', "Value3"]);
  assert.deepEqual(toHost(rows[2]), ["Simple1", "Simple2", "Simple3"]);
});

test("detectCsvHeaderAndRows skips metadata preamble lines", () => {
  const { parseCsvLines, detectCsvHeaderAndRows } = getExports();
  const csv = [
    "Axis Bank Corporate Statement",
    "Account Number: 987654321000",
    "IFSC: UTIB0000123",
    "",
    "Value Date,Particulars,Instrument Id,Deposit,Withdrawal,Balance",
    "24-08-2026,Razorpay Settlement Bangalore,CMS002938491850,85000.00,0.00,185000.00",
    "25-08-2026,SMS Alert Fee,INST12345678,0.00,59.00,184941.00",
  ].join("\n");

  const rows = parseCsvLines(csv);
  const detected = detectCsvHeaderAndRows(rows);

  assert.notEqual(detected, null);
  assert.equal(detected.headerIndex, 3);
  assert.deepEqual(toHost(detected.headers), [
    "Value Date",
    "Particulars",
    "Instrument Id",
    "Deposit",
    "Withdrawal",
    "Balance",
  ]);
  assert.equal(detected.dataRows.length, 2);
  assert.equal(detected.dataRows[0]["Value Date"], "24-08-2026");
  assert.equal(detected.dataRows[0]["Deposit"], "85000.00");
});

test("isStandardBankStatement identifies standard HDFC, ICICI, SBI statements", () => {
  const { isStandardBankStatement } = getExports();

  // HDFC
  assert.equal(
    isStandardBankStatement(["Date", "Chq/Ref No.", "Narration", "Deposit Amt.", "Withdrawal Amt."]),
    true
  );

  // ICICI
  assert.equal(
    isStandardBankStatement([
      "Transaction Date",
      "Transaction Reference Number",
      "Transaction Remarks",
      "Deposit Amount (INR )",
      "Withdrawal Amount (INR )",
    ]),
    true
  );

  // SBI
  assert.equal(
    isStandardBankStatement(["Txn Date", "Ref No./Cheque No.", "Description", "Credit", "Debit", "Balance"]),
    true
  );

  // Generic standard
  assert.equal(
    isStandardBankStatement(["date", "utr", "description", "amount", "direction"]),
    true
  );
});

test("isStandardBankStatement returns false for non-standard corporate bank statements", () => {
  const { isStandardBankStatement } = getExports();

  // Axis / Federal / Yes Bank style non-standard headers
  assert.equal(
    isStandardBankStatement(["Value Date", "Particulars", "Instrument Id", "Deposit", "Withdrawal", "Balance"]),
    false
  );

  assert.equal(
    isStandardBankStatement(["Booking Date", "Narrative", "Doc No", "Paid In", "Paid Out"]),
    false
  );

  assert.equal(
    isStandardBankStatement(["Col A", "Col B", "Col C", "Col D"]),
    false
  );
});

test("guessColumnMappings accurately detects column roles", () => {
  const { guessColumnMappings } = getExports();
  const headers = ["Value Date", "Particulars", "Instrument Id", "Deposit", "Withdrawal", "Balance"];
  const guessed = guessColumnMappings(headers);

  assert.equal(guessed.date, "Value Date");
  assert.equal(guessed.narration, "Particulars");
  assert.equal(guessed.ref, "Instrument Id");
  assert.equal(guessed.amount, "Deposit");
  assert.equal(guessed.withdrawal, "Withdrawal");
});

test("computeHeaderSignature generates deterministic key", () => {
  const { computeHeaderSignature } = getExports();
  const headers1 = ["Value Date", "Particulars", "Instrument Id", "Deposit"];
  const headers2 = ["Instrument Id", "Deposit", "Particulars", "Value Date"]; // different order
  const sig1 = computeHeaderSignature(headers1);
  const sig2 = computeHeaderSignature(headers2);

  assert.equal(sig1, sig2);
  assert.match(sig1, /^recongrid_csv_mapping_[a-f0-9]+$/);
});

test("parseCsvLines preserves embedded newlines in quoted cells across records", () => {
  const { parseCsvLines } = getExports();
  const csv = [
    'Date,Narration,Amount',
    '24-08-2026,"Invoice 101\nPayment for consultancy",50000.00',
    '25-08-2026,"Vendor disbursement\nRef: PO-9981",12500.00',
  ].join("\n");

  const rows = parseCsvLines(csv);
  assert.equal(rows.length, 3);
  assert.equal(rows[1][1], "Invoice 101\nPayment for consultancy");
  assert.equal(rows[2][1], "Vendor disbursement\nRef: PO-9981");
});

test("detectCsvHeaderAndRows disambiguates duplicate headers with column labels and index keys", () => {
  const { parseCsvLines, detectCsvHeaderAndRows } = getExports();
  const csv = [
    "Date,Narration,Amount,Amount,Balance",
    "24-08-2026,Settlement Alpha,10000.00,0.00,100000.00",
    "25-08-2026,Fee Beta,0.00,500.00,99500.00",
  ].join("\n");

  const rows = parseCsvLines(csv);
  const detected = detectCsvHeaderAndRows(rows);
  assert.notEqual(detected, null);
  assert.equal(detected.columns.length, 5);

  // First Amount column
  assert.equal(detected.columns[2].name, "Amount");
  assert.equal(detected.columns[2].key, "2");
  assert.equal(detected.columns[2].label, "Amount (Col 3)");

  // Second Amount column
  assert.equal(detected.columns[3].name, "Amount");
  assert.equal(detected.columns[3].key, "3");
  assert.equal(detected.columns[3].label, "Amount (Col 4)");

  // Data row access by key
  assert.equal(detected.dataRows[0]["2"], "10000.00");
  assert.equal(detected.dataRows[0]["3"], "0.00");
  assert.equal(detected.dataRows[1]["2"], "0.00");
  assert.equal(detected.dataRows[1]["3"], "500.00");
});

test("guessColumnMappings uses word boundary so Description never matches credit/amount", () => {
  const { guessColumnMappings } = getExports();
  const headers = ["Txn Date", "Description", "Ref Number", "Amount", "Balance"];

  // 1. String array input (backward compatibility)
  const guessedStr = guessColumnMappings(headers);
  assert.equal(guessedStr.narration, "Description");
  assert.notEqual(guessedStr.amount, "Description");
  assert.equal(guessedStr.amount, "Amount");

  // 2. CsvColumn descriptor input
  const columns = headers.map((h, idx) => ({
    index: idx,
    name: h,
    key: String(idx),
    label: h,
  }));
  const guessedCol = guessColumnMappings(columns);
  assert.equal(guessedCol.narration, "1"); // index of Description
  assert.equal(guessedCol.amount, "3");    // index of Amount (not 1)
});

test("detectCsvHeaderAndRows scans up to line 30 for table header", () => {
  const { parseCsvLines, detectCsvHeaderAndRows } = getExports();
  // 29 preamble lines, header on line 30 (index 29)
  const preamble = Array.from({ length: 29 }, (_, i) => `Metadata Line ${i + 1}`);
  const lines = [
    ...preamble,
    "Date,Description,Deposit,Withdrawal,Balance",
    "24-08-2026,Payout CMS123,50000.00,0.00,250000.00",
  ];
  const csv = lines.join("\n");
  const rows = parseCsvLines(csv);
  const detected = detectCsvHeaderAndRows(rows);

  assert.notEqual(detected, null);
  assert.equal(detected.headerIndex, 29);
  assert.equal(detected.columns[0].name, "Date");
  assert.equal(detected.columns[2].name, "Deposit");
  assert.equal(detected.dataRows.length, 1);
  assert.equal(detected.dataRows[0]["Date"], "24-08-2026");
});

test("guessColumnMappings detects both deposit and withdrawal for dual-column statements", () => {
  const { guessColumnMappings } = getExports();
  const headers = ["Value Date", "Description", "Instrument No", "Credit", "Debit", "Balance"];
  const guessed = guessColumnMappings(headers);

  assert.equal(guessed.date, "Value Date");
  assert.equal(guessed.narration, "Description");
  assert.equal(guessed.ref, "Instrument No");
  assert.equal(guessed.amount, "Credit");
  assert.equal(guessed.withdrawal, "Debit");
});

