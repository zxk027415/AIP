// @AI_GENERATED
/**
 * 旅程连续性契约校验（任务 10.8，可选）。
 *
 * 无前端测试运行器（vitest/jest 未配置），故对 utils/journeyParams.ts 的「上下文合同」做
 * 结构化校验（design §32 / §33.2）：
 * 1. JOURNEY_PARAM 声明全部 6 个规范 query 名。
 * 2. 读取兼容历史别名：scenario←scenario_id、template←solution_id、workflowId←workflow_id。
 * 3. 写入只输出规范名（applySpine / buildJourneyHref 使用 JOURNEY_PARAM.*，不写别名字面量）。
 * 4. appendSearch 透传未消费参数（§33.2）。
 *
 * 说明：完整的「跨页导航后 scope 深链接保持 / 切换即清空下游」行为需浏览器 E2E（Playwright 未安装），
 * 属环境阻断；此处覆盖其可自动执行的纯函数契约核心。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(__dirname, '..', 'src', 'utils', 'journeyParams.ts'), 'utf-8');

const problems = [];

// 1. 6 个规范名。
const canonical = ['scenario_id', 'solution_id', 'slot', 'project_id', 'workflow_id', 'dataset_version_id'];
for (const name of canonical) {
  if (!new RegExp(`'${name}'`).test(src)) problems.push(`[CANONICAL] JOURNEY_PARAM 缺规范名 ${name}`);
}

// 2. 别名映射。
const aliasChecks = [
  ['scenario_id', 'scenario'],
  ['solution_id', 'template'],
  ['workflow_id', 'workflowId'],
];
const aliasBlock = (src.match(/PARAM_ALIASES[\s\S]*?};/) || [''])[0];
for (const [canon, alias] of aliasChecks) {
  const line = new RegExp(`${canon}:\\s*\\[[^\\]]*'${alias}'`);
  if (!line.test(aliasBlock)) problems.push(`[ALIAS] ${canon} 未兼容历史别名 ${alias}`);
}

// 3. 写入只输出规范名：applySpine 体内应使用 JOURNEY_PARAM.*，不得出现别名字面量。
const applyBlock = (src.match(/export function applySpine[\s\S]*?\n}/) || [''])[0];
for (const [, alias] of aliasChecks) {
  if (new RegExp(`'${alias}'`).test(applyBlock)) {
    problems.push(`[WRITE] applySpine 疑似写出别名 ${alias}（应只输出规范名）`);
  }
}
if (!/JOURNEY_PARAM\./.test(applyBlock)) problems.push('[WRITE] applySpine 未使用 JOURNEY_PARAM 规范名常量');

// 4. appendSearch 透传。
if (!/export function appendSearch/.test(src)) problems.push('[PASSTHROUGH] 缺少 appendSearch（未消费参数向下透传）');

// 5. readParam 优先规范名（别名数组第一个即规范名）。
if (!/aliases\[0\]|PARAM_ALIASES\[canonical\]\s*\?\?\s*\[canonical\]/.test(src) && !/const aliases = PARAM_ALIASES/.test(src)) {
  problems.push('[READ] readParam 未基于 PARAM_ALIASES 解析');
}

if (problems.length) {
  console.log(`JOURNEY_CHECK_FAILED count=${problems.length}`);
  for (const p of problems) console.log(p);
  process.exit(1);
}
console.log('JOURNEY_CHECK_OK 规范名齐全、别名读取兼容、写入只出规范名、透传契约在位');
// @AI_GENERATED: end
