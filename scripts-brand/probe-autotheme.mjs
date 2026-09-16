// "Auto" theme looked inert in one probe because the OS preference was light,
// so resolving auto -> light left data-theme unchanged. Verify it actually
// tracks the system preference by emulating both schemes.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });

for (const scheme of ['light', 'dark']) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, colorScheme: scheme });
  await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
  const page = await ctx.newPage();
  await page.goto(BASE + '/settings?tab=userInfo', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3200);

  // Pin to a known state first so Auto has something to change.
  await page.getByRole('button', { name: 'Light', exact: true }).first().click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(700);
  const start = await page.evaluate(() => ({ t: document.documentElement.getAttribute('data-theme'), ls: localStorage.getItem('theme') }));

  await page.getByRole('button', { name: 'Auto', exact: true }).first().click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(900);
  const afterAuto = await page.evaluate(() => ({ t: document.documentElement.getAttribute('data-theme'), ls: localStorage.getItem('theme') }));

  // Reload: with localStorage 'auto' the resolved theme must follow the emulated OS scheme.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  const afterReload = await page.evaluate(() => ({ t: document.documentElement.getAttribute('data-theme'), ls: localStorage.getItem('theme'),
                                                      favicon: document.querySelector('link[rel*="icon"]')?.getAttribute('href') }));

  const expected = scheme;
  const pass = afterReload.ls === 'auto' && afterReload.t === expected;
  console.log(`OS=${scheme}: light->${start.t}  ${afterAuto.t}/${afterAuto.ls}  reload->${afterReload.t}/${afterReload.ls} favicon=${afterReload.favicon}  ${pass ? 'PASS' : 'FAIL (expected ' + expected + ')'}`);
  await ctx.close();
}

await browser.close();
console.log('AUTO-THEME PROBE DONE');
