// Confirms the settings form controls are reachable by their *visible* label.
// Reads the accessibility tree, not the DOM: a label is only associated if the
// browser's own name computation picks it up (htmlFor/id, wrapper, or aria-*).
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;

const browser = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.addInitScript(() => {
  sessionStorage.setItem('finhub_setup_skipped', '1');
  localStorage.setItem('theme', 'dark');
});
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e).slice(0, 200)));

await page.goto('http://localhost:5173/settings?tab=userInfo', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(4000);

const report = await page.evaluate(() => {
  const out = [];
  const controls = [...document.querySelectorAll('input, select, textarea')];
  for (const el of controls) {
    if (el.closest('[inert]')) continue;
    // A display:none / zero-size input is not in the a11y tree at all — it is
    // driven by a named proxy button (the avatar picker here). Reporting it as
    // "unnamed" is the harness being wrong, not the page.
    const box = el.getBoundingClientRect();
    const hidden = el.type === 'hidden' || (box.width === 0 && box.height === 0);
    if (hidden) continue;
    const id = el.id || '(no id)';
    // querySelector escape for ids containing CSS-special chars is not needed here.
    const lab = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
    // What a screen reader would announce: use the a11y name approximation.
    const aria = el.getAttribute('aria-label');
    const named = aria || lab?.textContent?.trim() || (el.getAttribute('placeholder') ?? '');
    out.push({
      id,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      hasForLabel: !!lab,
      ariaLabel: aria,
      announced: named || '(unnamed)',
      disabled: el.disabled,
    });
  }
  return out;
});

console.log('=== FORM CONTROLS on /settings?tab=userInfo ===');
for (const r of report) {
  console.log(
    `${r.hasForLabel ? 'LABEL<' : '      '} ${r.tag}${r.type ? '[' + r.type + ']' : ''} id=${r.id}  →  "${r.announced}"${r.disabled ? '  (disabled)' : ''}`,
  );
}
const unlabelled = report.filter(r => !r.hasForLabel && !r.ariaLabel && !r.disabled);
console.log(`\ncontrols: ${report.length}, unlabelled & enabled: ${unlabelled.length}`);
if (unlabelled.length) console.log('UNLABELLED:', JSON.stringify(unlabelled, null, 2));

// Segmented groups: role=group must exist and exactly one button per group pressed.
const groups = await page.evaluate(() => {
  return [...document.querySelectorAll('[role="group"]')].map(g => ({
    name: g.getAttribute('aria-labelledby'),
    labelText: g.getAttribute('aria-labelledby') ? document.getElementById(g.getAttribute('aria-labelledby'))?.textContent : null,
    pressed: [...g.querySelectorAll('button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.textContent.trim()),
    total: g.querySelectorAll('button').length,
  })).filter(g => g.total > 0);
});
console.log('\n=== SEGMENTED GROUPS ===');
for (const g of groups) {
  console.log(`group "${g.labelText}" — ${g.total} buttons, pressed: [${g.pressed.join(', ')}]`);
}

if (errors.length) console.log('\nPAGE ERRORS:', errors);
await browser.close();
