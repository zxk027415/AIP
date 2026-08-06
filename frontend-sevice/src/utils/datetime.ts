/**
 * 后端时间戳展示工具
 *
 * 后端（如 backend-service/services/iterative_labeling/*）统一用
 * `datetime.utcnow().isoformat()` 产出时间戳，结果是**不带时区标识**的裸字符串，
 * 例如 `2026-08-03T08:34:56.500738`。
 *
 * 按 ECMAScript 规范，ISO 日期时间形式在缺少偏移量时按**本地时间**解释，
 * 于是 `new Date(value)` 会把 UTC 值当成本地值，页面显示比真实时间早 8 小时
 * （UTC+8 环境）。这里在解析前补上 `Z`，把「裸字符串即 UTC」这个后端约定显式化。
 *
 * 已带 `Z` 或 `±HH:MM` 的字符串保持原样，因此对未来改为时区感知输出的后端也安全。
 */
// @AI_GENERATED
const TIMEZONE_SUFFIX = /(?:Z|[+-]\d{2}:\d{2})$/i;

/**
 * 把后端时间戳格式化为本机时区的可读字符串。
 *
 * @param value 后端返回的 ISO 时间戳；裸字符串按 UTC 处理。
 * @param fallback 空值时的占位文本。
 * @returns 本地时区字符串；无法解析时原样返回输入，避免丢信息。
 */
export function formatBackendDateTime(value: unknown, fallback = '—'): string {
  const raw = String(value ?? '').trim();
  if (!raw) return fallback;
  const normalized = TIMEZONE_SUFFIX.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString('zh-CN', { hour12: false });
}
// @AI_GENERATED: end
