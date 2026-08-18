// @AI_GENERATED
/** PV 双路径控制台纯逻辑：严格 boolean confirm、刷新延迟、一致率两位小数。 */

export const PV_DUAL_PATH_REFRESH_MS = 3000;

export function isStrictTrue(value: unknown): boolean {
  return value === true;
}

export function formatAgreementRate(value: unknown): string {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return '—';
  return numeric.toFixed(2);
}

export function requiresBackfillDays(mode: string): boolean {
  return mode === 'recent_window';
}

export function isCrossPath(currentPath: string, targetPath: string): boolean {
  return Boolean(currentPath && targetPath && currentPath !== targetPath);
}

export function ledgerStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    waiting_data: '等待数据',
    ready: '可运行',
    running: '处理中',
    succeeded: '已成功',
    failed: '失败',
    revision_pending: '待修订',
  };
  return labels[status] || status;
}
// @AI_GENERATED: end
