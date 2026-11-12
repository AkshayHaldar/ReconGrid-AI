const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Compile and load the real src/lib/filters.ts module so tests execute actual production logic.
const source = readFileSync(path.join(__dirname, "../src/lib/filters.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

const filtersModule = {};
vm.runInNewContext(compiled, {
  exports: filtersModule,
  URLSearchParams,
});

const {
  isValidIsoDate,
  toDateKey,
  parseAmountInput,
  getDatePresetRange,
  detectDatePreset,
  filterReconciliationRecords,
  parseFilterSearchParams,
  buildFilterSearchParams,
} = filtersModule;

const sampleRecords = [
  {
    id: "rec-1",
    date: "2026-08-05T00:00:00Z",
    bank_amount: "4500.00",
    diagnostic_type: "EXACT_MATCH",
  },
  {
    id: "rec-2",
    date: "2026-08-10T00:00:00+00:00",
    bank_amount: "10000.00",
    diagnostic_type: "FEE_DEDUCTION",
  },
  {
    id: "rec-3",
    date: "2026-08-12T14:30:00Z",
    bank_amount: "25000.00",
    diagnostic_type: "TDS_194O_DEDUCTION",
  },
  {
    id: "rec-4",
    date: "2026-08-15T23:59:59Z",
    bank_amount: "9850.50",
    diagnostic_type: "EXACT_MATCH",
  },
  {
    id: "rec-5",
    date: "2026-08-20",
    bank_amount: "125000.00",
    diagnostic_type: "BATCHED_SETTLEMENT",
  },
];

test("filters records inclusively within startDate and endDate including end-of-day UTC timestamps", () => {
  const result = filterReconciliationRecords(sampleRecords, {
    startDate: "2026-08-10",
    endDate: "2026-08-15",
  });
  assert.deepEqual(
    result.map((r) => r.id),
    ["rec-2", "rec-3", "rec-4"]
  );
});

test("filters records with only startDate or only endDate specified", () => {
  const afterAug14 = filterReconciliationRecords(sampleRecords, {
    startDate: "2026-08-15",
  });
  assert.deepEqual(
    afterAug14.map((r) => r.id),
    ["rec-4", "rec-5"]
  );

  const upToAug10 = filterReconciliationRecords(sampleRecords, {
    endDate: "2026-08-10",
  });
  assert.deepEqual(
    upToAug10.map((r) => r.id),
    ["rec-1", "rec-2"]
  );
});

test("filters records by minAmount and maxAmount including comma-formatted and rupee-prefixed inputs", () => {
  const min10k = filterReconciliationRecords(sampleRecords, {
    minAmount: "10000",
  });
  assert.deepEqual(
    min10k.map((r) => r.id),
    ["rec-2", "rec-3", "rec-5"]
  );

  const minWithFormatting = filterReconciliationRecords(sampleRecords, {
    minAmount: "10,000",
    maxAmount: "₹30,000.00",
  });
  assert.deepEqual(
    minWithFormatting.map((r) => r.id),
    ["rec-2", "rec-3"]
  );
});

test("handles combined diagnostic, date range, and amount filters together", () => {
  const combined = filterReconciliationRecords(sampleRecords, {
    diagnostic: "FEE_DEDUCTION",
    startDate: "2026-08-10",
    endDate: "2026-08-15",
    minAmount: "10000",
  });
  assert.deepEqual(
    combined.map((r) => r.id),
    ["rec-2"]
  );
});

test("treats numeric zero as an explicit amount bound rather than unset", () => {
  const withZero = [
    { id: "z-0", date: "2026-08-01", bank_amount: "0.00", diagnostic_type: "EXACT_MATCH" },
    { id: "z-10", date: "2026-08-01", bank_amount: "10.00", diagnostic_type: "EXACT_MATCH" },
  ];
  const zeroMax = filterReconciliationRecords(withZero, { maxAmount: "0" });
  assert.deepEqual(
    zeroMax.map((r) => r.id),
    ["z-0"]
  );
});

test("validates calendar dates and extracts date keys safely", () => {
  assert.equal(isValidIsoDate("2026-08-15"), true);
  assert.equal(isValidIsoDate("2026-02-30"), false);
  assert.equal(isValidIsoDate("not-a-date"), false);
  assert.equal(toDateKey("2026-08-15T18:30:00Z"), "2026-08-15");
  assert.equal(parseAmountInput("₹ 25,000.50"), 25000.5);
  assert.equal(parseAmountInput(""), null);
});

const toPlain = (val) => JSON.parse(JSON.stringify(val));

test("computes and detects quick date presets deterministically", () => {
  const refDate = new Date(2026, 7, 15); // 15 Aug 2026 local
  const thisMonth = toPlain(getDatePresetRange("THIS_MONTH", refDate));
  assert.deepEqual(thisMonth, {
    startDate: "2026-08-01",
    endDate: "2026-08-31",
  });
  assert.equal(detectDatePreset("2026-08-01", "2026-08-31", refDate), "THIS_MONTH");

  const lastMonth = toPlain(getDatePresetRange("LAST_MONTH", refDate));
  assert.deepEqual(lastMonth, {
    startDate: "2026-07-01",
    endDate: "2026-07-31",
  });

  const last7 = toPlain(getDatePresetRange("LAST_7_DAYS", refDate));
  assert.deepEqual(last7, {
    startDate: "2026-08-09",
    endDate: "2026-08-15",
  });

  assert.equal(detectDatePreset("2026-08-10", "2026-08-15", refDate), "CUSTOM");
  assert.equal(detectDatePreset("", "", refDate), "ALL");
});

test("serializes and parses URL search params cleanly with sanitization", () => {
  const params = buildFilterSearchParams({
    status: "ALL",
    q: "",
    diagnostic: "ALL",
    startDate: "2026-08-01",
    endDate: "2026-08-15",
    minAmount: "",
    maxAmount: "",
  });
  assert.equal(params.toString(), "status=ALL&startDate=2026-08-01&endDate=2026-08-15");

  const parsed = toPlain(parseFilterSearchParams(params));
  assert.deepEqual(parsed, {
    status: "ALL",
    q: "",
    diagnostic: "ALL",
    startDate: "2026-08-01",
    endDate: "2026-08-15",
    minAmount: "",
    maxAmount: "",
  });

  // Clearing all filters returns an empty query string
  const cleared = buildFilterSearchParams({
    status: "ALL",
    q: "",
    diagnostic: "ALL",
    startDate: "",
    endDate: "",
    minAmount: "",
    maxAmount: "",
  });
  assert.equal(cleared.toString(), "");

  // Invalid query params are safely ignored / defaulted
  const malformed = new URLSearchParams("status=BOGUS&startDate=2026-99-99&minAmount=abc&maxAmount=10,000");
  const safeParsed = toPlain(parseFilterSearchParams(malformed));
  assert.deepEqual(safeParsed, {
    status: "ALL",
    q: "",
    diagnostic: "ALL",
    startDate: "",
    endDate: "",
    minAmount: "",
    maxAmount: "10,000",
  });
});
