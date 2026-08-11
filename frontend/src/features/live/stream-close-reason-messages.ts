import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Localises a WS close reason / stream error code, from the `live` namespace.
 *
 * Parallel to `useErrorMessage` in core/i18n, but not built on it: a stream
 * error has no HTTP response behind it, so it is never an `ApiError`, and
 * that hook only knows how to read one of those. Same principle either way -
 * translate from the machine code, never show it or a raw exception message.
 */
export function useStreamErrorMessage(): (code: string) => string {
  const { t } = useTranslation('live')

  return useCallback(
    (code: string): string => {
      const key = `closeReason${toPascalCase(code)}`
      const translated = t(key, { defaultValue: '' })
      if (translated) return translated
      if (import.meta.env.DEV) {
        console.warn(`[i18n] no live close-reason message for "${code}"`)
      }
      return t('closeReasonUnknown')
    },
    [t],
  )
}

function toPascalCase(snakeCase: string): string {
  return snakeCase
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')
}
