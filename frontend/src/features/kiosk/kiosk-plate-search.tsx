import { Alert, Flex, Input, Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/core/api/api-error'
import { KIOSK_SEARCH_CLEAR_MS } from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { KioskPlateResult } from './kiosk-plate-result'
import { MIN_PLATE_QUERY_LENGTH, useKioskPlateSearch } from './use-kiosk-plate-search'

// Matches `public_kiosk_window_s`'s default (`plan.md`) - used only when a
// 429 response is missing `details.retry_after_s`, which should not happen
// against a conforming backend but must not crash the display if it does.
const RATE_LIMIT_FALLBACK_S = 60

/**
 * The public plate search box - the kiosk's HUD hero (styled by `.kiosk-hud`
 * in droom.css: a plate-shaped, neon-edged field with a radar sweep while the
 * request is genuinely in flight - no fake delay, `isFetching` drives it).
 *
 * Rendered by `kiosk-page.tsx` only when the backend's `plate_search_enabled`
 * is true - never mounted disabled or empty-stated for a flag that is off,
 * because a box that can only ever return nothing is worse than no box.
 *
 * Submit-only, never as-you-type (`onSearch`, not `onChange`): every request
 * to `/public/plates/search` is written to the anonymous audit log, so firing
 * one per keystroke would turn "who searched for what" into noise - see
 * `use-kiosk-plate-search.ts`.
 *
 * A lobby display is shared hardware: the submitted query, the rendered result
 * AND the still-visible typed text all clear themselves `KIOSK_SEARCH_CLEAR_MS`
 * after a search - clearing only the result and leaving the plate in the box
 * would still hand it to the next person. Resets on every new search; the
 * timer is cancelled on unmount so no stray timeout outlives the component.
 */
export function KioskPlateSearch(): ReactNode {
  const { t } = useTranslation('kiosk')
  const toMessage = useErrorMessage()

  const [typed, setTyped] = useState('')
  const [submitted, setSubmitted] = useState('')

  const { data, error, isFetching } = useKioskPlateSearch(submitted)

  useEffect(() => {
    if (submitted.trim().length < MIN_PLATE_QUERY_LENGTH) return undefined
    const timerId = window.setTimeout(() => {
      // Both cleared together: the result disappearing but the plate still
      // sitting in the box would still leak it to the next person at the
      // screen - see this file's top comment.
      setSubmitted('')
      setTyped('')
    }, KIOSK_SEARCH_CLEAR_MS)
    return () => window.clearTimeout(timerId)
  }, [submitted])

  const tooShort = typed.trim().length > 0 && typed.trim().length < MIN_PLATE_QUERY_LENGTH
  const searched = submitted.trim().length >= MIN_PLATE_QUERY_LENGTH
  const matches = data?.matches ?? []
  const rateLimited = error instanceof ApiError && error.status === 429
  // A genuine failure (network, 5xx) is distinct from a clean "no matches" -
  // conflating them would tell a customer their plate was not found when the
  // truth is the search never ran.
  const otherError = error !== null && !rateLimited
  const retryAfterSeconds =
    rateLimited && error instanceof ApiError && typeof error.details.retry_after_s === 'number'
      ? error.details.retry_after_s
      : RATE_LIMIT_FALLBACK_S
  const scanning = searched && isFetching

  return (
    <div className={`kiosk-hud${scanning ? ' is-scanning' : ''}`}>
      <Input.Search
        size="large"
        allowClear
        loading={scanning}
        enterButton={t('kiosk:searchButton')}
        aria-label={t('kiosk:searchAriaLabel')}
        placeholder={t('kiosk:searchPlaceholder')}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        onSearch={(value) => setSubmitted(value)}
      />

      <Flex
        className="kiosk-result"
        vertical
        gap={12}
        align="center"
        style={{ marginTop: 16 }}
      >
        {tooShort && (
          <Typography.Text type="secondary" style={{ fontSize: 18 }}>
            {t('kiosk:tooShort', { min: MIN_PLATE_QUERY_LENGTH })}
          </Typography.Text>
        )}

        {rateLimited && (
          // A lobby screen has no `App.useApp()` message host worth relying on,
          // and a toast is unreadable at 2m - render inline instead.
          <Alert type="warning" showIcon message={t('kiosk:rateLimited', { seconds: retryAfterSeconds })} />
        )}

        {otherError && <Alert type="error" showIcon message={toMessage(error)} />}

        {!rateLimited && !otherError && searched && !isFetching && matches.length === 0 && (
          <Flex vertical gap={4} align="center">
            <Typography.Text style={{ fontSize: 18 }}>
              {t('kiosk:noMatches', { query: data?.query ?? submitted })}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 18 }}>
              {t('kiosk:noMatchesHint')}
            </Typography.Text>
          </Flex>
        )}

        {matches.map((match) => (
          <KioskPlateResult key={`${match.slot_code}-${match.read_at}`} match={match} />
        ))}
      </Flex>
    </div>
  )
}
