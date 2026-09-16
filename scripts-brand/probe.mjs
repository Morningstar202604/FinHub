// Evidence probe: for controls the bulk traversal flagged as "click-failed" or
// "no visible effect", report WHY — hit-testing, actionability, and state
// before/after a real click. Nothing here is concluded without measurement.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';

// route | control label | how to find it
const CASES = [
  ['/dashboard', 'Classic'],
  ['/dashboard', 'Custom'],
  ['/dashboard', 'Generate Personalized Brief'],
  ['/plugins', 'All'],
  ['/plugins', 'On'],
  ['/plugins', 'Off'],
  ['/chat', 'New chat'],
  ['/finance', 'Agent fills'],
  ['/finance', 'Manual'],
  ['/automations', 'Display options'],
  ['/settings', 'Account menu'],
];

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

async function settle(ms = 3000) { await page.waitForTimeout(ms); }

for (const [route, label] of CASES) {
  await page.goto(BASE + route, { waitUntil: 'domcontentloaded' });
  await settle(3500);
  const loc = page.getByText(label, { exact: true }).first();
  const found = await loc.count().catch(() => 0);
  if (!found) { console.log(`\n${route} :: "${label}" — NOT FOUND on page`); continue; }

  const info = await loc.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    const hit = document.elementFromPoint(cx, cy);
    return {
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      opacity: cs.opacity, pointerEvents: cs.pointerEvents, visibility: cs.visibility,
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      pressed: el.getAttribute('aria-pressed'), selected: el.getAttribute('aria-selected'),
      cls: (el.className || '').toString().slice(0, 90),
      tag: el.tagName.toLowerCase(),
      hitOwn: el === hit || el.contains(hit) || (hit && hit.contains(el)),
      hitTag: hit ? `${hit.tagName.toLowerCase()}.${(hit.className || '').toString().split(' ')[0]}` : 'none',
    };
  }).catch((e) => ({ err: String(e).slice(0, 120) }));

  let click = 'ok';
  try { await loc.click({ timeout: 3500, trial: false }); }
  catch (e) { click = String(e).split('\n')[0].slice(0, 150); }
  await settle(1400);

  const after = await loc.evaluate((el) => ({
    pressed: el.getAttribute('aria-pressed'), selected: el.getAttribute('aria-selected'),
    cls: (el.className || '').toString().slice(0, 90),
  })).catch(() => null);

  console.log(`\n${route} :: "${label}"`);
  console.log('  box        :', JSON.stringify(info.rect), 'opacity', info.opacity, 'pe', info.pointerEvents, 'disabled', info.disabled);
  console.log('  state      : aria-pressed', info.pressed, '->', after?.pressed, '| aria-selected', info.selected, '->', after?.selected);
  console.log('  classΔ     :', info.cls === after?.cls ? '(unchanged)' : `BEFORE ${info.cls}\n              AFTER  ${after?.cls}`);
  console.log('  hit-test   :', info.hitOwn ? 'clickable' : `BLOCKED by ${info.hitTag}`);
  console.log('  click      :', click);
}

await browser.close();
console.log('\nPROBE DONE');
