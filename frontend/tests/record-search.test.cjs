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

function loadApi(fetch) {
  const exports = {};
  vm.runInNewContext(compiled, {
    exports,
    process: { env: {} },
    window: {},
    URLSearchParams,
    fetch,
  });
  return exports;
}

test("passes one abort signal through status and every paginated record request", async () => {
  const requests = [];
  const api = loadApi(async (url, options) => {
    requests.push({ url, signal: options.signal });
    if (url.endsWith("/status")) return Response.json({ data: { total_records: 401 } });
    const page = Number(new URL(url, "http://localhost").searchParams.get("page"));
    return Response.json({ data: { records: [{ id: `page-${page}` }], total_count: 401 } });
  });
  const controller = new AbortController();

  const [status, result] = await Promise.all([
    api.fetchStatus("batch", controller.signal),
    api.fetchAllRecords("batch", "MATCHED", "bank", controller.signal),
  ]);

  assert.equal(status.total_records, 401);
  assert.deepEqual(Array.from(result.records, (record) => record.id), ["page-1", "page-2", "page-3"]);
  assert.equal(requests.length, 4);
  assert.ok(requests.every((request) => request.signal === controller.signal));
  assert.ok(requests.filter((request) => request.url.includes("/records?")).every((request) => request.url.includes("status=MATCHED") && request.url.includes("q=bank")));
});

test("aborted first page prevents stale pagination from starting", async () => {
  const controller = new AbortController();
  const requests = [];
  const api = loadApi(async (url, options) => {
    requests.push(url);
    assert.equal(options.signal, controller.signal);
    controller.abort();
    return Response.json({ data: { records: [{ id: "old" }], total_count: 5000 } });
  });

  await assert.rejects(api.fetchAllRecords("batch", "ALL", "old", controller.signal), (error) => error.name === "AbortError");
  assert.equal(requests.length, 1);
});
