const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

function load(file, extra = {}) {
  const source = readFileSync(path.join(__dirname, "../src", file), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: (name) => extra[name] ?? require(name), Number, Intl });
  return exports;
}

const lib = load("lib/exportConfirm.ts");
const formatters = load("lib/formatters.ts");
const status = { total_records: 1240, matched_count: 1124, exception_count: 3 };

test("the summary names the batch, period, counts and the file that will download", () => {
  const summary = lib.buildExcelExportSummary(status, "default", "Nov 2026 Close (FY 26-27)");
  assert.equal(summary.fileName, "recongrid_audit_default.xlsx");
  const byLabel = Object.fromEntries(summary.rows.map((r) => [r.label, r.value]));
  assert.equal(byLabel.Batch, "default");
  assert.equal(byLabel.Period, "Nov 2026 Close (FY 26-27)");
  assert.equal(byLabel["Matched records"], "1,124");
  assert.equal(byLabel["Unresolved exceptions"], "3");
});

test("the summary still builds before the status has loaded", () => {
  const summary = lib.buildExcelExportSummary(null, "default", "Nov 2026 Close (FY 26-27)");
  assert.equal(summary.rows.find((r) => r.label === "Matched records").value, "-");
});

test("only Escape cancels", () => {
  assert.equal(lib.dialogKeyAction("Escape"), "cancel");
  assert.equal(lib.dialogKeyAction("Enter"), null);
  assert.equal(lib.dialogKeyAction("Tab"), null);
});

const { ExportConfirmModal } = load("components/ExportConfirmModal.tsx", {
  react: React,
  "@/lib/exportConfirm": lib,
  "@/lib/formatters": formatters,
});

function render(isOpen) {
  return renderToStaticMarkup(
    React.createElement(ExportConfirmModal, {
      isOpen,
      title: "Download Reconciliation Audit Workbook",
      status: { ...status, last_reconciled_at: "2026-11-20T06:00:00Z" },
      batchId: "default",
      confirmLabel: "Download Excel (.xlsx)",
      onConfirm() {},
      onCancel() {},
    })
  );
}

test("the dialog renders nothing while closed", () => {
  assert.equal(render(false), "");
});

test("the open dialog is an accessible modal with both actions and the summary", () => {
  const html = render(true);
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /Download Reconciliation Audit Workbook/);
  assert.match(html, /recongrid_audit_default\.xlsx/);
  assert.match(html, /Nov 2026 Close \(FY 26-27\)/);
  assert.match(html, /1,124/);
  assert.match(html, />Cancel</);
  assert.match(html, />Download Excel \(\.xlsx\)</);
});
