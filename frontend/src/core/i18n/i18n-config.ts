import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enAlert from './locales/en/alert.json'
import enAuth from './locales/en/auth.json'
import enCamera from './locales/en/camera.json'
import enCommon from './locales/en/common.json'
import enErrors from './locales/en/errors.json'
import enSlot from './locales/en/slot.json'
import enSystem from './locales/en/system.json'
import viAlert from './locales/vi/alert.json'
import viAuth from './locales/vi/auth.json'
import viCamera from './locales/vi/camera.json'
import viCommon from './locales/vi/common.json'
import viErrors from './locales/vi/errors.json'
import viSlot from './locales/vi/slot.json'
import viSystem from './locales/vi/system.json'

export const SUPPORTED_LANGUAGES = ['vi', 'en'] as const
export type Language = (typeof SUPPORTED_LANGUAGES)[number]

export const LANGUAGE_STORAGE_KEY = 'caps.lang'

/**
 * Both languages are bundled statically.
 *
 * A lazy HTTP backend would add a loading state, a failure mode and a round
 * trip to save a few kilobytes of JSON. The dashboard is served off the same
 * small board it monitors; the round trip is the expensive part, not the bytes.
 */
const resources = {
  vi: {
    common: viCommon,
    auth: viAuth,
    camera: viCamera,
    slot: viSlot,
    alert: viAlert,
    system: viSystem,
    errors: viErrors,
  },
  en: {
    common: enCommon,
    auth: enAuth,
    camera: enCamera,
    slot: enSlot,
    alert: enAlert,
    system: enSystem,
    errors: enErrors,
  },
} as const

export function readStoredLanguage(): Language {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return stored === 'en' || stored === 'vi' ? stored : 'vi'
}

void i18n.use(initReactI18next).init({
  resources,
  lng: readStoredLanguage(),
  // Vietnamese is the working language of the building staff who use this;
  // English exists for the competition and for anyone reading the code.
  fallbackLng: 'en',
  defaultNS: 'common',
  ns: Object.keys(resources.vi),
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
})

export default i18n
