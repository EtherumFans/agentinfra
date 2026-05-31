// iCoDer i18n — React hook for locale access
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { locales, type Locale, type LocaleDict } from './locales';

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useLocaleStore = create<LocaleState>()(
  persist(
    (set) => ({
      locale: 'zh-CN',
      setLocale: (locale: Locale) => set({ locale }),
    }),
    { name: 'icoder-locale' }
  )
);

export function useT(): LocaleDict {
  const locale = useLocaleStore((s) => s.locale);
  return locales[locale];
}

export { type Locale, type LocaleDict };
