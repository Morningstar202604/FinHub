import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots';

const routes = [
  { path: '/dashboard',   name: '03-dashboard' },
  { path: '/finance',     name: '04-finance' },
  { path: '/market',      name: '05-market' },
  { path: '/automations', name: '06-automations' },
  { path: '/plugins',     name: '07-plugins' },
  { path: '/settings',    name: '08-settings' },
  { path: '/chat',        name: '09-chat' },
  { path: '/evals',       name: '10-evals' },
];

/** Close a page-intro overlay if one is showing. */
async function closeIntro(page) {
  const dlg = page.locator('.intro-dialog');
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.locator('button').last().click().catch(() => page.keyboard.press('Escape'));
    await page.waitForTimeout(800);
    console.log('  intro dialog closed');
  }
}

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});

/** New context with the setup gate pre-skipped (sessionStorage flag, per useSetupGate.ts). */
function newContext(opts) {
  const ctx = browser.newContext(opts);
  return ctx.then(async (c) => {
    await c.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
    return c;
  });
}

async function tour(ctx, tag) {
  const page = await ctx.newPage();
  for (const r of routes) {
    await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(3500);
    await closeIntro(page);
    const file = tag ? `${OUT}/${r.name}-${tag}.png` : `${OUT}/${r.name}.png`;
    await page.screenshot({ path: file });
    console.log('shot:', file);
  }
  await page.close();
}

// ---------- pass 1: light desktop ----------
await (async () => {
  const ctx = await newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.5 });
  await tour(ctx, '');
  await ctx.close();
})();

// ---------- pass 2: dark desktop ----------
await (async () => {
  const ctx = await newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.5 });
  await ctx.addInitScript(() => localStorage.setItem('theme', 'dark'));
  await tour(ctx, 'dark');
  await ctx.close();
})();

// ---------- pass 3: mobile (light) ----------
await (async () => {
  const ctx = await newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  for (const r of [routes[0], routes[2], routes[6]]) { // dashboard / market / chat
    await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(3500);
    await closeIntro(page);
    await page.screenshot({ path: `${OUT}/${r.name}-mobile.png` });
    console.log('shot:', `${r.name}-mobile`);
  }
  await page.close();
  await ctx.close();
})();

await browser.close();
console.log('DONE');
