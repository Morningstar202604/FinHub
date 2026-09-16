// Does `inert` on the collapsed plugin deck actually take its rows out of the
// tab order? The a11y sweep flagged 12 controls inside an aria-hidden ancestor
// but with tabIndex 0, which contradicts inert being applied. Measure directly.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/plugins', { waitUntil: 'domcontentloaded' });
await wait(4000);

const info = await page.evaluate(() => {
  const decks = [...document.querySelectorAll('[data-testid^="deck-cover-"]')];
  const out = [];
  for (const cover of decks.slice(0, 3)) {
    const hiddenAncestor = cover.closest('[aria-hidden="true"]');
    const rows = cover.querySelector('.flex.flex-col');
    const inner = cover.querySelector('[inert]');
    const btns = [...cover.querySelectorAll('button')].slice(0, 3).map((b) => ({
      label: (b.getAttribute('aria-label') || b.innerText || '').slice(0, 24),
      tabIndex: b.tabIndex,
      inertAncestor: !!b.closest('[inert]'),
      // The decisive test: is it actually focusable right now?
    }));
    // Try focusing the first button inside the collapsed deck.
    const probe = cover.querySelector('button');
    let focusable = null;
    if (probe) { probe.focus(); focusable = document.activeElement === probe; }
    out.push({
      deck: cover.getAttribute('data-testid'),
      hasAriaHiddenAncestor: !!hiddenAncestor,
      rowsContainerFound: !!rows,
      appliedInertAttr: inner ? inner.getAttribute('inert') : '(no [inert] element found)',
      buttonCount: cover.querySelectorAll('button').length,
      sample: btns,
      actuallyFocusable: focusable,
    });
  }
  return out;
});

for (const d of info) {
  console.log(`\ndeck ${d.deck}`);
  console.log(`  aria-hidden ancestor : ${d.hasAriaHiddenAncestor}`);
  console.log(`  applied inert attr   : ${JSON.stringify(d.appliedInertAttr)}`);
  console.log(`  buttons in deck      : ${d.buttonCount}`);
  console.log(`  first btn focusable  : ${d.actuallyFocusable}`);
  for (const s of d.sample) console.log(`     "${s.label}" tabIndex=${s.tabIndex} inertAncestor=${s.inertAncestor}`);
}

await browser.close();
console.log('\nINERT PROBE DONE');
