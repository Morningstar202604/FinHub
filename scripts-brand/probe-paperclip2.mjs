import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
await page.goto('http://localhost:5173/dashboard', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(4500);

const r = await page.evaluate(() => {
  const els = [...document.querySelectorAll('.widget-frame__add-btn--view')];
  return els.map((el) => {
    const cs = getComputedStyle(el);
    return {
      label: el.getAttribute('aria-label'),
      disabled: el.disabled,
      opacity: cs.opacity,
      pe: cs.pointerEvents,
      // the exact selectors the stylesheet branches on
      matchesFV: el.matches(':focus-visible'),
      hoverCapable: matchMedia('(hover: hover)').matches,
    };
  });
});
console.log('media (hover: hover) ->', await page.evaluate(() => matchMedia('(hover: hover)').matches));
console.log('media (hover: none) ->', await page.evaluate(() => matchMedia('(hover: none)').matches));
console.log('\npaperclip buttons:');
console.log(JSON.stringify(r, null, 2));

// Which rules actually match, per the CSSOM? Ask the browser, don't infer.
const rules = await page.evaluate(() => {
  const out = [];
  for (const sheet of document.styleSheets) {
    let list;
    try { list = sheet.cssRules; } catch { continue; }
    for (const rule of list) {
      const sel = rule.selectorText || '';
      if (sel.includes('add-btn--view')) out.push(sel);
    }
  }
  return out;
});
console.log('\nmatching selectors in stylesheets:');
for (const s of rules) console.log('  ', s);

await browser.close();
