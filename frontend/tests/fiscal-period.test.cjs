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
vm.runInNewContext(compiled, { exports: moduleExports, Date, String, isNaN, Math });
const { formatFiscalPeriod } = moduleExports;

test("an August date is in the fiscal year that started the previous April", () => {
  assert.equal(formatFiscalPeriod(new Date(2026, 7, 15)), "Aug 2026 Close (FY 26-27)");
});

test("April starts a new fiscal year", () => {
  assert.equal(formatFiscalPeriod(new Date(2027, 3, 1)), "Apr 2027 Close (FY 27-28)");
});

test("March is the last month of the fiscal year", () => {
  assert.equal(formatFiscalPeriod(new Date(2027, 2, 31)), "Mar 2027 Close (FY 26-27)");
});

test("January still belongs to the fiscal year that began the April before", () => {
  assert.equal(formatFiscalPeriod(new Date(2026, 0, 10)), "Jan 2026 Close (FY 25-26)");
});

test("the fiscal year rolls over the century correctly", () => {
  assert.equal(formatFiscalPeriod(new Date(2099, 5, 1)), "Jun 2099 Close (FY 99-00)");
});

test("an ISO date string from the API works", () => {
  assert.equal(formatFiscalPeriod("2026-11-14T10:30:00"), "Nov 2026 Close (FY 26-27)");
});

test("without a date it uses today", () => {
  assert.equal(formatFiscalPeriod(), formatFiscalPeriod(new Date()));
  assert.equal(formatFiscalPeriod(null), formatFiscalPeriod(new Date()));
});

test("a date it cannot read falls back to today", () => {
  assert.equal(formatFiscalPeriod("not a date"), formatFiscalPeriod(new Date()));
});
