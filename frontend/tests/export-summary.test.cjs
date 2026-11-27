const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Runs the real export-summary module, with its types removed by the TypeScript
// compiler the project already depends on.
const source = readFileSync(path.join(__dirname, "../src/lib/export-summary.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, { exports: moduleExports });
const { buildExportSummary, exportFileName } = moduleExports;

test("the file name matches the one the backend sends", () => {
  assert.equal(exportFileName("default"), "recongrid_audit_default.xlsx");
  assert.equal(exportFileName("nov-2026"), "recongrid_audit_nov-2026.xlsx");
});

test("the summary reports the batch, the file and the matched count", () => {
  const summary = buildExportSummary({ matched_count: 124, exception_count: 0, conflict_count: 0 }, "default");
  assert.equal(summary.batchId, "default");
  assert.equal(summary.fileName, "recongrid_audit_default.xlsx");
  assert.equal(summary.matchedCount, 124);
});

test("exceptions and conflicts are counted together, like the workbook's Exceptions sheet", () => {
  const summary = buildExportSummary({ matched_count: 10, exception_count: 2, conflict_count: 1 }, "default");
  assert.equal(summary.exceptionCount, 3);
});

test("rows that are only suggested or pending are not counted as exceptions", () => {
  const summary = buildExportSummary(
    { matched_count: 10, exception_count: 0, conflict_count: 0, suggested_count: 5, pending_count: 4 },
    "default"
  );
  assert.equal(summary.exceptionCount, 0);
});

test("an empty batch shows zeros, not blanks", () => {
  const summary = buildExportSummary({ matched_count: 0, exception_count: 0, conflict_count: 0 }, "default");
  assert.equal(summary.matchedCount, 0);
  assert.equal(summary.exceptionCount, 0);
});

test("before the status has loaded, the counts are unknown rather than zero", () => {
  for (const status of [null, undefined]) {
    const summary = buildExportSummary(status, "default");
    assert.equal(summary.matchedCount, null);
    assert.equal(summary.exceptionCount, null);
    assert.equal(summary.fileName, "recongrid_audit_default.xlsx");
  }
});
