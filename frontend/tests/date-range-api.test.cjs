const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function load(name, bindings = {}) {
  const exports = {};
  const source = readFileSync(path.join(__dirname, `../src/lib/${name}.ts`), "utf8");
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
    }
  );
  return exports;
}

test("fetchRecordWindow includes from_date and to_date when provided in query", async () => {
  const requests = [];
  const api = load("api", {
    fetch: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () => ({
          data: {
            records: [],
            total_count: 0,
            next_cursor: null,
            has_more: false,
          },
        }),
      };
    },
  });

  await api.fetchRecordWindow({
    batchId: "default",
    status: "ALL",
    search: "",
    diagnostic: "ALL",
    sort: "date",
    direction: "desc",
    fromDate: "2026-04-01",
    toDate: "2026-06-30",
  });

  assert.equal(requests.length, 1);
  const url = new URL(requests[0].url, "http://test");
  assert.equal(url.searchParams.get("from_date"), "2026-04-01");
  assert.equal(url.searchParams.get("to_date"), "2026-06-30");
});

test("fetchRecordWindow supports snake_case from_date and to_date", async () => {
  const requests = [];
  const api = load("api", {
    fetch: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () => ({
          data: {
            records: [],
            total_count: 0,
            next_cursor: null,
            has_more: false,
          },
        }),
      };
    },
  });

  await api.fetchRecordWindow({
    batchId: "default",
    status: "ALL",
    search: "",
    diagnostic: "ALL",
    sort: "date",
    direction: "desc",
    from_date: "2026-10-01",
    to_date: "2026-12-31",
  });

  assert.equal(requests.length, 1);
  const url = new URL(requests[0].url, "http://test");
  assert.equal(url.searchParams.get("from_date"), "2026-10-01");
  assert.equal(url.searchParams.get("to_date"), "2026-12-31");
});

test("fetchReconciliationRecords passes from_date and to_date to API endpoint", async () => {
  const requests = [];
  const api = load("api", {
    fetch: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () => ({
          data: {
            records: [],
            total_count: 0,
          },
        }),
      };
    },
  });

  // Call with positional args
  await api.fetchReconciliationRecords("default", "MATCHED", "search-term", 1, 50, "2026-07-01", "2026-09-30");
  assert.equal(requests.length, 1);
  const url1 = new URL(requests[0].url, "http://test");
  assert.equal(url1.searchParams.get("from_date"), "2026-07-01");
  assert.equal(url1.searchParams.get("to_date"), "2026-09-30");
  assert.equal(url1.searchParams.get("status"), "MATCHED");

  // Call with options object
  await api.fetchReconciliationRecords({
    batchId: "b1",
    status: "EXCEPTION",
    from_date: "2026-01-01",
    to_date: "2026-03-31",
  });
  assert.equal(requests.length, 2);
  const url2 = new URL(requests[1].url, "http://test");
  assert.equal(url2.searchParams.get("from_date"), "2026-01-01");
  assert.equal(url2.searchParams.get("to_date"), "2026-03-31");
  assert.equal(url2.searchParams.get("status"), "EXCEPTION");
});
