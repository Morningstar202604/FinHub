/// <reference types="vitest/globals" />
import '@testing-library/jest-dom';
// Side-effect import: initializes i18next with the same en-US/zh-CN
// resources the app uses, so `t()` in components returns real strings
// instead of bare key paths under test.
import { preloadAllLocales } from '@/i18n';

// Preload every locale bundle once, up front. In production only the active
// locale is fetched on demand (keeps the critical-path payload lean); tests,
// however, call `i18n.changeLanguage('zh-CN')` synchronously and assert on the
// result, which requires the bundle to already be present so the fast path is
// taken. Awaiting here means tests never race the lazy import().
await preloadAllLocales();

// Mock window.matchMedia for framer-motion
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock IntersectionObserver
class IntersectionObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver;

// Mock ResizeObserver
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
