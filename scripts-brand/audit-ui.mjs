import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = process.argv[2] || '/tmp/ui-elements.json';

const routes = [
  '/dashboard', '/finance', '/market', '/automations',
  '/plugins', '/settings', '/chat', '/evals',
];

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

const consoleErrors = [];
const failedRequests = [];
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push({ page: page.url(), text: m.text().slice(0, 300) });
});
page.on('response', (r) => {
  if (r.status() >= 400) failedRequests.push({ page: page.url(), url: r.url().slice(0, 180), status: r.status() });
});

const report = {};

for (const route of routes) {
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(4000);

  const els = await page.evaluate(() => {
    const seen = new Set();
    const out = [];
    const sel = ['button', '[role="button"]', '[role="tab"]', 'a[href]', 'input[type="checkbox"]',
                 'input[type="radio"]', 'select', '[role="switch"]', '[role="menuitem"]'];
    for (const s of sel) {
      for (const el of document.querySelectorAll(s)) {
        const rect = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        const visible = rect.width > 0 && rect.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
        if (!visible) continue;
        const label = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || el.getAttribute('placeholder') || '').trim().slice(0, 60);
        const key = `${s}|${label}|${Math.round(rect.x)},${Math.round(rect.y)}`;
        if (!label || seen.has(key)) continue;
        seen.add(key);
        out.push({
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute('type'),
          role: el.getAttribute('role'),
          label,
          disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
          href: el.getAttribute('href'),
          cls: (el.className || '').toString().slice(0, 80),
        });
      }
    }
    return out;
  });
  report[route] = els;
  console.log(`${route}: ${els.length} interactive elements`);
}

await browser.close();

const fs = await import('node:fs');
fs.writeFileSync(OUT, JSON.stringify({ report, consoleErrors, failedRequests }, null, 2));
console.log(`\nconsole errors: ${consoleErrors.length}`);
for (const e of consoleErrors.slice(0, 12)) console.log('  [console]', e.page.replace(BASE, ''), '|', e.text.slice(0, 160));
console.log(`failed requests: ${failedRequests.length}`);
for (const r of failedRequests.slice(0, 12)) console.log(`  [${r.status}]`, r.url.replace(BASE, '').replace('http://localhost:8000', ''));
console.log('DONE ->', OUT);
