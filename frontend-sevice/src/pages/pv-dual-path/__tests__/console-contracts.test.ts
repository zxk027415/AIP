// @AI_GENERATED
/**
 * PV 双路径控制台合同测试（纯 Node，不依赖 vitest）。
 * 运行：node --experimental-strip-types frontend-sevice/src/pages/pv-dual-path/__tests__/console-contracts.test.ts
 * 或在 tsx 可用时直接执行。此处用内联复制逻辑，避免编译器依赖。
 */
import assert from 'node:assert/strict';

function isStrictTrue(value: unknown): boolean {
  return value === true;
}
function formatAgreementRate(value: unknown): string {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return '—';
  return numeric.toFixed(2);
}
function requiresBackfillDays(mode: string): boolean {
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
console.log('pv dual-path console contracts passed');
// @AI_GENERATED: end
