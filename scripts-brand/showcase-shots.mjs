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

/** Wait until skeleton placeholders are gone (max 22s) — the dashboard needs
 * several quote/news round-trips before every widget resolves. */
async function settle(page) {
  await page.waitForFunction(() => document.querySelectorAll('[class*=skeleton]').length === 0,
    { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(3000);
}

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});

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
    await page.goto(BASE + r.path, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4200);
    await closeIntro(page);
    await settle(page);
    const file = `${OUT}/${r.name}-${theme}.png`;
    await page.screenshot({ path: file });
    console.log('shot:', file);
  }
  await ctx.close();
}

await browser.close();
console.log('showcase shots done');
