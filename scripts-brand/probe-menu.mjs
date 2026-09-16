// Open each dropdown fresh, then hit-test its items while the menu is actually
// open. v2 sweep measured menu items after Escape closed the menu, where Radix
// parks them at pointer-events:none — this confirms they are genuinely usable.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const BASE = 'http://localhost:5173';

const browser = await chromium.launch({
  chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome',
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const page = await ctx.newPage();

const calls = [];
page.on('request', (r) => {
  if (['PATCH', 'POST', 'DELETE', 'PUT'].includes(r.method())) calls.push(`${r.method()} ${r.url().replace(BASE, '').replace('http://localhost:8000', '')}`);
});
const wait = (ms) => page.waitForTimeout(ms);

await page.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4000);

// 1. Open the sidebar workspace/thread options menu.
const options = page.getByRole('button', { name: 'Options' }).first();
console.log('Options triggers found:', await page.getByRole('button', { name: 'Options' }).count());
await options.click({ timeout: 4000 }).catch((e) => console.log('open failed:', String(e).split('\n')[0]));
await wait(900);

const menuItems = await page.$$eval('[role="menuitem"]', (els) => els.map((el) => {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  const hit = document.elementFromPoint(cx, cy);
  return {
    label: (el.textContent || '').trim().slice(0, 40),
    visible: r.width > 0 && r.height > 0 && cs.opacity !== '0',
    pointerEvents: cs.pointerEvents,
    clickable: !!hit && (el === hit || el.contains(hit)),
    blockedBy: (!hit || el === hit || el.contains(hit)) ? null : hit.tagName.toLowerCase(),
  };
}));
console.log('\n-- menu items while OPEN --');
for (const m of menuItems) {
  console.log(`   ${m.clickable ? 'OK  ' : 'BAD '} ${m.label.padEnd(22)} pe=${m.pointerEvents} visible=${m.visible}${m.blockedBy ? ' blocked:' + m.blockedBy : ''}`);
}

// 2. Actually click Pin and read the wire.
const pin = page.locator('[role="menuitem"]', { hasText: /Pin|置顶/ }).first();
const pinCount = await pin.count();
console.log('\nPin item present:', pinCount);
if (pinCount) {
  calls.length = 0;
  const labelBefore = await pin.textContent();
  const err = await pin.click({ timeout: 4000 }).then(() => null, (e) => String(e).split('\n')[0].slice(0, 140));
  await wait(1800);
  console.log('click error :', err ?? 'none');
  console.log('label before:', labelBefore?.trim());
  console.log('mutations   :', calls.length ? calls.join(' , ') : '(none)');
  const toast = await page.locator('[role="status"], [data-sonner-toast], .toast').count();
  console.log('toast nodes :', toast);
}

// 3. Same treatment for Archive.
const page2 = await ctx.newPage();
await page2.goto(BASE + '/chat', { waitUntil: 'domcontentloaded' });
await wait(4000);
const opt2 = page2.getByRole('button', { name: 'Options' }).first();
await opt2.click({ timeout: 4000 }).catch(() => {});
await wait(900);
const arch = page2.locator('[role="menuitem"]', { hasText: /Archive|归档/ }).first();
const archCount = await arch.count();
console.log('\nArchive item present:', archCount);
if (archCount) {
  calls.length = 0;
  const err = await arch.click({ timeout: 4000 }).then(() => null, (e) => String(e).split('\n')[0].slice(0, 140));
  await wait(1500);
  console.log('click error :', err ?? 'none');
  const dialog = await page2.locator('[role="dialog"]').count();
  console.log('confirm dialog:', dialog, '| mutations:', calls.length ? calls.join(' , ') : '(none)');
  if (dialog) {
    const btns = await page2.locator('[role="dialog"] button').allTextContents();
    console.log('dialog buttons:', btns.map((b) => b.trim()).filter(Boolean).slice(0, 8));
  }
}

await browser.close();
console.log('\nMENU PROBE DONE');
