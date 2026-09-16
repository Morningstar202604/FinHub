// Verify the hover-revealed row actions are genuinely usable: the CSS parks the
// overlay at opacity:0 / pointer-events:none by design (NavigationPanel.css:53-82),
// and :hover restores both. So hover the row FIRST, then interact, and read the
// wire to confirm the action reaches the backend.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';
const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

const calls = [];
page.on('request', (r) => {
  if (!['PATCH', 'POST', 'DELETE', 'PUT'].includes(r.method())) return;
  calls.push(`${r.method()} ${r.url().replace('http://localhost:8000', '').replace(BASE, '')}`);
});
const toastTexts = [];
page.on('response', async (r) => {
  if (r.url().includes('/api/v1/') && r.status() >= 400) toastTexts.push(`HTTP${r.status()} ${r.url().replace('http://localhost:8000', '')}`);
});
const wait = (m) => page.waitForTimeout(m);

await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4500);

// Find a thread row (has a row-actions wrapper) inside the nav panel.
const rows = await page.$$('.nav-panel-row');
console.log('nav rows found:', rows.length);

for (let i = 0; i < Math.min(rows.length, 6); i++) {
  const box = await rows[i].boundingBox();
  const label = (await rows[i].innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 30);
  if (!box) continue;
  await rows[i].hover();
  await wait(500);
  const actions = await rows[i].$$('.nav-panel-row-actions button');
  const st = await rows[i].$eval('.nav-panel-row-actions', (el) => {
    const cs = getComputedStyle(el);
    return { opacity: cs.opacity, pe: cs.pointerEvents };
  }).catch(() => null);
  console.log(`\nrow[${i}] "${label}" box=${Math.round(box.x)},${Math.round(box.y)} ${Math.round(box.width)}x${Math.round(box.height)}`);
  console.log(`  actions: ${actions.length} buttons | overlay opacity=${st?.opacity} pe=${st?.pe}`);
  if (!actions.length) continue;

  const names = [];
  for (const a of actions) names.push(await a.evaluate((el) => (el.getAttribute('aria-label') || el.title || '').slice(0, 30)));
  console.log('  buttons:', names.join(' | '));

  // Hit-test each one now that the row is hovered.
  for (let j = 0; j < actions.length; j++) {
    const probe = await actions[j].evaluate((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return { w: Math.round(r.width), h: Math.round(r.height), pe: getComputedStyle(el).pointerEvents,
               reachable: !!hit && (el === hit || el.contains(hit) || hit.contains(el)),
               blockedBy: hit && !(el === hit || el.contains(hit) || hit.contains(el)) ? `${hit.tagName.toLowerCase()}.${(hit.className||'').toString().split(' ')[0]}` : null };
    });
    console.log(`    [${j}] ${names[j]} : ${probe.w}x${probe.h} pe=${probe.pe} ${probe.reachable ? 'REACHABLE' : 'BLOCKED by ' + probe.blockedBy}`);
  }

  // Click the Pin button for real.
  const pinBtn = actions.find(async () => true);
  calls.length = 0;
  const err = await actions[0].click({ timeout: 3000 }).then(() => null, (e) => String(e).split('\n')[0].slice(0, 120));
  await wait(1600);
  console.log(`    click[0] "${names[0]}" -> ${err ?? 'ok'}`);
  console.log('    wire   :', calls.length ? calls.join(' , ') : '(no mutation request)');
  if (toastTexts.length) console.log('    errors :', toastTexts.slice(0, 3).join(' , '));

  await page.mouse.move(800, 500); // leave the row
  await wait(400);
  break;
}

// Archive flow: hover row -> click Archive -> expect a confirm dialog.
await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4000);
const rows2 = await page.$$('.nav-panel-row');
for (let i = 0; i < rows2.length; i++) {
  const acts = await rows2[i].$$('.nav-panel-row-actions button');
  if (acts.length < 2) continue;
  await rows2[i].hover();
  await wait(400);
  calls.length = 0;
  const err = await acts[1].click({ timeout: 3000 }).then(() => null, (e) => String(e).split('\n')[0].slice(0, 120));
  await wait(1400);
  const dlg = await page.locator('[role="dialog"]').count();
  console.log(`\nArchive on row[${i}] -> ${err ?? 'ok'} | confirm dialog: ${dlg} | wire: ${calls.length ? calls.join(' , ') : '(none yet — expects confirmation)'}`);
  if (dlg) {
    const btns = (await page.locator('[role="dialog"] button').allTextContents()).map((s) => s.trim()).filter(Boolean);
    console.log('  dialog buttons:', btns.slice(0, 6).join(' | '));
    await page.keyboard.press('Escape');
  }
  break;
}

await browser.close();
console.log('\nROW-ACTION PROBE DONE');
