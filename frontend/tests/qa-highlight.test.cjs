const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('globals.css defines citationPulse keyframes with 2.5s duration and emerald ring', () => {
  const css = readFileSync(path.join(__dirname, '../src/app/globals.css'), 'utf8');
  assert.ok(css.includes('@keyframes citationPulse'), 'Must contain citationPulse keyframes');
  assert.ok(css.includes('2.5s'), 'Animation duration must be 2.5s');
  assert.ok(css.includes('16, 185, 129'), 'Must pulse with audited emerald ring');
  assert.ok(css.includes('.citation-highlight'), 'Must declare citation-highlight class');
});

test('ReconciliationTable renders row with citation-highlight and without competing pulse animation classes', () => {
  const source = readFileSync(path.join(__dirname, '../src/components/ReconciliationTable.tsx'), 'utf8');
  assert.ok(source.includes('citation-highlight'), 'Row must include citation-highlight');
  assert.ok(!source.includes('animate-pulse'), 'Row must not compete with citation-highlight animation');
  assert.ok(!source.includes('ring-2 ring-inset'), 'Row must not compete with citation-highlight ring classes');
  assert.ok(!source.includes('ring-emerald-500/80'), 'Row must not include competing ring color classes');
  assert.ok(source.includes('scrollIntoView'), 'Must call scrollIntoView');
  assert.ok(source.includes('scrollToIndex'), 'Must call virtualizer scrollToIndex');
});

test('ReconciliationTable gates scroll effect strictly on pendingScrollTarget and waits for record in sortedRecords', () => {
  const source = readFileSync(path.join(__dirname, '../src/components/ReconciliationTable.tsx'), 'utf8');
  assert.ok(source.includes('const targetId = pendingScrollTarget.current?.id;'), 'Scroll effect must be gated strictly on pendingScrollTarget');
  assert.ok(!source.includes('scrollRequest?.id || pendingScrollTarget.current?.id || highlightedRecordId'), 'Must not fall back to props after pendingScrollTarget is cleared');
  assert.ok(source.includes('sortedRecords.some'), 'Highlight timer must wait until record is present in sortedRecords');
});
