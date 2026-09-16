// /evals Refresh: the sweep logged "no visible effect" because the reload
// round-trips too fast to observe, and its 404 is the intended empty state.
// Verify the button's own contract: disabled + spinner while fetching.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

await page.goto(BASE + '/evals', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3800);

const before = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => /refresh/i.test(b.innerText || ''));
  return btn ? {
    text: btn.innerText.trim(),
    disabled: btn.disabled,
    spinner: !!btn.querySelector('.animate-spin'),
    hasText: !!(btn.innerText || '').trim(),
    bodyText: (document.querySelector('main')?.innerText || '').replace(/\s+/g, ' ').slice(0, 120),
  } : null;
});
console.log('refresh button at rest:', JSON.stringify(before));

// Click and sample the transient fetching state.
const reqs = [];
page.on('request', (r) => { if (r.url().includes('/evals/report')) reqs.push(r.url()); });
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => /refresh/i.test(b.innerText || ''));
  btn?.click();
});
for (const delay of [30, 120, 400]) {
  await page.waitForTimeout(delay);
  const snap = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find((b) => /refresh/i.test(b.innerText || ''));
    return btn ? { disabled: btn.disabled, spinner: !!btn.querySelector('.animate-spin') } : null;
  });
  console.log(`  +${delay}ms ->`, JSON.stringify(snap));
}

await page.waitForTimeout(1500);
const after = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => /refresh/i.test(b.innerText || ''));
  const main = (document.querySelector('main')?.innerText || '').replace(/\s+/g, ' ');
  return {
    disabled: btn?.disabled, spinner: !!btn?.querySelector('.animate-spin'),
    showsEmptyState: /no report|empty|yet/i.test(main),
    mainSnippet: main.slice(0, 140),
  };
});
console.log('\nafter settle:', JSON.stringify(after));
console.log('evals/report requests fired:', reqs.length);
console.log('\nEMPTY STATE TEXT:', after.mainSnippet);

await browser.close();
console.log('EVALS PROBE DONE');
