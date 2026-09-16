// Probe: load dashboard once, capture which bars/quotes endpoints are hit
// and how long they take, so backend Cache HIT/MISS lines can be correlated.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
import fs from 'node:fs';
const BASE = 'http://localhost:5173';
const OUT = process.env.OUT || '/tmp/probe-dash.json';

(async () => {
  const browser = await chromium.launch({
    headless: true, chromiumSandbox: false,
    executablePath: '/opt/google/chrome/chrome',
  });
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2,
  });
  await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  const page = await ctx.newPage();
  const t0 = Date.now();
  const reqs = [];
  page.on('response', async (r) => {
    const u = r.url();
    if (u.includes('/api/')) {
      reqs.push({ url: u.replace(BASE, ''), status: r.status(), ms: Date.now() - t0 });
    }
  });
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(20000);
  await page.screenshot({ path: '/tmp/probe-dash.png' });
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(reqs, null, 1));
  const slow = reqs.filter((r) => r.ms > 2000);
  console.log('total api:', reqs.length, '| slow(>2s):', slow.length);
  slow.slice(0, 15).forEach((r) => console.log(' ', r.status, String(r.ms).padStart(6) + 'ms', r.url.slice(0, 110)));
})();
