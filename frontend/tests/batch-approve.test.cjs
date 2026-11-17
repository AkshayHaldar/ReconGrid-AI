const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/lib/api.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

test("batch approval sends one threshold request and returns the server count", async () => {
  const exports = {};
  const requests = [];
  vm.runInNewContext(compiled, {
    exports,
    process: { env: {} },
    window: {},
    fetch: async (url, options) => {
      requests.push({ url, ...options });
      return Response.json({ data: { approved_count: 51, batch_id: "november" } });
    },
  });

  const result = await exports.batchApprove("november", 0.95);
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { approved_count: 51, batch_id: "november" });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/v1/reconciliation/november/batch-approve");
  assert.equal(requests[0].method, "POST");
  assert.deepEqual(JSON.parse(requests[0].body), { min_confidence: 0.95 });
});

test("batch approval encodes reserved characters in batch IDs", async () => {
  const exports = {};
  const requests = [];
  vm.runInNewContext(compiled, {
    exports,
    process: { env: {} },
    window: {},
    fetch: async (url) => {
      requests.push(url);
      return Response.json({ data: { approved_count: 0, batch_id: "Q1/2026?foo" } });
    },
  });

  await exports.batchApprove("Q1/2026?foo");
  assert.equal(requests[0], "/api/v1/reconciliation/Q1%2F2026%3Ffoo/batch-approve");
});
