// @AI_GENERATED
/** Temporary Playwright smoke for PathAggregateTable responsive sizing. */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const base = process.env.PV_UI_BASE || 'http://localhost:3001';
const outDir = join(process.cwd(), '_e2e_shots', 'path-aggregate-layout');
mkdirSync(outDir, { recursive: true });

const cases = [
  { name: 'accuracy-1440-default', route: '/accuracy-operations', width: 1440, height: 900, sidebar: 200 },
  { name: 'accuracy-1280-wide-sidebar', route: '/accuracy-operations', width: 1280, height: 800, sidebar: 420 },
  { name: 'deployment-1280-wide-sidebar', route: '/algorithm-deployment', width: 1280, height: 800, sidebar: 420 },
  { name: 'accuracy-390-mobile', route: '/accuracy-operations', width: 390, height: 844, sidebar: 200 },
];

const browser = await chromium.launch({ headless: true });
const results = [];
let failed = false;

for (const item of cases) {
  const context = await browser.newContext({ viewport: { width: item.width, height: item.height } });
  await context.addInitScript((sidebar) => {
    localStorage.setItem('isLoggedIn', 'true');
    localStorage.setItem('lang', 'zh');
    localStorage.setItem('username', 'layout-smoke');
    localStorage.setItem('mainLayout.sidebarWidth', String(sidebar));
  }, item.sidebar);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.goto(base + item.route, { waitUntil: 'load', timeout: 45_000 });
  await page.waitForSelector('.ant-table-tbody > tr', { timeout: 45_000 });
  await page.waitForTimeout(600);

  const metrics = await page.evaluate(() => {
    const content = document.querySelector('.ant-table-content');
    const table = content?.querySelector('table');
    const headers = [...document.querySelectorAll('.ant-table-thead th')].map((cell) => ({
      text: cell.textContent?.trim() || '(action)',
      width: Math.round(cell.getBoundingClientRect().width),
      whiteSpace: getComputedStyle(cell).whiteSpace,
    }));
    const firstRowWidths = [...document.querySelectorAll('.ant-table-tbody > tr:first-child > td')]
      .map((cell) => Math.round(cell.getBoundingClientRect().width));
    return {
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      contentClientWidth: content?.clientWidth || 0,
      contentScrollWidth: content?.scrollWidth || 0,
      tableWidth: table ? Math.round(table.getBoundingClientRect().width) : 0,
      tableLayout: table ? getComputedStyle(table).tableLayout : '',
      headers,
      firstRowWidths,
    };
  });

  const readableColumns = metrics.headers.length === 6
    && metrics.headers.every((header) => header.width >= 120);
  const internalScroll = metrics.contentScrollWidth >= 1150
    && metrics.contentScrollWidth >= metrics.contentClientWidth;
  const noBodyOverflow = metrics.documentScrollWidth <= metrics.viewport + 2;
  const passed = readableColumns && internalScroll && noBodyOverflow
    && metrics.tableLayout === 'fixed' && pageErrors.length === 0;
  failed ||= !passed;

  await page.screenshot({
    path: join(outDir, `${item.name}.png`),
    fullPage: true,
    animations: 'disabled',
  });
  results.push({ ...item, passed, pageErrors, ...metrics });
  console.log(`${passed ? 'PASS' : 'FAIL'} ${item.name}`, JSON.stringify(metrics));
  await context.close();
}

await browser.close();
writeFileSync(join(outDir, 'report.json'), JSON.stringify(results, null, 2), 'utf8');
console.log(`report=${join(outDir, 'report.json')}`);
process.exit(failed ? 1 : 0);
// @AI_GENERATED: end
