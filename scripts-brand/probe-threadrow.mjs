// Hover-revealed thread actions (pin / archive) live on the *thread* row, which
// only exists once its workspace is expanded. Expand first, then hover, then
// hit-test and click — the CSS parks the overlay at opacity:0/pointer-events:none
// until :hover (NavigationPanel.css:53-82), so hovering is mandatory.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

const calls = [];
const errors = [];
page.on('request', (r) => {
  if (['PATCH', 'POST', 'DELETE', 'PUT'].includes(r.method())) calls.push(`${r.method()} ${r.url().replace('http://localhost:8000', '')}`);
});
page.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errors.push(`HTTP${r.status()} ${r.url().replace('http://localhost:8000','')}`); });
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4500);

// Expand the first workspace so its thread rows mount.
const wsRows = await page.$$('.nav-panel-row');
console.log('before expand, nav rows:', wsRows.length);
await wsRows[0].click({ timeout: 3000 }).catch((e) => console.log('expand err', String(e).split('\n')[0]));
await wait(2500);
const after = await page.$$('.nav-panel-row');
console.log('after expand,  nav rows:', after.length);

// Find a row that actually carries the hover-revealed action overlay.
let target = null;
for (const row of after) {
  const txt = (await row.innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 30);
  await row.hover().catch(() => {});
  await wait(350);
  const overlay = await row.$('.nav-panel-row-actions');
  if (overlay) { target = { row, txt, overlay }; break; }
}
if (!target) {
  // Dump what every row contains so the miss is diagnosable, not guessed.
  for (let i = 0; i < after.length; i++) {
    const txt = (await after[i].innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 40);
    const cls = await after[i].getAttribute('class');
    console.log(`  row[${i}] "${txt}" class="${cls}"`);
  }
  await browser.close();
  console.log('\nNO ACTION OVERLAY FOUND');
  process.exit(0);
}

console.log(`\ntarget row: "${target.txt}"`);
const probe = await target.overlay.evaluate((el) => {
  const cs = getComputedStyle(el);
  const btns = [...el.querySelectorAll('button')];
  return {
    opacity: cs.opacity, pe: cs.pointerEvents,
    buttons: btns.map((b) => {
      const r = b.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return {
        label: (b.getAttribute('aria-label') || b.title || '').slice(0, 30),
        box: `${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.width)}x${Math.round(r.height)}`,
        pe: getComputedStyle(b).pointerEvents,
        reachable: !!hit && (b === hit || b.contains(hit) || hit.contains(b)),
        blockedBy: hit && !(b === hit || b.contains(hit) || hit.contains(b)) ? hit.tagName.toLowerCase() : null,
      };
    }),
  };
});
console.log(`overlay (hovered): opacity=${probe.opacity} pe=${probe.pe}`);
for (const b of probe.buttons) {
  console.log(`  ${b.reachable ? 'REACHABLE' : 'BLOCKED  '} ${b.label.padEnd(22)} ${b.box} pe=${b.pe}${b.blockedBy ? ' by ' + b.blockedBy : ''}`);
}

// Orphan check: a row at rest hides the overlay from both pointer AND screen readers.
const rest = await target.overlay.getAttribute('aria-hidden');
console.log(`overlay aria-hidden at rest: ${rest}`);

const btns = await target.overlay.$$('button');
if (btns.length) {
  calls.length = 0; errors.length = 0;
  const label = (await btns[0].getAttribute('aria-label')) || '';
  const err = await btns[0].click({ timeout: 3000 }).then(() => null, (e) => String(e).split('\n')[0].slice(0, 130));
  await wait(1800);
  console.log(`\nclick "${label}" -> ${err ?? 'ok'}`);
  console.log('  wire  :', calls.length ? calls.join(' , ') : '(no mutation sent)');
  console.log('  errors:', errors.length ? errors.join(' , ') : '(none)');
  const pinned = await target.row.evaluate((el) => !!el.querySelector('svg.fill-current, [fill="currentColor"]'));
  console.log('  pin glyph filled now:', pinned);
}

await browser.close();
console.log('\nTHREAD-ROW PROBE DONE');
