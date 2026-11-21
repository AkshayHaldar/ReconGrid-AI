const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/lib/rowMeasure.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = {};
vm.runInNewContext(compiled, { exports: mod });
const { observedBlockSize } = mod;

test("prefers borderBoxSize when the engine reports it", () => {
  assert.equal(observedBlockSize({ borderBoxSize: [{ blockSize: 52.6 }], contentRect: { height: 40 } }), 53);
});

test("falls back to contentRect when borderBoxSize is missing", () => {
  assert.equal(observedBlockSize({ contentRect: { height: 48.2 } }), 48);
  assert.equal(observedBlockSize({ borderBoxSize: [], contentRect: { height: 61 } }), 61);
});

test("returns undefined when nothing usable was observed", () => {
  assert.equal(observedBlockSize(undefined), undefined);
  assert.equal(observedBlockSize({}), undefined);
  assert.equal(observedBlockSize({ contentRect: { height: 0 } }), undefined);
  assert.equal(observedBlockSize({ contentRect: { height: NaN } }), undefined);
});

test("spacer colSpan matches the number of table header columns", () => {
  const src = readFileSync(
    path.join(__dirname, "../src/components/ReconciliationTable.tsx"),
    "utf8",
  );
  const span = Number(/const SPACER_COLSPAN = (\d+);/.exec(src)[1]);
  const thead = /<thead[\s\S]*?<\/thead>/.exec(src)[0];
  const headers = (thead.match(/<th[\s>]/g) || []).length;
  assert.equal(span, headers);
});
