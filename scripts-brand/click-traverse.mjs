// v2 exhaustive traversal. Differences from v1:
//   * nothing is skipped for being below the fold — it is scrolled into view
//   * controls revealed inside overlays get their own recursive pass
//   * a click that cannot be acted on is hit-tested: we report WHO blocks it
// This is the "every interface, every button" sweep; it only records evidence.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const fs = await import('node:fs');

const BASE = 'http://localhost:5173';
const OUT = process.argv[2] || '/tmp/ui-clicks2.json';
const SHOTDIR = '/tmp/click-shots2';
fs.mkdirSync(SHOTDIR, { recursive: true });

const ROUTES = process.argv[3]
  ? process.argv[3].split(',')
  : ['/dashboard', '/finance', '/market', '/automations', '/plugins', '/settings', '/chat', '/evals'];

const DESTRUCTIVE = /删除|移除|清空|重置|注销|退出登录|delete|remove|reset|clear all|log ?out|sign ?out|revoke|disconnect|断开/i;
const SEL = ['button', '[role="button"]', '[role="tab"]', '[role="switch"]', '[role="menuitem"]',
             'a[href]', 'input[type="checkbox"]', 'input[type="radio"]'].join(',');

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

let bucket = [];
page.on('console', (m) => { if (m.type() === 'error') bucket.push({ kind: 'console', text: m.text().slice(0, 200) }); });
page.on('pageerror', (e) => bucket.push({ kind: 'pageerror', text: String(e).slice(0, 200) }));
page.on('response', (r) => { if (r.status() >= 400) bucket.push({ kind: `http${r.status()}`, text: r.url().slice(0, 160) }); });

const wait = (ms) => page.waitForTimeout(ms);

async function snapshot() {
  return await page.evaluate(() => {
    const main = document.querySelector('main') || document.body;
    const txt = (main.innerText || '').replace(/\s+/g, ' ').trim();
    let h = 0;
    for (let i = 0; i < txt.length; i++) h = (h * 31 + txt.charCodeAt(i)) | 0;
    // Global state matters as much as panel text: theme switches flip
    // <html data-theme>, the font-scale control rewrites the root font size,
    // and neither touches <main>. Without these two a working control reads
    // as "no visible effect" — the wrong verdict for exactly the settings that
    // mutate app-wide appearance.
    const root = document.documentElement;
    return {
      len: txt.length, hash: h,
      theme: root.getAttribute('data-theme'),
      rootFont: getComputedStyle(root).fontSize,
      dialogs: document.querySelectorAll('[role="dialog"], .intro-dialog, [role="menu"], [role="listbox"]').length,
      busy: document.querySelectorAll('[aria-busy="true"], .animate-spin').length,
      controls: document.querySelectorAll('button,[role="button"],[role="tab"],[role="switch"],a[href],input[type="checkbox"],input[type="radio"]').length,
    };
  });
}

async function goto(route) {
  await page.goto(BASE + route, { waitUntil: 'domcontentloaded' });
  await wait(3200);
  for (let i = 0; i < 2; i++) {
    const skip = page.locator('.intro-dialog button, .intro-dialog [role="button"]').last();
    if (await skip.count().catch(() => 0)) { await skip.click({ timeout: 1500 }).catch(() => {}); await wait(900); }
  }
}

const desc = (el) => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') ||
                      el.getAttribute('placeholder') || el.getAttribute('aria-labelledby') || '')
                     .trim().replace(/\s+/g, ' ').slice(0, 60);

// Why Playwright refuses to act on an element: almost always another node sitting
// on top of its centre. Report that node instead of a bare TimeoutError.
async function blockerReason(handle) {
  return await handle.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return `hidden(${cs.visibility}/${cs.display})`;
    if (parseFloat(cs.opacity) === 0) return 'opacity:0';
    if (r.width === 0 || r.height === 0) return 'zero-size';
    if (cs.pointerEvents === 'none') return 'pointer-events:none';
    const hit = document.elementFromPoint(cx, cy);
    if (!hit) return 'off-viewport';
    if (el === hit || el.contains(hit) || hit.contains(el)) return 'unstable-or-detached';
    return `blocked by ${hit.tagName.toLowerCase()}.${(hit.className || '').toString().trim().split(/\s+/)[0]}`;
  }).catch((e) => String(e).slice(0, 120));
}

