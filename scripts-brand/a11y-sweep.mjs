// Two checks in one pass:
//  1. the thread-row overlay fix — aria-hidden on the desktop overlay + pin's
//     aria-pressed, and NO phantom tab stops from resting-invisible controls
//  2. a full a11y sweep: icon-only controls with no accessible name, and every
//     element that is focusable while invisible (opacity:0 / pointer-events:none)
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const fs = await import('node:fs');

const BASE = 'http://localhost:5173';
const OUT = '/tmp/a11y-sweep.json';
const ROUTES = ['/dashboard', '/finance', '/market', '/automations', '/plugins', '/settings', '/chat', '/evals'];

const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

const report = {};

for (const route of ROUTES) {
  await page.goto(BASE + route, { waitUntil: 'domcontentloaded' });
  await wait(3800);
  const skip = page.locator('.intro-dialog button').last();
  if (await skip.count().catch(() => 0)) { await skip.click({ timeout: 1200 }).catch(() => {}); await wait(800); }

  const res = await page.evaluate(() => {
    const controls = [...document.querySelectorAll('button, [role="button"], a[href], [role="tab"], [role="switch"]')];

    const unnamed = [];
    const invisibleButFocusable = [];

    for (const el of controls) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);

      // Accessible-name approximation: aria-label, aria-labelledby target text,
      // title, visible text, alt of a nested image, or value.
      const name = (
        el.getAttribute('aria-label') ||
        (el.getAttribute('aria-labelledby') ? (document.getElementById(el.getAttribute('aria-labelledby'))?.textContent || '') : '') ||
        el.getAttribute('title') ||
        (el.innerText || '').trim() ||
        (el.querySelector('img[alt]')?.getAttribute('alt') || '') ||
        el.getAttribute('value') || ''
      ).trim();

      const offscreen = el.closest('[aria-hidden="true"]');
      if (!name && !offscreen) unnamed.push({ tag: el.tagName.toLowerCase(), cls: (el.className || '').toString().slice(0, 60) });

      // Focusable while not perceivable is a keyboard-trap class defect. The
      // tabIndex prop alone LIES here: `inert` (and a hidden ancestor) removes
      // an element from the tab order without touching that attribute. So the
      // only trustworthy test is an actual focus() attempt.
      const invisible = parseFloat(cs.opacity) === 0 || cs.pointerEvents === 'none' ||
                        cs.visibility === 'hidden' || (r.width === 0 && r.height === 0);
      if (invisible) {
        const previouslyFocused = document.activeElement;
        let reachable = false;
        try { el.focus({ preventScroll: true }); reachable = document.activeElement === el; } catch { reachable = false; }
        if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus({ preventScroll: true });
        // A control inside a hidden/deck body is deliberately out of play — and
        // `:focus-within`-style reveals mean opacity:0 alone is not proof either.
        // Only report elements that take focus while nothing on screen changed.
        const insideInert = !!el.closest('[inert]');
        if (reachable && !insideInert) {
          invisibleButFocusable.push({
            tag: el.tagName.toLowerCase(),
            name: name.slice(0, 30),
            cls: (el.className || '').toString().slice(0, 50),
            opacity: cs.opacity, pe: cs.pointerEvents, tabIndex: el.tabIndex,
          });
        }
      }
    }
    return { total: controls.length, unnamed, invisibleButFocusable };
  });

  report[route] = res;
  console.log(`\n=== ${route} — ${res.total} controls ===`);
  console.log(`  unnamed (assistive tech sees nothing): ${res.unnamed.length}`);
  for (const u of res.unnamed.slice(0, 6)) console.log(`     <${u.tag}> class="${u.cls}"`);
  console.log(`  focusable-but-invisible (phantom tab stops): ${res.invisibleButFocusable.length}`);
  for (const u of res.invisibleButFocusable.slice(0, 8)) {
    console.log(`     <${u.tag}> "${u.name}" opacity=${u.opacity} pe=${u.pe} tabIndex=${u.tabIndex} class="${u.cls}"`);
  }
}

// Fix verification on /chat with an expanded workspace.
await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4500);
const rows = await page.$$('.nav-panel-row');
if (rows.length) { await rows[0].click().catch(() => {}); await wait(2200); }
const verify = await page.evaluate(() => {
  const out = [];
  for (const ov of document.querySelectorAll('.nav-panel-row-actions')) {
    const pin = ov.querySelector('button');
    out.push({
      ariaHidden: ov.getAttribute('aria-hidden'),
      overlayPe: getComputedStyle(ov).pointerEvents,
      overlayOpacity: getComputedStyle(ov).opacity,
      firstBtnLabel: pin?.getAttribute('aria-label'),
      firstBtnTabIndex: pin?.tabIndex,
      firstBtnAriaPressed: pin?.getAttribute('aria-pressed'),
      btnCount: ov.querySelectorAll('button').length,
    });
  }
  return out;
});
await browser.close();

console.log('\n===== FIX VERIFICATION (/chat, overlay at rest) =====');
for (const v of verify) console.log('  ', JSON.stringify(v));
const totalPhantom = Object.values(report).reduce((n, r) => n + r.invisibleButFocusable.length, 0);
const totalUnnamed = Object.values(report).reduce((n, r) => n + r.unnamed.length, 0);
fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log(`\nTOTALS  unnamed=${totalUnnamed}  phantomTabStops=${totalPhantom}  -> ${OUT}`);
