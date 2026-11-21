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

const lib = load("lib/tallyExportConfirm.ts");
const formatters = load("lib/formatters.ts");
const status = { matched_count: 1124, last_reconciled_at: "2026-11-20T06:00:00Z" };

test("the summary shows batch, fiscal year and the voucher estimate", () => {
  const summary = lib.buildTallyExportSummary(status, "default", "Nov 2026 Close (FY 26-27)");
  const byLabel = Object.fromEntries(summary.rows.map((r) => [r.label, r.value]));
  assert.equal(byLabel.Batch, "default");
  assert.equal(byLabel["Accounting period"], "FY 26-27");
  assert.equal(byLabel["Journal vouchers (up to)"], "1,124");
  assert.equal(summary.fileName, "reconciliation_tally_vouchers.xml");
});

test("the summary still builds before the status has loaded", () => {
  const summary = lib.buildTallyExportSummary(null, "default", "Nov 2026 Close (FY 26-27)");
  assert.equal(summary.rows.find((r) => r.label.startsWith("Journal")).value, "-");
});

test("only Escape cancels", () => {
  assert.equal(lib.dialogKeyAction("Escape"), "cancel");
  assert.equal(lib.dialogKeyAction("Enter"), null);
});

const { TallyExportModal } = load("components/TallyExportModal.tsx", {
  react: React,
  "@/lib/tallyExportConfirm": lib,
  "@/lib/formatters": formatters,
});

function render(isOpen) {
  return renderToStaticMarkup(
    React.createElement(TallyExportModal, { isOpen, status, batchId: "default", onConfirm() {}, onCancel() {} })
  );
}

test("the dialog renders nothing while closed", () => {
  assert.equal(render(false), "");
});

test("the open dialog is an accessible modal with the summary and both actions", () => {
  const html = render(true);
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /Export Tally XML Vouchers/);
  assert.match(html, /FY 26-27/);
  assert.match(html, /1,124/);
  assert.match(html, />Cancel</);
  assert.match(html, />Confirm &amp; Download XML</);
});
