const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Execute the real API module with only its network boundary replaced. The
// existing TypeScript dependency removes type annotations; no test-only parser
// or duplicate upload implementation is involved.
const source = readFileSync(path.join(__dirname, "../src/lib/api.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

for (const password of [" leading", "trailing ", " both ", " ", "   ", "ordinary", "", undefined]) {
  test(`upload preserves password ${JSON.stringify(password)}`, async () => {
    const exports = {};
    const requests = [];
    vm.runInNewContext(compiled, {
      exports,
      process: { env: {} },
      window: {},
      FormData,
      fetch: async (url, options) => {
        requests.push({ url, ...options });
        return Response.json({ data: { inserted_count: 1 } });
      },
    });

    const file = new File(["synthetic PDF fixture"], "statement.pdf", { type: "application/pdf" });
    const result = await exports.uploadBankStatement(file, "test-batch", password);

    assert.equal(result.inserted_count, 1);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, "/api/v1/bank/upload");
    assert.equal(requests[0].method, "POST");
    assert.equal(requests[0].body.get("batch_id"), "test-batch");
    assert.equal(requests[0].body.get("file").name, "statement.pdf");
    assert.equal(requests[0].body.get("password"), password === undefined || password === "" ? null : password);
  });
}
