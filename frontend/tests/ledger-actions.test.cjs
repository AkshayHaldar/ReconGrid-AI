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
      if (name === '@/lib/api') return { fetchStatus: async () => ({}), ...api };
      if (name === '@/lib/useLedgerRecords') return {
        useLedgerRecords: () => ({ records: [], loading: false, pager: {
          setRecords() {}, reload: async () => { refreshes++; },
        } }),
      };
      return new Proxy({}, { get: (_, key) => key });
    },
  });
  const tree = exports.default();
  function find(node, type) {
    if (!node || typeof node !== 'object') return;
    if (node.type === type) return node.props;
    for (const child of React.Children.toArray(node.props?.children)) {
      const result = find(child, type);
      if (result) return result;
    }
  }
  return { find: type => find(tree, type), updates, refreshes: () => refreshes };
}

test('uncertain batch response refreshes the ledger before a retry', async () => {
  let requests = 0;
  const page = dashboard({
    batchApprove: async () => { requests++; throw Error('response lost'); },
  });
  await page.find('FilterBar').onBatchApprove();
  assert.equal(requests, 1);
  assert.equal(page.refreshes(), 1);
  assert.ok(page.updates.some(value => typeof value === 'string' && value.includes('could not be confirmed')));
  assert.equal(page.updates.at(-1), false);
});

test('batch approval sends one request and reports the server count', async () => {
  const requests = [];
  const page = dashboard({
    batchApprove: async (...args) => { requests.push(args); return { approved_count: 3 }; },
  });
  await page.find('FilterBar').onBatchApprove();
  assert.deepEqual(requests, [['default', 0.9]]);
  assert.equal(page.refreshes(), 1);
  assert.ok(page.updates.some(value => value?.message?.includes('Approved 3 high-confidence suggestions')));
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
