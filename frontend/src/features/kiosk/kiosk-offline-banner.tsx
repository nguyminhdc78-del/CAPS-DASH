import { Alert } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Formats an age in whole seconds as "45s" / "12m" / "3h" - unlabelled unit
 * letters, matching how the rest of the app already shows raw units (e.g.
 * `camera:processMs` renders "42 ms" untranslated). Deliberately coarse: a
 * kiosk viewer needs "a few minutes old" at a glance, not a precise
 * countdown, and coarse buckets don't need re-rendering every second.
 */
function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h`
}

/**
 * Shown whenever the last poll to `/summary` failed. The numbers on screen
 * are NOT cleared for this - see `use-kiosk-summary.ts` - because a
 * stale-but-labelled count is more useful on a lobby display than a blank
 * spinner: a driver can still act on "23 free, as of 2 minutes ago" while a
 * blank screen tells them nothing and looks broken either way.
 */
export function KioskOfflineBanner({
  lastUpdatedAt,
  now,
}: {
  lastUpdatedAt: Date | null
  now: Date
}): ReactNode {
  const { t } = useTranslation('kiosk')

  const description =
    lastUpdatedAt === null
      ? t('kiosk:offlineNoDataYet')
      : t('kiosk:offlineDataAge', {
          age: formatAge(Math.max(0, Math.round((now.getTime() - lastUpdatedAt.getTime()) / 1000))),
        })

  return (
    <Alert type="warning" showIcon banner message={t('kiosk:offlineTitle')} description={description} />
  )
}
