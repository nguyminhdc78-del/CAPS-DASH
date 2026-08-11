import { ConfigProvider } from 'antd'
import enUS from 'antd/locale/en_US'
import viVN from 'antd/locale/vi_VN'
import dayjs from 'dayjs'
import 'dayjs/locale/en'
import 'dayjs/locale/vi'
import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useThemeConfig } from '@/core/theme/use-theme-config'
import { LANGUAGE_STORAGE_KEY, readStoredLanguage } from './i18n-config'
import type { Language } from './i18n-config'

interface LocaleContextValue {
  language: Language
  setLanguage: (language: Language) => void
}

export const LocaleContext = createContext<LocaleContextValue | null>(null)

const ANTD_LOCALES = { vi: viVN, en: enUS } as const

/**
 * One place changes the language.
 *
 * Three separate systems carry their own locale - i18next for our strings,
 * antd for its built-in component text, dayjs for dates. Changing them from
 * three call sites is how a UI ends up with Vietnamese labels above an English
 * date picker, so they are driven together from here.
 */
export function LocaleProvider({ children }: { children: ReactNode }): ReactNode {
  const { i18n } = useTranslation()
  const [language, setLanguageState] = useState<Language>(readStoredLanguage)
  const themeConfig = useThemeConfig()

  useEffect(() => {
    void i18n.changeLanguage(language)
    dayjs.locale(language)
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
    document.documentElement.lang = language
  }, [language, i18n])

  const setLanguage = useCallback((next: Language) => setLanguageState(next), [])

  const value = useMemo<LocaleContextValue>(
    () => ({ language, setLanguage }),
    [language, setLanguage],
  )

  return (
    <LocaleContext value={value}>
      <ConfigProvider locale={ANTD_LOCALES[language]} theme={themeConfig}>
        {children}
      </ConfigProvider>
    </LocaleContext>
  )
}
