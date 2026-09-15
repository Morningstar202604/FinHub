import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const OUT = '/workspace/FinHub/screenshots';

async function closeIntro(page) {
  const dlg = page.locator('.intro-dialog');
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.locator('button').last().click().catch(() => page.keyboard.press('Escape'));
    await page.waitForTimeout(800);
  }
}

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});

const shots = [
  { path: '/market',    name: '05-market' },
  { path: '/dashboard', name: '03-dashboard' },
  { path: '/market',    name: '05-market-mobile', mobile: true },
];

for (const [tag, theme] of [['', 'light'], ['dark', 'dark']]) {
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.5,
  });
  await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  if (theme === 'dark') await ctx.addInitScript(() => localStorage.setItem('theme', 'dark'));
  const page = await ctx.newPage();
  for (const s of shots.filter((x) => !x.mobile)) {
    await page.goto(BASE + s.path, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(6000); // charts + SWR settle
    await closeIntro(page);
    const file = `${OUT}/${s.name}${tag ? '-' + tag : ''}.png`;
    await page.screenshot({ path: file });
    console.log('shot:', file);
  }
  await ctx.close();
}

// mobile market
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
  });
  await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  const page = await ctx.newPage();
  await page.goto(BASE + '/market', { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(6000);
  await closeIntro(page);
  await page.screenshot({ path: `${OUT}/05-market-mobile.png` });
  console.log('shot: 05-market-mobile');
  await ctx.close();
}

await browser.close();
console.log('DONE');
