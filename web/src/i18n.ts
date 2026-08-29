import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enUS from './locales/en-US.json';
import zhCN from './locales/zh-CN.json';
import jaJP from './locales/ja-JP.json';
import { detectLocale } from './lib/locale';

// Locale resolution (cookie → browser language → English) lives in ./lib/locale,
// shared with the cookie helpers that components use. The cross-tab `storage`
// listener was removed along with localStorage-based locale: locale now rides a
// shared cookie (readable server-side, unlike localStorage); other tabs adopt a
// change on their next navigation.
i18n.use(initReactI18next).init({
  resources: {
    'en-US': { translation: enUS },
    'zh-CN': { translation: zhCN },
    'ja-JP': { translation: jaJP },
  },
  lng: detectLocale(),
  fallbackLng: 'en-US',
  interpolation: { escapeValue: false },
});

export default i18n;
