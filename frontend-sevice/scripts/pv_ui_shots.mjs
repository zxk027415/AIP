// @AI_GENERATED
/**
 * 浏览器 UI 验证（任务 7.5/8.4 + 用户要求的浏览器前端验证）。
 *
 * 用 Playwright(Chromium) 真实渲染工作台各页，逐页截图 + 采集 console/page 错误。
 * ProtectedRoute 仅查 localStorage.isLoggedIn，故 addInitScript 注入后即可进入 /projects。
 * 后端为隔离实时后端(8080)，前端 dev(5199) 代理 /api→8080；种子项目已由 _e2e_drive.py 建好。
 */

import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(__dirname, '..', '_e2e_shots');
mkdirSync(SHOTS, { recursive: true });

const BASE = process.env.PV_UI_BASE || 'http://localhost:3001';
const PID = process.argv[2] || 'proj-958c66ce2798';

// 每页附一个"内容已渲染"文本标记（截图前等它出现，避免截到 loading/skeleton）。
const pages = [
  ['01_project_list', `/projects`, '项目工作台'],
  ['02_overview', `/projects/${PID}/overview`, '三路径生命周期矩阵'],
  ['03_data', `/projects/${PID}/data`, '数据接入'],
  ['04_runs', `/projects/${PID}/runs?slot=pv_tsc`, '运行中心'],
  ['05_models_governance', `/projects/${PID}/models?slot=pv_tsc`, '当前检测模型'],
  ['06_reviews', `/projects/${PID}/reviews?slot=pv_tsc`, '审核'],
  ['07_cumulative', `/projects/${PID}/cumulative?slot=pv_tsc`, '累计'],
  ['08_operations_tsc', `/projects/${PID}/operations?slot=pv_tsc`, 'canonical'],
  ['09_operations_point', `/projects/${PID}/operations?slot=pv_point`, '回放'],
  ['10_operations_day', `/projects/${PID}/operations?slot=pv_day`, '生产事实'],
  ['11_validations', `/projects/${PID}/validations`, '跨数据集'],
  ['12_workflows', `/projects/${PID}/workflows?slot=pv_tsc`, '工作流'],
];

const report = [];

const browser = await chromium.launch({ headless: true });

for (const [name, path, marker] of pages) {
  // 每页独立 context（干净 localStorage），避免多页循环累积影响加载时序。
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(() => {
    localStorage.setItem('isLoggedIn', 'true');
    localStorage.setItem('lang', 'zh');
    localStorage.setItem('username', 'e2e');
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300));
  });
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)));
  let status = 'ok';
  let heading = '';
  let bodyLen = 0;
  let stageBandSeen = false;
  try {
    await page.goto(BASE + path, { waitUntil: 'load', timeout: 45000 });
    // 等页面特定内容标记出现（=真实内容已渲染，非骨架/loading）。
    stageBandSeen = await page
      .waitForFunction((m) => document.body && document.body.innerText.includes(m), marker, { timeout: 30000 })
      .then(() => true)
      .catch(() => false);
    await page.waitForTimeout(1200); // 内容出现后稍等布局稳定
    // 抓一级标题（h1-h5 或 ant-typography）文本，判断是否真渲染出内容。
    heading = await page.evaluate(() => {
      const el = document.querySelector('h1,h2,h3,h4,h5,.ant-typography,.ant-alert-message');
      return el ? el.textContent.trim().slice(0, 80) : '';
    });
    bodyLen = await page.evaluate(() => document.body.innerText.length);
    // animations:'disabled' 冻结 antd Skeleton shimmer / CSS 过渡到终态，避免 headless 截到骨架/过渡帧。
    await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true, animations: 'disabled' });
  } catch (e) {
    status = 'goto_fail: ' + String(e).slice(0, 200);
    try { await page.screenshot({ path: join(SHOTS, `${name}_err.png`) }); } catch { /* ignore */ }
  }
  report.push({ name, path, status, contentSeen: stageBandSeen, heading, bodyLen, consoleErrors: consoleErrors.slice(0, 5), pageErrors: pageErrors.slice(0, 5) });
  console.log(`${status === 'ok' ? 'OK ' : 'ERR'} | ${name} | content=${stageBandSeen} head="${heading}" bodyLen=${bodyLen} consoleErr=${consoleErrors.length} pageErr=${pageErrors.length}`);
  await page.close();
  await context.close();
}

writeFileSync(join(SHOTS, 'report.json'), JSON.stringify(report, null, 2), 'utf-8');
await browser.close();

const clean = report.filter((r) => r.status === 'ok' && r.pageErrors.length === 0 && r.bodyLen > 200).length;
console.log(`\nUI_SHOTS_SUMMARY clean=${clean}/${report.length} shots_dir=${SHOTS}`);
process.exit(0);
// @AI_GENERATED: end
