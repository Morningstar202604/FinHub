/**
 * A focus ring is the mouse cursor for someone navigating by keyboard, so it
 * has to be there for them and absent for everyone else. Both halves break
 * silently and neither is visible from inside a component.
 *
 * The half that broke: Radix hands focus back to the trigger when an overlay
 * closes, and Chromium propagates :focus-visible across a programmatic focus
 * move. So a menu opened and dismissed entirely with the mouse left its trigger
 * ringed until the next click, on every dropdown in the app. Nothing about that
 * is expressible in CSS, and a screenshot of the ring looks identical whether
 * it was earned by a keystroke or not. This is the only place the difference
 * can be measured.
 *
 * The other half is the one an over-eager fix takes out. Suppressing the
 * restore unconditionally would pass every mouse assertion below and leave
 * keyboard users pressing Escape into nowhere, so the keyboard cases are not
 * balance: they are the thing most at risk.
 */
import { test, expect, mockAPI } from './fixtures.js';

// The account button in the sidebar footer, chosen because it is a plain
// DropdownMenu over the shared ui/ wrapper -- whatever is true here is true of
// the other call sites, which is the point of fixing it in the wrapper.
const ROW = '.sidebar-account-row';

// Somewhere in the page body with nothing interactive under it.
const EMPTY = { x: 760, y: 300 };

/** Is a focus indicator actually painted on the element that holds focus? */
async function ringed(page) {
  return page.evaluate((sel) => {
    const row = document.querySelector(sel);
    if (!row) throw new Error('the account row is not on the page');
    return document.activeElement === row && row.matches(':focus-visible');
  }, ROW);
}

test.beforeEach(async ({ page }) => {
  await mockAPI(page);
  await page.goto('/dashboard');
  await expect(page.locator(ROW)).toBeVisible();
});

test.describe('a flow driven entirely by the mouse', () => {
  test('leaves no ring after choosing a menu item', async ({ page }) => {
    await page.click(ROW);
    // The regression lived here: this close returns focus to the trigger.
    await page.locator('[role="menuitem"]').first().click();
    await expect.poll(() => ringed(page)).toBe(false);
  });

  test('leaves no ring after dismissing the menu', async ({ page }) => {
    await page.click(ROW);
    await page.mouse.click(EMPTY.x, EMPTY.y);
    await expect.poll(() => ringed(page)).toBe(false);
  });

  test('leaves no ring on the click that opened it', async ({ page }) => {
    await page.click(ROW);
    await page.click(ROW);
    await expect.poll(() => ringed(page)).toBe(false);
  });
});

test.describe('a keyboard user still gets an indicator', () => {
  test('when focus lands on the row', async ({ page }) => {
    await page.keyboard.press('Escape');
    await page.locator(ROW).evaluate((el) => el.focus());
    await expect.poll(() => ringed(page)).toBe(true);
  });

  test('when they open the menu and press Escape', async ({ page }) => {
    await page.locator(ROW).evaluate((el) => el.focus());
    await page.keyboard.press('Enter');
    await expect(page.locator('[role="menuitem"]').first()).toBeVisible();
    // Escape must put them back where they were, still able to see where.
    await page.keyboard.press('Escape');
    await expect.poll(() => ringed(page)).toBe(true);
  });
});

/**
 * The chart half. Inside an SVG, Chromium paints its own focus ring on plain
 * :focus -- it does not gate that on :focus-visible the way it does for HTML.
 * So a mouse click on a chart draws a ring where the same click on a button
 * draws nothing, and no amount of :focus-visible styling reaches it.
 *
 * Which node the click lands on is the part that is easy to get wrong: recharts
 * 3.8 stacks its z-index layers as `<g tabindex="-1">` inside the surface, so a
 * click on a bar focuses the layer, not the surface. The rule covering that is
 * one space in a selector (`svg :focus...`) and reads like a typo. It shipped
 * missing once and took three rounds of screenshots to find, with the whole
 * unit suite green throughout: jsdom does not paint UA outlines, so this is the
 * only place the difference exists.
 *
 * The clicks below have to be real. A programmatic .focus() matches
 * :focus-visible and is caught by the tabindex="-1" rule instead, which passes
 * whether or not the rule under test is present.
 *
 * The fixture is hand-built rather than a rendered chart on purpose: what is
 * under test is the stylesheet, and coupling it to market-data mocks would let
 * it pass vacuously the day that data stops arriving.
 */
