import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enUS from './locales/en-US.json';
import { detectLocale } from './lib/locale';

// Locale resolution (cookie → browser language → English) lives in ./lib/locale,
// shared with the cookie helpers that components use. The cross-tab `storage`
// listener was removed along with localStorage-based locale: locale now rides a
// shared cookie (readable server-side, unlike localStorage); other tabs adopt a
// change on their next navigation.
//
// Only the default locale (en-US) ships in the entry bundle. zh-CN and ja-JP
// load on demand via dynamic import() the first time they are needed, keeping
// the critical-path payload lean — ja-JP alone is ~46 kB gz and zh-CN ~44 kB gz.
// The ceiling in scripts/check-critical-path.mjs is deliberately thin; every
// extra locale must earn its place in the initial bundle.
const LAZY_LOCALES: Record<string, () => Promise<{ default: Record<string, unknown> }>> = {
  'zh-CN': () => import('./locales/zh-CN.json'),
  'ja-JP': () => import('./locales/ja-JP.json'),
};

let readyPromise: Promise<typeof i18n> | null = null;

async function ensureLocale(lng: string): Promise<void> {
  if (i18n.hasResourceBundle(lng, 'translation')) return;
  const loader = LAZY_LOCALES[lng];
  if (!loader) return;
  i18n.addResourceBundle(lng, 'translation', (await loader()).default, true, true);
}

/**
 * Bootstrap i18next. en-US is bundled, so for that locale this resolves without
 * any network work; when zh-CN/ja-JP is the active locale its bundle is fetched
 * before the first render so there is no English flash.
 */
export function initI18n(): Promise<typeof i18n> {
  if (readyPromise) return readyPromise;
  readyPromise = (async () => {
    const detected = detectLocale();
    if (detected !== 'en-US') await ensureLocale(detected);

    await i18n.use(initReactI18next).init({
      resources: { 'en-US': { translation: enUS } },
      lng: detected,
      fallbackLng: 'en-US',
      interpolation: { escapeValue: false },
    });

    // Load a lazy locale before switching so a language change never renders
    // untranslated keys. Eager/present locales take a synchronous fast path
    // that preserves the pre-lazy behavior callers (and unit tests) rely on:
    // `i18n.language` is set before the returned promise settles.
    const changeLanguage = i18n.changeLanguage.bind(i18n);
    i18n.changeLanguage = ((lng, callback, options) => {
      const target = typeof lng === 'string' ? lng : (lng ?? i18n.language);
      if (target === 'en-US' || i18n.hasResourceBundle(target, 'translation')) {
        return changeLanguage(lng, callback, options);
      }
      return ensureLocale(target).then(() => changeLanguage(lng, callback, options));
    }) as typeof i18n.changeLanguage;

    return i18n;
  })();
  return readyPromise;
}

/**
 * Load every locale bundle. The test setup calls this so `t(key, { lng })`
 * coverage across all three locales and synchronous changeLanguage keep
 * working exactly as they did when every locale was statically imported.
 */
export async function preloadAllLocales(): Promise<void> {
  await initI18n();
  await Promise.all(Object.keys(LAZY_LOCALES).map((lng) => ensureLocale(lng)));
}

// Side-effect boot for anything that imports './i18n' without awaiting
// (legacy call sites). Production boots via main.tsx awaiting initI18n(); the
// promise is cached so both paths share one initialization.
initI18n();

export default i18n;
