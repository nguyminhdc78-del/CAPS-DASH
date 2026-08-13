import { FullscreenExitOutlined, FullscreenOutlined, GlobalOutlined } from '@ant-design/icons'
import { Button, Empty, Flex, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import { KioskDisabledNotice } from './kiosk-disabled-notice'
import { KioskFloorPanel } from './kiosk-floor-panel'
import { KioskOfflineBanner } from './kiosk-offline-banner'
import { KioskPlateSearch } from './kiosk-plate-search'
import { useKioskSummary } from './use-kiosk-summary'

/** Ticks once a second, shared by the clock and the offline banner's "data
 * is N seconds old" text - one `setInterval` for both instead of two. */
function useNowTick(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function useIsFullscreen(): boolean {
  const [isFullscreen, setIsFullscreen] = useState(() => document.fullscreenElement !== null)
  useEffect(() => {
    const handler = (): void => setIsFullscreen(document.fullscreenElement !== null)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])
  return isFullscreen
}

/** Module scope: touches only `document`, nothing from component state, so
 * there is no reason to recreate it on every render. */
function toggleFullscreen(): void {
  // Graceful no-op when the Fullscreen API is unavailable (older embedded
  // browsers on the kiosk hardware itself) rather than throwing.
  if (!document.fullscreenEnabled) return
  if (document.fullscreenElement) {
    void document.exitFullscreen()
  } else {
    void document.documentElement.requestFullscreen()
  }
}

/**
 * Public lobby display, route `/kiosk`. Unauthenticated - no session, no
 * login redirect, gated server-side by `PUBLIC_KIOSK_ENABLED` instead
 * (`app-router.tsx`, `use-kiosk-summary.ts`).
 *
 * This page shows a customer their own FREE bay codes and, when the backend
 * allows it, lets them search their own plate to find which bay it is in.
 * That is a deliberate, adopted trade, not an oversight: an earlier version
 * of this file described a resident-only view and cited "a public lobby
 * screen showing 'space B-17 is empty'" as the exact thing the privacy tier
 * existed to prevent. That description is no longer true. It is now what
 * this page does, on purpose, because a customer standing in the lobby
 * wanting to know where their own car is parked is the actual product.
 *
 * The two pieces carry very different risk and are not treated the same:
 *   - FREE codes (`kiosk-floor-panel.tsx` / `kiosk-free-codes.tsx`) are
 *     low-risk. An empty bay holds no car; a code here identifies a space,
 *     not a vehicle.
 *   - Plate search (`kiosk-plate-search.tsx`) is where the real risk lives.
 *     Partial match, public, unauthenticated means anyone in the building
 *     can enumerate the car park and locate a specific vehicle. This was
 *     accepted knowingly (`plans/.../plan.md`, "What this deliberately
 *     trades away"), not smuggled in, and it ships with guard rails: a
 *     per-IP rate limit, an audit row written for every single search
 *     (never as-you-type - see `use-kiosk-plate-search.ts`), and a
 *     kill-switch (`PLATE_READING_ENABLED`) that removes the search box
 *     from the DOM entirely rather than showing it disabled or empty.
 *
 * `position: fixed; inset: 0` covers the app's sider/header regardless of
 * whether the router still wraps this route in `<AppLayout>` - route
 * wiring for `/kiosk` belongs to `app-router.tsx`, not to this file, so the
 * "no chrome" requirement is met defensively here rather than assumed from
 * the route tree.
 */
export default function KioskPage(): ReactNode {
  const { t, i18n } = useTranslation('kiosk')
  const { summary, freeCodesByFloor, plateSearchEnabled, isOffline, isDisabled, lastUpdatedAt } =
    useKioskSummary()
  const now = useNowTick(1_000)
  const isFullscreen = useIsFullscreen()

  const toggleLanguage = (): void => {
    void i18n.changeLanguage(i18n.language === 'vi' ? 'en' : 'vi')
  }

  const floors = [...(summary?.by_floor ?? [])].sort((a, b) => compareSlotCodes(a.floor, b.floor))

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'auto',
        padding: 24,
        background: 'var(--ant-color-bg-layout, #f5f5f5)',
        zIndex: 1000,
        // A column so the floor row below can take the leftover height. A
        // lobby screen is mounted and never scrolled, so content hugging the
        // top and leaving the lower half of a 1080p panel empty is wasted
        // wall - the panels grow into it instead.
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Flex justify="space-between" align="center" style={{ marginBottom: 24 }}>
        <Typography.Title level={1} style={{ margin: 0 }}>
          {t('kiosk:title')}
        </Typography.Title>
        <Flex gap={16} align="center">
          <Typography.Title level={3} style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}>
            {dayjs(now).format('HH:mm:ss')}
          </Typography.Title>
          <Button icon={<GlobalOutlined />} onClick={toggleLanguage} aria-label={t('kiosk:languageToggleAriaLabel')}>
            {i18n.language.toUpperCase()}
          </Button>
          {document.fullscreenEnabled && (
            <Button
              icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
              aria-label={isFullscreen ? t('kiosk:fullscreenExit') : t('kiosk:fullscreenEnter')}
            />
          )}
        </Flex>
      </Flex>

      {isDisabled ? <KioskDisabledNotice /> : null}

      {!isDisabled && isOffline && <KioskOfflineBanner lastUpdatedAt={lastUpdatedAt} now={now} />}

      {/* Absent from the DOM when the flag is off - never rendered disabled
          or empty-stated, see this file's top comment and
          `kiosk-plate-search.tsx`. */}
      {!isDisabled && plateSearchEnabled ? (
        <div style={{ marginTop: 16 }}>
          <KioskPlateSearch />
        </div>
      ) : null}

      {isDisabled ? null : floors.length === 0 ? (
        <Flex flex={1} align="center" justify="center">
          <Empty description={t('kiosk:noFloorData')} />
        </Flex>
      ) : (
        // `flex={1}` claims the height the header and search box did not use;
        // `align="stretch"` makes every panel in a row the same height, so two
        // floors with different numbers of free bays do not render as two
        // cards of different sizes.
        <Flex gap={16} wrap flex={1} align="stretch" style={{ marginTop: 16 }}>
          {floors.map((floor) => (
            <div key={floor.floor} style={{ flex: '1 1 320px' }}>
              <KioskFloorPanel floor={floor} freeCodes={freeCodesByFloor[floor.floor] ?? []} />
            </div>
          ))}
        </Flex>
      )}
    </div>
  )
}
