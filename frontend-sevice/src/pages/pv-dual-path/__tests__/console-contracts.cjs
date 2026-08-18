// @AI_GENERATED
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function isStrictTrue(value) {
  return value === true;
}
function formatAgreementRate(value) {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return '—';
  return numeric.toFixed(2);
}
function requiresBackfillDays(mode) {
  return mode === 'recent_window';
}

assert.equal(isStrictTrue(true), true);
assert.equal(isStrictTrue('true'), false);
assert.equal(isStrictTrue(1), false);
assert.equal(requiresBackfillDays('recent_window'), true);
assert.equal(requiresBackfillDays('cutover_only'), false);
assert.equal(formatAgreementRate(0.876), '0.88');
assert.equal(formatAgreementRate(0.8), '0.80');
const statuses = ['waiting_data', 'ready', 'running', 'succeeded', 'failed', 'revision_pending'];
assert.equal(statuses.length, 6);

const srcRoot = path.resolve(__dirname, '../../..');
const layout = fs.readFileSync(path.join(srcRoot, 'components/MainLayout.tsx'), 'utf8');
const app = fs.readFileSync(path.join(srcRoot, 'App.tsx'), 'utf8');
const deployment = fs.readFileSync(path.join(srcRoot, 'pages/AlgorithmDeploymentPage.tsx'), 'utf8');
const accuracy = fs.readFileSync(path.join(srcRoot, 'pages/AccuracyOperationsPage.tsx'), 'utf8');
assert.equal(layout.includes("label: 'PV 双路径控制台'"), false);
assert.equal(layout.includes("key: '/pv-dual-path'"), false);
assert.equal(app.includes('slot=pv_fault&tab=governance'), true);
assert.equal(deployment.includes('PvDualPathGovernancePanel'), true);
assert.equal(deployment.includes('双路径治理'), true);
assert.equal(accuracy.includes('PvDualPathOperationsPanel'), true);
assert.equal(accuracy.includes("value: 'pv_fault'"), true);
console.log('pv dual-path console contracts passed');
// @AI_GENERATED: end
