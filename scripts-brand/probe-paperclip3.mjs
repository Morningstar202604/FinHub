// Clean keyboard-only session: no programmatic focus, no evaluate() that touches
// focus before the Tab run. Chrome's :focus-visible heuristic depends on how the
// last interaction happened, so the earlier probe's scripting may have pushed it
// into "pointer mode". This run presses Tab first and inspects only AFTER the
// element has focus — reading state through a snapshot taken on a fresh page load.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

await page.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(5000);

// Pure Tab walk. Track index -> element identity each press, and check whether
// the *currently focused* paperclip reports opacity 1 while it holds focus.
let reported = 0;
for (let i = 1; i <= 70; i++) {
  await page.keyboard.press('Tab');
  await page.waitForTimeout(120);
  const snap = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || !el.classList || !el.classList.contains('widget-frame__add-btn--view')) return null;
    const cs = getComputedStyle(el);
    return { opacity: cs.opacity, matchesFV: el.matches(':focus-visible'), disabled: el.disabled,
             outline: `${cs.outlineStyle} ${cs.outlineWidth}` };
  });
  if (!snap) continue;
  reported++;
  console.log(`Tab #${i}: paperclip focused -> opacity=${snap.opacity} :focus-visible=${snap.matchesFV} outline=${snap.outline}`);
  if (reported >= 3) break;
}

if (!reported) console.log('never reached a paperclip via Tab');

// Direct check: does [data-theme] or a wrapper disable focus-visible somewhere?
const focusRules = await page.evaluate(() => {
  const out = [];
  for (const sheet of document.styleSheets) {
    let list;
    try { list = sheet.cssRules; } catch { continue; }
    for (const rule of list) {
      const sel = rule.selectorText || '';
      if (sel.includes('focus-visible') && !sel.includes('add-btn')) out.push(sel);
    }
  }
  return out;
});
console.log('\nother :focus-visible rules on the page:', focusRules.length ? focusRules.join(' | ') : '(none)');

await browser.close();
console.log('CLEAN KEYBOARD PROBE DONE');
