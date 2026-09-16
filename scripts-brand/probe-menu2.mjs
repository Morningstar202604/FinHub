import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4500);

const trig = page.getByRole('button', { name: 'Options' });
const n = await trig.count();
console.log('Options triggers:', n);
for (let i = 0; i < n; i++) {
  const box = await trig.nth(i).boundingBox();
  console.log(`  [${i}]`, box ? `${Math.round(box.x)},${Math.round(box.y)} ${Math.round(box.width)}x${Math.round(box.height)}` : 'no box');
}

// Click the first and dump every portal-rendered surface.
await trig.first().click({ timeout: 4000 }).catch((e) => console.log('click err', String(e).split('\n')[0]));
await wait(1200);
await page.screenshot({ path: '/tmp/menu-open.png' });

const surfaces = await page.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll('body > div, body > div > div')) {
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 20) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none') continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: (el.className || '').toString().slice(0, 70),
      role: el.getAttribute('role'),
      dataState: el.getAttribute('data-state'),
      pe: cs.pointerEvents,
      opp: cs.opacity,
      rect: `${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.width)}x${Math.round(r.height)}`,
      nodeCount: el.querySelectorAll('*').length,
      text: (el.innerText || '').replace(/\s+/g, ' ').slice(0, 90),
    });
  }
  return out;
});
console.log('\n-- portal surfaces --');
for (const s of surfaces) console.log('  ', JSON.stringify(s));

const items = await page.evaluate(() => [...document.querySelectorAll('[role="menuitem"],[role="menu"]')].map((el) => {
  const r = el.getBoundingClientRect();
  return { role: el.getAttribute('role'), text: (el.textContent || '').trim().slice(0, 40), w: Math.round(r.width), h: Math.round(r.height) };
}));
console.log('\n-- menu nodes --', JSON.stringify(items));

await browser.close();
