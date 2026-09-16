// The dashboard paperclip (widget-frame__add-btn--view) is opacity:0 at rest but
// declares `:focus-visible { opacity: 1 }`. Programmatic el.focus() does NOT
// trigger :focus-visible, so the sweep could not see the reveal. Drive it with
// real keyboard Tab instead — that is what a keyboard user actually does.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded' });
await wait(4500);

// Focus the paperclip the way a keyboard user reaches it: real Tab presses,
// which is the only thing that produces :focus-visible.
let found = false;
for (let i = 0; i < 60; i++) {
  await page.keyboard.press('Tab');
  const hit = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || !el.classList || !el.classList.contains('widget-frame__add-btn--view')) return null;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const hitEl = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return {
      opacity: cs.opacity,
      outline: cs.outlineStyle + ' ' + cs.outlineWidth,
      label: el.getAttribute('aria-label'),
      reachableByPointer: !!hitEl && (el === hitEl || el.contains(hitEl)),
      tabIndex: el.tabIndex,
    };
  });
  if (hit) {
    found = true;
    console.log(`\nReached paperclip after ${i + 1} Tabs`);
    console.log(`  aria-label        : ${hit.label}`);
    console.log(`  opacity on focus  : ${hit.opacity}   (0 at rest, must be 1 when focused)`);
    console.log(`  focus ring        : ${hit.outline}`);
    console.log(`  pointer-reachable : ${hit.reachableByPointer}`);
    console.log(hit.opacity === '1'
      ? '  RESULT: PASS — keyboard focus reveals it; not a phantom tab stop'
      : '  RESULT: FAIL — focusable but stays invisible');
    break;
  }
}
if (!found) console.log('paperclip never received keyboard focus in 60 Tabs');

// Sanity: it is genuinely invisible at rest (no focus, no hover).
await page.mouse.move(1500, 850);
await page.evaluate(() => document.activeElement.blur());
await wait(500);
const atRest = await page.evaluate(() => {
  const el = document.querySelector('.widget-frame__add-btn--view');
  return el ? { opacity: getComputedStyle(el).opacity, pe: getComputedStyle(el).pointerEvents } : null;
});
console.log('\nat rest (blurred):', JSON.stringify(atRest));

await browser.close();
console.log('PAPERCLIP PROBE DONE');
