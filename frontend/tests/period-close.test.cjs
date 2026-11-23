const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

function compile(file) {
  const source = readFileSync(path.join(__dirname, "../src", file), "utf8");
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true, target: ts.ScriptTarget.ES2020 },
  }).outputText;
}

function load(file, sandbox = {}) {
  const exports = {};
  vm.runInNewContext(compile(file), { exports, process: { env: {} }, window: {}, Date, Intl, Number, String, Math, isNaN, ...sandbox });
  return exports;
}

test("period label is the calendar month read in India's time zone", () => {
  const { formatPeriodLabel } = load("lib/formatters.ts");
  assert.equal(formatPeriodLabel("2026-08-15T06:00:00Z"), "Aug 2026");
  // 00:30 IST on 1 September is still 31 August in UTC.
  assert.equal(formatPeriodLabel("2026-08-31T19:00:00Z"), "Sep 2026");
});

test("lockBatch posts the sign-off and returns the lock record", async () => {
  const requests = [];
  const api = load("lib/api.ts", {
    fetch: async (url, options) => {
      requests.push({ url, ...options });
      return Response.json({ data: { batch_id: "Q1/26", is_locked: true, locked_by: "CA Ramesh" } });
    },
  });
  const result = await api.lockBatch("Q1/26", "CA Ramesh", "");
  assert.equal(result.is_locked, true);
  assert.equal(requests[0].url, "/api/v1/reconciliation/Q1%2F26/lock");
  assert.equal(requests[0].method, "POST");
  assert.deepEqual(JSON.parse(requests[0].body), { locked_by: "CA Ramesh", lock_note: null });
});

test("a failed pre-flight surfaces the server message and code", async () => {
  const api = load("lib/api.ts", {
    fetch: async () =>
      Response.json({ error: { code: "PREFLIGHT_FAILED", message: "1 unresolved CONFLICT record(s)." } }, { status: 422 }),
  });
  await assert.rejects(api.lockBatch("default", "CA Ramesh"), (err) => {
    assert.equal(err.message, "1 unresolved CONFLICT record(s).");
    assert.equal(err.code, "PREFLIGHT_FAILED");
    return true;
  });
});

test("approve, deny, resolve and batch approve map HTTP 423 to a BATCH_LOCKED error", async () => {
  const api = load("lib/api.ts", { fetch: async () => new Response("{}", { status: 423 }) });
  const calls = [
    () => api.approveRecord("r1"),
    () => api.denyRecord("r1"),
    () => api.resolveConflict("r1", "setl_1"),
    () => api.batchApprove("default"),
  ];
  for (const call of calls) {
    await assert.rejects(call(), (err) => err.code === "BATCH_LOCKED" && /locked/.test(err.message));
  }
  // Other failures keep their generic message.
  const other = load("lib/api.ts", { fetch: async () => new Response("{}", { status: 500 }) });
  await assert.rejects(other.approveRecord("r1"), /Failed to approve record/);
});

// The dashboard, with children replaced by name so props can be inspected.
function dashboard(status, api = {}) {
  let stateCalls = 0;
  const hooks = {
    ...React,
    useState: (initial) => [stateCalls++ === 0 ? status : initial, () => {}],
    useMemo: (fn) => fn(), useCallback: (fn) => fn, useEffect() {},
    useRef: (value) => ({ current: value }),
  };
  const exports = {};
  vm.runInNewContext(compile("app/page.tsx"), {
    exports, console: { error() {} },
    require(name) {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return require(name);
      if (name === "@/lib/api") return { fetchStatus: async () => status, ...api };
      if (name === "@/lib/useLedgerRecords") {
        return { useLedgerRecords: () => ({ records: [{ id: "r1", bank_utr: "U1" }], loading: false, pager: { setRecords() {}, reload: async () => {} } }) };
      }
      return new Proxy({}, { get: (_, key) => key });
    },
  });
  const tree = exports.default();
  const find = (node, type) => {
    if (!node || typeof node !== "object") return;
    if (node.type === type) return node.props;
    for (const child of React.Children.toArray(node.props?.children)) {
      const found = find(child, type);
      if (found) return found;
    }
  };
  return (type) => find(tree, type);
}

const LOCKED = { total_records: 5, is_locked: true, locked_by: "CA Ramesh", locked_at: "2026-09-02T10:00:00Z", lock_note: "Audited" };

test("a locked batch makes the header, filter bar and ledger read-only", () => {
  const find = dashboard(LOCKED);
  const header = find("Header");
  assert.equal(header.isLocked, true);
  assert.equal(header.lockedBy, "CA Ramesh");
  assert.equal(header.lockNote, "Audited");
  assert.equal(find("FilterBar").isLocked, true);
  assert.equal(find("ReconciliationTable").isLocked, true);
});

test("an open batch keeps the ledger editable and offers the sign-off action", () => {
  const find = dashboard({ total_records: 5, is_locked: false });
  assert.equal(find("Header").isLocked, false);
  assert.equal(typeof find("Header").onOpenSignOff, "function");
  assert.equal(find("ReconciliationTable").isLocked, false);
});

test("handlers send no write requests while the batch is locked", async () => {
  const calls = [];
  const record = (name) => async () => { calls.push(name); return {}; };
  const find = dashboard(LOCKED, {
    approveRecord: record("approve"), denyRecord: record("deny"), batchApprove: record("batch"),
    resolveConflict: record("resolve"), collectRecordWindows: record("conflicts"),
  });
  const table = find("ReconciliationTable");
  await table.onApprove("r1");
  await table.onDeny("r1");
  await table.onOpenConflict({ id: "r1", rzp_settlement_db_id: "s1" });
  await find("FilterBar").onBatchApprove();
  await find("ConflictDrawer").onResolve("r1", "setl_1");
  assert.deepEqual(calls, []);
});

test("sign-off modal lists the pre-flight checks and blocks confirm until they pass", () => {
  const preflight = {
    can_lock: false,
    unresolved_variance: "100.00",
    checks: [
      { id: "NO_CONFLICTS", label: "Zero unresolved CONFLICT records", passed: false, detail: "1 unresolved CONFLICT record(s)." },
      { id: "NO_PENDING_SETTLEMENT", label: "Zero items awaiting gateway settlement data", passed: true, detail: "Nothing waiting on gateway sync." },
      { id: "TRIAL_BALANCE", label: "Trial balance is in balance", passed: false, detail: "Trial balance difference is INR 100.00" },
    ],
  };
  let n = 0;
  const hooks = { ...React, useState: (initial) => [n++ === 0 ? preflight : initial, () => {}], useEffect() {} };
  const exports = {};
  vm.runInNewContext(compile("components/SignOffModal.tsx"), {
    exports,
    require(name) {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return require(name);
      if (name === "@/lib/api") return { fetchLockStatus: async () => ({}), lockBatch: async () => ({}) };
      if (name === "@/lib/formatters") return { formatINR: (v) => `Rs ${v}`, formatPeriodLabel: () => "Aug 2026" };
      return new Proxy({}, { get: () => () => null });
    },
  });
  const html = renderToStaticMarkup(
    React.createElement(exports.SignOffModal, { isOpen: true, onClose() {}, batchId: "default", onLocked() {} })
  );
  assert.match(html, /Close &amp; Sign Off Period \(Aug 2026\)/);
  for (const c of preflight.checks) assert.ok(html.includes(c.label));
  assert.match(html, /1 unresolved CONFLICT record\(s\)\./);
  assert.match(html, /<button[^>]*disabled[^>]*>(?:(?!<\/button>).)*Confirm Close &amp; Lock/s);
});
