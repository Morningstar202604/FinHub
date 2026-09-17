// Ground-truth render check WITHOUT eyes: assert the live DOM has real data
// (no skeletons, holdings present, market quote non-zero) on the routes that
// feed the showcase. Prints PASS/FAIL per assertion.
import pkg from '/root/.nvm/versions/node/v22.13.1/lib/node_modules/@playwright/cli/node_modules/playwright-core/index.js';
const { chromium } = pkg;
const BASE = 'http://localhost:5173';
const b = await chromium.launch({ chromiumSandbox: false, headless: true, executablePath: '/opt/google/chrome/chrome' });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
await ctx.addInitScript(() => sessionStorage.setItem('finhub_setup_skipped', '1'));
const p = await ctx.newPage();
const results = [];
const ok = (name, cond, extra='') => results.push(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? '  → ' + extra : ''}`);

// --- dashboard ---
await p.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(13000);
const skel = await p.locator('[class*=skeleton]').count();
ok('dashboard: no skeletons', skel === 0, `skeletons=${skel}`);
const dashText = await p.locator('body').innerText();
const holdsSym = ['AAPL','NVDA','TSLA','MSFT','GOOGL'].filter(s => dashText.includes(s));
ok('dashboard: holdings show real symbols', holdsSym.length > 0, holdsSym.join(','));
const netVal = (dashText.match(/USD\s*[\d,]+/i) || dashText.match(/[\d,]+\.\d{2}/)) ? 'present' : 'missing';
ok('dashboard: net value rendered', netVal === 'present', netVal);

// --- market (GOOGL default) ---
await p.goto(BASE + '/market', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(13000);
const mskel = await p.locator('[class*=skeleton]').count();
ok('market: no skeletons', mskel === 0, `skeletons=${mskel}`);
const mText = await p.locator('body').innerText();
const priceEl = (await p.locator('.stock-price').innerText().catch(() => '')) || '';
const okPrice = /^\d{2,4}\.\d{2}$/.test(priceEl.trim()) && priceEl.trim() !== '0.00';
ok('market: quote header non-zero', okPrice, `price="${priceEl.trim()}"`);
const canvas = await p.locator('canvas').count();
ok('market: chart canvas present', canvas > 0, `canvas=${canvas}`);

// --- finance ---
await p.goto(BASE + '/finance', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(8000);
const fskel = await p.locator('[class*=skeleton]').count();
ok('finance: no skeletons', fskel === 0, `skeletons=${fskel}`);

console.log('\n' + results.join('\n'));
const failed = results.filter(r => r.startsWith('FAIL')).length;
console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'}`);
await b.close();
process.exit(failed === 0 ? 0 : 1);
