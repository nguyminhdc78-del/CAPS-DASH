import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/core/api/api-error'

/**
 * Turn a backend failure into a sentence a user can read.
 *
 * Localising from the error CODE, never from the server's `message` field:
 * that field is English written for developers and is not translated. A code
 * with no mapping falls back to the generic message rather than showing the
 * user a raw `SLOT_MAP_INVALID`.
 */
export function useErrorMessage(): (error: unknown) => string {
  const { t } = useTranslation('errors')

  return useCallback(
    (error: unknown): string => {
      const code = error instanceof ApiError ? error.code : 'INTERNAL_ERROR'
      const fallback = t('INTERNAL_ERROR')
      const translated = t(code, { defaultValue: '' })

      if (!translated) {
        if (import.meta.env.DEV) {
          // Surfaces gaps while developing instead of at a demo.
          console.warn(`[i18n] no message for error code "${code}"`)
        }
        return fallback
      }
      return translated
    },
    [t],
  )
}
