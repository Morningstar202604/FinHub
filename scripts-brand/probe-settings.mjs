// The settings controls reported "no visible effect" are the kind that mutate
// global state (html[data-theme], root font-size) rather than <main> text — which
// is all the bulk sweep watches. Verify each against the state it should change.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

const writes = [];
page.on('request', (r) => {
  if (['PATCH', 'POST', 'PUT', 'DELETE'].includes(r.method())) writes.push(`${r.method()} ${r.url().replace('http://localhost:8000', '').replace(BASE, '')}`);
});

await page.goto(BASE + '/settings?tab=userInfo', { waitUntil: 'domcontentloaded' });
await wait(3500);

const state = () => page.evaluate(() => ({
  theme: document.documentElement.getAttribute('data-theme'),
  themeLS: localStorage.getItem('theme'),
  rootFont: getComputedStyle(document.documentElement).fontSize,
  bodyFont: getComputedStyle(document.body).fontSize,
}));

// --- Theme buttons ---
for (const label of ['Dark', 'Light', 'Auto']) {
  const before = await state();
  const btn = page.getByRole('button', { name: label, exact: true }).first();
  const found = await btn.count();
  if (!found) { console.log(`theme "${label}": NOT FOUND`); continue; }
  await btn.click({ timeout: 3000 }).catch((e) => console.log(`theme "${label}" click err`, String(e).split('\n')[0]));
  await wait(900);
  const after = await state();
  const changed = before.theme !== after.theme || before.themeLS !== after.themeLS;
  console.log(`theme "${label}": ${changed ? 'WORKS' : 'NO EFFECT'}  data-theme ${before.theme} -> ${after.theme}  (localStorage ${before.themeLS} -> ${after.themeLS})`);
}

// --- Text-size buttons: whatever the labels are, they should change root font ---
const sizeBtns = await page.$$eval('button', (els) => els.map((e) => (e.textContent || '').trim()).filter((t) => /^\d{2,3}%$/.test(t)));
console.log('\ntext-size buttons found:', sizeBtns.join(', ') || '(none)');
for (const label of sizeBtns) {
  const before = await state();
  await page.getByRole('button', { name: label, exact: true }).first().click({ timeout: 3000 }).catch(() => {});
  await wait(700);
  const after = await state();
  console.log(`  "${label}": root ${before.rootFont} -> ${after.rootFont}  body ${before.bodyFont} -> ${after.bodyFont}  ${before.rootFont !== after.rootFont || before.bodyFont !== after.bodyFont ? 'WORKS' : 'NO EFFECT'}`);
}

// --- Voice Input toggle ---
writes.length = 0;
const vi = page.getByRole('switch', { name: /voice/i }).first();
const viCount = await vi.count();
if (viCount) {
  const before = await vi.getAttribute('aria-checked');
  await vi.click({ timeout: 3000 }).catch(() => {});
  await wait(1200);
  const after = await vi.getAttribute('aria-checked');
  console.log(`\nVoice Input switch: aria-checked ${before} -> ${after}  ${before !== after ? 'WORKS' : 'NO EFFECT'} | wire: ${writes.length ? writes.join(' , ') : '(none)'}`);
} else {
  console.log('\nVoice Input: no [role=switch] matched — locating by text');
  const el = page.getByText('Voice Input', { exact: true }).first();
  console.log('  element found:', await el.count(), '| tag:', await el.evaluate((e) => e.tagName + '.' + (e.className || '').toString().slice(0, 40)).catch(() => 'n/a'));
}

// --- Change Avatar ---
const av = page.getByRole('button', { name: /change avatar/i }).first();
if (await av.count()) {
  await av.click({ timeout: 3000 }).catch(() => {});
  await wait(1000);
  const fileInputs = await page.$$eval('input[type=file]', (els) => els.map((e) => ({ accept: e.accept, hidden: e.offsetParent === null })));
  const dialogs = await page.locator('[role="dialog"]').count();
  console.log(`\nChange Avatar: file inputs=${JSON.stringify(fileInputs)} dialogs=${dialogs}`);
}

await browser.close();
console.log('\nSETTINGS PROBE DONE');
