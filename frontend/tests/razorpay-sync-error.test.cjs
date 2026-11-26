const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadApi(bindings = {}) {
  const exports = {};
  const source = readFileSync(path.join(__dirname, "../src/lib/api.ts"), "utf8");
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

test("triggerRazorpaySync surfaces structured backend error code, status, and message on 401/502", async () => {
  const api = loadApi({
    fetch: async () => ({
      ok: false,
      status: 401,
      json: async () => ({
        success: false,
        data: null,
        error: {
          code: "RAZORPAY_UNAUTHORIZED",
          message: "Razorpay API rejected request with HTTP 401. Check Razorpay API credentials and parameters.",
          details: { upstream_status: 401 },
        },
      }),
    }),
  });

  await assert.rejects(
    () => api.triggerRazorpaySync(100, "batch alpha"),
    (err) => {
      assert.equal(err.code, "RAZORPAY_UNAUTHORIZED");
      assert.equal(err.status, 401);
      assert.deepEqual(err.details, { upstream_status: 401 });
      assert.match(err.message, /HTTP 401/);
      return true;
    }
  );
});

test("triggerRazorpaySync falls back to generic message when error body is unparseable", async () => {
  const api = loadApi({
    fetch: async () => ({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error("Invalid JSON");
      },
    }),
  });

  await assert.rejects(
    () => api.triggerRazorpaySync(50, "default"),
    (err) => {
      assert.equal(err.status, 502);
      assert.equal(err.message, "Failed to sync Razorpay settlements");
      return true;
    }
  );
});

test("DemoSyncModal surfaces errorMsg in alert banner on sync failure instead of mock success", () => {
  const modalSource = readFileSync(path.join(__dirname, "../src/components/DemoSyncModal.tsx"), "utf8");
  assert.match(modalSource, /setErrorMsg\(err\?\.message/);
  assert.match(modalSource, /role="alert"/);
  assert.doesNotMatch(modalSource, /mock sandbox gateway mode active/);
});
