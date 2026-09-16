// Scene 3 retake (finance). scrollTour capped at 25s — the finance page's
// cash-flow list makes scrollHeight huge; uncapped scrolling ran >100s.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots/video';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } } });
await ctx.addInitScript(() => {
  sessionStorage.setItem('finhub_setup_skipped', '1');
  localStorage.setItem('theme', 'dark');
});
const page = await ctx.newPage();
await page.goto(BASE + '/finance', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(12000);
await page.evaluate(async () => {
  const el = document.scrollingElement;
  const deadline = Date.now() + 25000;
  for (let y = 0; y <= el.scrollHeight - innerHeight && Date.now() < deadline; y += 500) {
    el.scrollTop = y;
    await new Promise((r) => setTimeout(r, 350));
  }
});
await page.waitForTimeout(1200);
await page.evaluate(() => { document.scrollingElement.scrollTop = 0; });
await page.waitForTimeout(900);
await ctx.close();
await browser.close();
console.log('scene 3 (finance) retake recorded');
