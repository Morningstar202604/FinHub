/**
 * Showcase pass A — high-res screenshots for the repo / README / video cards.
 * 1920x1080 viewport @2x. Dark theme. Every core route settled before the shot.
 * (Video recording lives in showcase-video.mjs — separate passes keep the
 * screenshot crops deterministic.)
 */
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots/showcase';

const routes = [
  { path: '/dashboard', name: 'dashboard' },
  { path: '/finance', name: 'finance' },
  { path: '/market', name: 'market' },
  { path: '/chat', name: 'chat' },
  { path: '/plugins', name: 'plugins' },
  { path: '/automations', name: 'automations' },
  { path: '/evals', name: 'evals' },
  { path: '/settings?tab=userInfo', name: 'settings-user' },
  { path: '/settings?tab=agent', name: 'settings-agent' },
  { path: '/settings?tab=model', name: 'settings-model' },
];

async function closeIntro(page) {
  const dlg = page.locator('.intro-dialog');
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.locator('button').last().click().catch(() => page.keyboard.press('Escape'));
    await page.waitForTimeout(800);
  }
}

/** Wait until skeleton placeholders are gone (max 30s) — the dashboard needs
 * several quote/news round-trips before every widget resolves. */
async function settle(page) {
  await page.waitForFunction(() => document.querySelectorAll('[class*=skeleton]').length === 0,
    { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(3000);
}

/** The market quote header falls back to "0.00"/"—" while its snapshot is
 * still loading. Don't shoot the market route until a real price is shown. */
async function waitForMarketPrice(page) {
  await page.waitForFunction(() => {
    const el = document.querySelector('.stock-price');
    if (!el) return false;
    const t = (el.textContent || '').trim();
    return t !== '' && t !== '—' && t !== '0.00';
  }, { timeout: 20000 }).catch(() => {});
}

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});

// Warm-up pass: after a container restart vite recompiles every module on
// first request (2-3s each, 30+ modules) and the backend cold-starts its
// caches. Shooting straight into that window captures skeletons and default
// prices. Visit every route once in a throwaway 1x context first.
{
  const wctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await wctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  const wpage = await wctx.newPage();
  for (const r of routes) {
    const t0 = Date.now();
    try {
      await wpage.goto(BASE + r.path, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await settle(wpage);
    } catch (e) {
      console.error(`warm SKIP ${r.path}: ${e.message}`);
    }
    console.log(`warm: ${r.path} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  }
  await wctx.close();
}

for (const theme of ['dark', 'light']) {
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
  });
  await ctx.addInitScript((t) => {
    sessionStorage.setItem('finhub_setup_skipped', '1');
    localStorage.setItem('theme', t);
  }, theme);
  const page = await ctx.newPage();
  for (const r of routes) {
    const file = `${OUT}/${r.name}-${theme}.png`;
    try {
      await page.goto(BASE + r.path, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(4200);
      await closeIntro(page);
      await settle(page);
      if (r.name === 'market') await waitForMarketPrice(page);
      await page.screenshot({ path: file, timeout: 60000, animations: 'disabled' });
      console.log('shot:', file);
    } catch (e) {
      console.error(`FAIL ${file}: ${e.message}`);
    }
  }
  await ctx.close();
}

await browser.close();
console.log('showcase shots done');
