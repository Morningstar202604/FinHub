// Scene 4 retake — question that the agent can fully answer from LOCAL
// portfolio data (no external market calls), so it converges quickly and
// renders a chart in the reply. Recording params identical to showcase-video.mjs.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots/video';

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
});
await ctx.addInitScript(() => {
  sessionStorage.setItem('finhub_setup_skipped', '1');
  localStorage.setItem('theme', 'dark');
});
const page = await ctx.newPage();
await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(12000);
const input = page.locator('textarea').first();
await input.click();
await input.pressSequentially('帮我算一下我的投资组合总市值和每个持仓的占比，用一段简短文字总结，并画一张占比饼图。', { delay: 40 });
await page.waitForTimeout(800);
await input.press('Enter');
// Agent plan: query local holdings → compute → matplotlib pie → stream reply.
await page.waitForTimeout(140000);
await ctx.close();
await browser.close();
console.log('scene 4 retake recorded');