// Main traversal over every control matching SEL currently in the DOM.
async function sweep(route, depth, budgetRef) {
  const log = [];
  let guard = 0;
  let idx = 0;
  while (idx < 400 && guard < 400) {
    guard++;
    const handles = await page.$$(SEL);
    let visible = [];
    for (const h of handles) {
      const vis = await h.evaluate((el) => {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' &&
               cs.display !== 'none' && parseFloat(cs.opacity) !== 0;
      }).catch(() => false);
      if (vis) visible.push(h);
    }
    if (idx >= visible.length) break;
    const el = visible[idx];
    const label = await el.evaluate(desc).catch(() => '');
    if (!label || budgetRef.seen.has(label)) { idx++; continue; }
    if (label === 'Loading…' || /^Loading/.test(label) || /Generating/.test(label)) { idx++; continue; }
    budgetRef.seen.add(label);
    if (DESTRUCTIVE.test(label)) {
      log.push({ route, depth, label, note: 'skipped (destructive)' });
      idx++; continue;
    }

    await el.scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => {});
    const before = await snapshot();
    const urlBefore = page.url();
    bucket = [];
    let err = null;
    try { await el.click({ timeout: 2500 }); }
    catch (e) { err = await blockerReason(el); }
    await wait(1100);
    const after = await snapshot();
    const urlAfter = page.url();

    let note;
    if (err) note = `UNCLICKABLE: ${err}`;
    else if (urlAfter !== urlBefore) note = `navigated -> ${urlAfter.replace(BASE, '')}`;
    else if (after.dialogs > before.dialogs) note = 'opened overlay';
    else if (after.dialogs < before.dialogs) note = 'closed overlay';
    else if (after.theme !== before.theme) note = `theme ${before.theme}->${after.theme}`;
    else if (after.rootFont !== before.rootFont) note = `font ${before.rootFont}->${after.rootFont}`;
    else if (after.hash !== before.hash) note = `content changed (${before.len}->${after.len})`;
    else if (after.controls !== before.controls) note = `controls ${before.controls}->${after.controls}`;
    else note = 'no visible effect';
    if (after.busy > 0) note += ' [spinner]';

    if (bucket.length && budgetRef.shots < 40) {
      await page.screenshot({ path: `${SHOTDIR}/${budgetRef.shots++}-${route.replace(/\W/g, '')}-${label.replace(/\W/g, '').slice(0, 18)}.png` }).catch(() => {});
    }
    log.push({ route, depth, label, note, issues: bucket.slice(0, 5) });
    console.log(`${'  '.repeat(depth)}${bucket.length ? '!' : ' '} [${route}${depth ? ' ›overlay' : ''}] ${label} :: ${note}`);
    for (const b of bucket.slice(0, 3)) console.log(`${'  '.repeat(depth)}     [${b.kind}] ${b.text.slice(0, 120)}`);

    // Follow the surface the click revealed.
    if (urlAfter !== urlBefore) {
      await goto(route);
    } else if (after.dialogs > before.dialogs && depth < 2) {
      log.push(...await sweep(route, depth + 1, budgetRef));
      await page.keyboard.press('Escape').catch(() => {});
      await wait(500);
      if (await page.locator('[role="menu"], [role="listbox"], [role="dialog"]').count()) {
        await goto(route); // overlay would not dismiss cleanly — restore the surface
      }
    } else {
      await page.keyboard.press('Escape').catch(() => {});
      await wait(350);
    }
    idx++;
  }
  return log;
}

const all = [];
const budgetRef = { seen: new Set(), shots: 0 };
for (const route of ROUTES) {
  await goto(route);
  console.log(`\n=== ${route} (full page, incl. below-the-fold) ===`);
  all.push(...await sweep(route, 0, budgetRef));
}

await browser.close();
const flat = all.filter((r) => !r.note.startsWith('skipped'));
const by = (p) => flat.filter((r) => p.test(r.note));
fs.writeFileSync(OUT, JSON.stringify({ clicks: all, summary: {
  total: flat.length,
  unclickable: by(/UNCLICKABLE/).length,
  noEffect: by(/^no visible effect/).length,
  issues: flat.filter((r) => r.issues?.length).length,
  overlaysOpened: flat.filter((r) => r.note.startsWith('opened')).length,
} }, null, 2));

console.log(`\n===== SUMMARY (v2) =====`);
console.log(`clicks        : ${flat.length}`);
console.log(`overlays opened: ${flat.filter((r) => r.note.startsWith('opened')).length}`);
console.log(`unclickable   : ${by(/UNCLICKABLE/).length}`);
console.log(`no effect     : ${by(/^no visible effect/).length}`);
console.log(`raised issues : ${flat.filter((r) => r.issues?.length).length}`);
console.log(`\n-- UNCLICKABLE (real defects if hit-blocked) --`);
for (const r of by(/UNCLICKABLE/)) console.log(`   [${r.route}] ${r.label} :: ${r.note}`);
console.log(`\n-- NO VISIBLE EFFECT --`);
for (const r of by(/^no visible effect/)) console.log(`   [${r.route}] ${r.label}`);
console.log(`\n-- ISSUES --`);
const seenIssue = new Set();
for (const r of flat.filter((x) => x.issues?.length)) {
  const k = r.issues.map((i) => i.text.slice(0, 60)).join('|');
  if (seenIssue.has(k)) continue;
  seenIssue.add(k);
  console.log(`   [${r.route}] ${r.label} :: ${r.issues.map((i) => `${i.kind} ${i.text.slice(0, 80)}`).join(' ; ')}`);
}
console.log('DONE ->', OUT);
