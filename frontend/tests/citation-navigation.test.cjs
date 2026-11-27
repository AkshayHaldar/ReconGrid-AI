const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

// Execute the table with the same stateful hook approach as ledger-actions.
// The virtualizer, DOM mounts and clock are controlled independently.
function tableHarness() {
  const slots = [], effects = [], timers = new Map(), mounted = new Map();
  const scrolls = [], indexes = [], consumed = [];
  let cursor = 0, now = 0, timerId = 0, props, tree;
  const equal = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const hooks = {
    ...React,
    useState(initial) {
      const i = cursor++;
      if (!slots[i]) slots[i] = { value: initial };
      return [slots[i].value, value => { slots[i].value = typeof value === 'function' ? value(slots[i].value) : value; }];
    },
    useRef(initial) { const i = cursor++; return slots[i] ||= { current: initial }; },
    useMemo(fn, deps) { const i = cursor++; if (!slots[i] || !equal(slots[i].deps, deps)) slots[i] = { deps, value: fn() }; return slots[i].value; },
    useCallback(fn, deps) { return hooks.useMemo(() => fn, deps); },
    useEffect(fn, deps) {
      const i = cursor++;
      if (!slots[i] || !equal(slots[i].deps, deps)) effects.push(() => {
        slots[i]?.cleanup?.();
        slots[i] = { deps, cleanup: fn() };
      });
    },
  };
  const virtualizer = {
    scrollToIndex: i => indexes.push(i),
    getVirtualItems: () => props.records.map((_, index) => ({ index, start: index * 53, end: (index + 1) * 53 })),
    getTotalSize: () => props.records.length * 53,
    measureElement() {},
  };
  const exports = {};
  const source = readFileSync(path.join(__dirname, '../src/components/ReconciliationTable.tsx'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  vm.runInNewContext(code, {
    exports, console,
    document: { getElementById: id => mounted.get(id.slice(7)) || null },
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, at: now + delay }); return id; },
    clearTimeout: id => timers.delete(id),
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return require(name);
      if (name === '@tanstack/react-virtual') return { useVirtualizer: () => virtualizer };
      return new Proxy({}, { get: (_, key) => key });
    },
  });
  const render = (changes = {}, flush = true) => {
    props = { records: [], loading: false, serverSort: { field: 'date', order: 'desc' }, onScrollConsumed: nonce => consumed.push(nonce), ...props, ...changes };
    cursor = 0;
    tree = exports.ReconciliationTable(props);
    if (flush) while (effects.length) effects.shift()();
    return tree;
  };
  const rows = () => {
    const found = [];
    const visit = node => {
      if (!node || typeof node !== 'object') return;
      if (node.props?.r && node.props?.onRowMount) found.push(node.props);
      React.Children.toArray(node.props?.children).forEach(visit);
    };
    visit(tree);
    return found;
  };
  const mount = id => {
    const row = rows().find(r => r.r.id === id);
    assert.ok(row, `missing row ${id}`);
    const node = { scrollIntoView: options => scrolls.push({ id, options }) };
    mounted.set(id, node);
    row.onRowMount(id, node);
  };
  const advance = ms => {
    now += ms;
    for (const [id, timer] of timers) if (timer.at <= now) { timers.delete(id); timer.fn(); }
  };
  const unmount = () => slots.forEach(slot => slot?.cleanup?.());
  return { render, rows, mount, advance, unmount, scrolls, indexes, consumed, timers, effects };
}

test('delayed mounting consumes a jump once and updates do not scroll again', () => {
  const h = tableHarness();
  const request = { id: 'a', nonce: 1 };
  h.render({ scrollRequest: request });
  assert.equal(h.indexes.length, 0);
  h.render({ records: [{ id: 'a' }] });
  assert.deepEqual(h.indexes, [0]);
  assert.equal(h.scrolls.length, 0);
  assert.equal(h.timers.size, 0);
  h.mount('a');
  assert.deepEqual(h.consumed, [1]);
  assert.equal(h.scrolls.length, 1);
  assert.equal(h.scrolls[0].options.behavior, 'smooth');
  h.render({ records: [{ id: 'a' }, { id: 'b' }] });
  h.mount('a');
  h.render({ records: [{ id: 'a', date: '2026-01-01' }, { id: 'b' }] });
  assert.equal(h.scrolls.length, 1);
  assert.deepEqual(h.consumed, [1]);
});

test('repeated selection restarts the highlight and clears 2.5 seconds after mounting', () => {
  const h = tableHarness();
  h.render({ records: [{ id: 'a' }], scrollRequest: { id: 'a', nonce: 1 } });
  h.mount('a');
  h.render();
  assert.equal(h.rows()[0].highlightNonce, 1);
  h.advance(2000);
  h.render({ scrollRequest: { id: 'a', nonce: 2 } });
  h.render();
  assert.equal(h.rows()[0].highlightNonce, 2);
  h.advance(500);
  h.render();
  assert.equal(h.rows()[0].isHighlighted, true);
  h.advance(1999);
  h.render();
  assert.equal(h.rows()[0].isHighlighted, true);
  h.advance(1);
  h.render();
  assert.equal(h.rows()[0].isHighlighted, false);
  assert.deepEqual(h.consumed, [1, 2]);
  assert.equal(h.scrolls.length, 2);
});

test('rapid selections ignore an old mount and cancel the old highlight timer', () => {
  const h = tableHarness();
  h.render({ records: [{ id: 'a' }, { id: 'b' }], scrollRequest: { id: 'a', nonce: 1 } });
  h.render({ scrollRequest: { id: 'b', nonce: 2 } });
  h.mount('a');
  assert.equal(h.scrolls.length, 0);
  h.mount('b');
  assert.deepEqual(h.consumed, [2]);
  h.render();
  assert.equal(h.rows()[1].isHighlighted, true);
  h.advance(1000);
  h.render({ scrollRequest: { id: 'a', nonce: 3 } });
  h.mount('a');
  h.render();
  h.advance(1500);
  h.render();
  assert.equal(h.rows()[0].isHighlighted, true);
  h.advance(1000);
  h.render();
  assert.equal(h.rows()[0].isHighlighted, false);
  assert.deepEqual(h.consumed, [2, 3]);
});

test('a stale row mounting during a new selection commit cannot consume the old request', () => {
  const h = tableHarness();
  h.render({ records: [{ id: 'a' }, { id: 'b' }], scrollRequest: { id: 'a', nonce: 1 } });
  h.render({ scrollRequest: { id: 'b', nonce: 2 } }, false);
  h.mount('a');
  assert.equal(h.scrolls.length, 0);
  while (h.effects.length) h.effects.shift()();
  h.mount('b');
  assert.deepEqual(h.consumed, [2]);
});

test('unmount cancels the active highlight timer', () => {
  const h = tableHarness();
  h.render({ records: [{ id: 'a' }], scrollRequest: { id: 'a', nonce: 1 } });
  h.mount('a');
  assert.equal(h.timers.size, 1);
  h.unmount();
  assert.equal(h.timers.size, 0);
});
