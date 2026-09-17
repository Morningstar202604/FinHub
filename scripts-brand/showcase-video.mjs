/**
 * Showcase pass B — record per-scene videos for the product film.
 * One context (and one webm) per scene so the editor can treat each
 * independently. 1920x1080. Real interactions only: navigation, scrolling,
 * theme/language switches, and a live agent chat turn.
 */
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots/video';

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});

// Clear stale webms so the post-run rename maps 1:1 to scene order.
for (const f of fs.readdirSync(OUT)) {
  if (f.endsWith('.webm')) fs.rmSync(path.join(OUT, f), { force: true });
}

function makeContext() {
  return browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
  });
}

async function prime(ctx) {
  await ctx.addInitScript(() => {
    sessionStorage.setItem('finhub_setup_skipped', '1');
    localStorage.setItem('theme', 'dark');
  });
  return ctx;
}

async function closeIntro(page) {
  const dlg = page.locator('.intro-dialog');
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.locator('button').last().click().catch(() => page.keyboard.press('Escape'));
    await page.waitForTimeout(900);
  }
}

async function goto(page, path, settleMs = 15000) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(settleMs);
  await closeIntro(page);
}

// Warm pass: hit every route once WITHOUT recording so vite's on-demand
// module transform and the API caches are hot — otherwise scene openers
// show multi-second compile stalls.
{
  const warm = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await warm.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  const wp = await warm.newPage();
  for (const p of ['/dashboard', '/market', '/finance', '/chat', '/settings?tab=userInfo', '/plugins', '/automations']) {
    await wp.goto(BASE + p, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await wp.waitForTimeout(5000);
  }
  await warm.close();
  console.log('warm pass done');
}

/** Smooth scroll to bottom then back to top — shows the page without jumps. */
async function scrollTour(page) {
  await page.evaluate(async () => {
    const el = document.scrollingElement;
    const step = 500;
    for (let y = 0; y <= el.scrollHeight - innerHeight; y += step) {
      el.scrollTop = y;
      await new Promise((r) => setTimeout(r, 350));
    }
  });
  await page.waitForTimeout(1200);
  await page.evaluate(() => { document.scrollingElement.scrollTop = 0; });
  await page.waitForTimeout(900);
}

// ---------------------------------------------------------------- scene 1
// Dashboard: load, absorb, scroll through the widgets.
{
  const ctx = await prime(await makeContext());
  const page = await ctx.newPage();
  await goto(page, '/dashboard', 20000);
  await page.waitForTimeout(6000);
  await scrollTour(page);
  await ctx.close();
  console.log('scene 1 (dashboard) recorded');
}

// ---------------------------------------------------------------- scene 2
// Market: charts, sidebar, switch the selected symbol.
{
  const ctx = await prime(await makeContext());
  const page = await ctx.newPage();
  await goto(page, '/market', 15000);
  await page.waitForTimeout(5000);
  // Don't record until the quote header resolves (it shows 0.00 while loading).
  await page.waitForFunction(() => {
    const el = document.querySelector('.stock-price');
    const t = el ? (el.textContent || '').trim() : '';
    return t !== '' && t !== '—' && t !== '0.00';
  }, { timeout: 20000 }).catch(() => {});
  // Click a watchlist row in the sidebar to switch symbols live.
  const row = page.locator('.market-sidebar-row').nth(1);
  if (await row.count()) {
    await row.click();
    await page.waitForTimeout(6000);
  }
  await ctx.close();
  console.log('scene 2 (market) recorded');
}

// ---------------------------------------------------------------- scene 3
// Finance: the finance-ministry page.
{
  const ctx = await prime(await makeContext());
  const page = await ctx.newPage();
  await goto(page, '/finance', 12000);
  await scrollTour(page);
  await ctx.close();
  console.log('scene 3 (finance) recorded');
}

// ---------------------------------------------------------------- scene 4
// Chat: a real agent turn — typed question, tool calls, streamed answer.
// The composer lives on the home page (/dashboard), not /chat (workspaces).
{
  const ctx = await prime(await makeContext());
  const page = await ctx.newPage();
  await goto(page, '/', 15000);
  const input = page.locator('textarea').first();
  await input.click();
  await input.pressSequentially('帮我算一下我的投资组合总市值和每个持仓的占比，用一段简短文字总结，并画一张占比饼图。', { delay: 40 });
  await page.waitForTimeout(800);
  await input.press('Enter');
  // Give the agent a generous window; whatever lands by then is what we cut.
  await page.waitForTimeout(100000);
  await ctx.close();
  console.log('scene 4 (chat) recorded');
}

// ---------------------------------------------------------------- scene 5
// Settings: theme flip (dark → light → dark), language switch, font size.
{
  const ctx = await makeContext();
  await ctx.addInitScript(() => {
    sessionStorage.setItem('finhub_setup_skipped', '1');
    localStorage.setItem('theme', 'dark');
  });
  const page = await ctx.newPage();
  await goto(page, '/settings?tab=userInfo', 8000);
  // Theme: Light (guarded — a missed locator must not kill the run)
  await page.getByRole('button', { name: 'Light' }).click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(1800);
  // Font size: step up one notch
  const fs = page.getByRole('button', { name: '110%' });
  if (await fs.count()) { await fs.click({ timeout: 4000 }).catch(() => {}); await page.waitForTimeout(1500); }
  // Language: 中文
  await page.selectOption('#settings-locale', 'zh-CN').catch(() => {});
  await page.waitForTimeout(2500);
  // Tabs under the new locale
  await page.getByRole('tab', { name: /偏好|Preferences/ }).click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(2200);
  await page.getByRole('tab', { name: /代理|Agent/ }).click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(2200);
  await ctx.close();
  console.log('scene 5 (settings) recorded');
}

// ---------------------------------------------------------------- scene 6
// Plugins + Automations quick pass.
{
  const ctx = await prime(await makeContext());
  const page = await ctx.newPage();
  await goto(page, '/plugins', 10000);
  await scrollTour(page);
  await page.goto(BASE + '/automations', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(9000);
  await closeIntro(page);
  await page.waitForTimeout(3000);
  await ctx.close();
  console.log('scene 6 (plugins+automations) recorded');
}

await browser.close();

// Rename the 6 recorded webms to deterministic scene-N.webm in creation order
// (contexts close in scene order, so mtime order == scene order).
const SCENE_NAMES = ['scene1-dashboard', 'scene2-market', 'scene3-finance',
  'scene4-chat', 'scene5-settings', 'scene6-plugins-auto'];
const webms = fs.readdirSync(OUT).filter((f) => f.endsWith('.webm'))
  .map((f) => ({ f, m: fs.statSync(path.join(OUT, f)).mtimeMs }))
  .sort((a, b) => a.m - b.m);
webms.forEach((w, i) => {
  if (i < SCENE_NAMES.length) {
    fs.renameSync(path.join(OUT, w.f), path.join(OUT, `${SCENE_NAMES[i]}.webm`));
    console.log(`renamed ${w.f} -> ${SCENE_NAMES[i]}.webm`);
  }
});
console.log('all scenes recorded');
