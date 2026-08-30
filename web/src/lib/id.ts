/**
 * Collision-safe unique id generator.
 *
 * Several chat/market modules previously re-implemented the same
 * `Date.now() + Math.random().toString(36).substr(...)` pattern (with the
 * deprecated `substr` call) for React keys and local message ids. This is the
 * single shared implementation: it prefers the native `crypto.randomUUID()`
 * (available in all modern browsers and secure contexts) and falls back to a
 * timestamp + random tail otherwise.
 */
export function newId(prefix = 'id'): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 11);
  return `${prefix}-${ts}-${rand}`;
}