const BAR = '#chart-fixture rect';
const BEFORE = '#before-fixture';
const PLAIN = '#plain-fixture';

// Where the fixture sits, so a click can be aimed at plot space with no bar
// under it -- the other way a chart takes focus from the mouse.
const CHART = { x: 600, y: 200, w: 200, h: 100 };
const BAR_BOX = { x: 10, y: 10, w: 100, h: 40 };
const EMPTY_PLOT = { x: CHART.x + CHART.w - 20, y: CHART.y + CHART.h - 20 };

/** A recharts surface, reduced to the parts the focus rules actually select. */
async function mountChartFixture(page, chart, bar) {
  await page.evaluate(({ chart, bar }) => {
    const NS = 'http://www.w3.org/2000/svg';
    const fixed = (css) => `position:fixed;z-index:9999;${css}`;

    // Tab lands here first, so the next Tab is a real keyboard entry into the
    // chart rather than a programmatic focus that would prove nothing.
    const before = document.createElement('button');
    before.id = 'before-fixture';
    before.type = 'button';
    before.textContent = 'before';
    before.setAttribute('style', fixed(`top:${chart.y - 40}px;left:${chart.x}px`));

    const svg = document.createElementNS(NS, 'svg');
    svg.id = 'chart-fixture';
    svg.setAttribute('class', 'recharts-surface');
    svg.setAttribute('role', 'application');
    svg.setAttribute('tabindex', '0');
    svg.setAttribute('style', fixed(`top:${chart.y}px;left:${chart.x}px;width:${chart.w}px;height:${chart.h}px`));

    const layer = document.createElementNS(NS, 'g');
    layer.setAttribute('class', 'recharts-zIndex-layer_300');
    layer.setAttribute('tabindex', '-1');
    const rect = document.createElementNS(NS, 'rect');
    for (const [k, v] of [['x', bar.x], ['y', bar.y], ['width', bar.w], ['height', bar.h]]) {
      rect.setAttribute(k, String(v));
    }
    rect.setAttribute('fill', 'currentColor');
    layer.appendChild(rect);
    svg.appendChild(layer);

    // The control the chart surface has to agree with: one baseline rule
    // serves both, and this is what proves it still does.
    const plain = document.createElement('button');
    plain.id = 'plain-fixture';
    plain.type = 'button';
    plain.textContent = 'reference';
    plain.setAttribute('style', fixed(`top:${chart.y + chart.h + 20}px;left:${chart.x}px`));

    document.body.append(before, svg, plain);
  }, { chart, bar });
}

/** What is focused right now, and the outline actually computed on it. */
async function focused(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName,
      tabindex: el.getAttribute('tabindex'),
      style: cs.outlineStyle,
      width: cs.outlineWidth,
      color: cs.outlineColor,
    };
  });
}

test.describe('a chart clicked with the mouse', () => {
  test.beforeEach(async ({ page }) => {
    await mountChartFixture(page, CHART, BAR_BOX);
  });

  test('leaves no ring on the layer a click on a bar lands in', async ({ page }) => {
    await page.locator(BAR).click();
    const el = await focused(page);
    // If this is the surface, the fixture stopped reproducing the real bug.
    expect({ tag: el.tag, tabindex: el.tabindex }).toEqual({ tag: 'g', tabindex: '-1' });
    // `auto` is the UA ring, in a blue this product uses nowhere.
    expect(el.style).toBe('none');
  });

  test('leaves no ring on the surface a click on empty plot space lands in', async ({ page }) => {
    await page.mouse.click(EMPTY_PLOT.x, EMPTY_PLOT.y);
    const el = await focused(page);
    expect(el.tag).toBe('svg');
    expect(el.style).toBe('none');
  });
});

test.describe('a chart reached by keyboard', () => {
  test.beforeEach(async ({ page }) => {
    await mountChartFixture(page, CHART, BAR_BOX);
  });

  test('is a visible tab stop wearing the same ring as every other control', async ({ page }) => {
    await page.locator(BEFORE).focus();
    await page.keyboard.press('Tab');

    const surface = await focused(page);
    expect(surface.tag).toBe('svg');
    expect(surface.style).toBe('solid');

    await page.locator(PLAIN).focus();
    const plain = await focused(page);
    expect(plain.style).toBe('solid');
    // One baseline rule serves both; drift here means a chart grew its own.
    expect(surface.color).toBe(plain.color);
    expect(surface.width).toBe(plain.width);
  });
});
