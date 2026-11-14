const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Runs the real formatters module, with its types removed by the TypeScript
// compiler the project already depends on.
const source = readFileSync(path.join(__dirname, "../src/lib/formatters.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, { exports: moduleExports, Date, String, Number, isNaN, Math, Intl });
const { formatFiscalPeriod } = moduleExports;

test("an August date is in the fiscal year that started the previous April", () => {
  assert.equal(formatFiscalPeriod("2026-08-15T06:00:00Z"), "Aug 2026 Close (FY 26-27)");
});

test("April starts a new fiscal year", () => {
  assert.equal(formatFiscalPeriod("2027-04-15T06:00:00Z"), "Apr 2027 Close (FY 27-28)");
});

test("March is the last month of the fiscal year", () => {
  assert.equal(formatFiscalPeriod("2027-03-15T06:00:00Z"), "Mar 2027 Close (FY 26-27)");
});

test("January still belongs to the fiscal year that began the April before", () => {
  assert.equal(formatFiscalPeriod("2026-01-10T06:00:00Z"), "Jan 2026 Close (FY 25-26)");
});

test("the fiscal year rolls over the century correctly", () => {
  assert.equal(formatFiscalPeriod("2099-06-01T06:00:00Z"), "Jun 2099 Close (FY 99-00)");
});

test("the month is read in India's time zone, not the viewer's", () => {
  // 00:30 IST on 1 April is still 31 March in UTC and in the Americas.
  assert.equal(formatFiscalPeriod("2026-03-31T19:00:00Z"), "Apr 2026 Close (FY 26-27)");
  // 23:30 IST on 31 March.
  assert.equal(formatFiscalPeriod("2026-03-31T18:00:00Z"), "Mar 2026 Close (FY 25-26)");
  // The same moment written with an offset gives the same label.
  assert.equal(formatFiscalPeriod("2026-04-01T00:30:00+05:30"), "Apr 2026 Close (FY 26-27)");
});

test("a date from the API without a time works", () => {
  assert.equal(formatFiscalPeriod("2026-11-14"), "Nov 2026 Close (FY 26-27)");
});

test("without a date it uses today", () => {
  assert.equal(formatFiscalPeriod(), formatFiscalPeriod(new Date()));
  assert.equal(formatFiscalPeriod(null), formatFiscalPeriod(new Date()));
});

test("a date it cannot read falls back to today", () => {
  assert.equal(formatFiscalPeriod("not a date"), formatFiscalPeriod(new Date()));
});
