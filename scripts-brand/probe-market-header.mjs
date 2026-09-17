import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const BASE = 'http://localhost:5173';
const b = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const p = await ctx.newPage();
const snaps = [];
p.on('response', async (r) => {
  const u = r.url();
  if (u.includes('/market-data/snapshots/stocks') && u.includes('GOOGL')) {
    try { const j = await r.json(); snaps.push(JSON.stringify(j).slice(0, 400)); } catch {}
  }
});
await p.goto(BASE + '/market', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(12000);
const header = await p.evaluate(() => {
  const el = document.querySelector('.stock-price');
  return el ? el.textContent : '(no .stock-price)';
});
const change = await p.evaluate(() => {
  const el = document.querySelector('.stock-change');
  return el ? el.textContent : '(no .stock-change)';
});
console.log('STOCK-PRICE:', JSON.stringify(header));
console.log('STOCK-CHANGE:', JSON.stringify(change));
console.log('GOOGL SNAPSHOT RESPONSES:');
snaps.forEach((s, i) => console.log(`  [${i}] ${s}`));
await b.close();
