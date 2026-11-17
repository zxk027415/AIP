// @AI_GENERATED
/**
 * P-UX-01 结构化校验（任务 9.2）：页面状态完整性 + 文案集中化。
 *
 * 无前端测试运行器（package.json 仅 dev/build/lint），故以静态结构校验替代运行时组件测试：
 * 1. types/scope.ts 声明的 10 动作状态 / 3 横切标记 / 5 禁用原因 / 6 readiness 状态，
 *    在 stateVocabulary.ts 中必须每一项都有集中文案（键覆盖）。
 * 2. ActionStateView.tsx 必须消费 stateVocabulary（集中文案，不散落字面量）。
 * 3. TypeScript 的 `Record<Enum, ...>` 已在编译期强制穷尽；本脚本是额外防线。
 *
 * 说明：真正的运行时“十状态渲染 + 无障碍”组件测试需要 vitest/jest（本项目未配置），
 * 因此这里只做可自动执行的静态完整性校验，并如实标注该限制。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, '..', 'src', 'pv-fault');

const scopeTs = readFileSync(join(SRC, 'types', 'scope.ts'), 'utf-8');
const vocabTs = readFileSync(join(SRC, 'copy', 'stateVocabulary.ts'), 'utf-8');
const actionViewTs = readFileSync(join(SRC, 'components', 'ActionStateView.tsx'), 'utf-8');

/** 从 `as const` 数组里提取字符串字面量成员。 */
function extractArray(text, constName) {
  const re = new RegExp(`${constName}[^=]*=\\s*\\[([\\s\\S]*?)\\]\\s*as const`, 'm');
  const m = text.match(re);
  if (!m) return [];
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
}

const problems = [];

const expected = {
  ACTION_STATES: { arr: extractArray(scopeTs, 'ACTION_STATES'), vocabs: ['ACTION_STATE_COPY', 'ACTION_STATE_ALERT_TYPE'], want: 10 },
  CROSS_CUTTING_MARKERS: { arr: extractArray(scopeTs, 'CROSS_CUTTING_MARKERS'), vocabs: ['CROSS_CUTTING_COPY'], want: 3 },
  DISABLED_REASON_TYPES: { arr: extractArray(scopeTs, 'DISABLED_REASON_TYPES'), vocabs: ['DISABLED_REASON_COPY'], want: 5 },
  READINESS_STATUSES: { arr: extractArray(scopeTs, 'READINESS_STATUSES'), vocabs: ['READINESS_COPY'], want: 6 },
};

for (const [name, spec] of Object.entries(expected)) {
  if (spec.arr.length !== spec.want) {
    problems.push(`[COUNT] ${name} 期望 ${spec.want} 项，实际 ${spec.arr.length}：${spec.arr.join(',')}`);
  }
  for (const member of spec.arr) {
    for (const vocab of spec.vocabs) {
      // 取该 vocab 的对象体，检查 member 作为键存在。
      const blockRe = new RegExp(`${vocab}[\\s\\S]*?=\\s*{([\\s\\S]*?)\\n};`, 'm');
      const block = vocabTs.match(blockRe);
      if (!block) {
        problems.push(`[VOCAB] 找不到文案对象 ${vocab}`);
        continue;
      }
      const keyRe = new RegExp(`(^|\\n)\\s*${member}\\s*:`);
      if (!keyRe.test(block[1])) {
        problems.push(`[MISSING-COPY] ${vocab} 缺少 ${member} 的文案`);
      }
    }
  }
}

// ActionStateView 必须消费集中文案。
for (const need of ['ACTION_STATE_COPY', 'ACTION_STATE_ALERT_TYPE', 'stateVocabulary']) {
  if (!actionViewTs.includes(need)) {
    problems.push(`[VIEW] ActionStateView 未引用 ${need}（文案应集中化）`);
  }
}

// 无障碍 spot check：ActionStateView 使用 Skeleton（加载态）与 Empty（初始空态）。
for (const need of ['Skeleton', 'Empty']) {
  if (!actionViewTs.includes(need)) {
    problems.push(`[A11Y] ActionStateView 缺少 ${need}（加载/空态结构）`);
  }
}

if (problems.length) {
  console.log(`PUX_CHECK_FAILED count=${problems.length}`);
  for (const p of problems) console.log(p);
  process.exit(1);
}
console.log('PUX_CHECK_OK 10 动作状态 / 3 横切 / 5 禁用原因 / 6 readiness 文案齐全，ActionStateView 集中消费文案');
// @AI_GENERATED: end
