/**
 * Which input device the user last reached for.
 *
 * Chromium propagates `:focus-visible` across a *programmatic* focus move: an
 * element focused by script inherits the state of the element focus came from.
 * Radix overlays hand focus back to their trigger on close, so a menu opened
 * and dismissed entirely with the mouse still lights that trigger's focus ring,
 * and leaves it lit until the next click. Overlays consult this to skip the
 * restore when no keyboard was involved.
 */

/** Held alone, a modifier is someone reaching for Cmd-Tab, not navigating. */
const MODIFIERS = new Set(['Meta', 'Control', 'Alt', 'Shift']);

let pointer = false;

if (typeof window !== 'undefined') {
  // Capture phase: a handler that stops propagation must not be able to hide
  // the interaction from this.
  window.addEventListener('pointerdown', () => { pointer = true; }, true);
  window.addEventListener(
    'keydown',
    (event) => {
      if (!MODIFIERS.has(event.key)) pointer = false;
    },
    true,
  );
}

export function lastInputWasPointer(): boolean {
  return pointer;
}
