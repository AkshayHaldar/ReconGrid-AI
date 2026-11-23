const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Runs the real gatewayPulse module, with its types removed by the TypeScript compiler.
const source = readFileSync(path.join(__dirname, "../src/lib/gatewayPulse.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, { exports: moduleExports, require: () => ({}), Date, String, isNaN, Math, Intl });
const {
  GATEWAY_POLL_MS, pulseView, signatureLabel, ingestionLabel, formatRelative, formatEventTimestamp,
  hasSignatureFailure, hasMalformedPayload, rawBodyOf,
} = moduleExports;

const health = (status) => ({ status, last_verified_at: null, last_rejected_at: null, last_rejection_reason: null, message: "" });

test("the pulse polls every 30 seconds", () => {
  assert.equal(GATEWAY_POLL_MS, 30000);
});

test("each backend status maps to its colour and label", () => {
  assert.deepEqual([pulseView(health("live"), false).label, pulseView(health("live"), false).dotClass], ["Live", "bg-emerald-400"]);
  assert.deepEqual([pulseView(health("idle"), false).label, pulseView(health("idle"), false).dotClass], ["Idle", "bg-amber-400"]);
  assert.deepEqual([pulseView(health("warning"), false).label, pulseView(health("warning"), false).dotClass], ["Warning", "bg-red-500"]);
});

test("before the first answer it says checking, and a failed poll says unknown rather than idle", () => {
  assert.equal(pulseView(null, false).key, "checking");
  assert.equal(pulseView(null, true).key, "unknown");
});

test("an old answer is kept on screen when a later poll fails", () => {
  assert.equal(pulseView(health("live"), true).key, "live");
});

test("signature and ingestion labels", () => {
  assert.equal(signatureLabel("VALID"), "Valid HMAC");
  assert.equal(signatureLabel("INVALID"), "Failed");
  assert.equal(signatureLabel("MALFORMED"), "Malformed payload");
  assert.equal(ingestionLabel("RECONCILIATION_TRIGGERED"), "Reconciliation Triggered");
  assert.equal(ingestionLabel("IGNORED"), "Ignored");
  assert.equal(ingestionLabel("FAILED"), "Reconciliation Failed");
  assert.equal(ingestionLabel("REJECTED"), "Rejected");
});

test("relative time buckets", () => {
  const now = Date.parse("2026-11-23T12:00:00Z");
  assert.equal(formatRelative("2026-11-23T11:59:40Z", now), "just now");
  assert.equal(formatRelative("2026-11-23T11:55:00Z", now), "5 min ago");
  assert.equal(formatRelative("2026-11-23T09:00:00Z", now), "3 h ago");
  assert.equal(formatRelative("2026-11-20T12:00:00Z", now), "3 d ago");
});

test("relative time copes with missing, future and unreadable values", () => {
  const now = Date.parse("2026-11-23T12:00:00Z");
  assert.equal(formatRelative(null, now), "--");
  assert.equal(formatRelative("nonsense", now), "--");
  assert.equal(formatRelative("2026-11-23T12:05:00Z", now), "just now");
});

test("timestamps are shown in India's time zone", () => {
  const text = formatEventTimestamp("2026-08-24T09:00:15Z");
  assert.match(text, /24 Aug 2026/);
  assert.match(text, /02:30:15/);
  assert.equal(formatEventTimestamp("nonsense"), "--");
});

test("banner helpers look at the signature status", () => {
  const ev = (signature_status) => ({ signature_status });
  assert.equal(hasSignatureFailure([ev("INVALID"), ev("VALID")]), true);
  assert.equal(hasSignatureFailure([ev("INVALID"), ev("MALFORMED")]), true);
  assert.equal(hasSignatureFailure([ev("VALID"), ev("MALFORMED")]), false);
  assert.equal(hasMalformedPayload([ev("MALFORMED")]), true);
  assert.equal(hasMalformedPayload([]), false);
});

test("a verified delivery after a refusal clears its banner", () => {
  const ev = (signature_status) => ({ signature_status });
  // newest first: a good delivery arrived after the old failures
  assert.equal(hasSignatureFailure([ev("VALID"), ev("INVALID")]), false);
  assert.equal(hasMalformedPayload([ev("VALID"), ev("MALFORMED")]), false);
  assert.equal(hasSignatureFailure([ev("MALFORMED"), ev("VALID"), ev("INVALID")]), false);
});

test("rejected deliveries expose their raw text", () => {
  assert.equal(rawBodyOf({ raw_body: "{oops" }), "{oops");
  assert.equal(rawBodyOf({ event: "payout.updated" }), null);
});
