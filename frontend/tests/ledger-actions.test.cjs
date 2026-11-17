const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

// Execute actual dashboard handlers with scheduling, child views and network
// boundaries replaced, to control partial writes and changes during loading.
function dashboard(api) {
  const updates = [];
  let refreshes = 0;
  const hooks = {
    ...React,
    useState: initial => [initial, value => updates.push(value)],
    useMemo: fn => fn(), useCallback: fn => fn, useEffect() {},
    useRef: value => ({ current: value }),
  };
  const exports = {};
  const source = readFileSync(path.join(__dirname, '../src/app/page.tsx'), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(code, {
    exports, console: { error() {} },
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return require(name);
      if (name === 'next/navigation') {
        return {
          useRouter: () => ({ replace() {}, push() {} }),
          usePathname: () => '/',
          useSearchParams: () => new URLSearchParams(),
        };
      }
      if (name === '@/lib/filters') {
        return {
          parseFilterSearchParams: () => ({
            status: "ALL",
            q: "",
            diagnostic: "ALL",
            startDate: "",
            endDate: "",
            minAmount: "",
            maxAmount: "",
          }),
          buildFilterSearchParams: () => new URLSearchParams(),
          normalizeAmountQueryParam: (val) =>
            val ? String(val).replace(/[₹,\s]/g, "").trim() : null,
        };
      }
      if (name === '@/lib/api') return { fetchStatus: async () => ({}), ...api };
      if (name === '@/lib/useLedgerRecords') return {
        useLedgerRecords: () => ({ records: [], loading: false, pager: {
          setRecords() {}, reload: async () => { refreshes++; },
        } }),
      };
      return new Proxy({}, { get: (_, key) => key });
    },
  });
  const tree = typeof exports.DashboardContent === 'function' ? exports.DashboardContent() : exports.default();
  function find(node, type) {
    if (!node || typeof node !== 'object') return;
    if (typeof node.type === 'function') {
      const rendered = node.type(node.props);
      const res = find(rendered, type);
      if (res) return res;
    }
    if (node.type === type) return node.props;
    for (const child of React.Children.toArray(node.props?.children)) {
      const result = find(child, type);
      if (result) return result;
    }
  }
  return { find: type => find(tree, type), updates, refreshes: () => refreshes };
}

test('partial batch failure refreshes committed rows and reports the failure', async () => {
  const approved = [];
  const page = dashboard({
    collectRecordWindows: async () => [{ id: 'a', confidence_score: 1 }, { id: 'b', confidence_score: 1 }],
    approveRecord: async id => { if (id === 'b') throw Error('request failed'); approved.push(id); },
  });
  await page.find('FilterBar').onBatchApprove();
  assert.deepEqual(approved, ['a']);
  assert.equal(page.refreshes(), 1);
  assert.ok(page.updates.some(value => typeof value === 'string' && value.includes('Some records may already be approved')));
  assert.equal(page.updates.at(-1), false);
});

test('a conflict removed during loading never opens with the stale row', async () => {
  const stale = { id: 'stale', rzp_settlement_db_id: 'settlement' };
  const page = dashboard({ collectRecordWindows: async () => [{ id: 'other' }] });
  await page.find('ReconciliationTable').onOpenConflict(stale);
  assert.equal(page.refreshes(), 1);
  assert.ok(!page.updates.includes(stale));
  assert.ok(page.updates.some(value => typeof value === 'string' && value.includes('conflict changed')));
});

test('an active conflict opens with the refreshed candidate', async () => {
  const stale = { id: 'same', rzp_settlement_db_id: 'settlement', diagnostic_note: 'old' };
  const fresh = { ...stale, diagnostic_note: 'current' };
  const page = dashboard({ collectRecordWindows: async () => [fresh] });
  await page.find('ReconciliationTable').onOpenConflict(stale);
  assert.ok(page.updates.includes(fresh));
  assert.ok(!page.updates.includes(stale));
});
