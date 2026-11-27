const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/lib/fiscalDate.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, { exports: moduleExports, Date, String, Number, isNaN, Math, Intl, RegExp });
const {
  getDatePartsIST,
  getCurrentIndianQuarter,
  getPreviousIndianQuarter,
  getLast30Days,
  getTodayIST,
  formatCompactDate,
  formatCompactDateShort,
} = moduleExports;

test("an August date falls in Q2 (Jul-Sep) of the fiscal year that started that April", () => {
  const q = getCurrentIndianQuarter("2026-08-15T06:00:00Z");
  assert.equal(q.quarter, "Q2");
  assert.equal(q.quarterNumber, 2);
  assert.equal(q.fyLabel, "FY 26-27");
  assert.equal(q.fromDate, "2026-07-01");
  assert.equal(q.toDate, "2026-09-30");
});

test("April date starts Q1 (Apr-Jun)", () => {
  const q = getCurrentIndianQuarter("2027-04-01T06:00:00Z");
  assert.equal(q.quarter, "Q1");
  assert.equal(q.quarterNumber, 1);
  assert.equal(q.fyLabel, "FY 27-28");
  assert.equal(q.fromDate, "2027-04-01");
  assert.equal(q.toDate, "2027-06-30");
});

test("October date falls in Q3 (Oct-Dec)", () => {
  const q = getCurrentIndianQuarter("2026-11-22T06:00:00Z");
  assert.equal(q.quarter, "Q3");
  assert.equal(q.quarterNumber, 3);
  assert.equal(q.fyLabel, "FY 26-27");
  assert.equal(q.fromDate, "2026-10-01");
  assert.equal(q.toDate, "2026-12-31");
});

test("January date falls in Q4 (Jan-Mar) of the fiscal year that started the previous April", () => {
  const q = getCurrentIndianQuarter("2026-01-15T06:00:00Z");
  assert.equal(q.quarter, "Q4");
  assert.equal(q.quarterNumber, 4);
  assert.equal(q.fyLabel, "FY 25-26");
  assert.equal(q.fromDate, "2026-01-01");
  assert.equal(q.toDate, "2026-03-31");
});

test("March date is the last month of Q4", () => {
  const q = getCurrentIndianQuarter("2027-03-31T06:00:00Z");
  assert.equal(q.quarter, "Q4");
  assert.equal(q.quarterNumber, 4);
  assert.equal(q.fyLabel, "FY 26-27");
  assert.equal(q.fromDate, "2027-01-01");
  assert.equal(q.toDate, "2027-03-31");
});

test("previous quarter from Q1 is Q4 of the previous fiscal year", () => {
  const prev = getPreviousIndianQuarter("2026-05-10T06:00:00Z"); // In Q1 FY 26-27
  assert.equal(prev.quarter, "Q4");
  assert.equal(prev.quarterNumber, 4);
  assert.equal(prev.fyLabel, "FY 25-26");
  assert.equal(prev.fromDate, "2026-01-01");
  assert.equal(prev.toDate, "2026-03-31");
});

test("previous quarter from Q2 is Q1 of the same fiscal year", () => {
  const prev = getPreviousIndianQuarter("2026-08-20T06:00:00Z"); // In Q2 FY 26-27
  assert.equal(prev.quarter, "Q1");
  assert.equal(prev.quarterNumber, 1);
  assert.equal(prev.fyLabel, "FY 26-27");
  assert.equal(prev.fromDate, "2026-04-01");
  assert.equal(prev.toDate, "2026-06-30");
});

test("previous quarter from Q3 is Q2 of the same fiscal year", () => {
  const prev = getPreviousIndianQuarter("2026-11-22T06:00:00Z"); // In Q3 FY 26-27
  assert.equal(prev.quarter, "Q2");
  assert.equal(prev.quarterNumber, 2);
  assert.equal(prev.fyLabel, "FY 26-27");
  assert.equal(prev.fromDate, "2026-07-01");
  assert.equal(prev.toDate, "2026-09-30");
});

test("previous quarter from Q4 is Q3 of the same fiscal year", () => {
  const prev = getPreviousIndianQuarter("2026-02-15T06:00:00Z"); // In Q4 FY 25-26
  assert.equal(prev.quarter, "Q3");
  assert.equal(prev.quarterNumber, 3);
  assert.equal(prev.fyLabel, "FY 25-26");
  assert.equal(prev.fromDate, "2025-10-01");
  assert.equal(prev.toDate, "2025-12-31");
});

test("IST timezone is used around midnight across UTC boundaries", () => {
  // 19:00 UTC on 31 March is 00:30 IST on 1 April (Q1 FY 26-27)
  const qApr = getCurrentIndianQuarter("2026-03-31T19:00:00Z");
  assert.equal(qApr.quarter, "Q1");
  assert.equal(qApr.fyLabel, "FY 26-27");
  assert.equal(qApr.fromDate, "2026-04-01");

  // 18:00 UTC on 31 March is 23:30 IST on 31 March (Q4 FY 25-26)
  const qMar = getCurrentIndianQuarter("2026-03-31T18:00:00Z");
  assert.equal(qMar.quarter, "Q4");
  assert.equal(qMar.fyLabel, "FY 25-26");
  assert.equal(qMar.fromDate, "2026-01-01");
});

test("last 30 days accurately produces a 30-day ISO date span ending on ref date", () => {
  const range = getLast30Days("2026-11-22T06:00:00Z");
  assert.equal(range.toDate, "2026-11-22");
  assert.equal(range.fromDate, "2026-10-24");
  assert.equal(range.label, "Last 30 Days");
});

test("formatting compact dates formats nicely for pill display", () => {
  assert.equal(formatCompactDate("2026-07-01"), "1 Jul 2026");
  assert.equal(formatCompactDate("2026-09-30"), "30 Sep 2026");
  assert.equal(formatCompactDateShort("2026-07-01"), "1 Jul");
  assert.equal(formatCompactDateShort("2026-09-30"), "30 Sep");
});


for (const reference of ["2024-03-01T06:00:00Z", "2026-03-01T06:00:00Z", "2026-01-01T06:00:00Z", "2026-03-31T19:00:00Z", "2026-03-31T18:00:00Z"]) {
  test(`last 30 days includes exactly 30 calendar dates at ${reference}`, () => {
    const range = getLast30Days(reference);
    assert.equal((Date.parse(range.toDate) - Date.parse(range.fromDate)) / 86400000 + 1, 30);
    const { year, month, day } = getDatePartsIST(reference);
    assert.equal(range.toDate, `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
  });
}
