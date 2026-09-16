// Settings tab walk, scoped properly this time: only controls inside the
// settings panel, identified by their tab index (the first N buttons in the
// panel are the tab bar, which we switch with deliberately). Nothing in the
// global sidebar is touched, and no getByText wrapper ambiguity.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const fs = await import('node:fs');

const BASE = 'http://localhost:5173';
const TABS = ['userInfo', 'preferences', 'agent', 'model', 'experiments'];
const OUT = '/tmp/settings-tabs.json';

const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();
const wait = (m) => page.waitForTimeout(m);

let bucket = [];
page.on('console', (m) => { if (m.type() === 'error') bucket.push({ k: 'console', t: m.text().slice(0, 140) }); });
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes('/api/v1/')) bucket.push({ k: `http${r.status()}`, t: r.url().slice(0, 120) }); });
page.on('request', (r) => { if (['PUT', 'PATCH', 'POST', 'DELETE'].includes(r.method()) && r.url().includes('/api/v1/')) bucket.push({ k: 'write', t: `${r.method()} ${r.url().replace('http://localhost:8000', '').slice(0, 110)}` }); });

// The settings panel is the subtree holding the tablist.
const PANEL = 'div:has(> [role="tablist"]), [role="tablist"] ~ *';

const report = {};

for (const tab of TABS) {
  await page.goto(`${BASE}/settings?tab=${tab}`, { waitUntil: 'domcontentloaded' });
  await wait(3400);

  // List controls strictly inside the settings panel (exclude the sidebar/global chrome).
  const controls = await page.evaluate(() => {
    const tablist = document.querySelector('[role="tablist"]');
    if (!tablist) return [];
    // Climb to the panel root that contains the tablist but is inside main.
    let root = tablist;
    while (root.parentElement && root.parentElement.tagName !== 'MAIN') root = root.parentElement;
    const sel = 'button, [role="button"], [role="switch"], a[href], input[type="checkbox"], input[type="radio"], select';
    return [...root.querySelectorAll(sel)].map((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (!(r.width > 0 && r.height > 0) || cs.visibility === 'hidden' || cs.display === 'none') return null;
      return {
        label: (el.getAttribute('aria-label') || el.innerText || el.textContent || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 46),
        tag: el.tagName.toLowerCase(), role: el.getAttribute('role'), type: el.getAttribute('type'),
        checked: el.getAttribute('aria-checked'), disabled: el.disabled === true,
        isTab: !!el.closest('[role="tablist"]'),
      };
    }).filter(Boolean);
  });
  console.log(`\n══════ ${tab} — ${controls.length} controls in panel ══════`);

  const log = [];
  const seen = new Set();
  for (const c of controls) {
    if (!c.label || seen.has(c.label) || c.isTab) continue;
    seen.add(c.label);
    if (/delete|remove|reset|clear|log ?out|revoke|disconnect|取消|删除/i.test(c.label)) {
      log.push({ ...c, note: 'skipped-destructive' });
      console.log(`    - ${c.label} :: skipped`);
      continue;
    }

    const snap = () => page.evaluate(() => {
      const root = document.documentElement;
      const tablist = document.querySelector('[role="tablist"]');
      let panel = tablist;
      while (panel?.parentElement && panel.parentElement.tagName !== 'MAIN') panel = panel.parentElement;
      const txt = (panel?.innerText || '').replace(/\s+/g, ' ').trim();
      let h = 0; for (let i = 0; i < txt.length; i++) h = (h * 31 + txt.charCodeAt(i)) | 0;
      return { hash: h, len: txt.length, theme: root.getAttribute('data-theme'),
               font: getComputedStyle(root).fontSize,
               dialogs: document.querySelectorAll('[role="dialog"]').length,
               switches: [...document.querySelectorAll('[role="switch"]')].map((s) => s.getAttribute('aria-checked')).join(',') };
    });
    const before = await snap();
    bucket = [];
    let err = null;
    // Re-resolve by role+name so the handle is concrete, not a text wrapper.
    const target = c.role === 'switch'
      ? page.getByRole('switch', { name: c.label, exact: true }).first()
      : page.getByRole('button', { name: c.label, exact: true }).first();
    const exists = await target.count().catch(() => 0);
    if (!exists) { console.log(`    ? ${c.label} :: handle not resolvable`); log.push({ ...c, note: 'unresolvable' }); continue; }
    try { await target.click({ timeout: 2200 }); } catch (e) { err = String(e).split('\n')[0].slice(0, 70); }
    await wait(1100);
    const after = await snap();

    let note;
    if (err) note = `click-failed: ${err}`;
    else if (after.dialogs > before.dialogs) note = 'opened overlay';
    else if (after.switches !== before.switches) note = `switch ${before.switches}->${after.switches}`;
    else if (after.theme !== before.theme) note = `theme->${after.theme}`;
    else if (after.font !== before.font) note = `font->${after.font}`;
    else if (after.hash !== before.hash) note = `content ${before.len}->${after.len}`;
    else note = 'no visible effect';

    const writes = bucket.filter((b) => b.k === 'write');
    const errors = bucket.filter((b) => b.k !== 'write');
    log.push({ ...c, note, writes: writes.map((w) => w.t), errors: errors.slice(0, 3) });
    const flag = errors.length ? '!' : (note === 'no visible effect' ? '?' : ' ');
    console.log(`  ${flag} ${c.label} :: ${note}${writes.length ? '  → ' + writes[0].t : ''}`);
    for (const e of errors.slice(0, 2)) console.log(`       [${e.k}] ${e.t}`);

    if (after.dialogs > before.dialogs) { await page.keyboard.press('Escape').catch(() => {}); await wait(600); }
  }
  report[tab] = log;
}

await browser.close();
fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log('\n════════ SUMMARY ════════');
for (const [tab, log] of Object.entries(report)) {
  const noEff = log.filter((r) => r.note === 'no visible effect');
  const noWrite = log.filter((r) => !r.writes?.length && !r.note.startsWith('skipped'));
  console.log(`\n[${tab}] controls=${log.length} noEffect=${noEff.length} noWrite=${noWrite.length}`);
  for (const r of noEff) console.log(`   ? ${r.label}`);
}
console.log('\nDONE ->', OUT);
