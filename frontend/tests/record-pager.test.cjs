const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load(name, bindings = {}) {
  const exports = {};
  const source = readFileSync(path.join(__dirname, `../src/lib/${name}.ts`), 'utf8');
  vm.runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText,
    {
      exports,
      AbortController,
      URLSearchParams,
      Error,
      process: { env: {} },
      window: {},
      require: () => ({}),
      ...bindings,
    },
  );
  return exports;
}
const query = {
  batchId: 'default',
  status: 'ALL',
  search: '',
  diagnostic: 'ALL',
  sort: 'date',
  direction: 'desc',
};
const windowPage = (ids, next = null, total = null) => ({
  records: ids.map((id) => ({ id })),
  total_count: total,
  next_cursor: next,
  has_more: next !== null,
});
const ids = (pager) => Array.from(pager.getSnapshot().records, (row) => row.id);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};
const pagerWith = (fetchPage) => new (load('recordPager').RecordPager)(fetchPage);

test('initial load requests one window, not every page; continuation preserves order/count', async () => {
  const calls = [];
  const pager = pagerWith(async (q, cursor) => {
    calls.push(cursor);
    return cursor ? windowPage(['c'], null) : windowPage(['a', 'b'], 'next', 20000);
  });
  await pager.reset(query);
  assert.deepEqual(calls, [null]);
  assert.equal(pager.getSnapshot().totalCount, 20000);
  await pager.loadMore();
  assert.deepEqual(calls, [null, 'next']);
  assert.deepEqual(ids(pager), ['a', 'b', 'c']);
  assert.equal(pager.getSnapshot().totalCount, 20000);
  await pager.loadMore();
  assert.equal(calls.length, 2);
});

test('repeated bottom notifications start only one in-flight continuation', async () => {
  const next = deferred();
  let calls = 0;
  const pager = pagerWith(async () => (++calls === 1 ? windowPage(['a'], 'next') : next.promise));
  await pager.reset(query);
  const pending = pager.loadMore();
  await pager.loadMore();
  await pager.loadMore();
  assert.equal(calls, 2);
  next.resolve(windowPage(['b']));
  await pending;
});

test('query reset aborts old requests and ignores late results even if transport ignores abort', async () => {
  const first = deferred();
  const calls = [];
  const pager = pagerWith((q, cursor, signal) => {
    calls.push({ q, signal });
    return calls.length === 1 ? first.promise : Promise.resolve(windowPage(['new']));
  });
  const old = pager.reset(query);
  await pager.reset({ ...query, search: 'new filter', sort: 'bank_amount', direction: 'asc' });
  assert.equal(calls[0].signal.aborted, true);
  first.resolve(windowPage(['stale']));
  await old;
  assert.deepEqual(ids(pager), ['new']);
  assert.equal(calls[1].q.search, 'new filter');
});

test('append failure keeps existing rows and retries exactly the failed cursor', async () => {
  const calls = [];
  const pager = pagerWith(async (q, cursor) => {
    calls.push(cursor);
    if (calls.length === 1) return windowPage(['a'], 'next', 3);
    if (calls.length === 2) throw new Error('offline');
    return windowPage(['a', 'b']);
  });
  await pager.reset(query);
  await pager.loadMore();
  assert.deepEqual(ids(pager), ['a']);
  assert.equal(pager.getSnapshot().error, 'offline');
  await pager.loadMore();
  assert.equal(calls.length, 2);
  await pager.retry();
  assert.deepEqual(calls, [null, 'next', 'next']);
  assert.deepEqual(ids(pager), ['a', 'b']);
});

test('initial failure can retry, cancellation cannot publish a stale error', async () => {
  const pending = deferred();
  let calls = 0;
  const pager = pagerWith(async () => {
    calls++;
    if (calls === 1) throw new Error('initial failure');
    if (calls === 2) return windowPage(['ok']);
    return pending.promise;
  });
  await pager.reset(query);
  await pager.retry();
  assert.deepEqual(ids(pager), ['ok']);
  const request = pager.reset(query);
  pager.cancel();
  pending.reject(new Error('late failure'));
  await request;
  assert.equal(pager.getSnapshot().error, null);
});

test('citation anchor applies only to first window; reload preserves the anchor', async () => {
  const calls = [];
  const pager = pagerWith(async (q, cursor, signal, anchor) => {
    calls.push(anchor);
    return windowPage(['cited'], cursor ? null : 'next');
  });
  await pager.reset(query, 'cited');
  await pager.loadMore();
  await pager.reload();
  assert.deepEqual(calls, ['cited', undefined, 'cited']);
});

test('non-advancing or cyclic cursors surface an error instead of an infinite fetch loop', async () => {
  let call = 0;
  const pager = pagerWith(async () => windowPage([String(++call)], call === 2 ? 'B' : 'A'));
  await pager.reset(query);
  await pager.loadMore();
  await pager.loadMore();
  assert.match(pager.getSnapshot().error, /did not advance/);
  assert.deepEqual(ids(pager), ['1', '2']);
});

test('real API window includes filters, abort signal and cursor, omits offset paging', async () => {
  const requests = [];
  const api = load('api', {
    fetch: async (url, options) => {
      requests.push({ url, options });
      return Response.json({ data: windowPage([]) });
    },
  });
  const signal = new AbortController().signal;
  await api.fetchRecordWindow(
    {
      ...query,
      batchId: 'batch/a',
      diagnostic: 'FEE_DEDUCTION',
      settlementId: 'settle',
      startDate: '2026-08-01',
      endDate: '2026-08-10',
      minAmount: '500',
      maxAmount: '10000',
    },
    'opaque+/=',
    signal,
  );
  const url = new URL(requests[0].url, 'http://test');
  assert.match(url.pathname, /batch%2Fa/);
  assert.equal(url.searchParams.get('cursor'), 'opaque+/=');
  assert.equal(url.searchParams.get('limit'), '200');
  assert.equal(url.searchParams.get('diagnostic'), 'FEE_DEDUCTION');
  assert.equal(url.searchParams.get('settlement_id'), 'settle');
  assert.equal(url.searchParams.get('start_date'), '2026-08-01');
  assert.equal(url.searchParams.get('end_date'), '2026-08-10');
  assert.equal(url.searchParams.get('min_amount'), '500');
  assert.equal(url.searchParams.get('max_amount'), '10000');
  assert.equal(url.searchParams.has('page'), false);
  assert.equal(requests[0].options.signal, signal);
});

test('explicit whole-selection collection walks windows sequentially', async () => {
  let active = 0,
    peak = 0;
  const cursors = [];
  const api = load('api', {
    fetch: async (url) => {
      active++;
      peak = Math.max(peak, active);
      const cursor = new URL(url, 'http://test').searchParams.get('cursor');
      cursors.push(cursor);
      await Promise.resolve();
      active--;
      return Response.json({ data: cursor ? windowPage(['b']) : windowPage(['a'], 'next') });
    },
  });
  const rows = await api.collectRecordWindows(query);
  assert.deepEqual(
    Array.from(rows, (row) => row.id),
    ['a', 'b'],
  );
  assert.deepEqual(cursors, [null, 'next']);
  assert.equal(peak, 1);
});
