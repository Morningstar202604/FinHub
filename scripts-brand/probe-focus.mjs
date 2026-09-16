// Confirm the keyboard-focus fix: tabbing to the (visually at-rest) pin/archive
// buttons must reveal them, and reaching a button by name must no longer require
// the overlay to be permanently in the accessibility tree.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4500);
const rows = await page.$$('.nav-panel-row');
if (rows.length) { await rows[0].click().catch(() => {}); await wait(2200); }

// Locate the overlay while NOT hovered, then focus its first button directly.
const state = await page.evaluate(() => {
  const ov = document.querySelector('.nav-panel-row-actions');
  if (!ov) return { found: false };
  const btn = ov.querySelector('button');
  const before = { opacity: getComputedStyle(ov).opacity, pe: getComputedStyle(ov).pointerEvents };
  btn.focus();
  return { found: true, label: btn.getAttribute('aria-label'), ariaPressed: btn.getAttribute('aria-pressed'),
           tabIndex: btn.tabIndex, before };
});
if (!state.found) { console.log('no overlay found'); await browser.close(); process.exit(0); }

// :focus-within must have flipped it visible now.
await wait(400);
const after = await page.evaluate(() => {
  const ov = document.querySelector('.nav-panel-row-actions');
  const btn = ov.querySelector('button');
  const r = btn.getBoundingClientRect();
  const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return {
    opacity: getComputedStyle(ov).opacity,
    pe: getComputedStyle(ov).pointerEvents,
    focused: document.activeElement === btn,
    hitReachable: !!hit && (btn === hit || btn.contains(hit)),
  };
});
console.log('button         :', state.label, '| aria-pressed=', state.ariaPressed, '| tabIndex=', state.tabIndex);
console.log('overlay before :', JSON.stringify(state.before));
console.log('overlay on focus:', JSON.stringify(after));
console.log(after.opacity === '1' && after.pe === 'auto' && after.focused && after.hitReachable
  ? 'PASS — keyboard focus reveals the row actions'
  : 'FAIL — focus did not reveal them');

// And the phantom-tab-stop count is now zero: no control is focusable while invisible.
const phantom = await page.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll('button, a[href], [role="button"], [role="tab"], [role="switch"]')) {
    if (el.tabIndex < 0) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const invisible = parseFloat(cs.opacity) === 0 && cs.pointerEvents === 'none';
    if (invisible) out.push((el.getAttribute('aria-label') || el.innerText || '').slice(0, 30));
  }
  return out;
});
console.log('focusable-while-invisible:', phantom.length, phantom.length ? phantom : '(none)');

await browser.close();
console.log('FOCUS PROBE DONE');
